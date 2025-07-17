from bbos import Reader, Writer, Type, Config
from bbos.paths import KEY_PTH, CERT_PTH
from bbos.os_utils import who_ip

import argparse, cv2, signal, subprocess, asyncio, uvicorn, re
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse

CFG = Config("stereo")
GRID_WIDTH = 17
CAL_X = 13
CAL_Y = 29.7


def extract_px_per_mm():
    host_ip = who_ip()
    user = input("Enter host username: ")
    with subprocess.Popen(["ssh", f"{user}@{host_ip}", "DISPLAY=:0 xrandr"],
                          stdout=subprocess.PIPE,
                          text=True) as proc:
        candidates = []
        for line in proc.stdout:
            if " connected" in line and "mm x" in line:
                match = re.search(
                    r"^(\S+)\s+connected.*?(\d+)x(\d+)\+\d+\+\d+.*?(\d+)mm x (\d+)mm",
                    line)
                if match:
                    name = match.group(1)
                    px_w = int(match.group(2))
                    px_h = int(match.group(3))
                    mm_w = int(match.group(4))
                    mm_h = int(match.group(5))
                    px_per_mm_x = px_w / mm_w
                    px_per_mm_y = px_h / mm_h
                    candidates.append((name, px_per_mm_x, px_per_mm_y))

    if not candidates:
        raise RuntimeError(
            "No connected displays with physical dimensions found.")

    print("Available displays:")
    for i, (name, px_x, px_y) in enumerate(candidates):
        print(f"[{i}] {name}: {px_x:.2f} px/mm (x), {px_y:.2f} px/mm (y)")

    choice = int(input("Select display index: "))
    _, px_x, px_y = candidates[choice]
    return px_x, px_y


_stop = False


def _sigint(*_):
    global _stop
    _stop = True


signal.signal(signal.SIGINT, _sigint)


def run(r_jpeg, rate, response_time=1, wait_time=5, port=8001):
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
<button onclick="sendClick()">CLICK</button>
<button onclick="sendStop()">STOP</button>
<div id="count">Count: 0</div>
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
        t = Time(20)
        folder = Path('cache')
        folder.mkdir(parents=True, exist_ok=True)

        async def gen():
            i = 0
            while not _stop:  # quits on Ctrl-C
                if r_jpeg.ready():
                    stale, d = r_jpeg.get()
                    if stale:
                        continue
                    img = cv2.imdecode(d['jpeg'], cv2.IMREAD_GRAYSCALE)
                    found, corners = cv2.findChessboardCorners(
                        img, args.size, flags=cv2.CALIB_CB_ADAPTIVE_THRESH)
                    if found:
                        if capture:
                            cv2.imwrite(
                                folder / f"frame{start + i:03d}_left.jpg",
                                img[:, :img.shape[1] // 2])
                            cv2.imwrite(
                                folder / f"frame{start + i:03d}_right.jpg",
                                img[:, img.shape[1] // 2:])
                            capture = False
                        cv2.drawChessboardCorners(img, size, corners, found)
                        i += 1
                    success, res = cv2.imencode('.jpg', img)
                    if not success:
                        res = d['jpeg'][:d['bytesused']]
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n"
                           b"Content-Length: %d\r\n\r\n" % res.nbytes +
                           memoryview(res) + b"\r\n")

        return StreamingResponse(gen(), headers=headers)

    @app.post("/clicked")
    async def clicked(req: Request):
        if stopped:
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
        log_level="critical",
        access_log=False,
        ssl_keyfile=str(KEY_PTH),
        ssl_certfile=str(CERT_PTH),
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(prog="calibrate_camera",
                                 description="Calibrate stereo camera")
    args = ap.parse_args()
    subprocess.run([f"./checker {GRID_WIDTH} {CAL_X} {CAL_Y}"], check=True)
    square_width = input("Square width (in meters)? ")

    with Reader("/camera.jpeg") as r_jpeg:
        run(r_jpeg)
    subprocess.run(
        [f"mrgingham --jobs 4 --gridn {GRID_WIDTH} '*.jpg' > corners.vnl"],
        check=True)
    for oddeven in ("odd", "even"):
        cmd = [
            "mrcal-calibrate-cameras", "--corners-cache", "corners.vnl",
            "--lensmodel",
            "LENSMODEL_SPLINED_STEREOGRAPHIC_order=3_Nx=30_Ny=18_fov_x_deg={}".
            format(xfov), "--focal",
            str(f_x), "--object-spacing",
            str(square_width), "--object-width-n",
            str(GRID_WIDTH)
        ]

        if oddeven == "even":
            globs = glob.glob("frame*[02468]-left.jpg") + glob.glob(
                "frame*[02468]-right.jpg")
        else:
            globs = glob.glob("frame*[13579]-left.jpg") + glob.glob(
                "frame*[13579]-right.jpg")

        cmd += globs

        subprocess.run(cmd, check=True)

        for i in ('left', 'right'):
            shutil.move(f"{i}.cameramodel", f"{i}-{oddeven}.cameramodel")
