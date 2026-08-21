# FinAllQ request-withdrawal A2A 어댑터 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** FinAllQ의 기존 REST API(`POST /api/v1/auth/login`, `GET /api/v1/accounts`,
`POST /api/v1/transfers`, 이미 동작 중)를 감싸는 독립 FastAPI 어댑터를 `:9101`에 띄워,
`request-withdrawal` A2A 스킬 하나가 실제로 요청→2단 승인 대기 응답 왕복을 증명하게 한다.

**Architecture:** `A2A_Q/adapters/finallq_a2a/`에 순수 번역 계층을 만든다. FinAllQ 코드는
전혀 건드리지 않고 HTTP 클라이언트로만 호출한다. `POST /api/v1/transfers`는 로그인 세션을
요구하므로, 어댑터가 서비스 계정으로 로그인해 토큰을 캐싱하는 계층(`auth.py`)을 InsuQ
어댑터에는 없던 새 구성요소로 추가한다.

**Tech Stack:** Python 3.13, FastAPI, httpx, pydantic v2, pytest + pytest-asyncio +
pytest-httpx (InsuQ 어댑터 작업에서 이미 repo root에 설치됨 — 재설치 불필요)

## Global Constraints

- FinAllQ 레포(`../FinAllQ`)는 이 계획에서 **읽기만 한다** — 어떤 파일도 쓰지 않는다.
- FinAllQ의 실제 DTO(Java 클래스)는 import하지 않는다 — dict/JSON으로만 주고받는다.
- 어댑터 기본 포트는 `9101`(README의 정식 `9001`과 구분되는 프로토타입 전용 포트).
- FinAllQ base URL은 환경변수 `FINALLQ_BASE_URL`, 기본값 `http://localhost:8080`.
- 서비스 계정 자격증명은 환경변수 `FINALLQ_SERVICE_EMAIL`/`FINALLQ_SERVICE_PASSWORD`로 받는다
  — 코드에 실제 값을 넣지 않는다.
- `from_account_id`는 A2A 요청 payload에 없다 — 어댑터가 로그인한 서비스 계정의
  `GET /api/v1/accounts` 첫 번째 계좌를 사용한다.
- 에러 응답 형식은 `{"error": "<code>", "detail": "<string>", "request_chain_id": "<string 또는 null>"}`.
- 인증 401을 받으면 캐시를 버리고 **1회만** 재로그인 후 재시도한다 — 그래도 401이면
  502로 보고한다. 무한 재시도 금지.
- 실행 환경은 Windows + Git Bash. venv는 이미 repo root `.venv/`에 있다 —
  `.venv/Scripts/python.exe`로 호출한다.

---

### Task 1: CP-002 계약 변경 + 프로젝트 스캐폴딩

**Files:**
- Modify: `docs/schemas/request-withdrawal.json`
- Modify: `docs/A2A_CONTRACT_CHANGES.md`
- Create: `adapters/finallq_a2a/__init__.py` (빈 파일)
- Create: `tests/adapters/finallq_a2a/__init__.py` (빈 파일 — `tests/`, `tests/adapters/`의
  `__init__.py`는 InsuQ 어댑터 작업에서 이미 존재하므로 새로 만들지 않는다)

**Interfaces:** 없음. 단, `docs/schemas/request-withdrawal.json`에 `to_account_number`
(필수)·`to_bank_code`(선택)가 추가된다는 사실은 Task 2(`schemas.py`)가 그대로 반영한다.

- [ ] **Step 1: `docs/schemas/request-withdrawal.json`에 계좌 필드 추가**

기존 파일의 `request.required` 배열에 `"to_account_number"`를 추가하고,
`request.properties`에 아래 두 필드를 추가한다(기존 필드는 그대로 둔다):

```json
      "to_account_number": {
        "type": "string",
        "description": "PROPOSED(A2A_Q, 2026-08-21): 거래처(수취인) 계좌번호. FinAllQ 계좌번호 형식과 동일.",
        "pattern": "^[0-9-]{4,20}$"
      },
      "to_bank_code": {
        "type": "string",
        "description": "PROPOSED(A2A_Q, 2026-08-21): 수취 은행 코드. 선택 — 국내 계좌이체 시 생략 가능."
      }
```

수정 후 전체 파일은 다음과 같아야 한다:

```json
{
  "skill_id": "request-withdrawal",
  "scenario": "S5",
  "direction": "MaintQ -> FinAllQ",
  "description": "발주 승인 완료된 부품 대금의 출금을 요청한다. 실행이 아니라 요청이며 2단 승인(팀장 -> 재무)을 거친다.",
  "request": {
    "type": "object",
    "required": ["requester", "request_chain_id", "po_id", "amount", "supplier", "approved_by", "purpose", "error_code", "to_account_number"],
    "properties": {
      "requester": { "$ref": "#/definitions/requester" },
      "request_chain_id": { "type": "string" },
      "po_id": { "type": "string" },
      "amount": { "type": "number" },
      "currency": { "type": "string", "default": "KRW" },
      "supplier": { "type": "string" },
      "approved_by": { "type": "string", "description": "MaintQ 팀장 승인자 ID" },
      "purpose": { "type": "string" },
      "error_code": { "type": "string" },
      "to_account_number": {
        "type": "string",
        "description": "PROPOSED(A2A_Q, 2026-08-21): 거래처(수취인) 계좌번호. FinAllQ 계좌번호 형식과 동일.",
        "pattern": "^[0-9-]{4,20}$"
      },
      "to_bank_code": {
        "type": "string",
        "description": "PROPOSED(A2A_Q, 2026-08-21): 수취 은행 코드. 선택 — 국내 계좌이체 시 생략 가능."
      }
    }
  },
  "response": {
    "type": "object",
    "required": ["status"],
    "properties": {
      "status": { "type": "string", "enum": ["input-required", "rejected", "completed"] },
      "fds_check": { "type": "string", "enum": ["pass", "hold"] },
      "requires_escalation": { "type": "boolean", "description": "금액 임계값 초과 시 상위 결재 필요 여부" },
      "req_id": { "type": "string" },
      "approved_by_finance": { "type": "string" },
      "executed_at": { "type": "string", "format": "date-time" },
      "reject_reason": { "type": "string" }
    }
  },
  "definitions": {
    "requester": {
      "type": "object",
      "required": ["finallq_company_id"],
      "properties": {
        "finallq_company_id": { "type": "string" },
        "building_id": { "type": "string" },
        "policy_id": { "type": "string" }
      }
    }
  }
}
```

