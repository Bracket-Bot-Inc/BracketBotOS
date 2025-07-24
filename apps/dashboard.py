# AUTO
# /// script
# dependencies = [
#   "fastapi",
#   "uvicorn",
#   "wsproto",
#   "bbos @ /home/GREEN/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
# ]
# ///
import asyncio
import json
import signal
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

from bbos.app_manager import AppManager
from bbos.paths import KEY_PTH, CERT_PTH

REFRESH_TIME: float = 2.0  # seconds

_stop = False

def _sigint(*_):
    global _stop
    _stop = True

signal.signal(signal.SIGINT, _sigint)

def main(app_manager):
    app = FastAPI()
    
    @app.get("/", response_class=HTMLResponse)
    async def root():
        return HTMLResponse("""
<!doctype html><meta charset=utf-8>
<title>BracketBot Dashboard</title>
<style>
body {
  margin: 20px;
  background: #111;
  color: white;
  font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.container {
  max-width: 1200px;
  margin: 0 auto;
}

h1, h2 {
  color: #4CAF50;
  text-align: center;
}

.section {
  background: #222;
  border-radius: 12px;
  padding: 20px;
  margin: 20px 0;
}

.app-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 15px;
  margin-top: 15px;
}

.app-card {
  background: #333;
  border-radius: 8px;
  padding: 15px;
  border: 2px solid #444;
}

.app-card.running {
  border-color: #4CAF50;
}

.app-card.stopped {
  border-color: #f44336;
}

.app-name {
  font-size: 18px;
  font-weight: bold;
  margin-bottom: 10px;
}

.app-status {
  margin: 5px 0;
  padding: 5px 10px;
  border-radius: 4px;
  font-size: 14px;
}

.status-running {
  background: #4CAF50;
  color: white;
}

.status-stopped {
  background: #f44336;
  color: white;
}

.toggle-btn {
  background: #2196F3;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  margin-top: 10px;
  width: 100%;
}

.toggle-btn:hover {
  background: #1976D2;
}

.toggle-btn:disabled {
  background: #666;
  cursor: not-allowed;
}

.lock-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
  margin-top: 15px;
}

.lock-item {
  background: #333;
  padding: 10px;
  border-radius: 6px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.lock-status {
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
}

.lock-active {
  background: #4CAF50;
  color: white;
}

.lock-inactive {
  background: #666;
  color: white;
}

.loading {
  text-align: center;
  color: #888;
  font-style: italic;
}
</style>

<div class="container">
  <h1>🤖 BracketBot Dashboard</h1>
  
  <div class="section">
    <h2>Applications</h2>
    <div id="apps-container" class="loading">Loading apps...</div>
  </div>
  
  <div class="section">
    <h2>Lock Files Status</h2>
    <div id="locks-container" class="loading">Loading lock files...</div>
  </div>
</div>

<script>
let ws = null;

function connectWebSocket() {
  const protocol = location.protocol === "https:" ? "wss://" : "ws://";
  ws = new WebSocket(protocol + location.host + "/ws");
  
  ws.onopen = function() {
    console.log("WebSocket connected");
    requestStatus();
  };
  
  ws.onmessage = function(event) {
    const data = JSON.parse(event.data);
    updateUI(data);
  };
  
  ws.onclose = function() {
    console.log("WebSocket disconnected, reconnecting...");
    setTimeout(connectWebSocket, 2000);
  };
  
  ws.onerror = function(error) {
    console.error("WebSocket error:", error);
  };
}

function requestStatus() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: "get_status" }));
  }
}

function toggleApp(appName, isRunning) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    const action = isRunning ? "stop_app" : "start_app";
    ws.send(JSON.stringify({ action: action, app_name: appName }));
  }
}

function updateUI(data) {
  if (data.apps) {
    updateApps(data.apps);
  }
  if (data.locks) {
    updateLocks(data.locks);
  }
}

function updateApps(apps) {
  const container = document.getElementById("apps-container");
  container.innerHTML = "";
  container.className = "app-grid";
  
  if (Object.keys(apps).length === 0) {
    container.innerHTML = "<div class='loading'>No apps found</div>";
    return;
  }
  
  for (const [appName, status] of Object.entries(apps)) {
    const isRunning = status.running;
    const card = document.createElement("div");
    card.className = `app-card ${isRunning ? "running" : "stopped"}`;
    
    card.innerHTML = `
      <div class="app-name">${appName}</div>
      <div class="app-status ${isRunning ? "status-running" : "status-stopped"}">
        ${isRunning ? "RUNNING" : "STOPPED"}
        ${status.pid ? ` (PID: ${status.pid})` : ""}
      </div>
      <button class="toggle-btn" onclick="toggleApp('${appName}', ${isRunning})">
        ${isRunning ? "Stop" : "Start"} App
      </button>
    `;
    
    container.appendChild(card);
  }
}

function updateLocks(locks) {
  const container = document.getElementById("locks-container");
  container.innerHTML = "";
  container.className = "lock-grid";
  
  if (Object.keys(locks).length === 0) {
    container.innerHTML = "<div class='loading'>No lock files found</div>";
    return;
  }
  
  for (const [lockName, isActive] of Object.entries(locks)) {
    const item = document.createElement("div");
    item.className = "lock-item";
    
    item.innerHTML = `
      <span>${lockName}</span>
      <span class="lock-status ${isActive ? "lock-active" : "lock-inactive"}">
        ${isActive ? "ACTIVE" : "INACTIVE"}
      </span>
    `;
    
    container.appendChild(item);
  }
}

// Connect WebSocket and refresh status periodically
connectWebSocket();
setInterval(requestStatus, """ + str(int(REFRESH_TIME * 1000)) + """);
</script>
""")
    
    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        print("[dashboard] WebSocket client connected")
        status = lambda: app_manager.get_status(exclude=['dashboard'])
        try:
            while not _stop:
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    data = json.loads(message)
                    
                    if data.get("action") == "get_status":
                        await websocket.send_text(json.dumps(status()))
                    
                    elif data.get("action") == "start_app":
                        app_name = data.get("app_name")
                        if app_name:
                            success = app_manager.start_app(app_name)
                            if success:
                                await websocket.send_text(json.dumps(status()))
                    
                    elif data.get("action") == "stop_app":
                        app_name = data.get("app_name")
                        if app_name:
                            success = app_manager.stop_app(app_name)
                            print(f"[dashboard] Stopping app: {app_name} - {success}")
                            if success:
                                await websocket.send_text(json.dumps(status()))
                
                except asyncio.TimeoutError:
                    # Send periodic status updates
                    await websocket.send_text(json.dumps(status()))
                    
        except WebSocketDisconnect:
            print("[dashboard] WebSocket client disconnected")
        except Exception as e:
            print(f"[dashboard] WebSocket error: {e}")

    # Run the server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        ws="wsproto",
        log_level="info",
            ssl_keyfile=str(KEY_PTH),
            ssl_certfile=str(CERT_PTH),
        )


if __name__ == "__main__":
    app_manager = AppManager(Path(__file__).parent)
    main(app_manager) 