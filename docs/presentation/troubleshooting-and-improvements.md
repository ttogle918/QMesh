# FinAllQ & InsuQ: Troubleshooting 및 성능 개선 기록

**분석 범위:** Sprint 6 ~ Sprint 16 (2026-07-20 ~ 2026-08-23)

---

## 📋 Executive Summary

FinAllQ와 InsuQ 개발 과정에서 마주친 주요 문제들과 해결 방안을 기록합니다. 특히:
- **LLM 모델 선택 과정**에서의 성능 지표 변화
- **골든셋 태깅 문제**와 평가 지표 재정의
- **구조적 결함**의 식별과 해결

이들은 프로젝트의 신뢰도를 높이기 위해 구현 중 발견되고 해결된 사항들입니다.

---

## 🔴 Major Issues

### Issue 1: LLM 모델 선택 — Nemotron vs Gemini

**프로젝트:** InsuQ
**발생 시기:** EXP-002~003 (2026-07-20)
**영향도:** 핵심 (모델 교체 결정)

#### 증상

모델 선택 당시 두 후보 비교:

| 모델 | p95 레이턴시 | 거부 정확도 | 단정 위반 | 게이트 |
|---|---|---|---|---|
| **NVIDIA nemotron** | 44.7s 🚨 | 100% | 1/24 | ❌ FAIL |
| **Gemini 3.5 Flash** | 10.4s ✅ | 100% | 0/24 | ✅ PASS |

#### 근본 원인

**nemotron의 타임아웃 악순환:**

1. 정상 호출의 최대 레이턴시: ~19.4s
2. 타임아웃 설정: 25s (너무 촉박)
3. 타임아웃 초과 시 exponential backoff 재시도 (1s + 2s + 4s = 7s)
4. 결과: 19.4 + 7 = ~26.4s → 여전히 초과 → 재시도 반복
5. **최종: p95 44.7s** ← 재시도 오버헤드로 인한 평가 세트 전체 실행 시간 2배 증가

#### 해결

**모델 교체** (구조적 해결 불가능)
- nemotron: "빠른 모델 찾기" 우회 불가능 (동일 제품군 내 선택지 제한)
- Gemini: "타임아웃 악순환" 원점 제거 (레이턴시 안정적)

#### 성능 개선 수치

```
EXP-002 (nemotron 기준) vs EXP-003 (Gemini 기준)

거부 정확도:   100% → 100% (동일)
단정 위반:     1/24 → 0/24 (개선)
p95 레이턴시:  44.7s → 10.4s (77% 단축) ✅
게이트 통과:   FAIL → PASS (결정적)
```

#### 교훈

"모델이 느리면 프롬프트나 인프라로 보완할 수 없다. 빠른 모델을 우선으로 찾는다." (원칙)

---

### Issue 2: 빈 응답 결함 (Truncated Response)

**프로젝트:** InsuQ
**발생 시기:** EXP-001 (2026-07-20)
**영향도:** 높음 (측정 신뢰도 훼손)

#### 증상

Reasoning 모델(qwen3-next) 호출 시:
```json
{
  "finish_reason": "length",        // ← 문제!
  "content": "",                    // ← 빈 응답
  "reasoning_content": "[생각...]"
}
```

**결과:** 빈 답변이 "거부하지 않은 답변"으로 집계됨 → 평가 지표 오염

#### 원인 분석

- `max_tokens=1024`가 모두 추론(`reasoning_content`)에 소진됨
- `finish_reason=length` 감지 불가능
- 클라이언트가 `content` 필드만 확인 → 빈 문자열을 통과

**결과:** 
```
기존 평가: 정상 답변 카테고리에 포함 (오염)
실제: 모델이 불완전한 응답을 생성
```

#### 해결

**1단계: TruncatedResponseError 신설**
```python
class TruncatedResponseError(Exception):
    """finish_reason=length 감지 시 발생"""
    pass
```

**2단계: max_tokens 상향 조정**
- 기존: `max_tokens=1024`
- 변경: `max_tokens=3000`
- 근거: 평가 문항 50개 기준으로 p75 ~2.8k

**3단계: 회귀 테스트 추가**
```python
def test_empty_response_is_not_silently_counted():
    # finish_reason=length 시 TruncatedResponseError 발생 확인
    assert mock_response.finish_reason == "length"
    with pytest.raises(TruncatedResponseError):
        llm_client.generate(...)
```

