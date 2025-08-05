import numpy as np

class RingBuf:
    """Compact fixed-size NumPy ring buffer (single writer/reader, single thread)."""
    def __init__(self, cap, *, dtype=np.float32):
        self.a = np.empty(cap, dtype)   # storage
        self.cap = cap                  # capacity
        self.tail = 0                   # index of oldest element
        self.len  = 0                   # number of valid items

    # ---------- writer ----------
    def push(self, data):
        x = np.asarray(data, self.a.dtype).ravel()
        n = x.size
        if n >= self.cap:                       # keep newest cap samples
            self.a[:] = x[-self.cap:]
            self.tail = 0; self.len = self.cap
            return
        head = (self.tail + self.len) % self.cap
        k = min(n, self.cap - head)            # contiguous part before wrap
        self.a[head:head+k] = x[:k]
        if n > k: self.a[0:n-k] = x[k:]        # wrapped part
        over = (self.len + n) - self.cap       # bytes that overwrite old data
        if over > 0:
            self.tail = (self.tail + over) % self.cap
            self.len  = self.cap
        else:
            self.len += n

    # ---------- reader ----------
    def pop(self, n):
        n = min(n, self.len)
        k = min(n, self.cap - self.tail)
        out = np.empty(n, self.a.dtype)
        out[:k]      = self.a[self.tail:self.tail+k]
        if n > k: out[k:] = self.a[0:n-k]       # wrapped part
        self.tail = (self.tail + n) % self.cap
        self.len  -= n
        return out