from bbos import register, realtime
import numpy as np


@register
class stereo:
    rate: int = 15  # Frames per second (camera supports 120fps at 2560x720 YUYV)
    dev: int = 2  # device id /dev/video<dev>
    width: int = 1280  # stereo image width
    height: int = 480  # stereo image height
    fmt: str = "YUYV"
    @staticmethod
    def split(stereo_img: np.ndarray):
        assert stereo_img.shape[1] == stereo.width and stereo_img.shape[0] == stereo.height
        if stereo.fmt == "MJPEG":
            return stereo_img[:, stereo.width//2:], stereo_img[:, :stereo.width//2] # NOTE: left/right are flipped
        else:
            return stereo_img[:, :stereo.width//2], stereo_img[:, stereo.width//2:]

@realtime(ms=70)
def camera_rgb():
    return [
        ("rgb", np.uint8, (stereo.height, stereo.width, 3)),
    ]