"""Standalone reproducible synthetic invoice demo, with no payment or AI calls."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
from fastapi.testclient import TestClient

from invoiceflow.api import create_app
from invoiceflow.config import Settings

ROOT = Path(__file__).parents[1]
KEY = "synthetic-demo-only-invoice-key-123456"


def main():
    with TemporaryDirectory(prefix="invoiceflow-demo-") as tmp:
        client = TestClient(create_app(Settings(operator_key=KEY,db_path=Path(tmp)/"demo.sqlite")))
        headers = {"X-Operator-Key": KEY}
        source = (ROOT/"examples/invoice-sample.txt").read_bytes()
        r = client.post("/api/invoices/upload",headers=headers,
                        files={"file":("sample-invoice.txt",source,"text/plain")})
        assert r.status_code == 200, r.text
        invoice = r.json()
        print("InvoiceFlow Pro — OFFLINE demo / no bank transactions")
        print("Imported:",json.dumps({"id":invoice["id"],"status":invoice["status"],
                                       "flags":invoice["errors"],"mode":invoice["extraction_mode"]}))
        duplicate = client.post("/api/invoices/upload",headers=headers,
                                files={"file":("sample-invoice.txt",source,"text/plain")})
        assert duplicate.status_code == 409
        print("Duplicate prevented: HTTP",duplicate.status_code)
        review = client.post(f"/api/invoices/{invoice['id']}/review",headers=headers,
                             json={"action":"approve","version":invoice["version"],
                                   "note":"Confirmed synthetic sample math"})
        assert review.status_code == 200, review.text
        assert review.json()["status"] == "approved"
        print("Manual simulated approval successful")
        metrics = client.get("/api/metrics",headers=headers).json()
        assert metrics["approved"] == 1 and metrics["needs_review"] == 0
        print("Metrics:",json.dumps(metrics))
        print("PASS — all demo steps; no real AI provider, accounting system or payments")


if __name__ == "__main__":
    main()
