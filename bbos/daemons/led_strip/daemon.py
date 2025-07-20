from bbos import Reader, Writer, Config, Type, Time
from bbos.os_utils import Priority, config_realtime_process

import numpy as np
import signal, sys, traceback
import time
from pi5neo import Pi5Neo


if __name__ == "__main__":
    CFG = Config("led_strip")
    config_realtime_process(1, Priority.CTRL_HIGH)
    neo = Pi5Neo(CFG.spi_device, CFG.num_leds, CFG.spi_speed)
    t = Time(CFG.rate_state)
    with Reader('/led_strip.ctrl') as r_ctrl:
        print(f"[LED] Daemon started - {CFG.num_leds} LEDs")
        while True:
            neo.fill_strip(0, 0, 0)
            if r_ctrl.ready():
                stale, d = r_ctrl.get()
                if not stale: 
                    equal = np.ptp(d['rgb'], axis=0) == 0
                    if equal.all(): 
                        neo.fill_strip(*d['rgb'][0])
                    else:
                        for i in range(CFG.num_leds):
                            neo.set_led_color(i, *list(d['rgb'][i]))
            neo.update_strip()
            t.tick()
    neo.clear_strip()
    neo.update_strip()
    print(t.stats())