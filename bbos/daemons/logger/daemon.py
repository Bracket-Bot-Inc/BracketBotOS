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
    with Reader("/camera.points") as r_points:
        while True:
            if r_points.ready():
                stale, d = r_points.get()
                rr.log(
                    "points",
                    rr.Points3D(positions=d['points'],
                                colors=d['colors'],
                                radii=0.02))
            t.tick()
    print(t.stats)
