from bbos import Reader, Writer, Type, Config
import cv2
import numpy as np
from pathlib import Path
import time

cv2.ocl.setUseOpenCL(True)

CALIB_FILE = 'cache/stereo_calibration_fisheye.yaml'

CFG = Config("stereo")
CFG_D = Config("depth")
CFG_P = Config("points")

def quat_rotate(q,v):
    x,y,z,w=q; vx,vy,vz=v
    t2=w*x; t3=w*y; t4=w*z
    t5=-x*x; t6=x*y; t7=x*z
    t8=-y*y; t9=y*z; t10=-z*z
    return np.array([
        2*((t8+t10)*vx+(t6-t4)*vy+(t3+t7)*vz)+vx,
        2*((t4+t6)*vx+(t5+t10)*vy+(t9-t2)*vz)+vy,
        2*((t7-t3)*vx+(t2+t9)*vy+(t5+t8)*vz)+vz
    ],dtype=float).squeeze()

def quat_from_R(R):
    m00,m01,m02,m10,m11,m12,m20,m21,m22 = R.ravel()
    tr = m00+m11+m22
    if tr>0:
        S=np.sqrt(tr+1.0)*2; w=0.25*S
        x=(m21-m12)/S; y=(m02-m20)/S; z=(m10-m01)/S
    elif (m00>m11) and (m00>m22):
        S=np.sqrt(1.0+m00-m11-m22)*2; w=(m21-m12)/S; x=0.25*S
        y=(m01+m10)/S; z=(m02+m20)/S
    elif m11>m22:
        S=np.sqrt(1.0+m11-m00-m22)*2; w=(m02-m20)/S
        x=(m01+m10)/S; y=0.25*S; z=(m12+m21)/S
    else:
        S=np.sqrt(1.0+m22-m00-m11)*2; w=(m10-m01)/S
        x=(m02+m20)/S; y=(m12+m21)/S; z=0.25*S
    q=np.array([x,y,z,w],dtype=float)
    return q/np.linalg.norm(q)

def quat_mul(q1,q2):
    x1,y1,z1,w1=q1; x2,y2,z2,w2=q2
    return np.array([
        w1*x2+x1*w2+y1*z2-z1*y2,
        w1*y2-x1*z2+y1*w2+z1*x2,
        w1*z2+x1*y2-y1*x2+z1*w2,
        w1*w2-x1*x2-y1*y2-z1*z2
    ],dtype=float).squeeze()

def disparity_to_camera_points(disp: cv2.UMat, Q: np.ndarray, left_img: cv2.UMat) -> tuple[np.ndarray, np.ndarray]:
    disp_np = disp.get()
    left_np = left_img.get()

    valid = (disp_np > (CFG_D.min_disp + 0.5))

    if not np.any(valid):
        return np.empty((0, 3)), np.empty((0, 3), dtype=np.uint8)

    # Reproject full grid
    pts_cam_all = cv2.reprojectImageTo3D(disp_np, Q) / 1000.0
    left_rgb = cv2.cvtColor(left_np, cv2.COLOR_BGR2RGB)

    # Mask valid
    pts_cam = pts_cam_all[valid]
    pts_rgb = left_rgb.reshape(-1, 3)[valid.ravel()]

    # 2D grid subsampling
    stride = CFG_P.stride
    if stride > 1:
        h, w = disp_np.shape
        mask = np.zeros_like(valid, dtype=bool)
        mask[::stride, ::stride] = True
        subsample = valid & mask
        pts_cam = cv2.reprojectImageTo3D(disp_np, Q)[subsample] / 1000.0
        pts_rgb = left_rgb.reshape(-1, 3)[subsample.ravel()]

    # Distance filter
    dist_m = np.linalg.norm(pts_cam, axis=1)
    keep = dist_m < CFG_P.max_range
    pts_cam, pts_rgb = pts_cam[keep], pts_rgb[keep]

    return pts_cam, pts_rgb

