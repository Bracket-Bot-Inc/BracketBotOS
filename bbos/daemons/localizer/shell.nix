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
    python311Packages.numpy
    python311Packages.matplotlib
    python311Packages.pybind11
    cmake
  ];

  shellHook = ''
    # Make inekf available in PYTHONPATH
    export PYTHONPATH="${inekf}/lib/python3.11/site-packages:$PYTHONPATH"
    
    if [ ! -d "venv" ]; then
      python -m venv venv --system-site-packages
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
      pip install -e ../../..
      # daemon dependencies
    else
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
    fi
  '';
} 