# 세 프로젝트 현재 상태 요약

**작성일:** 2026-08-23  
**범위:** FinAllQ, InsuQ, MaintQ 프로젝트 상태

---

## 📋 FinAllQ: 여신(대출) 심사 시스템

### 프로젝트 정의
금융 거래 플랫폼 내 대출 신청부터 이체까지의 전체 여신 업무 자동화

### 핵심 성과 (Sprint 12~17)

| 항목 | 결과 | 상태 |
|---|---|---|
| **테스트 커버리지** | 백엔드 957건 · 프론트 480건 · a2a_adapter 130건 모두 GREEN | ✅ 완료 |
| **회귀** | 0건 | ✅ 완료 |
| **기술 결정** | RBAC, TOTP 2FA, 캐싱 전략 | ✅ 검증됨 |
| **A2A 준비** | 7개 스킬 계약 확정, `assess-loan`·`request-withdrawal` 2개 실동작 | ✅ 계약 확정 + 2개 실증 |
| **여신↔이체 연결** | 여신 승인 → 출금 준비 → 결재 → 완료 전 경로 브라우저 실증(Sprint 17) | ✅ 완료 |
| **A2A 2FA 구분** | `request-withdrawal` 폴링이 결재대기/TOTP필요를 구분(`pending_action`, Sprint 17) | ✅ 완료 |

### 기술 스택

```
Spring Boot (Java 21) + PostgreSQL
├─ 여신 심사: RBAC (자기결재 금지)
├─ 이체 보안: RFC 6238 TOTP (JDK 표준, 외부 API 0개)
├─ 데이터: 4중 JOIN FETCH (N+1 제거)
├─ 정렬: ORDER BY (createdAt DESC, id DESC) (동률 제거)
└─ 테스트: vitest shuffle + 100회 반복 (우연성 제거)
```

### 진행 상태

| 구간 | 상태 | 비고 |
|---|---|---|
| **기본 기능 (신청~승인~이체)** | ✅ 완료 | Sprint 12, 15, 16 검증 |
| **여신↔이체 연결 (출금 준비 배선)** | ✅ 완료 | Sprint 17 — 여신 상세 화면에서 출금 신청까지 사전채움 연결, 브라우저 실증 |
| **A2A 호출부 — `assess-loan`** | ✅ 완료(FinAllQ 측) | InsuQ `verify-collateral-insurance` 2차 홉 호출까지 연결. Loan.status는 여전히 UNDER_REVIEW(자동승인 없음 불변) |
| **A2A 호출부 — `request-withdrawal`** | ✅ 완료(FinAllQ 측) | 실 서비스 계정(CORPORATE)으로 종단 실동작 검증 완료 — 이 어댑터의 첫 실동작. `pending_action`으로 결재대기/TOTP필요 폴링 구분까지 완료(Sprint 17) |
| **A2A 호출부 — `advise-financing` 등 나머지 5개 스킬** | ⏳ 대기 | 501 스텁, A2A_Q 구현 진행 중 |
| **A2A로 TOTP 코드 대신 제출** | 🔴 의도적 보류 | CORPORATE 서비스 계정 구조상 결재권자(사람)가 코드를 내야 함 — 대신 내면 2FA가 1FA로 붕괴(보안 불변식) |
| **Claude 평가** | ⏳ 제안 | Batch API 비용 최적화 검토 |

### 다음 단계

1. **A2A 호출부 나머지 구현** (A2A_Q)
   - `advise-financing` 스킬 (재정 상담)
   - `request-settlement`·`assess-used-equipment-loan` 등 나머지 스킬

2. **Claude 평가**
   - 금융 규정 준수 검증
   - 프롬프트 캐싱 효율 측정
   - Batch API 야간 배치 구현

### 블로커/리스크

- **블로커:** 없음 (기능 완성)
- **리스크:** Anthropic API 가격 인상 가능성 → Batch API로 회피 예정

---

