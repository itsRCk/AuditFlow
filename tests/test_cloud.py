import hashlib
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from server.cloud import Database, Files
from server.demo import fixtures, render_document
from server.extraction import extract
from server.main import create_app
from server.store import Store


class CloudPersistenceTests(unittest.TestCase):
    def uploads(self):
        return [(r["kind"], *render_document(r)) for r in fixtures()[0]["records"]]

    def test_remote_driver_preserves_rollback_and_named_rows(self):
        with tempfile.TemporaryDirectory() as temporary:
            db = Database(str(Path(temporary) / "network-driver.db"), "")
            db.executescript("CREATE TABLE evidence(id TEXT PRIMARY KEY, value TEXT);")
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT INTO evidence VALUES(?,?)", ("invoice", "original"))
            db.rollback()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM evidence").fetchone()[0], 0)
            db.execute("INSERT INTO evidence VALUES(?,?)", ("invoice", "original"))
            db.commit()
            db.close()
            reopened = Database(str(Path(temporary) / "network-driver.db"), "")
            self.assertEqual(
                dict(reopened.execute("SELECT * FROM evidence").fetchone()),
                {"id": "invoice", "value": "original"},
            )
            reopened.close()

    def test_lease_prevents_concurrent_work_and_fences_an_expired_claim(self):
        with tempfile.TemporaryDirectory() as temporary:
            store = Store(Path(temporary))
            another = Store(Path(temporary))
            case_id, _ = store.submit(self.uploads())
            entered, release = threading.Event(), threading.Event()
            first_call = True

            def pause_first(*args):
                nonlocal first_call
                if first_call:
                    first_call = False
                    entered.set()
                    self.assertTrue(release.wait(10))
                return extract(*args)

            with (
                patch("server.store.extract", side_effect=pause_first),
                ThreadPoolExecutor(max_workers=1) as pool,
            ):
                first = pool.submit(store.process_one, case_id)
                self.assertTrue(entered.wait(5))
                try:
                    self.assertFalse(another.process_one(case_id))
                    with another.connection() as db:
                        db.execute(
                            "UPDATE jobs SET lease_until=? WHERE case_id=?",
                            (time.time() - 1, case_id),
                        )
                    self.assertTrue(another.process_one(case_id))
                finally:
                    release.set()
                self.assertTrue(first.result(timeout=10))
            case = store.case(case_id)
            self.assertEqual(case["job"]["state"], "completed")
            self.assertEqual(case["job"]["attempts"], 2)
            self.assertEqual(sum(e["action"] == "extracted" for e in case["audit"]), 3)
            self.assertEqual(sum(e["action"] == "reconciled" for e in case["audit"]), 1)

    def test_processor_requires_authorization_and_queue_upload_is_durable(self):
        with (
            tempfile.TemporaryDirectory() as temporary,
            patch.dict(
                os.environ,
                {"AUDITFLOW_QUEUE_ENABLED": "true", "AUDITFLOW_JOB_TOKEN": "test-job-key"},
            ),
            patch("vercel.queue.send", new_callable=AsyncMock) as send,
        ):
            app = create_app(Path(temporary), seed_demo=False)
            with TestClient(app) as client:
                uploads = {kind: (name, content) for kind, name, content in self.uploads()}
                response = client.post("/api/cases", files=uploads)
                self.assertEqual(response.status_code, 202)
                case_id = response.json()["id"]
                send.assert_awaited_once()
                self.assertEqual(client.post(f"/api/internal/jobs/{case_id}").status_code, 404)
                self.assertEqual(app.state.store.case(case_id)["job"]["state"], "queued")
                processed = client.post(
                    f"/api/internal/jobs/{case_id}",
                    headers={"Authorization": "Bearer test-job-key"},
                )
                self.assertEqual(processed.status_code, 200)
                self.assertEqual(app.state.store.case(case_id)["job"]["state"], "completed")
                self.assertEqual(
                    client.post(
                        f"/api/internal/jobs/{case_id}",
                        headers={"Authorization": "Bearer test-job-key"},
                    ).status_code,
                    200,
                )
                self.assertEqual(
                    sum(e["action"] == "extracted" for e in app.state.store.case(case_id)["audit"]),
                    3,
                )

    def test_private_document_cache_rejects_bad_locations_and_corrupt_content(self):
        with tempfile.TemporaryDirectory() as temporary:
            files = Files.__new__(Files)
            files.root = Path(temporary)
            files.client = SimpleNamespace(
                get=lambda *args, **kwargs: SimpleNamespace(status_code=200, content=b"changed")
            )
            digest = hashlib.sha256(b"original").hexdigest()
            with self.assertRaisesRegex(RuntimeError, "integrity"):
                files.load("files/invoice.pdf", digest)
            self.assertFalse((files.root / "files/invoice.pdf").exists())
            for path in ("../invoice.pdf", "/outside/invoice.pdf"):
                with self.assertRaises(ValueError):
                    files.load(path)


if __name__ == "__main__":
    unittest.main()
