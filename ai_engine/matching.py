"""Exhaustive partition search, multi-aspect matching and explicit reorganization."""

import asyncio
import re

from . import prompts
from .errors import AnalysisError
from .schema import object_schema, array
from .sources import diagnostic, normalize, pack_chunks, stable_id, unique

TEXT = {"type": "string"}
FLAGS = [
    "transferred",
    "renamed",
    "split",
    "merged",
    "wording_changed",
    "scope_changed",
    "frequency_changed",
    "authority_changed",
]
DECISION = object_schema(
    before_id=TEXT,
    after_ids=array(TEXT),
    coverage={"type": "string", "enum": ["full", "partial", "none", "unknown"]},
    change_flags=array({"type": "string", "enum": FLAGS}),
    uncovered_aspects=array(TEXT),
    explanation=TEXT,
)
MATCH_SCHEMA = object_schema(decisions=array(DECISION))
ORG_SCHEMA = object_schema(
    events=array(
        object_schema(
            before_unit_ids=array(TEXT),
            after_unit_ids=array(TEXT),
            change_type={
                "type": "string",
                "enum": ["renamed", "merged", "split", "reorganized"],
            },
            explanation=TEXT,
            source_span_ids=array(TEXT),
        )
    )
)
ABSENCE_SCHEMA = object_schema(
    decisions=array(
        object_schema(
            before_id=TEXT,
            assessment={
                "type": "string",
                "enum": ["absent", "counterpart_found", "uncertain"],
            },
            evidence_ids=array(TEXT),
            explanation=TEXT,
        )
    )
)
ABSENCE_PROMPT = (
    prompts.BASE
    + """Challenge proposed missing duties using the ORIGINAL
after-document text, independently of extracted function lists. For each before_id,
search this entire supplied source partition for the duty or its missing aspects
(for partial proposals, examine only uncovered_aspects). Transfers, paraphrases and
split duties can refute loss. Return counterpart_found with actual after source ids
when relevant responsibility exists, uncertain when scope is ambiguous, absent when
this partition contains no counterpart. A generic other-tasks clause is not enough.
Do not fabricate an absence quote. This is a countercheck, not a new function extractor.
"""
)


def comparable(function):
    return function["modality"] in ("obligation", "permission")


def function_record(function, registry):
    return {
        **function,
        "evidence": registry.evidence(
            unique(function["source_span_ids"] + function["context_span_ids"])
        ),
    }


def names(unit):
    return {normalize(x) for x in [unit["name"]] + unit["aliases"]}


def actor_matches(before, after, units):
    before_id = before["role_id"] or before["unit_id"]
    after_id = after["role_id"] or after["unit_id"]
    return bool(
        before_id
        and after_id
        and units[before_id]["kind"] == units[after_id]["kind"]
        and names(units[before_id]) & names(units[after_id])
    )


def exact_key(function, registry):
    # Compare complete clause text, not its number. Context-sensitive facets must
    # agree too. Atomic functions sharing a clause retain separate action/objects.
    texts = [
        re.sub(
            r"^\s*(?:\d+(?:\.\d+)*\.?|[а-яәіңғүұқөһ]\.)\s*",
            "",
            registry.spans[s]["raw_text"],
        )
        for s in function["source_span_ids"]
    ]
    facets = [
        normalize(str(function[k] or ""))
        for k in (
            "action",
            "object",
            "scope",
            "modality",
            "frequency",
            "deliverable",
            "recipient",
        )
    ]
    return tuple(
        facets
        + [
            "|".join(sorted(normalize(c) for c in function["conditions"])),
            "|".join(sorted(normalize(t).rstrip(".;: ") for t in texts)),
        ]
    )


def unchanged_source_key(function, registry):
    """Identical singleton clauses with identical context need no semantic call.

    This tolerates variation in the model's paraphrased action label. Multi-atom
    clauses are excluded by the caller, so their different duties cannot collapse.
    """

    def texts(ids):
        return tuple(
            sorted(
                normalize(
                    re.sub(
                        r"^\s*\d+(?:\.\d+)*\.?\s*", "", registry.spans[s]["raw_text"]
                    )
                )
                for s in ids
            )
        )

    contexts = unique(
        function["context_span_ids"] + registry.context_ids(function["source_span_ids"])
    )
    return texts(function["source_span_ids"]), texts(contexts), function["modality"]


