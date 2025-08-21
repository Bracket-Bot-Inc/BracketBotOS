from bbos.registry import *
from bbos.tf import *
import numpy as np


@register
class depth:
    downsample = 0.5   # 37.5 % resolution → faster and less noisy
    window_size = 21   # StereoBM block size
    min_disp = -16
    num_disp = 64     # Must be multiple of 16
    uniqueness = 7
    speckle_window = 150
    speckle_range = 1
    pre_filter_cap = 21
    T_cam = rot([0,0,1],180) @ trans([0,-1.55,0]) @ rot([1,0,0],-36)
    #T_cam = trans([0,0,0])

@register
class points:
    stride = 2         # Process every Nth frame to reduce CPU usage
    max_range = 5.0


@realtime(ms=100)
def camera_depth(height, width):
    return [
        ("rect", np.float64, (2, height, width, 3)),
        ("depth", np.uint16, (height, width)),
    ]


@realtime(ms=100)
def camera_points(num_points):
    return [
        ("num_points", np.int32),
        ("points", np.float16, (num_points, 3)), # Transform convention, z is out of the camera imager and origin is the center of the camera imager
        ("colors", np.uint8, (num_points, 3)),
    ]