import pytest

from adapters.finallq_a2a.mapping import map_transfer_response


@pytest.mark.parametrize("status", ["PENDING", "APPROVED", "PENDING_2FA"])
def test_input_required_statuses(status):
    result = map_transfer_response({"requestId": 88213, "status": status, "message": None, "requestedAt": "2026-08-21T10:00:00Z"})

    assert result["status"] == "input-required"
    assert result["req_id"] == "88213"


def test_blocked_maps_to_rejected_with_fds_hold():
    result = map_transfer_response(
        {"requestId": 88213, "status": "BLOCKED", "message": "이상거래 탐지로 보류됨", "requestedAt": "2026-08-21T10:00:00Z"}
    )

    assert result["status"] == "rejected"
    assert result["fds_check"] == "hold"
    assert result["reject_reason"] == "이상거래 탐지로 보류됨"
    assert result["req_id"] == "88213"


def test_rejected_maps_to_rejected():
    result = map_transfer_response(
        {"requestId": 88213, "status": "REJECTED", "message": "재무 담당자가 반려함", "requestedAt": "2026-08-21T10:00:00Z"}
    )

    assert result["status"] == "rejected"
    assert result["reject_reason"] == "재무 담당자가 반려함"
    assert "fds_check" not in result


def test_completed_maps_to_completed():
    result = map_transfer_response(
        {"requestId": 88213, "status": "COMPLETED", "message": None, "requestedAt": "2026-08-21T10:00:00Z"}
    )

    assert result["status"] == "completed"
    assert result["executed_at"] == "2026-08-21T10:00:00Z"
    assert result["req_id"] == "88213"


def test_null_request_id_maps_to_none():
    result = map_transfer_response({"requestId": None, "status": "PENDING", "message": None, "requestedAt": None})

    assert result["req_id"] is None


def test_unknown_status_raises_value_error():
    with pytest.raises(ValueError):
        map_transfer_response({"requestId": 1, "status": "SOME_NEW_STATUS", "message": None, "requestedAt": None})


from adapters.finallq_a2a.mapping import map_loan_decision


def test_map_loan_decision_rejected_when_status_rejected():
    result = map_loan_decision(
        {"status": "rejected", "rejection_reason": "policy_not_found", "policy_valid": False, "coverage_amount": 0, "evidence": []},
        loan_amount=500000000,
    )
    assert result["decision"] == "rejected"
    assert result["condition_note"] == "policy_not_found"


def test_map_loan_decision_rejected_when_policy_invalid_even_if_status_completed():
    """status는 completed인데 policy_valid만 false인 방어적 케이스 — 그래도 거절로 판정한다."""
    result = map_loan_decision(
        {"status": "completed", "policy_valid": False, "coverage_amount": 0, "evidence": []},
        loan_amount=500000000,
    )
    assert result["decision"] == "rejected"


def test_map_loan_decision_approved_when_sufficient_true():
    result = map_loan_decision(
        {"status": "completed", "policy_valid": True, "coverage_amount": 500000000, "sufficient": True, "evidence": []},
        loan_amount=500000000,
    )
    assert result["decision"] == "approved"
    assert result["collateral_check"]["coverage_amount"] == 500000000
    assert result["collateral_check"]["sufficient"] is True
    assert result["condition_note"] is None


def test_map_loan_decision_conditional_when_sufficient_false():
    result = map_loan_decision(
        {"status": "completed", "policy_valid": True, "coverage_amount": 300000000, "sufficient": False, "evidence": []},
        loan_amount=500000000,
    )
    assert result["decision"] == "conditional"
    assert result["condition_note"] == "보험 300000000→500000000 증액 필요"
    assert result["collateral_check"]["sufficient"] is False


def test_map_loan_decision_falls_back_to_computed_sufficient_when_key_absent():
    """InsuQ 응답에 sufficient 필드가 없을 수 있다(스키마상 필수 아님) — coverage_amount와
    loan_amount를 직접 비교해 계산한다."""
    result = map_loan_decision(
        {"status": "completed", "policy_valid": True, "coverage_amount": 600000000, "evidence": []},
        loan_amount=500000000,
    )
    assert result["decision"] == "approved"


def test_map_loan_decision_missing_coverage_amount_defaults_to_zero():
    result = map_loan_decision(
        {"status": "completed", "policy_valid": True, "evidence": []},
        loan_amount=500000000,
    )
    assert result["decision"] == "conditional"
    assert result["collateral_check"]["coverage_amount"] == 0


def test_map_loan_decision_handles_null_coverage_amount_without_crashing():
    """InsuQ 쪽 verify-collateral-insurance가 아직 없어(설계 발견②) 실제로 어떤 모양의
    응답을 줄지 확정할 수 없다 — coverage_amount가 키는 있는데 값이 null인 경우도
    방어해야 한다(get(key, 0) 기본값은 키가 아예 없을 때만 적용되고 null에는 안 먹는다)."""
    result = map_loan_decision(
        {"status": "completed", "policy_valid": True, "coverage_amount": None, "evidence": []},
        loan_amount=500000000,
    )
    assert result["decision"] == "conditional"
    assert result["collateral_check"]["coverage_amount"] == 0
