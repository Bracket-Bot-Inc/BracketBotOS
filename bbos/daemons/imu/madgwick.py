"""
Madgwick AHRS algorithm implementation for orientation estimation.
Based on: https://www.x-io.co.uk/open-source-imu-and-ahrs-algorithms/
"""
import numpy as np


class Quaternion:
    """Quaternion class for orientation representation."""
    
    def __init__(self, q=None):
        if q is None:
            self.q = np.array([1.0, 0.0, 0.0, 0.0])
        else:
            self.q = np.array(q)
    
    @property
    def w(self):
        return self.q[0]
    
    @property
    def x(self):
        return self.q[1]
    
    @property
    def y(self):
        return self.q[2]
    
    @property
    def z(self):
        return self.q[3]
    
    def conj(self):
        """Quaternion conjugate."""
        return Quaternion([self.w, -self.x, -self.y, -self.z])
    
    def __mul__(self, other):
        """Quaternion multiplication."""
        if isinstance(other, Quaternion):
            w1, x1, y1, z1 = self.q
            w2, x2, y2, z2 = other.q
            return Quaternion([
                w1*w2 - x1*x2 - y1*y2 - z1*z2,
                w1*x2 + x1*w2 + y1*z2 - z1*y2,
                w1*y2 - x1*z2 + y1*w2 + z1*x2,
                w1*z2 + x1*y2 - y1*x2 + z1*w2
            ])
        else:
            return Quaternion(self.q * other)
    
    def normalize(self):
        """Normalize quaternion."""
        norm = np.linalg.norm(self.q)
        if norm > 0:
            self.q = self.q / norm
    
    @staticmethod
    def from_angle_axis(angle, x, y, z):
        """Create quaternion from angle-axis representation."""
        half_angle = angle / 2
        s = np.sin(half_angle)
        return Quaternion([np.cos(half_angle), x*s, y*s, z*s])
    
    def to_euler_angles(self):
        """Convert quaternion to Euler angles (roll, pitch, yaw)."""
        w, x, y, z = self.q
        
        # Roll (x-axis rotation)
        sinr_cosp = 2 * (w * x + y * z)
        cosr_cosp = 1 - 2 * (x * x + y * y)
        roll = np.arctan2(sinr_cosp, cosr_cosp)
        
        # Pitch (y-axis rotation)
        sinp = 2 * (w * y - z * x)
        if abs(sinp) >= 1:
            pitch = np.copysign(np.pi / 2, sinp)
        else:
            pitch = np.arcsin(sinp)
        
        # Yaw (z-axis rotation)
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = np.arctan2(siny_cosp, cosy_cosp)
        
        return roll, pitch, yaw


class MadgwickAHRS:
    """Madgwick AHRS algorithm implementation."""
    
    def __init__(self, samplePeriod=0.01, beta=0.008, zeta=0.0):
        """
        Initialize the filter.
        
        Args:
            samplePeriod: Sample period in seconds
            beta: Algorithm gain (typical: 0.008 to 0.048)
            zeta: Gyroscope bias drift compensation gain
        """
        self.samplePeriod = samplePeriod
        self.beta = beta
        self.zeta = zeta
        self.quaternion = Quaternion()
        self.gyro_bias = np.zeros(3)
    
    def update_imu(self, gyro, accel):
        """
        Update orientation estimate using IMU data.
        
        Args:
            gyro: Gyroscope data in rad/s [x, y, z]
            accel: Accelerometer data in any unit [x, y, z]
        """
        q = self.quaternion.q
        
        # Normalize accelerometer measurement
        if np.linalg.norm(accel) == 0:
            return
        accel = accel / np.linalg.norm(accel)
        
        # Gradient descent algorithm corrective step
        f = np.array([
            2*(q[1]*q[3] - q[0]*q[2]) - accel[0],
            2*(q[0]*q[1] + q[2]*q[3]) - accel[1],
            2*(0.5 - q[1]**2 - q[2]**2) - accel[2]
        ])
        
        J = np.array([
            [-2*q[2], 2*q[3], -2*q[0], 2*q[1]],
            [2*q[1], 2*q[0], 2*q[3], 2*q[2]],
            [0, -4*q[1], -4*q[2], 0]
        ])
        
        step = J.T @ f
        step = step / np.linalg.norm(step)
        
        # Apply feedback step
        gyro_corrected = gyro - self.gyro_bias
        
        # Compute rate of change of quaternion
        qDot = 0.5 * self._quat_multiply(q, [0, gyro_corrected[0], gyro_corrected[1], gyro_corrected[2]])
        
        # Apply correction
        qDot -= self.beta * step
        
        # Integrate to yield quaternion
        q += qDot * self.samplePeriod
        self.quaternion.q = q / np.linalg.norm(q)
        
        # Compute gyro bias correction (if zeta > 0)
        if self.zeta > 0:
            # Extract vector part of step quaternion and convert to gyro bias correction
            step_vector = np.array([step[1], step[2], step[3]])
            self.gyro_bias += 2 * self.zeta * step_vector * self.samplePeriod
    
    def _quat_multiply(self, q, r):
        """Quaternion multiplication helper."""
        if len(r) == 3:
            r = np.concatenate(([0], r))
        
        return np.array([
            q[0]*r[0] - q[1]*r[1] - q[2]*r[2] - q[3]*r[3],
            q[0]*r[1] + q[1]*r[0] + q[2]*r[3] - q[3]*r[2],
            q[0]*r[2] - q[1]*r[3] + q[2]*r[0] + q[3]*r[1],
            q[0]*r[3] + q[1]*r[2] - q[2]*r[1] + q[3]*r[0]
        ]) 