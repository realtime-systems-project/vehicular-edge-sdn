"""Check the macOS XQuartz display before starting a SUMO GUI experiment."""

from __future__ import annotations

import atexit
import os
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path


def write_view_settings(path: Path, city: bool = False) -> None:
    """Use a readable road view with enlarged car symbols, without changing physics."""

    from .network import write_xml

    root = ET.Element("viewsettings")
    scheme = ET.SubElement(root, "scheme", name="Course traffic")
    ET.SubElement(scheme, "background", backgroundColor="235,239,242", showGrid="0")
    ET.SubElement(scheme, "edges", laneEdgeMode="0", laneShowBorders="1",
                  showLinkDecals="1", widthExaggeration="1" if city else "3", minSize="0")
    ET.SubElement(scheme, "vehicles", vehicleMode="0", vehicleQuality="2",
                  vehicle_minSize="3", vehicle_exaggeration="4" if city else "6",
                  showBlinker="1", drawMinGap="0")
    ET.SubElement(scheme, "junctions", junctionMode="0", drawShape="1", showLane2Lane="1")
    ET.SubElement(scheme, "pois", poi_minSize="0", poi_exaggeration="1.5" if city else "8",
                  poiName_show="0" if city else "1", poiName_size="20", poiName_color="20,60,30")
    write_xml(root, path)


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


def local_server_authority() -> tuple[str, Path] | None:
    """Locate only this user's running local XQuartz server and private token file."""

    result = subprocess.run(["/bin/ps", "-u", str(os.getuid()), "-o", "command="],
                            capture_output=True, text=True, timeout=3)
    for line in result.stdout.splitlines():
        args = shlex.split(line)
        if not args or args[0] != "/opt/X11/bin/Xquartz" or "-auth" not in args:
            continue
        display = next((arg for arg in args if arg.startswith(":") and arg[1:].isdigit()), None)
        index = args.index("-auth") + 1
        if display is None or index >= len(args):
            continue
        path = Path(args[index])
        info = path.stat()
        if info.st_uid == os.getuid() and stat.S_ISREG(info.st_mode) and not info.st_mode & 0o077:
            return display, path
    return None


def recover_local_authority(probe: Path) -> bool:
    """Recover hostname-mismatched X11 credentials for this process only.

    Reuse the active same-user server's token in a private temporary authority
    file, under today's hostname. Never log tokens, pass them in command-line
    arguments, edit ~/.Xauthority, or relax XQuartz authentication. Retain the
    file for child SUMO processes and delete it when this Python process exits.
    """

    previous = {key: os.environ.get(key) for key in ("DISPLAY", "XAUTHORITY")}
    temporary = None
    success = False
    try:
        server = local_server_authority()
        if server is None:
            return False
        display, authority = server
        xauth = "/opt/X11/bin/xauth"
        result = subprocess.run([xauth, "-n", "-f", str(authority), "list"],
                                capture_output=True, text=True, timeout=3, check=True)
        records = [line.split() for line in result.stdout.splitlines()]
        record = next((row for row in records if len(row) == 3
                       and row[0].endswith("/unix" + display)
                       and row[1] == "MIT-MAGIC-COOKIE-1"
                       and len(row[2]) == 32 and all(c in "0123456789abcdefABCDEF" for c in row[2])), None)
        if record is None:
            return False
        temporary = tempfile.TemporaryDirectory(prefix="sumo-xauthority-")
        target = Path(temporary.name) / "authority"
        target.touch(mode=0o600)
        subprocess.run([xauth, "-f", str(target)],
                       input=f"add {socket.gethostname()}/unix{display} {record[1]} {record[2]}\n",
                       capture_output=True, text=True, timeout=3, check=True)
        environment = dict(os.environ, DISPLAY=display, XAUTHORITY=str(target))
        result = subprocess.run([str(probe), "-display", display], env=environment,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
        if result.returncode:
            return False
        os.environ.update(DISPLAY=display, XAUTHORITY=str(target))
        atexit.register(temporary.cleanup)
        success = True
        return True
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    finally:
        if not success:
            if temporary is not None:
                temporary.cleanup()
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


def prepare_gui() -> None:
    """Start/check XQuartz on macOS and fail before training if it cannot run."""

    if sys.platform != "darwin":
        return
    probe = Path("/opt/X11/bin/xdpyinfo")
    if not probe.is_file():
        raise RuntimeError("SUMO GUI on macOS requires XQuartz. Install it and open XQuartz first.")
    if working_display(probe):
        return
    if recover_local_authority(probe):
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
        if recover_local_authority(probe):
            return
        time.sleep(0.5)
    raise RuntimeError(
        "XQuartz has no accessible display. Inspect ~/Library/Logs/X11/org.xquartz.log.\n"
        "Try the command from XQuartz > Applications > Terminal, or sign out and back in.\n"
        "No training was started."
    )
