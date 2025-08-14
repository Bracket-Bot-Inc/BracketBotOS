# /// script
# dependencies = [
#   "numpy",
#   "aiohttp",
#   "aiortc",
#   "av",
#   "dotenv",
#   "scipy",
#   "bbos",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
import asyncio
import os, json
import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription, AudioStreamTrack, RTCIceServer, RTCConfiguration
from av import AudioFrame
from bbos import Reader, Writer, Config, Type
import numpy as np
from dotenv import load_dotenv
import threading
import fractions
from scipy import signal
import queue

CFG = Config("speakerphone")
REALTIME_INPUT_SAMPLE_RATE = 24000  # OpenAI Realtime API expects 24kHz
REALTIME_OUTPUT_SAMPLE_RATE = 48000
REALTIME_OUTPUT_MS = 20
OUTPUT_BASE_CHUNK_MS = np.gcd(CFG.speaker_ms, REALTIME_OUTPUT_MS)
REALTIME_OUTPUT_CHUNKS = REALTIME_OUTPUT_MS // OUTPUT_BASE_CHUNK_MS

class Mic(AudioStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.queue = queue.Queue(maxsize=20)
        self.time_base = fractions.Fraction(1, REALTIME_INPUT_SAMPLE_RATE)
        self.pts = 0

    async def recv(self):
        while True:
            try:
                frame = self.queue.get_nowait()
                break
            except queue.Empty:
                await asyncio.sleep(0.005)
        try:
            af = AudioFrame.from_ndarray(frame, format='s16', layout='mono')
        except Exception as e:
            return None
        af.sample_rate = REALTIME_INPUT_SAMPLE_RATE
        af.pts = self.pts
        self.pts += len(frame)
        return af

class Speaker:
    def __init__(self):
        self.queue = queue.Queue(maxsize=20)

    async def send(self, frame):
        try:
            ch = len(frame.layout.channels)
            audio_data = frame.to_ndarray().reshape(-1, ch)[:,0]
            assert audio_data.flatten().shape[0] == REALTIME_OUTPUT_SAMPLE_RATE // 1000 * REALTIME_OUTPUT_MS, print("Got ", audio_data.shape)
            audio_data = audio_data.reshape(REALTIME_OUTPUT_CHUNKS, -1)
            for i in range(REALTIME_OUTPUT_CHUNKS):
                audio_data_i = audio_data[i].flatten()
                try:
                    self.queue.put_nowait(audio_data_i)
                except queue.Full:
                    try: self.queue.get_nowait()
                    except queue.Empty: pass
                    self.queue.put_nowait(audio_data_i)
        except Exception as e:
            print(f"Speaker error: {e}")

class WebRTCManager:
    API_BASE = "https://api.openai.com/v1"
    SESSION_URL = f"{API_BASE}/realtime/sessions"
    STREAM_URL = f"{API_BASE}/realtime"

    def __init__(self, model, mic_track, speaker):
        print("Loading .env")
        print(os.getcwd())
        load_dotenv(dotenv_path=".env")

        api_key = os.getenv("OPENAI_API_KEY")
        assert api_key, print("OPENAI_API_KEY missing in environment")
        system_prompt = os.getenv("OPENAI_SYSTEM_PROMPT", 
                                "Say hello and introduce yourself as BracketBot. Always respond in English. You are currently being built by Brian and Raghava at Steinmetz Engineering.")  
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.pc = None
        self.mic_track = mic_track
        self.audio_out = speaker

    async def create_connection(self):
        cfg = RTCConfiguration(iceServers=[RTCIceServer(urls=["stun:stun.l.google.com:19302"])])
        self.pc = RTCPeerConnection(cfg)
        
        # Create data channel for OpenAI commands
        self.data_channel = self.pc.createDataChannel("oai-events")
        
        @self.data_channel.on("open")
        def on_datachannel_open():
            print("Data channel opened")
            asyncio.create_task(self._send_initial_messages())
        
        # Add mic track and setup handlers
        self.pc.addTrack(self.mic_track)

        @self.pc.on("track")
        async def on_track(track):
            print(f"Received {track.kind} track")
            if track.kind == "audio":
                asyncio.create_task(self._handle_audio_track(track))

        @self.pc.on("connectionstatechange")
        async def on_connectionstatechange():
            print(f"Connection state: {self.pc.connectionState}")

        return self.pc

    async def _handle_audio_track(self, track):
        try:
            while True:
                frame = await track.recv()
                await self.audio_out.send(frame)
                await asyncio.sleep(0.005)
        except Exception as e:
            print(f"Audio track error: {e}")

    async def connect_to_openai(self):
        offer = await self.pc.createOffer()
        await self.pc.setLocalDescription(offer)
        
        token = await self._get_ephemeral_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/sdp"}

        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self.STREAM_URL}?model={self.model}", headers=headers, data=offer.sdp) as resp:
                if resp.status not in [200, 201]:
                    error_text = await resp.text()
                    raise Exception(f"OpenAI API error {resp.status}: {error_text}")
                    
                sdp_answer = await resp.text()
                answer = RTCSessionDescription(sdp=sdp_answer, type="answer")
                await self.pc.setRemoteDescription(answer)
                
                # Wait for connection
                await self._wait_for_connection()

    async def _wait_for_connection(self):
        max_wait = 15
        start_time = asyncio.get_event_loop().time()
        
        while True:
            if self.pc.connectionState == "connected":
                print("WebRTC connected!")
                return
            elif self.pc.connectionState in ["failed", "closed"]:
                raise Exception(f"WebRTC connection failed: {self.pc.connectionState}")
            elif asyncio.get_event_loop().time() - start_time > max_wait:
                raise Exception("WebRTC connection timeout")
                
            await asyncio.sleep(0.5)

    async def _send_initial_messages(self):
        try:
            # Configure session
            session_update = {
                "type": "session.update",
                "session": {
                    "modalities": ["audio"],
                    "instructions": self.system_prompt,
                    "voice": "shimmer",
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 500,
                        "create_response": True,
                        "interrupt_response": False,
                    }
                }
            }
            self.data_channel.send(json.dumps(session_update))
            # Trigger initial response
            await asyncio.sleep(0.1)
            response_create = {
                "type": "response.create",
                "response": {
                    "modalities": ["audio"],
                    "instructions": "Say hello and introduce yourself as BracketBot. Always respond in English. You are currently being built by Brian and Raghava at Steinmetz Engineering."
                }
            }
            self.data_channel.send(json.dumps(response_create))
            
        except Exception as e:
            print(f"Failed to send initial messages: {e}")

    async def _get_ephemeral_token(self):
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"model": self.model, "voice": "alloy"}
        if self.system_prompt:
            payload["instructions"] = self.system_prompt

        async with aiohttp.ClientSession() as session:
            async with session.post(self.SESSION_URL, headers=headers, json=payload) as resp:
                if resp.status not in [200, 201]:
                    error_text = await resp.text()
                    raise Exception(f"Token request failed: {resp.status}")
                
                result = await resp.json()
                return result["client_secret"]["value"]
    async def start(self, stop_event):
        await self.create_connection()
        await self.connect_to_openai()
        print("Streaming. Ctrl+C to exit.")
        try:
            while not stop_event.is_set():
                await asyncio.sleep(1)
            if self.pc:
                await self.pc.close()
            print("Shutdown complete.")
        except Exception as e:
            print(f"Error: {e}")

