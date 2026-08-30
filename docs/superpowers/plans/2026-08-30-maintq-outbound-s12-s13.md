# MaintQ A2A 발신 트리거 S12·S13 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** MaintQ가 FinAllQ의 `assess-used-equipment-loan`(S13)·`request-settlement`(S12)를 실제로 호출하게 만들어 발신 스킬을 3종 → 5종으로 늘린다. S12는 응답으로 MaintQ 자신의 처분 블로커를 푼다.

**Architecture:** 기존 발신 3종과 **완전히 같은 경로**를 탄다 — `routers/a2a.py` 엔드포인트 → `a2a/payloads.py` 빌더 → `a2a/client.py` 발신 → `a2a/trace.py` 기록. 새 인프라는 만들지 않는다. 유일하게 새로운 것은 S12의 응답 소비(`assets.lien_consent_ref` 쓰기) 하나이며, 이것은 별도 서비스 함수로 분리해 불변식을 테스트로 잠근다.

**Tech Stack:** Python 3.13 · FastAPI · pydantic · pytest · PostgreSQL(`backend/db.py::connect`)

## Global Constraints

- **설계 문서(SSOT):** `A2A_Q/docs/superpowers/specs/2026-08-30-maintq-outbound-s12-s13-design.md`
- **계약 SSOT:** `A2A_Q/docs/schemas/assess-used-equipment-loan.json` · `request-settlement.json`
- **레포는 MaintQ 하나뿐이다.** FinAllQ 수신부는 이미 구현·검증돼 있고 이번에 변경하지 않는다.
- **외부 API 실호출 0건.** 모든 테스트는 대역으로 검증한다(기존 관례).
- 🔴 **`lien_released: true`여도 결정을 자동 서명하지 않는다.** `assets.lien_consent_ref`만 쓰고 서명은 사람이 한다. MaintQ 불변식 "서명 없는 처분 확정 0건" · "BLOCKING 우회 처분 0건"을 A2A 경로로 우회하지 않는다.
- 🔴 **`lien_consent_ref`에 빈 문자열(`''`)을 절대 쓰지 않는다.** `seed.py` 검사 ⑱이 `has_lien=1 AND trim(lien_consent_ref)=''`를 데이터 불변식으로 금지한다 — 빈 문자열은 `is_null`이 False가 되어 **BLOCKING 룰을 조용히 미발화**시킨다("키 하나 빠뜨림으로 나는 최악의 오판").
- **값이 없으면 키를 생략한다.** 빈 문자열·0으로 채우지 않는다(D62 — NULL 컬럼은 키 자체가 없다).
- **`.get(k, default)` 함정 주의:** 키가 없을 때만 default를 쓰고 값이 `None`이면 그대로 돌려준다. 필수 문자열 필드는 `or ""`로 걸러야 한다 — `request-withdrawal`이 `error_code=None` 때문에 FinAllQ에서 400(`schema_validation_failed`)을 맞은 전례가 있다(`payloads.py` 주석).
- **테스트 실행 시 `DATABASE_URL`이 필요하다.** pytest 경로엔 `load_dotenv`가 없어 기본값 5432로 떨어지는데 컨테이너는 5434다.
- **⚠️ S12는 판정만 한다** — FinAllQ `decide_settlement()`는 DB 조회 0인 순수 함수라 `remaining_balance`는 산술 결과일 뿐 장부 반영 잔액이 아니다(`loan_id` 부재, TASK-195). MaintQ는 `lien_released`만 소비한다.

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `backend/a2a/payloads.py` | payload 빌더 2개 추가 | Modify |
| `backend/a2a/test_payloads.py` | 빌더 단위 테스트 | Modify |
| `backend/services/lien.py` | **신설** — `lien_consent_ref` 쓰기 + 불변식 | Create |
| `backend/services/test_lien.py` | **신설** — 불변식 테스트 | Create |
| `backend/routers/a2a.py` | 엔드포인트 2개 + 요청 모델 2개 | Modify |
| `backend/routers/test_a2a.py` | 엔드포인트 통합 테스트 | Modify |

**`lien.py`를 따로 두는 이유:** 라우터에 인라인하면 "자동 서명 안 함"·"빈 문자열 금지" 두 불변식이 HTTP 계층에 묻혀 테스트하기 어려워진다. 이 프로젝트에서 제일 조심해야 할 쓰기이므로 순수 함수로 분리해 DB만 놓고 검증한다.

---

### Task 1: S13 payload 빌더

**Files:**
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\a2a\payloads.py`
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\a2a\test_payloads.py`

**Interfaces:**
- Consumes: 기존 `get_finallq_company_id(db_path)` · `backend.db.connect`
- Produces: `build_assess_used_equipment_loan_payload(asset_id: str, loan_amount: float, request_chain_id: str, db_path: str | None = None) -> dict[str, Any]` — Task 2가 호출한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/a2a/test_payloads.py` 끝에 추가한다. 기존 파일의 픽스처·헬퍼 이름을 먼저 읽고 그 관례에 맞춘다(자산을 만드는 헬퍼가 이미 있으면 재사용한다).

```python
def test_assess_used_equipment_loan_payload_derives_fields_from_asset(tmp_db):
    """자산 하나에서 계약 4필드가 파생된다 — 호출자는 asset_id 와 금액만 준다."""
    from backend.a2a.payloads import build_assess_used_equipment_loan_payload

    p = build_assess_used_equipment_loan_payload(
        asset_id="AST-L3-CONV", loan_amount=5_000_000.0,
        request_chain_id="CHAIN-TEST-1", db_path=tmp_db,
    )

    assert p["loan_amount"] == 5_000_000.0
    assert p["request_chain_id"] == "CHAIN-TEST-1"
    assert p["collateral_building_id"] == "BLD-A"        # assets.building_id
    assert p["equipment_year"] == 2019                    # assets.acquired_at 의 연도
    assert isinstance(p["inspection_data"], dict)


def test_inspection_data_carries_ownership_checks(tmp_db):
    """계약이 'S18 verify_ownership 결과 참조 가능'이라 적었고 그게 ownership_checks 다."""
    from backend.a2a.payloads import build_assess_used_equipment_loan_payload

    p = build_assess_used_equipment_loan_payload(
        asset_id="AST-L3-CONV", loan_amount=1.0,
        request_chain_id="C", db_path=tmp_db,
    )
    checks = p["inspection_data"]["ownership_checks"]

    assert isinstance(checks, list) and checks
    assert set(checks[0]) == {"category", "check_item", "state"}
    assert checks[0]["state"] in ("VERIFIED", "UNVERIFIED")