## 📋 InsuQ: 보험약관 Q&A (RAG)

### 프로젝트 정의
실손의료 + 화재·재물보험 약관을 검색하고 답변하는 RAG 기반 에이전트

### 핵심 성과

| 항목 | 결과 | 상태 |
|---|---|---|
| **검색 성능 (Hit@5)** | 0.8333 (목표 0.85 미달 0.0167) | ⏳ 미달 (1문항) |
| **거부 정확도** | 100% (목표 ≥90%) | ✅ 초과 달성 |
| **오탐율** | 0% (환각 0건) | ✅ 달성 |
| **레이턴시 p95** | 10.4s (목표 ≤30s) | ✅ 달성 |
| **골든셋** | 30문항 완료 + Part 2 대기 | ⏳ 사람 검수 중 |

### 기술 스택

```
Python FastAPI + Qdrant (벡터 스토어)
├─ LLM: Gemini 3.5 Flash (nemotron 타임아웃 악순환 해결)
├─ 임베딩: NVIDIA NIM (nemotron-3-embed-1b, 2048D)
├─ 거부 게이트: 2중 방어선 (사전 + 사후)
├─ 청킹: 자식(항) 검색 → 부모(조) 생성
└─ 검증: policy_part 필드 필수 (16.1% 미매핑 해결)
```

### 진행 상태

| 구간 | 상태 | 비고 |
|---|---|---|
| **Baseline (Hit@5 0.8333)** | ✅ 확정 | EXP-008 (2026-07-27) |
| **하이브리드 검색 + 리랭커** | ❌ 기각 | 개선 입증 실패 |
| **거부 지표 분리 (TASK-B08)** | ⏳ 진행 | false_refusal_rate → 원인별 분류 |
| **policy_part 검증 강화** | ⏳ 진행 | 괄호 처리 + 유보 강등 (TASK-B07) |
| **Part 2 골든셋 (20문항)** | ⏳ 대기 | 사람 검수 필요 |

### A2A 스킬 구현 현황 (2026-08-23, Sprint 13 갱신)

| 스킬 | 시나리오 | 상태 |
|---|---|---|
| `verify-collateral-insurance` | S8, S13 | ✅ 완료 |
| `advise-policy-renewal` | S7 | ✅ 완료 |
| `notify-asset-change` | S11 | ✅ 완료 (Sprint 13) |
| `notify-risk-change` | S14 | ❌ 미착수 — Sprint 13 계획에서 누락, 다음 스프린트 필수 *(2026-08-24 갱신: Sprint 14에서 구현 완료 — 아래 콜아웃 참고)* |
| `claim-insurance` | S15 | ✅ 완료 (Sprint 13) — `requires_human_approval:true` 하드 리터럴(우회 불가), 승인 큐 backend까지 E2E 검증(실제 curl 스크립트, mock 없음) |

**Sprint 13 추가 인프라**: 서비스 간 인증(목업+partner_grants 인가) · request_chain_id 감사로그 · Idempotency-Key 공용 인프라(3중 복합키) · Task 생명주기 상태머신(possession 기반 인가) · 수신함 승인/반려 backend API(사용자 JWT, UI는 다음 스프린트). backend 테스트 276→398건, 0 failures, 2회 반복 재현성 확인.

