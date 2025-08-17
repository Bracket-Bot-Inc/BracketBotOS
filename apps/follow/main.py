# /// script
# dependencies = [
#   "opencv-python",
#   "bbos",
#   "bracketbot-ai",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# bracketbot-ai = { path = "/home/bracketbot/BracketBotAI", editable = true }
# ///
from bbos import Config, Reader, Writer, Type
import numpy as np
import cv2
from bracketbot_ai import Detector

# Detection processing parameters
CENTER_THRESHOLD = 0.05
TARGET_WIDTH_RATIO = 0.3  # Target width of person relative to image width
WIDTH_THRESHOLD = 0.05  # Acceptable range around target width

# Speed control parameters
TURN_SPEED = 3
MAX_FORWARD_SPEED = 3.5 # Maximum speed when person is far
MIN_FORWARD_SPEED = 0.05  # Minimum speed when person is close
SPEED_SCALE_FACTOR = 1  # How aggressively speed changes with distance

def main():
    model = Detector("yolo11s")
    CFG = Config("stereo")
    img_width = CFG.width // 2
    with Reader("camera.jpeg") as r_jpeg, \
        Writer("drive.ctrl", Type("drive_ctrl")) as w_ctrl:
        while True:
            results = []
            if r_jpeg.ready():
                # Decode JPEG and get left image (first half of stereo)
                stereo_img = cv2.imdecode(r_jpeg.data['jpeg'], cv2.IMREAD_COLOR)
                # Convert BGR to RGB and get left half
                results = model(stereo_img[:, :img_width, :], classes=[0], conf=0.35, iou=0.45)
                # Save annotated image with detections
                if len(results) > 0:
                    cv2.imwrite('debug.jpg', results.plot())
            # Find the largest person detection
            cmd = np.zeros(2)
            if len(results) > 0:
                boxes = results.xyxy
                areas = (boxes[:,2] - boxes[:,0]) * (boxes[:,3] - boxes[:,1])
                biggest = boxes[np.argmax(areas)]
                # Get center point and width of the person
                center_x = (biggest[0] + biggest[2]) / 2
                image_center_x = img_width / 2
                x_error = (center_x - image_center_x) / image_center_x  # -1 to 1
                
                # Calculate width ratio of person relative to image
                person_width = biggest[2] - biggest[0]
                width_ratio = person_width / img_width
                width_error = width_ratio - TARGET_WIDTH_RATIO

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
                    else:  # Person is too close, go backward
                        # When going backward (person too close), use a more conservative speed
                        speed_multiplier = min(width_error * SPEED_SCALE_FACTOR, 1.0)
                        forward_speed = -MIN_FORWARD_SPEED - (MAX_FORWARD_SPEED - MIN_FORWARD_SPEED) * speed_multiplier * 0.5
                if abs(x_error) < CENTER_THRESHOLD:
                    cmd[:] = [forward_speed, 0]  # Note: negative sign to match robot's convention
                elif x_error > 0:
                    cmd[:] = [forward_speed, TURN_SPEED*abs(x_error)]  # Note: negative sign
                else:
                    cmd[:] = [forward_speed, -TURN_SPEED*abs(x_error)]  # Note: negative sign
            with w_ctrl.buf() as b:
                b['twist'] = cmd

if __name__ == "__main__":
    main()