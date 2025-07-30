# /// script
# dependencies = [
#   "bbos @ /home/bracketbot/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
# ]
# ///
import numpy as np
from bbos import Writer, Reader, Type, Config, Time
import time
import math
import random
import threading

CFG_LED = Config("led_strip")
CFG_AUDIO = Config("speakerphone")

# Whistle parameters
SAMPLE_RATE = CFG_AUDIO.sample_rate
WHISTLE_VOLUME = 0.3  # Adjust volume (0.0 to 1.0)
FADE_DURATION = 0.1   # Fade in/out duration in seconds

# Whistle frequencies (in Hz)
WHISTLE_NOTES = {
    'low': 800,      # Low whistle
    'medium': 1200,  # Medium whistle  
    'high': 1800,    # High whistle
    'very_high': 2400 # Very high whistle
}

# LED Colors for whistle visualization
WHISTLE_COLORS = {
    'low': (0, 255, 0),      # Green for low
    'medium': (255, 255, 0), # Yellow for medium
    'high': (255, 100, 0),   # Orange for high
    'very_high': (255, 0, 0) # Red for very high
}

# Whistle patterns
WHISTLE_PATTERNS = [
    {'name': 'single', 'notes': ['medium'], 'durations': [0.5]},
    {'name': 'double', 'notes': ['medium', 'medium'], 'durations': [0.3, 0.3]},
    {'name': 'rising', 'notes': ['low', 'medium', 'high'], 'durations': [0.3, 0.3, 0.4]},
    {'name': 'falling', 'notes': ['high', 'medium', 'low'], 'durations': [0.3, 0.3, 0.4]},
    {'name': 'trill', 'notes': ['medium', 'high'] * 4, 'durations': [0.15, 0.15] * 4},
    {'name': 'wolf_whistle', 'notes': ['high', 'very_high', 'low'], 'durations': [0.4, 0.3, 0.6]},
    {'name': 'referee', 'notes': ['very_high'] * 6, 'durations': [0.2] * 6},
    {'name': 'bird_call', 'notes': ['high', 'very_high', 'high', 'medium'], 'durations': [0.2, 0.1, 0.2, 0.3]},
]

def generate_whistle_tone(frequency, duration, sample_rate=SAMPLE_RATE):
    """Generate a pure whistle tone with fade in/out"""
    num_samples = int(duration * sample_rate)
    fade_samples = int(FADE_DURATION * sample_rate)
    
    # Generate time array
    t = np.linspace(0, duration, num_samples, False)
    
    # Generate sine wave
    tone = np.sin(2 * np.pi * frequency * t)
    
    # Add some harmonics for more realistic whistle sound
    tone += 0.1 * np.sin(2 * np.pi * frequency * 2 * t)  # 2nd harmonic
    tone += 0.05 * np.sin(2 * np.pi * frequency * 3 * t) # 3rd harmonic
    
    # Apply fade in/out to avoid clicks
    if fade_samples > 0:
        # Fade in
        fade_in = np.linspace(0, 1, fade_samples)
        tone[:fade_samples] *= fade_in
        
        # Fade out
        fade_out = np.linspace(1, 0, fade_samples)
        tone[-fade_samples:] *= fade_out
    
    # Apply volume
    tone *= WHISTLE_VOLUME
    
    return tone.astype(np.float32)

def set_whistle_leds(writer, note_name, intensity=1.0):
    """Set LEDs to visualize the whistle note"""
    color = WHISTLE_COLORS.get(note_name, (255, 255, 255))
    
    # Create breathing effect based on intensity
    brightness = int(intensity * 255)
    adjusted_color = tuple(int(c * brightness / 255) for c in color)
    
    # Create RGB array with wave pattern
    rgb_array = np.zeros((CFG_LED.num_leds, 3), dtype=np.uint8)
    
    # Fill with breathing pattern
    num_active = max(1, int(CFG_LED.num_leds * intensity))
    center = CFG_LED.num_leds // 2
    
    for i in range(CFG_LED.num_leds):
        distance = abs(i - center)
        if distance < num_active:
            fade_factor = 1.0 - (distance / num_active)
            led_color = tuple(int(c * fade_factor) for c in adjusted_color)
            rgb_array[i] = led_color
    
    with writer.buf() as b:
        b["rgb"] = rgb_array

