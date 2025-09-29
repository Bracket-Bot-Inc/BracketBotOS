from bbos import Reader, Writer, Type, Config
import cv2
import numpy as np
from pathlib import Path
import time

cv2.ocl.setUseOpenCL(True)

CFG = Config("stereo")
CFG_D = Config("depth")
CFG_P = Config("points")

def lr_consistency_mask(dL, dR, tol=1.0):
    """
    dL,dR disparity in pixels (same rectified geometry). NaN for invalid.
    Returns mask True=keep.
    """
    H, W = dL.shape
    xs = np.arange(W)[None, :].repeat(H, 0)
    # project left pixel x to right image
    xr = xs - dL
    xr_round = np.rint(xr).astype(np.int32)
    valid = (xr_round >= 0) & (xr_round < W) & np.isfinite(dL) & np.isfinite(dR)
    # fetch R disparity at projected coordinate
    dR_samp = np.full_like(dL, np.nan, dtype=np.float32)
    dR_samp[valid] = dR[ np.arange(H)[:,None][valid], xr_round[valid] ]
    # cross-check
    ok = np.abs(dL + dR_samp) <= tol
    mask = np.isfinite(dL) & ok
    return mask

def disparity_to_camera_points(disp: np.ndarray, Q: np.ndarray):
    h, w = disp.shape

    valid = (disp > (CFG_D.min_disp + 0.5))
    if not np.any(valid):
        return np.empty((0, 3)), np.empty((0,), dtype=np.uint32)

    # precompute linear indices
    lin = np.arange(h*w, dtype=np.int32).reshape(h, w)

    # subsample
    stride = CFG_P.stride
    if stride > 1:
        mask = np.zeros_like(valid, dtype=bool)
        mask[::stride, ::stride] = True
        sel = valid & mask
    else:
        sel = valid

    # project and gather
    pts_cam = cv2.reprojectImageTo3D(disp, Q)[sel] / 1000.0
    idx = lin[sel].ravel()                          # <- minimal mapping back to image

    # distance filter (propagate mapping)
    dist_m = np.linalg.norm(pts_cam, axis=1)
    keep = dist_m < CFG_P.max_range
    pts_cam = pts_cam[keep]
    idx     = idx[keep]

    return pts_cam, idx



