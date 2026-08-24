# A2A 통신 규약 & 계약 평가 보고서

**평가 기준일:** 2026-08-23  
**범위:** agent_cards/*.json, adapters/*/main.py, A2A_DIAGRAMS.md (v1.1)  
**평가 항목:** 통신 규약 적절성, 계약 명확성, 구현 vs 설계 일치도, 보안, 견고성

> ⚠️ **이 문서는 2026-08-23 기준 고정 스냅샷 리뷰입니다 — 이후 대부분의 항목이 바뀌었습니다.**
> 점수·판정은 감사 이력으로 그대로 남겨두고 고치지 않습니다. 최소한 아래 3가지는 이 보고서
> 작성 다음 날(2026-08-24)에 이미 뒤집혔습니다:
> - **"S5 request-withdrawal 🔴 미연결"(15·150행)** — 그 다음 날 실 E2E 성공(200) 확인됨.
> - **"인증 메커니즘 ⚠️ 임시, OAuth2-mock(M1)"·"Basic base64(id:secret)"(16·225-227행)** — MaintQ가
>   InsuQ·FinAllQ 실 인증 필터를 직접 대조한 결과 애초에 Basic이 아니라 Bearer+`X-A2A-Partner-Id`
>   였음을 확인, 그 스킴으로 재작성됨(D120).
> - **"lookup-clause ✅"** 판정 자체는 방향은 맞았지만, 그 뒤 InsuQ가 한때 이 어댑터를 정리하며
>   Spring backend(:8081)를 "정식" 수신부로 못박아 그쪽은 지금도 501을 반환한다 — 지금 동작하는
>   `:9102` 어댑터가 최종 위치인지는 여전히 InsuQ 쪽 결정 대기(H9).
>
> 최신 상태는 `MaintQ_시나리오맵.html` §②, `a2a-contract-and-data-flow.md` §5·§7,
> InsuQ `docs/status_audit.html`을 참고할 것.

---

## 📋 Executive Summary

| 항목 | 판정 | 점수 | 비고 |
|---|---|---|---|
| **HTTP 상태 코드 규약** | ✅ 적절 | 9/10 | 표준 따름, 단 일부 엣지 케이스 미처리 |
| **요청/응답 스키마** | ✅ 명확 | 8/10 | Pydantic 검증, 단 선택 필드 정의 불일치 |
| **구현 vs 설계 일치** | ⚠️ 부분 | 6/10 | lookup-clause ✅ / request-withdrawal 🔴 미연결 |
| **인증 메커니즘** | ⚠️ 임시 | 5/10 | OAuth2-mock (M1), 실제 토큰 교환 미완성 |
| **에러 처리** | ✅ 견고 | 8/10 | 상태 코드 매핑 완벽, 타임아웃 처리 O |
| **보안** | ⚠️ 경계 | 6/10 | 민감정보(Authorization) 제외, 토큰 캐시 기초 |
| **문서화** | ✅ 우수 | 9/10 | 명확한 주석, 다이어그램 충실 |

**종합 판정:** ✅ **계약 구조는 건전, 구현은 부분 완료 (M1 프로토타입 수준)**

---

## ✅ 긍정 평가

### 1. HTTP 상태 코드 규약 (9/10)

**설계 원칙:**

| 상태 | 의미 | 사용 예 | 판정 |
|---|---|---|---|
| **200 OK** | 성공 완료 | `lookup-clause` 응답, `request-withdrawal` COMPLETED | ✅ |
| **400 Bad Request** | 스키마 검증 실패 | 필드 누락, 타입 불일치, chain_id 미스매치 | ✅ |
| **401 Unauthorized** | 인증 실패 | (아직 미구현, 현재 501) | ⚠️ |
| **404 Not Found** | 스킬 미선언 | unknown_skill_id 호출 | ✅ |
| **501 Not Implemented** | 스킬 미구현 | `advise-hedge`, `claim-insurance` 등 | ✅ |
| **502 Bad Gateway** | 업스트림 불가 | InsuQ ai-engine 다운 | ✅ |
| **504 Gateway Timeout** | 업스트림 타임아웃 | InsuQ 응답 지연 | ✅ |

