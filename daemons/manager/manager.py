#!/usr/bin/env python3
import os
import sys
import argparse
import time
import signal
from multiprocessing import Process
from pathlib import Path

DAEMONS_ROOT = Path.home() / "BracketBotOS" / "daemons"


class ManagedProc:

    def __init__(self, name: str, cwd: Path):
        self.name = name
        self.cwd = cwd
        self.proc = None
        self.last_start = 0.0

    def _launch(self):
        os.chdir(self.cwd)
        log_file = f"/tmp/{self.name}.log"
        with open(log_file, "wb", buffering=0) as log_fd:
            os.dup2(log_fd.fileno(), 1)  # stdout → log file
            os.dup2(log_fd.fileno(), 2)  # stderr → log file
            os.execvp("nix-shell",
                      ["nix-shell", "--run", f"python daemon.py {self.name}"])

    def start(self):
        if self.proc or time.monotonic() - self.last_start < 1.0:
            return
        self.proc = Process(target=self._launch, name=self.name)
        self.proc.start()
        self.last_start = time.monotonic()
        print(f"[manager] started {self.name} (pid={self.proc.pid})")

    def stop(self, sig=signal.SIGINT):
        if not self.proc:
            return
        try:
            os.kill(self.proc.pid, sig)
        except ProcessLookupError:
            pass
        self.proc.join(timeout=5)
        self.proc = None

    def keep_alive(self):
        if not self.proc or self.proc.exitcode is not None:
            if self.proc:
                print(
                    f"[manager] {self.name} exited ({self.proc.exitcode}), restarting"
                )
                pass
            self.start()


def discover_daemons(root: Path):
    for p in root.rglob("shell.nix"):
        yield ManagedProc(p.parent.name, p.parent)


def main():
    ap = argparse.ArgumentParser(
        prog="manager", description="Start and supervise selected daemons")
    ap.add_argument("--only",
                    metavar="NAME",
                    nargs="*",
                    default=[],
                    help="Daemons to start/manage (space-separated list)")
    args = ap.parse_args()
    procs = list(discover_daemons(DAEMONS_ROOT))
    if args.only:
        procs = [proc for proc in procs if proc.name in args.only]
    print(f"Managing daemons: {', '.join(p.name for p in procs)}")

    running = True

    def shutdown(signum, _):
        nonlocal running
        print(f"\n[manager] signal {signum}, shutting down…")
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for p in procs:
        p.start()

    while running:
        for p in procs:
            p.keep_alive()
        time.sleep(0.5)

    for p in procs:
        p.stop()
    print("[manager] done")


if __name__ == "__main__":
    main()
