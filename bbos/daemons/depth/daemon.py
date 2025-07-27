from bbos import Reader, Writer, Type, Config, Loop
import sys
import mrcal
import cv2
import numpy as np
import numpysane as nps

CFG = Config("stereo")
CFG_D = Config("depth")


def main():
    models = [ mrcal.cameramodel(f) \
               for f in ('cache/camera-0.cameramodel',
                         'cache/camera-1.cameramodel') ]
    models_rectified = \
        mrcal.rectified_system(models,
                               az_fov_deg = CFG.xfov,
                               el_fov_deg = CFG.yfov)
    rec_w, rec_h = models_rectified[0].imagersize()
    rectification_maps = mrcal.rectification_maps(models, models_rectified)
    with Reader('/camera.jpeg') as r_jpeg, \
            Writer('/camera.depth', lambda: Type("camera_depth")(rec_h, rec_w)) as w_depth, \
            Writer('/camera.points', lambda: Type("camera_points")(rec_h, rec_w)) as w_points:

        print('starting depth')
        while True:
            if r_jpeg.ready():
                stereo = cv2.imdecode(r_jpeg.data["jpeg"], cv2.IMREAD_COLOR)

                if stereo is None: continue
                images_rectified = [
                    mrcal.transform_image(
                        stereo[:, i * CFG.width // 2:(i + 1) * CFG.width // 2],
                        rectification_maps[i]) for i in range(2)
                ]
                # Find stereo correspondences using OpenCV
                matcher = \
                    cv2.StereoSGBM_create(
                        minDisparity=CFG_D.min_disp,
                        numDisparities=CFG_D.num_disp,  # Reduce search range for speed
                        blockSize=CFG_D.block_size,          # Smaller block for less computation
                        P1=8 * 3 * CFG_D.block_size ** 2,
                        P2=32 * 3 * CFG_D.block_size ** 2,
                        disp12MaxDiff=2,
                        uniquenessRatio=CFG_D.uniquenessRatio,
                        speckleWindowSize=CFG_D.speckle_w_size,
                        speckleRange=CFG_D.specle_range,
                        preFilterCap=CFG_D.prefilter_cap,
                        mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY  # Retain 3-way optimization for speed
                    )
                disp = matcher.compute(*images_rectified).astype(
                    np.float32) / 16.0  # in pixels*16
                valid = disp > (CFG_D.min_disp + 0.5)
                denom = disp - CFG_D.min_disp
                depth_m = np.zeros_like(disp)
                mask = (denom > 0.1) & valid
                # Ensure type checker knows these are initialised
                assert fx_ds is not None and baseline_m is not None, "Stereo parameters not initialised"
                depth_m[mask] = fx_ds * baseline_m / denom[mask]

                # Encode depth to 16-bit PNG (millimetres – preserves precision)
                depth_mm = np.clip(depth_m * 1000.0, 0,
                                   65535).astype(np.uint16)

                with w_depth.buf() as b:
                    b['depth'] = depth_mm.reshape((rec_h, rec_w))

                with w_points.buf() as b:
                    b['points'] = mrcal.stereo_unproject(disp16,
                                                            models_rectified,
                                                            disparity_scale=16)
                    Rt_cam0_rect0 = mrcal.compose_Rt(
                        models[0].extrinsics_Rt_fromref(),
                        models_rectified[0].extrinsics_Rt_toref())
                    b['points'] = mrcal.transform_point_Rt(
                        Rt_cam0_rect0, b['points'][:])
                    b['colors'] = images_rectified[0]
                    b['timestamp'] = r_jpeg.data['timestamp']
            Loop.sleep()


if __name__ == "__main__":
    pass
    #main()
