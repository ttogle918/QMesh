# InsuQ `lookup-clause` A2A 어댑터 — 설계 (2026-08-21)

## 배경

QMesh(A2A_Q)의 A2A 구현은 오케스트레이터(:9000) + 3개 도메인 레포 어댑터로 구성될
예정이지만, 도메인 레포 3곳 모두 A2A 창구가 0개인 상태에서 한꺼번에 설계하면 범위가
너무 크다. 첫 조각으로 **InsuQ의 `lookup-clause` 스킬 어댑터 하나**를 골랐다 — 시나리오
문서(`docs/A2A_SCENARIOS.md`)가 이미 "정책 원장 등 선행조건이 없어 A2A를 가장 싸게
증명할 수 있는 스킬"로 지목한 것이고, InsuQ 자체 코어(약관 검색·인용·거부)는 이미
동작 중이다(`InsuQ/ai-engine`의 `POST /qa`).

InsuQ 레포는 이번 라운드에서 **읽기만** 한다 — 어댑터는 InsuQ 코드를 고치지 않고, 이미
떠 있는 `POST /qa`(FastAPI, 기본 `:8000`)를 HTTP로 호출하는 순수 번역 계층으로
`A2A_Q/adapters/insuq_a2a/`에 만든다. InsuQ 자체 문서(`docs/ref_insuq/A2A_API_SPEC.md`,
"명세 확정·구현 미착수")가 이미 전송 계층(엔드포인트·봉투·에러·거부 규약)을 정해놨으므로
그걸 그대로 따른다 — 새로 설계하지 않는다.

## 범위

### ① 계약 추가 — `lookup-clause` 신규 스킬
- `docs/schemas/lookup-clause.json` 신규 작성.
  - `request`: `question`(필수) · `domain`(선택, enum `track1`|`track4` — InsuQ 내부
    `QaRequest.domain` 값 그대로) · `product`(선택, `track4`일 때만 의미 있는 정확
    문자열 — 내부 `product_filter`에 대응) · `requester`(공통 requester 객체, 필수) ·
    `request_chain_id`(필수)
  - `response`: `status`(`completed`|`input-required`|`rejected`) · `answer`(선택) ·
    `verdict`(선택) · `evidence[]`(문자열, 기존 InsuQ 인용 형식·pattern 재사용) ·
    `confirm_required[]`(선택) · `rejection_reason`(선택, `no_evidence_found` 등 기존
    enum 재사용)
- `docs/agent_cards/insuq.json`의 `skills[]`에 `lookup-clause` 등록(id·설명·스키마 참조).
- 기존 5종 스키마를 바꾸는 게 아니라 순수 신규 추가라 CP 합의 절차(다른 레포 확인 대기)를
  거치지 않는다.

### ② 어댑터 서비스 — `A2A_Q/adapters/insuq_a2a/`
독립 FastAPI 앱. 포트 `:9102`(프로토타입 전용 — InsuQ가 나중에 Spring에 실제 구현할
`:9002` 자리와 구분하기 위해 다른 포트를 쓴다).

**엔드포인트** (InsuQ `A2A_API_SPEC.md` §1 그대로):
- `GET /.well-known/agent-card.json` — `docs/agent_cards/insuq.json`을 그대로 서빙
- `POST /a2a/skills/lookup-clause` — 실제 동작
- `POST /a2a/skills/{other_skill_id}` (나머지 4종) — `501` + `{"error": "not_implemented"}`로
  명시적 미구현 응답. Agent Card엔 5+1개 스킬이 다 선언돼 있지만 이 프로토타입은
  `lookup-clause`만 구현하므로, 나머지를 침묵 실패시키지 않고 명시한다.

**요청 처리 흐름** (`POST /a2a/skills/lookup-clause`):
1. 헤더 검사: `X-Request-Chain-Id` 헤더와 body의 `request_chain_id` 불일치 시
   `400 chain_id_mismatch` (스펙 §2)
2. body를 `lookup-clause` request 스키마로 검증 실패 시 `400 schema_validation_failed`
3. InsuQ `POST /qa`에 매핑해서 호출: `question`→`question`, `domain`→`domain`,
   `product`→`product_filter`, 나머지(persona 등)는 기본값
4. ai-engine 연결 실패 → `502 upstream_unavailable`, 타임아웃(10초) → `504 upstream_timeout`
5. `QaResponse`를 아래 규칙으로 A2A 응답에 매핑:
   - `needs_clarification == true` → `status: "input-required"`,
     `confirm_required: clarify_questions`
   - 그 외 `evidence`가 빈 배열 → `status: "rejected"`, `rejection_reason: "no_evidence_found"`
     (스키마에 `message` 필드는 없다 — 거부 사유는 `rejection_reason`으로 전달)
   - 그 외 → `status: "completed"`, `answer`·`verdict`·`confirm_required`(있으면) 그대로
     전달, `evidence`를 `{product} {policy_part} {article_no}[ {clause_no}][, p.{page}]`
     형식 문자열 배열로 조립(InsuQ 인용 규약과 동일 — 이미 CP-001로 스키마 `pattern`에
     고정돼 있음)
6. 인증(§3의 `oauth2-mock`)·`Idempotency-Key`(조회 스킬이라 선택, 스펙 §7)는 이번
   프로토타입에서는 **받되 검증하지 않는다** — M1 단계 목업 수준으로 맞춘다. 검증 로직
   추가는 후속 스코프.

### ③ 파일 구조
```
adapters/insuq_a2a/
├── __init__.py
├── main.py          # FastAPI 앱, 라우트 등록
├── schemas.py        # lookup-clause request/response pydantic 모델
├── insuq_client.py   # httpx로 InsuQ /qa 호출하는 얇은 클라이언트
├── mapping.py         # QaResponse -> lookup-clause response 변환 (①의 매핑 규칙)
└── agent_card.py      # docs/agent_cards/insuq.json 로드·서빙
tests/adapters/insuq_a2a/
├── test_mapping.py    # 매핑 규칙 단위 테스트 (completed/input-required/rejected 3분기)
├── test_main.py        # 엔드포인트 테스트 — httpx 클라이언트는 목(mock)으로 대체
└── test_agent_card.py  # Agent Card 서빙 확인
```

## 하지 않는 것 (범위 밖)
- 나머지 4개 InsuQ 스킬 구현 (원장 조회·비례보상 계산 등 필요, 이번 스코프 아님)
- FinAllQ·MaintQ 어댑터
- QMesh 오케스트레이터(:9000) — 이 어댑터를 호출할 상위 라우팅 계층
- 실제 인증·인가 검증 (M1 목업 수준으로 받기만 함)
- InsuQ 레포 코드 변경 (전부 읽기 전용 참조)
- 이 어댑터를 실제로 InsuQ 레포에 이식하는 작업 — 지금은 A2A_Q 안에서 프로토타입만

## 완료 기준
- `docs/schemas/lookup-clause.json` 존재, `docs/agent_cards/insuq.json`에 등록됨
- `adapters/insuq_a2a/` 기동 시 `:9102`에서 Agent Card·lookup-clause 스킬 응답
- ai-engine 목(mock) 기준 유닛 테스트로 completed/input-required/rejected 3개 분기 모두 검증
- ai-engine이 안 떠 있어도(502) / 응답이 늦어도(504) 어댑터가 명세대로 에러를 냄
- 나머지 4개 스킬 경로 호출 시 501 명시 응답
