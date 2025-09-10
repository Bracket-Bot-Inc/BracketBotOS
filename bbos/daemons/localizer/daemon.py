#!/usr/bin/env python
import numpy as np
from bbos import Reader, Writer, Config, Type
#from model import DiffDriveEstimator2D
import matplotlib.pyplot as plt

def compute_odometry(
    left_turns: float,
    right_turns: float,
    prev_left: float,
    prev_right: float,
    x: float,
    y: float,
    yaw: float,
    wheel_diam: float,
    base_width: float,
):
    """Incremental odometry update using differential drive kinematics.
    
    Coordinate system: Y=forward, X=right, Z=up (standard robotics)
    Yaw=0 points forward (+Y), negative yaw is to the right
    """
    delta_left_turns = left_turns - prev_left
    delta_right_turns = right_turns - prev_right

    delta_left = delta_left_turns * np.pi * wheel_diam
    delta_right = delta_right_turns * np.pi * wheel_diam

    delta_distance = (delta_left + delta_right) / 2.0
    delta_theta = (delta_right - delta_left) / base_width

    # Y is forward, X is right
    # yaw=0 points forward (+Y), negative yaw is to the right
    y += delta_distance * np.cos(yaw + delta_theta / 2.0)  # Forward movement
    x += delta_distance * -np.sin(yaw + delta_theta / 2.0)  # Right movement (negative sin for correct direction)
    yaw += delta_theta

    # Note: Yaw is NOT normalized to allow continuous accumulation across multiple rotations
    # This enables proper tracking when the robot spins multiple times

    return x, y, yaw, left_turns, right_turns

if __name__ == "__main__":
    CFG = Config("localizer")
    CFG_odrive = Config("odrive")
    CFG_drive = Config("drive")
    print(f"[Localizer] Daemon started - State estimation using wheel odometry and IMU")
    # Initialize state writer
    with Reader('imu.data') as r_imu, \
         Reader('drive.state') as r_drive, \
         Writer('localizer.pose', Type("localizer_pose")) as w_pose:

        # estimator = DiffDriveEstimator2D(
        #     base_width_m=CFG_drive.robot_width,
        #     wheel_diam_m=CFG_odrive.wheel_diam,
        #     grid_axis=CFG.grid_axis,
        #     grid_axis_sign=CFG.grid_axis_sign,
        #     gyro_beta_std=np.deg2rad(0.5),
        #     beta_is_biased=True,  # Estimate gyro bias
        #     q_theta=1e-3,
        #     q_x=5e-2,
        #     q_y=5e-2
        # )
        x = y = yaw = 0.0  # x=right, y=forward, yaw=heading
        last_left = last_right = None
        # Main loop
        imu_data = None
        drive_state = None
        traj = []
        while True:
            if r_imu.ready():
                #resimu = estimator.update_imu(r_imu.data)
                pass
            if r_drive.ready():
                #res = estimator.update_drive(r_drive.data)
                if last_left is None:
                    last_left = r_drive.data['pos'][0]
                    last_right = r_drive.data['pos'][1]
                x, y, yaw, last_left, last_right = compute_odometry(
                    r_drive.data['pos'][0],
                    r_drive.data['pos'][1],
                    last_left,
                    last_right,
                    x,
                    y,
                    yaw,
                    CFG_drive.wheel_diam,
                    CFG_drive.robot_width
                )
                traj.append({'x': x, 'y': y, 'yaw': yaw})
            with w_pose.buf() as buf:
                if len(traj) > 0:
                    buf['theta'] = yaw
                    buf['x'] = x
                    buf['y'] = y