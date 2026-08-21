# InsuQ lookup-clause A2A 어댑터 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** InsuQ의 기존 `POST /qa`(:8000, 이미 동작 중)를 감싸는 독립 FastAPI 어댑터를
`:9102`에 띄워, `lookup-clause` A2A 스킬 하나가 실제로 요청→근거 있는 응답 왕복을
증명하게 한다.

**Architecture:** `A2A_Q/adapters/insuq_a2a/`에 순수 번역 계층을 만든다. InsuQ 코드는
전혀 건드리지 않고 HTTP 클라이언트로만 호출한다. 전송 계층(엔드포인트·에러·거부 규약)은
InsuQ 자체 명세(`InsuQ/docs/A2A_API_SPEC.md`)를 그대로 따른다.

**Tech Stack:** Python 3.13, FastAPI, httpx(비동기 클라이언트), pydantic v2, pytest +
pytest-asyncio + pytest-httpx

## Global Constraints

- InsuQ 레포(`../InsuQ`)는 이 계획에서 **읽기만 한다** — 어떤 파일도 쓰지 않는다.
- 어댑터는 InsuQ의 `POST /qa` 요청/응답 스키마(`InsuQ/ai-engine/insuq_ai/api/schemas.py`의
  `QaRequest`/`QaResponse`)를 **import하지 않는다** — 레포 간 코드 결합을 만들지 않기
  위해 dict/JSON으로만 주고받는다.
- 어댑터 기본 포트는 `9102`(README의 InsuQ 정식 포트 `9002`와 구분되는 프로토타입 전용
  포트).
- InsuQ ai-engine base URL은 환경변수 `INSUQ_AI_ENGINE_BASE_URL`로 받고 기본값은
  `http://localhost:8000`.
- 에러 응답 형식은 `{"error": "<code>", "detail": "<string>", "request_chain_id": "<string 또는 null>"}` —
  InsuQ `A2A_API_SPEC.md` §8 그대로.
- `evidence` 문자열 포맷은 `{product} {policy_part} {article_no}[ {clause_no}][, p.{page}]` —
  `clause_no`·`page`가 없으면 그 토막을 통째로 생략한다(`p.None` 금지).
- 인증(`oauth2-mock`)·`Idempotency-Key` 검증은 이번 스코프에 넣지 않는다 — 받되 확인하지
  않는다.
- 실행 환경은 Windows + Git Bash. venv는 `.venv/Scripts/python.exe`로 호출한다(이미
  `.gitignore`에 `.venv/`가 있음).

---

### Task 1: 계약 파일 + Python 프로젝트 스캐폴딩

**Files:**
- Create: `docs/schemas/lookup-clause.json`
- Modify: `docs/agent_cards/insuq.json`
- Create: `requirements.txt` (repo root)
- Create: `pytest.ini` (repo root)
- Create: `adapters/insuq_a2a/__init__.py` (빈 파일)
- Create: `tests/__init__.py`, `tests/adapters/__init__.py`, `tests/adapters/insuq_a2a/__init__.py` (빈 파일들 — 패키지 인식용)

**Interfaces:** 없음(다른 태스크가 소비할 코드 인터페이스는 아직 없음). 단,
`docs/agent_cards/insuq.json`의 `skills[]`에 `id: "lookup-clause"`가 추가된다는 사실은
Task 5(agent_card.py 테스트)가 검증에 사용한다.

- [ ] **Step 1: `docs/schemas/lookup-clause.json` 작성**

