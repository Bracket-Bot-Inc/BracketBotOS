from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn
import json

from pathlib import Path

app = FastAPI()


@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse("""
<!doctype html><meta charset=utf-8>
<title>IMU WebSocket Test</title>
<style>body{font-family:sans-serif;text-align:center;margin-top:2rem}</style>
<h3 id=s>Tap anywhere to start IMU streaming</h3>
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


@app.websocket("/ws")
async def imu_ws(ws: WebSocket):
    await ws.accept()
    print("[WS] IMU connected")
    try:
        while True:
            msg = await ws.receive_text()
            payload = json.loads(msg)
            print("[WS] Received:", payload)
    except WebSocketDisconnect:
        print("[WS] Client disconnected")


cert = Path(__file__).resolve().parent / "cert.pem"
key = Path(__file__).resolve().parent / "key.pem"
if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        ws="wsproto",
        log_level="info",
        ssl_keyfile=str(key),
        ssl_certfile=str(cert),
    )
