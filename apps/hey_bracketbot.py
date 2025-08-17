# /// script
# dependencies = [
#   "bbos",
#   "metaphone",
#   "textdistance",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
from bbos import Reader, Writer, Type, Config
from bbos.app_manager import start_app, stop_app
import metaphone
import textdistance
import numpy as np

CFG = Config("transcriber")
CFG_LED_STRIP = Config("led_strip")

def phonetic(token):
    return metaphone.doublemetaphone(token)[0]   # primary code

def detect_wake_word(text, match_words, weights):
    """Detect wake words using phonetic matching"""
    if not text:
        return False
    
    # Split into words and filter out empty strings
    words = [w.strip().lower() for w in text.split() if w.strip()]
    
    # Create sliding windows of match_words length
    window_size = len(match_words)
    windows = [tuple(words[i:i+window_size]) for i in range(len(words) - window_size + 1)]
    
    # Convert to phonetic codes
    code_windows = [tuple(phonetic(w) for w in window) for window in windows]
    
    # Target phonetic codes for match_words
    target_codes = [phonetic(word) for word in match_words]
    
    # Calculate best match score across all windows
    max_score = 0
    for code_window in code_windows:
        score = sum(
            weights[i] * (1 - textdistance.hamming.normalized_distance(code_window[i], target_codes[i]))
            for i in range(len(match_words))
        )
        max_score = max(max_score, score)
    
    # Threshold for detection (tune this based on testing)
    return max_score > 0.55

def main():
    with Reader("transcript") as r_transcript, \
         Writer("led_strip.ctrl", Type('led_strip_ctrl')) as w_led_strip:
        rgb_array = np.zeros((CFG_LED_STRIP.num_leds,3), dtype=np.uint8)
        color = [255, 255, 255]
        while True:
            if r_transcript.ready():
                text = r_transcript.data['text']
                if text:
                    if detect_wake_word(text, ["follow"], [0.7]):
                        start_app("follow")
                        color = [0, 255, 0]
                    if detect_wake_word(text, ["stop"], [0.7]):
                        stop_app("follow")
                        color = [255, 0, 0]
                    if detect_wake_word(text, ["talk"], [0.7]):
                        start_app("realtime")
                        color = [255, 0, 255]
                    if detect_wake_word(text, ["quiet"], [0.7]):
                        stop_app("realtime")
                        color = [0, 0, 0]
            rgb_array[:, :] = color
            w_led_strip["rgb"] = rgb_array
    stop_app("follow")

if __name__ == "__main__":
    main()