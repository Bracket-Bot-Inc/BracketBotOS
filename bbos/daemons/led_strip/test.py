from bbos import Writer, Type, Config
import time
import numpy as np
RAINBOW = [
    (255, 0, 0),  # Red
    (255, 127, 0),  # Orange
    (255, 255, 0),  # Yellow
    (0, 255, 0),  # Green
    (0, 0, 255),  # Blue
    (75, 0, 130),  # Indigo
    (148, 0, 211)  # Violet
]

if __name__ == "__main__":
    CFG = Config("led_strip")
    with Writer("led_strip.ctrl", Type("led_strip_ctrl")) as w_ctrl:
        while True:
            for color in RAINBOW:
                w_ctrl["rgb"] = np.array([color] * CFG.num_leds, dtype=np.uint8)