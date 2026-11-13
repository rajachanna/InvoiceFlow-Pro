"""Text-layer PDF extraction & conservative field matching (no OCR)."""
from datetime import date
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import BytesIO
import re

from pypdf import PdfReader


class DocumentError(ValueError):
    pass


ALIASES = {
    "vendor": ["vendor", "supplier", "from"],
    "invoice_number": ["invoice number", "invoice no", "invoice #", "invoice id"],
    "invoice_date": ["invoice date", "date issued", "issue date"],
    "due_date": ["due date", "payment due"],
    "currency": ["currency"],
    "subtotal": ["subtotal", "sub total", "net amount"],
    "tax": ["tax", "vat", "sales tax"],
    "total": ["total", "amount due", "grand total"],
}


def text_from_file(contents: bytes, filename: str, *, max_pages: int) -> str:
    if filename.lower().endswith(".txt"):
        try:
            text = contents.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise DocumentError("Text uploads must be UTF-8") from exc
    elif filename.lower().endswith(".pdf"):
        if not contents.startswith(b"%PDF-"):
            raise DocumentError("Uploaded file is not a PDF")
        try:
            pdf = PdfReader(BytesIO(contents), strict=True)
            if pdf.is_encrypted:
                raise DocumentError("Encrypted PDFs are not supported")
            if len(pdf.pages) == 0 or len(pdf.pages) > max_pages:
                raise DocumentError(f"PDF must contain 1 to {max_pages} pages")
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        except DocumentError:
            raise
        except Exception as exc:
            raise DocumentError("Cannot read this PDF; use a valid text-based PDF") from exc
    else:
        raise DocumentError("Only .pdf and .txt uploads are accepted")
    if not text.strip():
        raise DocumentError("No text layer found; scanned images need OCR/manual review")
    if len(text) > 100_000:
        raise DocumentError("Extracted text exceeds the processing limit")
    return text


def parse_invoice(text: str) -> dict:
    """Limited deterministic template parser, NOT general-purpose invoice AI."""
    values = {key: None for key in ALIASES}
    # Longest labels first; anchored to avoid Total matching Subtotal.
    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        for key, labels in ALIASES.items():
            if values[key] is not None:
                continue
            for label in sorted(labels, key=len, reverse=True):
                match = re.match(r"^" + re.escape(label) + r"\s*[:#–-]\s*(.+?)\s*$", line, re.I)
                if match:
                    values[key] = match.group(1).strip()
                    break
    details = []
    for line in lines:
        match = re.match(r"^ITEM\s*:\s*(.+?)\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*$", line.strip(), re.I)
        if match:
            details.append({"description": match[1][:120], "quantity": match[2], "unit_price": match[3], "line_total": match[4]})
    values["items"] = details[:100]
    return values


def _money(value):
    if value is None or value == "":
        return None
    try:
        raw = str(value).strip().replace(",", "")
        raw = re.sub(r"^[A-Z]{3}\s*", "", raw)
        raw = re.sub(r"^[€$£]\s*", "", raw)
        d = Decimal(raw)
        return d if d.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def validate_invoice(invoice: dict) -> list[str]:
    """Machine-readable review flags. No auto approval based on extraction alone."""
    errors = []
    for field in ("vendor", "invoice_number", "invoice_date", "currency", "total"):
        if not invoice.get(field):
            errors.append(f"missing_{field}")
    invoice_date = due_date = None
    try:
        if invoice.get("invoice_date"):
            invoice_date = date.fromisoformat(str(invoice["invoice_date"]))
    except ValueError:
        errors.append("invalid_invoice_date")
    try:
        if invoice.get("due_date"):
            due_date = date.fromisoformat(str(invoice["due_date"]))
    except ValueError:
        errors.append("invalid_due_date")
    if due_date and invoice_date and due_date < invoice_date:
        errors.append("due_before_invoice_date")
    if invoice.get("currency") and not re.fullmatch(r"[A-Z]{3}", str(invoice["currency"]).upper()):
        errors.append("invalid_currency")
    for field in ("subtotal", "tax", "total"):
        if invoice.get(field) is not None:
            value = _money(invoice[field])
            if value is None or value < 0:
                errors.append(f"invalid_{field}")
            elif value.as_tuple().exponent < -2:
                errors.append(f"excess_{field}_precision")
    subtotal, tax, total = (_money(invoice.get(name)) for name in ("subtotal", "tax", "total"))
    if subtotal is not None and tax is not None and total is not None and all(x >= 0 for x in (subtotal, tax, total)):
        if abs((subtotal + tax) - total) > Decimal("0.01"):
            errors.append("subtotal_tax_total_mismatch")
    items = invoice.get("items") or []
    line_sums = []
    for i, item in enumerate(items):
        quantity, unit, line = (_money(item.get(name)) for name in ("quantity", "unit_price", "line_total"))
        if quantity is None or unit is None or line is None or min(quantity, unit, line) < 0:
            errors.append(f"invalid_item_{i}")
        elif abs(quantity * unit - line) > Decimal("0.01"):
            errors.append(f"line_{i}_total_mismatch")
        else:
            line_sums.append(line)
    if items and subtotal is not None and len(line_sums) == len(items):
        if abs(sum(line_sums, Decimal(0)) - subtotal) > Decimal("0.01"):
            errors.append("items_subtotal_mismatch")
    if invoice.get("vendor") and len(str(invoice["vendor"])) > 120:
        errors.append("vendor_too_long")
    if invoice.get("invoice_number") and len(str(invoice["invoice_number"])) > 80:
        errors.append("invoice_number_too_long")
    return errors


def fingerprint(contents: bytes):
    return sha256(contents).hexdigest()


def invoice_key(invoice: dict):
    vendor = re.sub(r"\s+", " ", str(invoice.get("vendor") or "").strip()).casefold()
    number = str(invoice.get("invoice_number") or "").strip().casefold()
    return f"{vendor}|{number}" if vendor and number else None