def _decisions(response, requested, after_ids):
    values = response["decisions"]
    if len(values) != len(requested) or {v["before_id"] for v in values} != set(
        requested
    ):
        raise AnalysisError(
            "MATCH_COVERAGE_INVALID", "AI әр бұрынғы функция үшін бір шешім берген жоқ."
        )
    for value in values:
        if not set(value["after_ids"]).issubset(after_ids) or len(
            value["after_ids"]
        ) != len(set(value["after_ids"])):
            raise AnalysisError(
                "MATCH_REFERENCE_INVALID",
                "AI салыстыруында жарамсыз функция сілтемесі бар.",
            )
        if value["coverage"] in ("full", "partial") and not value["after_ids"]:
            raise AnalysisError(
                "MATCH_EVIDENCE_MISSING", "Қамтылған функция үшін кейінгі дәлел жоқ."
            )
        if value["coverage"] == "none" and value["after_ids"]:
            raise AnalysisError(
                "MATCH_INCONSISTENT", "Табылмаған функцияға кейінгі сәйкестік берілген."
            )
        if value["coverage"] == "partial" and not value["uncovered_aspects"]:
            raise AnalysisError(
                "MATCH_ASPECT_MISSING",
                "Ішінара қамтылмаған міндет бөлігі көрсетілмеген.",
            )
    return values


