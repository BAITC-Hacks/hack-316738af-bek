import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app.parsers import parse_document
from backend.app.security import COOKIE
from backend.app.workers import run_process
from backend.tests.conftest import docx_bytes, fake_engine, finish, prepared, start, upload


def test_crash_recovery_preserves_documents(settings):
    with TestClient(create_app(settings, engine=fake_engine, parser=parse_document)) as c:
        state = prepared(c)
        cookie = c.cookies.get(COOKIE)
    database = settings.data_dir / "qurylym.sqlite3"
    with closing(sqlite3.connect(database)) as connection, connection:
        state["status"] = "matching"
        state["progress"] = {"stage": "matching", "processed": 1, "total": 2, "message": "Interrupted"}
        connection.execute("UPDATE analyses SET state=? WHERE id=?", (json.dumps(state), state["analysis_id"]))
        connection.execute(
            "INSERT INTO jobs VALUES ('crashed',?,3,'running',NULL,'2026-01-01',NULL)", (state["analysis_id"],)
        )
    with TestClient(create_app(settings, engine=fake_engine, parser=parse_document)) as c:
        c.cookies.set(COOKIE, cookie)
        current = c.get(f"/api/analyses/{state['analysis_id']}").json()
        assert current["status"] == "failed" and len(current["documents"]) == 2
        assert current["warnings"][-1]["code"] == "server_restarted"
        assert start(c, current).status_code == 202
        assert finish(c, current)["status"] == "completed"


def test_parallel_run_claim_is_atomic(settings):
    async def slow(payload, emit_progress=None):
        await asyncio.sleep(0.5)
        return await fake_engine(payload, emit_progress)

    with TestClient(create_app(settings, engine=slow, parser=parse_document)) as c:
        state = prepared(c)
        with ThreadPoolExecutor(max_workers=6) as pool:
            responses = list(pool.map(lambda _: start(c, state, "parallel"), range(6)))
        assert all(response.status_code == 202 for response in responses)
        assert finish(c, state)["status"] == "completed"
    with closing(sqlite3.connect(settings.data_dir / "qurylym.sqlite3")) as connection:
        assert connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_second_worker_cannot_recover_live_job(settings):
    with TestClient(create_app(settings)):
        with pytest.raises(RuntimeError, match="one server worker"):
            with TestClient(create_app(settings)):
                pass


def test_production_engine_process(settings, tmp_path, monkeypatch):
    package = tmp_path / "engine-module/ai_engine"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "pipeline.py").write_text("from backend.tests.conftest import fake_engine as analyze\n")
    monkeypatch.syspath_prepend(str(package.parent))
    with TestClient(create_app(replace(settings, analysis_timeout=15), parser=parse_document)) as c:
        state = prepared(c)
        assert start(c, state).status_code == 202
        assert finish(c, state)["status"] == "completed"


def test_worker_timeout_terminates_process(settings):
    arguments = (docx_bytes(), "test.docx", "docx", "test", "before", settings)
    with pytest.raises(Exception, match="parse_timeout"):
        asyncio.run(run_process("parse", arguments, 0.001))


def test_file_limit_and_group_change(settings):
    with TestClient(create_app(replace(settings, max_files=2), engine=fake_engine, parser=parse_document)) as c:
        state = prepared(c)
        assert upload(c, state["analysis_id"], "before", docx_bytes("3.1. Another")).status_code == 400
    with TestClient(
        create_app(replace(settings, data_dir=settings.data_dir / "move"), engine=fake_engine, parser=parse_document)
    ) as c:
        state = c.post("/api/analyses").json()
        state = upload(c, state["analysis_id"], "before").json()
        response = c.patch(
            f"/api/analyses/{state['analysis_id']}/documents/{state['documents'][0]['id']}",
            json={"expected_revision": 2, "version": "after"},
        )
        assert response.status_code == 200
        assert response.json()["analysis_revision"] == 3
        assert response.json()["documents"][0]["version"] == "after"


def test_partial_documents_cannot_be_completed(settings):
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    output = io.BytesIO()
    writer.write(output)
    with TestClient(create_app(settings, engine=fake_engine, parser=parse_document)) as c:
        state = prepared(c)
        state = upload(c, state["analysis_id"], "after", output.getvalue(), "scan.pdf").json()
        assert state["documents"][-1]["parse_status"] == "failed"
        start(c, state)
        current = finish(c, state)
        assert current["status"] == "partial"
        assert current["warnings"]