```json
{
  "skill_id": "lookup-clause",
  "scenario": "제안 — 선행조건 없음",
  "direction": "MaintQ 또는 FinAllQ -> InsuQ",
  "description": "약관 원문에서 근거 조항을 검색해 인용과 함께 답한다. 계약별 답변이 아니라 약관 일반론만 답한다 — 정책 원장이 필요 없어 A2A 최초 검증용으로 제안됨.",
  "request": {
    "type": "object",
    "required": ["requester", "request_chain_id", "question"],
    "properties": {
      "requester": { "$ref": "#/definitions/requester" },
      "request_chain_id": { "type": "string" },
      "question": { "type": "string" },
      "domain": {
        "type": "string",
        "enum": ["track1", "track4"],
        "description": "실손(track1) | 화재·재물(track4). 미지정 시 InsuQ가 규칙 기반으로 분류"
      },
      "product": {
        "type": "string",
        "description": "정확 문자열 검색 필터. domain=track4일 때만 의미 있음"
      }
    }
  },
  "response": {
    "type": "object",
    "required": ["status", "evidence"],
    "properties": {
      "status": { "type": "string", "enum": ["completed", "input-required", "rejected"] },
      "rejection_reason": {
        "type": "string",
        "description": "status=rejected 일 때 필수. 거부는 장애가 아니므로 HTTP 200 으로 내려간다.",
        "enum": ["no_evidence_found", "citation_unverified", "out_of_corpus", "policy_not_found"]
      },
      "answer": { "type": "string" },
      "verdict": { "type": "string" },
      "confirm_required": {
        "type": "array",
        "description": "status=input-required 일 때 채워지는 되묻기 질문 목록",
        "items": { "type": "string" }
      },
      "evidence": {
        "type": "array",
        "description": "인용 형식 고정. `{상품명} {policy_part} {article_no}[ {clause_no}][, p.{page}]` — policy_part 생략 금지(파트 간 조 번호가 충돌해, 조 번호만 대조하면 다른 파트의 같은 조 번호를 지어내도 환각 탐지를 통과한다).",
        "items": { "type": "string", "pattern": "^.+ .+ 제\\d+조( [①-⑳\\d]+항?)?(, p\\.\\d+)?$" }
      }
    }
  },
  "definitions": {
    "requester": {
      "type": "object",
      "properties": {
        "finallq_company_id": { "type": "string" },
        "building_id": { "type": "string" },
        "policy_id": { "type": "string" }
      }
    }
  }
}
```

- [ ] **Step 2: `docs/agent_cards/insuq.json`의 `skills[]` 배열 끝(`claim-insurance` 다음)에
  추가**

```json
    ,
    {
      "id": "lookup-clause",
      "name": "약관 근거 조회",
      "description": "약관 원문에서 근거 조항을 검색해 인용과 함께 답한다. 계약별 답변이 아니라 약관 일반론만 답한다 — 정책 원장 불필요, A2A 최초 검증용 제안 스킬.",
      "scenario": "제안 — 선행조건 없음",
      "schema": "schemas/lookup-clause.json"
    }
```

(기존 `claim-insurance` 항목의 닫는 `}` 뒤에 콤마를 추가하고 위 객체를 이어 붙인다 —
JSON 배열이 깨지지 않게 주의)

- [ ] **Step 3: JSON 유효성 확인**

Run: `python -c "import json; json.load(open('docs/schemas/lookup-clause.json', encoding='utf-8')); json.load(open('docs/agent_cards/insuq.json', encoding='utf-8')); print('ok')"`
Expected: `ok` 출력, 예외 없음

- [ ] **Step 4: `requirements.txt` 작성 (repo root)**

```
fastapi>=0.115,<0.116
httpx>=0.27,<0.28
pydantic>=2.9,<3
uvicorn>=0.30,<0.31
pytest>=8.3,<9
pytest-asyncio>=0.24,<0.25
pytest-httpx>=0.30,<0.31
```

- [ ] **Step 5: `pytest.ini` 작성 (repo root)**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 6: venv 생성 및 의존성 설치**

Run:
```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install --upgrade pip
.venv/Scripts/python.exe -m pip install -r requirements.txt
```
Expected: 설치 완료, 에러 없음

- [ ] **Step 7: 패키지 인식용 빈 파일 생성**

Create `adapters/insuq_a2a/__init__.py`, `tests/__init__.py`, `tests/adapters/__init__.py`,
`tests/adapters/insuq_a2a/__init__.py` — 전부 내용 없는 빈 파일.

- [ ] **Step 8: 커밋**

```bash
git add docs/schemas/lookup-clause.json docs/agent_cards/insuq.json requirements.txt \
  pytest.ini adapters/insuq_a2a/__init__.py tests/__init__.py tests/adapters/__init__.py \
  tests/adapters/insuq_a2a/__init__.py
git commit -m "feat(insuq-adapter): lookup-clause 계약 추가 + Python 프로젝트 스캐폴딩"
```

---

### Task 2: `schemas.py` — lookup-clause pydantic 모델

