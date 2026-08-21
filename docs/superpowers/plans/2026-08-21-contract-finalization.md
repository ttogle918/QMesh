# 계약 문서 확정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CP-001을 '채택'으로 전환하고, `A2A_IDENTITY.md`의 미결 사항 5건을 해결됨/보류로
재분류하고, 문서 구조(스키마·Agent Card·인덱스 문서) drift 유무를 점검·기록한다.

**Architecture:** 순수 문서 편집 3작업. 코드·테스트 없음 — "테스트 통과" 대신 grep으로
결과를 검증한다. 세 작업 모두 `A2A_Q` 레포 안에서 끝나며 타 레포(FinAllQ·InsuQ·MaintQ)
파일은 이번 라운드에 변경하지 않는다(변경이 필요해지면 먼저 확인을 구한다).

**Tech Stack:** Markdown, JSON (스키마 파일), git, grep

## Global Constraints

- 스키마 파일의 `description` 값 중 `PROPOSED(InsuQ, 2026-08-19): ` 접두사만 제거한다 —
  뒤에 이어지는 설명 본문 텍스트는 한 글자도 바꾸지 않는다(spec §①).
- MaintQ·FinAllQ 쪽 확인 체크리스트는 이번 작업으로 체크하지 않는다(spec §①).
- `A2A_IDENTITY.md` 미결 사항 재정리는 결론을 새로 만드는 게 아니라 기존 결론의 위치를
  명확히 하는 것 — 본문 내용은 라벨 추가 외에 바꾸지 않는다(spec §②).
- 타 레포(`../FinAllQ`, `../InsuQ`, `../MaintQ`) 파일은 읽기만 하고 쓰지 않는다. 쓰기가
  필요해지면 먼저 사용자에게 확인한다.

---

### Task 1: CP-001 채택 전환

**Files:**
- Modify: `docs/schemas/advise-policy-renewal.json:34,46`
- Modify: `docs/schemas/claim-insurance.json:26,32`
- Modify: `docs/schemas/notify-asset-change.json:27,34`
- Modify: `docs/schemas/notify-risk-change.json:27,38`
- Modify: `docs/schemas/verify-collateral-insurance.json:24,37`
- Modify: `docs/A2A_CONTRACT_CHANGES.md` (CP-001 상태 표)

**Interfaces:** 없음(독립 문서 편집, 다른 태스크가 이 결과를 소비하지 않음).

- [ ] **Step 1: 5개 스키마 파일에서 `status=rejected` 관련 PROPOSED 접두사 제거**

각 파일에서 아래 문자열을 찾아 `PROPOSED(InsuQ, 2026-08-19): ` 부분만 제거한다(본문은
그대로 유지):

```
"description": "PROPOSED(InsuQ, 2026-08-19): status=rejected 일 때 필수. 거부는 장애가 아니므로 HTTP 200 으로 내려간다.",
```
↓
```
"description": "status=rejected 일 때 필수. 거부는 장애가 아니므로 HTTP 200 으로 내려간다.",
```

대상 파일: `advise-policy-renewal.json`(34행), `claim-insurance.json`(26행),
`notify-asset-change.json`(27행), `notify-risk-change.json`(27행),
`verify-collateral-insurance.json`(24행).

- [ ] **Step 2: 같은 5개 파일에서 evidence 인용 형식 관련 PROPOSED 접두사 제거**

각 파일에서 아래 문자열을 찾아 접두사만 제거한다:

```
"description": "PROPOSED(InsuQ, 2026-08-19): 인용 형식 고정. `{상품명} {policy_part} {article_no}[ {clause_no}][, p.{page}]` — policy_part 생략 금지(파트 간 조 번호가 충돌해, 조 번호만 대조하면 다른 파트의 같은 조 번호를 지어내도 환각 탐지를 통과한다).",
```
↓
```
"description": "인용 형식 고정. `{상품명} {policy_part} {article_no}[ {clause_no}][, p.{page}]` — policy_part 생략 금지(파트 간 조 번호가 충돌해, 조 번호만 대조하면 다른 파트의 같은 조 번호를 지어내도 환각 탐지를 통과한다).",
```

대상 파일: `advise-policy-renewal.json`(46행), `claim-insurance.json`(32행),
`notify-asset-change.json`(34행), `notify-risk-change.json`(38행),
`verify-collateral-insurance.json`(37행).

- [ ] **Step 3: PROPOSED 마커가 남아있지 않은지 확인**

Run: `grep -rn "PROPOSED" docs/schemas/`
Expected: 결과 없음 (exit code 1, no matches)

- [ ] **Step 4: `A2A_CONTRACT_CHANGES.md`의 CP-001 상태 갱신**

`docs/A2A_CONTRACT_CHANGES.md`의 CP-001 상태 표에서:

```
| **status** | 🟡 **제안** — MaintQ·FinAllQ 확인 대기 |
```
↓
```
| **status** | 🟢 **채택** (2026-08-21) — 스키마 5종의 PROPOSED 마커 제거 완료. MaintQ·FinAllQ 쪽 구현 확인은 각 레포 자체 진행 |
```

"각 프로젝트가 확인할 것" 체크리스트(MaintQ·FinAllQ 항목)는 수정하지 않는다.

- [ ] **Step 5: 변경 확인**

Run: `grep -n "채택" docs/A2A_CONTRACT_CHANGES.md`
Expected: CP-001 상태 줄에 `🟢 **채택** (2026-08-21)` 포함

- [ ] **Step 6: 커밋**

```bash
git add docs/schemas/advise-policy-renewal.json docs/schemas/claim-insurance.json \
  docs/schemas/notify-asset-change.json docs/schemas/notify-risk-change.json \
  docs/schemas/verify-collateral-insurance.json docs/A2A_CONTRACT_CHANGES.md
git commit -m "docs(contracts): CP-001 채택 — InsuQ 스킬 5종 PROPOSED 마커 제거"
```

---

### Task 2: A2A_IDENTITY.md 미결 사항 5건 재정리

**Files:**
- Modify: `docs/A2A_IDENTITY.md` (## 여전히 남아있는 미결 사항 절)

**Interfaces:** 없음.

- [ ] **Step 1: 항목 1(MaintQ 대리 여부)에 해결됨 라벨 추가**

```
1. **MaintQ는 자기 회사 건만 요청하나, 제3자 대리를 하나?** → actor/subject가 항상
   같은지, 달라질 수 있는지에 따라 위임 테이블 설계가 갈린다. **S8·S13(FinAllQ가
```
↓
```
1. ✅ **해결됨 — MaintQ는 자기 회사 건만 요청하나, 제3자 대리를 하나?** actor/subject가
   항상 같은지, 달라질 수 있는지에 따라 위임 테이블 설계가 갈린다. **S8·S13(FinAllQ가
```

- [ ] **Step 2: 항목 2(파트너 자격증명 발급 주체) 라벨 표기 통일**

```
2. **파트너 자격증명 발급 주체와 연결 절차 — 확정 (2026-08-13)**
```
↓
```
2. ✅ **해결됨 — 파트너 자격증명 발급 주체와 연결 절차** (확정 2026-08-13)
```

- [ ] **Step 3: 항목 3(대출심사 성격)에 해결됨 라벨 추가**

```
3. **"대출심사"(assess-loan 등)의 결과는 조언인가 실행인가?** → `request-withdrawal`·
```
↓
```
3. ✅ **해결됨 — "대출심사"(assess-loan 등)의 결과는 조언인가 실행인가?** `request-withdrawal`·
```

- [ ] **Step 4: 항목 4(출금 파이프라인 여부)에 보류 라벨 추가**

```
4. **출금 요청은 기존 이체 파이프라인(FDS→결재→잔액차감)을 타나, 별도 경로인가?**
   → 타야 한다면 `transfer_request.requester_user_id` NOT NULL 제약과 충돌한다
   (외부 요청에는 요청자 user가 없다). **미해결 — FinAllQ 구현 시 결정.** 후보:
```
↓
```
4. ⏸ **FinAllQ 구현 착수 시 결정 (QMesh 비차단) — 출금 요청은 기존 이체 파이프라인
   (FDS→결재→잔액차감)을 타나, 별도 경로인가?** 타야 한다면
   `transfer_request.requester_user_id` NOT NULL 제약과 충돌한다(외부 요청에는 요청자
   user가 없다). 후보:
```

- [ ] **Step 5: 항목 5(감사 로그 external actor)에 보류 라벨 추가**

```
5. **감사 로그에 외부 actor를 어떻게 남기나?** → 현재 `audit_log.actor_user_id`는
   사람 user를 전제한다. 4번과 같은 해법(서비스 계정 + `principal_type`)이면 자연히
   해결된다. **미해결 — FinAllQ 구현 시 결정.**
```
↓
```
5. ⏸ **FinAllQ 구현 착수 시 결정 (QMesh 비차단) — 감사 로그에 외부 actor를 어떻게
   남기나?** 현재 `audit_log.actor_user_id`는 사람 user를 전제한다. 4번과 같은 해법
   (서비스 계정 + `principal_type`)이면 자연히 해결된다.
```

- [ ] **Step 6: 절 제목에 재정리 날짜 추가**

```
## 여전히 남아있는 미결 사항 (FinAllQ 조사가 그대로 넘긴 것)

FinAllQ 조사 §5의 "QMesh 설계 시 답해야 할 질문"을 그대로 인용한다 — QMesh 쪽 결정이
필요하다:
```
↓
```
## 미결 사항 재정리 (2026-08-21) — 해결됨 3건 · 보류 2건

FinAllQ 조사 §5의 "QMesh 설계 시 답해야 할 질문"을 그대로 인용한다. 5건 중 3건(①②③)은
이미 본문에 결론이 있었고, 2건(④⑤)은 원문에도 "FinAllQ 구현 시 결정"이라 명시돼 있어
QMesh가 지금 대신 정할 수 없다 — 그 구분을 아래에 라벨로 명확히 한다:
```

- [ ] **Step 7: 라벨 반영 확인**

Run: `grep -n "해결됨\|QMesh 비차단" docs/A2A_IDENTITY.md`
Expected: 5개 항목(①~⑤) 모두 출력에 포함 — ✅ 3건, ⏸ 2건

- [ ] **Step 8: 커밋**

```bash
git add docs/A2A_IDENTITY.md
git commit -m "docs(identity): 미결 사항 5건을 해결됨/보류로 재분류"
```

---

### Task 3: 문서 구조 정리 — drift 점검 및 기록

**Files:**
- Read-only 점검: `docs/schemas/*.json`, `docs/agent_cards/*.json`, `README.md`,
  `docs/ref_insuq/A2A_CONTRACTS.md`, `docs/ref_maintq/A2A_CONTRACTS.md`,
  `docs/ref_finallq/A2A_CONTRACTS.md`
- Modify (조건부): 점검 중 실제 drift가 발견된 파일만
- Modify: `docs/A2A_CONTRACT_CHANGES.md` 또는 별도 위치에 점검 결과 한 줄 기록

**Interfaces:** 없음.

- [ ] **Step 1: 스키마 파일 수와 Agent Card 스킬 id 개수 재확인**

Run:
```bash
ls docs/schemas | wc -l
grep -h '"id"' docs/agent_cards/*.json | wc -l
```
Expected: 둘 다 12 — 브레인스토밍 단계에서 이미 확인했으므로 재확인 목적.

- [ ] **Step 2: README.md의 스키마 목록과 실제 파일 목록 대조**

Run:
```bash
ls docs/schemas | sort > /tmp/actual_schemas.txt
grep -oE '[a-z-]+\.json' README.md | sort -u > /tmp/readme_schemas.txt
diff /tmp/actual_schemas.txt /tmp/readme_schemas.txt
```
Expected: 차이 없음(또는 README에 없는 파일/파일에 없는 README 언급이 있으면 기록).

- [ ] **Step 3: ref_* 인덱스 문서 3개에서 "복제하지 않는다" 원칙 위반 여부 확인**

Run: `grep -L "복제하지 않는다\|복제하지 않고" docs/ref_insuq/A2A_CONTRACTS.md docs/ref_maintq/A2A_CONTRACTS.md docs/ref_finallq/A2A_CONTRACTS.md`
Expected: 결과 없음(세 파일 모두 원칙 문구를 포함해야 함 — `-L`은 매치 안 되는 파일만
출력하므로 빈 출력이 정상).

- [ ] **Step 4a (drift 없을 경우): 점검 결과를 문서에 기록**

`docs/A2A_CONTRACT_CHANGES.md` 맨 끝에 아래 절을 추가한다:

```markdown
---

## 문서 구조 점검 기록 (2026-08-21)

스키마 12종 = Agent Card 스킬 id 12종 = README.md 목록 12종 — 전수 대조 완료, drift 없음.
`docs/ref_insuq/`·`docs/ref_maintq/`·`docs/ref_finallq/` 세 인덱스 문서 모두 "원본은
A2A_Q, 복제하지 않는다" 원칙을 일관되게 유지 중. 별도 수정 없음.
```

- [ ] **Step 4b (drift 발견 시): 발견한 문제를 그 자리에서 수정**

Step 1~3에서 불일치가 나오면, 해당 파일을 직접 고치고 위 Step 4a 대신 아래 형식으로
무엇을 고쳤는지 기록한다:

```markdown
---

## 문서 구조 점검 기록 (2026-08-21)

점검 중 다음 drift를 발견해 수정했다: [발견한 내용과 수정한 파일·내용을 구체적으로 적는다]
```

- [ ] **Step 5: 커밋**

```bash
git add docs/A2A_CONTRACT_CHANGES.md
# Step 4b에서 다른 파일도 고쳤다면 함께 add
git commit -m "docs: 문서 구조 drift 점검 결과 기록"
```

---

## Self-Review 완료 기록

- **Spec 커버리지**: spec §①→Task 1, §②→Task 2, §③→Task 3. 3개 항목 모두 태스크로
  매핑됨.
- **Placeholder 스캔**: "TBD"/"나중에" 없음. Task 3 Step 4b만 조건부 분기이나, 분기
  자체가 점검 결과에 따라 달라지는 게 자연스러운 지점이라 placeholder가 아님 — 두
  갈래 모두 완전한 지시문을 담고 있음.
- **일관성**: 세 태스크 모두 "grep으로 검증 → 커밋" 패턴을 동일하게 따름.
