"""FinAllQ 어댑터가 InsuQ 어댑터의 verify-collateral-insurance를 2차 홉으로 호출하는 클라이언트.

InsuQ 코드도 FinAllQ 코드도 건드리지 않는다 — InsuQ의 A2A 봉투 계약
(docs/schemas/verify-collateral-insurance.json)을 그대로 호출한다. InsuQ가 돌려주는
status=rejected는 A2A 계약상 정상 200 응답이다(장애가 아니다) — 이 클라이언트는
파싱된 dict를 그대로 반환하고, "거절"을 판정하는 건 mapping.py의 몫이다.

⚠️ InsuQ는 이 스킬을 아직 구현하지 않았다(2026-08-23 기준, 설계 문서 발견②) — 지금은
501을 돌려주고, 이 클라이언트는 그걸 명확한 메시지로 구분해 502로 전달한다. 실제 E2E는
InsuQ가 정책 원장 조회 엔드포인트를 만든 뒤에나 가능하다.

httpx.TransportError로 폭넓게 잡는 이유는 insuq_a2a/insuq_client.py, finallq_client.py와
동일 — ConnectError·ReadError 등이 전부 그 서브클래스이기 때문이다.
"""

from __future__ import annotations

import httpx


class UpstreamUnavailableError(Exception):
    """InsuQ 어댑터에 연결할 수 없거나 5xx를 반환했을 때."""


class UpstreamTimeoutError(Exception):
    """InsuQ 어댑터 응답이 타임아웃됐을 때."""


async def call_verify_collateral_insurance(
    building_id: str,
    required_coverage: float,
    request_chain_id: str,
    finallq_company_id: str,
    base_url: str,
    timeout: float = 10.0,
) -> dict:
    """POST {base_url}/a2a/skills/verify-collateral-insurance 를 호출한다."""
    payload = {
        "requester": {"finallq_company_id": finallq_company_id, "building_id": building_id},
        "request_chain_id": request_chain_id,
        "building_id": building_id,
        "required_coverage": required_coverage,
    }
    headers = {"X-Request-Chain-Id": request_chain_id}

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.post(
                "/a2a/skills/verify-collateral-insurance", json=payload, headers=headers
            )
    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError(str(exc)) from exc
    except httpx.TransportError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    if response.status_code == 501:
        raise UpstreamUnavailableError(
            "InsuQ has not implemented verify-collateral-insurance yet (501) — "
            "see docs/superpowers/specs/2026-08-23-s8-multihop-loan-collateral-design.md 발견②"
        )

    if response.status_code >= 500:
        raise UpstreamUnavailableError(f"InsuQ adapter returned {response.status_code}")

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamUnavailableError(f"InsuQ adapter returned a non-JSON response: {exc}") from exc
