from bbos import Writer, Reader, Config, Type
from bbos.tf import trans, rmat
import cuvslam as vslam
import time
import numpy as np
import cv2
import queue
import numpy as np
from scipy.spatial.transform import Rotation as Rot

def splat_points_on_image(img, pts, colors, R=5, alpha=1.0, palette=None):
    """
    Draw filled disks of radius R centered at (u,v) points onto an existing image.

    Args:
        img: (H, W, 3) uint8 image (RGB or BGR—your choice, just match `colors`).
        pts: (N, 2) float array of (u, v) image coords. (x=u, y=v)
        colors:
            - If palette is None: (N, 3) uint8 per-point colors.
            - If palette provided: (N,) uint8 color IDs indexing `palette`.
        R: integer radius in pixels (filled circle).
        alpha: float in [0,1] or (N,) per-point alphas. 1.0 overwrites, <1 blends.
        palette: optional (M, 3) uint8; maps color IDs -> colors.

    Returns:
        The modified image (same array object as `img`, edited in place).
    """
    H, W = img.shape[:2]
    pts = np.asarray(pts, dtype=np.float32)

    # Resolve colors → (N,3) uint8
    if palette is not None:
        palette = np.asarray(palette, dtype=np.uint8)
        ids = np.asarray(colors)
        assert ids.ndim == 1, "When using a palette, `colors` must be (N,) IDs."
        assert ids.max() < len(palette), "Color id exceeds palette size."
        cols = palette[ids]
    else:
        cols = np.asarray(colors, dtype=np.uint8)
        assert cols.shape == (len(pts), 3), "`colors` must be (N,3) when no palette."

    # Alpha → per-pixel scalar list
    if np.isscalar(alpha):
        alphas = np.full((len(pts),), float(alpha), dtype=np.float32)
    else:
        alphas = np.asarray(alpha, dtype=np.float32)
        assert alphas.shape == (len(pts),), "`alpha` must be scalar or (N,)"

    # Round to nearest integer pixel center
    x = np.rint(pts[:, 0]).astype(np.int32)
    y = np.rint(pts[:, 1]).astype(np.int32)

    # Precompute disk offsets
    ys, xs = np.mgrid[-R:R+1, -R:R+1]
    disk = (xs*xs + ys*ys) <= R*R
    dy = ys[disk].ravel()
    dx = xs[disk].ravel()
    K = dy.size  # pixels per disk

    # All target pixel coordinates
    yy = (y[:, None] + dy[None, :]).reshape(-1)
    xx = (x[:, None] + dx[None, :]).reshape(-1)

    # Repeat colors & alphas per covered pixel
    cols_rep = np.repeat(cols, K, axis=0)            # (N*K, 3)
    alpha_rep = np.repeat(alphas, K).astype(np.float32)  # (N*K,)

    # Clip to bounds
    inb = (yy >= 0) & (yy < H) & (xx >= 0) & (xx < W)
    yy, xx = yy[inb], xx[inb]
    cols_rep = cols_rep[inb]
    alpha_rep = alpha_rep[inb]

    # Flattened indices into image
    flat = img.reshape(-1, 3)
    idx = yy * W + xx

    if np.all(alpha_rep >= 1.0):
        # Overwrite fast-path
        flat[idx] = cols_rep
    else:
        # Alpha blend: out = (1-a)*dst + a*src
        dst = flat[idx].astype(np.float32)
        src = cols_rep.astype(np.float32)
        a = alpha_rep[:, None]  # (N*K, 1)
        flat[idx] = np.clip((1.0 - a) * dst + a * src, 0, 255).astype(np.uint8)

    return img


