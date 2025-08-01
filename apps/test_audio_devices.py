#!/usr/bin/env python3
import sounddevice as sd

# Query all devices
devices = sd.query_devices()

print("=== ALL AUDIO DEVICES ===")
for i, device in enumerate(devices):
    print(f"\nDevice {i}: {device['name']}")
    print(f"  Channels: {device['max_input_channels']} in, {device['max_output_channels']} out")
    print(f"  Default sample rate: {device['default_samplerate']}")
    print(f"  Host API: {sd.query_hostapis(device['hostapi'])['name']}")

# Try to find USB audio device
print("\n=== LOOKING FOR USB AUDIO DEVICE ===")
for i, device in enumerate(devices):
    if 'usb' in device['name'].lower() or 'emeet' in device['name'].lower():
        print(f"Found potential USB device at index {i}: {device['name']}")

# Show default devices
print(f"\n=== DEFAULT DEVICES ===")
print(f"Default input device: {sd.default.device[0]}")
print(f"Default output device: {sd.default.device[1]}")
