{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    python311
    python311.pkgs.virtualenv
    python311.pkgs.pip
    zlib
    python311.pkgs.evdev
    libGL
    glibc
    xorg.libX11
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

      pip install -e ../..
      pip install fastapi uvicorn websockets wsproto
    else
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
    fi 
  '';
}
