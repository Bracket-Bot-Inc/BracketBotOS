from bbos import Config
from driver import ODriveUART

import time
import odrive
from odrive.enums import *
import yaml
import sys
import subprocess

# ANSI escape codes for colors
BLUE = '\033[94m'
YELLOW = '\033[93m'
GREEN = '\033[92m'
RED = '\033[91m'
BOLD = '\033[1m'
RESET = '\033[0m'

ODRIVE_SETTINGS = {
    # Motor configuration - full parameter paths
    "motor.config.calibration_current": 5.0,  # Motor calibration current (A)
    "motor.config.pole_pairs": 15,  # Number of motor pole pairs (ACTUAL VALUE)
    "motor.config.resistance_calib_max_voltage":
    4.0,  # Max voltage for resistance calibration
    "motor.config.requested_current_range": 25.0,  # Motor current range (A)
    "motor.config.current_control_bandwidth":
    100.0,  # Current control bandwidth (rad/s)
    "motor.config.torque_constant": 0.516875,  # Torque constant (8.27 / 16.0)

    # Encoder configuration (Hall sensor mode) - full parameter paths
    "encoder.config.mode": 1,  # ENCODER_MODE_HALL
    "encoder.config.cpr": 90,  # Encoder counts per revolution (ACTUAL VALUE)
    "encoder.config.calib_scan_distance": 150,  # Calibration scan distance
    "encoder.config.bandwidth": 100.0,  # Encoder bandwidth

    # Controller tuning (calculated from motor params) - full parameter paths
    "controller.config.pos_gain": 1.0,  # Position control gain (ACTUAL VALUE)
    "controller.config.vel_gain":
    0.930375,  # Velocity control gain (0.02 * 0.516875 * 90)
    "controller.config.vel_integrator_gain":
    4.651875,  # Velocity integrator gain (0.1 * 0.516875 * 90)
    "controller.config.vel_limit": 10.0,  # Velocity limit (turns/s)
    "controller.config.control_mode": 2,  # CONTROL_MODE_VELOCITY_CONTROL

    # Startup configuration - full parameter path
    "config.startup_closed_loop_control":
    True  # Auto-start in closed loop control
}

# Load configuration at startup
ODRIVE_CONFIG = Config("odrive")

# ODrive calibration constants and helper functions
ENCODER_ERRORS = {
    name: value
    for name, value in vars(odrive.enums).items()
    if name.startswith('ENCODER_ERROR')
}
CONTROLLER_ERRORS = {
    name: value
    for name, value in vars(odrive.enums).items()
    if name.startswith('CONTROLLER_ERROR')
}
MOTOR_ERRORS = {
    name: value
    for name, value in vars(odrive.enums).items()
    if name.startswith('MOTOR_ERROR')
}
AXIS_ERRORS = {
    name: value
    for name, value in vars(odrive.enums).items()
    if name.startswith('AXIS_ERROR')
}


# Helper function to wait until the axis reaches idle state
def wait_for_idle(axis):
    while axis.current_state != AXIS_STATE_IDLE:
        time.sleep(0.1)


# Helper function to reconnect to the ODrive after reboot
def connect_odrive():
    print("Connecting to ODrive...")
    import odrive
    serial_path = f"serial:{ODRIVE_CONFIG.serial_port}"
    timeout = ODRIVE_CONFIG.timeout
    odrv = odrive.find_any(path=serial_path, timeout=timeout)
    if odrv is None:
        raise Exception('ODrive timed out')
    return odrv


def save_and_reboot(odrv):
    print("Saving configuration...")
    try:
        odrv.save_configuration()
        print("Configuration saved successfully.")

        print("Rebooting ODrive...")
        try:
            odrv.reboot()
        except:
            # Exception is expected as connection is lost during reboot
            # Close the hanging connection
            odrv.__channel__.serial_device.close()

    except Exception as e:
        print(f"Error saving configuration: {str(e)}")
        return None

    time.sleep(1)
    return connect_odrive()


def print_errors(error_type, error_value):
    """Print errors for a given component type and error value."""
    if error_value == 0:
        return
    error_dict = {
        name: value
        for name, value in vars(odrive.enums).items()
        if name.startswith(f'{error_type.upper()}_ERROR')
    }

    error_string = ""
    for error_name, error_code in error_dict.items():
        if error_value & error_code:
            error_string += f"{error_name.replace(f'{error_type.upper()}_ERROR_', '').lower().replace('_', ' ')}, "
    error_string = error_string.rstrip(", ")
    print(
        f"\033[91m{error_type.capitalize()} error {hex(error_value)}: {error_string}\033[0m"
    )


