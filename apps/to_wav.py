# /// script
# dependencies = [
#   "bbos @ /home/bracketbot/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
#   "soundfile"          # lightweight, perfect for streamed WAV output
# ]
# ///
import numpy as np
import soundfile as sf
import time
from bbos import Reader, Config

CFG       = Config("speakerphone")     # your usual config object
DURATION  = 5.0                        # seconds to capture
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
with Reader("/audio.mic") as r_mic:
    start = time.monotonic()

    while time.monotonic() - start < DURATION:
        if r_mic.ready():
            # Grab the chunk from shared memory
            print("🎙️  got chunk", r_mic.data["audio"][0, :4])  # first few samples
            chunk = r_mic.data["audio"]          # shape (chunk_size, channels)
        else:
            # Mic not ready?  Write silence for that slice.
            chunk = np.zeros((CFG.mic_chunk_size,
                              CFG.mic_channels), dtype=np.int16)

        sf_writer.write(chunk)   # 🔑 stream the chunk straight into the WAV

# --------------------------------------------------------------------------- #
# 3. Always close the writer so the WAV header is finalized.
# --------------------------------------------------------------------------- #
sf_writer.close()
print(f"[+] Done. Saved to {OUT_PATH}")
