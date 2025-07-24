# /// script
# dependencies = [
#   "sshkeyboard",
#   "bbos @ /home/GREEN/BracketBotOS/dist/bbos-0.0.1-py3-none-any.whl",
# ]
# ///
from bbos import Writer, Type, Time
from sshkeyboard import listen_keyboard, stop_listening
import numpy as np

# Configuration
SPEED = 0.5  # Linear speed in m/s
TURN_SPEED = 3.0  # Angular speed in rad/s
# Global variables
writer = None

def press(key):
    """Handle key press events"""
    global writer
    if writer is None:
        return
        
    if key.lower() == 'w':
        # Forward: positive linear velocity, zero angular
        writer['twist'] = np.array([SPEED, 0.0], dtype=np.float32)
    elif key.lower() == 's':
        # Backward: negative linear velocity, zero angular
        writer['twist'] = np.array([-SPEED, 0.0], dtype=np.float32)
    elif key.lower() == 'a':
        # Turn left: zero linear velocity, positive angular
        writer['twist'] = np.array([0.0, TURN_SPEED], dtype=np.float32)
    elif key.lower() == 'd':
        # Turn right: zero linear velocity, negative angular
        writer['twist'] = np.array([0.0, -TURN_SPEED], dtype=np.float32)
    elif key.lower() == 'q':
        # Quit
        stop_listening()

def release(key):
    """Handle key release events - stop the robot"""
    global writer
    if writer is None:
        return
        
    # Stop all movement on key release
    writer['twist'] = np.array([0.0, 0.0], dtype=np.float32)

def main():
    """Main control loop"""
    global writer
    
    try:
        # Initialize the drive control writer
        with Writer("/drive.ctrl", Type("drive_ctrl")) as drive_writer:
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
        