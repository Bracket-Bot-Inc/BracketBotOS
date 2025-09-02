from bbos import register, realtime, state
import numpy as np

# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class so101:
    port = "/dev/ttyACM0"       # adjust for your system
    baudrate = 1000000
    motors = [1, 2, 3, 4, 5, 6]
    dof = len(motors)
    wristcam_width = 640
    wristcam_height = 480
# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------

@state
def so101_torque():
    return [("enable", np.bool_, so101.dof)]

@realtime(ms=20)
def so101_ctrl():
    return [("pos", np.float32, so101.dof), ("vel", np.float32, so101.dof)]

@realtime(ms=20)
def so101_state():
    return [("pos", np.float32, so101.dof), ("vel", np.float32, so101.dof), ("torque", np.float32, so101.dof)]

@realtime(ms=60)
def so101_wristcam():
    return [("cam", np.uint8, (so101.wristcam_height, so101.wristcam_width, 3))]