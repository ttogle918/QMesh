# S8 assess-loan collateral_check 확장 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `assess-loan`(S8) 응답의 `collateral_check`에 `insured_value`·`effective_recovery`·`evidence`를 추가해, MaintQ가 받는 조건부 승인 판정에 비례보상 근거와 약관 인용이 함께 실리게 한다.

**Architecture:** 계약 SSOT(`A2A_Q/docs/schemas/assess-loan.json`)를 먼저 확장하고, 그 계약을 소비하는 FinAllQ 프로덕션 어댑터(`a2a_adapter/`)의 pydantic 모델과 매핑 함수를 뒤따라 확장한다. 판정 로직(`map_assess_loan_response`)은 **건드리지 않는다** — S8은 `sufficient` 하나로만 approved/conditional을 가르는 계약이고, 이번 변경은 판정 근거를 실어 보내는 것이지 판정 규칙을 바꾸는 게 아니다. 기존 S13(`assess-used-equipment-loan`)의 `build_collateral_check`가 이미 같은 필드 3개 중 2개를 다루므로 그 관례(하향 열화 · `exclude_none`)를 그대로 재사용한다.

**Tech Stack:** JSON Schema (계약), Python 3.13 · FastAPI · pydantic v2 · pytest (어댑터)

## Global Constraints

- **계약 SSOT는 `A2A_Q/docs/schemas/assess-loan.json`이다.** 구현이 계약을 앞서지 않는다 — Task 1(계약)이 Task 2~4(구현)보다 먼저 커밋된다.
- **"자동 승인 경로 없음" 불변식을 유지한다.** FinAllQ 백엔드 `Loan.status`는 이 경로에서 `UNDER_REVIEW`로 남고, `decision`의 `approved`/`conditional`은 backend `LoanStatus`와 별개의 A2A 도메인 값이다(`mapping.py:106-116` docstring). 이번 변경은 이 불변식을 건드리지 않는다.
- **하향 열화 관례:** optional 필드가 InsuQ 응답에 없으면 `None`으로 채우고 예외를 던지지 않는다. `InvalidInsuQResponseError`는 `sufficient` 자체가 없거나 타입이 틀린 더 심각한 경우에만 `insuq_client.py`가 던진다. 이 `None`은 파이썬 레벨 값이며 `model_dump(exclude_none=True)` 직렬화를 거치면 JSON에서 키 자체가 생략된다.
- **`evidence` 타입은 `array of string`이다** (`verify-collateral-insurance.json` 응답 원문과 동일). 인용 형식 정규식도 그 계약에서 그대로 복사한다: `^.+ .+ 제\d+조( [①-⑳\d]+항?)?(, p\.\d+)?$`
- **🔴 알려진 제약 — InsuQ TASK-H08:** InsuQ가 반환하는 `evidence`는 현재 **실제 약관 조항 인용이 아니라 정책 레코드 요약 문자열**이다(`InsuQ_시나리오맵.html` L396: "소비자 신호 대기 — FinAllQ가 이 필드를 실제로 쓰기 시작할 때 처리"). 이 계획은 계약과 파이프라인만 열어두는 것이고, **데모 슬라이드·화면에 이 값을 "약관 조항 인용"으로 노출하면 안 된다.** Task 5가 이 사실을 문서에 못 박는다.
- **범위 밖:** `A2A_Q/adapters/finallq_a2a/`는 2스킬 프로토타입(`mapping.py` 90줄, `build_assess_loan_collateral_check` 자체가 없고 `map_loan_decision`이라는 다른 모양을 씀)이고 데모에서 돌지 않는다(README L73 "Templates + 프로토타입"). 이 계획은 **건드리지 않는다.** 드리프트 사실만 Task 5에서 기록한다.

---

## File Structure

| 파일 | 레포 | 책임 | 변경 |
|---|---|---|---|
| `docs/schemas/assess-loan.json` | A2A_Q | S8 계약 SSOT | Modify |
| `tests/contracts/test_assess_loan_schema.py` | A2A_Q | 계약 JSON 자체를 검증(현재 이런 테스트가 하나도 없다) | Create |
| `a2a_adapter/schemas.py` | FinAllQ | pydantic 응답 모델 | Modify (L77-85) |
| `a2a_adapter/mapping.py` | FinAllQ | InsuQ 응답 → `collateral_check` 조립 | Modify (L82-99) |
| `a2a_adapter/tests/test_mapping.py` | FinAllQ | 매핑 단위 테스트 | Modify |
| `a2a_adapter/tests/test_main.py` | FinAllQ | 엔드포인트 통합 테스트 | Modify |
| `A2A_DIAGRAMS.md` | A2A_Q | 다이어그램 SSOT §②2.3 | Modify |