def test_equipment_year_is_labelled_as_acquisition_year(tmp_db):
    """MaintQ 는 제조연도를 저장하지 않는다 — 취득연도를 보내되 그 사실을 함께 보낸다.

    계약의 equipment_year 는 '제조연도, 잔존연수 산정용'이다. acquired_at 은 취득일이라
    중고 설비에선 둘이 다르다. 값을 지어내지 않고, 무엇을 보냈는지 수신부가 알게 한다.
    """
    from backend.a2a.payloads import build_assess_used_equipment_loan_payload

    p = build_assess_used_equipment_loan_payload(
        asset_id="AST-L3-CONV", loan_amount=1.0,
        request_chain_id="C", db_path=tmp_db,
    )

    assert p["inspection_data"]["equipment_year_basis"] == "acquired_at"


def test_missing_inspection_dates_are_omitted_not_blanked(tmp_db):
    """NULL 은 키 자체를 생략한다 — 빈 문자열·0 으로 채우지 않는다 (D62)."""
    from backend.a2a.payloads import build_assess_used_equipment_loan_payload

    # last_inspection_date 가 NULL 인 자산을 쓴다 (픽스처에서 준비)
    p = build_assess_used_equipment_loan_payload(
        asset_id="AST-NO-INSPECTION", loan_amount=1.0,
        request_chain_id="C", db_path=tmp_db,
    )

    assert "last_inspection_date" not in p["inspection_data"]


def test_unknown_asset_raises(tmp_db):
    """없는 자산으로 payload 를 만들지 않는다 — 조용히 빈 값을 보내면 수신부가 400 을 낸다."""
    from backend.a2a.payloads import build_assess_used_equipment_loan_payload

    with pytest.raises(ValueError, match="AST-NOPE"):
        build_assess_used_equipment_loan_payload(
            asset_id="AST-NOPE", loan_amount=1.0, request_chain_id="C", db_path=tmp_db,
        )
```

**픽스처 준비:** `tmp_db`에 `AST-L3-CONV`(`building_id='BLD-A'`, `acquired_at='2019-05-01'`, `last_inspection_date` 있음)와 `AST-NO-INSPECTION`(`last_inspection_date IS NULL`)을 넣고, `AST-L3-CONV`에 `ownership_checks` 1행 이상을 넣는다. 기존 `test_payloads.py`가 쓰는 DB 픽스처 방식을 그대로 따른다.

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && DATABASE_URL=<컨테이너 DSN> python -m pytest backend/a2a/test_payloads.py -v -k used_equipment`

Expected: FAIL — `ImportError: cannot import name 'build_assess_used_equipment_loan_payload'`

- [ ] **Step 3: 빌더를 구현한다**

`payloads.py`의 `build_assess_loan_payload()` **바로 아래**에 추가한다.

```python
def build_assess_used_equipment_loan_payload(
    asset_id: str,
    loan_amount: float,
    request_chain_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """FinAllQ assess-used-equipment-loan 스킬(S13, 중고 설비 담보 대출 심사) payload.

    S8(`build_assess_loan_payload`)과 달리 **자산 하나에서 4필드를 파생한다** —
    호출자는 `asset_id` 와 `loan_amount` 만 준다. `build_request_withdrawal_payload`
    가 `supplier_id` 로 `suppliers` 를 조회하는 것과 같은 관례다.

    ⚠️ `equipment_year`: 계약은 **제조연도**를 요구하지만 MaintQ 는 그것을 저장하지
    않는다. 가장 가까운 값인 `acquired_at`(취득일)의 연도를 보내되, 무엇을 보냈는지
    `inspection_data.equipment_year_basis` 로 함께 알린다 — 지어내지 않고, 수신부가
    잔존연수를 재산정할 수 있게 한다.
    """
    with connect(db_path) as con:
        a = con.execute(
            "SELECT building_id, acquired_at, last_inspection_date,"
            " inspection_valid_until, safety_inspection_target"
            " FROM assets WHERE asset_id = ?",
            (asset_id,),
        ).fetchone()
        if a is None:
            raise ValueError(f"알 수 없는 asset_id: {asset_id}")
        checks = con.execute(
            "SELECT category, check_item, state FROM ownership_checks"
            " WHERE asset_id = ? ORDER BY check_id",
            (asset_id,),
        ).fetchall()

    # 계약이 "S18 verify_ownership 결과 참조 가능"이라 적은 자리 — ownership_checks 가 그것이다.
    inspection: dict[str, Any] = {
        "equipment_year_basis": "acquired_at",
        "ownership_checks": [
            {"category": c["category"], "check_item": c["check_item"], "state": c["state"]}
            for c in checks
        ],
    }
    # NULL 은 키 자체를 생략한다 (D62) — 빈 문자열·0 으로 채우면 "모름"이 "없음"으로 둔갑한다.
    for key in ("last_inspection_date", "inspection_valid_until"):
        if a[key] is not None:
            inspection[key] = str(a[key])
    if a["safety_inspection_target"] is not None:
        inspection["safety_inspection_target"] = bool(a["safety_inspection_target"])

    acquired = a["acquired_at"]
    return {
        "requester": {"finallq_company_id": get_finallq_company_id(db_path) or ""},
        "request_chain_id": request_chain_id,
        "loan_amount": loan_amount,
        "collateral_building_id": a["building_id"] or "",
        "equipment_year": int(str(acquired)[:4]) if acquired else 0,
        "inspection_data": inspection,
    }
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && DATABASE_URL=<DSN> python -m pytest backend/a2a/test_payloads.py -v`

Expected: PASS — 신규 5건 + 기존 전부.

- [ ] **Step 5: 커밋**

```bash
cd /c/Users/ttogl/workspace/MaintQ
git status --short   # 다른 세션 작업물과 섞이지 않는지 먼저 확인
git add backend/a2a/payloads.py backend/a2a/test_payloads.py
git commit -m "feat(a2a): assess-used-equipment-loan payload 빌더 (S13)

자산 하나에서 계약 4필드를 파생한다 — 호출자는 asset_id 와 금액만 준다.

equipment_year 는 계약상 제조연도인데 MaintQ 는 그걸 저장하지 않는다.
acquired_at 의 연도를 보내되 inspection_data.equipment_year_basis 로
그것이 취득연도임을 함께 알린다 — 값을 지어내지 않고 수신부가
잔존연수를 재산정할 수 있게 한다."
```

---

### Task 2: S13 엔드포인트

**Files:**
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\routers\a2a.py`
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\routers\test_a2a.py`

