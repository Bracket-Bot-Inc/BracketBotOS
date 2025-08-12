import importlib.util, sys
from pathlib import Path

# PEP 562
_symbols = {
    "Type": "bbos.registry",
    "Config": "bbos.registry",
    "register": "bbos.registry",
    "realtime": "bbos.registry",
    "Writer": "bbos.ipc",
    "Reader": "bbos.ipc",
    "AppManager": "bbos.app_manager",
}

_collected = False
def __getattr__(name):
    global _collected
    if name in _symbols:
        if name in ("Config", "Type") and not _collected:
            _collect_daemon_constants()
            _collected = True
        mod = importlib.import_module(_symbols[name])
        val = getattr(mod, name)
        globals()[name] = val  # cache for next time
        return val
    raise AttributeError(f"module 'bbos' has no attribute '{name}'")

def _collect_daemon_constants():
    """Import every daemons/<name>/constants.py once."""
    base = Path(__file__).parent / "daemons"
    if not base.is_dir():
        return
    for sub in base.iterdir():
        const = sub / "constants.py"
        if const.is_file():
            mod_name = f"{__name__}.daemons.{sub.name}.constants"
            if mod_name in sys.modules:  # idempotent
                continue
            spec = importlib.util.spec_from_file_location(mod_name, const)
            module = importlib.util.module_from_spec(spec)
            sys.modules[
                mod_name] = module  # register before exec to avoid recursion
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                print(f"[!] Error loading {mod_name}: {e}")