**코드 검증 (InsuQ adapter):**

```python
# main.py:79-96 (✅ 표준 준수)
except UpstreamUnavailableError as exc:
    return JSONResponse(status_code=502, ...)
except UpstreamTimeoutError as exc:
    return JSONResponse(status_code=504, ...)
```

**평가:** 표준 HTTP 상태 코드를 정확하게 사용. 다만 401(Unauthorized) 구현 대기 중.

---

### 2. 요청/응답 스키마 설계 (8/10)

**InsuQ lookup-clause 요청 검증:**

```python
# schemas.py 검증 규칙
class LookupClauseRequest(BaseModel):
    request_chain_id: str           # ✅ 멀티홉 추적
    domain: str                      # ✅ 실손/화재/재물
    product: str                     # ✅ 구체적 상품명
    question: str                    # ✅ 자연어 질의
```

**응답 상태 전이 (3가지):**

```python
# mapping.py:17-39 (✅ 결정론적)
if needs_clarification:
    return {"status": "input-required", ...}  # 추가 정보 필요
elif no evidence:
    return {"status": "rejected", "rejection_reason": "no_evidence_found"}
else:
    return {"status": "completed", "answer": ..., "evidence": [...]}
```

**FinAllQ transfer 상태 매핑 (6가지):**

```python
# mapping.py:20-50 (✅ 완벽한 열거)
PENDING / APPROVED / PENDING_2FA  → input-required
BLOCKED                          → rejected (fds_check="hold")
REJECTED                         → rejected
COMPLETED                        → completed
```

**평가:** Pydantic 검증으로 타입 안전성 확보. 상태 전이 명확. 단, 선택 필드(`confirm_required`, `sufficient`) 정의가 스키마마다 불일치.

---

### 3. 에러 처리 견고성 (8/10)

**계층별 에러 처리:**

| 계층 | 에러 처리 | 코드 | 평가 |
|---|---|---|---|
| **스키마** | 400 + 상세 메시지 | `ValidationError` 캐치 | ✅ 우수 |
| **업스트림** | 502/504 | UpstreamUnavailableError/TimeoutError | ✅ 우수 |
| **토큰** | 재시도 + 캐시 갱신 | `_transfer_with_auth_retry()` | ✅ 우수 |
| **알 수 없는 상태** | 502 | `ValueError` → JSONResponse | ✅ 안전 |

**FinAllQ 토큰 재시도 로직 (✅ 견고):**

```python
async def _transfer_with_auth_retry(parsed: RequestWithdrawalRequest) -> dict:
    token = await get_token(...)  # 첫 시도
    try:
        return await _do_transfer(parsed, token)
    except AuthExpiredError:
        _token_cache.clear()       # 캐시 무효화
        token = await get_token(...)  # 재획득
        return await _do_transfer(parsed, token)  # 재시도
```

**평가:** 타임아웃, 재시도, 캐시 무효화가 체계적으로 구현됨.

---

### 4. 문서화 품질 (9/10)

**장점:**

| 항목 | 평가 |
|---|---|
| **주석 정확성** | "누구나 이해하는 수준의 명확한 설명" |
| **다이어그램 충실도** | Mermaid + 상태 표기(✅/🔴) 완벽 |
| **설계 공개** | 의도와 제약(예: `:g` 포맷 금지) 명시 |
| **포트 관리** | 정식(9001/9002) vs 프로토타입(9101/9102) 명확히 구분 |

**예시 (InsuQ adapter docstring):**
```python
"""InsuQ lookup-clause A2A 어댑터 — 독립 FastAPI 서비스 (기본 포트 9102).
InsuQ 코드를 건드리지 않고 기존 POST /qa(:8000)를 A2A 봉투로 감싼다."""
```

