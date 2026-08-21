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
