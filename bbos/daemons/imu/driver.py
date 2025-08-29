"""
ICM42688P IMU Driver via I2C

Datasheet: https://invensense.tdk.com/wp-content/uploads/2020/04/ds-000347_icm-42688-p-datasheet.pdf
"""
import smbus2
import time
import struct
import numpy as np
from pathlib import Path
from madgwick import MadgwickAHRS, Quaternion


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
    
    def __init__(self, bus=0, address=0x68, enable_filter=True, beta=0.008, zeta=0.0):
        """Initialize ICM42688P IMU.
        
        Args:
            bus: I2C bus number (0 or 1)
            address: I2C address (0x68 or 0x69)
            enable_filter: Enable Madgwick AHRS filter for orientation
            beta: Madgwick filter gain (typical: 0.008)
            zeta: Gyroscope bias drift compensation gain
        """
        self.bus = smbus2.SMBus(bus)
        self.address = address
        self.enable_filter = enable_filter
        
        # Scaling factors (will be set based on configuration)
        self._accel_scale = 1.0
        self._gyro_scale = 1.0
        
        # Coordinate remapping (can be adjusted based on mounting)
        self.remap_axes = False  # Set to True if sensor is mounted differently
        
        # Initialize filter if enabled
        if self.enable_filter:
            self.ahrs = MadgwickAHRS(beta=beta, zeta=zeta)
            self.gyro_bias = np.zeros(3)
            self.last_update_time = None
            # Don't load bias yet - wait until after initialization
        
        # Check device ID
        who_am_i = self._read_byte(Registers.WHO_AM_I)
        if who_am_i != self.DEVICE_ID:
            raise RuntimeError(f"Unexpected WHO_AM_I value: 0x{who_am_i:02X}, expected 0x{self.DEVICE_ID:02X}")
        
        # Initialize and configure
        self.reset()
        self.configure()
        
        # Initialize filter after configuration
        if self.enable_filter:
            # Load any existing bias first
            self._load_gyro_bias()
            
            # Calibrate if no bias exists
            if np.allclose(self.gyro_bias, 0):
                self.calibrate_gyro()
            
            # Get initial accelerometer reading for orientation
            data = self.read_sensors()
            self.calculate_initial_orientation(data['accel'])
            
            # Initialize timing
            self.last_update_time = time.time()
            self.ahrs.samplePeriod = 0.01  # 100Hz default
    
    def _initialize_device(self):
        """Perform complete device initialization sequence."""
        # Reset device
        self.reset()
        
        # Reset signal paths
        self._bank_select(0)
        self._write_byte(Registers.SIGNAL_PATH_RESET, 0x03)  # Reset accel and gyro signal paths
        time.sleep(0.1)
        
        # Configure with default settings
        self.configure()
    
    def _read_byte(self, register):
        """Read a single byte from register."""
        return self.bus.read_byte_data(self.address, register)
    
    def _write_byte(self, register, value):
        """Write a single byte to register."""
        self.bus.write_byte_data(self.address, register, value)
    
    def _read_bytes(self, register, count):
        """Read multiple bytes starting from register."""
        return self.bus.read_i2c_block_data(self.address, register, count)
    
    def _bank_select(self, bank):
        """Select register bank (0-3)."""
        self._write_byte(Registers.REG_BANK_SEL, bank)
    
    def reset(self):
        """Software reset the device."""
        self._bank_select(0)
        self._write_byte(Registers.DEVICE_CONFIG, 0x01)
        time.sleep(0.1)  # Increased wait time for reset
        
        # Verify reset completed by checking WHO_AM_I
        who_am_i = self._read_byte(Registers.WHO_AM_I)
        if who_am_i != self.DEVICE_ID:
            raise RuntimeError(f"Reset failed: WHO_AM_I = 0x{who_am_i:02X}")
    
    def configure(self, accel_range=4, gyro_range=500, sample_rate=100):
        """Configure IMU settings.
        
        Args:
            accel_range: Accelerometer range in g (2, 4, 8, 16)
            gyro_range: Gyroscope range in dps (250, 500, 1000, 2000)
            sample_rate: Sample rate in Hz (12.5, 25, 50, 100, 200, 400, 800, 1600)
        """
        self._bank_select(0)
        
        # First put device in standby mode
        self._write_byte(Registers.PWR_MGMT0, 0x00)
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
        self._write_byte(Registers.ACCEL_CONFIG0, (accel_fs << 5) | odr)
        
        # Configure gyroscope
        gyro_fs_map = {
            2000: self.GYRO_FS_2000DPS,
            1000: self.GYRO_FS_1000DPS,
            500: self.GYRO_FS_500DPS,
            250: self.GYRO_FS_250DPS,
        }
        gyro_fs = gyro_fs_map.get(gyro_range, self.GYRO_FS_500DPS)
        self._gyro_scale = gyro_range / 32768.0 * np.pi / 180.0  # Convert to rad/s
        self._write_byte(Registers.GYRO_CONFIG0, (gyro_fs << 5) | odr)
        
        # Enable sensors in low noise mode
        self._write_byte(Registers.PWR_MGMT0, self.PWR_6AXIS_LOW_NOISE)
        time.sleep(0.1)  # Increased wait time for sensors to stabilize
        
        # Read and discard first few samples to ensure sensor is ready
        for _ in range(5):
            try:
                self.read_raw_data()
                time.sleep(0.01)
            except:
                pass
    
    def read_raw_data(self):
        """Read raw sensor data.
        
        Returns:
            tuple: (temp_raw, accel_raw, gyro_raw)
        """
        # Read all data in one transaction (14 bytes)
        data = self._read_bytes(Registers.TEMP_DATA1, 14)
        
        # Parse temperature (bytes 0-1)
        temp_raw = struct.unpack('>h', bytes(data[0:2]))[0]
        
        # Parse accelerometer (bytes 2-7)
        accel_raw = struct.unpack('>hhh', bytes(data[2:8]))
        
        # Parse gyroscope (bytes 8-13)
        gyro_raw = struct.unpack('>hhh', bytes(data[8:14]))
        
        # Debug: Check if gyro values are saturated
        if any(abs(g) >= 32767 for g in gyro_raw):
            print(f"[IMU DEBUG] Gyro saturated! Raw values: {gyro_raw}")
            print(f"[IMU DEBUG] Gyro bytes: {[hex(b) for b in data[8:14]]}")
        
        return temp_raw, accel_raw, gyro_raw
    
    def remap_accel_gyro(self, accel, gyro):
        """Remap accelerometer and gyroscope axes if needed.
        
        This is useful when the sensor is mounted in a different orientation.
        The default mapping matches the working MPU6050 implementation.
        """
        if self.remap_axes:
            # Remap to match the working implementation's coordinate system
            accel = np.array([-accel[1], accel[0], accel[2]])
            gyro = np.array([-gyro[1], gyro[0], gyro[2]])
        return accel, gyro
    
    def read_sensors(self):
        """Read scaled sensor data.
        
        Returns:
            dict: Dictionary with 'accel' (m/s^2), 'gyro' (rad/s), and 'temp' (°C)
        """
        temp_raw, accel_raw, gyro_raw = self.read_raw_data()
        
        # Convert temperature (formula from datasheet)
        temp = (temp_raw / 132.48) + 25.0
        
        # Convert to SI units
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
        
        # Apply axis remapping if needed
        accel, gyro = self.remap_accel_gyro(accel, gyro)
        
        return {
            'temp': np.float32(temp),
            'accel': accel.astype(np.float32),
            'gyro': gyro.astype(np.float32)
        }
    
    def close(self):
        """Close I2C connection."""
        self.bus.close()
    
    def _load_gyro_bias(self):
        """Load gyro bias from file or calculate it."""
        bias_file = Path(__file__).parent / 'gyro_bias.txt'
        try:
            self.gyro_bias = np.loadtxt(bias_file)
            print(f"[IMU] Loaded gyro bias: {self.gyro_bias}")
        except FileNotFoundError:
            print("[IMU] No gyro bias file found, will calibrate...")
            self.calibrate_gyro()
    
    def save_gyro_bias(self):
        """Save current gyro bias to file."""
        bias_file = Path(__file__).parent / 'gyro_bias.txt'
        np.savetxt(bias_file, self.gyro_bias)
    
    def calibrate_gyro(self, samples=200):
        """Calibrate gyroscope bias by averaging readings while stationary."""
        print("[IMU] Calibrating gyro bias - keep IMU stationary...")
        self.gyro_bias = np.zeros(3)
        
        # Wait for sensor to stabilize
        print("[IMU] Waiting for sensor to stabilize...")
        for _ in range(50):
            self.read_raw_data()
            time.sleep(0.01)
        
        print(f"[IMU] Collecting {samples} samples...")
        for i in range(samples):
            _, _, gyro_raw = self.read_raw_data()
            gyro_scaled = np.array([
                gyro_raw[0] * self._gyro_scale,
                gyro_raw[1] * self._gyro_scale,
                gyro_raw[2] * self._gyro_scale
            ])
            self.gyro_bias += gyro_scaled / samples
            time.sleep(0.01)
        
        # Save bias to file
        bias_file = Path(__file__).parent / 'gyro_bias.txt'
        np.savetxt(bias_file, self.gyro_bias)
        print(f"[IMU] Calculated gyro bias: {self.gyro_bias}")
    
    def read_sensors_filtered(self):
        """Read sensor data with Madgwick filter applied.
        
        Returns:
            dict: Dictionary with 'accel', 'gyro', 'temp', and 'quaternion'
        """
        # Get raw sensor data
        data = self.read_sensors()
        
        if not self.enable_filter:
            # Add dummy orientation data
            data['quaternion'] = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
            return data
        
        # Apply gyro bias correction
        gyro_corrected = data['gyro'] - self.gyro_bias
        
        # Update filter timing
        current_time = time.time()
        if self.last_update_time is not None:
            dt = current_time - self.last_update_time
            self.ahrs.samplePeriod = dt
        self.last_update_time = current_time
        
        # Update filter with corrected gyro
        self.ahrs.update_imu(gyro_corrected, data['accel'])
        
        # Get orientation as quaternion only
        quaternion = self.ahrs.quaternion.q
        
        # Add filtered data
        data['gyro'] = gyro_corrected  # Use bias-corrected gyro
        data['quaternion'] = quaternion.astype(np.float32)
        
        return data
    
    def calculate_initial_orientation(self, accel):
        """Calculate initial orientation from accelerometer."""
        if not self.enable_filter:
            return
        
        # Normalize accelerometer vector
        acc_magnitude = np.linalg.norm(accel)
        if acc_magnitude < 0.1:  # Avoid division by zero
            return
            
        acc_norm = accel / acc_magnitude
        
        # Estimate initial roll and pitch from accelerometer (matching working code)
        initial_roll = np.arctan2(acc_norm[1], acc_norm[2])
        initial_pitch = np.arctan2(-acc_norm[0], np.sqrt(acc_norm[1]**2 + acc_norm[2]**2))
        initial_yaw = 0  # Can't determine from accelerometer alone
        
        # Initialize quaternion using the from_angle_axis function
        q = Quaternion.from_angle_axis(initial_roll, 1, 0, 0)
        q = q * Quaternion.from_angle_axis(initial_pitch, 0, 1, 0)
        q = q * Quaternion.from_angle_axis(initial_yaw, 0, 0, 1)
        
        self.ahrs.quaternion = q 