#### 성능 영향

| 지표 | 변경 | 의미 |
|---|---|---|
| 측정 신뢰도 | 오염 → 정상 | 이후 baseline 신뢰 가능 |
| max_tokens | 1024 → 3000 | 메모리/속도 영향 미미 |
| 테스트 추가 | +1 회귀 테스트 | 영구적 보호 |

---

### Issue 3: 과잉 거부 및 골든셋 태깅 문제

**프로젝트:** InsuQ
**발생 시기:** EXP-040, 2026-08-14
**영향도:** 중간 (지표 정의 혼동)

#### 증상

"과잉 거부 4건" 보고 → 분석 결과 **원인이 셋으로 갈렸다**:

| 문항 | 근거 검색 | 발동 방어선 | 원인 분류 |
|---|---|---|---|
| gA-010 | ❌ 미검색 | defense_2 | **검색 실패** (정당한 거부) |
| gB-003 | ❌ 미검색 | defense_2 | **검색 실패** (정당한 거부) |
| gB-018 | ✅ 검색됨 | (없음) | **간헐적** (비결정성) |
| gB-020 | ❌ 미검색 | defense_2 | **방어선 오탐** + 검색 실패 |

#### 근본 원인

**1. false_refusal_rate의 정의 혼동**

```
false_refusal_rate = 과잉 거부
= (a) 근거 있는데 거부 (생성 오류)
+ (b) 근거 없는데 거부 (검색 실패) ← 정당한 거부인데 섞여 있음!
```

**문제:** 두 원인의 해결책이 완전히 다른데 한 숫자에 섞여 있음

**2. policy_part 문자열 매칭 실패**

코퍼스의 16.1% (356/2,214 청크)가 다음 형태:
```
"보통약관(제3장 재산손해종합보장...관련 보통약관)"
```

모델이 일반 명칭으로 인용:
```
"보통약관"
```

→ 문자열 불일치 → 환각으로 오판정

#### 해결

**1단계: 지표 분리 (TASK-B08)**
```python
def false_refusal_breakdown():
    """gold_article 검색 여부로 분리"""
    if gold_article in retrieved_chunks:
        return "generation_side_overrefusal"  # 진짜 오거부
    else:
        return "search_failure"  # 검색 실패 (정당)
```

**2단계: policy_part 검증 강화 (TASK-B07)**

선택지:
- **A**: 괄호 떼기 → 다중 조항 오매칭 위험
- **B (권장)**: 검증 실패 → 거부 아니라 "판단 유보"로 강등
- **C**: 프롬프트 정확성 유도 → 의존성 높음

**B 선택 근거:** 프로젝트 원칙 "틀리게 답하느니 모른다고 답한다"

#### 성능 영향

| 지표 | 변경 |
|---|---|
| false_refusal_rate 해석 | 단순 과잉 거부 → 원인별 분류 |
| 골든셋 신뢰도 | 향상 (원인 파악) |
| 차기 개선 방향 | 명확화 (검색 vs 생성) |

---

### Issue 4: 캘리브레이션 게이트 모델 미기록

**프로젝트:** InsuQ
**발생 시기:** EXP-008, 2026-08-07
**영향도:** 높음 (순환 평가 위험)
**상태:** 미수정 (TASK-202i 백로그)

#### 증상

평가 리포트가 다음을 기록하지 않음:
- `generation.llm_model` (어떤 생성 모델 사용?)
- `judge.llm_model` (어떤 평가 모델 사용?)

**문제:**
```
config에서: generation.llm_model='gemini-2.0-flash' 로 변경
게이트 검사: "agreement_rate >= threshold" 수치만 확인
결과: 모델이 바뀌어도 게이트가 통과함 ← 순환 평가!
```

사람이 **특정 모델의 특정 답변**에 라벨을 매겼는데, 모델이 바뀌면 라벨의 근거가 사라진다.

#### 근본 원인

**패턴: "config 값은 있는데 읽히는 경로가 없다"**

이 스프린트 3번 발생:

| 사례 | config 필드 | 쓰인 곳 | 결과 |
|---|---|---|---|
| EXP-015 | `refusal_accuracy` | 계산 로직에 읽히지 않음 | 죽은 지표 |
| EXP-017 | `calibration_report` 경로 | 게이트가 읽지 않음 | 캘리브레이션 가정 무시 |
| **이번** | `generation.llm_model` | 리포트·게이트에 기록 안 됨 | 모델 교체 무시 |

