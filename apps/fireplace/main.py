# NOAUTO
# /// script
# dependencies = [
#   "bbos @ /home/GREEN/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
# ]
# ///
import numpy as np
from bbos import Writer, Reader, Type, Config, Time
import time
import threading
import random
import math
import os
from pathlib import Path

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
        sample_rate = CFG_AUDIO.sample_rate
        channels = CFG_AUDIO.channels
        
        cmd = [
            'ffmpeg', '-i', file_path,
            '-f', 'f32le',  # 32-bit float little endian
            '-acodec', 'pcm_f32le',
            '-ar', str(sample_rate),
            '-ac', str(channels),
            '-'  # Output to stdout
        ]
        
        print(f"[Fireplace] Loading audio file: {file_path}")
        result = subprocess.run(cmd, capture_output=True, check=True)
        
        # Convert bytes to numpy array
        audio_data = np.frombuffer(result.stdout, dtype=np.float32)
        
        if channels == 2:
            audio_data = audio_data.reshape(-1, 2)
        else:
            audio_data = audio_data.reshape(-1, 1)
        
        # Apply volume multiplier and clip to prevent distortion
        audio_data = audio_data * VOLUME_MULTIPLIER
        audio_data = np.clip(audio_data, -1.0, 1.0)
        
        print(f"[Fireplace] Loaded {len(audio_data) / sample_rate:.1f} seconds of audio")
        return audio_data
        
    except (subprocess.CalledProcessError, FileNotFoundError, ImportError) as e:
        print(f"[Fireplace] Could not load audio file: {e}")
        return None