---

### Task 1: 계약 스키마 확장 + 계약 검증 테스트 신설 (A2A_Q)

계약 JSON을 읽고 검증하는 테스트가 이 레포에 **하나도 없다**(`grep -rn "docs/schemas" tests/` → 0건). 계약을 바꾸는 김에 그 계약이 스스로를 지키는 테스트를 함께 만든다. 이 테스트가 없으면 Task 1은 독립적으로 검증할 방법이 없다.

**Files:**
- Modify: `C:\Users\ttogl\workspace\A2A_Q\docs\schemas\assess-loan.json` (`response.properties.collateral_check.properties`)
- Create: `C:\Users\ttogl\workspace\A2A_Q\tests\contracts\__init__.py` (빈 파일)
- Create: `C:\Users\ttogl\workspace\A2A_Q\tests\contracts\test_assess_loan_schema.py`

**Interfaces:**
- Consumes: 없음 (첫 작업)
- Produces: `assess-loan.json`의 `collateral_check`가 `coverage_amount`(number) · `insured_value`(number) · `effective_recovery`(number) · `sufficient`(boolean) · `evidence`(array of string) 5필드를 정의한다. Task 2~4가 이 필드명·타입을 그대로 쓴다.

- [ ] **Step 1: 실패하는 계약 테스트를 쓴다**

`C:\Users\ttogl\workspace\A2A_Q\tests\contracts\__init__.py` 를 빈 파일로 만들고, `test_assess_loan_schema.py` 에 아래를 쓴다.

```python
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
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/A2A_Q && python -m pytest tests/contracts/test_assess_loan_schema.py -v`

Expected: FAIL — 4개 중 3개가 `KeyError: 'insured_value'` / `KeyError: 'evidence'` 로 실패하고, `test_decision_enum_is_unchanged` 만 PASS.

- [ ] **Step 3: 계약 JSON을 확장한다**

`docs/schemas/assess-loan.json` 의 `response.properties.collateral_check` 블록 전체를 아래로 교체한다. (`description` 도 2차 홉이 비례보상까지 실어온다는 사실을 반영해 갱신한다.)

```json
      "collateral_check": {
        "type": "object",
        "description": "InsuQ verify-collateral-insurance 2차 홉 응답을 요약해 담음. insured_value/effective_recovery/evidence는 optional — InsuQ가 내려주지 않으면 키 자체가 생략된다(하향 열화, 계약 위반 아님).",
        "properties": {
          "coverage_amount": { "type": "number" },
          "insured_value": { "type": "number", "description": "보험가액 — 비례보상(상법 674조) 계산 기준" },
          "effective_recovery": { "type": "number", "description": "실효 회수액 = 손해액 x (보험금액/보험가액). InsuQ가 loss_amount 없이 호출되면 생략된다" },
          "sufficient": { "type": "boolean" },
          "evidence": {
            "type": "array",
            "description": "2차 홉이 반환한 인용 문자열을 그대로 전달한다. 🔴 InsuQ TASK-H08 미해결 — 현재 값은 실제 약관 조항 인용이 아니라 정책 레코드 요약 문자열이므로 화면에 '약관 조항 인용'으로 표시하면 안 된다.",
            "items": { "type": "string", "pattern": "^.+ .+ 제\\d+조( [①-⑳\\d]+항?)?(, p\\.\\d+)?$" }
          }
        }
      },
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/A2A_Q && python -m pytest tests/contracts/ -v`

Expected: PASS — 4 passed.

- [ ] **Step 5: 기존 테스트가 안 깨졌는지 확인한다**

Run: `cd /c/Users/ttogl/workspace/A2A_Q && python -m pytest -q`

Expected: `89 passed` (기존 85 + 신규 4). 실패 0건.

- [ ] **Step 6: 커밋**

