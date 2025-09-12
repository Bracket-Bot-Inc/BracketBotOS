"""
ICM42688P IMU Driver via I2C

Datasheet: https://invensense.tdk.com/wp-content/uploads/2020/04/ds-000347_icm-42688-p-datasheet.pdf
"""
import smbus2
import time
import struct
import numpy as np

# ICM42688P Register Addresses
class Registers:
    # Device Info
    WHO_AM_I = 0x75
    DEVICE_CONFIG = 0x11
    
    # Power Management
    PWR_MGMT0 = 0x4E
    
    # Sensor Data
    TEMP_DATA1 = 0x1D
    ACCEL_DATA_X1 = 0x1F
    GYRO_DATA_X1 = 0x25
    
    # Configuration
    GYRO_CONFIG0 = 0x4F
    ACCEL_CONFIG0 = 0x50
    FIFO_CONFIG = 0x16
    
    # Signal Path Reset
    SIGNAL_PATH_RESET = 0x4B
    
    # Self Test
    SELF_TEST_CONFIG = 0x70
    
    # Interrupt
    INT_CONFIG = 0x14
    INT_STATUS = 0x2D
    
    # Bank Selection
    REG_BANK_SEL = 0x76


class ICM42688P:
    # Device constants
    DEVICE_ID = 0x47  # Expected WHO_AM_I value
    
    # Power modes
    PWR_TEMP_ON = 0x00
    PWR_IDLE = 0x10
    PWR_GYRO_STANDBY = 0x04
    PWR_ACCEL_LOW_POWER = 0x02
    PWR_ACCEL_LOW_NOISE = 0x03
    PWR_6AXIS_LOW_NOISE = 0x0F
    
    # Output Data Rate (ODR)
    ODR_1600HZ = 0x05
    ODR_800HZ = 0x06
    ODR_400HZ = 0x07
    ODR_200HZ = 0x08
    ODR_100HZ = 0x09
    ODR_50HZ = 0x0A
    ODR_25HZ = 0x0B
    ODR_12_5HZ = 0x0C
    
    # Accelerometer Full Scale
    ACCEL_FS_16G = 0x00
    ACCEL_FS_8G = 0x01
    ACCEL_FS_4G = 0x02
    ACCEL_FS_2G = 0x03
    
    # Gyroscope Full Scale
    GYRO_FS_2000DPS = 0x00
    GYRO_FS_1000DPS = 0x01
    GYRO_FS_500DPS = 0x02
    GYRO_FS_250DPS = 0x03
    GYRO_FS_125DPS = 0x04
    GYRO_FS_62_5DPS = 0x05
    GYRO_FS_31_25DPS = 0x06
    GYRO_FS_15_625DPS = 0x07
    
    def __init__(self, bus, address):
        """Initialize ICM42688P IMU.
        
        Args:
            bus: I2C bus number
            address: I2C address
        """
        self.bus = smbus2.SMBus(bus)
        self.address = address
        
        self._accel_scale = 1.0
        self._gyro_scale = 1.0
        self.gyro_bias = np.zeros(3)
    
    def reset(self):
        """Software reset the device."""
        self.bus.write_byte_data(self.address, Registers.REG_BANK_SEL, 0)   
        self.bus.write_byte_data(self.address, Registers.DEVICE_CONFIG, 0x01)
        time.sleep(0.1)  # Increased wait time for reset
        who_am_i = self.bus.read_byte_data(self.address, Registers.WHO_AM_I)
        if who_am_i != self.DEVICE_ID:
            raise RuntimeError(f"Reset failed: WHO_AM_I = 0x{who_am_i:02X}")
    
    def configure(self, accel_range, gyro_range, sample_rate):
        """Configure IMU settings.
        
        Args:
            accel_range: Accelerometer range in g (2, 4, 8, 16)
            gyro_range: Gyroscope range in dps (250, 500, 1000, 2000)
            sample_rate: Sample rate in Hz (12.5, 25, 50, 100, 200, 400, 800, 1600)
        """
        assert accel_range in [2, 4, 8, 16]
        assert gyro_range in [250, 500, 1000, 2000]
        assert sample_rate in [12.5, 25, 50, 100, 200, 400, 800, 1600]
        
        self.bus.write_byte_data(self.address, Registers.REG_BANK_SEL, 0)
        
        # First put device in standby mode
        self.bus.write_byte_data(self.address, Registers.PWR_MGMT0, 0x00)
        time.sleep(0.01)
        
        # Map sample rate to ODR setting
        odr_map = {
            1600: self.ODR_1600HZ,
            800: self.ODR_800HZ,
            400: self.ODR_400HZ,
            200: self.ODR_200HZ,
            100: self.ODR_100HZ,
            50: self.ODR_50HZ,
            25: self.ODR_25HZ,
            12.5: self.ODR_12_5HZ,
        }
        odr = odr_map.get(sample_rate, self.ODR_100HZ)
        
        # Configure accelerometer
        accel_fs_map = {
            16: self.ACCEL_FS_16G,
            8: self.ACCEL_FS_8G,
            4: self.ACCEL_FS_4G,
            2: self.ACCEL_FS_2G,
        }
        accel_fs = accel_fs_map.get(accel_range, self.ACCEL_FS_4G)
        self._accel_scale = accel_range / 32768.0 * 9.80665  # Convert to m/s^2
        self.bus.write_byte_data(self.address, Registers.ACCEL_CONFIG0, (accel_fs << 5) | odr)
        
        # Configure gyroscope
        gyro_fs_map = {
            2000: self.GYRO_FS_2000DPS,
            1000: self.GYRO_FS_1000DPS,
            500: self.GYRO_FS_500DPS,
            250: self.GYRO_FS_250DPS,
        }
        gyro_fs = gyro_fs_map.get(gyro_range, self.GYRO_FS_500DPS)
        self._gyro_scale = gyro_range / 32768.0 * (np.pi / 180.0)  # Convert to rad/s
        self.bus.write_byte_data(self.address, Registers.GYRO_CONFIG0, (gyro_fs << 5) | odr)
        
        # Enable sensors in low noise mode
        self.bus.write_byte_data(self.address, Registers.PWR_MGMT0, self.PWR_6AXIS_LOW_NOISE)
        time.sleep(0.1)  # Increased wait time for sensors to stabilize
        
        # Read and discard first few samples to ensure sensor is ready
        for _ in range(5):
            try:
                self.read()
                time.sleep(0.01)
            except:
                pass
    
    def read(self):
        """Read raw sensor data.
        
        Returns:
            tuple: (temp_raw, accel_raw, gyro_raw)
        """
        # Read all data in one transaction (14 bytes)
        data = self.bus.read_i2c_block_data(self.address, Registers.TEMP_DATA1, 14)
        temp_raw = struct.unpack('>h', bytes(data[0:2]))[0]
        accel_raw = struct.unpack('>hhh', bytes(data[2:8]))
        gyro_raw = struct.unpack('>hhh', bytes(data[8:14]))
        if any(abs(g) >= 32767 for g in gyro_raw):
            print(f"[IMU DEBUG] Gyro saturated! Raw values: {gyro_raw}")
            print(f"[IMU DEBUG] Gyro bytes: {[hex(b) for b in data[8:14]]}")
        temp = (temp_raw / 132.48) + 25.0
        accel = np.array([
            accel_raw[0] * self._accel_scale,
            accel_raw[1] * self._accel_scale,
            accel_raw[2] * self._accel_scale
        ])
        gyro = np.array([
            gyro_raw[0] * self._gyro_scale,
            gyro_raw[1] * self._gyro_scale,
            gyro_raw[2] * self._gyro_scale
        ])
        return accel, gyro, temp
    
    
    def close(self):
        """Close I2C connection."""
        self.bus.close()