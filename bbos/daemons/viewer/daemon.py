from bbos import Reader 
from bbos.os_utils import user_ip

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
         Reader("/drive.status") as r_status:
        while True:
            if r_jpeg.ready():
                rr.set_time("monotonic", timestamp=r_jpeg.data['timestamp'])
                rr.log("/camera", rr.EncodedImage(contents=r_jpeg.data['jpeg'],media_type="image/jpeg"))
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
                        rr.log(f"/drive/status/{field}", rr.Scalars(r_status.data[field]),)
            time.sleep(0.1)

if __name__ == "__main__":
    main()