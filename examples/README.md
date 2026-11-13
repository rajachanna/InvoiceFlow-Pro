# Synthetic demonstration invoices

- `invoice-sample.txt`: a fictional, USD-based invoice template supported by the deterministic parser.
- `invoice-sample.pdf`: generated text-based PDF of the same fictional data, suitable for an end-to-end PDF upload.
- For digital PDF support, the automated test `test_text_pdf_roundtrip` generates a fresh text-based PDF from this sample using ReportLab and extracts it using pypdf.

Never commit real invoices, bank details, customer names, tax identifiers or credentials.
