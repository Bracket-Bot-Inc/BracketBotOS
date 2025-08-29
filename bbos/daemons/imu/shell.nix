let 
pkgs = import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/63dacb46bf939521bdc93981b4cbb7ecb58427a0.tar.gz";
  sha256 = "sha256:1lr1h35prqkd1mkmzriwlpvxcb34kmhc9dnr48gkm8hh089hifmx";
}) {};
in
pkgs.mkShell {
  buildInputs = with pkgs; [
    python311
    python311.pkgs.virtualenv
    python311.pkgs.pip
    python311.pkgs.numpy
    python311.pkgs.smbus2
    zlib
    stdenv.cc.cc.lib
    gcc14
    i2c-tools
  ];

  shellHook = ''
    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.zlib}/lib:$LD_LIBRARY_PATH

    if [ ! -d "venv" ]; then
      python -m venv venv
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
      
      # Enable I2C interface
      echo "Ensuring I2C is enabled..."
      if [ -e /boot/dietpiEnv.txt ]; then
        # Check if I2C is already enabled in DietPi
        if ! grep -q "^overlays=.*i2c0" /boot/dietpiEnv.txt; then
          echo "Please enable I2C using: sudo dietpi-config"
        fi
      fi
      
      # Add user to i2c group for I2C permissions
      echo "Adding user to i2c group for I2C permissions..."
      sudo usermod -a -G i2c "$USER"
      
      # Install Python packages
      pip install smbus2
      pip install -e ../../..
    else
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
    fi
  '';
} 