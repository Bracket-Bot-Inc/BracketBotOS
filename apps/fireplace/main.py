# /// script
# dependencies = [
#   "bbos",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
import numpy as np
from bbos import Writer, Type, Config
import random
import math
import os
import time

CFG_LED = Config("led_strip")
CFG_AUDIO = Config("speakerphone")

# Audio file path - put your downloaded fireplace audio here
AUDIO_FILE_PATH = "fire.wav"

# Volume multiplier - adjust this to make audio louder or quieter
VOLUME_MULTIPLIER = 4.0  # 2x louder

# Fire color palette (RGB values)
FIRE_COLORS = [
    (255, 0, 0),      # Deep red
    (255, 30, 0),     # Red-orange
    (255, 60, 0),     # Orange
    (255, 100, 0),    # Orange-yellow
    (255, 140, 0),    # Yellow-orange
    (255, 160, 0),    # Warm orange (was 180)
    (255, 180, 0),    # Golden yellow (was 200, 50)
    (255, 200, 0),    # Bright golden (was 220, 100)
]

# Ember colors for occasional sparks
EMBER_COLORS = [
    (255, 100, 0),    # Orange ember
    (255, 150, 0),    # Bright ember
    (255, 180, 0),    # Golden ember (was 200, 50)
]

def load_audio_file(file_path):
    """Load audio file using ffmpeg if available, otherwise return None"""
    if not os.path.exists(file_path):
        return None
    
    try:
        import subprocess
        
        # Use ffmpeg to convert audio to the format we need
        sample_rate = CFG_AUDIO.speaker_sample_rate
        channels = CFG_AUDIO.speaker_channels
        
        cmd = [
            'ffmpeg', '-i', file_path,
            '-f', 's16le',  # 32-bit float little endian
            '-acodec', 'pcm_s16le',
            '-ar', str(sample_rate),
            '-ac', str(channels),
            '-'  # Output to stdout
        ]
        
        print(f"[Fireplace] Loading audio file: {file_path}")
        result = subprocess.run(cmd, capture_output=True, check=True)
        
        # Convert bytes to numpy array
        audio_data = np.frombuffer(result.stdout, dtype=np.int16)
        
        if channels == 2:
            audio_data = audio_data.reshape(-1, 2)
        else:
            audio_data = audio_data.reshape(-1, 1)
        
        # Apply volume multiplier and clip to prevent distortion
        audio_data = audio_data * VOLUME_MULTIPLIER
        audio_data = np.clip(audio_data, -32768, 32767)
        
        print(f"[Fireplace] Loaded {len(audio_data) / sample_rate:.1f} seconds of audio")
        return audio_data
        
    except (subprocess.CalledProcessError, FileNotFoundError, ImportError) as e:
        print(f"[Fireplace] Could not load audio file: {e}")
        return None

def get_fire_color_at_height(led_index, num_leds, time_offset=0):
    """Get fire color based on LED position and animation state"""
    # Height factor (bottom is hotter/redder, top is cooler/yellower)
    height_factor = led_index / max(1, num_leds - 1)
    
    # Add some flickering with sine waves and noise
    flicker1 = math.sin(time_offset * 3.2 + led_index * 0.5) * 0.3
    flicker2 = math.sin(time_offset * 2.1 + led_index * 0.8) * 0.2
    noise = (random.random() - 0.5) * 0.4
    
    intensity = 0.7 + flicker1 + flicker2 + noise
    intensity = max(0.1, min(1.0, intensity))
    
    # Color selection based on height and intensity
    if height_factor < 0.3:  # Bottom - hot reds/oranges
        if intensity > 0.8:
            base_color = FIRE_COLORS[2]  # Orange
        else:
            base_color = FIRE_COLORS[0]  # Deep red
    elif height_factor < 0.6:  # Middle - oranges
        if intensity > 0.7:
            base_color = FIRE_COLORS[4]  # Yellow-orange
        else:
            base_color = FIRE_COLORS[1]  # Red-orange
    else:  # Top - yellows and occasional flickers
        if random.random() < 0.1:  # Occasional ember
            base_color = random.choice(EMBER_COLORS)
        elif intensity > 0.6:
            base_color = FIRE_COLORS[6]  # Warm yellow
        else:
            base_color = FIRE_COLORS[3]  # Orange-yellow
    
    # Apply intensity to color
    return tuple(int(c * intensity) for c in base_color)