**Files:**
- Create: `adapters/insuq_a2a/schemas.py`
- Test: `tests/adapters/insuq_a2a/test_schemas.py`

**Interfaces:**
- Consumes: 없음(Task 1의 JSON 계약 내용을 사람이 눈으로 옮겨적음)
- Produces: `class Requester(BaseModel)` (`finallq_company_id: str | None`,
  `building_id: str | None`, `policy_id: str | None`, 전부 기본값 `None`).
  `class LookupClauseRequest(BaseModel)` (`requester: Requester`, `request_chain_id: str`,
  `question: str`, `domain: Literal["track1", "track4"] | None = None`,
  `product: str | None = None`). `class LookupClauseResponse(BaseModel)`
  (`status: str`, `rejection_reason: str | None = None`, `answer: str | None = None`,
  `verdict: str | None = None`, `confirm_required: list[str] = []`,
  `evidence: list[str] = []`). Task 3(mapping.py)·Task 6(main.py)이 이 세 클래스를
  그대로 가져다 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/insuq_a2a/test_schemas.py`:
```python
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
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/insuq_a2a/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.insuq_a2a.schemas'`

- [ ] **Step 3: `adapters/insuq_a2a/schemas.py` 구현**

```python
"""lookup-clause A2A 스킬 request/response pydantic 모델.

원본 계약은 docs/schemas/lookup-clause.json — 여기 필드는 그 스키마와 반드시 일치해야
한다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Requester(BaseModel):
    finallq_company_id: str | None = None
    building_id: str | None = None
    policy_id: str | None = None


class LookupClauseRequest(BaseModel):
    requester: Requester
    request_chain_id: str
    question: str
    domain: Literal["track1", "track4"] | None = None
    product: str | None = None


class LookupClauseResponse(BaseModel):
    status: str
    rejection_reason: str | None = None
    answer: str | None = None
    verdict: str | None = None
    confirm_required: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/insuq_a2a/test_schemas.py -v`
Expected: PASS (5/5)

- [ ] **Step 5: 커밋**

```bash
git add adapters/insuq_a2a/schemas.py tests/adapters/insuq_a2a/test_schemas.py
git commit -m "feat(insuq-adapter): lookup-clause request/response pydantic 모델"
```

---

### Task 3: `mapping.py` — QaResponse → lookup-clause response 변환

**Files:**
- Create: `adapters/insuq_a2a/mapping.py`
- Test: `tests/adapters/insuq_a2a/test_mapping.py`

**Interfaces:**
- Consumes: 없음(순수 함수, InsuQ의 실제 응답 JSON 모양을 dict로 흉내낸 테스트 fixture만
  사용)
- Produces: `def map_qa_response(qa_response: dict) -> dict` — Task 6(main.py)이 이 함수를
  그대로 호출해서 HTTP 응답 body를 만든다. 반환값의 키는 Task 2의 `LookupClauseResponse`
  필드와 일치한다(`status`·`rejection_reason`·`answer`·`verdict`·`confirm_required`·
  `evidence`).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/insuq_a2a/test_mapping.py`:
```python
from adapters.insuq_a2a.mapping import map_qa_response


def test_completed_with_evidence():
    qa_response = {
        "route": "verdict",
        "answer": "자기부담금은 보통약관 제5조에 따라 20%입니다.",
        "verdict": "지급 사유에 해당할 가능성이 높음",
        "evidence": [
            {
                "product": "든든실손4세대",
                "policy_part": "보통약관",
                "article_no": "제5조",
                "clause_no": "①",
                "page": 13,
                "quote": "자기부담금은 20%로 한다.",
            },
            {
                "product": "든든실손4세대",
                "policy_part": "특별약관",
                "article_no": "제1조",
                "clause_no": None,
                "page": None,
                "quote": "특약 적용 범위는...",
            },
        ],
        "needs_clarification": False,
        "clarify_questions": [],
    }

    result = map_qa_response(qa_response)

    assert result["status"] == "completed"
    assert result["answer"] == qa_response["answer"]
    assert result["verdict"] == qa_response["verdict"]
    assert result["evidence"] == [
        "든든실손4세대 보통약관 제5조 ①, p.13",
        "든든실손4세대 특별약관 제1조",
    ]