#### 해결 (구현 대기)

**1단계: 리포트 저장 시 모델 정보 추가**
```python
calib_report = {
    "generation": {
        "llm_model": config['generation']['llm_model'],
        ...
    },
    "judge": {
        "llm_model": config['judge']['llm_model'],
        ...
    },
    "adopted": ...,
    "agreement_rate": ...
}
```

**2단계: 게이트 검사 로직 강화**
```python
if calib_report['adopted']:
    if config['generation']['llm_model'] != \
       calib_report['generation']['llm_model']:
        raise ValueError(
            f"Model mismatch: calibration used "
            f"{calib_report['generation']['llm_model']}"
        )
```

#### 교훈

**"config 키 추가는 코드 한 줄에만 끝나지 않는다"**

체크리스트:
- [ ] 설정 로드 (config.yaml)
- [ ] 사용 (알고리즘)
- [ ] 결과 기록 (리포트)
- [ ] 게이트 검증 (배포 전)

---

### Issue 5: 에이전트 도구 출력 미반영

**프로젝트:** FinAllQ
**발생 시기:** 2026-08-06 (Sprint 6b)
**영향도:** 높음 (사용자 데이터 미노출)

#### 증상

사용자 질의: "내 최근 이상거래 경보와 세금 영향 알려줘"

| 기대 | 실제 |
|---|---|
| 경보 데이터(개수, 심각도) + 세금액 | "조회를 완료했습니다" × 2 (데이터 0건) |

도구는 실행됨 (OK 21ms, 10ms) 하지만 결과가 답변에 미반영

#### 원인 분석

**명세 공백:** "도구 실행 결과를 답변에 반영하는 경로"가 명세에 없음

역추적 결과:
1. `synthesizer.py:34-37`: `output` 매개변수 미참조 (정적 문구만)
2. `graph_runner.py:84-92`: citations에 런타임 값 0건 (정적 메타데이터만)

**부수 발견:** 주석이 "프론트가 데이터를 근거 패널로 노출한다"고 했으나 실제는 0건

#### 해결

**1단계: 화이트리스트 기본 거부 (보안)**
```python
TOOL_OBSERVATIONS_WHITELIST = {
    "alerts": {"fields": ["alert_id", "severity", "description", "timestamp"]},
    "tax": {"fields": ["tax_amount", "refund_amount", "due_date"]},
}

def _extract_safe_output(tool_name: str, output: dict) -> dict:
    if tool_name not in TOOL_OBSERVATIONS_WHITELIST:
        return {}  # 기본 거부
    whitelist = TOOL_OBSERVATIONS_WHITELIST[tool_name]["fields"]
    return {k: v for k, v in output.items() if k in whitelist}
```

**2단계: synthesizer가 실제 데이터 참조**
```python
# 수정 전
answer = f"- {tool_name}: 조회를 완료했습니다."

# 수정 후
safe_output = _extract_safe_output(tool_name, observation.get("output", {}))
if safe_output:
    answer = f"- {tool_name}: {safe_output}를 조회했습니다."
```

#### 성능 영향

| 항목 | 변경 |
|---|---|
| 민감정보 노출 경로 | 0건 (화이트리스트) |
| 사용자 데이터 표시 | 미노출 → 정상 표시 |
| 테스트 커버리지 | +2 (input validation) |

---

### Issue 6: 증분 인덱싱 검증 로직이 정상 완료를 항상 실패로 오탐

**프로젝트:** InsuQ
**발생 시기:** 2026-08-24
**영향도:** 높음 (정상 인덱싱 작업이 매번 실패로 보고됨)

#### 증상

`recreate: false`로 기존 Qdrant 컬렉션에 새 청크를 이어서 넣는 증분 인덱싱을 실행하면, 인덱싱 자체는
정상 완료되는데도 검증 단계(`_verify_roundtrip`)가 매번 실패로 보고했다.

#### 근본 원인

검증 로직이 "이번에 넣은 청크 집합"과 "컬렉션 전체"를 **완전일치**로 비교하고 있었다. 증분 인덱싱은
기존에 있던 포인트 위에 새 포인트를 더하는 것이므로, 컬렉션 전체는 이번 배치보다 항상 크다 —
완전일치 비교는 구조적으로 통과할 수 없는 조건이었다.

