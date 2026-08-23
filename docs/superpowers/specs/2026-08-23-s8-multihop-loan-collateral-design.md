# S8 멀티홉 — `assess-loan` + `verify-collateral-insurance` 설계 (2026-08-23)

## 배경

오늘 세션 1~3단계(FinAllQ `request-withdrawal`·InsuQ `lookup-clause` 실제 E2E 검증,
MaintQ A2A 코드 테스트 75건)가 끝난 뒤, 마지막 조각으로 시나리오맵의 하이라이트인
S8(담보 대출 심사 시 보험 검증, 멀티홉 릴레이)을 브레인스토밍했다. `docs/A2A_SCENARIOS.md`가
"A가 B를 부르고, B가 다시 C를 부르는" 증명 패턴으로 지목한 시나리오다.

착수 전 실측에서 예상보다 많은 게 이미 있었다:
- `docs/schemas/assess-loan.json`·`verify-collateral-insurance.json` — 계약 이미 확정
- `docs/A2A_IDENTITY.md` "인증/인가 분리 모델 — 옵션 C" — 2차 홉 신원 문제 이미 결론남
  (인증은 FinAllQ가 대신, 인가는 InsuQ가 자체 보유; actor=FinAllQ ≠ subject=MaintQ 소유 건물)
- InsuQ `V2__add_a2a_partner_tables.sql` — 정책 원장(`policy_object`·`partner_subject_ref`·
  `partner_grant`) 마이그레이션 이미 존재
- FinAllQ `LoanApplicationController`/`LoanAssessmentService` — 실제 여신 심사 도메인 존재

하지만 실측 중 계약과 실제 코드가 어긋나는 지점 두 개를 발견했고, 그 처리 방식이 이
설계의 핵심 결정이다.

## 발견 ① — `assess-loan`은 FinAllQ의 실제 여신 흐름과 성격이 다르다