def test_rejected_when_no_evidence():
    qa_response = {
        "route": "simple_lookup",
        "answer": None,
        "verdict": None,
        "evidence": [],
        "needs_clarification": False,
        "clarify_questions": [],
    }

    result = map_qa_response(qa_response)

    assert result["status"] == "rejected"
    assert result["rejection_reason"] == "no_evidence_found"
    assert result["evidence"] == []


def test_input_required_when_needs_clarification():
    qa_response = {
        "route": "clarify",
        "answer": None,
        "verdict": None,
        "evidence": [],
        "needs_clarification": True,
        "clarify_questions": ["가입하신 상품명을 알려주세요", "가입 시기를 알려주세요"],
    }

    result = map_qa_response(qa_response)

    assert result["status"] == "input-required"
    assert result["confirm_required"] == qa_response["clarify_questions"]
    assert result["evidence"] == []


def test_needs_clarification_takes_priority_over_empty_evidence():
    """evidence가 비어있어도 needs_clarification=True면 rejected가 아니라 input-required다."""
    qa_response = {
        "evidence": [],
        "needs_clarification": True,
        "clarify_questions": ["상품명을 알려주세요"],
    }

    result = map_qa_response(qa_response)

    assert result["status"] == "input-required"
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/insuq_a2a/test_mapping.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.insuq_a2a.mapping'`

- [ ] **Step 3: `adapters/insuq_a2a/mapping.py` 구현**

```python
"""InsuQ ai-engine QaResponse(dict) -> lookup-clause A2A response(dict) 변환.

원본 응답 모양: InsuQ/ai-engine/insuq_ai/api/schemas.py 의 QaResponse. 그 파이썬
클래스는 import하지 않는다(레포 간 결합 방지) — ai-engine이 HTTP로 실제로 돌려주는
JSON을 dict로 그대로 받는다.

분기 규칙:
1. needs_clarification=True -> input-required (evidence가 비어있어도 우선)
2. 그 외 evidence가 비어있음 -> rejected(no_evidence_found)
3. 그 외 -> completed
"""

from __future__ import annotations


def map_qa_response(qa_response: dict) -> dict:
    if qa_response.get("needs_clarification"):
        return {
            "status": "input-required",
            "confirm_required": qa_response.get("clarify_questions", []),
            "evidence": [],
        }

    formatted_evidence = [_format_evidence(item) for item in qa_response.get("evidence", [])]

    if not formatted_evidence:
        return {
            "status": "rejected",
            "rejection_reason": "no_evidence_found",
            "evidence": [],
        }

    return {
        "status": "completed",
        "answer": qa_response.get("answer"),
        "verdict": qa_response.get("verdict"),
        "evidence": formatted_evidence,
    }


def _format_evidence(item: dict) -> str:
    """"{product} {policy_part} {article_no}[ {clause_no}][, p.{page}]" 형식 문자열 조립.

    clause_no·page 가 없으면(None) 그 토막을 통째로 생략한다 — "p.None"이 나가면
    인용 신뢰가 무너진다.
    """
    text = f"{item['product']} {item['policy_part']} {item['article_no']}"
    clause_no = item.get("clause_no")
    if clause_no:
        text += f" {clause_no}"
    page = item.get("page")
    if page is not None:
        text += f", p.{page}"
    return text
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/insuq_a2a/test_mapping.py -v`
Expected: PASS (4/4)

- [ ] **Step 5: 커밋**

```bash
git add adapters/insuq_a2a/mapping.py tests/adapters/insuq_a2a/test_mapping.py
git commit -m "feat(insuq-adapter): QaResponse -> lookup-clause 응답 매핑 로직"
```

---

### Task 4: `insuq_client.py` — InsuQ `POST /qa` HTTP 클라이언트

**Files:**
- Create: `adapters/insuq_a2a/insuq_client.py`
- Test: `tests/adapters/insuq_a2a/test_insuq_client.py`

**Interfaces:**
- Consumes: 없음
- Produces: `class UpstreamUnavailableError(Exception)`,
  `class UpstreamTimeoutError(Exception)`,
  `async def call_qa(question: str, domain: str | None, product: str | None, base_url: str, timeout: float = 10.0) -> dict`.
  Task 6(main.py)이 이 함수와 두 예외 클래스를 그대로 가져다 쓴다 — `call_qa`의 반환값
  (dict)은 그대로 Task 3의 `map_qa_response()` 입력이 된다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/insuq_a2a/test_insuq_client.py`:
```python
import httpx
import pytest

