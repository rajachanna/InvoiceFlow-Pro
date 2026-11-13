from conftest import HEADERS, SAMPLE


def upload(client, payload=SAMPLE, name="invoice.txt", **kwargs):
    return client.post("/api/invoices/upload", files={"file":(name,payload)}, data=kwargs, headers=HEADERS)


def test_health_and_dashboard(client):
    assert client.get("/health").json()["payments_enabled"] is False
    assert "InvoiceFlow" in client.get("/").text


def test_private_endpoints_require_key(client):
    for path in ("/api/metrics", "/api/invoices", "/api/audit", "/api/export.csv"):
        assert client.get(path).status_code == 401
        assert client.get(path, headers={"X-Operator-Key":"incorrect"}).status_code == 401


def test_upload_review_approve(client, uploaded):
    assert uploaded["status"] == "needs_review"
    assert uploaded["errors"] == []
    assert uploaded["extraction_mode"] == "deterministic_template"
    reviewed = client.post(f"/api/invoices/{uploaded['id']}/review",headers=HEADERS,json={
        "action":"approve", "version":uploaded["version"], "note":"Checked against sample data"
    })
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "approved"
    assert client.get("/api/metrics", headers=HEADERS).json()["approved"] == 1
    assert len(client.get("/api/audit",headers=HEADERS).json()["events"]) == 2


def test_exact_duplicate_upload_blocked(client, uploaded):
    r=upload(client)
    assert r.status_code == 409
    assert "exact document" in r.text
    assert client.get("/api/metrics",headers=HEADERS).json()["total"] == 1


def test_vendor_invoice_duplicate_even_changed_file(client, uploaded):
    r=upload(client,SAMPLE+b"\n", "different.txt")
    assert r.status_code == 409
    assert "vendor" in r.text


def test_missing_fields_block_approval(client):
    r=upload(client,b"Vendor: Sample\nInvoice Number: BAD-1\n")
    assert r.status_code==200
    record=r.json()
    assert "missing_total" in record["errors"]
    reject=client.post(f"/api/invoices/{record['id']}/review",headers=HEADERS,json={
        "action":"approve", "version":record["version"]
    })
    assert reject.status_code==422
    assert "Resolve" in reject.text


def test_revise_then_approve(client):
    r=upload(client,b"Vendor: Sample\nInvoice Number: 118\nCurrency: USD\nInvoice Date: 2026-11-13\nSubtotal: 10.00\nTax: 1.00\nTotal: 999.00\n")
    row=r.json()
    assert "subtotal_tax_total_mismatch" in row["errors"]
    revised=client.patch(f"/api/invoices/{row['id']}",headers=HEADERS,json={
        "version":row["version"],"fields":{"total":"11.00"}
    })
    assert revised.status_code==200, revised.text
    assert revised.json()["errors"]==[]
    approved=client.post(f"/api/invoices/{row['id']}/review",headers=HEADERS,json={
        "action":"approve","version":revised.json()["version"],"note":"Reviewed"
    })
    assert approved.status_code==200
    assert approved.json()["status"]=="approved"


def test_stale_version_conflict(client, uploaded):
    path=f"/api/invoices/{uploaded['id']}"
    a=client.patch(path,headers=HEADERS,json={"version":1,"fields":{"vendor":"Changed"}})
    assert a.status_code==200
    b=client.patch(path,headers=HEADERS,json={"version":1,"fields":{"vendor":"Changed Twice"}})
    assert b.status_code==409


def test_rejected_cannot_rereview(client, uploaded):
    path=f"/api/invoices/{uploaded['id']}/review"
    r=client.post(path,headers=HEADERS,json={"action":"reject","version":1,"note":"Mismatch with contract"})
    assert r.status_code==200
    assert client.post(path,headers=HEADERS,json={"action":"approve","version":2}).status_code==422


def test_approved_cannot_modify(client, uploaded):
    iid=uploaded["id"]
    client.post(f"/api/invoices/{iid}/review",headers=HEADERS,json={"action":"approve","version":1})
    assert client.patch(f"/api/invoices/{iid}",headers=HEADERS,json={"version":2,"fields":{"vendor":"X"}}).status_code==422


def test_unknown_fields_rejected(client, uploaded):
    iid=uploaded["id"]
    assert client.patch(f"/api/invoices/{iid}",headers=HEADERS,json={"version":1,"fields":{"bank_account":"x"}}).status_code==422


def test_csv_export(client, uploaded):
    r=client.get("/api/export.csv",headers=HEADERS)
    assert r.status_code==200
    assert "Northstar Office Supply" in r.text
    assert "invoice_number" in r.text
    assert "ITEM:" not in r.text


def test_upload_limits(client):
    assert upload(client,b"",name="x.txt").status_code==413
    assert upload(client,b"A"*2_100_000,name="x.txt").status_code==413
    assert upload(client,b"malware",name="x.exe").status_code==422


def test_opt_in_ai_consent(client):
    r=upload(client,SAMPLE,name="invoice.txt",use_ai="true",ai_authorized="false")
    assert r.status_code==422
    assert "authorization" in r.text


def test_ai_requires_key(client):
    r=upload(client,SAMPLE,name="invoice.txt",use_ai="true",ai_authorized="true")
    assert r.status_code==422
    assert "not configured" in r.text


def test_manual_review_only_no_payments(client, uploaded):
    doc=client.get("/openapi.json").json()
    assert not any("pay" in p.lower() or "accounting" in p.lower() for p in doc["paths"])