```bash
cd /c/Users/ttogl/workspace/A2A_Q
git add docs/schemas/assess-loan.json tests/contracts/
git commit -m "feat(contract): assess-loan collateral_check에 비례보상·evidence 필드 추가

S8 응답이 coverage_amount/sufficient 둘만 실어보내던 것을 S13과 같은
비례보상 3필드(insured_value·effective_recovery·evidence)까지 확장한다.
계약 JSON을 읽는 테스트가 이 레포에 없었어서 함께 신설했다.

evidence는 InsuQ TASK-H08 미해결 상태(정책 레코드 요약 문자열)라 계약만
열어두고 화면 노출은 금지한다 — description에 명시."
```

---

### Task 2: FinAllQ pydantic 모델 확장

**Files:**
- Modify: `C:\Users\ttogl\workspace\FinAllQ\a2a_adapter\schemas.py:77-85` (`AssessLoanCollateralCheck`)
- Test: `C:\Users\ttogl\workspace\FinAllQ\a2a_adapter\tests\test_schemas.py`

**Interfaces:**
- Consumes: Task 1이 확정한 5필드 이름·타입
- Produces: `AssessLoanCollateralCheck(coverage_amount: float|None, insured_value: float|None, effective_recovery: float|None, sufficient: bool|None, evidence: list[str]|None)` — Task 3이 이 모델에 dict를 부어 넣는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`a2a_adapter/tests/test_schemas.py` 끝에 추가한다.

```python
def test_assess_loan_collateral_check_accepts_proportional_fields():
    """S8 collateral_check가 비례보상 3필드를 받는다(2026-08-29 계약 확장)."""
    from a2a_adapter.schemas import AssessLoanCollateralCheck

    check = AssessLoanCollateralCheck(
        coverage_amount=300_000_000,
        insured_value=500_000_000,
        effective_recovery=180_000_000,
        sufficient=False,
        evidence=["주택화재보험 보통약관 제12조 ①항, p.34"],
    )
    assert check.insured_value == 500_000_000
    assert check.effective_recovery == 180_000_000
    assert check.evidence == ["주택화재보험 보통약관 제12조 ①항, p.34"]


def test_assess_loan_collateral_check_omits_absent_optionals_when_serialized():
    """하향 열화: InsuQ가 안 내려준 필드는 JSON에서 키 자체가 사라진다."""
    from a2a_adapter.schemas import AssessLoanCollateralCheck

    check = AssessLoanCollateralCheck(coverage_amount=300_000_000, sufficient=False)
    dumped = check.model_dump(exclude_none=True)
    assert dumped == {"coverage_amount": 300_000_000, "sufficient": False}
    assert "insured_value" not in dumped
    assert "effective_recovery" not in dumped
    assert "evidence" not in dumped
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/FinAllQ/a2a_adapter && python -m pytest tests/test_schemas.py -k proportional -v`

Expected: FAIL — pydantic이 정의되지 않은 필드를 무시하거나(`insured_value` 접근에서 `AttributeError`) 거부한다.

- [ ] **Step 3: 모델을 확장한다**

`a2a_adapter/schemas.py:77-85` 의 `AssessLoanCollateralCheck` 클래스 전체를 아래로 교체한다.

```python
class AssessLoanCollateralCheck(BaseModel):
    """assess-loan 응답의 collateral_check 서브구조.

    2026-08-29 계약 확장 전까지는 coverage_amount/sufficient 둘뿐이었다 — MaintQ가
    받는 조건부 승인 판정에 "왜 부족한지"(보험가액 대비 비례보상)와 근거 인용이
    빠져 있어 demo 나레이션이 화면 밖 설명에 의존하고 있었다. S13
    (assess-used-equipment-loan)의 CollateralCheck와 같은 필드 집합이 됐지만,
    계약이 서로 다르므로(S8은 이 필드들을 판정에 쓰지 않는다 — sufficient 하나로만
    approved/conditional을 가른다) 클래스는 계속 분리해 둔다.

    insured_value/effective_recovery/evidence는 전부 optional이다 — InsuQ가 안 내려주면
    None으로 남고 model_dump(exclude_none=True) 직렬화에서 키가 생략된다(하향 열화,
    계약 위반 아님). mapping.build_assess_loan_collateral_check 참고.

    🔴 evidence는 InsuQ TASK-H08 미해결 — 실제 약관 조항 인용이 아니라 정책 레코드
    요약 문자열이다. 값을 그대로 통과시키되 "약관 인용"으로 표시하지 말 것.
    """

    coverage_amount: float | None = None
    insured_value: float | None = None
    effective_recovery: float | None = None
    sufficient: bool | None = None
    evidence: list[str] | None = None
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/FinAllQ/a2a_adapter && python -m pytest tests/test_schemas.py -v`

