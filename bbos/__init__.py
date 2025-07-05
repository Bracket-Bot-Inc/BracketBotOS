import importlib.util, sys
from pathlib import Path


def _ignite_daemon_constants():
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
            spec.loader.exec_module(module)  # ⟵ runs @register decorators


_ignite_daemon_constants()
