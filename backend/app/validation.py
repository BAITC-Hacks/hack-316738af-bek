"""Validate the engine boundary, including references and arithmetic, before publishing."""

from collections import Counter

from .models import AnalysisInput, AnalysisResult

EVIDENCE_KEYS = {"source_span_ids", "context_span_ids", "evidence_ids", "context_evidence_ids", "counterevidence_ids"}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def evidence_references(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if key in EVIDENCE_KEYS:
                yield from child
            else:
                yield from evidence_references(child)
    elif isinstance(value, list):
        for child in value:
            yield from evidence_references(child)


def validate_result(payload, raw):
    AnalysisInput.model_validate(payload)
    result = AnalysisResult.model_validate(raw).model_dump()
    for key in ("schema_version", "analysis_id", "analysis_revision"):
        require(result[key] == payload[key], f"changed_{key}")
    docs = {d["id"]: d for d in payload["documents"]}
    expected = [{k: v for k, v in d.items() if k != "spans"} for d in payload["documents"]]
    require(result["documents"] == expected, "changed_documents")
    require(all(d["parse_status"] != "pending" for d in docs.values()), "pending_document")
    spans = {s["id"]: s for d in docs.values() for s in d["spans"]}
    require(len(spans) == sum(len(d["spans"]) for d in docs.values()), "duplicate_source")
    for span in spans.values():
        seen, pending = set(), list(span["context_span_ids"])
        while pending:
            ref = pending.pop()
            require(ref in spans and ref != span["id"], "invalid_source_context")
            require(spans[ref]["document_id"] == span["document_id"], "foreign_source_context")
            if ref not in seen:
                seen.add(ref)
                pending.extend(spans[ref]["context_span_ids"])
    indexes, all_ids = {}, set()
    for key in ("units", "unit_changes", "functions", "mappings", "findings"):
        indexes[key] = {item["id"]: item for item in result[key]}
        require(len(indexes[key]) == len(result[key]), f"duplicate_{key}")
        require(not all_ids.intersection(indexes[key]), "ambiguous_id")
        require(all(indexes[key]), "empty_id")
        all_ids.update(indexes[key])
    units, functions = indexes["units"], indexes["functions"]
    refs = list(evidence_references(result))
    require(all(ref in spans for ref in refs), "unknown_evidence")

    def version_refs(ids, index, version):
        require(len(ids) == len(set(ids)), "duplicate_reference")
        require(all(ref in index and index[ref]["version"] == version for ref in ids), "wrong_version_reference")

    for unit in units.values():
        version_refs(
            unit["source_span_ids"],
            {i: {"version": docs[s["document_id"]]["version"]} for i, s in spans.items()},
            unit["version"],
        )
        require(bool(unit["source_span_ids"]), "unit_without_evidence")
        parent, visited = unit["parent_id"], {unit["id"]}
        while parent is not None:
            require(
                parent in units and parent not in visited and units[parent]["version"] == unit["version"],
                "invalid_unit_tree",
            )
            visited.add(parent)
            parent = units[parent]["parent_id"]
    for function in functions.values():
        for key in ("unit_id", "role_id"):
            if function[key] is not None:
                version_refs([function[key]], units, function["version"])
        require(function["role_id"] is None or units[function["role_id"]]["kind"] == "role", "invalid_role")
        require(bool(function["source_span_ids"]), "function_without_evidence")
        for ref in function["source_span_ids"] + function["context_span_ids"]:
            require(
                docs[spans[ref]["document_id"]]["version"] == function["version"], "function_wrong_evidence_version"
            )
        require(all(spans[ref]["is_content"] for ref in function["source_span_ids"]), "function_from_noncontent")
    for change in result["unit_changes"]:
        version_refs(change["before_unit_ids"], units, "before")
        version_refs(change["after_unit_ids"], units, "after")
        require(bool(change["source_span_ids"]), "change_without_evidence")
    comparable = {i: f for i, f in functions.items() if f["modality"] in ("obligation", "permission")}
    before = {i for i, f in comparable.items() if f["version"] == "before"}
    after = {i for i, f in comparable.items() if f["version"] == "after"}
    mapped_before, mapped_after, counts = [], set(), Counter()
    for mapping in result["mappings"]:
        b, a = mapping["before_function_ids"], mapping["after_function_ids"]
        version_refs(b, comparable, "before")
        version_refs(a, comparable, "after")
        require(bool(b), "empty_mapping")
        require(bool(mapping["source_span_ids"]), "mapping_without_evidence")
        if mapping["coverage_status"] in ("full", "partial"):
            require(bool(a), "covered_without_after")
        if mapping["coverage_status"] == "none":
            require(not a, "loss_with_after")
        if mapping["coverage_status"] == "partial":
            require(bool(mapping["uncovered_aspects"]), "partial_without_aspects")
        mapped_before.extend(b)
        mapped_after.update(a)
        counts[mapping["coverage_status"]] += len(b)
    require(set(mapped_before) == before and len(mapped_before) == len(before), "invalid_function_coverage")
    after_docs = {i for i, d in docs.items() if d["version"] == "after"}
    for finding in result["findings"]:
        require(finding["analysis_revision"] == payload["analysis_revision"], "finding_revision")
        require(finding["review_status"] == "unreviewed", "engine_cannot_review")
        require(bool(finding["evidence_ids"]), "finding_without_evidence")
        require(all(ref in units for ref in finding["affected_units"]), "unknown_affected_unit")
        role = finding["recommended_action"]["target_role_id"]
        require(role is None or role in units and units[role]["kind"] == "role", "unknown_action_role")
        scope = finding["search_scope_document_ids"]
        require(len(scope) == len(set(scope)) and set(scope) <= after_docs, "invalid_search_scope")
        if finding["search_complete"]:
            require(
                bool(scope) and all(docs[i]["parse_status"] == "complete" for i in scope), "incomplete_search_claim"
            )
        if finding["type"] == "potential_loss" or finding["risk_change"] == "no_longer_detected":
            require(bool(scope), "missing_search_scope")
            if finding["verification_status"] == "validated":
                require(finding["search_complete"] and set(scope) == after_docs, "unverified_absence")
    for warning in result["warnings"]:
        require(warning["document_id"] is None or warning["document_id"] in docs, "unknown_warning_document")
        require(all(ref in spans for ref in warning["span_ids"]), "unknown_warning_span")
    summary_targets = set(indexes["mappings"]) | set(indexes["findings"]) | set(indexes["unit_changes"])
    for item in result["summary"]["items"]:
        require(
            bool(item["reference_ids"]) and set(item["reference_ids"]).issubset(summary_targets),
            "ungrounded_summary",
        )
    coverage = result["coverage"]
    calculated = {
        "files_total": len(docs),
        "files_complete": sum(d["parse_status"] == "complete" for d in docs.values()),
        "files_partial": sum(d["parse_status"] == "partial" for d in docs.values()),
        "files_failed": sum(d["parse_status"] == "failed" for d in docs.values()),
        "before_functions_total": len(before),
        **{key: counts[key] for key in ("full", "partial", "none", "unknown")},
        "after_functions_new": len(after - mapped_after),
        "evidence_links_total": len(refs),
        "evidence_links_valid": len(refs),
    }
    require(coverage == calculated, "incorrect_counts")
    if any(d["parse_status"] != "complete" for d in docs.values()):
        require(result["status"] == "partial", "incomplete_documents_marked_complete")
    for d in docs.values():
        for warning in d["warnings"]:
            if warning not in result["warnings"]:
                result["warnings"].append(warning)
    return result
