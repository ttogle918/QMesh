"""FinAllQ request-withdrawal A2A 어댑터 — 독립 FastAPI 서비스 (기본 포트 9101).

FinAllQ 코드를 건드리지 않고 기존 REST API(/api/v1/auth/login, /api/v1/accounts,
/api/v1/transfers)를 A2A 봉투로 감싼다. request-withdrawal 외 6개 스킬은 Agent
Card에는 선언돼 있지만 이 프로토타입에서는 미구현 — 501로 명시 응답한다.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from adapters.finallq_a2a.agent_card import load_agent_card
from adapters.finallq_a2a.auth import LoginFailedError, TokenCache, get_token
from adapters.finallq_a2a.finallq_client import (
    AuthExpiredError,
    NoAccountError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    get_first_account_id,
    request_transfer,
)
from adapters.finallq_a2a.mapping import map_transfer_response
from adapters.finallq_a2a.schemas import RequestWithdrawalRequest, RequestWithdrawalResponse

FINALLQ_BASE_URL = os.environ.get("FINALLQ_BASE_URL", "http://localhost:8080")
FINALLQ_SERVICE_EMAIL = os.environ.get("FINALLQ_SERVICE_EMAIL", "")
FINALLQ_SERVICE_PASSWORD = os.environ.get("FINALLQ_SERVICE_PASSWORD", "")

_token_cache = TokenCache()

app = FastAPI(title="FinAllQ A2A Adapter (prototype)")


@app.get("/.well-known/agent-card.json")
async def agent_card_endpoint() -> dict:
    return load_agent_card()


async def _do_transfer(parsed: RequestWithdrawalRequest, token: str) -> dict:
    account_id = await get_first_account_id(token, FINALLQ_BASE_URL)
    return await request_transfer(
        token=token,
        from_account_id=account_id,
        amount=parsed.amount,
        to_account_number=parsed.to_account_number,
        to_bank_code=parsed.to_bank_code,
        memo=parsed.purpose,
        base_url=FINALLQ_BASE_URL,
    )


async def _transfer_with_auth_retry(parsed: RequestWithdrawalRequest) -> dict:
    token = await get_token(_token_cache, FINALLQ_SERVICE_EMAIL, FINALLQ_SERVICE_PASSWORD, FINALLQ_BASE_URL)
    try:
        return await _do_transfer(parsed, token)
    except AuthExpiredError:
        _token_cache.clear()
        token = await get_token(_token_cache, FINALLQ_SERVICE_EMAIL, FINALLQ_SERVICE_PASSWORD, FINALLQ_BASE_URL)
        return await _do_transfer(parsed, token)


@app.post("/a2a/skills/request-withdrawal")
async def request_withdrawal(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        body = None

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "schema_validation_failed",
                "detail": "request body must be a JSON object",
                "request_chain_id": None,
            },
        )

    chain_id_header = request.headers.get("X-Request-Chain-Id")
    body_chain_id = body.get("request_chain_id")
    if chain_id_header is not None and chain_id_header != body_chain_id:
        return JSONResponse(
            status_code=400,
            content={
                "error": "chain_id_mismatch",
                "detail": "X-Request-Chain-Id header does not match request_chain_id in body",
                "request_chain_id": body_chain_id,
            },
        )

    try:
        parsed = RequestWithdrawalRequest.model_validate(body)
    except ValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": "schema_validation_failed",
                "detail": str(exc),
                "request_chain_id": body_chain_id,
            },
        )

    try:
        transfer_response = await _transfer_with_auth_retry(parsed)
    except LoginFailedError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unavailable", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )
    except AuthExpiredError:
        return JSONResponse(
            status_code=502,
            content={
                "error": "upstream_unavailable",
                "detail": "FinAllQ rejected the access token even after re-login",
                "request_chain_id": parsed.request_chain_id,
            },
        )
    except NoAccountError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unavailable", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )
    except UpstreamUnavailableError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unavailable", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )
    except UpstreamTimeoutError as exc:
        return JSONResponse(
            status_code=504,
            content={"error": "upstream_timeout", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "schema_validation_failed", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )

    try:
        mapped = map_transfer_response(transfer_response)
    except ValueError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unavailable", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )

    validated = RequestWithdrawalResponse.model_validate(mapped)
    return JSONResponse(status_code=200, content=validated.model_dump(exclude_none=True))


@app.post("/a2a/skills/{skill_id}")
async def unimplemented_skill(skill_id: str) -> JSONResponse:
    known_skill_ids = {skill["id"] for skill in load_agent_card()["skills"]}
    if skill_id not in known_skill_ids:
        return JSONResponse(
            status_code=404,
            content={"error": "unknown_skill", "detail": f"'{skill_id}' is not declared in the Agent Card"},
        )
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": f"'{skill_id}' is not implemented in this prototype adapter"},
    )
