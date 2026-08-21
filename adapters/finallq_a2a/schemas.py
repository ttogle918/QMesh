"""request-withdrawal A2A 스킬 request/response pydantic 모델 (CP-002 반영).

원본 계약은 docs/schemas/request-withdrawal.json — 여기 필드는 그 스키마와 반드시
일치해야 한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requester(BaseModel):
    finallq_company_id: str
    building_id: str | None = None
    policy_id: str | None = None


class RequestWithdrawalRequest(BaseModel):
    requester: Requester
    request_chain_id: str
    po_id: str
    amount: float
    currency: str = "KRW"
    supplier: str
    approved_by: str
    purpose: str
    error_code: str
    to_account_number: str = Field(pattern=r"^[0-9-]{4,20}$")
    to_bank_code: str | None = None


class RequestWithdrawalResponse(BaseModel):
    status: Literal["input-required", "rejected", "completed"]
    fds_check: Literal["pass", "hold"] | None = None
    requires_escalation: bool | None = None
    req_id: str | None = None
    approved_by_finance: str | None = None
    executed_at: str | None = None
    reject_reason: str | None = None
