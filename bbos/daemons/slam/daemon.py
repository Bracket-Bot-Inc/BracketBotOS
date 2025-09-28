from bbos import Writer, Reader, Config

import cuvslam as vslam
import time
import numpy as np


def main():
    CFG = Config("slam")
    CFG_C = Config("camera")
    CFG_D = Config("depth")
    
    odom_cfg = vslam.Tracker.OdometryConfig(
        async_sba=False,
        enable_final_landmarks_export=True,
        enable_observations_export=True,
        horizontal_stereo_camera=False,
    )

    cam = vslam.Camera(
        border_bottom=0,
        border_top=0,
        border_left=0,
        border_right=0,
        focal=CFG_C.f_x,
        principal_point=(320, 240),
        rig_from_camera=vslam.Pose(
            rotation=list(CFG_D.T_base_cam.quat()),
            translation=list(CFG_D.T_base_cam.pos()),
        ),
        image_size=(CFG_C.width, CFG_C.height),
    )
    tracker = vslam.Tracker(vslam.Rig([cam]), odom_cfg)

    with Reader("camera_jpeg") as r_cam, \
         Writer("slam.pose") as w_pose:
        pos = np.zeros(3)
        quat = np.zeros(4)
        while True:
            if r_cam.ready():
                jpeg_data = r_cam.data["jpeg"][:r_cam["bytesused"]]
                stereo = cv2.imdecode(jpeg_data, cv2.IMREAD_COLOR)
                odom, _ =tracker.track(r_cam.data["timestamp"].astype("int64"), [CFG_C.split(stereo)])
                if odom.world_from_rig is None:
                    print("Warning: Pose tracking not valid")
                    continue
                pos = np.array(odom.world_from_rig.translation)
                quat = np.array(odom.world_from_rig.rotation)
                #tracker.export_landmarks(r_cam.data["timestamp"].astype("int64"))
            with w_pose.buf() as b:
                b["pos"] = pos
                b["quat"] = quat


if __name__ == "__main__":
    main()
