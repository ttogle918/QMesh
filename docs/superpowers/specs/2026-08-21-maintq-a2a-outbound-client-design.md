# MaintQ A2A 아웃바운드 클라이언트 — 설계 (2026-08-21)

> **이 문서는 설계만 다룬다 — 코드는 이 라운드에 작성하지 않는다.** 구현은 MaintQ 레포
> 쪽에서 별도로 진행한다. 여기서는 아키텍처·인터페이스·구체적 두 스킬(예시)의 payload
> 매핑까지 확정하고, 코드는 이 설계를 그대로 따라가면 되게 만드는 것이 목표다.

## 배경

MaintQ는 A2A 그래프에서 **항상 요청을 시작하는 client**다(`docs/ref_maintq/A2A_CONTRACTS.md`:
"MaintQ는 A2A 스킬을 노출하지 않는다"). 지금까지 A2A_Q에서 만든 두 어댑터
(`adapters/insuq_a2a/` — `lookup-clause`, `adapters/finallq_a2a/` — `request-withdrawal`)는
전부 **수신자** 쪽이었다. 이번 설계는 그 반대편, MaintQ가 그 어댑터들에게 **실제로 요청을
보내는 코드**의 아키텍처를 다룬다.

MaintQ 레포는 이미 이 작업을 상당 부분 준비해뒀다(Sprint 8, D91~D96):

- **`backend/a2a/credentials.py`** — 파트너(`finallq`·`insuq`)별 `client_id`/`client_secret`을
  환경변수에서 읽는 계층. 자체 docstring이 이미 못박아뒀다: *"토큰 캐시는 A2A 호출부가
  생기는 스프린트가 만든다"* — 이번 설계가 바로 그 스프린트다.
- **`partner_links` 테이블**(§18, D91·D92·D95·D96) — 외부 파트너 subject 매핑 대장.
  `(partner, subject_type, subject_ref)` PK, `link_state`(NULL=모름/NOT_LINKED/LINKED),
  `external_ref`(상대 시스템 식별자). 시드에 `finallq|company|''|LINKED|CMP-MAINTQ-001`
  행이 이미 있다 — 이게 `requester.finallq_company_id`가 가리킬 실제 값이다.
- **`traces.request_chain_id` 컬럼**(§25, D94) — 이미 있지만 nullable이고 "쓰는 쪽 없음"
  (A2A 호출부 미착수)이 시드 검사 ㉕의 기대값으로 명시돼 있다.

미착수인 것: **실제 HTTP 호출 코드, payload 조립, 응답 처리, trace 기록** — 이 넷이 이번
설계의 범위다.

## 범위

- **일반 아키텍처**: 트리거 감지 → payload 조립 → HTTP 호출(인증 포함) → 응답 처리 →
  trace 기록으로 이어지는 5단계 파이프라인. 어떤 스킬이든 이 모양을 따른다.
- **구체적으로 설계하는 스킬 둘**: `request-withdrawal`(S5, FinAllQ) — 실제로 존재하는
  어댑터가 있고 트리거(`po.py::transition`)도 실측했다. `lookup-clause`(InsuQ) — 마찬가지로
  실제 어댑터가 있다.
- **나머지 8개 트리거**는 §⑥에 표로만 정리한다 — 같은 파이프라인을 타되, 각 스킬의
  payload 조립 세부는 이번 설계에 넣지 않는다(어댑터 자체가 아직 InsuQ·FinAllQ 양쪽 다
  없다).

## ① 인증 설계 — credentials.py와 실제 어댑터 사이의 간극을 어떻게 다루나

