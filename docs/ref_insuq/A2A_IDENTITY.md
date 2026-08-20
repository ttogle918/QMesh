# A2A 신원 식별 — InsuQ 측 현황 조사 및 설계 메모

> 작성 2026-08-13. **조사·정리 문서이며 구현은 하지 않았다.**
> 상대 문서: `A2A_Q/docs/A2A_IDENTITY.md`(2026-08-13 개정, QMesh 확정본) ·
> `FinAllQ/docs/A2A_IDENTITY.md`(원본 조사) · `MaintQ/docs/A2A_IDENTITY.md`(MaintQ 회신).
> 절 구성은 나중에 합치기 쉽도록 세 문서와 같은 뼈대(조사 → 스키마 → 시드 → 인증 → 미해결)를 따랐다.
>
> A2A_Q §"각 프로젝트가 지금 준비해야 할 것" 표의 InsuQ 행이 **"요청됨, 회신 대기"** 상태였다.
> **이 문서가 그 회신이고, 회신 내용은 A2A_Q 쪽에 반영 완료됐다**(2026-08-13 — 스키마 3분할·
> `policy_id` 방향 정정·인증/인가 분리 옵션 C).
>
> ### 2026-08-13 확정 사항 (검토 회차 반영)
>
> | # | 확정 | 반영 위치 |
> |---|---|---|
> | 1 | **스킬 5개** — `advise-policy-renewal`(S7)을 백로그에 추가. `A2A_CONTRACTS.md`(5개)가 맞고 백로그를 A2A_Q 시나리오 기준으로 채운다 | `07_BACKLOG.md` 트랙7 서문·H01·H02 / §9-5 |
> | 2 | **A2A 수신부 = backend(Spring)** — 계약 대장(RDB)·인증이 Spring 소관이라 수신부만 ai-engine 에 두면 소유권 경계가 깨진다 | `07_BACKLOG.md` 트랙7 서문·H01·TASK-602 / §8 |
> | 3 | **미매핑 대조군 = `BLD-E`** — MaintQ 쪽 `BLD-D`는 안 바꾼다(전달 완료) | §6.3 / §9-3 |
> | 4 | **fail-soft (신규 정책, FinAllQ 검토에서 파생)** — S15 후속 체인에서 InsuQ 조회 실패 시 FinAllQ 가 즉시 거절이 아니라 **재시도+백오프 후 거절** | **§7.6 신설** |

## 0. 두 층을 구분한다

FinAllQ·MaintQ 문서와 같은 구분을 쓴다.

| 층 | 내용 | 이 문서의 상태 |
|---|---|---|
| **① 조사** | 지금 이 레포에 무엇이 있고 무엇이 없는가 (실측) | §1~§4. 확정 사실 |
| **② 설계 제안** | 무엇을 어떤 모양으로 채울 것인가 | §5~§8. **제안이며 미확정** — 사용자 확정 전까지 코드·스키마에 반영하지 않는다 |

## 0.5. 다섯 줄 요약

1. **계약 대장이 아직 없다.** `policies`·`business_sites`는 `07_BACKLOG.md` TASK-E01(트랙5)의
   **초안 문장으로만** 존재하고, backend 엔티티는 `User`·`UserIdentity`·`ConsultationSession`·
   `RefreshToken` 4종뿐이다. 즉 "컬럼을 추가할지"가 아니라 **"처음 만들 때 어떤 모양으로 만들지"**가 질문이다.
2. **`building_id`는 이미 초안에 있다 — 그런데 "누구의 키인지"가 안 적혀 있다.** TASK-E01은
   `business_sites(… building_id 포함)`이라고만 쓴다. 이름이 MaintQ 키와 같아서 같은 값으로
   착각하기 쉽지만, 소유자가 명시되지 않았다. §5는 이 이름을 **외부 참조 전용으로 분리**한다.
3. **`policy_id`는 방향이 반대다.** 이건 외부 참조 키가 아니라 **우리가 발급한 값**이고,
   MaintQ가 `assets.policy_id`에 복제해 들고 있다(실측 8행). 요청받은 6필드 초안의
   `external_owner_ref`와 같은 칸에 두면 in/out 방향이 섞인다.
4. **세 레포 중 위임 테이블을 실제로 가져야 하는 건 InsuQ뿐이다.** A2A_Q 결정 1의
   *"서버가 보유한 위임 테이블: partner_id → 다룰 수 있는 company_id 집합"* 에서 **그 서버가
   InsuQ**다(InsuQ는 항상 응답자). MaintQ는 호출자라 이 테이블이 필요 없고, FinAllQ는 발급자다.
5. **인증 주체 권고: 인증은 FinAllQ에 위임, 인가는 InsuQ가 자체 보유(§7 옵션 C).** 신뢰 앵커
   (KYB·연결 승인)를 두 곳에 두면 어긋나고, "이 파트너가 이 계약을 볼 수 있는가"는 계약 대장을
   가진 InsuQ만 판단할 수 있다. 단 **M1 단계에서는 토큰 검증부를 목업으로 두고 인가 테이블만
   먼저 스키마에 넣는다** — 스키마는 나중에 바꾸기 비싸고 검증부는 갈아끼우기 싸다.

---

## 1. 조사 ① — 계약 대장은 존재하지 않는다

### 1.1 실측

```
backend/src/main/java/com/insuq/domain/
  User.java                 (app_user — email·passwordHash·persona)
  UserIdentity.java         (OAuth provider 분리, TASK-706)
  ConsultationSession.java  (상담 세션 — userId nullable)
  RefreshToken.java
```

**계약·고객·사업장 엔티티는 0개다.** `PolicyIngestScheduler`가 있으나 이름과 달리 약관(policy
document) 수집 스케줄러이지 계약(insurance policy) 대장이 아니다 — **이름 충돌에 주의**한다.

- dev 프로파일: `jdbc:h2:mem:insuq`, `ddl-auto: update` (prod는 `validate`)
- **마이그레이션 도구 없음** — `backend/src/main/resources/`에 `application{,-dev,-prod}.yml` 3개뿐.
  FinAllQ의 `V1~V14` 같은 롤포워드 경로가 없다.

