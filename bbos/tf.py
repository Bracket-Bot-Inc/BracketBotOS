import numpy as np

class Operator:
    def __init__(self, f, f_inv):
        self.f = f
        self.f_inv = f_inv
    def __matmul__(self, other):
        fwd = lambda x: self.f(other.f(x))
        inv = lambda x: other.f_inv(self.f_inv(x))
        return Operator(fwd, inv)
    def __call__(self, x):
        x = np.asarray(x, dtype=float)
        return self.f(x)  # f itself handles (3,) or (N,3)
    def inv(self):
        return Operator(self.f_inv, self.f)

def trans(t):
    t = np.asarray(t, dtype=float)
    def f(x):
        return x + t
    def f_inv(x):
        return x - t
    return Operator(f, f_inv)

def rot(axis, angle_deg):
    """
    Rotation operator around `axis` by `angle_deg` degrees.
    Right-hand rule: positive angle = CCW when looking along +axis.
    """
    a = np.asarray(axis, dtype=float)
    a /= np.linalg.norm(a)
    θ = np.deg2rad(angle_deg)
    c, s = np.cos(θ), np.sin(θ)

    def f(x):
        x = np.asarray(x, dtype=float)
        # handle both single vector (3,) and batch (N,3)
        if x.ndim == 1:
            return x*c + np.cross(a, x)*s + a*np.dot(a, x)*(1-c)
        elif x.ndim == 2 and x.shape[1] == 3:
            return x*c + np.cross(np.broadcast_to(a, x.shape), x)*s + np.outer(np.dot(x, a), a)*(1-c)
        else:
            raise ValueError("Input must be shape (3,) or (N,3)")
    
    def f_inv(x):
        x = np.asarray(x, dtype=float)
        if x.ndim == 1:
            return x*c - np.cross(a, x)*s + a*np.dot(a, x)*(1-c)
        elif x.ndim == 2 and x.shape[1] == 3:
            return x*c - np.cross(np.broadcast_to(a, x.shape), x)*s + np.outer(np.dot(x, a), a)*(1-c)
        else:
            raise ValueError("Input must be shape (3,) or (N,3)")
    
    return Operator(f, f_inv)