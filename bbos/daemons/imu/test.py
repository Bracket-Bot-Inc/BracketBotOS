#!/usr/bin/env python3
"""Test script for ICM42688P IMU driver."""

from driver import ICM42688P
import time
import numpy as np


def main():
    print("Testing ICM42688P IMU with Madgwick filter...")
    
    try:
        # Initialize IMU with filtering enabled
        imu = ICM42688P(bus=1, address=0x69, enable_filter=True, beta=0.008)
        print("✓ IMU initialized successfully")
        
        # Reset and configure
        imu.reset()
        imu.configure(accel_range=4, gyro_range=500, sample_rate=200)
        print("✓ IMU configured: ±4g accel, ±500dps gyro, 100Hz")
        
        # Initialize orientation
        initial_data = imu.read_sensors()
        imu.calculate_initial_orientation(initial_data['accel'])
        print("✓ Initial orientation calculated")
        
        # Read data for 10 seconds
        print("\nReading sensor data for 10 seconds...")
        print("Time\tRoll\tPitch\tYaw\tAccel Mag\tGyro Mag\tTemp")
        print("-" * 70)
        
        start_time = time.time()
        readings = []
        
        while time.time() - start_time < 10:
            data = imu.read_sensors_filtered()
            
            # Calculate magnitudes
            accel_mag = np.linalg.norm(data['accel'])
            gyro_mag = np.linalg.norm(data['gyro'])
            
            # Get euler angles
            roll, pitch, yaw = data['euler']
            
            print(f"{time.time()-start_time:.2f}s\t"
                  f"{roll:6.1f}°\t{pitch:6.1f}°\t{yaw:6.1f}°\t"
                  f"{accel_mag:8.2f}\t{gyro_mag:8.2f}\t"
                  f"{data['temp']:.1f}°C")
            
            readings.append({
                'time': time.time() - start_time,
                'accel': data['accel'].copy(),
                'gyro': data['gyro'].copy(),
                'euler': data['euler'].copy(),
                'quaternion': data['quaternion'].copy()
            })
            
        
        # Calculate statistics
        print("\n" + "="*70)
        print("Statistics:")
        
        accels = np.array([r['accel'] for r in readings])
        gyros = np.array([r['gyro'] for r in readings])
        
        print(f"\nAccelerometer std dev: X={np.std(accels[:,0]):.4f}, Y={np.std(accels[:,1]):.4f}, Z={np.std(accels[:,2]):.4f}")
        print(f"Gyroscope std dev: X={np.std(gyros[:,0]):.4f}, Y={np.std(gyros[:,1]):.4f}, Z={np.std(gyros[:,2]):.4f}")
        
        avg_hz = len(readings) / (readings[-1]['time'] - readings[0]['time'])
        print(f"\nActual sample rate: {avg_hz:.1f} Hz")
        
        print("\n✓ Test completed successfully!")
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        print("\nTroubleshooting:")
        print("1. Check I2C is enabled: sudo dietpi-config")
        print("2. Check I2C devices: sudo i2cdetect -y 0")
        print("3. Verify wiring: SDA to pin 3, SCL to pin 5, VDD to 3.3V, GND to GND")
        print("4. Check permissions: user should be in 'i2c' group")
        import traceback
        traceback.print_exc()
    
    finally:
        if 'imu' in locals():
            imu.close()


if __name__ == "__main__":
    main() 