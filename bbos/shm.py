from typing import List
from bbos.registry import Type 
from bbos.time import TimeLog, Loop, Realtime
from bbos.os_utils import CACHE_LINE

import os, json, inspect, contextlib, sys, traceback, ctypes, posix_ipc, mmap, numpy as np, time
from pathlib import Path

def _get_lockfile(name):
    return f"/tmp{name}_lock"
def _caller_sig():
    f = inspect.stack()[2]
    return f"{os.path.abspath(f.filename)}:{f.lineno}"


def _write_lock(fd, sig, dtype, rate, priority, cores):
    owner = Path(sys.modules['__main__'].__file__)
    owner = owner.parent.name + '/' + owner.name # TODO: assumes name of app or daemon filename or directory of file
    os.write(fd, json.dumps({"caller": sig, "dtype": dtype.descr, "rate": rate, "owner": owner, "priority": priority, "cores": cores}).encode())


def json_descr_to_dtype(desc):
    """
    Convert dtype.descr that came through JSON back to a NumPy dtype.
    • Converts inner list shapes ([2]) → tuples (2,)
    • Converts bare ints (2)         → tuples (2,)
    """
    fixed = []
    for field in desc:
        if len(field) == 3:  # (name, dtype, shape)
            name, dt, shape = field
            if isinstance(shape, list):
                shape = tuple(shape)
            elif isinstance(shape, int):
                shape = (shape, )
            fixed.append((name, dt, shape))
        else:  # (name, dtype)
            fixed.append(tuple(field))
    return np.dtype(fixed)


class Writer:
    def __init__(self, name, datatype: Type | List[tuple]):
        shmtype, rate, (priority, cores) = datatype if isinstance(datatype, tuple) else datatype()
        Loop.set_hz(rate)
        Realtime.set_realtime(cores, priority)
        shmdtype = np.dtype(shmtype)
        size = shmdtype.itemsize + CACHE_LINE
        self._lockfile = _get_lockfile(name)
        sig = _caller_sig()
        try:
            self._lock_fd = os.open(self._lockfile,
                                    os.O_CREAT | os.O_EXCL | os.O_RDWR)
            _write_lock(self._lock_fd, sig, shmdtype, rate, priority, cores)
        except FileExistsError:
            raise RuntimeError(
                f"Writer for '{name}' exists, {self._lockfile})")
        self._shm = posix_ipc.SharedMemory(
            name,
            flags=posix_ipc.O_CREAT,
            mode=0o644,  # owner rw--, group r--, others r--
            size=size)
        self._mapfile = mmap.mmap(self._shm.fd, size, mmap.MAP_SHARED,
                                  mmap.PROT_READ | mmap.PROT_WRITE)
        self._seq = ctypes.c_uint32.from_buffer(self._mapfile, 0)
        self._buf = np.ndarray(1,
                               dtype=shmdtype,
                               buffer=memoryview(self._mapfile)[CACHE_LINE:])
        self._shm.close_fd()

    def __enter__(self):
        return self

    @contextlib.contextmanager
    def buf(self):
        self._seq.value += 1  # mark as dirty (odd)
        self._buf[0]['timestamp'] = time.monotonic_ns()
        try:
            yield self._buf[0]
        finally:
            self._seq.value += 1  # mark as published (even)

    def __setitem__(self, idx, data):
        self._seq.value += 1  # odd → readers ignore
        self._buf[0][idx] = data
        self._buf[0]['timestamp'] = time.monotonic_ns()
        self._seq.value += 1  # even → publish

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_val, exc_tb)
        self._shm.unlink()
        os.close(self._lock_fd)
        os.unlink(self._lockfile)
        return True


class Reader:
    def __init__(self, name):
        self._name = name
        self._lockfile = _get_lockfile(name)
        self._lock_fd = None
        self._readable = False
        self._valid = False
        self._tlog = TimeLog(name)
        self._data = None

    def __enter__(self):
        return self

    def ready(self):
        if not os.path.exists(self._lockfile):
            self._readable = False
            return self._readable
        # wait until the writer has created the lock-file
        if not self._readable:
            try:
                with open(self._lockfile, 'r') as f:
                    lock = json.load(f)
                    shmdtype = np.dtype(json_descr_to_dtype(lock["dtype"]))
                    Loop.set_hz(lock["rate"])
                    Realtime.set_realtime(lock["cores"], lock["priority"])
            except:
                self._readable = False
                return self._readable
            self._readable = True
            size = shmdtype.itemsize + CACHE_LINE
            self._shm = posix_ipc.SharedMemory(self._name)
            self._mapfile = mmap.mmap(self._shm.fd, size, mmap.MAP_SHARED,
                                    mmap.PROT_READ)
            self._seq = memoryview(self._mapfile)[:4].cast('I')
            self._buf = np.ndarray(1,
                                dtype=shmdtype,
                                buffer=memoryview(self._mapfile)[CACHE_LINE:])
            self._data = np.zeros_like(self._buf)[0]
            self._shm.close_fd()

        if not self._seq[0] & 1:
            s0 = self._seq[0]
            self._valid = self._buf[0]['timestamp'] != self._data['timestamp']
            for n in self._data.dtype.names:
                self._data[n] = self._buf[0][n]
            if s0 != self._seq[0]:
                self._valid = False
            if self._valid:
                self._tlog.log()
        return self._readable and self._valid

    @property
    def data(self):
        return self._data

    @property
    def readable(self):
        return self._readable

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_val, exc_tb)
        if self._lock_fd:
            os.unlink(self._lockfile)
        self._tlog.close()
        return True