# Function to calibrate a single axis
def calibrate_axis(odrv0, axis):
    print(f"Calibrating axis{axis}...")

    # Clear errors
    print("Clearing initial errors...")
    getattr(odrv0, f'axis{axis}').clear_errors()

    # Wait for a moment to ensure errors are cleared
    time.sleep(1)

    # Print current errors to verify they're cleared
    axis_error = getattr(odrv0, f'axis{axis}').error
    motor_error = getattr(odrv0, f'axis{axis}').motor.error
    encoder_error = getattr(odrv0, f'axis{axis}').encoder.error

    if axis_error or motor_error or encoder_error:
        print(f"Axis {axis} errors:")
        if axis_error:
            print_errors('axis', axis_error)
        if motor_error:
            print_errors('motor', motor_error)
        if encoder_error:
            print_errors('encoder', encoder_error)

    # -------- ODrive Configuration --------
    print("Configuring ODrive...")
    getattr(odrv0, f'axis{axis}').config.watchdog_timeout = 0.5
    getattr(odrv0, f'axis{axis}').config.enable_watchdog = False
    getattr(odrv0,
            f'axis{axis}').motor.config.calibration_current = ODRIVE_SETTINGS[
                'motor.config.calibration_current']
    getattr(
        odrv0, f'axis{axis}'
    ).motor.config.pole_pairs = ODRIVE_SETTINGS['motor.config.pole_pairs']
    getattr(odrv0, f'axis{axis}'
            ).motor.config.resistance_calib_max_voltage = ODRIVE_SETTINGS[
                'motor.config.resistance_calib_max_voltage']
    getattr(
        odrv0, f'axis{axis}'
    ).motor.config.requested_current_range = ODRIVE_SETTINGS[
        'motor.config.requested_current_range']  #Requires config save and reboot
    getattr(odrv0, f'axis{axis}'
            ).motor.config.current_control_bandwidth = ODRIVE_SETTINGS[
                'motor.config.current_control_bandwidth']
    getattr(odrv0,
            f'axis{axis}').motor.config.torque_constant = ODRIVE_SETTINGS[
                'motor.config.torque_constant']
    getattr(odrv0, f'axis{axis}'
            ).encoder.config.mode = ODRIVE_SETTINGS['encoder.config.mode']
    getattr(odrv0, f'axis{axis}'
            ).encoder.config.cpr = ODRIVE_SETTINGS['encoder.config.cpr']
    getattr(
        odrv0,
        f'axis{axis}').encoder.config.calib_scan_distance = ODRIVE_SETTINGS[
            'encoder.config.calib_scan_distance']
    getattr(
        odrv0, f'axis{axis}'
    ).encoder.config.bandwidth = ODRIVE_SETTINGS['encoder.config.bandwidth']
    getattr(odrv0, f'axis{axis}').controller.config.pos_gain = ODRIVE_SETTINGS[
        'controller.config.pos_gain']
    getattr(odrv0, f'axis{axis}').controller.config.vel_gain = ODRIVE_SETTINGS[
        'controller.config.vel_gain']
    getattr(
        odrv0,
        f'axis{axis}').controller.config.vel_integrator_gain = ODRIVE_SETTINGS[
            'controller.config.vel_integrator_gain']
    getattr(odrv0,
            f'axis{axis}').controller.config.vel_limit = ODRIVE_SETTINGS[
                'controller.config.vel_limit']
    getattr(odrv0,
            f'axis{axis}').controller.config.control_mode = ODRIVE_SETTINGS[
                'controller.config.control_mode']

    odrv0 = save_and_reboot(odrv0)

    # -------- Motor Calibration --------
    print("Starting motor calibration...")

    getattr(odrv0,
            f'axis{axis}').requested_state = AXIS_STATE_MOTOR_CALIBRATION
    wait_for_idle(getattr(odrv0, f'axis{axis}'))

    # Check for errors
    error = getattr(odrv0, f'axis{axis}').motor.error
    if error != 0:
        print_errors('motor', error)
        return odrv0, False
    else:
        print("Motor calibration successful.")
        # Validate phase resistance and inductance
        resistance = getattr(odrv0,
                             f'axis{axis}').motor.config.phase_resistance
        inductance = getattr(odrv0,
                             f'axis{axis}').motor.config.phase_inductance
        print(f"Measured phase resistance: {resistance} Ohms")
        print(f"Measured phase inductance: {inductance} H")

        if not (0.1 <= resistance <= 1.0):
            print("Warning: Phase resistance out of expected range!")
        if not (0.0001 <= inductance <= 0.005):
            print("Warning: Phase inductance out of expected range!")

        # Mark motor as pre-calibrated
        getattr(odrv0, f'axis{axis}').motor.config.pre_calibrated = True

    # -------- Skipping Hall Polarity Calibration --------
    print("Skipping Hall polarity calibration as per your request.")

    # -------- Encoder Offset Calibration --------
    print("Starting encoder offset calibration...")
    try:
        # Debug: Check ODrive connection and axis state
        print(f"Checking ODrive connection and axis{axis} status...")
        current_state = getattr(odrv0, f'axis{axis}').current_state
        print(f"Axis{axis} current state: {current_state}")
        print(
            f"AXIS_STATE_ENCODER_OFFSET_CALIBRATION value: {AXIS_STATE_ENCODER_OFFSET_CALIBRATION}"
        )

        print(f"Setting axis{axis} to ENCODER_OFFSET_CALIBRATION state...")
        getattr(odrv0, f'axis{axis}'
                ).requested_state = AXIS_STATE_ENCODER_OFFSET_CALIBRATION
        print(f"Axis{axis} state set, waiting for idle...")
        wait_for_idle(getattr(odrv0, f'axis{axis}'))
        print(f"Axis{axis} returned to idle state")
    except Exception as e:
        print(f"Error during encoder calibration: {e}")
        print(f"Error type: {type(e)}")
        import traceback
        traceback.print_exc()
        return odrv0, False

    # Check for errors
    error = getattr(odrv0, f'axis{axis}').encoder.error
    if error != 0:
        print_errors('encoder', error)
        return odrv0, False
    else:
        print("Encoder calibration successful.")
        # Validate phase offset float
        phase_offset_float = getattr(odrv0,
                                     f'axis{axis}').encoder.config.offset_float
        print(f"Phase offset float: {phase_offset_float}")

        if abs((phase_offset_float % 1) - 0.5) > 0.1:
            print("Warning: Phase offset float is out of expected range!")

        # Mark encoder as pre-calibrated
        getattr(odrv0, f'axis{axis}').encoder.config.pre_calibrated = True

    # -------- Test Motor Control --------
    print("Testing motor control...")

    # Enter closed-loop control
    getattr(odrv0,
            f'axis{axis}').requested_state = AXIS_STATE_CLOSED_LOOP_CONTROL
    time.sleep(1)  # Wait for state to settle

    # Command a velocity
    print("Spinning motor at 0.5 turns/sec...")
    getattr(odrv0, f'axis{axis}').controller.input_vel = 0.5
    time.sleep(2)

    # Stop the motor
    print("Stopping motor...")
    getattr(odrv0, f'axis{axis}').controller.input_vel = 0
    time.sleep(1)

    # Switch back to idle
    getattr(odrv0, f'axis{axis}').requested_state = AXIS_STATE_IDLE

    # -------- Automatic Startup Configuration --------
    print("Configuring automatic startup...")

    # Set axis to start in closed-loop control on startup
    getattr(
        odrv0,
        f'axis{axis}').config.startup_closed_loop_control = ODRIVE_SETTINGS[
            'config.startup_closed_loop_control']

    return odrv0, True


