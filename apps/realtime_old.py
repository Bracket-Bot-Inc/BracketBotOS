
# /// script
# dependencies = [
#   "bbos @ /home/bracketbot/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
#   "aiohttp",
#   "aiortc",
#   "av",
#   "dotenv",
#   "scipy",
#   "sounddevice",
#   "numpy",
#   "websockets",
#   "openai",
#   "pyaudio",
#   "python-dotenv",
#   "aiortc",
#   "scipy",
# ]
# ///

"""
OpenAI Realtime WebRTC Single-file Example - Compact Version

Requirements: sounddevice, numpy, websockets, openai, aiohttp, pyaudio, python-dotenv, aiortc, scipy

Install: pip install sounddevice numpy websockets openai aiohttp pyaudio python-dotenv aiortc scipy

Usage:
1. Create a .env file with OPENAI_API_KEY=your-key-here
2. Run: python openai_realtime_example.py
3. Speak into your microphone
4. Press Ctrl+C to exit
"""

import asyncio
import os
import logging
import numpy as np
import sounddevice as sd
import aiohttp
import json
from collections import deque
from typing import Optional, Callable, Dict, Any, Deque, Tuple
from aiortc import RTCPeerConnection, RTCSessionDescription, MediaStreamTrack, RTCConfiguration, RTCIceServer
from aiortc.mediastreams import MediaStreamError
from av import AudioFrame
from dotenv import load_dotenv
from scipy import signal

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Audio constants
RESPEAKER_SAMPLE_RATE = 16000  # ReSpeaker hardware sample rate
REALTIME_SAMPLE_RATE = 24000   # OpenAI Realtime API sample rate for sending
OPUS_SAMPLE_RATE = 48000      # Opus codec decodes to 48kHz
SAMPLE_RATE = RESPEAKER_SAMPLE_RATE  # Default sample rate
CHANNELS = 2  # EMEET OfficeCore M0 Plus has 2 channels
DTYPE = np.int16  # Keep int16 for input
FRAME_DURATION_MS = 20  # OpenAI recommends 20ms frames
DEFAULT_CHANNELS = 2
DEFAULT_BLOCK_SIZE = int(RESPEAKER_SAMPLE_RATE * FRAME_DURATION_MS / 1000)  # 320 samples at 16kHz
OUTPUT_DTYPE = np.int16  # Use int16 for output too


class AudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self, audio_handler):
        super().__init__()
        self._audio_handler = audio_handler
        self._queue = asyncio.Queue()
        self._task = None

    async def recv(self):
        if self._task is None:
            self._task = asyncio.create_task(self._audio_handler.start_recording(self._queue))
        try:
            return await self._queue.get()
        except Exception as e:
            logger.error(f"Error receiving audio frame: {str(e)}")
            raise MediaStreamError("Failed to receive audio frame")