#### 해결

비교 방식을 완전일치에서 **부분집합 비교**(이번에 넣은 청크가 컬렉션에 전부 포함되는지)로 변경.

#### 발견 경위

트랙4(화재보험)에 신규 상품 4종(주택화재보험·성공예감·비즈앤안전파트너·아파트안심보험)을 기존
컬렉션(동산종합·비지니스패키지·수퍼비즈니스, 2,214포인트)에 증분 인덱싱하는 과정에서 발견됐다.
수정 후 Qdrant Cloud `insuq_track4` 컬렉션은 2,214 → 6,505 포인트로 정상 반영됐다(무료 티어 유지).

#### 교훈

"검증 로직 자체가 늘어난 요구사항(증분 인덱싱)을 따라가지 못하면, 정상 동작이 실패로 보이고
그게 더 위험하다" — 인덱싱이 실제로 깨졌을 때와 구분이 안 되기 때문이다.

---

## 🟡 Known Issues & Workarounds

### InsuQ: 거부 비결정성 (조사 중)

**현상:**
```
temperature: 0 인데도
같은 질의에서 다른 거부 여부/근거 반환
```

**의심 원인:**
- 검색 노이즈 (무관 조항이 top-5에 섞임)
- 도구 루프 비결정성 (매 턴 도구 호출 여부 재결정)

**임시 방안:** 
- 도구 루프 로그 기록
- 동일 질의 10회 반복 테스트로 비결정성 발생률 측정

**근본 해결:**
- 하이브리드 검색 + 리랭커 (현재 기각된 상태)
- 또는 검색 상위 K 조정

---

### FinAllQ: 부분 응답 캐시 오염

**현상:**
노드 DOWN → 부분 응답 → 캐시 저장(TTL 300s) → 노드 복구 후도 캐시 반환

**해결:** 
부분 응답(`partial=True`)은 캐시하지 않도록 설정

---

## 📊 성능 개선 요약표

| 이슈 | 프로젝트 | 영향 | 해결 | 상태 |
|---|---|---|---|---|
| LLM 타임아웃 악순환 | InsuQ | p95 44.7s → 10.4s | 모델 교체 | ✅ 완료 |
| 빈 응답 결함 | InsuQ | 측정 오염 | TruncatedResponseError | ✅ 완료 |
| 과잉 거부 태깅 | InsuQ | 지표 혼동 | 원인 분리 | ✅ 완료 |
| 캘리브레이션 미기록 | InsuQ | 순환 평가 위험 | 모델 필드 추가 | ⏳ TASK-202i |
| 도구 결과 미반영 | FinAllQ | 데이터 미노출 | 화이트리스트 + 실제 데이터 반영 | ✅ 완료 |
| 증분 인덱싱 검증 오탐 | InsuQ | 정상 인덱싱이 실패로 오탐 | 완전일치 → 부분집합 비교 | ✅ 완료 (2026-08-24) |

---

## 🎓 설계 원칙 정리

### 절대 원칙 (이 프로젝트가 준수하는)

1. **"측정이 없으면 개선도 없다"** — 모든 변경은 전/후 지표로 검증
2. **"빈 응답은 버그다"** — 타임아웃·truncation 감지 자동화
3. **"빈 데이터는 노출하지 않는다"** — 화이트리스트 기본 거부
4. **"모델이 느리면 프롬프트로 보완할 수 없다"** — 빠른 모델 우선
5. **"config 추가는 3곳을 함께 수정한다"** — 로드·사용·기록·검증

---

## 📌 다음 단계

### 즉시 (1주)
- [ ] TASK-202i: 캘리브레이션 리포트 모델 필드 추가
- [ ] InsuQ: 도구 루프 비결정성 조사 (TASK-B09)

### 단기 (2주)
- [ ] false_refusal_rate 원인 분리 (TASK-B08)
- [ ] policy_part 검증 강화 (TASK-B07)

### 중기 (4주)
- [ ] 하이브리드 검색 + 리랭커 재평가 (또는 기각 확정)
- [ ] Part 2 골든셋 사람 검수 완료

---

**작성:** 개발팀 | **마지막 업데이트:** 2026-08-23 (InsuQ Issue 6 — 2026-08-24 추가)