async def compare_functions(
    functions, units, registry, provider, settings, complete, emit, vectors=None
):
    before = [f for f in functions if f["version"] == "before" and comparable(f)]
    after = [f for f in functions if f["version"] == "after" and comparable(f)]
    unit_map, after_map = {u["id"]: u for u in units}, {f["id"]: f for f in after}
    mappings, warnings = [], []
    exact_after, raw_before, raw_after = {}, {}, {}
    for function in before:
        raw_before.setdefault(unchanged_source_key(function, registry), []).append(
            function
        )
    for function in after:
        exact_after.setdefault(exact_key(function, registry), []).append(function)
        raw_after.setdefault(unchanged_source_key(function, registry), []).append(
            function
        )
    remaining = []
    for old in before:
        matches = exact_after.get(exact_key(old, registry), [])
        raw_key = unchanged_source_key(old, registry)
        if (
            len(matches) != 1
            and len(raw_before.get(raw_key, [])) == 1
            and len(raw_after.get(raw_key, [])) == 1
        ):
            matches = raw_after[raw_key]
        if len(matches) != 1:
            remaining.append(old)
            continue
        new = matches[0]
        flags = []
        if (
            not actor_matches(old, new, unit_map)
            and (old["unit_id"] or old["role_id"])
            and (new["unit_id"] or new["role_id"])
        ):
            flags.append("transferred")
        mappings.append(
            {
                "id": stable_id("map", old["id"], [new["id"]]),
                "before_function_ids": [old["id"]],
                "after_function_ids": [new["id"]],
                "coverage_status": "full",
                "change_flags": flags,
                "uncovered_aspects": [],
                "explanation": "Бастапқы міндет мәтіні және оның салыстырылған контексті не шығарылған шарт, мерзім мен өкілеттік өлшемдері сақталған."
                + (" Жауаптысы өзгерген." if flags else ""),
                "source_span_ids": unique(
                    old["source_span_ids"] + new["source_span_ids"]
                ),
                "context_evidence_ids": unique(
                    old["context_span_ids"] + new["context_span_ids"]
                ),
            }
        )
    # Small batches keep source-rich verification bounded, while after partitions
    # cover the entire registry rather than a top-k retrieval subset.
    batches = [remaining[i : i + 6] for i in range(0, len(remaining), 6)]
    finished = 0

    async def compare_batch(batch):
        nonlocal finished
        batch_mappings, batch_warnings = [], []
        proposals = {f["id"]: [] for f in batch}
        search_ok = True
        ordered_after = list(after)
        if vectors:

            def score(candidate):
                v = vectors.get(candidate["id"])
                if v is None:
                    return 0
                return max(
                    (
                        sum(x * y for x, y in zip(v, vectors[f["id"]]))
                        for f in batch
                        if f["id"] in vectors
                    ),
                    default=0,
                )

            ordered_after.sort(key=score, reverse=True)
        after_parts = list(
            pack_chunks(
                ordered_after,
                settings.comparison_chars,
                lambda f: function_record(f, registry),
            )
        )
        if not after_parts:
            after_parts = [[]]
        for partition in after_parts:
            try:
                response = await provider.structured(
                    "match_functions",
                    prompts.MATCH,
                    {
                        "before": [function_record(f, registry) for f in batch],
                        "after": [function_record(f, registry) for f in partition],
                        "units": units,
                    },
                    MATCH_SCHEMA,
                )
                decisions = _decisions(
                    response, proposals, {f["id"] for f in partition}
                )
                for d in decisions:
                    proposals[d["before_id"]].append(d)
            except AnalysisError as exc:
                if exc.code in ("PROVIDER_AUTH", "PROVIDER_REQUEST_REJECTED"):
                    raise
                search_ok = False
                batch_warnings.append(diagnostic(exc.code, exc.message))
        candidates = unique(
            [
                aid
                for group in proposals.values()
                for d in group
                for aid in d["after_ids"]
            ]
        )
        initial = []
        for old in batch:
            ds = proposals[old["id"]]
            ids = unique([aid for d in ds for aid in d["after_ids"]])
            if ids:
                # The verification pass below resolves joint/partial coverage.
                best = next((d for d in ds if d["coverage"] == "full"), ds[0])
                initial.append({**best, "before_id": old["id"], "after_ids": ids})
            else:
                unknown = (
                    not search_ok
                    or not complete["after"]
                    or any(d["coverage"] == "unknown" for d in ds)
                )
                initial.append(
                    {
                        "before_id": old["id"],
                        "after_ids": [],
                        "coverage": "unknown" if unknown else "none",
                        "change_flags": [],
                        "uncovered_aspects": [],
                        "explanation": "Кейінгі жүктелген функциялар жиынында сәйкестік анықталмады."
                        if not unknown
                        else "Сәйкестікті анықтауға дерек немесе тексеру жеткіліксіз.",
                    }
                )
        verified = initial
        # Include all source-rich positive/uncertain candidates; only a complete
        # earlier partition scan may establish absence.
        if candidates:
            try:
                response = await provider.structured(
                    "verify_matches",
                    prompts.VERIFY_MATCH,
                    {
                        "before": [function_record(f, registry) for f in batch],
                        "after": [
                            function_record(after_map[i], registry) for i in candidates
                        ],
                        "units": units,
                        "proposed": initial,
                        "partition_search_complete": search_ok and complete["after"],
                    },
                    MATCH_SCHEMA,
                )
                verified = _decisions(response, proposals, set(candidates))
            except AnalysisError as exc:
                if exc.code in ("PROVIDER_AUTH", "PROVIDER_REQUEST_REJECTED"):
                    raise
                batch_warnings.append(diagnostic(exc.code, exc.message))
                search_ok = False
                verified = [
                    {
                        **d,
                        "coverage": "unknown",
                        "explanation": "Сәйкестіктің дәлелін қайта тексеру аяқталмады.",
                    }
                    for d in initial
                ]
        # Absence is costly to establish. Challenge it against raw after text too,
        # so a duty omitted by entity extraction cannot silently become a loss.
        missing = [d for d in verified if d["coverage"] in ("none", "partial")]
        if missing and search_ok and complete["after"]:
            challenged, ws = await challenge_absence(
                missing, batch, registry, provider, settings
            )
            batch_warnings.extend(ws)
            verified = [
                {
                    **d,
                    "coverage": "unknown",
                    "explanation": "Бастапқы кейінгі мәтінді қайта тексеру ықтимал сәйкестікті немесе белгісіздікті көрсетті; жоғалу расталмады.",
                }
                if d["before_id"] in challenged
                else d
                for d in verified
            ]
        for old in batch:
            decision = next(d for d in verified if d["before_id"] == old["id"])
            coverage = decision["coverage"]
            if coverage in ("none", "partial") and (
                not search_ok or not complete["after"]
            ):
                coverage = "unknown"
            new = [after_map[x] for x in decision["after_ids"]]
            flags = list(decision["change_flags"])
            if (
                new
                and all(not actor_matches(old, n, unit_map) for n in new)
                and (old["unit_id"] or old["role_id"])
                and all(n["unit_id"] or n["role_id"] for n in new)
            ):
                flags.append("transferred")
            # Multiple counterparts may be duplicate duties. Only the semantic
            # verifier can establish an actual split, never the edge count alone.
            evidence = unique(
                old["source_span_ids"] + [s for n in new for s in n["source_span_ids"]]
            )
            contexts = unique(
                old["context_span_ids"]
                + [s for n in new for s in n["context_span_ids"]]
            )
            batch_mappings.append(
                {
                    "id": stable_id("map", old["id"], decision["after_ids"]),
                    "before_function_ids": [old["id"]],
                    "after_function_ids": decision["after_ids"],
                    "coverage_status": coverage,
                    "change_flags": unique(flags),
                    "uncovered_aspects": decision["uncovered_aspects"]
                    if coverage == "partial"
                    else [],
                    "explanation": decision["explanation"],
                    "source_span_ids": evidence,
                    "context_evidence_ids": contexts,
                }
            )
        finished += 1
        await emit(
            "matching",
            finished,
            len(batches),
            "Бұрынғы функциялар кейінгі барлық бөлімшелермен салыстырылуда.",
        )
        return batch_mappings, batch_warnings

    for i in range(0, len(batches), settings.concurrency):
        outputs = await asyncio.gather(
            *(compare_batch(batch) for batch in batches[i : i + settings.concurrency])
        )
        for batch_mappings, batch_warnings in outputs:
            mappings.extend(batch_mappings)
            warnings.extend(batch_warnings)
    # Two distinct old atoms covered by one new atom establish a merge;
    # repeated identical clauses alone do not.
    reuse = {}
    for mapping in mappings:
        for aid in mapping["after_function_ids"]:
            reuse.setdefault(aid, []).append(mapping)
    for group in reuse.values():
        old_lookup = {f["id"]: f for f in before}
        identities = {
            exact_key(old_lookup[b], registry)
            for m in group
            for b in m["before_function_ids"]
        }
        if len(group) > 1 and len(identities) > 1:
            for mapping in group:
                mapping["change_flags"] = unique(mapping["change_flags"] + ["merged"])
    return mappings, warnings