class AudioHandler:
    def __init__(self, sample_rate=RESPEAKER_SAMPLE_RATE, channels=CHANNELS, frame_duration=FRAME_DURATION_MS, 
                 dtype=DTYPE, device=None):
        self.sample_rate = sample_rate
        self.channels = channels
        self.frame_duration = frame_duration
        self.dtype = dtype
        self.device = device
        self.frame_size = int(sample_rate * frame_duration / 1000)
        self.stream = None
        self.is_recording = False
        self.is_paused = False
        self._loop = None
        self._pts = 0

    def create_audio_track(self):
        return AudioTrack(self)

    async def start_recording(self, queue):
        if self.is_recording:
            return

        self.is_recording = True
        self.is_paused = False
        self._loop = asyncio.get_running_loop()
        self._pts = 0

        try:
            def callback(indata, frames, time, status):
                if status:
                    logger.warning(f"Audio input status: {status}")
                if not self.is_paused:
                    # Handle multi-channel input (EMEET has 2 channels)
                    if indata.shape[1] > 1:
                        # Use first channel for simplicity (you could also mix both channels)
                        audio_data = indata[:, 0].copy()
                        logger.debug(f"Using channel 0 from {indata.shape[1]} available channels")
                    else:
                        audio_data = indata.copy()
                    
                    # Debug: Check if we're getting any input
                    input_max = np.max(np.abs(audio_data))
                    if input_max > 0.001:  # Log if there's any sound
                        logger.info(f"Microphone input detected: max_value={input_max}, dtype={audio_data.dtype}")
                    
                    if audio_data.dtype != self.dtype:
                        if self.dtype == np.int16:
                            audio_data = (audio_data * 32767).astype(self.dtype)
                        else:
                            audio_data = audio_data.astype(self.dtype)

                    # Resample from ReSpeaker's 16kHz to OpenAI's 24kHz
                    if self.sample_rate != REALTIME_SAMPLE_RATE:
                        resampled = signal.resample_poly(audio_data, REALTIME_SAMPLE_RATE, self.sample_rate)
                        resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
                    else:
                        resampled = audio_data
                    
                    # Create frame with proper sample rate
                    # Ensure resampled is 1D first
                    if resampled.ndim > 1:
                        resampled = resampled.flatten()
                    # Now reshape to (1, N) for AudioFrame
                    frame = AudioFrame.from_ndarray(resampled.reshape(1, -1), format='s16', layout='mono')
                    frame.sample_rate = REALTIME_SAMPLE_RATE
                    frame.pts = self._pts
                    self._pts += len(resampled)  # advance pts by samples at 24kHz
                    
                    # Debug: log when we send non-silent audio
                    max_val = np.max(np.abs(resampled))
                    if max_val > 100:  # Only log if there's actual sound
                        logger.info(f"Sending audio to OpenAI: max_value={max_val}")
                    
                    asyncio.run_coroutine_threadsafe(queue.put(frame), self._loop)

            # Use the default number of channels for the device
            input_channels = self.channels
            # Note: If using a ReSpeaker with 6 channels, you'd need to set input_channels = 6
            # For EMEET OfficeCore M0 Plus (device 2), use 2 channels
            logger.info(f"Using {input_channels} input channels for device {self.device}")
            
            self.stream = sd.InputStream(
                device=self.device,
                channels=input_channels,
                samplerate=self.sample_rate,
                dtype=self.dtype,
                blocksize=self.frame_size,
                callback=callback
            )
            self.stream.start()

            while self.is_recording:
                await asyncio.sleep(0.1)
        except Exception as e:
            logger.error(f"Error in audio recording: {str(e)}")
            raise
        finally:
            await self.stop()

    async def stop(self):
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None

    async def pause(self):
        self.is_paused = True

    async def resume(self):
        self.is_paused = False

    def set_device(self, device_id):
        self.device = device_id
        if self.stream:
            self.stream.stop()
            self.stream.close()
            self.stream = None


