"""FinAllQ 계좌 조회·이체 요청 HTTP 클라이언트.

FinAllQ 코드는 건드리지 않는다 — 이미 떠 있는 REST API(/api/v1/accounts,
/api/v1/transfers)를 그대로 호출한다. 인증 헤더(Bearer 토큰)는 호출부가 넘겨준다 —
이 모듈은 토큰을 발급·캐싱하지 않는다(auth.py 책임).

httpx.TransportError로 폭넓게 잡는 이유: ConnectError·ReadError·WriteError·
ProtocolError 등은 전부 그 서브클래스다(InsuQ 어댑터 작업에서 실측 확인 — TimeoutException도
같은 계열이지만 여기서는 먼저 갈라서 504로 보낸다).
"""

from __future__ import annotations

import httpx


class UpstreamUnavailableError(Exception):
    """FinAllQ에 연결할 수 없거나 5xx를 반환했을 때."""


class UpstreamTimeoutError(Exception):
    """FinAllQ 응답이 타임아웃됐을 때."""


class NoAccountError(Exception):
    """서비스 계정에 연결된 계좌가 0건일 때."""


class AuthExpiredError(Exception):
    """토큰이 만료/무효(401)일 때 — 호출부가 재로그인 후 재시도해야 한다."""


async def get_first_account_id(token: str, base_url: str, timeout: float = 10.0) -> int:
    """GET /api/v1/accounts?page=0 을 호출해 첫 번째 계좌의 accountId를 반환한다."""
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.get(
                "/api/v1/accounts",
                params={"page": 0},
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError(str(exc)) from exc
    except httpx.TransportError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    if response.status_code == 401:
        raise AuthExpiredError("FinAllQ rejected the access token")
    if response.status_code >= 500:
        raise UpstreamUnavailableError(f"FinAllQ returned {response.status_code}")

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise UpstreamUnavailableError(f"FinAllQ returned a non-JSON response: {exc}") from exc

    content = body.get("content", [])
    if not content:
        raise NoAccountError("service account has no linked account")
    return content[0]["accountId"]


async def request_transfer(
    token: str,
    from_account_id: int,
    amount: float,
    to_account_number: str,
    to_bank_code: str | None,
    memo: str,
    base_url: str,
    timeout: float = 10.0,
) -> dict:
    """POST /api/v1/transfers 를 호출해 TransferResponseDto(dict)를 반환한다."""
    payload: dict = {
        "fromAccountId": from_account_id,
        "amount": amount,
        "toAccountNumber": to_account_number,
        "memo": memo,
    }
    if to_bank_code is not None:
        payload["toBankCode"] = to_bank_code

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.post(
                "/api/v1/transfers",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError(str(exc)) from exc
    except httpx.TransportError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    if response.status_code == 401:
        raise AuthExpiredError("FinAllQ rejected the access token")
    if response.status_code == 400:
        raise ValueError(f"FinAllQ rejected the transfer request: {response.text}")
    if response.status_code >= 500:
        raise UpstreamUnavailableError(f"FinAllQ returned {response.status_code}")

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamUnavailableError(f"FinAllQ returned a non-JSON response: {exc}") from exc
