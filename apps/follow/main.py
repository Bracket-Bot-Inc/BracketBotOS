# NOAUTO
# /// script
# dependencies = [
#   "ultralytics",
#   "bbos @ /home/GREEN/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
#   "turbojpeg-rpi",
#   "ncnn",
# ]
# ///
from bbos import Config, Reader, Writer, Type, Time
import os
from pathlib import Path
from ultralytics import YOLO
import numpy as np
from turbojpeg import decompress, PF

os.environ['ULTRALYTICS_HIDE_CONSOLE'] = '1'
os.environ['YOLO_VERBOSE'] = 'False'
os.environ['ULTRALYTICS_QUIET'] = 'True'
os.environ['DISABLE_ULTRALYTICS_VERSIONING_CHECK'] = 'True'


TURN_SPEED = 2
CENTER_THRESHOLD = 0.05
FORWARD_SPEED = 21.0 # Speed for moving forward/backward
TARGET_WIDTH_RATIO = 0.2  # Target width of person relative to image width
WIDTH_THRESHOLD = 0.02  # Acceptable range around target width
MODEL_PATH =  "yolov8n.pt"
NCNN_MODEL_PATH = "yolov8n_ncnn_model"

def main():
    if not os.path.exists(NCNN_MODEL_PATH):
        model = YOLO(MODEL_PATH)
        model.export(format="ncnn")
    
    model = YOLO(NCNN_MODEL_PATH)
    cmd = np.zeros(2)
    CFG = Config("stereo")
    img_width = CFG.width // 2
    t = Time(15)
    with Reader("/camera.jpeg") as r_jpeg, \
        Writer("/drive.ctrl", Type("drive_ctrl")) as w_ctrl:
        while True:
            results = []
            if r_jpeg.ready():
                stale, d = r_jpeg.get()
                if stale: continue
                img = np.array(decompress(d['jpeg'], PF.RGB))[:,:img_width,:]
                results = model(img, classes=[0],verbose=False)

            # Find the largest person detection
            best_person = None
            max_area = 0

            if len(results) == 0 or len(results[0].boxes) == 0:
                continue

            for result in results[0].boxes:
                box = result.xyxy[0].cpu().numpy()
                area = (box[2] - box[0]) * (box[3] - box[1])
                if area > max_area:
                    max_area = area
                    best_person = box

            cmd = np.zeros(2)
            # Get center point and width of the person
            center_x = (best_person[0] + best_person[2]) / 2
            image_center_x = img.shape[1] / 2
            x_error = (center_x - image_center_x) / image_center_x  # -1 to 1
            
            # Calculate width ratio of person relative to image
            person_width = best_person[2] - best_person[0]
            width_ratio = person_width / img_width
            width_error = width_ratio - TARGET_WIDTH_RATIO
            
            # Determine forward/backward speed based on width
            forward_speed = 0
            if abs(width_error) > WIDTH_THRESHOLD:
                forward_speed = FORWARD_SPEED * (width_error / abs(width_error))
            
            if abs(x_error) < CENTER_THRESHOLD:
                cmd[:] = [0, forward_speed]
            elif x_error > 0:
                cmd[:] = [TURN_SPEED*abs(x_error), forward_speed]
            else:
                cmd[:] = [-TURN_SPEED*abs(x_error), forward_speed]
            with w_ctrl.buf() as b:
                b['twist'] = cmd
            t.tick()

if __name__ == "__main__":
    main()
