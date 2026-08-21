from fastapi.testclient import TestClient

from adapters.insuq_a2a import main
from adapters.insuq_a2a.insuq_client import UpstreamTimeoutError, UpstreamUnavailableError

client = TestClient(main.app)


def test_agent_card_endpoint_returns_insuq_card():
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.json()["name"] == "InsuQ"


def test_lookup_clause_success(monkeypatch):
    async def fake_call_qa(**kwargs):
        return {
            "answer": "자기부담금은 20%입니다.",
            "verdict": "지급 사유에 해당할 가능성이 높음",
            "evidence": [
                {
                    "product": "든든실손4세대",
                    "policy_part": "보통약관",
                    "article_no": "제5조",
                    "clause_no": None,
                    "page": 13,
                }
            ],
            "needs_clarification": False,
            "clarify_questions": [],
        }

    monkeypatch.setattr(main, "call_qa", fake_call_qa)

    body = {
        "requester": {},
        "request_chain_id": "chain-1",
        "question": "자기부담금이 얼마인가요",
    }
    resp = client.post(
        "/a2a/skills/lookup-clause",
        json=body,
        headers={"X-Request-Chain-Id": "chain-1"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["evidence"] == ["든든실손4세대 보통약관 제5조, p.13"]


def test_lookup_clause_chain_id_mismatch():
    body = {"requester": {}, "request_chain_id": "chain-1", "question": "q"}
    resp = client.post(
        "/a2a/skills/lookup-clause",
        json=body,
        headers={"X-Request-Chain-Id": "chain-DIFFERENT"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "chain_id_mismatch"


def test_lookup_clause_schema_validation_failed():
    body = {"requester": {}, "request_chain_id": "chain-1"}  # question 없음
    resp = client.post(
        "/a2a/skills/lookup-clause",
        json=body,
        headers={"X-Request-Chain-Id": "chain-1"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"


def test_lookup_clause_upstream_unavailable(monkeypatch):
    async def fake_call_qa(**kwargs):
        raise UpstreamUnavailableError("boom")

    monkeypatch.setattr(main, "call_qa", fake_call_qa)

    body = {"requester": {}, "request_chain_id": "chain-1", "question": "q"}
    resp = client.post(
        "/a2a/skills/lookup-clause",
        json=body,
        headers={"X-Request-Chain-Id": "chain-1"},
    )

    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_lookup_clause_upstream_timeout(monkeypatch):
    async def fake_call_qa(**kwargs):
        raise UpstreamTimeoutError("boom")

    monkeypatch.setattr(main, "call_qa", fake_call_qa)

    body = {"requester": {}, "request_chain_id": "chain-1", "question": "q"}
    resp = client.post(
        "/a2a/skills/lookup-clause",
        json=body,
        headers={"X-Request-Chain-Id": "chain-1"},
    )

    assert resp.status_code == 504
    assert resp.json()["error"] == "upstream_timeout"


def test_unimplemented_known_skill_returns_501():
    resp = client.post("/a2a/skills/verify-collateral-insurance", json={})
    assert resp.status_code == 501
    assert resp.json()["error"] == "not_implemented"


def test_unknown_skill_returns_404():
    resp = client.post("/a2a/skills/not-a-real-skill", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_skill"


def test_lookup_clause_malformed_json_body_returns_schema_validation_failed():
    resp = client.post(
        "/a2a/skills/lookup-clause",
        content=b"not valid json",
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"


def test_lookup_clause_non_dict_json_body_returns_schema_validation_failed():
    resp = client.post("/a2a/skills/lookup-clause", json=["not", "an", "object"])

    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"
