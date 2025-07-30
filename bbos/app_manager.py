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

class AppManager:
    def __init__(self, app_dirs: List[Path] | Path):
        self.app_dirs = app_dirs if isinstance(app_dirs, list) else [app_dirs]
        mp.set_start_method("fork", force=True)
        self.processes: Dict[str, Process] = {}
        self.last_start: Dict[str, float] = {}
        self.app_paths: Dict[str, Path] = {}
        self.get_available_apps()

    def get_available_apps(self) -> List[str]:
        """Get list of available apps from APPS_PATH"""
        apps = []
        for app_dir in self.app_dirs:
            # Check for .py files
            for app_file in app_dir.glob("*.py"):
                apps.append(app_file.stem)
                self.app_paths[app_file.stem] = app_file.absolute()
            
            # Check for folders with main.py
            for folder in app_dir.iterdir():
                if folder.is_dir():
                    main_file = folder / "main.py"
                    if main_file.exists():
                        apps.append(folder.name)
                        self.app_paths[folder.name] = main_file.absolute()
        return apps
    
    def is_app_running(self, app: str) -> bool:
        lock = get_lock_path(app)
        return (app in self.processes and self.processes[app].is_alive()) or (app not in self.processes and lock.exists())

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
    def stop_app(self, app, timeout=PROCESS_STOP_TIMEOUT):
        if self.is_app_running(app):
            if app in self.processes:
                p = self.processes[app]
                os.killpg(p.pid, signal.SIGINT)                 # ② INT the whole group
                p.join(timeout)
                if p.is_alive():
                    for lock in get_owned_locks(app):
                        os.remove(lock)
                    p.terminate(); p.join(2)                    # escalate → TERM/KILL
                del self.processes[app]
        get_lock_path(app).unlink(missing_ok=True) # will trigger stop if running in another app manager
        return True

    def _write_lock(self, app: str):
        lock = get_lock_path(app)
        if not lock.exists():
            lock.touch()
        else:
            print(f"[app-manager] {app} is already running!")
            return False
        return True

    def _read_lock(self, app: str):
        lock = get_lock_path(app)
        return lock.exists()

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
            print(f"[dashboard] Starting ")
            proc.start()
            self._write_lock(app_name)
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
    
    def get_app_logs(self, app: str) -> str:
        log_file = Path(f"/tmp/app-{app}.log")
        owned_locks = get_owned_locks(app)
        output = ""
        for log in owned_locks.replace('_lock', '.log'):
            if log.exists():
                with open(log, "r") as f:
                    output += f.read()
        if not log_file.exists():
            return output
        with open(log_file, "r") as f:
            output += f.read()
        return output
    
    def get_status(self, exclude: List[str] = []) -> Dict:
        """Get complete status of all apps and lock files"""
        apps = self.get_available_apps()
        app_status = {}
        
        for app in apps:
            if app in exclude:
                continue
            if not get_lock_path(app).exists() and app in self.processes:
                print(f"[app-manager] Detected external delete of {app}_lock. Terminating.")
                self.stop_app(app)
            app_status[app] = {
                "running": self.is_app_running(app),
                "pid": self.processes[app].pid if app in self.processes and self.processes[app].is_alive() else None
            }
        
        return {
            "apps": app_status,
            "locks": self.get_lock_files_status()
        }

    def stop_all_apps(self):
        while self.processes:
            app = next(iter(self.processes))
            self.stop_app(app)
    
    def __del__(self):
        self.stop_all_apps()