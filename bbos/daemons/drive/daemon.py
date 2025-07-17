from bbos import Reader, Writer, Config, Type, Time
from bbos.os_utils import Priority, config_realtime_process
from driver import ODriveUART

import numpy as np
import signal, sys, traceback

# ----------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------
CFG_drive = Config("drive")  # rates
CFG_odrive = Config("odrive")  # hardware + axis map

if __name__ == "__main__":
    with Writer('/drive.state', Type("drive_state"))   as w_state, \
         Writer('/drive.status', Type("drive_status")) as w_status, \
         Reader('/drive.ctrl')                         as r_ctrl:
        config_realtime_process(3, Priority.CTRL_HIGH)
        od = ODriveUART(CFG_odrive)
        ts = Time(CFG_drive.rate_state)
        tst = Time(CFG_drive.rate_status)
        tsc = Time(50)
        od.clear_errors_left()
        od.clear_errors_right()
        od.start_left()
        od.enable_velocity_mode_left()
        od.start_right()
        od.enable_velocity_mode_right()
        od.set_speed_turns_left(0)
        od.set_speed_turns_right(0)
        R = CFG_drive.robot_width * 0.5  # half-baseline
        while True:
            # -------------------------------------------------------------- state out
            if ts.tick(block=False):
                with w_state.buf() as s:
                    p_l, v_l = od.get_pos_vel_left()
                    p_r, v_r = od.get_pos_vel_right()
                    s['pos'][:] = [p_l, p_r]
                    s['vel'][:] = [v_l, v_r]

            # -------------------------------------------------------------- status
            if tst.tick(block=False):
                with w_status.buf() as st:
                    st['voltage'] = float(od.get_bus_voltage())

            # -------------------------------------------------------------- twist in
            if r_ctrl.ready() and tsc.tick(block=False):
                _, d = r_ctrl.get()
                vd, wd = map(float, d['twist'])  # desired linear, angular
                vd_l, vd_r = vd - wd * R, vd + wd * R
                od.set_speed_mps_left(vd_l)
                od.set_speed_mps_right(vd_r)
    od.stop_left()
    od.stop_right()
    print("state", ts.stats)
    print("status", tst.stats)
    print("ctrl", tsc.stats)
