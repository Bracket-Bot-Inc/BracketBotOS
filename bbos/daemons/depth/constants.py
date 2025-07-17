from bbos.registry import register

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


@register
def camera_depth(height, width):
    return [
        ("depth", np.uint16, (height, width)),
    ]


@register
def camera_points(height, width):
    return [
        ("points", np.float64, (height, width, 3)),
        ("colors", np.uint8, (height, width, 3)),
    ]
