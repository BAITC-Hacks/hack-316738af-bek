import asyncio
import io
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app.exports import csv_safe
from backend.app.main import create_app
from backend.app.parsers import parse_document
from backend.tests.conftest import docx_bytes, fake_engine, finish, prepared, start, upload


@pytest.mark.parametrize("form", [{"version": "before", "extra": "x"}, {"version": "invalid"}, {}])
def test_multipart_fields_exact(client, form):
    id = client.post("/api/analyses").json()["analysis_id"]
    response = client.post(f"/api/analyses/{id}/documents", data=form, files={"file": ("test.docx", docx_bytes())})
    assert response.status_code in (400, 422)
    assert set(response.json()) == {"code", "message", "retryable"}


def test_multiple_files_rejected(client):
    id = client.post("/api/analyses").json()["analysis_id"]
    response = client.post(
        f"/api/analyses/{id}/documents",
        data={"version": "before"},
        files=[("file", ("1.docx", docx_bytes())), ("file", ("2.docx", docx_bytes()))],
    )
    assert response.status_code == 400
    assert client.get(f"/api/analyses/{id}").json()["documents"] == []


def test_chunked_body_limit(client):
    def chunks():
        yield b"x" * 70_000
        yield b"y" * 70_000

    response = client.post(
        "/api/analyses/id/run",
        content=chunks(),
        headers={"content-type": "application/json", "Idempotency-Key": "test"},
    )
    assert response.status_code == 400
    assert set(response.json()) == {"code", "message", "retryable"}


def test_api_methods_match_frozen_contract(app):
    from backend.app.config import ROOT

    paths = json.loads((ROOT / "contracts/openapi.json").read_text(encoding="utf-8"))["paths"]
    for path, methods in paths.items():
        for method in methods:
            assert any(
                getattr(route, "path", None) == path and method.upper() in getattr(route, "methods", set())
                for route in app.routes
            )
    actual = {route.path for route in app.routes if getattr(route, "path", "").startswith("/api/")}
    assert actual == set(paths)


@pytest.mark.parametrize("value", ["\v=1", "\x1f=2", "＝cmd", "＋cmd", "＠SUM(A1)"])
def test_csv_unusual_formula_prefixes(value):
    assert csv_safe(value).startswith("'")


def test_xlsx_row_and_column_context(settings):
    workbook = Workbook()
    workbook.active.append(["Unit", "Function"])
    workbook.active.append(["Audit", "Prepare annual report"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    parsed = parse_document(buffer.getvalue(), "test.xlsx", "xlsx", "test", "before", settings)
    sources = {s["locator"]["cell_range"]: s for s in parsed["spans"]}
    assert sources["A2"]["id"] in sources["B2"]["context_span_ids"]
    assert sources["B1"]["id"] in sources["B2"]["context_span_ids"]
    assert sources["B2"]["id"] not in sources["B2"]["context_span_ids"]


def test_filename_not_a_storage_path(client):
    id = client.post("/api/analyses").json()["analysis_id"]
    response = upload(client, id, "before", filename="../../private.docx")
    assert response.status_code == 201
    assert response.json()["documents"][0]["filename"] == "private.docx"


def test_frontend_build_and_assets(settings):
    settings.frontend_dir.mkdir()
    (settings.frontend_dir / "index.html").write_text("<h1>Frontend test</h1>")
    (settings.frontend_dir / "app.js").write_text("// fixture")
    (settings.frontend_dir / ".env").write_text("should_not_escape")
    with TestClient(create_app(settings)) as c:
        assert "Frontend test" in c.get("/").text
        assert "Frontend test" in c.get("/analyses/example").text
        assert c.get("/app.js").text == "// fixture"
        assert c.get("/.env").status_code == 404
        assert c.get("/api/missing").status_code == 404


def test_typed_engine_error_is_safe(settings, tmp_path, monkeypatch):
    package = tmp_path / "typed-engine/ai_engine"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "errors.py").write_text(
        "class AnalysisError(Exception):\n    def __init__(self, code, message, retryable=False):\n        self.code, self.message, self.retryable = code, message, retryable\n"
    )
    (package / "pipeline.py").write_text(
        'from .errors import AnalysisError\nasync def analyze(payload, emit_progress=None):\n    raise AnalysisError("RATE_LIMIT", "sk-sensitive-provider-response", True)\n'
    )
    monkeypatch.syspath_prepend(str(package.parent))
    with TestClient(create_app(replace(settings, analysis_timeout=15), parser=parse_document)) as c:
        state = prepared(c)
        assert start(c, state).status_code == 202
        current = finish(c, state)
        assert current["status"] == "failed"
        assert current["warnings"][-1]["code"] == "RATE_LIMIT"
        assert "sk-sensitive" not in json.dumps(current)


def test_shutdown_cancels_job_and_releases_slot(settings):
    async def slow(payload, emit_progress=None):
        await asyncio.sleep(60)

    with TestClient(create_app(settings, engine=slow, parser=parse_document)) as c:
        state = prepared(c)
        assert start(c, state).status_code == 202
        cookie = c.cookies.get("qurylym_session")
    with TestClient(create_app(settings, engine=fake_engine, parser=parse_document)) as c:
        c.cookies.set("qurylym_session", cookie)
        current = c.get(f"/api/analyses/{state['analysis_id']}").json()
        assert current["status"] == "failed"
        assert start(c, current).status_code == 202
        assert finish(c, current)["status"] == "completed"
