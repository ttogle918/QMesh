# MaintQ A2A 발신 트리거 — S12·S13 설계 (2026-08-30)

## 배경

계약 13종은 **수신부가 전부 구현됐는데 MaintQ 발신부는 3종뿐이다**
(`lookup-clause`·`request-withdrawal`·`assess-loan`). 나머지 10종은 FinAllQ·InsuQ가
만들어놨지만 MaintQ가 호출하지 않아 동작하지 않는다 — `A2A_DIAGRAMS.md` §⑦이 이를
"가장 중요"로 표시해 두었고, 시연 범위를 3종으로 확정하며 의도적으로 미뤄둔 상태다
(MaintQ `docs/07_BACKLOG.md` P34).

이 설계는 그중 **MaintQ 도메인에 실제 데이터가 있는 2종**만 다룬다.

## 범위 결정 — 5종 중 2종만 만든다

MaintQ가 각 스킬의 필수 입력을 실제로 채울 수 있는지 `data/seed.py` 스키마로 대조했다.

| 스킬 | MaintQ 데이터 | 판정 |
|---|---|---|
| **S13** `assess-used-equipment-loan` | `assets.building_id` · `acquired_at` · `last_inspection_date` · `inspection_valid_until` · `safety_inspection_target` | ✅ **만든다** |
| **S12** `request-settlement` | `assets.has_lien` · `lien_creditor` · `lien_consent_ref` · `status` · `decisions` | ✅ **만든다** |
| S6 `advise-hedge` | 🔴 **통화·외화 데이터 0건** (`seed.py` 전체에 `currency`/`USD`/`환율` 매치 없음) | ❌ 만들지 않는다 |
| S16 `advise-financing` | 트리거가 될 도메인 이벤트가 없다 | ❌ 만들지 않는다 |
| S15 `advise-replacement-financing` | 🔴 2차 홉 전용인데 **MaintQ에 `claim-insurance` 발신 흐름 자체가 없다** | ❌ 만들지 않는다 |

**만들지 않는 3종은 "미착수"가 아니라 "데이터 없음"으로 문서에 닫는다.** S6를 만들려면
공급사에 통화 컬럼을 신설하고 환노출을 지어내야 하는데, 이 프로젝트는 모르는 값을
지어내지 않는 것을 원칙으로 삼아 왔다(D62 NULL=모름, D74 실측 아니면 NULL,
D76 구조 모르면 나열만). 스킬 개수를 늘리려고 그 원칙을 깨지 않는다.

S15는 사실상 **두 스킬 작업**(`claim-insurance` 발신 + S15)이므로 별도 사이클로 다룬다.

---

## 검증된 사실 — LIEN-CONSENT는 교착이 아니다

S12 계약이 `decision_id`(처분 결정)를 필수로 요구하는데, LIEN-CONSENT는 `BLOCKING`
룰이라 처분 결정을 막는다. 순서 교착으로 보였으나 **코드를 읽어 확인한 결과 아니다.**

1. **LIEN-CONSENT는 서명을 막지 draft 생성을 막지 않는다.**
   `decisions.state` 전이는 `ALLOWED_FROM = {"pending": "draft", "signed": "pending",
   "rejected": "pending"}` — **draft → pending → signed** 3단계이고, 차단 판정은 서명
   단계에서만 걸린다(`decisions.py`: `verdict in BLOCKING_VERDICTS and override is not
   True → OverrideRequired`). draft 결정은 `decision_id`를 갖고 존재한다.
2. **담보 자산도 evidence_bundle이 만들어진다.** `build_evidence_bundle.py`가 계약
   조항을 `law_text_unavailable` 검사에서 의도적으로 제외했고, 그 이유를 "검사에 넣으면
   `LIEN-CONSENT`가 걸린 자산의 번들이 **구조적으로 영원히 불가능해진다**(`04 §14` 명시)"로
   적어두었다. 즉 이 경우를 설계 단계에서 이미 보장해 뒀다.
3. **draft 결정 생성 경로가 실재한다.** `mcp_server/tools/generate_disposal_document.py:329`가
   `INSERT INTO decisions`를 `state='draft'` · `signed_at=NULL` · `override=0`으로 수행한다.

**따라서 계약을 고칠 필요가 없다.** `decision_id`는 draft 결정을 가리키면 된다.

### 해소는 `flags`가 아니라 `assets.lien_consent_ref`에 쓴다

`data/rules/rules/LIEN-CONSENT.json`:

```json
"disposal_type": "BLOCKING",
"required_facts": ["has_lien", "lien_creditor"],
"trigger": {"all_of": [
  {"field": "has_lien", "op": "eq", "value": true},
  {"field": "lien_consent_ref", "op": "is_null"}]},
"resolve_options": ["금융기관 동의서 확보 후 첨부 (lien_consent_ref 등록)",
                    "대출 상환 후 근저당 말소"]
```