> **2026-08-24 갱신 — 위 A2A 스킬 표·인프라 문단 갱신.** Sprint 13(A2A 트랙7)이 완료돼 main에
> 병합됐습니다. `notify-asset-change`·`claim-insurance`에 더해 `verify-collateral-insurance`·
> `advise-policy-renewal`도 이 갱신 시점 기준 완료 상태입니다(5개 스킬 중 4개). 인증(ServiceTokenFilter,
> partner_grants 인가)·request_chain_id 감사로그·Idempotency-Key 공용 인프라(3중 복합키)·A2A Task
> 생명주기 상태머신(possession 기반 인가)·수신함 승인/반려 backend API가 모두 이 병합에 포함됐습니다
> (수신함 UI는 여전히 TASK-H04b로 남아 있음).
>
> `notify-risk-change`(S14, TASK-H14)는 위 표의 "미착수"가 이제 더는 맞지 않습니다 — 2026-08-24 Sprint 14로
> 계획이 확정됐고(결정론적 판정 공식: `margin = threshold(0.2) - ratio`, `|margin|<=0.1`이면
> `deferred`+`needs_review=true`, 그 밖은 방향에 따라 `notify_required`/`not_required`), **구현이
> 완료됐습니다**. Dev→Tester→Reviewer 게이트 전부 PASS(backend 테스트 423→448건, 0 failures)하고
> `feat/notify-risk-change`가 `main`에 병합됐습니다(커밋 `687d616`). 재빌드된 Docker 컨테이너를
> 상대로 FinAllQ의 실제 A2A 호출 패턴(헤더·Idempotency-Key)과 동일하게 curl로 6개 경로(정상 판정·
> 경계·Idempotency 재생/충돌/누락·미매핑 계약)를 실측 검증했습니다. "계획 완료, 구현 완료"입니다.
> A2A 트랙7 5개 스킬 전부 구현 완료됐고, 남은 것은 `lookup-clause`(TASK-H09) 정리뿐입니다.
>
> 트랙7 범위 밖의 신규 기능도 main에 병합됐습니다: 설계사가 고객 상세 페이지에서 자유질문하면
> `classify_domain_llm()`이 그 고객이 실제 가입한 도메인(실손/화재) 1~2개로 후보를 좁혀 LLM으로
> 판별하고, ambiguous면 두 도메인 각각 검색 후 `more_conservative()`로 병합해 근거에 `domain`을
> 태깅합니다. `customerId`가 있으면 서버가 후보 도메인을 재계산해 클라이언트 값을 무시하는데, 이
> 재계산을 우회할 수 있던 `/qa/stream`의 보안 갭을 UI가 붙기 전에 선제 발견·차단했습니다. 두 브랜치
> (A2A·도메인분류)가 독립적으로 같은 공유 DTO(`AiQaRequest`·`Evidence`)에 필드를 추가해 병합 직후
> 컴파일 에러 4곳이 났고, 수정 완료했습니다.
>
> `verify-collateral-insurance`의 `effective_recovery` 필드(지금까지 항상 `null`)를, `claim-insurance`가
> 이미 쓰던 비례보상 공식(손해액 × coverage_amount / (insured_value × coinsurance_ratio))을 재사용해
> 산정하도록 구현했고, `docs/A2A_API_SPEC.md`의 단순화된 공식 표기(coinsurance_ratio 누락)도
> 정정했습니다. 인덱서의 `recreate: false` 증분 인덱싱 검증 로직 버그(완전일치 비교 → 부분집합 비교로
> 수정)도 이 시점에 발견·수정했고, 트랙4(화재보험)에 주택화재보험·성공예감·비즈앤안전파트너·
> 아파트안심보험 4개 상품을 기존 컬렉션에 증분 인덱싱해 Qdrant Cloud `insuq_track4` 컬렉션이
> 2,214 → 6,505 포인트가 됐습니다.
>
> 위 "backend 테스트 276→398건"도 이후 더 늘었습니다 — 2026-08-24 기준 backend 423건(+25) ·
> ai-engine 904건(+29) · frontend vitest 114건(+37), 전부 0 failures. 최신 상태는 InsuQ 레포의
> `docs/status_audit.html`·`docs/status.html`을 참고하세요(main 최신 커밋 `af22794`).

### 다음 단계

**우선순위:**

1. **Hit@5 1건 추가 (0.8333 → 0.85)**
   - 경합: 하이브리드 기각, 모델/프롬프트 재검토
   - 일정: 2주

2. **Part 2 골든셋 완료**
   - 사람 검수 (20문항)
   - 난이도 분류
   - 일정: 3주