def play_whistle_pattern(pattern, audio_writer, led_writer):
    """Play a complete whistle pattern"""
    print(f"[Whistle] Playing pattern: {pattern['name']}")
    
    for note, duration in zip(pattern['notes'], pattern['durations']):
        frequency = WHISTLE_NOTES[note]
        
        # Generate whistle tone
        tone = generate_whistle_tone(frequency, duration)
        
        # Calculate number of audio chunks to send
        chunk_size = CFG_AUDIO.chunk_size
        num_chunks = len(tone) // chunk_size
        
        print(f"[Whistle] Playing {note} note ({frequency}Hz) for {duration}s")
        
        # Send audio and LED data
        for i in range(num_chunks):
            start_idx = i * chunk_size
            end_idx = start_idx + chunk_size
            audio_chunk = tone[start_idx:end_idx]
            
            # Send audio
            with audio_writer.buf() as b:
                b["audio"] = audio_chunk
            
            # Update LEDs with breathing effect
            progress = i / max(1, num_chunks - 1)
            intensity = 0.5 + 0.5 * math.sin(progress * math.pi * 4)  # Breathing effect
            set_whistle_leds(led_writer, note, intensity)
            
            time.sleep(chunk_size / CFG_AUDIO.sample_rate)
        
        # Brief pause between notes
        time.sleep(0.05)
    
    # Turn off LEDs
    set_whistle_leds(led_writer, 'medium', 0)

def interactive_whistle_mode(audio_writer, led_writer):
    """Interactive mode where user can trigger different whistles"""
    print("\n[Whistle] Interactive Mode - Available patterns:")
    for i, pattern in enumerate(WHISTLE_PATTERNS):
        print(f"  {i+1}: {pattern['name']}")
    print("  r: Random pattern")
    print("  q: Quit")
    
    while True:
        try:
            choice = input("\nEnter choice: ").strip().lower()
            
            if choice == 'q':
                break
            elif choice == 'r':
                pattern = random.choice(WHISTLE_PATTERNS)
                play_whistle_pattern(pattern, audio_writer, led_writer)
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(WHISTLE_PATTERNS):
                    pattern = WHISTLE_PATTERNS[idx]
                    play_whistle_pattern(pattern, audio_writer, led_writer)
                else:
                    print("Invalid pattern number!")
            else:
                print("Invalid choice! Try again.")
                
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")

def demo_mode(audio_writer, led_writer):
    """Demo mode that plays all patterns"""
    print("[Whistle] Demo mode - playing all patterns...")
    
    for pattern in WHISTLE_PATTERNS:
        play_whistle_pattern(pattern, audio_writer, led_writer)
        time.sleep(1)  # Pause between patterns
    
    print("[Whistle] Demo complete!")

if __name__ == "__main__":
    print("[Whistle] Starting whistle app...")
    print(f"[Whistle] Sample rate: {SAMPLE_RATE}Hz, Volume: {WHISTLE_VOLUME}")
    print(f"[Whistle] Available patterns: {len(WHISTLE_PATTERNS)}")
    
    # Check if running in auto mode or interactive mode
    import sys
    auto_mode = len(sys.argv) > 1 and sys.argv[1] == "demo"
    
    with Writer("/audio.speaker", Type("speakerphone_audio")) as w_audio, \
         Writer("/led_strip.ctrl", Type("led_strip_ctrl")) as w_led:
        
        if auto_mode:
            print("[Whistle] Running in demo mode...")
            demo_mode(w_audio, w_led)
        else:
            print("[Whistle] Running in interactive mode...")
            interactive_whistle_mode(w_audio, w_led)
    
    print("[Whistle] Shutting down...") 