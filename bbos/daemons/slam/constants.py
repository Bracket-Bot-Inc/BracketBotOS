from bbos import *
from bbos.registry import *
import numpy as np
from pathlib import Path

CFG_C = Config("stereo")

@register
class slam:
    maps_dir: str = Path(__file__).parent / ".maps"
    history_len: int = 10


@state
def slam_trigger():
    return [("relocalize", np.bool_), ("save_map", np.bool_)]

# Data structures for SLAM output
@realtime(ms=70)
def slam_pose():
    """Current pose: position (x,y,z) and quaternion (x,y,z,w)"""
    return [
        ("pos", np.float32, 3), # x, y, z
        ("quat", np.float32, 4), # x, y, z, w
    ]

@realtime(ms=70)
def slam_debug():
    """Debug image, points, and colors"""
    return [
        ("img", np.uint8, (CFG_C.height, CFG_C.width // 2, 3)),
    ]