Expected: PASS — 신규 2건 포함 전부 통과.

- [ ] **Step 5: 커밋**

```bash
cd /c/Users/ttogl/workspace/FinAllQ
git add a2a_adapter/schemas.py a2a_adapter/tests/test_schemas.py
git commit -m "feat(a2a): AssessLoanCollateralCheck에 비례보상·evidence 필드 추가

A2A_Q 계약(assess-loan.json) 2026-08-29 확장분을 반영한다. 전부 optional이라
InsuQ 미지원 시 exclude_none으로 키가 생략된다(S13 CollateralCheck와 동일 관례)."
```

---

### Task 3: 매핑 함수 확장 — InsuQ 응답에서 3필드를 옮겨 담는다

**Files:**
- Modify: `C:\Users\ttogl\workspace\FinAllQ\a2a_adapter\mapping.py:82-99` (`build_assess_loan_collateral_check`)
- Test: `C:\Users\ttogl\workspace\FinAllQ\a2a_adapter\tests\test_mapping.py`

**Interfaces:**
- Consumes: Task 2의 `AssessLoanCollateralCheck` 필드 집합
- Produces: `build_assess_loan_collateral_check(insuq_response: dict | None) -> dict` — 5키를 가진 dict를 반환한다(`insuq_response is None`이면 5키 전부 `None`). Task 4의 통합 테스트가 이 반환값을 엔드포인트 응답에서 확인한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`a2a_adapter/tests/test_mapping.py` 끝에 추가한다.

```python
def test_assess_loan_collateral_check_carries_proportional_fields():
    """InsuQ가 비례보상·근거를 내려주면 그대로 옮겨 담는다(2026-08-29 계약 확장)."""
    from a2a_adapter.mapping import build_assess_loan_collateral_check

    result = build_assess_loan_collateral_check(
        {
            "coverage_amount": 300_000_000,
            "insured_value": 500_000_000,
            "effective_recovery": 180_000_000,
            "sufficient": False,
            "evidence": ["주택화재보험 보통약관 제12조 ①항, p.34"],
        }
    )
    assert result == {
        "coverage_amount": 300_000_000,
        "insured_value": 500_000_000,
        "effective_recovery": 180_000_000,
        "sufficient": False,
        "evidence": ["주택화재보험 보통약관 제12조 ①항, p.34"],
    }


def test_assess_loan_collateral_check_degrades_when_insuq_omits_optionals():
    """InsuQ가 optional 3필드를 안 내려줘도 예외 없이 None으로 열화한다."""
    from a2a_adapter.mapping import build_assess_loan_collateral_check

    result = build_assess_loan_collateral_check(
        {"coverage_amount": 300_000_000, "sufficient": True}
    )
    assert result["coverage_amount"] == 300_000_000
    assert result["sufficient"] is True
    assert result["insured_value"] is None
    assert result["effective_recovery"] is None
    assert result["evidence"] is None


def test_assess_loan_collateral_check_all_none_when_insuq_not_called():
    """backend가 이미 REJECTED라 InsuQ를 안 부른 경로 — 5필드 전부 None."""
    from a2a_adapter.mapping import build_assess_loan_collateral_check

    assert build_assess_loan_collateral_check(None) == {
        "coverage_amount": None,
        "insured_value": None,
        "effective_recovery": None,
        "sufficient": None,
        "evidence": None,
    }


def test_assess_loan_decision_still_keyed_on_sufficient_only():
    """이번 확장은 판정 규칙을 바꾸지 않는다 — effective_recovery가 없어도
    sufficient가 True면 approved다(S13의 '하향 열화 시 conditional' 규칙을
    S8에 잘못 옮겨오지 않았는지 지키는 회귀 테스트)."""
    from a2a_adapter.mapping import map_assess_loan_response

    result = map_assess_loan_response(
        {"loanId": 501, "status": "UNDER_REVIEW", "rejectionCode": None},
        {
            "coverage_amount": 900_000_000,
            "insured_value": None,
            "effective_recovery": None,
            "sufficient": True,
            "evidence": None,
        },
    )
    assert result["decision"] == "approved"
    assert result["condition_note"] is None
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/FinAllQ/a2a_adapter && python -m pytest tests/test_mapping.py -k "proportional or degrades or not_called or keyed_on" -v`

