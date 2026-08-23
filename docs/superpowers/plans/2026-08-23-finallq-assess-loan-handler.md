# FinAllQ `assess-loan` 핸들러 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `adapters/finallq_a2a`에 `assess-loan`(S8, 담보 대출 사전 판정) 스킬 핸들러를 추가한다 — InsuQ의 `verify-collateral-insurance`를 2차 홉으로 호출해 승인/조건부/거절을 판정한다.

**Architecture:** 기존 `request-withdrawal` 핸들러와 동일한 3-레이어(schemas → client → mapping → main 배선) 패턴을 재사용한다. 다만 2차 홉 클라이언트(`insuq_client.py`)는 FinAllQ의 내부 REST API가 아니라 **다른 A2A 어댑터(InsuQ)의 `/a2a/skills/verify-collateral-insurance`를 호출**한다는 점이 다르다 — MaintQ의 `backend/a2a/client.py::call_skill()`과 같은 성격의 "A2A-to-A2A" 호출이다.

**Tech Stack:** FastAPI, pydantic v2, httpx(AsyncClient), pytest + pytest-asyncio(`asyncio_mode=auto`) + pytest-httpx(`httpx_mock` fixture)

## Global Constraints

- 설계 문서: `docs/superpowers/specs/2026-08-23-s8-multihop-loan-collateral-design.md` §①이 이 계획의 유일한 소스 — 판정 규칙 표를 그대로 구현한다.
- `verify-collateral-insurance`는 InsuQ 쪽에 아직 구현이 없다(설계 문서 발견②) — 이 계획은 **호출부만** 만든다. 실제 E2E 테스트는 InsuQ가 엔드포인트를 만든 뒤에나 가능하다. 모든 테스트는 `httpx_mock`으로 InsuQ 어댑터 응답을 흉내낸다.
- FinAllQ 실제 여신 도메인(`Loan` 행 생성, ADMIN `decide()`)은 건드리지 않는다(설계 발견①) — 이 스킬은 순수 사전 판정이다.
- 2차 홉 인증/인가는 이번 스코프에 넣지 않는다(설계 §"아키텍처") — `X-Request-Chain-Id` 헤더만 싣는다.
- 기존 `request-withdrawal` 핸들러·파일 구조를 변경하지 않는다 — 순수 추가만.

---

### Task 1: `AssessLoanRequest`/`AssessLoanResponse` pydantic 모델

**Files:**
- Modify: `adapters/finallq_a2a/schemas.py`
- Test: `tests/adapters/finallq_a2a/test_schemas.py`

**Interfaces:**
- Consumes: 기존 `Requester` 클래스(같은 파일에 이미 정의됨 — `finallq_company_id: str`, `building_id: str | None`, `policy_id: str | None`)
- Produces: `AssessLoanRequest(requester, request_chain_id, loan_amount, purpose, collateral_building_id)`, `AssessLoanResponse(status, decision, condition_note=None, collateral_check=None, market_context=None)`, `CollateralCheck(coverage_amount=None, sufficient=None)` — Task 3(mapping)·Task 4(main)가 이 세 클래스를 그대로 가져다 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/finallq_a2a/test_schemas.py` 맨 끝에 추가:

```python


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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/adapters/finallq_a2a/test_schemas.py -v`
Expected: FAIL — `ImportError: cannot import name 'AssessLoanRequest' from 'adapters.finallq_a2a.schemas'` (6건 모두 실패 또는 에러)

- [ ] **Step 3: 최소 구현 작성**

`adapters/finallq_a2a/schemas.py` 맨 끝에 추가:

```python


class AssessLoanRequest(BaseModel):
    requester: Requester
    request_chain_id: str
    loan_amount: float
    purpose: str
    collateral_building_id: str


class CollateralCheck(BaseModel):
    coverage_amount: float | None = None
    sufficient: bool | None = None


