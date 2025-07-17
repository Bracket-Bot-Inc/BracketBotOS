from bbos import Reader, Time
from bbos.os_utils import who_ip

import time
import rerun as rr
import os

RERUN_HOST = who_ip()

if __name__ == "__main__":
    rr.init("vis", spawn=False)
    viewer_url = f"http://192.168.10.1:9090/?url=rerun%2Bhttp://192.168.10.1:9876/proxy"
    rr.serve_web(web_port=9090, server_memory_limit='500MB')
    rr.set_time("monotonic", timestamp=time.monotonic())
    t = Time(10)
    with Reader("/camera.depth") as r_depth:
        while True:
            if r_depth.ready():
                stale, d = r_depth.get()
                if stale: continue
                rr.log("depth_image", rr.Image(d['depth']))
            t.tick()
    print(t.stats)
