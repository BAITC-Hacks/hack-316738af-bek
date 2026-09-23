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
    args = parser.parse_args()
    report = {"url": args.url, "synthetic_documents": True, "engine": "not_tested", "checks": []}
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
            data = (ROOT / f"backend/tests/fixtures/{version}.docx").read_bytes()
            state = checked(
                client.post(
                    f"/api/analyses/{id}/documents",
                    data={"version": version},
                    files={"file": (f"{version}.docx", data)},
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

            for ref in set(evidence_references(result)):
                checked(client.get(f"/api/analyses/{id}/sources/{ref}"), 200)
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
    output = ROOT / "backend/test-results/live-smoke.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
