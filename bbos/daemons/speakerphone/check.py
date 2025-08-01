import sounddevice as sd
import re

def find_device_index(pattern, kind=None, flags=0):
    """
    Return the index of the first device whose name matches the regex pattern.
    
    :param pattern: Regex pattern to search in device names.
    :param kind: Optional filter: "input", "output", or None.
    :param flags: Optional regex flags, e.g., re.IGNORECASE
    :return: Device index or None if not found.
    """
    for i, d in enumerate(sd.query_devices()):
        if not re.search(pattern, d["name"], flags=flags | re.IGNORECASE):
            continue
        if kind == "input" and d["max_input_channels"] == 0:
            continue
        if kind == "output" and d["max_output_channels"] == 0:
            continue
        return i
    print(f"No device found matching pattern: {pattern}")
    print("Available devices:")
    for i, d in enumerate(sd.query_devices()):
        print(f"  {i}: {d['name']}")
    return None
def supported_configs(device_index, mode="input", rates=[8000, 16000, 44100, 48000], max_channels=8):
    """
    Check supported (sample_rate, channels) for the given device index.
    
    :param device_index: Integer device index from sd.query_devices().
    :param mode: "input" or "output".
    :param rates: List of sample rates to test.
    :param max_channels: Max number of channels to test (1 to max_channels).
    :return: List of (rate, channels) tuples that are supported.
    """
    checker = sd.check_input_settings if mode == "input" else sd.check_output_settings
    supported = []
    for rate in rates:
        for ch in range(1, max_channels + 1):
            try:
                checker(device=device_index, samplerate=rate, channels=ch)
                supported.append((rate, ch))
            except Exception:
                pass
    return supported
idx = find_device_index("Respeaker Lite")
print(idx)
print(sd.query_devices(idx))
print("Supported configs:", supported_configs(idx, mode="input"))
print("Supported configs:", supported_configs(idx, mode="output"))
