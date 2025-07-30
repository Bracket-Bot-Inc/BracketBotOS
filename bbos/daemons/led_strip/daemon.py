from bbos import Reader, Config

import numpy as np
from pi5neo import Pi5Neo


if __name__ == "__main__":
    CFG = Config("led_strip")
    neo = Pi5Neo(CFG.spi_device, CFG.num_leds, CFG.spi_speed)
    with Reader('/led_strip.ctrl') as r_ctrl:
        print(f"[LED] Daemon started - {CFG.num_leds} LEDs")
        while True:
            neo.fill_strip(0, 0, 0)
            if r_ctrl.ready():
                equal = np.ptp(r_ctrl.data['rgb'], axis=0) == 0
                if equal.all(): 
                    neo.fill_strip(*r_ctrl.data['rgb'][0])
                else:
                    for i in range(CFG.num_leds):
                        neo.set_led_color(i, *list(r_ctrl.data['rgb'][i]))
            neo.update_strip()
    neo.clear_strip()
    neo.update_strip()