"""Cross-object invariants that JSON Schema alone cannot express."""

from .errors import AnalysisError
from .matching import comparable
from .schema import validate

EVIDENCE_FIELDS = {
    "source_span_ids",
    "context_span_ids",
    "evidence_ids",
    "context_evidence_ids",
    "counterevidence_ids",
}


def evidence_references(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in EVIDENCE_FIELDS:
                yield from item
            else:
                yield from evidence_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from evidence_references(item)


def _fail(message):
    raise AnalysisError("RESULT_INVARIANT_FAILED", message)


def validate_result(result, registry):
    validate("AnalysisResult", result, output=True)
    source = registry.payload
    for key in ("schema_version", "analysis_id", "analysis_revision"):
        if result[key] != source[key]:
            _fail("Талдаудың идентификаторы немесе нұсқасы өзгерген.")
    if result["documents"] != registry.summaries():
        _fail("Түпнұсқа құжат метадеректері өзгерген.")
    indexes = {}
    all_ids = set()
    for name in ("units", "unit_changes", "functions", "mappings", "findings"):
        index = {}
        for item in result[name]:
            if not item["id"] or item["id"] in all_ids:
                _fail("Нәтиже объектілерінің ID-і бос немесе қайталанған.")
            all_ids.add(item["id"])
            index[item["id"]] = item
        indexes[name] = index
    units, functions = indexes["units"], indexes["functions"]
    refs = list(evidence_references(result))
    registry.ids(refs)
    for unit in units.values():
        if not unit["name"].strip():
            _fail("Бөлімше атауы бос.")
        registry.ids(unit["source_span_ids"], unit["version"], True)
        parent = unit["parent_id"]
        if parent is not None and (
            parent not in units or units[parent]["version"] != unit["version"]
        ):
            _fail("Бөлімше бағыныштылығының нұсқасы жарамсыз.")
        seen, current = set(), unit["id"]
        while current is not None:
            if current in seen:
                _fail("Бөлімшелер құрылымында цикл бар.")
            seen.add(current)
            current = units[current]["parent_id"]
    for func in functions.values():
        if not func["action"].strip() or not func["object"].strip():
            _fail("Функция әрекеті немесе объектісі бос.")
        registry.ids(func["source_span_ids"], func["version"], True)
        registry.ids(func["context_span_ids"], func["version"])
        for key in ("unit_id", "role_id"):
            uid = func[key]
            if uid is not None:
                if uid not in units or units[uid]["version"] != func["version"]:
                    _fail("Функцияның жауаптысына сілтеме жарамсыз.")
                if (key == "role_id" and units[uid]["kind"] != "role") or (
                    key == "unit_id" and units[uid]["kind"] == "role"
                ):
                    _fail("Лауазым мен бөлімше идентификаторлары шатастырылған.")
    for change in result["unit_changes"]:
        for side in ("before", "after"):
            for uid in change[side + "_unit_ids"]:
                if uid not in units or units[uid]["version"] != side:
                    _fail("Бөлімше өзгерісінің сілтемесі жарамсыз.")
        registry.ids(change["source_span_ids"], nonempty=True)
    mapped, after_linked = [], set()
    counts = {k: 0 for k in ("full", "partial", "none", "unknown")}
    for mapping in result["mappings"]:
        if not mapping["before_function_ids"]:
            _fail("Салыстыруда бұрынғы функция жоқ.")
        for side in ("before", "after"):
            for fid in mapping[side + "_function_ids"]:
                if (
                    fid not in functions
                    or functions[fid]["version"] != side
                    or not comparable(functions[fid])
                ):
                    _fail("Салыстыру функциясы немесе оның редакциясы жарамсыз.")
        mapped.extend(mapping["before_function_ids"])
        after_linked.update(mapping["after_function_ids"])
        counts[mapping["coverage_status"]] += len(mapping["before_function_ids"])
        if (
            mapping["coverage_status"] in ("full", "partial")
            and not mapping["after_function_ids"]
        ):
            _fail("Қамтылған функция үшін кейінгі сәйкестік жоқ.")
        if mapping["coverage_status"] == "none" and mapping["after_function_ids"]:
            _fail("Табылмаған функцияның кейінгі сәйкестігі бар.")
        if mapping["coverage_status"] == "partial" and not mapping["uncovered_aspects"]:
            _fail("Қамтылмаған міндет бөлігі көрсетілмеген.")
        for fid in mapping["before_function_ids"] + mapping["after_function_ids"]:
            if not set(functions[fid]["source_span_ids"]).intersection(
                mapping["source_span_ids"]
            ):
                _fail("Сәйкестік әр байланыстырылған функцияның дәлелін қамтымайды.")
    before_ids = {
        f["id"]
        for f in functions.values()
        if f["version"] == "before" and comparable(f)
    }
    if len(mapped) != len(set(mapped)) or set(mapped) != before_ids:
        _fail("Әр бұрынғы функция дәл бір рет саналған жоқ.")
    for item in result["findings"]:
        if (
            item["analysis_revision"] != source["analysis_revision"]
            or item["review_status"] != "unreviewed"
        ):
            _fail("AI қызметкердің шешімін немесе талдау нұсқасын өзгерткен.")
        if not set(item["affected_units"]).issubset(units):
            _fail("Ауытқудың жауапты бөлімшесі табылмады.")
        registry.ids(item["evidence_ids"], nonempty=True)
        for did in item["search_scope_document_ids"]:
            if did not in registry.docs or registry.docs[did]["version"] != "after":
                _fail("Тексерілген кейінгі құжаттар тізімі жарамсыз.")
        role = item["recommended_action"]["target_role_id"]
        if role is not None and (role not in units or units[role]["kind"] != "role"):
            _fail("Ұсыныстың жауапты рөлі расталмаған.")
        if item["risk_change"] == "no_longer_detected" and not item["search_complete"]:
            _fail("Қайта тексеру аяқталмай тәуекел жойылды деп көрсетілген.")
        if item["search_complete"] and set(item["search_scope_document_ids"]) != set(
            registry.doc_ids("after")
        ):
            _fail("Жоғалу туралы іздеу кейінгі барлық құжатты қамтымайды.")
    c = result["coverage"]
    if c["before_functions_total"] != len(before_ids) or any(
        c[k] != v for k, v in counts.items()
    ):
        _fail("Функция санақтары нақты нәтижемен сәйкес емес.")
    new_ids = {
        f["id"] for f in functions.values() if f["version"] == "after" and comparable(f)
    } - after_linked
    if c["after_functions_new"] != len(new_ids):
        _fail("Жаңа функциялар санағы қате.")
    for label, state in (
        ("files_complete", "complete"),
        ("files_partial", "partial"),
        ("files_failed", "failed"),
    ):
        if c[label] != sum(d["parse_status"] == state for d in registry.docs.values()):
            _fail("Оқылған құжаттар санағы қате.")
    if (
        c["files_total"] != len(registry.docs)
        or c["evidence_links_total"] != len(refs)
        or c["evidence_links_valid"] != len(refs)
    ):
        _fail("Қамту немесе дәлелдер санағы қате.")
    targets = (
        set(indexes["mappings"])
        | set(indexes["findings"])
        | set(indexes["unit_changes"])
    )
    for item in result["summary"]["items"]:
        if not item["reference_ids"] or not set(item["reference_ids"]).issubset(
            targets
        ):
            _fail("Қорытынды мәтіні расталған нәтижеге байланыстырылмаған.")
    return result
