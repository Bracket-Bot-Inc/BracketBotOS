from bbos import Reader, Writer, Type, Config
import cv2
import numpy as np
from pathlib import Path
import time

cv2.ocl.setUseOpenCL(True)

CALIB_FILE = 'cache/stereo_calibration_fisheye.yaml'

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

def disparity_to_camera_points(disp: cv2.UMat, Q: np.ndarray, left_img: cv2.UMat) -> tuple[np.ndarray, np.ndarray]:
    disp_np = disp.get()
    left_np = left_img.get()

    valid = (disp_np > (CFG_D.min_disp + 0.5))

    if not np.any(valid):
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.uint8)

    # Reproject full grid
    pts_cam_all = cv2.reprojectImageTo3D(disp_np, Q) / 1000.0
    left_rgb = cv2.cvtColor(left_np, cv2.COLOR_BGR2RGB)

    # Mask valid
    pts_cam = pts_cam_all[valid]
    pts_rgb = left_rgb.reshape(-1, 3)[valid.ravel()]

    # 2D grid subsampling
    stride = CFG_P.stride
    if stride > 1:
        h, w = disp_np.shape
        mask = np.zeros_like(valid, dtype=bool)
        mask[::stride, ::stride] = True
        subsample = valid & mask
        pts_cam = cv2.reprojectImageTo3D(disp_np, Q)[subsample] / 1000.0
        pts_rgb = left_rgb.reshape(-1, 3)[subsample.ravel()]

    # Distance filter
    dist_m = np.linalg.norm(pts_cam, axis=1)
    keep = dist_m < CFG_P.max_range
    pts_cam, pts_rgb = pts_cam[keep], pts_rgb[keep]

    return pts_cam, pts_rgb

def load_calib(path: Path, scale: float):
    """Load fisheye rectification matrices and return the scaled camera model."""
    fs = cv2.FileStorage(str(path), cv2.FILE_STORAGE_READ)
    if not fs.isOpened():
        raise FileNotFoundError(path)

    mtx_l = fs.getNode("mtx_l").mat();  dist_l = fs.getNode("dist_l").mat()
    mtx_r = fs.getNode("mtx_r").mat();  dist_r = fs.getNode("dist_r").mat()
    R1 = fs.getNode("R1").mat();        R2 = fs.getNode("R2").mat()
    P1 = fs.getNode("P1").mat();        P2 = fs.getNode("P2").mat()
    Q  = fs.getNode("Q").mat().astype(np.float32)
    fs.release()

    # Scale translation component to match *scale*
    Q[:4, 3] *= scale
    return mtx_l, dist_l, mtx_r, dist_r, R1, R2, P1, P2, Q

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
    ) = load_calib(CALIB_FILE, CFG_D.downsample)

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
    baseline_m = abs(P2_cam[0, 3] / P2_cam[0, 0]) / 1000.0
    fx_ds = P1_cam[0, 0] * CFG_D.downsample

    with Reader('camera.jpeg') as r_jpeg, \
            Writer('camera.depth', Type("camera_depth")) as w_depth, \
            Writer('camera.points', Type("camera_points")) as w_points:
        
        print(f"OpenCL available: {cv2.ocl.haveOpenCL()}", flush=True)
        if cv2.ocl.haveOpenCL():
            print(f"OpenCL device: {cv2.ocl.Device.getDefault().name()}", flush=True)
        print('starting depth', flush=True)

        depth_mm = None
        pts_cam = None
        pts_rgb = None
        t0 = time.time()
        while True:
            if r_jpeg.ready():
                # Decode and split stereo image
                stereo = cv2.imdecode(r_jpeg.data["jpeg"], cv2.IMREAD_COLOR)
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
                
                # Ensure type checker knows these are initialised
                assert fx_ds is not None and baseline_m is not None, "Stereo parameters not initialised"
                depth_m[mask] = fx_ds * baseline_m / denom[mask]

                # Encode depth to 16-bit PNG (millimetres – preserves precision)
                depth_mm = np.clip(depth_m * 1000.0, 0, 65535).astype(np.uint16)
                pts_cam, pts_rgb = disparity_to_camera_points(disp_float, Q, left_ds)
            with w_points.buf() as b:
                if pts_cam is not None and pts_rgb is not None:
                    b['num_points'] = len(pts_cam)
                    b['points'][:len(pts_cam)] = CFG_D.T_base_cam(pts_cam)
                    b['colors'][:len(pts_rgb)] = pts_rgb
                    b['timestamp'] = r_jpeg.data['timestamp']
            with w_depth.buf() as b:
                if depth_mm is not None:
                    b['depth'] = depth_mm
                    b['timestamp'] = r_jpeg.data['timestamp']


if __name__ == "__main__":
    main()