#!/usr/bin/env python3
import numpy as np
import pyopencl as cl
from pathlib import Path
import time
import os
from bbos import Writer, Reader, Config, Type
os.environ['PYOPENCL_CTX'] = '0'
CFG = Config('mapping')
CFG_D = Config('depth')
CFG_P = Config('points')
CFG_L = Config('localizer')
CFG_S = Config('segmenter')

def main():
    assert CFG_P.num_points % 32 == 0, "CFG_P.num_points must be a multiple of 32"
    # OpenCL context
    ctx = cl.create_some_context()
    queue = cl.CommandQueue(ctx)
    mf = cl.mem_flags

    origins = np.zeros((CFG_P.num_points,4), dtype=np.float32)   # all rays from (0,0,0)
    origins_buf = cl.Buffer(ctx, mf.READ_ONLY | mf.COPY_HOST_PTR, hostbuf=origins)
    endpoints = np.zeros((CFG_P.num_points, 4), dtype=np.float32)
    endpoints_buf = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=endpoints)

    sem_mask = np.zeros(1, dtype=Type('segmenter_mask').dtype)['mask'].squeeze()
    sem_mask_buf = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=sem_mask)

    with Reader('localizer.pose') as r_pose, \
         Reader('camera.points') as r_points, \
         Reader('segmenter.mask') as r_mask, \
         Writer('mapping.voxels', Type('mapping_voxels')) as w_voxels:

        w_voxels._buf[0]['keys'].fill(np.uint64(0xffffffffffffffff))
        keys_buf = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=w_voxels._buf[0]['keys'])
        logodds_buf = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=w_voxels._buf[0]['logodds'])
        key_masks_buf = cl.Buffer(ctx, mf.READ_WRITE | mf.COPY_HOST_PTR, hostbuf=w_voxels._buf[0]['key_masks'])
        # Build kernel
        kernel_src = Path("voxel_map.cl").read_text()
        prg = cl.Program(ctx, kernel_src).build()

        T_origin_base = CFG_L.T_origin_base({'x':0, 'y':0, 'theta':0})
        origin = np.zeros(3)
        while True:
            if r_mask.ready():
                cl.enqueue_copy(queue, sem_mask_buf, r_mask.data['mask'])
            if r_pose.ready():
                T_origin_base = CFG_L.T_origin_base(r_pose.data)
                origin = (T_origin_base @ CFG_D.T_base_cam)(np.zeros(3))
                origins[:, :3] = origin
            if r_points.ready():
                endpoints[:, :3] = T_origin_base(r_points.data['points']).astype(np.float32)
                n_valid = int(r_points.data['num_points'])
                cl.enqueue_copy(queue, endpoints_buf, endpoints)
                cl.enqueue_copy(queue, origins_buf, origins)

                wg = 32
                global_size = ((n_valid + wg - 1)//wg)*wg
                # Launch kernel
                prg.update_logodds_hash(queue, (global_size,), (wg,),
                                        origins_buf, endpoints_buf, sem_mask_buf,
                                        np.float32(CFG.voxel_size), np.int32(CFG.max_steps),
                                        keys_buf, logodds_buf, key_masks_buf,
                                        np.uint64(CFG.M),
                                        np.int32(CFG.hit_inc), np.int32(CFG.miss_dec),
                                        np.int32(n_valid), np.float32(CFG.decay_lambda), np.float32(CFG.min_hit))
                prg.clamp_logodds(queue, (CFG.M,), None, logodds_buf, np.int32(CFG.min_logodds), np.int32(CFG.max_logodds))
            # Copy results back
            with w_voxels.buf() as b:
                cl.enqueue_copy(queue, b['keys'], keys_buf).wait()
                cl.enqueue_copy(queue, b['logodds'], logodds_buf).wait()
                cl.enqueue_copy(queue, b['key_masks'], key_masks_buf).wait()

if __name__=="__main__":
    main()