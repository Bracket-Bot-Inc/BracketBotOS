import time, traceback, ctypes, posix_ipc, mmap, numpy as np

CACHE_LINE = 64


class Writer:

    def __init__(self, name, shmtype):
        shmdtype = np.dtype(shmtype() + [("timestamp", np.float64)])
        size = shmdtype.itemsize + CACHE_LINE
        self._shm = posix_ipc.SharedMemory(name,
                                           flags=posix_ipc.O_CREAT,
                                           mode=0o600,
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

    def __setitem__(self, idx, data):
        self._seq.value += 1  # odd → readers ignore
        self._buf[0][idx] = data
        self._buf[0]['timestamp'] = time.monotonic()
        self._seq.value += 1  # even → publish

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_val, exc_tb)
        self._shm.unlink()
        return True


class Reader:

    def __init__(self, name, shmtype):
        shmdtype = np.dtype(shmtype() + [("timestamp", np.float64)])
        size = shmdtype.itemsize + CACHE_LINE
        self._shm = posix_ipc.SharedMemory(name)
        self._mapfile = mmap.mmap(self._shm.fd, size, mmap.MAP_SHARED,
                                  mmap.PROT_READ)
        self._seq = memoryview(self._mapfile)[:4].cast('I')
        self._buf = np.ndarray(1,
                               dtype=shmdtype,
                               buffer=memoryview(self._mapfile)[CACHE_LINE:])
        self._data = np.zeros_like(self._buf)[0]
        self._shm.close_fd()

    def __enter__(self):
        return self

    def get(self):
        while self._seq[0] & 1:  # writer busy
            time.sleep(0)  # spin
        s1 = self._seq[0]
        data = self._buf[0]
        stale = data['timestamp'] == self._data['timestamp']
        if s1 == self._seq[0]:  # unchanged → valid
            self._data = data.copy()
        return stale, self._data

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            traceback.print_exception(exc_type, exc_val, exc_tb)
        return False