---

## ⚠️ 주의 평가

### 1. 구현 vs 설계 불일치 (6/10)

**A2A_DIAGRAMS.md v1.1 검증:**

| 시나리오 | 스킬 | 설계 상태 | 실제 상태 | 갭 |
|---|---|---|---|---|
| S7 | advise-policy-renewal | 🔴 미구현 | 501 | ✅ 일치 |
| S5 | request-withdrawal | 🔴 미연결 | 501 아님! | ❌ **불일치** |
| S8 | assess-loan (FinAllQ) | assess-loan 구현 + InsuQ 2차 호출 | **부분** | ⚠️ |
| Lookup | lookup-clause | ✅ 끝단 연결 | ✅ 동작 | ✅ 일치 |

**핵심 갭:**

#### 🔴 Issue 1: request-withdrawal 트리거 미연결

**현황 (A2A_DIAGRAMS.md §⑦ 재확인):**

```
┌──────────────────────────────────────────────┐
│ dispatch_a2a_withdrawal_request() 함수      │
│ • payload 조립 ✅                           │
│ • call_skill() 호출 ✅                      │
│ • trace 기록 ✅                             │
│                                              │
│ 문제: 이 함수를 호출하는 곳이 없다!        │
│ (MaintQ services/po.py::transition() 미연결)│
└──────────────────────────────────────────────┘
```

**실제 코드 (finallq_a2a/main.py:77-101):**

```python
@app.post("/a2a/skills/request-withdrawal")
async def request_withdrawal(request: Request) -> JSONResponse:
    # ✅ 어댑터는 준비됨
    # 🔴 하지만 MaintQ가 이 엔드포인트를 호출하지 않음
```

**해석:** 설계는 완벽하지만 마지막 배선이 없음. A2A_DIAGRAMS.md의 "🔴 트리거 미연결" 표기가 맞음.

---

#### ⚠️ Issue 2: assess-loan 2차 홉 (FinAllQ → InsuQ)

**설계 의도:**
```
MaintQ → FinAllQ assess-loan
           ↓ (내부 호출)
           InsuQ verify-collateral-insurance
           ↓ (응답)
         LTV 판정
```

**구현 현황:**

```python
# finallq_a2a/main.py:28
from adapters.finallq_a2a.insuq_client import call_verify_collateral_insurance

# 근데 assess-loan 엔드포인트가 finallq_a2a에는 없다!
# (agent_card에는 선언되어 있지만 main.py에 @app.post("/a2a/skills/assess-loan")이 없음)
```

**문제:** assess-loan은 선언되어 있지만 엔드포인트 구현이 없음 → 404 반환.

---

### 2. 인증 메커니즘 (5/10)

**현황:**

| 단계 | 상태 | 코드 | 평가 |
|---|---|---|---|
| **M1: 목업** | ✅ 완료 | `oauth2-mock` 선언 | ✅ |
| **토큰 캐싱** | ✅ 기초 | `TokenCache()` 클래스 | ✅ |
| **토큰 갱신** | ✅ 재시도 | `_transfer_with_auth_retry()` | ✅ |
| **실제 OAuth2** | 🔴 미결정 | FinAllQ 쪽 구현 미정 | ❌ |
| **토큰 검증** | 🔴 미구현 | 어댑터에서 헤더 검사 없음 | ❌ |

**코드 검증:**

```python
# finallq_a2a/auth.py::build_auth_header()
if usable:
    return {"Authorization": "Basic base64(id:secret)"}
else:
    return {}  # 🔴 인증 없이도 요청 가능
```

**FinAllQ adapter의 헤더 검사:**

```python
# finallq_a2a/main.py에는 Authorization 검증이 없음
# (로그인 후 토큰을 받지만, 어댑터 입구에서 검증하지 않음)
```

**평가:** M1 목업으로는 충분하지만, 프로덕션 이전에 실제 토큰 검증 로직 필요.

---