Expected: FAIL — 앞 3건이 `AssertionError`(반환 dict에 `insured_value` 키가 없음). `test_assess_loan_decision_still_keyed_on_sufficient_only`는 PASS(기존 로직이 이미 그렇게 동작).

- [ ] **Step 3: 매핑 함수를 확장한다**

`a2a_adapter/mapping.py:82-99` 의 `build_assess_loan_collateral_check` 전체를 아래로 교체한다.

```python
def build_assess_loan_collateral_check(insuq_response: dict | None) -> dict:
    """InsuQ verify-collateral-insurance 응답 -> assess-loan 응답의 collateral_check
    서브구조.

    2026-08-29 계약 확장으로 S13(build_collateral_check)과 같은 필드 집합이 됐다 —
    coverage_amount/insured_value/effective_recovery/sufficient에 evidence가 하나 더
    붙는다(S13 계약엔 evidence가 없다).

    🔴 **필드가 같아졌다고 판정 규칙까지 S13을 따라가면 안 된다.** S13의
    map_used_equipment_loan_response는 "insured_value·effective_recovery가 둘 다
    있어야 approved"라는 하향 열화 규칙을 쓰지만, S8(map_assess_loan_response)은
    계약상 sufficient 하나로만 approved/conditional을 가른다. 이번 확장은 판정
    근거를 실어 보내는 것이지 판정을 바꾸는 게 아니다
    (tests/test_mapping.py::test_assess_loan_decision_still_keyed_on_sufficient_only
    가 이걸 지킨다).

    insuq_response가 None인 경우는 백엔드 loan이 이미 REJECTED라 애초에 InsuQ를
    호출하지 않은 경로다(main.py) — 이때는 전부 null이다. optional 필드가 InsuQ
    응답에 없어도 InvalidInsuQResponseError를 던지지 않는다(하향 열화) — 그건
    sufficient 자체가 없거나 타입이 틀린 더 심각한 경우에만 insuq_client.py가
    이미 처리한다. 이 None은 파이썬 dict 레벨 값이며 main.py의
    model_dump(exclude_none=True) 직렬화를 거치면 JSON에서 키가 생략된다.

    🔴 evidence는 InsuQ TASK-H08 미해결 — 실제 약관 조항 인용이 아니라 정책 레코드
    요약 문자열이 온다. 여기서는 가공 없이 그대로 통과시키고, 표시 계층이 이걸
    "약관 인용"이라고 부르지 않게 하는 건 소비자 책임이다.
    """
    if insuq_response is None:
        return {
            "coverage_amount": None,
            "insured_value": None,
            "effective_recovery": None,
            "sufficient": None,
            "evidence": None,
        }

    return {
        "coverage_amount": insuq_response.get("coverage_amount"),
        "insured_value": insuq_response.get("insured_value"),
        "effective_recovery": insuq_response.get("effective_recovery"),
        "sufficient": insuq_response.get("sufficient"),
        "evidence": insuq_response.get("evidence"),
    }
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/FinAllQ/a2a_adapter && python -m pytest tests/test_mapping.py -v`

Expected: PASS — 신규 4건 포함 전부 통과, 실패 0건.

- [ ] **Step 5: 커밋**

```bash
cd /c/Users/ttogl/workspace/FinAllQ
git add a2a_adapter/mapping.py a2a_adapter/tests/test_mapping.py
git commit -m "feat(a2a): assess-loan collateral_check에 InsuQ 비례보상·evidence 전달

build_assess_loan_collateral_check가 InsuQ 응답의 insured_value·
effective_recovery·evidence를 그대로 옮겨 담는다. 판정 규칙(sufficient 하나로
approved/conditional)은 그대로 — S13의 하향열화 규칙을 옮겨오지 않았는지
지키는 회귀 테스트를 함께 추가했다."
```

---

### Task 4: 엔드포인트 통합 검증 — 실제 데모 숫자로

Task 2·3은 단위 레벨이다. 실제로 `POST /a2a/skills/assess-loan` 응답 JSON에 필드가 실려 나가는지, 그리고 `exclude_none` 직렬화가 의도대로 동작하는지는 엔드포인트를 통과시켜야 확인된다.

