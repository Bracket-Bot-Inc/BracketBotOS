from bbos import Reader, Writer, Type, Config
from bbos.paths import KEY_PTH, CERT_PTH

from pathlib import Path
import argparse, cv2, signal, subprocess, asyncio, uvicorn, re, os, glob, shutil
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, StreamingResponse

CFG = Config("stereo")
GRID_WIDTH = 5
SQUARE_WIDTH = 0.08397
CAL_X = 54.04
CAL_Y = 131.45

_stop = False


def _sigint(*_):
    global _stop
    _stop = True


signal.signal(signal.SIGINT, _sigint)


def run(r_jpeg, response_time=1, wait_time=5, port=8002):
    # Specify the model ID
    app = FastAPI()
    print("app")


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
<div id="count">Count: 0</div>
<img id="feed" src="/feed" alt="camera stream">
<button onclick="sendClick()">CLICK</button>
<script>
let localCount = 0;
let stopped = false;
const countElem = document.getElementById("count");
function sendClick() {
  if (stopped) return;
  localCount++;
  countElem.textContent = `Count: ${localCount}`;
  fetch("/clicked", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ clicked: true })
  });
}
function sendStop() {
  stopped = true;
  fetch("/stop", { method: "POST" });
}
</script>
""")
    capture = False

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
            nonlocal capture
            i = 0
            start = 0  # Initialize frame counter start
            print("ready")
            while not _stop:  # quits on Ctrl-C
                if r_jpeg.ready():
                    img = cv2.imdecode(r_jpeg.data['jpeg'][:r_jpeg.data['bytesused']], cv2.IMREAD_GRAYSCALE)
                    grid = (GRID_WIDTH, GRID_WIDTH)
                    found, corners = cv2.findChessboardCorners(
                        img, grid, flags=cv2.CALIB_CB_ADAPTIVE_THRESH)
                    if found:
                        cv2.imwrite(
                            str(folder / f"frame{start + i:03d}_left.jpg"),
                            img[:, :img.shape[1] // 2])
                        cv2.imwrite(
                            str(folder / f"frame{start + i:03d}_right.jpg"),
                            img[:, img.shape[1] // 2:])
                        capture = False
                        i += 1
                        cv2.drawChessboardCorners(img, grid, corners, found)
                        _, res = cv2.imencode('.jpg', img)  # Get the encoded data from tuple
                        print(res.nbytes)
                    else:
                        res = r_jpeg.data['jpeg'][:r_jpeg.data['bytesused']]
                        print("no corners", res.nbytes)
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n"
                           b"Content-Length: %d\r\n\r\n" % res.nbytes + memoryview(res) + 
                           b"\r\n")
                await asyncio.sleep(0.5)

        return StreamingResponse(gen(), headers=headers)

    @app.post("/clicked")
    async def clicked(req: Request):
        nonlocal capture
        if _stop:
            return {"ok": False, "message": "stopped"}
        data = await req.json()
        if data.get("clicked"):
            capture = True
        return {"ok": True}

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
    '''
    with Reader("/camera.jpeg") as r_jpeg:
        run(r_jpeg)
    '''
    subprocess.run([
        "mrgingham", "--jobs", "4", "--gridn",
        str(GRID_WIDTH), *["cache/*.jpg"]
    ],
                   stdout=open("cache/corners.vnl", "w"),
                   check=True)
    print(CFG.__dict__)
    cmd = [
        "mrcal-calibrate-cameras",
        "--corners-cache",
        "cache/corners.vnl",
        "--lensmodel",
        #"LENSMODEL_SPLINED_STEREOGRAPHIC_order=3_Nx=30_Ny=18_fov_x_deg={}".format(int(round(CFG.xfov))),
        "LENSMODEL_OPENCV8",
        "--focal",
        str(CFG.f_x),
        "--object-spacing",
        str(SQUARE_WIDTH),
        "--object-width-n",
        str(GRID_WIDTH),
        "cache/frame*_left.jpg",
        "cache/frame*_right.jpg",
    ]
    print(cmd)
    subprocess.run(cmd, check=True)

    for i,j in ((0, 'left'), (1, 'right')):
        shutil.move(f"camera-{i}.cameramodel", f"cache/{j}.cameramodel")