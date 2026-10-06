"""SQLite persistence: durable jobs, optimistic revisions, and append-only audit events."""

import hashlib
import json
import os
import sqlite3
import subprocess
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .extraction import extract
from .models import set_path
from .reconcile import reconcile


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class Conflict(ValueError):
    pass


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.files = root / "files"
        self.previews = root / "previews"
        self.files.mkdir(exist_ok=True)
        self.previews.mkdir(exist_ok=True)
        self.db_path = root / "auditflow.db"
        self.database_url = os.environ.get("TURSO_DATABASE_URL")
        self.database_token = os.environ.get("TURSO_AUTH_TOKEN", "")
        if (
            os.environ.get("AUDITFLOW_REQUIRE_MANAGED_STORAGE", "").lower() == "true"
            and not self.database_url
        ):
            raise RuntimeError(
                "This deployment requires its managed SQL database and private file store."
            )
        self.cloud_files = None
        if self.database_url:
            if not self.database_token or not os.environ.get("BLOB_READ_WRITE_TOKEN"):
                raise RuntimeError(
                    "Managed SQL and private Blob credentials are required together."
                )
            from .cloud import Files

            self.cloud_files = Files(root)
        self.wake = threading.Event()
        self.stop = threading.Event()
        self.worker = None
        with self.connection() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL DEFAULT 'processing', revision INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL, result TEXT, is_demo INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
                    kind TEXT NOT NULL, filename TEXT NOT NULL, digest TEXT NOT NULL, path TEXT NOT NULL,
                    size INTEGER NOT NULL, extraction TEXT, UNIQUE(case_id,kind)
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, case_id TEXT NOT NULL UNIQUE REFERENCES cases(id),
                    state TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT, duration_ms INTEGER, error TEXT,
                    lease_until REAL, claim_token TEXT
                );
                CREATE TABLE IF NOT EXISTS audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, case_id TEXT NOT NULL REFERENCES cases(id),
                    document_id TEXT, action TEXT NOT NULL, actor TEXT NOT NULL,
                    payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS audit_case_idx ON audit(case_id,sequence);
                CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit
                    BEGIN SELECT RAISE(ABORT,'Audit events are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit
                    BEGIN SELECT RAISE(ABORT,'Audit events are immutable'); END;
            """)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(jobs)")}
            for name, kind in (("lease_until", "REAL"), ("claim_token", "TEXT")):
                if name not in columns:
                    db.execute(f"ALTER TABLE jobs ADD COLUMN {name} {kind}")

    @contextmanager
    def connection(self):
        if self.database_url:
            from .cloud import Database

            db = Database(self.database_url, self.database_token)
        else:
            db = sqlite3.connect(self.db_path, timeout=20)
            db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def event(db, case_id, action, payload, document_id=None, actor="AuditFlow"):
        db.execute(
            "INSERT INTO audit(case_id,document_id,action,actor,payload,created_at) VALUES(?,?,?,?,?,?)",
            (case_id, document_id, action, actor, encode(payload), now()),
        )

    def submit(
        self, uploads: list[tuple[str, str, bytes]], demo=False, created_at=None
    ) -> tuple[str, bool]:
        prepared = []
        for kind, filename, content in uploads:
            digest = hashlib.sha256(content).hexdigest()
            suffix = Path(filename).suffix.lower()
            path = self.files / f"{digest}{suffix}"
            if not path.exists():
                # All content is addressed by SHA256; no user-controlled storage paths.
                temporary = self.files / f".{digest}-{uuid.uuid4().hex}.tmp"
                temporary.write_bytes(content)
                temporary.replace(path)
            if self.cloud_files:
                self.cloud_files.save(path)
            stored_path = path.relative_to(self.root).as_posix() if self.cloud_files else str(path)
            prepared.append((kind, Path(filename).name[:200], digest, stored_path, len(content)))
        fingerprint = hashlib.sha256(
            encode(sorted((p[0], p[2]) for p in prepared)).encode()
        ).hexdigest()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT id FROM cases WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
            if existing:
                return existing["id"], False
            case_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO cases(id,fingerprint,created_at,is_demo) VALUES(?,?,?,?)",
                (case_id, fingerprint, created_at or now(), int(demo)),
            )
            for kind, filename, digest, path, size in prepared:
                db.execute(
                    "INSERT INTO documents(id,case_id,kind,filename,digest,path,size) VALUES(?,?,?,?,?,?,?)",
                    (uuid.uuid4().hex, case_id, kind, filename, digest, path, size),
                )
            db.execute(
                "INSERT INTO jobs(id,case_id,created_at) VALUES(?,?,?)",
                (uuid.uuid4().hex, case_id, now()),
            )
            self.event(
                db, case_id, "uploaded", {"filenames": [p[1] for p in prepared], "demo": demo}
            )
        self.wake.set()
        return case_id, True

    def documents(self, db, case_id):
        docs = []
        for row in db.execute(
            "SELECT * FROM documents WHERE case_id=? ORDER BY CASE kind WHEN 'invoice' THEN 0 WHEN 'purchase_order' THEN 1 ELSE 2 END",
            (case_id,),
        ):
            item = dict(row)
            item.pop("path", None)
            extraction = json.loads(item.pop("extraction")) if item.get("extraction") else {}
            docs.append({**item, **extraction})
        return docs

    def case(self, case_id):
        with self.connection() as db:
            row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not row:
                raise KeyError(case_id)
            result = json.loads(row["result"]) if row["result"] else None
            docs = self.documents(db, case_id)
            job = dict(db.execute("SELECT * FROM jobs WHERE case_id=?", (case_id,)).fetchone())
            job.pop("claim_token", None)
            job.pop("lease_until", None)
            events = [
                {**dict(event), "payload": json.loads(event["payload"])}
                for event in db.execute(
                    "SELECT * FROM audit WHERE case_id=? ORDER BY sequence DESC", (case_id,)
                )
            ]
            invoice = next((d.get("record") for d in docs if d["kind"] == "invoice"), None)
            return {
                "id": case_id,
                "status": row["status"],
                "revision": row["revision"],
                "created_at": row["created_at"],
                "is_demo": bool(row["is_demo"]),
                "invoice": invoice,
                "documents": docs,
                "result": result,
                "job": job,
                "audit": events,
            }

    def cases(self):
        with self.connection() as db:
            rows = db.execute("SELECT * FROM cases ORDER BY created_at DESC, rowid DESC").fetchall()
            jobs = {row["case_id"]: dict(row) for row in db.execute("SELECT * FROM jobs")}
            documents = db.execute(
                "SELECT case_id,kind,filename,extraction FROM documents ORDER BY CASE kind WHEN 'invoice' THEN 0 WHEN 'purchase_order' THEN 1 ELSE 2 END"
            ).fetchall()
        grouped = {}
        for document in documents:
            grouped.setdefault(document["case_id"], []).append(document)
        cases = []
        for row in rows:
            docs = grouped[row["id"]]
            invoice = next((d for d in docs if d["kind"] == "invoice"), None)
            extraction = (
                json.loads(invoice["extraction"]) if invoice and invoice["extraction"] else {}
            )
            job = jobs[row["id"]]
            job.pop("claim_token", None)
            job.pop("lease_until", None)
            cases.append(
                {
                    **{key: row[key] for key in ("id", "status", "revision", "created_at")},
                    "is_demo": bool(row["is_demo"]),
                    "invoice": extraction.get("record"),
                    "result": json.loads(row["result"]) if row["result"] else None,
                    "job": job,
                    "document_count": len(docs),
                    "filename": docs[0]["filename"],
                }
            )
        return cases

    def refresh(self, db, primary_id=None):
        previous = []
        for row in db.execute(
            "SELECT cases.*,jobs.state AS job_state FROM cases JOIN jobs ON cases.id=jobs.case_id ORDER BY cases.rowid"
        ).fetchall():
            if row["job_state"] != "completed" and row["id"] != primary_id:
                continue
            if row["result"] is None and row["id"] != primary_id:
                continue
            docs = self.documents(db, row["id"])
            result = reconcile(docs, previous)
            old_result = json.loads(row["result"]) if row["result"] else None
            changed = old_result != result
            status = result["status"]
            if (
                row["status"] in ("approved", "rejected")
                and not changed
                and row["id"] != primary_id
            ):
                status = row["status"]
            if changed or row["id"] == primary_id:
                if old_result:
                    db.execute("UPDATE cases SET revision=revision+1 WHERE id=?", (row["id"],))
                db.execute(
                    "UPDATE cases SET result=?,status=? WHERE id=?",
                    (encode(result), status, row["id"]),
                )
                self.event(
                    db,
                    row["id"],
                    "reconciled",
                    {
                        "status": status,
                        "flags": result["flags"],
                        "rule_version": result["rule_version"],
                    },
                )
                if row["status"] in ("approved", "rejected"):
                    self.event(
                        db,
                        row["id"],
                        "decision_invalidated",
                        {"reason": "Document values or related invoice evidence changed"},
                    )
            invoice = next((d.get("record") for d in docs if d["kind"] == "invoice"), None)
            if invoice:
                previous.append({"case_id": row["id"], "record": invoice})

    def document_path(self, path, digest=None):
        return self.cloud_files.load(path, digest) if self.cloud_files else Path(path)

    def preview_path(self, digest, page):
        key = f"previews/{digest}-{page}.png"
        return self.cloud_files.load(key) if self.cloud_files else self.root / key

    def process_one(self, case_id=None) -> bool:
        claim_token = uuid.uuid4().hex
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute(
                "SELECT * FROM jobs WHERE (state='queued' OR (state='running' AND COALESCE(lease_until,0)<?))"
                + (" AND case_id=?" if case_id else "")
                + " ORDER BY rowid LIMIT 1",
                (time.time(), case_id) if case_id else (time.time(),),
            ).fetchone()
            if not job:
                return False
            db.execute(
                "UPDATE jobs SET state='running',attempts=attempts+1,started_at=?,error=NULL,lease_until=?,claim_token=? WHERE id=?",
                (now(), time.time() + 330, claim_token, job["id"]),
            )
            documents = [
                dict(row)
                for row in db.execute("SELECT * FROM documents WHERE case_id=?", (job["case_id"],))
            ]
        started = time.monotonic()
        try:
            results = []
            for document in documents:
                try:
                    result = extract(
                        self.document_path(document["path"], document["digest"]),
                        document["kind"],
                        self.previews,
                        document["digest"],
                    )
                except (ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                    result = {
                        "record": None,
                        "fields": {},
                        "uncertain": [],
                        "errors": [str(exc)[:800]],
                        "pages": [],
                        "method": "failed",
                        "cost_usd": None,
                    }
                if self.cloud_files:
                    for page in result["pages"]:
                        self.cloud_files.save(
                            self.previews / f"{document['digest']}-{page['page']}.png"
                        )
                results.append((document, result))
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT claim_token FROM jobs WHERE id=?", (job["id"],)
                ).fetchone()
                if current["claim_token"] != claim_token:
                    return True
                for document, result in results:
                    db.execute(
                        "UPDATE documents SET extraction=? WHERE id=?",
                        (encode(result), document["id"]),
                    )
                    self.event(
                        db,
                        job["case_id"],
                        "extracted",
                        {
                            "kind": document["kind"],
                            "method": result["method"],
                            "field_count": len(result["fields"]),
                            "errors": result["errors"],
                        },
                        document["id"],
                    )
                self.refresh(db, job["case_id"])
                db.execute(
                    "UPDATE jobs SET state='completed',finished_at=?,duration_ms=?,lease_until=NULL WHERE id=?",
                    (now(), round((time.monotonic() - started) * 1000), job["id"]),
                )
        except Exception:
            # Detailed exceptions can carry provider content; expose a safe retry message.
            import logging

            logging.getLogger(__name__).error("Document job %s failed", job["id"])
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute(
                    "SELECT claim_token FROM jobs WHERE id=?", (job["id"],)
                ).fetchone()
                if current["claim_token"] != claim_token:
                    return True
                db.execute(
                    "UPDATE jobs SET state='failed',error=?,finished_at=?,lease_until=NULL WHERE id=?",
                    (
                        "Processing failed. Retry the job; check server configuration if the failure persists.",
                        now(),
                        job["id"],
                    ),
                )
                db.execute(
                    "UPDATE cases SET status='failed',revision=revision+1 WHERE id=?",
                    (job["case_id"],),
                )
                self.event(db, job["case_id"], "processing_failed", {"reason": "Processing failed"})
        return True

    def start_worker(self):
        with self.connection() as db:
            db.execute(
                "UPDATE jobs SET state='queued',error=NULL,lease_until=NULL WHERE state='running'"
            )
        self.stop.clear()

        def loop():
            while not self.stop.is_set():
                if not self.process_one():
                    self.wake.wait(1)
                    self.wake.clear()

        self.worker = threading.Thread(target=loop, name="auditflow-worker", daemon=True)
        self.worker.start()

    def stop_worker(self):
        self.stop.set()
        self.wake.set()
        if self.worker:
            self.worker.join(timeout=130)

    def correct(self, case_id, document_id, correction):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            case = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not case:
                raise KeyError(case_id)
            if case["revision"] != correction.expected_revision:
                raise Conflict("This case has changed. Refresh before saving your correction.")
            if case["status"] in ("processing", "failed"):
                raise ValueError("Wait for processing to complete before correcting values.")
            document = db.execute(
                "SELECT * FROM documents WHERE id=? AND case_id=?", (document_id, case_id)
            ).fetchone()
            if not document:
                raise KeyError(document_id)
            extraction = json.loads(document["extraction"])
            if not extraction["record"]:
                raise ValueError(
                    "This document needs to be uploaded again using a supported layout."
                )
            if correction.path not in extraction["fields"]:
                raise ValueError("This value has no extracted field to correct.")
            field = extraction["fields"][correction.path]
            updated = set_path(extraction["record"], correction.path, correction.value)
            pieces = correction.path.split(".")
            value = updated
            for piece in pieces:
                value = value[int(piece)] if isinstance(value, list) else value[piece]
            old_value = field["value"]
            if old_value == value:
                raise ValueError("Enter a different value to make a correction.")
            extraction["record"] = updated
            extraction["fields"][correction.path] = {
                **field,
                "value": value,
                "corrected": True,
                "confidence": 1,
            }
            extraction["uncertain"] = [p for p in extraction["uncertain"] if p != correction.path]
            db.execute(
                "UPDATE documents SET extraction=? WHERE id=?", (encode(extraction), document_id)
            )
            self.event(
                db,
                case_id,
                "corrected",
                {
                    "path": correction.path,
                    "before": old_value,
                    "after": value,
                    "reason": correction.reason,
                    "source": field["source"],
                    "extracted_value": field["extracted_value"],
                },
                document_id,
                "Reviewer",
            )
            self.refresh(db, case_id)
        return self.case(case_id)

    def decide(self, case_id, decision):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM cases WHERE id=?", (case_id,)).fetchone()
            if not row:
                raise KeyError(case_id)
            if row["revision"] != decision.expected_revision:
                raise Conflict("This case has changed. Refresh before submitting your decision.")
            if row["status"] in ("processing", "failed"):
                raise ValueError("Wait for processing to finish before making a decision.")
            docs = self.documents(db, case_id)
            if decision.action == "approve" and any(d.get("record") is None for d in docs):
                raise ValueError("All three documents must have validated records before approval.")
            status = "approved" if decision.action == "approve" else "rejected"
            if row["status"] == status:
                raise ValueError("This decision has already been recorded.")
            db.execute(
                "UPDATE cases SET status=?,revision=revision+1 WHERE id=?", (status, case_id)
            )
            self.event(
                db,
                case_id,
                decision.action,
                {
                    "note": decision.note,
                    "flags_acknowledged": json.loads(row["result"] or "{}").get("flags", []),
                    "revision": row["revision"],
                },
                actor="Reviewer",
            )
        return self.case(case_id)

    def retry(self, case_id):
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM jobs WHERE case_id=?", (case_id,)).fetchone()
            if not row:
                raise KeyError(case_id)
            if row["state"] in ("queued", "running"):
                raise ValueError("This job is already being processed.")
            docs = self.documents(db, case_id)
            if row["state"] != "failed" and not any(d.get("errors") for d in docs):
                raise ValueError("Only failed processing or failed extraction can be retried.")
            db.execute(
                "UPDATE jobs SET state='queued',error=NULL,lease_until=NULL WHERE case_id=?",
                (case_id,),
            )
            db.execute(
                "UPDATE cases SET status='processing',revision=revision+1 WHERE id=?", (case_id,)
            )
            self.event(db, case_id, "retried", {}, actor="Reviewer")
        self.wake.set()
