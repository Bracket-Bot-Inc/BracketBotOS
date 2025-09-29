let
pkgs = import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/63dacb46bf939521bdc93981b4cbb7ecb58427a0.tar.gz";
  sha256 = "sha256:1lr1h35prqkd1mkmzriwlpvxcb34kmhc9dnr48gkm8hh089hifmx";
}) {};

  # Modular CUDA configuration for JetPack
  cuda = rec {
    # Base CUDA path
    basePath = "/usr/local/cuda-12.6";
    
    # CUDA directories
    binPath = "${basePath}/bin";
    libPath = "${basePath}/lib64";
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
    ];
    
    # Compiler paths
    compilerPaths = {
      CPATH = includePath;
      LIBRARY_PATH = libPath;
    };
  };

in
pkgs.mkShell {
   buildInputs = with pkgs;  [ 
    python311
    python311.pkgs.virtualenv
    python311.pkgs.pip
    python311.pkgs.numpy
    python311.pkgs.opencv4
    python311.pkgs.pycuda
    libdrm
    xorg.libxcb
    wayland

    zlib
    libGL
    glibc
    xorg.libX11
    glibc.dev
  ];

  # Expose CUDA environment variables
  inherit (cuda.envVars) 
    CUDA_PATH CUDA_HOME CUDACXX CUDAHOSTCXX 
    TORCH_CUDA_ARCH_LIST FORCE_CUDA;
  
  # CUDA pkg-config path
  PKG_CONFIG_PATH = "${cuda.envVars.PKG_CONFIG_PATH}";

  shellHook = ''
    # Add CUDA to PATH
    export PATH="${cuda.binPath}:$PATH"
    
    # Set up library paths for general use (CUDA + system libs)
    export LD_LIBRARY_PATH="${cuda.libPath}:$LD_LIBRARY_PATH"
    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.zlib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.libGL}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.xorg.libX11}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.xorg.libxcb}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.wayland}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.libdrm}/lib:$LD_LIBRARY_PATH
    
    # CUDA compiler paths
    export CPATH="${cuda.includePath}''${CPATH:+:$CPATH}"
    export LIBRARY_PATH="${cuda.libPath}''${LIBRARY_PATH:+:$LIBRARY_PATH}"
    
    # Create nvcc wrapper function
    nvcc() {
      LD_LIBRARY_PATH="${cuda.libPath}:/lib/aarch64-linux-gnu:/usr/lib/aarch64-linux-gnu" ${cuda.nvcc} "$@"
    }
    export -f nvcc
    
    # Sanity checks
    if [ -x "${cuda.nvcc}" ]; then
      echo "🟢 Using CUDA from ${cuda.basePath}"
      nvcc --version >/dev/null 2>&1 && echo "   nvcc is working correctly" || echo "   Note: nvcc may show warnings, but CUDA compilation should work"
    else
      echo "🟠 nvcc not found at ${cuda.nvcc} (CUDA may not be available)"
    fi
    
    echo "🟢 PyCUDA configured"

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
