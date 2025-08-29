from bbos.registry import *
import numpy as np


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class imu:
    i2c_bus: int = 1  # I2C bus number (0 or 1)
    i2c_address: int = 0x69  # ICM42688P default I2C address
    accel_range: int = 4  # Accelerometer range in g (2, 4, 8, 16)
    sample_rate: int = 100  # Sample rate in Hz
    gyro_range: int = 2000  # Gyroscope range in dps (250, 500, 1000, 2000)
    enable_temperature: bool = True  # Enable temperature sensor
    enable_filter: bool = True  # Enable Madgwick AHRS filter
    filter_beta: float = 0.008  # Madgwick filter gain - proven value from working code
    filter_zeta: float = 0.0  # Gyro bias drift compensation gain - disabled as in working code


# ----------------------------------------------------------------------
# Types
# ----------------------------------------------------------------------
@realtime(ms=10)
def imu_data():
    """IMU sensor data: accelerometer, gyroscope, and temperature"""
    return [
        ("accel", (np.float32, 3)),  # Accelerometer data in m/s^2 [x, y, z]
        ("gyro", (np.float32, 3)),   # Gyroscope data in rad/s [x, y, z]
        ("temp", np.float32),        # Temperature in Celsius
    ]


@realtime(ms=10)
def imu_orientation():
    """Computed orientation from IMU data (optional, for future use)"""
    return [
        ("quaternion", (np.float32, 4)),  # Orientation quaternion [w, x, y, z]
    ] 