from adapters.insuq_a2a.insuq_client import (
    UpstreamTimeoutError,
    UpstreamUnavailableError,
    call_qa,
)


async def test_call_qa_maps_domain_and_product_to_qa_request(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/qa",
        method="POST",
        json={"route": "simple_lookup", "evidence": [], "needs_clarification": False},
    )

    result = await call_qa(
        question="자기부담금이 얼마인가요",
        domain="track4",
        product="든든실손4세대",
        base_url="http://test-insuq",
    )

    assert result == {"route": "simple_lookup", "evidence": [], "needs_clarification": False}
    request = httpx_mock.get_requests()[0]
    sent_body = request.read()
    import json

    payload = json.loads(sent_body)
    assert payload["question"] == "자기부담금이 얼마인가요"
    assert payload["domain"] == "track4"
    assert payload["product_filter"] == "든든실손4세대"


async def test_call_qa_omits_optional_fields_when_none(httpx_mock):
    httpx_mock.add_response(
        url="http://test-insuq/qa", method="POST", json={"evidence": [], "needs_clarification": False}
    )

    await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")

    request = httpx_mock.get_requests()[0]
    import json

    payload = json.loads(request.read())
    assert "domain" not in payload
    assert "product_filter" not in payload


async def test_call_qa_raises_upstream_unavailable_on_connect_error(httpx_mock):
    httpx_mock.add_exception(httpx.ConnectError("connection refused"))

    with pytest.raises(UpstreamUnavailableError):
        await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")


async def test_call_qa_raises_upstream_timeout_on_timeout(httpx_mock):
    httpx_mock.add_exception(httpx.TimeoutException("timed out"))

    with pytest.raises(UpstreamTimeoutError):
        await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")


async def test_call_qa_raises_upstream_unavailable_on_5xx(httpx_mock):
    httpx_mock.add_response(url="http://test-insuq/qa", method="POST", status_code=500)

    with pytest.raises(UpstreamUnavailableError):
        await call_qa(question="q", domain=None, product=None, base_url="http://test-insuq")
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/insuq_a2a/test_insuq_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.insuq_a2a.insuq_client'`

- [ ] **Step 3: `adapters/insuq_a2a/insuq_client.py` 구현**

```python
"""InsuQ ai-engine POST /qa 호출 클라이언트.

InsuQ 코드는 건드리지 않는다 — 이미 떠 있는 HTTP 엔드포인트를 그대로 호출한다.
에러 매핑은 InsuQ/docs/A2A_API_SPEC.md §8을 따른다: 연결 불가 -> 502, 타임아웃 -> 504.
"""

from __future__ import annotations

import httpx


class UpstreamUnavailableError(Exception):
    """ai-engine에 연결할 수 없거나 5xx를 반환했을 때 (§8: 502 upstream_unavailable)."""


class UpstreamTimeoutError(Exception):
    """ai-engine 응답이 타임아웃됐을 때 (§8: 504 upstream_timeout)."""


async def call_qa(
    question: str,
    domain: str | None,
    product: str | None,
    base_url: str,
    timeout: float = 10.0,
) -> dict:
    """InsuQ ai-engine의 POST /qa를 호출하고 QaResponse(dict)를 반환한다.

    domain -> QaRequest.domain, product -> QaRequest.product_filter로 매핑한다
    (InsuQ ai-engine/insuq_ai/api/schemas.py 참조 — product_filter는 정확 문자열 필터).
    """
    payload: dict = {"question": question}
    if domain is not None:
        payload["domain"] = domain
    if product is not None:
        payload["product_filter"] = product

    try:
        async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as client:
            response = await client.post("/qa", json=payload)
    except httpx.TimeoutException as exc:
        raise UpstreamTimeoutError(str(exc)) from exc
    except httpx.ConnectError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    if response.status_code >= 500:
        raise UpstreamUnavailableError(f"ai-engine returned {response.status_code}")

    response.raise_for_status()
    return response.json()
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/insuq_a2a/test_insuq_client.py -v`
Expected: PASS (5/5)

- [ ] **Step 5: 커밋**

