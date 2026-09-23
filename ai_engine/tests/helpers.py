"""Scripted model outputs for orchestration tests, not an offline AI mode."""

import copy

from ai_engine.schema import validate_model


class FixtureProvider:
    def __init__(self, case):
        self.case = case
        self.calls = []
        self.cache_hits = 0

    def usage(self):
        return [
            {
                "provider": "test-double",
                "model": "scripted-control",
                "input_tokens": None,
                "output_tokens": None,
                "calls": len(self.calls),
                "elapsed_ms": 0,
            }
        ]

    async def embeddings(self, texts, input_type="passage"):
        return [[1.0, 0.0] for _ in texts]

    async def structured(self, operation, instructions, payload, schema):
        self.calls.append((operation, copy.deepcopy(payload)))
        value = self.respond(operation, payload)
        validate_model(schema, value)
        return value

    def respond(self, operation, payload):
        if operation == "extract_functions":
            facts = copy.deepcopy(self.case.facts[payload["document"]["id"]])
            target = set(payload["target_span_ids"])
            available = {s["id"] for s in payload["sources"]}
            functions = [
                f
                for f in facts["functions"]
                if target.intersection(f["source_span_ids"])
            ]
            units = [
                u
                for u in facts["units"]
                if set(u["source_span_ids"]).issubset(available)
            ]
            used = {s for f in functions for s in f["source_span_ids"]}
            return {
                "units": units,
                "functions": functions,
                "coverage": [
                    {
                        "span_id": s,
                        "disposition": "functional" if s in used else "context",
                    }
                    for s in sorted(target)
                ],
            }
        if operation == "audit_extraction":
            return {
                "decisions": [
                    {
                        "id": x["id"],
                        "kind": kind,
                        "supported": True,
                        "reason": "Бақылау сценарийіндегі scripted жауап.",
                    }
                    for field, kind in (("units", "unit"), ("functions", "function"))
                    for x in payload[field]
                ]
            }
        if operation in ("match_functions", "verify_matches"):
            decisions = []
            for before in payload["before"]:
                bid = before["source_span_ids"][0]
                expected = self.case.links.get(bid, [])
                after = [
                    a
                    for a in payload["after"]
                    if set(a["source_span_ids"]) & set(expected)
                ]
                found = {s for a in after for s in a["source_span_ids"]}
                full = set(expected).issubset(found) and bool(expected)
                coverage = "full" if full else ("partial" if after else "none")
                if after:
                    coverage = self.case.coverages.get(bid, coverage)
                decisions.append(
                    {
                        "before_id": before["id"],
                        "after_ids": [a["id"] for a in after],
                        "coverage": coverage,
                        "change_flags": self.case.flags.get(bid, []),
                        "uncovered_aspects": ["Міндеттің бөлігі табылмады"]
                        if coverage == "partial"
                        else [],
                        "explanation": "Сценарий бойынша сәйкестік тексерілді.",
                    }
                )
            return {"decisions": decisions}
        if operation in ("compare_organization", "verify_organization"):
            events = []
            for e in self.case.events:
                if not any(s["id"] == e["source"] for s in payload["sources"]):
                    continue
                events.append(
                    {
                        "before_unit_ids": [
                            u["id"]
                            for u in payload["before_units"]
                            if u["name"] == e["before_name"]
                        ],
                        "after_unit_ids": [
                            u["id"]
                            for u in payload["after_units"]
                            if u["name"] == e["after_name"]
                        ],
                        "change_type": e["type"],
                        "explanation": "Қайта атау өкімде берілген.",
                        "source_span_ids": [e["source"]],
                    }
                )
            return {"events": events}
        if operation == "audit_absence":
            return {
                "decisions": [
                    {
                        "before_id": f["id"],
                        "assessment": "absent",
                        "evidence_ids": [],
                        "explanation": "Scripted тексеру: бақылау мәтінінде міндет жоқ.",
                    }
                    for f in payload["before"]
                ]
            }
        if operation in ("detect_risks", "verify_risks"):
            decisions = []
            for p in payload["pairs"]:
                key = tuple(
                    sorted(
                        (
                            p["left"]["source_span_ids"][0],
                            p["right"]["source_span_ids"][0],
                        )
                    )
                )
                kind = self.case.risks.get(key, "none")
                evidence = p["left"]["source_span_ids"] + p["right"]["source_span_ids"]
                if kind == "conflict":
                    evidence += [s["id"] for s in payload["constraints"]]
                decisions.append(
                    {
                        "pair_id": p["id"],
                        "type": kind,
                        "explanation": "Бақылау сценарийінің күтілетін мағыналық шешімі.",
                        "severity": "medium",
                        "evidence_ids": list(dict.fromkeys(evidence)),
                        "counterevidence_ids": [],
                    }
                )
            return {"decisions": decisions}
        raise AssertionError(operation)
