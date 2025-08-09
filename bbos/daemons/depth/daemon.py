from bbos import Reader, Writer, Type, Config
import cv2
import numpy as np
from pathlib import Path

cv2.ocl.setUseOpenCL(True)

CALIB_FILE = 'cache/stereo_calibration_fisheye.yaml'

CFG = Config("stereo")
CFG_D = Config("depth")
CFG_P = Config("points")

def disparity_to_camera_points(disp: cv2.UMat, Q: np.ndarray, left_img: cv2.UMat) -> tuple[np.ndarray, np.ndarray]:
    """Convert disparity map to 3D camera coordinate points using OpenCL acceleration."""
    # Convert UMat to numpy for processing (only when necessary)
    disp_np = disp.get()
    left_np = left_img.get()
    
    # Valid pixels (same disparity threshold as original)
    valid = disp_np > (CFG_D.min_disp + 0.5)
    
    if not np.any(valid):
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.uint8)

    # Point cloud in camera frame (exactly like original working example)
    pts_cam = cv2.reprojectImageTo3D(disp_np, Q) / 1000.0  # Convert mm to m
    pts_cam = pts_cam[valid]
    
    # Get colors from left image (RGB conversion like original)
    left_rgb = cv2.cvtColor(left_np, cv2.COLOR_BGR2RGB)
    cols = left_rgb.reshape(-1, 3)[valid.ravel()]

    # Filter points by distance (same as original)
    dist_m = np.linalg.norm(pts_cam, axis=1)
    keep = dist_m < CFG_P.max_range
    pts_cam, cols = pts_cam[keep], cols[keep]
    
    # Subsample points if needed
    if CFG_P.stride > 1:
        pts_cam = pts_cam[::CFG_P.stride]
        cols = cols[::CFG_P.stride]

    return pts_cam, cols

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
    width_D, height_D = (int(img_w * CFG_D.downsample), int(CFG.height * CFG_D.downsample))

    num_pts = int(np.floor((width_D * height_D + CFG_P.stride - 1) / CFG_P.stride))

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
    stereo_bm = cv2.StereoBM_create(numDisparities=CFG_D.num_disp, blockSize=CFG_D.window_size)
    stereo_bm.setMinDisparity(CFG_D.min_disp)
    stereo_bm.setUniquenessRatio(CFG_D.uniqueness)
    stereo_bm.setSpeckleWindowSize(CFG_D.speckle_window)
    stereo_bm.setSpeckleRange(CFG_D.speckle_range)
    stereo_bm.setPreFilterCap(CFG_D.pre_filter_cap)
    
    # Pre-calculate stereo parameters
    baseline_m = abs(P2_cam[0, 3] / P2_cam[0, 0]) / 1000.0
    fx_ds = P1_cam[0, 0] * CFG_D.downsample

    with Reader('camera.jpeg') as r_jpeg, \
            Writer('camera.depth', lambda: Type("camera_depth")(height_D, width_D)) as w_depth, \
            Writer('camera.points', lambda: Type("camera_points")(num_pts)) as w_points:
        
        print(f"OpenCL available: {cv2.ocl.haveOpenCL()}", flush=True)
        if cv2.ocl.haveOpenCL():
            print(f"OpenCL device: {cv2.ocl.Device.getDefault().name()}", flush=True)

        print('starting depth', flush=True)
        while True:
            if r_jpeg.ready():
                # Decode and split stereo image
                stereo = cv2.imdecode(r_jpeg.data["jpeg"], cv2.IMREAD_COLOR)
                left  = cv2.UMat(stereo[:, :img_w])
                right = cv2.UMat(stereo[:, img_w:])
                
                # Rectify using pre-computed maps (OpenCL accelerated)
                left_r  = cv2.remap(left,  map1x_gpu, map1y_gpu, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
                right_r = cv2.remap(right, map2x_gpu, map2y_gpu, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
                
                # Resize (OpenCL accelerated)
                left_ds  = cv2.resize(left_r,  (width_D, height_D), interpolation=cv2.INTER_AREA)
                right_ds = cv2.resize(right_r, (width_D, height_D), interpolation=cv2.INTER_AREA)
                
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
                pts_cam, cols = disparity_to_camera_points(disp_float, Q, left_ds)

                with w_depth.buf() as b:
                    b['rect'][0] = left_ds.get()
                    b['rect'][1] = right_ds.get()
                    b['depth'] = depth_mm.reshape((height_D, width_D))
                    b['timestamp'] = r_jpeg.data['timestamp']

                with w_points.buf() as b:
                    b['num_points'] = len(pts_cam)
                    b['points'][:len(pts_cam)] = pts_cam
                    b['colors'][:len(cols)] = cols
                    b['timestamp'] = r_jpeg.data['timestamp']


if __name__ == "__main__":
    main()