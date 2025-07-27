#!/usr/bin/env python3
"""
Low‑latency full‑duplex: mic → /audio.mic SHM  |  /audio.speaker → loudspeaker
Works like your original design but lets PortAudio own the timing.
"""

from bbos import Writer, Reader, Type, Config
import numpy as np
import sounddevice as sd
import signal, sys, threading

CFG = Config("speakerphone")

# ── shared objects ───────────────────────────────────────────────────────
mic_type  = Type("speakerphone_audio")(CFG.mic_chunk_size, CFG.mic_channels)
zeros     = np.zeros((CFG.speaker_chunk_size, CFG.speaker_channels), np.int16)

r_speak = Reader("/audio.speaker")
w_mic   = Writer("/audio.mic", mic_type)

# Use a lock‑free queue if you prefer; here we share a NumPy view.
spk_buf = np.empty_like(zeros)        # scratch for speaker data
spk_lock = threading.Lock()           # protects spk_buf swap

# ── callbacks ────────────────────────────────────────────────────────────
def mic_cb(indata, frames, time_info, status):
    # indata is int16 ndarray shape (frames, mic_channels)
    if status:                           # XRuns etc.
        print("⚠️", status, file=sys.stderr)

    with w_mic.buf() as b:               # copy into shared‑mem struct
        b["audio"][:] = indata

def spk_cb(outdata, frames, time_info, status):
    if status.output_underflow:
        print("⚠️ speaker underflow", file=sys.stderr)

    with spk_lock:
        if r_speak.ready():
            # /audio.speaker has exactly speaker_chunk_size frames
            np.copyto(outdata, r_speak.data["audio"])
        else:                            # no fresh data ‑ play silence
            np.copyto(outdata, zeros)

# ── set up and run ───────────────────────────────────────────────────────
sd.check_input_settings (samplerate=CFG.mic_sample_rate,  channels=CFG.mic_channels,  dtype='int16')
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
                             blocksize  = CFG.speaker_chunk_size,
                             callback   = spk_cb)

def stop_all(*_):
    mic_stream.abort(); spk_stream.abort()
    mic_stream.close(); spk_stream.close()
    r_speak.close(); w_mic.close()
    sys.exit(0)

signal.signal(signal.SIGINT,  stop_all)
signal.signal(signal.SIGTERM, stop_all)

with w_mic, r_speak, mic_stream, spk_stream:
    print("⇄  streaming – Ctrl‑C to quit")
    signal.pause()           # main thread sleeps; callbacks do the work
