#!/usr/bin/env python3
import os
import sys
import argparse
import time
import signal
from multiprocessing import Process
from pathlib import Path

DAEMONS_DIR = Path(__file__).parent.parent.absolute()


class ManagedProc:

    def __init__(self, name: str, cwd: Path):
        self.name = name
        self.cwd = cwd
        self.proc = None
        self.last_start = 0.0

    def _launch(self):
        os.chdir(self.cwd)
        log_path = f"/tmp/{self.name}.log"
        cmd = [
            "nix-shell", "--run",
            f"echo '[shell] now running daemon: {self.name}'; python daemon.py {self.name}"
        ]
        with open(log_path, "wb", buffering=0) as log_fd:
            os.dup2(log_fd.fileno(), 1)
            os.dup2(log_fd.fileno(), 2)
            os.execvp(cmd[0], cmd)

    def _wait_for_ready(self, timeout=500.0):
        log_path = Path(f"/tmp/{self.name}.log")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if not log_path.exists():
                time.sleep(0.1)
                continue
            with open(log_path, "rb") as f:
                lines = f.readlines()[-10:]
                if any(b"now running daemon" in l for l in lines):
                    self.ready = True
                    print(f"[manager] {self.name} is now running:")
                    return
            time.sleep(0.2)
        print(
            f"[manager] {self.name} did not signal readiness within {timeout} sec"
        )

    def start(self):
        if self.proc or time.monotonic() - self.last_start < 1.0:
            return
        self.proc = Process(target=self._launch, name=self.name)
        self.proc.start()
        self.last_start = time.monotonic()
        print(f"[manager] initializing {self.name}... (pid={self.proc.pid})")
        self._wait_for_ready()

    def stop(self, sig=signal.SIGINT):
        if not self.proc:
            return
        try:
            os.kill(self.proc.pid, sig)
        except ProcessLookupError:
            pass
        self.proc.join(timeout=5)
        self.proc = None

    def check_alive(self):
        if not self.proc or self.proc.exitcode is not None:
            if self.proc:
                print(f"[manager] {self.name} exited ({self.proc.exitcode})")


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
            p.check_alive()
        time.sleep(1.0)

    for p in procs:
        p.stop()
    print("[manager] done")


if __name__ == "__main__":
    main()
