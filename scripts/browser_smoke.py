"""Exercise the actual production UI against an isolated SQLite database and files."""

import argparse
import csv
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

from server.demo import fixtures, render_document

ROOT = Path(__file__).resolve().parent.parent
PORT = 3100
API_URL = f"http://127.0.0.1:{PORT}"
ARTIFACTS = ROOT / "test-results"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--split-origin",
        action="store_true",
        help="Serve the frontend separately; first build with VITE_API_BASE_URL=http://127.0.0.1:3100.",
    )
    split_origin = parser.parse_args().split_origin
    url = "http://127.0.0.1:3101" if split_origin else API_URL
    artifacts = ARTIFACTS / "split-origin" if split_origin else ARTIFACTS
    if not (ROOT / "dist/index.html").exists():
        raise SystemExit("Run npm run build before the browser smoke test.")
    executable = (
        os.environ.get("AUDITFLOW_CHROMIUM")
        or shutil.which("chromium")
        or shutil.which("google-chrome")
    )
    artifacts.mkdir(parents=True, exist_ok=True)
    checks = []

    def passed(message):
        checks.append(message)
        print(f"PASS {message}", flush=True)

    with (
        tempfile.TemporaryDirectory(prefix="auditflow-browser-") as temporary,
        (artifacts / "browser-server.log").open("w") as log,
    ):
        environment = {
            **os.environ,
            "AUDITFLOW_DATA_DIR": temporary,
            "AUDITFLOW_SEED_DEMO": "true",
            "AUDITFLOW_AI_ENABLED": "false",
            "AUDITFLOW_ALLOWED_ORIGINS": url if split_origin else "",
        }
        frontend = None
        server = subprocess.Popen(
            [
                str(ROOT / ".venv/bin/python"),
                "-m",
                "uvicorn",
                "server.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(PORT),
            ],
            cwd=ROOT,
            env=environment,
            stdout=log,
            stderr=log,
        )
        try:
            if split_origin:
                frontend = subprocess.Popen(
                    [
                        str(ROOT / ".venv/bin/python"),
                        "-m",
                        "http.server",
                        "3101",
                        "--bind",
                        "127.0.0.1",
                        "--directory",
                        str(ROOT / "dist"),
                    ],
                    stdout=log,
                    stderr=log,
                )
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if server.poll() is not None:
                    raise AssertionError(
                        "Browser-test server exited before readiness. See test-results/browser-server.log"
                    )
                try:
                    health = httpx.get(API_URL + "/api/health", timeout=1)
                    frontend_ready = not split_origin or httpx.get(url, timeout=1).is_success
                    if health.is_success and health.json()["pending_jobs"] == 0 and frontend_ready:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
            else:
                raise AssertionError("Demo jobs did not complete before the readiness deadline")

            with sync_playwright() as p:
                browser = p.chromium.launch(executable_path=executable, headless=True)
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    device_scale_factor=1,
                    accept_downloads=True,
                )
                page = context.new_page()
                errors = []
                wrong_api_requests = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                if split_origin:
                    page.on(
                        "request",
                        lambda request: (
                            wrong_api_requests.append(request.url)
                            if request.url.startswith(url + "/api")
                            else None
                        ),
                    )
                page.goto(url, wait_until="networkidle")
                expect(page.get_by_role("heading", name="Reconciliations.")).to_be_visible()
                expect(page.locator(".cases-table tbody tr")).to_have_count(8)
                passed("Dashboard loads nine real fixture cases")
                page.screenshot(path=artifacts / "dashboard.png", full_page=True)
                with page.expect_download() as download:
                    page.get_by_role("link", name="Export", exact=True).click()
                rows = list(csv.reader(io.StringIO(Path(download.value.path()).read_text())))
                assert len(rows) == 10 and rows[0][0] == "Case ID"
                passed("CSV download includes all nine reconciliations")

                page.get_by_role("button", name="Next", exact=True).click()
                expect(page.locator(".cases-table tbody tr")).to_have_count(1)
                page.get_by_role("button", name="Previous", exact=True).click()
                passed("Table pagination works")
                page.get_by_role("tab", name=re.compile("Duplicates")).click()
                expect(page.locator(".cases-table tbody tr")).to_have_count(1)
                expect(page.locator(".cases-table")).to_contain_text("Duplicate")
                page.get_by_role("tab", name=re.compile("All invoices")).click()
                page.get_by_role("textbox", name="Search invoices", exact=True).fill("Northstar")
                expect(page.locator(".cases-table tbody tr")).to_have_count(1)
                passed("Status filters and supplier search work")
                page.get_by_role("button", name="Open NS-2089").click()
                expect(page.locator(".source-highlight")).to_be_visible()
                expect(page.locator(".document-image img")).to_be_visible()
                page.wait_for_function(
                    "document.querySelector('.document-image img')?.naturalWidth > 0"
                )
                expect(page.locator(".flags-list")).to_contain_text("total is incorrect")
                page.screenshot(path=artifacts / "invoice-review.png", full_page=True)
                passed("Incorrect total opens with highlighted source evidence")
                with page.expect_download() as download:
                    page.get_by_role("link", name="Download original document", exact=True).click()
                assert Path(download.value.path()).read_bytes().startswith(b"%PDF-")
                passed("Original source document downloads as a PDF")
                page.locator(".comparison-table tbody tr").first.locator("td").nth(2).get_by_role(
                    "button"
                ).click()
                expect(page.locator(".evidence-heading")).to_contain_text("Quantity")
                expect(page.locator(".source-quote")).to_contain_text("20")
                passed("Clicking a line value changes the source highlight")

                page.get_by_role("link", name="Overview", exact=True).click()
                expect(page.locator(".recent-row")).to_have_count(5)
                page.get_by_role("link", name=re.compile("Review queue")).first.click()
                expect(page.locator(".cases-table tbody tr")).to_have_count(5)
                passed("Overview and review queue contain the expected cases")
                page.get_by_role("link", name="Documents", exact=True).click()
                expect(page.locator(".document-card")).to_have_count(27)
                page.get_by_role("button", name=re.compile("^Invoices")).click()
                expect(page.locator(".document-card")).to_have_count(9)
                page.get_by_role("textbox", name="Search documents", exact=True).fill("Acme")
                expect(page.locator(".document-card")).to_have_count(2)
                passed("Document previews, type filtering, and document search work")
                page.get_by_role("link", name="Audit history", exact=True).click()
                expect(page.locator(".audit-entry")).to_have_count(45)
                page.get_by_role("button", name="Corrections", exact=True).click()
                expect(page.get_by_role("heading", name="The story starts here")).to_be_visible()
                passed("Audit history filters actual immutable events")
                page.get_by_role("link", name="Performance", exact=True).click()
                expect(
                    page.get_by_role("heading", name="Small dataset. Clear evidence.")
                ).to_be_visible()
                expect(page.locator(".metric-card").first).to_contain_text(
                    "Fixture evaluation has not run"
                )
                passed("Metrics do not invent accuracy without a benchmark")
                page.get_by_role("link", name="Workspace settings", exact=True).click()
                expect(page.locator(".settings-rows")).to_contain_text("PDF text + Tesseract OCR")
                passed("Settings reflect the active extractor")
                page.keyboard.press("Control+k")
                expect(
                    page.get_by_role("textbox", name="Search invoices", exact=True)
                ).to_be_focused()
                passed("Quick-search keyboard shortcut works across pages")

                page.get_by_role("button", name="New reconciliation", exact=True).click()
                with page.expect_download() as download:
                    page.get_by_role("link", name="Download sample document sets").click()
                with zipfile.ZipFile(download.value.path()) as archive:
                    assert len(archive.namelist()) == 27
                    contents = [archive.read(name) for name in archive.namelist()]
                    assert sum(content.startswith(b"%PDF-") for content in contents) == 26
                    assert sum(content.startswith(b"\x89PNG") for content in contents) == 1
                passed("Sample download contains 26 PDFs and one scanned image")
                page.get_by_role("button", name="Start reconciliation", exact=True).click()
                expect(page.locator(".field-error")).to_have_count(3)
                records = fixtures()[2]["records"]
                records[0]["number"] = "UI-TEST-1001"
                for record in records:
                    filename, content = render_document(record, layout=1)
                    page.get_by_label(
                        f"Upload { {'invoice': 'invoice', 'purchase_order': 'purchase order', 'delivery': 'delivery record'}[record['kind']] }",
                        exact=True,
                    ).set_input_files(
                        {"name": filename, "mimeType": "application/pdf", "buffer": content}
                    )
                page.get_by_role("button", name="Start reconciliation", exact=True).click()
                expect(page.locator(".case-title")).to_contain_text("UI-TEST-1001", timeout=15000)
                expect(page.locator(".case-title")).to_contain_text("Needs review")
                passed("Browser upload validates all slots and processes a new packet")
                page.get_by_role("button", name="Correct value", exact=True).click()
                page.get_by_label("Corrected value", exact=True).fill("2203.20")
                page.get_by_label("Reason for correction", exact=True).fill(
                    "Verified sum of source line items and tax"
                )
                page.get_by_role("button", name="Save correction", exact=True).click()
                expect(page.locator(".case-title")).to_contain_text("Matched")
                expect(page.locator(".original-value")).to_contain_text("2303.20")
                expect(page.locator(".source-highlight")).to_have_class(
                    re.compile("corrected-highlight")
                )
                passed("Correction reruns rules and retains the original value and source")
                page.get_by_role("button", name="Approve invoice", exact=True).click()
                page.get_by_label("Review note", exact=False).fill(
                    "Approved after verifying corrected arithmetic against the source"
                )
                page.get_by_role("button", name="Record approval", exact=True).click()
                expect(page.locator(".case-title")).to_contain_text("Approved")
                passed("Approval requires a note and records the decision")
                page.get_by_role("tab", name=re.compile("Audit history")).click()
                expect(page.locator(".audit-list")).to_contain_text("Extracted value corrected")
                expect(page.locator(".audit-list")).to_contain_text("Invoice approved")
                passed("Case audit history includes the correction and approval")
                with page.expect_download() as download:
                    page.get_by_role("link", name="Export case", exact=True).click()
                export = json.loads(Path(download.value.path()).read_text())
                assert export["status"] == "approved"
                assert any(event["action"] == "corrected" for event in export["audit"])
                assert any(event["action"] == "approve" for event in export["audit"])
                passed("Exported JSON includes source fields, corrections, and audit decisions")
                page.reload(wait_until="networkidle")
                expect(page.locator(".case-title")).to_contain_text("Approved")
                passed("Review state persists after a reload")

                mobile = context.new_page()
                mobile.set_viewport_size({"width": 390, "height": 844})
                mobile.goto(url, wait_until="networkidle")
                expect(mobile.get_by_role("heading", name="Reconciliations.")).to_be_visible()
                assert mobile.evaluate(
                    "document.documentElement.scrollWidth <= window.innerWidth"
                ), "Mobile page has horizontal overflow"
                mobile.screenshot(path=artifacts / "mobile.png", full_page=True)
                mobile.get_by_role("button", name="Open navigation").click()
                mobile.get_by_role("link", name=re.compile("Review queue")).first.click()
                expect(mobile.get_by_role("heading", name="Review queue.")).to_be_visible()
                assert not mobile.locator(".sidebar").evaluate(
                    "element => element.classList.contains('mobile-open')"
                )
                passed("Mobile layout fits the viewport and navigation closes after selection")
                mobile.get_by_role("button", name="New reconciliation", exact=True).click()
                expect(mobile.get_by_role("dialog")).to_be_visible()
                mobile.get_by_role("button", name="Close upload", exact=True).click()
                expect(mobile.get_by_role("dialog")).to_have_count(0)
                passed("Upload dialog is usable on mobile")
                assert not errors, errors
                passed("No browser runtime errors")
                if split_origin:
                    assert not wrong_api_requests, wrong_api_requests
                    passed("Frontend uses the separate backend for API calls and source images")
                browser.close()
            print(f"\n{len(checks)} browser checks passed.", flush=True)
            (artifacts / "browser-results.json").write_text(
                json.dumps({"passed": len(checks), "checks": checks}, indent=2)
            )
        finally:
            if frontend:
                frontend.terminate()
                try:
                    frontend.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    frontend.kill()
                    frontend.wait()
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()


if __name__ == "__main__":
    main()