def main():
        mic = Mic()
        speaker = Speaker()
        manager = WebRTCManager(model="gpt-4o-realtime-preview",
                                mic_track=mic, speaker=speaker)

        stop_event = threading.Event()        
        thread = threading.Thread(target=asyncio.run, args=(manager.start(stop_event),))
        thread.start()
        j = 0
        with Reader("audio.mic") as r_mic, \
            Writer("audio.speaker", Type("speakerphone_speaker")) as w_speaker:
            speaker_chunks = CFG.speaker_ms // OUTPUT_BASE_CHUNK_MS
            full_chunk = np.zeros((speaker_chunks, REALTIME_OUTPUT_SAMPLE_RATE // 1000 * OUTPUT_BASE_CHUNK_MS))
            resampled = np.zeros((CFG.speaker_chunk_size, CFG.speaker_channels))
            while True:
                if r_mic.ready():
                    resampled = signal.resample_poly(r_mic.data['audio'].astype(np.float32), 
                                                REALTIME_INPUT_SAMPLE_RATE, CFG.mic_sample_rate)
                    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
                    try:
                        mic.queue.put_nowait(resampled.reshape(1, -1))
                    except queue.Full:
                        # drop oldest: clear one and reinsert (keeps capture real-time)
                        try: mic.queue.get_nowait()
                        except queue.Empty: pass
                        mic.queue.put_nowait(resampled)
                if w_speaker._update():
                    j += 1
                    print("Speaker update: ", j)
                    for i in range(speaker_chunks):
                        try:
                            full_chunk[i] = speaker.queue.get_nowait()
                        except queue.Empty:
                            print("Empty queue")
                            full_chunk[i] = 0
                    resampled = signal.resample_poly(full_chunk.flatten().astype(np.float32), 
                                                CFG.speaker_sample_rate, REALTIME_OUTPUT_SAMPLE_RATE)
                    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
                    with w_speaker.buf() as b:
                        b['audio'] = resampled.reshape(-1, CFG.speaker_channels)
        stop_event.set()
        thread.join()
if __name__ == "__main__":
    main()