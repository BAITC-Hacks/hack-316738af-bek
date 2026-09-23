"""Validate the frozen team contract without changing backend/frontend schemas."""

from functools import lru_cache
from pathlib import Path
import copy
import hashlib
import json

from jsonschema import Draft202012Validator

from .errors import AnalysisError

CONTRACT_SHA256 = "b8b529d5e9840dcdcda42d91df6359e4584ddea84cdedea17020d7a55dfc8fe9"
SCHEMA_VERSION = "1.0.0"


@lru_cache(maxsize=1)
def contract():
    path = Path(__file__).resolve().parents[1] / "contracts" / "openapi.json"
    try:
        raw = path.read_bytes()
    except OSError:
        raise AnalysisError(
            "CONTRACT_MISSING", "contracts/openapi.json файлы қажет."
        ) from None
    if hashlib.sha256(raw).hexdigest() != CONTRACT_SHA256:
        raise AnalysisError(
            "CONTRACT_MISMATCH", "Ортақ API келісімінің нұсқасы сәйкес емес."
        )
    return json.loads(raw)


def validate(name, value, *, output=False):
    document = contract()
    validator = Draft202012Validator(
        {"$ref": f"#/components/schemas/{name}", "components": document["components"]}
    )
    error = next(validator.iter_errors(value), None)
    if error:
        # Do not expose jsonschema's raw values (possibly untrusted or secret).
        location = "/".join(str(x) for x in error.absolute_path)
        raise AnalysisError(
            "OUTPUT_INVALID" if output else "INPUT_INVALID",
            f"{name}: {location or '/'} өрісі келісімге сәйкес емес.",
        )


def object_schema(**properties):
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def array(items):
    return {"type": "array", "items": items}


def expanded(name):
    """Inline the finite contract types for strict Responses output schemas."""
    definitions = contract()["components"]["schemas"]

    def expand(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return expand(definitions[node["$ref"].rsplit("/", 1)[-1]])
            return {k: expand(v) for k, v in node.items()}
        if isinstance(node, list):
            return [expand(v) for v in node]
        return node

    return expand(copy.deepcopy(definitions[name]))


def validate_model(schema, value):
    if next(Draft202012Validator(schema).iter_errors(value), None):
        raise AnalysisError(
            "MODEL_SCHEMA_INVALID",
            "AI жауабы сұралған деректер схемасына сәйкес емес.",
            True,
        )