### 3. 민감정보 처리 (7/10)

**장점:**

```python
# main.py:76 (✅ 민감정보 제외)
MQ->>MQ: traces에 tool_call/tool_result 기록(Authorization 헤더 제외)
```

**우려사항:**

| 항목 | 현황 | 리스크 |
|---|---|---|
| **password** | 환경변수 | ⚠️ 로그에 노출 가능 |
| **token** | 메모리 캐시 | ⚠️ 메모리 덤프 시 노출 |
| **response** | dict 그대로 저장 | ⚠️ API 응답에 민감정보 포함 시 저장됨 |

**권장사항:** response를 추상화된 형태로만 저장 (예: response_summary = f"status={status}")

---

## ❌ 문제 평가

### 1. Agent Card vs 실제 구현 괴리 (6/10)

**InsuQ Agent Card 선언:**

```json
{
  "skills": [
    {"id": "advise-policy-renewal", "scenario": "S7"},
    {"id": "verify-collateral-insurance", "scenario": "S8, S13"},
    {"id": "notify-asset-change", "scenario": "S11"},
    {"id": "notify-risk-change", "scenario": "S14"},
    {"id": "claim-insurance", "scenario": "S15"},
    {"id": "lookup-clause", "scenario": "제안"}
  ]
}
```

**실제 구현 (insuq_a2a/main.py):**

```python
@app.post("/a2a/skills/lookup-clause")
async def lookup_clause(...):
    # ✅ 구현됨

@app.post("/a2a/skills/{skill_id}")
async def unimplemented_skill(skill_id: str, ...):
    # 🔴 나머지 5개 스킬 → 501 반환
```

**평가:** 정직한 503/501 응답은 좋지만, Agent Card와 구현의 일치 여부를 외부자가 판단하기 어려움.

**권장사항:**
```json
{
  "skills": [
    {
      "id": "lookup-clause",
      "status": "implemented",
      "scenario": "제안"
    },
    {
      "id": "advise-policy-renewal",
      "status": "declared-not-implemented",
      "scenario": "S7"
    }
  ]
}
```

---

### 2. 스키마 필드 불일치 (6/10)

**InsuQ lookup-clause 응답:**

```python
# mapping.py:18-39 (3가지 경로)
# 경로 1: status="input-required"
return {"status": "input-required", "confirm_required": [...], "evidence": []}

# 경로 2: status="rejected"
return {"status": "rejected", "rejection_reason": "...", "evidence": []}

# 경로 3: status="completed"
return {"status": "completed", "answer": "...", "verdict": "...", 
        "confirm_required": [...], "evidence": [...]}
```

**문제:** 경로마다 응답 필드가 다름 → 호출자가 어떤 필드를 기대해야 할지 불명확.

**권장 해결:**

```python
class LookupClauseResponse(BaseModel):
    status: Literal["input-required", "rejected", "completed"]
    
    # 항상 존재
    evidence: list[str] = []
    request_chain_id: str
    
    # 조건부 — Optional + Field(default=None)
    answer: Optional[str] = Field(None, description="status='completed'일 때만")
    rejection_reason: Optional[str] = Field(None, description="status='rejected'일 때만")
    confirm_required: list[str] = Field(default_factory=list)
```

---

### 3. 멀티홉 error propagation (5/10)

**S8 (assess-loan)의 2차 홉:**

```
MaintQ → FinAllQ assess-loan
           → InsuQ verify-collateral-insurance (2차)
             × 502 Bad Gateway
           → ???
```

**현황:**

```python
# finallq_a2a/main.py (미구현)
# assess-loan 엔드포인트 자체가 없으므로
# 2차 홉 에러 처리도 정의되지 않음
```

**위험:**

| 케이스 | 처리 | 평가 |
|---|---|---|
| InsuQ 502 | 그대로 반환? | ❌ 불명확 |
| InsuQ 504 | 재시도? | ❌ 정책 없음 |
| 부분 응답 | 거절? | ❌ 가이드 없음 |

