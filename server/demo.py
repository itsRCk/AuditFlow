"""Real, deterministic fixture documents and independent ground-truth records."""

from decimal import Decimal

import fitz

from .reconcile import money


def record(kind, supplier, number, po_number, date, items, tax_rate="0.08"):
    lines = [
        {
            "sku": sku,
            "description": description,
            "quantity": str(quantity),
            "unit_price": str(money(price)) if kind != "delivery" else None,
            "amount": str(money(Decimal(str(quantity)) * Decimal(str(price))))
            if kind != "delivery"
            else None,
        }
        for sku, description, quantity, price in items
    ]
    subtotal = (
        sum((Decimal(line["amount"]) for line in lines), Decimal("0"))
        if kind != "delivery"
        else None
    )
    tax = money(subtotal * Decimal(tax_rate)) if subtotal is not None else None
    return {
        "kind": kind,
        "supplier": supplier,
        "number": number,
        "po_number": po_number,
        "date": date,
        "currency": "USD",
        "subtotal": str(money(subtotal)) if subtotal is not None else None,
        "tax": str(tax) if tax is not None else None,
        "total": str(money(subtotal + tax)) if subtotal is not None else None,
        "line_items": lines,
    }


def fixtures() -> list[dict]:
    definitions = [
        (
            "Acme Supply Co.",
            "INV-2026-084",
            "PO-2026-041",
            "2026-10-02",
            [
                ("PAP-01", "A4 copy paper", 24, "18.50"),
                ("TON-02", "Laser toner cartridge", 8, "64.00"),
            ],
            "matched",
            0,
        ),
        (
            "Forma Office",
            "INV-1038",
            "PO-2026-052",
            "2026-10-05",
            [
                ("LMP-01", "Task desk lamp", 12, "48.00"),
                ("TRY-02", "Cable management tray", 24, "22.00"),
            ],
            "quantity",
            1,
        ),
        (
            "Northstar Electronics",
            "NS-2089",
            "PO-2026-048",
            "2026-10-05",
            [("DOC-10", "USB docking station", 20, "90.00"), ("HDM-20", "HDMI cable", 10, "24.00")],
            "total",
            2,
        ),
        (
            "Paperlane",
            "PL-26091",
            "PO-2026-046",
            "2026-10-03",
            [("FLD-10", "Document folder", 150, "3.20"), ("PAD-20", "Meeting notepad", 40, "8.50")],
            "matched",
            1,
        ),
        (
            "Evergreen Packaging",
            "EP-0412",
            "PO-2026-054",
            "2026-10-06",
            [("BOX-01", "Shipping box", 50, "12.80"), ("TAP-02", "Packing tape roll", 12, "19.50")],
            "delivery",
            0,
        ),
        (
            "Summit Logistics",
            "SL-00931",
            "PO-2026-049",
            "2026-10-04",
            [
                ("FRT-01", "Regional freight", 4, "185.00"),
                ("HND-02", "Warehouse handling", 8, "24.00"),
            ],
            "matched",
            2,
        ),
        (
            "Vertex Hardware",
            "VH-3381",
            "PO-2026-050",
            "2026-10-06",
            [
                ("BLT-01", "Stainless steel bolt", 200, "3.20"),
                ("BRK-02", "Mounting bracket", 50, "16.00"),
            ],
            "price",
            1,
        ),
        (
            "Lumen Design",
            "LD-1086",
            "PO-2026-056",
            "2026-10-06",
            [
                ("PNL-01", "Acoustic wall panel", 10, "120.00"),
                ("KIT-02", "Installation kit", 2, "45.00"),
            ],
            "matched",
            2,
        ),
        (
            "Acme Supply Co.",
            "INV-2026-084",
            "PO-2026-041",
            "2026-10-06",
            [
                ("PAP-01", "A4 copy paper", 24, "18.50"),
                ("TON-02", "Laser toner cartridge", 8, "64.00"),
            ],
            "duplicate",
            1,
        ),
    ]
    packets = []
    for i, (supplier, number, po_number, date, items, scenario, layout) in enumerate(definitions):
        invoice_items = list(items)
        delivery_items = list(items)
        if scenario == "quantity":
            sku, desc, qty, price = invoice_items[0]
            invoice_items[0] = (sku, desc, qty + 3, price)
        if scenario == "price":
            sku, desc, qty, price = invoice_items[0]
            invoice_items[0] = (sku, desc, qty, "3.60")
        if scenario == "delivery":
            sku, desc, qty, price = delivery_items[0]
            delivery_items[0] = (sku, desc, qty - 5, price)
        invoice = record("invoice", supplier, number, po_number, date, invoice_items)
        if scenario == "total":
            invoice["total"] = str(money(Decimal(invoice["total"]) + 100))
        po = record("purchase_order", supplier, po_number, po_number, date, items)
        delivery = record("delivery", supplier, f"DN-{4100 + i}", po_number, date, delivery_items)
        expected = {
            "matched": [],
            "quantity": ["quantity_mismatch", "delivery_mismatch"],
            "total": ["total_mismatch"],
            "delivery": ["delivery_mismatch"],
            "price": ["price_mismatch"],
            "duplicate": ["duplicate_invoice"],
        }[scenario]
        packets.append(
            {
                "scenario": scenario,
                "layout": layout,
                "scanned": supplier == "Lumen Design",
                "records": [invoice, po, delivery],
                "expected_flags": expected,
                "created_at": f"2026-10-{2 + i // 2:02d}T{9 + i % 3:02d}:{i * 5:02d}:00+00:00",
            }
        )
    return packets


