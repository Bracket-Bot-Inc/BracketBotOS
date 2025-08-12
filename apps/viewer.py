# /// script
# dependencies = [
#   "bbos",
#   "rerun-sdk"
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
from bbos import Reader 
import time
import rerun as rr
import socket
HOSTNAME = socket.gethostname()

def main():
    rr.init("BracketBot Viewer", spawn=False)
    server_uri = rr.serve_grpc(grpc_port=9876, server_memory_limit="500MB")
    rr.serve_web_viewer(web_port=9090, connect_to=server_uri, open_browser=False)
    url = f"http://{HOSTNAME}.local:9090/?url=rerun%2Bhttp://{HOSTNAME}.local:9876/proxy"
    print("Viewer URL: ", url)
    rr.set_time("monotonic", timestamp=time.monotonic())
    with Reader("camera.jpeg") as r_jpeg,  \
         Reader("drive.ctrl") as r_ctrl,   \
         Reader("drive.state") as r_state, \
         Reader("drive.status") as r_status, \
         Reader("audio.mic") as r_mic,  \
         Reader("led_strip.ctrl") as r_led,  \
         Reader("audio.speaker") as r_speak, \
         Reader("camera.points") as r_pts:
        while True:
            if r_                                    colors=r_pts.data['colors'][:r_pts.data['num_points']]))
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
            if r_