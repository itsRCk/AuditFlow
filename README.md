# AuditFlow

Reconcile an invoice with its purchase order and delivery record. Click any
extracted value to highlight the original source. Correct it with a reason,
rerun the matching rules, and export the complete decision trail.

The first version is a working, single-user full-stack demo: React + TypeScript,
FastAPI + Pydantic, SQLite, content-addressed local files, and a durable background
job queue. PDF text extraction and Tesseract OCR work without API credentials.
An optional Gemini multimodal adapter is included.

## Run locally

Prerequisites: Node **24** (minimum 22.12), Python **3.12**, [uv](https://docs.astral.sh/uv/),
and Tesseract with its English language pack. On Ubuntu, the OCR packages are
`tesseract-ocr tesseract-ocr-eng`. Browser tests also require Chromium or a
Playwright-managed Chromium installation.

From the checkout:

```bash
bash scripts/setup.sh
npm run dev
```

The frontend uses port **3000** and proxies `/api` to FastAPI on **8000**. The dev
command starts both services and shuts them down together. Nine sample cases
and 27 real documents are seeded into a new, empty database. Existing records
are preserved on restart. Use `AUDITFLOW_SEED_DEMO=false` for an empty workspace.

For the built application, `npm run build` followed by `npm start` serves both
the frontend and API on **3000**. Use a single server process; the local job
worker is designed for one instance. There is no authentication in this demo.

Cloud tasks already have an isolated checkout. Work in the existing
`/workspace/AuditFlow` directory; no additional Git worktree is needed.

## Deploy with Vercel

Vercel Services deploys the React frontend and the Python API in one project on
the same domain. The API container installs **Tesseract and English language
data**, along with the hashed Python runtime dependencies. **Turso SQL** retains
records, jobs, revisions, and immutable audit history. **Private Vercel Blob**
retains original documents and source images; `/tmp` is only a cache.

The browser uploads files directly into private Blob storage, preserving the
20 MB per-document limit without passing large bodies through Vercel Functions.
Vercel Queues invokes a private Node consumer, which calls the OCR container
through a service binding. SQL claims have expiring leases and fencing tokens so
redelivery cannot process a packet twice or overwrite a newer claim. Transient
processing failures retry up to three times, then remain visible for manual retry.

This is a public demonstration without user authentication. Use fictional
documents; API readers can see all cases. Vercel Services, container images, and
Queues currently use Vercel's beta features.

1. Import **itsRCk/AuditFlow** at the repository root and select the **Services**
   framework. `vercel.json` defines the Vite frontend, container API, private queue
   consumer, and public routing. No separate backend host or `VITE_API_BASE_URL`
   is required.
2. Connect **Turso Cloud**, selecting the **Starter ($0/month)** plan in **iad1**.
   With a linked CLI project, use `vercel install tursocloud --name auditflow-db
--metadata region=iad1 --plan starter`. The account owner must accept its
   marketplace terms in their browser. It injects `TURSO_DATABASE_URL` and
   `TURSO_AUTH_TOKEN`; connect each environment that will be deployed.
3. Connect a **private** Blob store in **iad1**. For a new project, use
   `vercel blob create-store auditflow-files --access private --region iad1 --yes`.
   Reuse existing project storage rather than creating duplicates. The connection
   supplies `BLOB_READ_WRITE_TOKEN`.
4. Set **`PORT=8000`**, **`AUDITFLOW_AI_ENABLED=false`**, and an encrypted random
   **`AUDITFLOW_JOB_TOKEN`** in the project environments. The job token authorizes
   the consumer's internal processor requests. Keep all credentials in server
   environment variables; never prefix a secret with `VITE_`.
5. Deploy from the repository root with `vercel deploy --prod`. Check
   `/api/health` for `status=ok`, `processing_mode=vercel_queue`, and eventually
   `pending_jobs=0`. `worker_alive` is false because this deployment uses Queues.
   The empty database seeds nine fictional cases and 27 documents.
6. Verify upload → extraction → source highlight → correction → approval → export,
   then verify a new container instance can retrieve the same records and files.

To let Codex deploy into your Vercel account, create a scoped access token at
[Vercel's token settings](https://vercel.com/account/tokens) and add it securely
as **`VERCEL_TOKEN`** in this cloud environment's secret settings. Do not paste it
into chat, tracked files, or frontend variables. If this environment restricts
network access, allow `api.vercel.com`, `vercel.com`, and `*.vercel.app`, then
save/publish the environment settings. The Vercel project also needs the managed
storage connections above before deployment can serve the API.

For local container verification:

```bash
docker compose up --build -d
# The API listens on port 8000; the named auditflow-data volume retains records.
```

Keep the named volume when stopping or upgrading the service. On cloud build
machines that inspect HTTPS, supply their trusted CA bundle using Docker's
build-only secret; TLS verification and dependency hash checks remain enabled:

```bash
docker build --secret id=build_ca_bundle,src=/etc/ssl/certs/ca-certificates.crt -t auditflow-api .
# Build the stateless Vercel API image with its production dependencies:
docker build --secret id=build_ca_bundle,src=/etc/ssl/certs/ca-certificates.crt -f Dockerfile.vercel -t auditflow-vercel .
```

To exercise the separate frontend/backend setup locally:

```bash
VITE_API_BASE_URL=http://127.0.0.1:3100 npm run build
npm run test:e2e -- --split-origin
npm run build # restore the local frontend that uses /api on its own origin
```

This test serves static assets on **3101** and the isolated API on **3100** and
saves artifacts under `test-results/split-origin/`.

## Try the workflow

1. Open **Reconciliations**. The sample cases cover three PDF layouts and a scanned
   invoice. Acme demonstrates duplicate detection, Forma a quantity mismatch,
   Northstar an incorrect total, Evergreen a delivery shortage, and Vertex an
   incorrect unit price.
2. Open Northstar's `NS-2089` case. Click **Invoice · Total**, or any value in
   **Extracted records**, to highlight its precise location in the source document.
3. Correct the total from `2303.20` to `2203.20`, adding a reason. The original
   extraction and its source remain in the record; deterministic checks run again.
4. Approve or reject with a review note. Export the case as JSON to include its
   current records, original values, corrections, source coordinates, and all audit
   events. Export the case list or selected rows as CSV.
5. Download sample document sets from the upload dialog. Upload an invoice, PO,
   and delivery together. Uploading identical bytes returns the existing case;
   another packet with the same supplier and invoice number is flagged as a duplicate.

The **Documents**, **Review queue**, **Audit history**, **Performance**, and
**Workspace settings** pages display actual stored records and measured results.

## Supported document scope

English PDFs, PNG/JPEG scans, and UTF-8 text; up to **20 MB and 20 pages** per
document. Text fields must have explicit labels. Financial tables must have
item codes, descriptions, quantities, unit prices, and line amounts. Delivery
tables need item codes, descriptions, and quantities. Whitespace-aligned and
pipe-delimited tables are supported.

```text
Supplier: Example Supply Co.
Invoice no: INV-2026-101
PO reference: PO-2026-041
Date: 2026-10-06
Currency: USD
SKU | Description | Qty | Unit price | Amount
PAP-01 | A4 paper | 3 | 18.50 | 55.50
Subtotal: 55.50
Tax: 4.44
Total: 59.94
```

PO documents use `PO number:` instead of `Invoice no:`; delivery records use
`Delivery note:`. Supported label aliases and date formats live in
`server/extraction.py`. Currencies are USD, EUR, GBP, INR, CAD, and AUD; no currency
conversion is performed. This version uses cents as the monetary unit.

Unsupported/missing required fields or low OCR confidence enter review; no
complete financial record is invented. A document that cannot validate must be
uploaded again in a supported format before its case can be approved. Re-upload
the full corrected packet; the original case remains in the audit history and
can be rejected. Partial invoicing, credit notes, line-level discounts, multiple
delivery records, handwriting, and description-only fuzzy matching are outside
the first version.

## Rules and persistence

- **Three-way matching:** normalize exact item codes; compare suppliers, PO
  references, currencies, ordered/invoiced/received quantities, and unit prices.
- **Financial checks:** Decimal arithmetic checks each line amount, subtotal,
  and total plus stated tax. Tax rates are not independently inferred or verified.
- **Duplicate checks:** normalized supplier + invoice number, with the earliest
  submitted case as the canonical record. Rejected records remain evidence for
  duplicate detection; explicitly documented overrides require a review note.
- **Conservative review:** unknown extraction, repeated item codes, missing items,
  mismatching references, and source uncertainty do not auto-match.
- **Amount flagged:** a potential discrepancy estimate in the invoice currency,
  using the maximum of total mismatch and line-level discrepancies; quantities
  and delivery shortages on the same line are not double counted. Duplicate
  cases flag the full invoice amount. The dashboard totals open USD cases only.
- **Idempotency:** each packet is keyed by the SHA256 of its three document hashes
  and kinds. Original files are stored by content hash, outside application code.
- **Durable jobs:** SQL-backed `queued → running → completed/failed` states;
  interrupted running jobs return to the queue on startup. A failed extraction
  can be retried after correcting its prerequisite.
- **Review:** schema-validated corrections use optimistic case revisions to avoid
  overwriting concurrent work. Changes rerun rules and invalidate decisions if
  their evidence changes, including dependent duplicate cases.
- **Audit:** append-only SQL events record actor, timestamp, reason, before/after
  values, source, rules, decisions, and case exports. SQL triggers reject event
  updates and deletions. The demo reviewer identity is fictional; this is not a
  cryptographically tamper-evident or authenticated production audit system.

Data lives in ignored `.data/`: `auditflow.db`, original `files/`, rendered
`previews/`, and `evaluation.json`. Set `AUDITFLOW_DATA_DIR` to move all data to a
persistent location. Processes must restart after restoring an environment;
SQLite and files survive ordinary restarts. Back up the entire data directory
with the application stopped, or use SQLite's backup API and copy the file store.

## Validation and measured evidence

```bash
npm test          # API, extraction, rules, persistence, provider contract tests
npm run evaluate # independent fixture ground truth → .data/evaluation.json
npm run build    # TypeScript + production assets
npm run test:e2e # real Chromium, isolated database, full upload/review/export flow
```

The browser script starts its own temporary production server on port **3100**;
it does not alter the running workspace. It saves screenshots and a result file
under ignored `test-results/`. Set `AUDITFLOW_CHROMIUM` to choose a system browser.
If none is installed, `.venv/bin/python -m playwright install chromium` downloads
the browser (network access to Playwright's CDN is required).

The local fixture benchmark has **27 documents**, **423 labelled fields**,
**three layouts**, **one scanned invoice**, and **nine cases**. Exact field
accuracy and discrepancy precision/recall are calculated from independent labels;
results are not hardcoded into the UI. This small synthetic dataset is not a
production accuracy estimate. Future accuracy work needs held-out real documents
and separate OCR/AI evaluations.

Correction effort reports recorded field corrections and corrections among
reviewed cases. Review duration is not yet measured. Cost uses observed provider
token usage and explicitly configured rates. Local extraction has zero provider
API charges; displayed API costs exclude compute, storage, and human time.

## Optional multimodal AI

Local extraction is the default. To opt in, securely set these process variables
before restarting the application:

| Variable                              | Purpose                                                        |
| ------------------------------------- | -------------------------------------------------------------- |
| `AUDITFLOW_AI_ENABLED=true`           | Enable cloud extraction; sends document page images to Gemini  |
| `AUDITFLOW_AI_KEY`                    | Secure Gemini API key binding; never store it in tracked files |
| `AUDITFLOW_AI_MODEL`                  | Model name; defaults to `gemini-2.5-flash`                     |
| `AUDITFLOW_AI_INPUT_USD_PER_MILLION`  | Current input-token price for cost measurement                 |
| `AUDITFLOW_AI_OUTPUT_USD_PER_MILLION` | Current output-token price for cost measurement                |

The destination is **generativelanguage.googleapis.com**. If cloud Internet
access is restricted, add that hostname in environment settings. No provider
key is required for this version's core workflow. `.env.example` documents the
variables; `.env` files are not automatically loaded. Configure the process
through your environment manager or shell rather than pasting secrets into chat.

Provider output must pass the same Pydantic schema. Evidence quotes must agree
with the returned value and resolve uniquely to page words; fields whose source
cannot be verified go to review. OCR source resolution can still be imperfect
and model evidence must be checked by a reviewer. AI does not perform matching
or arithmetic. Provider contract tests use mocked responses; a live provider
request has not been validated without credentials.

## Project map

| Location                                | Responsibility                                                       |
| --------------------------------------- | -------------------------------------------------------------------- |
| `src/`                                  | Dashboard, upload, source-linked review, documents, metrics, history |
| `server/main.py`                        | HTTP API, startup, exports, static frontend                          |
| `server/extraction.py`                  | PDF/OCR extraction and source bounding boxes                         |
| `server/models.py`                      | Validated records and correction schema                              |
| `server/reconcile.py`                   | Deterministic rules and monetary arithmetic                          |
| `server/store.py`                       | SQLite, file storage, jobs, revisions, audit                         |
| `server/provider.py`                    | Opt-in multimodal extraction adapter                                 |
| `server/demo.py` / `server/evaluate.py` | Real fixtures and labelled evaluation                                |
| `tests/` / `scripts/browser_smoke.py`   | Backend and browser validation                                       |

Production work should add authenticated users and access control, encrypted
managed storage, a multi-worker queue, migration/versioning policies, resource
limits for untrusted document rendering, observability, and a broader held-out
evaluation corpus. The current build is designed to demonstrate the complete
workflow and make those next steps concrete.