룰이 읽는 필드는 **`lien_consent_ref`** 하나다. `flags` 테이블은 해소 라이프사이클
(`OPEN`→`RESOLVED`, `resolved_by`, `evidence_ref`)이 설계돼 있으나 **쓰기 경로가 없어
0행**이고, 룰 평가에 관여하지 않는다 — 여기 쓰는 것은 해소가 아니다.

**S12는 정확히 `resolve_options[1]`("대출 상환 후 근저당 말소")의 자동화다.** 계약 설명도
"설비 매각대금으로 잔여 대출을 상환할지 판단을 요청한다"로 같은 말을 한다.

---

## S13 — `assess-used-equipment-loan`

기존 `assess-loan`(S8)의 형제 스킬이고 트리거 성격도 같다(사람이 여신 심사를 요청).
**새 패턴을 만들지 않고 S8을 그대로 따른다.**

### 인터페이스

- **엔드포인트**: `POST /api/a2a/assess-used-equipment-loan`
  (`backend/routers/a2a.py` — `assess-loan`이 있는 자리)
- **요청 본문**: `{asset_id: str, loan_amount: float}`
- **payload 빌더**: `build_assess_used_equipment_loan_payload(asset_id, loan_amount,
  request_chain_id, db_path=None) -> dict`

### 필드 출처

| 계약 필드 | 출처 |
|---|---|
| `loan_amount` | 호출자 입력 |
| `collateral_building_id` | `assets.building_id` |
| `equipment_year` | `assets.acquired_at`의 연도 |
| `inspection_data` | `assets.last_inspection_date` · `inspection_valid_until` · `safety_inspection_target` |
| `requester.finallq_company_id` | 기존 `get_finallq_company_id()` 재사용 |

**S8과 달라지는 점:** S8은 `collateral_building_id`를 인자로 받지만 S13은 자산 하나에서
4필드를 파생한다. 그래서 호출부는 `asset_id`만 받고 빌더가 DB를 읽는다 —
`build_request_withdrawal_payload()`가 `supplier_id`로 `suppliers`를 조회하는 것과 같은
관례다.

### 값이 없을 때

`last_inspection_date`가 NULL이면 **그 키를 생략한다**(D62 — NULL 컬럼은 키 자체가 없다).
빈 문자열이나 0으로 채우지 않는다. `inspection_data`가 통째로 빌 수 있으며, 그것은
계약 위반이 아니라 "점검 이력 없음"이라는 사실의 정직한 전달이다.

---

## S12 — `request-settlement`

**MaintQ 발신 스킬 중 처음으로 응답이 MaintQ 상태를 바꾸는 스킬이다.** 기존 3종은
조회하거나(`lookup-clause`·`assess-loan`) 남의 시스템을 움직였을 뿐(`request-withdrawal`)
자기 블로커를 풀지 않았다.

### 흐름

```
draft DISPOSAL 결정 존재 (LIEN-CONSENT로 서명 불가)
  → POST /api/a2a/request-settlement (decision_id = 그 draft)
  → FinAllQ 판정
  → lien_released: true  →  assets.lien_consent_ref 기록
  → 재산출 시 LIEN-CONSENT 미발화 → 서명 경로 열림
  → ★ 서명은 사람이 한다
```

### 인터페이스

- **엔드포인트**: `POST /api/a2a/request-settlement`
- **요청 본문**: `{decision_id: str, sale_amount: float, outstanding_loan: float,
  approved_by: str, prepayment_fee: float | None}`
- **payload 빌더**: `build_request_settlement_payload(decision_id, sale_amount,
  outstanding_loan, approved_by, prepayment_fee, request_chain_id, db_path=None) -> dict`

### 필드 출처

| 계약 필드 | 출처 |
|---|---|
| `decision_id` | 호출자 입력 (draft DISPOSAL 결정) |
| `sale_amount` · `outstanding_loan` · `prepayment_fee` | 호출자 입력 — **MaintQ가 알 수 없는 값이다.** 매각 금액과 대출 잔액은 MaintQ 도메인 밖이다 |
| `lien_creditor` | `assets.lien_creditor` (`decision_id` → `decisions.asset_id` → `assets`) |
| `approved_by` | 호출자 입력 — 아래 근거 참고 |

`prepayment_fee`는 계약상 optional이므로 값이 없으면 키를 생략한다.

