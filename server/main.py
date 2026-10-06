import csv
import io
import json
import os
import re
import secrets
import shutil
import zipfile
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError
from starlette.concurrency import run_in_threadpool

from .demo import fixtures, render_document, seed
from .models import Correction, Decision
from .store import Conflict, Store

BASE = Path(__file__).resolve().parent.parent
MAX_FILE_SIZE = 20 * 1024 * 1024


class BlobReference(BaseModel):
    pathname: str = Field(max_length=240)
    filename: str = Field(min_length=1, max_length=200)


class BlobPacket(BaseModel):
    invoice: BlobReference
    purchase_order: BlobReference
    delivery: BlobReference


def validate_upload(kind, filename, content):
    extension = Path(filename).suffix.lower()
    if extension not in (".pdf", ".png", ".jpg", ".jpeg", ".txt"):
        raise HTTPException(422, "Use PDF, PNG, JPEG, or UTF-8 TXT documents.")
    if not content or len(content) > MAX_FILE_SIZE:
        raise HTTPException(422, "Each document must contain data and be under 20 MB.")
    if extension == ".pdf" and b"%PDF-" not in content[:1024]:
        raise HTTPException(422, "This file is not a valid PDF.")
    if extension == ".txt":
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            raise HTTPException(422, "Text documents must use UTF-8 encoding.")
    return kind, filename, content


