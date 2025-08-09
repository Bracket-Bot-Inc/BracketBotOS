import os, json, signal, time, multiprocessing as mp
from pathlib import Path
from typing import Dict, List
from multiprocessing import Process
import multiprocessing as mp
import pwd

# Configuration
RATE_LIMIT_INTERVAL: float = 2.0  # seconds between app starts
PROCESS_STOP_TIMEOUT: float = 5.0  
CURRENT_USER = pwd.getpwuid(os.getuid()).pw_name

def get_owned_locks(name):
    for lock in Path("/tmp").glob(f"{name}_lock"):
        with open(lock, 'r') as f:
            if name in json.load(f)['owner']:
                yield lock
    return []

def get_lock_path(app): return Path(f"/tmp/app-{app}_lock")

def stop_app(app):
    lock = get_lock_path(app)
    if lock.exists():
        lock.unlink()
    else:
        print(f"[app-manager] {app} is not running!")
        return False
    return True

def start_app(name):
    lock = get_lock_path(name)
    if lock.exists():
        print(f"[app-manager] {name} is already running!")
        return False
    else:
        lock.touch()
    return True

def get_status(exclude: List[str] = []) -> Dict:
    """Get complete status of all apps and lock files"""
    with open(f"/tmp/app-manager_lock", "r") as fd:
        app_paths = json.load(fd)
    app_status = {}
    for app in app_paths:
        if app in exclude:
            continue
        app_status[app] = get_lock_path(app).exists()
    return app_status

class AppManager:
    def __init__(self, app_dirs: List[Path] | Path):
        self.app_dirs = app_dirs if isinstance(app_dirs, list) else [app_dirs]
        mp.set_start_method("fork", force=True)
        self.processes: Dict[str, Process] = {}
        self.last_start: Dict[str, float] = {}
        self.app_paths: Dict[str, Path] = {}
        self.autostart: List[str] = []
        self.get_available_apps()

    def get_available_apps(self) -> List[str]:
        """Get list of available apps from APPS_PATH"""
        def is_autostart(file: Path) -> bool:
            for i, line in enumerate(file.read_text().splitlines()):
                if i > 3:  # Only check first 10 lines
                    break
                line_stripped = line.strip()
                if line_stripped.startswith("#AUTO") or line_stripped.startswith("# AUTO"):
                    print(f"[autostart] Found autostart app: {file.parent.name}/{file.stem}") 
                    return True
            else:
                return False
        apps = []
        for app_dir in self.app_dirs:
            # Check for .py files
            for app_file in app_dir.glob("*.py"):
                apps.append(app_file.stem)
                self.app_paths[app_file.stem] = app_file.absolute()
                if is_autostart(app_file):
                    self.autostart.append(app_file.stem)
            
            # Check for folders with main.py
            for folder in app_dir.iterdir():
                if folder.is_dir():
                    main_file = folder / "main.py"
                    if main_file.exists():
                        apps.append(folder.name)
                        self.app_paths[folder.name] = main_file.absolute()
                        if is_autostart(main_file):
                            self.autostart.append(folder.name)
        with open(f"/tmp/app-manager_lock", "w") as fd:
            json.dump({k: str(v.absolute()) for k, v in self.app_paths.items()}, fd)
        return apps
    
    def is_app_running(self, app: str) -> bool:
        return app in self.processes and self.processes[app].is_alive()

   # ── dashboard/launch side ─────────────────────────────────────────────
    def _launch_app(self, app):
        os.setsid()                                    # ① new session = new PGID
        os.chdir(self.app_paths[app].parent)
        os.environ["PATH"] += f"/home/{CURRENT_USER}/.local/bin"
        log_fd = open(f"/tmp/app-{app}.log", "wb", 0)
        os.dup2(log_fd.fileno(), 1); os.dup2(log_fd.fileno(), 2)
        venv_path = str(self.app_paths[app].parent / ".venv")
        if Path(venv_path).exists():
            os.execvp("bash", ["bash", "-c", f"source {venv_path}/bin/activate && exec python {self.app_paths[app]}"])
        else:
            os.execvp("uv", ["uv", "run", str(self.app_paths[app])])

    # ── dashboard/stop side ───────────────────────────────────────────────
    def _stop_app(self, app, timeout=PROCESS_STOP_TIMEOUT):
        if self.is_app_running(app):
            if app in self.processes:
                p = self.processes[app]
                os.killpg(p.pid, signal.SIGINT)                 # ② INT the whole group
                p.join(timeout)
                if p.is_alive():
                    p.terminate(); p.join(2)                    # escalate → TERM/KILL
                del self.processes[app]
        return True


    def _start_app(self, app_name: str) -> bool:
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
            print(f"[dashboard] Starting ")
            proc.start()
            self.processes[app_name] = proc
            self.last_start[app_name] = time.time()
            print(f"[dashboard] Started app: {app_name} (pid={proc.pid})")
            return True
            
        except Exception as e:
            print(f"[dashboard] Failed to start {app_name}: {e}")
            return False
    
    def start(self):
        for app in self.autostart:
            print(f"[app-manager] Starting autostart app: {app}")
            if not start_app(app):
                print(f"[app-manager] Failed to start autostart app: {app}")
        try:
            while True:
                for app in self.get_available_apps():
                    if not get_lock_path(app).exists() and app in self.processes:
                        print(f"[app-manager] Detected external delete of {app}_lock. Terminating.")
                        self._stop_app(app)
                    if get_lock_path(app).exists() and app not in self.processes:
                        print(f"[app-manager] Detected external creation of {app}_lock. Starting.")
                        self._start_app(app)
                    time.sleep(0.05)
        except KeyboardInterrupt:
            self.stop_all()

    def stop_all(self):
        while self.processes:
            app = next(iter(self.processes))
            self.stop_app(app)
    
    def __del__(self):
        self.stop_all()