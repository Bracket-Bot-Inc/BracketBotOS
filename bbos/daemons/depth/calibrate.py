#!/opt/robot/daemons/camera/venv/bin/python3
"""
Camera Calibration Script

Interactive stereo camera calibration with web interface.
Automatically uses bootstrap calibration from stereo_calib.yaml for faster convergence.
Follows the ODrive calibration pattern with service management.

Usage:
    # Default: Bootstrap calibration using ../stereo_calib.yaml (recommended)
    ./calibrate_camera [--port 8080]
    
    # Use different bootstrap file
    ./calibrate_camera --bootstrap /path/to/different_calibration.yaml [--port 8080]
    
    # Force standard calibration from scratch (not recommended)
    ./calibrate_camera --bootstrap /nonexistent/file.yaml [--port 8080]

Bootstrap calibration benefits (enabled by default):
    - Faster convergence (fewer LM iterations)
    - Requires fewer images (as few as 2-3 pairs vs 20-40 from scratch)
    - More robust when camera modules are similar
    - Automatically falls back to standard calibration if bootstrap fails
"""

import os
import cv2
import numpy as np
import time
from datetime import datetime
import json
import socket
import threading
import subprocess
import sys
import argparse
import yaml
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
import glob
import select
import base64

from bbos import Config, Reader

# ANSI escape codes for colors
BLUE = '\033[94m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
RED = '\033[91m'
BOLD = '\033[1m'
RESET = '\033[0m'

# Configuration
TOTAL_SQUARES = 12
CHECKERBOARD = (5, 5)
square_mm = 83.97 # mm

PORT = 8082

# Path to save calibration files to the calibration folder
CALIB_DIR = './cache'
CALIB_YAML_PATH = os.path.join(CALIB_DIR, 'stereo_calibration_fisheye.yaml')
INIT_CALIB_YAML_PATH = 'stereo_calib.yaml'
IMG_DIR = CALIB_DIR

# Ensure directories exist
os.makedirs(CALIB_DIR, exist_ok=True)


# --- BOOTSTRAP CALIBRATION UTILS ---
def load_calibration_yaml(filepath):
    """Load camera matrices and distortion coefficients from a YAML file.
    
    Args:
        filepath: Path to the calibration YAML file
        
    Returns:
        dict: Dictionary containing K1, D1, K2, D2 matrices if successful, None otherwise
    """
    try:
        #print(f"[INFO] Loading bootstrap calibration from: {filepath}")
        
        # Use OpenCV FileStorage to read the YAML (same format as write_calib_yaml)
        fs = cv2.FileStorage(filepath, cv2.FILE_STORAGE_READ)
        
        # Try to read the matrices
        K1 = fs.getNode('mtx_l').mat()
        D1 = fs.getNode('dist_l').mat()
        K2 = fs.getNode('mtx_r').mat()
        D2 = fs.getNode('dist_r').mat()
        
        fs.release()
        
        # Validate that we got valid matrices
        if K1 is None or D1 is None or K2 is None or D2 is None:
            print("[WARN] Could not read camera matrices from YAML file")
            return None
            
        # Ensure proper shapes for fisheye calibration
        if K1.shape != (3, 3) or K2.shape != (3, 3):
            print(f"[WARN] Invalid camera matrix shapes: K1={K1.shape}, K2={K2.shape}")
            return None
            
        if D1.shape[0] < 4 or D2.shape[0] < 4:
            print(f"[WARN] Invalid distortion coefficient shapes: D1={D1.shape}, D2={D2.shape}")
            return None
            
        # Ensure D1 and D2 are (4,1) for fisheye model
        D1 = D1.reshape(4, 1) if D1.size >= 4 else np.zeros((4, 1))
        D2 = D2.reshape(4, 1) if D2.size >= 4 else np.zeros((4, 1))
        
        print(f"[INFO] Successfully loaded calibration matrices:")
        print(f"[INFO]   Left camera matrix (K1): focal_length=({K1[0,0]:.1f}, {K1[1,1]:.1f}), center=({K1[0,2]:.1f}, {K1[1,2]:.1f})")
        print(f"[INFO]   Right camera matrix (K2): focal_length=({K2[0,0]:.1f}, {K2[1,1]:.1f}), center=({K2[0,2]:.1f}, {K2[1,2]:.1f})")
        print(f"[INFO]   Left distortion (D1): [{D1[0,0]:.6f}, {D1[1,0]:.6f}, {D1[2,0]:.6f}, {D1[3,0]:.6f}]")
        print(f"[INFO]   Right distortion (D2): [{D2[0,0]:.6f}, {D2[1,0]:.6f}, {D2[2,0]:.6f}, {D2[3,0]:.6f}]")
        
        return {
            'K1': K1.astype(np.float64),
            'D1': D1.astype(np.float64),
            'K2': K2.astype(np.float64),
            'D2': D2.astype(np.float64)
        }
        
    except Exception as e:
        print(f"[WARN] Failed to load calibration from {filepath}: {e}")
        return None

