# /// script
# dependencies = [
#   "bbos",
#   "sshkeyboard",
# ]
# [tool.uv.sources]
# bbos = { path = "/home/bracketbot/BracketBotOS", editable = true }
# ///
from bbos import Writer, Type
from sshkeyboard import listen_keyboard, stop_listening
import numpy as np

# Configuration
TURN_SPEED = 4.0  # Linear speed in m/s
SPEED = 1  # Angular speed in rad/s
# Global variables
writer = None

def press(key):
    """Handle key press events"""
    global writer, pressed
    if writer is None:
        return
    speed = 0.0
    turn = 0.0
    if key.lower() == 'w':
        speed = SPEED
    elif key.lower() == 's':
        speed = -SPEED
    elif key.lower() == 'a':
        turn = -TURN_SPEED
    elif key.lower() == 'd':
        turn = TURN_SPEED
    elif key.lower() == 'q':
        stop_listening()
    writer['twist'] = [speed, turn]

def release(key):
    """Handle key release events - stop the robot"""
    global writer, pressed
    if writer is None:
        return

    writer['twist'] = np.array([0.0, 0.0], dtype=np.float32)

def main():
    """Main control loop"""
    global writer
    
    try:
        # Initialize the drive control writer
        with Writer("drive.ctrl", Type("drive_ctrl")) as drive_writer:
            writer = drive_writer
            
            print("BracketBotOS WASD Robot Control + Camera Capture")
            print("===============================================")
            print("Controls:")
            print("  W - Move Forward")
            print("  S - Move Backward") 
            print("  A - Turn Left")
            print("  D - Turn Right")
            print("  Q - Quit")
            print("Press and hold keys to move, release to stop.")
            print("Ready for input...")
            
            # Start keyboard listener
            listen_keyboard(
                on_press=press,
                on_release=release,
                delay_second_char=0.05,
                delay_other_chars=0.02,
                sequential=False,
                sleep=0.01
            )
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        # Ensure robot stops
        if writer is not None:
            writer['twist'] = np.array([0.0, 0.0], dtype=np.float32)
        print("Robot stopped and camera capture ended. Goodbye!")

if __name__ == "__main__":
    main()
        