FinAllQ의 실제 `apply()`(`POST /api/v1/loans/applications`)는 **자동 승인 경로가 전혀 없다**
— 한도·LTV 위반만 자동 `REJECTED`고, 그 외는 전부 `UNDER_REVIEW`로 접수돼 사람(ADMIN)의
`decide()` 호출을 기다린다(`LoanAssessmentService` 주석: "이 클래스 어디에도 자동 승인
경로가 없다"). 반면 `assess-loan.json`의 응답은 `status: ["completed"]` 하나뿐이라
요청 한 번으로 동기 판정(승인/조건부/거절)이 나는 것을 가정한다.

**결정 — `assess-loan`은 독립적인 사전 판정(pre-screening)이다.** FinAllQ의 실제 `Loan`
행을 만들지 않고, 사람 승인 대기 상태도 만들지 않는다. "승인되면 이후 S5로 연결"(시나리오
문서 5단계)이 이미 이 성격을 암시한다 — `assess-loan`의 판정은 예측이지 집행이 아니다.
실제 대출 신청·최종 승인은 이 스킬의 책임 밖이며, 사람이 FinAllQ 화면에서 별도로 진행한다.
`request-withdrawal`이 FinAllQ의 `/approve`·`/reject`를 호출하지 않는 것과 같은 경계
원칙이다.

## 발견 ② — `verify-collateral-insurance`를 감쌀 InsuQ 엔드포인트가 없다

`lookup-clause`는 이미 동작하던 `ai-engine`의 `POST /qa`를 감쌌을 뿐이라 "어댑터=번역
계층"이 성립했다. `verify-collateral-insurance`는 다르다 — 정책 원장 테이블(`policy_object`)은
있지만, 그걸 조회하는 Spring REST 엔드포인트가 InsuQ 쪽에 **하나도 없다**
(`PayoutRequestController`·`CustomerController`·`MeController`·`HistoryController`·
`AuthController`·`HealthController`·`QaController` 7개 컨트롤러 전수 확인, 정책 원장
조회 없음).

**결정 — InsuQ 선행 작업으로 명시하고, 오늘은 계약만 확정한다.** `verify-collateral-insurance`의
실제 구현(`adapters/insuq_a2a`에 핸들러 추가)은 InsuQ가 아래 §4의 엔드포인트를 만든
뒤로 미룬다. `request-withdrawal`의 CP-002(`suppliers.account_number` 갭)와 같은 성격의
외부 의존성이다 — 오늘은 그 갭을 발견하고 문서화하는 데서 멈춘다.

## 아키텍처

```
MaintQ ──(assess-loan)──▶ adapters/finallq_a2a :9101
                                │
                                │ 2차 홉 (신규)
                                ▼
                          adapters/insuq_a2a :9102 ──(verify-collateral-insurance)──▶
                                                       [InsuQ 정책원장 엔드포인트 — 미착수, §4]
```

- 2차 홉 인증/인가는 **생략한다** — `lookup-clause`와 동일 수준(무인증 프로토타입). `A2A_IDENTITY.md`가
  이미 "인증=FinAllQ, 인가=InsuQ 자체 보유"로 결론냈지만, `partner_grant` 테이블을 실제로
  조회하는 인가 검증은 **소비자가 아직 없는 코드**다(`credentials.py`의 "토큰 캐시는
  호출부가 생기는 스프린트가 만든다"와 같은 판단 — 지금 만들면 회귀 부담만 늘어난다).
  실제 파트너 자격증명이 붙는 시점의 후속 작업으로 문서에만 남긴다.

## ① FinAllQ 어댑터 — `assess-loan` 핸들러 (신규, `adapters/finallq_a2a`에 추가)

**모델**: `AssessLoanRequest`/`AssessLoanResponse` pydantic 모델을 `schemas.py`에 추가.
계약은 이미 `docs/schemas/assess-loan.json`에 있으므로 그대로 매핑 — 새 CP 불필요.

**처리 흐름** (`POST /a2a/skills/assess-loan`):
1. 요청 검증 (기존 두 어댑터와 동일한 `X-Request-Chain-Id`/body 일치 검사 → 400)
2. `INSUQ_A2A_BASE_URL`(기본 `http://localhost:9102`)로 `verify-collateral-insurance` 호출
   — `building_id`←`collateral_building_id`, `required_coverage`←`loan_amount`("대출액만큼은
   보장돼야 한다"는 보수적 기준), `request_chain_id`는 원 요청에서 그대로 물림
3. 판정 규칙 (`mapping.py`에 순수 함수로 추가):

| InsuQ 응답 | `assess-loan` 판정 | 비고 |
|---|---|---|
| `status=rejected` 또는 `policy_valid=false` | `decision=rejected` | `condition_note`에 InsuQ `rejection_reason` 반영 |
| `policy_valid=true`, `sufficient=true` | `decision=approved` | |
| `policy_valid=true`, `sufficient=false` | `decision=conditional` | `condition_note="보험 {coverage_amount}→{loan_amount} 증액 필요"` |

- `collateral_check`(`coverage_amount`·`sufficient`)에 InsuQ 응답을 그대로 요약해 담는다
- `market_context`는 이번 스코프에서 채우지 않는다(스키마가 이미 `null` 허용을 명시)

**2차 홉 실패 처리 — 임의로 `rejected`로 강등하지 않는다.** InsuQ 어댑터가 연결
불가/타임아웃이면 `assess-loan`도 그대로 502/504를 MaintQ에 전파한다. "심사해서
거절"과 "심사를 못 했다"를 뭉개면, 오늘 FinAllQ 어댑터 리뷰에서 고친 403≠502 교훈을
그대로 반복하는 셈이다.

**범위 밖(YAGNI)**: FinAllQ 자체 신용한도(`credit_limit`)·LTV 검사는 이 스킬에 넣지
않는다. S8이 증명하려는 건 멀티홉 릴레이지 여신 심사 엔진 재구현이 아니다 — 판정은
오직 InsuQ의 담보-보험 검증 결과 하나로 결정한다.

## ② InsuQ 어댑터 — `verify-collateral-insurance` 핸들러 (계약만, 구현은 후속)

`docs/schemas/verify-collateral-insurance.json`(이미 존재)을 그대로 채택한다. 구현
착수 조건은 §4가 InsuQ 쪽에 제안하는 엔드포인트가 생기는 시점이다. 그때 어댑터가
할 일은 얇다 — `partner_subject_ref`로 `building_id`→`business_site_id` 변환 후
그 엔드포인트를 호출해 A2A 봉투로 감싸는 것뿐(다른 두 어댑터와 동일 패턴).

## ③ 추적

`request_chain_id`는 MaintQ→FinAllQ→InsuQ 전 구간에 그대로 전파한다 — 오늘 두 어댑터가
이미 쓰는 관례(`X-Request-Chain-Id` 헤더 + body 양쪽) 재사용. FinAllQ 어댑터가 InsuQ를
부를 때도 같은 규약을 그대로 따른다. 새로운 trace 저장 로직은 필요 없다 — MaintQ
쪽 `record_a2a_trace`가 이미 최초 요청(assess-loan 호출) 1건만 기록하면 충분하고,
2차 홉(FinAllQ→InsuQ)은 FinAllQ 쪽 감사 책임이라 A2A_Q 프로토타입이 대신 만들지
않는다.

## ④ InsuQ 선행 작업 제안 (구현 아님 — 참고용 명세)

InsuQ가 정책 원장 조회 엔드포인트를 만들 때 참고할 최소 계약:

```
GET /api/policy-objects?business_site_id={id}
→ { policy_valid: boolean, coverage_amount: number, insured_value: number, evidence: string[] }
```

- `policy_object` 테이블의 `coverage_amount`를 그대로 노출
- `policy_valid`는 해당 `business_site_id`에 매칭되는 유효 `policy_object` 행 존재 여부
- 인가(`partner_grant` 조회)는 이 엔드포인트가 아니라 A2A 수신부(향후 InsuQ Spring
  A2A 컨트롤러)가 담당 — 이 GET 자체는 내부용으로 남을 수도 있다는 뜻

## 하지 않는 것 (범위 밖)

- `verify-collateral-insurance` 실제 구현 — InsuQ 정책 원장 엔드포인트 선행 필요(§4)
- `assess-loan`의 실제 FinAllQ 여신 도메인 연동(`Loan` 행 생성, ADMIN `decide()`) — 발견①에서
  의도적으로 분리
- FinAllQ 자체 신용한도(LTV·`credit_limit`) 판정 로직
- 2차 홉 인증/인가(`partner_grant` 검증) — 계약에만 반영, 코드는 파트너 자격증명 도입 시점으로
- `assess-used-equipment-loan`(S13, 비례보상 확장) — `verify-collateral-insurance` 재사용
  전제가 같으므로 이 스킬이 열리면 자동으로 따라온다. 별도 설계 불필요
- 코드 구현 전체 — 이번 라운드는 브레인스토밍/설계까지, 사용자가 별도로 구현 진행 예정
  (MaintQ 아웃바운드 클라이언트 설계와 같은 패턴)

## 완료 기준

이 설계 문서 자체가 완료 기준이다 — 구현 완료 기준은 후속 `writing-plans` 단계에서
정의한다. 오늘 세션 기준으로는:
- `docs/superpowers/specs/2026-08-23-s8-multihop-loan-collateral-design.md` 작성·커밋
- 발견 ①·②가 `docs/A2A_SCENARIOS.md`의 S8 준비도(🔴 10%)와 정합적으로 설명됨
- InsuQ 선행 작업(§4)이 InsuQ 레포가 아니라 이 문서에만 존재 — QMesh는 신뢰의 근원이
  아니라 계약 중계자로 남는다는 기존 원칙과 일치