def main():
    CFG = Config("slam")
    CFG_C = Config("stereo")
    CFG_D = Config("depth")
    
    mtx_l, dist_l, mtx_r, dist_r, R1, R2, P1, P2, Q, baseline_m, fx_ds, R, t = CFG_D.camera_cal()
    cams = []
    for rot, t, P, dist in [(np.eye(3), np.zeros(3), P1, dist_l), (R, t, P2, dist_r)]:
        #tf = rmat(R) @ trans(-t)
        quat = Rot.from_matrix(rot).as_quat()  # [x, y, z, w]
        print(quat, t)

        cams.append(vslam.Camera(
            focal=(P[0, 0],P[1,1]),
            principal=(P[0, 2],P[1,2]),
            rig_from_camera=vslam.Pose(
                rotation=quat.tolist(),
                translation=t.tolist(),
            ),
            distortion=vslam.Distortion(
                model=vslam.Distortion.Model.Fisheye,
                parameters=dist,
            ),
            size=[CFG_C.width // 2, CFG_C.height],
        ))
    odom_cfg = vslam.Tracker.OdometryConfig(
        async_sba=False,
        enable_observations_export=True,
        enable_final_landmarks_export=True,
        horizontal_stereo_camera=False,
        odometry_mode=vslam.Tracker.OdometryMode.Multicamera

    )  
    slam_cfg = vslam.Tracker.SlamConfig(
        use_gpu=True,                 # keep SLAM on GPU
        sync_mode=False,              # SLAM in its own thread (recommended)
        throttling_time_ms=800,       # min time between LC events (tune below)
        max_map_size=0,               # 0 = unlimited pose graph (good for large loops)
        planar_constraints=True       # if your rig is ground vehicle; else False
    )
    # loc_cfg = vslam.Tracker.SlamLocalizationSettings(
    #     angular_step_rads=0.1,
    #     horizontal_search_radius=10,
    #     horizontal_step=0.2,
    #     vertical_search_radius=0.3,
    #     vertical_step=0.05,
    # )

    tracker = vslam.Tracker(vslam.Rig(cams), odom_cfg, slam_cfg)
    with Reader("camera.rgb", sync=True) as r_rect, \
         Reader("slam.trigger", Type("slam_trigger")) as r_trigger, \
         Writer("slam.pose", Type("slam_pose"), buf_ms=100) as w_pose, \
         Writer("slam.debug", Type("slam_debug")) as w_debug:
        pos = np.zeros(3)
        quat = np.zeros(4)
        t0 = time.monotonic()
        left = np.zeros((CFG_C.height, CFG_C.width // 2, 3), dtype=np.uint8)
        colors = {}
        img_buffer = np.zeros((CFG.history_len, CFG_C.height, CFG_C.width // 2, 3), dtype=np.uint8)
        logs = queue.Queue(maxsize=5)
        while True:
            if not logs.empty():
                print(logs.get_nowait(), flush=True)
            if r_trigger.ready():
                if r_trigger.data["relocalize"]:
                    def on_relocalize(success):
                        logs.put(f"relocalized={success}")
                    print("relocalizing", flush=True)
                    tracker.localize_in_map(CFG.map_path, 
                        cuvslam.Pose(orientation=np.array([0, 0, 0, 1]), translation=np.array([0, 0, 0])), 
                        [img_buffer[i] for i in range(len(img_buffer))], 
                        loc_cfg, 
                        on_relocalize)
                if r_trigger.data["save_map"]:
                    def on_save_map(saved):
                        logs.put(f"saved={saved}!")
                    print("saving map", flush=True)
                    save_path = f"{CFG.maps_dir}/map_{r_trigger.data['timestamp']}"
                    tracker.save_map(save_path, on_save_map)
            if r_rect.ready():
                t0 = time.monotonic()
                stereo = r_rect.data["rgb"]
                left_view, right = CFG_C.split(stereo)
                left = left_view.copy()
                img_buffer[0] = left.copy()
                imgs = [np.ascontiguousarray(left_view), np.ascontiguousarray(right)]
                odom, slam_odom = tracker.track(int(r_rect.data["timestamp"].astype('int64')), images=imgs)
                m = tracker.get_slam_metrics()
                if slam_odom is not None:
                    pose_for_use = slam_odom
                else:
                    pose_for_use = odom.world_from_rig.pose
                if pose_for_use is not None:
                    pos = np.array(pose_for_use.translation)
                    quat = np.array(pose_for_use.rotation)
                    obs = tracker.get_last_observations(0)
                    pts = np.array([[o.u, o.v] for o in obs])
                    for o in obs:
                        if o.id not in colors:
                            colors[o.id] = np.random.randint(0, 256, size=3)
                    colors_np = np.array([
                        colors[o.id] for o in obs
                    ])
                    # pts are (u,v) floats in image coordinates, color a 5 pixel radius around the point
                    splat_points_on_image(left, pts, colors_np, R=2)
                else:
                    print("Warning: Pose tracking not valid")
            with w_pose.buf() as b:
                b["pos"] = pos
                b["quat"] = quat
            with w_debug.buf() as b:
                if left is not None:
                    b["img"] = left



if __name__ == "__main__":
    main()
