"""Run the real browser acceptance test without putting keys in shell history."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path

from dotenv import dotenv_values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--channel", default=os.getenv("PLAYWRIGHT_CHANNEL", ""))
    parser.add_argument("--fixture-set", choices=("standard", "judge"), default="standard")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    values = dotenv_values(root / ".env")
    env = dict(os.environ)
    for name in ("OPENAI_API_KEY", "NVIDIA_API_KEY"):
        env.pop(name, None)
    env["APP_ACCESS_TOKEN"] = env.get("APP_ACCESS_TOKEN") or values.get("APP_ACCESS_TOKEN") or ""
    env["LIVE_BASE_URL"] = args.url
    env["PLAYWRIGHT_CHANNEL"] = args.channel
    env["LIVE_FIXTURE_SET"] = args.fixture_set
    npm = shutil.which("npm.cmd" if os.name == "nt" else "npm")
    if not npm:
        raise SystemExit("Node.js/npm is required")
    return subprocess.call(
        [npm, "exec", "--", "playwright", "test", "--config", "integration/playwright.config.ts"],
        cwd=root / "frontend",
        env=env,
    )


if __name__ == "__main__":
    raise SystemExit(main())