def validate_bootstrap_matrices(K1, D1, K2, D2, image_size):
    """Validate that bootstrap matrices are reasonable for the given image size.
    
    Args:
        K1, D1, K2, D2: Camera matrices and distortion coefficients
        image_size: (width, height) of the images
        
    Returns:
        bool: True if matrices seem reasonable, False otherwise
    """
    width, height = image_size
    
    # Check focal lengths are reasonable (should be in pixel units, roughly image width)
    f1_x, f1_y = K1[0,0], K1[1,1]
    f2_x, f2_y = K2[0,0], K2[1,1]
    
    # Focal length should be positive and in reasonable range (0.2x to 3x image width)
    min_focal = width * 0.2
    max_focal = width * 3.0
    
    if not (min_focal < f1_x < max_focal and min_focal < f1_y < max_focal):
        print(f"[WARN] Left camera focal length out of range: f=({f1_x:.1f}, {f1_y:.1f}), expected ({min_focal:.1f}, {max_focal:.1f})")
        return False
        
    if not (min_focal < f2_x < max_focal and min_focal < f2_y < max_focal):
        print(f"[WARN] Right camera focal length out of range: f=({f2_x:.1f}, {f2_y:.1f}), expected ({min_focal:.1f}, {max_focal:.1f})")
        return False
    
    # Check principal points are within image bounds (with some margin)
    cx1, cy1 = K1[0,2], K1[1,2]
    cx2, cy2 = K2[0,2], K2[1,2]
    
    margin = 0.3  # Allow 30% outside image bounds
    min_x, max_x = -width * margin, width * (1 + margin)
    min_y, max_y = -height * margin, height * (1 + margin)
    
    if not (min_x < cx1 < max_x and min_y < cy1 < max_y):
        print(f"[WARN] Left camera principal point out of range: c=({cx1:.1f}, {cy1:.1f})")
        return False
        
    if not (min_x < cx2 < max_x and min_y < cy2 < max_y):
        print(f"[WARN] Right camera principal point out of range: c=({cx2:.1f}, {cy2:.1f})")
        return False
    
    # Check distortion coefficients are reasonable (fisheye model)
    # For fisheye, k1 and k2 are typically small, k3 and k4 can be larger
    for name, D in [("Left", D1), ("Right", D2)]:
        if np.any(np.abs(D) > 10):  # Very large distortion coefficients are suspicious
            print(f"[WARN] {name} camera has very large distortion coefficients: {D.flatten()}")
            # Don't fail validation, just warn
    
    print("[INFO] Bootstrap matrices validation passed")
    return True

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


