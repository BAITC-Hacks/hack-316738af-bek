"""SQLite transactions own revisions, idempotency and the single active job.

Original bytes live in SQLite too: an upload is either committed in full or not at all.
Every lookup is scoped to its analysis and its unguessable browser session.
"""

import json
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone

from .errors import APIError, conflict, not_found
from .models import AnalysisState


def dumps(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def now():
    return datetime.now(timezone.utc).isoformat()


def progress(stage, message, processed=0, total=None):
    return {"stage": stage, "processed": processed, "total": total, "message": message}


class Store:
    def __init__(self, path):
        self.path = path

    @contextmanager
    def transaction(self):
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.executescript("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analysis_versions (
                    analysis_id TEXT NOT NULL REFERENCES analyses(id), revision INTEGER NOT NULL,
                    state TEXT NOT NULL, PRIMARY KEY(analysis_id, revision)
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL REFERENCES analyses(id),
                    metadata TEXT NOT NULL, sha256 TEXT NOT NULL, version TEXT NOT NULL,
                    original BLOB NOT NULL, UNIQUE(analysis_id, sha256, version)
                );
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL REFERENCES analyses(id),
                    document_id TEXT NOT NULL REFERENCES documents(id), data TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS sources_analysis ON sources(analysis_id, document_id);
                CREATE TABLE IF NOT EXISTS results (
                    analysis_id TEXT NOT NULL REFERENCES analyses(id), revision INTEGER NOT NULL,
                    data TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(analysis_id, revision)
                );
                CREATE TABLE IF NOT EXISTS reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, analysis_id TEXT NOT NULL REFERENCES analyses(id),
                    revision INTEGER NOT NULL, finding_id TEXT NOT NULL, data TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, analysis_id TEXT NOT NULL REFERENCES analyses(id),
                    revision INTEGER NOT NULL, status TEXT NOT NULL, error TEXT,
                    created_at TEXT NOT NULL, finished_at TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_job ON jobs((1)) WHERE status='running';
                CREATE TABLE IF NOT EXISTS idempotency (
                    key TEXT PRIMARY KEY, analysis_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    job_id TEXT REFERENCES jobs(id)
                );
                PRAGMA user_version=1;
            """)

    def ping(self):
        with closing(sqlite3.connect(self.path, timeout=2)) as connection:
            connection.execute("SELECT id FROM analyses LIMIT 1").fetchone()

    def _get(self, c, analysis_id, owner):
        row = c.execute("SELECT state FROM analyses WHERE id=? AND owner=?", (analysis_id, owner)).fetchone()
        if row is None:
            raise not_found()
        return json.loads(row["state"])

    def _save(self, c, state):
        AnalysisState.model_validate(state)
        c.execute("UPDATE analyses SET state=? WHERE id=?", (dumps(state), state["analysis_id"]))
        c.execute(
            "INSERT INTO analysis_versions VALUES (?,?,?) ON CONFLICT(analysis_id,revision) DO UPDATE SET state=excluded.state",
            (state["analysis_id"], state["analysis_revision"], dumps(state)),
        )

    def _mutable(self, c, state, expected=None):
        if expected is not None and expected != state["analysis_revision"]:
            raise conflict()
        if c.execute("SELECT 1 FROM jobs WHERE analysis_id=? AND status='running'", (state["analysis_id"],)).fetchone():
            raise conflict("analysis_busy", "Талдау орындалуда. Аяқталғаннан кейін өзгертіңіз.")

    def _changed(self, state):
        state["analysis_revision"] += 1
        state["status"] = "uploaded"
        state["progress"] = progress("uploaded", "Құжаттар жаңартылды. Жаңа талдау қажет.")
        state["warnings"] = [warning for document in state["documents"] for warning in document["warnings"]]

    def create(self, owner):
        state = {
            "schema_version": "1.0.0",
            "analysis_id": "ana_" + uuid.uuid4().hex,
            "analysis_revision": 1,
            "status": "uploaded",
            "documents": [],
            "warnings": [],
            "progress": progress("uploaded", "Дейін және кейін құжаттарын жүктеңіз."),
        }
        with self.transaction() as c:
            c.execute("INSERT INTO analyses VALUES (?,?,?,?)", (state["analysis_id"], owner, dumps(state), now()))
            self._save(c, state)
        return state

    def state(self, analysis_id, owner):
        with self.transaction() as c:
            return self._get(c, analysis_id, owner)

    def upload_preflight(self, analysis_id, owner, max_files):
        with self.transaction() as c:
            state = self._get(c, analysis_id, owner)
            self._mutable(c, state)
            if len(state["documents"]) >= max_files:
                raise APIError(400, "file_limit", f"Бір талдауға ең көбі {max_files} файл жүктеледі.")

    def add_document(self, analysis_id, owner, document, content, max_files):
        metadata = {k: v for k, v in document.items() if k != "spans"}
        with self.transaction() as c:
            state = self._get(c, analysis_id, owner)
            self._mutable(c, state)
            if len(state["documents"]) >= max_files:
                raise APIError(400, "file_limit", f"Бір талдауға ең көбі {max_files} файл жүктеледі.")
            duplicate = c.execute(
                "SELECT 1 FROM documents WHERE analysis_id=? AND sha256=? AND version=?",
                (analysis_id, document["source_sha256"], document["version"]),
            ).fetchone()
            if duplicate:
                raise conflict("duplicate_document", "Осы файл таңдалған топқа бұрын жүктелген.")
            c.execute(
                "INSERT INTO documents VALUES (?,?,?,?,?,?)",
                (document["id"], analysis_id, dumps(metadata), document["source_sha256"], document["version"], content),
            )
            c.executemany(
                "INSERT INTO sources VALUES (?,?,?,?)",
                [(s["id"], analysis_id, document["id"], dumps(s)) for s in document["spans"]],
            )
            state["documents"].append(metadata)
            self._changed(state)
            self._save(c, state)
        return state

    def move_document(self, analysis_id, owner, document_id, expected, version):
        with self.transaction() as c:
            state = self._get(c, analysis_id, owner)
            self._mutable(c, state, expected)
            document = next((d for d in state["documents"] if d["id"] == document_id), None)
            if document is None:
                raise not_found()
            if document["version"] == version:
                return state
            if any(
                d["id"] != document_id and d["version"] == version and d["source_sha256"] == document["source_sha256"]
                for d in state["documents"]
            ):
                raise conflict("duplicate_document", "Бұл топта бірдей файл бар.")
            document["version"] = version
            c.execute("UPDATE documents SET version=?, metadata=? WHERE id=?", (version, dumps(document), document_id))
            self._changed(state)
            self._save(c, state)
            return state

    def source(self, analysis_id, owner, span_id):
        with self.transaction() as c:
            state = self._get(c, analysis_id, owner)
            rows = c.execute("SELECT data FROM sources WHERE analysis_id=?", (analysis_id,)).fetchall()
            spans = {s["id"]: s for row in rows if (s := json.loads(row["data"]))}
            if span_id not in spans:
                raise not_found()
            source = spans[span_id]
            return {
                "document": next(d for d in state["documents"] if d["id"] == source["document_id"]),
                "source": source,
                "context": [spans[s] for s in source["context_span_ids"]],
            }

    def download(self, analysis_id, owner, document_id):
        with self.transaction() as c:
            self._get(c, analysis_id, owner)
            row = c.execute(
                "SELECT metadata,original FROM documents WHERE id=? AND analysis_id=?", (document_id, analysis_id)
            ).fetchone()
            if row is None:
                raise not_found()
            return json.loads(row["metadata"]), row["original"]

    def claim(self, analysis_id, owner, revision, key):
        """Return state/status, optional job ID and an immutable input snapshot."""
        with self.transaction() as c:
            state = self._get(c, analysis_id, owner)
            if revision != state["analysis_revision"]:
                raise conflict()
            prior = c.execute("SELECT * FROM idempotency WHERE key=?", (key,)).fetchone()
            if prior:
                if prior["analysis_id"] != analysis_id or prior["revision"] != revision:
                    raise conflict("idempotency_conflict", "Idempotency-Key басқа сұрауға қолданылған.")
                job = c.execute("SELECT status FROM jobs WHERE id=?", (prior["job_id"],)).fetchone()
                if job and job["status"] == "failed":
                    raise conflict(
                        "previous_run_failed",
                        "Алдыңғы әрекет үзілді. Қайта талдау үшін жаңа Idempotency-Key жіберіңіз.",
                    )
                return state, 202 if job and job["status"] == "running" else 200, None, None
            if state["status"] in ("completed", "partial"):
                c.execute("INSERT INTO idempotency VALUES (?,?,?,NULL)", (key, analysis_id, revision))
                return state, 200, None, None
            if c.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():
                raise conflict("server_busy", "Серверде бір талдау орындалуда. Кейін қайта көріңіз.")
            if not all(
                any(
                    d["version"] == v and d["parse_status"] in ("complete", "partial") and d["span_count"] > 0
                    for d in state["documents"]
                )
                for v in ("before", "after")
            ):
                raise APIError(400, "documents_required", "Әр топқа кемінде бір оқылатын құжат жүктеңіз.")
            job_id = uuid.uuid4().hex
            c.execute("INSERT INTO jobs VALUES (?,?,?,'running',NULL,?,NULL)", (job_id, analysis_id, revision, now()))
            c.execute("INSERT INTO idempotency VALUES (?,?,?,?)", (key, analysis_id, revision, job_id))
            state["status"] = "extracting"
            state["progress"] = progress("extracting", "Функцияларды шығару басталды.", 0, len(state["documents"]))
            state["warnings"] = [w for d in state["documents"] for w in d["warnings"]]
            self._save(c, state)
            documents = []
            for d in state["documents"]:
                spans = [
                    json.loads(r["data"])
                    for r in c.execute(
                        "SELECT data FROM sources WHERE analysis_id=? AND document_id=? ORDER BY rowid",
                        (analysis_id, d["id"]),
                    )
                ]
                documents.append({**d, "spans": spans})
            payload = {
                "schema_version": "1.0.0",
                "analysis_id": analysis_id,
                "analysis_revision": revision,
                "documents": documents,
            }
            return state, 202, job_id, payload

    def update_progress(self, job_id, event):
        with self.transaction() as c:
            job = c.execute("SELECT * FROM jobs WHERE id=? AND status='running'", (job_id,)).fetchone()
            if job is None:
                return
            row = c.execute("SELECT state FROM analyses WHERE id=?", (job["analysis_id"],)).fetchone()
            state = json.loads(row["state"])
            # A provider cannot publish completion before validation and persistence.
            if event["stage"] not in ("extracting", "matching", "verifying"):
                return
            order = {"extracting": 0, "matching": 1, "verifying": 2}
            if order[event["stage"]] < order.get(state["status"], 0):
                return
            state["status"], state["progress"] = event["stage"], event
            self._save(c, state)

    def finish(self, job_id, result=None, error=None):
        with self.transaction() as c:
            job = c.execute("SELECT * FROM jobs WHERE id=? AND status='running'", (job_id,)).fetchone()
            if job is None:
                return
            state = json.loads(
                c.execute("SELECT state FROM analyses WHERE id=?", (job["analysis_id"],)).fetchone()["state"]
            )
            if result is not None:
                state["status"] = result["status"]
                state["progress"] = progress(
                    result["status"], "Талдау сақталды.", len(state["documents"]), len(state["documents"])
                )
                state["warnings"] = result["warnings"]
                c.execute(
                    "INSERT INTO results VALUES (?,?,?,?)", (job["analysis_id"], job["revision"], dumps(result), now())
                )
            else:
                error = error or {"code": "analysis_failed", "message": "Талдау аяқталмады.", "retryable": True}
                state["status"] = "failed"
                state["progress"] = progress("failed", error["message"])
                state["warnings"].append(
                    {"code": error["code"], "message": error["message"], "document_id": None, "span_ids": []}
                )
            self._save(c, state)
            c.execute(
                "UPDATE jobs SET status=?,error=?,finished_at=? WHERE id=?",
                (state["status"], dumps(error) if error else None, now(), job_id),
            )

    def recover(self):
        with self.transaction() as c:
            jobs = [r["id"] for r in c.execute("SELECT id FROM jobs WHERE status='running'")]
        for job_id in jobs:
            self.finish(
                job_id,
                error={
                    "code": "server_restarted",
                    "message": "Сервер қайта қосылды. Талдауды жаңа кілтпен қайта бастаңыз.",
                    "retryable": True,
                },
            )

    def _result(self, c, analysis_id, owner):
        state = self._get(c, analysis_id, owner)
        row = c.execute(
            "SELECT data FROM results WHERE analysis_id=? AND revision=?", (analysis_id, state["analysis_revision"])
        ).fetchone()
        if row is None:
            raise conflict("result_not_ready", "Осы нұсқаның нәтижесі әлі дайын емес.")
        result = json.loads(row["data"])
        reviews = {}
        for row in c.execute(
            "SELECT data FROM reviews WHERE analysis_id=? AND revision=? ORDER BY id",
            (analysis_id, state["analysis_revision"]),
        ):
            review = json.loads(row["data"])
            reviews[review["finding_id"]] = review
        for finding in result["findings"]:
            if finding["id"] in reviews:
                finding["review_status"] = reviews[finding["id"]]["review_status"]
        return result, reviews

    def result(self, analysis_id, owner):
        with self.transaction() as c:
            return self._result(c, analysis_id, owner)

    def report_snapshot(self, analysis_id, owner):
        from .validation import evidence_references

        with self.transaction() as c:
            result, reviews = self._result(c, analysis_id, owner)
            documents = {d["id"]: d for d in result["documents"]}
            spans = {
                s["id"]: s
                for row in c.execute("SELECT data FROM sources WHERE analysis_id=?", (analysis_id,))
                if (s := json.loads(row["data"]))
            }
            wanted = list(dict.fromkeys(evidence_references(result)))
            # Include parser context even when the engine did not explicitly repeat it.
            for ref in wanted:
                for context in spans[ref]["context_span_ids"]:
                    if context not in wanted:
                        wanted.append(context)
            evidence = {ref: {"source": spans[ref], "document": documents[spans[ref]["document_id"]]} for ref in wanted}
            return result, reviews, evidence

    def review(self, analysis_id, owner, finding_id, patch):
        with self.transaction() as c:
            state = self._get(c, analysis_id, owner)
            self._mutable(c, state, patch["analysis_revision"])
            result, _ = self._result(c, analysis_id, owner)
            if not any(f["id"] == finding_id for f in result["findings"]):
                raise not_found()
            review = {"finding_id": finding_id, **patch, "reviewed_at": now()}
            c.execute(
                "INSERT INTO reviews(analysis_id,revision,finding_id,data) VALUES (?,?,?,?)",
                (analysis_id, patch["analysis_revision"], finding_id, dumps(review)),
            )
            return review
