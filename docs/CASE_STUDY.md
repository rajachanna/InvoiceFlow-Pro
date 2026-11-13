# InvoiceFlow Pro — Engineering case study

**Developer:** Raja Channa · NextGen Tech Solutions  
**Release:** v0.1 local finance-workflow prototype

## The client problem

Accounts payable teams need more than invoice OCR. Intake must handle damaged files, ensure numbers reconcile, detect repeat invoices, support human review and keep a clear record of decisions. Accidental duplicate approvals and unverified extracted data can create substantial financial exposure.

## What this prototype demonstrates

### 1. Guarded intake

`POST /api/invoices/upload` accepts a limited PDF (digital text layer) or a UTF-8 invoice template. Size, extension, PDF header and page-count checks reduce unbounded input processing. Parsed source document bytes are **not** stored in the application database.

### 2. Two extraction paths, clearly labeled

A deterministic parser handles known templates with labels and `ITEM:` rows. An optional external AI adapter exists but is *off* unless an authenticated operator both selects and authorizes external processing. Both paths produce structured candidate fields for manual verification.

### 3. Financial correctness checks

Using Python `Decimal`, the engine verifies `subtotal + tax ≈ total`, line-item amounts, mandatory fields and valid dates. These checks are transparent **review flags**, not a guarantee of financial or regulatory correctness.

### 4. Duplicate prevention and concurrency

Raw source SHA-256 catches identical uploads. A normalized `(vendor, invoice number)` unique key catches simple same-invoice resubmissions even when file bytes differ. A transactional store plus optimistic versioning reduces repeat approvals and stale updates.

### 5. Human-controlled decisions

A reviewer can inspect, correct and approve/reject a pending invoice. Invoices with unresolved flags cannot be approved. Decisions are locally audited; no payments or accounting API calls follow.

## Architecture and acceptance

| Review area | Evidence | Limitation |
| --- | --- | --- |
| Digital PDF and UTF-8 parsing | Parser + generated-PDF tests | No scans/OCR |
| Decimal validations | `tests/test_extract.py` | Tax categories and supplier legitimacy unknown |
| Duplicate checks | `tests/test_api.py` | Sophisticated vendor impersonation not detected |
| Human approval control | Operator API + versioned corrections | Single-operator demo |
| Audit | SQLite events and dashboard | Not tamper-proof |
| Optional AI | Mocked JSON adapter tests | No live AI account verified |
| Finance integrations | Roadmap only | QuickBooks/Xero are not connected |

## Demo walkthrough

1. Install test dependencies and run `python scripts/demo.py` with **synthetic sample data**.
2. Confirm a sample document enters `needs_review` and its arithmetic checks pass.
3. Attempt a duplicate upload; verify HTTP 409.
4. Approve the sample with manual action; confirm metrics and audit history.
5. Upload a mismatched invoice and confirm approval is blocked until corrected.
6. Test with a generated text-based PDF and rerun the automated suite.

## Client delivery proposal

**Discovery → vendor/PO field map → authorized document samples → validation acceptance criteria → human approval UI → sandbox accounting integration → security & UAT signoff.**

Every provider integration should have its own verifiable sandbox milestone. Commercial work should avoid implying automatic payments, guaranteed fraud protection, or complete tax compliance.

**Contact:** https://nextgentechdev.com
