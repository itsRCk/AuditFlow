import hashlib
import tempfile
import unittest
from pathlib import Path

import fitz

from server.demo import fixtures, render_document
from server.evaluate import evaluate
from server.extraction import extract


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def extract_fixture(self, record, layout=0, scanned=False):
        filename, content = render_document(record, layout, scanned)
        path = self.root / filename
        path.write_bytes(content)
        return extract(
            path, record["kind"], self.root / "previews", hashlib.sha256(content).hexdigest()
        )

    def test_three_supported_layouts_and_source_boxes(self):
        invoice = fixtures()[0]["records"][0]
        for layout in range(3):
            with self.subTest(layout=layout):
                result = self.extract_fixture(invoice, layout)
                self.assertEqual(result["record"], invoice)
                self.assertEqual(result["fields"]["line_items.0.quantity"]["source"]["text"], "24")
                self.assertEqual(result["fields"]["total"]["source"]["text"], "1032.48")
                for field in result["fields"].values():
                    self.assertIsNotNone(field["source"])
                    bbox = field["source"]["bbox"]
                    self.assertTrue(all(0 <= value <= 1 for value in bbox))
                    self.assertLess(bbox[0], bbox[2])
                    self.assertLess(bbox[1], bbox[3])

    def test_real_ocr_of_rendered_scan(self):
        invoice = fixtures()[7]["records"][0]
        result = self.extract_fixture(invoice, layout=2, scanned=True)
        self.assertEqual(result["method"], "ocr")
        self.assertEqual(result["record"], invoice)
        self.assertIsNotNone(result["fields"]["supplier"]["source"])

    def test_pipe_delimited_text_and_decimal_values(self):
        path = self.root / "invoice.txt"
        path.write_text(
            "Supplier: Example Co\nInvoice no: INV-01\nPO reference: PO-01\nDate: 2026-10-06\nCurrency: USD\nSKU | Description | Qty | Unit price | Amount\nABC-01 | Copy paper | 3 | 0.10 | 0.30\nSubtotal: 0.30\nTax: 0.00\nTotal: 0.30\n"
        )
        result = extract(path, "invoice", self.root / "previews", "text-fixture")
        self.assertIsNotNone(result["record"], result["errors"])
        self.assertEqual(result["record"]["line_items"][0]["description"], "Copy paper")
        self.assertEqual(result["record"]["total"], "0.30")

    def test_unsupported_content_is_not_invented(self):
        path = self.root / "unknown.txt"
        path.write_text("A letter with no financial fields or item table.\n")
        result = extract(path, "invoice", self.root / "previews", "unknown")
        self.assertIsNone(result["record"])
        self.assertTrue(result["errors"])

    def test_page_limit_and_encrypted_pdf(self):
        pdf = fitz.open()
        for _ in range(21):
            pdf.new_page()
        path = self.root / "too-many-pages.pdf"
        pdf.save(path)
        pdf.close()
        with self.assertRaisesRegex(ValueError, "20 pages"):
            extract(path, "invoice", self.root / "previews", "large")
        pdf = fitz.open()
        pdf.new_page()
        path = self.root / "encrypted.pdf"
        pdf.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="user")
        pdf.close()
        with self.assertRaisesRegex(ValueError, "Password-protected"):
            extract(path, "invoice", self.root / "previews", "encrypted")

    def test_fixture_pdf_generation_is_repeatable(self):
        record = fixtures()[0]["records"][0]
        self.assertEqual(render_document(record)[1], render_document(record)[1])

    def test_oversized_pdf_page_is_rejected_before_rendering(self):
        pdf = fitz.open()
        pdf.new_page(width=20000, height=20000)
        path = self.root / "large-dimensions.pdf"
        pdf.save(path)
        pdf.close()
        with self.assertRaisesRegex(ValueError, "25 megapixels"):
            extract(path, "invoice", self.root / "previews", "giant")

    def test_end_to_end_benchmark_matches_independent_labels(self):
        metrics = evaluate(self.root)
        self.assertEqual(metrics["documents"], 27)
        self.assertEqual(metrics["fields_correct"], metrics["fields_total"])
        self.assertEqual(metrics["false_positives"], 0)
        self.assertEqual(metrics["false_negatives"], 0)
        self.assertGreater(metrics["true_positives"], 0)


if __name__ == "__main__":
    unittest.main()