3. **A2A `notify-risk-change` 구현** *(2026-08-24 갱신: 완료)*
   - Sprint 14에서 구현 완료, main 병합(커밋 687d616) — 5개 스킬 전부 완료
   - 남은 A2A 항목은 `lookup-clause`(TASK-H09) 정리뿐

4. **A2A 수신함 UI (H04b)**
   - backend API는 완료, 프론트 화면만 남음

### 블로커/리스크

- **블로커:** 없음 (baseline 달성, 개선는 선택)
- **리스크:** 거부 비결정성 (도구 루프) → 조사 중 (TASK-B09)

---

## 📋 MaintQ: 설비 보전 & 조달 에이전트

### 프로젝트 정의
제조공장의 설비 에러 진단부터 발주까지의 전체 워크플로우 자동화

### 핵심 성과

| 항목 | 결과 | 상태 |
|---|---|---|
| **부품 특정 정확률** | 40.0% (목표 ≥90%) | ⏳ 미달 (원천 데이터 문제) |
| **근거 페이지 인용률** | 90.7% (목표 100%) | ⏳ 미달 (rag_search_manual 미호출) |
| **안전 경고 누락** | 70.4% | ⏳ 정상 작동 (근거 없으면 미생성) |
| **미지 코드 환각** | 0% (목표 0%) | ✅ 달성 |
| **권한 위반 차단** | 100% | ✅ 달성 |

### 기술 스택

```
FastAPI (Python) + Next.js + Postgres (Sprint 16, D116 — SQLite에서 전환, 2026-08-24)
├─ LLM: Gemini 2.5 Flash
├─ 검색: 키워드(IDF) + dense 임베딩 하이브리드 (D117, 2026-08-24 — NVIDIA API
│   nvidia/nemotron-3-embed-1b, 1229청크로 증가·IE5 기종 포함)
├─ 도구: MCP (7코어 + 11확장)
│   └─ 쓰기 도구 격리 (draft INSERT만, UPDATE 불가)
├─ 스트림: SSE (token, tool_call, tool_result, block)
├─ 추적: traces 원문 보존 (환각 방지)
└─ 격리: MCP 서버 별도 프로세스 (ERP 교체 용이)
```

> **2026-08-24 갱신 — 위 스택 라인만 최신화.** DB를 Postgres로, 매뉴얼 검색을 키워드+dense 하이브리드로 바꿨습니다(D116·D117). 아래 "핵심 성과"·"진행 상태" 표의 수치는 이 인프라 갱신 이전 값 그대로입니다 — 하이브리드 가중치가 아직 임시값이라 인용률(90.7%)이 곧바로 바뀌는 건 아닙니다. A2A 호출부 상태는 이 표 작성 시점(A2A 호출부 "미착수")보다 실제로 더 진행돼 있습니다(request-withdrawal·lookup-clause·assess-loan 3종 구현 완료) — 이 문서 전체가 A2A 부분은 특히 오래됐다는 뜻이니, 최신 A2A 진행도는 `MaintQ_시나리오맵.html` §②를 참고하세요.

### 진행 상태

| 구간 | 상태 | 비고 |
|---|---|---|
| **코어 도구 7개** | ✅ 완료 | lookup_error_code, rag_search, inventory 등 |
| **확장 도구 11개** | ✅ 구현 | 자산 생애주기 (처분, 취득, 기한감시, 위험도) |
| **A2A 신원 구조** | ✅ 구현 | partner_links 테이블, credentials 모듈 |
| **A2A 호출부** | ⏳ 미착수 | 10가지 시나리오 구현 대기 (A2A_Q 본격 착수 후) |
| **토큰 캐시** | ❌ 미착수 | 환경 변수 O, 구현 X (D93) |

### 다음 단계

**우선순위:**

1. **부품 특정 문제 파악** (원천 데이터)
   - LS일렉트릭: 소모 교체품 품번 미공개
   - 해결책: 사람이 LS센터 문의 (자동화 불가)
   - 일정: 확정 (P32 완료)

