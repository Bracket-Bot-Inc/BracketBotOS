from bbos.registry import *
import numpy as np
import math


# ----------------------------------------------------------------------
# Configs
# ----------------------------------------------------------------------
@register
class imu:
    i2c_bus: int = 1  # I2C bus number (0 or 1)
    i2c_address: int = 0x69  # ICM42688P default I2C address
    accel_range: int = 4  # Accelerometer range in g (2, 4, 8, 16)
    sample_rate: int = 400  # Sample rate in Hz
    gyro_range: int = 1000  # Gyroscope range in dps (250, 500, 1000, 2000)
    filter_beta: float = 0.008
    filter_zeta: float = 0

@realtime(ms=10)
def imu_orientation():
    """Computed orientation from IMU data"""
    return [
        ("rpy", (np.float32, 3)),
    ] 