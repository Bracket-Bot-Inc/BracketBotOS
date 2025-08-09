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

timing = pkgs.writeShellApplication {
  name = "timing";
  text = ''
  for f in /tmp/*_time_lock; do
  [ -f "$f" ] || continue
  if raw=$(dd if="$f" bs=8 count=1 2>/dev/null | od -An -t d8); then
    val=$(echo "$raw" | awk '{print $1}')
    if [ "$val" -ne 0 ] 2>/dev/null; then
      freq=$(awk -v v="$val" 'BEGIN { printf "%.2f", 1/(v * 1e-9) }')
      echo "$(basename "$f"): $freq Hz"
    fi
  fi
done
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

status = pkgs.writeShellApplication {
  name = "status";
  text = ''
    set -eu
    host=$(hostname)
    echo "http://$host.local:9090/?url=rerun%2Bhttp://$host.local:9876/proxy"
  '';
};

list = pkgs.writeShellApplication {
  name = "list";
  text = ''
    set -eu
    GREEN="\033[32m"
    BLUE="\033[34m"
    RESET="\033[0m"
    
    echo -e "$BLUE=== Running Daemons ===$RESET"
    
    if pgrep -f "python daemon.py" > /dev/null; then
      pgrep -f "python daemon.py" | while read -r pid; do
        cmd=$(ps -p "$pid" -o args= 2>/dev/null || echo "")
        daemon_name=$(echo "$cmd" | awk '/python daemon\.py/ {print $3}')
        if [ -n "$daemon_name" ]; then
          echo -e "$GREEN✓ $daemon_name$RESET (PID: $pid)"
        fi
      done
    else
      echo "No daemons running"
    fi
  '';
};


in pkgs.buildEnv {
  name = "manager";
  paths = [ manager calibrate debug_service debug_daemons restart stop timing status list];
}