from bbos.registry import *
import numpy as np


@register
class depth:
    stride = 4         # Process every Nth frame to reduce CPU usage
    downsample= 0.5   # 37.5 % resolution → faster and less noisy
    window_size= 23   # StereoBM block size
    min_disp= -64
    num_disp= 128     # Must be multiple of 16
    uniqueness=7
    speckle_window= 150
    speckle_range= 1
    pre_filter_cap= 21
    max_range= 8.0

@register
class points:
    stride = 4         # Process every Nth frame to reduce CPU usage
    max_range= 5.0


@realtime(ms=80)
def camera_depth(height, width):
    return [
        ("rect", np.float64, (2, height, width, 3)),
        ("depth", np.uint16, (height, width)),
    ]


@realtime(ms=80)
def camera_points(num_points):
    return [
        ("num_points", np.int32),
        ("points", np.float64, (num_points, 3)),
        ("colors", np.uint8, (num_points, 3)),
    ]