def render_document(record: dict, layout: int = 0, scanned=False) -> tuple[str, bytes]:
    pdf = fitz.open()
    page = pdf.new_page(width=595, height=842)
    ink = (0.16, 0.21, 0.19)
    gray = (0.47, 0.51, 0.48)
    accent = (
        (0.22, 0.40, 0.31)
        if layout == 0
        else (0.18, 0.27, 0.43)
        if layout == 1
        else (0.34, 0.28, 0.23)
    )
    title = {"invoice": "INVOICE", "purchase_order": "PURCHASE ORDER", "delivery": "DELIVERY NOTE"}[
        record["kind"]
    ]
    labels = {"invoice": "Invoice no", "purchase_order": "PO number", "delivery": "Delivery note"}

    def text(x, y, value, size=11, color=ink, font="helv"):
        page.insert_text((x, y), str(value), fontsize=size, fontname=font, color=color)

    if layout == 0:
        page.draw_rect(fitz.Rect(0, 0, 595, 10), color=None, fill=accent)
        text(40, 60, record["supplier"].upper(), 14, accent, "hebo")
        text(40, 108, title, 30, ink, "hebo")
    elif layout == 1:
        page.draw_rect(fitz.Rect(0, 0, 595, 125), color=None, fill=(0.95, 0.96, 0.98))
        text(40, 55, title, 26, accent, "hebo")
        text(40, 85, record["supplier"], 14, ink)
    else:
        text(40, 55, record["supplier"], 22, ink, "hebo")
        page.draw_line((40, 76), (555, 76), color=accent, width=1)
        text(40, 110, title, 16, accent)
    # Explicit labels intentionally vary between the supported layouts.
    supplier_label = "Supplier" if layout != 1 else "Vendor"
    number_label = labels[record["kind"]]
    if layout == 2 and record["kind"] == "invoice":
        number_label = "Invoice number"
    for y, label, value in (
        (158, supplier_label, record["supplier"]),
        (184, number_label, record["number"]),
        (210, "PO reference", record["po_number"]),
        (236, "Date", record["date"]),
        (262, "Currency", record["currency"]),
    ):
        text(40, y, f"{label}: {value}", 11)
    page.draw_rect(fitz.Rect(40, 291, 555, 317), color=None, fill=(0.94, 0.95, 0.94))
    columns = [48, 125, 377, 437, 508]
    headers = ["SKU", "Description", "Qty", "Unit price", "Amount"]
    for x, header in zip(columns, headers[:3] if record["kind"] == "delivery" else headers):
        text(x, 308, header, 9, gray, "hebo")
    for i, item in enumerate(record["line_items"]):
        y = 344 + i * 34
        values = [
            item["sku"],
            item["description"],
            item["quantity"],
            item["unit_price"],
            item["amount"],
        ]
        for x, value in zip(columns, values[:3] if record["kind"] == "delivery" else values):
            text(x, y, value, 10)
        page.draw_line((40, y + 13), (555, y + 13), color=(0.87, 0.89, 0.87), width=0.5)
    if record["kind"] != "delivery":
        for y, label, value in (
            (456, "Subtotal", record["subtotal"]),
            (484, "Tax", record["tax"]),
            (520, "Amount due" if layout == 2 else "Total", record["total"]),
        ):
            text(
                365,
                y,
                f"{label}: {value}",
                12 if label in ("Total", "Amount due") else 11,
                ink,
                "hebo" if y == 520 else "helv",
            )
    else:
        text(40, 456, "Received by: Morgan Lee", 11)
        text(40, 484, "Goods inspected upon delivery.", 10, gray)
    page.draw_line((40, 738), (555, 738), color=(0.87, 0.89, 0.87), width=0.5)
    text(40, 762, "AuditFlow sample document - fictional supplier and transaction", 8, gray)
    text(40, 780, "For workflow demonstration only. Page 1 of 1.", 8, gray)
    extension = ".pdf"
    if scanned:
        content = page.get_pixmap(matrix=fitz.Matrix(2.5, 2.5), alpha=False).tobytes("png")
        extension = ".png"
    else:
        content = pdf.tobytes(garbage=4, deflate=True, no_new_id=True)
    pdf.close()
    return f"{record['number']}-{record['kind']}{extension}", content


def seed(store):
    with store.connection() as db:
        if db.execute("SELECT COUNT(*) FROM cases").fetchone()[0] > 0:
            return
    for packet in fixtures():
        uploads = []
        for document in packet["records"]:
            filename, content = render_document(
                document, packet["layout"], packet["scanned"] and document["kind"] == "invoice"
            )
            uploads.append((document["kind"], filename, content))
        store.submit(uploads, demo=True, created_at=packet["created_at"])
