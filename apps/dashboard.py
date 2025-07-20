# /// script
# dependencies = [
#   "fastapi",
#   "uvicorn",
#   "wsproto",
# ]
# ///
import asyncio
import json
import os
import signal
import time
from pathlib import Path
from typing import Dict, List
from multiprocessing import Process
import multiprocessing as mp

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

from bbos.os_utils import Priority, config_realtime_process
from bbos.paths import *

# Configuration
REFRESH_TIME: float = 2.0  # seconds
RATE_LIMIT_INTERVAL: float = 2.0  # seconds between app starts
PROCESS_STOP_TIMEOUT: float = 5.0  

class AppManager:
    def __init__(self):
        self.processes: Dict[str, Process] = {}
        self.last_start: Dict[str, float] = {}
    
    def get_available_apps(self) -> List[str]:
        """Get list of available apps from APPS_PATH"""
        if not APPS_PATH.exists():
            return []
        
        apps = []
        for app_file in APPS_PATH.glob("*.py"):
            apps.append(app_file.stem)
        return sorted(apps)
    
    def is_app_running(self, app_name: str) -> bool:
        """Check if an app is currently running"""
        if app_name not in self.processes:
            return False
        
        proc = self.processes[app_name]
        if not proc or proc.exitcode is not None:
            # Process has terminated, remove it
            if proc and proc.exitcode != 0:
                print(f"[dashboard] {app_name} exited ({proc.exitcode})")
            del self.processes[app_name]
            return False
        
        return True

   # ── dashboard/launch side ─────────────────────────────────────────────
    def _launch_app(self, app):
        os.chdir(BRACKETBOT_PATH)
        os.setsid()                                     # ① new session = new PGID
        log_fd = open(f"/tmp/app-{app}.log", "wb", 0)
        os.dup2(log_fd.fileno(), 1); os.dup2(log_fd.fileno(), 2)
        os.execvp("run", ["run", f"apps/{app}.py"])     # replaces the process

    # ── dashboard/stop side ───────────────────────────────────────────────
    def stop_app(self, app, timeout=PROCESS_STOP_TIMEOUT):
        if not self.is_app_running(app):
            return False
        p = self.processes[app]
        os.killpg(p.pid, signal.SIGINT)                 # ② INT the whole group
        p.join(timeout)
        if p.is_alive():
            p.terminate(); p.join(2)                    # escalate → TERM/KILL
        del self.processes[app]
        return True 
    
    def start_app(self, app_name: str) -> bool:
        """Start an app"""
        if self.is_app_running(app_name):
            return False  # Already running
        
        # Rate limiting: don't start too frequently
        if app_name in self.last_start and time.time() - self.last_start[app_name] < RATE_LIMIT_INTERVAL:
            return False
        
        try:

            ctx  = mp.get_context("fork")         # optional – keeps code explicit
            proc = ctx.Process(target=self._launch_app, args=(app_name,),
                              name=app_name)
            proc.start()
            
            self.processes[app_name] = proc
            self.last_start[app_name] = time.time()
            print(f"[dashboard] Started app: {app_name} (pid={proc.pid})")
            return True
            
        except Exception as e:
            print(f"[dashboard] Failed to start {app_name}: {e}")
            return False
    
    def get_lock_files_status(self) -> Dict[str, bool]:
        """Get status of lock files in /tmp/*_lock"""
        lock_files = {}
        tmp_path = Path("/tmp")
        
        for lock_file in tmp_path.glob("*_lock"):
            name = lock_file.name[:-5]  # Remove '_lock' suffix
            lock_files[name] = lock_file.exists()
        
        return lock_files
    
    def get_status(self) -> Dict:
        """Get complete status of all apps and lock files"""
        apps = self.get_available_apps()
        app_status = {}
        
        for app in apps:
            app_status[app] = {
                "running": self.is_app_running(app),
                "pid": self.processes[app].pid if self.is_app_running(app) else None
            }
        
        return {
            "apps": app_status,
            "locks": self.get_lock_files_status()
        }

# Global app manager
mp.set_start_method("fork", force=True)   # put this once at program start
app_manager = AppManager()
_stop = False

def _sigint(*_):
    global _stop
    _stop = True

signal.signal(signal.SIGINT, _sigint)

def create_app():
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
        
        try:
            while not _stop:
                try:
                    # Wait for message with timeout
                    message = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                    data = json.loads(message)
                    
                    if data.get("action") == "get_status":
                        status = app_manager.get_status()
                        await websocket.send_text(json.dumps(status))
                    
                    elif data.get("action") == "start_app":
                        app_name = data.get("app_name")
                        if app_name:
                            success = app_manager.start_app(app_name)
                            if success:
                                # Send updated status
                                status = app_manager.get_status()
                                await websocket.send_text(json.dumps(status))
                    
                    elif data.get("action") == "stop_app":
                        app_name = data.get("app_name")
                        if app_name:
                            success = app_manager.stop_app(app_name)
                            print(f"[dashboard] Stopping app: {app_name} - {success}")
                            if success:
                                # Send updated status
                                status = app_manager.get_status()
                                await websocket.send_text(json.dumps(status))
                
                except asyncio.TimeoutError:
                    # Send periodic status updates
                    status = app_manager.get_status()
                    await websocket.send_text(json.dumps(status))
                    
        except WebSocketDisconnect:
            print("[dashboard] WebSocket client disconnected")
        except Exception as e:
            print(f"[dashboard] WebSocket error: {e}")

    return app

def main():
    config_realtime_process(3, Priority.CTRL_HIGH)
    
    # Create FastAPI app
    app = create_app()
    
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
    main() 