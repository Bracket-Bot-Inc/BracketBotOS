from bbos.registry import *
from bbos.tf import *
import numpy as np
from pathlib import Path

cam = Config('stereo')

@register
class depth:
    downsample = 0.375   # 37.5 % resolution → faster and less noisy
    window_size = 13    # StereoBM block size (odd number, 5-21 typical) - smaller = more detail
    min_disp = 0
    num_disp = 32     # Must be multiple of 16
    uniqueness = 7     # Lower = more matches but potentially more noise (5-15 typical)
    speckle_window = 75   # Size of smooth disparity regions to consider noise
    speckle_range = 32  # Max disparity variation within each connected component
    pre_filter_cap = 25  # Pre-filter to normalize image brightness (15-63 typical)
    width_D, height_D = (int(cam.width//2 * downsample), int(cam.height * downsample))
    T_base_cam = trans([0,0,1.55]) @ rot([-1,0,0], 90) @ rot([-1,0,0], 36) 
    calib_path = Path(__file__).parent / "cache" / "stereo_calibration_fisheye.yaml"
    @staticmethod
    def camera_cal():
        import cv2
        print(depth.calib_path)
        """Load fisheye rectification matrices and return the scaled camera model."""
        fs = cv2.FileStorage(str(depth.calib_path), cv2.FILE_STORAGE_READ)
        if not fs.isOpened():
            raise FileNotFoundError(depth.calib_path)

        mtx_l = fs.getNode("mtx_l").mat();  dist_l = fs.getNode("dist_l").mat()
        mtx_r = fs.getNode("mtx_r").mat();  dist_r = fs.getNode("dist_r").mat()
        R1 = fs.getNode("R1").mat();        R2 = fs.getNode("R2").mat()
        P1 = fs.getNode("P1").mat();        P2 = fs.getNode("P2").mat()
        Q  = fs.getNode("Q").mat().astype(np.float32)
        fs.release()
        # Scale translation component to match *scale*
        Q[:4, 3] *= depth.downsample
        baseline_m = abs(P2[0, 3] / P2[0, 0]) / 1000.0
        fx_ds = P1[0, 0] * depth.downsample
        return mtx_l, dist_l, mtx_r, dist_r, R1, R2, P1, P2, Q, baseline_m, fx_ds

@register
class points:
    stride = 2         # Process every Nth frame to reduce CPU usage
    max_range = 5.0
    num_points = int(np.floor((depth.width_D * depth.height_D + stride - 1) / stride))


@realtime(ms=100)
def camera_depth():
    return [
        ("depth", np.uint16, (depth.height_D, depth.width_D)),
    ]


@realtime(ms=100)
def camera_points():
    return [
        ("num_points", np.int32),
        ("points", np.float16, (points.num_points, 3)), # Transform convention, z is out of the camera imager and origin is the center of the left camera imager (at the origin of the camera)
        ("colors", np.uint8, (points.num_points, 3)),
        ("img2pts", np.int32, (depth.width_D * depth.height_D,)), # indexes rectified image to get points
    ]

@realtime(ms=100)
def camera_rect():
    return [
        ("rect", np.uint8, (depth.height_D, depth.width_D, 3)),
    ]