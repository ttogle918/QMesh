import pytest
from pydantic import ValidationError

from adapters.insuq_a2a.schemas import LookupClauseRequest, LookupClauseResponse, Requester


def test_requester_all_fields_optional():
    r = Requester()
    assert r.finallq_company_id is None
    assert r.building_id is None
    assert r.policy_id is None


def test_lookup_clause_request_requires_question_and_chain_id():
    with pytest.raises(ValidationError):
        LookupClauseRequest(requester=Requester(), request_chain_id="chain-1")  # question 없음


def test_lookup_clause_request_valid_minimal():
    req = LookupClauseRequest(
        requester=Requester(), request_chain_id="chain-1", question="화재보험 자기부담금이 얼마인가요"
    )
    assert req.domain is None
    assert req.product is None


def test_lookup_clause_request_rejects_invalid_domain():
    with pytest.raises(ValidationError):
        LookupClauseRequest(
            requester=Requester(),
            request_chain_id="chain-1",
            question="q",
            domain="not-a-real-domain",
        )


def test_lookup_clause_response_defaults():
    resp = LookupClauseResponse(status="completed")
    assert resp.evidence == []
    assert resp.confirm_required == []
    assert resp.rejection_reason is None