class AssessLoanResponse(BaseModel):
    status: Literal["completed"]
    decision: Literal["approved", "conditional", "rejected"]
    condition_note: str | None = None
    collateral_check: CollateralCheck | None = None
    market_context: dict | None = None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/adapters/finallq_a2a/test_schemas.py -v`
Expected: PASS (기존 테스트 포함 전부)

- [ ] **Step 5: 커밋**

```bash
git add adapters/finallq_a2a/schemas.py tests/adapters/finallq_a2a/test_schemas.py
git commit -m "feat(finallq-a2a): add AssessLoanRequest/Response pydantic models"
```

---

### Task 2: InsuQ 2차 홉 HTTP 클라이언트

**Files:**
- Create: `adapters/finallq_a2a/insuq_client.py`
- Test: `tests/adapters/finallq_a2a/test_insuq_client.py`

**Interfaces:**
- Consumes: 없음(독립 모듈, httpx만 사용)
- Produces: `async call_verify_collateral_insurance(building_id: str, required_coverage: float, request_chain_id: str, finallq_company_id: str, base_url: str, timeout: float = 10.0) -> dict` — InsuQ 어댑터의 파싱된 JSON 응답(dict)을 그대로 반환한다. `UpstreamUnavailableError`·`UpstreamTimeoutError` 예외 클래스. Task 4(main.py)가 이 함수와 두 예외를 가져다 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/finallq_a2a/test_insuq_client.py` 신규 생성:

```python
import httpx
import pytest

from adapters.finallq_a2a.insuq_client import (
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    call_verify_collateral_insurance,
)


async def test_call_sends_expected_payload_and_headers(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/a2a/skills/verify-collateral-insurance",
        method="POST",
        json={"status": "completed", "policy_valid": True, "coverage_amount": 300000000, "evidence": []},
    )

    result = await call_verify_collateral_insurance(
        building_id="BLD-A",
        required_coverage=500000000,
        request_chain_id="chain-1",
        finallq_company_id="FQ-1043",
        base_url="http://test-insuq",
    )

    assert result == {"status": "completed", "policy_valid": True, "coverage_amount": 300000000, "evidence": []}
    request = httpx_mock.get_requests()[0]
    assert request.headers["X-Request-Chain-Id"] == "chain-1"
    import json as _json

    body = _json.loads(request.content)
    assert body["building_id"] == "BLD-A"
    assert body["required_coverage"] == 500000000
    assert body["request_chain_id"] == "chain-1"
    assert body["requester"]["finallq_company_id"] == "FQ-1043"
    assert body["requester"]["building_id"] == "BLD-A"


async def test_call_raises_upstream_timeout_on_timeout(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))

    with pytest.raises(UpstreamTimeoutError):
        await call_verify_collateral_insurance(
            building_id="BLD-A",
            required_coverage=500000000,
            request_chain_id="chain-1",
            finallq_company_id="FQ-1043",
            base_url="http://test-insuq",
        )


async def test_call_raises_upstream_unavailable_on_connect_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"))

    with pytest.raises(UpstreamUnavailableError):
        await call_verify_collateral_insurance(
            building_id="BLD-A",
            required_coverage=500000000,
            request_chain_id="chain-1",
            finallq_company_id="FQ-1043",
            base_url="http://test-insuq",
        )


async def test_call_raises_upstream_unavailable_on_5xx(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/a2a/skills/verify-collateral-insurance",
        method="POST",
        status_code=502,
    )

    with pytest.raises(UpstreamUnavailableError):
        await call_verify_collateral_insurance(
            building_id="BLD-A",
            required_coverage=500000000,
            request_chain_id="chain-1",
            finallq_company_id="FQ-1043",
            base_url="http://test-insuq",
        )


async def test_call_raises_upstream_unavailable_on_non_json_body(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/a2a/skills/verify-collateral-insurance",
        method="POST",
        status_code=200,
        content=b"not json",
    )

    with pytest.raises(UpstreamUnavailableError):
        await call_verify_collateral_insurance(
            building_id="BLD-A",
            required_coverage=500000000,
            request_chain_id="chain-1",
            finallq_company_id="FQ-1043",
            base_url="http://test-insuq",
        )


async def test_call_returns_body_even_when_insuq_rejects(httpx_mock):
    """InsuQ의 status=rejected는 A2A 계약상 정상 200 응답이다 — 예외가 아니라 dict 그대로 반환."""
    httpx_mock.add_response(
        url="http://test-insuq/a2a/skills/verify-collateral-insurance",
        method="POST",
        json={"status": "rejected", "rejection_reason": "policy_not_found", "policy_valid": False, "coverage_amount": 0, "evidence": []},
    )

    result = await call_verify_collateral_insurance(
        building_id="BLD-A",
        required_coverage=500000000,
        request_chain_id="chain-1",
        finallq_company_id="FQ-1043",
        base_url="http://test-insuq",
    )

    assert result["status"] == "rejected"
    assert result["policy_valid"] is False
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/adapters/finallq_a2a/test_insuq_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.finallq_a2a.insuq_client'`

