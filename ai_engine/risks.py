"""Cross-unit duplication, incompatible duties, counterevidence and risk changes."""

import asyncio
from itertools import combinations, product
import re

from . import prompts
from .errors import AnalysisError
from .matching import comparable
from .schema import object_schema, array
from .sources import diagnostic, normalize, pack_chunks, stable_id, unique

STR = {"type": "string"}
PAIR_SCHEMA = object_schema(
    decisions=array(
        object_schema(
            pair_id=STR,
            type={
                "type": "string",
                "enum": ["duplicate", "conflict", "none", "uncertain"],
            },
            explanation=STR,
            severity={"type": "string", "enum": ["low", "medium", "high"]},
            evidence_ids=array(STR),
            counterevidence_ids=array(STR),
        )
    )
)


def terms(text):
    return {w[:7] for w in re.findall(r"[^\W\d_]{3,}", normalize(text), re.UNICODE)}


def similarity(a, b):
    a, b = terms(a), terms(b)
    return len(a & b) / max(1, min(len(a), len(b)))


def candidate_pairs(functions, vectors=None, forced=()):
    """Inspect every pair lexically; embeddings improve candidate recall.

    This generates hypotheses only. No risk is declared by a similarity threshold.
    Forced pairs retest former risks even if lexical ranking would exclude them.
    """
    fs = {f["id"]: f for f in functions if comparable(f)}
    pairs = {
        tuple(sorted(x))
        for x in forced
        if len(x) == 2 and x[0] != x[1] and all(i in fs for i in x)
    }
    for left, right in combinations(fs.values(), 2):
        same_actor = (left["role_id"] or left["unit_id"]) == (
            right["role_id"] or right["unit_id"]
        )
        if same_actor and normalize(left["action"]) == normalize(right["action"]):
            # Repetition of the same action by the same actor is not cross-actor
            # duplication; different execution/control actions remain candidates.
            continue
        score = similarity(left["object"], right["object"])
        if not score:
            score = (
                similarity(
                    left["action"] + " " + left["object"],
                    right["action"] + " " + right["object"],
                )
                * 0.5
            )
        if vectors and left["id"] in vectors and right["id"] in vectors:
            cos = sum(a * b for a, b in zip(vectors[left["id"]], vectors[right["id"]]))
            if cos >= 0.72:
                score = max(score, 0.3)
        if score >= 0.25:
            pairs.add(tuple(sorted((left["id"], right["id"]))))
    return [
        {"id": stable_id("pair", *p), "left": fs[p[0]], "right": fs[p[1]]}
        for p in sorted(pairs)
    ]


def constraint_sources(registry, version):
    needles = (
        "независим",
        "объективн",
        "конфликт",
        "не имеют права",
        "не вправе",
        "запрещ",
        "тәуелсіз",
        "тыйым",
        "мүдделер",
    )
    return [
        s["id"]
        for s in registry.spans.values()
        if registry.version(s["id"]) == version
        and s["is_content"]
        and any(n in normalize(s["raw_text"]) for n in needles)
    ]


