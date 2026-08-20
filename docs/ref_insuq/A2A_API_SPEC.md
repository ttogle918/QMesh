# InsuQ — A2A HTTP API 명세 (TASK-H01·H02)

> **작성 2026-08-19.** 상태: **명세 확정, 구현 미착수.**
>
> **이 문서의 범위**: InsuQ가 A2A 스킬을 **HTTP로 어떻게 노출하는가** — 엔드포인트·봉투·
> 인증·에러·상태 전이. **스킬별 payload 스키마는 여기서 정의하지 않는다** — 원본은
> `A2A_Q/docs/schemas/*.json`이고 복제하면 drift가 난다(`docs/A2A_CONTRACTS.md` 방침).
> 이 문서는 그 스키마를 **감싸는 전송 계층**만 규정한다.
>
> 관련: `docs/A2A_CONTRACTS.md`(스킬 인덱스) · `A2A_Q/docs/agent_cards/insuq.json`(Agent Card)

---

## 0. 먼저 — 계약에서 발견한 결함 3건

명세를 쓰면서 기존 스키마를 전수 대조한 결과다. **구현 전에 결정이 필요하다.**

### 결함 ① 거부를 표현할 수단이 없다 🔴

InsuQ의 절대 원칙은 **"근거를 못 찾으면 `약관에서 확인 불가`로 거부한다"**(CLAUDE.md)이다.
그런데 스킬 5종 중 4종의 `status`는 **`enum: ["completed"]` 단일값**이고, `claim-insurance`만
`["input-required", "completed"]`다.

즉 **A2A 계약에는 "근거가 없어 답할 수 없다"를 담을 자리가 없다.** 구현하면 둘 중 하나가 된다:

- 없는 근거를 만들어 `completed`로 응답한다 → **절대 원칙 위반**
- HTTP 에러로 떨어뜨린다 → 호출자는 "InsuQ 장애"로 오해한다. **거부는 정상 응답이지 장애가 아니다**

⇒ **제안**: 모든 스킬 `status`에 `"rejected"`를 추가하고, `rejection_reason`(enum)을 동반한다.
상세는 §5.

### 결함 ② `verify-collateral-insurance`만 `evidence`가 없다 🟡

`docs/A2A_CONTRACTS.md`는 *"모든 회신에 **약관 조항 인용 필수** — 근거 없는 응답 0건"*이라
명시했는데, 이 스킬의 response에는 `evidence` 필드 자체가 없다. **문서와 스키마가 어긋난다.**

게다가 이 스킬은 FinAllQ 대출심사의 2차 홉으로 불린다(S8·S13) — **대출 실행 판단의 근거가
되는 응답**이다. 근거 조항 없이 `policy_valid: true`만 돌려주면 받는 쪽이 검증할 방법이 없다.

⇒ **제안**: `evidence`를 required에 추가.

### 결함 ③ `evidence` 문자열 형식이 자유롭다 🟡

타입이 `array of string`이고, `advise-policy-renewal`에만 예시(`"든든실손4세대 보통약관 제4조 ①, p.13"`)가
description으로 달려 있다. 나머지는 형식 언급이 없다.

이 프로젝트는 **`policy_part`를 뺀 인용을 금지**한다 — 한 약관 안에 `제1조`가 여러 파트에
존재해서, 조 번호만 대조하면 **모델이 다른 파트의 같은 조 번호를 지어내도 환각 탐지를 통과**하기
때문이다(`.claude/rules/rag.md`). 형식이 자유로우면 이 보증이 A2A 경계에서 증발한다.

⇒ **제안**: §4에 형식을 못박고 `pattern`을 스키마에 추가.

---

## 1. 엔드포인트

InsuQ는 A2A에서 **항상 응답자**다. 외부로 요청을 보내지 않는다.

| 메서드 | 경로 | 용도 |
|---|---|---|
| `GET` | `/.well-known/agent-card.json` | Agent Card 노출. 인증 불필요 |
| `POST` | `/a2a/skills/{skill_id}` | 스킬 실행 |
| `GET` | `/a2a/tasks/{task_id}` | Task 상태 조회 (§6) |

`{skill_id}`는 Agent Card의 `skills[].id`와 **정확히 일치**해야 한다:
`advise-policy-renewal` · `verify-collateral-insurance` · `notify-asset-change` ·
`notify-risk-change` · `claim-insurance`

