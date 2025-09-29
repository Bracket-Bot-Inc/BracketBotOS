from bbos import Writer, Reader, Config, Type
from bbos.tf import trans
import cuvslam as vslam
import time
import numpy as np
import cv2


def main():
    CFG = Config("slam")
    CFG_C = Config("stereo")
    CFG_D = Config("depth")
    
    odom_cfg = vslam.Tracker.OdometryConfig(
        async_sba=False,
        enable_final_landmarks_export=True,
        enable_observations_export=True,
        horizontal_stereo_camera=False,
    )

    mtx_l, dist_l, mtx_r, dist_r, R1, R2, P1, P2, Q, baseline_m, fx_ds = CFG_D.camera_cal()
    cams = []
    for xoff, mtx in [(0, mtx_l), (baseline_m, mtx_r)]:
        cams.append(vslam.Camera(
            border_bottom=0,
            border_top=0,
            border_left=0,
            border_right=0,
            focal=(mtx[0, 0],mtx[1,1]),
            principal=(mtx[0, 2],mtx[1,2]),
            rig_from_camera=vslam.Pose(
                rotation=list(CFG_D.T_base_cam.quat()),
                translation=list((CFG_D.T_base_cam @ trans([xoff, 0, 0])).pos()),
            ),
            size=[CFG_C.width // 2, CFG_C.height],
        ))
    tracker = vslam.Tracker(vslam.Rig(cams), odom_cfg)

    with Reader("camera.jpeg") as r_cam, \
         Writer("slam.pose", Type("slam_pose")) as w_pose:
        pos = np.zeros(3)
        quat = np.zeros(4)
        while True:
            if r_cam.ready():
                stereo = cv2.imdecode(r_cam.data['jpeg'], cv2.IMREAD_COLOR)
                l, r = CFG_C.split(stereo)
                odom, _ = tracker.track(int(r_cam.data["timestamp"]), images=[np.ascontiguousarray(l), np.ascontiguousarray(r)])
                if odom.world_from_rig is None:
                    print("Warning: Pose tracking not valid")
                    continue
                pos = np.array(odom.world_from_rig.pose.translation)
                quat = np.array(odom.world_from_rig.pose.rotation)
                #tracker.export_landmarks(r_cam.data["timestamp"].astype("int64"))
            with w_pose.buf() as b:
                b["pos"] = pos
                b["quat"] = quat


if __name__ == "__main__":
    main()
