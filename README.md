# AuditFlow

AuditFlow checks an invoice against its purchase order and delivery record. It
shows where quantities, prices, and totals disagree, and lets you inspect the
documents before recording a decision.

**[Open AuditFlow](https://auditflow-flax.vercel.app)**

The live demo is a shared, public workspace. Use the sample documents or fictional
files; other visitors can access uploaded documents and reviews.

## Get started

1. Open **Reconciliations** and click **New reconciliation**.
2. Add one **invoice**, one **purchase order**, and one **delivery record** in their
   respective upload slots. You can download sample document sets from the same
   dialog.
3. Click **Start reconciliation**. AuditFlow reads the documents and compares their
   line items, references, and financial totals.
4. Open the case to see the result. Cases with discrepancies or uncertain
   extraction appear in the **Review queue**.

Uploading the same three files again opens their existing case. A different set
of files with the same supplier and invoice number can be flagged as a duplicate.

## Understand the result

| Status            | What it means                                                            |
| ----------------- | ------------------------------------------------------------------------ |
| Processing        | The documents are still being read.                                      |
| Matched           | The extracted records passed the matching checks.                        |
| Needs review      | A discrepancy or uncertain value needs someone to check it.              |
| Duplicate         | The supplier and invoice number match an earlier case.                   |
| Approved          | A reviewer approved the invoice and left a note.                         |
| Rejected          | A reviewer rejected the invoice and left a note.                         |
| Processing failed | Processing did not finish. Open the case for the error and retry option. |

**Three-way match** shows the ordered, invoiced, and received quantities alongside
any issues. AuditFlow also checks unit prices, line amounts, subtotals, tax plus
subtotal, supplier names, purchase order references, and currencies.

The **Amount flagged** figure is an estimate of the value involved in open
discrepancies. The dashboard adds up USD cases only; it does not convert currencies.

## Check the original document

Open a case and click an extracted quantity, price, total, or other field. The
**Source document** panel shows the relevant document and highlights the value's
location when evidence is available.

Use the document controls to switch between the invoice, purchase order, and
delivery record, change pages, zoom, or download the original file. The
**Extracted records** tab gives you a fuller view of what AuditFlow read.

Fields whose source could not be verified are sent for review. Check the original
document before relying on them.

## Make a correction or record a decision

Use **Correct value** when the extracted value differs from the document. Enter
the corrected value and a reason, then save. AuditFlow runs the matching checks
again and keeps the original extraction, source location, and correction history.

If the document itself contains an error, record your assessment in the review
note. **Approve invoice** and **Reject invoice** both require a note. Approval can
acknowledge an unresolved discrepancy, so explain what you checked and why you
accepted it.

A later change to the evidence can invalidate an earlier decision. Check the
case's **Audit history** to see corrections, decisions, and exports in order.

## Try the sample cases

The sample documents include a few deliberate mistakes:

| Supplier              | What to look for                                              |
| --------------------- | ------------------------------------------------------------- |
| Acme Supply Co.       | A duplicate invoice submitted in another layout.              |
| Forma Office          | An invoiced quantity that differs from the purchase order.    |
| Northstar Electronics | A stated total that does not equal the line amounts plus tax. |
| Evergreen Packaging   | Fewer items delivered than invoiced.                          |
| Vertex Hardware       | An invoice unit price that differs from the purchase order.   |

Start with Northstar's `NS-2089`. Its invoice states **2,303.20**, while the line
amounts plus tax come to **2,203.20**. Click the total discrepancy to see the
original figure in the invoice. The shared demo may already contain reviews or
corrections from another visitor; the original document and history remain
available.

## Find your way around

| Page               | Use it to                                                                                     |
| ------------------ | --------------------------------------------------------------------------------------------- |
| Overview           | See workspace totals, reconciliation health, and recent cases.                                |
| Reconciliations    | Search, filter, and open invoices; select cases for export.                                   |
| Review queue       | Work through discrepancies, duplicates, and processing failures.                              |
| Documents          | Browse source documents, download originals, and open their cases.                            |
| Audit history      | Follow the recorded activity across cases.                                                    |
| Performance        | See processing time, correction counts, costs, and fixture evaluation results when available. |
| Workspace settings | Check supported formats, file limits, and matching rules.                                     |

The theme button in the header switches between light and dark mode and remembers
your choice.

## Export your work

- **Export** on the reconciliation list downloads a CSV summary of all cases.
- Select invoices with the checkboxes, then use **Export selected** to download
  just those cases as CSV.
- **Export case** inside a case downloads JSON with the extracted records,
  original values, source locations, corrections, discrepancies, and audit history.

CSV is useful for a spreadsheet overview. The case JSON contains the detailed
evidence behind a review.

## Which documents work?

AuditFlow currently supports **English PDF, PNG, JPEG, and UTF-8 TXT** files, up to
**20 MB and 20 pages per document**.

Use documents with clear field labels and item codes. Invoice and purchase order
tables should contain descriptions, quantities, unit prices, and line amounts.
Delivery records need item codes, descriptions, and quantities. The sample
downloads show the supported layouts.

Supported currencies are **USD, EUR, GBP, INR, CAD, and AUD**. Monetary totals use
cents, and documents in different currencies are flagged for review.

This version handles one invoice, one purchase order, and one delivery record per
case. Partial invoicing, credit notes, multiple delivery records, handwriting,
and matching items by description alone are outside its current scope. Tax rates
are not independently verified.

If a document cannot be read into a valid record, it cannot be approved. Prepare
a supported version and upload the full document set again; the earlier case
stays in the history.

Performance figures describe the measured workspace activity. Extraction accuracy
and discrepancy precision/recall, when shown, come from a small synthetic fixture
benchmark and do not predict accuracy on every invoice format.

## Run it locally

Install Node 24, Python 3.12, [uv](https://docs.astral.sh/uv/), and Tesseract with
its English language pack, then run:

```bash
bash scripts/setup.sh
npm run dev
```

Open **http://localhost:3000**. A new local workspace starts with nine sample cases.
Its documents, corrections, and reviews are saved in `.data/` between restarts.

See the [development guide](docs/development.md) for configuration, tests, and
deployment details.
