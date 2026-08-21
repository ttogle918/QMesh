"""InsuQ lookup-clause A2A 어댑터 — 독립 FastAPI 서비스 (기본 포트 9102).

InsuQ 코드를 건드리지 않고 기존 POST /qa(:8000)를 A2A 봉투로 감싼다. 전송 계층
규약은 InsuQ/docs/A2A_API_SPEC.md 를 따른다. lookup-clause 외 4개 스킬은 Agent
Card에는 선언돼 있지만 이 프로토타입에서는 미구현 — 501로 명시 응답한다.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from adapters.insuq_a2a.agent_card import load_agent_card
from adapters.insuq_a2a.insuq_client import UpstreamTimeoutError, UpstreamUnavailableError, call_qa
from adapters.insuq_a2a.mapping import map_qa_response
from adapters.insuq_a2a.schemas import LookupClauseRequest

INSUQ_BASE_URL = os.environ.get("INSUQ_AI_ENGINE_BASE_URL", "http://localhost:8000")

KNOWN_SKILL_IDS = [
    "advise-policy-renewal",
    "verify-collateral-insurance",
    "notify-asset-change",
    "notify-risk-change",
    "claim-insurance",
]

app = FastAPI(title="InsuQ A2A Adapter (prototype)")


@app.get("/.well-known/agent-card.json")
async def agent_card_endpoint() -> dict:
    return load_agent_card()


@app.post("/a2a/skills/lookup-clause")
async def lookup_clause(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
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
        parsed = LookupClauseRequest.model_validate(body)
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
        qa_response = await call_qa(
            question=parsed.question,
            domain=parsed.domain,
            product=parsed.product,
            base_url=INSUQ_BASE_URL,
        )
    except UpstreamUnavailableError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "error": "upstream_unavailable",
                "detail": str(exc),
                "request_chain_id": parsed.request_chain_id,
            },
        )
    except UpstreamTimeoutError as exc:
        return JSONResponse(
            status_code=504,
            content={
                "error": "upstream_timeout",
                "detail": str(exc),
                "request_chain_id": parsed.request_chain_id,
            },
        )

    mapped = map_qa_response(qa_response)
    return JSONResponse(status_code=200, content=mapped)


@app.post("/a2a/skills/{skill_id}")
async def unimplemented_skill(skill_id: str) -> JSONResponse:
    if skill_id not in KNOWN_SKILL_IDS:
        return JSONResponse(
            status_code=404,
            content={
                "error": "unknown_skill",
                "detail": f"'{skill_id}' is not declared in the Agent Card",
            },
        )
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented",
            "detail": f"'{skill_id}' is not implemented in this prototype adapter",
        },
    )