def main():
    (
        mtx_l,
        dist_l,
        mtx_r,
        dist_r,
        R1,
        R2,
        P1_cam,
        P2_cam,
        Q,
        baseline_m,
        fx_ds,
    ) = CFG_D.camera_cal()

    # Calculate correct dimensions based on downsampled stereo frame
    # The stereo frame contains both cameras side by side, so width needs to be halved
    img_w = CFG.width // 2

    # Pre-compute rectification maps outside the loop
    map1x, map1y = cv2.fisheye.initUndistortRectifyMap(
        mtx_l, dist_l, R1, P1_cam, (img_w, CFG.height), cv2.CV_32FC1
    )
    map2x, map2y = cv2.fisheye.initUndistortRectifyMap(
        mtx_r, dist_r, R2, P2_cam, (img_w, CFG.height), cv2.CV_32FC1
    )
    
    # Convert maps to UMat for OpenCL acceleration
    map1x_gpu = cv2.UMat(map1x)
    map1y_gpu = cv2.UMat(map1y)
    map2x_gpu = cv2.UMat(map2x)
    map2y_gpu = cv2.UMat(map2y)
    
    # Initialize stereo matcher outside the loop
    stereo_bm = cv2.StereoSGBM_create(numDisparities=CFG_D.num_disp, blockSize=CFG_D.window_size)
    stereo_bm.setMinDisparity(CFG_D.min_disp)
    stereo_bm.setUniquenessRatio(CFG_D.uniqueness)
    stereo_bm.setSpeckleWindowSize(CFG_D.speckle_window)
    stereo_bm.setSpeckleRange(CFG_D.speckle_range)
    stereo_bm.setPreFilterCap(CFG_D.pre_filter_cap)
    
    # Pre-calculate stereo parameters

    with Reader('camera.jpeg') as r_jpeg, \
            Writer('camera.depth', Type("camera_depth")) as w_depth, \
            Writer('camera.rect', Type("camera_rect")) as w_rect, \
            Writer('camera.points', Type("camera_points")) as w_points:
        
        print(f"OpenCL available: {cv2.ocl.haveOpenCL()}", flush=True)
        if cv2.ocl.haveOpenCL():
            print(f"OpenCL device: {cv2.ocl.Device.getDefault().name()}", flush=True)
        print('starting depth', flush=True)

        depth_mm = None
        pts_cam = None
        pts_rgb = None
        left_rect = None
        idx = None
        t0 = time.time()
        while True:
            if r_jpeg.ready():
                # Decode and split stereo image
                stereo = cv2.imdecode(r_jpeg.data["jpeg"], cv2.IMREAD_COLOR)
                if stereo is not None:
                    left  = cv2.UMat(stereo[:, img_w:])
                    right = cv2.UMat(stereo[:, :img_w])
                    # Rectify using pre-computed maps (OpenCL accelerated)
                    left_r  = cv2.remap(left,  map1x_gpu, map1y_gpu, cv2.INTER_LINEAR)
                    right_r = cv2.remap(right, map2x_gpu, map2y_gpu, cv2.INTER_LINEAR)
                    
                    # Resize (OpenCL accelerated)
                    left_ds  = cv2.resize(left_r,  (CFG_D.width_D, CFG_D.height_D), interpolation=cv2.INTER_AREA)
                    right_ds = cv2.resize(right_r, (CFG_D.width_D, CFG_D.height_D), interpolation=cv2.INTER_AREA)
                    
                    # Convert to grayscale (OpenCL accelerated)
                    l_gray = cv2.cvtColor(left_ds,  cv2.COLOR_BGR2GRAY)
                    r_gray = cv2.cvtColor(right_ds, cv2.COLOR_BGR2GRAY)
                    
                    # Compute disparity (OpenCL accelerated)
                    disp = stereo_bm.compute(l_gray, r_gray)
                    
                    # Convert disparity to float and scale (keep as UMat)
                    disp_float = cv2.multiply(disp, 1.0/16.0, dtype=cv2.CV_32F)
                    
                    # Convert to numpy only for depth calculation and point cloud generation
                    disp_np = disp_float.get()
                    valid = disp_np > (CFG_D.min_disp + 0.5)
                    denom = disp_np - CFG_D.min_disp
                    depth_m = np.zeros_like(disp_np)
                    mask = (denom > 0.1) & valid
                    left_rect = left_ds.get()
                    
                    # Ensure type checker knows these are initialised
                    assert fx_ds is not None and baseline_m is not None, "Stereo parameters not initialised"
                    depth_m[mask] = fx_ds * baseline_m / denom[mask]

                    # Encode depth to 16-bit PNG (millimetres – preserves precision)
                    depth_mm = np.clip(depth_m * 1000.0, 0, 65535).astype(np.uint16)
                    pts_cam, idx = disparity_to_camera_points(disp_np, Q)
            with w_rect.buf() as b:
                if left_rect is not None:
                    b['rect'] = left_rect
                    b['timestamp'] = r_jpeg.data['timestamp']

            with w_points.buf() as b:
                if pts_cam is not None:
                    b['num_points'] = len(pts_cam)
                    b['points'][:len(pts_cam)] = CFG_D.T_base_cam(pts_cam)
                    b['colors'][:len(pts_cam)] = cv2.cvtColor(left_rect, cv2.COLOR_BGR2RGB).reshape(-1, 3)[idx]
                    b['img2pts'][:len(idx)] = idx
                    b['timestamp'] = r_jpeg.data['timestamp']
            with w_depth.buf() as b:
                if depth_mm is not None:
                    b['depth'] = depth_mm
                    b['timestamp'] = r_jpeg.data['timestamp']


if __name__ == "__main__":
    main()