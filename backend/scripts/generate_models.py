"""Generate reviewable, strict Pydantic models from the team's frozen contract."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def annotation(schema):
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    if "anyOf" in schema:
        return " | ".join(annotation(s) for s in schema["anyOf"])
    if "enum" in schema:
        return f"Literal[{', '.join(repr(v) for v in schema['enum'])}]"
    kind = schema["type"]
    value = (
        f"list[{annotation(schema['items'])}]"
        if kind == "array"
        else {"string": "str", "integer": "int", "boolean": "bool", "null": "None"}.get(kind, "dict")
    )
    constraints = []
    if "minimum" in schema:
        constraints.append(f"ge={schema['minimum']}")
    if "pattern" in schema:
        constraints.append(f"pattern={schema['pattern']!r}")
    return f"Annotated[{value}, Field({', '.join(constraints)})]" if constraints else value


def main():
    contract = json.loads((ROOT / "contracts/openapi.json").read_text(encoding="utf-8"))
    lines = [
        '"""Generated from contracts/openapi.json; regenerate with backend/scripts/generate_models.py."""',
        "from __future__ import annotations",
        "",
        "from typing import Annotated, Literal",
        "from pydantic import BaseModel, ConfigDict, Field",
        "",
        "",
        "class ContractModel(BaseModel):",
        '    model_config = ConfigDict(extra="forbid", strict=True)',
    ]
    for name, schema in contract["components"]["schemas"].items():
        lines.extend(["", "", f"class {name}(ContractModel):"])
        for field, value in schema["properties"].items():
            lines.append(f"    {field}: {annotation(value)}")
    for name in contract["components"]["schemas"]:
        lines.extend(["", f"{name}.model_rebuild()"])
    (ROOT / "backend/app/models.py").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
