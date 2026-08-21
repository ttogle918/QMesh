# FinAllQ `request-withdrawal` A2A 어댑터 — 설계 (2026-08-21)

## 배경

InsuQ `lookup-clause` 어댑터에 이은 A2A 구현의 두 번째 조각으로 FinAllQ의 `request-withdrawal`
(S5, 출금 요청)을 골랐다 — 시나리오 문서가 "레일은 다 깔렸고 문(창구)만 없다"(75% 준비도)로
지목한 스킬이다. FinAllQ 레포 자체 조사(`docs/troubleshooting/2026-08-20_a2a-contracts-drift.md`)로
이체 요청·2단 승인 흐름(`TransferController`, Sprint 7~14)이 실제로 동작 중임을 확인했다.

InsuQ 때와 달리 이번엔 **인증 문제**가 있다 — FinAllQ의 `POST /api/v1/transfers`는
`@AuthenticationPrincipal`로 실제 로그인 세션을 요구하고, 요청자 ID를 body가 아니라 인증
주체에서 강제로 가져온다(파트너 자격증명·머신 신원은 백로그 131·132로 여전히 미착수).
그리고 **계약 갭**도 있다 — 기존 `request-withdrawal.json` 스키마엔 계좌번호 필드가 없어
FinAllQ의 실제 이체 API를 호출할 방법이 없다.

FinAllQ 레포는 이번 라운드에서 **읽기만** 한다 — 어댑터는 FinAllQ 코드를 고치지 않고
기존 REST API(`/api/v1/auth/login`, `/api/v1/accounts`, `/api/v1/transfers`)를 호출하는
번역 계층으로 `A2A_Q/adapters/finallq_a2a/`에 만든다.

## 범위

### ① CP-002 — `request-withdrawal` 스키마에 계좌 필드 추가 (제안)
- `docs/schemas/request-withdrawal.json`의 `request.properties`에 추가:
  - `to_account_number`(필수, `string`, FinAllQ 계좌번호 패턴 `^[0-9-]{4,20}$`과 동일한
    `pattern`) — 거래처(수취인) 계좌번호
  - `to_bank_code`(선택, `string`) — 수취 은행 코드
- `required` 배열에 `to_account_number` 추가
- 각 필드 `description`에 `PROPOSED(A2A_Q, 2026-08-21): ...` 접두사(CP-001과 동일 패턴)
- `from_account_id`는 스키마에 넣지 않는다 — "어느 계좌에서 나가는지"는 **actor(어댑터가
  로그인한 서비스 계정)에 딸린 정보**이지 caller(MaintQ)가 지정할 subject가 아니다
  (`A2A_IDENTITY.md` 결정 1의 actor/subject 분리 원칙 재적용)
- `docs/A2A_CONTRACT_CHANGES.md`에 **CP-002**로 신규 등재, 상태는 `🟡 제안 — MaintQ 확인
  대기`(MaintQ가 실제로 `to_account_number`를 채워 보낼 수 있는지 — 발주서에 거래처 계좌
  정보가 있는지 — 확인 필요)

### ② 어댑터 서비스 — `A2A_Q/adapters/finallq_a2a/`
독립 FastAPI 앱. 포트 `:9101`(프로토타입 전용 — README의 정식 `:9001`과 구분, InsuQ
어댑터가 `:9102`를 쓴 것과 같은 이유).

**인증 흐름**:
- 서비스 계정 자격증명은 환경변수 `FINALLQ_SERVICE_EMAIL`/`FINALLQ_SERVICE_PASSWORD`로 받는다
  (FinAllQ 시드 데이터의 `demo-employee@finallq.example` 계정을 가리키는 것을 전제 — 실제
  값은 코드에 넣지 않는다)
- 어댑터는 최초 요청 시(또는 토큰 만료 후) `POST /api/v1/auth/login`을 호출해 `accessToken`을
  얻고 프로세스 메모리에 캐싱한다. `401`을 받으면 캐시를 버리고 1회 재로그인 후 재시도한다.
- **이번 프로토타입에서는 refresh 토큰·만료 시각 파싱을 넣지 않는다** — 401 발생 시
  재로그인하는 단순 재시도만 구현한다(YAGNI, 실제 만료 정책은 이 스코프 밖).

**엔드포인트**:
- `GET /.well-known/agent-card.json` — `docs/agent_cards/finallq.json`을 그대로 서빙
- `POST /a2a/skills/request-withdrawal` — 실제 동작
- `POST /a2a/skills/{other_skill_id}` (나머지 6종) — `501` + `{"error": "not_implemented"}`

**요청 처리 흐름** (`POST /a2a/skills/request-withdrawal`):
1. 헤더 검사: `X-Request-Chain-Id`와 body의 `request_chain_id` 불일치 → `400 chain_id_mismatch`
2. body를 `request-withdrawal` request 스키마(CP-002 반영본)로 검증 실패 → `400 schema_validation_failed`
3. 서비스 계정 JWT 획득(캐시 우선, 없으면 로그인)
4. `GET /api/v1/accounts`(page=0) 호출 → 응답의 첫 번째 계좌 `accountId`를 `from_account_id`로
   사용. 계좌가 0건이면 `502 upstream_unavailable`("service account has no account")
