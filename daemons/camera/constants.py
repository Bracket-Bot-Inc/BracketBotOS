from bbos.registry import register
import numpy as np


@register
class CFG_camera_stereo_OV9281:
    fps: int = 120  # Frames per second (camera supports 120fps at 2560x720 MJPG)
    dev: int = 0  # device id /dev/video<dev>
    jpeg_quality: int = 80  # JPEG compression quality (1-100)
    width: int = 2560  # stereo image width
    height: int = 720  # stereo image height


@register
def camera_stereo_OV9281():
    return camera_stereo(CFG_camera_stereo_OV9281.width,
                         CFG_camera_stereo_OV9281.height)


def camera_stereo(width, height):
    return [
        ("stereo", np.uint8, (height, width, 3)),
    ]
