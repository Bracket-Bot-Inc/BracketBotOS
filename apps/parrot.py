# /// script
# dependencies = [
#   "bbos @ /home/bracketbot/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
#   "scipy"
# ]
# ///
import numpy as np
from bbos import Writer, Reader, Type, Config
from scipy.signal import resample_poly
import time

CFG = Config("speakerphone")
DURATION = 5.0  # seconds

if __name__ == "__main__":
    recorded = []

    print(f"[+] Recording for {DURATION} seconds...")

    with Reader("/audio.mic") as r_mic:
        start = time.monotonic()
        while time.monotonic() - start < DURATION:
            if r_mic.ready():
                recorded.append(r_mic.data["audio"])
            else:
                recorded.append(np.zeros((CFG.mic_chunk_size, CFG.mic_channels), dtype=np.float32))

    print("[+] Recording complete. Concatenating...")

    audio = np.concatenate(recorded, axis=0)
    # Resample to match speaker sample rate
    audio = resample_poly(audio.squeeze(), up=3, down=1)
    print(audio.shape)
    audio_48k_stereo = np.stack([audio, audio], axis=-1)  # shape (N, 2)
    print(audio_48k_stereo.shape)

    audio = np.clip(audio, -1.0, 1.0)

    # Optional: Clip to avoid overflow
    print(len(audio) / CFG.speaker_sample_rate)
    print(f"[+] Playing back {len(audio) / CFG.speaker_sample_rate:.2f} seconds...")

    with Writer("/audio.speaker", Type("speakerphone_audio")(CFG.speaker_chunk_size, CFG.speaker_channels)) as w_speak:
        for i in range(0, len(audio_48k_stereo), CFG.speaker_chunk_size):
            chunk = audio_48k_stereo[i:i + CFG.speaker_chunk_size]
            if chunk.shape[0] < CFG.speaker_chunk_size:
                pad = np.zeros((CFG.speaker_chunk_size - chunk.shape[0], CFG.speaker_channels), dtype=np.float32)
                chunk = np.vstack((chunk, pad))
            with w_speak.buf() as b:
                b["audio"][:] = chunk

    print("[+] Done.")
