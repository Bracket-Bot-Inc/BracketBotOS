let
pkgs = import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/63dacb46bf939521bdc93981b4cbb7ecb58427a0.tar.gz";
  sha256 = "sha256:1lr1h35prqkd1mkmzriwlpvxcb34kmhc9dnr48gkm8hh089hifmx";
}) {};

  inekf = pkgs.python311Packages.buildPythonPackage rec {
    pname = "inekf";
    version = "0.1.0";
    format = "other";
    src = pkgs.fetchgit {
      url = "https://bitbucket.org/frostlab/inekf.git";
      rev = "HEAD";
      sha256 = "sha256-itle/hLv8k8rGvS+8nAe7tfVRxkqAZ6ej+WE9LxCFjc=";
    };
    
    # No sourceRoot needed - build from root directory
    
    nativeBuildInputs = with pkgs; [
      cmake
      git
      eigen
      python311Packages.pybind11
      python311Packages.setuptools
      python311Packages.wheel
      python311Packages.pip
    ];
    
    propagatedBuildInputs = with pkgs.python311Packages; [
      numpy
    ];
    
    # Override configure phase to set proper CMake flags
    configurePhase = ''
      mkdir -p build
      cd build
      cmake .. \
        -DCMAKE_BUILD_TYPE=Release \
        -DPYTHON=ON \
        -DPYTHON_EXECUTABLE=${pkgs.python311}/bin/python \
        -DCMAKE_PREFIX_PATH=${pkgs.eigen}/share/eigen3/cmake \
        -DEigen3_DIR=${pkgs.eigen}/share/eigen3/cmake
    '';
    
    # Custom build phase
    buildPhase = ''
      make -j$NIX_BUILD_CORES
    '';
    
    # Custom install phase
    installPhase = ''
      # The setup.py is generated in the build/python directory
      cd python
      ${pkgs.python311}/bin/python setup.py install --prefix=$out --single-version-externally-managed --root=/
    '';
    
    doCheck = false;
  };

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