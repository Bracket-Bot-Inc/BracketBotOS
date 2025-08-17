let 
pkgs = import (fetchTarball {
  url = "https://github.com/NixOS/nixpkgs/archive/63dacb46bf939521bdc93981b4cbb7ecb58427a0.tar.gz";
  sha256 = "sha256:1lr1h35prqkd1mkmzriwlpvxcb34kmhc9dnr48gkm8hh089hifmx";
}) {};
in
let
  makeWrapper = pkgs.makeWrapper;
  python = pkgs.python311;
  runtimePath = pkgs.lib.makeBinPath [ python pkgs.busybox ];

  manager = pkgs.stdenv.mkDerivation {
    name = "manager";
    version = "1.0";
    src = ./.;
    nativeBuildInputs = [ makeWrapper ];
    installPhase = ''
      mkdir -p $out/bin
      ln -s "$src/manager.py" "$out/bin/manager.py"

      makeWrapper ${python}/bin/python3 $out/bin/manager \
        --add-flags "$out/bin/manager.py" \
        --set PATH ${runtimePath}
    '';
  };

  calibrate = pkgs.stdenv.mkDerivation {
    name = "calibrate";
    version = "1.0";
    src = ./.;
    nativeBuildInputs = [ makeWrapper ];
    installPhase = ''
      mkdir -p $out/bin
      ln -s "$src/calibrate.py" "$out/bin/calibrate.py"

      makeWrapper ${python}/bin/python3 $out/bin/calibrate \
        --add-flags "$out/bin/calibrate.py" \
        --set PATH ${runtimePath}
    '';
  };

  list = pkgs.stdenv.mkDerivation {
    name = "list";
    version = "1.0";
    src = ./.;
    nativeBuildInputs = [ makeWrapper ];
    installPhase = ''
      mkdir -p $out/bin
      ln -s "$src/list.py" "$out/bin/list.py"

      makeWrapper ${python}/bin/python3 $out/bin/list \
        --add-flags "$out/bin/list.py" \
        --set PATH ${runtimePath}
    '';
  };

logs = pkgs.writeShellApplication {
  name = "logs";
  text = ''
    PINK="\033[1;35m"
    RED="\033[31m"
    RESET="\033[0m"

    highlight_errors() {
      awk -v red="$RED" -v reset="$RESET" '
        /Traceback|Error|Exception|KeyboardInterrupt|No such file or directory|fail|Failed/ {
          print red $0 reset;
          next;
        }
        { print }
      '
    }

    if [ "$#" -eq 0 ]; then
      # No argument provided - show all log files
      for f in /tmp/*.log; do
        echo -e "$PINK========== LOG FILE: $f ==========$RESET"
        highlight_errors < "$f"
        echo ""
      done
    else
      DAEMON_NAME="$1"
      
      # First try to find daemon log files
      FOUND_LOGS=false
      for f in /tmp/*"$DAEMON_NAME"*.log; do
        if [ -f "$f" ]; then
          echo -e "$PINK========== LOG FILE: $f ==========$RESET"
          highlight_errors < "$f"
          echo ""
          FOUND_LOGS=true
        fi
      done
      
      # If no daemon logs found, try systemd service
      if [ "$FOUND_LOGS" = false ]; then
        echo -e "$PINK========== SYSTEMD SERVICE: $DAEMON_NAME.service ==========$RESET"
        if sudo journalctl -u "$DAEMON_NAME.service" --no-pager -l 2>/dev/null | highlight_errors; then
          FOUND_LOGS=true
        fi
      fi
      
      if [ "$FOUND_LOGS" = false ]; then
        echo -e "$RED" "[ERROR] No logs found for: $DAEMON_NAME" "$RESET"
        exit 1
      fi
    fi
  '';
};

clean = pkgs.writeShellApplication {
  name = "clean";
  text = ''
    set -eu
    sudo systemctl kill -s SIGKILL manager
    sudo systemctl kill -s SIGKILL app_manager
    find /tmp -maxdepth 1 \( -name '*_lock' -o -name '*.log' \) -exec rm -f {} +
    sudo systemctl restart manager
    sudo systemctl restart app_manager
    echo "Clean Slate!"
  '';
};

restart = pkgs.writeShellApplication {
  name = "restart";
  text = ''
    set -eu
    sudo systemctl kill -s SIGKILL manager
    sudo systemctl kill -s SIGKILL app_manager
    find /tmp -maxdepth 1 \( -name '*_lock' -o -name '*.log' \) -exec rm -f {} +
    sudo systemctl restart manager
    sudo systemctl restart app_manager
    echo "Restarted!"
  '';
};

stop = pkgs.writeShellApplication {
  name = "stop";
  text = ''
    set -eu
    if [ "$#" -eq 0 ]; then
      sudo systemctl kill -s SIGKILL manager
      sudo systemctl kill -s SIGKILL app_manager
      find /tmp -maxdepth 1 \( -name '*_lock' -o -name '*.log' \) -exec rm -f {} +
      echo "Stopped!"
    else
      for arg in "$@"; do
        pkill -f "python daemon.py $arg" || true
        rm -f "/tmp/$${arg}_lock" "/tmp/$${arg}.log"
      done
      echo "Stopped daemons: $*"
    fi
  '';
};

in pkgs.buildEnv {
  name = "manager";
  paths = [ manager calibrate logs restart stop list];
}