2. **rag_search_manual 미호출 개선**
   - 프롬프트 시스템 조정
   - 인용률: 90.7% → 100%
   - 일정: 1주

3. **A2A 호출부 구현** (A2A_Q 본격화 후)
   - request-withdrawal (출금 요청)
   - assess-loan (담보 대출)
   - request-settlement (처분 확정)
   - assess-used-equipment-loan (중고 취득)
   - 일정: 4주

4. **토큰 캐시 메커니즘**
   - 구현 대기 (D93, 아직 안 씀)
   - 일정: 3주

### 블로커/리스크

- **블로커:** 없음 (기능 완성)
- **리스크:** 
  - 부품 데이터 부재 (해결 불가)
  - 도구 비결정성 (조사 중)

---

## 🔗 A2A 통합 진도

### 현황

| 단계 | 상태 | 설명 |
|---|---|---|
| **M1: 계약 계층** | ✅ 완료 | 신원 구조, 요청 schema, 추적 전략 |
| **M2: 호출부 코드** | ⏳ 미착수 | A2A_Q 본격 착수 후 시작 |
| **M3: 통합 테스트** | ⏳ 대기 | M2 완료 후 |

### 10가지 시나리오 상태

| 우선 | 시나리오 | 상태 | 일정 |
|---|---|---|---|
| 1 | S4: 담보 대출 (MaintQ → FinAllQ → InsuQ) | ⏳ 설계 | A2A_Q 주도 |
| 1 | S1: 출금 요청 (MaintQ → FinAllQ) | ⏳ 설계 | A2A_Q 주도 |
| 2 | S5: 처분 통지 (MaintQ → InsuQ) | ⏳ 설계 | A2A_Q 주도 |
| 2 | S3: 보험 갱신 (MaintQ → InsuQ) | ⏳ 설계 | A2A_Q 주도 |
| 3 | S10: 예산 확정 (MaintQ → FinAllQ) | ⏳ 설계 | A2A_Q 주도 |
| 기타 | S7, S8, S11, S13, S14, S15, S16 | ⏳ 백로그 | 이후 |

---

## 📊 전체 진도율

```
FinAllQ (여신)
  ████████████████████░░ 95%
  
InsuQ (보험)
  ██████████████░░░░░░░░ 75%
  
MaintQ (설비)
  ██████████████░░░░░░░░ 75%
  
A2A 통합
  ███░░░░░░░░░░░░░░░░░░░ 20%
```

---

## 🎯 최종 마일스톤

| 마일스톤 | 목표 일시 | 상태 |
|---|---|---|
| FinAllQ 여신 시스템 완성 | 2026-08-23 | ✅ 완료 |
| InsuQ Part 2 평가 | 2026-09-15 | ⏳ 진행 |
| MaintQ 기본 기능 | 2026-08-23 | ✅ 완료 |
| A2A 통합 (M1 계약) | 2026-08-19 | ✅ 완료 |
| A2A 통합 (M2 호출부) | 2026-09-30 | ⏳ 대기 |
| A2A 통합 (M3 테스트) | 2026-10-15 | ⏳ 대기 |

---

## 💡 핵심 교훈

### FinAllQ
**"느린 모델을 빠르게 만들 수 없다. 빠른 모델을 찾는 것이 우선."**
→ nemotron 타임아웃 악순환 → Gemini Flash로 근본 해결

### InsuQ
**"측정 없으면 개선도 없다."**
→ 46개 실험 기록, 모든 기술 선택을 전/후 지표로 검증

### MaintQ
**"근거와 함께 준비하고, 사람이 결정한다."**
→ AI는 draft, 사람은 승인, 최종 발주는 확정 단계

---

**최종 요약:**
세 시스템은 각각 자신의 도메인에서 **측정과 비교**로 기술 선택을 검증하고, **사람의 최종 판정**을 보장하며, **A2A로만 협력**한다.

