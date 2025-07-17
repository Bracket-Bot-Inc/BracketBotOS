import gc, os, re, platform, subprocess

_system = platform.system()
_machine = platform.machine()

if _system == "Windows":
    CACHE_LINE = 64  # All modern Windows PCs (x86-64, ARM64)
elif _system == "Darwin":
    CACHE_LINE = 128 if _machine == "arm64" else 64  # Apple Silicon vs Intel Mac
elif _system == "Linux":
    CACHE_LINE = 64  # Most Linux systems (x86-64, ARM64)
else:
    CACHE_LINE = 64  # Fallback default
try:
    IS_BB = 'raspberry pi' in open(
        '/sys/firmware/devicetree/model').read().lower()
except Exception:
    IS_BB = False


# Portions Copyright (c) 2018, Comma.ai, Inc.
# Licensed under the MIT License.
class Priority:
    # CORE 2
    # - modeld = 55
    # - camerad = 54
    CTRL_LOW = 51  # plannerd & radard

    # CORE 3
    # - pandad = 55
    CTRL_HIGH = 53


def set_core_affinity(cores: list[int]) -> None:
    if _system == 'Linux' and IS_BB:
        os.sched_setaffinity(0, cores)


def config_realtime_process(cores: int | list[int], priority: int) -> None:
    gc.disable()
    if _system == 'Linux' and IS_BB:
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(priority))
    c = cores if isinstance(cores, list) else [
        cores,
    ]
    set_core_affinity(c)


def user_ip() -> str:
    """Return the first remote IP shown by `who`."""
    out = subprocess.check_output(['who'], text=True)
    return re.search(r'\(([\d.]+)\)', out).group(1)


def gateway() -> str:
    """Return the default gateway for wlan0-ap."""
    out = subprocess.check_output(['ip', 'route', 'show', 'dev', 'wlan0-ap'],
                                  text=True)
    match = re.search(r'src ([\d.]+)', out)
    if match:
        return match.group(1)
    raise RuntimeError("No gateway found for wlan0-ap.")
