"""Synthetic controls. Expected labels never enter the live engine request."""

from dataclasses import dataclass, field
import hashlib


@dataclass
class Case:
    name: str
    payload: dict
    facts: dict
    links: dict
    flags: dict = field(default_factory=dict)
    risks: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    expected: dict = field(default_factory=dict)
    coverages: dict = field(default_factory=dict)


def unit(name, key, parent=None, kind="department"):
    return {"name": name, "key": key, "parent": parent, "kind": kind}


def duty(
    key,
    owner,
    action,
    obj,
    text=None,
    *,
    scope=None,
    frequency=None,
    modality="obligation",
    conditions=(),
):
    return {
        "key": key,
        "owner": owner,
        "action": action,
        "object": obj,
        "text": text or f"{action}: {obj}.",
        "scope": scope,
        "frequency": frequency,
        "modality": modality,
        "conditions": list(conditions),
    }


def make_case(
    name,
    before_units,
    before_duties,
    after_units,
    after_duties,
    links,
    *,
    flags=None,
    risks=None,
    constraints=None,
    events=None,
    expected=None,
    coverages=None,
):
    docs, facts = [], {}
    for version, units, functions in (
        ("before", before_units, before_duties),
        ("after", after_units, after_duties),
    ):
        doc_id = version + "-document"
        spans, out_units, out_functions = [], [], []

        def span(sid, text, clause, context=()):
            return {
                "id": sid,
                "document_id": doc_id,
                "raw_text": text,
                "section_path": ["Ұйымдық ереже"],
                "context_span_ids": list(context),
                "locator": {
                    "kind": "docx",
                    "clause": clause,
                    "path": f"paragraph:{len(spans) + 1}",
                    "page": None,
                    "sheet": None,
                    "cell_range": None,
                },
                "is_content": True,
            }

        for u in units:
            sid = version + ":unit:" + u["key"]
            raw = "Бөлімше: " + u["name"]
            if u["parent"]:
                raw += "; бағынышты: " + next(
                    x["name"] for x in units if x["key"] == u["parent"]
                )
            spans.append(span(sid, raw, "1"))
            out_units.append(
                {
                    "id": u["key"],
                    "version": version,
                    "name": u["name"],
                    "aliases": [],
                    "kind": u["kind"],
                    "parent_id": u["parent"],
                    "source_span_ids": [sid],
                    "evidence_quotes": [{"span_id": sid, "quote": raw}],
                }
            )
        for f in functions:
            sid = version + ":fn:" + f["key"]
            context = [version + ":unit:" + f["owner"]] if f["owner"] else []
            raw = f["text"]
            owner_name = next(
                (u["name"] for u in units if u["key"] == f["owner"]), "Жауапты белгісіз"
            )
            rendered = owner_name + ": " + raw
            if f["scope"]:
                rendered += " Қолданылу аясы: " + f["scope"]
            if f["frequency"]:
                rendered += " Жиілігі: " + f["frequency"]
            if f["modality"] == "prohibition":
                rendered = owner_name + " үшін тыйым салынған әрекет: " + raw
            spans.append(span(sid, rendered, str(len(spans) + 1), context))
            out_functions.append(
                {
                    "id": f["key"],
                    "version": version,
                    "unit_id": f["owner"],
                    "role_id": None,
                    "action": f["action"],
                    "object": f["object"],
                    "scope": f["scope"],
                    "modality": f["modality"],
                    "conditions": f["conditions"],
                    "frequency": f["frequency"],
                    "deliverable": None,
                    "recipient": None,
                    "source_span_ids": [sid],
                    "context_span_ids": context,
                    "evidence_quotes": [{"span_id": sid, "quote": rendered}],
                }
            )
        for i, raw in enumerate((constraints or {}).get(version, [])):
            spans.append(span(f"{version}:rule:{i}", raw, "9"))
        raw_bytes = "\n".join(s["raw_text"] for s in spans).encode()
        docs.append(
            {
                "id": doc_id,
                "version": version,
                "filename": name + "-" + version + ".docx",
                "title": "Жасанды бақылау: " + name,
                "document_type": "regulation",
                "edition": None,
                "source_sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "parse_status": "complete",
                "span_count": len(spans),
                "warnings": [],
                "spans": spans,
            }
        )
        facts[doc_id] = {"units": out_units, "functions": out_functions}
    return Case(
        name,
        {
            "schema_version": "1.0.0",
            "analysis_id": "control-" + name,
            "analysis_revision": 1,
            "documents": docs,
        },
        facts,
        {"before:fn:" + k: ["after:fn:" + x for x in v] for k, v in links.items()},
        {"before:fn:" + k: v for k, v in (flags or {}).items()},
        risks or {},
        events or [],
        expected or {},
        {"before:fn:" + k: v for k, v in (coverages or {}).items()},
    )


