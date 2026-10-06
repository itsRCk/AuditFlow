import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from server.demo import fixtures
from server.provider import extract_with_ai


class ProviderTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "digest-1.png").write_bytes(b"png-test-image")
        self.record = fixtures()[0]["records"][0]
        self.pages = [
            {
                "page": 1,
                "lines": [
                    {
                        "page": 1,
                        "text": "Total: 1032.48",
                        "words": [
                            {
                                "text": "Total:",
                                "start": 0,
                                "end": 6,
                                "page": 1,
                                "bbox": [0.1, 0.2, 0.3, 0.3],
                            },
                            {
                                "text": "1032.48",
                                "start": 7,
                                "end": 14,
                                "page": 1,
                                "bbox": [0.4, 0.2, 0.6, 0.3],
                            },
                        ],
                    }
                ],
            }
        ]
        self.baseline = {"pages": [{"page": 1, "width": 595, "height": 842}]}

    def tearDown(self):
        self.temp.cleanup()

    def response(self, evidence=None):
        import httpx

        output = {
            "record": self.record,
            "evidence": evidence or {"total": {"page": 1, "quote": "1032.48"}},
        }
        return httpx.Response(
            200,
            json={
                "candidates": [{"content": {"parts": [{"text": json.dumps(output)}]}}],
                "usageMetadata": {"promptTokenCount": 1000, "candidatesTokenCount": 100},
            },
        )

    def test_missing_key_is_an_explicit_prerequisite(self):
        with patch.dict("os.environ", {"AUDITFLOW_AI_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "not configured"):
                extract_with_ai(self.pages, self.root, "digest", "invoice", self.baseline)

    def test_verified_evidence_is_linked_and_unverified_fields_need_review(self):
        with (
            patch.dict("os.environ", {"AUDITFLOW_AI_KEY": "mock-test-key"}),
            patch("server.provider.httpx.post", return_value=self.response()),
        ):
            result = extract_with_ai(self.pages, self.root, "digest", "invoice", self.baseline)
        self.assertEqual(result["fields"]["total"]["source"]["text"], "1032.48")
        self.assertNotIn("total", result["uncertain"])
        self.assertIn("supplier", result["uncertain"])
        self.assertIsNone(result["cost_usd"])

    def test_incorrect_evidence_quote_is_not_treated_as_verified(self):
        self.record["total"] = "2000.00"
        with (
            patch.dict("os.environ", {"AUDITFLOW_AI_KEY": "mock-test-key"}),
            patch("server.provider.httpx.post", return_value=self.response()),
        ):
            result = extract_with_ai(self.pages, self.root, "digest", "invoice", self.baseline)
        self.assertIsNone(result["fields"]["total"]["source"])
        self.assertIn("total", result["uncertain"])

    def test_provider_http_errors_do_not_expose_response_content(self):
        import httpx

        with (
            patch.dict("os.environ", {"AUDITFLOW_AI_KEY": "mock-test-key"}),
            patch(
                "server.provider.httpx.post",
                return_value=httpx.Response(401, text="sensitive provider details"),
            ),
        ):
            with self.assertRaisesRegex(ValueError, "HTTP 401") as error:
                extract_with_ai(self.pages, self.root, "digest", "invoice", self.baseline)
            self.assertNotIn("sensitive", str(error.exception))

    def test_cost_uses_configured_rates_and_observed_usage(self):
        with (
            patch.dict(
                "os.environ",
                {
                    "AUDITFLOW_AI_KEY": "mock-test-key",
                    "AUDITFLOW_AI_INPUT_USD_PER_MILLION": "0.30",
                    "AUDITFLOW_AI_OUTPUT_USD_PER_MILLION": "2.50",
                },
            ),
            patch("server.provider.httpx.post", return_value=self.response()),
        ):
            result = extract_with_ai(self.pages, self.root, "digest", "invoice", self.baseline)
        self.assertEqual(result["cost_usd"], "0.00055")


if __name__ == "__main__":
    unittest.main()
