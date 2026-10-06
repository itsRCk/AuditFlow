"""English PDF/text/image extraction, preserving source coordinates for every value.

The baseline deliberately supports explicit labels and SKU-based table layouts.
Unsupported documents fail into review instead of inventing plausible records.
"""

import csv
import io
import os
import re
import subprocess
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import fitz
from PIL import Image

from .models import DocumentRecord

MAX_PAGES = 20


def group_lines(words: list[dict]) -> list[dict]:
    groups: list[list[dict]] = []
    for word in sorted(words, key=lambda w: (w["bbox"][1], w["bbox"][0])):
        center = (word["bbox"][1] + word["bbox"][3]) / 2
        height = word["bbox"][3] - word["bbox"][1]
        matching = next(
            (
                g
                for g in reversed(groups[-4:])
                if abs(center - (g[0]["bbox"][1] + g[0]["bbox"][3]) / 2) < max(height * 0.45, 0.003)
            ),
            None,
        )
        if matching is None:
            groups.append([word])
        else:
            matching.append(word)
    lines = []
    for group in groups:
        group.sort(key=lambda w: w["bbox"][0])
        text = ""
        for word in group:
            word["start"] = len(text)
            text += word["text"] + " "
            word["end"] = len(text) - 1
        lines.append({"text": text.strip(), "words": group, "page": group[0]["page"]})
    return lines


def ocr_words(png: bytes, page: int) -> list[dict]:
    with Image.open(io.BytesIO(png)) as image:
        width, height = image.size
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "eng", "--psm", "6", "tsv"],
            input=png,
            capture_output=True,
            timeout=60,
            check=True,
            env={**os.environ, "OMP_THREAD_LIMIT": "1"},
        )
    except FileNotFoundError as exc:
        raise ValueError(
            "Image extraction requires Tesseract with the English language pack."
        ) from exc
    words = []
    for row in csv.DictReader(io.StringIO(result.stdout.decode()), delimiter="\t"):
        text = (row.get("text") or "").strip()
        if text and float(row["conf"]) >= 0:
            x, y, w, h = (int(row[key]) for key in ("left", "top", "width", "height"))
            words.append(
                {
                    "text": text,
                    "bbox": [x / width, y / height, (x + w) / width, (y + h) / height],
                    "confidence": float(row["conf"]) / 100,
                    "page": page,
                }
            )
    return words


def read_pages(path: Path, previews: Path, digest: str) -> tuple[list[dict], str]:
    previews.mkdir(parents=True, exist_ok=True)
    pages = []
    method = "pdf_text"
    if path.suffix.lower() == ".pdf":
        pdf = fitz.open(path)
        if pdf.is_encrypted:
            raise ValueError("Password-protected PDFs are not supported.")
        if not 1 <= len(pdf) <= MAX_PAGES:
            raise ValueError(f"Documents must contain between 1 and {MAX_PAGES} pages.")
        try:
            for index, page in enumerate(pdf):
                page_no = index + 1
                if page.rect.width * page.rect.height * 1.5**2 > 25000000:
                    raise ValueError("PDF pages must render to fewer than 25 megapixels.")
                pixmap = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                png = pixmap.tobytes("png")
                preview_path = previews / f"{digest}-{page_no}.png"
                preview_path.write_bytes(png)
                words = [
                    {
                        "text": w[4],
                        "bbox": [
                            w[0] / page.rect.width,
                            w[1] / page.rect.height,
                            w[2] / page.rect.width,
                            w[3] / page.rect.height,
                        ],
                        "confidence": 1.0,
                        "page": page_no,
                    }
                    for w in page.get_text("words")
                ]
                if len(words) < 8:
                    method = "ocr"
                    words = ocr_words(png, page_no)
                pages.append(
                    {
                        "page": page_no,
                        "width": pixmap.width,
                        "height": pixmap.height,
                        "lines": group_lines(words),
                    }
                )
        finally:
            pdf.close()
    elif path.suffix.lower() in (".png", ".jpg", ".jpeg"):
        method = "ocr"
        with Image.open(path) as image:
            if image.width * image.height > 25000000:
                raise ValueError("Images must be under 25 megapixels.")
            image = image.convert("RGB")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            png = buffer.getvalue()
            (previews / f"{digest}-1.png").write_bytes(png)
            pages.append(
                {
                    "page": 1,
                    "width": image.width,
                    "height": image.height,
                    "lines": group_lines(ocr_words(png, 1)),
                }
            )
    elif path.suffix.lower() == ".txt":
        method = "text"
        text = path.read_text(encoding="utf-8")
        if len(text) > 60000:
            raise ValueError("Text documents must contain fewer than 60,000 characters.")
        pdf = fitz.open()
        text_lines = text.splitlines()
        for page_index in range(0, len(text_lines), 48):
            page = pdf.new_page()
            for row, line in enumerate(text_lines[page_index : page_index + 48]):
                page.insert_text((35, 50 + row * 15), line[:110], fontsize=9)
        if not len(pdf):
            pdf.new_page()
        if len(pdf) > MAX_PAGES:
            raise ValueError("Text document is too long.")
        temporary_pdf = previews / f"{digest}-text.pdf"
        pdf.save(temporary_pdf)
        pdf.close()
        pages, _ = read_pages(temporary_pdf, previews, digest)
    else:
        raise ValueError("Supported files: PDF, PNG, JPEG, and UTF-8 TXT.")
    return pages, method


