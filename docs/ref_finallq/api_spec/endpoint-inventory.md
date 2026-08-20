# 능력 목록 (Endpoint Inventory) — A2A agent card 작성용 참조

**기준 시점: 2026-08-19** · 컨트롤러 20개 · 엔드포인트 **59개**

> 이 문서는 `A2A_Q/docs/agent_cards/` 에 FinAllQ 카드를 쓸 때 **"실제로 무엇을 할 수 있는가"**
> 를 확인하는 용도다. 스킬 계약(7종)의 원본은 `docs/A2A_CONTRACTS.md` → `A2A_Q` 이고,
> 여기서는 복제하지 않는다.
>
> 🔴 **`openapi.yml` 만 보고 카드를 쓰면 안 된다.** 커버리지가 20/59(34%)이고,
> 1차 확인에서 **구현된 적 없는 경로 2건**이 들어 있었다(아래 §4).

---

## 1. 이 목록을 뽑은 방법

`@RequestMapping` + `@(Get|Post|Put|Patch|Delete)Mapping` + `@PreAuthorize` 를 컨트롤러
20개에서 기계적으로 추출했다. 손으로 적지 않았으므로 **누락이 없다** — 다만 요청/응답
스키마는 이 문서의 범위가 아니다(그건 `openapi.yml` 몫이고, 지금은 20경로만 덮는다).

---

## 2. 전체 엔드포인트

경로는 `servers: /api/v1` 기준이다(`/api/health` 만 예외).
`[ADMIN]` 표기는 `@PreAuthorize("hasRole('ADMIN')")` 가 붙은 것이다.
표기가 없다고 공개는 아니다 — 대부분 `SecurityConfig` 의 인증 요구 아래 있다.

### 인증 · 신원

| 메서드 | 경로 | 비고 |
|---|---|---|
| POST | `/auth/signup` | |
| POST | `/auth/login` | Access(본문) + Refresh(HttpOnly 쿠키) |
| POST | `/auth/refresh` | 🔴 Redis 키가 `RT:{email}` **단일**이라 재로그인 시 이전 세션이 끊긴다 |
| POST | `/auth/logout` | |

### 이체 · 결재 — `request-withdrawal` · `request-settlement` 의 실체

| 메서드 | 경로 | 비고 |
|---|---|---|
| GET | `/transfers` | 목록 |
| POST | `/transfers` | **이체 요청 생성 + FDS 판정** |
| GET | `/transfers/approvals` | 결재 대기함(페이지네이션) |
| GET | `/transfers/{requestId}/approvals` | 결재 이력. `comment` 는 서버가 마스킹해 내려준다 |
| POST | `/transfers/{requestId}/approve` | |
| POST | `/transfers/{requestId}/reject` | 사유 코드 4종 + 메모(≤500자) |

### 여신 — `assess-loan` · `assess-used-equipment-loan` · `advise-financing` 의 실체

| 메서드 | 경로 | 비고 |
|---|---|---|
| POST | `/loans/simulate` | 상환 방식 3종 비교. 🔴 `rate` 는 **소수**(0.045 = 4.5%) |
| GET | `/loans/applications` | 목록 |
| POST | `/loans/applications` | 신청(담보 배열 포함). 🔴 `annualRate` 는 **퍼센트**(4.5 = 4.5%) |
| GET | `/loans/applications/{loanId}` | |
| POST | `/loans/applications/{loanId}/decision` | 심사(승인/거절). 자기결재 차단 |

🔴 **`rate`(소수)와 `annualRate`(퍼센트)는 단위가 다른 별개 계약이다.** 두 값을 잇는 변환은
`frontend/src/features/loan/prefill.ts` 한 곳뿐이다 — 카드 스키마에서 둘을 같은 필드로 묶지 않는다.

### 이상거래 · 보안

| 메서드 | 경로 | 비고 |
|---|---|---|
| POST | `/fds/score` | 위험 점수 + 사유 코드 + 권고 조치 |
| POST | `/sms/analyze` | |
| POST | `/sms/classify` | |
| GET | `/alerts` | |
| PUT | `/alerts/{alertId}/acknowledge` | |

### 자산 · 투자

| 메서드 | 경로 | 비고 |
|---|---|---|
| GET | `/accounts` | 계좌번호는 서버에서 마스킹돼 내려온다 |
| GET | `/portfolio` · POST `/portfolio` · DELETE `/portfolio/{holdingId}` | 보유 종목 |
| POST | `/portfolio/rebalance` | |
| POST | `/portfolio/what-if` | |
| GET | `/stocks/prices` | 페이지네이션 |
| GET | `/stocks/{ticker}/predict` | 쿼리 `days`(기본 7). 🔴 옛 스펙의 `/stocks/forecast/{ticker}` 는 **없다** |

### 리포트 · 세금 · 케어

| 메서드 | 경로 |
|---|---|
| GET | `/reports` · `/reports/{reportId}` |
| GET | `/reports/transaction-summary` · `/reports/health-check` |
| POST | `/reports/composite-risk` |
| POST | `/tax/calculate` |
| POST | `/fees/scan` |
| POST | `/stress/analyze` · `/future/timemachine` · `/esg/filter` · `/news/briefing` |

### 규제 · 감사 · 초대

