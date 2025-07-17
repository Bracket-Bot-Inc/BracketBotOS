from bbos import Reader, Writer, Type, Config, Time
from bbos.os_utils import config_realtime_process, Priority
import sys
import mrcal
import cv2
import numpy as np
import numpysane as nps

CFG = Config("stereo")

if __name__ == "__main__":
    config_realtime_process(1, Priority.CTRL_HIGH)
    models = [ mrcal.cameramodel(f) \
               for f in ('cache/camera-0_opencv.cameramodel',
                         'cache/camera-1_opencv.cameramodel') ]
    models_rectified = \
        mrcal.rectified_system(models,
                               az_fov_deg = CFG.xfov,
                               el_fov_deg = CFG.yfov)
    rec_w, rec_h = models_rectified[0].imagersize()
    rectification_maps = mrcal.rectification_maps(models, models_rectified)
    with Reader('/camera.jpeg') as r_jpeg, \
            Writer('/camera.points', lambda: Type("camera_points")(rec_h, rec_w)) as w_points:

        t = Time(20)

        print('starting depth')
        while True:
            if r_jpeg.ready():
                stale, d = r_jpeg.get()
                if stale: continue
                stereo = cv2.imdecode(d["jpeg"], cv2.IMREAD_COLOR)


                if stereo is None: continue
                images_rectified = [
                    mrcal.transform_image(
                        stereo[:, i * CFG.width // 2:(i + 1) * CFG.width // 2],
                        rectification_maps[i]) for i in range(2)
                ]
                # Find stereo correspondences using OpenCV
                block_size = 5
                max_disp = 160  # in pixels
                matcher = \
                    cv2.StereoSGBM_create(
                        minDisparity=0,
                        numDisparities=16*3,  # Reduce search range for speed
                        blockSize=3,          # Smaller block for less computation
                        P1=8*3*3**2,
                        P2=32*3*3**2,
                        disp12MaxDiff=2,
                        uniquenessRatio=5,
                        speckleWindowSize=50,
                        speckleRange=16,
                        preFilterCap=31,
                        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY  # Retain 3-way optimization for speed
                    )
                disp16 = matcher.compute(
                    *images_rectified)  # in pixels*16
                disp16 = disp16.astype(np.float32) / 16.0
                disp16[disp16 <= 0] = np.nan
                valid = np.isfinite(disp16)
                disp_norm = np.zeros_like(disp16, dtype=np.uint8)
                disp_norm[valid] = np.clip(
                    255 * (disp16[valid] - np.nanmin(disp16)) / (np.nanmax(disp16) - np.nanmin(disp16)),
                    0, 255
                ).astype(np.uint8)

                # Color map
                color_disp = cv2.applyColorMap(disp_norm, cv2.COLORMAP_JET)
                color_disp = cv2.cvtColor(color_disp, cv2.COLOR_BGR2RGB)
                # Point cloud in rectified camera-0 coordinates
                # shape (H,W,3)

                with w_depth.buf() as b:

                with w_points.buf() as b:
                    b['points'][:] = mrcal.stereo_unproject(disparity16,
                                                            models_rectified,
                                                            disparity_scale=16)
                    Rt_cam0_rect0 = mrcal.compose_Rt(
                        models[0].extrinsics_Rt_fromref(),
                        models_rectified[0].extrinsics_Rt_toref())
                    b['points'][:] = mrcal.transform_point_Rt(
                        Rt_cam0_rect0, b['points'][:])
                    b['colors'][:] = images_rectified[0]
                    b['timestamp'] = d['timestamp']
            t.tick()
    print(t.stats)