- [ ] **Step 2: JSON 유효성 확인**

Run: `python -c "import json; json.load(open('docs/schemas/request-withdrawal.json', encoding='utf-8')); print('ok')"`
Expected: `ok`

- [ ] **Step 3: `docs/A2A_CONTRACT_CHANGES.md` 맨 끝에 CP-002 절 추가**

```markdown

---

## CP-002 — request-withdrawal: 수취 계좌 필드 추가 (제안)

| | |
|---|---|
| **status** | 🟡 **제안** — MaintQ 확인 대기 |
| **제안자** | A2A_Q (FinAllQ `request-withdrawal` 어댑터 프로토타입 작업 중 발견) |
| **제안일** | 2026-08-21 |
| **원본 조사** | FinAllQ `backend-core/.../dto/TransferRequestDto.java` 실측 |
| **영향 스킬** | `request-withdrawal` |
| **코드 영향** | 없음 — FinAllQ·MaintQ 양쪽 다 이 스킬 A2A 구현 착수 전 |

### 어떻게 발견했나

FinAllQ `request-withdrawal` 어댑터를 설계하며 실제 이체 API(`POST /api/v1/transfers`)의
요청 DTO를 대조하다 드러났다. 기존 스키마는 `supplier`(거래처명, 자유 텍스트)만 있고
계좌번호가 없어, 이 정보만으로는 실제 이체를 호출할 방법이 없다.

### 변경 — `to_account_number`(필수)·`to_bank_code`(선택) 추가

**문제.** `request-withdrawal.json`의 요청 필드에 수취 계좌 정보가 전혀 없다. FinAllQ의
`TransferRequestDto`는 `toAccountNumber`(필수, 패턴 `^[0-9-]{4,20}$`)와 `toBankCode`(선택)를
요구하는데 대응하는 A2A 필드가 없었다.

**변경.**
```jsonc
"to_account_number": { "type": "string", "pattern": "^[0-9-]{4,20}$" },
"to_bank_code": { "type": "string" }
```
`to_account_number`를 `required`에 추가했다.

**`from_account_id`는 스키마에 넣지 않는다** — "어느 계좌에서 나가는지"는 호출자(actor,
서비스 계정)에 딸린 정보이지 MaintQ가 지정할 subject가 아니다(`A2A_IDENTITY.md` 결정 1의
actor/subject 분리 원칙). FinAllQ 쪽 어댑터가 로그인한 계정의 계좌를 자동으로 조회해 채운다.

**호출자에게 필요한 조치** — MaintQ는 발주서(PO)에 거래처 계좌번호 정보를 갖고 있어야
`request-withdrawal`을 호출할 수 있다.

## 각 프로젝트가 확인할 것 (CP-002)

### MaintQ
- [ ] 발주서(PO) 데이터에 거래처 계좌번호가 있는지 확인 — 없으면 별도 입력 UI나 거래처
      마스터 데이터 연동이 선행돼야 한다

### FinAllQ
- [ ] `to_bank_code` 생략 시(같은 은행 내 이체) `TransferService`가 정상 처리하는지 확인
```

- [ ] **Step 4: 변경 확인**

Run: `grep -n "CP-002" docs/A2A_CONTRACT_CHANGES.md`
Expected: 최소 1줄 매치

- [ ] **Step 5: 빈 패키지 파일 생성**

Create `adapters/finallq_a2a/__init__.py`, `tests/adapters/finallq_a2a/__init__.py` — 내용 없음.

- [ ] **Step 6: 커밋**

```bash
git add docs/schemas/request-withdrawal.json docs/A2A_CONTRACT_CHANGES.md \
  adapters/finallq_a2a/__init__.py tests/adapters/finallq_a2a/__init__.py
git commit -m "feat(finallq-adapter): CP-002 제안(계좌 필드 추가) + 프로젝트 스캐폴딩"
```

---

### Task 2: `schemas.py` — request-withdrawal pydantic 모델 (CP-002 반영)

**Files:**
- Create: `adapters/finallq_a2a/schemas.py`
- Test: `tests/adapters/finallq_a2a/test_schemas.py`

**Interfaces:**
- Produces: `class Requester(BaseModel)` (`finallq_company_id: str`(필수),
  `building_id: str | None`, `policy_id: str | None`). `class RequestWithdrawalRequest(BaseModel)`
  (`requester: Requester`, `request_chain_id: str`, `po_id: str`, `amount: float`,
  `currency: str = "KRW"`, `supplier: str`, `approved_by: str`, `purpose: str`,
  `error_code: str`, `to_account_number: str`, `to_bank_code: str | None = None`).
  `class RequestWithdrawalResponse(BaseModel)` (`status: Literal["input-required","rejected","completed"]`,
  `fds_check: Literal["pass","hold"] | None = None`, `requires_escalation: bool | None = None`,
  `req_id: str | None = None`, `approved_by_finance: str | None = None`,
  `executed_at: str | None = None`, `reject_reason: str | None = None`). Task 3(mapping)·
  Task 7(main)이 이 세 클래스를 그대로 가져다 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/finallq_a2a/test_schemas.py`:
```python
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
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.finallq_a2a.schemas'`

