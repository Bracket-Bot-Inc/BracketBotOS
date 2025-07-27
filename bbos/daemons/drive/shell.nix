{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  buildInputs = with pkgs; [
    python311
    python311.pkgs.virtualenv
    python311.pkgs.pip
    python311.pkgs.numpy
    zlib
    python311.pkgs.evdev
    stdenv.cc.cc.lib
    libGL
    xorg.libX11
    gcc14
  ];

  shellHook = ''

    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.zlib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.libGL}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.xorg.libX11}/lib:$LD_LIBRARY_PATH

    if [ ! -d "venv" ]; then
      python -m venv venv
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
      # Add user to dialout group for UART communication
      echo "Adding user to dialout group for UART permissions..."
      sudo usermod -a -G dialout "$USER"
      sudo bash -c "curl https://cdn.odriverobotics.com/files/odrive-udev-rules.rules > /etc/udev/rules.d/91-odrive.rules && udevadm control --reload-rules && udevadm trigger"
      pip install PyYAML odrive==0.5.1.post0 pyserial
      pip install -e ../../..
    else
      source venv/bin/activate
      sudo setcap 'cap_sys_nice=eip' $(readlink -f $(command -v python3))
      echo "Virtual environment activated. Use 'deactivate' to exit."
    fi
  '';
}
