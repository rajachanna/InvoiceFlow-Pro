# InvoiceFlow Pro — Product roadmap

## ✅ v0.1: local accounts payable review lab

- UTF-8 invoices + text-layer PDFs, controlled extraction limits
- Deterministic demo parser; optional AI adapter with explicit authorization
- Decimal subtotal/tax/item validation and review flags
- Duplicate hash + normalized vendor/invoice-number prevention
- Local reviewer correction and approve/reject lifecycle
- SQLite audit events, metrics, CSV export and responsive dashboard
- Offline automated tests and synthetic client demo

## 🔲 v0.2: higher-quality document intake

- OCR for scanned invoices with sandboxed processing
- Field-level citation boxes/provenance/confidence and OCR quality flags
- Many invoice layouts and multilingual supplier templates
- Secure background jobs, bulk operations, idempotent import receipts

## 🔲 v0.3: business workflow integrations

- Real multi-user roles and approvals per cost center
- Purchase order / goods receipt matching and invoice policy rules
- Independently tested QuickBooks/Xero sandbox accounts (OAuth, read-only preflight before writes)
- Outbox, webhook reconciliation, retry handling and integration test reports

## 🔲 Beyond MVP

- Audit hardening, retention/deletion, tenant isolation, approval SLAs, ERP connectors
- Vendor fraud/risk assessment with independently evaluated false-positive rates
- Production infrastructure and monitored pilot using authorized test data

**No financial transaction or real accounting sync is implemented in v0.1.**
