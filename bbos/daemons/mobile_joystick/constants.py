from bbos.registry import register
import numpy as np


@register
class mobile_joystick:
    rate = 50


@register
def joystick():
    return [
        ("state", np.float32, 2),  # x,y
    ]
