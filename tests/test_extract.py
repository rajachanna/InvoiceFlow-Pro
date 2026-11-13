from io import BytesIO
from datetime import date
import pytest
from reportlab.pdfgen import canvas

from invoiceflow.extract import DocumentError, parse_invoice, text_from_file, validate_invoice, fingerprint, invoice_key
from conftest import SAMPLE


def test_parse_demo_fields():
    result = parse_invoice(SAMPLE.decode())
    assert result["vendor"] == "Northstar Office Supply"
    assert result["invoice_number"] == "NS-1042"
    assert result["currency"] == "USD"
    assert result["total"] == "165.00"
    assert len(result["items"]) == 2
    assert validate_invoice(result) == []


def test_invoice_key_normalization():
    assert invoice_key({"vendor":"  ACME   inc  ","invoice_number":"inv-ABC"}) == "acme inc|inv-abc"
    assert invoice_key({"vendor":"ACME"}) is None


def test_fingerprint_repeatable():
    assert fingerprint(SAMPLE) == fingerprint(bytes(SAMPLE))
    assert fingerprint(SAMPLE) != fingerprint(SAMPLE+b"\n")


def test_missing_fields_flagged():
    flags = validate_invoice(parse_invoice("Vendor: Sample\nInvoice Number: A1\n"))
    assert "missing_total" in flags
    assert "missing_invoice_date" in flags
    assert "missing_currency" in flags


def test_arithmetic_mismatch():
    item = parse_invoice(SAMPLE.decode())
    item["total"] = "166.00"
    assert "subtotal_tax_total_mismatch" in validate_invoice(item)


def test_line_item_mismatch():
    item = parse_invoice(SAMPLE.decode())
    item["items"][0]["line_total"] = "100.00"
    flags = validate_invoice(item)
    assert "line_0_total_mismatch" in flags


def test_total_invalid_and_negative():
    base = parse_invoice(SAMPLE.decode())
    for val in ("abc", "NaN", "-3", "Infinity"):
        base["total"] = val
        assert "invalid_total" in validate_invoice(base)


def test_due_before_issue():
    base = parse_invoice(SAMPLE.decode())
    base["due_date"] = "2026-01-01"
    assert "due_before_invoice_date" in validate_invoice(base)


def test_invalid_date_and_currency():
    base = parse_invoice(SAMPLE.decode())
    base["invoice_date"] = "yesterday"
    base["currency"] = "USDD"
    flags = validate_invoice(base)
    assert "invalid_invoice_date" in flags
    assert "invalid_currency" in flags


def test_excess_money_precision():
    base = parse_invoice(SAMPLE.decode())
    base["total"] = "165.0001"
    assert "excess_total_precision" in validate_invoice(base)


def test_utf8_only():
    with pytest.raises(DocumentError, match="UTF-8"):
        text_from_file(b"\xff\xff", "invoice.txt", max_pages=8)


def test_unsupported_file():
    with pytest.raises(DocumentError, match="Only"):
        text_from_file(b"data", "invoice.exe", max_pages=8)


def test_fake_pdf_rejected():
    with pytest.raises(DocumentError, match="not a PDF"):
        text_from_file(b"not pdf", "invoice.pdf", max_pages=8)


def test_text_pdf_roundtrip():
    stream = BytesIO()
    doc = canvas.Canvas(stream, pagesize=(612,792))
    for j,line in enumerate(SAMPLE.decode().splitlines()):
        doc.drawString(45, 750-j*22, line)
    doc.save()
    extracted = text_from_file(stream.getvalue(), "invoice.pdf", max_pages=3)
    result = parse_invoice(extracted)
    assert result["vendor"] == "Northstar Office Supply"
    assert result["total"] == "165.00"
    assert validate_invoice(result) == []


def test_pdf_limit():
    stream = BytesIO(); doc = canvas.Canvas(stream)
    for _ in range(3):
        doc.drawString(40, 650, "Hello")
        doc.showPage()
    doc.save()
    with pytest.raises(DocumentError, match="1 to 2 pages"):
        text_from_file(stream.getvalue(), "invoice.pdf", max_pages=2)


def test_pdf_without_text():
    stream=BytesIO(); doc=canvas.Canvas(stream); doc.showPage(); doc.save()
    with pytest.raises(DocumentError, match="No text layer"):
        text_from_file(stream.getvalue(), "invoice.pdf", max_pages=3)