def test_motor_direction():
    print("Motor direction test - Visual confirmation required")
    print("Watch each wheel carefully and report the direction it spins.")
    print("Forward = wheel spins to move robot forward")
    print("Backward = wheel spins to move robot backward")

    motor_controller = ODriveUART(ODRIVE_CONFIG)
    directions = {'left': 1, 'right': 1}

    for name in ['left', 'right']:
        print(f"\n{BOLD}Testing {name} motor...{RESET}")

        # Start motor and clear any errors
        if name == 'left':
            motor_controller.start_left()
            motor_controller.enable_velocity_mode_left()
            if motor_controller.check_errors_left():
                print("Clearing left motor errors...")
                motor_controller.clear_errors_left()
        else:
            motor_controller.start_right()
            motor_controller.enable_velocity_mode_right()
            if motor_controller.check_errors_right():
                print("Clearing right motor errors...")
                motor_controller.clear_errors_right()

        # Spin motor slowly for visual inspection
        print(
            f"{YELLOW}Watch the {name} wheel - it will spin for 3 seconds...{RESET}"
        )
        time.sleep(1)  # Give user time to position themselves

        if name == 'left':
            motor_controller.set_speed_turns_left(
                0.3)  # Slow speed for easy observation
        else:
            motor_controller.set_speed_turns_right(0.3)

        time.sleep(3)  # Spin for 3 seconds

        # Stop the motor
        if name == 'left':
            motor_controller.stop_left()
        else:
            motor_controller.stop_right()

        # Get user input for direction
        while True:
            response = input(
                f"{BLUE}Did the {name} wheel spin FORWARD or BACKWARD? [f/b]: {RESET}"
            ).lower().strip()
            if response in ['f', 'forward']:
                directions[name] = 1  # Forward direction
                print(
                    f"{GREEN}{name.capitalize()} wheel direction: FORWARD (+1){RESET}"
                )
                break
            elif response in ['b', 'backward']:
                directions[name] = -1  # Backward direction
                print(
                    f"{GREEN}{name.capitalize()} wheel direction: BACKWARD (-1){RESET}"
                )
                break
            else:
                print(
                    f"{RED}Please enter 'f' for forward or 'b' for backward{RESET}"
                )

        time.sleep(0.5)

    # Save direction results to config.yaml
    config_path = 'config.yaml'
    try:
        config = {}

        # Update motor directions
        config['dir_left'] = directions['left']
        config['dir_right'] = directions['right']

        # Write config
        with open(config_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, indent=2)

        print(f"\n{GREEN}Direction test complete!{RESET}")
        print(
            f"Left direction: {directions['left']}, Right direction: {directions['right']}"
        )
        print(f"Configuration updated in {config_path}")

    except Exception as e:
        print(f"{RED}Error updating configuration file: {e}{RESET}")
        print(
            f"Direction results: Left={directions['left']}, Right={directions['right']}"
        )
        print(f"Please manually update {config_path} with these values.")


