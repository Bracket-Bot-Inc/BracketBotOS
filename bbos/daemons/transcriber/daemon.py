from bbos import Reader, Writer, Type, Config
from bracketbot_ai import Transcriber
import numpy as np, threading, queue, time

CFG_SPKPN = Config('speakerphone')
CFG_TRNS  = Config('transcriber')

class Buffer:
    def __init__(self, shape):
        self.buffer = np.zeros(shape)
        self.index = 0
        self.full = False

    def add(self, data):
        self.buffer[self.index] = data
        if self.index == len(self.buffer) - 1:
            self.full = True
        else:
            self.full = False
        self.index = (self.index + 1) % len(self.buffer)

    def ready(self):
        return self.full

def infer_worker(model, in_q, out_q):
    while True:
        frame = in_q.get()
        out = model(frame)              # blocking, off main thread
        txt = out.text
        out_q.put(txt)

def main(r_mic, w_text):
    model = Transcriber(device=-1, chunk_duration=CFG_TRNS.chunk_ms/1e3, context_chunk_count=CFG_TRNS.context_chunk_count)
    buffer = Buffer((CFG_TRNS.chunk_ms // CFG_SPKPN.mic_ms, CFG_SPKPN.mic_chunk_size))
    in_q  = queue.Queue(maxsize=3)
    out_q = queue.Queue(maxsize=4)

    # spin up worker
    t = threading.Thread(
        target=infer_worker,
        args=(model, in_q, out_q),
        daemon=True,
    )
    t.start()
    i = 0
    last_enq = -1  # simple guard to avoid enqueuing every hop if you later change hop<win
    while True:
        if r_mic.ready():
            frame = r_mic.data['audio'].flatten()  # int16 [HOP_SAMP]
            buffer.add(frame)
            if buffer.ready():
                try:
                    in_q.put_nowait(buffer.buffer)
                except queue.Full:
                    # drop oldest: clear one and reinsert (keeps capture real-time)
                    try: in_q.get_nowait()
                    except queue.Empty: pass
                    in_q.put_nowait(buffer.buffer)

        try:
            with w_text.buf() as buf:
                buf['text'] = out_q.get_nowait() if w_text._update() else ""
        except queue.Empty:
            pass

if __name__ == "__main__":
    with Reader("audio.mic") as r_mic, \
         Writer("transcript", Type('transcriber_text')) as w_text:
        main(r_mic, w_text)