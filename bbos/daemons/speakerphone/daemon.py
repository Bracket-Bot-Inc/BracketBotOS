from bbos import Writer, Reader, Type, Config, Time
from bbos.os_utils import config_realtime_process, Priority
import sounddevice as sd
import numpy as np

if __name__ == "__main__":
    CFG = Config("speakerphone")
    config_realtime_process(2, Priority.CTRL_HIGH)

    assert CFG.chunk_size is not None, "CFG.chunk_size must be defined"
    blocksize = CFG.chunk_size  # frames per block

    sd.check_input_settings(device=CFG.device, samplerate=CFG.sample_rate, channels=CFG.channels)
    sd.check_output_settings(device=CFG.device, samplerate=CFG.sample_rate, channels=CFG.channels)

    with Reader("/audio.speaker") as r_speak, \
         Writer("/audio.mic", Type("speakerphone_audio")) as w_mic:

        def callback(indata, outdata, frames, time_info, status):
            if r_speak.ready():
                stale, data = r_speak.get()
                if not stale:
                    outdata[:] = data["audio"]
            if not r_speak.ready() or stale:
                outdata[:] = 0
            indata *= CFG.gain 
            indata = np.clip(indata, -1.0, 1.0)
            with w_mic.buf() as b:
                b["audio"][:] = indata  # mic input

        with sd.Stream(
            samplerate=CFG.sample_rate,
            blocksize=blocksize,
            device=(CFG.device, CFG.device),
            dtype='float32',
            channels=CFG.channels,
            callback=callback,
        ):
            t = Time(CFG.update_rate)
            try:
                while True:
                    t.tick()
            except KeyboardInterrupt:
                pass

    print(t.stats)