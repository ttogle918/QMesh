# A2A_IDENTITY — 신원 식별 설계 결정

> QMesh M1(계약 계층) 착수 시점 결정. **2026-08-13 개정** — FinAllQ가 자체 코드베이스를
> 실측 조사한 `FinAllQ/docs/A2A_IDENTITY.md`가 이 문서 초안(payload 단독)보다 훨씬 정교한
> 결론을 냈고, 그 결론이 근거도 탄탄해서 이번 개정에서 **그대로 채택**한다. 이하 "FinAllQ
> 조사"라고 인용하는 내용은 전부 `FinAllQ/docs/A2A_IDENTITY.md`가 원본이다.
>
> **2026-08-13 추가 개정** — MaintQ·InsuQ 자체 조사 반영. InsuQ는 golden set(평가 문항 세트)
> 제작 중이라 API 명세가 소폭 바뀔 수 있다는 전제하에 작성됨 — 이 문서가 다루는 신원·스키마
> 구조 결정은 golden set과 무관하므로 안정적이지만, 실제 시드 데이터 채우기는 golden set
> 안정화 이후로 미루는 게 안전하다.

## 결정 1 (개정) — 신원은 "토큰(actor) + payload(subject)" 조합으로 싣는다

**초안(2026-08-13 이전)에서는 "payload에만 명시적으로 싣는다"였으나, 이번 개정으로 폐기한다.**
이유는 FinAllQ 조사가 지적한 문제가 원칙적으로 맞기 때문이다:

