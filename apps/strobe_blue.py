# /// script
# dependencies = [
#   "bbos",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
from bbos import Writer, Type, Config
import numpy as np
import time
import math

# Just blue color
BLUE = (0,0,255)

# Breathing parameters
BREATH_DURATION = 4.0  # Duration of one complete breath cycle in seconds

def apply_brightness(color, brightness):
    """Apply brightness scaling to RGB color tuple."""
    # Preserve zero channels to maintain pure colors
    return tuple(int(min(255, c * brightness)) for c in color)

def calculate_breathing_brightness(elapsed_time, duration):
    """Calculate brightness using cosine wave for smooth breathing effect."""
    phase = (elapsed_time / duration) * 2 * math.pi
    brightness = (1 - math.cos(phase)) / 2
    # Add minimum brightness to prevent complete darkness while preserving color
    return max(0.1, brightness)

if __name__ == "__main__":
    CFG = Config("led_strip")
    with Writer("led_strip.ctrl", Type("led_strip_ctrl")) as w_ctrl:
        start_time = time.time()
        
        print("Starting blue breathing effect...")
        print(f"Blue color RGB: {BLUE}")
        
        while True:
            # Calculate elapsed time
            elapsed_time = (time.time() - start_time) % BREATH_DURATION
            # Calculate breathing brightness (0.05 to 1.0)
            brightness = calculate_breathing_brightness(elapsed_time, BREATH_DURATION)
            scaled_color = apply_brightness(BLUE, brightness)
            w_ctrl["rgb"] = np.array([scaled_color] * CFG.num_leds, dtype=np.uint8)