def create_app(data_dir: Path | None = None, seed_demo: bool | None = None):
    store = Store(data_dir or Path(os.environ.get("AUDITFLOW_DATA_DIR", str(BASE / ".data"))))
    demo_enabled = (
        seed_demo
        if seed_demo is not None
        else os.environ.get("AUDITFLOW_SEED_DEMO", "true").lower() == "true"
    )
    queue_enabled = os.environ.get("AUDITFLOW_QUEUE_ENABLED", "").lower() == "true"

    async def dispatch(case_id):
        if queue_enabled:
            from vercel.queue import send

            await send("auditflow-documents", {"case_id": case_id})

    @asynccontextmanager
    async def lifespan(app):
        if demo_enabled:
            seed(store)
        with store.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            store.refresh(db)
        if queue_enabled:
            with store.connection() as db:
                pending = [
                    r["case_id"]
                    for r in db.execute("SELECT case_id FROM jobs WHERE state='queued'")
                ]
            for case_id in pending:
                await dispatch(case_id)
        else:
            store.start_worker()
        yield
        if not queue_enabled:
            store.stop_worker()

    app = FastAPI(title="AuditFlow", version="0.1.0", lifespan=lifespan)
    app.state.store = store
    allowed_origins = [
        origin.strip().rstrip("/")
        for origin in os.environ.get("AUDITFLOW_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    ]
    if allowed_origins:
        for origin in allowed_origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in ("http", "https")
                or not parsed.hostname
                or "*" in origin
                or any(character.isspace() for character in origin)
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "AUDITFLOW_ALLOWED_ORIGINS must contain exact HTTP(S) origins, not wildcards or paths."
                )
            # Accessing the port also rejects malformed or out-of-range values.
            _ = parsed.port
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["GET", "POST", "PATCH"],
            allow_headers=["Content-Type"],
            expose_headers=["Content-Disposition"],
        )

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse(
            status_code=404, content={"detail": "The requested record does not exist."}
        )

    @app.exception_handler(Conflict)
    async def conflict(request, exc):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        if isinstance(exc, ValidationError):
            return JSONResponse(
                status_code=422,
                content={
                    "detail": "The corrected value does not satisfy the document schema. Use a valid date, currency, or nonnegative numeric value."
                },
            )
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        with store.connection() as db:
            db.execute("SELECT 1").fetchone()
            queued = db.execute(
                "SELECT COUNT(*) FROM jobs WHERE state IN ('queued','running')"
            ).fetchone()[0]
        return {
            "status": "ok",
            "worker_alive": bool(store.worker and store.worker.is_alive()),
            "processing_mode": "vercel_queue" if queue_enabled else "local_worker",
            "pending_jobs": queued,
        }

    @app.get("/api/cases")
    def list_cases():
        return store.cases()

    @app.get("/api/cases/{case_id}")
    def get_case(case_id: str):
        return store.case(case_id)

    @app.post("/api/cases", status_code=202)
    async def upload(
        invoice: Annotated[UploadFile, File()],
        purchase_order: Annotated[UploadFile, File()],
        delivery: Annotated[UploadFile, File()],
    ):
        uploads = []
        for kind, file in (
            ("invoice", invoice),
            ("purchase_order", purchase_order),
            ("delivery", delivery),
        ):
            filename = file.filename or "document"
            content = await file.read(MAX_FILE_SIZE + 1)
            uploads.append(validate_upload(kind, filename, content))
        case_id, created = await run_in_threadpool(store.submit, uploads)
        if store.case(case_id)["job"]["state"] == "queued":
            await dispatch(case_id)
        return {
            "id": case_id,
            "created": created,
            "message": "Processing started"
            if created
            else "These documents have already been processed",
        }

    @app.post("/api/cases/from-uploads", status_code=202)
    async def uploaded_files(packet: BlobPacket):
        if not store.cloud_files:
            raise HTTPException(422, "Direct document uploads are not configured.")

        def download():
            uploads = []
            for kind in ("invoice", "purchase_order", "delivery"):
                reference = getattr(packet, kind)
                if not re.fullmatch(
                    r"incoming/[a-f0-9-]{36}/[a-zA-Z0-9_.-]{1,180}", reference.pathname
                ):
                    raise HTTPException(422, "Invalid document upload location.")
                metadata = store.cloud_files.client.head(reference.pathname)
                if not 0 < metadata.size <= MAX_FILE_SIZE:
                    raise HTTPException(422, "Each document must contain data and be under 20 MB.")
                result = store.cloud_files.client.get(reference.pathname, access="private")
                if result is None or result.status_code != 200:
                    raise HTTPException(
                        422, "An uploaded document could not be retrieved. Upload it again."
                    )
                uploads.append(validate_upload(kind, reference.filename, result.content))
            return uploads

        uploads = await run_in_threadpool(download)
        case_id, created = await run_in_threadpool(store.submit, uploads)
        await dispatch(case_id)
        # Original documents now have content-addressed durable copies.
        await run_in_threadpool(
            store.cloud_files.client.delete,
            [getattr(packet, kind).pathname for kind in ("invoice", "purchase_order", "delivery")],
        )
        return {"id": case_id, "created": created}

    @app.post("/api/internal/jobs/{case_id}")
    def process_job(case_id: str, request: Request):
        expected = os.environ.get("AUDITFLOW_JOB_TOKEN")
        if not expected or not secrets.compare_digest(
            request.headers.get("Authorization", ""), f"Bearer {expected}"
        ):
            raise HTTPException(404, "Unknown API endpoint.")
        previous = store.case(case_id)["job"]
        if previous["state"] == "failed":
            if previous["attempts"] >= 3:
                return {"id": case_id, "status": "failed"}
            store.retry(case_id)
        store.process_one(case_id)
        job = store.case(case_id)["job"]
        if job["state"] != "completed":
            raise HTTPException(503, "Document processing is incomplete.")
        return {"id": case_id, "status": "completed"}

    @app.patch("/api/cases/{case_id}/documents/{document_id}")
    def correct(case_id: str, document_id: str, correction: Correction):
        return store.correct(case_id, document_id, correction)

    @app.post("/api/cases/{case_id}/decision")
    def decide(case_id: str, decision: Decision):
        return store.decide(case_id, decision)

    @app.post("/api/cases/{case_id}/retry", status_code=202)
    async def retry(case_id: str):
        store.retry(case_id)
        await dispatch(case_id)
        return {"id": case_id, "status": "processing"}

    @app.get("/api/documents")
    def documents():
        with store.connection() as db:
            statuses = {
                row["id"]: row["status"]
                for row in db.execute("SELECT id,status FROM cases ORDER BY created_at DESC")
            }
            return [
                doc | {"case_status": status}
                for case_id, status in statuses.items()
                for doc in store.documents(db, case_id)
            ]

    @app.get("/api/documents/{document_id}/file")
    def original(document_id: str):
        with store.connection() as db:
            row = db.execute(
                "SELECT path,filename,digest FROM documents WHERE id=?", (document_id,)
            ).fetchone()
            if not row:
                raise KeyError(document_id)
            return FileResponse(
                store.document_path(row["path"], row["digest"]), filename=row["filename"]
            )

    @app.get("/api/documents/{document_id}/pages/{page_number}")
    def page_image(document_id: str, page_number: int):
        with store.connection() as db:
            row = db.execute(
                "SELECT digest,extraction FROM documents WHERE id=?", (document_id,)
            ).fetchone()
            if not row:
                raise KeyError(document_id)
            data = json.loads(row["extraction"] or "{}")
            if page_number not in [p["page"] for p in data.get("pages", [])]:
                raise KeyError(page_number)
            path = store.preview_path(row["digest"], page_number)
            if not path.is_file():
                raise KeyError(page_number)
            return FileResponse(
                path, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"}
            )

    @app.get("/api/events")
    def events():
        with store.connection() as db:
            result = []
            for event in db.execute("SELECT * FROM audit ORDER BY sequence DESC LIMIT 300"):
                item = dict(event)
                item["payload"] = json.loads(item["payload"])
                result.append(item)
            return result

    @app.get("/api/metrics")
    def metrics():
        with store.connection() as db:
            jobs = [dict(r) for r in db.execute("SELECT * FROM jobs WHERE state='completed'")]
            corrections = db.execute(
                "SELECT COUNT(*) FROM audit WHERE action='corrected'"
            ).fetchone()[0]
            reviewed = db.execute(
                "SELECT COUNT(DISTINCT case_id) FROM audit WHERE action IN ('approve','reject')"
            ).fetchone()[0]
            reviewed_corrections = db.execute(
                "SELECT COUNT(*) FROM audit WHERE action='corrected' AND case_id IN (SELECT case_id FROM audit WHERE action IN ('approve','reject'))"
            ).fetchone()[0]
            extractions = [
                json.loads(r[0])
                for r in db.execute("SELECT extraction FROM documents WHERE extraction IS NOT NULL")
            ]
        costs = [e.get("cost_usd") for e in extractions]
        known = [Decimal(str(cost)) for cost in costs if cost is not None]
        evaluation = None
        evaluation_path = store.root / "evaluation.json"
        if evaluation_path.exists():
            evaluation = json.loads(evaluation_path.read_text())
        return {
            "documents_processed": len(extractions),
            "corrections": corrections,
            "reviewed_cases": reviewed,
            "corrections_per_reviewed_case": reviewed_corrections / reviewed if reviewed else None,
            "average_processing_ms": round(sum(j["duration_ms"] or 0 for j in jobs) / len(jobs))
            if jobs
            else None,
            "api_cost_usd": str(sum(known, Decimal(0))) if len(known) == len(costs) else None,
            "cost_per_document": str(sum(known, Decimal(0)) / len(costs))
            if costs and len(known) == len(costs)
            else None,
            "evaluation": evaluation,
        }

    @app.get("/api/settings")
    def settings():
        return {
            "version": "0.1.0",
            "extraction": "Gemini multimodal"
            if os.environ.get("AUDITFLOW_AI_ENABLED", "").lower() == "true"
            else "PDF text + Tesseract OCR",
            "ai_key_configured": bool(os.environ.get("AUDITFLOW_AI_KEY")),
            "ocr_available": bool(shutil.which("tesseract")),
            "languages": ["English"],
            "currencies": ["USD", "EUR", "GBP", "INR", "CAD", "AUD"],
            "max_file_size_mb": 20,
            "max_pages": 20,
            "rules": "three-way-v1",
            "storage": "Private Vercel Blob + Turso SQL"
            if store.cloud_files
            else "Local files + SQLite",
            "deployment": "Public demonstration"
            if store.cloud_files
            else "Single-user development demo",
            "direct_uploads": bool(store.cloud_files),
        }

    @app.get("/api/cases/{case_id}/export")
    def export_case(case_id: str):
        case = store.case(case_id)
        with store.connection() as db:
            store.event(
                db,
                case_id,
                "exported",
                {"format": "json", "revision": case["revision"]},
                actor="Reviewer",
            )
        case = store.case(case_id)
        return Response(
            json.dumps({"schema_version": 1, **case}, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="auditflow-{case_id[:8]}.json"'},
        )

    @app.get("/api/export")
    def export_csv():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "Case ID",
                "Invoice",
                "Supplier",
                "Purchase order",
                "Currency",
                "Total",
                "Status",
                "Discrepancies",
                "Created",
                "Revision",
            ]
        )
        for case in store.cases():
            invoice = case["invoice"] or {}
            row = [
                case["id"],
                invoice.get("number", ""),
                invoice.get("supplier", ""),
                invoice.get("po_number", ""),
                invoice.get("currency", ""),
                invoice.get("total", ""),
                case["status"],
                "; ".join(f["code"] for f in (case["result"] or {}).get("flags", [])),
                case["created_at"],
                case["revision"],
            ]
            # Do not let document-provided strings become spreadsheet formulas.
            writer.writerow(
                [
                    "'" + str(value)
                    if str(value).startswith(("=", "+", "-", "@", "\t", "\r"))
                    else value
                    for value in row
                ]
            )
        return Response(
            buffer.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="auditflow-reconciliations.csv"'},
        )

    @app.get("/api/samples")
    def samples():
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for index, packet in enumerate(fixtures()):
                for document in packet["records"]:
                    filename, content = render_document(
                        document,
                        packet["layout"],
                        packet["scanned"] and document["kind"] == "invoice",
                    )
                    archive.writestr(f"{index + 1:02d}-{packet['scenario']}/{filename}", content)
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": 'attachment; filename="auditflow-sample-documents.zip"'
            },
        )

    assets = BASE / "dist" / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    def frontend(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Unknown API endpoint.")
        if path == "favicon.svg":
            return FileResponse(BASE / "public" / "favicon.svg")
        index = BASE / "dist" / "index.html"
        if index.exists():
            return FileResponse(index)
        return Response(
            "Frontend is not built. Run npm run dev for development or npm run build first.",
            status_code=503,
        )

    return app


app = create_app()