async def evaluate_pairs(pairs, units, registry, provider, settings, version, emit):
    warnings, observed, complete = [], {}, True
    constraints = constraint_sources(registry, version)
    actors = {u["id"]: u for u in units if u["version"] == version}

    def lineage(function):
        actor = function["role_id"] or function["unit_id"]
        chain = []
        while actor in actors and actor not in chain:
            chain.append(actor)
            actor = actors[actor]["parent_id"]
        return chain

    def record(pair):
        left, right = lineage(pair["left"]), lineage(pair["right"])
        relationship = "not_established"
        if left and right:
            if left[0] == right[0]:
                relationship = "same_actor"
            elif left[0] in right[1:] or right[0] in left[1:]:
                relationship = "ancestor_descendant"
        return {
            "id": pair["id"],
            "left": pair["left"],
            "right": pair["right"],
            "actor_relationship": relationship,
        }

    # Source paragraphs are shared across many pairs. Send each once per request
    # instead of repeating the entire ancestor chain inside every function.
    parts = [
        part[i : i + 24]
        for part in pack_chunks(pairs, settings.comparison_chars, record)
        for i in range(0, len(part), 24)
    ]
    finished = 0

    async def inspect_part(part):
        nonlocal finished
        pair_map = {p["id"]: p for p in part}
        source_ids = unique(
            constraints
            + [
                s
                for p in part
                for f in (p["left"], p["right"])
                for s in f["source_span_ids"] + f["context_span_ids"]
            ]
            + [
                sid
                for p in part
                for f in (p["left"], p["right"])
                for uid in lineage(f)
                for sid in actors[uid]["source_span_ids"]
            ]
        )
        request = {
            "version": version,
            "pairs": [record(p) for p in part],
            "units": [u for u in units if u["version"] == version],
            "sources": registry.evidence(source_ids),
            "constraints": registry.evidence(constraints),
        }
        allowed = {s["id"] for s in registry.evidence(source_ids)}
        batch_warnings = []
        decisions = []
        ok = True
        try:
            response = await provider.structured(
                "detect_risks", prompts.RISKS, request, PAIR_SCHEMA
            )
            decisions = response["decisions"]
            validate_pair_decisions(decisions, pair_map, registry, allowed, version)
            challenged = [
                d
                for d in decisions
                if d["type"] in ("duplicate", "conflict")
                or all(
                    normalize(pair_map[d["pair_id"]]["left"][field] or "")
                    == normalize(pair_map[d["pair_id"]]["right"][field] or "")
                    for field in ("action", "object")
                )
            ]
            if challenged:
                selected = {d["pair_id"] for d in challenged}
                audit_request = {
                    **request,
                    "pairs": [record(p) for p in part if p["id"] in selected],
                    "proposed": challenged,
                }
                audit = await provider.structured(
                    "verify_risks",
                    prompts.RISKS
                    + "\nIndependently verify each proposed decision, including negative decisions. Find actual safeguards, different scopes or reporting hierarchy that refute a risk. Also correct a missed overlap when the same duty is assigned to distinct actors without a documented distinction. Do not invent safeguards or assume department names mean different objects. Return the evidence-supported decision, which may differ from proposed.",
                    audit_request,
                    PAIR_SCHEMA,
                )
                audit_map = {k: v for k, v in pair_map.items() if k in selected}
                validate_pair_decisions(
                    audit["decisions"], audit_map, registry, allowed, version
                )
                corrected = {d["pair_id"]: d for d in audit["decisions"]}
                decisions = [corrected.get(d["pair_id"], d) for d in decisions]
        except AnalysisError as exc:
            if exc.code in ("PROVIDER_AUTH", "PROVIDER_REQUEST_REJECTED"):
                raise
            ok = False
            decisions = []
            batch_warnings.append(diagnostic(exc.code, exc.message))
        finished += 1
        await emit(
            "verifying",
            finished,
            len(parts),
            f"{version}: ықтимал қайталану мен қақтығыстың дәлелдері тексерілуде.",
        )
        return (
            {
                d["pair_id"]: {
                    **d,
                    "functions": [
                        pair_map[d["pair_id"]]["left"]["id"],
                        pair_map[d["pair_id"]]["right"]["id"],
                    ],
                }
                for d in decisions
            },
            ok,
            batch_warnings,
        )

    for i in range(0, len(parts), settings.concurrency):
        batches = await asyncio.gather(
            *(inspect_part(part) for part in parts[i : i + settings.concurrency])
        )
        for decisions, ok, ws in batches:
            observed.update(decisions)
            complete = complete and ok
            warnings.extend(ws)
    return observed, complete, warnings


def validate_pair_decisions(decisions, pairs, registry, allowed, version):
    if len(decisions) != len(pairs) or {d["pair_id"] for d in decisions} != set(pairs):
        raise AnalysisError(
            "RISK_COVERAGE_INVALID", "AI әр салыстыру жұбы бойынша шешім берген жоқ."
        )
    for decision in decisions:
        evidence = registry.ids(decision["evidence_ids"], version)
        counter = registry.ids(decision["counterevidence_ids"], version)
        if not set(evidence + counter).issubset(allowed):
            raise AnalysisError(
                "RISK_SOURCE_INVALID", "Тәуекелге сұрауда берілмеген дерек қосылған."
            )
        if decision["type"] in ("duplicate", "conflict"):
            pair = pairs[decision["pair_id"]]
            for side in ("left", "right"):
                if not set(pair[side]["source_span_ids"]).intersection(evidence):
                    raise AnalysisError(
                        "RISK_EVIDENCE_MISSING",
                        "Тәуекел екі міндеттің де дәлелімен расталмаған.",
                    )
            if decision["type"] == "conflict" and not set(
                constraint_sources(registry, version)
            ).intersection(evidence):
                raise AnalysisError(
                    "CONFLICT_RULE_MISSING",
                    "Қақтығысқа қолданылатын берілген шектеу көрсетілмеген.",
                )