> **왜 스킬별 경로인가**: 단일 `/run`에 `skill_id`를 body로 받으면 라우팅 오류가
> **런타임 400**으로만 드러난다. 경로에 두면 **알 수 없는 스킬이 404로 즉시** 갈린다.
> 게이트웨이·로그·레이트리밋도 경로 단위로 걸 수 있다.

### 서비스 배치

A2A 수신부는 **ai-engine(FastAPI)이 아니라 backend(Spring)**에 둔다.

- `A2A_IDENTITY.md` 결정에 따라 신원(`requester`)·인가·감사 로그는 Spring 소관이다
- 계약 대장(`Policy`·`Customer`·`BusinessSite`)이 Spring RDB에 있다 —
  `building_id`/`policy_id` 해석이 여기서만 가능하다
- ai-engine은 **약관 근거 검색·생성만** 담당하고 Spring이 내부 호출한다
  (`AI_ENGINE_BASE_URL`, 기존 `/qa` 경로와 동일 구조)

---

## 2. 요청 봉투

```http
POST /a2a/skills/verify-collateral-insurance HTTP/1.1
Content-Type: application/json
Authorization: Bearer <token>
X-Request-Chain-Id: chain-2026-0819-a1b2
Idempotency-Key: maintq-evt-88213
```

```json
{
  "requester":        { "finallq_company_id": "FQ-1043", "building_id": "BLD-77" },
  "request_chain_id": "chain-2026-0819-a1b2",
  "building_id":      "BLD-77",
  "required_coverage": 1200000000
}
```

**body는 해당 스킬 스키마의 `request` 그대로다.** 별도 래핑을 하지 않는다 — 래핑하면
스키마 검증기를 그대로 못 쓴다.

| 헤더 | 필수 | 의미 |
|---|---|---|
| `Authorization: Bearer` | ✅ | §3 |
| `X-Request-Chain-Id` | ✅ | body의 `request_chain_id`와 **동일해야 한다**. 다르면 400. 헤더는 게이트웨이 로깅용, body는 스키마 준수용 |
| `Idempotency-Key` | 통지·청구 스킬 필수 | §7 |

---

## 3. 인증

M1은 `oauth2-mock`이다(Agent Card 명시). 토큰은 검증하되 **신원은 `payload.requester`로
판단**한다(`A2A_IDENTITY.md` 결정 1).

⚠️ **`requester`를 신뢰 경계로 삼는다는 뜻이 아니다.** M1에서는 호출자 자체가 신뢰된
내부 에이전트라는 전제이고, **외부 노출 시에는 토큰의 subject와 `requester`가 일치하는지
검증해야 한다**. 이 검증 없이 인터넷에 노출하면 `finallq_company_id`만 바꿔 **남의 계약을
조회**할 수 있다 — 트랙4에서 `product_filter`로 막은 것과 같은 종류의 사고다.

| 상황 | 응답 |
|---|---|
| 토큰 없음/만료 | `401` |
| 토큰은 유효하나 해당 `building_id`/`policy_id` 접근 권한 없음 | `403` |

---

## 4. `evidence` 형식 (결함 ③ 해소안)

**모든 성공 응답은 `evidence`를 포함한다.** 형식은 InsuQ 인용 규약과 동일하게 고정한다:

```
{상품명} {policy_part} {article_no}[ {clause_no}][, p.{page}]
```

```json
"evidence": [
  "삼성화재 수퍼비즈니스보험 보통약관 제4조 ①, p.13",
  "삼성화재 수퍼비즈니스보험 구내폭발위험 특별약관 제1조, p.36"
]
```

**규칙**
- `policy_part`는 **생략 불가**. 파트 간 조 번호가 충돌한다(`.claude/rules/rag.md`)
- `clause_no`·`page`는 값이 없으면 **그 토막을 통째로 생략**한다. `p.None`이 나가면 인용
  신뢰가 무너진다
- 인용은 **`verify_citations` 검증을 통과한 것만** 싣는다. 검증 실패 인용은 응답에서 제외하고,
  검증된 인용이 하나도 남지 않으면 **거부**(§5)다

**제안 `pattern`** (스키마에 추가):
```
^.+ .+ 제\\d+조(\\s+[①-⑳\\d]+항?)?(, p\\.\\d+)?$
```

---

## 5. 거부·유보 (결함 ① 해소안)

### 상태 값

