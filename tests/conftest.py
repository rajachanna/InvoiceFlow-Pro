from pathlib import Path
from fastapi.testclient import TestClient
import pytest

from invoiceflow.api import create_app
from invoiceflow.config import Settings

KEY = "invoiceflow-demo-operator-key-123456"
HEADERS = {"X-Operator-Key": KEY}
SAMPLE = (Path(__file__).parents[1] / "examples" / "invoice-sample.txt").read_bytes()

@pytest.fixture
def client(tmp_path):
    return TestClient(create_app(Settings(operator_key=KEY, db_path=tmp_path / "test.sqlite")))

@pytest.fixture
def uploaded(client):
    r = client.post("/api/invoices/upload", files={"file": ("invoice.txt", SAMPLE, "text/plain")}, headers=HEADERS)
    assert r.status_code == 200, r.text
    return r.json()