**Interfaces:**
- Consumes: Task 1의 `build_assess_used_equipment_loan_payload(asset_id, loan_amount, request_chain_id, db_path=None)`
- Produces: `POST /api/a2a/assess-used-equipment-loan` — 요청 `{asset_id, loan_amount, session_id?, request_chain_id?}`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/routers/test_a2a.py` 끝에 추가한다. 기존 `assess-loan` 테스트가 `call_skill`을 어떻게 대역으로 바꾸는지 먼저 읽고 **같은 방식**을 쓴다.

```python
def test_assess_used_equipment_loan_endpoint_returns_partner_response(client, monkeypatch):
    captured = {}

    async def fake_call_skill(**kwargs):
        captured.update(kwargs)
        return {"status": "ok", "decision": "conditional", "appraised_value": 4_000_000}

    monkeypatch.setattr("backend.routers.a2a.call_skill", fake_call_skill)

    res = client.post("/api/a2a/assess-used-equipment-loan",
                      json={"asset_id": "AST-L3-CONV", "loan_amount": 5_000_000})

    assert res.status_code == 200
    body = res.json()
    assert body["decision"] == "conditional"
    assert body["request_chain_id"]                      # 파트너가 echo 안 해도 채워진다
    assert captured["skill_id"] == "assess-used-equipment-loan"
    assert captured["partner"] == "finallq"


def test_assess_used_equipment_loan_unknown_asset_is_400(client, monkeypatch):
    """빌더가 ValueError 를 던지면 500 이 아니라 400 으로 나간다."""
    async def fake_call_skill(**kwargs):
        raise AssertionError("없는 자산인데 발신하면 안 된다")

    monkeypatch.setattr("backend.routers.a2a.call_skill", fake_call_skill)

    res = client.post("/api/a2a/assess-used-equipment-loan",
                      json={"asset_id": "AST-NOPE", "loan_amount": 1})

    assert res.status_code == 400
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && DATABASE_URL=<DSN> python -m pytest backend/routers/test_a2a.py -v -k used_equipment`

Expected: FAIL — 404 (라우트 없음).

- [ ] **Step 3: 요청 모델과 엔드포인트를 추가한다**

`routers/a2a.py` 임포트에 빌더를 추가한다.

```python
from backend.a2a.payloads import (
    build_assess_loan_payload,
    build_assess_used_equipment_loan_payload,
    build_lookup_clause_payload,
)
```

`AssessLoanRequest` 클래스 **바로 아래**에 모델을 추가한다.

```python
class AssessUsedEquipmentLoanRequest(BaseModel):
    asset_id: str = Field(..., min_length=1, description="담보로 잡을 MaintQ 자산 ID")
    loan_amount: float = Field(..., gt=0, description="중고 설비 담보 대출 희망 금액")
    session_id: str | None = Field(None, description="MaintQ 세션 ID")
    request_chain_id: str | None = Field(None, description="멀티홉 추적용 체인 ID")
```

`assess_loan_endpoint` **바로 아래**에 엔드포인트를 추가한다. 예외 처리 4종은 `assess-loan`과 동일한 구조를 그대로 따른다.

```python
@router.post("/assess-used-equipment-loan")
async def assess_used_equipment_loan_endpoint(
    req: AssessUsedEquipmentLoanRequest,
) -> dict[str, Any]:
    """FinAllQ assess-used-equipment-loan 스킬로 중고 설비 담보 대출 심사를 요청한다(S13)."""
    base_url = os.environ.get("MAINTQ_A2A_FINALLQ_BASE_URL") or "http://localhost:9101"
    chain_id = req.request_chain_id or f"CHAIN-UELOAN-{uuid.uuid4().hex[:8]}"

    try:
        payload = build_assess_used_equipment_loan_payload(
            asset_id=req.asset_id,
            loan_amount=req.loan_amount,
            request_chain_id=chain_id,
        )
    except ValueError as exc:
        # 없는 자산이다 — 발신하지 않는다. 조용히 빈 값을 보내면 수신부가 400 을 낸다.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await _dispatch(
        skill_id="assess-used-equipment-loan",
        payload=payload,
        chain_id=chain_id,
        session_id=req.session_id or "",
        base_url=base_url,
        partner_label="FinAllQ",
    )
```

**`_dispatch` 헬퍼를 신설한다.** `assess-loan` 엔드포인트의 `try/except` 4종이 이미 `lookup-clause`와 거의 같은 코드이고, 여기서 두 번 더 복제하면 같은 블록이 4벌이 된다. `router = APIRouter(...)` 정의 아래에 추가한다.

```python
async def _dispatch(
    *,
    skill_id: str,
    payload: dict[str, Any],
    chain_id: str,
    session_id: str,
    base_url: str,
    partner_label: str,
    partner: str = "finallq",
) -> dict[str, Any]:
    """A2A 발신 + trace 기록 + 오류 매핑. 스킬마다 같은 블록을 복제하지 않는다.

    상태코드 매핑은 기존 lookup-clause·assess-loan 과 동일하다:
    timeout→504 · unavailable→502 · client error→그쪽 status(없으면 400).
    """
    def _trace(status: str, response: dict[str, Any]) -> None:
        record_a2a_trace(
            session_id=session_id,
            skill_id=skill_id,
            request_payload=payload,
            response_payload=response,
            request_chain_id=chain_id,
            status=status,
        )

    try:
        res = await call_skill(
            partner=partner, skill_id=skill_id, payload=payload,
            request_chain_id=chain_id, base_url=base_url,
        )
        res["request_chain_id"] = chain_id  # 파트너가 echo 안 해도 상관관계 키를 보장한다
        _trace("ok", res)
        return res
    except A2ATimeoutError as exc:
        _trace("timeout", {"error": str(exc)})
        raise HTTPException(status_code=504, detail=f"{partner_label} A2A adapter timeout") from exc
    except A2AUpstreamUnavailableError as exc:
        _trace("unavailable", {"error": str(exc)})
        raise HTTPException(status_code=502, detail=f"{partner_label} A2A adapter unavailable") from exc
    except A2AClientError as exc:
        _trace("error", {"error": str(exc)})
        raise HTTPException(status_code=exc.status_code or 400, detail=exc.detail or str(exc)) from exc
```

⚠️ **기존 두 엔드포인트를 `_dispatch`로 바꾸지 않는다.** 이번 목표는 신규 2종이고, 동작하는 코드를 함께 건드리면 회귀 위험만 커진다. 기존 것 정리는 별건이다.

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && DATABASE_URL=<DSN> python -m pytest backend/routers/test_a2a.py -v`

Expected: PASS — 신규 2건 + 기존 전부(기존 엔드포인트는 안 건드렸으므로 그대로 통과해야 한다).

- [ ] **Step 5: 커밋**

```bash
cd /c/Users/ttogl/workspace/MaintQ
git add backend/routers/a2a.py backend/routers/test_a2a.py
git commit -m "feat(a2a): POST /api/a2a/assess-used-equipment-loan (S13)

발신+trace+오류매핑을 _dispatch 헬퍼로 분리했다 — 같은 블록이 4벌이
되는 걸 막는다. 기존 lookup-clause·assess-loan 은 건드리지 않았다.

없는 자산이면 발신 전에 400 으로 끊는다."
```

