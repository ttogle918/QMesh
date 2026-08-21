"""FinAllQ 서비스 계정 로그인 + 토큰 캐시.

파트너 자격증명(머신 신원, 백로그 131·132)이 아직 없어 임시로 사람 계정(서비스 계정)을
재사용한다 — 자격증명은 .env로 받고, 로그인 결과(accessToken)를 프로세스 메모리에
캐싱한다. 만료 시각 파싱은 하지 않는다(YAGNI) — 401을 받으면 캐시를 버리고 재로그인한다
(그 재시도 로직은 finallq_client.AuthExpiredError를 받는 호출부, 즉 main.py의 책임이다).
"""

from __future__ import annotations

import httpx


class LoginFailedError(Exception):
    """서비스 계정 로그인 자체가 실패했을 때 (자격증명 오류, 연결 실패 등)."""


# 동시 요청 간 경쟁 조건이 있다 — 캐시가 갱신 중일 때 다른 요청이 만료된 값을 읽고
# clear() 할 수 있다. 정확성은 깨지지 않는다(어떤 토큰이 발급되든 유효하다) — 최악의
# 경우 로그인이 한 번 더 일어날 뿐이다. 프로토타입 규모에서는 asyncio.Lock을 넣는
# 복잡도가 이 이득보다 크다고 판단해 의도적으로 넣지 않았다.
class TokenCache:
    def __init__(self) -> None:
        self._token: str | None = None

    def get(self) -> str | None:
        return self._token

    def set(self, token: str) -> None:
        self._token = token

    def clear(self) -> None:
        self._token = None


async def login(email: str, password: str, base_url: str, timeout: float = 10.0) -> str:
    """POST /api/v1/auth/login 을 호출해 accessToken을 반환한다."""
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": password}
            )
    except httpx.HTTPError as exc:
        raise LoginFailedError(f"FinAllQ login request failed: {exc}") from exc

    if response.status_code != 200:
        raise LoginFailedError(f"FinAllQ login failed with status {response.status_code}")

    body = response.json()
    return body["accessToken"]


async def get_token(cache: TokenCache, email: str, password: str, base_url: str) -> str:
    """캐시된 토큰이 있으면 그대로 반환하고, 없으면 로그인해서 캐시에 저장한다."""
    token = cache.get()
    if token is None:
        token = await login(email, password, base_url)
        cache.set(token)
    return token
