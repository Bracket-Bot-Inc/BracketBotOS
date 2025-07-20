from bbos import Reader, Time
from bbos.os_utils import user_ip

import time
import rerun as rr
import os

def main():
    RERUN_HOST = user_ip()
    rr.init("vis", spawn=False)
    viewer_url = f"http://{user_ip()}:9090/?url=rerun%2Bhttp://{user_ip()}:9876/proxy"
    print(f"[logger] Viewer URL: {viewer_url}")
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

if __name__ == "__main__":
    pass