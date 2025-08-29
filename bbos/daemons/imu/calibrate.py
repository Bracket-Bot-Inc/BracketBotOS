#!/usr/bin/env python3
"""Calibrate the IMU gyroscope bias."""

from driver import ICM42688P
import time
import sys


def main():
    print("IMU Gyroscope Calibration")
    print("=" * 40)
    print("\nThis will calibrate the gyroscope bias.")
    print("Make sure the IMU is completely stationary during calibration!")
    print("\nPress Enter to start calibration or Ctrl+C to cancel...")
    
    try:
        input()
    except KeyboardInterrupt:
        print("\nCalibration cancelled.")
        return
    
    try:
        # Initialize IMU
        print("\nInitializing IMU...")
        from bbos import Config
        CFG = Config("imu")
        imu = ICM42688P(bus=CFG.i2c_bus, address=CFG.i2c_address, enable_filter=False)
        imu.reset()
        imu.configure(accel_range=CFG.accel_range, gyro_range=CFG.gyro_range, sample_rate=CFG.sample_rate)
        print("✓ IMU initialized")
        
        # Perform calibration
        print("\nCalibrating gyroscope bias...")
        print("Keep the IMU perfectly still!")
        
        # Clear any existing bias
        imu.gyro_bias = [0, 0, 0]
        
        # Calibrate with more samples for better accuracy
        imu.calibrate_gyro(samples=100)
        
        print("\n✓ Calibration complete!")
        print(f"Gyro bias saved to: gyro_bias.txt")
        print(f"Bias values: X={imu.gyro_bias[0]:.6f}, Y={imu.gyro_bias[1]:.6f}, Z={imu.gyro_bias[2]:.6f} rad/s")
        
        # Test the calibration
        print("\nTesting calibration (5 seconds)...")
        print("Gyro readings should be close to zero when stationary:")
        
        for i in range(50):
            data = imu.read_sensors()
            gyro = data['gyro'] - imu.gyro_bias
            print(f"Gyro: X={gyro[0]:7.4f}, Y={gyro[1]:7.4f}, Z={gyro[2]:7.4f} rad/s", end='\r')
            time.sleep(0.1)
        
        print("\n\n✓ Calibration test complete!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
    
    finally:
        if 'imu' in locals():
            imu.close()


if __name__ == "__main__":
    main() 