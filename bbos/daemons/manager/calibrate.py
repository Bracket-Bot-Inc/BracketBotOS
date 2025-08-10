#!/usr/bin/env python3
import os
import sys
import subprocess
from pathlib import Path
import pwd

CURRENT_USER = pwd.getpwuid(os.getuid()).pw_name

if len(sys.argv) != 2:
    print("Usage: calibrate <daemon-name>")
    sys.exit(1)

daemon_name = sys.argv[1]
daemon_dir = Path.home() / "BracketBotOS" / "bbos" / "daemons" / daemon_name
calibrate_py = daemon_dir / "calibrate.py"

if not calibrate_py.exists():
    print(f"[calibrate] No calibrate.py found for daemon '{daemon_name}'")
    sys.exit(1)

os.chdir(daemon_dir)
os.environ["PATH"] = f"/home/{CURRENT_USER}/.nix-profile/bin"
cmd = ["nix-shell", "--run", f"python calibrate.py {daemon_name}"]
os.execvp(cmd[0], cmd)