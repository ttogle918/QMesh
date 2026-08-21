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