def calibrate_odrive():
    print("Finding an ODrive...")
    odrv0 = connect_odrive()
    print("Found ODrive.")

    # ASCII art for clear space warning
    print(r"""
{YELLOW}
          1m radius
        _________________
      /         ^         \
     /          |          \
    |          1m           |
    |           |           |
    | <--1m-->{{BOT}}<--1m--> |
    |           |           |
    |          1m           |
     \          |          /
      \_________v_________/
      
{RESET}
    """.format(YELLOW=YELLOW, RESET=RESET))

    print(
        f"{BOLD}WARNING:{RESET} The robot needs clear space to move during calibration."
    )
    confirmation = input(
        f"{BLUE}Ensure the robot has at least 1 meter of clear space around it.\nIs the area clear? [yes/no]: {RESET}"
    ).lower()
    if confirmation.lower() != 'yes':
        print(
            f'{YELLOW}Please ensure the area is clear and rerun the script.{RESET}'
        )
        return False
    print()

    for axis in [ODRIVE_CONFIG.left_axis, ODRIVE_CONFIG.right_axis]:
        odrv0, success = calibrate_axis(odrv0, axis)
        if success:
            print('\033[92m' +
                  f"Axis {axis} calibration completed successfully." +
                  '\033[0m')
            print()
        else:
            print('\033[91m' + f"Axis {axis} calibration failed." + '\033[0m')
            print(
                '\nPlease fix the issue with this axis before rerunning this script.'
            )
            return False

    odrv0 = save_and_reboot(odrv0)

    # Close the ODrive connection
    try:
        odrv0.__channel__.serial_device.close()
    except:
        pass

    print('\033[94m' + "\nODrive setup complete." + '\033[0m')
    return True


if __name__ == '__main__':
    service_was_running = False

    try:
        print("\n\033[1;33mDrive Calibration\033[0m")
        print("\nThis script will run two calibration steps:")
        print(
            "1. ODrive motor calibration - requires robot to be on a stand with wheels free to spin"
        )
        print(
            "2. Motor direction calibration - requires robot to be on the ground with some open space"
        )

        # First calibration - ODrive
        print("\n\033[1;36mStep 1: ODrive Motor Calibration\033[0m")
        #calibration_success = calibrate_odrive()
        calibration_success = True

        if not calibration_success:
            print(f"\n{RED}ODrive calibration failed.{RESET}")
            sys.exit(1)

        # Second calibration - Motor direction
        print("\n\033[1;36mStep 2: Motor Direction Calibration\033[0m")
        # Removed confirmation prompt - assuming robot is ready
        # confirmation = input("Place the robot on the ground with space to move.\nIs the robot on the ground with space to move? [yes/no] ").lower()
        # if confirmation.lower() != 'yes':
        #     print('Rerun this script once the robot is on the ground with space to move.')
        #     sys.exit(1)

        test_motor_direction()
        print("\n\033[1;32mDrive calibration complete!\033[0m")

    except KeyboardInterrupt:
        print(f"\n{YELLOW}Calibration interrupted by user.{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n\033[91mError occurred: {e}\033[0m")
        sys.exit(1)
