from typing import List, Set
from bbos.registry import Type 
from bbos.time import TimeLog, Loop

import os, json, inspect, contextlib, sys, traceback, ctypes, posix_ipc, atexit, mmap, time, selectors, socket
import numpy as np
from pathlib import Path

CACHE_LINE = 64

def is_socket_closed(sock: socket.socket) -> bool:
    try:
        # this will try to read bytes without blocking and also without removing them from buffer (peek only)
        data = sock.recv(16, socket.MSG_DONTWAIT | socket.MSG_PEEK)
        if len(data) == 0:
            return True
    except BlockingIOError:
        return False  # socket is open and reading from it would block
    except ConnectionResetError:
        return True  # socket was closed for some other reason
    except Exception as e:
        logger.exception("unexpected exception when checking if a socket is closed")
        return False
    return False

class Status:
    PAYLOAD_SIZE = 4096
    def __init__(self, name: str, data: bytes = None):
        self._sock = self.name2socket(name)
        self._data = data
        self._srv = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
        try:
            self._srv.bind(self._sock)
        except OSError as e:
            res = self._srv.connect_ex(self._sock)
            self._srv.settimeout(0.1)
            if res == 0:
                try:
                    data = self._srv.recv(1024)
                    details = json.loads(data)
                    print(f"Writer for {name} already exists @ {details['caller']}", flush=True)
                except socket.timeout:
                    pass
            self._srv.close()
            sys.exit(1)
        self._srv.listen()
        self._srv.setblocking(False)
        self._sel = selectors.DefaultSelector()
        self._sel.register(self._srv, selectors.EVENT_READ)
        self._clients = set()
    @staticmethod
    def name2socket(name):
        return f"\0{name}.bbos"
    def update(self, data=None):
        if data is None:
            data = self._data
            assert data is not None, "No data to update!"
        try:
            for key, _ in self._sel.select(timeout=0):
                if key.fileobj is self._srv:
                    c, _ = self._srv.accept()
                    c.sendall(data)
                    c.setblocking(False)
                    self._clients.add(c)
            remove = set() 
            for c in self._clients:
                try:
                    if not c.recv(1, socket.MSG_DONTWAIT):
                        remove.add(c)
                except BlockingIOError:
                    pass
                except OSError:
                    remove.add(c)
            self._clients -= remove
        except Exception as e:
            print(e)
    def close(self):
        self._srv.close()
        self._sel.close()
        for c in self._clients:
            c.close()
        self._clients.clear()

def _caller_signature():
    f = inspect.stack()[2]
    return f"{os.path.abspath(f.filename)}:{f.lineno}"

def _encode_lock(sig, dtype, period):
    owner = Path(sys.modules['__main__'].__file__)
    owner = owner.parent.name + '/' + owner.name # TODO: assumes name of app or daemon filename or directory of file
    return json.dumps({"caller": sig, "dtype": dtype.descr, "period": period, "owner": owner}).encode()


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
    def __init__(self, name, datatype: Type | List[tuple], keeptime=True):
        shmtype, period = datatype if isinstance(datatype, tuple) else datatype()
        shmdtype = np.dtype(shmtype)
        size = shmdtype.itemsize + CACHE_LINE
        sig = _caller_signature()
        self._lock: bytes = _encode_lock(sig, shmdtype, period)
        assert len(self._lock) <= Status.PAYLOAD_SIZE, "Lock is too large! Increase PAYLOAD_SIZE or reconfigure your Type"
        self._status = Status(name, self._lock)

        self._keeptime = keeptime
        if keeptime:
            # set loop trigger
            self._trigger = [0] # mutable counter
            Loop.init(self._trigger)
            Loop.set_ms(period, self._trigger)

        # create shared memory
        self._shm = posix_ipc.SharedMemory(
            name,
            flags=posix_ipc.O_CREAT,
            mode=0o644,  # owner rw--, group r--, others r--
            size=size)
        self._mapfile = mmap.mmap(self._shm.fd, size, mmap.MAP_SHARED,
                                  mmap.PROT_READ | mmap.PROT_WRITE)
        self._mapfile.write(b'\x00' * shmdtype.itemsize)
        self._mapfile.flush()
        self._seq = ctypes.c_uint32.from_buffer(self._mapfile, 0)
        self._seq.value = 0
        self._buf = np.ndarray(1,
                               dtype=shmdtype,
                               buffer=memoryview(self._mapfile)[CACHE_LINE:])
        self._shm.close_fd()

    def __enter__(self):
        return self

    def _update(self):
        if self._keeptime:
            return self._trigger[0] == 0
        else:
            return True

    @contextlib.contextmanager
    def buf(self):
        self._status.update()
        self._seq.value += 1  # mark as dirty (odd)
        try:
            if self._update():
                self._buf[0]['timestamp'] = np.datetime64(time.time_ns(), 'ns')
            yield self._buf[0] if self._update() else np.zeros_like(self._buf[0])
        finally:
            self._seq.value += 1  # mark as published (even)
        if self._keeptime:
            Loop.keeptime()

    def __setitem__(self, idx, data):
        self._status.update()
        if self._update():
            self._seq.value += 1  # odd → readers ignore
            self._buf[0]['timestamp'] = np.datetime64(time.time_ns(), 'ns') 
            self._buf[0][idx] = data
            self._seq.value += 1  # even → publish
        if self._keeptime:
            Loop.keeptime()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_val, exc_tb)
        try:
            self._shm.unlink()
            self._status.close()
        except:
            pass
        return True


class Reader:
    def __init__(self, name, keeptime=True):
        self._name = name
        self._readable = False
        self._valid = False
        self._tlog = TimeLog(name)
        self._data = None
        self._keeptime = keeptime
        if keeptime:
            self._trigger = [0] # mutable counter
            Loop.init(self._trigger)
        self._writer_lock = None
        self._s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)

    def __enter__(self):
        return self

    def _update(self):
        if self._keeptime:
            return self._trigger[0] == 0
        else:
            return True

    def ready(self):
        if not self._readable or is_socket_closed(self._s): # enters when writer is closed
            self._s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
            res = self._s.connect_ex(Status.name2socket(self._name))
            if res == 0:
                try: # antipattern: remove all these try catches
                    self._writer_lock = self._s.recv(Status.PAYLOAD_SIZE)
                except OSError as e:
                    self._readable = False
                    if self._keeptime:
                        Loop.keeptime()
                    return self._readable
            else:
                self._readable = False
                if self._keeptime:
                    Loop.keeptime()
                return self._readable
            try:
                lock = json.loads(self._writer_lock)
                shmdtype = np.dtype(json_descr_to_dtype(lock["dtype"]))
                if self._keeptime:
                    self._trigger[0] = 0
                    Loop.set_ms(lock["period"], self._trigger)
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
            except Exception as e:
                self._readable = False
                if self._keeptime:
                    Loop.keeptime()
                return self._readable
        data = self._read()
        stale = data['timestamp'] == self._data['timestamp']
        self._data = data
        if not stale:
            self._tlog.log()
        if self._keeptime:
            Loop.keeptime()
        return not stale

    def _read(self):
        """Guarantees a good read"""
        while True:
            s0 = self._seq[0]
            if s0 & 1:          # writer busy → spin
                time.sleep(0)
                continue
            s1 = self._seq[0]   # re‑read before copy
            if s1 != s0:        # writer slipped in
                continue
            data = self._buf[0].copy()
            if self._seq[0] == s0:       # still identical & even → success
                return data

    @property
    def data(self):
        return self._data

    @property
    def readable(self):
        return self._readable

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_val, exc_tb)
        self._s.close()
        return True