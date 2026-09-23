import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ai_engine.__main__ import main, load_env, read_payload, write_json
from ai_engine.config import Settings
from ai_engine.errors import AnalysisError
from ai_engine.pipeline import AnalysisEngine
from ai_engine.tests.helpers import FixtureProvider
from evaluation.control_cases import cases
from evaluation.scoring import score


class CliTests(unittest.TestCase):
    def test_validate_input_without_keys_or_network(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "input.json"
            write_json(path, cases()[0].payload)
            with (
                patch.dict(os.environ, {}, clear=True),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(main(["--input", str(path), "--validate-only"]), 0)
            self.assertEqual(read_payload(path), cases()[0].payload)

    def test_env_file_does_not_evaluate_shell_or_override_existing_environment(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "keys.env"
            path.write_text(
                'OPENAI_API_KEY="$(not-a-command)"\nOPENAI_MODEL=file-model\nUNRELATED=value\n',
                encoding="utf-8",
            )
            with patch.dict(os.environ, {"OPENAI_MODEL": "existing-model"}, clear=True):
                load_env(path)
                self.assertEqual(os.environ["OPENAI_API_KEY"], "$(not-a-command)")
                self.assertEqual(os.environ["OPENAI_MODEL"], "existing-model")
                self.assertNotIn("UNRELATED", os.environ)

    def test_invalid_input_file_is_sanitized(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "input.json"
            path.write_text('{"secret":"not-valid', encoding="utf-8")
            with self.assertRaises(AnalysisError) as caught:
                read_payload(path)
            self.assertEqual(caught.exception.code, "INPUT_FILE_INVALID")
            self.assertNotIn("secret", caught.exception.message)


class EvaluationTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_scorer_accepts_known_truth_and_rejects_wrong_source(self):
        for case in cases():
            with self.subTest(case=case.name):
                result = await AnalysisEngine(
                    Settings("test", "test"), FixtureProvider(case)
                ).analyze(case.payload)
                self.assertTrue(score(case, result)["passed"])
                if case.name == "transfer":
                    result["mappings"][0]["after_function_ids"] = []
                    self.assertFalse(score(case, result)["passed"])