| 메서드 | 경로 | 비고 |
|---|---|---|
| POST | `/rules` | 규제 점검 |
| GET | `/rules/notifications` · PUT `/rules/notifications/{id}/read` | |
| GET | `/audit/logs` | |
| POST | `/audit/report` | |
| POST | `/invitations` · POST `/invitations/accept` | 직원 초대 |

### 관리자 전용 (`[ADMIN]` 11개)

`/admin/accounts` · `/admin/customers`(GET·POST) · `/admin/customers/{customerId}` ·
`/admin/customers/{customerId}/invitations` · `/admin/rules` · `/admin/rules/{ruleId}/active` ·
`/admin/stock-prices/import` · `/admin/transactions/import` ·
`/admin/users/{userId}/role` · `/admin/users/{userId}/invite-authority`

### 오케스트레이터 · 헬스

| 메서드 | 경로 | 비고 |
|---|---|---|
| POST | `/agent/query` | **MCP Hub 오케스트레이터 진입점** — 아래 §3 |
| GET | `/api/health` | 접두사 없음 |

---

## 3. MCP 툴 (오케스트레이터가 엮는 단위)

`POST /api/v1/agent/query` 가 MCP Hub 를 부르고, Hub 가 아래 툴을 엮어 답을 만든다.
코드에서 추출한 식별자 **18종**(CLAUDE.md 는 20종으로 적고 있다 — 차이는 확인 필요):

```
alerts.list      esg.filter        fds.score          fees.scan
future.timemachine  loans.simulate  market.whatIf     news.brief
portfolio.rebalance reports.compositeRisk  reports.healthCheck
reports.list     reports.transactionSummary  rules.scan
sms.classify     stocks.predict    stress.analyze     tax.calculate
```

🔴 **카드에 "AI 상담"으로 적지 않는다.** 이 프로젝트에 LLM 은 없다 —
Hub 의 `plan` 은 **규칙 기반 키워드 매칭**이고 `synthesize` 는 **템플릿 조립**이다.
툴 출력도 화이트리스트(`mcp/hub/app/graph/summary.py`)에 등재된 키만 답변에 실린다.
카드의 성격 표기는 "규칙 기반 오케스트레이션"이 정확하다.

---

## 4. 🔴 `openapi.yml` 을 그대로 믿으면 안 되는 이유

2026-08-19 대조에서 나온 것:

| 항목 | 실측 |
|---|---|
| 스펙이 덮는 경로 | **20 / 59 (34%)** |
| 구현된 적 없는 경로 | **2건** — 아래 |

| 스펙에 있던 경로 | 실제 | 조치 |
|---|---|---|
| `POST/GET /reports/spending` | **없다.** 설명에 "Kafka/RabbitMQ 연동"이 적혀 있었는데 이 프로젝트엔 둘 다 없다 — 초기 설계안 잔재다 | **제거** |
| `GET /stocks/forecast/{ticker}` | `GET /stocks/{ticker}/predict` (파라미터도 `horizon_days` → `days`) | **정정** |

에이전트 카드에서는 **없는 기능을 광고하는 것이 빠뜨리는 것보다 나쁘다** — 상대 에이전트가
호출했다가 404 를 받는다. 그래서 커버리지를 늘리기 전에 잘못된 2건을 먼저 걷어냈다.

🟡 나머지 39경로는 **이 문서에만 있고 `openapi.yml` 에는 없다.** 요청/응답 스키마를 확인 없이
지어내지 않았다 — 필요한 경로가 생기면 컨트롤러·DTO 를 읽고 하나씩 옮긴다.

---

## 5. 카드 작성 시 주의할 계약

- **인증** — JWT. Access 는 응답 본문, Refresh 는 HttpOnly 쿠키 + Redis 화이트리스트.
  🔴 A2A **외부 수신부는 아직 없다**(`A2A_CONTRACTS.md` 상태: M1 계약 초안). 지금 카드에 적는
  엔드포인트는 **내부 API** 이며, 파트너 자격증명 경로는 미구현이다.
- **requester 필드** — `A2A_Q/docs/A2A_IDENTITY.md` 결정을 따른다. 이 레포의
  `docs/A2A_IDENTITY.md` 가 자체 조사 원본이다.
- **페이지네이션** — 목록 API 는 전부 `page`·`size` 를 받는다(절대 원칙 7).
  카드에 "전체 목록 반환"으로 적으면 계약이 어긋난다.
- **마스킹** — 계좌번호·결재 `comment` 는 **서버가 이미 마스킹해서** 내려준다.
  카드 응답 예시에 원문을 적지 않는다.
- **금액 표기** — `BigDecimal` 이 JSON 숫자로 나간다. 큰 값이 지수 표기(`2.0515E+7`)로
  읽히지 않게 소비 측에서 주의한다(백로그 82 이력).

---

## 관련 문서

| 문서 | 역할 |
|---|---|
| `docs/A2A_CONTRACTS.md` | 노출할 스킬 7종 + 스키마 포인터 (원본은 `A2A_Q`) |
| `docs/A2A_IDENTITY.md` | 신원 확인 방식 자체 조사 — 원본 |
| `docs/api_spec/openapi.yml` | 20경로 상세 스키마 |
| `docs/api_spec/fds_dashboard_api_spec.md` | FDS 대시보드 전용 스펙 |
