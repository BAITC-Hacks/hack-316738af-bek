import asyncio
import hashlib
import json
import sqlite3
import time
from contextlib import closing
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from backend.app.config import ROOT
from backend.app.main import create_app
from backend.app.parsers import parse_document
from backend.app.security import COOKIE
from backend.tests.conftest import docx_bytes, fake_engine, finish, prepared, result_for, start, upload

CONTRACT = json.loads((ROOT / "contracts/openapi.json").read_text(encoding="utf-8"))


def schema(name, value):
    Draft202012Validator({"$ref": f"#/components/schemas/{name}", "components": CONTRACT["components"]}).validate(value)


def test_health_and_contract(client):
    schema("Health", client.get("/api/health").json())
    assert client.get("/openapi.json").json() == CONTRACT
    assert "QURYLYM" in client.get("/").text
    assert client.get("/docs").status_code == 200


def test_complete_flow_review_export_and_persistence(client, app, settings):
    state = prepared(client)
    schema("AnalysisState", state)
    assert state["analysis_revision"] == 3
    response = start(client, state, "flow-key")
    assert response.status_code == 202
    current = finish(client, state)
    assert current["status"] == "completed", current
    id = state["analysis_id"]
    result = client.get(f"/api/analyses/{id}/results").json()
    schema("AnalysisResult", result)
    ref = result["functions"][0]["source_span_ids"][0]
    evidence = client.get(f"/api/analyses/{id}/sources/{ref}").json()
    schema("SourceEvidence", evidence)
    assert "annual report" in evidence["source"]["raw_text"]
    assert evidence["context"][0]["raw_text"] == "Audit department"
    original = client.get(f"/api/analyses/{id}/documents/{evidence['document']['id']}/download")
    assert hashlib.sha256(original.content).hexdigest() == evidence["document"]["source_sha256"]
    patch = {"analysis_revision": 3, "review_status": "confirmed", "note": "<script>alert(1)</script>"}
    reviewed = client.patch(f"/api/analyses/{id}/findings/finding-1", json=patch)
    schema("FindingReview", reviewed.json())
    assert client.get(f"/api/analyses/{id}/results").json()["findings"][0]["review_status"] == "confirmed"
    html = client.get(f"/api/analyses/{id}/export?format=html")
    assert html.status_code == 200
    assert "<script>alert" not in html.text and "&lt;script&gt;" in html.text
    assert "annual report" in html.text and "default-src 'none'" in html.headers["content-security-policy"]
    csv = client.get(f"/api/analyses/{id}/export?format=csv")
    assert csv.content.startswith(b"\xef\xbb\xbf") and "confirmed" in csv.text
    assert start(client, state, "flow-key").status_code == 200
    assert start(client, state, "another-key").status_code == 200
    with closing(sqlite3.connect(settings.data_dir / "qurylym.sqlite3")) as c:
        assert c.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        assert c.execute("SELECT count(*) FROM reviews").fetchone()[0] == 1
        versions = c.execute("SELECT revision,state FROM analysis_versions ORDER BY revision").fetchall()
        assert [v[0] for v in versions] == [1, 2, 3]
        assert [len(json.loads(v[1])["documents"]) for v in versions] == [0, 1, 2]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"expected_revision": "1"},
        {"expected_revision": True},
        {"expected_revision": 0},
        {"expected_revision": 1, "extra": 1},
    ],
)
def test_validation_errors_use_contract(client, body):
    state = client.post("/api/analyses").json()
    response = client.post(f"/api/analyses/{state['analysis_id']}/run", json=body, headers={"Idempotency-Key": "key"})
    assert response.status_code == 422
    schema("Error", response.json())