5. `POST /api/v1/transfers`에 매핑해서 호출:
   `fromAccountId`←④의 accountId, `amount`←`amount`, `toBankCode`←`to_bank_code`,
   `toAccountNumber`←`to_account_number`, `memo`←`purpose`(100자 초과 시 자름 — FinAllQ
   `MEMO_MAX_LENGTH=100` 제약)
6. FinAllQ 연결 실패/5xx → `502 upstream_unavailable`, 타임아웃(10초) → `504 upstream_timeout`,
   FinAllQ가 400(Bean Validation 실패 등)을 돌려주면 → `400 schema_validation_failed`로
   변환(InsuQ 스펙의 에러 규약과 통일)
7. `TransferResponseDto.status`를 아래 규칙으로 A2A 응답에 매핑:

| FinAllQ `TransferStatus` | A2A `status` | 비고 |
|---|---|---|
| `PENDING`, `APPROVED`, `PENDING_2FA` | `input-required` | 재무 승인 대기 — 사람 승인 필요 |
| `BLOCKED` | `rejected` | `fds_check: "hold"` 동반 |
| `REJECTED` | `rejected` | `reject_reason`에 FinAllQ `message` 전달 |
| `COMPLETED` | `completed` | `executed_at`에 FinAllQ `requestedAt` 전달(즉시 완료 시나리오 대비) |

- `req_id`에는 FinAllQ `requestId`를 문자열로 변환해 전달
- `approved_by_finance`·`requires_escalation`은 이번 프로토타입에서 채우지 않는다
  (`TransferResponseDto`에 대응 필드가 없음 — FinAllQ가 결재 상세를 별도 조회 API로
  노출하고 있어(§`getApprovalDetail`), 필요해지면 후속 스코프에서 그 API를 추가로 호출)

**하지 않는 것 — 승인/거절 엔드포인트는 이 스코프 밖**:
- FinAllQ의 `/approve`·`/reject`는 호출하지 않는다 — A2A 관통 원칙("AI는 요청까지만, 실행은
  사람 승인 뒤")과 일치하며, 재무 담당자는 FinAllQ 자체 화면에서 승인한다.

### ③ 파일 구조
```
adapters/finallq_a2a/
├── __init__.py
├── main.py             # FastAPI 앱, 라우트 등록
├── schemas.py           # request-withdrawal request/response pydantic 모델 (CP-002 반영)
├── auth.py               # 서비스 계정 로그인 + 토큰 캐시
├── finallq_client.py     # httpx로 /accounts, /transfers 호출
├── mapping.py             # TransferResponseDto -> A2A 응답 변환 (②-7 표)
└── agent_card.py          # docs/agent_cards/finallq.json 로드·서빙
tests/adapters/finallq_a2a/
├── test_schemas.py
├── test_auth.py           # 로그인 성공/401 재시도/캐시 재사용
├── test_finallq_client.py # /accounts, /transfers 호출 + 에러 매핑
├── test_mapping.py         # TransferStatus 6종 -> A2A status 매핑 전수
├── test_main.py            # 엔드포인트 통합(모두 목으로 대체)
└── test_agent_card.py
```

## 하지 않는 것 (범위 밖)
- MaintQ 어댑터, QMesh 오케스트레이터
- FinAllQ의 나머지 6개 스킬(advise-hedge·assess-loan 등) — 분석 로직·2차 홉이 필요해
  이번 스코프 아님
- 실제 파트너 자격증명(머신 신원, 131·132) — 서비스 계정 자격증명(사람 계정 재사용)으로
  대체하는 임시 접근. 실제 머신 신원이 생기면 `auth.py`만 교체하면 되도록 인증 로직을
  `finallq_client.py`와 분리해둔다
- FinAllQ의 `/approve`·`/reject` 호출 — 사람이 FinAllQ 화면에서 직접 처리
- 감사 로그에 `request_chain_id` 남기기 — FinAllQ 쪽 감사 스키마에 그 컬럼이 없음(별도
  스코프)
- FinAllQ 레포 코드 변경 (전부 읽기 전용 참조)

## 완료 기준
- `docs/schemas/request-withdrawal.json`에 `to_account_number`·`to_bank_code` 추가,
  `docs/A2A_CONTRACT_CHANGES.md`에 CP-002 등재(제안 상태)
- `adapters/finallq_a2a/` 기동 시 `:9101`에서 Agent Card·request-withdrawal 스킬 응답
- 로그인 목(mock) 기준 유닛 테스트로 TransferStatus 6종 전부 매핑 검증
- FinAllQ가 401을 반환하면 1회 재로그인 후 재시도, 그래도 실패하면 502
- FinAllQ가 안 떠 있어도(502) / 응답이 늦어도(504) 어댑터가 명세대로 에러를 냄
- 나머지 6개 스킬 경로 호출 시 501 명시 응답
