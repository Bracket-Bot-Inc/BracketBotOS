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
        if x.ndim == 2 and x.shape[0] == 1:
            x = x.squeeze()
        return self.f(x)  # f itself handles (3,) or (N,3)
    def inv(self):
        return Operator(self.f_inv, self.f)
    
    def quat(self):
        """Extract the rotation quaternion from the transformation."""
        # Apply the operator to standard basis vectors to get rotation matrix
        e1 = self.f(np.array([1., 0., 0.]))
        e2 = self.f(np.array([0., 1., 0.]))
        e3 = self.f(np.array([0., 0., 1.]))
        
        # Get origin translation
        origin = self.f(np.array([0., 0., 0.]))
        
        # Remove translation component to get pure rotation
        R = np.column_stack([e1 - origin, e2 - origin, e3 - origin])
        
        # Convert rotation matrix to quaternion using standard formula
        trace = np.trace(R)
        
        if trace > 0:
            s = 0.5 / np.sqrt(trace + 1.0)
            w = 0.25 / s
            x = (R[2, 1] - R[1, 2]) * s
            y = (R[0, 2] - R[2, 0]) * s
            z = (R[1, 0] - R[0, 1]) * s
        elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
            s = 2.0 * np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2])
            w = (R[2, 1] - R[1, 2]) / s
            x = 0.25 * s
            y = (R[0, 1] + R[1, 0]) / s
            z = (R[0, 2] + R[2, 0]) / s
        elif R[1, 1] > R[2, 2]:
            s = 2.0 * np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2])
            w = (R[0, 2] - R[2, 0]) / s
            x = (R[0, 1] + R[1, 0]) / s
            y = 0.25 * s
            z = (R[1, 2] + R[2, 1]) / s
        else:
            s = 2.0 * np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1])
            w = (R[1, 0] - R[0, 1]) / s
            x = (R[0, 2] + R[2, 0]) / s
            y = (R[1, 2] + R[2, 1]) / s
            z = 0.25 * s
        
        return np.array([x, y, z, w])
    
    def pos(self):
        """Get the final position after applying transformation to origin."""
        return self([0., 0., 0.])

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

def rmat(R):
    """
    Rotation operator from a 3x3 rotation matrix.
    """
    R = np.asarray(R, dtype=float)
    if R.shape != (3, 3):
        raise ValueError("Rotation matrix must be shape (3, 3)")
    R_inv = R.T
    
    def f(x):
        x = np.asarray(x, dtype=float)
        if x.ndim == 1:
            return R @ x
        elif x.ndim == 2 and x.shape[1] == 3:
            return (R @ x.T).T
        else:
            raise ValueError("Input must be shape (3,) or (N,3)")
    
    def f_inv(x):
        x = np.asarray(x, dtype=float)
        if x.ndim == 1:
            return R_inv @ x
        elif x.ndim == 2 and x.shape[1] == 3:
            return (R_inv @ x.T).T
        else:
            raise ValueError("Input must be shape (3,) or (N,3)")
    
    return Operator(f, f_inv)