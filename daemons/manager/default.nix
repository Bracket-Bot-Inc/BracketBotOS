{ pkgs ? import <nixpkgs> {} }:

let
  manager = pkgs.stdenv.mkDerivation {
    name = "manager";
    version = "1.0";
    src = ./.;
    buildInputs = [ pkgs.python311 ];
    installPhase = ''
      mkdir -p $out/bin
      ln -s "$src/manager.py" "$out/bin/manager.py"

      cat > $out/bin/manager <<EOF
#!/bin/sh
exec python3 "\$(dirname "\$0")/manager.py" "\$@"
EOF
      chmod +x $out/bin/manager
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

    for f in /tmp/*.log; do
      echo -e "$PINK========== LOG FILE: $f ==========$RESET"
      highlight_errors < "$f"
      echo ""
    done
  '';
};

debug_systemd = pkgs.writeShellApplication {
  name = "debug-systemd";
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

in pkgs.buildEnv {
  name = "manager";
  paths = [ manager debug_systemd debug_daemons ];
}