**권장:** SLA 정의
```
2차 홉 타임아웃(504) → MaintQ에 input-required 반환하고 재시도 권유
2차 홉 502 → 일단 "담보 검증 불가" 상태로 대기
```

---

## 🔒 보안 평가

### 위험도 순위

| 위험 | 수준 | 현재 상태 | 완화책 |
|---|---|---|---|
| **토큰 노출** | 높음 | M1 목업 | OAuth2 실제 구현 후 TLS + Secure 쿠키 |
| **민감정보 로그** | 중간 | Authorization 제외 | response 추상화 필터 추가 |
| **CSRF** | 중간 | 미고려 | POST 엔드포인트 + state 검증 추가 |
| **Rate limit** | 중간 | 미구현 | FastAPI middleware 추가 |
| **의존성** | 낮음 | httpx, pydantic | 정기 보안 업데이트 |

---

## 💡 개선 제안

### Priority 1: 즉시 필요 (Pre-M2)

| 항목 | 현황 | 작업 | 일정 |
|---|---|---|---|
| request-withdrawal 트리거 배선 | 🔴 미연결 | MaintQ po.py::transition() 호출 추가 | 1주 |
| assess-loan 엔드포인트 구현 | 🔴 미구현 | FinAllQ adapter에 @app.post("/a2a/skills/assess-loan") 추가 | 2주 |
| 스키마 필드 문서화 | ⚠️ 불명확 | 조건부 필드 Optional + 주석 추가 | 1주 |
| 테스트 추가 | ❌ 전무 | `test_lookup_clause.py`, `test_request_withdrawal.py` 추가 | 2주 |

### Priority 2: 안정화 (M2~M3)

| 항목 | 작업 |
|---|---|
| **OAuth2 실제 구현** | FinAllQ의 service account 인증 체계 구축 |
| **토큰 검증** | adapter 엔드포인트에서 Authorization 헤더 검증 |
| **2차 홉 error propagation** | assess-loan에서 verify-collateral 실패 시 정책 정의 |
| **Agent Card 상태 필드** | `status: "implemented" \| "declared-not-implemented"` 추가 |

### Priority 3: 장기 개선 (Post-M3)

| 항목 | 작업 |
|---|---|
| **Rate limiting** | FastAPI middleware로 IP당 요청 제한 |
| **Circuit breaker** | 업스트림 503이 N회 이상 시 fail-fast |
| **분산 추적** | OpenTelemetry + Jaeger로 멀티홉 추적 |
| **메트릭** | Prometheus로 요청 지연/에러율 모니터링 |

---

## 📊 최종 스코어

```
통신 규약 적절성:   9/10 ✅
계약 명확성:        8/10 ✅
구현 완성도:        6/10 ⚠️
인증/보안:          5/10 ⚠️
에러 처리:          8/10 ✅
문서화:             9/10 ✅
───────────────────
평균:              7.5/10 (B+ 수준)

M1 프로토타입으로서는 ✅ 건전
본격 M2 구현 전에 Priority 1 완료 필수
```

---

## 📝 체크리스트

**M2 Go/No-Go 전:**

- [ ] request-withdrawal 트리거 배선 (MaintQ)
- [ ] assess-loan 엔드포인트 (FinAllQ adapter)
- [ ] 스키마 필드 문서화 (모든 adapter)
- [ ] 최소 5개 통합 테스트 (lookup-clause, request-withdrawal, assess-loan)
- [ ] 에러 처리 규칙 문서화 (멀티홉 timeout/502)
- [ ] Agent Card `status` 필드 추가

**M3 Go/No-Go 전:**

- [ ] OAuth2 실제 구현 + 토큰 검증
- [ ] Rate limiting middleware
- [ ] 분산 추적 통합
- [ ] 모든 스킬 구현 또는 Deprecated 표기

---

**작성:** 기술 검토팀  
**다음 검토:** M2 구현 50% 완료 시