def finding(
    kind,
    title,
    explanation,
    evidence,
    contexts,
    affected,
    revision,
    *,
    risk_change="unknown",
    severity="medium",
    counter=(),
    search_docs=(),
    search_complete=False,
    verified=True,
):
    affected = unique([actor for actor in affected if actor])
    action = {
        "potential_loss": "Міндеттің кейінгі жауаптысын тексеріп, жетіспейтін бекітуді нақтылау.",
        "ownership_gap": "Осы функцияның жауапты бөлімшесін және өкілеттігін құжатта нақтылау.",
        "potential_duplicate": "Екі жауаптының міндет объектісі мен шекарасын нақтылап, қажет болса жетекші және қатысушы рөлдерін ажырату.",
        "potential_conflict": "Орындау және тәуелсіз бақылау рөлдерін, сондай-ақ қолданылатын қорғаныс шараларын жауапты қызметкермен тексеру.",
        "document_quality": "Мәтіннің түпнұсқасын немесе жетіспейтін қосымшаны толықтыру.",
    }[kind]
    return {
        "id": stable_id(
            "finding", kind, sorted(evidence), sorted(affected), risk_change
        ),
        "analysis_revision": revision,
        "type": kind,
        "risk_change": risk_change,
        "title": title,
        "explanation": explanation,
        "severity": severity,
        "evidence_ids": unique(evidence),
        "context_evidence_ids": unique(contexts),
        "counterevidence_ids": unique(counter),
        "affected_units": affected,
        "recommended_action": {
            "action": action,
            "target_role_id": None,
            "required_document": "Функциялар мен жауапкершіліктерді бекітетін толық кейінгі құжаттар"
            if kind in ("potential_loss", "ownership_gap")
            else None,
            "reason": explanation,
        },
        "verification_status": "validated" if verified else "needs_review",
        "review_status": "unreviewed",
        "search_scope_document_ids": list(search_docs),
        "search_complete": search_complete,
    }


