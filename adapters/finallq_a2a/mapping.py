"""FinAllQ TransferResponseDto(dict) -> request-withdrawal A2A 응답(dict) 변환.

원본 응답 모양: FinAllQ backend-core/.../dto/TransferResponseDto.java
({requestId, status, message, requestedAt}). 그 자바 클래스는 import하지 않는다 —
REST로 받은 JSON을 dict로 그대로 받는다.

FinAllQ TransferStatus 6종 -> A2A status 매핑 (design spec §②-7):
  PENDING · APPROVED · PENDING_2FA -> input-required (재무 승인 대기)
  BLOCKED                          -> rejected (fds_check=hold)
  REJECTED                         -> rejected
  COMPLETED                        -> completed
알 수 없는 status는 계약 밖의 값이므로 ValueError를 던진다 — 호출부가 502로 변환한다.
"""

from __future__ import annotations

_INPUT_REQUIRED_STATUSES = {"PENDING", "APPROVED", "PENDING_2FA"}


def map_transfer_response(transfer_response: dict) -> dict:
    status = transfer_response.get("status")
    request_id = transfer_response.get("requestId")
    req_id = str(request_id) if request_id is not None else None

    if status in _INPUT_REQUIRED_STATUSES:
        return {"status": "input-required", "req_id": req_id}

    if status == "BLOCKED":
        return {
            "status": "rejected",
            "fds_check": "hold",
            "req_id": req_id,
            "reject_reason": transfer_response.get("message"),
        }

    if status == "REJECTED":
        return {
            "status": "rejected",
            "req_id": req_id,
            "reject_reason": transfer_response.get("message"),
        }

    if status == "COMPLETED":
        return {
            "status": "completed",
            "req_id": req_id,
            "executed_at": transfer_response.get("requestedAt"),
        }

    raise ValueError(f"unknown FinAllQ TransferStatus: {status!r}")


def map_loan_decision(insuq_response: dict, loan_amount: float) -> dict:
    """verify-collateral-insurance 응답 -> assess-loan 판정 매핑 (design §① 표).

    InsuQ 응답에 sufficient가 없으면(스키마상 필수 아님) coverage_amount와 loan_amount를
    직접 비교해 계산한다 — 아직 구현되지 않은 InsuQ 엔드포인트의 선택 필드 보장에
    의존하지 않는다.
    """
    status = insuq_response.get("status")
    policy_valid = insuq_response.get("policy_valid", False)
    coverage_amount = insuq_response.get("coverage_amount", 0)

    if status == "rejected" or not policy_valid:
        return {
            "decision": "rejected",
            "condition_note": insuq_response.get("rejection_reason"),
            "collateral_check": {"coverage_amount": coverage_amount, "sufficient": False},
        }

    sufficient = insuq_response.get("sufficient")
    if sufficient is None:
        sufficient = coverage_amount >= loan_amount

    if sufficient:
        return {
            "decision": "approved",
            "condition_note": None,
            "collateral_check": {"coverage_amount": coverage_amount, "sufficient": True},
        }

    return {
        "decision": "conditional",
        # 🔴 :g 포맷 금지 — 3억(300000000)처럼 큰 정수에 :g를 쓰면 "3e+08"(과학적 표기)로
        # 깨진다(실측). 금액은 정수로 캐스팅해 그대로 찍는다.
        "condition_note": f"보험 {int(coverage_amount)}→{int(loan_amount)} 증액 필요",
        "collateral_check": {"coverage_amount": coverage_amount, "sufficient": False},
    }
