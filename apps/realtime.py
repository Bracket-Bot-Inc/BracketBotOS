# /// script
# dependencies = [
#   "numpy",
#   "aiohttp",
#   "aiortc",
#   "av",
#   "dotenv",
#   "scipy",
#   "bbos @ /home/bracketbot/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
# ]
# ///
import asyncio
import os, json
import aiohttp
from aiortc import RTCPeerConnection, RTCSessionDescription, AudioStreamTrack, RTCIceServer, RTCConfiguration
from av import AudioFrame
from bbos import Reader, Writer, Config, Type
import numpy as np
from dotenv import load_dotenv
import fractions
from scipy import signal

CFG = Config("speakerphone")
REALTIME_SAMPLE_RATE = 24000  # OpenAI Realtime API expects 24kHz

class Mic(AudioStreamTrack):
    kind = "audio"

    def __init__(self, reader):
        super().__init__()
        self.reader = reader
        self.pts = 0
        self.time_base = fractions.Fraction(1, REALTIME_SAMPLE_RATE)

    async def recv(self):
        while True:
            if self.reader.ready():
                audio_data = self.reader.data["audio"]
                
                # Convert stereo to mono if needed
                if audio_data.shape[1] == 2:
                    mono_data = ((audio_data[:, 0] + audio_data[:, 1]) // 2).astype(np.int16)
                else:
                    mono_data = audio_data[:, 0].astype(np.int16)
                
                # Resample from 16kHz to 24kHz for OpenAI
                if CFG.mic_sample_rate != REALTIME_SAMPLE_RATE:
                    resampled = signal.resample_poly(mono_data.astype(np.float32), 
                                                   REALTIME_SAMPLE_RATE, CFG.mic_sample_rate)
                    resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
                else:
                    resampled = mono_data
                
                # Create AudioFrame with 24kHz sample rate
                frame = AudioFrame.from_ndarray(resampled.reshape(1, -1), format='s16', layout='mono')
                frame.sample_rate = REALTIME_SAMPLE_RATE
                frame.pts = self.pts
                self.pts += len(resampled)
                return frame
            await asyncio.sleep(0.001)

class Speaker:
    def __init__(self, writer):
        self.writer = writer
        self.buffer = np.array([], dtype=np.int16)

    async def play_frame(self, frame):
        try:
            audio_data = frame.to_ndarray()
            #print(f"Raw frame: shape={audio_data.shape}, max_val={np.max(np.abs(audio_data))}")
            
            # Flatten if needed (remove extra dimensions)
            if audio_data.ndim > 1 and audio_data.shape[0] == 1:
                audio_data = audio_data.flatten()
            
            # Check what OpenAI actually reports
            frame_sample_rate = getattr(frame, 'sample_rate', 48000)
            
            if CFG.speaker_sample_rate != frame_sample_rate:
                resampled = signal.resample_poly(audio_data.astype(np.float32), 
                                               CFG.speaker_sample_rate, frame_sample_rate * 2)
                resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
                #print(f"After resample: {len(resampled)} samples, max_val={np.max(np.abs(resampled))}")
            else:
                resampled = audio_data.astype(np.int16)
            
            # Add to buffer
            self.buffer = np.concatenate([self.buffer, resampled])
            
            # Only write when we have enough for one chunk
            if len(self.buffer) >= CFG.speaker_chunk_size:
                chunk = self.buffer[:CFG.speaker_chunk_size]
                self.buffer = self.buffer[CFG.speaker_chunk_size:]
                # Convert to proper channels
                if CFG.speaker_channels == 2:
                    chunk_shaped = np.repeat(chunk.reshape(-1, 1), 2, axis=1)
                else:
                    chunk_shaped = chunk.reshape(-1, 1)
                
                #print(f"Writing chunk: {chunk_shaped.shape}, max_val={np.max(np.abs(chunk_shaped))}")
                
                # Write one chunk - match bbos timing
                with self.writer.buf() as b:
                    b['audio'] = chunk_shaped
                
        except Exception as e:
            print(f"Speaker error: {e}")

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
                await self.audio_out.play_frame(frame)
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

async def main():
    load_dotenv()
    api_key = os.getenv("OPENAI_API_KEY")
    
    SYSTEM_PROMPT = os.getenv("OPENAI_SYSTEM_PROMPT", 
                             "Say hello and introduce yourself as BracketBot. Always respond in English. You are currently being built by Brian and Raghava at Steinmetz Engineering.")  
    
    if not api_key:
        print("OPENAI_API_KEY missing in environment")
        return

    with Reader("/audio.mic") as r_mic, \
        Writer("/audio.speaker", Type("speakerphone_speaker")) as w_speaker:

        mic = Mic(reader=r_mic)
        speaker = Speaker(writer=w_speaker)
        manager = WebRTCManager(api_key=api_key, model="gpt-4o-realtime-preview",
                                system_prompt=SYSTEM_PROMPT,
                                mic_track=mic, speaker=speaker)

        try:
            await manager.create_connection()
            await manager.connect_to_openai()
            print("Streaming. Ctrl+C to exit.")
            
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            if manager.pc:
                await manager.pc.close()
            print("Shutdown complete.")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())