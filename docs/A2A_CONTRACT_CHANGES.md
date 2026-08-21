# A2A 계약 변경 제안 — 이력과 합의 상태

> 이 문서는 **공유 계약(`docs/schemas/`·`docs/agent_cards/`) 변경 제안의 대장**이다.
> `A2A_IDENTITY.md`와 같은 방식으로 운영한다 — **각 프로젝트가 자기 레포에서 실측 조사를
> 하고, 그 결론을 여기서 검토·채택**한다(선례: FinAllQ의 `docs/A2A_IDENTITY.md` 조사를
> A2A_Q가 그대로 채택).
>
> **읽는 법**: `status`가 `제안`인 항목은 **아직 합의되지 않았다.** 스키마 파일에는 이미
> 반영돼 있지만 `description`에 `PROPOSED(...)` 표시가 붙어 있다. 합의되면 그 표시를 떼고
> 여기 `status`를 `채택`으로 바꾼다.

---

## CP-001 — InsuQ 스킬 5종: 거부 표현·근거 인용 (채택)

| | |
|---|---|
| **status** | 🟢 **채택** (2026-08-21) — 스키마 5종의 PROPOSED 마커 제거 완료. MaintQ·FinAllQ 쪽 구현 확인은 각 레포 자체 진행 |
| **제안자** | InsuQ |
| **제안일** | 2026-08-19 |
| **원본 조사** | `InsuQ/docs/A2A_API_SPEC.md` §0 |
| **영향 스킬** | `advise-policy-renewal` · `verify-collateral-insurance` · `notify-asset-change` · `notify-risk-change` · `claim-insurance` |
| **코드 영향** | **없음** — 세 레포 전수 확인 결과 이 스킬들을 **참조하는 코드가 0건**이다(문서 언급만). 지금이 계약을 고칠 수 있는 마지막으로 싼 시점이다 |

### 어떻게 발견했나

InsuQ가 A2A HTTP 명세(엔드포인트·봉투·에러 규약)를 쓰면서 기존 스키마 5종을 전수 대조하다
드러났다. **기능을 구현하다 만난 게 아니라, 명세를 글로 쓰다 만났다** — 구현 전에 나온 게 다행이다.

---

### 변경 ① `status`에 `rejected` 추가 + `rejection_reason` 신설 🔴

**문제.** 스킬 5종 중 4종의 `status`가 `enum: ["completed"]` **단일값**이었다
(`claim-insurance`만 `["input-required","completed"]`).

InsuQ의 절대 원칙은 **"근거를 못 찾으면 「약관에서 확인 불가」로 거부한다"**이다
(`InsuQ/CLAUDE.md`). 보험은 오답 비용이 커서 **틀리게 답하느니 모른다고 답한다**는 게 제품의
핵심 약속이고, 별도 지표(거부 정확도)로 측정까지 한다.

그런데 계약에 **거부를 담을 자리가 없었다.** 이대로 구현하면 둘 중 하나가 된다:

| 선택 | 결과 |
|---|---|
| 없는 근거를 만들어 `completed` 반환 | **절대 원칙 위반.** A2A 경계에서 제품 약속이 무너진다 |
| HTTP 4xx/5xx로 반환 | 호출자가 **InsuQ 장애로 오인**한다. 재시도 로직이 돌고, 그 재시도가 LLM 비용이 된다 |

**변경.**
```jsonc
"status": { "type": "string", "enum": ["completed", "rejected"] },
"rejection_reason": {
  "type": "string",
  "enum": ["no_evidence_found", "citation_unverified", "out_of_corpus", "policy_not_found"]
}
```

⚠️ **`rejected`는 HTTP 200이다.** 거부는 **정상 동작이지 장애가 아니다.**

| `rejection_reason` | 언제 |
|---|---|
| `no_evidence_found` | 검색 결과에 근거 조항이 없다 |
| `citation_unverified` | 생성은 됐으나 인용 검증을 통과한 조항이 0건이다 |
| `out_of_corpus` | 해당 상품·약관이 코퍼스에 없다 |
| `policy_not_found` | `policy_id`/`building_id`에 해당하는 계약이 없다 |

**호출자에게 필요한 조치** — `status`로 분기할 때 `rejected`를 **재시도 대상에서 제외**해야
한다. 재시도해도 결과가 같고(코퍼스에 없는 근거는 다시 물어도 없다) 비용만 든다.

---

### 변경 ② `verify-collateral-insurance`에 `evidence` 신설 🟡