def generate_crackling_sound(duration_seconds=1.0):
    """Generate realistic crackling fire sound"""
    sample_rate = CFG_AUDIO.sample_rate
    channels = CFG_AUDIO.channels
    num_samples = int(duration_seconds * sample_rate)
    
    # Start with a gentle base hiss (much quieter than before)
    base_hiss = np.random.normal(0, 0.02, num_samples)
    
    # Apply low-pass filter to base hiss to remove harsh frequencies
    # Simple exponential moving average filter
    alpha = 0.1
    filtered_hiss = np.zeros_like(base_hiss)
    filtered_hiss[0] = base_hiss[0]
    for i in range(1, len(base_hiss)):
        filtered_hiss[i] = alpha * base_hiss[i] + (1 - alpha) * filtered_hiss[i-1]
    
    audio = filtered_hiss
    
    # Add realistic crackle pops (sharp attacks with decay)
    num_crackles = random.randint(4, 12)
    for _ in range(num_crackles):
        crackle_start = random.randint(0, max(1, num_samples - 2000))
        crackle_duration = random.randint(50, 300)
        
        # Create sharp attack crackle sound
        t = np.arange(crackle_duration) / sample_rate
        
        # Sharp attack, quick decay
        envelope = np.exp(-t * random.uniform(15, 40))
        
        # Mix of frequencies for realistic crackle
        freq1 = random.uniform(800, 2500)
        freq2 = random.uniform(1200, 4000)
        crackle = (np.sin(2 * np.pi * freq1 * t) * 0.6 + 
                  np.sin(2 * np.pi * freq2 * t) * 0.4) * envelope
        
        # Apply intensity variation
        intensity = random.uniform(0.3, 0.8)
        crackle *= intensity
        
        # Add to audio
        end_idx = min(crackle_start + crackle_duration, num_samples)
        audio[crackle_start:end_idx] += crackle[:end_idx - crackle_start]
    
    # Add wood "settling" sounds (lower frequency pops)
    num_pops = random.randint(1, 4)
    for _ in range(num_pops):
        pop_start = random.randint(0, max(1, num_samples - 3000))
        pop_duration = random.randint(200, 800)
        
        t = np.arange(pop_duration) / sample_rate
        
        # Slower attack, longer decay for wood settling
        envelope = (1 - np.exp(-t * 20)) * np.exp(-t * 8)
        
        # Lower frequencies for wood sounds
        freq = random.uniform(200, 800)
        pop_sound = np.sin(2 * np.pi * freq * t) * envelope * random.uniform(0.2, 0.5)
        
        end_idx = min(pop_start + pop_duration, num_samples)
        audio[pop_start:end_idx] += pop_sound[:end_idx - pop_start]
    
    # Add subtle low-frequency fire rumble
    t_full = np.arange(num_samples) / sample_rate
    rumble1 = np.sin(2 * np.pi * 25 * t_full) * 0.03
    rumble2 = np.sin(2 * np.pi * 45 * t_full) * 0.02
    audio += rumble1 + rumble2
    
    # Apply final envelope to avoid clicks
    fade_samples = min(1000, num_samples // 10)
    if fade_samples > 0:
        fade_in = np.linspace(0, 1, fade_samples)
        fade_out = np.linspace(1, 0, fade_samples)
        audio[:fade_samples] *= fade_in
        audio[-fade_samples:] *= fade_out
    
    # Normalize and clip
    audio = np.clip(audio * 0.6, -1.0, 1.0)
    
    # Apply volume multiplier
    audio = audio * VOLUME_MULTIPLIER
    audio = np.clip(audio, -1.0, 1.0)
    
    if channels == 2:
        # Create stereo with slight variation for spatial feel
        left = audio
        right = audio * 0.95 + np.random.normal(0, 0.005, len(audio))
        stereo = np.column_stack([left, right])
    else:
        stereo = audio.reshape(-1, 1)
    
    return stereo.astype(np.float32)

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
    t = Time(CFG_LED.rate_state)
    start_time = time.monotonic()
    
    while True:
        current_time = time.monotonic() - start_time
        rgb_array = np.zeros((CFG_LED.num_leds, 3), dtype=np.uint8)
        
        # Create fire effect for each LED
        for i in range(CFG_LED.num_leds):
            color = get_fire_color_at_height(i, CFG_LED.num_leds, current_time)
            rgb_array[i] = color
        
        # Occasionally add some ember sparkles at random positions
        if random.random() < 0.1:
            spark_led = random.randint(CFG_LED.num_leds // 2, CFG_LED.num_leds - 1)
            rgb_array[spark_led] = random.choice(EMBER_COLORS)
        
        # Update LEDs
        with writer.buf() as b:
            b["rgb"] = rgb_array
        
        t.tick()

def play_fire_sounds(writer, audio_file=None):
    """Play fire sounds - either from file or generated"""
    print("[Fireplace] Starting fire sound playback...")
    t = Time(CFG_AUDIO.update_rate)
    chunk_size = CFG_AUDIO.chunk_size
    
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
                    padding = np.zeros((pad_size, 2), dtype=np.float32)
                else:
                    padding = np.zeros((pad_size, 1), dtype=np.float32)
                chunk = np.vstack((chunk, padding))
            
            with writer.buf() as b:
                b["audio"] = chunk
            t.tick()
    else:
        print("[Fireplace] Using generated fireplace sounds...")
        # Use the original generated audio
        while True:
            # Generate a chunk of crackling fire sound
            sound_duration = random.uniform(0.8, 1.5)  # Vary duration slightly
            audio_chunk = generate_crackling_sound(sound_duration)
            
            # Play the sound chunk by chunk
            for i in range(0, len(audio_chunk), chunk_size):
                chunk = audio_chunk[i:i + chunk_size]
                
                # Pad if necessary
                if len(chunk) < chunk_size:
                    pad_size = chunk_size - len(chunk)
                    if CFG_AUDIO.channels == 2:
                        padding = np.zeros((pad_size, 2), dtype=np.float32)
                    else:
                        padding = np.zeros((pad_size, 1), dtype=np.float32)
                    chunk = np.vstack((chunk, padding))
                
                with writer.buf() as b:
                    b["audio"] = chunk
                t.tick()

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
             Writer("/audio.speaker", Type("speakerphone_audio")) as w_audio:
            
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