def cases():
    a, b = unit("Есеп бөлімі", "a"), unit("Бақылау бөлімі", "b")
    archive = duty(
        "archive",
        "a",
        "мұрағаттау",
        "келісімшарттар",
        "Келісімшарттарды мұрағаттауға міндетті.",
    )
    report = duty(
        "report",
        "a",
        "дайындау",
        "қызмет есебі",
        "Қызмет есебін дайындауға міндетті.",
        frequency="ай сайын",
    )
    result = []
    result.append(
        make_case(
            "unchanged",
            [a],
            [archive],
            [a],
            [archive],
            {"archive": ["archive"]},
            expected={"none": 0, "full": 1, "loss": 0},
        )
    )
    result.append(
        make_case(
            "loss",
            [a],
            [archive, report],
            [a],
            [archive],
            {"archive": ["archive"], "report": []},
            expected={"none": 1, "full": 1, "loss": 1},
        )
    )
    moved = duty(
        "moved",
        "b",
        "мұрағаттау",
        "келісімшарттар",
        "Келісімшарттарды мұрағаттауға міндетті.",
    )
    result.append(
        make_case(
            "transfer",
            [a],
            [archive],
            [b],
            [moved],
            {"archive": ["moved"]},
            flags={"archive": ["transferred"]},
            expected={"none": 0, "full": 1, "loss": 0, "transferred": 1},
        )
    )
    changed = duty(
        "yearly",
        "a",
        "дайындау",
        "қызмет есебі",
        "Қызмет есебін дайындауға міндетті.",
        frequency="жыл сайын",
    )
    result.append(
        make_case(
            "frequency",
            [a],
            [report],
            [a],
            [changed],
            {"report": ["yearly"]},
            flags={"report": ["frequency_changed"]},
            coverages={"report": "partial"},
            expected={"full": 0, "partial": 1, "loss": 1, "frequency_changed": 1},
        )
    )
    combined = duty(
        "both",
        "a",
        "мұрағаттау",
        "келісімшарттар және шоттар",
        "Келісімшарттар мен шоттарды мұрағаттауға міндетті.",
    )
    invoices = duty(
        "invoices", "a", "мұрағаттау", "шоттар", "Шоттарды мұрағаттауға міндетті."
    )
    result.append(
        make_case(
            "split",
            [a],
            [combined],
            [a],
            [archive, invoices],
            {"both": ["archive", "invoices"]},
            flags={"both": ["split"]},
            expected={"full": 1, "split": 1, "loss": 0},
        )
    )
    result.append(
        make_case(
            "merge",
            [a],
            [archive, invoices],
            [a],
            [combined],
            {"archive": ["both"], "invoices": ["both"]},
            expected={"full": 2, "merged": 2, "loss": 0},
        )
    )
    duplicate = duty(
        "copy",
        "b",
        "мұрағаттау",
        "келісімшарттар",
        "Келісімшарттарды мұрағаттауға міндетті.",
    )
    riskkey = tuple(sorted(("after:fn:archive", "after:fn:copy")))
    result.append(
        make_case(
            "duplicate",
            [a],
            [archive],
            [a, b],
            [archive, duplicate],
            {"archive": ["archive"]},
            risks={riskkey: "duplicate"},
            expected={"duplicate": 1, "loss": 0, "new_risk": 1},
        )
    )
    before_copy = duty(
        "copy",
        "b",
        "мұрағаттау",
        "келісімшарттар",
        "Келісімшарттарды мұрағаттауға міндетті.",
    )
    oldrisk = tuple(sorted(("before:fn:archive", "before:fn:copy")))
    result.append(
        make_case(
            "persistent",
            [a, b],
            [archive, before_copy],
            [a, b],
            [archive, duplicate],
            {"archive": ["archive"], "copy": ["copy"]},
            risks={oldrisk: "duplicate", riskkey: "duplicate"},
            expected={"duplicate": 1, "persisting": 1},
        )
    )
    auditor = duty(
        "audit",
        "a",
        "тәуелсіз тексеру",
        "төлемдер",
        "Өзі орындайтын төлемдерді тәуелсіз тексеруге міндетті.",
    )
    executor = duty(
        "execute", "a", "орындау", "төлемдер", "Төлемдерді орындауға міндетті."
    )
    rule = "Тәуелсіз бақылау талабы: қызметкер өзі орындайтын төлемдерді өзі тәуелсіз тексере алмайды. Мүдделер қақтығысына жол берілмейді."
    result.append(
        make_case(
            "conflict",
            [a],
            [executor],
            [a],
            [executor, auditor],
            {"execute": ["execute"]},
            risks={tuple(sorted(("after:fn:execute", "after:fn:audit"))): "conflict"},
            constraints={"after": [rule]},
            expected={"conflict": 1},
        )
    )
    independent = duty(
        "audit",
        "b",
        "тәуелсіз тексеру",
        "төлемдер",
        "Басқа бөлімше орындайтын төлемдерді тәуелсіз тексереді.",
    )
    result.append(
        make_case(
            "executor_controller",
            [a],
            [executor],
            [a, b],
            [executor, independent],
            {"execute": ["execute"]},
            constraints={"after": [rule]},
            expected={"conflict": 0, "duplicate": 0},
        )
    )
    it = duty(
        "it",
        "a",
        "тексеру",
        "ақпараттық жүйелер",
        "Ақпараттық жүйелер аудитін жүргізеді.",
        scope="IT",
    )
    hr = duty(
        "hr",
        "b",
        "тексеру",
        "персонал процестері",
        "Персонал процестерінің аудитін жүргізеді.",
        scope="HR",
    )
    result.append(
        make_case(
            "different_scope",
            [a],
            [it],
            [a, b],
            [it, hr],
            {"it": ["it"]},
            expected={"duplicate": 0, "loss": 0},
        )
    )
    ban = duty(
        "ban", "a", "бекіту", "төлемдер", "Төлемдерді бекіту", modality="prohibition"
    )
    result.append(
        make_case(
            "prohibition",
            [a],
            [archive, ban],
            [a],
            [archive, ban],
            {"archive": ["archive"]},
            expected={"before_total": 1, "loss": 0},
        )
    )
    unknown = duty("unknown", None, "дайындау", "есеп", "Есеп дайындалуы тиіс.")
    result.append(
        make_case(
            "owner_unknown",
            [a],
            [archive],
            [a],
            [archive, unknown],
            {"archive": ["archive"]},
            expected={"ownership_gap": 1},
        )
    )
    parent = unit("Аудит блогы", "p", kind="organization")
    child = unit("Аудит департаменті", "c", parent="p")
    fp = duty(
        "parent", "p", "тексеру", "тәуекелдер", "Тәуекелдер аудитін ұйымдастырады."
    )
    fc = duty(
        "child",
        "c",
        "тексеру",
        "тәуекелдер",
        "Блок міндетін орындау аясында тәуекелдер аудитін жүргізеді.",
    )
    result.append(
        make_case(
            "hierarchy",
            [parent, child],
            [fp, fc],
            [parent, child],
            [fp, fc],
            {"parent": ["parent"], "child": ["child"]},
            expected={"duplicate": 0},
        )
    )
    renamed = unit("Құжаттарды сақтау бөлімі", "z")
    fd = duty(
        "renamed",
        "z",
        "мұрағаттау",
        "келісімшарттар",
        "Келісімшарттарды мұрағаттауға міндетті.",
    )
    result.append(
        make_case(
            "rename",
            [a],
            [archive],
            [renamed],
            [fd],
            {"archive": ["renamed"]},
            constraints={
                "after": ["Өкім: Есеп бөлімін Құжаттарды сақтау бөлімі деп қайта атау."]
            },
            events=[
                {
                    "before_name": a["name"],
                    "after_name": renamed["name"],
                    "source": "after:rule:0",
                    "type": "renamed",
                }
            ],
            expected={"renamed_unit": 1, "loss": 0},
        )
    )
    return result