- [ ] **Step 3: `adapters/finallq_a2a/schemas.py` 구현**

```python
"""request-withdrawal A2A 스킬 request/response pydantic 모델 (CP-002 반영).

원본 계약은 docs/schemas/request-withdrawal.json — 여기 필드는 그 스키마와 반드시
일치해야 한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requester(BaseModel):
    finallq_company_id: str
    building_id: str | None = None
    policy_id: str | None = None


class RequestWithdrawalRequest(BaseModel):
    requester: Requester
    request_chain_id: str
    po_id: str
    amount: float
    currency: str = "KRW"
    supplier: str
    approved_by: str
    purpose: str
    error_code: str
    to_account_number: str
    to_bank_code: str | None = None


class RequestWithdrawalResponse(BaseModel):
    status: Literal["input-required", "rejected", "completed"]
    fds_check: Literal["pass", "hold"] | None = None
    requires_escalation: bool | None = None
    req_id: str | None = None
    approved_by_finance: str | None = None
    executed_at: str | None = None
    reject_reason: str | None = None
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_schemas.py -v`
Expected: PASS (6/6)

- [ ] **Step 5: 커밋**

```bash
git add adapters/finallq_a2a/schemas.py tests/adapters/finallq_a2a/test_schemas.py
git commit -m "feat(finallq-adapter): request-withdrawal request/response pydantic 모델"
```

---

### Task 3: `mapping.py` — TransferResponseDto → request-withdrawal 응답 변환

**Files:**
- Create: `adapters/finallq_a2a/mapping.py`
- Test: `tests/adapters/finallq_a2a/test_mapping.py`

**Interfaces:**
- Consumes: 없음(순수 함수)
- Produces: `def map_transfer_response(transfer_response: dict) -> dict` — 입력은 FinAllQ
  `TransferResponseDto`의 실제 JSON 모양(`{requestId, status, message, requestedAt}`)을
  흉내낸 dict. 반환 dict의 키는 Task 2의 `RequestWithdrawalResponse` 필드와 일치한다.
  **모르는 `status` 값이 들어오면 `ValueError`를 던진다** — Task 7(main.py)이 이 예외를
  잡아 `502 upstream_unavailable`로 변환한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/finallq_a2a/test_mapping.py`:
```python
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
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.finallq_a2a.mapping'`

- [ ] **Step 3: `adapters/finallq_a2a/mapping.py` 구현**

```python
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
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_mapping.py -v`
Expected: PASS (9/9 — 3개는 parametrize로 묶인 것)

- [ ] **Step 5: 커밋**

```bash
git add adapters/finallq_a2a/mapping.py tests/adapters/finallq_a2a/test_mapping.py
git commit -m "feat(finallq-adapter): TransferResponseDto -> request-withdrawal 응답 매핑"
```

---

### Task 4: `auth.py` — 서비스 계정 로그인 + 토큰 캐시

**Files:**
- Create: `adapters/finallq_a2a/auth.py`
- Test: `tests/adapters/finallq_a2a/test_auth.py`

**Interfaces:**
- Produces: `class LoginFailedError(Exception)`, `class TokenCache` (`get() -> str | None`,
  `set(token: str) -> None`, `clear() -> None`), `async def login(email: str, password: str,
  base_url: str, timeout: float = 10.0) -> str`, `async def get_token(cache: TokenCache,
  email: str, password: str, base_url: str) -> str`(캐시에 있으면 그대로 반환, 없으면
  `login()` 호출 후 캐시에 저장하고 반환). Task 7(main.py)이 `TokenCache` 인스턴스를
  모듈 스코프에 하나 두고 `get_token()`을 호출한다. `LoginFailedError`는
  Task 5(`finallq_client.py`)의 `AuthExpiredError`와 별개 예외다 — 로그인 자체 실패 vs
  발급된 토큰이 나중에 거부됨을 구분한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/finallq_a2a/test_auth.py`:
```python
import json

import pytest

from adapters.finallq_a2a.auth import LoginFailedError, TokenCache, get_token, login


async def test_login_returns_access_token(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/auth/login",
        method="POST",
        json={"accessToken": "jwt-abc123", "email": "svc@finallq.example", "role": "USER",
              "canInvite": False, "userId": 1, "companyId": 1},
    )

    token = await login("svc@finallq.example", "pw", base_url="http://test-finallq")

    assert token == "jwt-abc123"
    request = httpx_mock.get_requests()[0]
    payload = json.loads(request.read())
    assert payload == {"email": "svc@finallq.example", "password": "pw"}


async def test_login_raises_on_non_200(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/auth/login", method="POST", status_code=401
    )

    with pytest.raises(LoginFailedError):
        await login("svc@finallq.example", "wrong-pw", base_url="http://test-finallq")


def test_token_cache_get_set_clear():
    cache = TokenCache()
    assert cache.get() is None

    cache.set("jwt-xyz")
    assert cache.get() == "jwt-xyz"

    cache.clear()
    assert cache.get() is None


async def test_get_token_calls_login_when_cache_empty(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/auth/login", method="POST",
        json={"accessToken": "jwt-fresh", "email": "e", "role": "USER", "canInvite": False,
              "userId": 1, "companyId": 1},
    )
    cache = TokenCache()

    token = await get_token(cache, "svc@finallq.example", "pw", base_url="http://test-finallq")

    assert token == "jwt-fresh"
    assert cache.get() == "jwt-fresh"


