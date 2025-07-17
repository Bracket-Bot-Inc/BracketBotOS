#!/usr/bin/env python3
import signal, sys, numpy as np
from bbos import Writer, Reader, Type, Time

SPEED_LIN = 2.0  # m s⁻¹  forward/back
SPEED_ANG = 2.0  # rad s⁻¹ CCW+

# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------
if __name__ == "__main__":
    with Writer("/drive.ctrl", Type("drive_ctrl")) as w_ctrl, \
         Reader("/mobile.imu") as r_mobile_imu:
        t = Time(50)
        while True:
            if r_mobile_imu.ready():
                stale, imu = r_mobile_imu.get()
                gyro = imu['gyro']
                cmd = gyro[1] * -SPEED_LIN, gyro[0] * SPEED_ANG
                with w_ctrl.buf() as b:
                    b["twist"][:] = cmd
            t.tick()

print("Shutdown complete.")
