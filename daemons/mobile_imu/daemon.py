from bbos import Reader, Writer, Config, Type, Time
from bbos.os_utils import Priority, config_realtime_process
from bbos.paths import KEY_PTH, CERT_PTH

import traceback, shutil, subprocess, time, os, signal, sys, json, numpy as np
from pathlib import Path
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, StreamingResponse
import uvicorn

# Configuration
cert = Path(__file__).resolve().parent / "cert.pem"
key = Path(__file__).resolve().parent / "key.pem"
CFG = Config("device_imu")


class PosAccum:

    def __init__(self):
        self.turns = None  # integer turn counter
        self.pi = None  # previous raw reading

    def __call__(self, p):
        p = np.asarray(p)

        if self.pi is None:  # first sample
            self.pi = p
            self.turns = np.zeros_like(p, dtype=int)
            return p

        dx = p - self.pi
        step = np.where(
            dx < -0.5,
            1,  # crossed 1→0 (forward)
            np.where(dx > 0.5, -1, 0))  # crossed 0→1 (reverse)

        self.turns += step  # accumulate full turns
        self.pi = p  # advance reference

        return p + self.turns  # unwrapped position


_stop = False


def _sigint(*_):
    global _stop
    _stop = True


signal.signal(signal.SIGINT, _sigint)


def run(w_imu, r_cam, rate, response_time=1, wait_time=5, port=8000):
    # Specify the model ID
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse("""
<!doctype html><meta charset=utf-8>
<title>IMU WebSocket Test</title>
<style>body{font-family:sans-serif;text-align:center;margin-top:2rem}</style>
<h3 id=s>Tap anywhere to start IMU streaming</h3>
<img id="feed" src="/feed" alt="camera stream">
<pre id=o>{}</pre>
<script>
const s = document.querySelector('h3'), o = document.getElementById('o');
document.body.addEventListener('click', async () => {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(`${scheme}://${location.host}/ws`);
    ws.onopen = () => s.textContent = 'WebSocket connected';
    ws.onclose = () => s.textContent = 'WebSocket closed';

    if (DeviceMotionEvent?.requestPermission) {
        await DeviceMotionEvent.requestPermission().catch(console.error);
        await DeviceOrientationEvent.requestPermission().catch(console.error);
    }

    const imu = {};

    window.addEventListener('deviceorientation', e => {
        Object.assign(imu, { alpha: e.alpha, beta: e.beta, gamma: e.gamma });
    });

    window.addEventListener('devicemotion', e => {
        Object.assign(imu, {
            ax: e.acceleration?.x,
            ay: e.acceleration?.y,
            az: e.acceleration?.z,
            rx: e.rotationRate?.alpha,
            ry: e.rotationRate?.beta,
            rz: e.rotationRate?.gamma
        });
    });

    setInterval(() => {
        o.textContent = JSON.stringify(imu, null, 2);
        if (ws.readyState === 1) ws.send(JSON.stringify(imu));
    }, 20);
}, { once: true });
</script>
""")

    @app.get("/feed")
    async def feed():
        boundary = b"--frame\r\n"
        headers = {"Content-Type": "multipart/x-mixed-replace; boundary=frame"}
        t = Time(20)

        async def gen():
            while not _stop:  # quits on Ctrl-C
                if r_cam.ready():
                    stale, img = r_cam.get()
                    if stale:
                        continue
                    size = int(img["bytesused"])
                    jpeg = memoryview(img["jpeg"])[:size]
                    yield (b"--frame\r\n"
                           b"Content-Type: image/jpeg\r\n"
                           b"Content-Length: %d\r\n\r\n" % size + jpeg +
                           b"\r\n")
                await asyncio.sleep(0.05)

        return StreamingResponse(gen(), headers=headers)

    @app.websocket("/ws")
    async def imu_ws(ws: WebSocket):
        await ws.accept()
        print("[WS] IMU connected")
        pos = PosAccum()  # handle overflows
        try:
            while True:
                msg = await ws.receive_text()
                payload = json.loads(msg)
                if set([
                        'alpha', 'beta', 'gamma', 'ax', 'ay', 'az', 'rx', 'ry',
                        'rz'
                ]) != set(payload.keys()):
                    continue

                with w_imu.buf() as buf:
                    buf[:]['gyro'] = pos(
                        np.array(
                            [payload[k]
                             for k in ['alpha', 'beta', 'gamma']]) / 360.)
                    buf[:]['accel'] = np.array([
                        payload[k]
                        for k in ['ax', 'ay', 'az', 'rx', 'ry', 'rz']
                    ])
                    buf[:]['timestamp'] = rate.now()
                await asyncio.sleep(0.01)
        except WebSocketDisconnect:
            print("[WS] Client disconnected")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        ws="wsproto",
        log_level="info",
        ssl_keyfile=str(KEY_PTH),
        ssl_certfile=str(CERT_PTH),
    )


def main():
    config_realtime_process(3, Priority.CTRL_HIGH)
    rate = Time(CFG.rate)
    with Writer('/mobile.imu', Type("imu")) as w_imu, \
         Reader('/camera.jpeg') as r_cam :
        run(w_imu, r_cam, rate)
    print(rate.stats)


if __name__ == "__main__":
    main()
