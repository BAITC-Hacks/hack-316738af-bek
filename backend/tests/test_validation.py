import json
from copy import deepcopy

import pytest

from backend.app.config import ROOT
from backend.app.exports import csv_safe
from backend.app.parsers import parse_document
from backend.app.validation import validate_result
from backend.tests.conftest import docx_bytes, result_for


@pytest.fixture
def payload(settings):
    documents = [parse_document(docx_bytes(), v + ".docx", "docx", v, v, settings) for v in ("before", "after")]
    return {"schema_version": "1.0.0", "analysis_id": "test", "analysis_revision": 3, "documents": documents}


def test_valid_result_and_official_examples(payload):
    assert validate_result(payload, result_for(payload))["status"] == "completed"
    source = json.loads((ROOT / "contracts/analysis_input.example.json").read_text(encoding="utf-8"))
    result = json.loads((ROOT / "contracts/analysis_result.example.json").read_text(encoding="utf-8"))
    assert validate_result(source, result)["status"] == "completed"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda r: r.update(analysis_id="other"),
        lambda r: r.update(analysis_revision=8),
        lambda r: r["documents"][0].update(title="invented"),
        lambda r: r["functions"][0].update(source_span_ids=["foreign"]),
        lambda r: r["units"][0].update(parent_id="u-before"),
        lambda r: r["functions"][0].update(unit_id="missing"),
        lambda r: r["functions"][0].update(role_id="u-before"),
        lambda r: r["mappings"].append(deepcopy(r["mappings"][0])),
        lambda r: r["mappings"][0].update(coverage_status="none"),
        lambda r: r["mappings"][0].update(coverage_status="partial"),
        lambda r: r["findings"][0].update(review_status="confirmed"),
        lambda r: r["findings"][0].update(type="potential_loss", verification_status="validated"),
        lambda r: r["coverage"].update(full=20),
        lambda r: r["coverage"].update(evidence_links_valid=0),
        lambda r: r["summary"]["items"][0].update(reference_ids=["fake"]),
        lambda r: r.update(secret="not allowed"),
    ],
)
def test_corrupt_engine_results_rejected(payload, mutation):
    result = result_for(payload)
    mutation(result)
    with pytest.raises(ValueError):
        validate_result(payload, result)


@pytest.mark.parametrize("value", ["=1+1", "+CMD", "-1+3", "@SUM(A1)", " \t=2+2", "\r=1", "\n@evil", "\ufeff=1"])
def test_csv_formula_neutralization(value):
    assert csv_safe(value).startswith("'")


def test_safe_csv_text():
    assert csv_safe("Қазақша мәтін") == "Қазақша мәтін"
    assert csv_safe(None) == ""
