# /// script
# dependencies = [
#   "ultralytics",
#   "bbos @ /home/bracketbot/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
#   "turbojpeg-rpi",
#   "openvino",
# ]
# ///
from bbos import Config, Reader, Writer, Type
import os, time
from pathlib import Path
from ultralytics import YOLO
import numpy as np
import cv2

os.environ['ULTRALYTICS_HIDE_CONSOLE'] = '1'
os.environ['YOLO_VERBOSE'] = 'True'
os.environ['ULTRALYTICS_QUIET'] = 'True'
os.environ['DISABLE_ULTRALYTICS_VERSIONING_CHECK'] = 'True'


TURN_SPEED = 0.3
CENTER_THRESHOLD = 0.05
FORWARD_SPEED = 2.0 # Speed for moving forward/backward
TARGET_WIDTH_RATIO = 0.3  # Target width of person relative to image width
WIDTH_THRESHOLD = 0.05  # Acceptable range around target width
MODEL_PATH = "yolov8n.pt"
OPENVINO_MODEL_PATH = "yolov8n_openvino_model"  # Not used anymore

# Speed control parameters
MAX_FORWARD_SPEED = 10  # Maximum speed when person is far
MIN_FORWARD_SPEED = 0.3  # Minimum speed when person is close
SPEED_SCALE_FACTOR = 3.0  # How aggressively speed changes with distance

def main():
    # Load the PyTorch model directly
    print("Loading YOLO model...")
    if not os.path.exists(OPENVINO_MODEL_PATH):
        model = YOLO(MODEL_PATH)
        model.export(format="openvino", dynamic=True)
    
    # Initialize OpenVINO runtime

    model = YOLO(OPENVINO_MODEL_PATH)
    cmd = np.zeros(2)
    CFG = Config("stereo")
    img_width = CFG.width // 2
    with Reader("camera.jpeg") as r_jpeg, \
        Writer("drive.ctrl", Type("drive_ctrl")) as w_ctrl:

        while True:
            loop_start = time.time()
            # print("huh")
            results = []
            if r_jpeg.ready():
                # Decode JPEG and get left image (first half of stereo)
                stereo_img = cv2.imdecode(r_jpeg.data['jpeg'], cv2.IMREAD_COLOR)
                # Convert BGR to RGB and get left half
                img = cv2.cvtColor(stereo_img[:, :img_width, :], cv2.COLOR_BGR2RGB)
                results = model(img, classes=[0],verbose=False)
                
                # Save annotated image with detections
                if len(results) > 0:
                    annotated_img = results[0].plot()
                    cv2.imwrite('debug.jpg', cv2.cvtColor(annotated_img, cv2.COLOR_RGB2BGR))
            # Find the largest person detection
            best_person = None
            max_area = 0

            if len(results) == 0 or len(results[0].boxes) == 0:
                loop_end = time.time()
                print(f"Loop time: {(loop_end - loop_start)*1000:.1f}ms")
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
            
            # Debug prints
            print(f"Person width: {person_width:.1f}, Image width: {img_width}, Width ratio: {width_ratio:.3f}")
            print(f"Width error: {width_error:.3f} (negative=far, positive=close)")
            
            # Determine forward/backward speed based on width
            forward_speed = 0
            if abs(width_error) > WIDTH_THRESHOLD:
                # Calculate proportional speed based on distance
                # Negative width_error means person is too far (small bbox), should go forward faster
                # Positive width_error means person is too close (large bbox), should go backward slower
                
                if width_error < 0:  # Person is too far, go forward
                    # The farther they are, the faster we go (up to MAX_FORWARD_SPEED)
                    speed_multiplier = min(abs(width_error) * SPEED_SCALE_FACTOR, 1.0)
                    forward_speed = MIN_FORWARD_SPEED + (MAX_FORWARD_SPEED - MIN_FORWARD_SPEED) * speed_multiplier
                    print(f"Going FORWARD: speed = {forward_speed:.2f}")
                else:  # Person is too close, go backward
                    # When going backward (person too close), use a more conservative speed
                    speed_multiplier = min(width_error * SPEED_SCALE_FACTOR, 1.0)
                    forward_speed = -MIN_FORWARD_SPEED - (MAX_FORWARD_SPEED - MIN_FORWARD_SPEED) * speed_multiplier * 0.5
                    print(f"Going BACKWARD: speed = {forward_speed:.2f}")
            else:
                print(f"Within threshold, no forward/backward movement")
            
            if abs(x_error) < CENTER_THRESHOLD:
                cmd[:] = [0, -forward_speed]  # Note: negative sign to match robot's convention
            elif x_error > 0:
                cmd[:] = [TURN_SPEED*abs(x_error), -forward_speed]  # Note: negative sign
            else:
                cmd[:] = [-TURN_SPEED*abs(x_error), -forward_speed]  # Note: negative sign
            with w_ctrl.buf() as b:
                b['twist'] = cmd
            print(x_error, width_error)
            loop_end = time.time()
            print(f"Loop time: {(loop_end - loop_start)*1000:.1f}ms")

if __name__ == "__main__":
    main()
