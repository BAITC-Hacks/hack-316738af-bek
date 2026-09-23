"""Build a small allowlisted handoff, excluding teammates' code and local data."""

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESTINATION = ROOT / "backend/delivery"
ROOT_FILES = [
    "Dockerfile",
    "compose.yaml",
    ".env.example",
    "README.md",
    ".gitignore",
    ".dockerignore",
    "coordination/backend.md",
    "coordination/requests/backend.md",
]
BACKEND_FILES = ["__init__.py", "requirements.txt", "requirements-dev.txt", "pyproject.toml", "HANDOFF.md"]
DIRECTORIES = ["backend/app", "backend/scripts", "backend/tests"]
EXCLUDED = {"__pycache__", ".pytest_cache", ".ruff_cache", ".venv", ".verify-venv", "node_modules"}


def main():
    original = (
        json.loads((ROOT / "MANIFEST.json").read_text(encoding="utf-8")) if (ROOT / "MANIFEST.json").is_file() else None
    )
    if original:
        for name, expected in original["files"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == expected, f"Original file changed: {name}"
    files = [ROOT / name for name in ROOT_FILES] + [ROOT / "backend" / name for name in BACKEND_FILES]
    for directory in DIRECTORIES:
        files.extend(
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file() and not set(p.parts) & EXCLUDED and p.suffix not in (".pyc", ".pyo")
        )
    files = sorted(set(files))
    manifest = {
        "contract_version": "1.0.0",
        "contract_sha256": hashlib.sha256((ROOT / "contracts/openapi.json").read_bytes()).hexdigest(),
        "git_commit": None,
        "files": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
    }
    DESTINATION.mkdir(parents=True, exist_ok=True)
    archive = DESTINATION / "qurylym-backend.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in files:
            output.write(path, path.relative_to(ROOT).as_posix())
    manifest["archive_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()
    (DESTINATION / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    with zipfile.ZipFile(archive) as check:
        assert check.testzip() is None
        assert set(check.namelist()) == set(manifest["files"])
    print(f"Packaged {len(files)} files, {archive.stat().st_size} bytes: {archive}")


if __name__ == "__main__":
    main()
