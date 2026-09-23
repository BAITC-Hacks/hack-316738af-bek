"""Reproducible offline engineering checks; explicitly not live AI evaluation."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
import unittest

from ai_engine.__main__ import write_json
from ai_engine.schema import CONTRACT_SHA256


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--report",
        type=Path,
        default=Path("evaluation/local_reports/engineering_checks.json"),
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    suite = unittest.defaultTestLoader.discover(
        str(root / "ai_engine" / "tests"), top_level_dir=str(root)
    )
    start = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {
        "mode": "offline_engineering_tests",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "contract_sha256": CONTRACT_SHA256,
        "tests_run": result.testsRun,
        "failures": len(result.failures),
        "errors": len(result.errors),
        "skipped": len(result.skipped),
        "seconds": round(time.monotonic() - start, 3),
        "passed": result.wasSuccessful(),
        "live_api_calls": 0,
        "live_model_accuracy_measured": False,
        "scope": [
            "15 scripted domain controls exercise real extraction/matching/risk orchestration and evidence validation.",
            "Malformed sources, fabricated quotes, semantic audit rejection, cancellation and progress errors.",
            "Provider envelope validation, retry, request limits, cache, refusal and embeddings.",
        ],
        "limitations": [
            "Scripted model replies test code paths; they do not measure real model understanding.",
            "No UI, backend parsing, storage or export integration is exercised.",
        ],
    }
    write_json(args.report, report)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
