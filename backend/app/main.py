"""Run from repository root: python -m uvicorn backend.app.main:app --workers 1."""

import asyncio
import hashlib
import json
import os
import re
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import FastAPI, Header, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from filelock import FileLock, Timeout
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles

from . import models
from .config import ROOT, Settings
from .errors import APIError
from .exports import csv_report, html_report
from .parsers import RejectedFile
from .security import COOKIE, SafetyMiddleware, owner_for
from .storage import Store
from .workers import JobRunner, require_engine, run_process


def create_app(settings=None, *, engine=None, parser=None):
    settings = settings or Settings()
    store = Store(settings.data_dir / "qurylym.sqlite3")
    runner = JobRunner(store, settings, engine)
    parse_gate = asyncio.Semaphore(2)

    @asynccontextmanager
    async def lifespan(app):
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        lock = FileLock(settings.data_dir / "server.lock")
        try:
            lock.acquire(timeout=0)
        except Timeout as exc:
            raise RuntimeError("Use one server worker per DATA_DIR") from exc
        try:
            await asyncio.to_thread(store.initialize)
            await asyncio.to_thread(store.recover)
            yield
        finally:
            await runner.close()
            lock.release()

    app = FastAPI(title="Qurylym AI", version="1.0.0", lifespan=lifespan)
    app.state.store, app.state.runner = store, runner
    contract_path = ROOT / "contracts/openapi.json"
    contract_bytes = contract_path.read_bytes()
    expected_hash = (ROOT / "contracts/CONTRACT_SHA256.txt").read_text().split()[0]
    if hashlib.sha256(contract_bytes).hexdigest() != expected_hash:
        raise RuntimeError("Contract checksum mismatch; coordinate a versioned update")
    contract = json.loads(contract_bytes)
    app.openapi = lambda: contract
    app.add_middleware(SafetyMiddleware, max_file_bytes=settings.max_file_bytes)
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.allowed_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["Content-Type", "Idempotency-Key", "Authorization"],
        )

    @app.exception_handler(APIError)
    async def api_error(request, exc):
        return JSONResponse(exc.body, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {"code": "validation_error", "message": "Сұрау өрістері API келісіміне сай емес.", "retryable": False},
            status_code=422,
        )

    @app.exception_handler(RejectedFile)
    async def rejected_file(request, exc):
        return JSONResponse(
            {"code": str(exc), "message": "Файл бұзылған немесе қауіпсіз өңдеу шегінен асады.", "retryable": False},
            status_code=400,
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return JSONResponse(
            {
                "code": "not_found" if exc.status_code == 404 else "invalid_request",
                "message": "Сұралған маршрут/сұрау жарамсыз.",
                "retryable": False,
            },
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return JSONResponse(
            {"code": "internal_error", "message": "Ішкі қате. Сервер күйін тексеріңіз.", "retryable": True},
            status_code=500,
        )

    def owner(request):
        return owner_for(request, settings)[0]

    @app.get("/api/health", response_model=models.Health)
    async def health():
        await asyncio.to_thread(store.ping)
        return {
            "status": "ok",
            "schema_version": "1.0.0",
            "openai_configured": bool(os.getenv("OPENAI_API_KEY", "").strip()),
            "nvidia_configured": os.getenv("NVIDIA_ENABLED", "false").lower() == "true"
            and bool(os.getenv("NVIDIA_API_KEY", "").strip()),
        }

    @app.post("/api/analyses", response_model=models.AnalysisState, status_code=201)
    async def create(request: Request, response: Response):
        session_owner, token = owner_for(request, settings, create=True)
        state = await asyncio.to_thread(store.create, session_owner)
        response.set_cookie(
            COOKIE, token, httponly=True, secure=settings.secure_cookie, samesite="lax", max_age=30 * 86400, path="/"
        )
        return state

    @app.get("/api/analyses/{id}", response_model=models.AnalysisState)
    async def state(id: str, request: Request):
        return await asyncio.to_thread(store.state, id, owner(request))

    @app.post("/api/analyses/{id}/documents", response_model=models.AnalysisState, status_code=201)
    async def upload(id: str, request: Request):
        session_owner = owner(request)
        await asyncio.to_thread(store.upload_preflight, id, session_owner, settings.max_files)
        async with request.form(max_files=1, max_fields=1, max_part_size=1024) as form:
            if set(form.keys()) != {"file", "version"} or len(form.multi_items()) != 2:
                raise APIError(422, "validation_error", "Бір файл және before/after version өрісі қажет.")
            file, version = form["file"], form["version"]
            if not isinstance(file, UploadFile) or version not in ("before", "after"):
                raise APIError(422, "validation_error", "Бір файл және before/after version өрісі қажет.")
            filename = (file.filename or "").replace("\\", "/").split("/")[-1]
            filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)[:240]
            kind = Path(filename).suffix.lower().lstrip(".")
            if kind not in ("docx", "pdf", "xlsx"):
                raise APIError(
                    400,
                    "unsupported_format",
                    "Тек DOCX, мәтіндік PDF және XLSX қолданылады. DOC/XLS файлдарын түрлендіріңіз.",
                )
            content = await file.read(settings.max_file_bytes + 1)
            if not content or len(content) > settings.max_file_bytes:
                raise APIError(
                    400, "upload_too_large" if content else "empty_file", "Файл бос немесе 20 МБ шегінен асады."
                )
        arguments = (content, filename, kind, "doc_" + uuid.uuid4().hex, version, settings)
        async with parse_gate:
            document = (
                await run_process("parse", arguments, settings.parse_timeout)
                if parser is None
                else await asyncio.to_thread(parser, *arguments)
            )
        return await asyncio.to_thread(store.add_document, id, session_owner, document, content, settings.max_files)

    @app.patch("/api/analyses/{id}/documents/{document_id}", response_model=models.AnalysisState)
    async def move(id: str, document_id: str, patch: models.DocumentPatch, request: Request):
        return await asyncio.to_thread(
            store.move_document, id, owner(request), document_id, patch.expected_revision, patch.version
        )

    @app.post("/api/analyses/{id}/run", response_model=models.AnalysisState)
    async def run(
        id: str,
        body: models.RunRequest,
        request: Request,
        response: Response,
        idempotency_key: Annotated[str, Header(alias="Idempotency-Key")],
    ):
        session_owner = owner(request)
        if (
            not 1 <= len(idempotency_key) <= 200
            or not idempotency_key.isascii()
            or any(ord(c) < 33 or ord(c) > 126 for c in idempotency_key)
        ):
            raise APIError(422, "invalid_idempotency_key", "Idempotency-Key 1–200 ASCII таңбасынан тұруы тиіс.")
        current = await asyncio.to_thread(store.state, id, session_owner)
        if body.expected_revision != current["analysis_revision"]:
            from .errors import conflict

            raise conflict()
        if engine is None and current["status"] not in ("completed", "partial"):
            require_engine()
        state, code, job_id, payload = await asyncio.to_thread(
            store.claim, id, session_owner, body.expected_revision, idempotency_key
        )
        if job_id:
            runner.start(job_id, payload)
        response.status_code = code
        return state

    @app.get("/api/analyses/{id}/results", response_model=models.AnalysisResult)
    async def results(id: str, request: Request):
        result, _ = await asyncio.to_thread(store.result, id, owner(request))
        return result

    @app.get("/api/analyses/{id}/sources/{span_id}", response_model=models.SourceEvidence)
    async def source(id: str, span_id: str, request: Request):
        return await asyncio.to_thread(store.source, id, owner(request), span_id)

    @app.get("/api/analyses/{id}/documents/{document_id}/download")
    async def download(id: str, document_id: str, request: Request):
        document, content = await asyncio.to_thread(store.download, id, owner(request), document_id)
        return Response(
            content,
            media_type="application/octet-stream",
            headers={"Content-Disposition": "attachment; filename*=UTF-8''" + quote(document["filename"], safe="")},
        )

    @app.patch("/api/analyses/{id}/findings/{finding_id}", response_model=models.FindingReview)
    async def review(id: str, finding_id: str, patch: models.ReviewPatch, request: Request):
        return await asyncio.to_thread(store.review, id, owner(request), finding_id, patch.model_dump())

    @app.get("/api/analyses/{id}/export")
    async def export(id: str, format: Literal["html", "csv"], request: Request):
        session_owner = owner(request)
        result, reviews, evidence = await asyncio.to_thread(store.report_snapshot, id, session_owner)
        if format == "csv":
            content = await asyncio.to_thread(csv_report, result, reviews)
        else:
            content = await asyncio.to_thread(html_report, result, reviews, evidence)
        return Response(
            content,
            media_type="text/html" if format == "html" else "text/csv",
            headers={"Content-Disposition": f'attachment; filename="qurylym-{id}.{format}"'},
        )

    app.mount("/backend-assets", StaticFiles(directory=Path(__file__).parent / "static"), name="backend-assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def frontend(path: str):
        if path == "api" or path.startswith("api/"):
            raise APIError(404, "not_found", "API маршруты табылмады.")
        root = settings.frontend_dir.resolve()
        target = (root / path).resolve()
        if root not in target.parents and target != root:
            raise APIError(404, "not_found", "Файл табылмады.")
        if target.is_file() and not any(part.startswith(".") for part in Path(path).parts):
            return FileResponse(target)
        if (root / "index.html").is_file() and "." not in Path(path).name:
            return FileResponse(root / "index.html")
        if path:
            raise APIError(404, "not_found", "Бет табылмады.")
        return HTMLResponse((Path(__file__).parent / "static/index.html").read_text(encoding="utf-8"))

    return app


app = create_app()