**문제.** `A2A_CONTRACTS.md`는 *"모든 회신에 **약관 조항 인용 필수** — 근거 없는 응답 0건"*
이라고 못박았는데, **이 스킬 response에만 `evidence` 필드 자체가 없었다.** 문서와 스키마가
어긋나 있었다.

하필 이 스킬은 **FinAllQ 대출심사의 2차 홉**이다(S8·S13). `policy_valid: true`와
`coverage_amount`만 받아서 **대출 실행을 판단**하는데, 근거 조항이 없으면 FinAllQ 쪽에서
검증할 방법이 없다. 금액이 움직이는 경로에서 근거가 빠지는 건 다른 스킬보다 위험하다.

**변경.** `evidence`를 properties에 추가하고 **`required`에 편입**했다.

**FinAllQ에게 필요한 조치** — 응답에 `evidence[]`가 추가된다. 무시해도 동작은 하지만,
**대출 심사 기록에 근거를 남기려면 저장 대상에 포함**하는 게 맞다.

---

### 변경 ③ `evidence` 문자열 형식 고정 🟡

**문제.** 타입이 `array of string`뿐이라 형식이 자유로웠다.

InsuQ는 **`policy_part`(보통약관/특별약관명)를 뺀 인용을 금지**한다. 한 약관 안에 `제1조`가
여러 파트에 동시에 존재해서, **조 번호만 대조하면 모델이 다른 파트의 같은 조 번호를 지어내도
환각 탐지를 통과**하기 때문이다(`InsuQ/.claude/rules/rag.md`, 실측 확인된 사고 패턴).

형식이 자유로우면 InsuQ가 내부에서 막아둔 이 보증이 **A2A 경계에서 증발한다.**

**변경.**
```
{상품명} {policy_part} {article_no}[ {clause_no}][, p.{page}]
```
```jsonc
"items": { "type": "string", "pattern": "^.+ .+ 제\\d+조( [①-⑳\\d]+항?)?(, p\\.\\d+)?$" }
```

실제 인용으로 검증했다 — 아래 5종 통과, `policy_part` 없는 형태는 차단:
```
✅ 삼성화재 수퍼비즈니스보험 보통약관 제4조 ①, p.13
✅ 삼성화재 수퍼비즈니스보험 구내폭발위험 특별약관 제1조, p.36
✅ SF실손2607 실손의료비보험 특별약관2(비중증 비급여 실손의료비) 제5조 ④, p.73
✅ 동산종합보험 보통약관 제1조                    (clause_no·page 없는 경우)
❌ 제4조 ①, p.13                                 (policy_part 없음 → 차단)
```

⚠️ `clause_no`·`page`는 값이 없으면 **그 토막을 통째로 생략**한다 — `p.None`이 나가면 인용
신뢰가 무너진다.

---

## 각 프로젝트가 확인할 것

### MaintQ
- [ ] `notify-asset-change`·`notify-risk-change`·`claim-insurance` 응답 처리에서
      **`status == "rejected"`를 재시도하지 않도록** 분기 추가
- [ ] `claim-insurance`가 `rejected`로 오는 경우의 UX 결정 — 보험금 산정 불가를 사용자에게
      어떻게 보일지

### FinAllQ
- [ ] `verify-collateral-insurance` 응답의 **`evidence[]` 수용** — 대출 심사 기록에 남길지 결정
- [ ] `status == "rejected"`(예: `policy_not_found`)일 때 **대출 심사를 어떻게 진행할지** 결정.
      "보험 없음"과 "조회 실패"는 다른 상황이다

### InsuQ
- [x] 스키마 반영 (2026-08-19)
- [x] HTTP 명세 작성 — `InsuQ/docs/A2A_API_SPEC.md`
- [ ] 구현 (TASK-H01·H02, 미착수)

---

## 미결 — 이번 제안에 넣지 않은 것

**유보(deferred) 축의 확장.** `notify-risk-change`만 `verdict: "deferred"` + `needs_review`로
"근거는 있는데 결론을 못 내겠다"를 표현할 수 있다. 나머지 4종에는 그 축이 없다.

InsuQ는 판정을 **가능성 높음 / 낮음 / 판단 유보** 3단계로 고정하는데, A2A에서는 유보가
`completed`로 뭉개진다. **거부(근거 없음)와 유보(근거는 있으나 결론 불가)는 다른 상태**다.

