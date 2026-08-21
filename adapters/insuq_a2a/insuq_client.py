"""InsuQ ai-engine POST /qa 호출 클라이언트.

InsuQ 코드는 건드리지 않는다 — 이미 떠 있는 HTTP 엔드포인트를 그대로 호출한다.
에러 매핑은 InsuQ/docs/A2A_API_SPEC.md §8을 따른다: 연결 불가 -> 502, 타임아웃 -> 504.
"""

from __future__ import annotations

import httpx


class UpstreamUnavailableError(Exception):
    """ai-engine에 연결할 수 없거나 5xx를 반환했을 때 (§8: 502 upstream_unavailable)."""


class UpstreamTimeoutError(Exception):
    """ai-engine 응답이 타임아웃됐을 때 (§8: 504 upstream_timeout)."""


async def call_qa(
    question: str,
    domain: str | None,
    product: str | None,
    base_url: str,
    timeout: float = 10.0,
) -> dict:
    """InsuQ ai-engine의 POST /qa를 호출하고 QaResponse(dict)를 반환한다.

    domain -> QaRequest.domain, product -> QaRequest.product_filter로 매핑한다
    (InsuQ ai-engine/insuq_ai/api/schemas.py 참조 — product_filter는 정확 문자열 필터).
    """
    payload: dict = {"question": question}
    if domain is not None:
        payload["domain"] = domain
    if product is not None:
        payload["product_filter"] = product

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.post("/qa", json=payload)
    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError(str(exc)) from exc
    except httpx.ConnectError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    if response.status_code >= 500:
        raise UpstreamUnavailableError(f"ai-engine returned {response.status_code}")

    response.raise_for_status()
    return response.json()
