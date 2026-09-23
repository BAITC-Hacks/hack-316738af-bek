"""Pin the installed runtime dependency closure without mixing in test tools."""

from importlib.metadata import distribution
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = [
    "fastapi",
    "uvicorn",
    "python-multipart",
    "python-docx",
    "pypdf",
    "openpyxl",
    "defusedxml",
    "filelock",
    "python-dotenv",
]
DEV = ["httpx", "httpx2", "pytest", "pytest-cov", "ruff", "pip-audit", "reportlab", "jsonschema"]


def closure(names):
    packages = {}

    def visit(name):
        package = distribution(name)
        canonical = package.metadata["Name"].lower().replace("_", "-")
        if canonical in packages:
            return
        packages[canonical] = package.version
        for value in package.requires or []:
            requirement = Requirement(value)
            if requirement.marker is None or requirement.marker.evaluate({"extra": ""}):
                visit(requirement.name)

    for name in names:
        visit(name)
    return packages


def main():
    runtime = closure(RUNTIME)
    development = closure(DEV)
    for filename, packages, prefix in (
        ("requirements.txt", runtime, ""),
        ("requirements-dev.txt", {k: v for k, v in development.items() if k not in runtime}, "-r requirements.txt\n"),
    ):
        text = "# Exact versions validated with Python 3.14; regenerate using lock_requirements.py.\n" + prefix
        text += "\n".join(f"{name}=={version}" for name, version in sorted(packages.items())) + "\n"
        (ROOT / "backend" / filename).write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
