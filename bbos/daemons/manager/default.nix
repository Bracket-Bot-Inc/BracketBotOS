let 
pkgs = import (fetchTarball "https://github.com/NixOS/nixpkgs/archive/63dacb46bf939521bdc93981b4cbb7ecb58427a0.tar.gz") {};
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

debug_daemons = pkgs.writeShellApplication {
  name = "debug-daemons";
  text = ''
    PINK="\033[1;35m"
    RED="\033[31m"
    RESET="\033[0m"

    highlight_errors() {
      awk -v red="$RED" -v reset="$RESET" '
        /Traceback|Error|Exception|KeyboardInterrupt|No such file or directory/ {
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
      # Argument provided - show logs containing daemon name
      DAEMON_NAME="$1"
      FOUND_LOGS=false
      
      for f in /tmp/*"$DAEMON_NAME"*.log; do
        if [ -f "$f" ]; then
          echo -e "$PINK========== LOG FILE: $f ==========$RESET"
          highlight_errors < "$f"
          echo ""
          FOUND_LOGS=true
        fi
      done
      
      if [ "$FOUND_LOGS" = false ]; then
        echo -e "$RED" "[ERROR] No log files found containing: $DAEMON_NAME" "$RESET"
        exit 1
      fi
    fi
  '';
};

debug_service = pkgs.writeShellApplication {
  name = "debug-service";
  text = ''
    PINK="\033[1;35m"
    RED="\033[31m"
    RESET="\033[0m"

    set -eu
    if [ "$#" -eq 0 ]; then
      echo -e "$RED" "[ERROR] Usage: logs-systemd <service-name>" "$RESET"
      exit 1
    fi

    SERVICE_NAME="$1"
    echo -e "$PINK========== SYSTEMD SERVICE: $SERVICE_NAME.service ==========$RESET"

    sudo journalctl -u "$SERVICE_NAME.service" --no-pager -l | awk -v red="$RED" -v reset="$RESET" '
      /Traceback|Error|Exception|fail|Failed|No such file or directory/ {
        print red $0 reset;
        next;
      }
      { print }
    '
  '';
};

clean = pkgs.writeShellApplication {
  name = "clean";
  text = ''
    set -eu
    sudo systemctl kill -s SIGKILL manager
    sudo systemctl kill -s SIGKILL autostart
    find /tmp -maxdepth 1 \( -name '*_lock' -o -name '*.log' \) -exec rm -f {} +
    sudo systemctl restart manager
    sudo systemctl restart autostart
    echo "Clean Slate!"
  '';
};

restart = pkgs.writeShellApplication {
  name = "restart";
  text = ''
    set -eu
    sudo systemctl kill -s SIGKILL manager
    sudo systemctl kill -s SIGKILL autostart
    find /tmp -maxdepth 1 \( -name '*_lock' -o -name '*.log' \) -exec rm -f {} +
    sudo systemctl restart manager
    sudo systemctl restart autostart
    echo "Restarted!"
  '';
};

stop = pkgs.writeShellApplication {
  name = "stop";
  text = ''
    set -eu
    sudo systemctl kill -s SIGKILL manager
    sudo systemctl kill -s SIGKILL autostart
    find /tmp -maxdepth 1 \( -name '*_lock' -o -name '*.log' \) -exec rm -f {} +
    echo "Stopped!"
  '';
};


in pkgs.buildEnv {
  name = "manager";
  paths = [ manager calibrate debug_service debug_daemons restart stop];
}