def load_calib(path: Path, scale: float):
    """Load fisheye rectification matrices and return the scaled camera model."""
    fs = cv2.FileStorage(str(path), cv2.FILE_STORAGE_READ)
    if not fs.isOpened():
        raise FileNotFoundError(path)

    mtx_l = fs.getNode("mtx_l").mat();  dist_l = fs.getNode("dist_l").mat()
    mtx_r = fs.getNode("mtx_r").mat();  dist_r = fs.getNode("dist_r").mat()
    R1 = fs.getNode("R1").mat();        R2 = fs.getNode("R2").mat()
    P1 = fs.getNode("P1").mat();        P2 = fs.getNode("P2").mat()
    Q  = fs.getNode("Q").mat().astype(np.float32)
    fs.release()

    # Scale translation component to match *scale*
    Q[:4, 3] *= scale
    return mtx_l, dist_l, mtx_r, dist_r, R1, R2, P1, P2, Q

def main():
    (
        mtx_l,
        dist_l,
        mtx_r,
        dist_r,
        R1,
        R2,
        P1_cam,
        P2_cam,
        Q,
    ) = load_calib(CALIB_FILE, CFG_D.downsample)

    # Calculate correct dimensions based on downsampled stereo frame
    # The stereo frame contains both cameras side by side, so width needs to be halved
    img_w = CFG.width // 2

    # Pre-compute rectification maps outside the loop
    map1x, map1y = cv2.fisheye.initUndistortRectifyMap(
        mtx_l, dist_l, R1, P1_cam, (img_w, CFG.height), cv2.CV_32FC1
    )
    map2x, map2y = cv2.fisheye.initUndistortRectifyMap(
        mtx_r, dist_r, R2, P2_cam, (img_w, CFG.height), cv2.CV_32FC1
    )
    
    # Convert maps to UMat for OpenCL acceleration
    map1x_gpu = cv2.UMat(map1x)
    map1y_gpu = cv2.UMat(map1y)
    map2x_gpu = cv2.UMat(map2x)
    map2y_gpu = cv2.UMat(map2y)
    
    # Initialize stereo matcher outside the loop
    stereo_bm = cv2.StereoSGBM_create(numDisparities=CFG_D.num_disp, blockSize=CFG_D.window_size)
    stereo_bm.setMinDisparity(CFG_D.min_disp)
    stereo_bm.setUniquenessRatio(CFG_D.uniqueness)
    stereo_bm.setSpeckleWindowSize(CFG_D.speckle_window)
    stereo_bm.setSpeckleRange(CFG_D.speckle_range)
    stereo_bm.setPreFilterCap(CFG_D.pre_filter_cap)
    
    # Pre-calculate stereo parameters
    baseline_m = abs(P2_cam[0, 3] / P2_cam[0, 0]) / 1000.0
    fx_ds = P1_cam[0, 0] * CFG_D.downsample

    with Reader('camera.jpeg') as r_jpeg, \
            Writer('camera.depth', Type("camera_depth")) as w_depth, \
            Writer('camera.vo', Type("camera_vo")) as w_vo, \
            Writer('camera.points', Type("camera_points")) as w_points:
        
        print(f"OpenCL available: {cv2.ocl.haveOpenCL()}", flush=True)
        if cv2.ocl.haveOpenCL():
            print(f"OpenCL device: {cv2.ocl.Device.getDefault().name()}", flush=True)
        print('starting depth', flush=True)

        depth_mm = None
        pts_cam = None
        pts_rgb = None
        prev_l_gray = None
        t0 = time.time()
        q = np.array([0,0,0,1], dtype=np.float32)
        qi = np.array([0,0,0,1], dtype=np.float32)
        t = np.zeros(3, dtype=np.float32)
        ti = np.zeros(3, dtype=np.float32)
        timestamp = None
        while True:
            if r_jpeg.ready():
                # Decode and split stereo image
                stereo = cv2.imdecode(r_jpeg.data["jpeg"], cv2.IMREAD_COLOR)
                timestamp = r_jpeg.data['timestamp']

                left  = cv2.UMat(stereo[:, img_w:])
                right = cv2.UMat(stereo[:, :img_w])
                # Rectify using pre-computed maps (OpenCL accelerated)
                left_r  = cv2.remap(left,  map1x_gpu, map1y_gpu, cv2.INTER_LINEAR)
                right_r = cv2.remap(right, map2x_gpu, map2y_gpu, cv2.INTER_LINEAR)
                
                # Resize (OpenCL accelerated)
                left_ds  = cv2.resize(left_r,  (CFG_D.width_D, CFG_D.height_D), interpolation=cv2.INTER_AREA)
                right_ds = cv2.resize(right_r, (CFG_D.width_D, CFG_D.height_D), interpolation=cv2.INTER_AREA)
                
                # Convert to grayscale (OpenCL accelerated)
                l_gray = cv2.cvtColor(left_ds,  cv2.COLOR_BGR2GRAY)
                r_gray = cv2.cvtColor(right_ds, cv2.COLOR_BGR2GRAY)

                if False and prev_l_gray is not None:
                    # run VO: track features between prev_l_gray and l_gray
                    # for example:
                    pts0 = cv2.goodFeaturesToTrack(prev_l_gray, maxCorners=800, qualityLevel=0.01, minDistance=8)
                    pts1, st, err = cv2.calcOpticalFlowPyrLK(prev_l_gray, l_gray, pts0, None)
                    ptsback, stb, err = cv2.calcOpticalFlowPyrLK(l_gray, prev_l_gray, pts1, None)
                    p0 = pts0.get() if isinstance(pts0, cv2.UMat) else pts0
                    p1 = pts1.get() if isinstance(pts1, cv2.UMat) else pts1
                    pb = ptsback.get() if isinstance(ptsback, cv2.UMat) else ptsback
                    st = (st.get() if isinstance(st, cv2.UMat) else st).ravel().astype(bool)
                    stb = (stb.get() if isinstance(stb, cv2.UMat) else stb).ravel().astype(bool)
                    fb_err = np.linalg.norm(pb.reshape(-1,2) - p0.reshape(-1,2), axis=1)
                    good = st & stb & np.isfinite(fb_err) & (fb_err < CFG_D.fb_thr)
                    p0 = p0.reshape(-1,2)[good]
                    p1 = p1.reshape(-1,2)[good]
                    E, inl = cv2.findEssentialMat(p0, p1, P1_cam[:3, :3], method=cv2.RANSAC, prob=0.999, threshold=0.3)
                    inl = inl.ravel().astype(bool) if inl is not None else np.zeros(len(p0), bool)
                    _, Ri, ti, _ = cv2.recoverPose(E, p0[inl], p1[inl], P2_cam[:3, :3])
                    print(ti, flush=True)
                    print(Ri, flush=True)
                    ti = ti.squeeze()
                    qi = quat_from_R(Ri)
                    t = quat_rotate(qi, ti) + t
                    q = quat_mul(q, qi)
                # After processing, update previous frame
                prev_l_gray = l_gray
                prev_r_gray = r_gray
                
                # Compute disparity (OpenCL accelerated)
                disp = stereo_bm.compute(l_gray, r_gray)
                
                # Convert disparity to float and scale (keep as UMat)
                disp_float = cv2.multiply(disp, 1.0/16.0, dtype=cv2.CV_32F)
                
                # Convert to numpy only for depth calculation and point cloud generation
                disp_np = disp_float.get()
                valid = disp_np > (CFG_D.min_disp + 0.5)
                denom = disp_np - CFG_D.min_disp
                depth_m = np.zeros_like(disp_np)
                mask = (denom > 0.1) & valid
                
                # Ensure type checker knows these are initialised
                assert fx_ds is not None and baseline_m is not None, "Stereo parameters not initialised"
                depth_m[mask] = fx_ds * baseline_m / denom[mask]

                # Encode depth to 16-bit PNG (millimetres – preserves precision)
                depth_mm = np.clip(depth_m * 1000.0, 0, 65535).astype(np.uint16)
                pts_cam, pts_rgb = disparity_to_camera_points(disp_float, Q, left_ds)
            with w_points.buf() as b:
                if pts_cam is not None and pts_rgb is not None and timestamp is not None:
                    b['num_points'] = len(pts_cam)
                    b['points'][:len(pts_cam)] = CFG_D.T_base_cam(pts_cam)
                    b['colors'][:len(pts_rgb)] = pts_rgb
                    b['timestamp'] = timestamp
            with w_vo.buf() as b:
                if qi is not None and ti is not None and timestamp is not None:
                    b['q'] = qi
                    b['t'] = ti
                    b['q_acc'] = q
                    b['t_acc'] = t
                    b['timestamp'] = timestamp
            with w_depth.buf() as b:
                if depth_mm is not None:
                    b['depth'] = depth_mm
                    b['timestamp'] = timestamp


if __name__ == "__main__":
    main()