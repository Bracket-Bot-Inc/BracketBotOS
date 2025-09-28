from bbos import register, realtime
import numpy as np


@register
class slam:
    rate: int = 10  # SLAM update rate in Hz
    enabled: bool = False  # Whether SLAM is active
    pose_buffer_size: int = 1000


# Data structures for SLAM output
@realtime(ms=100)
def slam_pose():
    """Current pose: position (x,y,z) and quaternion (x,y,z,w)"""
    return [
        ("pos", np.float32, 3), # x, y, z
        ("quat", np.float32, 4), # x, y, z, w
    ]