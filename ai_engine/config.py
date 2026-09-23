"""Explicit configuration; no secrets or untrusted document URLs in logs."""

from dataclasses import dataclass, field
import os

from .errors import AnalysisError


def _integer(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        raise AnalysisError("CONFIG_INVALID", f"{name}: бүтін сан қажет.") from None
    if not low <= value <= high:
        raise AnalysisError("CONFIG_INVALID", f"{name}: {low}–{high} аралығы қажет.")
    return value


@dataclass(frozen=True)
class Settings:
    api_key: str = field(repr=False)
    model: str
    nvidia_key: str = field(default="", repr=False)
    nvidia_model: str = "nvidia/llama-nemotron-embed-1b-v2"
    nvidia_enabled: bool = False
    timeout_seconds: int = 600
    request_timeout: int = 90
    max_requests: int = 100
    max_output_tokens: int = 12000
    extraction_chars: int = 18000
    comparison_chars: int = 42000
    max_input_chars: int = 1200000
    max_functions: int = 1500
    concurrency: int = 3
    retries: int = 2
    max_risk_pairs: int = 200

    @classmethod
    def from_env(cls):
        enabled = os.getenv("NVIDIA_ENABLED", "false").strip().lower()
        if enabled not in ("true", "false"):
            raise AnalysisError(
                "CONFIG_INVALID", "NVIDIA_ENABLED: true немесе false қажет."
            )
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            model=os.getenv("OPENAI_MODEL", "").strip(),
            nvidia_key=os.getenv("NVIDIA_API_KEY", "").strip(),
            nvidia_model=os.getenv(
                "NVIDIA_EMBED_MODEL", "nvidia/llama-nemotron-embed-1b-v2"
            ).strip(),
            nvidia_enabled=enabled == "true",
            timeout_seconds=_integer("ANALYSIS_TIMEOUT_SECONDS", 600, 10, 3600),
            request_timeout=_integer("AI_REQUEST_TIMEOUT_SECONDS", 90, 1, 300),
            max_requests=_integer("AI_MAX_REQUESTS", 100, 1, 500),
            max_output_tokens=_integer("AI_MAX_OUTPUT_TOKENS", 12000, 500, 32000),
            concurrency=_integer("AI_CONCURRENCY", 3, 1, 8),
            max_risk_pairs=_integer("AI_MAX_RISK_PAIRS", 200, 1, 5000),
        )

    def require_live(self):
        if not self.api_key:
            raise AnalysisError(
                "OPENAI_KEY_MISSING", "Серверде OPENAI_API_KEY орнатылмаған."
            )
        if not self.model:
            raise AnalysisError(
                "OPENAI_MODEL_MISSING", "Серверде OPENAI_MODEL орнатылмаған."
            )
