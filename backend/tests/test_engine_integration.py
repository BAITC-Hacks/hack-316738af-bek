"""Exercise the real team's pipeline with its scripted provider, without API spending."""

import asyncio

import pytest

pytest.importorskip("ai_engine", reason="The shared AI package is not present in a backend-only delivery")

from ai_engine.config import Settings  # noqa: E402
from ai_engine.pipeline import AnalysisEngine  # noqa: E402
from ai_engine.tests.helpers import FixtureProvider  # noqa: E402
from evaluation.control_cases import cases  # noqa: E402

from backend.app.validation import validate_result  # noqa: E402


@pytest.mark.parametrize("case", cases(), ids=lambda case: case.name)
def test_real_engine_result_is_accepted(case):
    async def run():
        result = await AnalysisEngine(Settings("test-only", "test-model"), FixtureProvider(case)).analyze(case.payload)
        return validate_result(case.payload, result)

    result = asyncio.run(run())
    assert result["analysis_id"] == case.payload["analysis_id"]
    assert result["status"] == "completed"
