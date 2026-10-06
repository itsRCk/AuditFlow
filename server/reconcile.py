"""Deterministic three-way matching with Decimal arithmetic and explicit evidence."""

import re
from decimal import ROUND_HALF_UP, Decimal

RULE_VERSION = "three-way-v1"
CENT = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value or "0")).quantize(CENT, rounding=ROUND_HALF_UP)


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def reconcile(documents: list[dict], previous_invoices: list[dict] | None = None) -> dict:
    by_kind = {document["kind"]: document for document in documents}
    flags: list[dict] = []
    impact = Decimal("0")

    def flag(code, title, message, severity="warning", paths=None, amount=None):
        flags.append(
            {
                "code": code,
                "title": title,
                "message": message,
                "severity": severity,
                "paths": paths or [],
                "amount": str(amount) if amount is not None else None,
            }
        )

    for kind in ("invoice", "purchase_order", "delivery"):
        doc = by_kind.get(kind)
        if doc is None or doc.get("record") is None:
            flag(
                "extraction_failed",
                "Document needs attention",
                f"The {kind.replace('_', ' ')} could not be validated. Re-upload a supported document.",
                "error",
            )
        elif doc.get("uncertain"):
            flag(
                "uncertain_extraction",
                "Verify extracted fields",
                f"Some {kind.replace('_', ' ')} values need a source check.",
                "warning",
                [{"kind": kind, "path": p} for p in doc["uncertain"]],
            )
    if any(not by_kind.get(k, {}).get("record") for k in ("invoice", "purchase_order", "delivery")):
        return {
            "status": "needs_review",
            "flags": flags,
            "lines": [],
            "exposure": "0.00",
            "rule_version": RULE_VERSION,
        }

    invoice, po, delivery = (
        by_kind[k]["record"] for k in ("invoice", "purchase_order", "delivery")
    )
    duplicates = []
    for previous in previous_invoices or []:
        old = previous["record"]
        if normalized(old["supplier"]) == normalized(invoice["supplier"]) and normalized(
            old["number"]
        ) == normalized(invoice["number"]):
            duplicates.append(previous["case_id"])
    if duplicates:
        flag(
            "duplicate_invoice",
            "Duplicate invoice",
            f"This supplier and invoice number already exist in case {duplicates[0][:8].upper()}.",
            "error",
            [{"kind": "invoice", "path": "number"}],
            money(invoice["total"]),
        )
        impact = money(invoice["total"])

    for kind, record in (("purchase_order", po), ("delivery", delivery)):
        if normalized(record["supplier"]) != normalized(invoice["supplier"]):
            flag(
                "supplier_mismatch",
                "Supplier does not match",
                f"The {kind.replace('_', ' ')} names a different supplier.",
                "error",
                [{"kind": kind, "path": "supplier"}, {"kind": "invoice", "path": "supplier"}],
            )
        if normalized(record["po_number"]) != normalized(invoice["po_number"]):
            flag(
                "po_mismatch",
                "Purchase order does not match",
                f"The {kind.replace('_', ' ')} references {record['po_number']} instead of {invoice['po_number']}.",
                "error",
                [{"kind": kind, "path": "po_number"}, {"kind": "invoice", "path": "po_number"}],
            )
        if record["currency"] != invoice["currency"]:
            flag(
                "currency_mismatch",
                "Currency does not match",
                "Documents use different currencies; amounts cannot be compared.",
                "error",
            )

    for kind, record in (("invoice", invoice), ("purchase_order", po)):
        for index, item in enumerate(record["line_items"]):
            calculated = money(Decimal(item["quantity"]) * Decimal(item["unit_price"]))
            if money(item["amount"]) != calculated:
                delta = abs(money(item["amount"]) - calculated)
                flag(
                    "line_total_mismatch",
                    "Line total is incorrect",
                    f"{item['sku']}: quantity × unit price is {calculated}, but the line total is {item['amount']}.",
                    "error",
                    [{"kind": kind, "path": f"line_items.{index}.amount"}],
                    delta,
                )
        sum_lines = sum((money(item["amount"]) for item in record["line_items"]), Decimal("0"))
        expected_total = money(sum_lines + money(record["tax"]))
        if sum_lines != money(record["subtotal"]):
            flag(
                "subtotal_mismatch",
                "Subtotal is incorrect",
                f"Line items add up to {sum_lines}, but the {kind.replace('_', ' ')} subtotal is {record['subtotal']}.",
                "error",
                [{"kind": kind, "path": "subtotal"}],
                abs(sum_lines - money(record["subtotal"])),
            )
        if money(record["total"]) != expected_total:
            delta = abs(money(record["total"]) - expected_total)
            flag(
                "total_mismatch",
                "Invoice total is incorrect"
                if kind == "invoice"
                else "Purchase order total is incorrect",
                f"Line items plus tax equal {expected_total}; the document states {record['total']}.",
                "error",
                [{"kind": kind, "path": "total"}],
                delta,
            )
            if kind == "invoice" and not duplicates:
                impact = max(impact, delta)

    def index_lines(kind: str, record: dict):
        mapping = {}
        for index, item in enumerate(record["line_items"]):
            key = normalized(item["sku"])
            if key in mapping:
                flag(
                    "duplicate_sku",
                    "Repeated item code",
                    f"{item['sku']} occurs more than once in the {kind.replace('_', ' ')}. Verify these lines before approving.",
                    "error",
                )
            mapping[key] = (index, item)
        return mapping

    po_lines = index_lines("purchase_order", po)
    delivery_lines = index_lines("delivery", delivery)
    invoice_lines = index_lines("invoice", invoice)
    rows = []
    item_impact = Decimal("0")
    for index, item in enumerate(invoice["line_items"]):
        key = normalized(item["sku"])
        ordered = po_lines.get(key)
        received = delivery_lines.get(key)
        quantity = Decimal(item["quantity"])
        issues = []
        quantity_impact = Decimal("0")
        if not ordered:
            issues.append("Not on PO")
            flag(
                "unmatched_item",
                "Item is not on the purchase order",
                f"{item['sku']} has no matching item code on the purchase order.",
                "error",
                [{"kind": "invoice", "path": f"line_items.{index}.sku"}],
            )
            item_impact += money(item["amount"])
        else:
            po_index, ordered_item = ordered
            if quantity != Decimal(ordered_item["quantity"]):
                issues.append("Quantity")
                delta = money(
                    abs(quantity - Decimal(ordered_item["quantity"])) * Decimal(item["unit_price"])
                )
                flag(
                    "quantity_mismatch",
                    "Invoiced quantity does not match",
                    f"{item['sku']}: {item['quantity']} invoiced, {ordered_item['quantity']} ordered.",
                    "error",
                    [
                        {"kind": "invoice", "path": f"line_items.{index}.quantity"},
                        {"kind": "purchase_order", "path": f"line_items.{po_index}.quantity"},
                    ],
                    delta,
                )
                quantity_impact = delta
            if invoice["currency"] == po["currency"] and money(item["unit_price"]) != money(
                ordered_item["unit_price"]
            ):
                issues.append("Unit price")
                delta = money(
                    abs(money(item["unit_price"]) - money(ordered_item["unit_price"])) * quantity
                )
                flag(
                    "price_mismatch",
                    "Unit price does not match",
                    f"{item['sku']}: {item['unit_price']} invoiced, {ordered_item['unit_price']} agreed.",
                    "error",
                    [{"kind": "invoice", "path": f"line_items.{index}.unit_price"}],
                    delta,
                )
                item_impact += delta
        if not received:
            issues.append("Not received")
            flag(
                "missing_delivery_item",
                "Item is missing from delivery",
                f"{item['sku']} is invoiced but has no delivery record.",
                "error",
            )
        elif quantity != Decimal(received[1]["quantity"]):
            issues.append("Delivery")
            delivery_delta = money(
                max(Decimal("0"), quantity - Decimal(received[1]["quantity"]))
                * Decimal(item["unit_price"])
            )
            quantity_impact = max(quantity_impact, delivery_delta)
            flag(
                "delivery_mismatch",
                "Delivered quantity does not match",
                f"{item['sku']}: {item['quantity']} invoiced, {received[1]['quantity']} received.",
                "error",
                [
                    {"kind": "delivery", "path": f"line_items.{received[0]}.quantity"},
                    {"kind": "invoice", "path": f"line_items.{index}.quantity"},
                ],
                delivery_delta,
            )
        item_impact += quantity_impact
        rows.append(
            {
                "sku": item["sku"],
                "description": item["description"],
                "invoiced": item["quantity"],
                "ordered": ordered[1]["quantity"] if ordered else None,
                "received": received[1]["quantity"] if received else None,
                "unit_price": item["unit_price"],
                "amount": item["amount"],
                "issues": issues,
                "invoice_index": index,
            }
        )
    for key, (_, item) in po_lines.items():
        if key not in invoice_lines:
            flag(
                "missing_invoice_item",
                "Ordered item is not invoiced",
                f"{item['sku']} appears on the PO but not the invoice. Verify whether this is a partial invoice.",
                "warning",
            )
    if not duplicates:
        impact = max(impact, item_impact)
    return {
        "status": "duplicate" if duplicates else "needs_review" if flags else "matched",
        "flags": flags,
        "lines": rows,
        "exposure": str(money(impact)),
        "rule_version": RULE_VERSION,
        "duplicate_cases": duplicates,
    }