async def detect_risks(
    functions,
    units,
    mappings,
    registry,
    provider,
    settings,
    complete,
    emit,
    vectors=None,
):
    by_id = {f["id"]: f for f in functions}
    old_fs = [f for f in functions if f["version"] == "before"]
    new_fs = [f for f in functions if f["version"] == "after"]
    warnings = []

    def bounded(pairs, version):
        if len(pairs) <= settings.max_risk_pairs:
            return pairs, True
        total = len(pairs)
        ranked = sorted(
            pairs,
            key=lambda p: (
                -similarity(p["left"]["object"], p["right"]["object"]),
                -similarity(p["left"]["action"], p["right"]["action"]),
                p["id"],
            ),
        )
        warnings.append(
            diagnostic(
                "RISK_SEARCH_LIMIT",
                f"{version}: {total} кандидат жұптың ең ұқсас {settings.max_risk_pairs} жұбы тексеруге таңдалды. Қалғандары тексерілмеді; тәуекелді іздеу толық емес.",
            )
        )
        return ranked[: settings.max_risk_pairs], False

    # Spend the bounded model budget on the changed organization first. Historic
    # risk classification is useful, but must not starve the current risk search.
    new_pairs, new_scope_ok = bounded(candidate_pairs(new_fs, vectors), "after")
    new, new_ok, ws = await evaluate_pairs(
        new_pairs, units, registry, provider, settings, "after", emit
    )
    warnings.extend(ws)
    new_ok = new_ok and new_scope_ok
    old_pairs, old_scope_ok = bounded(candidate_pairs(old_fs, vectors), "before")
    old, old_ok, ws = await evaluate_pairs(
        old_pairs, units, registry, provider, settings, "before", emit
    )
    warnings.extend(ws)
    old_ok = old_ok and old_scope_ok
    links = {b: m for m in mappings for b in m["before_function_ids"]}
    forced = []
    for d in old.values():
        if d["type"] in ("duplicate", "conflict"):
            left, right = d["functions"]
            forced.extend(
                product(
                    links.get(left, {}).get("after_function_ids", []),
                    links.get(right, {}).get("after_function_ids", []),
                )
            )
    seen = {p["id"] for p in new_pairs}
    forced_set = {tuple(sorted(p)) for p in forced}
    extra = [
        p
        for p in candidate_pairs(new_fs, vectors, forced)
        if p["id"] not in seen
        and tuple(sorted((p["left"]["id"], p["right"]["id"]))) in forced_set
    ]
    if extra:
        extra, extra_scope_ok = bounded(extra, "after follow-up")
        followups, followups_ok, ws = await evaluate_pairs(
            extra, units, registry, provider, settings, "after", emit
        )
        new.update(followups)
        new_pairs.extend(extra)
        new_ok = new_ok and followups_ok and extra_scope_ok
        warnings.extend(ws)
    findings, persisted_old = [], set()
    revision = registry.payload["analysis_revision"]

    def mapped_pair(previous, current):
        a, b = previous["functions"]
        aa = set(links.get(a, {}).get("after_function_ids", []))
        bb = set(links.get(b, {}).get("after_function_ids", []))
        x, y = current["functions"]
        return (x in aa and y in bb) or (x in bb and y in aa)

    for current in new.values():
        if current["type"] not in ("duplicate", "conflict"):
            continue
        previous = next(
            (
                d
                for d in old.values()
                if d["type"] == current["type"] and mapped_pair(d, current)
            ),
            None,
        )
        change = (
            "persisting"
            if previous
            else ("new" if old_ok and complete["before"] else "unknown")
        )
        if previous:
            persisted_old.add(previous["pair_id"])
        fs = [by_id[x] for x in current["functions"]]
        evidence = current["evidence_ids"] + (
            previous["evidence_ids"] if previous else []
        )
        kind = (
            "potential_duplicate"
            if current["type"] == "duplicate"
            else "potential_conflict"
        )
        contexts = unique(
            [s for f in fs for s in f["context_span_ids"]]
            + registry.context_ids(evidence)
        )
        findings.append(
            finding(
                kind,
                "Функциялардың ықтимал қайталануы"
                if kind == "potential_duplicate"
                else "Рөлдердің ықтимал мүдделер қақтығысы",
                current["explanation"],
                evidence,
                contexts,
                [f["unit_id"] or f["role_id"] for f in fs],
                revision,
                risk_change=change,
                severity=current["severity"],
                counter=current["counterevidence_ids"],
            )
        )
    for previous in old.values():
        if (
            previous["type"] not in ("duplicate", "conflict")
            or previous["pair_id"] in persisted_old
        ):
            continue
        linked = [links.get(x) for x in previous["functions"]]
        followups = [d for d in new.values() if mapped_pair(previous, d)]
        resolved = (
            new_ok
            and complete["after"]
            and all(m and m["coverage_status"] == "full" for m in linked)
            and bool(followups)
            and all(d["type"] == "none" for d in followups)
        )
        # Unknown former risks remain inspectable; do not call them solved just
        # because an actor or document went missing.
        kind = (
            "potential_duplicate"
            if previous["type"] == "duplicate"
            else "potential_conflict"
        )
        fs = [by_id[x] for x in previous["functions"]]
        counter = unique(
            [
                sid
                for d in followups
                for sid in d["evidence_ids"] + d["counterevidence_ids"]
            ]
        )
        findings.append(
            finding(
                kind,
                "Бұрынғы тәуекел кейінгі нұсқада қайта тексерілді",
                previous["explanation"]
                + (
                    " Кейінгі тексерілген міндеттерде бұл жағдай енді анықталмады."
                    if resolved
                    else " Кейінгі нұсқадағы күйі бірмәнді анықталмады."
                ),
                previous["evidence_ids"],
                registry.context_ids(previous["evidence_ids"]),
                [f["unit_id"] or f["role_id"] for f in fs],
                revision,
                risk_change="no_longer_detected" if resolved else "unknown",
                severity=previous["severity"],
                counter=counter,
                search_docs=registry.doc_ids("after"),
                search_complete=resolved,
                verified=resolved,
            )
        )
    for mapping in mappings:
        if mapping["coverage_status"] not in ("none", "partial", "unknown"):
            continue
        oldf = by_id[mapping["before_function_ids"][0]]
        if mapping["coverage_status"] == "unknown":
            # This is explicitly an unresolved correspondence, not an alleged loss.
            continue
        findings.append(
            finding(
                "potential_loss",
                "Функция кейінгі жиында табылмады"
                if mapping["coverage_status"] == "none"
                else "Функция ішінара қамтылған",
                mapping["explanation"]
                + (
                    " Қамтылмаған бөлік: " + "; ".join(mapping["uncovered_aspects"])
                    if mapping["uncovered_aspects"]
                    else ""
                ),
                mapping["source_span_ids"],
                mapping["context_evidence_ids"],
                [oldf["unit_id"] or oldf["role_id"]],
                revision,
                risk_change="new",
                search_docs=registry.doc_ids("after"),
                search_complete=complete["after"],
                severity="medium",
            )
        )
    for func in new_fs:
        if comparable(func) and func["unit_id"] is None and func["role_id"] is None:
            findings.append(
                finding(
                    "ownership_gap",
                    "Функцияның жауаптысы анықталмаған",
                    "Берілген мәтінде осы функцияға жауапты бөлімше немесе лауазым бірмәнді анықталмады.",
                    func["source_span_ids"],
                    func["context_span_ids"],
                    [],
                    revision,
                    verified=False,
                )
            )
    warnings.append(
        diagnostic(
            "RISK_SEARCH_SCOPE",
            f"Мағыналық тексеруге бұрынғы {len(old_pairs)}, кейінгі {len(new_pairs)} функция жұбы жіберілді. Кандидат іріктеу барлық функция жұбының лексикалық ұқсастығын қарады; анықталмаған тәуекелдің жоқтығына кепіл берілмейді.",
        )
    )
    return list({f["id"]: f for f in findings}.values()), old_ok and new_ok, warnings
