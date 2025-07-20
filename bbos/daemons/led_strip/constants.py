from bbos.registry import register

import numpy as np


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class led_strip:
    rate_state: int = 20  # Hz - LED state update rate
    num_leds: int = 30  # Number of LEDs in the strip
    spi_device: str = "/dev/spidev0.0"  # SPI device for LED communication
    spi_speed: int = 800  # SPI speed in kHz (800 kHz for WS2812B)

# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------

@register
def led_strip_ctrl():
    """Control message to set LED colors and brightness"""
    return [
        ("rgb", (np.uint8, (30, 3))),  # RGB values for all LEDs (0.0-1.0)
    ]