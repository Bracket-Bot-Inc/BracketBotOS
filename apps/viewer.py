# AUTO
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
         Reader("camera.points") as r_pts, \
         Reader("audio.mic") as r_mic:
        while True:
            if r_jpeg.ready():
                rr.set_time("monotonic", timestamp=r_jpeg.data['timestamp'])
                rr.log("/camera", rr.EncodedImage(contents=r_jpeg.data['jpeg'],media_type="image/jpeg"))
            if r_pts.ready():
                rr.set_time("monotonic", timestamp=r_pts.data['timestamp'])
                rr.log("/points", rr.Points3D(r_pts.data['points'][:r_pts.data['num_points']], 
                                              colors=r_pts.data['colors'][:r_pts.data['num_points']]))
            if r_mic.ready():
                rr.set_time("monotonic", timestamp=r_mic.data['timestamp'])
                rr.log("/audio/mic", rr.Scalars(r_mic.data['audio'].mean()))
if __name__ == "__main__":
    main()