def update_fire_leds(writer, time_offset):
    """Update fire effect on LEDs"""
    rgb_array = np.zeros((CFG_LED.num_leds, 3), dtype=np.uint8)
    
    # Create fire effect for each LED
    for i in range(CFG_LED.num_leds):
        color = get_fire_color_at_height(i, CFG_LED.num_leds, time_offset)
        rgb_array[i] = color
    
    # Occasionally add some ember sparkles at random positions
    if random.random() < 0.1:
        spark_led = random.randint(CFG_LED.num_leds // 2, CFG_LED.num_leds - 1)
        rgb_array[spark_led] = random.choice(EMBER_COLORS)
    
    # Update LEDs
    writer["rgb"] = rgb_array

def get_next_audio_chunk(audio_file, audio_pos, chunk_size):
    """Get the next audio chunk and update position"""
    if audio_file is None:
        # Return silence if no audio file
        if CFG_AUDIO.speaker_channels == 2:
            return np.zeros((chunk_size, 2), dtype=np.int16), 0
        else:
            return np.zeros((chunk_size, 1), dtype=np.int16), 0
    
    # Get the next chunk from the loaded audio
    chunk = audio_file[audio_pos:audio_pos + chunk_size]
    
    # If we've reached the end, loop back
    if len(chunk) < chunk_size:
        remaining = chunk_size - len(chunk)
        new_audio_pos = 0  # Reset to beginning
        loop_chunk = audio_file[new_audio_pos:new_audio_pos + remaining]
        if len(loop_chunk) > 0:
            chunk = np.vstack((chunk, loop_chunk)) if len(chunk) > 0 else loop_chunk
        new_audio_pos = remaining
    else:
        new_audio_pos = audio_pos + chunk_size
    
    # Pad if still necessary
    if len(chunk) < chunk_size:
        pad_size = chunk_size - len(chunk)
        if CFG_AUDIO.speaker_channels == 2:
            padding = np.zeros((pad_size, 2), dtype=np.int16)
        else:
            padding = np.zeros((pad_size, 1), dtype=np.int16)
        chunk = np.vstack((chunk, padding))
    
    return chunk, new_audio_pos

def run_fireplace(w_led, w_audio, audio_file=None):
    """Run fireplace simulation in single thread"""
    print("[Fireplace] Starting single-threaded fireplace simulation...")
    
    chunk_size = CFG_AUDIO.speaker_chunk_size
    audio_pos = 0
    start_time = time.time()
    
    while True:
        current_time = time.time() - start_time
        
        # Update LEDs
        update_fire_leds(w_led, current_time)
        
        # Get and play next audio chunk
        audio_chunk, audio_pos = get_next_audio_chunk(audio_file, audio_pos, chunk_size)
        w_audio["audio"] = audio_chunk

if __name__ == "__main__":
    print("🔥 [Fireplace] Starting cozy fireplace simulation...")
    print(f"🔥 [Fireplace] LEDs: {CFG_LED.num_leds}")
    
    # Try to load real fireplace audio
    loaded_audio = load_audio_file(AUDIO_FILE_PATH)
    if loaded_audio is not None:
        print("🔥 [Fireplace] Real fireplace audio loaded!")
    else:
        print("🔥 [Fireplace] Using silence (no audio file found)...")
        print(f"🔥 [Fireplace] To use real audio, put your fireplace audio file at: {AUDIO_FILE_PATH}")
    
    try:
        with Writer("led_strip.ctrl", Type("led_strip_ctrl")) as w_led, \
             Writer("audio.speaker", Type("speakerphone_speaker")) as w_audio:
            
            print("🔥 [Fireplace] Fire is burning! Press Ctrl+C to extinguish...")
            
            # Run everything in single thread
            run_fireplace(w_led, w_audio, loaded_audio)
            
    except KeyboardInterrupt:
        print("\n🔥 [Fireplace] Extinguishing fire... Goodbye!")
    except Exception as e:
        print(f"🔥 [Fireplace] Error: {e}")
