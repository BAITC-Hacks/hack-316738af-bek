"""Portable reports: escape all content; neutralize spreadsheet formula prefixes."""

import csv
import io
import json
from html import escape
from pathlib import Path


def csv_safe(value):
    text = "" if value is None else str(value)
    # Spreadsheet programs ignore whitespace/control characters before formulas.
    check = text.lstrip("".join(chr(n) for n in range(33)) + "\ufeff")
    return (
        "'" + text
        if check.startswith(("=", "+", "-", "@", "＝", "＋", "－", "＠")) or text.startswith(("\t", "\r", "\n"))
        else text
    )


def csv_report(result, reviews):
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(
        [
            "record_type",
            "id",
            "analysis_revision",
            "status",
            "title",
            "explanation",
            "evidence_ids",
            "review_status",
            "review_note",
            "details",
        ]
    )

    def row(*values):
        writer.writerow([csv_safe(v) for v in values])

    revision = result["analysis_revision"]
    row("summary", result["analysis_id"], revision, result["status"], result["summary"]["headline"], "", "", "", "", "")
    for key, value in result["coverage"].items():
        row("coverage", key, revision, "", key, value, "", "", "", "")
    for mapping in result["mappings"]:
        row(
            "mapping",
            mapping["id"],
            revision,
            mapping["coverage_status"],
            " → ".join([", ".join(mapping["before_function_ids"]), ", ".join(mapping["after_function_ids"])]),
            mapping["explanation"],
            ", ".join(mapping["source_span_ids"] + mapping["context_evidence_ids"]),
            "",
            "",
            json.dumps(mapping, ensure_ascii=False),
        )
    for finding in result["findings"]:
        row(
            "finding",
            finding["id"],
            revision,
            finding["risk_change"],
            finding["title"],
            finding["explanation"],
            ", ".join(finding["evidence_ids"] + finding["context_evidence_ids"] + finding["counterevidence_ids"]),
            finding["review_status"],
            reviews.get(finding["id"], {}).get("note", ""),
            json.dumps(finding, ensure_ascii=False),
        )
    for collection in ("documents", "units", "unit_changes", "functions", "warnings", "usage"):
        for item in result[collection]:
            row(
                collection,
                item.get("id", item.get("code", "")),
                revision,
                "",
                item.get("title", item.get("name", "")),
                item.get("message", ""),
                "",
                "",
                "",
                json.dumps(item, ensure_ascii=False),
            )
    return "\ufeff" + output.getvalue()


