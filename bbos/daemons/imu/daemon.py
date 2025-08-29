from bbos import Writer, Config, Type
from driver import ICM42688P
import time


if __name__ == "__main__":
    CFG = Config("imu")
    
    # Initialize IMU
    imu = ICM42688P(
        bus=CFG.i2c_bus, 
        address=CFG.i2c_address,
        enable_filter=CFG.enable_filter,
        beta=CFG.filter_beta,
        zeta=CFG.filter_zeta
    )
    imu.reset()
    imu.configure(
        accel_range=CFG.accel_range,
        gyro_range=CFG.gyro_range,
        sample_rate=CFG.sample_rate
    )
    
    # Initialize orientation if filter is enabled
    if CFG.enable_filter:
        # Take initial accelerometer reading for orientation
        initial_data = imu.read_sensors()
        imu.calculate_initial_orientation(initial_data['accel'])
    
    print(f"[IMU] Daemon started - ICM42688P on I2C bus {CFG.i2c_bus} address 0x{CFG.i2c_address:02X}")
    print(f"[IMU] Sample rate: {CFG.sample_rate}Hz, Accel: ±{CFG.accel_range}g, Gyro: ±{CFG.gyro_range}dps")
    if CFG.enable_filter:
        print(f"[IMU] Madgwick filter enabled - beta: {CFG.filter_beta}, zeta: {CFG.filter_zeta}")
    
    with Writer('imu.data', Type("imu_data")) as w_data, \
         Writer('imu.orientation', Type("imu_orientation")) as w_orient:
        while True:
            # Read sensor data with filtering
            data = imu.read_sensors_filtered()
            # Write raw sensor data to shared memory
            with w_data.buf() as b:
                b['accel'] = data['accel']
                b['gyro'] = data['gyro']
                b['temp'] = data['temp']
            
            # Write orientation data if filter is enabled
            if CFG.enable_filter:
                with w_orient.buf() as b:
                    b['quaternion'] = data['quaternion']