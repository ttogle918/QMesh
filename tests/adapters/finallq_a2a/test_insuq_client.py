import httpx
import pytest

from adapters.finallq_a2a.insuq_client import (
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    call_verify_collateral_insurance,
)


async def test_call_sends_expected_payload_and_headers(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/a2a/skills/verify-collateral-insurance",
        method="POST",
        json={"status": "completed", "policy_valid": True, "coverage_amount": 300000000, "evidence": []},
    )

    result = await call_verify_collateral_insurance(
        building_id="BLD-A",
        required_coverage=500000000,
        request_chain_id="chain-1",
        finallq_company_id="FQ-1043",
        base_url="http://test-insuq",
    )

    assert result == {"status": "completed", "policy_valid": True, "coverage_amount": 300000000, "evidence": []}
    request = httpx_mock.get_requests()[0]
    assert request.headers["X-Request-Chain-Id"] == "chain-1"
    import json as _json

    body = _json.loads(request.content)
    assert body["building_id"] == "BLD-A"
    assert body["required_coverage"] == 500000000
    assert body["request_chain_id"] == "chain-1"
    assert body["requester"]["finallq_company_id"] == "FQ-1043"
    assert body["requester"]["building_id"] == "BLD-A"


async def test_call_raises_upstream_timeout_on_timeout(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))

    with pytest.raises(UpstreamTimeoutError):
        await call_verify_collateral_insurance(
            building_id="BLD-A",
            required_coverage=500000000,
            request_chain_id="chain-1",
            finallq_company_id="FQ-1043",
            base_url="http://test-insuq",
        )


async def test_call_raises_upstream_unavailable_on_connect_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"))

    with pytest.raises(UpstreamUnavailableError):
        await call_verify_collateral_insurance(
            building_id="BLD-A",
            required_coverage=500000000,
            request_chain_id="chain-1",
            finallq_company_id="FQ-1043",
            base_url="http://test-insuq",
        )


async def test_call_raises_upstream_unavailable_on_5xx(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/a2a/skills/verify-collateral-insurance",
        method="POST",
        status_code=502,
    )

    with pytest.raises(UpstreamUnavailableError):
        await call_verify_collateral_insurance(
            building_id="BLD-A",
            required_coverage=500000000,
            request_chain_id="chain-1",
            finallq_company_id="FQ-1043",
            base_url="http://test-insuq",
        )


async def test_call_raises_upstream_unavailable_on_non_json_body(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/a2a/skills/verify-collateral-insurance",
        method="POST",
        status_code=200,
        content=b"not json",
    )

    with pytest.raises(UpstreamUnavailableError):
        await call_verify_collateral_insurance(
            building_id="BLD-A",
            required_coverage=500000000,
            request_chain_id="chain-1",
            finallq_company_id="FQ-1043",
            base_url="http://test-insuq",
        )


async def test_call_returns_body_even_when_insuq_rejects(httpx_mock):
    """InsuQ의 status=rejected는 A2A 계약상 정상 200 응답이다 — 예외가 아니라 dict 그대로 반환."""
    httpx_mock.add_response(
        url="http://test-insuq/a2a/skills/verify-collateral-insurance",
        method="POST",
        json={"status": "rejected", "rejection_reason": "policy_not_found", "policy_valid": False, "coverage_amount": 0, "evidence": []},
    )

    result = await call_verify_collateral_insurance(
        building_id="BLD-A",
        required_coverage=500000000,
        request_chain_id="chain-1",
        finallq_company_id="FQ-1043",
        base_url="http://test-insuq",
    )

    assert result["status"] == "rejected"
    assert result["policy_valid"] is False


async def test_call_raises_distinct_message_on_insuq_not_implemented_501(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/a2a/skills/verify-collateral-insurance",
        method="POST",
        status_code=501,
    )

    with pytest.raises(UpstreamUnavailableError, match="has not implemented"):
        await call_verify_collateral_insurance(
            building_id="BLD-A",
            required_coverage=500000000,
            request_chain_id="chain-1",
            finallq_company_id="FQ-1043",
            base_url="http://test-insuq",
        )
