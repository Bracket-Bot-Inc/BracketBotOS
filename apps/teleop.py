# /// script
# dependencies = [
#   "fastapi",
#   "uvicorn",
#   "wsproto",
#   "bbos",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
from bbos import Reader, Writer, Type

import signal, json, numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn
import asyncio

SPEED_LIN =12.0  # m s⁻¹  forward/back
SPEED_ANG = 0.5  # rad s⁻¹ CCW+

_stop = False

def _sigint(*_):
    global _stop
    _stop = True

signal.signal(signal.SIGINT, _sigint)

def run(w_ctrl, r_cam, port=8000):
    # Specify the model ID
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse("""
    <!doctype html><meta charset=utf-8>
    <title>BracketBot Teleop</title>
    <style>
    body {
      margin: 0;
      background: #111;
      color: white;
      font-family: sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100vh;
      overflow: hidden;
    }
    #container {
      display: flex;
      flex-direction: row;
      align-items: center;
      justify-content: center;
      gap: 2rem;
    }
    canvas {
      background: #222;
      border-radius: 12px;
      touch-action: none;
    }
    #feed {
      max-height: 480px;
      max-width: 640px;
      border: 2px solid #333;
      border-radius: 12px;
    }
    </style>
    <div id="container">
      <canvas id="joy-vert" width="100" height="240"></canvas>
      <img id="feed" src="/feed" alt="camera">
      <canvas id="joy-horz" width="240" height="100"></canvas>
    </div>
    <script>
    const vert = document.getElementById("joy-vert");
    const horz = document.getElementById("joy-horz");
    const ctxV = vert.getContext("2d");
    const ctxH = horz.getContext("2d");
    let vPos = 0, hPos = 0;
    const r = 100;

    function drawV() {
      ctxV.clearRect(0, 0, vert.width, vert.height);
      ctxV.fillStyle = "#555";
      ctxV.fillRect(40, 20, 20, 200);
      ctxV.beginPath();
      ctxV.arc(50, 120 + vPos * 100, 20, 0, 2 * Math.PI);
      ctxV.fillStyle = "#0f0";
      ctxV.fill();
    }

    function drawH() {
      ctxH.clearRect(0, 0, horz.width, horz.height);
      ctxH.fillStyle = "#555";
      ctxH.fillRect(20, 40, 200, 20);
      ctxH.beginPath();
      ctxH.arc(120 + hPos * 100, 50, 20, 0, 2 * Math.PI);
      ctxH.fillStyle = "#0f0";
      ctxH.fill();
    }

    function send(ws) {
      if (ws.readyState === 1) {
        ws.send(JSON.stringify({ x: hPos, y: vPos }));
      }
    }

    const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/ws");

    function clamp(v) {
      return Math.max(-1, Math.min(1, v));
    }

    function attachJoystick(canvas, isVertical, setPos) {
      let dragging = false;
      canvas.addEventListener("pointerdown", e => { dragging = true; update(e); });
      canvas.addEventListener("pointermove", e => { if (dragging) update(e); });
      canvas.addEventListener("pointerup", () => { dragging = false; setPos(0); });
      canvas.addEventListener("pointerleave", () => { if (dragging) { dragging = false; setPos(0); } });

      function update(e) {
        const rect = canvas.getBoundingClientRect();
        const pos = isVertical
          ? ((e.clientY - rect.top - rect.height / 2) / (rect.height / 2))
          : ((e.clientX - rect.left - rect.width / 2) / (rect.width / 2));
        setPos(clamp(pos));
      }
    }

    attachJoystick(vert, true, y => { vPos = y; drawV(); send(ws); });
    attachJoystick(horz, false, x => { hPos = x; drawH(); send(ws); });

    drawV();
    drawH();
    </script>
    """)

    @app.get("/feed")
    async def feed():
        boundary = b"--frame\r\n"
        headers = {"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
        async def gen():
            while not _stop:  # quits on Ctrl-C
                if r_cam.ready():
                    size = int(r_cam.data["bytesused"])
                    jpeg = memoryview(r_cam.data["jpeg"])[:size]
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n"
                           b"Content-Length: %d\r\n\r\n" % size + jpeg +
                           b"\r\n")
                await asyncio.sleep(0.05)
        return StreamingResponse(gen(), headers=headers)

    @app.websocket("/ws")
    async def joy_ws(ws: WebSocket):
        await ws.accept()
        print("[WS] Joystick connected")
        try:
            while not _stop:
                msg = await ws.receive_text()
                payload = json.loads(msg)
                if "x" not in payload or "y" not in payload:
                    continue
                cmd = np.array([payload['x'] * SPEED_ANG, payload['y'] * SPEED_LIN])
                w_ctrl["twist"] = cmd
                await asyncio.sleep(0.05)
        except WebSocketDisconnect:
            print("[WS] Client disconnected")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        ws="wsproto",
        log_level="info",
    )


def main():
    with Writer('drive.ctrl', Type("drive_ctrl")) as w_ctrl, \
         Reader('camera.jpeg') as r_cam:
        run(w_ctrl, r_cam)

if __name__ == "__main__":
    main()