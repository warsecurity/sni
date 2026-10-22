#!/usr/bin/env python3
"""Stop only this project's processes; never kill every Python process."""
import os
import signal
import subprocess
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent)

def matches(cmd: str) -> bool:
    return ROOT in cmd and ("tunnel.py" in cmd or "ssh.py" in cmd)

me = os.getpid()
result = subprocess.run(["ps", "-eo", "pid=,args="], text=True, capture_output=True)
for line in result.stdout.splitlines():
    line = line.strip()
    if not line:
        continue
    pid_text, _, command = line.partition(" ")
    try:
        pid = int(pid_text)
    except ValueError:
        continue
    if pid != me and matches(command):
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
