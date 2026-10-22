"""Find SUMO applications and their Python TraCI interface on Mac or Windows."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class SumoRuntime:
    """Executable paths and matching Python interfaces for one installation."""

    sumo: str
    netgenerate: str
    gui: str | None
    traci: Any
    sumolib: Any

    def version(self) -> str:
        """Fail early on missing native libraries and record the actual version."""

        result = subprocess.run([self.sumo, "--version"], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"SUMO cannot start:\n{result.stderr}")
        return result.stdout.splitlines()[0]


def load_runtime(sumo_home: Path | None = None) -> SumoRuntime:
    """Load an explicit installation, SUMO_HOME, or executables on PATH.

    An explicit home takes priority over a pip installation, which is useful
    when the platform's latest Python wheel contains an older SUMO binary.
    """

    home = sumo_home or (Path(os.environ["SUMO_HOME"]) if os.getenv("SUMO_HOME") else None)
    if home is None and sys.platform == "darwin":
        candidates = [Path("/Library/Frameworks/EclipseSUMO.framework/Versions/Current/EclipseSUMO/share/sumo"),
                      Path.home() / "Applications" / "EclipseSUMO-1.28.0" / "share" / "sumo"]
        home = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if home:
        home = home.expanduser().resolve()
        os.environ["SUMO_HOME"] = str(home)
        if sys.platform == "darwin" and not os.getenv("PROJ_DATA") and not os.getenv("PROJ_LIB"):
            # The native bundle's nested framework can hide PROJ's map database.
            databases = list(home.parents[1].glob(
                "framework/EclipseSUMO.framework/Versions/*/EclipseSUMO/share/proj/proj.db"))
            if databases:
                os.environ["PROJ_DATA"] = str(databases[0].parent)
        if (home / "tools" / "traci").is_dir():
            sys.path.insert(0, str(home / "tools"))
    try:
        traci = importlib.import_module("traci")
        sumolib = importlib.import_module("sumolib")
    except ImportError as error:
        raise RuntimeError("Install traci, or pass --sumo-home pointing to SUMO's folder.") from error

    directories = [home / "bin"] if home else []
    directories.append(Path(sys.executable).parent)
    if home is None:
        try:
            directories.append(Path(importlib.import_module("sumo").SUMO_HOME) / "bin")
        except ImportError:
            pass

    def find(name: str, required: bool = True) -> str | None:
        """Resolve a binary without shell expansion or platform-specific syntax."""

        suffix = ".exe" if os.name == "nt" else ""
        for directory in directories:
            candidate = directory / (name + suffix)
            if candidate.is_file():
                return str(candidate)
        path = shutil.which(name)
        if not path and required:
            raise RuntimeError(f"Cannot find {name}. Set SUMO_HOME or use --sumo-home.")
        return path

    runtime = SumoRuntime(find("sumo"), find("netgenerate"), find("sumo-gui", False), traci, sumolib)
    runtime.version()
    return runtime
