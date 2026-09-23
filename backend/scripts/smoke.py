"""Exercise a running HTTP server using synthetic documents and the real engine if present."""

import argparse
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def main():
    load_dotenv(ROOT / ".env")
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--require-engine", action="store_true")
    parser.add_argument("--fixture-set", choices=("standard", "judge"), default="standard")
    parser.add_argument("--format", choices=("docx", "pdf", "xlsx"), default="docx")
    args = parser.parse_args()
    if args.fixture_set == "judge" and args.format != "docx":
        parser.error("The judge fixtures are DOCX documents")
    fixture_dir = ROOT / "backend/tests/fixtures"
    if args.fixture_set == "judge":
        fixture_dir /= "judge"
    report = {"url": args.url, "synthetic_documents": True, "engine": "not_tested", "checks": []}
    report.update(fixture_set=args.fixture_set, format=args.format)
    output = ROOT / f"backend/test-results/live-smoke-{args.fixture_set}-{args.format}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    report["passed"] = False
    headers = {"Authorization": "Bearer " + os.environ["APP_ACCESS_TOKEN"]} if os.getenv("APP_ACCESS_TOKEN") else {}
    with httpx.Client(base_url=args.url, headers=headers, timeout=65) as client:

        def checked(response, status):
            if response.status_code != status:
                raise RuntimeError(f"Unexpected HTTP status {response.status_code}, expected {status}")
            return response.json()

        checked(client.get("/api/health"), 200)
        report["checks"].append("health")
        state = checked(client.post("/api/analyses"), 201)
        id = state["analysis_id"]
        for version in ("before", "after"):
            filename = f"{version}.{args.format}"
            data = (fixture_dir / filename).read_bytes()
            state = checked(
                client.post(
                    f"/api/analyses/{id}/documents",
                    data={"version": version},
                    files={"file": (filename, data)},
                ),
                201,
            )
            document = state["documents"][-1]
            original = client.get(f"/api/analyses/{id}/documents/{document['id']}/download")
            assert (
                original.status_code == 200
                and hashlib.sha256(original.content).hexdigest() == document["source_sha256"]
            )
            report["checks"].append(f"{version}_upload_parse_download_sha256")
        response = client.post(
            f"/api/analyses/{id}/run",
            json={"expected_revision": state["analysis_revision"]},
            headers={"Idempotency-Key": str(uuid.uuid4())},
        )
        if response.status_code == 500 and response.json().get("code") == "engine_unavailable":
            report["engine"] = "unavailable_no_fake_result"
            if args.require_engine:
                raise RuntimeError("Real AI engine is required for this integration test")
        else:
            checked(response, 202)
            deadline = time.monotonic() + 330
            while time.monotonic() < deadline:
                state = checked(client.get(f"/api/analyses/{id}"), 200)
                if state["status"] in ("completed", "partial", "failed"):
                    break
                time.sleep(0.5)
            assert state["status"] in ("completed", "partial"), "Analysis failed or did not complete"
            result = checked(client.get(f"/api/analyses/{id}/results"), 200)
            from backend.app.validation import evidence_references

            sources = {
                ref: checked(client.get(f"/api/analyses/{id}/sources/{ref}"), 200)
                for ref in set(evidence_references(result))
            }
            assert any(u["provider"] == "openai" and u["calls"] > 0 for u in result["usage"]), "No real OpenAI usage"
            report.update(
                analysis_status=result["status"],
                functions=len(result["functions"]),
                findings=len(result["findings"]),
                usage=result["usage"],
                warning_codes=sorted({w["code"] for w in result["warnings"]}),
            )
            # Keep the real result and a failed checkpoint if a semantic assertion
            # below fails. A successful HTTP response alone is not acceptance.
            output.with_suffix(".result.json").write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            output.write_text(json.dumps(report, indent=2), encoding="utf-8")
            if args.fixture_set == "judge":
                assert any(c["change_type"] == "renamed" for c in result["unit_changes"]), "Rename was not detected"
                assert any(
                    f["type"] == "potential_loss"
                    and any("резервтік көшірмелерін" in sources[s]["source"]["raw_text"] for s in f["evidence_ids"])
                    for f in result["findings"]
                ), "Known missing backup duty was not detected"
                assert any(
                    f["type"] == "potential_duplicate"
                    and len(
                        {
                            sources[s]["source"]["locator"]["clause"]
                            for s in f["evidence_ids"]
                            if sources[s]["document"]["version"] == "after"
                            and "орталық мұрағатта" in sources[s]["source"]["raw_text"]
                        }
                    )
                    >= 2
                    for f in result["findings"]
                ), "Known duplicate was not linked to both clauses"
                report["checks"].append("judge_rename_loss_duplicate_with_correct_sources")
            if result["findings"]:
                finding_id = result["findings"][0]["id"]
                checked(
                    client.patch(
                        f"/api/analyses/{id}/findings/{finding_id}",
                        json={
                            "analysis_revision": state["analysis_revision"],
                            "review_status": "needs_information",
                            "note": "Synthetic integration check",
                        },
                    ),
                    200,
                )
            for format in ("html", "csv"):
                response = client.get(f"/api/analyses/{id}/export", params={"format": format})
                assert response.status_code == 200 and response.content
            report["engine"] = "real_module_completed"
            report["checks"].append("run_result_sources_review_exports")
    report["passed"] = True
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
