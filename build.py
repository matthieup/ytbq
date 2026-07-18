#!/usr/bin/env python3
"""
Build a standalone binary distribution of YTBQ using PyInstaller.

Usage:
    python build.py [--onefile] [--clean]

Requires: pyinstaller (pip install pyinstaller)
"""

import os
import sys
import shutil
import subprocess
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
DIST_DIR = PROJECT_ROOT / "dist"


def create_default_config() -> dict:
    return {
        "base_url": "http://localhost:8000",
        "video_quality": 1080,
        "allow_multiple_videos": True,
        "multiple_videos_locked": False,
        "auto_queue_enabled": False,
        "auto_queue_locked": False,
        "logo_path": "",
        "max_duration_seconds": 600,
    }


def build(onefile: bool = False, clean: bool = False):
    if clean and DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
        for spec_file in PROJECT_ROOT.glob("*.spec"):
            spec_file.unlink(missing_ok=True)

    # Ensure a default config.json exists at project root (it's required at import time)
    config_path = PROJECT_ROOT / "config.json"
    if not config_path.exists():
        with open(config_path, "w") as f:
            json.dump(create_default_config(), f, indent=4)
        print(f"Created default {config_path}")

    # Build the .spec content programmatically
    hidden_imports = [
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.middleware",
        "uvicorn.middleware.asgi2",
        "uvicorn.middleware.wsgi",
        "uvicorn.middleware.proxy_headers",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "jinja2",
        "jinja2.ext",
        "multipart",
        "qrcode",
        "yt_dlp",
        "websockets",
        "httpx",
        "pydantic",
    ]

    datas = [
        (str(PROJECT_ROOT / "app" / "templates"), "app/templates"),
        (str(PROJECT_ROOT / "static"), "static"),
        (str(PROJECT_ROOT / "config.json"), "."),
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "ytbq",
        "--noconfirm",
    ]

    for imp in hidden_imports:
        cmd.extend(["--hidden-import", imp])

    for src, dst in datas:
        cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    cmd.append(str(PROJECT_ROOT / "run.py"))

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("Build failed!")
        sys.exit(1)

    print("\nBuild complete!")
    binary_dir = DIST_DIR / "ytbq"
    if onefile:
        print(f"Binary: {DIST_DIR / 'ytbq' / 'ytbq'}")
    else:
        print(f"Binary: {binary_dir / 'ytbq'}")
        file_count = len(list(binary_dir.rglob("*")))
        print(f"Total files in distribution: {file_count}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build YTBQ binary distribution")
    parser.add_argument("--onefile", action="store_true", help="Build a single-file executable")
    parser.add_argument("--clean", action="store_true", help="Clean dist/ before building")
    args = parser.parse_args()
    build(onefile=args.onefile, clean=args.clean)
