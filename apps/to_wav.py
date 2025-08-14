# /// script
# dependencies = [
#   "ultralytics",
#   "turbojpeg-rpi",
#   "openvino",
#   "bbos",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
import numpy as np
import soundfile as sf
import time
from bbos import Reader, Config

CFG       = Config("speakerphone")     # your usual config object
DURATION  = 10.0                        # seconds to capture
OUT_PATH  = "mic_capture.wav"          # output file

# --------------------------------------------------------------------------- #
# 1. Open a SoundFile object once, in streaming‑write mode.
#    We keep the mic’s native sample‑rate / channel‑count so nothing changes.
# --------------------------------------------------------------------------- #
print(f"[+] Writing {DURATION} s of mic audio to {OUT_PATH} …")
print(f"[+] Sample rate: {CFG.mic_sample_rate}")
print(f"[+] Channels: {CFG.mic_channels}")

sf_writer = sf.SoundFile(
    OUT_PATH,
    mode='w',
    samplerate=CFG.mic_sample_rate,    # e.g. 16000
    channels=CFG.mic_channels,         # 1 for mono, 2 for stereo mic
    subtype='PCM_16'                    # 32‑bit float PCM
)

print(f"[+] Writing {DURATION} s of mic audio to {OUT_PATH} …")

# --------------------------------------------------------------------------- #
# 2. Stream mic chunks directly into the file.
# --------------------------------------------------------------------------- #
with Reader("audio.mic") as r_mic:
    start = time.monotonic()
    i = 0
    while time.monotonic() - start < DURATION:
        if r_mic.ready():
            i += 1
            chunk = r_mic.data["audio"]
            sf_writer.write(chunk)
            print(r_mic.data["timestamp"])
sf_writer.close()
print(f"[+] Wrote {i} chunks")
print(f"[+] Done. Saved to {OUT_PATH}")
