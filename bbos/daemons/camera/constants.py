from bbos import register, realtime


import numpy as np


@register
class stereo:
    rate: int = 20  # Frames per second (camera supports 120fps at 2560x720 MJPG)
    dev: int = 0  # device id /dev/video<dev>
    width: int = 2560  # stereo image width
    height: int = 720  # stereo image height
    fov_diag = 180  # degrees
    r = np.sqrt((width / 2)**2 + height**2)
    xfov = 180
    yfov = 83
    f_x = 1500 
    @staticmethod
    def split(stereo_img: np.ndarray):
        assert stereo_img.shape[1] == stereo.width and stereo_img.shape[0] == stereo.height
        return stereo_img[:, stereo.width//2:], stereo_img[:, :stereo.width//2] # NOTE: left/right are flipped


@realtime(ms=70)
def camera_jpeg(buflen):
    return [
        ("bytesused", np.uint32),
        ("jpeg", np.uint8, buflen),
    ]