**`approved_by`를 `decisions.reviewed_by`에서 가져오지 않는 이유:** draft 결정은
`reviewed_by`가 **NULL**이다(`generate_disposal_document.py`가 `override=0` ·
`override_reason`/`reviewed_by`/`signed_at`=NULL · `state='draft'`로 INSERT 한다).
`reviewed_by`는 서명 시점에 채워지는데, 이 스킬은 **서명 전에** 발신되므로 그 자리에서
읽으면 항상 NULL이고 계약 필수 필드가 빈다.

의미상으로도 호출자 입력이 맞다. `approved_by`는 *처분 결정을 서명한 사람*이 아니라
**정산 요청을 승인한 사람**이다 — 계약 설명의 "2단 승인"이 가리키는 것이고,
`request-withdrawal`이 `approved_by`에 `po.decided_by`(발주 승인자)를 싣는 것과 같은
자리다. 처분 서명자와 정산 승인자는 다른 사람일 수 있다.

### 🔴 지켜야 할 불변식 — 자동 서명 금지

**`lien_released: true`가 와도 결정을 자동 서명하지 않는다.** `assets.lien_consent_ref`만
기록하고 서명은 사람이 한다.

MaintQ는 `decisions` DDL의 CHECK 두 개로 **"사유 없는 우회 서명"을 스키마 수준에서
표현 불가능**하게 만들어 두었고, 불변식을 "BLOCKING 우회 처분 0건" · "서명 없는 처분
확정 0건"으로 명시한다. 외부 시스템의 응답 하나로 서명이 일어나면 그 불변식이
A2A 경로로 우회된다. `assess-loan`이 `conditional`을 받아도 대출을 자동 실행하지 않는
것과 같은 태도다(FinAllQ `mapping.py`의 "자동 승인 경로 없음").

### `lien_consent_ref`에 무엇을 쓰는가

**비어 있지 않은 의미 있는 참조**를 쓴다 — FinAllQ 응답을 특정할 수 있는 값
(`request_chain_id` 기반 문자열 등, 구현 시 확정).

🔴 **`''`(빈 문자열)을 절대 쓰지 않는다.** `seed.py` 검사 ⑱이 이를 데이터 불변식으로
잠가 두었다: `has_lien=1 AND trim(lien_consent_ref)=''`인 행이 있으면 안 된다. 규약은
`''` = "확인된 해당 없음" / `NULL` = "모름"이고, 빈 문자열을 쓰면 `is_null`이 False가
되어 **BLOCKING 룰이 조용히 미발화한다** — seed.py가 이를 "키 하나 빠뜨림으로 나는
최악의 오판"이라 적어 두었다.

### `lien_released: false`일 때

**아무것도 쓰지 않는다.** 플래그는 그대로 남고 결정도 그대로 막혀 있다. 응답의
`remaining_balance`·`action`은 trace에만 남긴다.

### ⚠️ 이 스킬은 판정만 한다 — FinAllQ 장부를 갱신하지 않는다

FinAllQ `decide_settlement()`는 **외부 호출·DB 조회가 0인 순수 함수**다(TASK-195의
명시적 설계 판정). 계약에 `loan_id`가 없어 어느 여신 레코드를 갱신할지 특정할 방법이
애초에 없기 때문이다. 따라서 응답의 `remaining_balance`는 **산술 결과이지 FinAllQ
장부에 반영된 잔액이 아니다.**

이것은 결함이 아니라 `assess-loan`(S8)과 같은 성격이다 — S8도 `conditional` 판정을
내리지만 대출을 실행하지 않는다(FinAllQ `mapping.py`의 "자동 승인 경로 없음"). **다만
모르고 쓰면 "정산이 끝났다"고 오해할 수 있으므로 여기 적어 둔다.** MaintQ는
`lien_released`만 소비하고 `remaining_balance`는 trace에만 남긴다.

FinAllQ Pool 200에 이 갭(`loan_id` 부재로 여신 잔액 미반영, 음수 `remaining_balance`
경계)이 이미 등재돼 있고 "A2A_Q 계약 갱신 협의 선행 필요"로 표시돼 있다. **이 설계의
범위 밖이다** — 수신부 계약 구조를 바꾸는 일이라 별도 사이클로 다룬다.

---

## 공통 구조 — 새 인프라는 만들지 않는다

두 스킬 모두 기존 3종과 같은 경로를 탄다:

```
routers/a2a.py 엔드포인트
  → a2a/payloads.py 빌더
  → a2a/client.py 발신 (인증 헤더·재시도·타임아웃 기존 것 재사용)
  → a2a/trace.py 기록
```

`auth_header.py`(D120 Bearer + `X-A2A-Partner-Id`)·`credentials.py`·`client.py`는
**변경하지 않는다.** 이 설계가 추가하는 것은 payload 빌더 2개, 엔드포인트 2개,
그리고 S12의 응답 소비 로직 하나뿐이다.

---

## 테스트

