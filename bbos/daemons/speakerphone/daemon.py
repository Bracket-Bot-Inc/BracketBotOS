#!/usr/bin/env python3
"""
Low‑latency full‑duplex: mic → /audio.mic SHM  |  /audio.speaker → loudspeaker
Works like your original design but lets PortAudio own the timing.
"""

from bbos import Writer, Reader, Type, Config
from bbos.time import Loop
import numpy as np
import sounddevice as sd
import signal, sys, threading
import re

CFG = Config("speakerphone")

def find_device_index(pattern, kind=None, flags=0):
    """
    Return the index of the first device whose name matches the regex pattern.
    
    :param pattern: Regex pattern to search in device names.
    :param kind: Optional filter: "input", "output", or None.
    :param flags: Optional regex flags, e.g., re.IGNORECASE
    :return: Device index or None if not found.
    """
    for i, d in enumerate(sd.query_devices()):
        print(f"Device {i}: {d['name']}", flush=True)
        if not re.search(pattern, d["name"], flags=flags | re.IGNORECASE):
            continue
        if kind == "input" and d["max_input_channels"] == 0:
            continue
        if kind == "output" and d["max_output_channels"] == 0:
            continue
        print(f"Found device: {d['name']}", flush=True)
        return i
    print(f"No device found matching pattern: {pattern}", flush=True)
    print("Available devices:", flush=True)
    for i, d in enumerate(sd.query_devices()):
        print(f"  {i}: {d['name']}")
    return None

def main(w_mic, r_speak):
    def mic_cb(indata, frames, time_info, status):
        w_mic["audio"] = indata
    # ── set up and run ───────────────────────────────────────────────────────
    sd.check_input_settings(samplerate=CFG.mic_sample_rate,  channels=CFG.mic_channels,  dtype='int16')
    sd.check_output_settings(samplerate=CFG.speaker_sample_rate, channels=CFG.speaker_channels, dtype='int16')

    mic_stream = sd.InputStream(device     = find_device_index(CFG.mic_device),
                                samplerate = CFG.mic_sample_rate,
                                channels   = CFG.mic_channels,
                                dtype      = 'int16',
                                blocksize  = CFG.mic_chunk_size,
                                callback   = mic_cb)
    spk_stream = sd.OutputStream(device     = find_device_index(CFG.speaker_device),
                                samplerate = CFG.speaker_sample_rate,
                                channels   = CFG.speaker_channels,
                                dtype      = 'int16',
                                blocksize  = CFG.speaker_chunk_size)
    zeros = np.zeros((CFG.speaker_chunk_size, CFG.speaker_channels), np.int16)
    mic_stream.start()
    spk_stream.start()
    while True:
        if r_speak.ready():
            data = r_speak.data["audio"]
            y = (data.astype(np.float32) / 32768.0) * CFG.volume
            y = np.clip(y, -1.0, 1.0)
            data = (y * 32768.0).astype(np.int16)
            spk_stream.write(data)
        if not r_speak.readable:
            spk_stream.write(zeros)
    spk_stream.stop()
    mic_stream.stop()
    spk_stream.close()
    mic_stream.close()

if __name__ == "__main__":
    mic_type  = Type("speakerphone_mic")
    r_speak = Reader("audio.speaker")
    w_mic   = Writer("audio.mic", mic_type, keeptime=False)
    with w_mic, r_speak:
        main(w_mic, r_speak)