- [ ] **Step 3: 최소 구현 작성**

`adapters/finallq_a2a/insuq_client.py` 신규 생성:

```python
"""FinAllQ 어댑터가 InsuQ 어댑터의 verify-collateral-insurance를 2차 홉으로 호출하는 클라이언트.

InsuQ 코드도 FinAllQ 코드도 건드리지 않는다 — InsuQ의 A2A 봉투 계약
(docs/schemas/verify-collateral-insurance.json)을 그대로 호출한다. InsuQ가 돌려주는
status=rejected는 A2A 계약상 정상 200 응답이다(장애가 아니다) — 이 클라이언트는
파싱된 dict를 그대로 반환하고, "거절"을 판정하는 건 mapping.py의 몫이다.

httpx.TransportError로 폭넓게 잡는 이유는 insuq_a2a/insuq_client.py, finallq_client.py와
동일 — ConnectError·ReadError 등이 전부 그 서브클래스이기 때문이다.
"""

from __future__ import annotations

import httpx


class UpstreamUnavailableError(Exception):
    """InsuQ 어댑터에 연결할 수 없거나 5xx를 반환했을 때."""


class UpstreamTimeoutError(Exception):
    """InsuQ 어댑터 응답이 타임아웃됐을 때."""


async def call_verify_collateral_insurance(
    building_id: str,
    required_coverage: float,
    request_chain_id: str,
    finallq_company_id: str,
    base_url: str,
    timeout: float = 10.0,
) -> dict:
    """POST {base_url}/a2a/skills/verify-collateral-insurance 를 호출한다."""
    payload = {
        "requester": {"finallq_company_id": finallq_company_id, "building_id": building_id},
        "request_chain_id": request_chain_id,
        "building_id": building_id,
        "required_coverage": required_coverage,
    }
    headers = {"X-Request-Chain-Id": request_chain_id}

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.post(
                "/a2a/skills/verify-collateral-insurance", json=payload, headers=headers
            )
    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError(str(exc)) from exc
    except httpx.TransportError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    if response.status_code >= 500:
        raise UpstreamUnavailableError(f"InsuQ adapter returned {response.status_code}")

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamUnavailableError(f"InsuQ adapter returned a non-JSON response: {exc}") from exc
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/adapters/finallq_a2a/test_insuq_client.py -v`
Expected: PASS (6/6)

- [ ] **Step 5: 커밋**

```bash
git add adapters/finallq_a2a/insuq_client.py tests/adapters/finallq_a2a/test_insuq_client.py
git commit -m "feat(finallq-a2a): add InsuQ verify-collateral-insurance 2nd-hop client"
```

---

### Task 3: 판정 매핑 함수 `map_loan_decision`

**Files:**
- Modify: `adapters/finallq_a2a/mapping.py`
- Test: `tests/adapters/finallq_a2a/test_mapping.py`

**Interfaces:**
- Consumes: 없음(순수 함수, dict만 받는다)
- Produces: `map_loan_decision(insuq_response: dict, loan_amount: float) -> dict` — 반환 dict는 `{"decision": str, "condition_note": str | None, "collateral_check": {"coverage_amount": float | None, "sufficient": bool | None}}` 형태. Task 4(main.py)가 이 반환값을 `AssessLoanResponse.model_validate({"status": "completed", **결과})`에 그대로 스프레드한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/finallq_a2a/test_mapping.py` 맨 끝에 추가:

```python


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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/adapters/finallq_a2a/test_mapping.py -v`
Expected: FAIL — `ImportError: cannot import name 'map_loan_decision' from 'adapters.finallq_a2a.mapping'`

- [ ] **Step 3: 최소 구현 작성**

`adapters/finallq_a2a/mapping.py` 맨 끝에 추가:

```python


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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/adapters/finallq_a2a/test_mapping.py -v`
Expected: PASS (기존 테스트 포함 전부)

- [ ] **Step 5: 커밋**

```bash
git add adapters/finallq_a2a/mapping.py tests/adapters/finallq_a2a/test_mapping.py
git commit -m "feat(finallq-a2a): add map_loan_decision for assess-loan verdict"
```

---

### Task 4: `POST /a2a/skills/assess-loan` 엔드포인트 배선

**Files:**
- Modify: `adapters/finallq_a2a/main.py`
- Test: `tests/adapters/finallq_a2a/test_main.py`

**Interfaces:**
- Consumes: Task 1의 `AssessLoanRequest`/`AssessLoanResponse`, Task 2의 `call_verify_collateral_insurance`/`UpstreamTimeoutError`/`UpstreamUnavailableError`(insuq_client), Task 3의 `map_loan_decision`
- Produces: 실제 HTTP 엔드포인트 `POST /a2a/skills/assess-loan` — 이후 태스크 없음(이 계획의 마지막 코드 변경)

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/finallq_a2a/test_main.py`에서 두 가지를 한다:

**(a)** `test_unimplemented_known_skills_return_501`의 parametrize 목록에서 `"assess-loan"`을 제거한다(이제 구현되므로 501 대상이 아니다):

```python
@pytest.mark.parametrize(
    "skill_id",
    [
        "advise-hedge",
        "request-settlement",
        "assess-used-equipment-loan",
        "advise-financing",
        "advise-replacement-financing",
    ],
)
def test_unimplemented_known_skills_return_501(skill_id):
    resp = client.post(f"/a2a/skills/{skill_id}", json={}, headers={"X-Request-Chain-Id": "chain-99"})
    assert resp.status_code == 501
    assert resp.json()["error"] == "not_implemented"
    assert resp.json()["request_chain_id"] == "chain-99"
```

**(b)** 파일 맨 끝에 추가:

```python


def _valid_assess_loan_body(**overrides):
    body = {
        "requester": {"finallq_company_id": "FQ-1043"},
        "request_chain_id": "chain-loan-1",
        "loan_amount": 500000000,
        "purpose": "노후 설비 교체",
        "collateral_building_id": "BLD-A",
    }
    body.update(overrides)
    return body


def test_assess_loan_approved(monkeypatch):
    async def fake_call(**kwargs):
        return {"status": "completed", "policy_valid": True, "coverage_amount": 500000000, "sufficient": True, "evidence": []}

    monkeypatch.setattr(main, "call_verify_collateral_insurance", fake_call)

    resp = client.post(
        "/a2a/skills/assess-loan", json=_valid_assess_loan_body(), headers=_headers("chain-loan-1")
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["decision"] == "approved"
    assert data["collateral_check"]["coverage_amount"] == 500000000


def test_assess_loan_conditional(monkeypatch):
    async def fake_call(**kwargs):
        return {"status": "completed", "policy_valid": True, "coverage_amount": 300000000, "sufficient": False, "evidence": []}

    monkeypatch.setattr(main, "call_verify_collateral_insurance", fake_call)

    resp = client.post(
        "/a2a/skills/assess-loan", json=_valid_assess_loan_body(), headers=_headers("chain-loan-1")
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "conditional"
    assert data["condition_note"] == "보험 300000000→500000000 증액 필요"


def test_assess_loan_rejected(monkeypatch):
    async def fake_call(**kwargs):
        return {"status": "rejected", "rejection_reason": "policy_not_found", "policy_valid": False, "coverage_amount": 0, "evidence": []}

    monkeypatch.setattr(main, "call_verify_collateral_insurance", fake_call)

    resp = client.post(
        "/a2a/skills/assess-loan", json=_valid_assess_loan_body(), headers=_headers("chain-loan-1")
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["decision"] == "rejected"
    assert data["condition_note"] == "policy_not_found"


def test_assess_loan_chain_id_mismatch():
    resp = client.post(
        "/a2a/skills/assess-loan", json=_valid_assess_loan_body(), headers=_headers("chain-DIFFERENT")
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "chain_id_mismatch"


def test_assess_loan_schema_validation_failed():
    body = _valid_assess_loan_body()
    del body["collateral_building_id"]
    resp = client.post("/a2a/skills/assess-loan", json=body, headers=_headers("chain-loan-1"))
    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"


def test_assess_loan_insuq_upstream_unavailable(monkeypatch):
    from adapters.finallq_a2a.insuq_client import UpstreamUnavailableError as InsuqUpstreamUnavailableError

    async def fake_call(**kwargs):
        raise InsuqUpstreamUnavailableError("connection refused")

    monkeypatch.setattr(main, "call_verify_collateral_insurance", fake_call)

    resp = client.post(
        "/a2a/skills/assess-loan", json=_valid_assess_loan_body(), headers=_headers("chain-loan-1")
    )
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_assess_loan_insuq_upstream_timeout(monkeypatch):
    from adapters.finallq_a2a.insuq_client import UpstreamTimeoutError as InsuqUpstreamTimeoutError

    async def fake_call(**kwargs):
        raise InsuqUpstreamTimeoutError("timed out")

    monkeypatch.setattr(main, "call_verify_collateral_insurance", fake_call)

    resp = client.post(
        "/a2a/skills/assess-loan", json=_valid_assess_loan_body(), headers=_headers("chain-loan-1")
    )
    assert resp.status_code == 504
    assert resp.json()["error"] == "upstream_timeout"


def test_assess_loan_forwards_loan_amount_as_required_coverage(monkeypatch):
    captured = {}

    async def fake_call(**kwargs):
        captured.update(kwargs)
        return {"status": "completed", "policy_valid": True, "coverage_amount": 500000000, "sufficient": True, "evidence": []}

    monkeypatch.setattr(main, "call_verify_collateral_insurance", fake_call)

    client.post(
        "/a2a/skills/assess-loan",
        json=_valid_assess_loan_body(loan_amount=700000000),
        headers=_headers("chain-loan-1"),
    )

    assert captured["required_coverage"] == 700000000
    assert captured["building_id"] == "BLD-A"
    assert captured["request_chain_id"] == "chain-loan-1"
    assert captured["finallq_company_id"] == "FQ-1043"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python -m pytest tests/adapters/finallq_a2a/test_main.py -v`