**Files:**
- Test: `C:\Users\ttogl\workspace\FinAllQ\a2a_adapter\tests\test_main.py`

**Interfaces:**
- Consumes: Task 3의 `build_assess_loan_collateral_check` 5키 반환값, Task 2의 `AssessLoanCollateralCheck`
- Produces: 없음 (최종 검증 작업)

- [ ] **Step 1: 실패하는 통합 테스트를 쓴다**

`a2a_adapter/tests/test_main.py` 끝에 추가한다. 기존 테스트(L457 부근 `test_...UNDER_REVIEW면 항상 InsuQ를 호출한다`)의 monkeypatch 관례를 그대로 따른다 — **작업 전에 그 테스트를 먼저 읽고 fixture/monkeypatch 이름을 이 파일의 실제 관례에 맞춰 조정할 것.**

```python
def test_assess_loan_response_carries_proportional_evidence(monkeypatch, client):
    """데모 시나리오 2 실제 숫자(담보 3억 / 보험가액 5억 / 요구 5억)로,
    조건부 승인 응답에 비례보상 근거가 실려 나가는지 확인한다."""

    async def fake_apply_loan(*args, **kwargs):
        return {"loanId": 520, "status": "UNDER_REVIEW", "rejectionCode": None}

    async def fake_verify_collateral(*args, **kwargs):
        return {
            "status": "completed",
            "policy_valid": True,
            "coverage_amount": 300_000_000,
            "insured_value": 500_000_000,
            "effective_recovery": 180_000_000,
            "sufficient": False,
            "evidence": ["주택화재보험 보통약관 제12조 ①항, p.34"],
        }

    monkeypatch.setattr("a2a_adapter.main.apply_loan", fake_apply_loan)
    monkeypatch.setattr("a2a_adapter.main.verify_collateral_insurance", fake_verify_collateral)

    response = client.post(
        "/a2a/skills/assess-loan",
        json={
            "requester": {"finallq_company_id": "8818", "building_id": "BLD-A"},
            "request_chain_id": "CHAIN-LOAN-plan-a",
            "loan_amount": 500_000_000,
            "purpose": "설비 교체",
            "collateral_building_id": "BLD-A",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["decision"] == "conditional"
    check = body["collateral_check"]
    assert check["coverage_amount"] == 300_000_000
    assert check["insured_value"] == 500_000_000
    assert check["effective_recovery"] == 180_000_000
    assert check["sufficient"] is False
    assert check["evidence"] == ["주택화재보험 보통약관 제12조 ①항, p.34"]


def test_assess_loan_response_omits_fields_insuq_did_not_send(monkeypatch, client):
    """InsuQ가 optional을 안 내려주면 응답 JSON에 키 자체가 없어야 한다."""

    async def fake_apply_loan(*args, **kwargs):
        return {"loanId": 521, "status": "UNDER_REVIEW", "rejectionCode": None}

    async def fake_verify_collateral(*args, **kwargs):
        return {
            "status": "completed",
            "policy_valid": True,
            "coverage_amount": 900_000_000,
            "sufficient": True,
            "evidence": [],
        }

    monkeypatch.setattr("a2a_adapter.main.apply_loan", fake_apply_loan)
    monkeypatch.setattr("a2a_adapter.main.verify_collateral_insurance", fake_verify_collateral)

    response = client.post(
        "/a2a/skills/assess-loan",
        json={
            "requester": {"finallq_company_id": "8818", "building_id": "BLD-A"},
            "request_chain_id": "CHAIN-LOAN-plan-a-2",
            "loan_amount": 500_000_000,
            "purpose": "설비 교체",
            "collateral_building_id": "BLD-A",
        },
    )

    assert response.status_code == 200
    check = response.json()["collateral_check"]
    assert check["sufficient"] is True
    assert "insured_value" not in check
    assert "effective_recovery" not in check
    assert check["evidence"] == []  # 빈 배열은 None이 아니라 그대로 실린다
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/FinAllQ/a2a_adapter && python -m pytest tests/test_main.py -k "proportional_evidence or did_not_send" -v`

Expected: 첫 번째는 `KeyError: 'insured_value'`로 FAIL. (Task 2·3이 이미 끝났다면 통과할 수도 있다 — 그 경우 이 Task는 회귀 방어용 테스트 추가로만 의미가 있고, Step 3을 건너뛴다.)

- [ ] **Step 3: 실패하면 원인을 잡는다**

