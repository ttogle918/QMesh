import json

import pytest

from adapters.finallq_a2a.auth import LoginFailedError, TokenCache, get_token, login


async def test_login_returns_access_token(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/auth/login",
        method="POST",
        json={"accessToken": "jwt-abc123", "email": "svc@finallq.example", "role": "USER",
              "canInvite": False, "userId": 1, "companyId": 1},
    )

    token = await login("svc@finallq.example", "pw", base_url="http://test-finallq")

    assert token == "jwt-abc123"
    request = httpx_mock.get_requests()[0]
    payload = json.loads(request.read())
    assert payload == {"email": "svc@finallq.example", "password": "pw"}


async def test_login_raises_on_non_200(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/auth/login", method="POST", status_code=401
    )

    with pytest.raises(LoginFailedError):
        await login("svc@finallq.example", "wrong-pw", base_url="http://test-finallq")


def test_token_cache_get_set_clear():
    cache = TokenCache()
    assert cache.get() is None

    cache.set("jwt-xyz")
    assert cache.get() == "jwt-xyz"

    cache.clear()
    assert cache.get() is None


async def test_get_token_calls_login_when_cache_empty(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/auth/login", method="POST",
        json={"accessToken": "jwt-fresh", "email": "e", "role": "USER", "canInvite": False,
              "userId": 1, "companyId": 1},
    )
    cache = TokenCache()

    token = await get_token(cache, "svc@finallq.example", "pw", base_url="http://test-finallq")

    assert token == "jwt-fresh"
    assert cache.get() == "jwt-fresh"


async def test_get_token_reuses_cache_without_calling_login(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("login() should not be called when cache is populated")

    monkeypatch.setattr("adapters.finallq_a2a.auth.login", fail_if_called)
    cache = TokenCache()
    cache.set("jwt-cached")

    token = await get_token(cache, "svc@finallq.example", "pw", base_url="http://test-finallq")

    assert token == "jwt-cached"