| `status` | 의미 | HTTP |
|---|---|---|
| `completed` | 정상 응답 | 200 |
| `input-required` | 판단에 필요한 정보 부족 → 되묻기 | 200 |
| **`rejected`** *(신규)* | **약관에서 근거를 찾지 못함** | 200 |

⚠️ **`rejected`는 200이다.** 거부는 **정상 동작이지 장애가 아니다** — 4xx/5xx로 내리면
호출자가 재시도하거나 InsuQ 장애로 오인한다.

### 거부 응답

```json
{
  "status": "rejected",
  "rejection_reason": "no_evidence_found",
  "message": "약관에서 확인 불가",
  "evidence": []
}
```

| `rejection_reason` | 언제 |
|---|---|
| `no_evidence_found` | 검색 결과에 근거 조항이 없다 |
| `citation_unverified` | 생성은 됐으나 인용 검증을 통과한 조항이 0건이다 |
| `out_of_corpus` | 해당 상품·약관이 코퍼스에 없다 |
| `policy_not_found` | `policy_id`/`building_id`에 해당하는 계약이 없다 |

### 유보

판단이 서지 않을 때는 **거부가 아니라 유보**다. 근거는 있는데 결론을 못 내는 경우다.

`notify-risk-change`는 이미 `verdict: "deferred"` + `needs_review: true`로 표현한다.
**나머지 스킬에도 같은 축이 필요하다** — 제안:

```json
{ "status": "completed", "verdict": "deferred", "needs_review": true, "evidence": ["…"] }
```

⚠️ **`claim-insurance`는 `requires_human_approval: true`가 상수**다. AI가 보험금 지급을
확정하지 않는다는 뜻이고, **이 필드를 false로 만들 수 있는 경로는 없어야 한다.**

---

## 6. Task 생명주기 (TASK-H03)

동기 응답이 원칙이다. 다만 `claim-insurance`처럼 **사람 승인이 끼는 스킬**은 즉시 종결되지
않는다.

```
요청 → [동기] completed | rejected | input-required
              └─ 사람 승인 필요 시 → pending-approval → (사람) → completed | rejected
```

승인 대기가 발생하면 응답에 `task_id`를 실어 보내고, 호출자는 `GET /a2a/tasks/{task_id}`로
폴링한다.

```json
{ "status": "pending-approval", "task_id": "tsk-88213", "requires_human_approval": true }
```

> **왜 콜백이 아니라 폴링인가**: 콜백은 InsuQ가 외부로 요청을 보내는 구조인데, Agent Card에
> *"InsuQ는 항상 응답자 — 자신이 다른 도메인에 요청을 보내는 경우는 없다"*고 못박혀 있다.
> 콜백을 넣으면 그 원칙이 깨진다.

---

## 7. 멱등성

`notify-asset-change`·`notify-risk-change`·`claim-insurance`는 **계약 변경·금전 판단**을
낳는다. 같은 요청이 두 번 오면 접수도 두 번 되면 안 된다.

- 이 세 스킬은 `Idempotency-Key` **필수**. 없으면 `400`
- 같은 키로 재요청하면 **최초 응답을 그대로 재생**한다(재계산하지 않는다)
- 조회 스킬(`verify-collateral-insurance`·`advise-policy-renewal`)은 선택

`notify-asset-change`의 `decision_id`(MaintQ 처분 서명 레코드)는 **멱등 키가 아니다** —
감사 추적용이다. 둘을 섞지 않는다.

---

## 8. 에러 응답

```json
{ "error": "schema_validation_failed", "detail": "required 'building_id' is missing", "request_chain_id": "chain-…" }
```

| HTTP | `error` | 언제 |
|---|---|---|
| 400 | `schema_validation_failed` | 스킬 스키마 위반 |
| 400 | `chain_id_mismatch` | 헤더와 body의 `request_chain_id` 불일치 |
| 400 | `idempotency_key_required` | 통지·청구 스킬에 키 누락 |
| 401 | `unauthenticated` | 토큰 없음/만료 |
| 403 | `forbidden` | 해당 계약 접근 권한 없음 |
| 404 | `unknown_skill` | Agent Card에 없는 `skill_id` |
| 409 | `idempotency_conflict` | 같은 키에 다른 payload |
| 502 | `upstream_unavailable` | ai-engine 도달 불가 |
| 504 | `upstream_timeout` | ai-engine 응답 초과 |

