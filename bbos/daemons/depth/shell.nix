let
pkgs = import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/63dacb46bf939521bdc93981b4cbb7ecb58427a0.tar.gz";
  sha256 = "sha256:1lr1h35prqkd1mkmzriwlpvxcb34kmhc9dnr48gkm8hh089hifmx";
}) {};

  # ── Mali G610 driver + firmware packaged as a derivation ───────────────
  maliG610 = pkgs.stdenv.mkDerivation {
    pname   = "mali-g610-opencl";
    version = "g6p0";

    # Binary Valhall driver
    src = pkgs.fetchurl {
      url = "https://github.com/JeffyCN/mirrors/raw/libmali/lib/aarch64-linux-gnu/libmali-valhall-g610-g6p0-x11-wayland-gbm.so";
      sha256 = "sha256-Sz+eRzdezb+7EPZUa58zG7vobHTi9h4d13mnrOBnQl8=";  # run `nix-prefetch-url <url>` once
    };

    # Firmware blob
    fw = pkgs.fetchurl {
      url = "https://github.com/JeffyCN/mirrors/raw/libmali/firmware/g610/mali_csffw.bin";
      sha256 = "sha256-YP+jdu3sjEAtwO6TV8aF2DXsLg+z0HePMD0IqYAtV/E=";
    };

    dontUnpack = true;

    installPhase = ''
      mkdir -p $out/lib $out/lib/firmware $out/etc/OpenCL/vendors
      cp $src $out/lib/
      cp $fw  $out/lib/firmware/
      echo "$out/lib/$(basename $src)" > $out/etc/OpenCL/vendors/mali.icd
    '';
  };
in
pkgs.mkShell {
   buildInputs = with pkgs;  [ 
    python311
    python311.pkgs.virtualenv
    python311.pkgs.pip
    python311.pkgs.numpy
    python311.pkgs.opencv4
    python311.pkgs.pyyaml

    mesa         # mesa-opencl-icd
    ocl-icd              # ocl-icd-opencl-dev (runtime)
    opencl-headers       # headers split out in Nix
    clinfo               # diagnostic tool
    maliG610             # driver + firmware + ICD file
    libdrm
    xorg.libxcb
    wayland

    zlib
    libGL
    glibc
    xorg.libX11
    glibc.dev
  ];

  shellHook = ''
    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.zlib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.libGL}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.xorg.libX11}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.xorg.libxcb}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.wayland}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.libdrm}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:${maliG610}/lib
    export OCL_ICD_VENDORS=${maliG610}/etc/OpenCL/vendors

    if [ ! -d "venv" ]; then
      python -m venv venv
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
      pip install -e ../../..
    else
      source venv/bin/activate
      
      echo "Virtual environment activated. Use 'deactivate' to exit."
    fi

  '';
}
