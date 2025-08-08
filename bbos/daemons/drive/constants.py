from bbos import register, realtime


import numpy as np


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class drive:
    rate_status: int = 1
    rate_state: int = 50
    robot_width: float = 0.21


@register
class odrive:
    serial_port: str = "/dev/ttyS2"
    baudrate: int = 115200
    timeout: int = 15  # seconds
    left_axis: int = 0
    right_axis: int = 1
    axis_state_closed_loop: int = 8
    dir_left: int = 1  # Motor direction for left axis (1 or -1)
    dir_right: int = -1  # Motor direction for right axis (1 or -1)
    wheel_diam: float = 0.165
    torque_bias: float = 0.05


# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------


@realtime(ms=30)
def drive_ctrl():
    return [("twist", (np.float32, 2))]  # linear, angular


@realtime(ms=30)
def drive_state():
    return [("pos", (np.float32, 2)), ("vel", (np.float32, 2)),
            ("torque", (np.float32, 2))]


@realtime(ms=1000)
def drive_status():
    return [
        ("voltage", np.float32),
    ]
