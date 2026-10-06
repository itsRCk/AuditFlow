import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from server.main import create_app


class CORSTests(unittest.TestCase):
    def client(self, root, origins):
        with patch.dict("os.environ", {"AUDITFLOW_ALLOWED_ORIGINS": origins}):
            return TestClient(create_app(Path(root), seed_demo=False))

    def test_configured_frontend_can_read_and_preflight_corrections(self):
        with (
            tempfile.TemporaryDirectory() as root,
            self.client(root, "https://auditflow.example/, https://review.example") as client,
        ):
            response = client.get("/api/health", headers={"Origin": "https://auditflow.example"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.headers["Access-Control-Allow-Origin"], "https://auditflow.example"
            )
            self.assertIn("Content-Disposition", response.headers["Access-Control-Expose-Headers"])
            preflight = client.options(
                "/api/cases/example/documents/example",
                headers={
                    "Origin": "https://review.example",
                    "Access-Control-Request-Method": "PATCH",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            self.assertEqual(preflight.status_code, 200)
            self.assertEqual(
                preflight.headers["Access-Control-Allow-Origin"], "https://review.example"
            )
            self.assertNotIn("Access-Control-Allow-Credentials", preflight.headers)

    def test_unlisted_frontend_is_not_granted_browser_access(self):
        with (
            tempfile.TemporaryDirectory() as root,
            self.client(root, "https://auditflow.example") as client,
        ):
            response = client.get("/api/cases", headers={"Origin": "https://other.example"})
            self.assertNotIn("Access-Control-Allow-Origin", response.headers)
            preflight = client.options(
                "/api/cases",
                headers={
                    "Origin": "https://other.example",
                    "Access-Control-Request-Method": "POST",
                },
            )
            self.assertEqual(preflight.status_code, 400)
            self.assertNotIn("Access-Control-Allow-Origin", preflight.headers)

    def test_local_default_does_not_enable_cross_origin_access(self):
        with tempfile.TemporaryDirectory() as root, self.client(root, "") as client:
            response = client.get("/api/health", headers={"Origin": "https://other.example"})
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    def test_invalid_origin_configuration_fails_at_startup(self):
        for origin in (
            "*",
            "https://*.vercel.app",
            "https://example.com/api",
            "https://example.com?query=1",
            "https://example.com#fragment",
            "https://user:password@example.com",
            "https://@example.com",
            "https://example .com",
            "https://example.com:invalid",
            "https://example.com:99999",
        ):
            with (
                self.subTest(origin=origin),
                tempfile.TemporaryDirectory() as root,
                self.assertRaises(ValueError),
            ):
                self.client(root, origin)
