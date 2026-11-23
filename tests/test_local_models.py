from email.message import Message
import json

import pytest

from opspilot_x.hybrid import ModelUnavailable
from opspilot_x.local_models import LocalModels


def test_http_only_contacts_fixed_loopback_and_rejects_redirect(monkeypatch):
    events = []

    class Redirect:
        status = 307
        headers = Message()
        headers["Location"] = "https://example.invalid/collect"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

    class Connection:
        def __init__(self, host, port, *, timeout):
            self.sock = object()
            events.append((host, port, timeout))

        def connect(self):
            pass

        def request(self, method, route, *, body, headers):
            events.append((method, route, json.loads(body), headers.get("Authorization")))

        def getresponse(self):
            return Redirect()

        def close(self):
            events.append("closed")

    monkeypatch.setattr("http.client.HTTPConnection", Connection)
    with pytest.raises(ModelUnavailable, match="HTTP response"):
        LocalModels(7211, 7212, api_key="test-scoped-key").embed(["synthetic evidence"])
    assert events == [
        ("127.0.0.1", 7211, 90.0),
        ("POST", "/v1/embeddings", {
            "model": "opspilot-embed", "input": ["synthetic evidence"], "encoding_format": "float",
        }, "Bearer test-scoped-key"),
        "closed",
    ]
    with pytest.raises(ValueError, match="key format"):
        LocalModels(7211, 7212, api_key="invalid\r\nHeader: value")


def test_embedding_preserves_input_order_and_rejects_corrupt_vector(monkeypatch):
    rows = [{"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]}]
    models = LocalModels(7211, 7212)
    monkeypatch.setattr(models, "_post", lambda *args: {"data": rows})
    assert models.embed(["query", "document"]) == [[1.0, 0.0], [0.0, 1.0]]
    rows[0]["embedding"][0] = float("nan")
    with pytest.raises(ModelUnavailable, match="vector"):
        models.embed(["query", "document"])
    rows[0]["embedding"][0] = 0.0
    rows[0]["index"] = 0
    with pytest.raises(ModelUnavailable, match="indices"):
        models.embed(["query", "document"])


def test_generation_sends_bounded_structured_request_and_checks_finish(monkeypatch):
    models = LocalModels(7211, 7212)
    sources = [
        {"evidence_id": "SOP-42", "text": "기록을 정리한다.", "action": "inspect", "quote_start": 0},
        {"evidence_id": "SOP-42", "text": "  먼저 센서를 확인한다. ", "action": "inspect", "quote_start": 480},
        {"evidence_id": "NOTE-42", "text": "Operator speculation.", "action": ""},
    ]
    draft = {"action": "inspect", "citations": [{
        "evidence_id": "SOP-42", "quote": "먼저 센서를 확인한다.", "quote_start": 482,
    }]}
    choice = {"finish_reason": "stop", "message": {"content": '{"selection":"p2"}'}}

    def post(port, route, body):
        assert (port, route) == (7212, "/v1/chat/completions")
        assert body["stream"] is False
        assert (body["temperature"], body["seed"], body["max_tokens"]) == (0, 42, 48)
        assert "tools" not in body
        schema = body["response_format"]["schema"]["properties"]
        assert schema == {"selection": {"type": "string", "enum": ["p1", "p2", "review"]}}
        assert json.loads(body["messages"][1]["content"])["evidence"] == [
            {"selection": "p1", "passage": "기록을 정리한다.", "action": "inspect"},
            {"selection": "p2", "passage": "먼저 센서를 확인한다.", "action": "inspect"},
        ]
        return {"choices": [choice]}

    monkeypatch.setattr(models, "_post", post)
    assert models.generate("Which action is prescribed?", sources) == draft
    choice["message"]["content"] = '{"selection":"review"}'
    assert models.generate("Which action is prescribed?", sources) == {}
    choice["message"]["content"] = '{"selection":"p3"}'
    assert models.generate("Which action is prescribed?", sources) == {}
    choice["message"]["content"] = '{"selection":"p2","quote":"기록을 정리한다."}'
    assert models.generate("Which action is prescribed?", sources) == {}
    choice["message"]["content"] = '{"selection":"p2"}'
    choice["finish_reason"] = "length"
    assert models.generate("Which action is prescribed?", sources) == {}
