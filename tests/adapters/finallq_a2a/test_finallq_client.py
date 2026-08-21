import json

import httpx
import pytest

from adapters.finallq_a2a.finallq_client import (
    AuthExpiredError,
    NoAccountError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    get_first_account_id,
    request_transfer,
)


async def test_get_first_account_id_returns_first_account(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/accounts?page=0",
        method="GET",
        json={"content": [{"accountId": 42, "maskedAccountNumber": "****0001", "balance": 200000000, "createdAt": "2026-01-01"}],
              "page": 0, "size": 20, "totalElements": 1, "totalPages": 1},
    )

    account_id = await get_first_account_id("jwt-abc", base_url="http://test-finallq")

    assert account_id == 42
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer jwt-abc"


async def test_get_first_account_id_raises_no_account_when_empty(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/accounts?page=0",
        method="GET",
        json={"content": [], "page": 0, "size": 20, "totalElements": 0, "totalPages": 0},
    )

    with pytest.raises(NoAccountError):
        await get_first_account_id("jwt-abc", base_url="http://test-finallq")


async def test_get_first_account_id_raises_auth_expired_on_401(httpx_mock):
    httpx_mock.add_response(url="http://test-finallq/api/v1/accounts?page=0", method="GET", status_code=401)

    with pytest.raises(AuthExpiredError):
        await get_first_account_id("jwt-expired", base_url="http://test-finallq")


async def test_get_first_account_id_raises_upstream_unavailable_on_connect_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"))

    with pytest.raises(UpstreamUnavailableError):
        await get_first_account_id("jwt-abc", base_url="http://test-finallq")


async def test_request_transfer_sends_expected_payload(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/transfers",
        method="POST",
        status_code=201,
        json={"requestId": 88213, "status": "PENDING", "message": None, "requestedAt": "2026-08-21T10:00:00Z"},
    )

    result = await request_transfer(
        token="jwt-abc",
        from_account_id=42,
        amount=1500000,
        to_account_number="900-000-001",
        to_bank_code=None,
        memo="유압 실린더 교체 부품 대금",
        base_url="http://test-finallq",
    )

    assert result["status"] == "PENDING"
    request = httpx_mock.get_requests()[0]
    payload = json.loads(request.read())
    assert payload == {
        "fromAccountId": 42,
        "amount": 1500000,
        "toAccountNumber": "900-000-001",
        "memo": "유압 실린더 교체 부품 대금",
    }
    assert "toBankCode" not in payload
    assert request.headers["Authorization"] == "Bearer jwt-abc"


async def test_request_transfer_includes_bank_code_when_given(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/transfers", method="POST", status_code=201,
        json={"requestId": 1, "status": "PENDING", "message": None, "requestedAt": None},
    )

    await request_transfer(
        token="jwt-abc", from_account_id=42, amount=1000, to_account_number="900-000-001",
        to_bank_code="004", memo="m", base_url="http://test-finallq",
    )

    request = httpx_mock.get_requests()[0]
    payload = json.loads(request.read())
    assert payload["toBankCode"] == "004"


async def test_request_transfer_raises_auth_expired_on_401(httpx_mock):
    httpx_mock.add_response(url="http://test-finallq/api/v1/transfers", method="POST", status_code=401)

    with pytest.raises(AuthExpiredError):
        await request_transfer(
            token="jwt-expired", from_account_id=42, amount=1000, to_account_number="900-000-001",
            to_bank_code=None, memo="m", base_url="http://test-finallq",
        )


async def test_request_transfer_raises_value_error_on_400(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/transfers", method="POST", status_code=400,
        text="계좌번호 형식이 올바르지 않습니다.",
    )

    with pytest.raises(ValueError):
        await request_transfer(
            token="jwt-abc", from_account_id=42, amount=1000, to_account_number="bad",
            to_bank_code=None, memo="m", base_url="http://test-finallq",
        )


async def test_request_transfer_raises_upstream_unavailable_on_5xx(httpx_mock):
    httpx_mock.add_response(url="http://test-finallq/api/v1/transfers", method="POST", status_code=500)

    with pytest.raises(UpstreamUnavailableError):
        await request_transfer(
            token="jwt-abc", from_account_id=42, amount=1000, to_account_number="900-000-001",
            to_bank_code=None, memo="m", base_url="http://test-finallq",
        )


async def test_request_transfer_raises_upstream_timeout(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))

    with pytest.raises(UpstreamTimeoutError):
        await request_transfer(
            token="jwt-abc", from_account_id=42, amount=1000, to_account_number="900-000-001",
            to_bank_code=None, memo="m", base_url="http://test-finallq",
        )
