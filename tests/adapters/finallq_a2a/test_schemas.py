import pytest
from pydantic import ValidationError

from adapters.finallq_a2a.schemas import (
    Requester,
    RequestWithdrawalRequest,
    RequestWithdrawalResponse,
)


def test_requester_requires_finallq_company_id():
    with pytest.raises(ValidationError):
        Requester()


def test_requester_minimal():
    r = Requester(finallq_company_id="FQ-1043")
    assert r.building_id is None
    assert r.policy_id is None


def _valid_request_kwargs():
    return dict(
        requester=Requester(finallq_company_id="FQ-1043"),
        request_chain_id="chain-1",
        po_id="PO-88213",
        amount=1500000,
        supplier="ABC 부품상사",
        approved_by="team-lead-01",
        purpose="유압 실린더 교체 부품 대금",
        error_code="E-4102",
        to_account_number="900-000-001",
    )


def test_request_withdrawal_valid_minimal():
    req = RequestWithdrawalRequest(**_valid_request_kwargs())
    assert req.currency == "KRW"
    assert req.to_bank_code is None


def test_request_withdrawal_requires_to_account_number():
    kwargs = _valid_request_kwargs()
    del kwargs["to_account_number"]
    with pytest.raises(ValidationError):
        RequestWithdrawalRequest(**kwargs)


def test_request_withdrawal_response_status_enum_enforced():
    with pytest.raises(ValidationError):
        RequestWithdrawalResponse(status="not-a-real-status")


def test_request_withdrawal_response_defaults():
    resp = RequestWithdrawalResponse(status="input-required")
    assert resp.fds_check is None
    assert resp.req_id is None


def test_request_withdrawal_rejects_malformed_account_number():
    kwargs = _valid_request_kwargs()
    kwargs["to_account_number"] = "not-a-valid-account-number-format!!"
    with pytest.raises(ValidationError):
        RequestWithdrawalRequest(**kwargs)


def test_request_withdrawal_accepts_valid_account_number_formats():
    for valid_number in ["900-000-001", "1234", "12345678901234567890"]:
        kwargs = _valid_request_kwargs()
        kwargs["to_account_number"] = valid_number
        RequestWithdrawalRequest(**kwargs)  # should not raise


def _valid_assess_loan_kwargs():
    return dict(
        requester=Requester(finallq_company_id="FQ-1043"),
        request_chain_id="chain-1",
        loan_amount=500000000,
        purpose="노후 설비 교체",
        collateral_building_id="BLD-A",
    )


def test_assess_loan_request_valid_minimal():
    from adapters.finallq_a2a.schemas import AssessLoanRequest

    req = AssessLoanRequest(**_valid_assess_loan_kwargs())
    assert req.loan_amount == 500000000
    assert req.collateral_building_id == "BLD-A"


def test_assess_loan_request_requires_collateral_building_id():
    from adapters.finallq_a2a.schemas import AssessLoanRequest

    kwargs = _valid_assess_loan_kwargs()
    del kwargs["collateral_building_id"]
    with pytest.raises(ValidationError):
        AssessLoanRequest(**kwargs)


def test_assess_loan_response_status_enum_enforced():
    from adapters.finallq_a2a.schemas import AssessLoanResponse

    with pytest.raises(ValidationError):
        AssessLoanResponse(status="pending", decision="approved")


def test_assess_loan_response_decision_enum_enforced():
    from adapters.finallq_a2a.schemas import AssessLoanResponse

    with pytest.raises(ValidationError):
        AssessLoanResponse(status="completed", decision="maybe")


def test_assess_loan_response_defaults():
    from adapters.finallq_a2a.schemas import AssessLoanResponse

    resp = AssessLoanResponse(status="completed", decision="approved")
    assert resp.condition_note is None
    assert resp.collateral_check is None
    assert resp.market_context is None


def test_assess_loan_response_collateral_check_nested():
    from adapters.finallq_a2a.schemas import AssessLoanResponse, CollateralCheck

    resp = AssessLoanResponse(
        status="completed",
        decision="conditional",
        condition_note="보험 3억->5억 증액 필요",
        collateral_check=CollateralCheck(coverage_amount=300000000, sufficient=False),
    )
    assert resp.collateral_check.coverage_amount == 300000000
    assert resp.collateral_check.sufficient is False
