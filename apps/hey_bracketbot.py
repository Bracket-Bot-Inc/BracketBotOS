# AUTO
# /// script
# dependencies = [
#   "bbos @ /home/bracketbot/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
#   "metaphone",
#   "textdistance",
# ]
# ///
from bbos import Reader, Writer, Type, Config
import metaphone
import textdistance
import numpy as np

CFG = Config("transcriber")
CFG_LED_STRIP = Config("led_strip")

def phonetic(token):
    return metaphone.doublemetaphone(token)[0]   # primary code

def detect_wake_word(text):
    """Detect 'hey bracket bot' using phonetic matching"""
    if not text:
        return False
    
    # Split into words and filter out empty strings
    words = [w.strip().lower() for w in text.split() if w.strip()]
    
    if len(words) < 3:  # Need at least 3 words for "hey bracket bot"
        return False
    
    # Create sliding windows of 3 words
    windows = [(words[i], words[i+1], words[i+2]) for i in range(len(words) - 2)]
    
    # Convert to phonetic codes
    code_windows = [(phonetic(w1), phonetic(w2), phonetic(w3)) for w1, w2, w3 in windows]
    
    # Target phonetic codes for "hey bracket bot"
    target_hey = phonetic("hey")     # Should be "H"
    target_bracket = phonetic("bracket")  # Should be "PRKT" 
    target_bot = phonetic("bot")     # Should be "PT" or "BT"
    
    # Calculate best match score across all windows
    max_score = 0
    for w1, w2, w3 in code_windows:
        score = (
            0.4 * (1 - textdistance.hamming.normalized_distance(w1, target_hey)) +
            0.4 * (1 - textdistance.hamming.normalized_distance(w2, target_bracket)) + 
            0.2 * (1 - textdistance.hamming.normalized_distance(w3, target_bot))
        )
        max_score = max(max_score, score)
    
    # Threshold for detection (tune this based on testing)
    return max_score > 0.7

def main():
    with Reader("/transcript") as r_transcript, \
         Writer("/led_strip.ctrl", Type('led_strip_ctrl')) as w_led_strip:
        rgb_array = np.zeros((CFG_LED_STRIP.num_leds,3), dtype=np.uint8)
        detected = False
        while True:
            if r_transcript.ready():
                print(r_transcript.data['timestamp'])
                text = r_transcript.data['text']
                if detect_wake_word(text):
                    detected = True
                    print("DETECTED")
                else:
                    detected = False
            if detected:
                rgb_array[:, 1] = 255
            else:
                rgb_array[:, 1] = 0
            w_led_strip["rgb"] = rgb_array

if __name__ == "__main__":
    main()