async def test_get_token_reuses_cache_without_calling_login(monkeypatch):
    async def fail_if_called(*args, **kwargs):
        raise AssertionError("login() should not be called when cache is populated")

    monkeypatch.setattr("adapters.finallq_a2a.auth.login", fail_if_called)
    cache = TokenCache()
    cache.set("jwt-cached")

    token = await get_token(cache, "svc@finallq.example", "pw", base_url="http://test-finallq")

    assert token == "jwt-cached"
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.finallq_a2a.auth'`

- [ ] **Step 3: `adapters/finallq_a2a/auth.py` 구현**

```python
"""FinAllQ 서비스 계정 로그인 + 토큰 캐시.

파트너 자격증명(머신 신원, 백로그 131·132)이 아직 없어 임시로 사람 계정(서비스 계정)을
재사용한다 — 자격증명은 .env로 받고, 로그인 결과(accessToken)를 프로세스 메모리에
캐싱한다. 만료 시각 파싱은 하지 않는다(YAGNI) — 401을 받으면 캐시를 버리고 재로그인한다
(그 재시도 로직은 finallq_client.AuthExpiredError를 받는 호출부, 즉 main.py의 책임이다).
"""

from __future__ import annotations

import httpx


class LoginFailedError(Exception):
    """서비스 계정 로그인 자체가 실패했을 때 (자격증명 오류, 연결 실패 등)."""


class TokenCache:
    def __init__(self) -> None:
        self._token: str | None = None

    def get(self) -> str | None:
        return self._token

    def set(self, token: str) -> None:
        self._token = token

    def clear(self) -> None:
        self._token = None


async def login(email: str, password: str, base_url: str, timeout: float = 10.0) -> str:
    """POST /api/v1/auth/login 을 호출해 accessToken을 반환한다."""
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.post(
                "/api/v1/auth/login", json={"email": email, "password": password}
            )
    except httpx.HTTPError as exc:
        raise LoginFailedError(f"FinAllQ login request failed: {exc}") from exc

    if response.status_code != 200:
        raise LoginFailedError(f"FinAllQ login failed with status {response.status_code}")

    body = response.json()
    return body["accessToken"]


async def get_token(cache: TokenCache, email: str, password: str, base_url: str) -> str:
    """캐시된 토큰이 있으면 그대로 반환하고, 없으면 로그인해서 캐시에 저장한다."""
    token = cache.get()
    if token is None:
        token = await login(email, password, base_url)
        cache.set(token)
    return token
```

(`httpx.HTTPError`는 `httpx`의 모든 예외의 공통 조상 클래스다 — 로그인 단계에서는 연결
실패·타임아웃을 세분화하지 않고 전부 `LoginFailedError`로 뭉뚱그린다. 실제 이체 호출
단계(Task 5)에서만 502/504를 구분한다.)

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_auth.py -v`
Expected: PASS (5/5)

- [ ] **Step 5: 커밋**

```bash
git add adapters/finallq_a2a/auth.py tests/adapters/finallq_a2a/test_auth.py
git commit -m "feat(finallq-adapter): 서비스 계정 로그인 + 토큰 캐시"
```

---

### Task 5: `finallq_client.py` — 계좌 조회·이체 요청 HTTP 클라이언트

**Files:**
- Create: `adapters/finallq_a2a/finallq_client.py`
- Test: `tests/adapters/finallq_a2a/test_finallq_client.py`

**Interfaces:**
- Consumes: 없음
- Produces: `class UpstreamUnavailableError(Exception)`, `class UpstreamTimeoutError(Exception)`,
  `class NoAccountError(Exception)`, `class AuthExpiredError(Exception)`,
  `async def get_first_account_id(token: str, base_url: str, timeout: float = 10.0) -> int`,
  `async def request_transfer(token: str, from_account_id: int, amount: float,
  to_account_number: str, to_bank_code: str | None, memo: str, base_url: str,
  timeout: float = 10.0) -> dict`. Task 7(main.py)이 이 함수들과 네 예외 클래스를 그대로
  가져다 쓴다 — `request_transfer`의 반환값(dict)은 그대로 Task 3의
  `map_transfer_response()` 입력이 된다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/finallq_a2a/test_finallq_client.py`:
```python
import json

import httpx
import pytest

from adapters.finallq_a2a.finallq_client import (
    AuthExpiredError,
    NoAccountError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    get_first_account_id,
    request_transfer,
)


async def test_get_first_account_id_returns_first_account(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/accounts?page=0",
        method="GET",
        json={"content": [{"accountId": 42, "maskedAccountNumber": "****0001", "balance": 200000000, "createdAt": "2026-01-01"}],
              "page": 0, "size": 20, "totalElements": 1, "totalPages": 1},
    )

    account_id = await get_first_account_id("jwt-abc", base_url="http://test-finallq")

    assert account_id == 42
    request = httpx_mock.get_requests()[0]
    assert request.headers["Authorization"] == "Bearer jwt-abc"


async def test_get_first_account_id_raises_no_account_when_empty(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/accounts?page=0",
        method="GET",
        json={"content": [], "page": 0, "size": 20, "totalElements": 0, "totalPages": 0},
    )

    with pytest.raises(NoAccountError):
        await get_first_account_id("jwt-abc", base_url="http://test-finallq")


async def test_get_first_account_id_raises_auth_expired_on_401(httpx_mock):
    httpx_mock.add_response(url="http://test-finallq/api/v1/accounts?page=0", method="GET", status_code=401)

    with pytest.raises(AuthExpiredError):
        await get_first_account_id("jwt-expired", base_url="http://test-finallq")


async def test_get_first_account_id_raises_upstream_unavailable_on_connect_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("refused"))

    with pytest.raises(UpstreamUnavailableError):
        await get_first_account_id("jwt-abc", base_url="http://test-finallq")


async def test_request_transfer_sends_expected_payload(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/transfers",
        method="POST",
        status_code=201,
        json={"requestId": 88213, "status": "PENDING", "message": None, "requestedAt": "2026-08-21T10:00:00Z"},
    )

    result = await request_transfer(
        token="jwt-abc",
        from_account_id=42,
        amount=1500000,
        to_account_number="900-000-001",
        to_bank_code=None,
        memo="유압 실린더 교체 부품 대금",
        base_url="http://test-finallq",
    )

    assert result["status"] == "PENDING"
    request = httpx_mock.get_requests()[0]
    payload = json.loads(request.read())
    assert payload == {
        "fromAccountId": 42,
        "amount": 1500000,
        "toAccountNumber": "900-000-001",
        "memo": "유압 실린더 교체 부품 대금",
    }
    assert "toBankCode" not in payload
    assert request.headers["Authorization"] == "Bearer jwt-abc"


async def test_request_transfer_includes_bank_code_when_given(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/transfers", method="POST", status_code=201,
        json={"requestId": 1, "status": "PENDING", "message": None, "requestedAt": None},
    )

    await request_transfer(
        token="jwt-abc", from_account_id=42, amount=1000, to_account_number="900-000-001",
        to_bank_code="004", memo="m", base_url="http://test-finallq",
    )

    request = httpx_mock.get_requests()[0]
    payload = json.loads(request.read())
    assert payload["toBankCode"] == "004"


async def test_request_transfer_raises_auth_expired_on_401(httpx_mock):
    httpx_mock.add_response(url="http://test-finallq/api/v1/transfers", method="POST", status_code=401)

    with pytest.raises(AuthExpiredError):
        await request_transfer(
            token="jwt-expired", from_account_id=42, amount=1000, to_account_number="900-000-001",
            to_bank_code=None, memo="m", base_url="http://test-finallq",
        )


async def test_request_transfer_raises_value_error_on_400(httpx_mock):
    httpx_mock.add_response(
        url="http://test-finallq/api/v1/transfers", method="POST", status_code=400,
        text="계좌번호 형식이 올바르지 않습니다.",
    )

    with pytest.raises(ValueError):
        await request_transfer(
            token="jwt-abc", from_account_id=42, amount=1000, to_account_number="bad",
            to_bank_code=None, memo="m", base_url="http://test-finallq",
        )


async def test_request_transfer_raises_upstream_unavailable_on_5xx(httpx_mock):
    httpx_mock.add_response(url="http://test-finallq/api/v1/transfers", method="POST", status_code=500)

    with pytest.raises(UpstreamUnavailableError):
        await request_transfer(
            token="jwt-abc", from_account_id=42, amount=1000, to_account_number="900-000-001",
            to_bank_code=None, memo="m", base_url="http://test-finallq",
        )


async def test_request_transfer_raises_upstream_timeout(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))

    with pytest.raises(UpstreamTimeoutError):
        await request_transfer(
            token="jwt-abc", from_account_id=42, amount=1000, to_account_number="900-000-001",
            to_bank_code=None, memo="m", base_url="http://test-finallq",
        )
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_finallq_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.finallq_a2a.finallq_client'`

- [ ] **Step 3: `adapters/finallq_a2a/finallq_client.py` 구현**

```python
"""FinAllQ 계좌 조회·이체 요청 HTTP 클라이언트.

FinAllQ 코드는 건드리지 않는다 — 이미 떠 있는 REST API(/api/v1/accounts,
/api/v1/transfers)를 그대로 호출한다. 인증 헤더(Bearer 토큰)는 호출부가 넘겨준다 —
이 모듈은 토큰을 발급·캐싱하지 않는다(auth.py 책임).

httpx.TransportError로 폭넓게 잡는 이유: ConnectError·ReadError·WriteError·
ProtocolError 등은 전부 그 서브클래스다(InsuQ 어댑터 작업에서 실측 확인 — TimeoutException도
같은 계열이지만 여기서는 먼저 갈라서 504로 보낸다).
"""

from __future__ import annotations

import httpx


class UpstreamUnavailableError(Exception):
    """FinAllQ에 연결할 수 없거나 5xx를 반환했을 때."""


class UpstreamTimeoutError(Exception):
    """FinAllQ 응답이 타임아웃됐을 때."""


class NoAccountError(Exception):
    """서비스 계정에 연결된 계좌가 0건일 때."""


class AuthExpiredError(Exception):
    """토큰이 만료/무효(401)일 때 — 호출부가 재로그인 후 재시도해야 한다."""


async def get_first_account_id(token: str, base_url: str, timeout: float = 10.0) -> int:
    """GET /api/v1/accounts?page=0 을 호출해 첫 번째 계좌의 accountId를 반환한다."""
    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.get(
                "/api/v1/accounts",
                params={"page": 0},
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError(str(exc)) from exc
    except httpx.TransportError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    if response.status_code == 401:
        raise AuthExpiredError("FinAllQ rejected the access token")
    if response.status_code >= 500:
        raise UpstreamUnavailableError(f"FinAllQ returned {response.status_code}")

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    try:
        body = response.json()
    except ValueError as exc:
        raise UpstreamUnavailableError(f"FinAllQ returned a non-JSON response: {exc}") from exc

    content = body.get("content", [])
    if not content:
        raise NoAccountError("service account has no linked account")
    return content[0]["accountId"]


async def request_transfer(
    token: str,
    from_account_id: int,
    amount: float,
    to_account_number: str,
    to_bank_code: str | None,
    memo: str,
    base_url: str,
    timeout: float = 10.0,
) -> dict:
    """POST /api/v1/transfers 를 호출해 TransferResponseDto(dict)를 반환한다."""
    payload: dict = {
        "fromAccountId": from_account_id,
        "amount": amount,
        "toAccountNumber": to_account_number,
        "memo": memo,
    }
    if to_bank_code is not None:
        payload["toBankCode"] = to_bank_code

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.post(
                "/api/v1/transfers",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError(str(exc)) from exc
    except httpx.TransportError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    if response.status_code == 401:
        raise AuthExpiredError("FinAllQ rejected the access token")
    if response.status_code == 400:
        raise ValueError(f"FinAllQ rejected the transfer request: {response.text}")
    if response.status_code >= 500:
        raise UpstreamUnavailableError(f"FinAllQ returned {response.status_code}")

    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    try:
        return response.json()
    except ValueError as exc:
        raise UpstreamUnavailableError(f"FinAllQ returned a non-JSON response: {exc}") from exc
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_finallq_client.py -v`
Expected: PASS (9/9)