async def challenge_absence(proposals, before, registry, provider, settings):
    requested = {d["before_id"] for d in proposals}
    uncertain, warnings = set(), []
    raw = [
        s["id"]
        for s in registry.spans.values()
        if registry.version(s["id"]) == "after"
        and s["is_content"]
        and s["raw_text"].strip()
    ]
    for part in pack_chunks(
        raw, settings.comparison_chars, lambda sid: registry.evidence([sid])
    ):
        sources = registry.evidence(part)
        allowed = {s["id"] for s in sources}
        try:
            response = await provider.structured(
                "audit_absence",
                ABSENCE_PROMPT,
                {
                    "before": [
                        function_record(f, registry)
                        for f in before
                        if f["id"] in requested
                    ],
                    "proposed": proposals,
                    "after_sources": sources,
                },
                ABSENCE_SCHEMA,
            )
            decisions = response["decisions"]
            if (
                len(decisions) != len(requested)
                or {d["before_id"] for d in decisions} != requested
            ):
                raise AnalysisError(
                    "ABSENCE_AUDIT_INCOMPLETE",
                    "Жоғалуды қайта тексеру толық аяқталмады.",
                )
            for d in decisions:
                registry.ids(
                    d["evidence_ids"],
                    "after",
                    nonempty=d["assessment"] == "counterpart_found",
                )
                if not set(d["evidence_ids"]).issubset(allowed):
                    raise AnalysisError(
                        "ABSENCE_EVIDENCE_INVALID",
                        "Қайта тексеруде жарамсыз дәлел қолданылған.",
                    )
                if d["assessment"] != "absent":
                    uncertain.add(d["before_id"])
                    warnings.append(
                        diagnostic(
                            "LOSS_COUNTERCHECK_UNCERTAIN",
                            "Бастапқы мәтіндегі ықтимал сәйкестікке байланысты жоғалу туралы қорытынды тоқтатылды.",
                            span_ids=d["evidence_ids"],
                        )
                    )
        except AnalysisError as exc:
            if exc.code in ("PROVIDER_AUTH", "PROVIDER_REQUEST_REJECTED"):
                raise
            uncertain.update(requested)
            warnings.append(diagnostic(exc.code, exc.message))
    return uncertain, warnings


