#!/usr/bin/env python3
import signal, sys, numpy as np
from bbos import Writer, Reader, Type, Time
from bbos.os_utils import gateway

SPEED_LIN = 2.0  # m s⁻¹  forward/back
SPEED_ANG = 4.0  # rad s⁻¹ CCW+

# ----------------------------------------------------------------------
# main
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print("teleop webpage: https://" + gateway() + ":8000")

    with Writer("/drive.ctrl", Type("drive_ctrl")) as w_ctrl, \
         Reader("/mobile.joystick") as r_joy:
        t = Time(50)
        while True:
            if r_joy.ready():
                stale, joy = r_joy.get()
                state = joy['state']
                cmd = state[1] * SPEED_LIN, -state[0] * SPEED_ANG
                with w_ctrl.buf() as b:
                    b["twist"][:] = cmd
            t.tick()

print("Shutdown complete.")
