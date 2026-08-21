import httpx
import pytest

from adapters.insuq_a2a.insuq_client import (
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    call_qa,
)


async def test_call_qa_maps_domain_and_product_to_qa_request(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/qa",
        method="POST",
        json={"route": "simple_lookup", "evidence": [], "needs_clarification": False},
    )

    result = await call_qa(
        question="자기부담금이 얼마인가요",
        domain="track4",
        product="든든실손4세대",
        base_url="http://test-insuq",
    )

    assert result == {"route": "simple_lookup", "evidence": [], "needs_clarification": False}
    request = httpx_mock.get_requests()[0]
    sent_body = request.read()
    import json

    payload = json.loads(sent_body)
    assert payload["question"] == "자기부담금이 얼마인가요"
    assert payload["domain"] == "track4"
    assert payload["product_filter"] == "든든실손4세대"


async def test_call_qa_omits_optional_fields_when_none(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/qa", method="POST", json={"evidence": [], "needs_clarification": False}
    )

    await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")

    request = httpx_mock.get_requests()[0]
    import json

    payload = json.loads(request.read())
    assert "domain" not in payload
    assert "product_filter" not in payload


async def test_call_qa_raises_upstream_unavailable_on_connect_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    with pytest.raises(UpstreamUnavailableError):
        await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")


async def test_call_qa_raises_upstream_timeout_on_timeout(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))

    with pytest.raises(UpstreamTimeoutError):
        await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")


async def test_call_qa_raises_upstream_unavailable_on_5xx(httpx_mock):
    httpx_mock.add_response(url="http://test-insuq/qa", method="POST", status_code=500)

    with pytest.raises(UpstreamUnavailableError):
        await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")


async def test_call_qa_raises_upstream_unavailable_on_read_error(httpx_mock):
    httpx_mock.add_exception(httpx.ReadError("connection reset"))

    with pytest.raises(UpstreamUnavailableError):
        await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")


async def test_call_qa_raises_upstream_unavailable_on_4xx(httpx_mock):
    httpx_mock.add_response(url="http://test-insuq/qa", method="POST", status_code=422)

    with pytest.raises(UpstreamUnavailableError):
        await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")


async def test_call_qa_raises_upstream_unavailable_on_non_json_response(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/qa", method="POST", status_code=200, content=b"not json"
    )

    with pytest.raises(UpstreamUnavailableError):
        await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")
