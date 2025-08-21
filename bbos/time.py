import math, struct, time, ctypes
from pathlib import Path
from ctypes import c_long
import sys
WHOAMI = f"{Path(sys.modules['__main__'].__file__).parent.name}__{Path(sys.modules['__main__'].__file__).name[:-3]}"


class timespec(ctypes.Structure):
    _fields_ = [("tv_sec", c_long),
                ("tv_nsec", c_long)]
librt = ctypes.CDLL("librt.so.1", use_errno=True)
CLOCK_MONOTONIC = 1
def ns_sleep(ns: int):
    sec = ns // 1_000_000_000
    nsec = ns % 1_000_000_000
    ts = timespec(sec, nsec)
    librt.clock_nanosleep(CLOCK_MONOTONIC, 0, ctypes.byref(ts), None)

# https://github.com/commaai/openpilot/blob/master/common/util.py#L23
class MovingAverage:
    def __init__(self, window_size: int):
        self.window_size: int = window_size
        self.buffer: list[float] = [0.0] * window_size
        self.index: int = 0
        self.count: int = 0
        self.sum: float = 0.0
        self.sum_sq: float = 0.0

    def add(self, new_value: float):
        # Update the sum: subtract the value being replaced and add the new value
        old_value = self.buffer[self.index]
        self.sum -= old_value
        self.sum_sq -= old_value * old_value
        self.buffer[self.index] = new_value
        self.sum += new_value
        self.sum_sq += new_value * new_value
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

    def std(self) -> float:
        if self.count == 0:
            return float('nan')
        if self.count == 1:
            return 0.0
        mean = self.avg()
        variance = (self.sum_sq / self.count) - (mean * mean)
        return math.sqrt(max(0.0, variance))


class TimeLog:
    time_store = struct.Struct("<qq") # avg, std
    def __init__(self, name):
        from bbos.ipc import Status
        self._name = name
        self._buf = MovingAverage(5)
        self._last = -1
        self._status = Status(f"{name}__{WHOAMI}__timelog")
        print(f"[+] TimeLog: {name}__{WHOAMI}__timelog: {self._status._sock} -> {self._status._srv}", flush=True)
    def log(self):
        if self._last < 0:
            self._last = time.monotonic_ns()
        self._buf.add(float(time.monotonic_ns()-self._last))
        self._last = time.monotonic_ns()
        if self._buf.index == 0:
            self._status.update(self.time_store.pack(int(self._buf.avg()), int(self._buf.std())))
        return self._buf.avg()


class Loop:
    _latency = 100 # ms
    _last = -1
    _requested_ms = set()
    _triggers = {}
    _num_calls = 0
    _i = 0
    _manage_latency = True
    _lagging = False
    @staticmethod
    def keeptime():
        if Loop._i == Loop._num_calls - 1:
            Loop._i = 0 
            if Loop._last > 0:
                sleep_for = 1_000_000*Loop._latency - (time.monotonic_ns() - Loop._last)
                if sleep_for >= 0:
                    if Loop._manage_latency:
                        ns_sleep(sleep_for)
                else:
                    Loop._lagging = True
            Loop._last = time.monotonic_ns()
            for trigger, reset in Loop._triggers.values():
                trigger[0] = (trigger[0] + 1) % reset if not Loop._lagging else 0
        else:
            Loop._i += 1
    
    @staticmethod
    def init(trigger):
        Loop._num_calls += 1
        Loop._triggers[hex(id(trigger))] = [trigger,1]
        print(Loop._triggers)

    @staticmethod
    def manage_latency(value):
        assert isinstance(value, bool)
        Loop._manage_latency = value

    @staticmethod
    def set_ms(ms, trigger):
        assert ms > 0 and isinstance(ms, int)
        if not ms in Loop._requested_ms:
            Loop._requested_ms.add(ms)
            print(Loop._requested_ms)
            new_latency = math.gcd(*Loop._requested_ms)
            if len(Loop._requested_ms) != 1 and new_latency != Loop._latency:
                multiplier = Loop._latency // new_latency
                for t in Loop._triggers:
                    Loop._triggers[t][1] *= multiplier
                print(f"[+] Changed Loop._latency from {Loop._latency}ms to {new_latency}ms")
            Loop._latency = new_latency
        Loop._triggers[hex(id(trigger))] = [trigger, int(ms / Loop._latency)]
        print(f"[+] Loop._latency: {Loop._latency}ms")
        print(Loop._triggers)