- [ ] **Step 5: 커밋**

```bash
git add adapters/finallq_a2a/finallq_client.py tests/adapters/finallq_a2a/test_finallq_client.py
git commit -m "feat(finallq-adapter): 계좌 조회·이체 요청 HTTP 클라이언트"
```

---

### Task 6: `agent_card.py` — Agent Card 로더

**Files:**
- Create: `adapters/finallq_a2a/agent_card.py`
- Test: `tests/adapters/finallq_a2a/test_agent_card.py`

**Interfaces:**
- Consumes: `docs/agent_cards/finallq.json`(이미 `request-withdrawal` 스킬 포함 — 이번
  작업에서 이 파일 자체는 바꾸지 않는다)
- Produces: `def load_agent_card() -> dict`. Task 7(main.py)이 `GET
  /.well-known/agent-card.json` 핸들러와 미구현 스킬 판별(`{skill["id"] for skill in
  load_agent_card()["skills"]}`)에서 그대로 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/finallq_a2a/test_agent_card.py`:
```python
from adapters.finallq_a2a.agent_card import load_agent_card


def test_load_agent_card_returns_finallq_card_with_request_withdrawal():
    card = load_agent_card()

    assert card["name"] == "FinAllQ"
    skill_ids = [s["id"] for s in card["skills"]]
    assert "request-withdrawal" in skill_ids
    assert "assess-loan" in skill_ids
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_agent_card.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.finallq_a2a.agent_card'`

- [ ] **Step 3: `adapters/finallq_a2a/agent_card.py` 구현**

```python
"""FinAllQ Agent Card 로더 — docs/agent_cards/finallq.json 을 그대로 서빙한다.

파일을 복제하지 않는다 — 원본은 docs/agent_cards/에 있고(A2A_Q 계약 문서 원칙, drift
방지), 여기서는 읽기만 한다.
"""

from __future__ import annotations

import json
from pathlib import Path

_AGENT_CARD_PATH = Path(__file__).resolve().parents[2] / "docs" / "agent_cards" / "finallq.json"


def load_agent_card() -> dict:
    return json.loads(_AGENT_CARD_PATH.read_text(encoding="utf-8"))
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_agent_card.py -v`
Expected: PASS (1/1)

- [ ] **Step 5: 커밋**

```bash
git add adapters/finallq_a2a/agent_card.py tests/adapters/finallq_a2a/test_agent_card.py
git commit -m "feat(finallq-adapter): Agent Card 로더"
```

---

### Task 7: `main.py` — FastAPI 앱 배선

**Files:**
- Create: `adapters/finallq_a2a/main.py`
- Test: `tests/adapters/finallq_a2a/test_main.py`

**Interfaces:**
- Consumes: `load_agent_card()`(Task 6), `LoginFailedError`·`TokenCache`·`get_token()`
  (Task 4), `AuthExpiredError`·`NoAccountError`·`UpstreamUnavailableError`·
  `UpstreamTimeoutError`·`get_first_account_id()`·`request_transfer()`(Task 5),
  `map_transfer_response()`(Task 3), `RequestWithdrawalRequest`·`RequestWithdrawalResponse`
  (Task 2)
- Produces: `app`(FastAPI 인스턴스) — 마지막 태스크.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/finallq_a2a/test_main.py`:
```python
from fastapi.testclient import TestClient

from adapters.finallq_a2a import main
from adapters.finallq_a2a.auth import LoginFailedError
from adapters.finallq_a2a.finallq_client import (
    AuthExpiredError,
    NoAccountError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
)

client = TestClient(main.app)


def _valid_body(**overrides):
    body = {
        "requester": {"finallq_company_id": "FQ-1043"},
        "request_chain_id": "chain-1",
        "po_id": "PO-88213",
        "amount": 1500000,
        "supplier": "ABC 부품상사",
        "approved_by": "team-lead-01",
        "purpose": "유압 실린더 교체 부품 대금",
        "error_code": "E-4102",
        "to_account_number": "900-000-001",
    }
    body.update(overrides)
    return body


def _headers(chain_id="chain-1"):
    return {"X-Request-Chain-Id": chain_id}


def test_agent_card_endpoint_returns_finallq_card():
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.json()["name"] == "FinAllQ"


def test_request_withdrawal_success(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        return 42

    async def fake_request_transfer(**kwargs):
        return {"requestId": 88213, "status": "PENDING", "message": None, "requestedAt": "2026-08-21T10:00:00Z"}

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)
    monkeypatch.setattr(main, "request_transfer", fake_request_transfer)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "input-required"
    assert data["req_id"] == "88213"


