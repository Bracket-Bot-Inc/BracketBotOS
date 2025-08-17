# /// script
# dependencies = [
#   "bbos",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///

import os
import time
import sys
from pathlib import Path
from bbos import Reader, Config, Writer, Type
from subprocess import Popen, PIPE

OUTPUT_DIR = Path(".record_video")
DEFAULT_RECORD_FPS = 5

def main(record_fps=DEFAULT_RECORD_FPS):
    """Record video frames from camera daemon at specified FPS directly into ffmpeg."""
    
    frame_interval = 1.0 / record_fps
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    CFG = Config("stereo")
    print(f"[+] Recording video (encoded via ffmpeg)")
    print(f"[+] Camera: {CFG.width}x{CFG.height} @ {CFG.rate} fps")
    print(f"[+] Recording at {record_fps} fps (saving every {frame_interval*1000:.0f}ms)")
    
    frame_count = 0
    last_save_time = 0
    session_id = int(time.time())
    video_file = OUTPUT_DIR / f"{session_id}.mp4"

    # ffmpeg process
    p = Popen([
        'ffmpeg',
        '-y',
        '-f', 'image2pipe',
        '-vcodec', 'mjpeg',       # input: JPEG stream
        '-r', str(record_fps),
        '-i', '-',
        # Output codec & compression
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-pix_fmt', 'yuv420p',    # required for QuickTime compatibility
        str(video_file)
    ], stdin=PIPE)
    with Reader("camera.jpeg") as r_jpeg, \
         Writer("led_strip.ctrl", Type('led_strip_ctrl')) as w_led:
        color = [0, 0, 0]
        now = time.time()
        current_time = time.time()
        while True:
            if r_jpeg.ready():
                current_time = time.time()
                if current_time - last_save_time >= frame_interval:
                    # Grab JPEG data
                    jpeg_bytes = r_jpeg.data['jpeg'][:r_jpeg.data['bytesused']]
                    # Write JPEG to ffmpeg stdin
                    p.stdin.write(jpeg_bytes)
                    frame_count += 1
                    last_save_time = current_time
            if int(current_time - now) % 2 == 1:
                color = [255, 0, 0]  # Set LED to red
            else:
                color = [0, 0, 0]
            with w_led.buf() as buf:
                buf['rgb'][:] = color
            # Close ffmpeg stdin and wait for flush
    p.stdin.close()
    p.wait()
    print(f"[+] Saved {frame_count} frames to {video_file}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ['-h', '--help']:
        print("Usage: python record_video.py [fps]")
        print("  Records camera frames and encodes directly into video file")
        sys.exit(0)
    
    fps = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RECORD_FPS
    main(fps)