def test_isolation_foreign_sources_and_files(client, app):
    state = prepared(client)
    assert start(client, state).status_code == 202
    finish(client, state)
    id = state["analysis_id"]
    result = client.get(f"/api/analyses/{id}/results").json()
    ref = result["functions"][0]["source_span_ids"][0]
    other = client.post("/api/analyses").json()["analysis_id"]
    assert client.get(f"/api/analyses/{other}/sources/{ref}").status_code == 404
    assert client.get(f"/api/analyses/{other}/documents/{state['documents'][0]['id']}/download").status_code == 404
    cookie = client.cookies.get(COOKIE)
    client.cookies.clear()
    for suffix in ("", "/results", "/export?format=html", f"/sources/{ref}"):
        assert client.get(f"/api/analyses/{id}{suffix}").status_code == 404
    client.post("/api/analyses")
    assert client.cookies.get(COOKIE) != cookie
    assert client.get(f"/api/analyses/{id}").status_code == 404
    assert (
        client.patch(
            f"/api/analyses/{id}/findings/finding-1",
            json={"analysis_revision": 3, "review_status": "confirmed", "note": ""},
        ).status_code
        == 404
    )


def test_revisions_stale_result_and_duplicate(client):
    state = prepared(client)
    id, doc = state["analysis_id"], state["documents"][0]["id"]
    assert upload(client, id, "before").status_code == 409
    assert start(client, {**state, "analysis_revision": 1}).status_code == 409
    assert start(client, state, "revision-key").status_code == 202
    finish(client, state)
    response = upload(client, id, "before", docx_bytes("2.1. A new obligation."))
    assert response.status_code == 201 and response.json()["analysis_revision"] == 4
    assert client.get(f"/api/analyses/{id}/results").status_code == 409
    assert (
        client.patch(
            f"/api/analyses/{id}/findings/finding-1",
            json={"analysis_revision": 3, "review_status": "confirmed", "note": "stale"},
        ).status_code
        == 409
    )
    assert start(client, response.json(), "revision-key").status_code == 409
    patch = client.patch(f"/api/analyses/{id}/documents/{doc}", json={"expected_revision": 4, "version": "before"})
    assert patch.json()["analysis_revision"] == 4
    assert (
        client.patch(
            f"/api/analyses/{id}/documents/{doc}", json={"expected_revision": 4, "version": "after"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "filename,content,code", [("old.doc", b"abc", 400), ("bad.docx", b"bad zip", 400), ("empty.pdf", b"", 400)]
)
def test_bad_uploads(client, filename, content, code):
    state = client.post("/api/analyses").json()
    response = upload(client, state["analysis_id"], "before", content, filename)
    assert response.status_code == code
    schema("Error", response.json())
    assert client.get(f"/api/analyses/{state['analysis_id']}").json()["analysis_revision"] == 1


def test_missing_group_and_key(client):
    state = client.post("/api/analyses").json()
    assert start(client, state).status_code == 400
    response = client.post(f"/api/analyses/{state['analysis_id']}/run", json={"expected_revision": 1})
    assert response.status_code == 422


def test_busy_and_idempotency(settings):
    async def slow(payload, emit_progress=None):
        await asyncio.sleep(0.35)
        return result_for(payload)

    with TestClient(create_app(settings, engine=slow, parser=parse_document)) as c:
        one, two = prepared(c), prepared(c)
        assert start(c, one, "same").status_code == 202
        assert start(c, one, "same").status_code == 202
        assert start(c, two, "same").json()["code"] == "idempotency_conflict"
        assert start(c, two).json()["code"] == "server_busy"
        assert upload(c, one["analysis_id"], "before", docx_bytes("2.1. New")).status_code == 409
        assert (
            c.patch(
                f"/api/analyses/{one['analysis_id']}/documents/{one['documents'][0]['id']}",
                json={"expected_revision": 3, "version": "after"},
            ).status_code
            == 409
        )
        assert c.get("/api/health").status_code == 200
        assert finish(c, one)["status"] == "completed"


@pytest.mark.parametrize("mode", ["invalid", "exception", "timeout"])
def test_engine_failure_no_secret_leak(settings, mode):
    async def engine(payload, emit_progress=None):
        if mode == "timeout":
            await asyncio.sleep(10)
        if mode == "exception":
            raise RuntimeError("sk-secret-do-not-leak")
        result = result_for(payload)
        result["coverage"]["full"] = 999
        return result

    with TestClient(create_app(replace(settings, analysis_timeout=0.1), engine=engine, parser=parse_document)) as c:
        state = prepared(c)
        assert start(c, state, "failing").status_code == 202
        current = finish(c, state)
        assert current["status"] == "failed"
        assert "sk-secret" not in json.dumps(current)
        assert start(c, state, "failing").status_code == 409
        assert c.get(f"/api/analyses/{state['analysis_id']}/results").status_code == 409


def test_runtime_never_uses_fake(settings, monkeypatch):
    # This case also runs after the real AI package has been merged into the repo.
    monkeypatch.setattr("backend.app.workers.importlib.util.find_spec", lambda name: None)
    with TestClient(create_app(settings, parser=parse_document)) as c:
        state = prepared(c)
        response = start(c, state)
        assert response.status_code == 500 and response.json()["code"] == "engine_unavailable"
        assert c.get(f"/api/analyses/{state['analysis_id']}").json()["status"] == "uploaded"


def test_restart_and_review_history(settings):
    with TestClient(create_app(settings, engine=fake_engine, parser=parse_document)) as c:
        state = prepared(c)
        start(c, state)
        finish(c, state)
        id = state["analysis_id"]
        c.patch(
            f"/api/analyses/{id}/findings/finding-1",
            json={"analysis_revision": 3, "review_status": "rejected", "note": "Saved"},
        )
        cookie = c.cookies.get(COOKIE)
    with TestClient(create_app(settings, engine=fake_engine, parser=parse_document)) as c:
        c.cookies.set(COOKIE, cookie)
        assert c.get(f"/api/analyses/{id}/results").json()["findings"][0]["review_status"] == "rejected"
        assert "Saved" in c.get(f"/api/analyses/{id}/export?format=html").text
        state = upload(c, id, "before", docx_bytes("3.1. Additional task")).json()
        start(c, state)
        finish(c, state)
        assert c.get(f"/api/analyses/{id}/results").json()["findings"][0]["review_status"] == "unreviewed"


def test_request_limits_and_origin(settings):
    with TestClient(create_app(replace(settings, max_file_bytes=32), engine=fake_engine, parser=parse_document)) as c:
        state = c.post("/api/analyses").json()
        response = upload(c, state["analysis_id"], "before", b"x" * 33)
        assert response.status_code == 400
        response = c.post("/api/analyses", content=b"x" * 140000)
        assert response.status_code == 400
        assert c.post("/api/analyses", headers={"Origin": "https://attacker.invalid"}).status_code == 400


def test_access_token_and_cors(settings):
    with TestClient(
        create_app(replace(settings, access_token="test-access", allowed_origins=("http://localhost:5173",)))
    ) as c:
        assert c.post("/api/analyses").status_code == 404
        response = c.post(
            "/api/analyses", headers={"Authorization": "Bearer test-access", "Origin": "http://localhost:5173"}
        )
        assert response.status_code == 201
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert "HttpOnly" in response.headers["set-cookie"]


def test_unknown_api_and_static_traversal(client):
    for route in ("/api/nope", "/.env", "/backend-assets/../main.py", "/%2e%2e/%2e%2e/.env"):
        response = client.get(route)
        assert response.status_code == 404
        schema("Error", response.json())


def test_real_parser_process(settings):
    with TestClient(create_app(replace(settings, parse_timeout=20))) as c:
        state = c.post("/api/analyses").json()
        t = time.monotonic()
        response = upload(c, state["analysis_id"], "before")
        assert response.status_code == 201, response.text
        assert response.json()["documents"][0]["parse_status"] == "complete"
        response = upload(c, state["analysis_id"], "after", b"not a zip")
        assert response.status_code == 400 and response.json()["code"] == "invalid_container"
        assert time.monotonic() - t < 30
