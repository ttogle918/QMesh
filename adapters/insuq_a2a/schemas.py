"""lookup-clause A2A 스킬 request/response pydantic 모델.

원본 계약은 docs/schemas/lookup-clause.json — 여기 필드는 그 스키마와 반드시 일치해야
한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requester(BaseModel):
    finallq_company_id: str | None = None
    building_id: str | None = None
    policy_id: str | None = None


class LookupClauseRequest(BaseModel):
    requester: Requester
    request_chain_id: str
    question: str
    domain: Literal["track1", "track4"] | None = None
    product: str | None = None


class LookupClauseResponse(BaseModel):
    status: str
    rejection_reason: str | None = None
    answer: str | None = None
    verdict: str | None = None
    confirm_required: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
