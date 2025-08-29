import numpy as np
import inekf

class DiffDriveEstimator2D:
    """
    Timestamp-aware, minimal odometry with gyro-z bias fusion (IMU ⟷ wheel kinematics),
    integrating pose on SE(2) with InEKF — no magnetometer/absolute heading required.

    Assumptions:
      - drive_state.pos is CUMULATIVE wheel turns (L, R).
      - imu_data.gyro is rad/s in IMU frame; we rotate IMU->base via R_bi, then
        take the component along `grid_axis` (0=x, 1=y, 2=z) as the yaw-rate source.
    """

    # ---------- Tiny KF for yaw-rate + bias (state = [omega, bias]) ----------
    class _YawKF:
        def __init__(self, q_omega=0.02**2, q_bias=1e-6**2, P0=None):
            self.x = np.zeros(2)                                 # [omega, bias]
            self.P = np.diag([1.0, 1e-2]) if P0 is None else P0.copy()
            self.q_omega = float(q_omega)
            self.q_bias  = float(q_bias)
            self._last_alpha = None                               # last raw gyro component

        @property
        def omega(self): return float(self.x[0])
        @property
        def bias(self):  return float(self.x[1])

        def propagate(self, omega_alpha, dt):
            omega_alpha = float(omega_alpha)
            if self._last_alpha is None:
                self._last_alpha = omega_alpha
                return
            d_omega = omega_alpha - self._last_alpha              # cancels constant bias between samples
            self.x += np.array([d_omega, 0.0])
            self.P += np.diag([self.q_omega, self.q_bias]) * float(dt)
            self._last_alpha = omega_alpha

        def update_beta(self, omega_beta, beta_var, biased=False):
            H = np.array([[1.0, 1.0]]) if biased else np.array([[1.0, 0.0]])
            R = np.array([[float(beta_var)]])
            S = H @ self.P @ H.T + R
            K = self.P @ H.T @ np.linalg.inv(S)
            y = np.array([[float(omega_beta)]]) - H @ self.x.reshape(-1,1)
            self.x = (self.x.reshape(-1,1) + K @ y).ravel()
            I_KH = np.eye(2) - K @ H
            self.P = I_KH @ self.P @ I_KH.T + K @ R @ K.T

    # ---------- Public API ----------
    def __init__(self,
                 base_width_m: float,
                 wheel_diam_m: float,
                 R_bi: np.ndarray = np.eye(3),
                 grid_axis: int = 2,          # 0=x, 1=y, 2=z (axis normal to the 2D grid plane)
                 grid_axis_sign: float = +1.0,# flip if your axis sign is opposite
                 gyro_beta_std=np.deg2rad(0.5),
                 beta_is_biased=False,
                 q_theta=1e-3, q_x=5e-2, q_y=5e-2,
                 P0_pose=np.diag([1e-3,1e-3,1e-3])):
        """
        grid_axis selects which base-frame axis is "up"/normal to the plane (i.e., yaw axis).
        grid_axis_sign lets you invert that axis if needed (+1 or -1).
        """
        assert grid_axis in (0,1,2)
        self.B = float(base_width_m)
        self.wheel_diam = float(wheel_diam_m)
        self.R_bi = np.array(R_bi, float)
        self.axis = int(grid_axis)
        self.axis_sign = float(grid_axis_sign)

        # Filters
        self.kf = self._YawKF()
        self.beta_var = float(gyro_beta_std)**2
        self.beta_is_biased = bool(beta_is_biased)

        # InEKF on SE(2)
        self.proc = inekf.OdometryProcess(q_theta, q_x, q_y)
        self.state = inekf.SE2(0.0, 0.0, 0.0, P0_pose)
        self.iekf = inekf.InEKF(self.proc, self.state, inekf.ERROR.RIGHT)

        # Bookkeeping
        self._imu_ts_last   = None
        self._drive_ts_last = None
        self._pos_turns_last = None

    # ---- Utilities ----
    @staticmethod
    def _dt_seconds(ts_now: np.datetime64, ts_last: np.datetime64) -> float:
        return (ts_now - ts_last).astype('timedelta64[ns]').astype(float) * 1e-9

    def _wheel_increments_m(self, pos_turns_now, pos_turns_last):
        drev = np.asarray(pos_turns_now, float) - np.asarray(pos_turns_last, float)  # (L,R) turns
        return np.pi * self.wheel_diam * drev  # meters

    # ---- Streaming updates ----
    def update_imu(self, imu_row: dict):
        """
        imu_row must contain:
          - "timestamp": np.datetime64
          - "gyro": (3,) rad/s in IMU frame
        Accel/Temp are ignored here.
        """
        ts = np.datetime64(imu_row["timestamp"])
        gyro_imu = np.asarray(imu_row["gyro"], float)
        # rotate IMU->base, select yaw component along grid_axis, apply sign
        gyro_base = self.R_bi @ gyro_imu
        omega_alpha = self.axis_sign * float(gyro_base[self.axis])

        if self._imu_ts_last is None:
            self._imu_ts_last = ts
            self.kf.propagate(omega_alpha, dt=0.0)  # initialize memory
            return None

        dt = self._dt_seconds(ts, self._imu_ts_last)
        self._imu_ts_last = ts
        self.kf.propagate(omega_alpha, dt)
        return {"omega": self.kf.omega, "bias": self.kf.bias}

    def update_drive(self, drive_row: dict):
        """
        drive_row must contain:
        - "timestamp": np.datetime64
        - "pos": (2,) cumulative TURNS (L,R)           [optional but preferred for ds]
        - "vel": (2,) TURNS/SEC (L,R)                   [optional; used for omega_beta and ds fallback]
        - "torque": ignored
        """
        ts = np.datetime64(drive_row["timestamp"])
        pos_turns_now = drive_row["pos"]
        vel_turns = drive_row["vel"]

        if self._drive_ts_last is None:
            self._drive_ts_last = ts
            if pos_turns_now is not None:
                self._pos_turns_last = np.asarray(pos_turns_now, float).copy()
            return None

        dt = self._dt_seconds(ts, self._drive_ts_last)
        self._drive_ts_last = ts
        dt = max(float(dt), 1e-9)

        # --- Convert velocities if provided (turns/s -> m/s)
        vL = vR = None
        if vel_turns is not None:
            vel_turns = np.asarray(vel_turns, float)
            vL = (np.pi * self.wheel_diam) * vel_turns[0]
            vR = (np.pi * self.wheel_diam) * vel_turns[1]

        # --- Distance increment from positions if available (less noisy)
        use_pos = pos_turns_now is not None and self._pos_turns_last is not None
        if use_pos:
            pos_turns_now = np.asarray(pos_turns_now, float)
            ds_L, ds_R = self._wheel_increments_m(pos_turns_now, self._pos_turns_last)
            self._pos_turns_last = pos_turns_now.copy()
            ds = 0.5 * (ds_R + ds_L)                # [m]
            dtheta_wheel = (ds_R - ds_L) / self.B   # [rad]
        else:
            # Fallback: integrate distance from velocities
            if vL is None or vR is None:
                # nothing we can do this cycle
                return None
            ds = 0.5 * (vR + vL) * dt
            dtheta_wheel = ((vR - vL) / self.B) * dt

        # --- KF correction: prefer velocity-derived yaw-rate
        if vL is not None and vR is not None:
            omega_beta = (vR - vL) / self.B
        else:
            omega_beta = dtheta_wheel / dt
        self.kf.update_beta(omega_beta, beta_var=self.beta_var, biased=self.beta_is_biased)

        # --- Heading & pose predict
        dtheta = self.kf.omega * dt
        self.state = self.iekf.predict(inekf.SE2(dtheta, ds, 0.0))

        # --- Extract components
        R2 = np.array(self.state.R.mat, dtype=float)
        theta = float(np.arctan2(R2[1, 0], R2[0, 0]))
        x, y = map(float, np.array(self.state[0]).reshape(-1)[:2])

        return {
            "theta_xy": np.array([theta, x, y], float),
            "cov": self.state.cov,
            "omega": self.kf.omega,
            "bias": self.kf.bias,
        }