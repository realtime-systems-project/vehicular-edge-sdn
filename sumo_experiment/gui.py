"""Check the macOS XQuartz display before starting a SUMO GUI experiment."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


def working_display(probe: Path) -> str | None:
    """Find an accessible display, preferring the user's working setting.

    A Terminal can retain a dead launchd socket address after XQuartz restarts.
    Probe the current setting, the current launchd setting, and the local X11
    server. Change only this Python process's environment after a successful
    connection; never disable X11 authentication or enable network access.
    """

    try:
        result = subprocess.run(["/bin/launchctl", "getenv", "DISPLAY"],
                                capture_output=True, text=True, timeout=2)
        launchd_display = result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        launchd_display = ""
    candidates = dict.fromkeys((os.environ.get("DISPLAY", ""), launchd_display, ":0"))
    for address in candidates:
        if not address:
            continue
        try:
            result = subprocess.run([str(probe), "-display", address],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            os.environ["DISPLAY"] = address
            return address
    return None


def prepare_gui() -> None:
    """Start/check XQuartz on macOS and fail before training if it cannot run."""

    if sys.platform != "darwin":
        return
    probe = Path("/opt/X11/bin/xdpyinfo")
    if not probe.is_file():
        raise RuntimeError("SUMO GUI on macOS requires XQuartz. Install it and open XQuartz first.")
    if working_display(probe):
        return
    if not Path("/tmp/.X11-unix").is_dir():
        raise RuntimeError(
            "XQuartz cannot start: /tmp/.X11-unix is missing.\n"
            "Run this administrator command in your Terminal:\n"
            "  sudo install -d -o root -g wheel -m 1777 /tmp/.X11-unix\n"
            "Then open XQuartz and rerun this command. No training was started."
        )
    try:
        result = subprocess.run(["/usr/bin/open", "-a", "XQuartz"],
                                capture_output=True, text=True, timeout=5)
        if result.returncode:
            raise RuntimeError(f"Could not open XQuartz: {result.stderr.strip()}")
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("Open XQuartz manually, then rerun the GUI command.") from error
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        if working_display(probe):
            return
        time.sleep(0.5)
    raise RuntimeError(
        "XQuartz has no accessible display. Inspect ~/Library/Logs/X11/org.xquartz.log.\n"
        "Try the command from XQuartz > Applications > Terminal, or sign out and back in.\n"
        "No training was started."
    )
