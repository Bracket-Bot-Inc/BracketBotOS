from bbos import Reader, Writer, Type, Config
from bracketbot_ai import Transcriber
import numpy as np, threading, queue, time
import soundfile as sf

CFG_SPKPN = Config('speakerphone')
CFG_TRNS  = Config('transcriber')

OVERLAP_CHUNKS = CFG_TRNS.overlap_ms // CFG_SPKPN.mic_ms
CHUNK_LENGTH = CFG_TRNS.chunk_ms // CFG_SPKPN.mic_ms

class PeekQueue(queue.Queue):
    def peek(self,i):
        with self.mutex:  # use Queue’s internal lock
            return self.queue[i] if self.queue else None

def infer_worker(model, in_q, out_q):
    chunk = np.zeros((CHUNK_LENGTH, CFG_SPKPN.mic_chunk_size), dtype=np.float32)
    while True:
        for i in range(CHUNK_LENGTH - OVERLAP_CHUNKS):
            chunk[i] = in_q.get()
        for i in range(OVERLAP_CHUNKS):
            while len(in_q.queue) <= i: time.sleep(0.001)
            chunk[CHUNK_LENGTH - OVERLAP_CHUNKS + i] = in_q.peek(i)
        #sf.write("chunk.wav", chunk.flatten(), CFG_SPKPN.mic_sample_rate)
        out = model(chunk.flatten())
        txt = out.text
        print(txt)
        out_q.put(txt)

def main(r_mic, w_text):
    model = Transcriber(device=-1, chunk_duration=CFG_TRNS.chunk_ms/1e3)
    in_q  = PeekQueue(maxsize=CHUNK_LENGTH*2)
    out_q = PeekQueue(maxsize=CHUNK_LENGTH*2)

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
            frame = r_mic.data['audio'].flatten().astype(np.float32) / 32768.0
            try:
                in_q.put_nowait(frame)
            except queue.Full:
                # drop oldest: clear one and reinsert (keeps capture real-time)
                try: in_q.get_nowait()
                except queue.Empty: pass
                in_q.put_nowait(frame)
        if w_text._update():
            try:
                txt = out_q.get_nowait()
            except queue.Empty:
                txt = ""
        w_text['text'] = txt

if __name__ == "__main__":
    with Reader("audio.mic") as r_mic, \
         Writer("transcript", Type('transcriber_text')) as w_text:
        main(r_mic, w_text)