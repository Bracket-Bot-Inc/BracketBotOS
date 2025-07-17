from bbos.registry import register

import numpy as np


@register
def camera_depth(height, width):
    return [
        ("depth", np.float64, (height, width, 1)),
    ]


@register
def camera_points(height, width):
    return [
        ("points", np.float64, (height, width, 3)),
        ("colors", np.uint8, (height, width, 3)),
    ]