**간극**: `credentials.py`는 OAuth2 client-credentials 그랜트(client_id/secret → 토큰
발급 → 캐싱, D93 원안)를 상정한다. 그런데 실제로 만든 두 어댑터는 이 흐름을 검증하지
않는다 — InsuQ `lookup-clause`는 인증 자체가 없고, FinAllQ `request-withdrawal`은 사람
서비스 계정 로그인이라 파트너 토큰 개념 자체가 없다(`docs/A2A_IDENTITY.md`: "M1 단계
권고 — 인가 테이블은 지금 스키마에 넣고, 토큰 검증부는 목업 유지").

**결정**: 지금은 `credentials.load(partner)`만 호출해서 얻은 값을 헤더에 실어 보내고,
어댑터가 검사하지 않아도 무시되도록 둔다. 미래에 실제 토큰 교환이 붙어도 **호출부
코드는 안 바뀌게** — 헤더를 만드는 부분만 나중에 교체될 내부 구현으로 격리한다(FinAllQ
어댑터의 `auth.py`를 나머지 코드에서 분리해둔 것과 같은 이유).

```python
# backend/a2a/auth_header.py (신규, 개념)
def build_auth_header(partner: str) -> dict[str, str]:
    """credentials.load(partner)로 얻은 값을 Authorization 헤더로 만든다.

    M1 목업: 실제 토큰 교환 엔드포인트가 아직 없어 client_id:client_secret을
    HTTP Basic으로 그대로 실어 보낸다. 어댑터가 검사하지 않으므로 지금은
    효과가 없지만, 나중에 어댑터 쪽에 토큰 교환이 붙으면 **이 함수 내부만
    바뀐다** — 호출부(client.py)는 "헤더 dict를 받아 붙인다"는 계약만 안다.
    """
    cred = credentials.load(partner)
    if not cred.usable:
        return {}  # not_configured/incomplete여도 예외를 던지지 않는다(D9) — 헤더 없이 호출 진행
    token = base64.b64encode(f"{cred.client_id}:{cred.client_secret}".encode()).decode()
    return {"Authorization": f"Basic {token}"}
```

`cred.usable`이 아닐 때(현재 실제 상태 — env var가 전부 빈칸)도 호출 자체는 막지 않는다.
어댑터가 인증을 검사하지 않는 지금은 이게 정상 동작이다.

## ② 공용 호출 함수 — `backend/a2a/client.py` (신규, 개념)

```python
async def call_skill(
    partner: str,          # "finallq" | "insuq"
    skill_id: str,         # "request-withdrawal" | "lookup-clause" | ...
    payload: dict,
    request_chain_id: str,
    base_url: str,
    timeout: float = 10.0,
) -> dict:
    """A2A_Q 어댑터의 POST /a2a/skills/{skill_id}를 호출한다.

    - Authorization 헤더: build_auth_header(partner) (있으면 붙이고 없으면 생략)
    - X-Request-Chain-Id 헤더: request_chain_id (body의 request_chain_id와 반드시 동일 —
      다르면 어댑터가 400 chain_id_mismatch를 낸다, InsuQ/FinAllQ 어댑터 공통 규약)
    - 에러 매핑(두 어댑터의 공통 에러 봉투 {"error", "detail", "request_chain_id"}를
      그대로 파싱): 502/504는 재시도하지 않고 즉시 실패로 처리, rejected/input-required는
      정상 응답으로 취급(HTTP 200)하고 호출부가 status로 분기
    """
```

**partner별 `base_url`은 어떻게 아는가** — 이번 설계에서는 환경변수로 고정한다
(`MAINTQ_A2A_FINALLQ_BASE_URL`·`MAINTQ_A2A_INSUQ_BASE_URL`, 기본값 없음 — 미설정이면
호출 자체를 시도하지 않고 즉시 실패로 처리한다. QMesh 오케스트레이터(:9000)가 서면 그
쪽으로 단일화하겠지만, 아직 없으므로 지금은 각 어댑터를 직접 가리킨다).

## ③ 스킬 1 — `request-withdrawal` (S5, FinAllQ) 구체 설계

### 트리거
`backend/services/po.py::transition(po_id, "approved", decided_by, note)`가 성공적으로
반환한 직후(같은 트랜잭션은 아니어도 됨 — 커밋 후 별도 스텝) — 이게 "팀장 승인 완료"
시점이다.

### 🔴 발견한 갭 — `suppliers` 테이블에 계좌번호가 없다
CP-002(`docs/A2A_CONTRACT_CHANGES.md`)가 `request-withdrawal` 스키마에
`to_account_number`(필수)를 추가했는데, MaintQ의 `suppliers` 테이블(`docs/05_DB_SCHEMA.md`
§7)에는 `supplier_id`·`name`·`contact`뿐이고 **계좌번호를 저장할 컬럼 자체가 없다.**
이건 FinAllQ 쪽에서 발견한 것과 같은 종류의 갭이 MaintQ 쪽에도 있다는 뜻이다 —
**MaintQ가 먼저 `suppliers.account_number`(및 선택적으로 `bank_code`) 컬럼을 추가하지
않으면, `to_account_number`를 채울 원천 데이터가 없다.** 이 설계 문서는 이 갭을
**기록만** 한다 — 실제 마이그레이션·시드 갱신은 MaintQ 레포 쪽 결정(D-번호 신설 대상)이다.

### Payload 조립
`po` 인자는 `services/po.py::get_po()`가 반환하는 dict(= `_PO_SELECT` 조인 결과, `part_name`·
`supplier_name`·`decided_by_name` 등 포함)이고, `supplier_row`는 `suppliers` 테이블에서
`supplier_id`로 직접 조회한 행이다(`_PO_SELECT`는 `supplier_name`만 조인해 오므로 계좌
정보를 얻으려면 별도 조회가 필요 — 갭 해소 후 `account_number`·`bank_code` 컬럼이 생기면
이 조회 하나만 추가하면 된다):

```python
def build_request_withdrawal_payload(
    po: dict, supplier_row: dict, request_chain_id: str
) -> dict:
    return {
        "requester": {
            "finallq_company_id": get_finallq_company_id() or "",
        },
        "request_chain_id": request_chain_id,
        "po_id": po["po_id"],
        "amount": po["unit_price"] * po["qty"],
        "supplier": po["supplier_name"],
        "approved_by": po["decided_by"],  # X-User로 주입된 팀장 사용자 ID
        "purpose": po["reason"],  # po_drafts.reason — "진단 근거"를 출금 사유로 재사용
        "error_code": po["error_code"],
        "to_account_number": supplier_row["account_number"],  # 🔴 갭 — 컬럼이 아직 없다(아래 참조)
        "to_bank_code": supplier_row.get("bank_code"),
    }
```

**`finallq_company_id`를 하드코딩하지 않는다** — 실제로는:
```python
def get_finallq_company_id(db_path=None) -> str | None:
    """partner_links에서 finallq 파트너의 company 결 external_ref를 조회한다.

    회사 결은 subject_ref=''(D96)로 고정돼 있다 — 건물처럼 여러 행이 아니라 항상
    정확히 1행이다. link_state != 'LINKED'면 None을 반환하고 호출부가 호출을
    보류한다 — "연결 승인 전에는 아무것도 나가면 안 된다"는 A2A_Q 결정 2와 같다.
    """
    with connect(db_path) as con:
        r = con.execute(
            "SELECT external_ref, link_state FROM partner_links"
            " WHERE partner = 'finallq' AND subject_type = 'company' AND subject_ref = ''"
        ).fetchone()
    if r is None or r["link_state"] != "LINKED":
        return None
    return r["external_ref"]
```

### 응답 처리
- `status: "input-required"` → 정상 — "재무 승인 대기 중" 상태를 화면(승인 큐)에 반영.
  이 스킬은 원래 2단 승인이 전제이므로 `input-required`가 **기대되는 결과**다.
- `status: "rejected"` → FDS 차단 등 — 사람(팀장)에게 사유(`reject_reason`)와 함께 안내.
  **재시도하지 않는다**(CP-001이 확립한 원칙을 이 방향에도 그대로 적용).
- `status: "completed"` → 즉시 실행됨(드문 경로, 소액 자동승인 등) — 발주 상태에 반영.
- 502/504(어댑터·FinAllQ 도달 불가) → 발주는 `approved` 상태 그대로 두고, "출금 요청
  전송 실패, 재시도 필요"를 팀장 화면에 노출. **자동 재시도는 하지 않는다** — 멱등성
  키가 아직 계약에 없어서(design spec의 "하지 않는 것" 참조), 자동 재시도가 중복 요청을
  만들 수 있다.

### Trace 기록
- `traces.request_chain_id`에 값을 채운다(지금까지 nullable로만 있던 컬럼의 첫 실사용).
- 나가는 요청·받은 응답 원문은 **컬럼으로 복제하지 않고** 그 trace 이벤트의
  `tool_result` 행에 그대로 보관한다(MaintQ 자체 결정 — `A2A_IDENTITY.md`의 "MaintQ
  구현 세부 결정" 참조: "link_state가 나중에 바뀔 수 있어 과거 trace에 박제된 값과
  현재 매핑이 어긋나면 판정 근거가 사라진다").
- ⛔ **`Authorization` 헤더는 저장 대상에서 반드시 제외** — payload를 통째로 저장하는
  결정이므로, 헤더까지 같이 저장하면 자격증명이 평문으로 DB에 남는다.

## ④ 스킬 2 — `lookup-clause`(InsuQ) 구체 설계

### 트리거가 다르다 — 상태 전이가 아니라 질의(query)
`request-withdrawal`은 "발주가 승인됐다"는 **상태 전이**가 트리거지만, `lookup-clause`는
그런 이벤트가 없다. InsuQ 어댑터 설계 스펙 자체가 이 스킬의 용도를 이렇게 규정했다:
*"MaintQ가 '이 설비 손해가 약관상 뭐라고 돼 있나'를 물을 때"*(`2026-08-21-insuq-lookup-clause-adapter-design.md`) —
**사람(정비사·관리자)이 화면에서 직접 물어보는 질의**다.

### 승인 게이트가 필요 없다 — 하지만 여전히 백엔드를 거친다
`credentials.py`의 docstring은 "A2A 호출은 사람 승인 뒤 백엔드가 하는 일이다(절대규칙
1)"이라고 적어뒀는데, 이 문장은 **돈·계약이 움직이는 스킬**을 염두에 두고 쓰인 것이다
(QMesh README §4-①: "돈과 계약이 움직이는 곳에는 반드시 사람의 승인"). `lookup-clause`는
순수 조회이고 InsuQ 어댑터 자체도 "돈·계약 안 움직임 → 최저 위험"으로 분류했다 —
**승인 게이트 없이 즉시 호출**해도 관통 원칙에 어긋나지 않는다.

**단, MCP 도구에서 직접 호출하지는 않는다** — D15("MCP 도구는 A2A를 보지 않는다")는
그대로 지킨다. 화면(또는 채팅 핸들러)이 사용자 질문을 받으면 **백엔드 API 엔드포인트**를
하나 거쳐 `call_skill("insuq", "lookup-clause", ...)`을 호출하고, 그 결과를 화면에
그대로 보여준다. MCP 도구는 이 흐름에 관여하지 않는다 — LLM이 A2A 호출 여부를 결정하지
않는다는 원칙(신원 위조 방지와 같은 이유)이 조회형 스킬에도 동일하게 적용된다.

### Payload 조립
```python
def build_lookup_clause_payload(question: str, request_chain_id: str) -> dict:
    return {
        "requester": {
            "finallq_company_id": get_finallq_company_id() or "",  # 선택 필드, 없어도 호출 가능
        },
        "request_chain_id": request_chain_id,
        "question": question,
        # domain·product는 지정하지 않는다 — InsuQ 쪽이 규칙 기반으로 분류(스펙 §)
    }
```
`lookup-clause`의 `requester` 내부 필드는 전부 선택(§Requester 설계 참조)이라
`finallq_company_id`가 비어 있어도 유효한 요청이다 — `partner_links`에 InsuQ 연결이
아직 안 돼 있어도(현재 실제 상태) 호출이 막히지 않는다.

### 응답 처리
- `status: "completed"` → `answer`·`verdict`·`evidence[]`를 그대로 화면에 표시.
- `status: "input-required"` → `confirm_required[]`(되묻기 질문)를 사용자에게 다시 노출.
- `status: "rejected"` → "약관에서 확인할 수 없습니다"를 그대로 보여준다 — InsuQ의
  거부가 이미 사용자 대면 문구로 설계돼 있으므로 가공하지 않는다.

### Trace 기록
`request-withdrawal`과 동일한 패턴(request_chain_id 채움, 원문은 tool_result에).
단, 이 스킬은 돈이 안 움직이므로 감사 강도를 다르게 가져갈지는 이번 설계에서 결정하지
않는다 — MaintQ 팀 판단.

## ⑤ 두 스킬에서 공통으로 뽑아낸 파이프라인

```
[1] 트리거 감지
    - 상태 전이형: 서비스 함수(예: po.transition) 호출 성공 직후
    - 질의형: 사용자 요청을 받는 백엔드 엔드포인트 핸들러 안
[2] partner_links 조회 → subject 확정 (company/building/asset 결에 맞게)
    - link_state != LINKED면 호출을 보류하고 사람에게 사유 표시
[3] payload 조립 (스킬별 함수, §③·④ 패턴)
[4] call_skill() 호출
    - build_auth_header(partner) 로 헤더 구성
    - X-Request-Chain-Id == body.request_chain_id 보장
[5] 응답 처리
    - status 분기 (completed/input-required/rejected는 정상 200, 재시도 안 함)
    - 502/504는 사람에게 "재시도 필요" 안내, 자동 재시도 안 함(멱등키 없음)
[6] trace 기록
    - traces.request_chain_id 채움
    - 원문(헤더 제외)을 tool_result에 보관
```

## ⑥ 나머지 8개 트리거 (이번 설계에 포함하지 않음 — 표로만)

`docs/ref_maintq/A2A_CONTRACTS.md`가 이미 실측한 트리거 목록을 그대로 인용한다. 전부
§⑤ 파이프라인을 타지만, 상대 어댑터(InsuQ의 나머지 4스킬, FinAllQ의 나머지 6스킬)가
아직 하나도 없어서 payload 조립 세부는 이번 설계에 넣지 않는다.

| 트리거 (MaintQ 내부 이벤트) | 대상 | 스킬 |
|---|---|---|
| 환헤지 상담 요청(수동, 향후) | FinAllQ | `advise-hedge` |
| 화재보험 갱신 상담 요청 | InsuQ | `advise-policy-renewal` |
| 담보 대출 상담 요청 | FinAllQ (→ 내부 2차홉 InsuQ) | `assess-loan` |
| 처분 서명 완료 (`decisions.py` sign) | InsuQ | `notify-asset-change` |
| 처분 확정 + 매각대금 입금 | FinAllQ | `request-settlement` |
| 중고설비 취득 검토 | FinAllQ (→ 내부 2차홉 InsuQ) | `assess-used-equipment-loan` |
| 신규 설비 등재 → 위험 프로파일 재계산 | InsuQ | `notify-risk-change` |
| 설비 화재 멸실 사고 | InsuQ (응답 후 FinAllQ 2차 호출) | `claim-insurance` → `advise-replacement-financing` |
| 설비 취득 예산 확정 | FinAllQ | `advise-financing` |

## 하지 않는 것 (범위 밖)

- 위 표 8개 스킬의 payload 조립 세부 설계 — 상대 어댑터가 생기면 그때.
- 실제 코드 작성 — 이 문서는 설계까지만, 구현은 MaintQ 레포에서 별도 진행.
- 실제 OAuth 토큰 교환 엔드포인트 구현 — 어댑터·MaintQ 양쪽 다 아직 없음. `build_auth_header`는
  그 자리에 들어갈 함수의 **모양**만 정의한다.
- `suppliers.account_number` 마이그레이션 — MaintQ 레포 쪽 결정으로 남긴다(§③의 갭 참조).
- QMesh 오케스트레이터(:9000) 연동 — 아직 없으므로 각 어댑터 base_url을 직접 설정.
- 멱등성(`Idempotency-Key`) — InsuQ·FinAllQ 어댑터 양쪽 다 아직 없어서 MaintQ 쪽에서
  먼저 보낼 이유가 없다. 어댑터가 먼저 갖추면 그때 호출부에 추가한다.

## 완료 기준 (이 설계 문서 자체의 완료 기준 — 코드 완료 기준 아님)

- `build_auth_header`·`call_skill`의 시그니처와 책임 분리가 명확한가
- `request-withdrawal`·`lookup-clause` 두 스킬의 트리거·payload 조립·응답 처리·trace
  기록이 실제 코드(`po.py`, `partner_links`, `traces`)와 어긋나지 않는가
- `suppliers` 테이블 갭처럼, 구현 전에 MaintQ 팀이 먼저 결정해야 할 것이 명확히
  드러나 있는가
