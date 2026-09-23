"""Cross-unit duplication, incompatible duties, counterevidence and risk changes."""

from itertools import combinations, product
import re

from . import prompts
from .errors import AnalysisError
from .matching import comparable, function_record
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

    def record(pair):
        return {
            "id": pair["id"],
            "left": function_record(pair["left"], registry),
            "right": function_record(pair["right"], registry),
        }

    parts = list(pack_chunks(pairs, settings.comparison_chars, record))
    for n, part in enumerate(parts):
        pair_map = {p["id"]: p for p in part}
        source_ids = unique(
            constraints
            + [
                s
                for p in part
                for f in (p["left"], p["right"])
                for s in f["source_span_ids"] + f["context_span_ids"]
            ]
        )
        request = {
            "version": version,
            "pairs": [record(p) for p in part],
            "units": units,
            "constraints": registry.evidence(constraints),
        }
        allowed = {s["id"] for s in registry.evidence(source_ids)}
        try:
            response = await provider.structured(
                "detect_risks", prompts.RISKS, request, PAIR_SCHEMA
            )
            decisions = response["decisions"]
            validate_pair_decisions(decisions, pair_map, registry, allowed, version)
            positives = [d for d in decisions if d["type"] in ("duplicate", "conflict")]
            if positives:
                selected = {d["pair_id"] for d in positives}
                audit_request = {
                    **request,
                    "pairs": [record(p) for p in part if p["id"] in selected],
                    "proposed": positives,
                }
                audit = await provider.structured(
                    "verify_risks",
                    prompts.RISKS
                    + "\nIndependently challenge each proposed risk. Find safeguards, different scopes, or reporting hierarchy that refute it. Correct false positives to none/uncertain.",
                    audit_request,
                    PAIR_SCHEMA,
                )
                audit_map = {k: v for k, v in pair_map.items() if k in selected}
                validate_pair_decisions(
                    audit["decisions"], audit_map, registry, allowed, version
                )
                corrected = {d["pair_id"]: d for d in audit["decisions"]}
                decisions = [corrected.get(d["pair_id"], d) for d in decisions]
            observed.update(
                {
                    d["pair_id"]: {
                        **d,
                        "functions": [
                            pair_map[d["pair_id"]]["left"]["id"],
                            pair_map[d["pair_id"]]["right"]["id"],
                        ],
                    }
                    for d in decisions
                }
            )
        except AnalysisError as exc:
            if exc.code in ("PROVIDER_AUTH", "PROVIDER_REQUEST_REJECTED"):
                raise
            complete = False
            warnings.append(diagnostic(exc.code, exc.message))
        await emit(
            "verifying",
            n + 1,
            len(parts),
            f"{version}: ықтимал қайталану мен қақтығыстың дәлелдері тексерілуде.",
        )
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
        "affected_units": unique([u for u in affected if u]),
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
    old_pairs = candidate_pairs(old_fs, vectors)
    old, old_ok, warnings = await evaluate_pairs(
        old_pairs, units, registry, provider, settings, "before", emit
    )
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
    new_pairs = candidate_pairs(new_fs, vectors, forced)
    new, new_ok, ws = await evaluate_pairs(
        new_pairs, units, registry, provider, settings, "after", emit
    )
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
