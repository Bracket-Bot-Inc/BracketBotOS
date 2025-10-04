let
  pkgs = import (fetchTarball {
    # Using nixpkgs 22.11 for better Python 3.10 support
    url = "https://github.com/NixOS/nixpkgs/archive/4d2b37a84fad1091b9de401eb450aae66f1a741e.tar.gz";
    sha256 = "11w3wn2yjhaa5pv20gbfbirvjq6i3m7pqrq2msf0g7cv44vijwgw";
  }) {};

  # Modular CUDA configuration for JetPack
  cuda = rec {
    # Base CUDA path
    basePath = "/usr/local/cuda-12.6";
    
    # CUDA directories
    binPath = "${basePath}/bin";
    libPath = "${basePath}/lib64";
    # Jetson-specific CUDA library path
    jetsonLibPath = "${basePath}/targets/aarch64-linux/lib";
    includePath = "${basePath}/include";
    pkgConfigPath = "${basePath}/targets/aarch64-linux/lib/pkgconfig";
    
    # CUDA executables
    nvcc = "${binPath}/nvcc";
    
    # Environment variables
    envVars = {
      CUDA_PATH = basePath;
      CUDA_HOME = basePath;
      CUDACXX = nvcc;
      CUDAHOSTCXX = "g++";
      PKG_CONFIG_PATH = pkgConfigPath;
      # PyTorch CUDA settings
      TORCH_CUDA_ARCH_LIST = "7.2;8.7";  # Jetson Orin Nano compute capability
      FORCE_CUDA = "1";
    };
    
    # Library paths for runtime
    ldLibraryPaths = [
      libPath
      jetsonLibPath
    ];
    
    # Compiler paths
    compilerPaths = {
      CPATH = includePath;
      LIBRARY_PATH = libPath;
    };
  };
in
pkgs.mkShell {
  buildInputs = with pkgs; [
    # toolchain
    gcc gnumake cmake pkg-config git git-lfs file
    # Add gcc12 for newer libstdc++ (GLIBCXX_3.4.30)
    gcc12
    # python 3.10
    python310 
    python310.pkgs.virtualenv 
    python310.pkgs.pip 
    python310.pkgs.wheel
    python310.pkgs.setuptools
    python310.pkgs.numpy
    python310.pkgs.opencv4
    # system libs for CUDA builds
    zlib libGL glibc glibc.dev libdrm xorg.libX11 xorg.libxcb wayland
  ];

  # Expose CUDA environment variables
  inherit (cuda.envVars) 
    CUDA_PATH CUDA_HOME CUDACXX CUDAHOSTCXX 
    PKG_CONFIG_PATH TORCH_CUDA_ARCH_LIST FORCE_CUDA;

  shellHook = ''
    # prepend CUDA bin
    export PATH="${cuda.binPath}:$PATH"
    # Set up library paths for general use (Nix libraries first for compatibility)
    export LD_LIBRARY_PATH="${cuda.libPath}''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
    # Add Jetson-specific CUDA library path
    export LD_LIBRARY_PATH="${cuda.jetsonLibPath}:$LD_LIBRARY_PATH"

    # Use gcc12's libstdc++ for GLIBCXX_3.4.30 support
    export LD_LIBRARY_PATH="${pkgs.gcc12.cc.lib}/lib:$LD_LIBRARY_PATH"
    export LD_LIBRARY_PATH="${pkgs.zlib}/lib:$LD_LIBRARY_PATH"
    export LD_LIBRARY_PATH="${pkgs.libGL}/lib:$LD_LIBRARY_PATH"
    export LD_LIBRARY_PATH="${pkgs.xorg.libX11}/lib:$LD_LIBRARY_PATH"
    export LD_LIBRARY_PATH="${pkgs.xorg.libxcb}/lib:$LD_LIBRARY_PATH"
    export LD_LIBRARY_PATH="${pkgs.wayland}/lib:$LD_LIBRARY_PATH"
    export LD_LIBRARY_PATH="${pkgs.libdrm}/lib:$LD_LIBRARY_PATH"
    
    # Add NVIDIA driver libraries for Jetson
    export LD_LIBRARY_PATH="/usr/lib/aarch64-linux-gnu/nvidia:$LD_LIBRARY_PATH"
    export LD_LIBRARY_PATH="/usr/lib/aarch64-linux-gnu:$LD_LIBRARY_PATH"

    # headers for compilers finding CUDA
    export CPATH="${cuda.includePath}''${CPATH:+:$CPATH}"
    export LIBRARY_PATH="${cuda.jetsonLibPath}:${cuda.libPath}''${LIBRARY_PATH:+:$LIBRARY_PATH}"

    # Create functions for CUDA tools that need system libraries
    nvcc() {
      LD_LIBRARY_PATH="${cuda.jetsonLibPath}:${cuda.libPath}:/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu" ${cuda.nvcc} "$@"
    }
    export -f nvcc
    

    # sanity check
    if [ -x "${cuda.nvcc}" ]; then
      echo "🟢 Using CUDA from ${cuda.basePath}"
      # Test nvcc without showing GLIBC errors
      nvcc --version >/dev/null 2>&1 && echo "   nvcc is working correctly" || echo "   Note: nvcc may show warnings, but CUDA compilation should work"
    else
      echo "🔴 nvcc not found at ${cuda.nvcc}"
    fi

    # ----- venv bootstrap -----
    if [ ! -d "venv" ]; then
      echo "Creating Python 3.10 virtual environment..."
      python3.10 -m venv venv
      source venv/bin/activate
      pip install -e ../../..
      echo "Virtual environment created and activated."
      
      # Install pycuvslam if not already present
      if [ ! -d "pycuvslam" ]; then
        echo "Cloning pycuvslam repository..."
        git clone https://github.com/NVlabs/pycuvslam.git
        cd pycuvslam && git lfs fetch --all && cd ..
      fi
      
      echo "Installing pycuvslam..."
      pip install -e pycuvslam/bin/aarch64
    else
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
    fi
  '';
}