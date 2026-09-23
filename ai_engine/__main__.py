"""CLI for a real provider run or a free input validation check."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

from .config import Settings
from .errors import AnalysisError
from .pipeline import analyze
from .sources import SourceRegistry

ENV_NAMES = {
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "NVIDIA_API_KEY",
    "NVIDIA_ENABLED",
    "NVIDIA_EMBED_MODEL",
    "ANALYSIS_TIMEOUT_SECONDS",
    "AI_REQUEST_TIMEOUT_SECONDS",
    "AI_MAX_REQUESTS",
    "AI_MAX_OUTPUT_TOKENS",
    "AI_CONCURRENCY",
    "AI_MAX_RISK_PAIRS",
}


def load_env(path):
    """Optional explicit file, no shell evaluation and no automatic file search."""
    if path is None:
        return
    try:
        raw = Path(path).read_text(encoding="utf-8-sig")
    except OSError:
        raise AnalysisError(
            "ENV_FILE_UNREADABLE", "Көрсетілген орта файлы оқылмады."
        ) from None
    if len(raw) > 65536:
        raise AnalysisError("ENV_FILE_INVALID", "Орта файлы тым үлкен.")
    for index, line in enumerate(raw.splitlines(), 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise AnalysisError(
                "ENV_FILE_INVALID", f"Орта файлының {index}-жолында KEY=VALUE қажет."
            )
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if name not in ENV_NAMES:
            # The same local env file may contain backend settings.
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        if not os.environ.get(name):
            os.environ[name] = value


def read_payload(path):
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            raise AnalysisError(
                "INPUT_TOO_LARGE", "Кіріс JSON файлы 16 MiB шегінен асты."
            )
        return json.loads(raw.decode("utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise AnalysisError(
            "INPUT_FILE_INVALID", "Кіріс файлы оқылмады немесе жарамды UTF-8 JSON емес."
        ) from None


def write_json(path, value):
    """Replace atomically; interrupted writes do not create a half-JSON report."""
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=target.parent,
            prefix=target.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


async def progress(event):
    print(json.dumps(event, ensure_ascii=True), file=sys.stderr, flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Qurylym AI: live analysis of the frozen AnalysisInput contract."
    )
    parser.add_argument("--input", help="Parsed AnalysisInput JSON from the backend")
    parser.add_argument("--output", help="AnalysisResult JSON output")
    parser.add_argument("--env-file", help="Explicit local env file (never commit it)")
    parser.add_argument(
        "--validate-only", action="store_true", help="Validate input without API calls"
    )
    parser.add_argument(
        "--config-check",
        action="store_true",
        help="Show readiness booleans without revealing credentials",
    )
    args = parser.parse_args(argv)
    try:
        load_env(args.env_file)
        settings = Settings.from_env()
        if args.config_check:
            print(
                json.dumps(
                    {
                        "openai_key_present": bool(settings.api_key),
                        "openai_model_present": bool(settings.model),
                        "nvidia_enabled": settings.nvidia_enabled,
                        "nvidia_key_present": bool(settings.nvidia_key),
                        "max_requests": settings.max_requests,
                    },
                    ensure_ascii=True,
                )
            )
            return 0 if settings.api_key and settings.model else 2
        if not args.input:
            parser.error("--input is required unless --config-check is used")
        payload = read_payload(args.input)
        registry = SourceRegistry(payload, settings.max_input_chars)
        if args.validate_only:
            print(
                json.dumps(
                    {
                        "valid": True,
                        "documents": len(registry.docs),
                        "spans": len(registry.spans),
                    },
                    ensure_ascii=True,
                )
            )
            return 0
        if not args.output:
            parser.error("--output is required for live analysis")
        result = asyncio.run(analyze(payload, progress))
        write_json(args.output, result)
        print(
            json.dumps(
                {
                    "status": result["status"],
                    "output": str(Path(args.output).resolve()),
                },
                ensure_ascii=True,
            )
        )
        return 0 if result["status"] == "completed" else 3
    except AnalysisError as exc:
        print(
            json.dumps(
                {
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "retryable": exc.retryable,
                    }
                },
                ensure_ascii=True,
            ),
            file=sys.stderr,
        )
        return 2
    except OSError:
        print(
            json.dumps(
                {
                    "error": {
                        "code": "OUTPUT_WRITE_FAILED",
                        "message": "Result file could not be written.",
                        "retryable": False,
                    }
                }
            ),
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
