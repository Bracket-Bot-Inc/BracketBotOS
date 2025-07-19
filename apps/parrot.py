#!/usr/bin/env python3

import numpy as np
from bbos import Writer, Reader, Type, Config, Time
import time

CFG = Config("speakerphone")
DURATION = 5.0  # seconds
CHUNK = CFG.chunk_size
SAMPLE_RATE = CFG.sample_rate
CHANNELS = CFG.channels

if __name__ == "__main__":
    recorded = []

    print(f"[+] Recording for {DURATION} seconds...")

    with Reader("/audio.mic") as r_mic:
        t = Time(CFG.update_rate)
        start = time.monotonic()
        while time.monotonic() - start < DURATION:
            if r_mic.ready():
                stale, data = r_mic.get()
                if stale: continue
                recorded.append(data["audio"])
            t.tick()

    print("[+] Recording complete. Concatenating...")

    audio = np.concatenate(recorded, axis=0)

    # Optional: Clip to avoid overflow
    np.clip(audio, -1.0, 1.0, out=audio)
    print(f"[+] Playing back {len(audio) / SAMPLE_RATE:.2f} seconds...")

    with Writer("/audio.speaker", Type("speakerphone_audio")) as w_speak:
        t = Time(CFG.update_rate)
        for i in range(0, len(audio), CHUNK):
            chunk = audio[i:i + CHUNK]
            if chunk.shape[0] < CHUNK:
                pad = np.zeros((CHUNK - chunk.shape[0], CHANNELS), dtype=np.float32)
                chunk = np.vstack((chunk, pad))
            with w_speak.buf() as b:
                b["audio"] = chunk
            t.tick()

    print("[+] Done.")