```bash
git add adapters/insuq_a2a/insuq_client.py tests/adapters/insuq_a2a/test_insuq_client.py
git commit -m "feat(insuq-adapter): InsuQ POST /qa 호출 클라이언트"
```

---

### Task 5: `agent_card.py` — Agent Card 로더

**Files:**
- Create: `adapters/insuq_a2a/agent_card.py`
- Test: `tests/adapters/insuq_a2a/test_agent_card.py`

**Interfaces:**
- Consumes: `docs/agent_cards/insuq.json` (Task 1에서 `lookup-clause` 등록됨)
- Produces: `def load_agent_card() -> dict`. Task 6(main.py)이 `GET
  /.well-known/agent-card.json` 핸들러에서 그대로 호출한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/insuq_a2a/test_agent_card.py`:
```python
from adapters.insuq_a2a.agent_card import load_agent_card


def test_load_agent_card_returns_insuq_card_with_lookup_clause():
    card = load_agent_card()

    assert card["name"] == "InsuQ"
    skill_ids = [s["id"] for s in card["skills"]]
    assert "lookup-clause" in skill_ids
    assert "verify-collateral-insurance" in skill_ids
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/insuq_a2a/test_agent_card.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.insuq_a2a.agent_card'`

- [ ] **Step 3: `adapters/insuq_a2a/agent_card.py` 구현**

```python
"""InsuQ Agent Card 로더 — docs/agent_cards/insuq.json 을 그대로 서빙한다.

파일을 복제하지 않는다 — 원본은 docs/agent_cards/에 있고(A2A_Q 계약 문서 원칙, drift
방지), 여기서는 읽기만 한다.
"""

from __future__ import annotations

import json
from pathlib import Path

_AGENT_CARD_PATH = Path(__file__).resolve().parents[2] / "docs" / "agent_cards" / "insuq.json"


def load_agent_card() -> dict:
    return json.loads(_AGENT_CARD_PATH.read_text(encoding="utf-8"))
```

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/insuq_a2a/test_agent_card.py -v`
Expected: PASS (1/1)

- [ ] **Step 5: 커밋**

```bash
git add adapters/insuq_a2a/agent_card.py tests/adapters/insuq_a2a/test_agent_card.py
git commit -m "feat(insuq-adapter): Agent Card 로더"
```

---

### Task 6: `main.py` — FastAPI 앱 배선

**Files:**
- Create: `adapters/insuq_a2a/main.py`
- Test: `tests/adapters/insuq_a2a/test_main.py`

**Interfaces:**
- Consumes: `load_agent_card()`(Task 5), `call_qa()`·`UpstreamUnavailableError`·
  `UpstreamTimeoutError`(Task 4), `map_qa_response()`(Task 3), `LookupClauseRequest`
  (Task 2)
- Produces: `app`(FastAPI 인스턴스) — 이 태스크가 마지막이라 이후 태스크가 소비할 것은
  없다. 이 서비스를 실행하는 방법은 이 태스크의 Step 6에 기록한다.

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/adapters/insuq_a2a/test_main.py`:
```python
from fastapi.testclient import TestClient

from adapters.insuq_a2a import main
from adapters.insuq_a2a.insuq_client import UpstreamTimeoutError, UpstreamUnavailableError

client = TestClient(main.app)


def test_agent_card_endpoint_returns_insuq_card():
    resp = client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200
    assert resp.json()["name"] == "InsuQ"


def test_lookup_clause_success(monkeypatch):
    async def fake_call_qa(**kwargs):
        return {
            "answer": "자기부담금은 20%입니다.",
            "verdict": "지급 사유에 해당할 가능성이 높음",
            "evidence": [
                {
                    "product": "든든실손4세대",
                    "policy_part": "보통약관",
                    "article_no": "제5조",
                    "clause_no": None,
                    "page": 13,
                }
            ],
            "needs_clarification": False,
            "clarify_questions": [],
        }

    monkeypatch.setattr(main, "call_qa", fake_call_qa)

    body = {
        "requester": {},
        "request_chain_id": "chain-1",
        "question": "자기부담금이 얼마인가요",
    }
    resp = client.post(
        "/a2a/skills/lookup-clause",
        json=body,
        headers={"X-Request-Chain-Id": "chain-1"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["evidence"] == ["든든실손4세대 보통약관 제5조, p.13"]


def test_lookup_clause_chain_id_mismatch():
    body = {"requester": {}, "request_chain_id": "chain-1", "question": "q"}
    resp = client.post(
        "/a2a/skills/lookup-clause",
        json=body,
        headers={"X-Request-Chain-Id": "chain-DIFFERENT"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "chain_id_mismatch"


def test_lookup_clause_schema_validation_failed():
    body = {"requester": {}, "request_chain_id": "chain-1"}  # question 없음
    resp = client.post(
        "/a2a/skills/lookup-clause",
        json=body,
        headers={"X-Request-Chain-Id": "chain-1"},
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "schema_validation_failed"


def test_lookup_clause_upstream_unavailable(monkeypatch):
    async def fake_call_qa(**kwargs):
        raise UpstreamUnavailableError("boom")

    monkeypatch.setattr(main, "call_qa", fake_call_qa)

    body = {"requester": {}, "request_chain_id": "chain-1", "question": "q"}
    resp = client.post(
        "/a2a/skills/lookup-clause",
        json=body,
        headers={"X-Request-Chain-Id": "chain-1"},
    )

    assert resp.status_code == 502
    assert resp.json()["error"] == "upstream_unavailable"


def test_lookup_clause_upstream_timeout(monkeypatch):
    async def fake_call_qa(**kwargs):
        raise UpstreamTimeoutError("boom")

    monkeypatch.setattr(main, "call_qa", fake_call_qa)

    body = {"requester": {}, "request_chain_id": "chain-1", "question": "q"}
    resp = client.post(
        "/a2a/skills/lookup-clause",
        json=body,
        headers={"X-Request-Chain-Id": "chain-1"},
    )

    assert resp.status_code == 504
    assert resp.json()["error"] == "upstream_timeout"


def test_unimplemented_known_skill_returns_501():
    resp = client.post("/a2a/skills/verify-collateral-insurance", json={})
    assert resp.status_code == 501
    assert resp.json()["error"] == "not_implemented"


def test_unknown_skill_returns_404():
    resp = client.post("/a2a/skills/not-a-real-skill", json={})
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_skill"
```

