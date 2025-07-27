import struct, sys, os, time, numpy as np, asyncio
from pathlib import Path

time_store = struct.Struct("<q")

def _get_lockfile(name):
    return f"/tmp{name}_{Path(sys.modules['__main__'].__file__).name[:-3]}_time_lock"

class TimeLog:

    def __init__(self, name, blen=2**4):
        self._name = name
        self._blen = blen
        self._buf = np.zeros(blen, dtype=np.int64)
        self._i = 0
        self._f = os.open(_get_lockfile(name),
             os.O_WRONLY | os.O_CREAT | os.O_DSYNC,
             0o444)

    def log(self):
        self._buf[self._i] = time.monotonic_ns()
        self._i = (self._i + 1) % self._blen
        if self._i == 0:
           latency_ns = np.diff(self._buf[range(self._i - self._blen + 1, self._i)]).max()   # cast to int
           os.pwrite(self._f, time_store.pack(latency_ns), 0)
        return self._buf[self._i]

    def close(self):
        os.unlink(_get_lockfile(self._name))

class TimeRead: 
    def __init__(self, name):
        self._f = os.open(_get_lockfile(name), os.O_RDONLY)
        self._latency = 0

    def ready(self):
        raw = os.pread(self._f, 8, 0)
        if raw:
            self._latency = time_store.unpack(raw)[0] * 1e-9
            return True
        else:
            return False

    def latency(self):
        return self._latency

    def close(self):
        os.close(self._f)
    
class Loop:
    latency = 0.5
    @staticmethod
    def sleep():
        if sys._getframe(1).f_code.co_flags & 0x380:
            return asyncio.sleep(Loop.latency)
        else:
            time.sleep(Loop.latency)
        return True

    @staticmethod
    def set_hz(hz):
        Loop.latency = min(Loop.latency, 1/hz) if Loop.latency is not None else 1/hz

class Realtime:
    pri = 20
    @staticmethod
    def set_realtime(cores, priority):
        if priority > Realtime.pri:
            print(f"[+] Setting realtime priority to {priority} and cores to {cores}")
            os.sched_setaffinity(0, cores)
            os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(priority))
            Realtime.pri = priority