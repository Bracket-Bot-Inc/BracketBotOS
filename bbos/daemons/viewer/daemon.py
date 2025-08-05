from bbos import Reader 
from bbos.os_utils import user_ip
from bbos.time import Loop

import time
import rerun as rr
import os

def main():
    rr.init("BracketBot Viewer", spawn=False)
    server_uri = rr.serve_grpc(grpc_port=9876, server_memory_limit="500MB")
    rr.serve_web_viewer(web_port=9090, connect_to=server_uri, open_browser=False)
    rr.set_time("monotonic", timestamp=time.monotonic())
    with Reader("/camera.jpeg") as r_jpeg,  \
         Reader("/drive.ctrl") as r_ctrl,   \
         Reader("/drive.state") as r_state, \
         Reader("/drive.status") as r_status, \
         Reader("/audio.mic") as r_mic,  \
         Reader("/led_strip.ctrl") as r_led,  \
         Reader("/audio.speaker") as r_speak, \
         Reader("/camera.depth") as r_depth:
        while True:
            if r_jpeg.ready():
                rr.set_time("monotonic", timestamp=r_jpeg.data['timestamp'])
                rr.log("/camera", rr.EncodedImage(contents=r_jpeg.data['jpeg'],media_type="image/jpeg"))
            if r_depth.ready():
                rr.set_time("monotonic", timestamp=r_depth.data['timestamp'])
                rr.log("/depth", rr.DepthImage(r_depth.data['depth']))
            if r_ctrl.ready():
                for field in r_ctrl.data.dtype.names:
                    if field != 'timestamp':
                        rr.set_time("monotonic", timestamp=r_ctrl.data['timestamp'])
                        rr.log(f"/drive/ctrl/{field}", rr.Scalars(r_ctrl.data[field]))
            if r_state.ready():
                for field in r_state.data.dtype.names:
                    if field != 'timestamp':
                        rr.set_time("monotonic", timestamp=r_state.data['timestamp'])
                        rr.log(f"/drive/state/{field}", rr.Scalars(r_state.data[field]))
            if r_status.ready():
                for field in r_status.data.dtype.names:
                    if field != 'timestamp':
                        rr.set_time("monotonic", timestamp=r_status.data['timestamp'])
                        rr.log(f"/drive/status/{field}", rr.Scalars(r_status.data[field]))
            if r_mic.ready():
                rr.set_time("monotonic", timestamp=r_mic.data['timestamp'])
                rr.log("/audio/mic", rr.Scalars(r_mic.data['audio'].mean()))
            if r_speak.ready():
                rr.set_time("monotonic", timestamp=r_speak.data['timestamp'])
                rr.log("/audio/speaker", rr.Scalars(r_speak.data['audio'].mean()))
            if r_led.ready():
                rr.set_time("monotonic", timestamp=r_led.data['timestamp'])
                rr.log("/led_strip", rr.Scalars(r_led.data['rgb']))

if __name__ == "__main__":
    main()