class AudioOutput:
    def __init__(self, sample_rate=RESPEAKER_SAMPLE_RATE, channels=1,  # Changed to mono output
                 dtype=OUTPUT_DTYPE, device=None, buffer_size=5):
        self.sample_rate = sample_rate
        self.channels = channels
        self.dtype = dtype
        self.device = device
        self.block_size = DEFAULT_BLOCK_SIZE
        self._buffer = deque(maxlen=buffer_size)
        self._queue = asyncio.Queue(maxsize=buffer_size)
        self.stream = None
        self.is_playing = False
        self._task = None
        self._remaining_data = None
        self.buffer_size = buffer_size

    async def start(self):
        if self.is_playing:
            return

        try:
            logger.info(f"Starting audio output: device={self.device}, samplerate={self.sample_rate}, channels={self.channels}")
            self.stream = sd.OutputStream(
                device=self.device,
                samplerate=self.sample_rate,
                channels=self.channels,
                dtype=self.dtype,
                blocksize=self.block_size,
                callback=self._audio_callback,
                prime_output_buffers_using_stream_callback=True
            )
            self.stream.start()
            self.is_playing = True
            self._task = asyncio.create_task(self._process_audio())
            logger.info(f"Audio output started successfully")
        except Exception as e:
            logger.error(f"Failed to start audio output: {str(e)}")
            raise

    async def stop(self):
        if not self.is_playing:
            return
            
        try:
            self.is_playing = False
            if self._task:
                self._task.cancel()
                self._task = None

            if self.stream:
                self.stream.stop()
                self.stream.close()
                self.stream = None

            self._buffer.clear()
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            logger.info("Audio output stopped")
        except Exception as e:
            logger.error(f"Error stopping audio output: {str(e)}")

    def _audio_callback(self, outdata, frames, time, status):
        if status:
            logger.warning(f"Audio output status: {status}")

        try:
            if len(self._buffer) > 0:
                data = self._buffer.popleft()
                # Check if data has any non-zero values
                max_val = np.max(np.abs(data))
                logger.debug(f"Playing audio: shape={data.shape}, outdata_shape={outdata.shape}, max_value={max_val}")
                
                # Reshape data to match output shape
                if len(data.shape) == 1 and len(outdata.shape) == 2:
                    # Reshape 1D array to 2D for mono output
                    data = data.reshape(-1, 1)
                
                # Ensure we only copy the amount of data that fits
                samples_to_copy = min(len(data), len(outdata))
                outdata[:samples_to_copy] = data[:samples_to_copy]
                # Fill any remaining space with silence
                if samples_to_copy < len(outdata):
                    outdata[samples_to_copy:].fill(0)
            else:
                if self.is_playing:  # Only log when we expect audio
                    logger.debug("No audio in buffer, outputting silence")
                outdata.fill(0)
        except Exception as e:
            logger.error(f"Error in audio callback: {str(e)}")
            outdata.fill(0)

    async def _process_audio(self):
        try:
            while self.is_playing:
                if len(self._buffer) < self._buffer.maxlen:
                    try:
                        data = await asyncio.wait_for(self._queue.get(), 0.1)
                        self._buffer.append(data)
                    except (asyncio.TimeoutError, asyncio.QueueEmpty):
                        continue
                    except Exception as e:
                        logger.error(f"Error getting data from queue: {str(e)}")
                else:
                    await asyncio.sleep(0.001)
        except asyncio.CancelledError:
            logger.info("Audio processing task cancelled")
        except Exception as e:
            logger.error(f"Error processing audio: {str(e)}")

    def resample_audio(self, audio_data, from_rate=REALTIME_SAMPLE_RATE, to_rate=RESPEAKER_SAMPLE_RATE):
        """Resample audio from one sample rate to another."""
        if from_rate == to_rate:
            return audio_data
        
        # Use scipy.signal.resample_poly for better quality
        resampled = signal.resample_poly(audio_data, to_rate, from_rate)
        
        # Ensure the output is the same type as input
        if audio_data.dtype == np.int16:
            resampled = np.clip(resampled, -32768, 32767).astype(np.int16)
            
        return resampled

    async def play_frame(self, frame):
        try:
            audio_data = frame.to_ndarray()
            
            # Get the actual sample rate from the frame
            frame_sample_rate = getattr(frame, 'sample_rate', REALTIME_SAMPLE_RATE)
            logger.debug(f"Received audio frame: shape={audio_data.shape}, dtype={audio_data.dtype}, frame_rate={frame_sample_rate}")
            
            # Flatten if needed (remove extra dimensions) 
            if audio_data.ndim > 1 and audio_data.shape[0] == 1:
                audio_data = audio_data.flatten()
            
            # Log raw audio stats before processing
            logger.debug(f"Raw audio stats: min={np.min(audio_data)}, max={np.max(audio_data)}, mean={np.mean(audio_data):.2f}")
            
            # IMPORTANT: OpenAI sends Opus audio which decodes to 48kHz, we need to resample to 16kHz for ReSpeaker
            # The frame from aiortc after Opus decoding is at 48kHz
            if self.sample_rate != OPUS_SAMPLE_RATE:
                logger.debug(f"Resampling from {OPUS_SAMPLE_RATE}Hz to {self.sample_rate}Hz")
                audio_data = self.resample_audio(audio_data, from_rate=OPUS_SAMPLE_RATE, to_rate=self.sample_rate)
            
            # Apply volume adjustment (increase to 2.0 for louder output)
            if audio_data.dtype == np.int16:
                audio_data = np.clip(audio_data * 2.0, -32768, 32767).astype(np.int16)
            
            # Log audio stats after volume adjustment
            logger.debug(f"After volume adjustment: min={np.min(audio_data)}, max={np.max(audio_data)}, mean={np.mean(audio_data):.2f}")
                
            # Prepend any leftover data from the previous call
            if self._remaining_data is not None:
                audio_data = np.concatenate((self._remaining_data, audio_data))
                self._remaining_data = None
                
            # Split into block_size chunks
            start = 0
            total_samples = len(audio_data)
            chunks_queued = 0
            
            while start + self.block_size <= total_samples:
                chunk = audio_data[start : start + self.block_size]
                
                # Only convert to stereo if needed (but we're using mono now)
                if self.channels == 2:
                    chunk = np.repeat(chunk[:, None], 2, axis=1)
                
                await self._queue.put(chunk)
                chunks_queued += 1
                start += self.block_size
                
            # Save any leftover for the next call
            if start < total_samples:
                self._remaining_data = audio_data[start:]
                logger.debug(f"Saved {len(self._remaining_data)} samples for next frame")
            
            logger.debug(f"Queued {chunks_queued} chunks, queue size: {self._queue.qsize()}")
            
        except Exception as e:
            logger.error(f"Error queueing audio frame: {str(e)}")
            raise


