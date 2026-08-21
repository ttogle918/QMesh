from fastapi.testclient import TestClient

from adapters.finallq_a2a import main
from adapters.finallq_a2a.auth import LoginFailedError
from adapters.finallq_a2a.finallq_client import (
    AuthExpiredError,
    NoAccountError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

client = TestClient(main.app)


def _valid_body(**overrides):
    body = {
        "requester": {"finallq_company_id": "FQ-1043"},
        "request_chain_id": "chain-1",
        "po_id": "PO-88213",
        "amount": 1500000,
        "supplier": "ABC 부품상사",
        "approved_by": "team-lead-01",
        "purpose": "유압 실린더 교체 부품 대금",
        "error_code": "E-4102",
        "to_account_number": "900-000-001",
    }
    body.update(overrides)
    return body


def _headers(chain_id="chain-1"):
    return {"X-Request-Chain-Id": chain_id}


def test_agent_card_endpoint_returns_finallq_card():
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.json()["name"] == "FinAllQ"


def test_request_withdrawal_success(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        return 42

    async def fake_request_transfer(**kwargs):
        return {"requestId": 88213, "status": "PENDING", "message": None, "requestedAt": "2026-08-21T10:00:00Z"}

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)
    monkeypatch.setattr(main, "request_transfer", fake_request_transfer)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "input-required"
    assert data["req_id"] == "88213"


def test_request_withdrawal_chain_id_mismatch():
    resp = client.post(
        "/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers("chain-DIFFERENT")
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "chain_id_mismatch"


def test_request_withdrawal_schema_validation_failed():
    body = _valid_body()
    del body["to_account_number"]
    resp = client.post("/a2a/skills/request-withdrawal", json=body, headers=_headers())
    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"


def test_request_withdrawal_non_dict_body():
    resp = client.post("/a2a/skills/request-withdrawal", json=["not", "an", "object"])
    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"


def test_request_withdrawal_login_failed(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        raise LoginFailedError("bad credentials")

    monkeypatch.setattr(main, "get_token", fake_get_token)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_request_withdrawal_retries_once_on_auth_expired_then_succeeds(monkeypatch):
    call_count = {"get_token": 0, "transfer_flow": 0}

    async def fake_get_token(cache, email, password, base_url):
        call_count["get_token"] += 1
        return f"jwt-{call_count['get_token']}"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        return 42

    async def fake_request_transfer(**kwargs):
        call_count["transfer_flow"] += 1
        if call_count["transfer_flow"] == 1:
            raise AuthExpiredError("token expired")
        return {"requestId": 1, "status": "PENDING", "message": None, "requestedAt": None}

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)
    monkeypatch.setattr(main, "request_transfer", fake_request_transfer)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())

    assert resp.status_code == 200
    assert call_count["get_token"] == 2  # 최초 1회 + 재로그인 1회
    assert call_count["transfer_flow"] == 2  # 최초 시도 1회 + 재시도 1회


def test_request_withdrawal_still_auth_expired_after_retry(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-always-rejected"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        return 42

    async def fake_request_transfer(**kwargs):
        raise AuthExpiredError("token expired")

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)
    monkeypatch.setattr(main, "request_transfer", fake_request_transfer)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())

    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_request_withdrawal_no_account(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        raise NoAccountError("no account")

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_request_withdrawal_upstream_unavailable(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        raise UpstreamUnavailableError("boom")

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_request_withdrawal_upstream_timeout(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        raise UpstreamTimeoutError("boom")

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 504
    assert resp.json()["error"] == "upstream_timeout"


def test_request_withdrawal_finallq_400_maps_to_schema_validation_failed(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        return 42

    async def fake_request_transfer(**kwargs):
        raise ValueError("계좌번호 형식이 올바르지 않습니다.")

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)
    monkeypatch.setattr(main, "request_transfer", fake_request_transfer)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"


def test_request_withdrawal_unknown_finallq_status_maps_to_upstream_unavailable(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        return 42

    async def fake_request_transfer(**kwargs):
        return {"requestId": 1, "status": "SOME_NEW_STATUS", "message": None, "requestedAt": None}

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)
    monkeypatch.setattr(main, "request_transfer", fake_request_transfer)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_unimplemented_known_skill_returns_501():
    resp = client.post("/a2a/skills/assess-loan", json={})
    assert resp.status_code == 501
    assert resp.json()["error"] == "not_implemented"


def test_unknown_skill_returns_404():
    resp = client.post("/a2a/skills/not-a-real-skill", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_skill"