> **시사점**: FinAllQ는 "기존 스키마에 컬럼을 덧붙이는" 문제였고(§3 "마이그레이션 롤포워드로
> 값싸게 붙는다"), MaintQ는 "이미 시드된 `assets`를 안 건드리는" 문제였다. **InsuQ는 백지다.**
> 나중에 고치는 비용이 아니라 **처음에 결을 틀리는 비용**이 이 문서의 관심사다.

### 1.2 TASK-E01 초안 (`07_BACKLOG.md` E1) — 이것이 계약 대장의 원안

> `customers`(공통, `customer_type` 구분컬럼) + `individual_profiles`/`corporate_profiles`(1:1) +
> `business_sites`(기업 고객 전용, 1:N, **`building_id` 포함**) + `policies`(양쪽 공통,
> `customer_id`로 연결, 기업은 `business_site_id`로 사업장별 연결 가능)

그리고 트랙 7 선행 조건이 이렇게 못박아 뒀다 — *"TASK-E01이 **이미 계약 대장(정책 원장) 역할을
한다**. TASK-E01 없이는 스킬 핸들러가 조회할 데이터가 없다."*

**즉 계약 대장 = TASK-E01이다.** 별도 A2A 전용 대장을 새로 만들자는 게 아니라, TASK-E01을
설계할 때 A2A 요구를 같이 반영하는 것이 이 문서의 범위다.

---

## 2. 조사 ② — `building_id`는 있다. 문제는 "누구의 키인가"가 없다는 것

질문 1("외부(MaintQ) 참조 키로 명시적으로 받는 컬럼이 있는가")의 답은 **"컬럼 이름은 있고,
외부 참조라는 명시는 없다"** 이다. 두 가지로 읽힌다:

| 읽기 | 의미 | 결과 |
|---|---|---|
| (a) InsuQ 자체 건물 번호 | 우리가 사업장에 붙인 로컬 일련번호 | MaintQ의 `BLD-A`와 값이 다르다 → S7·S11·S14가 subject를 못 찾는다 |
| (b) MaintQ 참조 키 | MaintQ `assets.building_id`를 그대로 저장 | 우리 PK가 외부 시스템 값에 묶인다 → MaintQ가 키 체계를 바꾸면 우리 PK가 흔들린다 |

**둘 다 틀렸다.** 필요한 건 "우리 키 + 외부 키를 잇는 매핑"이지 한 컬럼이 두 역할을 겸하는
게 아니다. MaintQ가 D78(`insured`↔`policy_id` 분리)로 푼 것과 정확히 같은 모양의 문제다.

그리고 **A2A_Q 결정 1이 요구하는 성격("이 값만으로 요청을 승인하면 안 된다")을 컬럼 주석으로는
표현할 수 없다.** 주석은 강제력이 없다 — MaintQ 문서 §4.1이 같은 지적을 했다. §5는 이를
**구조로** 표현한다.

---

## 3. 조사 ③ — `policy_id`는 외부 참조가 아니다. 방향이 반대다

이게 요청받은 6필드 초안(`{building_id, policy_id, insurer, coverage_amount, expiry_date,
external_owner_ref}`)에서 가장 먼저 갈라야 할 지점이다.

| 값 | 원본 소유자 | 흐르는 방향 | InsuQ에서의 성격 |
|---|---|---|---|
| `building_id` (`BLD-A`) | **MaintQ** | MaintQ → InsuQ (inbound) | **외부 참조.** 우리가 해석해야 하는 남의 키 |
| `finallq_company_id` | **FinAllQ** | FinAllQ → InsuQ (inbound) | **외부 참조.** 단 온보딩 전까지 실체 없음(A2A_Q §결정 2) |
| `policy_id` / 증권번호 (`POL-2026-FIRE-01`) | **InsuQ** | InsuQ → MaintQ (outbound) | **우리 키.** 외부 참조 컬럼이 아니다 |

MaintQ 실측(`MaintQ/data/seed.py`)에서 `assets.policy_id = 'POL-2026-FIRE-01'`이 **8행에 복제**돼
있다. MaintQ 문서 §1.3이 이걸 *"자산 단위 사실이 아니라 사실상 건물·회사 단위 사실이 자산 행에
복제된 것"* 이라고 정리했다.

> **결론**: `policy_id`를 `external_owner_ref`와 같은 테이블·같은 결에 두면, **우리가 발급하는
> 값과 우리가 해석하는 값이 한 칸에 섞인다.** 증권번호는 `policies`의 자연키(`policy_no`)이지
> 외부 참조가 아니다.

---

## 4. 조사 ④ — 세 레포 중 위임 테이블이 필요한 건 InsuQ뿐이다

A2A_Q 결정 1의 구조를 역할별로 갈라 보면 이렇다.

| 레포 | A2A 역할 | actor 토큰 | subject 매핑 | **위임 테이블(인가)** |
|---|---|---|---|---|
| FinAllQ | 발급자 + 호출자(S8·S13 2차 홉) | 발급한다 | 자기 `company` | 자기 것 필요 |
| MaintQ | **호출자 전용** | 받아서 제시 | `partner_links`(제안) | **불필요** — 남을 인가할 일이 없다 |
| **InsuQ** | **응답자 전용** (`A2A_CONTRACTS.md` — *"항상 응답자"*) | **검증한다** | 매핑 필요 | **필수** |

A2A_Q 결정 1이 말한 *"서버가 보유한 위임 테이블: partner_id → 다룰 수 있는 company_id 집합"*
에서 **그 "서버"가 InsuQ**다. MaintQ 회신이 `partner_links` 한 테이블에 `link_state`(승인 상태)와
`external_ref`(식별자)를 함께 담은 것은 호출자 입장에서 맞는 설계지만, **응답자인 InsuQ는
그 둘이 다른 테이블이어야 한다** — 이유는 §5.3에 적는다.

### 4.1 부수 실측 — FinAllQ가 겪은 스키마 충돌은 InsuQ엔 없다

FinAllQ 미결 4번(`transfer_request.requester_user_id`가 NOT NULL인데 외부 요청엔 요청자 user가
없다)에 대응하는 문제가 InsuQ에도 있는지 확인했다. **없다** —
`ConsultationSession.userId`는 이미 nullable이다(*"Phase B(SSO) 전까지 항상 null — 지금은 익명
세션"*). A2A 요청을 상담 세션으로 남겨도 NOT NULL 충돌이 안 난다.

**단 뒤집으면 새 문제다**: nullable이라 **"로그인 안 한 사람"과 "머신 주체"가 구분되지 않는다.**
FinAllQ §2.6이 제안한 `principal_type` 구분 컬럼이 InsuQ에도 그대로 필요하다(§9-4).

---

## 5. 제안 ① — 스키마: 6필드를 세 결로 쪼갠다

**질문 1에 대한 직접 답변: 요청받은 `{building_id, policy_id, insurer, coverage_amount,
expiry_date, external_owner_ref}` 6필드를 한 테이블로 만들면 안 된다.** 결이 셋 섞여 있다.

| 필드 | 결 | 갈 곳 |
|---|---|---|
| `building_id`, `external_owner_ref` | **외부 참조(subject 해석)** | `partner_subject_refs` (신규) |
| `insurer`, `expiry_date` | **증권 헤더** | `policies` (TASK-E01) |
| `coverage_amount` | **목적물별 담보** | `policy_objects` (신규) |
| `policy_id` | **우리 키** — 외부 참조 아님(§3) | `policies.policy_no` |

### 5.1 왜 `policy_objects`를 나누는가 — MaintQ 실측이 요구한다

MaintQ 시드는 **증권 1개(`POL-2026-FIRE-01`)가 건물 4개(`BLD-A~D`)를 덮는다.** TASK-E01 초안대로
`policies.business_site_id` 하나만 두면 이 사실을 표현하려고 **같은 증권을 4행 복제**하게 되고,
이건 MaintQ 문서 §2가 경고한 drift(한 행만 안 고쳐지는 사고)를 InsuQ 쪽에서 그대로 재생산한다.

화재보험 실물 구조도 그렇다 — 증권 하나에 목적물 명세가 여러 줄 달린다.

### 5.2 `coverage_amount` 하나로는 S8·S13을 못 푼다 (중요)

트랙7 TASK-H02가 `verify-collateral-insurance`에 요구하는 것은 *"화재보험 유효성·보장 금액 확인 →
비례보상(요구 담보 대비 부족분) 계산"* 이다. 재물보험의 비례보상은 **가입금액 하나로 계산되지
않는다** — 보험가액과 부보비율이 있어야 한다.

```
지급보험금 = 손해액 × 보험가입금액 / (보험가액 × 부보비율)
             ~~~~~~   ~~~~~~~~~~~~   ~~~~~~~~  ~~~~~~~~
             사고      coverage_amount  insured_value  coinsurance_ratio
```

⚠️ **위 식은 재물보험의 일반형이고 상품마다 다르다.** 트랙4 코퍼스(비지니스패키지·동산종합 등)의
해당 조항을 인용해 계산해야 하며, **계산 결과도 단정 표현으로 회신하지 않는다**(절대 원칙 1).
`"담보로 충분합니다"`가 아니라 `"요구담보 5억 대비 가입금액 3억 — 부족분 2억, 근거: <상품>
<policy_part> 제N조 M항, p.X"` 형식이다.

→ 따라서 `insured_value`(보험가액)·`coinsurance_ratio`(부보비율)·`deductible`(자기부담금, S15용)이
스키마에 **필요하다.** 6필드 초안에는 없다.

### 5.3 제안 DDL (미확정)

```sql
-- ── TASK-E01 계약 대장 (이 문서가 A2A 요구를 반영해 보강한 부분만 표시) ──

CREATE TABLE business_sites (
  business_site_id  BIGINT PRIMARY KEY,     -- ★ InsuQ 로컬 키. 외부 값에 묶지 않는다
  customer_id       BIGINT NOT NULL,
  site_name         VARCHAR(128) NOT NULL,
  address           VARCHAR(255)
  -- ⛔ building_id 컬럼을 여기 두지 않는다 — 남의 키를 우리 테이블의 사실로 적지 않는다(§2)
);

CREATE TABLE policies (
  policy_id         BIGINT PRIMARY KEY,     -- 내부 PK
  policy_no         VARCHAR(64) NOT NULL UNIQUE,  -- 'POL-2026-FIRE-01' — 우리가 발급, 외부로 나감(§3)
  customer_id       BIGINT NOT NULL,
  product_code      VARCHAR(64) NOT NULL,   -- 트랙4에서 실제 파싱·인덱싱한 상품과 1:1 (TASK-E01 요구)
  insurer           VARCHAR(64) NOT NULL,
  effective_date    DATE NOT NULL,
  expiry_date       DATE NOT NULL,
  cancelled_at      DATE                    -- 해지. NULL=해지 안 됨
  -- ⛔ 'ACTIVE/EXPIRED' 같은 파생 상태 컬럼을 두지 않는다 — 만기는 expiry_date 와 as_of 비교로
  --    파생되고, 중복 저장하면 값이 어긋난다(.claude/rules/data.md 의 difficulty 규칙과 같은 정신)
);

CREATE TABLE policy_objects (                -- 목적물 명세. 증권 1 : 목적물 N (§5.1)
  policy_id         BIGINT NOT NULL,
  business_site_id  BIGINT NOT NULL,
  object_type       VARCHAR(16) NOT NULL,    -- 'building' | 'equipment' | 'stock'
  coverage_amount   BIGINT NOT NULL,         -- 보험가입금액
  insured_value     BIGINT,                  -- 보험가액        ★ 비례보상(§5.2)
  coinsurance_ratio DECIMAL(4,3),            -- 부보비율(0.800) ★ 비례보상(§5.2)
  deductible        BIGINT,                  -- 자기부담금      ★ S15
  PRIMARY KEY (policy_id, business_site_id, object_type)
);

-- ── A2A 신원 계층 (신규 2종) ──

-- ⛔ 이 테이블은 **인증 정보가 아니다.** 여기 행이 있다는 사실은 "우리가 아는 외부 키"일 뿐,
--    요청을 승인할 근거가 되지 않는다. 인가는 partner_grants 가 한다 — A2A_Q 결정 1.
CREATE TABLE partner_subject_refs (
  partner       VARCHAR(16) NOT NULL,        -- 'maintq' | 'finallq'
  subject_type  VARCHAR(16) NOT NULL,        -- 'building' | 'company'
  external_key  VARCHAR(64) NOT NULL,        -- 'BLD-A' | finallq_company_id
  local_table   VARCHAR(32) NOT NULL,        -- 'business_sites' | 'customers'
  local_id      BIGINT      NOT NULL,
  mapped_at     DATE        NOT NULL,
  PRIMARY KEY (partner, subject_type, external_key),
  UNIQUE (partner, subject_type, local_id)   -- 역방향도 1:1 (한 사업장에 BLD-A·BLD-B 동시 매핑 금지)
);

-- 인가(위임) 테이블. A2A_Q 결정 1의 "서버가 보유한 위임 테이블"이 이것이다(§4).
CREATE TABLE partner_grants (
  partner_id     VARCHAR(64) NOT NULL,       -- actor. 액세스 토큰의 sub/client_id 와 대조하는 값
  subject_scope  VARCHAR(64) NOT NULL,       -- 이 actor 가 다룰 수 있는 finallq_company_id
  allowed_skills VARCHAR(255) NOT NULL,      -- 목업이라 CSV. 스킬 단위 제한(§7.3)
  valid_until    DATE NOT NULL,              -- A2A_Q 온보딩 모델: 한도·허용작업·유효기간 함께 발급
  revoked_at     DATE,                       -- 폐기. NULL=유효
  issued_by      VARCHAR(32) NOT NULL,       -- 'finallq_admin' — 발급 주체를 기록에 남긴다
  PRIMARY KEY (partner_id, subject_scope)
);
```

### 5.4 "인증용 아님"을 주석이 아니라 구조로 만드는 방법

세 겹으로 잠근다.

1. **테이블 분리** — subject 해석(`partner_subject_refs`)과 인가(`partner_grants`)가 다른 테이블이라,
   한쪽만 조회하면 아무것도 판정되지 않는다. 매핑 행의 존재는 "안다"이지 "허용한다"가 아니다.
2. **단일 진입점** — 스킬 핸들러는 두 테이블을 직접 읽지 않고 `resolveAuthorizedSubject(actorPartnerId,
   requester)` **하나만** 호출한다. 이 함수의 시그니처가 **actor를 필수 인자로 받는다** — payload만으로는
   호출 자체가 불가능하다. (아래 조회 경로)
3. **가드 테스트** — `partner_subject_refs` 리포지토리가 그 함수 밖에서 호출되면 실패하는 아키텍처
   테스트를 둔다. ai-engine 쪽 레이어 방향을 가드 테스트로 좁혀 둔 것(`.claude/rules/python.md`
   예외 1)과 같은 태도다.

```
조회 경로 (이 순서를 건너뛸 수 없다)
  ① 토큰 검증 → actor_partner_id 확보              (없으면 401, 대장 조회조차 안 한다)
  ② partner_grants: actor 가 유효한가              (revoked/만료면 403)
  ③ partner_subject_refs: external_key → local_id  (없으면 "확인 불가" — 존재 여부도 흘리지 않는다)
  ④ ②의 subject_scope 안에 ③의 소유 회사가 있는가  (아니면 403)
  ⑤ 그제서야 policies / policy_objects 조회
```

> ③에서 **"그런 건물 없음"과 "권한 없음"을 같은 응답으로 회신한다.** 다르게 회신하면 외부에서
> `BLD-*`를 훑어 우리 계약 대장의 존재 여부를 탐지할 수 있다(FinAllQ §1.4의 열거 공격 지적과 같은 문제).
> 마침 InsuQ 절대 원칙 1의 `"약관에서 확인 불가"` 거부 형식이 이 요구와 그대로 맞는다.

### 5.5 검토했으나 권하지 않는 대안

| 대안 | 왜 안 되나 |
|---|---|
| `business_sites.building_id`에 MaintQ 키를 직접 저장(TASK-E01 초안 문면 그대로) | §2 — 소유자 미명시. 파트너가 늘면(FinAllQ company) 컬럼이 계속 늘고, 남의 키 체계 변경이 우리 테이블을 흔든다 |
| 요청받은 6필드를 한 테이블(flat)로 | §3·§5.1 — in/out 방향과 증권/목적물 결이 한 칸에 섞인다 |
| `partner_subject_refs`에 MaintQ처럼 `link_state`를 같이 둔다 | 응답자에겐 **승인 상태의 원본이 발급된 자격증명(grant)**이다. 매핑 테이블에도 상태를 두면 두 곳이 어긋나고, "매핑 있음 = 승인됨"으로 다시 읽히기 시작한다(§2가 막으려던 것) |
| 인가를 코드 상수(`config`)로 | 파트너 폐기·유효기간을 표현 못 한다. A2A_Q 온보딩 모델이 *한도·허용작업·유효기간 함께 발급*을 요구한다 |

---

## 6. 제안 ② — 시드: "이미 화재보험에 가입돼 있다"를 어떻게 심을까

**질문 2의 답: MaintQ 시드 실측값에 맞춰 심되, 공유 상수의 SSOT를 A2A_Q에 두고 양쪽이 인용한다.**

### 6.1 맞춰야 하는 값 (MaintQ `data/seed.py` 실측)

| 값 | 원본 | MaintQ 실측 | InsuQ가 심을 것 |
|---|---|---|---|
| `BLD-A`~`BLD-D` | MaintQ | 자산 9건에 분포 (A:1, B:2, C:3, D:3) | `partner_subject_refs` 4행 → `business_sites` 4행 |
| `POL-2026-FIRE-01` | **InsuQ** | `assets.policy_id` 8행에 복제 | `policies.policy_no` **1행** + `policy_objects` 4행 |
| `AST-L3-LIFT` (`insured=0`) | MaintQ | 유일한 확인된 미부보 | InsuQ 쪽엔 대응 행 없음 — 자산 결은 우리 관심 밖(§6.4) |
| `finallq_company_id` | FinAllQ | 없음(null) | **심지 않는다** — A2A_Q §결정 2가 "논리적으로만 존재, 물리적으로 null". 가짜 값을 심으면 그게 사실처럼 굳는다 |

### 6.2 공유 상수의 SSOT — 두 레포가 같은 문자열을 하드코딩하는 문제

`BLD-A`·`POL-2026-FIRE-01`이 InsuQ와 MaintQ 양쪽 시드에 각각 박히면, 한쪽만 바꿔도 아무도 모른다.
데모 당일에 조용히 "확인 불가"가 나오는 종류의 사고다.

**제안**: `A2A_Q/docs/fixtures/demo_identifiers.md`(신규)에 표 하나를 두고 **양쪽 시드가 그 문서를
주석으로 인용**한다. QMesh는 프로토콜 중계자이지 데이터 소유자가 아니지만, **데모 픽스처는 두
레포의 교집합**이라 어느 한쪽에 두면 그쪽이 상대 데이터의 주인처럼 보인다.

값싼 보강 2가지:
- InsuQ 시드 자가검증 테스트 1건 — `POL-2026-FIRE-01`이 정확히 1행, `BLD-A~D` 매핑이 4행.
- 시드 주석에 출처 표기: `# 출처: A2A_Q/docs/fixtures/demo_identifiers.md (MaintQ assets 실측)`

### 6.3 대조군 — 성공 케이스만 심으면 데모가 거짓말을 한다

MaintQ가 `AST-L3-LIFT`(`insured=0`) 한 건으로 `CLEAR` 경로를 확보한 것과 같은 이유로, InsuQ도
**실패 경로가 실제로 데이터에서 나와야 한다.** 실패 모드가 서로 다른 3종을 심는다.

| # | 대조군 | 시드 | 나와야 하는 응답 |
|---|---|---|---|
| 1 | **subject 미해석** ✅확정 | `BLD-E`(양쪽 어디에도 없는 키)를 요청에 사용 — **2026-08-13 확정**, MaintQ `BLD-D`는 그대로 둔다 | "확인 불가" — 존재 여부도 흘리지 않음(§5.4) |
| 2 | **grant 폐기** | `partner_grants`에 `revoked_at` 채운 행 1건(`maintq-agent-legacy`) | 403. **매핑은 멀쩡한데 거부된다** = "식별자만으론 승인 안 된다"가 눈에 보이는 유일한 지점 |
| 3 | **증권 만료** | `POL-2025-FIRE-01`, `expiry_date = 2026-03-31`(as_of 2026-08-13 기준 만료) | "유효한 담보 아님". 동시에 S7(갱신 상담)의 자연스러운 소재 |

그리고 **정상 응답 쪽에도 계산이 일어나야** 한다 — 백로그 TASK-H02가 예로 든 *"보장 3억 vs 대출
5억"* 을 그대로 시드에 맞춘다:

```
BLD-A 사업장 목적물(building):
  coverage_amount   = 300,000,000   -- 3억
  insured_value     = 500,000,000   -- 5억
  coinsurance_ratio = 0.800         -- 부보비율 미달(3억 < 5억×0.8=4억) → S13 비례보상 대상
```

이 한 줄로 S8(부족분 2억)과 S13(비례보상)이 **같은 데이터에서** 서로 다른 계산을 하게 된다.

### 6.4 시드 설계 시 지킬 것

- **`as_of` 기준일을 고정한다** — 상대 날짜(`오늘+180일`)로 심으면 몇 달 뒤 데모가 조용히 바뀐다.
  기준 2026-08-13, 유효 증권 `expiry_date = 2027-03-31`, 만료 대조군 `2026-03-31`.
- **자산(`asset_id`) 결은 InsuQ가 갖지 않는다.** S11·S14·S15가 `asset_id`를 실어 보내지만, InsuQ는
  이를 **subject로 해석하지 않고 통지 내용(payload)으로만 보관**한다. `subject_type`은
  `building`·`company` 2종으로 고정 — 인가 검사 표면을 자산 개수만큼 늘리지 않는다.
- **가상 데이터 경고**를 `data/README.md` 관례대로 붙인다. `insurer`·`product_code`는 트랙4에서
  실제 파싱한 상품과 1:1이어야 하지만(TASK-E01 요구), **계약·고객·사업장은 전부 가상**이다.
- 시드 위치: 계약 대장은 RDB(backend 소유)이므로 **Spring 시드**다(`data/`가 아니다 —
  `05_ARCHITECTURE.md` 데이터 소유권 경계).

---

## 7. 제안 ③ — 인증 주체를 InsuQ가 가질까, FinAllQ를 신뢰할까

**질문 3.** 먼저 용어를 갈라야 답이 나온다.

- **인증(authentication)** = "이 호출자가 진짜 그 파트너인가" → 토큰 검증
- **인가(authorization)** = "이 파트너가 이 계약을 볼 수 있는가" → 위임 테이블

**이 둘의 주체는 달라도 된다.** 아래 옵션이 갈리는 지점이 정확히 여기다.

### 7.1 옵션 A — InsuQ가 자체 파트너 등록·발급 (자체 IdP)

InsuQ가 파트너를 직접 등록받고 client credentials를 발급, 자기 토큰만 신뢰한다.

| | |
|---|---|
| ✅ | **응답자로서 완결적이다.** 다른 프로젝트의 가용성·정책 변경에 우리 인증이 인질로 잡히지 않는다 |
| ✅ | 폐기가 즉각적 — 우리가 발급했으니 우리가 끊는다 |
| ✅ | InsuQ 단독으로 A2A 데모가 성립한다(QMesh·FinAllQ 미착수 상태에서도) |
| 🔴 | **신뢰 앵커가 둘이 된다.** A2A_Q가 확정한 KYB·초대·연결 승인은 FinAllQ ADMIN 소관인데, InsuQ가 따로 등록을 받으면 **"FinAllQ는 거절했는데 InsuQ는 허용한 파트너"**가 존재할 수 있다 |
| 🔴 | 기업 실재 확인(KYB)을 InsuQ가 할 수단이 없다. 사실상 "요청하면 발급"이 되어 등록 절차가 형식이 된다 |
| ⚠️ | 파트너가 늘면 회사마다 InsuQ에 따로 등록해야 한다 — A2A_Q가 초대 모델로 없앤 선형 심사 부담이 되살아난다 |

### 7.2 옵션 B — FinAllQ 발급 자격증명을 InsuQ가 그대로 신뢰 (연합)

FinAllQ를 IdP로 두고, InsuQ는 그 토큰을 검증만 한다(JWKS로 공개키 획득).

| | |
|---|---|
| ✅ | **신뢰 앵커가 하나다.** A2A_Q 온보딩 모델(사람이 연결 자체를 승인 → 그때 자격증명 발급)이 그대로 InsuQ에도 적용된다 |
| ✅ | 파트너가 늘어도 InsuQ가 할 일이 없다 |
| ✅ | 폐기가 한 곳 — FinAllQ가 끊으면 전 도메인에서 끊긴다 |
| 🔴 | **인가까지 위임하면 위험하다.** FinAllQ 토큰에 "이 파트너는 InsuQ 계약을 볼 수 있다"는 판단이 실려 오면, **우리 계약 대장의 접근 권한을 남이 정한다.** 계약 정보의 보유자는 InsuQ다 |
| 🔴 | **`aud` 검증이 없으면 confused deputy.** FinAllQ용으로 발급된 토큰을 InsuQ에 재사용할 수 있다 |
| ⚠️ | **FinAllQ의 현재 서명은 HS256 대칭키다**(FinAllQ §3.1 실측). 대칭키로는 검증자에게 발행 능력을 함께 주게 되므로, InsuQ가 검증하려면 **비대칭(RS256/ES256) 전환이 선행**돼야 한다 |
| ⚠️ | FinAllQ 미착수(백로그 126~130, Sprint 10 후보)라 InsuQ가 그 일정에 묶인다 |

### 7.3 옵션 C (권고) — 인증은 위임, 인가는 자체 보유

```
FinAllQ ADMIN  ─ 발급 ─▶ 파트너 자격증명(client credentials)
                             │
MaintQ 에이전트 ─ 토큰 취득 ─┘
        │
        ▼  Authorization: Bearer <FinAllQ 서명 토큰>   ← ① InsuQ 가 서명·aud·만료 검증 (인증 = 위임)
      InsuQ
        └─ partner_grants 조회                          ← ② 이 actor 가 이 subject 를 볼 수 있는가 (인가 = 자체)
```

**근거:**
1. **신뢰 앵커는 하나여야 하고(옵션 B), 자원 접근 판단은 자원 보유자가 해야 한다(옵션 A).** 두
   요구가 충돌하지 않는 이유는 **층이 다르기 때문**이다. A2A_Q 결정 1이 이미 이 구조를 적어 뒀다 —
   *"서버가 보유한 위임 테이블"* 이 바로 ②이고, 서버는 InsuQ다(§4).
2. **스킬 단위 제한이 여기서 자연히 나온다.** `partner_grants.allowed_skills`가 호출 성격을 가른다:

   | actor | 허용 스킬 | 근거 |
   |---|---|---|
   | MaintQ 에이전트 | `advise-policy-renewal`·`notify-asset-change`·`notify-risk-change`·`claim-insurance` | S7·S11·S14·S15 — 자기 자산·자기 계약 |
   | FinAllQ 에이전트 | `verify-collateral-insurance` **만** | S8·S13 — 담보 조회 목적에 한정 |

   FinAllQ 토큰이 `claim-insurance`(보험금 청구)를 부를 수 있어야 할 이유가 없다. 이 제한은
   **InsuQ만 알 수 있는 사실**이라 인가를 위임하면 표현할 자리가 사라진다.
3. **비용이 가장 싸다.** ①은 표준 JWT 검증이고, ②는 §5.3의 테이블 하나다. 옵션 A의 등록 콘솔·
   KYB가 불필요하다.

**필수 조건 3가지** (없으면 옵션 C가 성립하지 않는다):
- **비대칭 서명 + JWKS.** FinAllQ §4가 *"외부에 나갈 토큰은 비대칭"* 을 지금 못박아 두라고 한 것과 같은 요구.
- **`aud` 클레임 검증.** `aud = insuq`가 아니면 거부 — 이게 없으면 FinAllQ용 토큰이 InsuQ에 통한다.
- **사용자 JWT와 키·필터를 완전히 분리.** InsuQ의 `JwtService`는 HS256 대칭키에 access·refresh가
  **같은 키**다(실측). 여기에 외부 토큰을 얹으면 사용자 로그인과 서비스 인증의 권한 경계가 무너진다.
  트랙7 TASK-H05가 이미 *"사용자 JWT와 서비스 토큰 미들웨어를 분리"* 로 명시해 뒀다.

### 7.4 2차 홉(S8·S13)은 성격이 다른가 — "FinAllQ가 이미 인증한 요청을 다시 검증할 필요가 있나"

**질문 3의 후속.** 답: **인증은 중복이 아니고, 인가는 생략할 수 없다.**

먼저 2차 홉이 어떤 모양으로 오느냐가 갈린다.

| 형태 | 설명 | 평가 |
|---|---|---|
| (a) 토큰 전달 | FinAllQ가 **MaintQ의 토큰을 그대로** InsuQ에 넘긴다 | **비권장.** `aud`가 FinAllQ용이라 §7.3 검증과 충돌하고, FinAllQ가 남의 자격증명을 보관하게 되며, 폐기 시 누구를 끊어야 하는지가 흐려진다 |
| (b) **자기 토큰 + 원 요청자 표기** | FinAllQ가 **자기 자격증명**으로 호출하고, 원 요청자는 `request_chain_id`(+ 필요 시 `on_behalf_of`)로 payload에 싣는다 | **권장.** actor는 항상 **직접 호출자**로 고정된다 |

(b)를 택하면 "다시 검증하나"라는 질문 자체가 해소된다:

- InsuQ가 검증하는 actor는 **FinAllQ**이지 MaintQ가 아니다. **다른 대상을 검증하므로 중복이 아니다.**
- FinAllQ가 MaintQ를 인증한 사실은 InsuQ에 **주장으로만** 도착한다(payload의 `on_behalf_of`).
  주장을 신뢰의 근거로 쓰면 §2가 막으려던 것("식별자만으로 승인")이 한 단계 위에서 재발한다.
- **인가는 오히려 2차 홉에서 더 필요하다.** MaintQ 직접 호출(S7·S11·S14·S15)은 "자기 건"이라
  actor=subject지만, S8·S13은 **actor(FinAllQ) ≠ subject(MaintQ 회사)** 다. A2A_Q 미결 1번이
  *"지금까지 나온 시나리오 전부 actor=subject"* 라고 잠정 가정했는데, **S8·S13은 그 가정의
  예외다.** 이 문서가 그 점을 회신 사항으로 올린다(§9-1).

**그래서 실제로 달라지는 것**: 인증 강도가 아니라 **권한 범위**다(§7.3-2 표). 2차 홉은 조회 전용
스킬 하나만 허용되고, 통지·청구는 MaintQ 직접 호출로만 들어온다.

### 7.5 M1 단계 권고 — 지금 무엇을 하고 무엇을 미룰까

FinAllQ §4("지금 막을까 나중에 막을까")와 같은 판단 재료로 정리한다.

| 항목 | 지금 | 이유 |
|---|---|---|
| `partner_grants`·`partner_subject_refs` **스키마** | ✅ **지금** | 계약 대장(TASK-E01)을 처음 만드는 시점이다. 나중에 끼워 넣으면 이미 쓰이는 조회 경로를 전부 고쳐야 한다 |
| 조회 경로 §5.4(단일 진입점·가드 테스트) | ✅ **지금** | 핸들러가 늘어난 뒤에 강제하면 이미 새는 경로가 생긴다 |
| **토큰 검증 실물** | ⏸ **미룬다** | TASK-H05가 이미 *"실습 단계에선 목업 토큰 허용"* 으로 컷해 뒀다. 검증부는 나중에 갈아끼워도 스키마가 안 바뀐다 |
| FinAllQ 비대칭 전환 대기 | ⏸ **미룬다** | FinAllQ 백로그 126~130 미착수. **단 "외부 토큰은 비대칭" 한 줄은 지금 문서에 못박는다**(§7.3) |
| InsuQ 자체 파트너 등록 콘솔 | ❌ **안 만든다** | 옵션 A의 🔴 — 신뢰 앵커 이중화. A2A_Q가 연결 승인 UX를 명시적으로 범위 밖에 뒀다 |

> **목업 토큰 단계에서도 §5.4의 5단계 조회 경로는 그대로 탄다.** ①이 "고정 문자열 비교"로
> 바뀔 뿐이다. 이러면 나중에 실물 검증으로 교체할 때 **한 함수만** 바뀐다.

### 7.6 fail-soft 전제 — 느슨해지는 것과 **오히려 조여지는 것** (2026-08-13 신규 정책)

**FinAllQ 결정**: S15 후속 체인(FinAllQ `advise-replacement-financing`)의 **체인 연속성 검증**에서
InsuQ 조회가 실패하면 **즉시 거절이 아니라 재시도+백오프 후 거절**(fail-soft).

#### 느슨해지는 것 — 응답 시간 예산

InsuQ의 일시적 지연·실패가 남의 체인을 즉사시키지 않는다. **SLA를 타이트하게 잡지 않아도 된다.**

단 "느려도 된다"는 뜻은 아니다 — 재시도 **총** 예산 안에는 들어야 하고, 스킬마다 성격이 다르다:

| 스킬 | RAG 파이프라인 | 현실적 예산 |
|---|---|---|
| `verify-collateral-insurance` · `notify-*` · Task 상태 조회 | **안 탄다** (대장 조회·산식) | 수백 ms — 여기가 느리면 fail-soft로 가릴 게 아니라 버그다 |
| `advise-policy-renewal` · `claim-insurance` | **탄다** (검색→리랭크→생성) | `.claude/rules/rag.md` 「레이턴시 예산」 30초 |

→ **fail-soft 완화가 실제로 값을 갖는 건 후자**다. 상담·판정형 스킬이 30초를 쓰는 동안 FinAllQ가
기다려 준다는 뜻이므로, 이 두 스킬을 위해 파이프라인을 성급히 잘라낼 이유가 없어졌다.

#### 오히려 조여지는 것 3가지 — 재시도는 공짜가 아니다

1. **멱등성.** 재시도 전제는 조회 계열엔 무해하지만 **통지·청구(S11·S14·S15)에 붙으면 중복
   접수**가 된다. 지금 결정된 fail-soft 대상은 "체인 연속성 검증"(순수 조회)이라 **당장은
   안전**하다 — 위험은 FinAllQ·MaintQ가 같은 재시도 정책을 통지·청구로 확대하는 시점에 열린다.
   값싼 선제 방어 2가지:
   - `(request_chain_id, skill)` 유니크 제약 — 같은 체인의 같은 스킬은 한 번만 접수된다.
   - **재시도 안전 여부를 스킬 단위 속성으로 Agent Card(TASK-H01)에 선언한다.** 상대가 이 문서를
     안 읽어도 **계약에서 보인다** — 트랙7 서문의 *"외부 프로젝트 입장에서 InsuQ는 블랙박스,
     계약만 지키면 된다"* 는 관점과 같다.
2. **실패도 로깅해야 한다.** fail-soft에서는 **FinAllQ의 거절 사유가 "InsuQ 무응답"이 된다.**
   우리 로그에 성공만 남으면 "왜 저쪽이 거절했는지"를 우리 쪽에서 추적할 방법이 없다 →
   TASK-H06에 실패·타임아웃 로깅과 재시도 N건 묶어보기를 추가했다.
3. **Task 상태 조회에도 인가가 필요하다.** 체인 연속성 검증은 스킬 호출이 아니라 **TASK-H03의
   상태 조회 엔드포인트 폴링**인데, **폴링 주체가 원 요청자가 아니다** — Task를 만든 건
   MaintQ(`claim-insurance`), 읽는 건 FinAllQ다. §7.3의 `allowed_skills`(스킬 단위 허용)로는
   "남이 만든 Task를 읽을 수 있는가"가 표현되지 않는다. **미해결 §9-9.**

> **라벨 정정**: 이번 전달에서 S15가 `advise-replacement-financing`으로 표기됐는데, 최초 시나리오
> 정의상 **S15 = `claim-insurance`**(설비 화재 멸실 → 보험금 청구)이고
> `advise-replacement-financing`은 그 회신 뒤 MaintQ가 FinAllQ에 잇는 **후속 스킬(InsuQ 소관 밖)**
> 이다. 이 문서는 혼동을 피해 **"S15 후속 체인"**으로 적는다 — A2A_Q 표기 확인 필요(§9-10).

---

## 8. 제안 ④ — A2A 수신부는 어느 서비스에 두는가 ✅ **확정 (2026-08-13)**

인증·인가·계약 대장이 전부 한 곳에 있어야 하므로 이 문서가 건드릴 수밖에 없는 항목이다.

**실측**: `/run` 엔드포인트는 **어느 서비스에도 없다**(backend·ai-engine 둘 다 `/health`만 있다).
`07_BACKLOG.md` TASK-602/TASK-H01은 *"`/health`,`/run` 엔드포인트 추가"* 라고만 하고 **어느
서비스인지 정하지 않았다.**

**확정: A2A 수신부는 Spring(backend)** 이다 (2026-08-13 사용자 결정 — `07_BACKLOG.md` 트랙7
서문·TASK-H01·TASK-602에 반영). 근거는 아래 그대로다.

- 계약 대장(RDB)의 소유자가 Spring이다. ai-engine에 두면 `05_ARCHITECTURE.md` 「데이터 소유권
  경계(확정 — 재논의 금지)」의 *"ai-engine에는 RDB 커넥션을 만들지 않는다"* 를 깬다.
- 인증·인가는 이미 Spring의 책임이다(*"ai-engine은 누가 물었는지·권한을 모른다"*).
- 근거 조항이 필요한 스킬(`advise-policy-renewal`·`notify-risk-change`·`claim-insurance`)은
  **Spring이 ai-engine을 호출해 근거를 받아 조립**한다. 기존 `/qa` 흐름과 같은 방향이라 새 경계가 안 생긴다.
- 부수 효과: **MCP 서버는 A2A 자격증명을 보지 않는다.** MaintQ 문서 §7.3이 같은 이유로 MCP 도구를
  자격증명에서 격리한 것과 같은 결론이고, `05_ARCHITECTURE.md`가 *"MCP 서버는 아무나 부른다"* 는
  이유로 ai-engine을 신원에 무지하게 유지한 것과도 맞는다.

---

## 9. 미해결 — 결정·협의가 필요한 것

1. **A2A_Q 미결 1번("actor=subject 고정")의 예외를 인정할 것인가.** §7.4 — S8·S13은
   actor(FinAllQ) ≠ subject(MaintQ 회사)다. **A2A_Q 쪽 회신 필요.**
2. **조회 동의(consent)를 어떻게 표현할까.** 대출 심사에서 은행이 차주의 보험 계약을 조회하는 것은
   실무상 계약자 동의가 전제다. `partner_grants`를 회사 단위 상시 허용으로 두면 **동의가 스키마에서
   사라진다.** 후보: 요청 payload에 `consent_ref` 필수화 / grant에 목적(purpose) 제한.
   **미해결 — 목업 범위를 넘지만 기록해 둔다.**
3. ~~**`MaintQ` §5의 `BLD-D = NOT_LINKED` 제안과 InsuQ 시드가 어긋난다.**~~ ✅ **해소
   (2026-08-13)** — InsuQ가 §6.3대로 미매핑 대조군을 `BLD-E`(양쪽에 없는 키)로 따로 확보하고,
   **MaintQ 쪽 `BLD-D`는 바꾸지 않는다.** MaintQ에 전달 완료.
4. **외부 actor를 감사 기록에 어떻게 남길까.** §4.1 — `ConsultationSession.userId`가 nullable이라
   NOT NULL 충돌은 없지만, **"익명 사용자"와 "머신 주체"가 구분되지 않는다.** FinAllQ §2.6의
   `principal_type` 해법이 InsuQ에도 필요. TASK-H06(`request_chain_id` 로깅)과 함께 결정.
5. ~~**`docs/A2A_CONTRACTS.md`와 `07_BACKLOG.md`의 스킬 개수가 다르다.**~~ ✅ **해소
   (2026-08-13)** — `A2A_CONTRACTS.md`의 **5개가 맞고**, 백로그를 A2A_Q 시나리오 기준으로 채우는
   쪽으로 확정. `07_BACKLOG.md` 트랙7 서문(SSOT 선언)·TASK-H01(Agent Card 스킬 배열·테스트)·
   TASK-H02(핸들러 4종→**5종**, ⑤ `advise-policy-renewal` 명세 신설)에 반영 완료.
   판단 근거: *"백로그가 SSOT"* 는 **스킬 정의의 권위가 백로그에 있다**는 뜻이지 **누락을
   정당화한다**는 뜻이 아니다.
6. **`A2A_CONTRACTS.md` §선행 조건의 6필드 초안이 이 문서 §5와 어긋난다.** 이 문서의 §5가 채택되면
   그 두 줄을 갱신해야 한다.
7. **TASK-E01 초안 문면 수정 필요.** `business_sites(… building_id 포함)` → §5.3대로면 `building_id`는
   `business_sites`에서 빠지고 `partner_subject_refs`로 간다. **트랙5 착수 전에 정리해야** 시드를
   두 번 안 만든다.
8. ~~**A2A 수신부 서비스 미확정.**~~ ✅ **확정 (2026-08-13)** — **backend(Spring)**. §8 참고,
   `07_BACKLOG.md` 트랙7 서문·TASK-H01·TASK-602에 반영 완료.
9. **Task 상태 조회의 인가를 무엇으로 표현할까 (신규, fail-soft에서 파생).** §7.6-3 — 체인 연속성
   검증은 **Task를 만들지 않은 파트너(FinAllQ)가 남의 Task(MaintQ의 `claim-insurance`)를 읽는**
   최초 사례다. `partner_grants.allowed_skills`는 "어떤 스킬을 부를 수 있나"만 표현하므로 이걸
   담지 못한다. 후보:
   - (a) `allowed_skills`에 `task-read` 같은 유사 스킬을 추가 — 단순하지만 스킬 아닌 것을 스킬 칸에 넣는다
   - (b) **같은 `request_chain_id` 안에 있으면 읽기 허용** — 체인 참여자만 그 체인을 본다.
     의미가 맞지만 `request_chain_id`를 아는 것이 곧 권한이 되므로 **추측 불가능한 값**이어야 한다
     (순번·짧은 문자열 금지 → UUIDv4 이상). §2가 막으려던 "식별자=권한"이 여기서 재발할 수 있다
   - (c) grant에 `readable_chains` 류의 별도 축 신설 — 가장 정확하지만 목업엔 과함

   **잠정 권고 (b) + 값 추측 불가 요구.** TASK-H03·H06과 함께 결정.
10. **S15 라벨 표기 확인.** §7.6 말미 — `advise-replacement-financing`이 S15 자체인지 S15의
    **후속 스킬**인지가 전달마다 다르게 쓰였다. InsuQ 소관은 `claim-insurance`까지이므로 실무
    영향은 없으나, 시나리오 번호는 세 레포가 공유하는 좌표라 **A2A_Q 표기를 한쪽으로 맞춰야 한다.**

## 관련 문서

- `A2A_Q/docs/A2A_IDENTITY.md` — QMesh 확정본 (결정 1·2, 온보딩 모델의 인용처)
- `FinAllQ/docs/A2A_IDENTITY.md` — 최초 조사 원본 (§2.5 온보딩 · §3.2 옵션 비교 · §5 미해결)
- `MaintQ/docs/A2A_IDENTITY.md` — MaintQ 회신 (`partner_links` 제안 · D78 패턴 · 시드 A/B안)
- `docs/A2A_CONTRACTS.md` — 이 레포가 노출할 스킬 목록 (⚠️ §9-5·§9-6, 갱신 필요)
- `docs/07_BACKLOG.md` — 트랙5 TASK-E01(계약 대장) · 트랙7 TASK-H01~H06
- `docs/05_ARCHITECTURE.md` 「데이터 소유권 경계」 — §8 수신부 위치 판단의 근거
- `.claude/rules/data.md` — 파생 가능한 값을 중복 저장하지 않는 원칙(§5.3 `cancelled_at` 판단)
