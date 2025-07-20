{ pkgs ? import <nixpkgs> {} }:
pkgs.mkShell {
  buildInputs = with pkgs; [
    python311
    python311.pkgs.virtualenv
    python311.pkgs.pip
    python311.pkgs.numpy
    python311.pkgs.spidev
    zlib
    stdenv.cc.cc.lib
    gcc14
  ];

  shellHook = ''
    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.zlib}/lib:$LD_LIBRARY_PATH

    if [ ! -d "venv" ]; then
      python -m venv venv
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
      
      # Enable SPI for LED communication
      echo "Enabling SPI interface..."
      sudo raspi-config nonint do_spi 0
      
      # Add user to spi group for SPI permissions
      echo "Adding user to spi group for SPI permissions..."
      sudo usermod -a -G spi "$USER"
      
      # Install Python packages
      pip install Pi5Neo>=1.0.0
      pip install -e ../../..
    else
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
    fi
  '';
}