def html_report(result, reviews, evidence):
    def e(value):
        return escape(str(value), quote=True)

    def links(ids):
        return " ".join(f'<a class="source" href="#e-{e(ref)}">{e(ref)}</a>' for ref in dict.fromkeys(ids))

    def detail_table(title, headers, rows):
        head = "".join(f"<th>{e(h)}</th>" for h in headers)
        body = "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in row) + "</tr>" for row in rows)
        return f'<section><h2>{e(title)}</h2><div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></section>'

    units = {u["id"]: u["name"] for u in result["units"]}
    structural = detail_table(
        "Құрылым өзгерістері",
        ("Дейін → кейін", "Өзгеріс", "Негіз", "Түсіндірме"),
        [
            (
                ", ".join(units[i] for i in u["before_unit_ids"])
                + " → "
                + ", ".join(units[i] for i in u["after_unit_ids"]),
                u["change_type"],
                u["basis"],
                u["explanation"],
            )
            for u in result["unit_changes"]
        ],
    )
    inventory = detail_table(
        "Функциялар тізілімі",
        ("ID / нұсқа", "Жауапты", "Әрекет / объект", "Шарт және шеңбер"),
        [
            (
                f"{f['id']} / {f['version']}",
                units.get(f["role_id"] or f["unit_id"], "Анықталмаған"),
                f"{f['action']} — {f['object']}",
                "; ".join([f["modality"], f["scope"] or "", *f["conditions"], f["frequency"] or ""]),
            )
            for f in result["functions"]
        ],
    )

    metrics = "".join(
        f'<div class="metric"><strong>{value}</strong><span>{e(label)}</span></div>'
        for label, value in (
            ("Бұрынғы функция", result["coverage"]["before_functions_total"]),
            ("Толық сақталған", result["coverage"]["full"]),
            ("Ішінара", result["coverage"]["partial"]),
            ("Табылмаған", result["coverage"]["none"]),
            ("Белгісіз", result["coverage"]["unknown"]),
        )
    )
    summary = "".join(
        f"<li>{e(item['text'])} <small>{e(', '.join(item['reference_ids']))}</small></li>"
        for item in result["summary"]["items"]
    )
    mappings = "".join(
        f"<tr><td>{e(m['id'])}</td><td>{e(', '.join(m['before_function_ids']))} → {e(', '.join(m['after_function_ids'])) or '—'}</td><td>{e(m['coverage_status'])}</td><td>{e(m['explanation'])}<br>{links(m['source_span_ids'] + m['context_evidence_ids'])}</td></tr>"
        for m in result["mappings"]
    )
    findings = ""
    for f in result["findings"]:
        review = reviews.get(f["id"], {})
        findings += f'<article><div class="eyebrow">{e(f["severity"])} · {e(f["risk_change"])} · {e(f["verification_status"])}</div><h3>{e(f["title"])}</h3><p>{e(f["explanation"])}</p><p><b>Келесі әрекет:</b> {e(f["recommended_action"]["action"])}</p><p>{links(f["evidence_ids"] + f["context_evidence_ids"] + f["counterevidence_ids"])}</p><div class="review"><b>Қызметкер шешімі: {e(f["review_status"])}</b><p>{e(review.get("note", "Түсініктеме жоқ"))}</p><small>{e(review.get("reviewed_at", ""))}</small></div></article>'
    sources = ""
    for ref, item in evidence.items():
        s, d = item["source"], item["document"]
        loc = s["locator"]
        locator = loc["clause"] or loc["cell_range"] or (f"{loc['page']}-бет" if loc["page"] else loc["path"])
        sources += f'<article id="e-{e(ref)}"><div class="eyebrow">{e(d["filename"])} · {e(d["version"])} · {e(locator)}</div><blockquote>{e(s["raw_text"])}</blockquote><small>{e(ref)} · SHA-256 {e(d["source_sha256"])}</small></article>'
    warnings = "".join(f"<li>{e(w['message'])}</li>" for w in result["warnings"]) or "<li>Тіркелген ескерту жоқ.</li>"
    css = (Path(__file__).parent / "static/report.css").read_text(encoding="utf-8")
    return f"""<!doctype html><html lang="kk"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Qurylym AI — талдау есебі</title><style>{css}</style><body><main><header><div class="brand">Q<span>•</span> QURYLYM AI</div><div class="eyebrow">ҰЙЫМДЫҚ ӨЗГЕРІСТЕР · ТАЛДАУ ЕСЕБІ</div><h1>{e(result["summary"]["headline"])}</h1><p>{e(result["analysis_id"])} · {result["analysis_revision"]}-нұсқа · {e(result["status"])}</p></header>{structural}{inventory}<section class="metrics">{metrics}</section><section><h2>Негізгі қорытынды</h2><ul>{summary}</ul><p class="muted">AI қорытындысы — тексеруге арналған ұсыным. Қызметкер шешімі бөлек сақталады.</p></section><section><h2>Функциялардың жолы</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>Дейін → кейін</th><th>Қамту</th><th>Негіздеме және дәлел</th></tr></thead><tbody>{mappings}</tbody></table></div></section><section><h2>Тексеруді қажет ететін жағдайлар</h2>{findings or "<p>Тіркелген жағдай жоқ.</p>"}</section><section><h2>Қамту және шектеулер</h2><p>Файлдар: {result["coverage"]["files_total"]} · толық: {result["coverage"]["files_complete"]} · ішінара: {result["coverage"]["files_partial"]} · оқылмаған: {result["coverage"]["files_failed"]}</p><p>Дәлел сілтемелері: {result["coverage"]["evidence_links_valid"]}/{result["coverage"]["evidence_links_total"]}</p><ul>{warnings}</ul></section><section><h2>Түпнұсқа дәлелдер</h2>{sources}</section><footer>Qurylym AI · Келісім 1.0.0 · Есеп ұсынылған құжаттардың ауқымымен шектеледі.</footer></main></body></html>"""