Task 2·3이 끝났는데도 실패한다면 원인은 하나뿐이다 — `main.py`가 `collateral_check`를 `AssessLoanCollateralCheck`로 감싸지 않고 raw dict를 그대로 응답에 넣거나, `model_dump(exclude_none=True)`가 아닌 다른 직렬화를 쓰고 있는 경우다. `a2a_adapter/main.py:354-355` 부근을 읽어 아래를 확인한다:

```python
collateral_check = build_assess_loan_collateral_check(insuq_response)
return map_assess_loan_response(loan_response, collateral_check)
```

이 반환 dict가 `AssessLoanResponse`로 검증되어 `exclude_none`으로 직렬화되는 경로인지 확인하고, 아니라면 그 경로에 맞춘다. **판정 로직(`map_assess_loan_response`)은 절대 고치지 않는다.**

- [ ] **Step 4: 어댑터 전체 테스트를 돌린다**

Run: `cd /c/Users/ttogl/workspace/FinAllQ/a2a_adapter && python -m pytest -q`

Expected: 실패 0건. (변경 전 baseline 개수를 Task 2 시작 전에 기록해두고, 신규 8건만큼만 늘었는지 대조한다.)

- [ ] **Step 5: 커밋**

```bash
cd /c/Users/ttogl/workspace/FinAllQ
git add a2a_adapter/tests/test_main.py
git commit -m "test(a2a): assess-loan 비례보상 필드 엔드포인트 통합 검증

데모 시나리오2 실제 숫자(담보 3억/보험가액 5억/요구 5억)로 conditional 응답에
insured_value·effective_recovery·evidence가 실려 나가는 것과, InsuQ가 안 내려준
필드는 exclude_none으로 키가 생략되는 것을 함께 검증한다."
```

---

### Task 5: 문서 반영 — `A2A_DIAGRAMS.md` §②2.3 + InsuQ TASK-H08 신호

계약이 바뀌었는데 SSOT 다이어그램 문서가 그대로면, 8/24 세션이 정정했던 것과 같은 종류의 stale 서술이 다시 쌓인다.

**Files:**
- Modify: `C:\Users\ttogl\workspace\A2A_Q\A2A_DIAGRAMS.md` (§②2.3 assess-loan 절 + 홉별 요약표)

**Interfaces:**
- Consumes: Task 1의 계약 필드 집합, Task 4의 검증 결과
- Produces: 없음 (문서화 종결)

- [ ] **Step 1: §②2.3의 현재 서술을 읽는다**

Run: `cd /c/Users/ttogl/workspace/A2A_Q && grep -n "2.3" A2A_DIAGRAMS.md | head`
그다음 해당 절 전체를 읽어 `collateral_check` 필드를 열거한 곳과 홉별 요약표 위치를 확인한다.

- [ ] **Step 2: 계약 확장 사실을 §②2.3에 반영한다**

`collateral_check`가 2필드라고 적힌 서술을 5필드로 갱신하고, 절 하단에 아래 경고 블록을 추가한다.

```markdown
> ⚠️ **2026-08-29 계약 확장 — `evidence`를 "약관 인용"으로 표시하지 말 것.**
> `collateral_check`가 `coverage_amount`/`sufficient` 2필드에서
> `insured_value`·`effective_recovery`·`evidence`를 더한 5필드로 확장됐다
> (`docs/schemas/assess-loan.json`, FinAllQ `a2a_adapter` 반영 완료).
> 다만 `evidence`가 실어 나르는 값은 **InsuQ TASK-H08이 아직 미해결**이라
> 실제 약관 조항 인용이 아니라 **정책 레코드 요약 문자열**이다
> (`InsuQ_시나리오맵.html` §트랙4 표 참고). 파이프라인만 열어둔 상태이므로
> 데모 슬라이드·화면이 이 값을 "약관 조항 인용 첨부"로 소개하면 안 된다.
>
> 또한 필드 집합이 S13(`assess-used-equipment-loan`)과 같아졌지만
> **판정 규칙은 여전히 다르다** — S8은 `sufficient` 하나로만
> `approved`/`conditional`을 가르고, S13처럼 "비례보상 정보가 없으면 conditional"로
> 열화시키지 않는다.
```

- [ ] **Step 3: 문서 렌더 검증**

