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
from cffi import FFI
ffi = FFI()
CFG = Config("speakerphone")
#Loop.nonblock()

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

# ── shared objects ───────────────────────────────────────────────────────
mic_type  = Type("speakerphone_mic")
zeros     = np.zeros((CFG.speaker_chunk_size, CFG.speaker_channels), np.int16)

r_speak = Reader("/audio.speaker")
w_mic   = Writer("/audio.mic", mic_type)

# Use a lock‑free queue if you prefer; here we share a NumPy view.
spk_buf = np.empty_like(zeros)        # scratch for speaker data
spk_lock = threading.Lock()           # protects spk_buf swap

# Define the C struct layout
ffi.cdef("""
typedef struct {
    double inputBufferAdcTime;
    double currentTime;
    double outputBufferDacTime;
} PaStreamCallbackTimeInfo;
""")

def time_info_to_string(time_info_ptr):
    ti = ffi.cast("PaStreamCallbackTimeInfo *", time_info_ptr)[0]
    return f"{ti.currentTime},{ti.inputBufferAdcTime},{ti.outputBufferDacTime}\n"

# ── callbacks ────────────────────────────────────────────────────────────
def mic_cb(indata, frames, time_info, status):
    if status:                           # XRuns etc.
        print("⚠️", status, file=sys.stderr)
    w_mic["audio"] = indata

def spk_cb(outdata, frames, time_info, status):
    if status:
        print(status)
    if r_speak.ready():
        # /audio.speaker has exactly speaker_chunk_size frames
        np.copyto(outdata, r_speak.data["audio"].copy())
    else:
        np.copyto(outdata, zeros)

# ── set up and run ───────────────────────────────────────────────────────
sd.check_input_settings(samplerate=CFG.mic_sample_rate,  channels=CFG.mic_channels,  dtype='int16')
sd.check_output_settings(samplerate=CFG.speaker_sample_rate, channels=CFG.speaker_channels, dtype='int16')

mic_stream = sd.InputStream(device     = CFG.mic_device,
                            samplerate = CFG.mic_sample_rate,
                            channels   = CFG.mic_channels,
                            dtype      = 'int16',
                            blocksize  = CFG.mic_chunk_size,
                            callback   = mic_cb)

spk_stream = sd.OutputStream(device     = CFG.speaker_device,
                             samplerate = CFG.speaker_sample_rate,
                             channels   = CFG.speaker_channels,
                             dtype      = 'int16',
                             blocksize  = CFG.speaker_chunk_size)

def stop_all(*_):
    mic_stream.abort(); spk_stream.abort()
    mic_stream.close(); spk_stream.close()
    r_speak.close(); w_mic.close()
    sys.exit(0)

signal.signal(signal.SIGINT,  stop_all)
signal.signal(signal.SIGTERM, stop_all)

with w_mic, r_speak, mic_stream, spk_stream:
    print("⇄  streaming – Ctrl‑C to quit")
    spk_stream.start()
    while True:
        if r_speak.ready():
            data = r_speak.data["audio"]
            spk_stream.write(data)
        if not r_speak.readable:
            spk_stream.write(zeros)