class WebRTCManager:
    OPENAI_API_BASE = "https://api.openai.com/v1"
    REALTIME_SESSION_URL = f"{OPENAI_API_BASE}/realtime/sessions"
    REALTIME_URL = f"{OPENAI_API_BASE}/realtime"

    def __init__(self):
        self.ice_servers = [RTCIceServer(urls=["stun:stun.l.google.com:19302"])]
        self.audio_output = None
        self.peer_connection = None
        self.output_device = None

    async def create_connection(self):
        config = RTCConfiguration(iceServers=self.ice_servers)
        self.peer_connection = RTCPeerConnection(config)

        # Use 48kHz for USB audio devices, 44.1kHz for device 1, 16kHz for others
        if self.output_device == 2:
            output_sample_rate = 48000
        elif self.output_device == 1:
            output_sample_rate = 44100  # rockchip,es8388 default sample rate
        else:
            output_sample_rate = RESPEAKER_SAMPLE_RATE
        self.audio_output = AudioOutput(
            sample_rate=output_sample_rate,
            device=self.output_device
        )
        await self.audio_output.start()

        @self.peer_connection.on("track")
        async def on_track(track):
            logger.info(f"Received {track.kind} track from remote")
            if track.kind == "audio":
                @track.on("ended")
                async def on_ended():
                    if self.audio_output:
                        await self.audio_output.stop()

                while True:
                    try:
                        frame = await track.recv()
                        if self.audio_output and frame:
                            # Debug: check if frame has actual audio data
                            frame_data = frame.to_ndarray()
                            if frame_data.size > 0:
                                logger.debug(f"Remote frame stats: size={frame_data.size}, max={np.max(np.abs(frame_data))}")
                            await self.audio_output.play_frame(frame)
                    except Exception as e:
                        logger.error(f"Error processing remote audio frame: {str(e)}")
                        break

        @self.peer_connection.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state changed to: {self.peer_connection.connectionState}")
            if self.peer_connection.connectionState == "failed" and self.audio_output:
                await self.audio_output.stop()

        @self.peer_connection.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            logger.info(f"ICE connection state changed to: {self.peer_connection.iceConnectionState}")

        return self.peer_connection

    async def cleanup(self):
        if self.audio_output:
            await self.audio_output.stop()
            self.audio_output = None

        if self.peer_connection:
            await self.peer_connection.close()
            self.peer_connection = None

    async def get_ephemeral_token(self, api_key, model, system_prompt=None):
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "realtime=v1"
        }

        data = {"model": model, "voice": "alloy"}
        if system_prompt:
            data["instructions"] = system_prompt

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.REALTIME_SESSION_URL, headers=headers, json=data) as response:
                    if response.status not in [200, 201]:
                        error_text = await response.text()
                        raise Exception(f"Failed to get ephemeral token: {error_text}")

                    result = await response.json()
                    return result["client_secret"]["value"], result.get("session", {}).get("id", "")
        except Exception as e:
            logger.error(f"Failed to get ephemeral token: {str(e)}")
            raise

    async def connect_to_openai(self, api_key, model, offer, system_prompt=None):
        try:
            ephemeral_token, session_id = await self.get_ephemeral_token(api_key, model, system_prompt)
            headers = {
                "Authorization": f"Bearer {ephemeral_token}",
                "Content-Type": "application/sdp",
                "OpenAI-Beta": "realtime=v1"
            }
            
            url = f"{self.REALTIME_URL}?model={model}"
            if session_id:
                url += f"&session_id={session_id}"

            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=offer.sdp) as response:
                    if response.status not in [200, 201]:
                        error_text = await response.text()
                        raise Exception(f"OpenAI WebRTC error: {error_text}")

                    sdp_answer = await response.text()
                    return {"type": "answer", "sdp": sdp_answer}
        except Exception as e:
            logger.error(f"Failed to connect to OpenAI: {str(e)}")
            raise

    async def handle_ice_candidate(self, peer_connection, candidate):
        try:
            await peer_connection.addIceCandidate(candidate)
        except Exception as e:
            logger.error(f"Error adding ICE candidate: {str(e)}")
            raise


