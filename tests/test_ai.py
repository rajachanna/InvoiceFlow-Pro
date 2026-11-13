from types import SimpleNamespace
import pytest
from invoiceflow.ai import extract_with_ai
from invoiceflow.extract import DocumentError


def client_with(content):
    class FakeCreate:
        def create(self, **kwargs):
            assert kwargs["response_format"] == {"type":"json_object"}
            assert "Do not infer" in kwargs["messages"][0]["content"]
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
    return SimpleNamespace(chat=SimpleNamespace(completions=FakeCreate()))


def test_ai_structured_result_with_injected_provider():
    client=client_with('{"vendor":"Example","invoice_number":"2026-1","items":[],"total":"99.00"}')
    result=extract_with_ai("Invoice example",api_key="unused",model="mock",client=client)
    assert result["vendor"]=="Example"
    assert result["tax"] is None


def test_ai_rejects_invalid_json():
    with pytest.raises(DocumentError, match="validated"):
        extract_with_ai("Invoice",api_key="x",model="mock",client=client_with("not JSON"))


def test_ai_rejects_wrong_shapes():
    with pytest.raises(DocumentError):
        extract_with_ai("Invoice",api_key="x",model="mock",client=client_with('{"vendor": {"nested":true}, "items": []}'))


def test_ai_no_credentials():
    with pytest.raises(DocumentError, match="not configured"):
        extract_with_ai("Invoice",api_key="",model="mock")


def test_ai_max_text():
    with pytest.raises(DocumentError, match="shorter"):
        extract_with_ai("x"*26000,api_key="x",model="mock",client=client_with("{}"))
