import asyncio
import copy
import unittest
from dataclasses import replace
from unittest.mock import patch

from ai_engine.config import Settings
from ai_engine.errors import AnalysisError
from ai_engine.pipeline import AnalysisEngine, analyze
from ai_engine.sources import SourceRegistry
from ai_engine.validation import validate_result
from evaluation.control_cases import cases, make_case, unit, duty
from ai_engine.tests.helpers import FixtureProvider


def measurements(result):
    findings, mappings = result["findings"], result["mappings"]
    return {
        **{k: result["coverage"][k] for k in ("full", "partial", "none", "unknown")},
        "before_total": result["coverage"]["before_functions_total"],
        **{
            label: sum(f["type"] == kind for f in findings)
            for label, kind in (
                ("loss", "potential_loss"),
                ("duplicate", "potential_duplicate"),
                ("conflict", "potential_conflict"),
                ("ownership_gap", "ownership_gap"),
            )
        },
        **{
            flag: sum(flag in m["change_flags"] for m in mappings)
            for flag in ("transferred", "frequency_changed", "split", "merged")
        },
        "new_risk": sum(
            f["risk_change"] == "new"
            for f in findings
            if f["type"] in ("potential_duplicate", "potential_conflict")
        ),
        "persisting": sum(f["risk_change"] == "persisting" for f in findings),
        "renamed_unit": sum(
            u["change_type"] == "renamed" for u in result["unit_changes"]
        ),
    }


