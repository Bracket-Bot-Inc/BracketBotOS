from bbos.registry import *
from bbos.os_utils import Priority

import numpy as np


@register
class depth:
    block_size = 23
    max_disp = 160  # in pixels
    num_disp = 128  # in pixels
    min_disp = -32
    uniqueness = 7
    speckle_w_size = 150
    speckle_range = 1
    prefilter_cap = 21


@realtime(10, Priority.CTRL_MED, [0, 1])
def camera_depth(height, width):
    return [
        ("depth", np.uint16, (height, width)),
    ]


@realtime(10, Priority.CTRL_MED, [0, 1])
def camera_points(height, width):
    return [
        ("points", np.float64, (height, width, 3)),
        ("colors", np.uint8, (height, width, 3)),
    ]
