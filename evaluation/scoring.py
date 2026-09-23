"""Clause-anchored scoring; ground truth is only used AFTER the engine runs."""


def score(case, result):
    checks = []
    functions = {f["id"]: f for f in result["functions"]}

    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    check("analysis_completed", result["status"] == "completed", result["status"])
    check(
        "references_valid",
        result["coverage"]["evidence_links_total"]
        == result["coverage"]["evidence_links_valid"],
        str(result["coverage"]["evidence_links_valid"]),
    )
    # Compare clause correspondences, allowing the live model to split a compound
    # source clause into multiple atoms rather than requiring scripted atom counts.
    for old_source, expected_after in case.links.items():
        maps = [
            m
            for m in result["mappings"]
            if any(
                old_source in functions[f]["source_span_ids"]
                for f in m["before_function_ids"]
            )
        ]
        actual_after = {
            s
            for m in maps
            for f in m["after_function_ids"]
            for s in functions[f]["source_span_ids"]
        }
        if expected_after:
            expected_status = case.coverages.get(old_source, "full")
            check(
                "mapping:" + old_source,
                bool(maps)
                and set(expected_after).issubset(actual_after)
                and all(m["coverage_status"] == expected_status for m in maps),
                {
                    "expected_sources": expected_after,
                    "observed_sources": sorted(actual_after),
                    "expected_status": expected_status,
                },
            )
        else:
            check(
                "absence:" + old_source,
                bool(maps) and all(m["coverage_status"] == "none" for m in maps),
                {"statuses": [m["coverage_status"] for m in maps]},
            )
    for source, flags in case.flags.items():
        # Clause atomization may produce one-to-one edges for a split clause.
        required = set(flags) - {"split", "merged"}
        got = {
            flag
            for m in result["mappings"]
            if any(
                source in functions[f]["source_span_ids"]
                for f in m["before_function_ids"]
            )
            for flag in m["change_flags"]
        }
        if required:
            check(
                "change:" + source,
                required.issubset(got),
                {"expected": sorted(required), "observed": sorted(got)},
            )
    observed = set()
    for f in result["findings"]:
        if (
            f["type"] not in ("potential_duplicate", "potential_conflict")
            or f["risk_change"] == "no_longer_detected"
        ):
            continue
        anchors = tuple(
            sorted(s for s in f["evidence_ids"] if s.startswith("after:fn:"))
        )
        if len(anchors) >= 2:
            observed.add((f["type"].removeprefix("potential_"), anchors))
    expected = {
        (kind, key)
        for key, kind in case.risks.items()
        if all(s.startswith("after:") for s in key)
    }
    # Source pairs, rather than prose matching, reveal wrong-citation findings.
    check(
        "risk_pairs",
        observed == expected,
        {
            "expected": [list(x) for x in sorted(expected)],
            "observed": [list(x) for x in sorted(observed)],
        },
    )
    if case.expected.get("loss") == 0:
        check(
            "no_false_loss",
            not any(f["type"] == "potential_loss" for f in result["findings"]),
            str(sum(f["type"] == "potential_loss" for f in result["findings"])),
        )
    for event in case.events:
        check(
            "organization:" + event["type"],
            any(
                c["change_type"] == event["type"]
                and event["source"] in c["source_span_ids"]
                for c in result["unit_changes"]
            ),
            event["source"],
        )
    if "ownership_gap" in case.expected:
        check(
            "ownership_gap",
            sum(f["type"] == "ownership_gap" for f in result["findings"])
            == case.expected["ownership_gap"],
            str(case.expected["ownership_gap"]),
        )
    for field in ("persisting", "new_risk"):
        if field in case.expected:
            status = "persisting" if field == "persisting" else "new"
            check(
                field,
                sum(
                    f["risk_change"] == status
                    for f in result["findings"]
                    if f["type"] in ("potential_duplicate", "potential_conflict")
                )
                == case.expected[field],
                status,
            )
    return {
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
        "risk_true_positive": len(expected & observed),
        "risk_false_positive": len(observed - expected),
        "risk_false_negative": len(expected - observed),
    }
