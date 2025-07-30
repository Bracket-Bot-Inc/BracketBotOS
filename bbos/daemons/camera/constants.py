from bbos import register, realtime
from bbos.os_utils import Priority

import numpy as np


@register
class stereo:
    rate: int = 20  # Frames per second (camera supports 120fps at 2560x720 MJPG)
    dev: int = 0  # device id /dev/video<dev>
    width: int = 2560  # stereo image width
    height: int = 720  # stereo image height
    fov_diag = 180  # degrees
    r = np.sqrt((width / 2)**2 + height**2)
    xfov = 147
    yfov = 83
    f_x = (width / 2) / (2 * np.tan(np.deg2rad(xfov) / 2))


@realtime(15, Priority.CTRL_HIGH, [0,1,2,3,4,5,6,7])
def camera_jpeg(buflen):
    return [
        ("bytesused", np.uint32),
        ("jpeg", np.uint8, buflen),
    ]