⚠️ **근거 없음은 에러가 아니다.** `200 + status: rejected`다(§5). 이 구분이 무너지면
호출자가 거부를 재시도하고, 그 재시도가 LLM 비용이 된다.

---

## 9. 스킬별 입출력 요약

payload 원본은 `A2A_Q/docs/schemas/*.json`이다. 아래는 **필수 필드만** 추린 참조표다.

### `advise-policy-renewal` (S7) — 화재보험 갱신 상담
| | 필드 |
|---|---|
| **입력(필수)** | `requester` · `request_chain_id` · `building_id` · `policy_id` · `incident_history[]`(date·error_code·severity) |
| **출력(필수)** | `status` · `renewal_condition`{premium_change_pct, special_clause} · `evidence[]` |

### `verify-collateral-insurance` (S8·S13) — 담보 보험 검증
| | 필드 |
|---|---|
| **입력(필수)** | `requester` · `request_chain_id` · `building_id` · `required_coverage` |
| 입력(선택) | `loss_amount` — S13 비례보상 계산 시에만 |
| **출력(필수)** | `status` · `policy_valid` · `coverage_amount` |
| 출력(선택) | `insured_value` · `effective_recovery`(= 손해액 × 보험금액/보험가액) · `sufficient` |

⚠️ **결함 ②** — `evidence`가 required에 없다. 대출 실행 판단의 근거가 되는 응답이므로
추가해야 한다.

### `notify-asset-change` (S11) — 목적물 변경 통지 접수
| | 필드 |
|---|---|
| **입력(필수)** | `requester` · `request_chain_id` · `building_id` · `policy_id` · `change_type`(`REMOVE`\|`ADD`) · `equipment[]` · `effective_date` · `decision_id` |
| **출력(필수)** | `status` · `receipt_no` · `evidence[]` |
| 출력(선택) | `premium_adjustment` |

### `notify-risk-change` (S14) — 위험등급 변동 통지 접수
| | 필드 |
|---|---|
| **입력(필수)** | `requester` · `request_chain_id` · `building_id` · `policy_id` · `risk_before` · `risk_after` · `changed_factors[]` · `effective_date` |
| **출력(필수)** | `status` · `verdict`(`notify_required`\|`not_required`\|`deferred`) · `threshold_used` · `margin` · `needs_review` · `evidence[]` |

⭐ **다섯 스킬 중 유일하게 유보(`deferred`)를 표현할 수 있는 스킬이다.** 임계값 ±10% 이내면
`needs_review: true`로 사람에게 넘긴다 — 다른 스킬에도 이 축이 필요하다(§5).

### `claim-insurance` (S15) — 보험금 청구·산정
| | 필드 |
|---|---|
| **입력(필수)** | `requester` · `request_chain_id` · `building_id` · `policy_id` · `equipment_info` · `incident_detail`{date, cause} · `book_value` |
| **출력(필수)** | `status`(`input-required`\|`completed`) · `payout_decision` · `evidence[]` |
| 출력(고정) | `requires_human_approval: true` **상수** |

⚠️ 유일하게 **사고가 시작점**인 스킬이다(사람이 아니라). 그리고 유일하게 사람 승인이 계약에
박혀 있다 — §6의 `pending-approval` 경로가 필요한 스킬이다.

---

## 10. 구현 전 확인 사항

- [ ] **결함 ①** `rejected` 상태를 계약에 추가할지 — `A2A_Q` 스키마 수정이 필요하다(원본이 거기 있다)
- [ ] **결함 ②** `verify-collateral-insurance`에 `evidence` 추가
- [ ] **결함 ③** `evidence` `pattern` 추가
- [ ] 유보 축(`verdict`/`needs_review`)을 나머지 스킬로 확장할지
- [ ] `building_id` → 계약 조회 경로 확정 (`Policy`·`BusinessSite` 스키마와 대조)
- [ ] 외부 노출 시 토큰 subject ↔ `requester` 일치 검증 (§3 경고)

> ⚠️ **위 4건은 `A2A_Q` 레포의 스키마를 고쳐야 한다.** 이 문서에서 임의로 바꾸지 않았다 —
> 원본이 거기 있고, 복제하면 drift가 나기 때문이다(`A2A_CONTRACTS.md` 방침).
> **MaintQ·FinAllQ 쪽 합의가 선행**이다.
