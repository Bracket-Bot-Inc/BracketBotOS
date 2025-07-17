let
  pkgs = import (builtins.fetchTarball {
     url = "https://github.com/NixOS/nixpkgs/archive/refs/tags/24.05.tar.gz";
     sha256 = "sha256:1lr1h35prqkd1mkmzriwlpvxcb34kmhc9dnr48gkm8hh089hifmx";
  }) {
    config = {
      allowUnfree = true;
      allowBroken = true;
      allowInsecure = true;
    };
  };

  freeimage = pkgs.freeimage.overrideAttrs (old: {
    meta = old.meta // {
      knownVulnerabilities = [];
    };
  });
in

let 
  opencvPythonSimd = pkgs.python311.pkgs.opencv4.overrideAttrs (old: {
    cmakeFlags = (old.cmakeFlags or []) ++ [
      "-DWITH_OPENCL=ON"
      "-DWITH_TBB=ON"
      "-DENABLE_NEON=ON"
      "-DCPU_BASELINE=NEON"
      "-DCPU_DISPATCH=NEON_FP16,NEON_BF16,NEON_DOTPROD"
      "-DENABLE_FAST_MATH=ON"
      "-DCV_DISABLE_OPTIMIZATION=OFF"
    ];
    buildPhase = ''
      make -j3  # or substitute with fixed number: -j4
    '';
  });

  gnuplotlib = pkgs.stdenv.mkDerivation rec {
    pname = "gnuplotlib";
    version = "0.0.2";
    src = pkgs.fetchurl {
      url = "https://github.com/raghavauppuluri13/gnuplotlib/archive/refs/tags/v${version}.tar.gz";
      sha256 = "sha256-hOkUoWZ5Ws7zQj2N6210VqPiLciHT26yhR08AhgdzU4=";  # run nix-prefetch-url to get this
    };
    nativeBuildInputs = with pkgs.python3Packages; [ setuptools ];
    buildInputs = with pkgs; [
      python3
      python3Packages.numpy
      numpysane
      perl
      perlPackages.ListMoreUtils
      gnuplot
    ];
    python = pkgs.python3;
    sitePackages = "lib/${python.libPrefix}/site-packages";
    installPhase = ''
      mkdir -p $out/${sitePackages}
      cp gnuplotlib.py $out/${sitePackages}/
    '';
  };

 numpy_1 = pkgs.python311Packages.numpy.overridePythonAttrs (old: {
    version = "1.26.4";
    src = pkgs.fetchPypi {
      inherit (old) pname;
      version = "1.26.4";
      sha256 = "sha256-KgKrqe0S5KxOs+qUIcQgMBoMZGDZgw10qd+H76SRIBA="; # run nix-prefetch-url or check PyPI
    };
 });
  numpysane = pkgs.stdenv.mkDerivation rec {
    pname = "numpysane";
    version = "0.42";
    src = pkgs.fetchurl {
      url = "https://github.com/dkogan/numpysane/archive/refs/tags/v${version}.tar.gz";
      sha256 = "sha256-CtV8vy5zlUEpRZNUbzVsSKfs7lAcd9DU8FekY9SMQcs=";  # run nix-prefetch-url to get this
    };
    nativeBuildInputs = with pkgs.python3Packages; [ setuptools ];
    buildInputs = with pkgs; [
      python311
      numpy_1
      perl
      perlPackages.ListMoreUtils
    ];
    python = pkgs.python311;
    sitePackages = "lib/${python.libPrefix}/site-packages";
    installPhase = ''
      mkdir -p $out/${sitePackages}
      cp numpysane.py numpysane_pywrap.py $out/${sitePackages}/
      mkdir -p $out/${sitePackages}/pywrap-templates
      cp pywrap-templates/*.c $out/${sitePackages}/pywrap-templates/
    '';
  };
  mrbuildSrc = pkgs.fetchurl {
    url = "https://github.com/dkogan/mrbuild/archive/refs/tags/v1.13.tar.gz";
    sha256 = "07izs4x9ws1qdn055r25yy63q06i93snwy1cn7fa4zjsf97rr75c";
  };
  mrgingham = pkgs.stdenv.mkDerivation rec {
    pname = "mrgingham";
    version = "1.26";

    src = pkgs.fetchurl {
      url = "https://github.com/dkogan/mrgingham/archive/refs/tags/v${version}.tar.gz";
      sha256 = "0lrc58iw9pvnvszk4j40wjjglla1pdl6vdbl4l6vfia3fqdik29r";  # run nix-prefetch-url to get this
    };

    nativeBuildInputs = with pkgs; [ pkg-config ];


    buildInputs = with pkgs; [
      opencv3
      boost
      libjpeg
      libpng
      libtiff
      mawk
      perl
      python3
      python3Packages.numpy
    ];

    unpackPhase = ''
      tar xf $src
      tar xf ${mrbuildSrc}
      ln -sf ../mrbuild-1.13 mrgingham-${version}/mrbuild
      cd mrgingham-${version}
    '';


    buildPhase = ''
      export NPY_INCLUDE_DIR=$(python3 -c "import numpy; print(numpy.get_include())")
      export CFLAGS="-I$NPY_INCLUDE_DIR -I$PYTHON_INCLUDE_DIR $CFLAGS"
      export CCXXFLAGS="$CFLAGS"
      make
    '';

    installPhase = ''
      mkdir -p $out/{bin,lib}
      cp mrgingham* $out/bin/
      cp libmrgingham.so* $out/lib/
    '';
  };
  libdogleg = pkgs.stdenv.mkDerivation rec {
    pname = "libdogleg";
    version = "0.16";
    src = pkgs.fetchurl {
      url = "https://github.com/dkogan/libdogleg/archive/refs/tags/v${version}.tar.gz";
      sha256 = "sha256-lhpSKynVfep3H7tH5kjjUzIHLtQ/6Ig6m2K2O5X3jkk=";  # run nix-prefetch-url to get this
    };

    buildInputs = with pkgs; [
      suitesparse
      lapack
    ];

    unpackPhase = ''
      tar xf $src
      tar xf ${mrbuildSrc}
      ln -sf ../mrbuild-1.13 libdogleg-${version}/mrbuild
      cd libdogleg-${version}
    '';

    buildPhase = ''
      make
    '';

    installPhase = ''
      mkdir -p $out/lib $out/include
      cp libdogleg.so* $out/lib/
      cp *.a $out/lib/ || true
      cp *.h $out/include/
    '';
  };
 mrcal = pkgs.stdenv.mkDerivation rec {
    pname = "mrcal";
    version = "2.4.1";
    src = pkgs.fetchurl {
      url = "https://github.com/dkogan/mrcal/archive/refs/tags/v${version}.tar.gz";
      sha256 = "sha256-dMdGv3TtYeLrV2b0A/fzXUtdeTAg37wYUROm6SlFdTE=";  # run nix-prefetch-url to get this
    };
    nativeBuildInputs = with pkgs; [
      re2c
      perl
      perlPackages.ListMoreUtils
      makeWrapper
    ];
    buildInputs = with pkgs; [
      libdogleg
      suitesparse
      freeimage
      mrgingham
      perl
      perlPackages.ListMoreUtils
      python311
      python311Packages.numpy
      python311Packages.scipy
      python311Packages.pip
      python311Packages.opencv4
      numpysane
      gnuplotlib 
    ];

    unpackPhase = ''
      tar xf $src
      tar xf ${mrbuildSrc}
      ln -sf ../mrbuild-1.13 mrcal-${version}/mrbuild
      cd mrcal-${version}
    '';
    postPatch = ''
      patchShebangs minimath/minimath_generate.pl
    '';

    python = pkgs.python3;
    sitePackages = "lib/${python.libPrefix}/site-packages";

    buildPhase = ''
      export PATH=$PATH:$(pwd)/../mrbuild
      export NPY_INCLUDE_DIR=$(python3 -c "import numpy; print(numpy.get_include())")
      export CFLAGS="-I$NPY_INCLUDE_DIR -I$PYTHON_INCLUDE_DIR $CFLAGS"
      export CCXXFLAGS="$CFLAGS"
      export CFLAGS="-I${libdogleg}/include $CFLAGS"
      export LDFLAGS="-L${libdogleg}/lib -Wl,-rpath=${libdogleg}/lib $LDFLAGS"
      make
    '';

    installPhase = ''
      mkdir -p $out/bin $out/lib/python3/dist-packages
      mkdir -p $out/lib/python3/dist-packages/mrcal
      cp -a mrcal $out/lib/python3/dist-packages
      cp -a mrcal-* tools/* $out/bin/ || true
      cp -a *.so* $out/lib

      for f in $(find $out/bin -type f -executable); do
          if head -c2 "$f" | grep -q '^#!'; then
            wrapProgram "$f" \
              --set PYTHONPATH "$out/lib/python3/dist-packages:${numpysane}/${sitePackages}:${gnuplotlib}/${sitePackages}:${pkgs.python3Packages.numpy}/${sitePackages}:${pkgs.python3Packages.scipy}/${sitePackages}:${pkgs.python3Packages.opencv4}/${sitePackages}"
          fi
      done
    '';
  };

  vnlogSrc = pkgs.fetchFromGitHub {
    owner = "dkogan";
    repo = "vnlog";
    rev = "v1.40";
    sha256 = "sha256-8jGlMcREwgFMcZfuuLi5WpJ8YHN7mvcre3kiE8nnlI4=";
  };

in

pkgs.mkShell {
   buildInputs = with pkgs;  [ 
    mrgingham 
    feedgnuplot
    python311
    python311.pkgs.virtualenv
    python311.pkgs.pip
    python311.pkgs.evdev
    #python311.pkgs.opencv4
    opencvPythonSimd
    zlib
    libGL
    glibc
    xorg.libX11
    libjpeg
    libpng
    libtiff
    mrcal 
    mawk
    perl
    perlPackages.ListMoreUtils
    gnuplot
    glibc.dev
    numpysane
  ];

  shellHook = ''
    export VNLOG_SRC=${vnlogSrc}
    export PATH="$VNLOG_SRC:$PATH"
    export PYTHONPATH="$VNLOG_SRC:$PYTHONPATH"
    export PYTHONPATH=${mrcal}/lib/python3/dist-packages:${numpysane}/lib/python3.11/site-packages:$PYTHONPATH
    export PERL5LIB="$VNLOG_SRC:$PERL5LIB"

    export LD_LIBRARY_PATH=${pkgs.stdenv.cc.cc.lib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.zlib}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.libGL}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${pkgs.xorg.libX11}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${mrgingham}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${libdogleg}/lib:$LD_LIBRARY_PATH
    export LD_LIBRARY_PATH=${mrcal}/lib:$LD_LIBRARY_PATH

    if [ ! -d "venv" ]; then
      python -m venv venv
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
      pip install -e ../../
      # daemon
      pip install turbojpeg-rpi v4l2-python3 
      # mrcal
      pip install scipy pyyaml gnuplotlib numpysane
      # cal
      pip install fastapi uvicorn websockets wsproto

    else
      source venv/bin/activate
      echo "Virtual environment activated. Use 'deactivate' to exit."
    fi
  '';
}