Expected: FAIL — `assess-loan` 관련 신규 테스트는 404(핸들러 없음, `unimplemented_skill` catch-all이 대신 받음)로 실패, `test_unimplemented_known_skills_return_501`은 목록 수정으로 이미 통과

- [ ] **Step 3: 최소 구현 작성**

`adapters/finallq_a2a/main.py`의 import 블록을 수정 — 기존:

```python
from adapters.finallq_a2a.agent_card import load_agent_card
from adapters.finallq_a2a.auth import LoginFailedError, TokenCache, get_token
from adapters.finallq_a2a.finallq_client import (
    AuthExpiredError,
    ForbiddenError,
    NoAccountError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    get_first_account_id,
    request_transfer,
)
from adapters.finallq_a2a.mapping import map_transfer_response
from adapters.finallq_a2a.schemas import RequestWithdrawalRequest, RequestWithdrawalResponse
```

다음으로 교체(끝에 3줄 추가, 나머지는 그대로):

```python
from adapters.finallq_a2a.agent_card import load_agent_card
from adapters.finallq_a2a.auth import LoginFailedError, TokenCache, get_token
from adapters.finallq_a2a.finallq_client import (
    AuthExpiredError,
    ForbiddenError,
    NoAccountError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    get_first_account_id,
    request_transfer,
)
from adapters.finallq_a2a.insuq_client import call_verify_collateral_insurance
from adapters.finallq_a2a.insuq_client import UpstreamTimeoutError as InsuqUpstreamTimeoutError
from adapters.finallq_a2a.insuq_client import UpstreamUnavailableError as InsuqUpstreamUnavailableError
from adapters.finallq_a2a.mapping import map_loan_decision, map_transfer_response
from adapters.finallq_a2a.schemas import (
    AssessLoanRequest,
    AssessLoanResponse,
    RequestWithdrawalRequest,
    RequestWithdrawalResponse,
)
```

`FINALLQ_SERVICE_PASSWORD = os.environ.get(...)` 줄 바로 다음 줄에 추가:

```python
INSUQ_A2A_BASE_URL = os.environ.get("INSUQ_A2A_BASE_URL", "http://localhost:9102")
```

`@app.post("/a2a/skills/request-withdrawal")` 핸들러 함수 전체가 끝나는 지점(`return JSONResponse(status_code=200, content=validated.model_dump(exclude_none=True))` 다음 줄, `@app.post("/a2a/skills/{skill_id}")` catch-all 바로 앞)에 새 핸들러를 삽입:

