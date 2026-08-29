"""assess-loan(S8) 계약 JSON 자체를 검증한다.

이 레포는 계약 SSOT를 들고 있지만 지금까지 계약 JSON을 읽는 테스트가 없었다 —
스키마를 손으로 고치다 오타가 나도 아무도 못 잡는 상태였다. 2026-08-29
collateral_check 확장(insured_value/effective_recovery/evidence)을 계기로 신설한다.

verify-collateral-insurance(2차 홉 원본)와 필드 타입이 어긋나면 어댑터가 조용히
None을 채우고 넘어가므로, 두 계약을 교차 검증하는 테스트를 함께 둔다.
"""

import json
from pathlib import Path

import pytest

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "docs" / "schemas"


@pytest.fixture(scope="module")
def assess_loan() -> dict:
    return json.loads((SCHEMA_DIR / "assess-loan.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def verify_collateral() -> dict:
    return json.loads(
        (SCHEMA_DIR / "verify-collateral-insurance.json").read_text(encoding="utf-8")
    )


def _collateral_props(assess_loan: dict) -> dict:
    return assess_loan["response"]["properties"]["collateral_check"]["properties"]


def test_collateral_check_exposes_proportional_compensation_fields(assess_loan):
    """비례보상 판정 근거 3필드가 S8 collateral_check에 노출된다."""
    props = _collateral_props(assess_loan)
    assert props["coverage_amount"]["type"] == "number"
    assert props["insured_value"]["type"] == "number"
    assert props["effective_recovery"]["type"] == "number"
    assert props["sufficient"]["type"] == "boolean"


def test_collateral_check_evidence_is_array_of_string(assess_loan):
    """evidence는 인용 문자열 배열이다(verify-collateral-insurance와 같은 모양)."""
    evidence = _collateral_props(assess_loan)["evidence"]
    assert evidence["type"] == "array"
    assert evidence["items"]["type"] == "string"


def test_evidence_citation_pattern_matches_upstream_contract(
    assess_loan, verify_collateral
):
    """인용 형식 정규식이 2차 홉 원본(verify-collateral-insurance)과 글자 단위로 같다.

    두 계약이 서로 다른 정규식을 들고 있으면, InsuQ가 통과시킨 인용을 FinAllQ가
    거절하는(또는 그 반대) 조용한 불일치가 생긴다.
    """
    downstream = _collateral_props(assess_loan)["evidence"]["items"]["pattern"]
    upstream = verify_collateral["response"]["properties"]["evidence"]["items"]["pattern"]
    assert downstream == upstream


def test_decision_enum_is_unchanged(assess_loan):
    """이번 확장은 판정 규칙을 바꾸지 않는다 — decision enum은 그대로여야 한다."""
    decision = assess_loan["response"]["properties"]["decision"]
    assert decision["enum"] == ["approved", "conditional", "rejected"]
