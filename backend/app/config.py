"""Explicit server limits; credentials are never serialized into responses."""

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", ROOT / "backend/data")))
    frontend_dir: Path = field(default_factory=lambda: ROOT / "frontend/dist")
    analysis_timeout: float = field(default_factory=lambda: float(os.getenv("ANALYSIS_TIMEOUT_SECONDS", "300")))
    parse_timeout: float = 45
    max_file_bytes: int = 20 * 1024 * 1024
    max_files: int = 10
    max_text_chars: int = 500_000
    max_spans: int = 20_000
    max_archive_bytes: int = 100 * 1024 * 1024
    access_token: str = field(default_factory=lambda: os.getenv("APP_ACCESS_TOKEN", ""))
    secure_cookie: bool = field(default_factory=lambda: os.getenv("COOKIE_SECURE", "false").lower() == "true")
    allowed_origins: tuple[str, ...] = field(
        default_factory=lambda: tuple(s.strip() for s in os.getenv("CORS_ORIGINS", "").split(",") if s.strip())
    )

    def __post_init__(self):
        if self.analysis_timeout <= 0 or self.parse_timeout <= 0:
            raise ValueError("Timeouts must be positive")
        if "*" in self.allowed_origins:
            raise ValueError("CORS_ORIGINS must contain explicit origins")
