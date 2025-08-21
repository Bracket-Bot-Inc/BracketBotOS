from bbos import Reader, Writer, Config, Type
from driver import ODriveUART
import numpy as np
import time

CFG_drive = Config("drive")
CFG_odrive = Config("odrive")

if __name__ == "__main__":
    with Writer('drive.state', Type("drive_state"))   as w_state, \
         Writer('drive.status', Type("drive_status")) as w_status, \
         Reader('drive.ctrl')                         as r_ctrl:
        od = ODriveUART(CFG_odrive)
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
            if od.has_errors():
                od.dump_errors()
                od.clear_errors_left()
                od.clear_errors_right()
            p_l, v_l = od.get_pos_vel_left()
            p_r, v_r = od.get_pos_vel_right()
            with w_state.buf() as b:
                b['pos'] = [p_l, p_r]
                b['vel'] = [v_l, v_r]
            w_status['voltage'] = float(od.get_bus_voltage())
            if r_ctrl.ready():
                vd, wd = r_ctrl.data['twist'][:2]  # desired linear, angular
                vd_l, vd_r = vd - (wd * R) / 2, vd + (wd * R) / 2, 
            if not r_ctrl.readable or (np.datetime64(time.time_ns(), "ns") - r_ctrl.data['timestamp']) > np.timedelta64(200, "ms"):
                vd_l, vd_r = 0, 0
            od.set_speed_mps_left(vd_l)
            od.set_speed_mps_right(vd_r)
    od.stop_left()
    od.stop_right()