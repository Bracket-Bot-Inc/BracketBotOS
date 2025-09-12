from bbos import Writer, Config, Type
from driver import ICM42688P
from madgwick import MadgwickAHRS, Quaternion
import time
import numpy as np

CFG = Config("imu")

class FilteredIMU():
    
    def __init__(self):
        self.sensor = ICM42688P(bus=CFG.i2c_bus, address=CFG.i2c_address)
        self.sensor.reset()
        self.sensor.configure(
            accel_range=CFG.accel_range,
            gyro_range=CFG.gyro_range,
            sample_rate=CFG.sample_rate,
        )
        # self.sensor.gyro_range = adafruit_mpu6050.GyroRange.RANGE_500_DPS  # Set gyroscope range to ±1000 dps
        self.ahrs = MadgwickAHRS(beta=CFG.filter_beta, zeta=CFG.filter_zeta)
        self.gyro_bias = np.array([0., 0., 0.])
        self.q_ref = None


    def calibrate(self):
        self.gyro_bias = np.array([0., 0., 0.])
        for _ in range(50):
            _, gyro, _ = self.sensor.read()
            self.gyro_bias += gyro / 50
            time.sleep(0.01)
        print('Calculated gyro bias:', self.gyro_bias)
        self.accel, gyro_raw, _ = self.sensor.read()
        self.gyro = gyro_raw - self.gyro_bias
        self.t = time.monotonic()

        self.quat = self._calculate_initial_q(self.accel)
        self.grav = self.quat_rotate(self.quat.conj(), [0, 0, 1])
        self.ahrs.quaternion = self.quat

        # ---------- FAST-SETTLE: 1.5 s with high beta/zeta while still ----------
        G = 9.80665
        settle_sec = 5
        t_end = time.monotonic() + settle_sec
        last = time.monotonic()
        while time.monotonic() < t_end:
            a, g, _ = self.sensor.read()
            # per-step dt
            now = time.monotonic()
            dt = max(1e-4, now - last)
            last = now
            self.ahrs.samplePeriod = dt

            # stationary test (tune to your platform)
            a_norm = np.linalg.norm(a)
            w_norm = np.linalg.norm(g - self.gyro_bias)  # rad/s
            still = (abs(a_norm - G) < 0.15) and (w_norm < 0.15)  # ~0.015 g and ~8.6°/s

            if still:
                self.ahrs.beta = 0.12    # strong gravity correction
                self.ahrs.zeta = 0.012   # fast bias adaptation
                self.ahrs.update_imu(g - self.gyro_bias, a)
            else:
                # moving: don’t over-trust accel
                self.ahrs.beta = 0.02
                self.ahrs.zeta = 0.004
                self.ahrs.update_imu(g - self.gyro_bias, a)

        # After settle, set normal gains
        self.ahrs.beta = 0.035
        self.ahrs.zeta = 0.006
        # ------------------------------------------------------------------------


    def get_orientation(self):
        self.update()
        gx, gy, gz = self.grav

        # Map gravity vector components to new axes
        gX_new = gy       # gX_new = gy
        gY_new = -gx      # gY_new = -gx
        gZ_new = gz       # gZ_new = gz

        # Compute roll and pitch using the standard formulas
        roll = np.degrees(np.arctan2(gY_new, gZ_new))
        pitch = np.degrees(np.arctan2(-gX_new, np.sqrt(gY_new**2 + gZ_new**2)))

        # Compute yaw from the quaternion
        qw, qx, qy, qz = self.quat
        yaw = np.degrees(np.arctan2(2 * (qw * qz + qx * qy),
                                    1 - 2 * (qy**2 + qz**2)))

        return np.array([pitch, roll, yaw])

    def _calculate_initial_q(self, accel):
        acc_norm = accel / np.linalg.norm(accel)

        # Estimate initial roll and pitch from accelerometer
        initial_roll = np.arctan2(acc_norm[1], acc_norm[2])
        initial_pitch = np.arctan2(-acc_norm[0], np.sqrt(acc_norm[1]**2 + acc_norm[2]**2))
        initial_yaw = 0

        # Initialize quaternion using the from_angle_axis function
        initial_q = Quaternion.from_angle_axis(initial_roll, 1, 0, 0)
        initial_q = initial_q * Quaternion.from_angle_axis(initial_pitch, 0, 1, 0)
        initial_q = initial_q * Quaternion.from_angle_axis(initial_yaw, 0, 0, 1)
        return initial_q

    def update(self):
        # Read and map sensor readings
        self.accel, gyro_raw, _ = self.sensor.read()
        self.gyro = gyro_raw - self.gyro_bias
        t = time.monotonic()

        # Store raw data
        self.accel_RAW = self.accel
        self.gyro_RAW = self.gyro
        self.quat_RAW = self._calculate_initial_q(self.accel_RAW)
        self.grav_RAW = self.quat_rotate(self.quat_RAW.conj(), [0, 0, 1])

        self.ahrs.samplePeriod = t - self.t

        # --------- Gate accel if not close to gravity ---------
        G = 9.80665
        a_norm = np.linalg.norm(self.accel)
        if abs(a_norm - G) > 0.25:       # > ~0.025 g => likely linear accel
            beta_save = self.ahrs.beta
            self.ahrs.beta = 0.0         # skip gravity correction this step
            self.ahrs.update_imu(self.gyro, self.accel)
            self.ahrs.beta = beta_save
        else:
            self.ahrs.update_imu(self.gyro, self.accel)
        # ------------------------------------------------------
        self.t = t
        quat = self.ahrs.quaternion
        self.quat = quat.q
        self.grav = self.quat_rotate(quat.conj(), [0, 0, 1])


    def quat_rotate(self, q, v):
        """Rotate a vector v by a quaternion q"""
        qv = np.concatenate(([0], v))
        return (q * Quaternion(qv) * q.conj()).q[1:]

if __name__ == "__main__":
    # Initialize IMU
    imu = FilteredIMU()
    imu.calibrate()
    start_time = time.time()
    while time.time() - start_time < 5:
        rpy = imu.get_orientation()

    ori_bias = np.array([0.0, 0.0, 0.0])
    for _ in range(100):
        rpy = imu.get_orientation()
        ori_bias += rpy
    ori_bias /= 100
    prev_rpy = np.array([0.0, 0.0, 0.0])
    alpha = 1

    print(f"[IMU] Daemon started - ICM42688P on I2C bus {CFG.i2c_bus} address 0x{CFG.i2c_address:02X}")
    print(f"[IMU] Sample rate: {CFG.sample_rate}Hz, Accel: ±{CFG.accel_range}g, Gyro: ±{CFG.gyro_range}dps")

    with Writer('imu.orientation', Type("imu_orientation")) as w_orient:
        while True:
            rpy = imu.get_orientation() - ori_bias
            rpy = prev_rpy * (1 - alpha) + rpy * alpha
            prev_rpy = rpy
            with w_orient.buf() as b:
                b['rpy'] = rpy