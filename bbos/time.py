import struct, sys, os, time, numpy as np, asyncio
from pathlib import Path

# https://github.com/commaai/openpilot/blob/master/common/util.py#L23
class MovingAverage:
    def __init__(self, window_size: int):
        self.window_size: int = window_size
        self.buffer: list[float] = [0.0] * window_size
        self.index: int = 0
        self.count: int = 0
        self.sum: float = 0.0

    def add(self, new_value: float):
        # Update the sum: subtract the value being replaced and add the new value
        self.sum -= self.buffer[self.index]
        self.buffer[self.index] = new_value
        self.sum += new_value
        # Update the index in a circular manner
        self.index = (self.index + 1) % self.window_size
        # Track the number of added values (for partial windows)
        self.count = min(self.count + 1, self.window_size)

    def last(self) -> float:
        return self.buffer[self.index]

    def avg(self) -> float:
        if self.count == 0:
            return float('nan')
        return self.sum / self.count

time_store = struct.Struct("<q")

def _get_lockfile(name):
    pth = f"{Path(sys.modules['__main__'].__file__).parent.name}_{Path(sys.modules['__main__'].__file__).name[:-3]}"
    return f"/tmp{name}_{pth}_time_lock"

class TimeLog:
    def __init__(self, name):
        self._name = name
        self._buf = MovingAverage(50)
        self._f = os.open(_get_lockfile(name),
             os.O_WRONLY | os.O_CREAT | os.O_DSYNC,
             0o444)
        self._last = -1
    def log(self):
        if self._last < 0:
            self._last = time.monotonic()
        self._buf.add(time.monotonic()-self._last)
        self._last = time.monotonic()
        if self._buf.index == 0:
            os.pwrite(self._f, time_store.pack(int(self._buf.avg()*1e9)), 0)
        return self._buf.avg()

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
    _latency = 0.5
    _last = -1
    _num_calls = 0
    _i = 0
    @staticmethod
    def keeptime():
        if Loop._i == 0:
            Loop._i = (Loop._i + 1) % Loop._num_calls
            if Loop._last < 0:
                Loop._last = time.monotonic()
                return
            now = time.monotonic()
            sleep_for = Loop._latency - (now - Loop._last)
            Loop._last = now
            if sleep_for > 0:
                time.sleep(sleep_for)
        else:
            Loop._i = (Loop._i + 1) % Loop._num_calls

    @staticmethod
    def set_hz(hz):
        Loop._num_calls += 1
        Loop._latency = min(Loop._latency, 1./hz)

class Realtime:
    pri = 20
    @staticmethod
    def set_realtime(cores, priority):
        if priority > Realtime.pri:
            print(f"[+] Setting realtime priority to {priority} and cores to {cores}")
            os.sched_setaffinity(0, cores)
            os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(priority))
            Realtime.pri = priority