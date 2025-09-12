import math, struct, time, ctypes
import ctypes.util  # <-- this is the missing piece
from pathlib import Path
from ctypes import c_long
import sys, os, errno
WHOAMI = f"{Path(sys.modules['__main__'].__file__).parent.name}__{Path(sys.modules['__main__'].__file__).name[:-3]}"


# --- C glue ---
class timespec(ctypes.Structure):
    _fields_ = [("tv_sec", ctypes.c_long),
                ("tv_nsec", ctypes.c_long)]

librt = ctypes.CDLL("librt.so.1", use_errno=True)   # libc.so.6 also works on new glibc
CLOCK_MONOTONIC = 1
TIMER_ABSTIME   = 1

librt.clock_nanosleep.argtypes = [
    ctypes.c_int, ctypes.c_int,
    ctypes.POINTER(timespec), ctypes.POINTER(timespec)
]
librt.clock_nanosleep.restype = ctypes.c_int

def sleep_until_ns(deadline_ns: int):
    """Sleep until absolute CLOCK_MONOTONIC time 'deadline_ns'."""
    ts = timespec(deadline_ns // 1_000_000_000,
                  deadline_ns %  1_000_000_000)
    while True:
        rc = librt.clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME,
                                   ctypes.byref(ts), None)
        if rc == 0:
            return
        e = ctypes.get_errno()
        if e == errno.EINTR:
            # Try again with the same absolute deadline
            continue
        raise OSError(e, os.strerror(e))


# https://github.com/commaai/openpilot/blob/master/common/util.py#L23
class MovingAverage:
    def __init__(self, window_size: int):
        self._window_size: int = window_size
        self._buffer: list[float] = [0.0] * window_size
        self._index: int = 0
        self._count: int = 0
        self._sum: float = 0.0
        self._sum_sq: float = 0.0
        self._max: float = 0.0

    def add(self, new_value: float):
        # Update the sum: subtract the value being replaced and add the new value
        old_value = self._buffer[self._index]
        self._sum -= old_value
        self._sum_sq -= old_value * old_value
        self._max = max(self._max, new_value)
        self._buffer[self._index] = new_value
        self._sum += new_value
        self._sum_sq += new_value * new_value
        # Update the index in a circular manner
        self._index = (self._index + 1) % self._window_size
        # Track the number of added values (for partial windows)
        self._count = min(self._count + 1, self._window_size)

    def last(self) -> float:
        return self._buffer[self._index]

    def is_reset(self) -> bool:
        return self._index == 0

    def avg(self) -> float:
        if self._count == 0:
            return float('nan')
        return self._sum / self._count

    def max(self) -> float:
        if self._count == 0:
            return float('nan')
        return self._max

    def std(self) -> float:
        if self._count == 0:
            return float('nan')
        if self._count == 1:
            return 0.0
        mean = self.avg()
        variance = (self._sum_sq / self._count) - (mean * mean)
        return math.sqrt(max(0.0, variance))


class TimeLog:
    time_store = struct.Struct("<qqq") # avg, std, max
    def __init__(self, name):
        from bbos.ipc import Status
        self._name = name
        self._buf = MovingAverage(10)
        self._last = -1
        self._status = Status(f"{name}__{WHOAMI}__timelog")
    def log(self):
        if self._last < 0:
            self._last = time.monotonic_ns()
        self._buf.add(float(time.monotonic_ns()-self._last))
        self._last = time.monotonic_ns()
        if self._buf.is_reset():
            self._status.update(self.time_store.pack(int(self._buf.avg()), int(self._buf.std()), int(self._buf.max())))


class SchedParam(ctypes.Structure):
    _fields_ = [("sched_priority", ctypes.c_int)]


class Loop:
    _period = 100 # ms
    _period_ns = 1_000_000*_period
    _requested_ms = set()
    _deadline_ns = -1
    _triggers = {}
    _num_calls = 0
    _i = 0
    _manage_period = True
    _lagging = False
    _init = False
    _realtime_enabled = False
    @staticmethod
    def keeptime():
        if Loop._i >= Loop._num_calls - 1:
            Loop._i = 0
            if Loop._deadline_ns < 0:
                Loop._deadline_ns = time.monotonic_ns() + Loop._period_ns
            # Sleep only if we're early
            now = time.monotonic_ns()
            if Loop._manage_period and now < Loop._deadline_ns:
                sleep_until_ns(Loop._deadline_ns)
                now = time.monotonic_ns()

            # Positive = late by this many ms (includes scheduler + Python overhead)
            diff_ms = (now - Loop._deadline_ns) * 1e-6
            # Update lag flag
            Loop._lagging = now > Loop._deadline_ns

            # Advance the absolute deadline by whole multiples to avoid drift
            if Loop._lagging:
                behind = now - Loop._deadline_ns
                skip = behind // Loop._period_ns + 1
                Loop._deadline_ns += skip * Loop._period_ns
            else:
                Loop._deadline_ns += Loop._period_ns

            # Tick triggers
            for trigger, reset in Loop._triggers.values():
                trigger[0] = (trigger[0] + 1) % reset if not Loop._lagging else 0
        else:
            Loop._i += 1
    
    @staticmethod
    def enable_realtime(priority: int, cores={4,5,6,7}):
        if not Loop._realtime_enabled:
            import os, grp
            # Get group IDs for this process
            gids = os.getgroups()
            # Resolve to names
            groups = [grp.getgrgid(g).gr_name for g in gids]
            print("Group IDs:", gids, flush=True)
            print("Groups:", groups, flush=True)

            # Show effective UID's primary group too
            primary_gid = os.getgid()
            print("Primary group:", grp.getgrgid(primary_gid).gr_name, flush=True)
            """Set FIFO scheduler, lock memory, and pin to RT cores."""
            SCHED_FIFO = 1
            MCL_CURRENT = 1
            MCL_FUTURE = 2
            # Scheduler
            print(f"[+] Setting realtime priority to {priority} on cores {cores}", flush=True)
            param = SchedParam(priority)
            libc = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
            if libc.sched_setscheduler(0, SCHED_FIFO, ctypes.byref(param)) != 0:
                raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
            # Affinity
            os.sched_setaffinity(0, cores)
            Loop._realtime_enabled = True
    
    @staticmethod
    def init(trigger):
        Loop._num_calls += 1
        Loop._triggers[hex(id(trigger))] = [trigger,1]
    
    @staticmethod
    def remove(trigger):
        Loop._num_calls -= 1
        Loop._triggers.pop(hex(id(trigger)))

    @staticmethod
    def manage_period(value):
        assert isinstance(value, bool)
        Loop._manage_period = value

    @staticmethod
    def set_ms(ms, trigger):
        assert ms > 0 and isinstance(ms, int)
        if not ms in Loop._requested_ms:
            Loop._requested_ms.add(ms)
            print(Loop._requested_ms)
            new_period = math.gcd(*Loop._requested_ms)
            if len(Loop._requested_ms) != 1 and new_period != Loop._period:
                multiplier = Loop._period // new_period
                for t in Loop._triggers:
                    Loop._triggers[t][1] *= multiplier
                print(f"[+] Changed Loop._period from {Loop._period}ms to {new_period}ms")
            Loop._period = new_period
            Loop._period_ns = 1_000_000*Loop._period
        Loop._triggers[hex(id(trigger))] = [trigger, int(ms / Loop._period)]
        print(f"[+] Loop._period: {Loop._period}ms")
        print(Loop._triggers)