---

### Task 3: S12 payload 빌더

**Files:**
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\a2a\payloads.py`
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\a2a\test_payloads.py`

**Interfaces:**
- Consumes: 기존 `get_finallq_company_id` · `connect`
- Produces: `build_request_settlement_payload(decision_id: str, sale_amount: float, outstanding_loan: float, approved_by: str, prepayment_fee: float | None, request_chain_id: str, db_path: str | None = None) -> dict[str, Any]` — Task 5가 호출한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_request_settlement_payload_reads_lien_creditor_via_decision(tmp_db):
    """decision_id → decisions.asset_id → assets.lien_creditor 로 타고 간다."""
    from backend.a2a.payloads import build_request_settlement_payload

    p = build_request_settlement_payload(
        decision_id="DEC-0001", sale_amount=8_000_000.0, outstanding_loan=3_000_000.0,
        approved_by="U-FIN-01", prepayment_fee=None,
        request_chain_id="CHAIN-SET-1", db_path=tmp_db,
    )

    assert p["decision_id"] == "DEC-0001"
    assert p["lien_creditor"] == "한빛은행 여신부"
    assert p["sale_amount"] == 8_000_000.0
    assert p["outstanding_loan"] == 3_000_000.0
    assert p["approved_by"] == "U-FIN-01"


def test_prepayment_fee_omitted_when_none(tmp_db):
    """계약상 optional 이다 — None 이면 키를 생략한다 (0 으로 채우지 않는다)."""
    from backend.a2a.payloads import build_request_settlement_payload

    p = build_request_settlement_payload(
        decision_id="DEC-0001", sale_amount=1.0, outstanding_loan=1.0,
        approved_by="U", prepayment_fee=None, request_chain_id="C", db_path=tmp_db,
    )

    assert "prepayment_fee" not in p


def test_prepayment_fee_included_when_zero(tmp_db):
    """0 은 '없음'이 아니라 '수수료 0원'이라는 사실이다 — 생략하지 않는다."""
    from backend.a2a.payloads import build_request_settlement_payload

    p = build_request_settlement_payload(
        decision_id="DEC-0001", sale_amount=1.0, outstanding_loan=1.0,
        approved_by="U", prepayment_fee=0.0, request_chain_id="C", db_path=tmp_db,
    )

    assert p["prepayment_fee"] == 0.0


def test_draft_decision_is_accepted(tmp_db):
    """decision_id 는 **미서명 draft** 를 가리킨다 — 그것이 정상 경로다.

    담보 자산은 LIEN-CONSENT(BLOCKING)로 서명이 막혀 있고, 그 담보를 푸는 수단이
    이 스킬 자신이다. 서명 후 호출은 구조적으로 불가능하다
    (A2A_Q docs/schemas/request-settlement.json 의 decision_id 설명).
    """
    from backend.a2a.payloads import build_request_settlement_payload

    p = build_request_settlement_payload(   # DEC-0001 은 state='draft', signed_at=NULL
        decision_id="DEC-0001", sale_amount=1.0, outstanding_loan=1.0,
        approved_by="U", prepayment_fee=None, request_chain_id="C", db_path=tmp_db,
    )

    assert p["decision_id"] == "DEC-0001"


def test_unknown_decision_raises(tmp_db):
    from backend.a2a.payloads import build_request_settlement_payload

    with pytest.raises(ValueError, match="DEC-NOPE"):
        build_request_settlement_payload(
            decision_id="DEC-NOPE", sale_amount=1.0, outstanding_loan=1.0,
            approved_by="U", prepayment_fee=None, request_chain_id="C", db_path=tmp_db,
        )


def test_asset_without_lien_raises(tmp_db):
    """담보가 없는 자산에 정산을 요청하지 않는다 — lien_creditor 가 빈 채로 나가면
    수신부가 400 을 낸다(계약 필수 필드)."""
    from backend.a2a.payloads import build_request_settlement_payload

    with pytest.raises(ValueError, match="담보"):
        build_request_settlement_payload(   # DEC-NOLIEN 의 자산은 has_lien=0
            decision_id="DEC-NOLIEN", sale_amount=1.0, outstanding_loan=1.0,
            approved_by="U", prepayment_fee=None, request_chain_id="C", db_path=tmp_db,
        )
```

**픽스처 준비:** `DEC-0001`(`state='draft'`, `signed_at=NULL`, `asset_id`가 `has_lien=1` · `lien_creditor='한빛은행 여신부'` · `lien_consent_ref IS NULL`인 자산)과 `DEC-NOLIEN`(`has_lien=0`인 자산)을 넣는다. `decisions`는 `evidence_bundle`·`bundle_hash`·`verdict_at_signing`이 `NOT NULL`이므로 더미 값을 채운다.

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && DATABASE_URL=<DSN> python -m pytest backend/a2a/test_payloads.py -v -k settlement`

Expected: FAIL — `ImportError: cannot import name 'build_request_settlement_payload'`

- [ ] **Step 3: 빌더를 구현한다**

`payloads.py` 끝에 추가한다.

```python
def build_request_settlement_payload(
    decision_id: str,
    sale_amount: float,
    outstanding_loan: float,
    approved_by: str,
    prepayment_fee: float | None,
    request_chain_id: str,
    db_path: str | None = None,
) -> dict[str, Any]:
    """FinAllQ request-settlement 스킬(S12, 매각대금 정산·근저당 말소) payload.

    **`decision_id` 는 미서명 draft 결정을 가리킨다 — 그것이 정상 경로다.**
    담보 자산은 LIEN-CONSENT(BLOCKING)로 서명이 막혀 있고 그 담보를 푸는 수단이
    이 스킬 자신이므로(같은 룰의 resolve_options[1] "대출 상환 후 근저당 말소"),
    정산 요청이 서명보다 먼저 일어나야 한다. 계약도 이를 명시한다.

    `approved_by` 는 **정산 요청 승인자**이지 처분 서명자가 아니다 — draft 결정은
    `reviewed_by` 가 NULL 이라 거기서 읽으면 항상 빈다. 호출자가 준다.
    """
    with connect(db_path) as con:
        row = con.execute(
            "SELECT a.has_lien, a.lien_creditor FROM decisions d"
            " JOIN assets a ON a.asset_id = d.asset_id"
            " WHERE d.decision_id = ?",
            (decision_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"알 수 없는 decision_id: {decision_id}")
    if not row["has_lien"] or not row["lien_creditor"]:
        raise ValueError(
            f"{decision_id} 의 자산에 담보가 없다 — 정산 요청 대상이 아니다."
        )

    payload: dict[str, Any] = {
        "requester": {"finallq_company_id": get_finallq_company_id(db_path) or ""},
        "request_chain_id": request_chain_id,
        "decision_id": decision_id,
        "sale_amount": sale_amount,
        "lien_creditor": row["lien_creditor"],
        "outstanding_loan": outstanding_loan,
        "approved_by": approved_by,
    }
    # optional — None 이면 키를 생략한다. 단 0.0 은 "수수료 0원"이라는 사실이므로 싣는다.
    if prepayment_fee is not None:
        payload["prepayment_fee"] = prepayment_fee
    return payload
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && DATABASE_URL=<DSN> python -m pytest backend/a2a/test_payloads.py -v`

