# /// script
# dependencies = [
#   "bbos",
#   "soundfile",          # lightweight, perfect for streamed WAV input
#   "scipy"          # lightweight, perfect for streamed WAV input
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
import numpy as np
import soundfile as sf
import time
from bbos import Writer, Config, Type

CFG       = Config("speakerphone")     # your usual config object
INPUT_PATH = "mic_capture.wav"         # input file to play

# --------------------------------------------------------------------------- #
# 1. Open the WAV file for reading
# --------------------------------------------------------------------------- #
print(f"[+] Reading audio from {INPUT_PATH} …")
try:
    sf_reader = sf.SoundFile(INPUT_PATH, mode='r')
    print(f"[+] Sample rate: {sf_reader.samplerate}")
    print(f"[+] Channels: {sf_reader.channels}")
    print(f"[+] Duration: {len(sf_reader) / sf_reader.samplerate:.2f} seconds")
    
    # --------------------------------------------------------------------------- #
    # 2. Stream WAV chunks to speaker with resampling from 16kHz to 48kHz
    # --------------------------------------------------------------------------- #
    with Writer("audio.speaker", Type("speakerphone_speaker")) as w_speaker:
        i = 0

        start = time.monotonic()
        while True:
            # Read input chunk at file's sample rate (typically 16kHz)
            input_chunk = sf_reader.read(CFG.speaker_chunk_size, dtype='int16')
            if len(input_chunk) == 0:  # End of file
                break
            i += 1
            # Send to speaker - Writer.buf() handles timing automatically
            before = time.monotonic()
            with w_speaker.buf() as b:
                b['audio'] = input_chunk.reshape(-1, CFG.speaker_channels)
            after = time.monotonic()
        end = time.monotonic()
        print(f"[+] Total time: {end - start:.6f}s")
    sf_reader.close()
    print(f"[+] Played {i} chunks")
    print(f"[+] Done. Finished playing {INPUT_PATH}")
    
except FileNotFoundError:
    print(f"[-] Error: Could not find {INPUT_PATH}")
except Exception as e:
    print(f"[-] Error: {e}")