이 절에 mermaid를 새로 추가하지 않았다면 렌더 검증은 생략한다. 추가했다면 8/24 세션 방식대로 `mermaid.parse()`로 파싱 예외를 확인한다(육안 스크린샷만으로는 "Syntax error in text"를 놓친다).

- [ ] **Step 4: 커밋·푸시**

```bash
cd /c/Users/ttogl/workspace/A2A_Q
git status --short   # 다른 세션이 만든 미추적 파일과 안 섞이게 반드시 먼저 확인
git add A2A_DIAGRAMS.md
git commit -m "docs: A2A_DIAGRAMS §2.3에 S8 collateral_check 5필드 확장 반영

evidence가 InsuQ TASK-H08 미해결로 실제 약관 인용이 아니라는 경고와,
필드 집합이 S13과 같아져도 판정 규칙은 다르다는 점을 함께 못 박는다."
git push origin main
```

- [ ] **Step 5: InsuQ 쪽에 소비자 신호를 남긴다**

InsuQ TASK-H08은 "소비자 신호 대기 — FinAllQ가 이 필드를 실제로 쓰기 시작할 때 처리" 상태였다. 이 계획이 바로 그 신호이므로 InsuQ 레포 백로그에 기록한다.

Run: `cd /c/Users/ttogl/workspace/InsuQ && git status --short` 로 다른 세션 작업물과 섞이지 않는지 먼저 확인한 뒤, InsuQ 백로그 문서(`docs/07_BACKLOG.md` 또는 해당 레포의 백로그 파일 — 실제 경로를 먼저 `ls docs/`로 확인)의 TASK-H08 항목에 아래를 덧붙이고 **그 파일 하나만** 스테이징해 커밋한다.

```markdown
- 2026-08-29 — **소비자 신호 도착.** FinAllQ `a2a_adapter`가 `assess-loan`(S8) 응답의
  `collateral_check.evidence`로 이 필드를 실제로 전달하기 시작했다
  (A2A_Q `docs/schemas/assess-loan.json` 계약 확장). 현재 값이 정책 레코드 요약
  문자열이라 소비 측 문서에 "약관 인용으로 표시 금지" 경고를 달아둔 상태 —
  실제 조항 인용으로 교체되면 그 경고를 걷어낼 수 있다.
```

---

## Self-Review

**1. 스펙 커버리지**
- "S8 스키마에 `effective_recovery`·`insured_value`·`evidence` 추가" → Task 1(계약) · Task 2(모델) · Task 3(매핑) · Task 4(통합검증) ✅
- "비례보상·약관인용이 데모 나레이션과 맞물리게" → Task 5가 **맞물리지 않는다는 사실**(evidence가 아직 진짜 인용이 아님)을 명시적으로 문서화 ✅ — 이건 계획의 한계가 아니라 InsuQ 쪽 미해결 의존성이며, Task 5 Step 5가 그 해소를 촉발한다.

**2. 플레이스홀더 스캔**
- Task 4 Step 1의 monkeypatch 대상 이름(`a2a_adapter.main.apply_loan` 등)은 **실제 함수명을 확인하지 않고 추정한 것**이다. 실행자는 Step 1 전에 `tests/test_main.py` L457 부근 기존 테스트를 읽고 그 파일의 실제 관례에 맞춰야 한다 — 이 지시를 Task 4 Step 1 본문에 명시해 두었다. 그 외 TBD·"적절히 처리" 류 없음. ✅
- Task 5 Step 5의 InsuQ 백로그 경로는 `ls docs/`로 먼저 확인하라고 지시했다(A2A_Q 세션에서 InsuQ 레포 구조를 확정하지 않았으므로 추정 경로를 단정하지 않았다). ✅

**3. 타입 일관성**
- `insured_value`·`effective_recovery`: 계약 `number` / pydantic `float | None` / 매핑 `None` 기본 — 일관 ✅
- `evidence`: 계약 `array of string` / pydantic `list[str] | None` / 매핑 `.get("evidence")` — 일관 ✅
- 함수명 `build_assess_loan_collateral_check`가 Task 3·4에서 동일 ✅
- Task 4 Step 1 마지막 단언(`check["evidence"] == []`)은 의도적이다 — 빈 리스트는 `None`이 아니므로 `exclude_none`에 걸리지 않고 키가 남는다. Task 2 Step 1의 `"evidence" not in dumped`(값이 `None`인 경우)와 모순이 아니다. ✅
