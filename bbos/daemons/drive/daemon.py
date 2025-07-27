from bbos import Reader, Writer, Config, Type, Loop
from driver import ODriveUART

CFG_drive = Config("drive")
CFG_odrive = Config("odrive")

if __name__ == "__main__":
    with Writer('/drive.state', Type("drive_state"))   as w_state, \
         Writer('/drive.status', Type("drive_status")) as w_status, \
         Reader('/drive.ctrl')                         as r_ctrl:
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
            p_l, v_l = od.get_pos_vel_left()
            p_r, v_r = od.get_pos_vel_right()
            with w_state.buf() as b:
                b['pos'] = [p_l, p_r]
                b['vel'] = [v_l, v_r]
            w_status['voltage'] = float(od.get_bus_voltage())
            if r_ctrl.ready():
                vd, wd = map(float, r_ctrl.data['twist'])  # desired linear, angular
                vd_l, vd_r = vd - wd * R, vd + wd * R
            if not r_ctrl.readable:
                vd_l, vd_r = 0, 0
            od.set_speed_mps_left(vd_l)
            od.set_speed_mps_right(vd_r)
            Loop.sleep()
    od.stop_left()
    od.stop_right()
