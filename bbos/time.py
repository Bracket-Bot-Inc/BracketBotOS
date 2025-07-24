import time, numpy as np

class Time:

    def __init__(self, hz, blen=10):
        self._blen = blen
        self._buf = np.zeros(blen, dtype=np.float64)
        self._i = 0
        self._interval = 1 / hz
        self._stats = {"max": -np.inf, "min": np.inf}

    def tick(self, block=True):
        delay = self._buf[self._i - 1] + self._interval - time.monotonic()
        if (delay > 0):
            if block:
                time.sleep(delay)
            else:
                return False
        self._buf[self._i] = time.monotonic()
        self._i = (self._i + 1) % self._blen
        if self._i == 0:
            self._stats['min'] = min(self.hz, self._stats['min'])
            self._stats['max'] = max(self.hz, self._stats['max'])
        return True

    @staticmethod
    def now():
        return time.monotonic()

    @property
    def hz(self):
        return 1 / np.mean(
            np.diff(self._buf[range(self._i - self._blen + 1, self._i)]))

    @property
    def stats(self):
        """OS jitter waaaa"""
        return self._stats