> payload 단독(사업자번호 등 식별자만 받는 방식)은 **단독으로는 인증이 아니다.** 식별자는
> 공개정보라 "번호만 알면 남의 회사 건을 요청"할 수 있다 — 이건 QMesh의 관통 원칙("돈이
> 실제로 움직이는 앞에는 반드시 사람의 승인")과는 다른 층위의 구멍이다. 승인은 사람이
> 하더라도, 애초에 "누구 건으로 승인 요청이 올라왔는지"가 위조 가능하면 승인 자체가
> 무의미해진다.

그래서 **A(토큰=actor) + B(payload=subject)의 조합**을 정식 채택한다:

```
파트너 자격증명(client credentials) → 서명된 액세스 토큰 (actor = partner_id)
        +
요청 payload의 대상 식별자 (subject = company/building/policy)
        +
서버가 보유한 위임 테이블: partner_id → 다룰 수 있는 company_id 집합
```

- **actor**(토큰) = "누가 호출했나" → 인증. 위조 불가, 자격증명 단위 폐기 가능.
- **subject**(payload) = "누구 건을 처리하나" → 대상 지정. MaintQ가 자기 건을 요청하면
  actor=subject로 같지만, 대리·플랫폼 역할을 하면 다를 수 있다(§ 미해결 질문 참조).
- 서버는 "이 actor가 이 subject를 다룰 권한이 있는가"를 위임 테이블로 검사한다.

payload 스키마 자체(요청 body에 `requester` 객체를 두는 것)는 **바뀌지 않는다** — 다만
그 필드의 성격이 "이것만으로 인증됨"에서 "누구 건인지 지정하는 파라미터(subject)"로
재정의된다. 실제 인증은 별도 계층(파트너 토큰)이 담당한다.

### 왜 이게 초안보다 나은가

- 초안의 전제("아직 OAuth 목업 단계라 토큰 파싱을 못 믿는다")는 **지금 당장 코드를
  안 짜는 것**과는 별개 문제였다. 계약(스키마) 단계에서는 "최종적으로 어떤 모양이어야
  하는가"를 정하는 게 목적이므로, 나중에 이관할 걸 알면서 임시 스펙을 못박는 것보다
  처음부터 맞는 모양으로 정의해두는 편이 낫다.
- FinAllQ 조사가 실제 코드(`JwtTokenProvider`, MCP Hub의 토큰 위임 구조)까지 확인하고
  내린 결론이라 추상적 논의보다 신뢰도가 높다.

## 결정 2 — company_id는 FinAllQ 기준으로 통일한다 (유지, 변경 없음)

FinAllQ의 `company` 테이블 PK를 전역 기준 식별자로 삼아 `finallq_company_id`로
부른다. MaintQ·InsuQ는 각자의 로컬 식별자(`building_id`, `policy_id`)를
그대로 쓰되, 상대 도메인으로 나가는 모든 요청에 `finallq_company_id`를
같이 실어 보낸다.

**단, FinAllQ 조사로 드러난 제약이 붙는다**: 지금 `company` 테이블에는 외부 파트너를
가리킬 발급형 식별자(`external_partner_id` 같은 것)가 없다. `finallq_company_id`가
가리킬 실제 컬럼이 아직 없다는 뜻이므로, §5 온보딩 확정 전까지는 이 필드가
**논리적으로만 존재**하고 물리적으로는 null이다.

**MaintQ 쪽도 같은 이유로 정정됐다(2026-08-13)** — 처음엔 MaintQ `assets` 테이블에
`finallq_company_id` 컬럼을 얹는 안이었으나, MaintQ 자체 조사가 이걸 회피했다: 회사·건물·
자산은 결(grain)이 다른데(`finallq_company_id`=회사 단위, `policy_id`·`building_id`=건물
단위, `asset_id`=자산 단위) `assets`에 회사 식별자를 얹으면 자산 9행에 같은 값이 복제되어
drift가 시작된다. 대신 **별도 `partner_links` 테이블**에 `link_state`(NULL=모름/
NOT_LINKED/LINKED) + `external_ref`를 두고, `CHECK (link_state='LINKED' OR
external_ref IS NULL)`로 "식별자만 있고 승인은 없는 상태"를 DDL에서 차단한다 — 이건
결정 1의 actor/subject 분리를 스키마 레벨에서 다시 한번 강제하는 것과 같은 효과다.

**InsuQ 쪽도 같은 문제가 있었고, 더 세분화된 결론을 냈다(2026-08-13)** — 원래 요청한
"계약 대장에 building_id 등 6필드를 한 테이블로" 안은 InsuQ 조사에 의해 기각됐다.
결이 셋으로 갈린다:

| 결(grain) | 필드 | 테이블 |
|---|---|---|
| 외부 참조(subject 해석) | `building_id`, `external_owner_ref` | 신규 `partner_subject_refs` |
| 증권 헤더 | `insurer`, `expiry_date`, `policy_no`(정정 — 아래 참조) | `policies` |
| 목적물별 담보 | `coverage_amount` 외 3필드(아래 참조) | 신규 `policy_objects` |

**`policy_id`는 외부 참조가 아니다** — 방향이 반대다. InsuQ가 발급하고 MaintQ가
그 값을 복제해 들고 있는 거지, MaintQ가 발급한 값을 InsuQ가 참조하는 게 아니다.
그래서 `policy_id`는 `partner_subject_refs`가 아니라 `policies.policy_no`로 간다.

**`coverage_amount` 하나로는 S13 비례보상을 못 푼다** — `insured_value`(보험가액)·
`coinsurance_ratio`(공동보험 비율)·`deductible`(자기부담금)이 빠져 있었다.
`policy_objects`에 이 셋을 추가해야 S13의 "실효 회수액 = 손해액 × (보험금액/보험가액)"
계산이 성립한다. `verify-collateral-insurance.json` 스키마의 `insured_value`
필드는 이미 있으나, InsuQ 내부 테이블 설계에 이 근거 데이터가 없으면 그 필드는
항상 null로만 채워지게 된다 — 조사 결과를 반영해 실제 컬럼을 만들어야 한다.

또한 MaintQ와 마찬가지로 **"인증용 아님"을 주석이 아니라 구조로 잠갔다** — 매핑
(subject 해석용 `partner_subject_refs`)과 인가(권한 판단용, 아래 § 참조) 테이블을
분리하고, actor를 필수 인자로 받는 단일 진입점 + 가드 테스트로 강제한다. 그리고
"그런 건물이 없음"과 "권한이 없음"을 **같은 응답으로 회신**해 열거 공격을 막는다 —
이는 InsuQ 기존 원칙("근거 불충분 시 확인 불가 반환")과 형태가 같다.

## 공통 requester 객체 (모든 스킬 payload에 동일하게 삽입) — 유지

```json
"requester": {
  "finallq_company_id": "string (required) — 전역 기업 식별자(subject). FinAllQ company.id 기준",
  "building_id": "string (optional) — MaintQ 자산/건물 참조 시",
  "policy_id": "string (optional) — InsuQ 계약 참조 시"
},
"request_chain_id": "string (required) — 멀티홉 추적용, 최초 요청에서 발급 후 전 구간 전파"
```

> 이 객체는 여전히 payload에 남는다(결정 1 참조 — subject 지정 역할). 다만 인증은
> 별도 헤더/토큰(actor)이 담당하며, 이 스키마 문서는 그 인증 계층의 세부(비대칭 서명,
> 클레임 구조 등)까지는 규정하지 않는다 — `FinAllQ/docs/A2A_IDENTITY.md` §3.2가 원본이다.

## 온보딩 모델 (개정) — "초대 기반"으로 확정

**초안에서 미해결로 남겼던 문제** — "MaintQ가 FinAllQ의 기업 고객으로 언제·어떻게
최초 등록되는지" — 를 FinAllQ 조사가 실제로 결정했다. 그대로 채택한다.

### 채택 모델 — 담당자 발급(초대) 모델

```
[1회, 무겁다]  기업 실재 확인(사업자등록증명원·법인등기부·대표자 확인)
                    → 신뢰 앵커 1개 = 마스터 계정
                              ↓ 위임
[N회, 가볍다]  마스터가 직원 계정 발급 · 권한/한도 부여 · 퇴사자 폐기
```

- KYB(기업실사)는 **회사당 1회**(무거움). 그 뒤 계정 발급은 회사 내부에 위임(가벼움).
- 은행이 MaintQ 같은 파트너사를 직접 심사하지 않아도 된다 — **회사가 자기 파트너를
  등록**하는 구조가 되므로 파트너사가 늘어도 은행의 심사 부담이 선형으로 늘지 않는다.
- 단, **회사가 외부 시스템(A2A 파트너)에 부여할 수 있는 권한의 상한은 은행이 정한다.**
  파트너 자격증명에는 최소 **한도·허용 작업 종류·유효기간**이 함께 발급돼야 한다
  (그렇지 않으면 §2.6의 "위임 권한 무제한 확대" 위험이 A2A 규모로 재발한다).

### S0(온보딩 시나리오 신설)에 대한 결론

FinAllQ 조사가 이미 답을 냈으므로 **S0을 별도 A2A 시나리오로 만들 필요는 없다** —
온보딩은 A2A 프로토콜이 아니라 **FinAllQ 자체 기능(기업 고객 등록 API + 초대 API,
FinAllQ 백로그 #126·#127)**으로 처리된다. QMesh 쪽에서 할 일은:

1. MaintQ가 FinAllQ의 기업 고객으로 **먼저 등록되어 있다는 것을 전제**로 S5~S16을 설계한다
   (InsuQ의 S7이 "전제: 기가입 보험 존재"로 이미 같은 패턴을 쓰고 있다 — 일관성 있음).
2. 그 등록 시점에 발급되는 **파트너 자격증명**(액세스 토큰 발급용 client credentials)이
   QMesh의 `requester.finallq_company_id`가 가리킬 실제 값과, actor 토큰의 클레임을
   채운다.
3. QMesh 문서에는 "온보딩은 FinAllQ 자체 기능이 전제조건"이라는 선행조건 문구만
   남기고, 구현은 FinAllQ 백로그(#126~130)를 따른다.

## 인증/인가 분리 모델 — 옵션 C 채택 (2026-08-13, InsuQ 조사)

S8·S13에서 FinAllQ가 InsuQ의 `verify-collateral-insurance`를 2차 홉으로 호출할 때,
"인증을 FinAllQ가 대신 하는가, InsuQ가 다시 하는가"가 미해결로 남아있었다. InsuQ
조사가 다음으로 정리했다 — **채택**:

- **인증은 FinAllQ에 위임한다** — 신뢰 앵커(KYB)는 하나여야 하고, InsuQ에는 애초에
  기업 실재를 확인할 KYB 수단이 없다.
- **인가(권한 판단)는 InsuQ가 자체 보유한다** — 자원(보험 계약 정보) 접근 여부는
  자원을 가진 쪽이 판단해야 한다. 결정 1의 "서버가 보유한 위임 테이블"에서 그 서버가
  바로 InsuQ다 — 세 프로젝트 중 A2A 요청에 응답만 하는 쪽이 InsuQ뿐이기 때문이다.

**2차 홉 질문에 대한 답**: 인증은 중복이 아니고, 인가는 생략 불가하다. FinAllQ가
자기 토큰으로 InsuQ를 부르면, InsuQ가 검증하는 actor는 **FinAllQ**이지 MaintQ가
아니다 — 대상 자체가 다르므로 "이중 인증"이 아니다. 그리고 **S8·S13은 actor≠subject인
사례**다(actor=FinAllQ, subject=MaintQ 소유 건물) — 이는 1번 항목("잠정적으로
actor=subject 고정으로 가정한다")의 **첫 반례**이며, 그 가정이 S5~S16 전체가 아니라
"MaintQ가 직접 호출하는 스킬"에만 한정된다는 걸 보여준다. 실제로 달라지는 건 인증
강도가 아니라 **권한 범위** — FinAllQ가 받는 grant는 `verify-collateral-insurance`
하나뿐이고, `notify-asset-change`·`notify-risk-change`·`claim-insurance`(통지·청구)는
MaintQ 직접 호출로만 허용된다.

**M1 단계 권고(InsuQ 채택)**: 인가 테이블은 지금 스키마에 넣고, 토큰 검증부는 목업
유지. 스키마는 나중에 바꾸는 비용이 크고, 검증부는 함수 하나만 갈아끼우면 되기 때문.

## 각 프로젝트가 지금(QMesh 이전) 준비해야 할 것 (2026-08-13 갱신)

| 프로젝트 | 준비 사항 | 상태 |
|---|---|---|
| FinAllQ | 기업 고객 등록 API(#126) · 발급자 lockout(#129) · `findById(1L)` 시한폭탄 수정(#128) · 직원 초대 발급·수락 API(#127) · 파트너 자격증명(client credentials, 비대칭 서명) 발급 체계 · 연결 승인 절차(#131) · 스코프별(#131) 허용 작업 분리 · 파트너 관리 화면(#132) · market_context 원천 정비(#133, ESG는 영구 null 가능성 인지) | **126~128 구현·커밋 완료**(0bf2845·e133661·99826e8, 브랜치 `feat/corporate-onboarding`, 아직 main 미머지). 129~133은 Pool 유지 |
| MaintQ | `assets`에 컬럼 얹지 않고 별도 `partner_links` 테이블(`link_state`+`external_ref` 분리, CHECK 제약). `request_chain_id`는 traces에 nullable 컬럼, subject 원문은 tool_result 행에 봉투째 보관(컬럼 복제 안 함), 인증 헤더는 저장 시 제외 | D91~D94 등재 완료(`docs/10_DECISIONS.md`). 코드 미착수, `/sprint`로 스테이지 진행 예정 |
| InsuQ | 계약 대장을 6필드 단일 테이블이 아니라 `partner_subject_refs`(외부 참조)·`policies`(증권 헤더)·`policy_objects`(목적물별 담보, `insured_value`·`coinsurance_ratio`·`deductible` 포함)로 분리. `policy_id`는 InsuQ가 발급하는 값이므로 외부 참조 테이블이 아니라 `policies.policy_no`로. 인가 테이블은 지금 넣고 토큰 검증부는 목업 유지 | 조사·설계 완료(`docs/A2A_IDENTITY.md` 신규 작성, 아직 미커밋). golden set 제작 중이라 API 명세 소폭 변경 가능성 있음 — 시드 데이터 채우기는 golden set 안정화 후로 미룸 |

## 확인·정리 필요 (진행 중)

1. **`A2A_CONTRACTS.md`(5개 스킬) vs InsuQ `07_BACKLOG.md` Track 7(4개, `advise-policy-renewal`
   누락) — 백로그가 SSOT라고 선언돼 있는데 시나리오가 안 맞았다.** → **결정: `07_BACKLOG.md`
   Track 7에 `advise-policy-renewal`(S7)을 추가한다.** `A2A_CONTRACTS.md`는 A2A_Q의
   시나리오 목록(11_A2A_SCENARIOS.md)을 그대로 반영하는 인덱스로 설계했으므로, 어긋난
   쪽(백로그)을 A2A_Q 기준에 맞춰 채우는 게 맞다.
2. **`/run` 엔드포인트를 backend(Spring)와 ai-engine(Python) 중 어디에 둘지 미정이었다.**
   → **결정: Spring(backend).** 계약 대장(RDB)과 인증이 이미 Spring 소관인데 수신부만
   ai-engine에 두면 "Spring이 신원·권한 데이터를 모른 채 소유권 경계를 넘는" 상황이
   생긴다. `05_ARCHITECTURE.md`의 기존 계층 분리 원칙("Spring은 어떻게 검색·판정하는지
   모르고, ai-engine은 누가 물었는지 모른다")과도 일치한다.
3. **MaintQ가 제안한 BLD-D = NOT_LINKED 대조군이 MaintQ 자체 시드(BLD-D 자산 3건 전부
   insured=1)와 어긋났다.** → **결정: MaintQ는 바꿀 필요 없음.** InsuQ가 별도로
   BLD-E를 대조군으로 확보하는 쪽으로 진행한다. 실제 충돌이 아니라 각자 자기 쪽에서
   해결 가능한 문제였다.

## 미결 사항 재정리 (2026-08-21) — 해결됨 3건 · 보류 2건

FinAllQ 조사 §5의 "QMesh 설계 시 답해야 할 질문"을 옮겨온 것이다. 5건 중 3건(①②③)은
이미 본문에 결론이 있었고, 2건(④⑤)은 원문에도 "FinAllQ 구현 시 결정"이라 명시돼 있어
QMesh가 지금 대신 정할 수 없다 — 그 구분을 아래에 라벨로 명확히 한다:

1. ✅ **해결됨 — MaintQ는 자기 회사 건만 요청하나, 제3자 대리를 하나?** actor/subject가
   항상 같은지, 달라질 수 있는지에 따라 위임 테이블 설계가 갈린다. **S8·S13(FinAllQ가
   InsuQ를 2차 홉으로 부르는 경우)은 이미 actor≠subject의 실제 사례로 확인됐다**(위
   "인증/인가 분리 모델" 참조). 다만 MaintQ가 직접 호출하는 나머지 스킬(S5·S6·S7·
   S11·S12·S14·S16)은 여전히 actor=subject로 가정한다 — 대리 시나리오는 아직 없다.
2. ✅ **해결됨 — 파트너 자격증명 발급 주체와 연결 절차** (확정 2026-08-13)

   **결론: FinAllQ ADMIN 콘솔이 발급 주체가 맞다.** QMesh는 신뢰의 근원이 아니라
   프로토콜 중계자로 남는다 — README의 "QMesh는 각 프로젝트 내부를 모르는 블랙박스"
   원칙과 맞다.

   **그리고 자격증명은 회사가 아니라 사람에게 발급한다.** 즉 "MaintQ라는 회사"가
   자격증명을 받는 게 아니라, MaintQ 측의 담당자(예: 재무팀장)가 발급 대상이다.
   이건 앞서 FinAllQ 자체 조사가 확정한 §2.5 초대 기반 온보딩 모델과 정확히 같은
   결 — 기업 신원은 사람에게 붙고, 그 사람이 회사를 대표해 자격증명(기계 신원)을
   발급받는 구조다.

   **연결 절차 자체가 3단계로 확정된다** (2026-08-13 최종 정정 — FinAllQ 자체 검토가
   순서 오류를 잡았다: 연결 승인이 생기기 전에 회사가 먼저 company(CORPORATE)로
   존재해야 신용한도·계좌·여신을 매달 수 있다):

   ```
   [1] 등록          FinAllQ ADMIN이 MaintQ를 기업 고객(CORPORATE)으로 등록
                      (백로그 #126 — QMesh 없이도 필요한 층 ①, 이미 구현·커밋됨)
   [2] 연결 승인      MaintQ 담당자 ↔ FinAllQ ADMIN이 연결 자체를 승인
                      ("이 회사와 통신하는 것을 허용한다" — 백로그 #131)
   [3] 자격증명 발급  승인 완료 시점에 FinAllQ ADMIN이 파트너 자격증명 발급
                      (client credentials, 허용 작업·한도·유효기간 함께 — 백로그 #131)
   [4] 기계 단계      그 자격증명으로 MaintQ 에이전트가 액세스 토큰을 스스로 발급받아
                      (S5~S16) 스킬 호출 — 이 이후부터만 "에이전트끼리 대화"가 시작된다
   ```

   즉 **"회사 간 연결"과 "에이전트 간 통신"이 명확히 분리된다** — 사람이 연결
   자체를 승인하기 전까지는 어떤 스킬도 호출될 수 없다. 이건 QMesh 관통 원칙
   ("돈·계약이 움직이는 건 요청/제안 + 사람 승인")을 **개별 스킬 호출 시점이
   아니라 연결 자체의 최초 1회에도** 적용하는 셈이다. S5(출금)만 사람 승인을
   거치는 게 아니라, **연결 자체가 사람 승인을 거친다** — 그 다음에는 S6·S7·S8같은
   조회/상담성 스킬도 이미 승인된 연결 위에서만 오간다.

   **허용 작업은 한 덩어리로 주면 안 된다** (2026-08-13 FinAllQ 검토에서 추가 확정) —
   상담(S6·S16)과 출금(S5·S12)은 위험도가 다른데, 하나로 묶으면 상담용 연결이
   출금 권한까지 갖게 된다. 최소 3단계로 나눠 자격증명 스코프를 부여한다:

   | 등급 | 스킬 | 실행 위험 |
   |---|---|---|
   | 조회/상담 | advise-hedge(S6), advise-financing(S16) | 없음 — 제안만 |
   | 심사 | assess-loan(S8), assess-used-equipment-loan(S13) | 없음 — 결과가 조건부 승인일 뿐, 실행 아님 |
   | 자금이동 | request-withdrawal(S5), request-settlement(S12) | 높음 — `input-required` 2단 승인 필수 |

   **S15(advise-replacement-financing)는 이 분류와 별개로 추가 제약이 필요하다** —
   이 스킬은 "누가 부를 수 있는가"(자격증명 스코프)가 아니라 "언제 부를 수 있는가"
   (InsuQ claim-insurance 응답 이후에만)가 문제라, 체크박스형 허용 목록으로는 표현되지
   않는다. 해법: **자격증명 스코프가 아니라 체인 연속성 검증으로 해결한다.** FinAllQ가
   이 스킬 요청을 받으면, 같은 `request_chain_id`로 시작된 InsuQ `claim-insurance`가
   실제로 존재하고 완료되었는지를 서버가 확인한 다음에만 처리한다. 이 제약은
   `advise-replacement-financing.json`의 `direction` 필드에 이미 서술되어 있으나,
   구현 시점에 이 검증을 **스코프와 별개의 서버측 검증 로직**으로 구현해야 함을 명시한다.

   **FinAllQ가 이 검증을 검토하며 새 정책 미결을 남겼다(2026-08-13)** — 체인 연속성
   검증은 InsuQ 조회를 수반하는 외부 호출이라 캐싱 대상이고, 더 중요하게는 **조회
   실패 시 거절할지 보류할지 정책이 필요하다**(무조건 거절 = InsuQ 장애가 곧 FinAllQ
   서비스 거절 전파, 무조건 통과 = 검증 무의미). **결정: S15는 위 등급표에서
   "조회/상담 — 실행 위험 없음"에 해당하므로, 실패 시 즉시 거절(4xx)이 아니라
   fail-soft(제한된 재시도 + 백오프, 그래도 실패하면 그때 거절)로 처리한다.**
   실행 위험이 없는 스킬인데 InsuQ 장애를 FinAllQ 서비스 거절로 곧장 전파하는 건
   과하다.

   이 만큼 새로 생기는 설계 과제: **"연결 승인" 자체를 QMesh Task로 표현할지,
   FinAllQ 내부 절차(ADMIN 콘솔 UI)로만 처리할지.** 잠정 결론: 연결 승인은 QMesh
   프로토콜 밖의 일회성 절차(FinAllQ ADMIN 콘솔 + MaintQ 담당자 간 오프라인/수동
   확인도 가능)로 두고, QMesh는 그 결과물(발급된 자격증명)만 전제로 삼는다 —
   연결 자체의 승인 UX까지 A2A 프로토콜로 묶으려고 하지 않는다(과잉설계).

   **파트너 화면은 #130과 별개로 간다** (백로그 #132) — 사람 계정 vs 머신 신원 /
   ADMIN+담당자 vs ADMIN 전용 / 72h 1회성 vs 장기+폐기 / 계정 생성 vs 시크릿 노출·출금권한
   부여로 네 축이 다 다르다 — 합치면 기업 담당자가 접근하는 화면에 파트너 시크릿이
   엮인다. 부수적으로 #130이 ADMIN 등록 폼과 담당자 초대 화면 두 사용자를 섞고
   있다는 지적도 남겼다 — 착수 시점에 놓치면 안 되는 것.

3. ✅ **해결됨 — "대출심사"(assess-loan 등)의 결과는 조언인가 실행인가?** `request-withdrawal`·
   `request-settlement`는 명시적으로 `input-required`를 거치므로 실행이 아니다.
   `assess-loan`·`assess-used-equipment-loan`은 "심사 결과"이지 여신 실행 자체가
   아니므로, 이체 결재 라인(`ApprovalPolicy`)과는 별개 — 대출 실행이 필요해지면
   그건 별도로 `request-withdrawal`을 다시 태워야 한다는 뜻. **이 관계를 스키마
   `response.decision`(approved/conditional/rejected)에 "심사 결과일 뿐, 실행 아님"
   주석으로 이미 반영해뒀다.**
4. ⏸ **FinAllQ 구현 착수 시 결정 (QMesh 비차단) — 출금 요청은 기존 이체 파이프라인
   (FDS→결재→잔액차감)을 타나, 별도 경로인가?** 타야 한다면
   `transfer_request.requester_user_id` NOT NULL 제약과 충돌한다(외부 요청에는 요청자
   user가 없다). 후보:
   파트너를 서비스 계정 user row로 만들되 `principal_type` 구분 컬럼을 둬서
   `ApprovalPolicy`가 머신 주체를 사람으로 오인하지 않게 한다(FinAllQ 조사 §2.6 말미).
5. ⏸ **FinAllQ 구현 착수 시 결정 (QMesh 비차단) — 감사 로그에 외부 actor를 어떻게
   남기나?** 현재 `audit_log.actor_user_id`는 사람 user를 전제한다. 4번과 같은 해법
   (서비스 계정 + `principal_type`)이면 자연히 해결된다.

## MaintQ 구현 세부 결정 (2026-08-13, MaintQ 자체 조사)

QMesh와 무관하게 MaintQ 내부에서만 정해지는 세부 사항이지만, 다른 두 레포가 비슷한
trace/로그 설계를 할 때 참고할 수 있어 요약해 남긴다.

- **왜 subject를 trace 컬럼으로 복제하지 않는가**: `link_state`가 나중에 바뀔 수 있어
  과거 trace에 박제된 값과 현재 매핑이 어긋나면 판정 근거가 사라진다. 파생값을
  복제하면 진실의 원천이 두 곳이 된다.
- **S5(자금이동)의 재현 요구는 원문 보관으로 해결**: "그때 어느 company_id로
  보냈나"가 필요하면, 그 시점 trace 이벤트의 `tool_result` 행에 실린 요청·응답
  원문(payload)을 직접 연다. `event_type` 신설(비용이 큼: DDL CHECK + 스파이크
  2종 추가)보다 싸다.
- **⛔ 인증 헤더는 저장 대상에서 반드시 제외**: 원문을 통째로 저장하는 결정이므로,
  액세스 토큰이 payload에 섞여 있으면 그대로 DB에 평문으로 남는다. 결정 1의
  "토큰(actor)은 헤더, payload는 subject"라는 구조를 저장 시점에도 그대로
  지켜야 한다.
- **원문을 사람이 여는 경로는 미결로 유보**: 현재 조회 API(`read_trace`)는
  `tool_payload`를 의도적으로 포함하지 않는다. 지금은 DB 직접 조회로 충분하고,
  실제 사용 요구(예: 재무 담당자의 감사 조회)가 생기면 그때 전용 API를 만든다 —
  지금 만들면 쓸 사람 없는 API에 인증·권한까지 미리 설계하는 낭비다.
- **D91~D94 등재 완료**(`MaintQ/docs/10_DECISIONS.md`) — partner_links 스키마(D91),
  seed 전제+대조군(D92), 자격증명 위치(D93), trace 배치(D94)가 서로를 근거로
  물리게 기록되어 있어, 하나만 읽어도 전체 설계 흐름이 추적된다.

## InsuQ 구현 세부 결정 (2026-08-13, InsuQ 자체 조사)

- **시드 전략**: MaintQ 실측(BLD-A~D, `POL-2026-FIRE-01`이 8행에 복제, `AST-L3-LIFT`
  미부보)에 맞추되, 같은 문자열이 두 레포에 각각 박히는 걸 막기 위해 `A2A_Q/docs/fixtures/`에
  SSOT를 두고 양쪽이 인용 + InsuQ 자가검증 테스트로 어긋남을 잡는다. 성공 케이스만
  심으면 데모가 거짓말을 하므로 **실패 모드 3종(미매핑/grant 폐기/증권 만료)**을
  반드시 함께 심는다. `finallq_company_id`는 심지 않는다 — A2A_Q가 "물리적으로 null"
  이라고 명시했는데 가짜 값을 심으면 그게 사실처럼 굳어버린다.
- **BLD-D 대조군 문제**: MaintQ가 제안한 BLD-D=NOT_LINKED가 MaintQ 자체 시드와
  어긋나는 걸 발견 → InsuQ가 BLD-E로 별도 대조군을 확보하기로 해 MaintQ 쪽 변경
  없이 해결(위 "확인·정리 필요" §3 참조).

## 부록 — 인용 원본

이 문서의 결정 1·온보딩 모델·미결 사항은 전부 `FinAllQ/docs/A2A_IDENTITY.md`
(2026-08-13, 특히 §2.5~§2.7, §3.2, §5)를 원본으로 한다. `partner_links` 스키마·
trace 배치 결정은 `MaintQ/docs/A2A_IDENTITY.md`(2026-08-13)가 원본이다.
`partner_subject_refs`·`policies`·`policy_objects` 분리, 인증/인가 분리 모델은
`InsuQ/docs/A2A_IDENTITY.md`(2026-08-13, 신규 작성·미커밋)가 원본이다. 상세 근거
(실측 SQL, 코드 인용, 대안 비교표)는 각 원본 문서를 참조할 것 — 이 문서는 QMesh
계약에 필요한 결론만 요약한다.
