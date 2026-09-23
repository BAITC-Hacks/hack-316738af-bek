"""Local server entry point, without changing PowerShell execution policies."""

import argparse
import subprocess
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    command = [
        sys.executable,
        "-m",
        "uvicorn",
        "backend.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.port),
        "--workers",
        "1",
    ]
    if (root / ".env").is_file():
        command += ["--env-file", str(root / ".env")]
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
