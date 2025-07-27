# /// script
# dependencies = [
#   "bbos @ /home/GREEN/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
# ]
# ///

import os
import time
import sys
from pathlib import Path
from bbos import Reader, Config, Loop


OUTPUT_DIR = Path(".record_video")

def main():
    """Record video frames from camera daemon with configurable cadence."""
    
    # Ensure output directory exists
    print(os.listdir())
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Get camera config for context
    CFG = Config("stereo")
    print(f"[+] Recording video to {OUTPUT_DIR}")
    print(f"[+] Camera: {CFG.width}x{CFG.height} @ {CFG.rate} fps")
    
    frame_count = 0

    session_id = int(time.time())
    
    with Reader("/camera.jpeg") as r_jpeg:
        while True:
            if r_jpeg.ready():
                # Extract JPEG data 
                jpeg_bytes = r_jpeg.data['jpeg'][:r_jpeg.data['bytesused']]
                timestamp = r_jpeg.data['timestamp']
                
                # Generate filename with session ID, frame number, and timestamp
                filename = f"{session_id}_{frame_count:06d}_{timestamp:.3f}.jpg"
                filepath = OUTPUT_DIR / filename
                
                # Write JPEG frame efficiently
                with open(filepath, 'wb') as f:
                    f.write(jpeg_bytes)
                
                frame_count += 1
                
            Loop.sleep()

if __name__ == "__main__":
    # Show usage if requested
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print("Usage: python record_video.py [cadence_ms]")
        print(f"  cadence_ms: Recording interval in milliseconds (default: {DEFAULT_CADENCE_MS})")
        print("  Example: python record_video.py 250  # Record every 250ms (4 Hz)")
        sys.exit(0)
    
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n[+] Recording stopped")