class OpenAIWebRTCClient:
    def __init__(self, api_key, model="gpt-4o-realtime-preview", sample_rate=RESPEAKER_SAMPLE_RATE, 
                 channels=CHANNELS, frame_duration=FRAME_DURATION_MS, 
                 input_device=None, output_device=None, system_prompt=None):
        self.api_key = api_key
        self.model = model
        self.system_prompt = system_prompt
        self.audio_handler = AudioHandler(
            sample_rate=sample_rate,
            channels=channels,
            frame_duration=frame_duration,
            device=input_device
        )
        self.webrtc_manager = WebRTCManager()
        if output_device is not None:
            self.webrtc_manager.output_device = output_device

        self.peer_connection = None
        self.is_streaming = False
        self.on_transcription = None

    async def start_streaming(self):
        if self.is_streaming:
            logger.warning("Streaming is already active")
            return

        try:
            self.peer_connection = await self.webrtc_manager.create_connection()
            audio_track = self.audio_handler.create_audio_track()
            self.peer_connection.addTrack(audio_track)

            offer = await self.peer_connection.createOffer()
            await self.peer_connection.setLocalDescription(offer)

            response = await self.webrtc_manager.connect_to_openai(
                self.api_key, self.model, offer, self.system_prompt
            )

            answer = RTCSessionDescription(sdp=response["sdp"], type=response["type"])
            await self.peer_connection.setRemoteDescription(answer)

            self.is_streaming = True
            logger.info("Streaming started successfully")
        except Exception as e:
            logger.error(f"Failed to start streaming: {str(e)}")
            await self.stop_streaming()
            raise

    async def stop_streaming(self):
        if not self.is_streaming:
            return

        try:
            await self.webrtc_manager.cleanup()
            await self.audio_handler.stop()
            self.is_streaming = False
            logger.info("Streaming stopped successfully")
        except Exception as e:
            logger.error(f"Error while stopping streaming: {str(e)}")
            raise

    async def pause_streaming(self):
        if self.is_streaming:
            await self.audio_handler.pause()

    async def resume_streaming(self):
        if self.is_streaming:
            await self.audio_handler.resume()

    def set_audio_device(self, device_id):
        self.audio_handler.set_device(device_id)

    def _handle_transcription(self, text):
        if self.on_transcription:
            self.on_transcription(text)


async def main():
    # List available audio devices
    print("Available audio devices:")
    print(sd.query_devices())
    print("\n")
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set.")
        print("Please create a .env file with your OpenAI API key.")
        return

    # Try with specific devices or default
    use_respeaker = True  # Set to False to use default audio devices
    
    if use_respeaker:
        input_device = 1   # rockchip,es8388 - has 2 input/output channels
        output_device = 1  # rockchip,es8388 - has 2 input/output channels
        print("Using rockchip,es8388 audio device (device 1)")
    else:
        input_device = None  # Default input
        output_device = None # Default output
        print("Using default audio devices")
    
    client = OpenAIWebRTCClient(
        api_key=api_key,
        model="gpt-4o-realtime-preview",
        system_prompt="You are providing help around the University of Waterloo campus. You are the help desk, try your best to help students and staff with their questions. Always respond in English.",
        input_device=input_device,
        output_device=output_device
    )

    def on_transcription(text):
        print(f"Transcription: {text}")

    client.on_transcription = on_transcription

    # Test microphone before starting
    print("\nTesting microphone input...")
    print("Please make some noise or speak for 2 seconds...")
    
    test_data = []
    def test_callback(indata, frames, time, status):
        if status:
            print(f"Microphone status: {status}")
        test_data.append(np.max(np.abs(indata)))
    
    test_channels = 2 if input_device in [1, 2] else 1  # Both devices have 2 channels
    test_stream = sd.InputStream(
        device=input_device,
        channels=test_channels,
        samplerate=RESPEAKER_SAMPLE_RATE,
        callback=test_callback,
        blocksize=int(RESPEAKER_SAMPLE_RATE * 0.1)  # 100ms blocks
    )
    
    with test_stream:
        await asyncio.sleep(2.0)
    
    if test_data and max(test_data) > 0.001:
        print(f"✓ Microphone is working! Max level detected: {max(test_data):.4f}")
    else:
        print("✗ No audio detected from microphone!")
        print("Please check:")
        print("  - Microphone is connected")
        print("  - Correct device is selected")
        print("  - Microphone permissions are granted")
        print("  - Try speaking louder or closer to the mic")
        response = input("\nContinue anyway? (y/n): ")
        if response.lower() != 'y':
            return
    
    try:
        print("\nStarting streaming session...")
        await client.start_streaming()
        print("Streaming started. Speak into your microphone.")
        print("The AI should respond to your questions about the University of Waterloo campus.")
        print("Try saying 'Hello' or asking a question about the campus.")
        print("Press Ctrl+C to stop.")
        
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        # This is normal when the event loop is interrupted
        pass
    except KeyboardInterrupt:
        print("\nStopping streaming...")
    finally:
        await client.stop_streaming()
        print("Streaming stopped.")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main()) 