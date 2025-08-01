#!/usr/bin/env python3

# /// script
# dependencies = [
#   "sounddevice",
# ]
# ///

import sounddevice as sd

print("=== SOUNDDEVICE DEVICE LIST ===")
devices = sd.query_devices()

# Check up to 50 devices (sounddevice might have more than 10)
for i in range(50):
    try:
        device = sd.query_devices(i)
        if device:
            print(f"\nDevice {i}: {device['name']}")
            print(f"  Channels: {device['max_input_channels']} in, {device['max_output_channels']} out")
            print(f"  Default sample rate: {device['default_samplerate']}")
            
            # Look for USB or EMEET devices
            name_lower = device['name'].lower()
            if any(keyword in name_lower for keyword in ['usb', 'emeet', 'officecore', 'plus', 'hw:2']):
                print(f"  *** POTENTIAL USB DEVICE FOUND ***")
    except:
        # No more devices
        break

print(f"\n=== DEFAULT DEVICES ===")
try:
    print(f"Default input: {sd.default.device[0]}")
    print(f"Default output: {sd.default.device[1]}")
except:
    print("Could not determine default devices")

# Also check host APIs
print(f"\n=== HOST APIS ===")
apis = sd.query_hostapis()
for i, api in enumerate(apis):
    print(f"\nHost API {i}: {api['name']}")
    print(f"  Default input: {api['default_input_device']}")
    print(f"  Default output: {api['default_output_device']}")
    print(f"  Device count: {api['device_count']}")
