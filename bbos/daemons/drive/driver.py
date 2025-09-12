import serial
import odrive.enums
import os
import yaml
from bbos import Config

CFG_drive = Config("drive")


class ODriveUART:
    ERROR_DICT = {
        k: v
        for k, v in odrive.enums.__dict__.items()
        if k.startswith("AXIS_ERROR_")
    }

    def __init__(self, cfg):
        self.cfg = cfg
        # Use config values or override with parameters
        self.AXIS_STATE_CLOSED_LOOP_CONTROL = cfg.axis_state_closed_loop
        self.SERIAL_PORT = cfg.serial_port
        self.left_axis = cfg.left_axis
        self.right_axis = cfg.right_axis
        try:
            with open("config.yaml") as f:
                yml = yaml.safe_load(f) or {}
        except FileNotFoundError:
            yml = {}
        self.dir_left = yml.get("dir_left", cfg.dir_left)
        self.dir_right = yml.get("dir_right", cfg.dir_right)
        self.bus = serial.Serial(port=self.SERIAL_PORT,
                                 baudrate=cfg.baudrate,
                                 parity=serial.PARITY_NONE,
                                 stopbits=serial.STOPBITS_ONE,
                                 bytesize=serial.EIGHTBITS,
                                 timeout=cfg.timeout)

        # Clear the ASCII UART buffer
        self.bus.reset_input_buffer()
        self.bus.reset_output_buffer()

    def send_command(self, command: str):
        self.bus.reset_input_buffer()
        self.bus.write(f"{command}\n".encode())
        # Wait for the response if it's a read command
        if command.startswith('r') or command.startswith('f'):
            # Read until a newline character is encountered
            response = self.bus.readline().decode('ascii').strip()
            # If the response is empty, print a debug message
            if response == '':
                print(f"No response received for command: {command}")
            return response
        else:
            return None

    def get_config_parameter(self, parameter_path: str):
        response = self.send_command(f'r {parameter_path}')
        if response == '':
            print(
                f"No response received for config parameter: {parameter_path}")
            return None
        return response

    def get_errors_left(self):
        response = self.send_command(f'r axis{self.left_axis}.error')
        try:
            cleaned_response = ''.join(c for c in response if c.isdigit())
            return int(cleaned_response)
        except ValueError:
            print(f"Unexpected error response format: {response}")
            return -1  # Return -1 to indicate parsing error

    def get_errors_right(self):
        response = self.send_command(f'r axis{self.right_axis}.error')
        try:
            cleaned_response = ''.join(c for c in response if c.isdigit())
            return int(cleaned_response)
        except ValueError:
            print(f"Unexpected error response format: {response}")
            return -1  # Return -1 to indicate parsing error

    def has_errors(self):
        for axis in [0, 1]:
            error_response = self.send_command(f'r axis{axis}.error')
            try:
                cleaned_response = ''.join(c for c in error_response
                                           if c.isdigit())
                error_code = int(cleaned_response)
            except ValueError:
                print(f"Unexpected error response format: {error_response}")
                return True
            if error_code != 0:
                return True
        return False

    def dump_errors(self):
        error_sources = [
            "axis0", "axis0.encoder", "axis0.controller", "axis0.motor",
            "axis1", "axis1.encoder", "axis1.controller", "axis1.motor"
        ]
        print('======= ODrive Errors =======', flush=True)
        for src in error_sources:
            error_response = self.send_command(f'r {src}.error')
            try:
                cleaned_response = ''.join(c for c in error_response
                                           if c.isdigit())
                error_code = int(cleaned_response)
            except ValueError:
                print(f"Unexpected error response format: {error_response}")
                continue

            if error_code == 0:
                print(src + '.error=0x0: \033[92mNone\033[0m', flush=True)
                continue

            error_prefix = f"{src.split('.')[-1].strip('01').upper()}_ERROR"
            error_dict = {
                name: value
                for name, value in vars(odrive.enums).items()
                if name.startswith(error_prefix)
            }
            error_string = ""
            for error_name, code in error_dict.items():
                if error_code & code:
                    error_string += f"{error_name.replace(error_prefix + '_', '').lower().replace('_', ' ')}, "
            error_string = error_string.rstrip(", ")
            print(
                f"{src}.error={hex(error_code)}: \033[91m{error_string}\033[0m", flush=True
            )
        print('=============================', flush=True)

    def enable_torque_mode_left(self):
        self.send_command(
            f'w axis{self.left_axis}.controller.config.control_mode 1')
        self.send_command(
            f'w axis{self.left_axis}.controller.config.input_mode 1')
        print(f"Left axis set to torque control mode")

    def enable_torque_mode_right(self):
        self.send_command(
            f'w axis{self.right_axis}.controller.config.control_mode 1')
        self.send_command(
            f'w axis{self.right_axis}.controller.config.input_mode 1')
        print(f"Right axis set to torque control mode")

    def enable_velocity_mode_left(self):
        self.send_command(
            f'w axis{self.left_axis}.controller.config.control_mode 2')
        self.send_command(
            f'w axis{self.left_axis}.controller.config.input_mode 1')
        print(f"Left axis set to velocity control mode")

    def enable_velocity_mode_right(self):
        self.send_command(
            f'w axis{self.right_axis}.controller.config.control_mode 2')
        self.send_command(
            f'w axis{self.right_axis}.controller.config.input_mode 1')
        print(f"Right axis set to velocity control mode")

    def enable_velocity_ramp_mode_left(self):
        self.send_command(
            f'w axis{self.left_axis}.controller.config.control_mode 2')
        self.send_command(
            f'w axis{self.left_axis}.controller.config.input_mode 2')
        print(f"Left axis set to ramped velocity control mode")

    def enable_velocity_ramp_mode_right(self):
        self.send_command(
            f'w axis{self.right_axis}.controller.config.control_mode 2')
        self.send_command(
            f'w axis{self.right_axis}.controller.config.input_mode 2')
        print(f"Right axis set to ramped velocity control mode")

    def set_velocity_ramp_rate_left(self, ramp_rate):
        self.send_command(
            f'w axis{self.left_axis}.controller.config.vel_ramp_rate {ramp_rate:.4f}'
        )
        print(f"Left axis velocity ramp rate set to {ramp_rate:.4f} turns/s^2")

    def set_velocity_ramp_rate_right(self, ramp_rate):
        self.send_command(
            f'w axis{self.right_axis}.controller.config.vel_ramp_rate {ramp_rate:.4f}'
        )
        print(
            f"Right axis velocity ramp rate set to {ramp_rate:.4f} turns/s^2")

    def start_left(self):
        self.send_command(f'w axis{self.left_axis}.requested_state 8')

    def start_right(self):
        self.send_command(f'w axis{self.right_axis}.requested_state 8')

    def set_speed_turns_left(self, turns):
        self.send_command(
            f'w axis{self.left_axis}.controller.input_vel {turns * self.dir_left:.4f}'
        )

    def set_speed_turns_right(self, turns):
        self.send_command(
            f'w axis{self.right_axis}.controller.input_vel {turns * self.dir_right:.4f}'
        )

    def set_speed_mps_left(self, mps):
        rps = mps / (CFG_drive.wheel_diam * 3.14159)
        self.send_command(
            f'w axis{self.left_axis}.controller.input_vel {rps * self.dir_left:.4f}'
        )

    def set_speed_mps_right(self, mps):
        rps = mps / (CFG_drive.wheel_diam * 3.14159)
        self.send_command(
            f'w axis{self.right_axis}.controller.input_vel {rps * self.dir_right:.4f}'
        )

    def set_torque_nm_left(self, nm):
        torque_bias = self.cfg.torque_bias  # Small torque bias in Nm
        adjusted_torque = nm * self.dir_left + (torque_bias * self.dir_left *
                                                (1 if nm >= 0 else -1))
        # IDK why we dont use the controller.input_torque command, but it seems to be broken.
        # self.send_command(f'w axis{self.left_axis}.controller.input_torque {adjusted_torque:.4f}')
        self.send_command(f'c {self.left_axis} {adjusted_torque:.4f}')
        self.send_command(f'u {self.left_axis}')

    def set_torque_nm_right(self, nm):
        torque_bias = self.cfg.torque_bias  # Small torque bias in Nm
        adjusted_torque = nm * self.dir_right + (torque_bias * self.dir_right *
                                                 (1 if nm >= 0 else -1))
        # IDK why we dont use the controller.input_torque command, but it seems to be broken.
        # self.send_command(f'w axis{self.right_axis}.controller.input_torque {adjusted_torque:.4f}')
        self.send_command(f'c {self.right_axis} {adjusted_torque:.4f}')
        self.send_command(f'u {self.right_axis}')

    def get_pos_vel_left(self):
        pos, vel = self.send_command(f'f {self.left_axis}').split(' ')
        return float(pos) * self.dir_left, float(vel) * self.dir_left

    def get_pos_vel_right(self):
        pos, vel = self.send_command(f'f {self.right_axis}').split(' ')
        return float(pos) * self.dir_right, float(vel) * self.dir_right

    def stop_left(self):
        self.send_command(f'w axis{self.left_axis}.controller.input_vel 0')
        self.send_command(f'w axis{self.left_axis}.controller.input_torque 0')
        # Going at high torque and changing to idle causes overcurrent
        # self.send_command(f'w axis{self.left_axis}.requested_state 1')

    def stop_right(self):
        self.send_command(f'w axis{self.right_axis}.controller.input_vel 0')
        self.send_command(f'w axis{self.right_axis}.controller.input_torque 0')
        # Going at high torque and changing to idle causes overcurrent
        # self.send_command(f'w axis{self.right_axis}.requested_state 1')

    def check_errors_left(self):
        response = self.send_command(f'r axis{self.left_axis}.error')
        try:
            # Remove any non-numeric characters (like 'd' for decimal)
            cleaned_response = ''.join(c for c in response if c.isdigit())
            return int(cleaned_response) != 0
        except ValueError:
            print(f"Unexpected response format: {response}")
            return True  # Assume there's an error if we can't parse the response

    def check_errors_right(self):
        response = self.send_command(f'r axis{self.right_axis}.error')
        try:
            # Remove any non-numeric characters (like 'd' for decimal)
            cleaned_response = ''.join(c for c in response if c.isdigit())
            return int(cleaned_response) != 0
        except ValueError:
            print(f"Unexpected response format: {response}")
            return True  # Assume there's an error if we can't parse the response

    def clear_errors_left(self):
        self.send_command(f'w axis{self.left_axis}.error 0')
        self.send_command(
            f'w axis{self.left_axis}.requested_state {self.AXIS_STATE_CLOSED_LOOP_CONTROL}'
        )

    def clear_errors_right(self):
        self.send_command(f'w axis{self.right_axis}.error 0')
        self.send_command(
            f'w axis{self.right_axis}.requested_state {self.AXIS_STATE_CLOSED_LOOP_CONTROL}'
        )

    def enable_watchdog_left(self):
        self.send_command(f'w axis{self.left_axis}.config.enable_watchdog 1')

    def enable_watchdog_right(self):
        self.send_command(f'w axis{self.right_axis}.config.enable_watchdog 1')

    def disable_watchdog_left(self):
        self.send_command(f'w axis{self.left_axis}.config.enable_watchdog 0')

    def disable_watchdog_right(self):
        self.send_command(f'w axis{self.right_axis}.config.enable_watchdog 0')

    def set_watchdog_timeout(self, timeout):
        self.send_command(f'w axis0.config.watchdog_timeout {timeout}')
        self.send_command(f'w axis1.config.watchdog_timeout {timeout}')
    
    def feed_watchdog(self):
        self.send_command(f'w axis0.config.watchdog_feed 1')
        self.send_command(f'w axis1.config.watchdog_feed 1')

    def get_bus_voltage(self):
        response = self.send_command('r vbus_voltage')
        return f"{float(response):.1f}"