class PipelineTests(unittest.IsolatedAsyncioTestCase):
    async def run_case(self, case, provider=None, settings=None, callback=None):
        return await AnalysisEngine(
            settings or Settings("test-only", "test-model"),
            provider or FixtureProvider(case),
        ).analyze(case.payload, callback)

    async def test_fifteen_domain_controls(self):
        for case in cases():
            with self.subTest(case=case.name):
                original = copy.deepcopy(case.payload)
                result = await self.run_case(case)
                actual = measurements(result)
                self.assertEqual(case.payload, original, "Caller input was mutated")
                self.assertEqual(result["status"], "completed")
                for key, expected in case.expected.items():
                    self.assertEqual(actual[key], expected, key)
                self.assertTrue(
                    all(f["review_status"] == "unreviewed" for f in result["findings"])
                )
                self.assertEqual(
                    result["coverage"]["evidence_links_total"],
                    result["coverage"]["evidence_links_valid"],
                )
                validate_result(result, SourceRegistry(case.payload))

    async def test_partial_after_does_not_prove_absence(self):
        case = next(c for c in cases() if c.name == "loss")
        case.payload["documents"][1]["parse_status"] = "partial"
        result = await self.run_case(case)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["coverage"]["none"], 0)
        self.assertEqual(result["coverage"]["unknown"], 1)
        self.assertFalse(any(f["type"] == "potential_loss" for f in result["findings"]))

    async def test_role_in_department_slot_preserves_evidenced_actor(self):
        position = unit("Аудитор", "r", kind="role")
        task = duty("check", "r", "тексеру", "есеп")
        case = make_case(
            "role-slot", [position], [task], [position], [task], {"check": ["check"]}
        )
        provider = FixtureProvider(case)
        result = await self.run_case(case, provider)
        self.assertEqual(result["status"], "completed")
        self.assertTrue(
            all(f["unit_id"] is None and f["role_id"] for f in result["functions"])
        )
        self.assertEqual({u["kind"] for u in result["units"]}, {"role"})
        for op, payload in provider.calls:
            if op == "audit_extraction":
                self.assertTrue(
                    all(
                        f["unit_id"] is None and f["role_id"]
                        for f in payload["functions"]
                    )
                )

    async def test_fabricated_quote_quarantines_chunk(self):
        case = cases()[0]

        class Fabricated(FixtureProvider):
            def respond(self, operation, payload):
                data = super().respond(operation, payload)
                if operation == "extract_functions" and payload["version"] == "after":
                    data["functions"][0]["evidence_quotes"][0]["quote"] = (
                        "THIS QUOTE DOES NOT EXIST"
                    )
                return data

        result = await self.run_case(case, Fabricated(case))
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["coverage"]["unknown"], 1)
        self.assertIn("QUOTE_INVALID", {w["code"] for w in result["warnings"]})
        self.assertFalse(any(f["version"] == "after" for f in result["functions"]))

    async def test_invalid_quote_retries_once_then_audits_regenerated_evidence(self):
        case = cases()[0]

        class Corrected(FixtureProvider):
            def respond(self, operation, payload):
                data = super().respond(operation, payload)
                if (
                    operation == "extract_functions"
                    and payload["version"] == "after"
                    and "correction" not in payload
                ):
                    data["functions"][0]["evidence_quotes"][0]["quote"] = (
                        "NONVERBATIM SUMMARY..."
                    )
                return data

        provider = Corrected(case)
        result = await self.run_case(case, provider)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["coverage"]["full"], 1)
        self.assertEqual(sum(op == "extract_functions" for op, _ in provider.calls), 3)
        self.assertEqual(sum(op == "audit_extraction" for op, _ in provider.calls), 2)

    async def test_semantic_audit_rejects_unsupported_object(self):
        case = cases()[0]

        class Rejecting(FixtureProvider):
            def respond(self, operation, payload):
                data = super().respond(operation, payload)
                if (
                    operation == "audit_extraction"
                    and payload["functions"][0]["version"] == "after"
                ):
                    for d in data["decisions"]:
                        if d["kind"] == "function":
                            d["supported"] = False
                return data

        result = await self.run_case(case, Rejecting(case))
        self.assertEqual(result["coverage"]["unknown"], 1)
        self.assertIn("GROUNDING_REJECTED", {w["code"] for w in result["warnings"]})

    async def test_cross_version_extraction_rejected(self):
        case = cases()[0]

        class WrongVersion(FixtureProvider):
            def respond(self, operation, payload):
                data = super().respond(operation, payload)
                if operation == "extract_functions" and payload["version"] == "after":
                    data["functions"][0]["source_span_ids"] = ["before:fn:archive"]
                return data

        result = await self.run_case(case, WrongVersion(case))
        self.assertEqual(result["coverage"]["unknown"], 1)
        self.assertIn("EVIDENCE_INVALID", {w["code"] for w in result["warnings"]})

    async def test_raw_source_countercheck_prevents_false_loss(self):
        case = next(c for c in cases() if c.name == "loss")

        class Counterpart(FixtureProvider):
            def respond(self, operation, payload):
                data = super().respond(operation, payload)
                if operation == "audit_absence":
                    for d in data["decisions"]:
                        d["assessment"] = "counterpart_found"
                        d["evidence_ids"] = ["after:fn:archive"]
                return data

        result = await self.run_case(case, Counterpart(case))
        self.assertEqual(result["coverage"]["none"], 0)
        self.assertEqual(result["coverage"]["unknown"], 1)
        self.assertFalse(any(f["type"] == "potential_loss" for f in result["findings"]))

    async def test_final_callback_failure_is_reported(self):
        async def fail_last(event):
            if event["stage"] == "completed":
                raise RuntimeError("details")

        result = await self.run_case(cases()[0], callback=fail_last)
        self.assertIn(
            "PROGRESS_CALLBACK_FAILED", {w["code"] for w in result["warnings"]}
        )

    async def test_organization_failure_marks_result_partial(self):
        case = next(c for c in cases() if c.name == "rename")

        class FailedOrg(FixtureProvider):
            async def structured(self, operation, *args):
                if operation == "compare_organization":
                    raise AnalysisError("PROVIDER_UNAVAILABLE", "Unavailable", True)
                return await super().structured(operation, *args)

        result = await self.run_case(case, FailedOrg(case))
        self.assertEqual(result["status"], "partial")

    async def test_callback_failure_does_not_destroy_analysis(self):
        async def broken(event):
            raise RuntimeError("private callback details")

        result = await self.run_case(cases()[0], callback=broken)
        self.assertEqual(result["status"], "completed")
        self.assertIn(
            "PROGRESS_CALLBACK_FAILED", {w["code"] for w in result["warnings"]}
        )
        self.assertNotIn("private callback", str(result))

    async def test_progress_and_deterministic_ids(self):
        events = []

        async def collect(event):
            events.append(event)

        case = cases()[0]
        first = await self.run_case(case, callback=collect)
        second = await self.run_case(case)
        self.assertEqual(first, second)
        self.assertEqual(events[0]["stage"], "extracting")
        self.assertEqual(events[-1]["stage"], "completed")

    async def test_timeout(self):
        case = cases()[0]

        class Slow(FixtureProvider):
            async def structured(self, *args):
                await asyncio.sleep(2)

        with self.assertRaises(AnalysisError) as caught:
            await self.run_case(
                case,
                Slow(case),
                replace(Settings("test", "test"), timeout_seconds=0.01),
            )
        self.assertEqual(caught.exception.code, "ANALYSIS_TIMEOUT")

    async def test_cancellation_propagates(self):
        case = cases()[0]

        class Cancelled(FixtureProvider):
            async def structured(self, *args):
                raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await self.run_case(case, Cancelled(case))

    async def test_public_entry_never_uses_scripted_fallback(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(AnalysisError) as caught:
                await analyze(cases()[0].payload)
        self.assertEqual(caught.exception.code, "OPENAI_KEY_MISSING")

    async def test_output_tampering_rejected(self):
        case = cases()[0]
        good = await self.run_case(case)
        for mutate in (
            lambda r: r["coverage"].__setitem__("full", 99),
            lambda r: r["mappings"][0]["source_span_ids"].append("invented"),
            lambda r: r["mappings"].append(copy.deepcopy(r["mappings"][0])),
            lambda r: r["functions"][0].__setitem__("unit_id", "missing-owner"),
        ):
            bad = copy.deepcopy(good)
            mutate(bad)
            with self.assertRaises(AnalysisError):
                validate_result(bad, SourceRegistry(case.payload))

    async def test_nvidia_failure_is_visible_and_comparison_continues(self):
        case = cases()[0]

        class NoNvidia(FixtureProvider):
            async def embeddings(self, *args):
                raise AnalysisError("NVIDIA_KEY_MISSING", "missing")

        result = await self.run_case(
            case, NoNvidia(case), replace(Settings("test", "test"), nvidia_enabled=True)
        )
        self.assertEqual(result["coverage"]["full"], 1)
        self.assertIn("NVIDIA_UNAVAILABLE", {w["code"] for w in result["warnings"]})

    async def test_same_position_title_under_different_departments_not_merged(self):
        units = [
            unit("Аудит бөлімі", "a"),
            unit("Есеп бөлімі", "b"),
            unit("Бөлім бастығы", "ra", parent="a", kind="role"),
            unit("Бөлім бастығы", "rb", parent="b", kind="role"),
        ]
        fs = [duty("report", "a", "жасау", "есеп")]
        case = make_case("repeated_title", units, fs, units, fs, {"report": ["report"]})
        result = await self.run_case(case)
        for version in ("before", "after"):
            roles = [
                u
                for u in result["units"]
                if u["version"] == version and u["kind"] == "role"
            ]
            self.assertEqual(len(roles), 2)
            self.assertNotEqual(roles[0]["parent_id"], roles[1]["parent_id"])

    async def test_empty_numbered_clause_not_a_function(self):
        case = cases()[0]
        document = case.payload["documents"][0]
        empty = copy.deepcopy(document["spans"][-1])
        empty.update(id="before:empty", raw_text="5.5.3. ;")
        document["spans"].append(empty)
        document["span_count"] += 1
        result = await self.run_case(case)
        self.assertEqual(result["coverage"]["before_functions_total"], 1)
        self.assertTrue(
            any(
                f["type"] == "document_quality" and "before:empty" in f["evidence_ids"]
                for f in result["findings"]
            )
        )

    async def test_search_covers_all_after_partitions(self):
        a = unit("Есеп бөлімі", "a")
        old = duty("missing", "a", "сақтау", "ерекше мұрағат")
        later = [
            duty(
                "item" + str(i),
                "a",
                "жасау",
                "есептің " + str(i) + " түрі",
                text="Арнайы есепті жасау. " + ("Толық мазмұн. " * 15),
            )
            for i in range(12)
        ]
        case = make_case("partitions", [a], [old], [a], later, {"missing": []})
        provider = FixtureProvider(case)
        result = await self.run_case(
            case, provider, replace(Settings("test", "test"), comparison_chars=3000)
        )
        searches = [p for op, p in provider.calls if op == "match_functions"]
        self.assertGreater(len(searches), 1)
        searched = {
            s for p in searches for f in p["after"] for s in f["source_span_ids"]
        }
        self.assertEqual(searched, {"after:fn:item" + str(i) for i in range(12)})
        raw_searched = {
            s["id"]
            for op, p in provider.calls
            if op == "audit_absence"
            for s in p["after_sources"]
        }
        self.assertTrue(searched.issubset(raw_searched))
        self.assertEqual(result["coverage"]["none"], 1)

    async def test_partial_counterpart_after_incomplete_parse_is_unknown(self):
        case = next(c for c in cases() if c.name == "split")
        case.payload["documents"][1]["parse_status"] = "partial"

        class Partial(FixtureProvider):
            def respond(self, operation, payload):
                data = super().respond(operation, payload)
                if operation in ("match_functions", "verify_matches"):
                    for d in data["decisions"]:
                        d["coverage"] = "partial"
                        d["uncovered_aspects"] = ["Шоттар міндетінің қамтуы белгісіз"]
                return data

        result = await self.run_case(case, Partial(case))
        self.assertEqual(result["coverage"]["unknown"], 1)
        self.assertFalse(any(f["type"] == "potential_loss" for f in result["findings"]))


class InputTests(unittest.TestCase):
    def test_invalid_source_graphs_and_counts(self):
        for code, mutate in (
            (
                "DOCUMENT_ID_DUPLICATE",
                lambda p: p["documents"].append(copy.deepcopy(p["documents"][0])),
            ),
            (
                "SPAN_COUNT_MISMATCH",
                lambda p: p["documents"][0].__setitem__("span_count", 999),
            ),
            (
                "SOURCE_DOCUMENT_MISMATCH",
                lambda p: p["documents"][0]["spans"][0].__setitem__(
                    "document_id", "after-document"
                ),
            ),
            (
                "SOURCE_CONTEXT_INVALID",
                lambda p: p["documents"][0]["spans"][0].__setitem__(
                    "context_span_ids", ["after:unit:a"]
                ),
            ),
            (
                "SOURCE_CONTEXT_CYCLE",
                lambda p: p["documents"][0]["spans"][0].__setitem__(
                    "context_span_ids", ["before:fn:archive"]
                ),
            ),
            (
                "PARSING_PENDING",
                lambda p: p["documents"][0].__setitem__("parse_status", "pending"),
            ),
        ):
            with self.subTest(code=code):
                payload = copy.deepcopy(cases()[0].payload)
                mutate(payload)
                with self.assertRaises(AnalysisError) as caught:
                    SourceRegistry(payload)
                self.assertEqual(caught.exception.code, code)

    def test_limits_and_config(self):
        with self.assertRaises(AnalysisError) as caught:
            SourceRegistry(cases()[0].payload, max_chars=1)
        self.assertEqual(caught.exception.code, "INPUT_TOO_LARGE")
        for key, value in [
            ("AI_CONCURRENCY", "0"),
            ("AI_MAX_REQUESTS", "oops"),
            ("NVIDIA_ENABLED", "perhaps"),
        ]:
            with patch.dict("os.environ", {key: value}, clear=True):
                with self.assertRaises(AnalysisError) as caught:
                    Settings.from_env()
                self.assertEqual(caught.exception.code, "CONFIG_INVALID")
        self.assertNotIn(
            "secret-marker",
            repr(Settings("secret-marker", "model", nvidia_key="secret-marker")),
        )
