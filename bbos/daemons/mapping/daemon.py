#!/usr/bin/env python3
import os
import time
from pathlib import Path

import numpy as np

# --- PyCUDA ---
import pycuda.autoinit               # creates a context on device 0
import pycuda.driver as cuda
from pycuda.compiler import SourceModule
import pycuda.gpuarray as gpuarray

# --- your I/O/config layer ---
from bbos import Writer, Reader, Config, Type

CFG  = Config('mapping')
CFG_D = Config('depth')
CFG_P = Config('points')
CFG_S = Config('slam')

# Optional: pick a device via environment, e.g. CUDA_DEVICE=0
# (pycuda.autoinit already picks device 0; use explicit context creation if needed)

def main():
    assert CFG_P.num_points % 32 == 0, "CFG_P.num_points must be a multiple of 32"

    # --- Build CUDA module ---
    # Save the CUDA kernels I provided earlier into 'voxel_map.cu'
    kernel_src = Path("voxel_map.cu").read_text()
    # You can add '-arch=sm_XX' to match your GPU (e.g., sm_60, sm_75, sm_86)
    mod = SourceModule(kernel_src, options=["-O3", "-std=c++11"])
    k_update = mod.get_function("update_logodds_hash")
    k_clamp  = mod.get_function("clamp_logodds_n")  # bounded clamp variant

    stream = cuda.Stream()

    # --- Host buffers (same shapes/dtypes as before) ---
    origins   = np.zeros((CFG_P.num_points, 4), dtype=np.float32)
    endpoints = np.zeros((CFG_P.num_points, 4), dtype=np.float32)

    # --- Device buffers ---
    origins_d   = gpuarray.to_gpu(origins)     # will be updated in-place
    endpoints_d = gpuarray.to_gpu(endpoints)   # will be updated in-place

    M = int(CFG.M)  # hash table capacity
    keys_d    = gpuarray.empty(M, dtype=np.uint64)
    logodds_d = gpuarray.zeros(M, dtype=np.int32)

    # Initialize keys to EMPTY_KEY64 (0xFF...FF) efficiently on device
    cuda.memset_d8(keys_d.gpudata, 0xFF, keys_d.nbytes)

    with Reader('slam.pose') as r_pose, \
         Reader('camera.points') as r_points, \
         Writer('mapping.voxels', Type('mapping_voxels')) as w_voxels:

        # Initialize the writer's host view to match device state
        w_voxels._buf[0]['keys'].fill(np.uint64(0xFFFFFFFFFFFFFFFF))
        w_voxels._buf[0]['logodds'].fill(np.int32(0))

        T_origin_base = CFG_L.T_origin_base({'x': 0, 'y': 0, 'theta': 0})
        origin = np.zeros(3, dtype=np.float32)

        wg = 32  # threads per block to mimic your OpenCL local size
        block_update = (wg, 1, 1)

        block_clamp = (256, 1, 1)
        grid_clamp = ((M + block_clamp[0] - 1) // block_clamp[0], 1, 1)

        while True:
            # Update origin pose if available
            if r_pose.ready():
                T_origin_base = CFG_L.T_origin_base(r_pose.data)
                # compose pose with depth->camera transform and evaluate at (0,0,0)
                origin = (T_origin_base @ CFG_D.T_base_cam)(np.zeros(3)).astype(np.float32)
                origins[:, :3] = origin  # same origin for all rays

            # Update endpoints if available and run kernels
            if r_points.ready():
                endpoints[:, :3] = T_origin_base(r_points.data['points']).astype(np.float32)
                n_valid = int(r_points.data['num_points'])

                # HtoD copies (async)
                cuda.memcpy_htod_async(origins_d.gpudata, origins, stream)
                cuda.memcpy_htod_async(endpoints_d.gpudata, endpoints, stream)

                # Round up global size to multiple of wg
                global_size = ((n_valid + wg - 1) // wg) * wg
                grid_update = (global_size // wg, 1, 1)

                # Launch update_logodds_hash
                k_update(
                    origins_d.gpudata,
                    endpoints_d.gpudata,
                    np.float32(CFG.voxel_size),
                    np.int32(CFG.max_steps),
                    keys_d.gpudata,
                    logodds_d.gpudata,
                    np.uint64(CFG.M),
                    np.int32(CFG.hit_inc),
                    np.int32(CFG.miss_dec),
                    np.int32(n_valid),
                    np.float32(CFG.decay_lambda),
                    np.float32(CFG.min_hit),
                    block=block_update, grid=grid_update, stream=stream
                )

                # Clamp (bounded kernel variant)
                k_clamp(
                    logodds_d.gpudata,
                    np.int32(CFG.min_logodds),
                    np.int32(CFG.max_logodds),
                    np.int32(M),
                    block=block_clamp, grid=grid_clamp, stream=stream
                )

            # Copy results back to your writer’s buffers
            with w_voxels.buf() as b:
                cuda.memcpy_dtoh_async(b['keys'],    keys_d.gpudata,    stream)
                cuda.memcpy_dtoh_async(b['logodds'], logodds_d.gpudata, stream)
                stream.synchronize()

            # Optional: throttle / exit condition
            # time.sleep(0.001)

if __name__ == "__main__":
    main()