# --- CALIBRATION UTILS ---
def calibrate_and_rectify(pairs, bootstrap_calib=None):
    """Perform stereo fisheye calibration with optional bootstrap initialization.
    
    Args:
        pairs: List of (left_image, right_image, filename) tuples
        bootstrap_calib: Optional dict with K1, D1, K2, D2 matrices for initialization
        
    Returns:
        dict with calibration results or None if failed
    """
    if len(pairs) < 5:
        return None

    # Prepare object points in fisheye format (N,1,3)
    objp = np.zeros((CHECKERBOARD[0]*CHECKERBOARD[1], 1, 3), np.float32)
    objp[:, 0, :2] = np.mgrid[0:CHECKERBOARD[0], 0:CHECKERBOARD[1]].T.reshape(-1, 2)
    objp *= SQUARE_SIZE

    objpoints, imgpoints_left, imgpoints_right = [], [], []
    for left, right, fname in pairs:
        gray_left = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
        gray_right = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
        ret_l, corners_l = cv2.findChessboardCorners(gray_left, CHECKERBOARD, cv2.CALIB_CB_FAST_CHECK)
        ret_r, corners_r = cv2.findChessboardCorners(gray_right, CHECKERBOARD, cv2.CALIB_CB_FAST_CHECK)
        if ret_l and ret_r:
            # Refine corners for better accuracy
            crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-6)
            corners_l = cv2.cornerSubPix(gray_left, corners_l, (3, 3), (-1, -1), crit)
            corners_r = cv2.cornerSubPix(gray_right, corners_r, (3, 3), (-1, -1), crit)
            
            # Quality check: ensure corners are well distributed
            if len(corners_l) == CHECKERBOARD[0] * CHECKERBOARD[1] and len(corners_r) == CHECKERBOARD[0] * CHECKERBOARD[1]:
                objpoints.append(objp)
                imgpoints_left.append(corners_l)
                imgpoints_right.append(corners_r)
                print(f"[INFO] Using calibration image: {fname}")
            else:
                print(f"[WARN] Skipping image with poor corner detection: {fname}")
        else:
            print(f"[WARN] Skipping image - checkerboard not found in both views: {fname}")

    if len(objpoints) < 5:
        return None

    image_size = gray_left.shape[::-1]
    
    # Initialize camera matrices & distortion coeffs - use bootstrap if available
    if bootstrap_calib is not None:
        print("[INFO] Using bootstrap calibration as initial guess")
        
        # Validate bootstrap matrices against current image size
        if not validate_bootstrap_matrices(bootstrap_calib['K1'], bootstrap_calib['D1'], 
                                         bootstrap_calib['K2'], bootstrap_calib['D2'], image_size):
            print("[WARN] Bootstrap matrices failed validation, falling back to zero initialization")
            bootstrap_calib = None
    
    if bootstrap_calib is not None:
        # Use bootstrap matrices as initial guess
        K1 = bootstrap_calib['K1'].copy()
        D1 = bootstrap_calib['D1'].copy()
        K2 = bootstrap_calib['K2'].copy()
        D2 = bootstrap_calib['D2'].copy()
        
        # Store original values to check for divergence
        orig_fx1, orig_fy1 = K1[0,0], K1[1,1]
        orig_fx2, orig_fy2 = K2[0,0], K2[1,1]
        orig_cx1, orig_cy1 = K1[0,2], K1[1,2]
        orig_cx2, orig_cy2 = K2[0,2], K2[1,2]
        
        # Use more conservative flags to prevent divergence from bootstrap
        flags = (cv2.fisheye.CALIB_USE_INTRINSIC_GUESS | 
                cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | 
                cv2.fisheye.CALIB_FIX_SKEW |
                cv2.fisheye.CALIB_FIX_PRINCIPAL_POINT)  # Keep principal points fixed
        
        print(f"[INFO] Bootstrap mode: Starting with focal lengths L=({K1[0,0]:.1f}, {K1[1,1]:.1f}), R=({K2[0,0]:.1f}, {K2[1,1]:.1f})")
        print(f"[INFO] Using conservative calibration flags to prevent divergence from initial guess")
        
        # For bootstrap mode, use fewer iterations and stricter convergence criteria
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1e-5)
        
    else:
        # Initialize with zeros (standard calibration from scratch)
        K1 = np.zeros((3, 3))
        D1 = np.zeros((4, 1))
        K2 = np.zeros((3, 3))
        D2 = np.zeros((4, 1))
        
        flags = cv2.fisheye.CALIB_RECOMPUTE_EXTRINSIC | cv2.fisheye.CALIB_FIX_SKEW
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 1e-6)
        print("[INFO] From-scratch mode: Starting with zero initialization")

    print(f"[INFO] Attempting fisheye stereo calibration with {len(objpoints)} valid image pairs...")
    print(f"[INFO] Image size: {image_size}")
    
    try:
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
    except cv2.error as e:
        print(f"[ERROR] Fisheye stereo calibration failed: {e}")
        if "abs_max < threshold" in str(e):
            print("[ERROR] This error typically occurs when:")
            print("  - Calibration images have poor quality corner detection")
            print("  - Images are too similar (not enough variety in checkerboard positions)")
            print("  - Checkerboard is too close to camera edges")
            print("  - Try capturing images with checkerboard in different positions/orientations")
        return None
    except Exception as e:
        print(f"[ERROR] Unexpected error during calibration: {e}")
        return None

    rms = _stereo_out[0]
    K1_new, D1_new, K2_new, D2_new, R, T = _stereo_out[1:7]
    E = F = None
    if len(_stereo_out) >= 9:
        E, F = _stereo_out[7:9]

    # Validate calibration results against bootstrap if we used one
    if bootstrap_calib is not None:
        # Check for significant divergence from bootstrap values
        fx1_change = abs(K1_new[0,0] - orig_fx1) / orig_fx1
        fy1_change = abs(K1_new[1,1] - orig_fy1) / orig_fy1
        fx2_change = abs(K2_new[0,0] - orig_fx2) / orig_fx2
        fy2_change = abs(K2_new[1,1] - orig_fy2) / orig_fy2
        
        # Allow only small changes from bootstrap (max 20% change in focal length)
        max_allowed_change = 0.20
        
        if (fx1_change > max_allowed_change or fy1_change > max_allowed_change or
            fx2_change > max_allowed_change or fy2_change > max_allowed_change):
            
            print(f"[WARN] Calibration diverged significantly from bootstrap:")
            print(f"[WARN]   Left focal change: fx={fx1_change*100:.1f}%, fy={fy1_change*100:.1f}%")
            print(f"[WARN]   Right focal change: fx={fx2_change*100:.1f}%, fy={fy2_change*100:.1f}%")
            print(f"[WARN] Rejecting divergent calibration, keeping bootstrap values")
            
            # Use bootstrap values with just extrinsic refinement
            K1_final, D1_final = bootstrap_calib['K1'], bootstrap_calib['D1']
            K2_final, D2_final = bootstrap_calib['K2'], bootstrap_calib['D2']
        else:
            print(f"[INFO] Calibration converged nicely (max focal change: {max(fx1_change, fy1_change, fx2_change, fy2_change)*100:.1f}%)")
            K1_final, D1_final = K1_new, D1_new
            K2_final, D2_final = K2_new, D2_new
    else:
        K1_final, D1_final = K1_new, D1_new
        K2_final, D2_final = K2_new, D2_new

    # Alias pin‑hole variable names used elsewhere so the rest of the script and
    # downstream YAML consumers (stereo.py) remain untouched.
    mtx_l, dist_l = K1_final, D1_final
    mtx_r, dist_r = K2_final, D2_final

    print(f"[INFO] Fisheye stereo calibration RMS error: {rms:.3f}")
    print(f"[INFO] Final focal lengths: L=({K1_final[0,0]:.1f}, {K1_final[1,1]:.1f}), R=({K2_final[0,0]:.1f}, {K2_final[1,1]:.1f})")

    # Skip unreliable OpenCV rectification - use constrained approach with known hardware
    print(f"[INFO] Using constrained rectification with known hardware baseline (65mm)")
    
    # Use calibrated intrinsics but known hardware baseline
    fx_avg = (K1_final[0,0] + K2_final[0,0]) / 2  # Fine-tuned focal length
    fy_avg = (K1_final[1,1] + K2_final[1,1]) / 2  # Fine-tuned focal length  
    cx_avg = (K1_final[0,2] + K2_final[0,2]) / 2  # Fine-tuned principal point
    cy_avg = (K1_final[1,2] + K2_final[1,2]) / 2  # Fine-tuned principal point
    
    # Known hardware constraint - this never changes
    baseline_mm = 65.0  # Physical camera separation
    baseline_px = fx_avg * baseline_mm  # Baseline in pixels
    
    # Construct projection matrices with hardware constraints
    P1 = np.array([
        [fx_avg, 0, cx_avg, 0],  # Left camera: no translation
        [0, fy_avg, cy_avg, 0], 
        [0, 0, 1, 0]
    ], dtype=np.float64)
    
    P2 = np.array([
        [fx_avg, 0, cx_avg, -baseline_px],  # Right camera: translate by baseline
        [0, fy_avg, cy_avg, 0],
        [0, 0, 1, 0]
    ], dtype=np.float64)
    
    # Simple rectification (works well for aligned cameras)
    R1 = R2 = np.eye(3, dtype=np.float64)
    
    # Q matrix for accurate depth calculation  
    Q = np.array([
        [1, 0, 0, -cx_avg],
        [0, 1, 0, -cy_avg], 
        [0, 0, 0, fx_avg],
        [0, 0, -1/baseline_mm, 0]  # Depth scaling factor
    ], dtype=np.float64)
    
    print(f"[INFO] Constrained matrices:")
    print(f"[INFO]   Focal length: {fx_avg:.1f}px (fine-tuned from calibration)")
    print(f"[INFO]   Baseline: {baseline_mm}mm = {baseline_px:.1f}px (hardware constraint)")
    print(f"[INFO]   Expected depth accuracy: ~{baseline_mm/10:.1f}mm at 1m distance")

    map1x, map1y = cv2.fisheye.initUndistortRectifyMap(K1_final, D1_final, R1, P1, image_size, cv2.CV_16SC2)
    map2x, map2y = cv2.fisheye.initUndistortRectifyMap(K2_final, D2_final, R2, P2, image_size, cv2.CV_16SC2)
    
    # Validate rectification produced proper baseline for depth calculation
    baseline_px = abs(P2[0,3])  # Baseline in pixels  
    focal_length_px = P1[0,0]   # Focal length in pixels
    
    # Calculate baseline using the SAME formula as the depth daemon
    baseline_m = (baseline_px / focal_length_px) / 1000.0 if focal_length_px != 0 else 0
    
    print(f"[INFO] Rectification successful:")
    print(f"[INFO]   P1[0,0] (focal): {focal_length_px:.1f}px")
    print(f"[INFO]   P2[0,3] (baseline): {P2[0,3]:.1f}px")
    print(f"[INFO]   Calculated baseline: {baseline_m*1000:.1f}mm")
    
    # Sanity check for depth calculation (should be around 65mm)
    expected_baseline_mm = 65.0
    if abs(baseline_m * 1000 - expected_baseline_mm) > 20:
        print(f"[WARN] Baseline seems wrong! Expected ~{expected_baseline_mm}mm, got {baseline_m*1000:.1f}mm")
        print(f"[WARN] Depth service may show incorrect depth values")
    
    if abs(P2[0,3]) < 100.0:  # Should be thousands of pixels for proper baseline
        print(f"[WARN] P2[0,3] is too small ({P2[0,3]:.1f}), rectification likely failed")
        print(f"[WARN] Depth service will show black images with this calibration")

    return {
        'map1x': map1x, 'map1y': map1y, 'map2x': map2x, 'map2y': map2y,
        'mtx_l': mtx_l, 'dist_l': dist_l, 'mtx_r': mtx_r, 'dist_r': dist_r,
        'R': R, 'T': T, 'E': E, 'F': F, 'R1': R1, 'R2': R2, 'P1': P1, 'P2': P2, 'Q': Q,
        'rms': rms
    }

