from bbos.registry import *
import numpy as np
from bbos.tf import *

# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class localizer:
    grid_axis: int = 0
    grid_axis_sign: int = 1
    T_origin_base = lambda pose: trans([pose['x'], pose['y'], 0]) @ rot([0,0,1], np.rad2deg(pose['theta']))
    cov_odom = np.diag([0.04, 0.04, np.deg2rad(2.0)])**2


# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------
@realtime(ms=50, priority=70)
def localizer_pose():
    """Localizer pose: x, y, theta"""
    return [
        ("x", np.float32),
        ("y", np.float32),
        ("theta", np.float32),
    ]