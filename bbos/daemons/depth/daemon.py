from bbos import Reader, Writer, Type, Config
import cv2
import numpy as np
from pathlib import Path

cv2.ocl.setUseOpenCL(True)

CALIB_FILE = 'cache/stereo_calibration_fisheye.yaml'

CFG = Config("stereo")
CFG_D = Config("depth")
CFG_P = Config("points")

def disparity_to_camera_points(disp: np.ndarray, Q: np.ndarray, left_img: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Convert disparity map to 3D camera coordinate points (same logic as working example)."""
    # Valid pixels (same disparity threshold as original)
    valid = disp > (CFG_D.min_disp + 0.5)
    
    if not np.any(valid):
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.uint8)

    # Point cloud in camera frame (exactly like original working example)
    pts_cam = cv2.reprojectImageTo3D(disp, Q) / 1000.0  # Convert mm to m
    pts_cam = pts_cam[valid]
    
    # Get colors from left image (RGB conversion like original)
    left_rgb = cv2.cvtColor(left_img, cv2.COLOR_BGR2RGB)
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
    width_D, height_D = (int(CFG.width * CFG_D.downsample), int(CFG.height * CFG_D.downsample))

    with Reader('/camera.jpeg') as r_jpeg, \
            Writer('/camera.depth', lambda: Type("camera_depth")(height_D, width_D)) as w_depth, \
            Writer('/camera.points', lambda: Type("camera_points")(height_D, width_D)) as w_points:
        
        print(f"OpenCL available: {cv2.ocl.haveOpenCL()}")
        if cv2.ocl.haveOpenCL():
            print(f"OpenCL device: {cv2.ocl.Device.getDefault().name()}")

        print('starting depth')
        while True:
            if r_jpeg.ready():
                stereo = cv2.imdecode(r_jpeg.data["jpeg"], cv2.IMREAD_COLOR)
                if stereo is None:
                    continue
                left  = stereo[:, :CFG.width//2]
                right = stereo[:, CFG.width//2:]
                baseline_m = abs(P2_cam[0, 3] / P2_cam[0, 0]) / 1000.0
                fx_ds      = P1_cam[0, 0] * CFG_D.downsample
                map1x, map1y = cv2.fisheye.initUndistortRectifyMap(
                    mtx_l, dist_l, R1, P1_cam, (CFG.width, CFG.height), cv2.CV_32FC1
                )
                map2x, map2y = cv2.fisheye.initUndistortRectifyMap(
                    mtx_r, dist_r, R2, P2_cam, (CFG.width, CFG.height), cv2.CV_32FC1
                )
                stereo = cv2.StereoBM_create(numDisparities=CFG_D.num_disp, blockSize=CFG_D.window_size)
                stereo.setMinDisparity(CFG_D.min_disp)
                stereo.setUniquenessRatio(CFG_D.uniqueness)
                stereo.setSpeckleWindowSize(CFG_D.speckle_window)
                stereo.setSpeckleRange(CFG_D.speckle_range)
                stereo.setPreFilterCap(CFG_D.pre_filter_cap)
                left_r  = cv2.remap(left,  map1x, map1y, cv2.INTER_LINEAR)
                right_r = cv2.remap(right, map2x, map2y, cv2.INTER_LINEAR)
                left_ds  = cv2.resize(left_r,  (width_D, height_D), interpolation=cv2.INTER_AREA)
                right_ds = cv2.resize(right_r, (width_D, height_D), interpolation=cv2.INTER_AREA)
                l_gray = cv2.cvtColor(left_ds,  cv2.COLOR_BGR2GRAY)
                r_gray = cv2.cvtColor(right_ds, cv2.COLOR_BGR2GRAY)
                disp = stereo.compute(l_gray, r_gray).astype(np.float32) / 16.0
                valid = disp > (CFG_D.min_disp + 0.5)
                denom = disp - CFG_D.min_disp
                depth_m = np.zeros_like(disp)
                mask = (denom > 0.1) & valid
                # Ensure type checker knows these are initialised
                assert fx_ds is not None and baseline_m is not None, "Stereo parameters not initialised"
                depth_m[mask] = fx_ds * baseline_m / denom[mask]

                # Encode depth to 16-bit PNG (millimetres – preserves precision)
                depth_mm = np.clip(depth_m * 1000.0, 0, 65535).astype(np.uint16)
                #pts_cam, cols = disparity_to_camera_points(disp, Q, left_ds)

                with w_depth.buf() as b:
                    b['rect'][0] = left_ds
                    b['rect'][1] = right_ds
                    b['depth'] = depth_mm.reshape((height_D, width_D))
                    b['timestamp'] = r_jpeg.data['timestamp']

if __name__ == "__main__":
    main()