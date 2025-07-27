#!/usr/bin/env python3
"""
Minimal CALLBACK‑based recorder (signed‑16‑bit WAV).
Matches the behaviour of your working pull‑mode script.

Dependencies:
    pip install sounddevice
"""

import wave, signal, sys
import numpy as np
import sounddevice as sd

# ── user settings ───────────────────────────────────────────────────────
FILE_NAME    = "recording_cb.wav"
DURATION     = 5            # seconds
SAMPLE_RATE  = 48_000       # Hz
CHANNELS     = 1            # whatever works for your device
BLOCK_FRAMES = 1024         # same as pull version
DEVICE       = None         # None = default; or an index / "hw:…"
# ────────────────────────────────────────────────────────────────────────

# Sanity‑check the device with the desired channel count
sd.check_input_settings(device=DEVICE,
                        samplerate=SAMPLE_RATE,
                        channels=CHANNELS,
                        dtype='int16')

# Open WAV writer once (thread‑safe for small writes)
wav = wave.open(FILE_NAME, "wb")
wav.setnchannels(CHANNELS)
wav.setsampwidth(2)          # 16‑bit
wav.setframerate(SAMPLE_RATE)

frames_to_write = DURATION * SAMPLE_RATE

def mic_callback(indata, frames, time_info, status):
    """PortAudio calls this every BLOCK_FRAMES samples."""
    global frames_to_write
    if status:
        print("⚠️", status, file=sys.stderr)

    # Trim last partial block at end‑of‑recording
    if frames_to_write <= 0:
        return

    write_now = indata[:min(frames, frames_to_write)]
    wav.writeframes(write_now.tobytes())
    frames_to_write -= len(write_now)

    # Stop the stream automatically when done
    if frames_to_write <= 0:
        raise sd.CallbackStop

def graceful_exit(*_):
    stream.close()
    wav.close()
    sys.exit(0)

signal.signal(signal.SIGINT,  graceful_exit)
signal.signal(signal.SIGTERM, graceful_exit)

stream = sd.InputStream(device     = DEVICE,
                        samplerate = SAMPLE_RATE,
                        channels   = CHANNELS,
                        dtype      = 'int16',
                        blocksize  = BLOCK_FRAMES,
                        callback   = mic_callback)

with stream:               # starts the callback thread
    sd.sleep(int(DURATION * 1000) + 200)  # wait a bit longer than needed

wav.close()
print("Done – saved", FILE_NAME)