def test_request_withdrawal_chain_id_mismatch():
    resp = client.post(
        "/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers("chain-DIFFERENT")
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "chain_id_mismatch"


def test_request_withdrawal_schema_validation_failed():
    body = _valid_body()
    del body["to_account_number"]
    resp = client.post("/a2a/skills/request-withdrawal", json=body, headers=_headers())
    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"


def test_request_withdrawal_non_dict_body():
    resp = client.post("/a2a/skills/request-withdrawal", json=["not", "an", "object"])
    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"


def test_request_withdrawal_login_failed(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        raise LoginFailedError("bad credentials")

    monkeypatch.setattr(main, "get_token", fake_get_token)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_request_withdrawal_retries_once_on_auth_expired_then_succeeds(monkeypatch):
    call_count = {"get_token": 0, "transfer_flow": 0}

    async def fake_get_token(cache, email, password, base_url):
        call_count["get_token"] += 1
        return f"jwt-{call_count['get_token']}"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        return 42

    async def fake_request_transfer(**kwargs):
        call_count["transfer_flow"] += 1
        if call_count["transfer_flow"] == 1:
            raise AuthExpiredError("token expired")
        return {"requestId": 1, "status": "PENDING", "message": None, "requestedAt": None}

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)
    monkeypatch.setattr(main, "request_transfer", fake_request_transfer)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())

    assert resp.status_code == 200
    assert call_count["get_token"] == 2  # 최초 1회 + 재로그인 1회
    assert call_count["transfer_flow"] == 2  # 최초 시도 1회 + 재시도 1회