```python


@app.post("/a2a/skills/assess-loan")
async def assess_loan(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except (ValueError, UnicodeDecodeError):
        body = None

    if not isinstance(body, dict):
        return JSONResponse(
            status_code=400,
            content={
                "error": "schema_validation_failed",
                "detail": "request body must be a JSON object",
                "request_chain_id": None,
            },
        )

    chain_id_header = request.headers.get("X-Request-Chain-Id")
    body_chain_id = body.get("request_chain_id")
    if chain_id_header is not None and chain_id_header != body_chain_id:
        return JSONResponse(
            status_code=400,
            content={
                "error": "chain_id_mismatch",
                "detail": "X-Request-Chain-Id header does not match request_chain_id in body",
                "request_chain_id": body_chain_id,
            },
        )

    try:
        parsed = AssessLoanRequest.model_validate(body)
    except ValidationError as exc:
        return JSONResponse(
            status_code=400,
            content={
                "error": "schema_validation_failed",
                "detail": str(exc),
                "request_chain_id": body_chain_id,
            },
        )

    try:
        insuq_response = await call_verify_collateral_insurance(
            building_id=parsed.collateral_building_id,
            required_coverage=parsed.loan_amount,
            request_chain_id=parsed.request_chain_id,
            finallq_company_id=parsed.requester.finallq_company_id,
            base_url=INSUQ_A2A_BASE_URL,
        )
    except InsuqUpstreamUnavailableError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unavailable", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )
    except InsuqUpstreamTimeoutError as exc:
        return JSONResponse(
            status_code=504,
            content={"error": "upstream_timeout", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )

    mapped = map_loan_decision(insuq_response, parsed.loan_amount)
    validated = AssessLoanResponse.model_validate({"status": "completed", **mapped})
    return JSONResponse(status_code=200, content=validated.model_dump(exclude_none=True))
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python -m pytest tests/adapters/finallq_a2a/ -v`
Expected: PASS 전부 (Task 1~4가 추가한 테스트 + 기존 테스트 전부)

- [ ] **Step 5: 전체 스위트 회귀 확인**

Run: `python -m pytest tests/ -v`
Expected: PASS 전부 — InsuQ 어댑터 테스트를 포함해 이번 변경이 다른 어댑터에 영향 없음을 확인

- [ ] **Step 6: 커밋**

```bash
git add adapters/finallq_a2a/main.py tests/adapters/finallq_a2a/test_main.py
git commit -m "feat(finallq-a2a): wire POST /a2a/skills/assess-loan endpoint"
```

---

### Task 5: 수동 기동 확인 (코드 변경 없음)

**Files:** 없음(검증 전용)

- [ ] **Step 1: 어댑터 기동**

```bash
.venv/Scripts/python.exe -m uvicorn adapters.finallq_a2a.main:app --port 9101
```

- [ ] **Step 2: Agent Card에 assess-loan이 여전히 노출되는지 확인**

```bash
curl -s http://localhost:9101/.well-known/agent-card.json | grep assess-loan
```

Expected: `"id": "assess-loan"` 포함 (Agent Card는 이번 변경으로 안 바뀜 — 배선만 실제로 됐는지 확인하는 스모크 테스트)

- [ ] **Step 3: InsuQ 어댑터가 안 떠 있는 상태에서 502 확인 (실제 네트워크 경로 검증)**

```bash
curl -s -w "\nHTTP:%{http_code}\n" -X POST http://localhost:9101/a2a/skills/assess-loan \
  -H "Content-Type: application/json" \
  -H "X-Request-Chain-Id: chain-smoke-1" \
  -d '{"requester":{"finallq_company_id":"FQ-1043"},"request_chain_id":"chain-smoke-1","loan_amount":500000000,"purpose":"설비 교체","collateral_building_id":"BLD-A"}'
```

Expected: `HTTP:502`, `{"error":"upstream_unavailable", ...}` — `:9102`에 아무것도 안 떠 있으므로 연결 실패가 그대로 전파돼야 한다(설계 §①의 "임의로 rejected로 강등하지 않는다"가 실제로 지켜지는지 확인하는 유일한 수동 검증 지점).

- [ ] **Step 4: 어댑터 종료**

기동한 uvicorn 프로세스를 Ctrl+C 또는 종료.

---

## Self-Review 메모 (계획 작성자용, 실행 불필요)

- 스펙 §① 판정 표 3행(rejected/approved/conditional) 전부 Task 3·4 테스트로 커버됨
- 스펙의 "2차 홉 실패 시 강등 금지"는 Task 4 테스트(`test_assess_loan_insuq_upstream_unavailable`/`_timeout`) + Task 5 수동 확인 이중으로 커버됨
- 스펙의 "market_context는 채우지 않는다"는 Task 1 `test_assess_loan_response_defaults`가 `None` 기본값으로 확인
- 스펙의 "YAGNI — credit_limit/LTV 검사 안 함"은 이 계획 어디에도 그 로직을 추가하지 않는 것으로 자연히 충족(별도 태스크 없음)
- `verify-collateral-insurance` 자체 구현(InsuQ 쪽)은 이 계획 범위 밖 — Global Constraints에 명시
