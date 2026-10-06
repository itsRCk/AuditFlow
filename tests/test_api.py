import copy
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.demo import fixtures, render_document
from server.main import create_app
from server.store import Store


def uploads(records, layout=0):
    return {
        document["kind"]: (*render_document(document, layout), "application/pdf")
        for document in records
    }


class APITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.environment = patch.dict("os.environ", {"AUDITFLOW_AI_ENABLED": "false"})
        self.environment.start()
        self.app = create_app(self.root, seed_demo=False)
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.environment.stop()
        self.temp.cleanup()

    def submit(self, records=None, layout=0):
        response = self.client.post(
            "/api/cases", files=uploads(records or fixtures()[2]["records"], layout)
        )
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def wait(self, case_id):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            result = self.client.get(f"/api/cases/{case_id}").json()
            if result["status"] != "processing":
                self.assertNotEqual(result["status"], "failed", result)
                return result
            time.sleep(0.03)
        self.fail("The queued document job did not complete")

    def test_upload_processing_source_correction_approval_and_export(self):
        submitted = self.submit()
        self.assertTrue(submitted["created"])
        data = self.wait(submitted["id"])
        self.assertEqual(data["status"], "needs_review")
        self.assertEqual([flag["code"] for flag in data["result"]["flags"]], ["total_mismatch"])
        invoice = next(d for d in data["documents"] if d["kind"] == "invoice")
        original_source = copy.deepcopy(invoice["fields"]["total"]["source"])
        response = self.client.get(f"/api/documents/{invoice['id']}/pages/1")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"\x89PNG"))
        original = self.client.get(f"/api/documents/{invoice['id']}/file")
        self.assertTrue(original.content.startswith(b"%PDF-"))
        corrected = self.client.patch(
            f"/api/cases/{data['id']}/documents/{invoice['id']}",
            json={
                "path": "total",
                "value": "2203.20",
                "reason": "Verified line items and tax in source",
                "expected_revision": data["revision"],
            },
        )
        self.assertEqual(corrected.status_code, 200, corrected.text)
        updated = corrected.json()
        self.assertEqual(updated["status"], "matched")
        corrected_doc = next(d for d in updated["documents"] if d["kind"] == "invoice")
        self.assertEqual(corrected_doc["fields"]["total"]["extracted_value"], "2303.20")
        self.assertEqual(corrected_doc["fields"]["total"]["value"], "2203.20")
        self.assertEqual(corrected_doc["fields"]["total"]["source"], original_source)
        self.assertTrue(corrected_doc["fields"]["total"]["corrected"])
        self.assertTrue(
            any(
                e["action"] == "corrected" and e["payload"]["before"] == "2303.20"
                for e in updated["audit"]
            )
        )
        decision = self.client.post(
            f"/api/cases/{data['id']}/decision",
            json={
                "action": "approve",
                "note": "Checked and approved corrected invoice",
                "expected_revision": updated["revision"],
            },
        )
        self.assertEqual(decision.status_code, 200, decision.text)
        self.assertEqual(decision.json()["status"], "approved")
        export = self.client.get(f"/api/cases/{data['id']}/export")
        self.assertEqual(export.status_code, 200)
        evidence = export.json()
        self.assertEqual(evidence["schema_version"], 1)
        self.assertEqual(evidence["audit"][0]["action"], "exported")
        self.assertTrue(any(e["action"] == "approve" for e in evidence["audit"]))
        self.assertNotIn(str(self.root), export.text)
        metrics = self.client.get("/api/metrics").json()
        self.assertEqual(metrics["corrections"], 1)
        self.assertEqual(metrics["corrections_per_reviewed_case"], 1)
        self.assertEqual(metrics["api_cost_usd"], "0.000000")

    def test_identical_upload_is_idempotent(self):
        first = self.submit()
        second = self.submit()
        self.assertEqual(first["id"], second["id"])
        self.assertFalse(second["created"])
        self.assertEqual(len(self.client.get("/api/cases").json()), 1)
        data = self.wait(first["id"])
        self.assertEqual(sum(e["action"] == "uploaded" for e in data["audit"]), 1)

    def test_duplicate_different_layout_is_detected(self):
        first = self.wait(self.submit(fixtures()[0]["records"])["id"])
        other = copy.deepcopy(fixtures()[0]["records"])
        other[2]["number"] = "DN-DUPLICATE"
        second = self.wait(self.submit(other, layout=1)["id"])
        self.assertEqual(first["status"], "matched")
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(second["result"]["duplicate_cases"], [first["id"]])

    def test_optimistic_concurrency_rejects_stale_correction_and_decision(self):
        data = self.wait(self.submit()["id"])
        doc = next(d for d in data["documents"] if d["kind"] == "invoice")
        body = {
            "path": "total",
            "value": "2203.20",
            "reason": "Verified correct total",
            "expected_revision": data["revision"],
        }
        self.assertEqual(
            self.client.patch(
                f"/api/cases/{data['id']}/documents/{doc['id']}", json=body
            ).status_code,
            200,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/cases/{data['id']}/documents/{doc['id']}", json={**body, "value": "2204.20"}
            ).status_code,
            409,
        )
        self.assertEqual(
            self.client.post(
                f"/api/cases/{data['id']}/decision",
                json={
                    "action": "approve",
                    "note": "Approval",
                    "expected_revision": data["revision"],
                },
            ).status_code,
            409,
        )

    def test_a_correction_invalidates_an_existing_decision(self):
        data = self.wait(self.submit(fixtures()[0]["records"])["id"])
        approved = self.client.post(
            f"/api/cases/{data['id']}/decision",
            json={
                "action": "approve",
                "note": "Checked all source documents",
                "expected_revision": data["revision"],
            },
        ).json()
        doc = next(d for d in data["documents"] if d["kind"] == "invoice")
        response = self.client.patch(
            f"/api/cases/{data['id']}/documents/{doc['id']}",
            json={
                "path": "total",
                "value": "1033.48",
                "reason": "New evidence of total error",
                "expected_revision": approved["revision"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "needs_review")
        self.assertTrue(
            any(e["action"] == "decision_invalidated" for e in response.json()["audit"])
        )

    def test_dependent_duplicate_decision_is_invalidated_after_identity_correction(self):
        first = self.wait(self.submit(fixtures()[0]["records"])["id"])
        second = self.wait(self.submit(fixtures()[8]["records"], layout=1)["id"])
        self.assertEqual(second["status"], "duplicate")
        rejected = self.client.post(
            f"/api/cases/{second['id']}/decision",
            json={
                "action": "reject",
                "note": "Duplicate of first invoice",
                "expected_revision": second["revision"],
            },
        ).json()
        self.assertEqual(rejected["status"], "rejected")
        doc = next(d for d in first["documents"] if d["kind"] == "invoice")
        response = self.client.patch(
            f"/api/cases/{first['id']}/documents/{doc['id']}",
            json={
                "path": "number",
                "value": "INV-CORRECTED",
                "reason": "Verified distinct invoice identity",
                "expected_revision": first["revision"],
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        updated = self.client.get(f"/api/cases/{second['id']}").json()
        self.assertEqual(updated["status"], "matched")
        self.assertTrue(any(e["action"] == "decision_invalidated" for e in updated["audit"]))

    def test_validation_error_does_not_destroy_the_original_record(self):
        data = self.wait(self.submit()["id"])
        doc = next(d for d in data["documents"] if d["kind"] == "invoice")
        response = self.client.patch(
            f"/api/cases/{data['id']}/documents/{doc['id']}",
            json={
                "path": "total",
                "value": "-1",
                "reason": "Invalid change",
                "expected_revision": data["revision"],
            },
        )
        self.assertEqual(response.status_code, 422)
        unchanged = self.client.get(f"/api/cases/{data['id']}").json()
        self.assertEqual(unchanged["revision"], data["revision"])
        self.assertEqual(unchanged["invoice"]["total"], "2303.20")

    def test_unsupported_extraction_requires_review_and_cannot_be_approved(self):
        files = uploads(fixtures()[0]["records"])
        files["invoice"] = (
            "unknown.txt",
            b"Unstructured letter with no invoice fields",
            "text/plain",
        )
        response = self.client.post("/api/cases", files=files)
        data = self.wait(response.json()["id"])
        self.assertEqual(data["status"], "needs_review")
        self.assertIsNone(data["invoice"])
        approval = self.client.post(
            f"/api/cases/{data['id']}/decision",
            json={
                "action": "approve",
                "note": "Try approval",
                "expected_revision": data["revision"],
            },
        )
        self.assertEqual(approval.status_code, 422)
        self.assertEqual(self.client.post(f"/api/cases/{data['id']}/retry").status_code, 202)

    def test_file_type_empty_file_and_required_slots(self):
        files = uploads(fixtures()[0]["records"])
        files["invoice"] = ("bad.exe", b"bad", "application/octet-stream")
        self.assertEqual(self.client.post("/api/cases", files=files).status_code, 422)
        files["invoice"] = ("bad.pdf", b"not pdf", "application/pdf")
        self.assertEqual(self.client.post("/api/cases", files=files).status_code, 422)
        files["invoice"] = ("empty.pdf", b"", "application/pdf")
        self.assertEqual(self.client.post("/api/cases", files=files).status_code, 422)
        self.assertEqual(
            self.client.post("/api/cases", files={"invoice": files["invoice"]}).status_code, 422
        )
        self.assertEqual(self.client.get("/api/cases").json(), [])

    def test_audit_storage_is_append_only(self):
        self.wait(self.submit()["id"])
        with sqlite3.connect(self.app.state.store.db_path) as db:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                db.execute("UPDATE audit SET actor='rewritten'")
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                db.execute("DELETE FROM audit")

    def test_csv_export_escapes_spreadsheet_formulas(self):
        records = copy.deepcopy(fixtures()[0]["records"])
        for record in records:
            record["supplier"] = "=SUM(1,2)"
        self.wait(self.submit(records)["id"])
        response = self.client.get("/api/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("'=SUM(1,2)", response.text)

    def test_missing_record_and_page_return_404(self):
        self.assertEqual(self.client.get("/api/cases/not-found").status_code, 404)
        data = self.wait(self.submit()["id"])
        doc = data["documents"][0]
        self.assertEqual(self.client.get(f"/api/documents/{doc['id']}/pages/999").status_code, 404)

    def test_current_instance_and_restart_preserve_records(self):
        first = self.wait(self.submit()["id"])
        with TestClient(create_app(self.root, seed_demo=False)) as other:
            restored = other.get(f"/api/cases/{first['id']}").json()
            self.assertEqual(restored["invoice"], first["invoice"])
            self.assertEqual(restored["job"]["attempts"], 1)
            self.assertEqual(restored["audit"], first["audit"])


class JobRecoveryTests(unittest.TestCase):
    def test_worker_recovers_interrupted_jobs_from_disk(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict("os.environ", {"AUDITFLOW_AI_ENABLED": "false"}),
        ):
            store = Store(Path(directory))
            packet = [(doc["kind"], *render_document(doc)) for doc in fixtures()[0]["records"]]
            case_id, _ = store.submit(packet)
            with store.connection() as db:
                db.execute("UPDATE jobs SET state='running',attempts=1 WHERE case_id=?", (case_id,))
            recovered = Store(Path(directory))
            recovered.start_worker()
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    case = recovered.case(case_id)
                    if case["status"] != "processing":
                        break
                    time.sleep(0.03)
                self.assertEqual(case["status"], "matched")
                self.assertEqual(case["job"]["attempts"], 2)
                self.assertEqual(sum(e["action"] == "uploaded" for e in case["audit"]), 1)
            finally:
                recovered.stop_worker()


if __name__ == "__main__":
    unittest.main()
