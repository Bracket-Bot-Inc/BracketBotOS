# /// script
# dependencies = [
#   "bbos",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
import numpy as np
from bbos import Writer, Reader, Type, Config
from bbos.time import Realtime


CFG_LED = Config("led_strip")
CFG_AUDIO = Config("speakerphone")

# LED Colors
GREEN = (0, 255, 0)  # Speaker active
BLUE = (0, 0, 255)   # Mic active  
OFF = (0, 0, 0)      # No activity

# Audio parameters
VOLUME_SENSITIVITY = 10      # Multiplier to adjust volume sensitivity for LEDs
RAMP_SPEED = 2              # Amount to change the LED count per update (higher = faster ramping)


# Audio activity thresholds  
MIC_THRESHOLD = 0.01        # Minimum audio level to consider mic "active"
SPEAKER_THRESHOLD = 0.01    # Minimum audio level to consider speaker "active"

def get_audio_level(audio_data):
    """Calculate RMS volume level from audio data"""
    if audio_data is None or len(audio_data) == 0:
        return 0.0
    
    # Calculate RMS (root mean square) amplitude
    avg_volume = np.sqrt(np.mean(audio_data**2))
    return avg_volume

def set_leds_smooth(writer, color, led_count):
    """Set LEDs with smooth transitions using fractional LED count"""
    # Create RGB array
    rgb_array = np.zeros((CFG_LED.num_leds, 3), dtype=np.uint8)
    
    # Light up fully lit LEDs
    full_leds = int(led_count)
    for i in range(min(full_leds, CFG_LED.num_leds)):
        rgb_array[i] = color
    
    # Add partial brightness to the next LED for smooth transitions
    if full_leds < CFG_LED.num_leds:
        partial_brightness = led_count - full_leds
        if partial_brightness > 0:
            # Apply brightness to the partial LED
            rgb_array[full_leds] = tuple(int(c * partial_brightness) for c in color)
    
    writer["rgb"] = rgb_array

if __name__ == "__main__":
    print("[AudioLED] Starting audio-controlled LED volume bar...")
    print(f"[AudioLED] Green bar = Speaker volume, Blue bar = Mic volume")
    print(f"[AudioLED] Volume sensitivity: {VOLUME_SENSITIVITY}, Ramp speed: {RAMP_SPEED}")
    
    with Reader("audio.mic") as r_mic, \
         Reader("audio.speaker") as r_speaker, \
         Writer("led_strip.ctrl", Type("led_strip_ctrl")) as w_led:
        # Animation state - use float for smooth ramping
        current_led_count = 0.0
        current_color = OFF
        
        print("[AudioLED] Ready - monitoring audio levels...")
        
        while True:
            speaker_volume = 0.0
            mic_volume = 0.0
            
            # Check speaker audio level (takes priority)
            if r_speaker.ready():
                speaker_volume = get_audio_level(r_speaker.data["audio"])
            
            # Check mic audio level
            if r_mic.ready():
                mic_volume = get_audio_level(r_mic.data["audio"])
            
            # Determine desired LED count based on active audio source
            if speaker_volume > SPEAKER_THRESHOLD:
                # Map speaker volume to LED count
                desired_led_count = speaker_volume * CFG_LED.num_leds * VOLUME_SENSITIVITY
                desired_led_count = min(CFG_LED.num_leds, desired_led_count)
                active_color = GREEN
                active_source = "Speaker"
                active_volume = speaker_volume
            elif mic_volume > MIC_THRESHOLD:
                # Map mic volume to LED count
                desired_led_count = mic_volume * CFG_LED.num_leds * VOLUME_SENSITIVITY
                desired_led_count = min(CFG_LED.num_leds, desired_led_count)
                active_color = BLUE
                active_source = "Mic"
                active_volume = mic_volume
            else:
                desired_led_count = 0.0
                active_color = current_color  # Keep last color while ramping down
                active_source = "None"
                active_volume = 0.0
            
            # Smooth transition: adjust current_led_count towards desired_led_count
            if current_led_count < desired_led_count:
                current_led_count += RAMP_SPEED
                current_led_count = min(current_led_count, desired_led_count)
                current_color = active_color
            elif current_led_count > desired_led_count:
                current_led_count -= RAMP_SPEED
                current_led_count = max(current_led_count, desired_led_count)
            
            # Update LEDs
            if current_led_count > 0:
                set_leds_smooth(w_led, current_color, current_led_count)
            else:
                set_leds_smooth(w_led, OFF, 0)
                current_color = OFF
