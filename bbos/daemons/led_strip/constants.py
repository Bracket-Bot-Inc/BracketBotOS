from bbos.registry import *


import numpy as np


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class led_strip:
    num_leds: int = 15 # Number of LEDs in the strip
    spi_device: str = "/dev/spidev0.0"  # SPI device for LED communication
    spi_speed: int = 800  # SPI speed in kHz (800 kHz for WS2812B)

# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------

@realtime(ms=100)
def led_strip_ctrl():
    """Control message to set LED colors and brightness"""
    return [
        ("rgb", (np.uint8, (led_strip.num_leds, 3))),  # RGB values for all LEDs (0.0-1.0)
    ]
