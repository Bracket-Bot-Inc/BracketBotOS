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
    python311Packages.opencv4
    python311Packages.scipy
    zlib
    libGL
    swig                    # required for binding generation
    glibc
    glibc.dev
    cmake
    xorg.libX11
  ];

  shellHook = ''
    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.zlib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.libGL}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.xorg.libX11}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.glibc.dev}/lib:$LD_LIBRARY_PATH

    if [ ! -d "venv" ]; then
      python -m venv venv
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
      pip install -e ../../..
      pip install -e /home/bracketbot/BracketBotAI
    else
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
    fi
  '';
} 
