"""Live AI evaluation. No fixture provider is imported by this runner."""

import argparse
import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
import time

from ai_engine.__main__ import load_env, write_json
from ai_engine.config import Settings
from ai_engine.errors import AnalysisError
from ai_engine.pipeline import AnalysisEngine
from ai_engine.prompts import PROMPT_VERSION
from ai_engine.schema import CONTRACT_SHA256
from .control_cases import cases
from .scoring import score


async def run(selected, settings, directory, max_total_calls):
    reports = []
    calls_used = 0
    started = time.monotonic()
    for case in selected:
        remaining = max_total_calls - calls_used
        if remaining <= 0:
            reports.append(
                {
                    "case": case.name,
                    "status": "not_run",
                    "reason": "SUITE_CALL_BUDGET_EXCEEDED",
                    "passed": False,
                }
            )
            continue
        engine = AnalysisEngine(
            replace(settings, max_requests=min(settings.max_requests, remaining))
        )
        t0 = time.monotonic()
        try:
            result = await engine.analyze(case.payload)
            write_json(directory / (case.name + ".result.json"), result)
            reports.append(
                {
                    "case": case.name,
                    "status": result["status"],
                    "seconds": round(time.monotonic() - t0, 3),
                    **score(case, result),
                }
            )
        except AnalysisError as exc:
            reports.append(
                {
                    "case": case.name,
                    "status": "error",
                    "error_code": exc.code,
                    "passed": False,
                    "seconds": round(time.monotonic() - t0, 3),
                }
            )
        reports[-1]["usage"] = engine.provider.usage()
        calls_used += sum(u["calls"] for u in engine.provider.usage())
        print(
            case.name
            + ": "
            + reports[-1]["status"]
            + "; passed="
            + str(reports[-1]["passed"]),
            flush=True,
        )
        # Checkpoint a real report even when a later case is cancelled.
        write_json(
            directory / "live_evaluation.json",
            {"mode": "live", "complete": False, "cases": reports},
        )
    tp = sum(r.get("risk_true_positive", 0) for r in reports)
    fp = sum(r.get("risk_false_positive", 0) for r in reports)
    fn = sum(r.get("risk_false_negative", 0) for r in reports)
    report = {
        "mode": "live",
        "complete": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": settings.model,
        "nvidia_enabled": settings.nvidia_enabled,
        "prompt_version": PROMPT_VERSION,
        "contract_sha256": CONTRACT_SHA256,
        "cases_total": len(selected),
        "cases_passed": sum(r["passed"] for r in reports),
        "calls_used": calls_used,
        "seconds": round(time.monotonic() - started, 3),
        "risk_precision": tp / (tp + fp) if tp + fp else None,
        "risk_recall": tp / (tp + fn) if tp + fn else None,
        "cases": reports,
        "limitations": [
            "Small synthetic set; these metrics are not a guarantee on unseen organizational documents.",
            "Parsing, UI and source-file navigation must be tested in the integrated backend/frontend.",
            "Source-anchored labels allow different atomic extraction granularity.",
        ],
    }
    write_json(directory / "live_evaluation.json", report)
    return 0 if report["cases_passed"] == len(selected) else 1


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Export synthetic inputs or run real, paid model evaluations."
    )
    parser.add_argument(
        "--export-dir",
        type=Path,
        help="Export inputs and expected labels separately; no API calls",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call configured OpenAI model; consumes API credits",
    )
    parser.add_argument(
        "--cases",
        default="unchanged,loss,transfer,duplicate,rename,executor_controller",
    )
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--env-file")
    parser.add_argument(
        "--output-dir", type=Path, default=Path("evaluation/local_reports")
    )
    parser.add_argument("--max-total-calls", type=int, default=120)
    args = parser.parse_args(argv)
    available = {c.name: c for c in cases()}
    names = list(available) if args.all else args.cases.split(",")
    if not names or any(n not in available for n in names):
        parser.error(
            "Unknown case; use --all or names from evaluation/control_cases.py"
        )
    selected = [available[n] for n in names]
    if args.export_dir:
        for case in selected:
            write_json(args.export_dir / (case.name + ".input.json"), case.payload)
            write_json(
                args.export_dir / (case.name + ".expected.json"),
                {
                    "name": case.name,
                    "links": case.links,
                    "flags": case.flags,
                    "coverages": case.coverages,
                    "risks": [
                        {"source_ids": list(k), "kind": v}
                        for k, v in case.risks.items()
                    ],
                    "expectations": case.expected,
                },
            )
        print("Exported " + str(len(selected)) + " synthetic cases; no API calls.")
    if not args.live:
        if not args.export_dir:
            parser.error("Choose --export-dir or --live")
        return 0
    if not 1 <= args.max_total_calls <= 1000:
        parser.error("--max-total-calls must be in 1..1000")
    try:
        load_env(args.env_file)
        settings = Settings.from_env()
        settings.require_live()
        return asyncio.run(
            run(selected, settings, args.output_dir, args.max_total_calls)
        )
    except AnalysisError as exc:
        print("Evaluation not started: " + exc.code)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