기존 관례대로 **외부 API 실호출 0건**으로 검증한다.

**payload 빌더 (단위)**
- 🧪 S13: 자산에서 4필드가 정확히 파생된다
- 🧪 S13: `last_inspection_date`가 NULL이면 **키 자체가 생략된다**(빈 문자열·0 아님)
- 🧪 S12: `decision_id` → `decisions.asset_id` → `assets.lien_creditor` 조회가 맞다
- 🧪 S12: `prepayment_fee`가 None이면 키가 생략된다
- 🧪 두 빌더 모두 필수 필드가 `None`으로 새지 않는다 — `request-withdrawal`이
  `error_code=None` 때문에 FinAllQ에서 400(`schema_validation_failed`)을 맞은 전례가
  있다(`payloads.py` 주석). `.get(k, default)`는 키가 없을 때만 default를 쓰고 값이
  None이면 그대로 돌려주는 함정을 같은 방식으로 확인한다

**엔드포인트 (통합)**
- 🧪 S13: 정상 응답이 계약 형태로 반환된다
- 🧪 S12 양성: `lien_released=true` → `assets.lien_consent_ref`가 **비어 있지 않은 값**으로 채워진다
- 🧪 S12 음성: `lien_released=false` → `lien_consent_ref`가 **여전히 NULL**이다
- 🧪 **S12 자동 서명 금지**: `lien_released=true` 이후에도 `decisions.state`가 `draft`
  그대로이고 `signed_at`이 NULL이다
- 🧪 **`lien_consent_ref`에 `''`가 절대 쓰이지 않는다** — 데이터 불변식 보호
- 🧪 상대가 5xx·타임아웃일 때 MaintQ 상태가 바뀌지 않는다

**회귀**
- 🧪 MaintQ 회귀 스위트 전체 — 기준선은 `CLAUDE.md` 「회귀 스위트」 절을 따른다
  (⚠️ pytest는 `DATABASE_URL`이 없으면 5432로 떨어져 매단다. 컨테이너는 5434)
- 🧪 `spikes/verify()` 검사 ⑱(담보 자산 동의서 표기 규약)이 계속 통과한다

---

## 범위 밖

- **S6·S16·S15** — 위 「범위 결정」의 근거로 닫는다. 문서에 "데이터 없음"으로 기록하고,
  나중에 통화 데이터나 `claim-insurance` 발신이 생기면 그때 별도 사이클로 다룬다
- **`flags` 테이블 쓰기 경로 신설** — 룰이 `flags`를 읽지 않으므로 이 목표에 필요하지
  않다. 해소 라이프사이클을 실제로 쓰기 시작하는 것은 그 자체로 별도 설계가 필요하다
  (누가 `resolved_by`인가, `WAIVED`는 누가 정하는가 등)
- **`decisions` 상태 전이 자동화** — 서명은 사람이 한다는 불변식이 이 설계의 전제다
- **`request-withdrawal`처럼 도메인 이벤트에서 자동 발신** — 두 스킬 모두 MaintQ가
  알 수 없는 값(대출금액·매각금액)을 사람에게서 받아야 하므로 자동 트리거가 성립하지
  않는다. 명시적 엔드포인트가 맞다
- **UI** — 이 설계는 엔드포인트까지다. 화면은 별건이다

## 미해결

- **`lien_consent_ref`에 넣을 참조 문자열의 형식을 확정하지 않았다.** `request_chain_id`
  기반이 유력하나, 이 필드는 원래 "금융기관 동의서 문서 참조"를 담는 자리라 A2A 정산
  참조를 넣는 것이 의미상 맞는지 구현 시 한 번 더 판단한다. 최소 요건은 **비어 있지
  않을 것**과 **나중에 출처를 되짚을 수 있을 것** 두 가지다
~~FinAllQ 수신부가 draft 결정의 `decision_id`를 받아들이는지~~ → **2026-08-30 해소.**
FinAllQ 세션 확인 결과 받아들인다. 단 **"허용하기로 결정해서가 아니라 검사할 수단이
없어서"**다 — `decision_id` 사용처가 `a2a_adapter/schemas.py:235`의 pydantic 필드 선언
한 줄뿐이고 `decide_settlement()`에 인자로 전달조차 되지 않는다. `approved_by` 해석도
양쪽이 일치했다(정산 요청 승인자, 수신부는 검증·echo 하지 않음).

그 구분이 중요해서 **계약에 명시했다**(A2A_Q `9d7cf91`) — 나중에 누군가 "`decision_id`는
서명된 결정을 가리킨다"고 가정하고 검증을 추가하면 이 순환이 조용히 깨진다. 구조는
바꾸지 않고 `description`만 추가했으므로 FinAllQ pydantic 모델은 영향받지 않는다.
