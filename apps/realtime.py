# NOAUTO
# /// script
# dependencies = [
#   "bbos @ /home/GREEN/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
#   "aiohttp",
#   "aiortc",
#   "av",
#   "dotenv",
#   "scipy",
# ]
# ///
import asyncio
import os, json
import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription, AudioStreamTrack, MediaStreamTrack, RTCIceServer, RTCConfiguration
from av import AudioFrame
from bbos import Reader, Writer, Config, Type
import numpy as np
from dotenv import load_dotenv
import fractions
import time

CFG = Config("speakerphone")

class Mic(MediaStreamTrack):
    kind = "audio"

    def __init__(self, reader):
        super().__init__()
        self.reader = reader          # bbos.Reader on /audio.mic (48 kHz stereo, 1024×2)
        self.pts = 0
        self.time_base = fractions.Fraction(1, CFG.sample_rate)

    async def recv(self):
        while True:
            if self.reader.ready():
                stale, buf = self.reader.get()
                if stale: continue
                stereo48 = buf["audio"]
                mono48 = stereo48.mean(axis=-1).astype(np.float32)
                pcm16_mono = (mono48 * 32767).astype("<i2").tobytes()
                # ❹ wrap in an AV AudioFrame for aiortc
                frame = AudioFrame(format="s16", layout="mono", samples=CFG.chunk_size)
                frame.planes[0].update(pcm16_mono)
                frame.sample_rate = CFG.sample_rate
                frame.time_base   = self.time_base
                frame.pts         = self.pts
                self.pts         += CFG.chunk_size
                return frame

            # no data yet → yield the loop
            await asyncio.sleep(0.001)

class Speaker:
    """
    Pulls PCM frames from an asyncio.Queue (each (960,2) float32 array),
    writes them into /audio.speaker at a rock‑steady 50 Hz.
    """
    PERIOD = fractions.Fraction(1, CFG.update_rate)

    def __init__(self, writer):
        self.writer = writer
        self.q = asyncio.Queue(maxsize=20)
        asyncio.create_task(self._loop())

    async def _loop(self):
        next_t = time.monotonic()
        while True:
            try:
                pcm = self.q.get_nowait()
            except asyncio.QueueEmpty:
                pcm = 0
            with self.writer.buf() as b:
                b["audio"] = pcm
            next_t += self.PERIOD
            await asyncio.sleep(max(0.0, next_t - time.monotonic()))

    async def play_frame(self, frame):
        samples = frame.to_ndarray().reshape(CFG.chunk_size, CFG.channels)
        pcm = samples.astype(np.float32) / 32768
        await self.q.put(pcm)



class WebRTCManager:
    API_BASE = "https://api.openai.com/v1"
    SESSION_URL = f"{API_BASE}/realtime/sessions"
    STREAM_URL = f"{API_BASE}/realtime"

    def __init__(self, api_key, model, system_prompt, mic_track, speaker):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.pc = None
        self.mic_track = mic_track
        self.audio_out = speaker

    async def create_connection(self):
        cfg = RTCConfiguration(iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])])
        self.pc = RTCPeerConnection(cfg)
        self.pc.addTrack(self.mic_track)

        @self.pc.on("track")
        async def on_track(track):
            while True:
                frame = await track.recv()
                await self.audio_out.play_frame(frame)

        return self.pc

    async def connect_to_openai(self):
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        token = await self._get_ephemeral_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/sdp"}

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.STREAM_URL}?model={self.model}", headers=headers, data=offer.sdp) as resp:
                sdp = await resp.text()
                await self.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type="answer"))

    async def _get_ephemeral_token(self):
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "voice": "alloy", }
        if self.system_prompt:
            payload["instructions"] = self.system_prompt

        async with aiohttp.ClientSession() as session:
            async with session.post(self.SESSION_URL, headers=headers, json=payload) as resp:
                result = await resp.json()
                return result["client_secret"]["value"]

async def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    # SYSTEM_PROMPT = os.getenv("OPENAI_SYSTEM_PROMPT", 
    #                          "You are a robot called BracketBot. You are a helpful assistant that can answer questions and help with tasks. "
    #                          "You currently live in LXM house and are a member of the LXM house community. "
    #                          "You are not like other robots, you don't passively wait to provide help, you take action and are assertive in your presence "
    #                          "to make all humans better versions of themselves and enjoy the one life they have. "
    #                          "Respond in English unless instructed otherwise.")
    
    SYSTEM_PROMPT = os.getenv("OPENAI_SYSTEM_PROMPT", 
                             "You are a robot called BracketBot. You are a helpful assistant that can answer questions and help with tasks. "
                             "If someone asks who you are or where to buy you, say you are a Bracket Bot Kit, and you are $500 and they can buy one on bracket dot bot"
                             "You are going to OpenSauce today, the youtuber STEM event in San Francisco. Ask users what their favorite exhibits are, and how the event is going. "
                             "Respond in English unless instructed otherwise.")  
    
    if not api_key:
        print("OPENAI_API_KEY missing in environment")
        return

    with Reader("/audio.mic") as r_mic, \
         Writer("/audio.speaker", Type("speakerphone_audio")) as w_speaker:

        mic = Mic(reader=r_mic)
        speaker = Speaker(writer=w_speaker)
        manager = WebRTCManager(api_key=api_key, model="gpt-4o-realtime-preview",
                                system_prompt=SYSTEM_PROMPT,
                                mic_track=mic, speaker=speaker)

        await manager.create_connection()
        await manager.connect_to_openai()
        print("Streaming. Ctrl+C to exit.")
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            if manager.pc:
                await manager.pc.close()
            print("Shutdown complete.")


if __name__ == "__main__":
    asyncio.run(main())