def source(line: dict, start: int, end: int) -> dict | None:
    selected = [w for w in line["words"] if w["end"] > start and w["start"] < end]
    if not selected:
        return None
    boxes = [w["bbox"] for w in selected]
    return {
        "page": line["page"],
        "bbox": [
            min(b[0] for b in boxes),
            min(b[1] for b in boxes),
            max(b[2] for b in boxes),
            max(b[3] for b in boxes),
        ],
        "text": " ".join(w["text"] for w in selected),
    }


def numeric(raw: str) -> str:
    cleaned = re.sub(r"[,$£€₹\s]", "", raw)
    return str(Decimal(cleaned))


def parse_record(pages: list[dict], kind: str) -> dict:
    lines = [line for page in pages for line in page["lines"]]
    fields: dict = {}
    missing: list[str] = []
    record = {"kind": kind}

    def capture(path: str, patterns: list[str], transform=None, required=True):
        for pattern in patterns:
            for line in lines:
                match = re.search(pattern, line["text"], re.IGNORECASE)
                if match:
                    raw = match.group(1).strip()
                    try:
                        value = transform(raw) if transform else raw
                    except (ValueError, ArithmeticError):
                        continue
                    location = source(line, match.start(1), match.end(1))
                    confidence = min(
                        (
                            w["confidence"]
                            for w in line["words"]
                            if w["end"] > match.start(1) and w["start"] < match.end(1)
                        ),
                        default=0,
                    )
                    fields[path] = {
                        "value": value,
                        "extracted_value": value,
                        "confidence": round(confidence, 3),
                        "source": location,
                        "corrected": False,
                    }
                    return value
        if required:
            missing.append(path)
        return None

    record["supplier"] = capture("supplier", [r"^(?:Supplier|Vendor|Sold by|From)\s*:\s*(.+)$"])
    number_labels = {
        "invoice": r"Invoice\s*(?:number|no\.?|#)?",
        "purchase_order": r"(?:PO\s*(?:number|no\.?|#)?|Purchase order\s*(?:number|no\.?|#)?)",
        "delivery": r"(?:Delivery\s*(?:number|note|record|no\.?|#)|Packing slip)",
    }
    record["number"] = capture(
        "number", [rf"^{number_labels[kind]}\s*[:#]\s*([A-Z0-9][A-Z0-9_/-]*)"]
    )
    record["po_number"] = capture(
        "po_number",
        [
            r"^(?:PO\s*(?:reference|number|no\.?|#)?|Purchase order\s*(?:number|no\.?|#)?|Order reference)\s*[:#]\s*([A-Z0-9][A-Z0-9_/-]*)"
        ],
    )
    if not record["po_number"] and kind == "purchase_order" and record["number"]:
        record["po_number"] = record["number"]
        fields["po_number"] = {**fields["number"]}
        missing.remove("po_number")

    def parse_date(raw):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
            try:
                return datetime.strptime(raw, fmt).date().isoformat()
            except ValueError:
                pass
        raise ValueError("Unsupported date format")

    record["date"] = capture(
        "date", [r"^(?:(?:Invoice|Issue|Order|Delivery)\s+)?Date\s*:\s*(.+)$"], parse_date
    )
    record["currency"] = capture(
        "currency", [r"^Currency\s*:\s*(USD|EUR|GBP|INR|CAD|AUD)\b"], str.upper
    )
    amount_pattern = r"([\d,]+(?:\.\d{1,2})?)"
    for name, labels in (
        ("subtotal", "Subtotal|Sub total"),
        ("tax", "Tax|Sales tax|VAT"),
        ("total", "Total|Grand total|Amount due"),
    ):
        record[name] = capture(
            name,
            [
                rf"^(?:{labels})\s*[:]?\s*(?:USD|EUR|GBP|INR|CAD|AUD)?\s*[$£€₹]?\s*{amount_pattern}\s*(?:USD|EUR|GBP|INR|CAD|AUD)?$"
            ],
            numeric,
            required=kind != "delivery",
        )

    items = []
    # Pipe tables and column-aligned tables share a SKU + description + numeric-tail grammar.
    item_pattern = re.compile(
        r"^([A-Z0-9][A-Z0-9_-]{1,29})\s*[|]?\s+(.+?)\s*[|]?\s+(\d+(?:\.\d+)?)\s*[|]?\s+[$£€₹]?([\d,]+(?:\.\d{1,2})?)\s*[|]?\s+[$£€₹]?([\d,]+(?:\.\d{1,2})?)$",
        re.I,
    )
    delivery_pattern = re.compile(
        r"^([A-Z0-9][A-Z0-9_-]{1,29})\s*[|]?\s+(.+?)\s*[|]?\s+(\d+(?:\.\d+)?)$", re.I
    )
    for line in lines:
        if re.match(
            r"^(?:Subtotal|Total|Tax|Sales tax|VAT|Date|Currency|PO|Invoice|Order|Delivery|Supplier|Vendor|Received|Grand|Amount)\b",
            line["text"],
            re.I,
        ):
            continue
        match = (delivery_pattern if kind == "delivery" else item_pattern).match(line["text"])
        if not match or match[1].casefold() in ("sku", "item", "code"):
            continue
        index = len(items)
        item = {
            "sku": match[1],
            "description": match[2].strip(" |"),
            "quantity": numeric(match[3]),
            "unit_price": numeric(match[4]) if kind != "delivery" else None,
            "amount": numeric(match[5]) if kind != "delivery" else None,
        }
        for group, name in enumerate(
            ("sku", "description", "quantity", "unit_price", "amount"), start=1
        ):
            if group > (3 if kind == "delivery" else 5):
                continue
            location = source(line, match.start(group), match.end(group))
            confidence = min(
                (
                    w["confidence"]
                    for w in line["words"]
                    if w["end"] > match.start(group) and w["start"] < match.end(group)
                ),
                default=0,
            )
            fields[f"line_items.{index}.{name}"] = {
                "value": item[name],
                "extracted_value": item[name],
                "confidence": round(confidence, 3),
                "source": location,
                "corrected": False,
            }
        items.append(item)
    record["line_items"] = items
    if not items:
        missing.append("line_items")
    errors = []
    validated = None
    try:
        validated = DocumentRecord.model_validate(record).model_dump(mode="json")
    except Exception as exc:
        errors.append(
            "Missing or unsupported fields: " + ", ".join(missing) if missing else str(exc)
        )
    uncertain = [
        path
        for path, field in fields.items()
        if field["confidence"] < 0.85 or field["source"] is None
    ]
    return {
        "record": validated,
        "fields": fields,
        "uncertain": uncertain,
        "errors": errors,
        "pages": [{"page": p["page"], "width": p["width"], "height": p["height"]} for p in pages],
    }


def extract(path: Path, kind: str, previews: Path, digest: str) -> dict:
    pages, method = read_pages(path, previews, digest)
    result = parse_record(pages, kind)
    result["method"] = method
    result["cost_usd"] = "0.000000"
    # Optional multimodal extraction is opt-in; local processing remains the default.
    if os.environ.get("AUDITFLOW_AI_ENABLED", "").lower() == "true":
        from .provider import extract_with_ai

        result = extract_with_ai(pages, previews, digest, kind, result)
    return result
