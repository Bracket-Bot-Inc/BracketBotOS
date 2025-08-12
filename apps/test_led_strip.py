# /// script
# dependencies = [
#   "bbos",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
from bbos import Writer, Type, Config
import time
import numpy as np

PRIMARY_COLORS = [
    (255, 0, 0),    # Red
    (0, 255, 0),    # Green
    (0, 0, 255),    # Blue
]

if __name__ == "__main__":
    CFG = Config("led_strip")
    with Writer("led_strip.ctrl", Type("led_strip_ctrl")) as w_ctrl:
        while True:
            for color in PRIMARY_COLORS:
                print(color, flush=True)
                w_ctrl["rgb"] = np.array([color] * CFG.num_leds, dtype=np.uint8)
                time.sleep(2)
