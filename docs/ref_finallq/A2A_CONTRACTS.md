# FinAllQ — A2A 계약 참조 (외부, QMesh 예정)

> 이 문서는 **참조용 인덱스**다. 실제 스키마 원본은 `A2A_Q`(QMesh 허브 레포)
> `docs/schemas/`, `docs/agent_cards/`에 있고 여기서는 복제하지 않는다 — 원본이
> 바뀌면 이 문서가 아니라 A2A_Q 쪽만 고치면 된다(drift 방지).
>
> 상태: **M1(계약 계층) 초안.** A2A 실구현(외부 HTTP 수신부, 파트너 자격증명)은 아직 착수 전.
> `docs/api_spec/openapi.yml`이 다루는 현재 내부 API(`/api/v1/...`)와는 별개다.
>
> ⚠️ **이 레포는 A2A_IDENTITY.md에서 훨씬 깊은 자체 조사를 이미 완료했다.** 아래 표는
> 그 조사 결과의 "무엇을 노출할 것인가" 요약이고, "어떻게 신원을 확인할 것인가"의
> 실제 결정(옵션 A+B 조합, 미결 3건 등)은 `docs/A2A_IDENTITY.md`가 원본이다.

## FinAllQ의 역할

응답자이자, 2건(S8·S13)에서는 InsuQ를 다시 부르는 **2차 홉 발신자**이기도 하다.

## 이 레포가 노출할 스킬 (아직 미구현, 계약만 확정)

| 스킬 | 트리거(MaintQ 쪽 이벤트) | 성격 | 시나리오 | 스키마 |
|---|---|---|---|---|
| `request-withdrawal` | 팀장 승인 완료된 발주 대금 출금 | 요청 접수, 2단 승인(FDS→재무) | S5 | `A2A_Q/docs/schemas/request-withdrawal.json` |
| `advise-hedge` | 환헤지/여유자금 상담 요청 | 제안/상담(실행 없음) | S6 | `A2A_Q/docs/schemas/advise-hedge.json` |
| `assess-loan` | 담보 대출 상담(내부에서 InsuQ 2차 홉) | 대출 심사 | S8 | `A2A_Q/docs/schemas/assess-loan.json` |
| `request-settlement` | 매각대금 정산·상환 요청(S5 반대 방향) | 요청 접수, 2단 승인 | S12 | `A2A_Q/docs/schemas/request-settlement.json` |
| `assess-used-equipment-loan` | 중고설비 담보 대출 상담(내부에서 InsuQ 2차 홉, 비례보상) | 대출 심사 | S13 | `A2A_Q/docs/schemas/assess-used-equipment-loan.json` |
| `advise-financing` | 설비 취득 자금 조달 비교 상담 | 제안/상담 | S16 | `A2A_Q/docs/schemas/advise-financing.json` |
| `advise-replacement-financing` | S15 2차 홉 전용(직접 진입 없음) — InsuQ claim-insurance 응답 이후만 | 제안/상담 | S15 | `A2A_Q/docs/schemas/advise-replacement-financing.json` |

## 응답에 포함 가능한 nullable 참고 데이터 (`market_context`)

`assess-loan`·`assess-used-equipment-loan`·`advise-financing` 세 스킬 응답에는
`market_context.esg_rating`, `market_context.stock_price_snapshot`이 **nullable**로
정의돼 있다. 심사·조달비교 로직에 강제 반영하지 않고, 문구 보강(cost_note·risk_note)
용도로만 사용한다. 이 레포가 아직 보유하지 않은 값이면 항상 null로 응답한다.

## 이 레포에만 있는 것 — 층 ① 신원 조사 결과 요약

`docs/A2A_IDENTITY.md`가 실측한 내용이며, **QMesh 여부와 무관하게 이 레포 단독으로도
필요한 결정**이다(층 ①).

🔴 **2026-08-20 갱신 — 아래 목록의 절반은 이제 사실이 아니다.** 126~130(기업 고객 등록·
직원 초대·`findById(1L)` 시한폭탄·발급자 lockout·온보딩 화면)이 전부 구현 완료됐고
(`AdminController`·`InvitationService`·V15·V16), 여신 도메인도 V17(Sprint 12)로 생겼다.
자세한 변경 이력은 `docs/A2A_IDENTITY.md` 각 절의 "✅ 해소(2026-08-20)" 표시를 따라간다.
**지금도 남아 있는 것만** 요약하면:

- `company` 테이블에 **A2A 파트너 전용** 발급형 식별자(`external_partner_id` 등)가 여전히
  없다. 사업자번호 조회 경로(`findByBusinessRegistrationNumber`)는 126이 만들었지만, 이건
  **ADMIN이 신규 기업 고객을 등록할 때 쓰는 온보딩 조회**이지 A2A 파트너 인증자가 아니다 —
  사업자번호가 공개정보라 인증자로 쓸 수 없다는 문제(§1.4) 자체는 그대로다.
- 정산(`settlement`) 도메인 테이블이 여전히 없다(C102 이월 — V17 주석에 명시).
  여신(`loan`·`credit_limit`·`collateral`)은 이제 있고, 실제 심사 로직(한도·LTV 자동 판정 +
  사람의 승인/거절)까지 붙었다(Sprint 12·14). `POST /loans/simulate`만 여전히 DB 미접근
  순수 계산기(상환 스케줄 비교용, 심사 아님)로 남아 있다.
- MCP Hub는 사용자 토큰을 그대로 위임할 뿐 **머신 신원(machine identity) 개념이 0**이다 — 불변.
- 신원 확인은 **옵션 A(토큰=actor) + 옵션 B(payload=subject) 조합**으로 잠정 결론
  (A2A_IDENTITY.md §3.2) — 이 결정 자체(파트너 자격증명·연결 승인, 131~132)는 QMesh 착수
  전까지 여전히 Pool이다.

**완료된 항목**: 126·127·128·129·130·133(공수 18) — `kanban_board/backlog.md` 참고.
**남은 항목**: 131·132(공수 13, 층 ② · QMesh 전제) · 136(초대 목록·취소, 공수 3, Pool).

## 공통 requester 필드 (A2A_Q `docs/A2A_IDENTITY.md` 결정 사항)

QMesh 결정: payload에 `requester.finallq_company_id`(필수)를 싣는다. **다만 이 레포
자체 조사(§ 위)에 따르면 payload 단독은 인증이 아니므로**, 실제 구현 시 파트너
자격증명(액세스 토큰, actor)과 병행이 필요하다 — 두 문서의 결론이 정확히 일치한다.

## 관련 문서

- `docs/api_spec/openapi.yml` — 이 레포의 현재 내부 API
- `docs/A2A_IDENTITY.md` — 이 레포의 신원 식별 자체 조사(원본, 최신)
- A2A_Q `docs/A2A_IDENTITY.md` — QMesh 관점의 결정 요약
- A2A_Q `11_A2A_SCENARIOS.md`, `11_A2A_SCENARIOS_append_S11-S17.md` — 시나리오 상세
