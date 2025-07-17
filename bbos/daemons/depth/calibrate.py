from bbos import Reader, Writer, Type, Config
from bbos.paths import KEY_PTH, CERT_PTH
from bbos.os_utils import who_ip

from pathlib import Path
import argparse, cv2, signal, subprocess, asyncio, uvicorn, re, os, glob, shutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, StreamingResponse

CFG = Config("stereo")
GRID_WIDTH = 7  # number of corners excluding outer
CAL_X = 13
CAL_Y = 29.7
SQUARE_WIDTH = 0.02433

_stop = False


def _sigint(*_):
    global _stop
    _stop = True


signal.signal(signal.SIGINT, _sigint)


def run(r_jpeg, response_time=1, wait_time=5, port=8001):
    # Specify the model ID
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse("""
<!doctype html><meta charset=utf-8>
<title>Capture Chessboard Frames</title>
<style>
button {
  font-size: 2.5rem;
  padding: 1.2rem 2.5rem;
  margin: 2rem;
}
body {
  text-align: center;
  font-family: sans-serif;
  margin-top: 5rem;
}
#count {
  font-size: 4rem;
  margin-top: 2rem;
  color: #333;
}
</style>
<h1>Tap to Register Click</h1>
<button onclick="sendStop()">STOP</button>
<img id="feed" src="/feed" alt="camera stream">
<script>
let stopped = false;
function sendStop() {
  stopped = true;
  fetch("/stop", { method: "POST" });
}
</script>
""")

    @app.get("/feed")
    async def feed():
        boundary = b"--frame\r\n"
        headers = {"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
        folder = Path('cache')
        folder.mkdir(parents=True, exist_ok=True)
        start = max(
            (int(f.name[5:8])
             for f in list(folder.rglob("*.jpg"))), default=0) + 1

        async def gen():
            i = 0
            while not _stop:  # quits on Ctrl-C
                if r_jpeg.ready():
                    stale, d = r_jpeg.get()
                    if stale:
                        continue
                    size = int(d["bytesused"])
                    jpeg = memoryview(d['jpeg'])[:size]
                    img = cv2.imdecode(d["jpeg"], cv2.IMREAD_GRAYSCALE)
                    grid_size = (GRID_WIDTH, GRID_WIDTH)
                    found, corners = cv2.findChessboardCorners(
                        img, grid_size, flags=cv2.CALIB_CB_ADAPTIVE_THRESH)
                    if found:
                        cv2.imwrite(
                            str(folder / f"frame{start + i:03d}_left.jpg"),
                            img[:, :img.shape[1] // 2])
                        cv2.imwrite(
                            str(folder / f"frame{start + i:03d}_right.jpg"),
                            img[:, img.shape[1] // 2:])
                        cv2.drawChessboardCorners(img, grid_size, corners,
                                                  found)
                        i += 1
                    success, res = cv2.imencode('.jpg', img)
                    if success:
                        jpeg = memoryview(res)
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n"
                           b"Content-Length: %d\r\n\r\n" % jpeg.nbytes + jpeg +
                           b"\r\n")
                await asyncio.sleep(0.05)

        return StreamingResponse(gen(), headers=headers)

    @app.post("/stop")
    async def stop():
        global _stop
        _stop = True
        os.kill(os.getpid(), signal.SIGINT)
        return {"ok": True, "message": "counting stopped"}

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        ws="wsproto",
        log_level="info",
        access_log=False,
        ssl_keyfile=str(KEY_PTH),
        ssl_certfile=str(CERT_PTH),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="calibrate_camera",
                                 description="Calibrate stereo camera")
    '''
    with Reader("/camera.jpeg") as r_jpeg:
        run(r_jpeg)
    subprocess.run([
        "mrgingham", "--jobs", "4", "--gridn",
        str(GRID_WIDTH), *["cache/*.jpg"]
    ],
                   stdout=open("cache/corners.vnl", "w"),
                   check=True)
    '''
    print(CFG.__dict__)
    for oddeven in ("odd", "even"):
        cmd = [
            "mrcal-calibrate-cameras",
            "--corners-cache",
            "cache/corners.vnl",
            "--lensmodel",
            "LENSMODEL_SPLINED_STEREOGRAPHIC_order=3_Nx=30_Ny=18_fov_x_deg={}".
            format(int(round(CFG.xfov))),
            "--focal",
            str(CFG.f_x),
            "--object-spacing",
            str(SQUARE_WIDTH),
            "--object-width-n",
            str(GRID_WIDTH),
            "cache/*_left.jpg",
            "cache/*_right.jpg",
        ]

        if oddeven == "even":
            globs = glob.glob("frame*[048]_left.jpg") + glob.glob(
                "frame*[048]_right.jpg")
        else:
            globs = glob.glob("frame*[159]_left.jpg") + glob.glob(
                "frame*[159]_right.jpg")

        cmd += globs

        subprocess.run(cmd, check=True)

        for i in ('left', 'right'):
            shutil.move(f"{i}.cameramodel", f"cache/{i}-{oddeven}.cameramodel")
