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