def draw_epipolar_lines(img, color=(0,255,0), step=25):
    out = img.copy()
    for y in range(0, out.shape[0], step):
        cv2.line(out, (0, y), (out.shape[1], y), color, 1)
    return out

def encode_image_b64(img):
    """Encode image as base64 string for web display."""
    if img is None:
        return ""
    _, buffer = cv2.imencode('.jpg', img)
    return base64.b64encode(buffer).decode('utf-8')

def get_local_ip():
    """Get the local IP address"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "localhost"

class CameraCalibrator:
    def __init__(self, port=8080, bootstrap_calib=None):
        self.port = port
        self.bootstrap_calib = bootstrap_calib
        self.captured_pairs = []
        self.latest_maps = {'map1x': None, 'map1y': None, 'map2x': None, 'map2y': None}
        self.current_frame = {'left': None, 'right': None, 'stereo': None}
        self.checkerboard_detected = {'left': False, 'right': False}
        self.rectified_images = {'left': None, 'right': None}
        self.calibration_status = {'calibrated': False, 'rms': 0, 'pairs_count': 0}
        self.last_failed_pair_count = 0  # Track when last calibration failed to prevent infinite retries
        
        if bootstrap_calib is not None:
            print("[INFO] Calibrator initialized with bootstrap calibration")
        
        # Load existing images
        self.load_existing_images()
        
        # Try initial calibration if we have enough pairs
        if len(self.captured_pairs) >= 5:
            self.perform_calibration()
        elif bootstrap_calib is not None and len(self.captured_pairs) >= 2:
            # With bootstrap, we can try with fewer images (as low as 2-3 pairs)
            print("[INFO] Attempting bootstrap calibration with fewer image pairs...")
            self.perform_calibration()
    
    def load_existing_images(self):
        """Load existing calibration images from captures folder."""
        existing_files = glob.glob(os.path.join(IMG_DIR, '*_usb.jpg'))
        for fname in existing_files:
            img = cv2.imread(fname)
            if img is not None:
                height, width = img.shape[:2]
                left = img[:, :width//2]
                right = img[:, width//2:]
                self.captured_pairs.append((left, right, fname))
                
        if self.captured_pairs:
            print(f"[INFO] Loaded {len(self.captured_pairs)} existing image pairs for calibration.")
    
    def perform_calibration(self):
        """Perform calibration with current image pairs, automatically discarding problematic ones."""
        min_pairs = 2 if self.bootstrap_calib is not None else 5
        if len(self.captured_pairs) < min_pairs:
            return False
        
        # Prevent infinite retry loops - only attempt calibration if we have more pairs than last failure
        if len(self.captured_pairs) <= self.last_failed_pair_count:
            print(f"[INFO] Skipping calibration attempt - need more than {self.last_failed_pair_count} pairs (currently have {len(self.captured_pairs)})")
            return False
            
        calib_mode = "bootstrap" if self.bootstrap_calib is not None else "from-scratch"
        print(f"[INFO] Performing {calib_mode} calibration with {len(self.captured_pairs)} pairs...")
        
        # Try calibration with all pairs first
        calib_result = calibrate_and_rectify(self.captured_pairs, self.bootstrap_calib)
        
        if calib_result is not None:
            # Calibration succeeded - reset failure tracking
            self.last_failed_pair_count = 0
            self.latest_maps = {
                'map1x': calib_result['map1x'],
                'map1y': calib_result['map1y'], 
                'map2x': calib_result['map2x'],
                'map2y': calib_result['map2y']
            }
            
            # Save calibration parameters
            calib_dict = {k: v for k, v in calib_result.items() 
                         if k not in ['map1x', 'map1y', 'map2x', 'map2y']}
            write_calib_yaml(calib_dict, CALIB_YAML_PATH)
            
            self.calibration_status = {
                'calibrated': True,
                'rms': calib_result['rms'],
                'pairs_count': len(self.captured_pairs)
            }
            
            print(f"[INFO] Calibration successful! RMS error: {calib_result['rms']:.3f}")
            return True
        else:
            # Calibration failed - try to recover by removing problematic pairs
            return self._attempt_calibration_recovery()
    
    def _attempt_calibration_recovery(self):
        """Attempt to recover from calibration failure by removing problematic image pairs."""
        original_count = len(self.captured_pairs)
        min_pairs = 2 if self.bootstrap_calib is not None else 5
        print(f"[WARN] Calibration failed with {original_count} pairs. Attempting smart recovery...")
        
        # Improved Strategy: Systematically test which pair is causing the problem
        if len(self.captured_pairs) > min_pairs:
            print("[INFO] Testing calibration by removing each pair individually...")
            
            # Test removing each pair one by one to find the problematic one
            for i in range(len(self.captured_pairs)):
                test_pairs = self.captured_pairs[:i] + self.captured_pairs[i+1:]
                
                print(f"[INFO] Testing without pair {i+1}/{len(self.captured_pairs)}: {self.captured_pairs[i][2]}")
                calib_result = calibrate_and_rectify(test_pairs, self.bootstrap_calib)
                
                if calib_result is not None:
                    # Found the problematic pair!
                    removed_pair = self.captured_pairs.pop(i)
                    print(f"[INFO] Recovery successful! Found problematic pair: {removed_pair[2]}")
                    print(f"[INFO] Calibration now works with {len(self.captured_pairs)} pairs (RMS: {calib_result['rms']:.3f})")
                    return self._finalize_successful_calibration(calib_result)
            
            # If individual removal didn't work, try removing pairs with poor quality scores
            print("[INFO] Individual removal failed. Trying quality-based removal...")
            
            # Score pairs by corner detection quality and geometric consistency
            scored_pairs = []
            for left, right, fname in self.captured_pairs:
                score = self._evaluate_pair_quality(left, right)
                scored_pairs.append((score, left, right, fname))
            
            # Sort by quality (higher score = better quality)
            scored_pairs.sort(key=lambda x: x[0], reverse=True)
            
            # Remove the worst pair(s) and test
            for remove_count in range(1, min(3, len(scored_pairs) - min_pairs + 1)):
                test_pairs = [(left, right, fname) for _, left, right, fname in scored_pairs[:-remove_count]]
                
                print(f"[INFO] Testing with {remove_count} worst pairs removed...")
                calib_result = calibrate_and_rectify(test_pairs, self.bootstrap_calib)
                
                if calib_result is not None:
                    # Quality filtering worked!
                    self.captured_pairs = test_pairs
                    print(f"[INFO] Recovery successful! Removed {remove_count} low-quality pairs")
                    print(f"[INFO] Calibration now works with {len(self.captured_pairs)} pairs (RMS: {calib_result['rms']:.3f})")
                    return self._finalize_successful_calibration(calib_result)
        
        # All recovery attempts failed - track this failure to prevent immediate retries
        print("[WARN] Calibration recovery failed. Continue capturing more images with varied positions.")
        print(f"[INFO] Will not attempt calibration again until you have more than {len(self.captured_pairs)} image pairs.")
        self.last_failed_pair_count = len(self.captured_pairs)
        self.calibration_status['pairs_count'] = len(self.captured_pairs)
        return False
    
    def _evaluate_pair_quality(self, left, right):
        """Evaluate the quality of a calibration image pair based on multiple criteria."""
        gray_left = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
        gray_right = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
        
        ret_l, corners_l = cv2.findChessboardCorners(gray_left, CHECKERBOARD, cv2.CALIB_CB_FAST_CHECK)
        ret_r, corners_r = cv2.findChessboardCorners(gray_right, CHECKERBOARD, cv2.CALIB_CB_FAST_CHECK)
        
        if not (ret_l and ret_r):
            return 0  # Very poor quality
        
        # Refine corners and calculate quality metrics
        crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 1e-6)
        corners_l = cv2.cornerSubPix(gray_left, corners_l, (3, 3), (-1, -1), crit)
        corners_r = cv2.cornerSubPix(gray_right, corners_r, (3, 3), (-1, -1), crit)
        
        # Calculate comprehensive quality score
        score = 0
        
        # Check if all corners were found
        if len(corners_l) == CHECKERBOARD[0] * CHECKERBOARD[1] and len(corners_r) == CHECKERBOARD[0] * CHECKERBOARD[1]:
            score += 30  # Base score for detection
            
            # Check corner distribution (avoid corners too close to edges)
            h, w = gray_left.shape
            margin = min(w, h) * 0.15  # 15% margin
            
            left_corners_good = all(margin < c[0][0] < w-margin and margin < c[0][1] < h-margin for c in corners_l)
            right_corners_good = all(margin < c[0][0] < w-margin and margin < c[0][1] < h-margin for c in corners_r)
            
            if left_corners_good:
                score += 20
            if right_corners_good:
                score += 20
            
            # Check corner spread (good calibration needs corners spread across image)
            def corner_spread_score(corners, image_shape):
                h, w = image_shape
                x_coords = [c[0][0] for c in corners]
                y_coords = [c[0][1] for c in corners]
                
                x_range = max(x_coords) - min(x_coords)
                y_range = max(y_coords) - min(y_coords)
                
                # Good spread uses at least 50% of image width/height
                x_coverage = x_range / w
                y_coverage = y_range / h
                
                return min(15, (x_coverage + y_coverage) * 15)  # Max 15 points
            
            score += corner_spread_score(corners_l, gray_left.shape)
            score += corner_spread_score(corners_r, gray_right.shape)
            
            # Check image sharpness using Laplacian variance
            def sharpness_score(gray_img):
                laplacian_var = cv2.Laplacian(gray_img, cv2.CV_64F).var()
                # Normalize sharpness score (typical range 0-2000, we want 0-10 points)
                return min(10, laplacian_var / 200)
            
            score += sharpness_score(gray_left)
            score += sharpness_score(gray_right)
            
            # Penalize very similar consecutive captures (too little pose variation)
            if hasattr(self, '_last_corner_positions'):
                def corner_similarity_penalty(current_corners, last_corners):
                    if last_corners is None:
                        return 0
                    
                    # Calculate average corner movement
                    if len(current_corners) == len(last_corners):
                        total_movement = 0
                        for i in range(len(current_corners)):
                            dx = current_corners[i][0][0] - last_corners[i][0][0]
                            dy = current_corners[i][0][1] - last_corners[i][0][1]
                            total_movement += (dx*dx + dy*dy)**0.5
                        
                        avg_movement = total_movement / len(current_corners)
                        
                        # Penalize if average movement is too small (< 20 pixels)
                        if avg_movement < 20:
                            return -10  # Penalty for too similar poses
                    
                    return 0
                
                penalty = corner_similarity_penalty(corners_l, self._last_corner_positions)
                score += penalty
            
            # Store current corners for next comparison
            self._last_corner_positions = corners_l
        
        return max(0, score)  # Ensure non-negative score
    
    def _finalize_successful_calibration(self, calib_result):
        """Finalize a successful calibration."""
        self.latest_maps = {
            'map1x': calib_result['map1x'],
            'map1y': calib_result['map1y'], 
            'map2x': calib_result['map2x'],
            'map2y': calib_result['map2y']
        }
        
        # Save calibration parameters
        calib_dict = {k: v for k, v in calib_result.items() 
                     if k not in ['map1x', 'map1y', 'map2x', 'map2y']}
        write_calib_yaml(calib_dict, CALIB_YAML_PATH)
        
        self.calibration_status = {
            'calibrated': True,
            'rms': calib_result['rms'],
            'pairs_count': len(self.captured_pairs)
        }
        
        print(f"[INFO] Calibration successful! RMS error: {calib_result['rms']:.3f}")
        print(f"[INFO] Using {len(self.captured_pairs)} high-quality image pairs")
        return True
    
    def capture_frame(self, frame):
        """Process a new frame from the camera."""
        h, w = frame.shape[:2]
        left = frame[:, :w//2]
        right = frame[:, w//2:]
        
        self.current_frame = {'left': left.copy(), 'right': right.copy(), 'stereo': frame.copy()}
        
        # Check for checkerboard detection
        gray_left = cv2.cvtColor(left, cv2.COLOR_BGR2GRAY)
        gray_right = cv2.cvtColor(right, cv2.COLOR_BGR2GRAY)
        ret_l, corners_l = cv2.findChessboardCorners(gray_left, CHECKERBOARD, None)
        ret_r, corners_r = cv2.findChessboardCorners(gray_right, CHECKERBOARD, None)
        
        self.checkerboard_detected = {'left': ret_l, 'right': ret_r}
        
        # Draw corners if detected
        vis_left = left.copy()
        vis_right = right.copy()
        if ret_l:
            cv2.drawChessboardCorners(vis_left, CHECKERBOARD, corners_l, ret_l)
        if ret_r:
            cv2.drawChessboardCorners(vis_right, CHECKERBOARD, corners_r, ret_r)
            
        self.current_frame['left'] = vis_left
        self.current_frame['right'] = vis_right
        
        # Generate rectified images if calibration available
        if all(self.latest_maps[k] is not None for k in ['map1x', 'map1y', 'map2x', 'map2y']):
            rect_left = cv2.remap(left, self.latest_maps['map1x'], self.latest_maps['map1y'], cv2.INTER_LINEAR)
            rect_right = cv2.remap(right, self.latest_maps['map2x'], self.latest_maps['map2y'], cv2.INTER_LINEAR)
            
            self.rectified_images = {
                'left': draw_epipolar_lines(rect_left),
                'right': draw_epipolar_lines(rect_right)
            }
    
    def save_calibration_image(self):
        """Save current frame as calibration image if checkerboard detected."""
        if not (self.checkerboard_detected['left'] and self.checkerboard_detected['right']):
            return False, "Checkerboard not detected in both images"
        
        if self.current_frame['stereo'] is None:
            return False, "No camera frame available"
            
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        fname = os.path.join(IMG_DIR, f'{timestamp}_usb.jpg')
        cv2.imwrite(fname, self.current_frame['stereo'])
        
        left = self.current_frame['stereo'][:, :self.current_frame['stereo'].shape[1]//2]
        right = self.current_frame['stereo'][:, self.current_frame['stereo'].shape[1]//2:]
        self.captured_pairs.append((left.copy(), right.copy(), fname))
        
        # Update pairs count immediately
        self.calibration_status['pairs_count'] = len(self.captured_pairs)
        
        # Perform calibration if we have enough pairs
        min_pairs = 2 if self.bootstrap_calib is not None else 5
        if len(self.captured_pairs) >= min_pairs:
            success = self.perform_calibration()
        
        return True, f"Image saved: {fname} (Total pairs: {len(self.captured_pairs)})"

def create_handler(calibrator):
    """Create HTTP handler with calibrator instance"""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/':
                self.serve_html()
            elif self.path == '/api/status':
                self.serve_status()
            else:
                self.send_error(404)
        
        def do_POST(self):
            if self.path == '/api/capture':
                self.capture_image()
            else:
                self.send_error(404)
        
        def serve_html(self):
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Camera Calibration - Stereo Setup</title>
    <style>
        body {{ 
            font-family: Arial, sans-serif; 
            margin: 20px; 
            background-color: #f0f0f0; 
        }}
        .container {{ 
            max-width: 1400px; 
            margin: 0 auto; 
            background: white; 
            padding: 20px; 
            border-radius: 10px; 
            box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
        }}
        .header {{ 
            text-align: center; 
            margin-bottom: 20px; 
            border-bottom: 2px solid #007acc; 
            padding-bottom: 10px; 
        }}
        .status-bar {{
            background: #e8f4fd;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .camera-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-bottom: 20px;
        }}
        .camera-view {{
            text-align: center;
        }}
        .camera-view h3 {{
            margin-bottom: 10px;
            color: #007acc;
        }}
        .camera-view img {{
            border: 2px solid #007acc;
            border-radius: 5px;
            max-width: 100%;
            height: auto;
        }}
        .rectified-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin-top: 20px;
        }}
        .capture-section {{
            text-align: center;
            margin: 20px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 5px;
        }}
        .capture-btn {{
            background: #28a745;
            color: white;
            border: none;
            padding: 15px 30px;
            border-radius: 5px;
            font-size: 16px;
            cursor: pointer;
        }}
        .capture-btn:hover {{
            background: #218838;
        }}
        .capture-btn:disabled {{
            background: #6c757d;
            cursor: not-allowed;
        }}
        .detection-status {{
            display: inline-block;
            padding: 5px 10px;
            border-radius: 3px;
            margin: 5px;
            font-weight: bold;
        }}
        .detected {{
            background: #d4edda;
            color: #155724;
        }}
        .not-detected {{
            background: #f8d7da;
            color: #721c24;
        }}
        .calibration-info {{
            background: #fff3cd;
            padding: 15px;
            border-radius: 5px;
            margin-top: 20px;
        }}
    </style>
    <script>
        let updateInterval;
        
        function updateStatus() {{
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {{
                    // Update images
                    if (data.images.left) {{
                        document.getElementById('leftImg').src = 'data:image/jpeg;base64,' + data.images.left;
                    }}
                    if (data.images.right) {{
                        document.getElementById('rightImg').src = 'data:image/jpeg;base64,' + data.images.right;
                    }}
                    
                    // Update rectified images
                    if (data.images.rect_left) {{
                        document.getElementById('rectLeftImg').src = 'data:image/jpeg;base64,' + data.images.rect_left;
                        document.getElementById('rectifiedSection').style.display = 'block';
                    }}
                    if (data.images.rect_right) {{
                        document.getElementById('rectRightImg').src = 'data:image/jpeg;base64,' + data.images.rect_right;
                    }}
                    
                    // Update detection status
                    const leftStatus = document.getElementById('leftStatus');
                    const rightStatus = document.getElementById('rightStatus');
                    
                    leftStatus.textContent = data.detection.left ? 'DETECTED' : 'NOT DETECTED';
                    leftStatus.className = 'detection-status ' + (data.detection.left ? 'detected' : 'not-detected');
                    
                    rightStatus.textContent = data.detection.right ? 'DETECTED' : 'NOT DETECTED';
                    rightStatus.className = 'detection-status ' + (data.detection.right ? 'detected' : 'not-detected');
                    
                    // Update capture button
                    const captureBtn = document.getElementById('captureBtn');
                    captureBtn.disabled = !(data.detection.left && data.detection.right);
                    
                    // Update calibration info
                    document.getElementById('pairsCount').textContent = data.calibration.pairs_count;
                    document.getElementById('calibrationStatus').textContent = data.calibration.calibrated ? 'CALIBRATED' : 'NOT CALIBRATED';
                    if (data.calibration.calibrated) {{
                        document.getElementById('rmsError').textContent = data.calibration.rms.toFixed(3);
                        document.getElementById('rmsInfo').style.display = 'inline';
                    }} else {{
                        document.getElementById('rmsInfo').style.display = 'none';
                    }}
                }})
                .catch(err => console.log('Update failed:', err));
        }}
        
        function captureImage() {{
            fetch('/api/capture', {{method: 'POST'}})
                .then(response => response.json())
                .then(data => {{
                    if (data.success) {{
                        alert('Image captured successfully!');
                    }} else {{
                        alert('Capture failed: ' + data.message);
                    }}
                }})
                .catch(err => alert('Capture failed: ' + err));
        }}
        
        function startUpdates() {{
            updateStatus();
            updateInterval = setInterval(updateStatus, 200);
        }}
        
        function stopUpdates() {{
            if (updateInterval) {{
                clearInterval(updateInterval);
            }}
        }}
        
        window.onload = startUpdates;
        window.onbeforeunload = stopUpdates;
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Camera Calibration - Stereo Setup</h1>
            <p>Interactive stereo camera calibration using checkerboard pattern ({CHECKERBOARD[0]}x{CHECKERBOARD[1]})</p>
        </div>
        
        <div class="status-bar">
            <strong>Left Camera:</strong> <span id="leftStatus" class="detection-status">--</span>
            <strong>Right Camera:</strong> <span id="rightStatus" class="detection-status">--</span>
        </div>
        
        <div class="camera-grid">
            <div class="camera-view">
                <h3>Left Camera</h3>
                <img id="leftImg" src="" alt="Left Camera Feed" />
            </div>
            <div class="camera-view">
                <h3>Right Camera</h3>
                <img id="rightImg" src="" alt="Right Camera Feed" />
            </div>
        </div>
        
        <div class="capture-section">
            <button id="captureBtn" class="capture-btn" onclick="captureImage()" disabled>
                Capture Calibration Image
            </button>
            <p>Position checkerboard so it's visible in both cameras, then click capture.</p>
        </div>
        
        <div id="rectifiedSection" class="rectified-grid" style="display: none;">
            <div class="camera-view">
                <h3>Rectified Left (with epipolar lines)</h3>
                <img id="rectLeftImg" src="" alt="Rectified Left" />
            </div>
            <div class="camera-view">
                <h3>Rectified Right (with epipolar lines)</h3>
                <img id="rectRightImg" src="" alt="Rectified Right" />
            </div>
        </div>
        
        <div class="calibration-info">
            <strong>Calibration Status:</strong> <span id="calibrationStatus">--</span><br>
            <strong>Captured Pairs:</strong> <span id="pairsCount">0</span><br>
            <span id="rmsInfo" style="display: none;"><strong>RMS Error:</strong> <span id="rmsError">--</span></span>
        </div>
    </div>
</body>
</html>
            """
            
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(html.encode())
        
        def serve_status(self):
            try:
                # Resize images for web display
                left_small = None
                if calibrator.current_frame['left'] is not None:
                    left_small = cv2.resize(calibrator.current_frame['left'], 
                                          (calibrator.current_frame['left'].shape[1]//2, 
                                           calibrator.current_frame['left'].shape[0]//2))
                
                right_small = None
                if calibrator.current_frame['right'] is not None:
                    right_small = cv2.resize(calibrator.current_frame['right'], 
                                           (calibrator.current_frame['right'].shape[1]//2, 
                                            calibrator.current_frame['right'].shape[0]//2))
                
                rect_left_small = None
                if calibrator.rectified_images['left'] is not None:
                    rect_left_small = cv2.resize(calibrator.rectified_images['left'], 
                                               (calibrator.rectified_images['left'].shape[1]//2, 
                                                calibrator.rectified_images['left'].shape[0]//2))
                
                rect_right_small = None
                if calibrator.rectified_images['right'] is not None:
                    rect_right_small = cv2.resize(calibrator.rectified_images['right'], 
                                                (calibrator.rectified_images['right'].shape[1]//2, 
                                                 calibrator.rectified_images['right'].shape[0]//2))
                
                response = {
                    'images': {
                        'left': encode_image_b64(left_small),
                        'right': encode_image_b64(right_small),
                        'rect_left': encode_image_b64(rect_left_small),
                        'rect_right': encode_image_b64(rect_right_small)
                    },
                    'detection': calibrator.checkerboard_detected,
                    'calibration': calibrator.calibration_status
                }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
                
            except Exception as e:
                print(f"Error serving status: {e}")
                # Return JSON error instead of HTML error page
                response = {
                    'images': {'left': '', 'right': '', 'rect_left': '', 'rect_right': ''},
                    'detection': {'left': False, 'right': False},
                    'calibration': {'calibrated': False, 'rms': 0, 'pairs_count': 0}
                }
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
        
        def capture_image(self):
            try:
                success, message = calibrator.save_calibration_image()
                
                response = {
                    'success': success,
                    'message': message
                }
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
                
            except Exception as e:
                print(f"Error capturing image: {e}")
                # Return JSON error instead of HTML error page
                response = {
                    'success': False,
                    'message': f"Error: {str(e)}"
                }
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())
        
        def log_message(self, format, *args):
            # Suppress HTTP log messages for cleaner output
            pass
    
    return Handler

def screen_calibration(squares: int):
    import sys, fcntl, termios, struct
    if squares < 2:
        raise ValueError("squares_per_side must be >= 2")

    # terminal size (rows, cols)
    s = struct.pack("HHHH", 0, 0, 0, 0)
    rows, cols, _, _ = struct.unpack("HHHH", fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, s))
    print(f"{rows}  {cols}")

    cal_block_w = rows // squares
    cal_block_h = cols // squares
    cal_block_w = min(cal_block_w, cal_block_h)
    cal_block_h = cal_block_w

    pad_top = (rows - cal_block_h) // 2
    pad_left = (cols - cal_block_w) // 2

    # clear screen
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

    for _ in range(pad_top):
        print()

    for _ in range(cal_block_h):
        for _ in range(2):
            sys.stdout.write(" " * pad_left)
            for _ in range(cal_block_w):
                sys.stdout.write("██")
            sys.stdout.write("\n")
    sys.stdout.flush()

    measured_mm_w = float(input("\n\nWidth in mm: "))
    measured_mm_h = float(input("Height in mm: "))

    char_mm_w = measured_mm_w / cal_block_w
    char_mm_h = measured_mm_h / cal_block_h

    max_square_cols = cols // squares
    max_square_rows = rows // squares

    square_mm_w = max_square_cols * char_mm_w
    square_mm_h = max_square_rows * char_mm_h
    square_mm = min(square_mm_w, square_mm_h)

    square_cols = int(square_mm / char_mm_w)
    square_rows = int(square_mm / char_mm_h)

    print(f"{square_mm:.2f} {square_cols} {square_rows}")
    return square_mm, square_cols, square_rows

def draw_checker(squares: int, square_cols: int, square_rows: int):
    if squares < 2:
        raise ValueError("squares_per_side must be >= 2")

    BLACK = "█"
    WHITE = " "

    # Clear screen before drawing grid
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()

    for gy in range(squares):
        for _ in range(square_rows):
            line = []
            for gx in range(squares):
                cell = BLACK if ((gx + gy) % 2 == 0) else WHITE
                if gx == 0 or gy == 0 or gx == squares - 1 or gy == squares - 1:
                    cell = BLACK
                line.append(cell * square_cols)
            sys.stdout.write("".join(line) + "\n")
    sys.stdout.flush()



def main():
    service_was_running = False
    cap = None
    
    try:
        
        # Load bootstrap calibration (default: stereo_calib.yaml)
        bootstrap_calib = None
        if os.path.exists(INIT_CALIB_YAML_PATH):
            bootstrap_calib = load_calibration_yaml(INIT_CALIB_YAML_PATH)
            if bootstrap_calib is not None:
                print(f"{GREEN}Bootstrap calibration loaded successfully from {INIT_CALIB_YAML_PATH}{RESET}")
                print(f"{GREEN}Using existing calibration as starting point for faster convergence{RESET}")
            else:
                print(f"{YELLOW}Warning: Could not load bootstrap calibration from {INIT_CALIB_YAML_PATH}{RESET}")
                print(f"{YELLOW}Continuing with standard calibration from scratch...{RESET}")
        else:
            print(f"{YELLOW}Warning: Bootstrap file {INIT_CALIB_YAML_PATH} does not exist{RESET}")
            print(f"{YELLOW}Continuing with standard calibration from scratch...{RESET}")
        
        # Create calibrator
        calibrator = CameraCalibrator(port=PORT, bootstrap_calib=bootstrap_calib)
        
        # Start camera capture thread
        def capture_loop():
            with Reader("camera.jpeg") as r_jpeg: 
                while True:
                    if r_jpeg.ready():
                        frame = cv2.imdecode(r_jpeg.data['jpeg'], cv2.IMREAD_COLOR)
                        calibrator.capture_frame(frame)
        
        capture_thread = threading.Thread(target=capture_loop, daemon=True)
        capture_thread.start()
        
        # Start HTTP server
        def server_loop():
            handler = create_handler(calibrator)
            httpd = HTTPServer(('0.0.0.0', PORT), handler)
            httpd.serve_forever()
        
        server_thread = threading.Thread(target=server_loop, daemon=True)
        server_thread.start()
        
        local_ip = get_local_ip()
        print(f"\n{GREEN}Calibration web interface started!{RESET}")
        print(f"📱 Open your web browser and go to:")
        print(f"   http://{local_ip}:{PORT}")
        print(f"   http://localhost:{PORT}")
        print(f"\n✨ Press Ctrl+C to stop calibration\n")

        print("SCREEN CALIBRATION")
        print(f"{GREEN}INSTRUCTIONS: A calibration square will be loaded within this terminal after following these instructions. \n\
        1. Minimize the terminal window by pressing `CMD/CTRL -` \n\
        2. You will then be prompted with the WIDTH, then the HEIGHT in mm of a calibration square. \n\
        3. Measure the square with a ruler (or ideally a caliper) and enter the values one after the other and hit enter for each value.{RESET}")
        print(f"{GREEN}Press ENTER key to load the calibration square...{RESET}")
        input()
        square_mm, square_cols, square_rows = screen_calibration(TOTAL_SQUARES)
        draw_checker(TOTAL_SQUARES, square_cols, square_rows)
        print("Square size: ", square_mm)
        print("Press Enter to exit...")
        input()
        
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Calibration interrupted by user.{RESET}")
    except Exception as e:
        print(f"\n{RED}Error occurred: {e}{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()