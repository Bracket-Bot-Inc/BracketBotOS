from bbos.registry import register
import numpy as np


@register
class device_imu:
    rate = 50


@register
def imu():
    return [
        ("gyro", np.float32, 3),  # alpha, beta, gamma
        ("accel", np.float32, 6),  # ax,ay,az,rx,ry,rz
    ]
