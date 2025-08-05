import os
import cv2
import numpy as np
import time
import glob
from datetime import datetime

# Path to save calibration YAML to the shared lib folder
CALIB_YAML_PATH = 'stereo_calibration_fisheye.yaml'
IMG_DIR = './cache'

# --- HELPER: save calibration mats robustly to YAML ---
def write_calib_yaml(params: dict, filename: str = CALIB_YAML_PATH):
    """Save numpy matrices to a YAML file using cv2.FileStorage.

    Skips any entries that are None and ensures values are numpy arrays.
    """
    try:
        fs = cv2.FileStorage(filename, cv2.FILE_STORAGE_WRITE)
        for k, v in params.items():
            if v is None:
                continue
            fs.write(k, np.asarray(v))
        fs.release()
        print(f"[INFO] Calibration parameters saved to {filename}")
    except Exception as e:
        print(f"[WARN] Could not save calibration file: {e}")

# --- CONFIGURATION ---
CHECKERBOARD = (5, 5)
SQUARE_SIZE = 1  # mm

def calibrate_and_rectify(pairs):
    if len(pairs) < 5:
        return None, None, None, None

    # Prepare object points in fisheye format (N,1,3)
    objp = np.zeros((CHECKERBOARD[0]*CHECKERBOARD[1], 1, 3), np.float32)
    objp[:, 0, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2)
    objp *= SQUARE_SIZE

    objpoints, imgpoints_left, imgpoints_right = [], [], []
    for left, right, _ in pairs:
        gray_left = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
        gray_right = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
        ret_l, corners_l = cv2.findChessboardCorners(gray_left, CHECKERBOARD, cv2.CALIB_CB_FAST_CHECK)
        ret_r, corners_r = cv2.findChessboardCorners(gray_right, CHECKERBOARD, cv2.CALIB_CB_FAST_CHECK)
        if ret_l and ret_r:
            # Refine corners for better accuracy
            crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-6)
            corners_l = cv2.cornerSubPix(gray_left, corners_l, (3, 3), (-1, -1), crit)
            corners_r = cv2.cornerSubPix(gray_right, corners_r, (3, 3), (-1, -1), crit)
            objpoints.append(np.ascontiguousarray(objp.copy(), dtype=np.float64))
            imgpoints_left.append(np.ascontiguousarray(corners_l.reshape(-1, 1, 2), dtype=np.float64))
            imgpoints_right.append(np.ascontiguousarray(corners_r.reshape(-1, 1, 2), dtype=np.float64))

    assert not np.isnan(objpoints).any(), "NaNs in objpoints!"
    assert np.max(np.abs(objpoints)) < 1000, "objpoints too large"

    print(np.max(np.abs(objpoints[0])))
    print(np.max(np.abs(corners_l)))

    if len(objpoints) < 5:
        return None, None, None, None

    # Initialize camera matrices & distortion coeffs
    K1 = np.eye(3)
    D1 = np.zeros((4, 1))
    K2 = np.eye(3)
    D2 = np.zeros((4, 1))

    image_size = gray_left.shape[::-1]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-6)
    flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_FIX_SKEW

    # OpenCV fisheye.stereoCalibrate has changed signature across versions.
    # It may return 7 or 9 values (… E, F).  Capture robustly.
    _stereo_out = cv2.fisheye.stereoCalibrate(
        objpoints,
        imgpoints_left,
        imgpoints_right,
        K1,
        D1,
        K2,
        D2,
        image_size,
        criteria=criteria,
        flags=flags,
    )

    rms = _stereo_out[0]
    K1, D1, K2, D2, R, T = _stereo_out[1:7]
    E = F = None
    if len(_stereo_out) >= 9:
        E, F = _stereo_out[7:9]

    # Alias pin‑hole variable names used elsewhere so the rest of the script and
    # downstream YAML consumers (stereo.py) remain untouched.
    mtx_l, dist_l = K1, D1
    mtx_r, dist_r = K2, D2

    print(f"[INFO] Fisheye stereo calibration RMS error: {rms:.3f}")

    # Rectify
    R1, R2, P1, P2, Q = cv2.fisheye.stereoRectify(K1, D1, K2, D2, image_size, R, T, flags=cv2.CALIB_ZERO_DISPARITY)

    map1x, map1y = cv2.fisheye.initUndistortRectifyMap(K1, D1, R1, P1, image_size, cv2.CV_16SC2)
    map2x, map2y = cv2.fisheye.initUndistortRectifyMap(K2, D2, R2, P2, image_size, cv2.CV_16SC2)

    return map1x, map1y, map2x, map2y, mtx_l, dist_l, mtx_r, dist_r, R, T, E, F, R1, R2, P1, P2, Q

def draw_epipolar_lines(img, color=(0,255,0), step=25):
    out = img.copy()
    for y in range(0, out.shape[0], step):
        cv2.line(out, (0, y), (out.shape[1], y), color, 1)
    return out

# --- MAIN LOOP ---
left_images = sorted(glob.glob(os.path.join(IMG_DIR, 'frame*_left.jpg')))
right_images = sorted(glob.glob(os.path.join(IMG_DIR, 'frame*_right.jpg')))
assert len(left_images) == len(right_images), "Mismatched left/right image count"
captured_pairs = []
for left, right in zip(left_images, right_images):
    left = cv2.imread(left)
    right = cv2.imread(right)
    fname = os.path.join(IMG_DIR, 'frame_0_usb.png')
    captured_pairs.append((left.copy(), right.copy(), fname))


print(f"[INFO] Attempting calibration/rectification with {len(captured_pairs)} pairs...")
calib_result = calibrate_and_rectify(captured_pairs)
map1x, map1y, map2x, map2y = calib_result[:4]
# Save calibration results if available
if map1x is not None:
    print("[INFO] Calibration and rectification successful. Logging rectified images.")
    # Update latest maps for live preview
    latest_maps['map1x'] = map1x
    latest_maps['map1y'] = map1y
    latest_maps['map2x'] = map2x
    latest_maps['map2y'] = map2y
    mtx_l = dist_l = mtx_r = dist_r = R = T = E = F = R1 = R2 = P1 = P2 = Q = None
    if len(calib_result) > 4:
        mtx_l, dist_l, mtx_r, dist_r, R, T, E, F, R1, R2, P1, P2, Q = calib_result[4:]
    calib_dict = {
        'mtx_l': mtx_l,
        'dist_l': dist_l,
        'mtx_r': mtx_r,
        'dist_r': dist_r,
        'R': R,
        'T': T,
        'E': E,
        'F': F,
        'R1': R1,
        'R2': R2,
        'P1': P1,
        'P2': P2,
        'Q': Q,
    }
    write_calib_yaml(calib_dict, CALIB_YAML_PATH)
else:
    print("[INFO] Not enough valid pairs for calibration.")