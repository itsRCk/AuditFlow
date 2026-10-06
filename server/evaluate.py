"""Evaluate exact fields and discrepancy rules against independent fixture labels."""

import json
import tempfile
from decimal import Decimal
from pathlib import Path

from .demo import fixtures, render_document
from .extraction import extract
from .reconcile import reconcile


def flatten(value, prefix=""):
    if isinstance(value, dict):
        return {
            key: val
            for name, item in value.items()
            for key, val in flatten(item, f"{prefix}.{name}" if prefix else name).items()
        }
    if isinstance(value, list):
        return {
            key: val
            for i, item in enumerate(value)
            for key, val in flatten(item, f"{prefix}.{i}").items()
        }
    return {prefix: value} if value is not None and prefix != "kind" else {}


def equal(a, b):
    if a == b:
        return True
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except Exception:
        return False


def evaluate(root: Path) -> dict:
    correct = total = tp = fp = fn = documents = failures = 0
    previous = []
    details = []
    with tempfile.TemporaryDirectory(prefix="auditflow-evaluation-") as temporary:
        directory = Path(temporary)
        for index, packet in enumerate(fixtures()):
            docs = []
            for record in packet["records"]:
                filename, content = render_document(
                    record, packet["layout"], packet["scanned"] and record["kind"] == "invoice"
                )
                path = directory / filename
                path.write_bytes(content)
                import hashlib

                result = extract(
                    path,
                    record["kind"],
                    directory / "previews",
                    hashlib.sha256(content).hexdigest(),
                )
                docs.append({"kind": record["kind"], **result})
                expected, observed = flatten(record), flatten(result["record"] or {})
                for field, value in expected.items():
                    total += 1
                    correct += int(equal(value, observed.get(field)))
                failures += int(result["record"] is None)
                documents += 1
            actual = {flag["code"] for flag in reconcile(docs, previous)["flags"]}
            expected_flags = set(packet["expected_flags"])
            tp += len(actual & expected_flags)
            fp += len(actual - expected_flags)
            fn += len(expected_flags - actual)
            details.append(
                {
                    "scenario": packet["scenario"],
                    "supplier": packet["records"][0]["supplier"],
                    "expected": sorted(expected_flags),
                    "observed": sorted(actual),
                    "passed": actual == expected_flags,
                }
            )
            if docs[0]["record"]:
                previous.append({"case_id": f"fixture-{index}", "record": docs[0]["record"]})
    metrics = {
        "dataset": "English demo fixtures v1",
        "layouts": 3,
        "documents": documents,
        "scanned_documents": 1,
        "fields_correct": correct,
        "fields_total": total,
        "field_accuracy": correct / total if total else None,
        "discrepancy_precision": tp / (tp + fp) if tp + fp else None,
        "discrepancy_recall": tp / (tp + fn) if tp + fn else None,
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "validation_failures": failures,
        "scenarios": details,
        "limitation": "Small synthetic benchmark, not a production accuracy estimate.",
    }
    from .store import now

    metrics["evaluated_at"] = now()
    root.mkdir(parents=True, exist_ok=True)
    (root / "evaluation.json").write_text(json.dumps(metrics, indent=2))
    return metrics


if __name__ == "__main__":
    import os

    metrics = evaluate(Path(os.environ.get("AUDITFLOW_DATA_DIR", ".data")))
    print(json.dumps(metrics, indent=2))
    if (
        metrics["validation_failures"]
        or metrics["false_positives"]
        or metrics["false_negatives"]
        or metrics["fields_correct"] != metrics["fields_total"]
    ):
        raise SystemExit(1)