Expected: PASS — 신규 6건 + Task 1의 5건 + 기존 전부.

- [ ] **Step 5: 커밋**

```bash
cd /c/Users/ttogl/workspace/MaintQ
git add backend/a2a/payloads.py backend/a2a/test_payloads.py
git commit -m "feat(a2a): request-settlement payload 빌더 (S12)

decision_id 는 미서명 draft 를 가리킨다 — 담보를 푸는 수단이 이 스킬
자신이라 정산 요청이 서명보다 먼저 일어나야 한다(계약에 명시됨).

approved_by 는 정산 요청 승인자다. draft 결정은 reviewed_by 가 NULL
이라 거기서 읽으면 항상 빈다.

담보 없는 자산은 발신 전에 거부한다 — lien_creditor 가 빈 채로 나가면
수신부가 400 을 낸다."
```

---

### Task 4: `resolve_lien_consent()` — 불변식 2개를 잠근다

**이 태스크가 이 계획에서 제일 위험하다.** MaintQ 상태를 바꾸는 유일한 지점이고, 잘못 쓰면 "담보 있는 자산을 동의서 없이 처분 가능"이라는 최악의 오판이 생긴다.

**Files:**
- Create: `C:\Users\ttogl\workspace\MaintQ\backend\services\lien.py`
- Create: `C:\Users\ttogl\workspace\MaintQ\backend\services\test_lien.py`

**Interfaces:**
- Consumes: `backend.db.connect`
- Produces: `resolve_lien_consent(decision_id: str, settlement_ref: str, db_path: str | None = None) -> bool` — 실제로 갱신했으면 `True`. Task 5가 호출한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/services/test_lien.py` 를 새로 만든다.

```python
# -*- coding: utf-8 -*-
"""LIEN-CONSENT 해소 — 이 레포에서 제일 조심해야 할 쓰기다.

`assets.lien_consent_ref` 는 LIEN-CONSENT 룰(BLOCKING)이 읽는 유일한 필드다
(`data/rules/rules/LIEN-CONSENT.json` 의 trigger: has_lien eq true AND
lien_consent_ref is_null). 여기에 잘못 쓰면 담보 있는 자산의 처분 차단이 풀린다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.services.lien import resolve_lien_consent  # noqa: E402


def test_writes_reference_and_returns_true(tmp_db, fetch_asset):
    changed = resolve_lien_consent("DEC-0001", "A2A-SETTLE-CHAIN-1", db_path=tmp_db)

    assert changed is True
    assert fetch_asset("AST-L3-CONV")["lien_consent_ref"] == "A2A-SETTLE-CHAIN-1"


def test_never_writes_empty_string(tmp_db, fetch_asset):
    """🔴 `''` 는 is_null 을 False 로 만들어 BLOCKING 룰을 **조용히 미발화**시킨다.

    seed.py 검사 ⑱ 이 has_lien=1 AND trim(lien_consent_ref)='' 를 데이터 불변식으로
    금지한다. 빈 참조가 오면 쓰지 않고 거부한다.
    """
    for bad in ("", "   "):
        with pytest.raises(ValueError, match="빈 참조"):
            resolve_lien_consent("DEC-0001", bad, db_path=tmp_db)

    assert fetch_asset("AST-L3-CONV")["lien_consent_ref"] is None


def test_does_not_sign_the_decision(tmp_db, fetch_decision):
    """🔴 담보만 푼다 — 서명은 사람이 한다.

    "서명 없는 처분 확정 0건" 불변식을 A2A 경로로 우회하지 않는다. assess-loan 이
    conditional 판정을 받아도 대출을 자동 실행하지 않는 것과 같은 태도다.
    """
    resolve_lien_consent("DEC-0001", "A2A-SETTLE-1", db_path=tmp_db)

    d = fetch_decision("DEC-0001")
    assert d["state"] == "draft"
    assert d["signed_at"] is None
    assert d["reviewed_by"] is None
    assert d["override"] in (0, False)


def test_unknown_decision_raises(tmp_db):
    with pytest.raises(ValueError, match="DEC-NOPE"):
        resolve_lien_consent("DEC-NOPE", "REF", db_path=tmp_db)


def test_already_resolved_is_not_overwritten(tmp_db, fetch_asset):
    """이미 동의서가 있으면 덮어쓰지 않는다 — 기존 근거를 A2A 참조로 지우면 안 된다."""
    resolve_lien_consent("DEC-0001", "FIRST-REF", db_path=tmp_db)

    changed = resolve_lien_consent("DEC-0001", "SECOND-REF", db_path=tmp_db)

    assert changed is False
    assert fetch_asset("AST-L3-CONV")["lien_consent_ref"] == "FIRST-REF"
```

**픽스처:** `tmp_db`는 Task 3과 같은 데이터. `fetch_asset(asset_id)`·`fetch_decision(decision_id)`는 해당 행을 dict로 돌려주는 헬퍼다 — 같은 파일 안에 `@pytest.fixture`로 둔다.

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && DATABASE_URL=<DSN> python -m pytest backend/services/test_lien.py -v`

Expected: FAIL — `ModuleNotFoundError: No module named 'backend.services.lien'`

- [ ] **Step 3: 구현한다**

`backend/services/lien.py` 를 새로 만든다.

```python
# -*- coding: utf-8 -*-
"""LIEN-CONSENT 해소 — `assets.lien_consent_ref` 쓰기.

**왜 이 파일이 따로 있는가:** 라우터에 인라인하면 아래 두 불변식이 HTTP 계층에 묻혀
테스트하기 어려워진다. 이 레포에서 제일 조심해야 할 쓰기이므로 순수 함수로 분리한다.

