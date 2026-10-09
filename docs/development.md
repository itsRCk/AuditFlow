# Development guide

The [README](../README.md) covers using AuditFlow. This guide covers running and
maintaining your own instance.

## Local setup

Use Node 24 (minimum 22.12), Python 3.12, [uv](https://docs.astral.sh/uv/), and
Tesseract with English language data. On Ubuntu, the OCR packages are
`tesseract-ocr tesseract-ocr-eng`.

```bash
bash scripts/setup.sh
npm run dev
```

The setup script installs locked dependencies, builds the frontend, and runs the
baseline fixture evaluation. Development starts Vite on port 3000 and FastAPI on
port 8000; Vite proxies `/api` to FastAPI.

For a built application, run `npm run build` followed by `npm start`. This serves
the frontend and API together on port 3000. Run one local server process.

Configure process variables through your shell or environment manager; `.env`
files are not loaded automatically. See [`.env.example`](../.env.example) for
available settings. `AUDITFLOW_SEED_DEMO=false` starts an empty workspace, and
`AUDITFLOW_DATA_DIR` sets its storage directory.

Local data lives in `.data/`: SQLite records, original files, rendered previews,
and fixture evaluation results. Back up the whole directory with the app stopped,
or use SQLite's backup API and copy the file store. Keep existing data when
restarting or upgrading.

## Checks

```bash
npm test
npm run build
npm run format:check
AUDITFLOW_AI_ENABLED=false npm run evaluate
npm run test:e2e
```

Browser tests require Chromium or a Playwright-managed browser. They use a
temporary database and a separate server on port 3100, and save results in
`test-results/`. Set `AUDITFLOW_CHROMIUM` to use a specific browser executable.

## Vercel deployment

Import the repository root as a Vercel Services project. [`vercel.json`](../vercel.json)
defines the frontend, Python OCR container, upload handler, queue publisher, and
queue consumer on one domain.

Connect a Turso database and a **private** Vercel Blob store to the project.
Configure these server variables for each deployed environment:

- `TURSO_DATABASE_URL`
- `TURSO_AUTH_TOKEN`
- `BLOB_READ_WRITE_TOKEN`
- `AUDITFLOW_JOB_TOKEN` — a random secret for internal queue requests
- `PORT=8000`
- `AUDITFLOW_AI_ENABLED=false`

Keep secret values in the hosting environment. Frontend variables prefixed with
`VITE_` are public.

Deploy with the connected Git repository or `vercel deploy --prod`. Check
`/api/health` for `status=ok`, `processing_mode=vercel_queue`, and eventually
`pending_jobs=0`. `worker_alive=false` is expected with Vercel Queues.

Turso retains records, job state, and audit events. Private Blob retains originals
and previews; the container's `/tmp` directory is only a cache. The current app
has no user authentication or workspace access controls.

## Optional AI extraction

PDF text extraction and Tesseract OCR work without an AI key. To enable the Gemini
adapter, configure `AUDITFLOW_AI_ENABLED=true` and `AUDITFLOW_AI_KEY` before
restarting. This sends document page images to Google's API.

`AUDITFLOW_AI_MODEL` selects the model. Configure
`AUDITFLOW_AI_INPUT_USD_PER_MILLION` and `AUDITFLOW_AI_OUTPUT_USD_PER_MILLION` to
report provider costs from observed token usage. Without configured rates, costs
are shown as unknown. Provider costs exclude hosting, storage, and review time.

## Where to make changes

| Location                                | Responsibility                                             |
| --------------------------------------- | ---------------------------------------------------------- |
| `src/`                                  | Upload, reconciliation, source review, and workspace pages |
| `src/components/ui/`                    | Shared shadcn components                                   |
| `src/styles/`                           | Typography, themes, and responsive layouts                 |
| `server/extraction.py`                  | PDF/OCR extraction and source coordinates                  |
| `server/models.py`                      | Record validation and allowed corrections                  |
| `server/reconcile.py`                   | Matching rules and Decimal arithmetic                      |
| `server/store.py`                       | Persistence, jobs, corrections, and audit events           |
| `server/cloud.py`                       | Managed SQL and private file storage                       |
| `server/main.py`                        | HTTP API and exports                                       |
| `server/demo.py` / `server/evaluate.py` | Sample documents and measured fixture evaluation           |
| `tests/` / `scripts/browser_smoke.py`   | Backend and browser checks                                 |

The UI follows the supplied shadcn/typeset scale: 16px desktop body text and 18px
on mobile, with Geist fonts and persistent light/dark themes. Keep original
document images inside `not-typeset` containers so typography changes do not
alter source highlight geometry.
