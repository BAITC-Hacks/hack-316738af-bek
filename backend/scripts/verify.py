"""Cross-platform verification entry point; uses the active Python environment."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    commands = [
        ["pip", "check"],
        ["ruff", "check", "backend"],
        ["ruff", "format", "--check", "backend"],
        [
            "pytest",
            "backend/tests",
            "-q",
            "-W",
            "error",
            "--cov=backend.app",
            "--cov-config=backend/pyproject.toml",
            "--cov-report=term-missing",
            "--cov-report=json:backend/test-results/coverage.json",
            "--junitxml=backend/test-results/junit.xml",
        ],
    ]
    for command in commands:
        result = subprocess.run([sys.executable, "-m", *command], cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