- [ ] **Step 2: 테스트 실행해서 실패 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/insuq_a2a/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'adapters.insuq_a2a.main'`

- [ ] **Step 3: `adapters/insuq_a2a/main.py` 구현**

```python
"""InsuQ lookup-clause A2A 어댑터 — 독립 FastAPI 서비스 (기본 포트 9102).

InsuQ 코드를 건드리지 않고 기존 POST /qa(:8000)를 A2A 봉투로 감싼다. 전송 계층
규약은 InsuQ/docs/A2A_API_SPEC.md 를 따른다. lookup-clause 외 4개 스킬은 Agent
Card에는 선언돼 있지만 이 프로토타입에서는 미구현 — 501로 명시 응답한다.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from adapters.insuq_a2a.agent_card import load_agent_card
from adapters.insuq_a2a.insuq_client import UpstreamTimeoutError, UpstreamUnavailableError, call_qa
from adapters.insuq_a2a.mapping import map_qa_response
from adapters.insuq_a2a.schemas import LookupClauseRequest

INSUQ_BASE_URL = os.environ.get("INSUQ_AI_ENGINE_BASE_URL", "http://localhost:8000")

KNOWN_SKILL_IDS = [
    "advise-policy-renewal",
    "verify-collateral-insurance",
    "notify-asset-change",
    "notify-risk-change",
    "claim-insurance",
]

app = FastAPI(title="InsuQ A2A Adapter (prototype)")


@app.get("/.well-known/agent-card.json")
async def agent_card_endpoint() -> dict:
    return load_agent_card()


@app.post("/a2a/skills/lookup-clause")
async def lookup_clause(request: Request) -> JSONResponse:
    body = await request.json()

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
        parsed = LookupClauseRequest.model_validate(body)
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
        qa_response = await call_qa(
            question=parsed.question,
            domain=parsed.domain,
            product=parsed.product,
            base_url=INSUQ_BASE_URL,
        )
    except UpstreamUnavailableError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "error": "upstream_unavailable",
                "detail": str(exc),
                "request_chain_id": parsed.request_chain_id,
            },
        )
    except UpstreamTimeoutError as exc:
        return JSONResponse(
            status_code=504,
            content={
                "error": "upstream_timeout",
                "detail": str(exc),
                "request_chain_id": parsed.request_chain_id,
            },
        )

    mapped = map_qa_response(qa_response)
    return JSONResponse(status_code=200, content=mapped)


@app.post("/a2a/skills/{skill_id}")
async def unimplemented_skill(skill_id: str) -> JSONResponse:
    if skill_id not in KNOWN_SKILL_IDS:
        return JSONResponse(
            status_code=404,
            content={
                "error": "unknown_skill",
                "detail": f"'{skill_id}' is not declared in the Agent Card",
            },
        )
    return JSONResponse(
        status_code=501,
        content={
            "error": "not_implemented",
            "detail": f"'{skill_id}' is not implemented in this prototype adapter",
        },
    )
```

**중요 — `test_main.py`의 `monkeypatch.setattr(main, "call_qa", fake_call_qa)`가 동작하려면**
`main.py`가 `from adapters.insuq_a2a.insuq_client import call_qa`로 이름을 모듈
네임스페이스에 들여와야 한다(위 코드처럼). `insuq_client.call_qa(...)`로 모듈 경유
호출하면 monkeypatch가 안 먹는다 — 위 구현처럼 `call_qa(...)`를 직접 호출하는 형태를
유지할 것.

- [ ] **Step 4: 테스트 실행해서 통과 확인**

Run: `.venv/Scripts/python.exe -m pytest tests/adapters/insuq_a2a/test_main.py -v`
Expected: PASS (8/8)

- [ ] **Step 5: 전체 스위트 한 번에 실행**

Run: `.venv/Scripts/python.exe -m pytest tests/ -v`
Expected: PASS (전체 — schemas 5 + mapping 4 + insuq_client 5 + agent_card 1 + main 8 = 23개)

- [ ] **Step 6: 로컬 기동 확인 (선택 — InsuQ ai-engine이 떠 있지 않아도 서버 자체는
  뜬다)**

Run:
```bash
.venv/Scripts/python.exe -m uvicorn adapters.insuq_a2a.main:app --port 9102 &
sleep 2
curl -s http://localhost:9102/.well-known/agent-card.json | head -c 200
kill %1
```
Expected: Agent Card JSON의 앞부분(`{"name":"InsuQ",...`)이 출력됨. InsuQ ai-engine이
안 떠 있으면 `/a2a/skills/lookup-clause` 호출은 502를 내겠지만, 서버 자체 기동과
Agent Card 서빙은 이 단계에서 확인된다.

- [ ] **Step 7: 커밋**

```bash
git add adapters/insuq_a2a/main.py tests/adapters/insuq_a2a/test_main.py
git commit -m "feat(insuq-adapter): FastAPI 앱 배선 — lookup-clause 엔드포인트 + 에러 매핑"
```

---

## Self-Review 완료 기록

- **Spec 커버리지**: 설계 스펙(`2026-08-21-insuq-lookup-clause-adapter-design.md`)의
  ①(계약 추가)→Task 1, ②(어댑터 서비스, 5단계 요청 흐름)→Task 2~6, ③(파일 구조)→
  Task 1~6의 Files 절이 정확히 그 구조를 만듦. "나머지 4개 스킬 501"→Task 6.
  "완료 기준" 5개 항목 전부 태스크로 커버됨(Agent Card 등록 확인은 Task 5+Task 6
  테스트가 이중으로 검증).
- **Placeholder 스캔**: "TBD"·"나중에" 없음. 모든 코드 스텝에 완전한 코드 포함.
- **타입/이름 일관성**: `call_qa(question, domain, product, base_url, timeout=10.0)`
  시그니처가 Task 4 구현·Task 4 테스트·Task 6 구현·Task 6 테스트에서 동일. `map_qa_response(dict) -> dict`
  키 이름(`status`/`rejection_reason`/`answer`/`verdict`/`confirm_required`/`evidence`)이
  Task 2의 `LookupClauseResponse` 필드명과 Task 6의 응답 바디에서 전부 일치.
  `UpstreamUnavailableError`/`UpstreamTimeoutError` 클래스명이 Task 4→Task 6에서 동일.
