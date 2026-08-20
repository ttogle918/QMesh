# InsuQ — A2A 계약 참조 (외부, QMesh 예정)

> 이 문서는 **참조용 인덱스**다. 실제 스키마 원본은 `A2A_Q`(QMesh 허브 레포)
> `docs/schemas/`, `docs/agent_cards/`에 있고 여기서는 복제하지 않는다 — 원본이
> 바뀌면 이 문서가 아니라 A2A_Q 쪽만 고치면 된다(drift 방지).
>
> 상태: **M1(계약 계층) 초안.** A2A 실구현(`/run` 노출, 외부 HTTP 수신부)은 아직 착수 전.
> `05_ARCHITECTURE.md`가 다루는 현재 서비스 구성(frontend→backend→ai-engine)과는 별개이며,
> Track 4(화재보험 상품군)·계약 대장이 먼저 실사용 가능해야 이 스킬들이 의미를 가진다.

## InsuQ의 역할

InsuQ는 A2A에서 **항상 응답자**다 — 다른 도메인에 요청을 보내는 경우는 없다.

## 이 레포가 노출할 스킬 (아직 미구현, 계약만 확정)

| 스킬 | 트리거(MaintQ 쪽 이벤트) | 성격 | 시나리오 | 스키마 |
|---|---|---|---|---|
| `advise-policy-renewal` | 화재보험 갱신 상담 요청(고장이력 첨부) | 상담 + 데이터 연계 | S7 | `A2A_Q/docs/schemas/advise-policy-renewal.json` |
| `verify-collateral-insurance` | FinAllQ 대출심사 중 2차 홉으로 호출 (MaintQ가 직접 부르지 않음) | 순수 조회 | S8, S13(비례보상 포함) | `A2A_Q/docs/schemas/verify-collateral-insurance.json` |
| `notify-asset-change` | MaintQ 처분 서명 완료 | 통지 접수(계약 변경) | S11 | `A2A_Q/docs/schemas/notify-asset-change.json` |
| `notify-risk-change` | MaintQ 신규 설비 등재 | 통지 접수(법적 의무) | S14 | `A2A_Q/docs/schemas/notify-risk-change.json` |
| `claim-insurance` | 설비 화재 멸실 사고 (사람이 아니라 사고가 트리거) | 보험금 산정, 사람 승인 필요 | S15 | `A2A_Q/docs/schemas/claim-insurance.json` |

## 공통 원칙 (기존 InsuQ 코어 원칙을 A2A로 그대로 연장)

- 모든 회신에 **약관 조항 인용 필수** — 근거 없는 응답 0건.
- 근거 불충분 시 확인 불가/유보 반환. 단정 금지.
- `claim-insurance`는 응답에 `requires_human_approval: true`가 상수로 고정돼 있다 —
  AI가 보험금 지급을 확정하지 않는다.

## 공통 requester 필드 (A2A_Q `docs/A2A_IDENTITY.md` 결정 1)

모든 inbound payload에 다음이 포함되어야 한다:

```json
"requester": {
  "finallq_company_id": "필수 — 전역 기업 식별자(subject)",
  "building_id": "선택 — MaintQ 자산/건물 참조 시(subject)",
  "policy_id": "선택 — InsuQ 계약 참조 시(subject)"
},
"request_chain_id": "필수 — 멀티홉 추적용"
```

> ⚠️ **이 객체는 인증이 아니다** (2026-08-13 결정 1 개정 반영). 여기 값들은 **"이 요청이 누구
> 건인지 지정하는 값(subject)"** 이고, **"누가 호출했는지(actor)"** 는 별도 파트너 토큰이 담당한다.
> `building_id`만 맞으면 요청이 통과하는 구조를 만들면 안 된다 — 검증 순서와 위임 테이블은
> `docs/A2A_IDENTITY.md` §5.4·§7을 따른다.

## 선행 조건 (이 레포 자체 백로그)

- 화재보험(기업 물건) 상품군 추가 — 약관 PDF 확보·파싱·인덱싱 (트랙4)
- **계약 대장 = TASK-E01**(트랙5). 별도 A2A 전용 대장을 만들지 않는다
- 계약 대장 스키마 — **2026-08-13 갱신**: 초안의 6필드 flat
  (`{building_id, policy_id, insurer, coverage_amount, expiry_date, external_owner_ref}`)을
  **세 결로 나눈다**(`docs/A2A_IDENTITY.md` §5):
  - `partner_subject_refs` — 외부 키(`BLD-A` 등) ↔ 우리 로컬 키 매핑. **인증 정보 아님**
  - `policies` — 증권 헤더(`policy_no`·`insurer`·기간). `policy_no`는 **우리가 발급**하는 값이라
    외부 참조 컬럼이 아니다(MaintQ가 `assets.policy_id`에 복제해 들고 있다)
  - `policy_objects` — 목적물별 담보(`coverage_amount`·`insured_value`·`coinsurance_ratio`·
    `deductible`). **비례보상 계산에 가입금액 하나로는 부족하다**
  - 인가는 별도 `partner_grants`(위임 테이블) — InsuQ는 응답자라 이 테이블을 실제로 가져야 한다

## 수신부 위치 (2026-08-13 확정)

A2A `/run`·Agent Card는 **backend(Spring)** 에 둔다 — 계약 대장(RDB)·인증이 Spring 소관이라
수신부만 ai-engine에 두면 `05_ARCHITECTURE.md` 데이터 소유권 경계가 깨진다. 근거 조항이 필요한
스킬은 Spring이 ai-engine을 호출해 조립한다. 상세: `docs/A2A_IDENTITY.md` §8.

## 관련 문서

- `A2A_IDENTITY.md` — **이 레포의 신원 식별 조사·설계 회신** (스키마 3분할·시드·인증/인가 분리)
- `05_ARCHITECTURE.md` — 이 레포의 실제 서비스 구성
- `07_BACKLOG.md` — Track 4(화재보험), Track 7(A2A) 진행 상태
- A2A_Q `docs/A2A_IDENTITY.md` — 신원 식별 설계 결정 전체
- A2A_Q `11_A2A_SCENARIOS.md`, `11_A2A_SCENARIOS_append_S11-S17.md` — 시나리오 상세
