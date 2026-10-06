import copy
import unittest
from decimal import Decimal

from server.demo import fixtures, record
from server.models import set_path
from server.reconcile import money, reconcile


def packet(records):
    return [{"kind": r["kind"], "record": r, "uncertain": []} for r in records]


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.records = copy.deepcopy(fixtures()[0]["records"])

    def codes(self, result):
        return {flag["code"] for flag in result["flags"]}

    def test_all_ground_truth_scenarios(self):
        previous = []
        for i, case in enumerate(fixtures()):
            with self.subTest(scenario=case["scenario"], supplier=case["records"][0]["supplier"]):
                result = reconcile(packet(case["records"]), previous)
                self.assertEqual(self.codes(result), set(case["expected_flags"]))
                previous.append({"case_id": str(i), "record": case["records"][0]})

    def test_decimal_arithmetic_does_not_create_float_discrepancies(self):
        items = [("SKU-01", "Small item", 3, "0.10")]
        records = [
            record(k, "Supplier", f"DOC-{i}", "PO-1", "2026-10-06", items, "0")
            for i, k in enumerate(("invoice", "purchase_order", "delivery"))
        ]
        self.assertEqual(reconcile(packet(records))["status"], "matched")
        self.assertEqual(money(Decimal("1.005")), Decimal("1.01"))

    def test_duplicate_identity_is_normalized_but_scoped_to_supplier(self):
        original = self.records[0]
        changed = copy.deepcopy(original)
        changed["number"] = "inv 2026 084"
        changed["supplier"] = "ACME SUPPLY CO"
        self.records[0] = changed
        previous = [{"case_id": "original", "record": original}]
        self.assertIn("duplicate_invoice", self.codes(reconcile(packet(self.records), previous)))
        previous[0]["record"] = {**original, "supplier": "Different Supplier"}
        self.assertNotIn("duplicate_invoice", self.codes(reconcile(packet(self.records), previous)))

    def test_missing_records_never_auto_match(self):
        docs = packet(self.records)
        docs[1]["record"] = None
        result = reconcile(docs)
        self.assertEqual(result["status"], "needs_review")
        self.assertIn("extraction_failed", self.codes(result))

    def test_unverified_extraction_is_sent_to_review(self):
        docs = packet(self.records)
        docs[0]["uncertain"] = ["total"]
        self.assertEqual(reconcile(docs)["status"], "needs_review")
        self.assertIn("uncertain_extraction", self.codes(reconcile(docs)))

    def test_cross_currency_amounts_are_not_compared(self):
        self.records[1]["currency"] = "EUR"
        self.records[1]["line_items"][0]["unit_price"] = "19.50"
        result = reconcile(packet(self.records))
        self.assertIn("currency_mismatch", self.codes(result))
        self.assertNotIn("price_mismatch", self.codes(result))

    def test_repeated_sku_requires_review(self):
        self.records[1]["line_items"][1]["sku"] = self.records[1]["line_items"][0]["sku"]
        self.assertIn("duplicate_sku", self.codes(reconcile(packet(self.records))))

    def test_po_reference_supplier_and_unmatched_items(self):
        self.records[1]["po_number"] = "PO-WRONG"
        self.records[2]["supplier"] = "Another Vendor"
        self.records[0]["line_items"][0]["sku"] = "SKU-UNKNOWN"
        codes = self.codes(reconcile(packet(self.records)))
        self.assertTrue(
            {
                "po_mismatch",
                "supplier_mismatch",
                "unmatched_item",
                "missing_delivery_item",
                "missing_invoice_item",
            }
            <= codes
        )

    def test_incorrect_line_subtotal_and_total_are_distinct(self):
        self.records[0]["line_items"][0]["amount"] = "99.00"
        codes = self.codes(reconcile(packet(self.records)))
        self.assertTrue({"line_total_mismatch", "subtotal_mismatch", "total_mismatch"} <= codes)

    def test_delivery_exposure_and_quantity_exposure_are_not_double_counted(self):
        case = fixtures()[1]
        result = reconcile(packet(case["records"]))
        self.assertEqual(result["exposure"], "144.00")
        delivery = reconcile(packet(fixtures()[4]["records"]))
        self.assertEqual(delivery["exposure"], "64.00")

    def test_schema_rejects_negative_or_invalid_corrections(self):
        with self.assertRaises(ValueError):
            set_path(self.records[0], "line_items.0.quantity", "-3")
        with self.assertRaises(ValueError):
            set_path(self.records[0], "total", "NaN")
        with self.assertRaises(ValueError):
            set_path(self.records[0], "date", "tomorrow")
        with self.assertRaises(ValueError):
            set_path(self.records[0], "kind", "delivery")
        with self.assertRaises(ValueError):
            set_path(self.records[0], "line_items.42.quantity", "3")


if __name__ == "__main__":
    unittest.main()
