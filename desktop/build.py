#!/usr/bin/env python3
"""Build a single-file desktop executable with PyInstaller.

PyInstaller is a build-time tool only; the app itself runs on the standard
library. Install it into the active environment first::

    pip install pyinstaller

Then run::

    python3 desktop/build.py

The result is written to ``desktop/dist/`` (``range_calculator_desktop.exe`` on
Windows, ``range_calculator_desktop.app``/binary on macOS). The physics config
is bundled next to the flattened modules so ``physics_config`` finds it.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

DESKTOP_DIR = Path(__file__).resolve().parent
REPO_ROOT = DESKTOP_DIR.parent
RANGE_CALCULATOR = REPO_ROOT / "range_calculator"
CONFIG_SOURCE = RANGE_CALCULATOR / "config" / "physics_constants.json"
APP_ENTRY = DESKTOP_DIR / "app.py"

APP_NAME = "range_calculator_desktop"


def main() -> int:
    if importlib.util.find_spec("PyInstaller") is None:
        print(
            "PyInstaller is not installed. Install it with:\n"
            "    pip install pyinstaller",
            file=sys.stderr,
        )
        return 1
    if not CONFIG_SOURCE.is_file():
        print(f"missing config file: {CONFIG_SOURCE}", file=sys.stderr)
        return 1

    # PyInstaller flattens top-level (non-package) modules into the bundle root,
    # so physics_config's __file__-relative "config" directory must land there.
    data_arg = f"{CONFIG_SOURCE}{os.pathsep}config"

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        APP_NAME,
        "--paths",
        str(RANGE_CALCULATOR),
        "--add-data",
        data_arg,
        "--distpath",
        str(DESKTOP_DIR / "dist"),
        "--workpath",
        str(DESKTOP_DIR / "build"),
        "--specpath",
        str(DESKTOP_DIR / "build"),
        str(APP_ENTRY),
    ]
    print("running:", " ".join(command))
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