async def compare_units(units, registry, provider, settings):
    all_units = {u["id"]: u for u in units}
    structural = [u for u in units if u["kind"] in ("organization", "department")]
    before = [u for u in structural if u["version"] == "before"]
    after = [u for u in structural if u["version"] == "after"]
    lookup = {u["id"]: u for u in structural}
    changes, warnings, consumed_before, consumed_after = [], [], set(), set()
    # Search explicit reorganization language across every supplied source. No
    # prescribed department names or clause numbers appear in production logic.
    keywords = (
        "переимен",
        "реорганиз",
        "объедин",
        "раздел",
        "присоедин",
        "қайта ата",
        "қайта ұйымдастыр",
        "біріктір",
        "бөлу",
    )
    evidence = [
        s["id"]
        for s in registry.spans.values()
        if s["is_content"] and any(k in normalize(s["raw_text"]) for k in keywords)
    ]
    if before and after and evidence:
        for part in pack_chunks(
            evidence, settings.comparison_chars, lambda sid: registry.evidence([sid])
        ):
            try:
                request = {
                    "before_units": before,
                    "after_units": after,
                    "sources": registry.evidence(part),
                }
                response = await provider.structured(
                    "compare_organization", prompts.ORG, request, ORG_SCHEMA
                )
                if response["events"]:
                    response = await provider.structured(
                        "verify_organization",
                        prompts.ORG
                        + "\nIndependently challenge proposed formal events using the actual wording. Remove any event not explicitly supported; a name disappearing or similar duties alone is insufficient.",
                        {**request, "proposed": response["events"]},
                        ORG_SCHEMA,
                    )
                allowed = {x["id"] for x in registry.evidence(part)}
                for event in response["events"]:
                    b, a = event["before_unit_ids"], event["after_unit_ids"]
                    if (
                        not b
                        or not a
                        or not all(
                            x in lookup and lookup[x]["version"] == "before" for x in b
                        )
                        or not all(
                            x in lookup and lookup[x]["version"] == "after" for x in a
                        )
                    ):
                        raise AnalysisError(
                            "ORG_REFERENCE_INVALID",
                            "Қайта ұйымдастыру байланысының нұсқасы жарамсыз.",
                        )
                    registry.ids(event["source_span_ids"], nonempty=True)
                    if not set(event["source_span_ids"]).issubset(allowed):
                        raise AnalysisError(
                            "ORG_EVIDENCE_INVALID",
                            "Қайта ұйымдастыруға берілмеген дерек қолданылған.",
                        )
                    changes.append(
                        {
                            "id": stable_id("uc", b, a, event["change_type"]),
                            **event,
                            "basis": "explicit_document",
                        }
                    )
                    consumed_before.update(b)
                    consumed_after.update(a)
            except AnalysisError as exc:
                if exc.code in ("PROVIDER_AUTH", "PROVIDER_REQUEST_REJECTED"):
                    raise
                warnings.append(diagnostic(exc.code, exc.message))
    for old in before:
        if old["id"] in consumed_before:
            continue
        matches = [
            u
            for u in after
            if u["id"] not in consumed_after
            and old["kind"] == u["kind"]
            and names(old) & names(u)
        ]
        if len(matches) == 1:
            new = matches[0]
            consumed_before.add(old["id"])
            consumed_after.add(new["id"])
            ev = unique(old["source_span_ids"] + new["source_span_ids"])
            changes.append(
                {
                    "id": stable_id("uc", old["id"], new["id"]),
                    "before_unit_ids": [old["id"]],
                    "after_unit_ids": [new["id"]],
                    "change_type": "preserved",
                    "basis": "explicit_document",
                    "explanation": "Бөлімше екі жүктелген нұсқада да көрсетілген.",
                    "source_span_ids": ev,
                }
            )
            bp, ap = old["parent_id"], new["parent_id"]
            if bp and ap and not names(all_units[bp]) & names(all_units[ap]):
                changes.append(
                    {
                        "id": stable_id("hier", old["id"], new["id"]),
                        "before_unit_ids": [old["id"]],
                        "after_unit_ids": [new["id"]],
                        "change_type": "reporting_changed",
                        "basis": "explicit_document",
                        "explanation": "Бөлімшенің құжатта көрсетілген бағыныштылығы өзгерген.",
                        "source_span_ids": unique(
                            ev
                            + all_units[bp]["source_span_ids"]
                            + all_units[ap]["source_span_ids"]
                        ),
                    }
                )
        else:
            consumed_after.update(x["id"] for x in matches)
            changes.append(
                {
                    "id": stable_id("uc", old["id"], "unmatched"),
                    "before_unit_ids": [old["id"]],
                    "after_unit_ids": [x["id"] for x in matches],
                    "change_type": "uncertain"
                    if matches or not registry.complete("after")
                    else "removed",
                    "basis": "insufficient_data",
                    "explanation": "Кейінгі жүктелген құрылымда бірмәнді сәйкестік табылмады; заңды таратылу оқиғасы расталмаған.",
                    "source_span_ids": old["source_span_ids"],
                }
            )
    for new in after:
        if new["id"] not in consumed_after:
            changes.append(
                {
                    "id": stable_id("uc", new["id"], "new"),
                    "before_unit_ids": [],
                    "after_unit_ids": [new["id"]],
                    "change_type": "created"
                    if registry.complete("before")
                    else "uncertain",
                    "basis": "insufficient_data",
                    "explanation": "Кейінгі жүктелген құрылымда жаңадан көрсетілген; заңды құрылу күні туралы қорытынды жасалмайды.",
                    "source_span_ids": new["source_span_ids"],
                }
            )
    return list({c["id"]: c for c in changes}.values()), warnings