이번엔 넣지 않았다 — 변경 ①만으로도 호출자 분기가 늘어나는데, 유보까지 한꺼번에 얹으면
**합의 비용이 커져 셋 다 미뤄질 위험**이 있다. ①이 합의된 뒤 별도 제안(CP-002)으로 올린다. (①은 2026-08-21 채택 — CP-002 착수 가능)

---

## 문서 구조 점검 기록 (2026-08-21)

스키마 12종 = Agent Card 스킬 id 12종 = README.md 목록 12종 — 전수 대조 완료, drift 없음.
`docs/ref_insuq/`·`docs/ref_maintq/`·`docs/ref_finallq/` 세 인덱스 문서 모두 "원본은
A2A_Q, 복제하지 않는다" 원칙을 일관되게 유지 중. 별도 수정 없음.

> **갱신 (2026-08-21, 같은 날 나중 시점)** — 위 "12종" 카운트는 InsuQ `lookup-clause`
> 스킬(신규 제안, `docs/superpowers/specs/2026-08-21-insuq-lookup-clause-adapter-design.md`)
> 추가로 **13종**이 됐다. 스키마·Agent Card·README 세 목록 모두 함께 갱신돼 여전히
> 서로 일치한다 — 이 점검 기록 자체는 그 시점 스냅샷이라 숫자만 갱신하고 본문은
> 남겨둔다.

---

## CP-002 — request-withdrawal: 수취 계좌 필드 추가 (제안)

| | |
|---|---|
| **status** | 🟡 **제안** — MaintQ 확인 대기 |
| **제안자** | A2A_Q (FinAllQ `request-withdrawal` 어댑터 프로토타입 작업 중 발견) |
| **제안일** | 2026-08-21 |
| **원본 조사** | FinAllQ `backend-core/.../dto/TransferRequestDto.java` 실측 |
| **영향 스킬** | `request-withdrawal` |
| **코드 영향** | FinAllQ·MaintQ 양쪽 다 착수 전이라 없음. **단, A2A_Q 자체 `adapters/finallq_a2a/` 프로토타입은 이미 이 필드에 의존한다** — CP-002가 반려·수정되면 그 어댑터의 `schemas.py`·`main.py`도 함께 바뀌어야 한다 |

### 어떻게 발견했나

FinAllQ `request-withdrawal` 어댑터를 설계하며 실제 이체 API(`POST /api/v1/transfers`)의
요청 DTO를 대조하다 드러났다. 기존 스키마는 `supplier`(거래처명, 자유 텍스트)만 있고
계좌번호가 없어, 이 정보만으로는 실제 이체를 호출할 방법이 없다.

### 변경 — `to_account_number`(필수)·`to_bank_code`(선택) 추가

**문제.** `request-withdrawal.json`의 요청 필드에 수취 계좌 정보가 전혀 없다. FinAllQ의
`TransferRequestDto`는 `toAccountNumber`(필수, 패턴 `^[0-9-]{4,20}$`)와 `toBankCode`(선택)를
요구하는데 대응하는 A2A 필드가 없었다.

**변경.**
```jsonc
"to_account_number": { "type": "string", "pattern": "^[0-9-]{4,20}$" },
"to_bank_code": { "type": "string" }
```
`to_account_number`를 `required`에 추가했다.

**`from_account_id`는 스키마에 넣지 않는다** — "어느 계좌에서 나가는지"는 호출자(actor,
서비스 계정)에 딸린 정보이지 MaintQ가 지정할 subject가 아니다(`A2A_IDENTITY.md` 결정 1의
actor/subject 분리 원칙). FinAllQ 쪽 어댑터가 로그인한 계정의 계좌를 자동으로 조회해 채운다.

**호출자에게 필요한 조치** — MaintQ는 발주서(PO)에 거래처 계좌번호 정보를 갖고 있어야
`request-withdrawal`을 호출할 수 있다.

## 각 프로젝트가 확인할 것 (CP-002)

### MaintQ
- [x] 발주서(PO) 및 `suppliers` 테이블 실측 확인 완료 (2026-08-21, `docs/superpowers/specs/2026-08-21-maintq-a2a-outbound-client-design.md`) — `suppliers` 테이블(`supplier_id`, `name`, `contact`)에 `account_number` 및 `bank_code` 컬럼이 없음이 확인됨. MaintQ 레포에서 `suppliers.account_number` 컬럼 추가(D-번호 신설 마이그레이션) 및 시드 갱신 선행 필요.

### FinAllQ
- [ ] `to_bank_code` 생략 시(같은 은행 내 이체) `TransferService`가 정상 처리하는지 확인

