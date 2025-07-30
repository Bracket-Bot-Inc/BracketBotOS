# /// script
# dependencies = [
#   "bbos @ /home/bracketbot/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
# ]
# ///
import numpy as np
from bbos import Writer, Type, Config
import threading
import random
import math
import os

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

def animate_fire_leds(writer):
    """Animate fire effect on LEDs"""
    print("[Fireplace] Starting LED fire animation...")
    while True:
        rgb_array = np.zeros((CFG_LED.num_leds, 3), dtype=np.uint8)
        
        # Create fire effect for each LED
        for i in range(CFG_LED.num_leds):
            color = get_fire_color_at_height(i, CFG_LED.num_leds)
            rgb_array[i] = color
        
        # Occasionally add some ember sparkles at random positions
        if random.random() < 0.1:
            spark_led = random.randint(CFG_LED.num_leds // 2, CFG_LED.num_leds - 1)
            rgb_array[spark_led] = random.choice(EMBER_COLORS)
        
        # Update LEDs
        writer["rgb"] = rgb_array

def play_fire_sounds(writer, audio_file=None):
    """Play fire sounds - either from file or generated"""
    print("[Fireplace] Starting fire sound playback...")
    chunk_size = CFG_AUDIO.speaker_chunk_size
    
    if audio_file is not None:
        print("[Fireplace] Using real fireplace audio!")
        # Loop the real audio file
        audio_pos = 0
        while True:
            # Get the next chunk from the loaded audio
            chunk = audio_file[audio_pos:audio_pos + chunk_size]
            
            # If we've reached the end, loop back
            if len(chunk) < chunk_size:
                remaining = chunk_size - len(chunk)
                audio_pos = 0  # Reset to beginning
                loop_chunk = audio_file[audio_pos:audio_pos + remaining]
                if len(loop_chunk) > 0:
                    chunk = np.vstack((chunk, loop_chunk)) if len(chunk) > 0 else loop_chunk
                audio_pos = remaining
            else:
                audio_pos += chunk_size
            
            # Pad if still necessary
            if len(chunk) < chunk_size:
                pad_size = chunk_size - len(chunk)
                if CFG_AUDIO.channels == 2:
                    padding = np.zeros((pad_size, 2), dtype=np.int16)
                else:
                    padding = np.zeros((pad_size, 1), dtype=np.int16)
                chunk = np.vstack((chunk, padding))
            
            writer["audio"] = chunk

if __name__ == "__main__":
    print("🔥 [Fireplace] Starting cozy fireplace simulation...")
    print(f"🔥 [Fireplace] LEDs: {CFG_LED.num_leds}")
    
    # Try to load real fireplace audio
    loaded_audio = load_audio_file(AUDIO_FILE_PATH)
    if loaded_audio is not None:
        print("🔥 [Fireplace] Real fireplace audio loaded!")
    else:
        print("🔥 [Fireplace] Using generated fireplace sounds...")
        print(f"🔥 [Fireplace] To use real audio, put your fireplace audio file at: {AUDIO_FILE_PATH}")
    
    try:
        with Writer("/led_strip.ctrl", Type("led_strip_ctrl")) as w_led, \
             Writer("/audio.speaker", Type("speakerphone_audio")(CFG_AUDIO.speaker_chunk_size, CFG_AUDIO.speaker_channels)) as w_audio:
            
            # Start LED animation in a separate thread
            led_thread = threading.Thread(target=animate_fire_leds, args=(w_led,), daemon=True)
            led_thread.start()
            
            print("🔥 [Fireplace] Fire is burning! Press Ctrl+C to extinguish...")
            
            # Run audio in main thread
            play_fire_sounds(w_audio, loaded_audio)
            
    except KeyboardInterrupt:
        print("\n🔥 [Fireplace] Extinguishing fire... Goodbye!")
    except Exception as e:
        print(f"🔥 [Fireplace] Error: {e}")
