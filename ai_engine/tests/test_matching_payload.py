"""Lossless evidence sharing and exhaustive size-bounded comparison requests."""

import copy
import json
import unittest

from ai_engine.errors import AnalysisError
from ai_engine.matching import (
    comparison_partitions,
    comparison_payload,
    function_record,
)
from ai_engine.sources import SourceRegistry
from evaluation.control_cases import cases


class ComparisonPayloadTests(unittest.TestCase):
    def setUp(self):
        case = cases()[0]
        self.registry = SourceRegistry(case.payload)
        old, new = case.payload["documents"]
        self.before = copy.deepcopy(case.facts[old["id"]]["functions"])
        base = case.facts[new["id"]]["functions"][0]
        self.after = [dict(copy.deepcopy(base), id=f"function-{i}") for i in range(12)]

    def test_shared_sources_reconstruct_every_original_record_without_mutation(self):
        original = copy.deepcopy((self.before, self.after))
        payload = comparison_payload(self.before, self.after, [], self.registry)
        sources = {s["id"]: s for s in payload["sources"]}
        self.assertEqual(len(sources), len(payload["sources"]))
        for field, functions in (("before", self.before), ("after", self.after)):
            for wire, function in zip(payload[field], functions):
                restored = dict(wire)
                restored["evidence"] = [
                    sources[sid] for sid in restored.pop("evidence_span_ids")
                ]
                self.assertEqual(restored, function_record(function, self.registry))
        self.assertEqual((self.before, self.after), original)
        expanded = {
            "before": [function_record(f, self.registry) for f in self.before],
            "after": [function_record(f, self.registry) for f in self.after],
            "units": [],
        }
        self.assertLess(len(json.dumps(payload)), len(json.dumps(expanded)))

    def test_partitions_cover_all_functions_and_preserve_every_context(self):
        one = comparison_payload([], self.after[:1], [], self.registry)
        limit = (
            len(json.dumps(one["after"], ensure_ascii=False))
            + len(json.dumps(one["sources"], ensure_ascii=False))
            + 100
        )
        parts = list(comparison_partitions(self.after, self.registry, limit))
        self.assertGreater(len(parts), 1)
        self.assertEqual([f for part in parts for f in part], self.after)
        for part in parts:
            payload = comparison_payload([], part, [], self.registry)
            size = len(json.dumps(payload["after"], ensure_ascii=False)) + len(
                json.dumps(payload["sources"], ensure_ascii=False)
            )
            self.assertLessEqual(size, limit)
            expected = {
                source["id"]: source
                for function in part
                for source in function_record(function, self.registry)["evidence"]
            }
            self.assertEqual({s["id"]: s for s in payload["sources"]}, expected)

    def test_oversized_evidence_fails_without_silent_truncation(self):
        with self.assertRaises(AnalysisError) as error:
            list(comparison_partitions(self.after, self.registry, 1))
        self.assertEqual(error.exception.code, "ITEM_TOO_LARGE")

    def test_empty_after_keeps_before_evidence(self):
        payload = comparison_payload(self.before, [], [], self.registry)
        self.assertEqual(payload["after"], [])
        self.assertTrue(payload["sources"])
        self.assertEqual(list(comparison_partitions([], self.registry, 100)), [])
