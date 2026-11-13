# Security & Privacy — InvoiceFlow Pro

This project is **not production accounting software**. Financial data and vendor details are sensitive. Only use synthetic examples when evaluating the public repository.

## Current defenses

- Every private API requires a separate **strong** `X-Operator-Key` (24+ characters, not a placeholder). No operator key is persisted in browser localStorage.
- PDF and text files have a configured **byte limit**; text-based PDFs also have a **page count limit**. Malformed, encrypted, unsupported and scanned/image-only inputs are rejected.
- This application stores **structured fields, source SHA-256, file name, and audit metadata** in local SQLite, not original source document bytes. Parsed fields still contain sensitive financial data.
- The database uses a unique source hash and normalized vendor/invoice-number key, with atomic transactions to stop straightforward duplicates.
- Financial totals are validated using `Decimal`, not binary floats. Validation flags block local approval, though they cannot prove invoice authenticity.
- `version` checking blocks stale reviewer writes; approved records cannot be edited in this simple workflow.
- Optional AI extraction is **off by default** and requires both `use_ai=true` and `ai_authorized=true` from an authenticated operator. It must not be used for confidential invoices without authorization and third-party data-processing review.
- No payment execution, bank access, invoice email sending, QuickBooks/Xero write connector or credential collection exists.
- Docker binds port 8000 to localhost, not the public internet.

## Before any production use

- Implement real SSO, RBAC, MFA, CSRF defenses where relevant, explicit employee identities, rate limits, session expiry and strong secrets management.
- Conduct a privacy impact assessment and legal data-processing review, including third-party AI vendor retention/handling terms.
- Add encrypted storage, authenticated backups, deletion/retention policies, malware/PDF sandboxing, and dependency/penetration testing.
- Implement structured logging that excludes vendor/customer personal details and documents, plus tamper-evident audit trails.
- Verify taxes, invoice authenticity, purchase orders, supplier banking changes and payment controls with qualified finance teams.
- Treat AI outputs as **untrusted**; check against original source content and require review before decisions.
- Never treat local approval as permission to transfer money or pay suppliers.

For private security reports, contact https://nextgentechdev.com without sharing credential strings or financial documents.