def test_request_withdrawal_still_auth_expired_after_retry(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-always-rejected"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        return 42

    async def fake_request_transfer(**kwargs):
        raise AuthExpiredError("token expired")

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)
    monkeypatch.setattr(main, "request_transfer", fake_request_transfer)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())

    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_request_withdrawal_no_account(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        raise NoAccountError("no account")

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_request_withdrawal_upstream_unavailable(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        raise UpstreamUnavailableError("boom")

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_request_withdrawal_upstream_timeout(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        raise UpstreamTimeoutError("boom")

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 504
    assert resp.json()["error"] == "upstream_timeout"


def test_request_withdrawal_finallq_400_maps_to_schema_validation_failed(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        return 42

    async def fake_request_transfer(**kwargs):
        raise ValueError("계좌번호 형식이 올바르지 않습니다.")

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)
    monkeypatch.setattr(main, "request_transfer", fake_request_transfer)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"


def test_request_withdrawal_unknown_finallq_status_maps_to_upstream_unavailable(monkeypatch):
    async def fake_get_token(cache, email, password, base_url):
        return "jwt-abc"

    async def fake_get_first_account_id(token, base_url, timeout=10.0):
        return 42

    async def fake_request_transfer(**kwargs):
        return {"requestId": 1, "status": "SOME_NEW_STATUS", "message": None, "requestedAt": None}

    monkeypatch.setattr(main, "get_token", fake_get_token)
    monkeypatch.setattr(main, "get_first_account_id", fake_get_first_account_id)
    monkeypatch.setattr(main, "request_transfer", fake_request_transfer)

    resp = client.post("/a2a/skills/request-withdrawal", json=_valid_body(), headers=_headers())
    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_unimplemented_known_skill_returns_501():
    resp = client.post("/a2a/skills/assess-loan", json={})
    assert resp.status_code == 501
    assert resp.json()["error"] == "not_implemented"


def test_unknown_skill_returns_404():
    resp = client.post("/a2a/skills/not-a-real-skill", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_skill"
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.finallq_a2a.main'`

- [ ] **Step 3: `adapters/finallq_a2a/main.py` 구현**

```python
"""FinAllQ request-withdrawal A2A 어댑터 — 독립 FastAPI 서비스 (기본 포트 9101).

FinAllQ 코드를 건드리지 않고 기존 REST API(/api/v1/auth/login, /api/v1/accounts,
/api/v1/transfers)를 A2A 봉투로 감싼다. request-withdrawal 외 6개 스킬은 Agent
Card에는 선언돼 있지만 이 프로토타입에서는 미구현 — 501로 명시 응답한다.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from adapters.finallq_a2a.agent_card import load_agent_card
from adapters.finallq_a2a.auth import LoginFailedError, TokenCache, get_token
from adapters.finallq_a2a.finallq_client import (
    AuthExpiredError,
    NoAccountError,
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    get_first_account_id,
    request_transfer,
)
from adapters.finallq_a2a.mapping import map_transfer_response
from adapters.finallq_a2a.schemas import RequestWithdrawalRequest, RequestWithdrawalResponse

FINALLQ_BASE_URL = os.environ.get("FINALLQ_BASE_URL", "http://localhost:8080")
FINALLQ_SERVICE_EMAIL = os.environ.get("FINALLQ_SERVICE_EMAIL", "")
FINALLQ_SERVICE_PASSWORD = os.environ.get("FINALLQ_SERVICE_PASSWORD", "")

_token_cache = TokenCache()

app = FastAPI(title="FinAllQ A2A Adapter (prototype)")


@app.get("/.well-known/agent-card.json")
async def agent_card_endpoint() -> dict:
    return load_agent_card()


async def _do_transfer(parsed: RequestWithdrawalRequest, token: str) -> dict:
    account_id = await get_first_account_id(token, FINALLQ_BASE_URL)
    return await request_transfer(
        token=token,
        from_account_id=account_id,
        amount=parsed.amount,
        to_account_number=parsed.to_account_number,
        to_bank_code=parsed.to_bank_code,
        memo=parsed.purpose,
        base_url=FINALLQ_BASE_URL,
    )


async def _transfer_with_auth_retry(parsed: RequestWithdrawalRequest) -> dict:
    token = await get_token(_token_cache, FINALLQ_SERVICE_EMAIL, FINALLQ_SERVICE_PASSWORD, FINALLQ_BASE_URL)
    try:
        return await _do_transfer(parsed, token)
    except AuthExpiredError:
        _token_cache.clear()
        token = await get_token(_token_cache, FINALLQ_SERVICE_EMAIL, FINALLQ_SERVICE_PASSWORD, FINALLQ_BASE_URL)
        return await _do_transfer(parsed, token)


@app.post("/a2a/skills/request-withdrawal")
async def request_withdrawal(request: Request) -> JSONResponse:
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
        parsed = RequestWithdrawalRequest.model_validate(body)
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
        transfer_response = await _transfer_with_auth_retry(parsed)
    except LoginFailedError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unavailable", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )
    except AuthExpiredError:
        return JSONResponse(
            status_code=502,
            content={
                "error": "upstream_unavailable",
                "detail": "FinAllQ rejected the access token even after re-login",
                "request_chain_id": parsed.request_chain_id,
            },
        )
    except NoAccountError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unavailable", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )
    except UpstreamUnavailableError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unavailable", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )
    except UpstreamTimeoutError as exc:
        return JSONResponse(
            status_code=504,
            content={"error": "upstream_timeout", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )
    except ValueError as exc:
        return JSONResponse(
            status_code=400,
            content={"error": "schema_validation_failed", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )

    try:
        mapped = map_transfer_response(transfer_response)
    except ValueError as exc:
        return JSONResponse(
            status_code=502,
            content={"error": "upstream_unavailable", "detail": str(exc), "request_chain_id": parsed.request_chain_id},
        )

    validated = RequestWithdrawalResponse.model_validate(mapped)
    return JSONResponse(status_code=200, content=validated.model_dump(exclude_none=True))


@app.post("/a2a/skills/{skill_id}")
async def unimplemented_skill(skill_id: str) -> JSONResponse:
    known_skill_ids = {skill["id"] for skill in load_agent_card()["skills"]}
    if skill_id not in known_skill_ids:
        return JSONResponse(
            status_code=404,
            content={"error": "unknown_skill", "detail": f"'{skill_id}' is not declared in the Agent Card"},
        )
    return JSONResponse(
        status_code=501,
        content={"error": "not_implemented", "detail": f"'{skill_id}' is not implemented in this prototype adapter"},
    )
```

**중요 — monkeypatch가 동작하려면** `main.py`가 `get_token`·`get_first_account_id`·
`request_transfer`를 각각 이름으로 모듈 네임스페이스에 들여와야 한다(위 코드처럼
`from ... import get_token` 형태). `auth.get_token(...)`처럼 모듈 경유로 호출하면
`monkeypatch.setattr(main, "get_token", ...)`이 안 먹는다 — InsuQ 어댑터 작업에서
같은 이유로 이미 한 번 확인된 패턴이다.

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/finallq_a2a/test_main.py -v`
Expected: PASS (13/13)

- [ ] **Step 5: 전체 스위트 한 번에 실행**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS 전체 — InsuQ 어댑터 31개 + 이번 태스크들(schemas 6 + mapping 9 + auth 5 +
finallq_client 9 + agent_card 1 + main 13 = 43) = 총 74개 근처(정확한 숫자는 InsuQ
쪽 스위트가 이미 몇 개인지에 따라 달라질 수 있음 — 실행 결과의 실제 합계를 보고하면 된다).
새로 추가된 43개가 전부 통과하고 기존 InsuQ 테스트에 회귀가 없어야 한다.

- [ ] **Step 6: 로컬 기동 확인 (선택)**

Run:
```bash
.venv/Scripts/python.exe -m uvicorn adapters.finallq_a2a.main:app --port 9101 &
sleep 2
curl -s http://localhost:9101/.well-known/agent-card.json | head -c 200
kill %1
```
Expected: Agent Card JSON 앞부분(`{"name":"FinAllQ",...`) 출력. FinAllQ 서버가 안 떠
있어도 이 단계(Agent Card 서빙)는 통과한다 — `/a2a/skills/request-withdrawal` 실제 호출은
502를 내겠지만 그건 이 스텝의 확인 대상이 아니다.

- [ ] **Step 7: 커밋**

```bash
git add adapters/finallq_a2a/main.py tests/adapters/finallq_a2a/test_main.py
git commit -m "feat(finallq-adapter): FastAPI 앱 배선 — request-withdrawal 엔드포인트 + 인증 재시도 + 에러 매핑"
```

---

## Self-Review 완료 기록

- **Spec 커버리지**: 설계 스펙(`2026-08-21-finallq-request-withdrawal-adapter-design.md`)의
  ①(CP-002)→Task 1, ②(어댑터 서비스, 인증 흐름·요청 처리 7단계·상태 매핑 표)→Task 2~7,
  ③(파일 구조)→각 태스크의 Files 절이 정확히 그 구조를 만듦. "완료 기준" 6개 항목 전부
  태스크로 커버됨(401 재시도는 Task 7의 전용 테스트 2개로 왕복 검증).
- **Placeholder 스캔**: "TBD"·"나중에" 없음. 모든 코드 스텝에 완전한 코드 포함. InsuQ
  어댑터 작업에서 최종 리뷰로 걸러진 패턴(TransportError 폭넓은 캐치, HTTPStatusError·
  비-JSON 응답 처리, Agent Card 기반 스킬 목록 동적 도출, 응답 pydantic 검증 연결)을
  처음부터 반영해뒀다 — 같은 리뷰 라운드를 반복하지 않기 위함.
- **타입/이름 일관성**: `get_first_account_id(token, base_url, timeout=10.0)`,
  `request_transfer(token, from_account_id, amount, to_account_number, to_bank_code, memo,
  base_url, timeout=10.0)` 시그니처가 Task 5 구현·테스트·Task 7 구현·테스트에서 동일.
  `map_transfer_response(dict) -> dict` 키 이름이 Task 2의 `RequestWithdrawalResponse`
  필드명과 Task 7의 응답 바디에서 일치. 예외 클래스명(`AuthExpiredError`·`NoAccountError`·
  `UpstreamUnavailableError`·`UpstreamTimeoutError`·`LoginFailedError`)이 정의 위치(Task 4·5)와
  사용 위치(Task 7)에서 동일.