**왜 `flags` 가 아니라 `assets` 인가:** LIEN-CONSENT 룰이 읽는 필드는
`lien_consent_ref` 하나다(`data/rules/rules/LIEN-CONSENT.json` —
trigger: `has_lien eq true` AND `lien_consent_ref is_null`). `flags` 테이블은 해소
라이프사이클이 설계돼 있으나 쓰기 경로가 없어 0행이고 룰 평가에 관여하지 않는다 —
거기 쓰는 것은 해소가 아니다.
"""

from __future__ import annotations

from backend.db import connect


def resolve_lien_consent(
    decision_id: str, settlement_ref: str, db_path: str | None = None
) -> bool:
    """FinAllQ 정산 판정으로 근저당이 말소됐음을 기록한다. 갱신했으면 True.

    LIEN-CONSENT.resolve_options[1] "대출 상환 후 근저당 말소"의 자동화다.

    🔴 **결정을 서명하지 않는다.** 담보만 풀고 서명은 사람이 한다 —
    "서명 없는 처분 확정 0건" 불변식을 A2A 경로로 우회하지 않는다.

    🔴 **빈 참조를 쓰지 않는다.** `''` 는 `is_null` 을 False 로 만들어 BLOCKING 룰을
    조용히 미발화시킨다(seed.py 검사 ⑱). 규약은 `''`="확인된 해당 없음" /
    `NULL`="모름" 이고, A2A 정산은 둘 중 어느 것도 아니다.
    """
    ref = (settlement_ref or "").strip()
    if not ref:
        raise ValueError(
            "빈 참조로 LIEN-CONSENT 를 해소할 수 없다 — 빈 문자열은 BLOCKING 룰을 "
            "조용히 미발화시킨다(seed.py 검사 ⑱)."
        )

    with connect(db_path) as con:
        row = con.execute(
            "SELECT d.asset_id, a.lien_consent_ref FROM decisions d"
            " JOIN assets a ON a.asset_id = d.asset_id"
            " WHERE d.decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"알 수 없는 decision_id: {decision_id}")
        if row["lien_consent_ref"] is not None:
            # 이미 근거가 있다 — A2A 참조로 덮어쓰면 기존 동의서 출처가 사라진다.
            return False

        con.execute(
            "UPDATE assets SET lien_consent_ref = ? WHERE asset_id = ?",
            (ref, row["asset_id"]),
        )
        con.commit()
    return True
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && DATABASE_URL=<DSN> python -m pytest backend/services/test_lien.py -v`

Expected: PASS — 5 passed.

- [ ] **Step 5: 데이터 불변식 검사가 여전히 통과하는지 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && uv run python data/seed.py --with-error-codes`

Expected: 검사 ⑱(담보 자산 동의서 표기 규약)을 포함해 전부 통과. ⛔ `--today` 를 붙이지 않는다(검사 ⑤가 위양성 FAIL 한다). 재시드 후 `SELECT count(*) FROM error_codes` 가 **65** 인지 확인한다.

- [ ] **Step 6: 커밋**

```bash
cd /c/Users/ttogl/workspace/MaintQ
git add backend/services/lien.py backend/services/test_lien.py
git commit -m "feat(lien): resolve_lien_consent — 정산 판정으로 근저당 말소를 기록

LIEN-CONSENT.resolve_options[1] 의 자동화다. 룰이 읽는 필드가
assets.lien_consent_ref 하나이므로 flags 가 아니라 여기에 쓴다.

불변식 2개를 테스트로 잠갔다:
- 결정을 서명하지 않는다 (서명 없는 처분 확정 0건)
- 빈 참조를 쓰지 않는다 (빈 문자열은 BLOCKING 룰을 조용히 미발화시킨다)

이미 동의서가 있으면 덮어쓰지 않는다 — 기존 근거 출처를 지우지 않는다."
```

---

### Task 5: S12 엔드포인트 — 발신 + 응답 소비

**Files:**
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\routers\a2a.py`
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\routers\test_a2a.py`

**Interfaces:**
- Consumes: Task 3의 `build_request_settlement_payload(...)` · Task 4의 `resolve_lien_consent(decision_id, settlement_ref, db_path=None) -> bool` · Task 2의 `_dispatch(...)`
- Produces: `POST /api/a2a/request-settlement`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def _fake_settlement(lien_released: bool):
    async def fake_call_skill(**kwargs):
        return {"status": "ok", "action": "repay",
                "lien_released": lien_released, "remaining_balance": 5_000_000}
    return fake_call_skill


def test_settlement_released_writes_lien_consent_ref(client, monkeypatch, fetch_asset):
    monkeypatch.setattr("backend.routers.a2a.call_skill", _fake_settlement(True))

    res = client.post("/api/a2a/request-settlement", json={
        "decision_id": "DEC-0001", "sale_amount": 8_000_000,
        "outstanding_loan": 3_000_000, "approved_by": "U-FIN-01"})

    assert res.status_code == 200
    ref = fetch_asset("AST-L3-CONV")["lien_consent_ref"]
    assert ref                      # 비어 있지 않다
    assert ref.strip() == ref       # 공백만 있는 값도 아니다


def test_settlement_not_released_writes_nothing(client, monkeypatch, fetch_asset):
    """음성 축 — lien_released=false 면 담보는 그대로 남는다."""
    monkeypatch.setattr("backend.routers.a2a.call_skill", _fake_settlement(False))

    res = client.post("/api/a2a/request-settlement", json={
        "decision_id": "DEC-0001", "sale_amount": 1, "outstanding_loan": 999_999_999,
        "approved_by": "U"})

    assert res.status_code == 200
    assert fetch_asset("AST-L3-CONV")["lien_consent_ref"] is None


def test_settlement_never_signs_the_decision(client, monkeypatch, fetch_decision):
    """🔴 lien_released=true 여도 결정은 draft 그대로다 — 서명은 사람이 한다."""
    monkeypatch.setattr("backend.routers.a2a.call_skill", _fake_settlement(True))

    client.post("/api/a2a/request-settlement", json={
        "decision_id": "DEC-0001", "sale_amount": 8_000_000,
        "outstanding_loan": 3_000_000, "approved_by": "U-FIN-01"})

    d = fetch_decision("DEC-0001")
    assert d["state"] == "draft" and d["signed_at"] is None


def test_upstream_failure_leaves_state_unchanged(client, monkeypatch, fetch_asset):
    """상대가 죽어도 MaintQ 상태는 안 바뀐다."""
    from backend.a2a.client import A2AUpstreamUnavailableError

    async def boom(**kwargs):
        raise A2AUpstreamUnavailableError("down")

    monkeypatch.setattr("backend.routers.a2a.call_skill", boom)

    res = client.post("/api/a2a/request-settlement", json={
        "decision_id": "DEC-0001", "sale_amount": 1, "outstanding_loan": 1,
        "approved_by": "U"})

    assert res.status_code == 502
    assert fetch_asset("AST-L3-CONV")["lien_consent_ref"] is None


def test_settlement_on_asset_without_lien_is_400(client, monkeypatch):
    async def fake(**kwargs):
        raise AssertionError("담보 없는 자산인데 발신하면 안 된다")

    monkeypatch.setattr("backend.routers.a2a.call_skill", fake)

    res = client.post("/api/a2a/request-settlement", json={
        "decision_id": "DEC-NOLIEN", "sale_amount": 1, "outstanding_loan": 1,
        "approved_by": "U"})

    assert res.status_code == 400
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && DATABASE_URL=<DSN> python -m pytest backend/routers/test_a2a.py -v -k settlement`

Expected: FAIL — 404 (라우트 없음).

- [ ] **Step 3: 요청 모델과 엔드포인트를 추가한다**

임포트를 보강한다.

```python
from backend.a2a.payloads import (
    build_assess_loan_payload,
    build_assess_used_equipment_loan_payload,
    build_lookup_clause_payload,
    build_request_settlement_payload,
)
from backend.services.lien import resolve_lien_consent
```

모델을 추가한다.

```python
class RequestSettlementRequest(BaseModel):
    decision_id: str = Field(..., min_length=1, description="처분 결정 ID(미서명 draft 여도 된다)")
    sale_amount: float = Field(..., gt=0, description="설비 매각 금액")
    outstanding_loan: float = Field(..., ge=0, description="잔여 대출 원금")
    approved_by: str = Field(..., min_length=1, description="정산 요청 승인자(처분 서명자가 아니다)")
    prepayment_fee: float | None = Field(None, ge=0, description="중도상환 수수료(선택)")
    session_id: str | None = Field(None, description="MaintQ 세션 ID")
    request_chain_id: str | None = Field(None, description="멀티홉 추적용 체인 ID")
```

엔드포인트를 추가한다.

```python
@router.post("/request-settlement")
async def request_settlement_endpoint(req: RequestSettlementRequest) -> dict[str, Any]:
    """FinAllQ request-settlement 로 매각대금 정산 판정을 요청한다(S12).

    **MaintQ 발신 스킬 중 유일하게 응답이 MaintQ 상태를 바꾼다** —
    `lien_released: true` 면 LIEN-CONSENT 를 해소한다. 단 **서명하지는 않는다**.

    ⚠️ 응답의 `remaining_balance` 는 FinAllQ 장부에 반영된 잔액이 아니라 산술
    결과다(`decide_settlement` 는 DB 조회 0인 순수 함수, `loan_id` 부재). trace 에만 남긴다.
    """
    base_url = os.environ.get("MAINTQ_A2A_FINALLQ_BASE_URL") or "http://localhost:9101"
    chain_id = req.request_chain_id or f"CHAIN-SETTLE-{uuid.uuid4().hex[:8]}"

    try:
        payload = build_request_settlement_payload(
            decision_id=req.decision_id,
            sale_amount=req.sale_amount,
            outstanding_loan=req.outstanding_loan,
            approved_by=req.approved_by,
            prepayment_fee=req.prepayment_fee,
            request_chain_id=chain_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    res = await _dispatch(
        skill_id="request-settlement",
        payload=payload,
        chain_id=chain_id,
        session_id=req.session_id or "",
        base_url=base_url,
        partner_label="FinAllQ",
    )

    # 응답 소비 — 담보 해소는 lien_released 가 명시적으로 true 일 때만 한다.
    # 키가 없거나 다른 값이면 아무것도 쓰지 않는다(조용한 해소 금지).
    if res.get("lien_released") is True:
        resolved = resolve_lien_consent(req.decision_id, f"A2A-SETTLE-{chain_id}")
        res["maintq_lien_consent_updated"] = resolved
        logger.info(
            "LIEN-CONSENT 해소 %s (decision=%s, chain=%s) — 서명은 사람이 한다",
            "완료" if resolved else "생략(이미 근거 있음)",
            req.decision_id, chain_id,
        )
    return res
```

**`lien_consent_ref` 에 넣는 값은 `f"A2A-SETTLE-{chain_id}"` 로 확정한다.** 설계 문서가 열어둔 미해결 항목이며, 요건 두 가지(비어 있지 않을 것 · 나중에 출처를 되짚을 수 있을 것)를 모두 만족한다 — `chain_id` 로 `traces` 에서 그 정산 왕복을 그대로 찾을 수 있다.

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && DATABASE_URL=<DSN> python -m pytest backend/routers/test_a2a.py backend/services/test_lien.py backend/a2a/test_payloads.py -v`

Expected: PASS — 신규 5건 + 앞 태스크 신규분 + 기존 전부.

- [ ] **Step 5: 회귀 스위트를 돌린다**

Run: MaintQ `CLAUDE.md` 「회귀 스위트」 절이 지정하는 명령. A2A 8파일군은 `pytest-asyncio` 없이 돌리면 async 테스트가 전부 떨어지므로 그 절이 지정한 러너를 쓴다.

Expected: 해당 절의 기준선 + 이 계획의 신규분. **FAIL 0건이 아니면 커밋하지 않는다.** 건수 차이를 설명할 수 없으면 커밋하지 않는다.

- [ ] **Step 6: 커밋**

```bash
cd /c/Users/ttogl/workspace/MaintQ
git add backend/routers/a2a.py backend/routers/test_a2a.py
git commit -m "feat(a2a): POST /api/a2a/request-settlement (S12)

MaintQ 발신 스킬 중 유일하게 응답이 MaintQ 상태를 바꾼다 —
lien_released=true 면 LIEN-CONSENT 를 해소한다. 단 서명하지는 않는다.

해소는 lien_released 가 명시적으로 true 일 때만 한다. 키가 없거나 다른
값이면 아무것도 쓰지 않는다(조용한 해소 금지).

lien_consent_ref 에 넣는 값은 A2A-SETTLE-<chain_id> 다 — 비어 있지 않고
traces 에서 그 정산 왕복을 되짚을 수 있다."
```

---

### Task 6: 문서 반영

**Files:**
- Modify: `C:\Users\ttogl\workspace\MaintQ\docs\07_BACKLOG.md` (P34)
- Modify: `C:\Users\ttogl\workspace\A2A_Q\A2A_DIAGRAMS.md` (§⑦ 끝 표, §①)

**Interfaces:**
- Consumes: Task 1~5
- Produces: 없음 (마지막)

- [ ] **Step 1: MaintQ 백로그 P34를 갱신한다**

P34는 "FinAllQ 추가 5스킬 발신 트리거 미착수"다. **5종 중 2종 완료**로 바꾸고, 나머지 3종은 **"미착수"가 아니라 "데이터 없음"**으로 사유를 적는다:

```markdown
- **S13·S12 완료 (2026-08-30)** — `assess-used-equipment-loan`·`request-settlement`
  발신 트리거 구현. S12는 응답 `lien_released`로 LIEN-CONSENT를 해소한다(서명은 사람이 한다).
- **S6·S16·S15는 만들지 않는다 — 미착수가 아니라 데이터 없음이다.**
  - `advise-hedge`(S6): MaintQ에 통화·외화 데이터가 0건이다. 만들려면 공급사에 통화
    컬럼을 신설하고 환노출을 지어내야 한다
  - `advise-financing`(S16): 트리거가 될 도메인 이벤트가 없다
  - `advise-replacement-financing`(S15): 2차 홉 전용인데 MaintQ에 `claim-insurance`
    발신 흐름 자체가 없다 — 사실상 두 스킬 작업이라 별도 사이클
```

- [ ] **Step 2: A2A_Q `A2A_DIAGRAMS.md` §⑦ 끝 표를 갱신한다**

"신규 — FinAllQ 추가 5스킬" 표의 MaintQ 쪽 상태를 고친다:

| 스킬 | MaintQ 쪽 상태 |
|---|---|
| `assess-used-equipment-loan`(S13) | ✅ 발신 트리거 구현(2026-08-30) |
| `request-settlement`(S12) | ✅ 발신 트리거 구현 — 응답이 LIEN-CONSENT를 해소하는 첫 스킬 |
| `advise-hedge`(S6) | ⚪ **만들지 않음 — 통화 데이터 0건** |
| `advise-financing`(S16) | ⚪ **만들지 않음 — 트리거 이벤트 없음** |
| `advise-replacement-financing`(S15) | ⚪ **만들지 않음 — `claim-insurance` 발신 선행 미충족** |

§①의 mermaid 엣지 라벨에서 `S6·S12·S13·S16` 묶음도 함께 정정한다 — S12·S13이 이제 발신되므로 "FinAllQ 수신부 완료·MaintQ 발신 미착수"에서 빠진다.

§⑦ 본문의 "MaintQ 쪽 발신 트리거는 여전히 이 3종뿐이다"도 **5종**으로 고친다.

- [ ] **Step 3: 문서 렌더 검증**

Run: `cd /c/Users/ttogl/workspace/A2A_Q && python -c "import pathlib; t=pathlib.Path('A2A_DIAGRAMS.md').read_text(encoding='utf-8'); print('mermaid 블록:', t.count('```mermaid'), '| 표 행:', t.count('|---'))"`

Expected: 갱신 전과 같은 개수(구조를 깨뜨리지 않았다).

- [ ] **Step 4: 커밋**

```bash
cd /c/Users/ttogl/workspace/MaintQ
git add docs/07_BACKLOG.md
git commit -m "docs: 백로그 P34 — S13·S12 완료, 나머지 3종은 '데이터 없음'으로 닫는다"

cd /c/Users/ttogl/workspace/A2A_Q
git status --short   # 다른 세션 작업물과 섞이지 않는지 확인
git add A2A_DIAGRAMS.md
git commit -m "docs: A2A_DIAGRAMS §⑦ — MaintQ 발신 3종 → 5종

S6·S16·S15 는 '미착수'가 아니라 '데이터 없음'으로 표기를 바꾼다 —
언젠가 할 일과 하지 않기로 한 일은 다르게 적어야 한다."
```

**푸시는 사용자에게 확인받는다.**

---

## Self-Review

**1. 스펙 커버리지**

| 스펙 요구 | 담당 |
|---|---|
| S13 엔드포인트 + 자산에서 4필드 파생 | Task 1·2 ✅ |
| `inspection_data`에 `ownership_checks` | Task 1 ✅ — 계약이 "S18 verify_ownership 결과 참조 가능"이라 적은 자리 |
| NULL은 키 생략(D62) | Task 1 ✅ |
| S12 엔드포인트 + draft `decision_id` | Task 3·5 ✅ |
| `approved_by`는 호출자 입력 | Task 3 ✅ |
| `lien_creditor`를 decision→asset으로 조회 | Task 3 ✅ |
| 🔴 자동 서명 금지 | Task 4·5 ✅ — 양쪽에서 테스트 |
| 🔴 빈 문자열 금지 | Task 4 ✅ |
| `lien_released:false`면 아무것도 안 씀 | Task 5 ✅ |
| 상대 장애 시 상태 불변 | Task 5 ✅ |
| 새 인프라 없음 | 전 Task ✅ — `client.py`·`auth_header.py`·`trace.py` 무변경 |
| 외부 실호출 0건 | 전 Task ✅ |
| 문서 반영 | Task 6 ✅ |
| S6·S16·S15 "데이터 없음"으로 닫기 | Task 6 ✅ |

**2. 플레이스홀더 스캔**

- `<컨테이너 DSN>`은 환경마다 다른 실제 값이라 의도적으로 비워뒀다. Global Constraints에 5434라는 사실을 적어뒀다.
- 픽스처 준비는 "무엇을 넣어야 하는지"를 구체적으로 지시했고 기존 파일 관례를 따르라고 명시했다 — 기존 픽스처 이름을 확정하지 않은 것은 A2A_Q 세션에서 `test_payloads.py` 본문을 읽지 않았기 때문이다.
- 설계 문서가 열어둔 미해결(`lien_consent_ref` 참조 형식)은 Task 5 Step 3에서 **`A2A-SETTLE-{chain_id}`로 확정**했다. TBD로 넘기지 않았다.
- 그 외 "적절히 처리" 류 없음. ✅

**3. 타입 일관성**

- `build_assess_used_equipment_loan_payload(asset_id, loan_amount, request_chain_id, db_path)` — Task 1 정의 ↔ Task 2 호출 일치 ✅
- `build_request_settlement_payload(decision_id, sale_amount, outstanding_loan, approved_by, prepayment_fee, request_chain_id, db_path)` — Task 3 정의 ↔ Task 5 호출, 인자 순서·이름 일치 ✅
- `resolve_lien_consent(decision_id, settlement_ref, db_path) -> bool` — Task 4 정의 ↔ Task 5 호출 일치 ✅
- `_dispatch(*, skill_id, payload, chain_id, session_id, base_url, partner_label, partner="finallq")` — Task 2 정의 ↔ Task 2·5 호출 일치(전부 키워드) ✅
- 두 빌더 모두 `ValueError`를 던지고 두 엔드포인트가 모두 400으로 매핑한다 ✅

**4. 알려진 위험**

- **Task 2가 `_dispatch` 헬퍼를 신설한다.** 기존 두 엔드포인트를 리팩터링하지 말라고 명시했다 — 동작하는 코드를 함께 건드리면 회귀 위험만 커진다.
- **Task 4의 `connect()`가 Postgres 트랜잭션을 어떻게 다루는지 확인이 필요하다.** `con.commit()`을 명시적으로 불렀으나 `connect()`가 컨텍스트 종료 시 자동 커밋한다면 중복이다. 구현자는 `backend/db.py`를 먼저 읽고 그 관례에 맞춘다.
- **`_dispatch`가 `res`가 dict가 아닌 응답을 받으면 `res["request_chain_id"] = chain_id`에서 터진다.** 기존 `assess-loan`도 같은 전제를 갖고 있어 새 위험은 아니다.
