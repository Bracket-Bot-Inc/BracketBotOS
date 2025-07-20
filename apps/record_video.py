#!/usr/bin/env python3
# /// script
# dependencies = [
#   "numpy",
# ]
# ///

import os
import time
import sys
from pathlib import Path
from bbos import Reader, Config, Time

# Configuration
DEFAULT_CADENCE_MS = 500  # Default recording cadence in milliseconds

def get_cadence():
    """Get recording cadence from command line or use default."""
    if len(sys.argv) > 1:
        try:
            return int(sys.argv[1])
        except ValueError:
            print(f"[!] Invalid cadence '{sys.argv[1]}', using default {DEFAULT_CADENCE_MS}ms")
    return DEFAULT_CADENCE_MS

OUTPUT_DIR = Path(".record_video")

def main():
    """Record video frames from camera daemon with configurable cadence."""
    
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    # Get cadence and convert to Hz
    cadence_ms = get_cadence()
    cadence_hz = 1000 / cadence_ms
    
    # Get camera config for context
    CFG = Config("stereo")
    print(f"[+] Recording video at {cadence_hz:.1f} Hz ({cadence_ms}ms interval) to {OUTPUT_DIR}")
    print(f"[+] Camera: {CFG.width}x{CFG.height} @ {CFG.rate} fps")
    
    frame_count = 0
    session_start = time.time()
    session_id = int(session_start)
    
    t = Time(cadence_hz)
    
    with Reader("/camera.jpeg") as r_jpeg:
        while True:
            if r_jpeg.ready():
                stale, data = r_jpeg.get()
                if stale:
                    continue
                
                # Extract JPEG data 
                jpeg_bytes = data['jpeg'][:data['bytesused']]
                timestamp = data['timestamp']
                
                # Generate filename with session ID, frame number, and timestamp
                filename = f"{session_id}_{frame_count:06d}_{timestamp:.3f}.jpg"
                filepath = OUTPUT_DIR / filename
                
                # Write JPEG frame efficiently
                with open(filepath, 'wb') as f:
                    f.write(jpeg_bytes)
                
                frame_count += 1
                if frame_count % 10 == 0:  # Progress every 10 frames
                    elapsed = time.time() - session_start
                    rate = frame_count / elapsed
                    print(f"[+] Recorded {frame_count} frames ({rate:.1f} fps avg)")
                
            t.tick()

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
