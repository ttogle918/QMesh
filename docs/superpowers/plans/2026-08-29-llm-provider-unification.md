# LLM 제공자 통일 + 자동 폴백 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** InsuQ·MaintQ의 서빙 LLM을 NVIDIA NIM 무료 티어 `openai/gpt-oss-120b`로 통일하고, 그 경로가 죽으면 OpenAI `gpt-4.1-mini`로 자동 폴백해 포트폴리오 사이트가 조용히 죽지 않게 한다.

**Architecture:** 두 레포 모두 **기존 클라이언트를 감싸는 래퍼**로 폴백을 넣는다 — 호출부는 한 줄도 바뀌지 않는다(InsuQ `llm.py`의 모듈 원칙). 실패 유형별 재시도 정책은 클라이언트 **안쪽**에서(401을 3번 재시도하지 않도록), 폴백 전환은 래퍼 **바깥쪽**에서 처리한다. 스트리밍 경로는 첫 델타가 나간 뒤에는 폴백하지 않는다.

**Tech Stack:** Python 3.13 · `openai` SDK(OpenAI 호환 규격) · pytest. InsuQ는 동기 클라이언트(`OpenAICompatClient`), MaintQ는 비동기 스트리밍 클라이언트(`AsyncOpenAI`)로 **구조가 다르다** — 코드를 공유하지 않고 각 레포 관례를 따른다.

## Global Constraints

- **설계 문서(SSOT):** `A2A_Q/docs/superpowers/specs/2026-08-29-llm-provider-unification-design.md`
- **기본 모델은 `openai/gpt-oss-120b`, 폴백 모델은 `gpt-4.1-mini`** — 두 레포 동일. 이 문자열을 그대로 쓴다.
- **NVIDIA base_url은 `https://integrate.api.nvidia.com/v1`이다.** MaintQ `EliceClient`는 `/v1`이 없으면 붙이므로 MaintQ에는 `https://integrate.api.nvidia.com`을 넣는다(`llm.py:422-424`).
- **외부 API 실호출 0건.** 모든 테스트는 대역(fake)으로 검증한다. 기존 관례다(InsuQ 932 passed, MaintQ 1,052 passed 모두 네트워크를 안 탄다).
- **API 키는 코드·로그·리포트 어디에도 남기지 않는다** (InsuQ `llm.py` 모듈 docstring, MaintQ D40). 로그에는 **예외 타입 이름만** 남긴다.
- **폴백 미설정 = 기존 동작.** 폴백 환경변수가 비어 있으면 래퍼를 씌우지 않는다. 이미 배포된 환경이 이 변경으로 깨지면 안 된다.
- **평가 judge는 폴백하지 않는다.** 실행 중간 전환은 앞뒤가 다른 모델로 채점된 리포트를 만든다 — 겉보기엔 정상이라 더 위험하다.
- **`.env`는 커밋하지 않는다.** `.env.example`만 커밋한다.
- **🔴 `elice` provider 항목을 지우지 않는다** — D115 자산 유지 결정.

## File Structure

| 파일 | 레포 | 책임 | 변경 |
|---|---|---|---|
| `ai-engine/insuq_ai/generation/llm.py` | InsuQ | 실패 분류 · 재시도 · `FallbackLLMClient` · 빌더 | Modify |
| `ai-engine/tests/generation/test_llm_fallback.py` | InsuQ | 폴백 단위 테스트 | Create |
| `ai-engine/insuq_ai/api/main.py` | InsuQ | 서빙 전용 env 오버라이드(L108-138) | Modify |
| `ai-engine/tests/api/test_generation_override.py` | InsuQ | 오버라이드 테스트 | Modify |
| `ai-engine/.env.example` · `docs/08_DEPLOYMENT.md` | InsuQ | 설정 문서 | Modify |
| `backend/agent/llm.py` | MaintQ | `PROVIDERS` · `get_client()` · `FallbackClient` | Modify |
| `backend/agent/test_llm_fallback.py` | MaintQ | 폴백 단위 테스트 | Create |
| `.env.example` | MaintQ | 설정 문서 | Modify |

**두 레포는 서로의 코드를 임포트하지 않는다.** 공용 라이브러리를 만들지 않는다 — 클라이언트 인터페이스가 동기/비동기로 근본적으로 다르고, 지금 두 곳뿐인 코드를 공유 패키지로 묶으면 배포 의존성이 늘기만 한다(YAGNI).

---

### Task 1: InsuQ — 실패 분류 + 재시도 정책 교정

**왜 먼저인가:** 지금 `complete_turn()`의 `except`는 `(RateLimitError, APITimeoutError, APIError)`를 한 덩어리로 잡아 **401도 3번 지수 백오프한다**(`llm.py:292`). 키가 틀린 것은 2초 뒤에 맞아지지 않는다. 이건 폴백과 무관하게 그 자체로 낭비이고, 폴백을 얹기 전에 고쳐야 폴백 진입 시점이 정의된다.

**Files:**
- Modify: `C:\Users\ttogl\workspace\InsuQ\ai-engine\insuq_ai\generation\llm.py`
- Create: `C:\Users\ttogl\workspace\InsuQ\ai-engine\tests\generation\test_llm_fallback.py`

**Interfaces:**
- Consumes: 없음 (첫 작업)
- Produces:
  - `IMMEDIATE_FALLBACK = "immediate"` · `SHORT_RETRY = "short_retry"` · `FULL_RETRY = "full_retry"` (모듈 상수, `str`)
  - `classify_failure(exc: Exception) -> str` — 위 세 값 중 하나를 반환
  - `retry_budget(kind: str, max_retries: int) -> int` — 해당 분류에서 허용할 **총 시도 횟수**
  - Task 2가 `classify_failure`를 임포트한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`ai-engine/tests/generation/test_llm_fallback.py` 를 새로 만든다.

```python
"""제공자 실패 분류 · 재시도 예산 · 자동 폴백 (2026-08-29 LLM 제공자 통일).

**네트워크를 타지 않는다.** openai SDK 예외를 흉내 낸 대역만 쓴다.

배경: 기존 `complete_turn()` 은 401(AuthenticationError)도 3회 지수 백오프했다.
키가 틀린 것은 2초 뒤에 맞아지지 않는다 — 분류해서 즉시 포기시킨다.
"""

from __future__ import annotations

import pytest

from insuq_ai.generation import llm


class FakeStatusError(Exception):
    """openai SDK 의 APIStatusError 를 흉내 낸다 — status_code 속성만 있으면 된다."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


@pytest.mark.parametrize("status", [401, 403, 404])
def test_auth_and_missing_model_are_immediate(status):
    """인증 실패·모델 없음은 재시도해도 달라지지 않는다 — 즉시 폴백."""
    assert llm.classify_failure(FakeStatusError(status)) == llm.IMMEDIATE_FALLBACK


@pytest.mark.parametrize("status", [402, 429])
def test_credit_and_rate_limit_get_one_retry(status):
    """크레딧 소진·rate limit 은 짧게 한 번만 더 본다."""
    assert llm.classify_failure(FakeStatusError(status)) == llm.SHORT_RETRY


@pytest.mark.parametrize("status", [500, 502, 503])
def test_server_errors_use_full_retry(status):
    """일시 장애는 기존 재시도 정책을 그대로 쓴다."""
    assert llm.classify_failure(FakeStatusError(status)) == llm.FULL_RETRY


def test_unclassified_error_defaults_to_full_retry():
    """status_code 가 없는 예외(연결 실패·타임아웃 등)의 기본은 5xx 경로다.

    '즉시 폴백'을 기본으로 두면 일시 장애에도 유료 경로로 새고, '폴백 안 함'을
    기본으로 두면 죽는다. 재시도 후 폴백이 두 실패를 모두 피한다.
    """
    assert llm.classify_failure(RuntimeError("boom")) == llm.FULL_RETRY


def test_retry_budget_immediate_is_single_attempt():
    """즉시 폴백은 '시도 1회' — 재시도 0회다."""
    assert llm.retry_budget(llm.IMMEDIATE_FALLBACK, max_retries=3) == 1


def test_retry_budget_short_retry_is_two_attempts():
    assert llm.retry_budget(llm.SHORT_RETRY, max_retries=3) == 2


def test_retry_budget_full_retry_uses_configured_max():
    assert llm.retry_budget(llm.FULL_RETRY, max_retries=3) == 3


def test_retry_budget_never_exceeds_configured_max():
    """max_retries=1 로 설정된 환경에서 short_retry 가 그걸 넘기면 안 된다."""
    assert llm.retry_budget(llm.SHORT_RETRY, max_retries=1) == 1
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/InsuQ/ai-engine && python -m pytest tests/generation/test_llm_fallback.py -v`

Expected: FAIL — `AttributeError: module 'insuq_ai.generation.llm' has no attribute 'classify_failure'` (수집 단계에서 전부 실패).

- [ ] **Step 3: 분류 함수와 재시도 예산을 구현한다**

`llm.py` 의 `LENGTH_FINISH_REASON = "length"` 정의 **바로 아래**에 추가한다.

```python
# 폴백 판단용 실패 분류 (2026-08-29). 재시도로 나아지는 실패와 그렇지 않은 실패를
# 가른다 — 401 을 3번 지수 백오프하는 것은 순수 낭비다(키가 2초 뒤에 맞아지지 않는다).
IMMEDIATE_FALLBACK = "immediate"
SHORT_RETRY = "short_retry"
FULL_RETRY = "full_retry"

# 인증·권한·모델 부재 — 같은 요청을 다시 보내도 같은 답이 온다.
# 404 를 여기 넣는 근거는 실측이다: NVIDIA `/v1/models` 목록에 있는 모델이 실제
# 호출에서 404 를 뱉는 경우를 5개 중 3개에서 봤다(2026-08-29 프로브).
# **모델 목록은 호출 가능성을 보장하지 않는다.**
_IMMEDIATE_STATUSES = frozenset({401, 403, 404})

# 크레딧 소진(402)·rate limit(429) — 짧게 한 번만 더 본다.
_SHORT_RETRY_STATUSES = frozenset({402, 429})


def classify_failure(exc: Exception) -> str:
    """제공자 호출 실패를 재시도 전략으로 분류한다.

    `status_code` 가 없는 예외(연결 실패·타임아웃·SDK 내부 오류)는 `FULL_RETRY` 다.
    크레딧 소진이 어떤 상태 코드로 오는지 문서로 확정하지 못했기 때문에, 모르는
    실패의 기본값이 중요하다 — 즉시 폴백이면 일시 장애에 유료 경로로 새고,
    폴백 안 함이면 죽는다. 재시도 후 폴백이 두 실패를 모두 피한다.
    """
    status = getattr(exc, "status_code", None)
    if status in _IMMEDIATE_STATUSES:
        return IMMEDIATE_FALLBACK
    if status in _SHORT_RETRY_STATUSES:
        return SHORT_RETRY
    return FULL_RETRY


def retry_budget(kind: str, max_retries: int) -> int:
    """분류별로 허용할 **총 시도 횟수**(재시도 횟수가 아니라 시도 횟수).

    설정된 `max_retries` 를 절대 넘지 않는다 — 운영자가 1회로 낮춰 두었으면
    분류가 무엇이든 1회다.
    """
    if kind == IMMEDIATE_FALLBACK:
        return 1
    if kind == SHORT_RETRY:
        return min(2, max_retries)
    return max_retries
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/InsuQ/ai-engine && python -m pytest tests/generation/test_llm_fallback.py -v`

Expected: PASS — 12 passed.

- [ ] **Step 5: `complete_turn()` 재시도 루프에 분류를 물린다**

`llm.py` `complete_turn()` 의 `except` 블록(현재 `llm.py:292` 부근)을 아래로 교체한다. `for attempt in range(self._max_retries):` 는 그대로 두고, **예산을 초과하면 break** 하는 방식으로 최소 변경한다.

```python
            except (RateLimitError, APITimeoutError, APIError) as exc:
                last_error = exc
                # 2026-08-29 — 실패 유형별 예산. 401/403/404 는 재시도해도 같은 답이
                # 오므로 첫 시도에서 포기하고 폴백(FallbackLLMClient)에 넘긴다.
                budget = retry_budget(classify_failure(exc), self._max_retries)
                if attempt >= budget - 1:
                    break
                sleep_s = BACKOFF_BASE_S**attempt
                # 예외 타입만 남긴다 — 응답 본문에 키가 섞여 들어갈 수 있다
                logger.warning(
                    "LLM 호출 실패 (%s), %.1fs 후 재시도 %d/%d",
                    type(exc).__name__,
                    sleep_s,
                    attempt + 1,
                    budget,
                )
                time.sleep(sleep_s)
```

- [ ] **Step 6: 재시도 횟수 회귀 테스트를 추가한다**

`test_llm_fallback.py` 끝에 추가한다.

```python
class CountingCompletions:
    """chat.completions.create 호출 횟수를 세면서 지정한 예외를 던지는 대역."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        raise self._exc


def _client_with(monkeypatch, exc: Exception, max_retries: int = 3):
    """OpenAICompatClient 를 실제 네트워크 없이 세운다."""
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
    config = {
        "generation": {
            "llm_model": "openai/gpt-oss-120b",
            "max_tokens": 512,
            "max_retries": max_retries,
        }
    }
    client = llm.OpenAICompatClient(config, llm.resolve_provider("nvidia"))
    counting = CountingCompletions(exc)

    class _Chat:
        completions = counting

    monkeypatch.setattr(client, "_client", type("_C", (), {"chat": _Chat})())
    monkeypatch.setattr(llm.time, "sleep", lambda _s: None)  # 테스트를 잠재우지 않는다
    return client, counting


def test_401_is_attempted_exactly_once(monkeypatch):
    """인증 실패에 3번 백오프하지 않는다 — 시도 1회로 끝난다."""
    client, counting = _client_with(monkeypatch, FakeStatusError(401))
    with pytest.raises(RuntimeError):
        client.complete_turn([{"role": "user", "content": "안녕"}])
    assert counting.calls == 1


def test_429_is_attempted_twice(monkeypatch):
    client, counting = _client_with(monkeypatch, FakeStatusError(429))
    with pytest.raises(RuntimeError):
        client.complete_turn([{"role": "user", "content": "안녕"}])
    assert counting.calls == 2


def test_500_uses_full_retry_budget(monkeypatch):
    """일시 장애는 기존 동작 그대로 3회 — 회귀 방지."""
    client, counting = _client_with(monkeypatch, FakeStatusError(500))
    with pytest.raises(RuntimeError):
        client.complete_turn([{"role": "user", "content": "안녕"}])
    assert counting.calls == 3
```

**주의:** `FakeStatusError`는 `openai` SDK 예외 계층에 속하지 않아 `except (RateLimitError, APITimeoutError, APIError)`에 잡히지 않는다. 테스트가 이 이유로 실패하면 `FakeStatusError`를 `openai.APIError`를 상속하도록 바꾼다 — SDK의 `APIError.__init__(message, request, body=...)` 시그니처를 `tests/generation/test_llm.py`의 기존 대역에서 확인하고 같은 방식으로 맞춘다.

- [ ] **Step 7: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/InsuQ/ai-engine && python -m pytest tests/generation/ -v`

Expected: PASS — 신규 15건 + 기존 `test_llm.py`·`test_llm_tools.py`·`test_llm_provider_url.py` 전부 통과.

- [ ] **Step 8: 커밋**

```bash
cd /c/Users/ttogl/workspace/InsuQ
git status --short   # 다른 세션 작업물과 섞이지 않는지 먼저 확인
git add ai-engine/insuq_ai/generation/llm.py ai-engine/tests/generation/test_llm_fallback.py
git commit -m "fix(llm): 실패 유형별 재시도 예산 — 401 을 3회 백오프하지 않는다

401/403/404 는 재시도해도 같은 답이 오므로 첫 시도에서 포기한다.
402/429 는 2회, 그 외(5xx·타임아웃·미분류)는 기존 max_retries 그대로.

404 를 즉시 포기 대상에 넣은 근거는 실측이다 — NVIDIA /v1/models 목록에
있는 모델이 실호출에서 404 를 뱉는 경우를 5개 중 3개에서 봤다."
```

---

### Task 2: InsuQ — `FallbackLLMClient`

**Files:**
- Modify: `C:\Users\ttogl\workspace\InsuQ\ai-engine\insuq_ai\generation\llm.py`
- Modify: `C:\Users\ttogl\workspace\InsuQ\ai-engine\tests\generation\test_llm_fallback.py`

**Interfaces:**
- Consumes: Task 1의 `classify_failure`(간접 — 내부 클라이언트가 이미 쓴다)
- Produces:
  - `LLMTurn.provider_used: str | None = None` (필드 추가, 기본값 있음)
  - `class FallbackLLMClient` — `__init__(self, primary: LLMClient, fallback: LLMClient, *, primary_name: str, fallback_name: str)`. `complete()` · `complete_turn()` · `stream_turn()` 세 메서드를 `LLMClient` Protocol대로 구현한다.
  - Task 3이 `FallbackLLMClient`를 임포트한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`test_llm_fallback.py` 끝에 추가한다.

```python
class RecordingClient:
    """LLMClient 대역 — 정해진 응답을 주거나 정해진 예외를 던진다."""

    def __init__(self, *, turn: llm.LLMTurn | None = None, exc: Exception | None = None,
                 deltas: list[str] | None = None, raise_after: int | None = None) -> None:
        self._turn = turn
        self._exc = exc
        self._deltas = deltas or []
        self._raise_after = raise_after
        self.turn_calls = 0
        self.stream_calls = 0

    def complete(self, system: str, user: str) -> str:
        turn = self.complete_turn(
            [{"role": "system", "content": system}, {"role": "user", "content": user}]
        )
        return turn.content or ""

    def complete_turn(self, messages, tools=None) -> llm.LLMTurn:
        self.turn_calls += 1
        if self._exc is not None:
            raise self._exc
        return self._turn

    def stream_turn(self, messages, tools=None):
        self.stream_calls += 1
        for i, d in enumerate(self._deltas):
            if self._raise_after is not None and i == self._raise_after:
                raise self._exc or RuntimeError("stream broke")
            yield d
        if self._exc is not None and self._raise_after is None:
            raise self._exc


def _turn(text: str) -> llm.LLMTurn:
    return llm.LLMTurn(content=text, tool_calls=[], finish_reason="stop")


def test_fallback_is_not_used_when_primary_succeeds():
    primary = RecordingClient(turn=_turn("일차 응답"))
    secondary = RecordingClient(turn=_turn("폴백 응답"))
    client = llm.FallbackLLMClient(primary, secondary,
                                   primary_name="nvidia", fallback_name="openai")

    turn = client.complete_turn([{"role": "user", "content": "안녕"}])

    assert turn.content == "일차 응답"
    assert turn.provider_used == "nvidia"
    assert secondary.turn_calls == 0


def test_fallback_takes_over_when_primary_fails():
    primary = RecordingClient(exc=FakeStatusError(401))
    secondary = RecordingClient(turn=_turn("폴백 응답"))
    client = llm.FallbackLLMClient(primary, secondary,
                                   primary_name="nvidia", fallback_name="openai")

    turn = client.complete_turn([{"role": "user", "content": "안녕"}])

    assert turn.content == "폴백 응답"
    assert turn.provider_used == "openai"
    assert primary.turn_calls == 1


def test_error_propagates_when_both_fail():
    """폴백까지 실패하면 조용히 빈 응답을 내지 않는다."""
    primary = RecordingClient(exc=FakeStatusError(401))
    secondary = RecordingClient(exc=FakeStatusError(500))
    client = llm.FallbackLLMClient(primary, secondary,
                                   primary_name="nvidia", fallback_name="openai")

    with pytest.raises(Exception):
        client.complete_turn([{"role": "user", "content": "안녕"}])


def test_fallback_logs_warning_without_api_key(caplog):
    """전환은 조용히 일어나면 안 되고, 로그에 키가 섞이면 안 된다."""
    primary = RecordingClient(exc=FakeStatusError(401))
    secondary = RecordingClient(turn=_turn("폴백 응답"))
    client = llm.FallbackLLMClient(primary, secondary,
                                   primary_name="nvidia", fallback_name="openai")

    with caplog.at_level("WARNING"):
        client.complete_turn([{"role": "user", "content": "안녕"}])

    text = caplog.text
    assert "nvidia" in text and "openai" in text
    assert "FakeStatusError" in text          # 예외 타입은 남긴다
    assert "test-key-not-real" not in text    # 키는 절대 안 남긴다


def test_stream_falls_back_before_first_delta():
    primary = RecordingClient(exc=FakeStatusError(429), deltas=[], raise_after=None)
    secondary = RecordingClient(deltas=["폴", "백"])
    client = llm.FallbackLLMClient(primary, secondary,
                                   primary_name="nvidia", fallback_name="openai")

    assert list(client.stream_turn([{"role": "user", "content": "안녕"}])) == ["폴", "백"]


def test_stream_does_not_fall_back_after_first_delta():
    """이미 화면에 토큰이 나간 뒤 다른 모델로 다시 쓰면 중복·모순 출력이 된다.

    `stream_turn()` 의 기존 재시도 경계와 같은 규칙이다 (TASK-108).
    """
    primary = RecordingClient(deltas=["일", "차"], raise_after=1, exc=FakeStatusError(500))
    secondary = RecordingClient(deltas=["폴", "백"])
    client = llm.FallbackLLMClient(primary, secondary,
                                   primary_name="nvidia", fallback_name="openai")

    out = []
    with pytest.raises(Exception):
        for delta in client.stream_turn([{"role": "user", "content": "안녕"}]):
            out.append(delta)

    assert out == ["일"]            # 끊긴 지점까지만 나갔다
    assert secondary.stream_calls == 0  # 폴백은 호출되지 않았다
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/InsuQ/ai-engine && python -m pytest tests/generation/test_llm_fallback.py -v -k fallback_is_not_used`

Expected: FAIL — `AttributeError: module 'insuq_ai.generation.llm' has no attribute 'FallbackLLMClient'`.

- [ ] **Step 3: `LLMTurn` 에 `provider_used` 를 추가한다**

`llm.py` 의 `LLMTurn` 정의(현재 `llm.py:133-140`)를 아래로 교체한다.

```python
@dataclass(frozen=True)
class LLMTurn:
    """`complete_turn()` 의 반환값 — 도구 호출 여부와 무관하게 항상 이 형태다."""

    content: str | None
    tool_calls: list[ToolCall]
    finish_reason: str
    #: 실제로 응답한 제공자 이름. `FallbackLLMClient` 를 거칠 때만 채워진다 —
    #: 단일 클라이언트는 자기 이름을 모르며, 그걸 알게 하려고 생성자 시그니처를
    #: 바꾸면 기존 호출부·테스트가 전부 흔들린다. 기본값 None 이라 하위 호환이다.
    provider_used: str | None = None
```

- [ ] **Step 4: `FallbackLLMClient` 를 구현한다**

`llm.py` 의 `def build_llm_client(` **바로 위**에 추가한다.

```python
class FallbackLLMClient:
    """primary 가 실패하면 fallback 으로 넘기는 `LLMClient` 래퍼 (2026-08-29).

    **호출부는 바뀌지 않는다** — 이 모듈의 원칙(제공자 교체는 config 한 줄)을
    지키기 위해 `complete_turn()` 본문을 고치는 대신 Protocol 구현체를 하나 더 둔다.

    재시도는 안쪽 클라이언트가 이미 실패 유형별 예산으로 처리한다(`retry_budget`).
    여기서는 "안쪽이 끝내 실패했는가"만 보고 제공자를 갈아탄다 — 재시도와 폴백을
    한 곳에 섞으면 401 에 백오프하면서 동시에 유료 경로로 새는 조합이 나온다.

    **스트리밍은 첫 델타 전까지만 폴백한다.** 이미 호출자에게 토큰이 나간 뒤에
    다른 모델로 다시 쓰면 화면에 중복·모순 출력이 생긴다 (TASK-108 재시도 경계와 동일).
    """

    def __init__(
        self,
        primary: LLMClient,
        fallback: LLMClient,
        *,
        primary_name: str,
        fallback_name: str,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_name = primary_name
        self._fallback_name = fallback_name

    def _warn(self, exc: Exception) -> None:
        # 예외 타입만 남긴다 — 응답 본문에 키가 섞여 들어갈 수 있다.
        logger.warning(
            "LLM 제공자 폴백: %s → %s (원인 %s). 유료 경로로 전환됐다.",
            self._primary_name,
            self._fallback_name,
            type(exc).__name__,
        )

    def complete(self, system: str, user: str) -> str:
        turn = self.complete_turn(
            [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            tools=None,
        )
        if turn.content is None:
            raise TruncatedResponseError(
                f"본문이 비어 있다 (finish_reason={turn.finish_reason})."
            )
        return turn.content

    def complete_turn(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LLMTurn:
        try:
            turn = self._primary.complete_turn(messages, tools)
            return replace(turn, provider_used=self._primary_name)
        except Exception as exc:  # noqa: BLE001 — 어떤 실패든 폴백 대상이다
            self._warn(exc)
        turn = self._fallback.complete_turn(messages, tools)
        return replace(turn, provider_used=self._fallback_name)

    def stream_turn(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> Iterator[str]:
        yielded = False
        try:
            for delta in self._primary.stream_turn(messages, tools):
                yielded = True
                yield delta
            return
        except Exception as exc:  # noqa: BLE001
            if yielded:
                # 이미 나간 토큰이 있다 — 다시 쓰지 않고 그대로 전파한다.
                raise
            self._warn(exc)
        yield from self._fallback.stream_turn(messages, tools)
```

`llm.py` 상단 임포트에 `replace` 를 추가한다.

```python
from dataclasses import dataclass, replace
```

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/InsuQ/ai-engine && python -m pytest tests/generation/ -v`

Expected: PASS — 신규 21건 포함 전부 통과.

- [ ] **Step 6: 커밋**

```bash
cd /c/Users/ttogl/workspace/InsuQ
git add ai-engine/insuq_ai/generation/llm.py ai-engine/tests/generation/test_llm_fallback.py
git commit -m "feat(llm): FallbackLLMClient — 제공자 실패 시 자동 전환

LLMClient Protocol 구현체로 만들어 호출부를 한 줄도 바꾸지 않는다.
전환은 WARN 으로 남긴다(키는 남기지 않는다) — 조용한 전환은
'왜 이번 달 청구서가 있지'가 된다.

스트리밍은 첫 델타 전까지만 폴백한다. 이미 나간 토큰 뒤에 다른 모델로
다시 쓰면 중복·모순 출력이 된다(TASK-108 재시도 경계와 동일)."
```

---

### Task 3: InsuQ — 설정 배선 (서빙 전용) + 문서

**핵심:** `_apply_generation_override()` 는 **서빙 경로에만** 적용되고 `eval/run.py` 는 이 함수를 타지 않는다(`main.py:110-117` docstring). 폴백 설정을 이 함수에서만 읽으면 **평가 경로에는 폴백이 아예 존재하지 않게 되어** 설계의 "judge는 폴백하지 않는다"가 구조적으로 보장된다. `build_judge_client()` 에 특례를 넣지 않는다.

**Files:**
- Modify: `C:\Users\ttogl\workspace\InsuQ\ai-engine\insuq_ai\generation\llm.py` (`build_llm_client`)
- Modify: `C:\Users\ttogl\workspace\InsuQ\ai-engine\insuq_ai\api\main.py` (`_apply_generation_override`)
- Modify: `C:\Users\ttogl\workspace\InsuQ\ai-engine\tests\api\test_generation_override.py`
- Modify: `C:\Users\ttogl\workspace\InsuQ\ai-engine\.env.example`
- Modify: `C:\Users\ttogl\workspace\InsuQ\docs\08_DEPLOYMENT.md`

**Interfaces:**
- Consumes: Task 2의 `FallbackLLMClient`
- Produces: `config["generation"]["fallback"] = {"provider": str, "llm_model": str}` 규약. `build_llm_client()` 가 이 키가 있을 때만 `FallbackLLMClient` 를 반환한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/generation/test_llm_fallback.py` 끝에 추가한다.

```python
def _base_config(fallback: dict | None = None) -> dict:
    generation = {
        "provider": "nvidia",
        "llm_model": "openai/gpt-oss-120b",
        "max_tokens": 512,
    }
    if fallback is not None:
        generation["fallback"] = fallback
    return {"generation": generation}


def test_build_llm_client_without_fallback_returns_bare_client(monkeypatch):
    """폴백 미설정 = 기존 동작. 배포된 환경이 이 변경으로 깨지면 안 된다."""
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
    client = llm.build_llm_client(_base_config())
    assert isinstance(client, llm.OpenAICompatClient)


def test_build_llm_client_with_fallback_wraps(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    client = llm.build_llm_client(
        _base_config({"provider": "openai", "llm_model": "gpt-4.1-mini"})
    )
    assert isinstance(client, llm.FallbackLLMClient)


def test_judge_client_never_gets_fallback(monkeypatch):
    """평가 judge 는 폴백하지 않는다.

    실행 중간에 judge 가 갈리면 앞부분과 뒷부분이 서로 다른 모델로 채점된
    리포트가 나온다 — 자기 자신과도 비교 불가능한데 겉보기엔 정상이다.
    서빙은 '죽는 것보다 비싼 게 낫다', 평가는 '오염된 숫자보다 실패가 낫다'.
    """
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    config = _base_config({"provider": "openai", "llm_model": "gpt-4.1-mini"})
    config["judge"] = {"provider": "nvidia", "llm_model": "openai/gpt-oss-120b"}

    judge = llm.build_judge_client(config)

    assert not isinstance(judge, llm.FallbackLLMClient)
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/InsuQ/ai-engine && python -m pytest tests/generation/test_llm_fallback.py -v -k build_llm_client`

Expected: FAIL — `test_build_llm_client_with_fallback_wraps` 가 `OpenAICompatClient` 를 받아 실패한다.

- [ ] **Step 3: `build_llm_client()` 를 확장한다**

`llm.py` 의 `build_llm_client()` 를 아래로 교체한다. `build_judge_client()` 는 **손대지 않는다.**

```python
def build_llm_client(config: dict[str, Any]) -> LLMClient:
    """설정의 `generation.provider` 에 맞는 LLM 클라이언트를 만든다.

    `generation.fallback` 이 있으면 `FallbackLLMClient` 로 감싼다(2026-08-29).
    이 키는 서빙 경로(`_apply_generation_override`)에서만 채워진다 — `eval/run.py`
    는 그 함수를 타지 않으므로 **평가에는 폴백이 존재하지 않는다.** judge 가 실행
    중간에 갈려 리포트가 오염되는 것을 구조적으로 막는다.
    """
    generation = config["generation"]
    primary_name = generation["provider"]
    primary = OpenAICompatClient(config, resolve_provider(primary_name))

    fallback_cfg = generation.get("fallback")
    if not fallback_cfg:
        return primary

    fallback_name = fallback_cfg["provider"]
    # 폴백은 provider·모델만 다르고 나머지 생성 파라미터는 그대로 쓴다.
    fallback_config = {**config, "generation": {**generation, **fallback_cfg}}
    fallback_config["generation"].pop("fallback", None)  # 중첩 폴백 방지
    fallback = OpenAICompatClient(fallback_config, resolve_provider(fallback_name))

    return FallbackLLMClient(
        primary, fallback, primary_name=primary_name, fallback_name=fallback_name
    )
```

- [ ] **Step 4: `_apply_generation_override()` 가 폴백 환경변수를 읽게 한다**

`main.py` 의 `_apply_generation_override()` 에서 `provider = os.environ.get(...)` 로 시작하는 본문을 아래로 교체한다(docstring은 그대로 두고 마지막 문단만 덧붙인다).

```python
    provider = os.environ.get("INSUQ_LLM_PROVIDER")
    model = os.environ.get("INSUQ_LLM_MODEL")
    fb_provider = os.environ.get("INSUQ_LLM_FALLBACK_PROVIDER")
    fb_model = os.environ.get("INSUQ_LLM_FALLBACK_MODEL")
    if not provider and not model and not fb_provider and not fb_model:
        return

    generation = config.setdefault("generation", {})
    before = (generation.get("provider"), generation.get("llm_model"))
    if provider:
        generation["provider"] = provider
    if model:
        generation["llm_model"] = model

    # 폴백은 **둘 다** 있어야 켠다. 하나만 설정된 상태를 조용히 절반만 적용하면
    # "폴백이 켜진 줄 알았는데 아니었다"가 된다 — 명시적으로 무시하고 경고한다.
    if fb_provider and fb_model:
        generation["fallback"] = {"provider": fb_provider, "llm_model": fb_model}
        logger.warning(
            "생성 모델 폴백 활성화: %s/%s. 기본 경로가 실패하면 자동 전환되며 "
            "그때마다 WARNING 이 남는다.",
            fb_provider,
            fb_model,
        )
    elif fb_provider or fb_model:
        logger.warning(
            "INSUQ_LLM_FALLBACK_PROVIDER 와 INSUQ_LLM_FALLBACK_MODEL 은 함께 설정해야 "
            "한다 — 하나만 있어 폴백을 켜지 않았다."
        )

    # 조용히 바뀌면 "config 엔 A 인데 실제론 B" 가 되어 원인 추적이 길어진다 — WARNING 으로 띄운다.
    logger.warning(
        "생성 모델 오버라이드: provider/model %s → %s (환경변수 INSUQ_LLM_PROVIDER/INSUQ_LLM_MODEL). "
        "서빙 전용이며 평가 리포트에는 반영되지 않는다.",
        before,
        (generation.get("provider"), generation.get("llm_model")),
    )
```

- [ ] **Step 5: 오버라이드 테스트를 보강한다**

`tests/api/test_generation_override.py` 끝에 추가한다. 기존 테스트의 `monkeypatch.delenv` 관례를 그대로 따른다 — 파일 첫 20줄을 먼저 읽고 헬퍼 이름을 맞춘다.

```python
def test_fallback_env_pair_sets_generation_fallback(monkeypatch):
    monkeypatch.setenv("INSUQ_LLM_FALLBACK_PROVIDER", "openai")
    monkeypatch.setenv("INSUQ_LLM_FALLBACK_MODEL", "gpt-4.1-mini")
    config = {"generation": {"provider": "nvidia", "llm_model": "openai/gpt-oss-120b"}}

    main._apply_generation_override(config)

    assert config["generation"]["fallback"] == {
        "provider": "openai",
        "llm_model": "gpt-4.1-mini",
    }


def test_half_configured_fallback_is_ignored(monkeypatch):
    """하나만 설정된 폴백을 절반만 적용하지 않는다."""
    monkeypatch.setenv("INSUQ_LLM_FALLBACK_PROVIDER", "openai")
    monkeypatch.delenv("INSUQ_LLM_FALLBACK_MODEL", raising=False)
    config = {"generation": {"provider": "nvidia", "llm_model": "openai/gpt-oss-120b"}}

    main._apply_generation_override(config)

    assert "fallback" not in config["generation"]
```

- [ ] **Step 6: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/InsuQ/ai-engine && python -m pytest tests/ -q`

Expected: PASS — 기존 932 passed + 신규분. 실패 0건.

- [ ] **Step 7: `.env.example` 을 갱신한다**

`ai-engine/.env.example` 의 `INSUQ_LLM_PROVIDER`·`INSUQ_LLM_MODEL` 두 줄(L28-29)을 아래 네 줄로 교체한다.

```bash
# 서빙 생성 경로 (2026-08-29). 기본은 NVIDIA NIM 무료 티어다 — 실측으로 tool-calling·
# 한국어·응답속도를 확인한 모델이다(A2A_Q 설계 문서 참고). NVIDIA_API_KEY 필요.
INSUQ_LLM_PROVIDER=nvidia
INSUQ_LLM_MODEL=openai/gpt-oss-120b
# 위 경로가 죽으면(크레딧 소진·인증 실패·모델 404) 자동 전환할 유료 경로.
# **둘 다** 채워야 켜진다. 비워두면 폴백 없이 동작한다(기존과 동일).
INSUQ_LLM_FALLBACK_PROVIDER=openai
INSUQ_LLM_FALLBACK_MODEL=gpt-4.1-mini
```

`NVIDIA_API_KEY` 항목이 `.env.example` 에 없으면 함께 추가한다(`OPENAI_API_KEY` 는 커밋 `9c4c941` 로 이미 있다).

- [ ] **Step 8: `docs/08_DEPLOYMENT.md` 환경변수 표를 갱신한다**

Run: `grep -n "INSUQ_LLM_PROVIDER\|INSUQ_LLM_MODEL\|OPENAI_API_KEY" /c/Users/ttogl/workspace/InsuQ/docs/08_DEPLOYMENT.md`

찾은 행을 `nvidia` / `openai/gpt-oss-120b` 기준으로 고치고, 폴백 두 변수를 행으로 추가한다. **⚠️ 배포 환경(Render 등)의 실제 환경변수는 이 계획의 범위 밖이다**(TASK-H15 후속 ①, 재배포 시 처리) — 그 사실을 표 아래 주석 한 줄로 남긴다.

- [ ] **Step 9: 커밋**

```bash
cd /c/Users/ttogl/workspace/InsuQ
git add ai-engine/insuq_ai/generation/llm.py ai-engine/insuq_ai/api/main.py \
        ai-engine/tests/api/test_generation_override.py \
        ai-engine/tests/generation/test_llm_fallback.py \
        ai-engine/.env.example docs/08_DEPLOYMENT.md
git commit -m "feat(serving): 기본 nvidia/gpt-oss-120b + openai 자동 폴백 배선

폴백 설정은 _apply_generation_override 에서만 읽는다 — eval/run.py 는 이
함수를 타지 않으므로 평가 경로에는 폴백이 존재하지 않는다. judge 가 실행
중간에 갈려 리포트가 오염되는 것을 구조로 막는다(특례 코드 없음).

폴백 환경변수는 둘 다 있어야 켜진다. 하나만 설정된 상태를 절반만 적용하면
'폴백이 켜진 줄 알았는데 아니었다'가 된다."
```

---

### Task 4: MaintQ — `nvidia` provider 추가

**Files:**
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\agent\llm.py` (`PROVIDERS` L503, `get_client()`)
- Create: `C:\Users\ttogl\workspace\MaintQ\backend\agent\test_llm_fallback.py`
- Modify: `C:\Users\ttogl\workspace\MaintQ\.env.example`

**Interfaces:**
- Consumes: 없음 (MaintQ 첫 작업 — InsuQ 코드를 임포트하지 않는다)
- Produces: `PROVIDERS` 에 `"nvidia"` 가 포함되고, `get_client()` 가 `MAINTQ_LLM_PROVIDER=nvidia` 에서 `EliceClient` 를 `base_url="https://integrate.api.nvidia.com"` 로 만든다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/agent/test_llm_fallback.py` 를 새로 만든다. 기존 `test_llm_cache.py` 의 헤더 관례(인코딩 주석 · `sys.path` 삽입)를 그대로 따른다.

```python
# -*- coding: utf-8 -*-
"""nvidia provider 추가 + 제공자 자동 폴백 (2026-08-29 LLM 제공자 통일).

**네트워크를 절대 타지 않는다** — 클라이언트 생성과 대역 스트림만 검증한다.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.agent import llm  # noqa: E402


def _clear_llm_env(monkeypatch):
    for name in (
        "MAINTQ_LLM_PROVIDER", "MAINTQ_LLM_MODEL",
        "MAINTQ_LLM_FALLBACK_PROVIDER", "MAINTQ_LLM_FALLBACK_MODEL",
        "NVIDIA_API_KEY", "OPENAI_API_KEY", "MAINTQ_LLM_CACHE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_nvidia_is_a_known_provider():
    assert "nvidia" in llm.PROVIDERS


def test_nvidia_client_uses_nim_base_url(monkeypatch):
    """EliceClient 가 /v1 을 붙이므로 여기서는 호스트까지만 넣는다 (llm.py:422-424)."""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")

    client = llm.get_client()

    assert isinstance(client, llm.EliceClient)
    assert str(client._client.base_url).rstrip("/") == "https://integrate.api.nvidia.com/v1"


def test_nvidia_without_key_fails_loudly(monkeypatch):
    """키가 없으면 가짜 응답으로 대체하지 않고 실패한다 (D40)."""
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "openai/gpt-oss-120b")

    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
        llm.get_client()
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && python -m pytest backend/agent/test_llm_fallback.py -v`

Expected: FAIL — `assert 'nvidia' in ('gemini', 'anthropic', 'elice', 'openai')`.

- [ ] **Step 3: `PROVIDERS` 와 `get_client()` 를 확장한다**

`backend/agent/llm.py:503` 을 교체한다.

```python
PROVIDERS = ("gemini", "anthropic", "elice", "openai", "nvidia")
```

`get_client()` 의 `elif provider == "openai":` 블록 **바로 아래**에 추가한다.

```python
    elif provider == "nvidia":
        # NVIDIA NIM — OpenAI 호환이라 EliceClient 를 그대로 재사용한다.
        # base_url 에 /v1 을 붙이지 않는다: EliceClient 가 없으면 붙인다(L422-424).
        api_key = os.environ.get("NVIDIA_API_KEY", "").strip()
        key_label = "NVIDIA_API_KEY"
        base_url = "https://integrate.api.nvidia.com"
```

같은 함수의 클라이언트 생성 분기를 교체한다.

```python
    elif provider in ("elice", "openai", "nvidia"):
        inner = EliceClient(model=model, api_key=api_key, base_url=base_url)
```

- [ ] **Step 4: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && python -m pytest backend/agent/test_llm_fallback.py -v`

Expected: PASS — 3 passed.

- [ ] **Step 5: `.env.example` 을 갱신한다**

`MAINTQ_LLM_PROVIDER`(L10)·`MAINTQ_LLM_MODEL`(L23) 을 아래로 바꾸고, `NVIDIA_API_KEY` 설명(L44-45)에 이제 생성에도 쓰인다는 사실을 덧붙인다.

```bash
MAINTQ_LLM_PROVIDER=nvidia
MAINTQ_LLM_MODEL=openai/gpt-oss-120b
```

- [ ] **Step 6: 커밋**

```bash
cd /c/Users/ttogl/workspace/MaintQ
git status --short   # 다른 세션 작업물과 섞이지 않는지 먼저 확인
git add backend/agent/llm.py backend/agent/test_llm_fallback.py .env.example
git commit -m "feat(llm): nvidia provider 추가 — NIM 무료 티어를 생성 경로로

OpenAI 호환이라 EliceClient 를 그대로 재사용한다. base_url 에 /v1 을 붙이지
않는다 — EliceClient 가 없으면 붙인다(llm.py:422-424).

NVIDIA_API_KEY 는 지금까지 임베딩에만 쓰였고 .env 에 없었다 — 생성에도
쓰이므로 .env.example 설명을 갱신했다."
```

---

### Task 5: MaintQ — `FallbackClient` (비동기 스트리밍)

**Files:**
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\agent\llm.py`
- Modify: `C:\Users\ttogl\workspace\MaintQ\backend\agent\test_llm_fallback.py`
- Modify: `C:\Users\ttogl\workspace\MaintQ\.env.example`

**Interfaces:**
- Consumes: Task 4의 `nvidia` provider
- Produces: `class FallbackClient` — `__init__(self, primary: LlmClient, fallback: LlmClient, *, primary_label: str, fallback_label: str)`, `stream(*, system, messages, tools) -> AsyncIterator[LlmDelta]`. `get_client()` 가 폴백 환경변수 쌍이 있을 때만 이것을 반환한다.

**주의:** MaintQ `LlmClient` 는 메서드가 `stream()` **하나뿐**이고 비동기다(`llm.py:36-39`). InsuQ 의 동기 3메서드 구조와 다르므로 코드를 복사하지 않는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`backend/agent/test_llm_fallback.py` 끝에 추가한다.

```python
class FakeStatusError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code


class FakeClient:
    """LlmClient 대역 — 델타를 흘리다 지정 지점에서 예외를 던진다."""

    def __init__(self, deltas=(), *, exc=None, raise_after=None):
        self._deltas = list(deltas)
        self._exc = exc
        self._raise_after = raise_after
        self.calls = 0

    def stream(self, *, system, messages, tools):
        self.calls += 1

        async def gen():
            for i, d in enumerate(self._deltas):
                if self._raise_after is not None and i == self._raise_after:
                    raise self._exc or RuntimeError("stream broke")
                yield d
            if self._exc is not None and self._raise_after is None:
                raise self._exc

        return gen()


async def _drain(client):
    out = []
    async for d in client.stream(system="s", messages=[], tools=[]):
        out.append(d)
    return out


def test_primary_success_does_not_touch_fallback():
    primary = FakeClient([("text", "일차")])
    secondary = FakeClient([("text", "폴백")])
    client = llm.FallbackClient(primary, secondary,
                                primary_label="nvidia", fallback_label="openai")

    assert asyncio.run(_drain(client)) == [("text", "일차")]
    assert secondary.calls == 0


def test_fallback_takes_over_before_first_delta():
    primary = FakeClient([], exc=FakeStatusError(401))
    secondary = FakeClient([("text", "폴백")])
    client = llm.FallbackClient(primary, secondary,
                                primary_label="nvidia", fallback_label="openai")

    assert asyncio.run(_drain(client)) == [("text", "폴백")]
    assert secondary.calls == 1


def test_no_fallback_after_first_delta():
    """이미 나간 델타 뒤에 다른 모델로 다시 쓰면 화면에 중복·모순 출력이 된다."""
    primary = FakeClient([("text", "일"), ("text", "차")],
                         raise_after=1, exc=FakeStatusError(500))
    secondary = FakeClient([("text", "폴백")])
    client = llm.FallbackClient(primary, secondary,
                                primary_label="nvidia", fallback_label="openai")

    with pytest.raises(Exception):
        asyncio.run(_drain(client))
    assert secondary.calls == 0


def test_fallback_logs_without_key(caplog):
    primary = FakeClient([], exc=FakeStatusError(401))
    secondary = FakeClient([("text", "폴백")])
    client = llm.FallbackClient(primary, secondary,
                                primary_label="nvidia", fallback_label="openai")

    with caplog.at_level("WARNING"):
        asyncio.run(_drain(client))

    assert "nvidia" in caplog.text and "openai" in caplog.text
    assert "FakeStatusError" in caplog.text
    assert "test-key-not-real" not in caplog.text


def test_get_client_wraps_only_when_both_fallback_vars_set(monkeypatch):
    _clear_llm_env(monkeypatch)
    monkeypatch.setenv("MAINTQ_LLM_PROVIDER", "nvidia")
    monkeypatch.setenv("MAINTQ_LLM_MODEL", "openai/gpt-oss-120b")
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key-not-real")

    # 폴백 미설정 → 기존 동작
    assert not isinstance(llm.get_client(), llm.FallbackClient)

    # 하나만 설정 → 여전히 기존 동작
    monkeypatch.setenv("MAINTQ_LLM_FALLBACK_PROVIDER", "openai")
    assert not isinstance(llm.get_client(), llm.FallbackClient)

    # 둘 다 설정 → 폴백
    monkeypatch.setenv("MAINTQ_LLM_FALLBACK_MODEL", "gpt-4.1-mini")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    assert isinstance(llm.get_client(), llm.FallbackClient)
```

- [ ] **Step 2: 테스트를 돌려 실패를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && python -m pytest backend/agent/test_llm_fallback.py -v`

Expected: FAIL — `AttributeError: module 'backend.agent.llm' has no attribute 'FallbackClient'`.

- [ ] **Step 3: `FallbackClient` 를 구현한다**

`backend/agent/llm.py` 의 `PROVIDERS = (...)` 정의 **바로 위**에 추가한다.

```python
class FallbackClient:
    """primary 스트림이 열리기 전에 실패하면 fallback 으로 넘긴다 (2026-08-29).

    **첫 델타가 나간 뒤에는 폴백하지 않는다.** 이미 화면에 토큰이 흘러간 뒤 다른
    모델로 다시 쓰면 중복·모순 출력이 된다 — 그 시점부터는 예외를 그대로 전파해
    호출자가 지금까지 누적된 델타로 판단하게 둔다.

    전환은 WARNING 으로 남긴다. 조용한 전환은 "왜 이번 달 청구서가 있지"가 된다 —
    Elice 장애 때 겪은 조용한 강등(생성 실패가 전부 거부 응답으로 둔갑)의 반복이다.
    """

    def __init__(
        self,
        primary: LlmClient,
        fallback: LlmClient,
        *,
        primary_label: str,
        fallback_label: str,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._primary_label = primary_label
        self._fallback_label = fallback_label

    def stream(
        self, *, system: str, messages: list[dict], tools: list[dict]
    ) -> AsyncIterator[LlmDelta]:
        primary, fallback = self._primary, self._fallback
        primary_label, fallback_label = self._primary_label, self._fallback_label

        async def gen() -> AsyncIterator[LlmDelta]:
            yielded = False
            try:
                async for delta in primary.stream(
                    system=system, messages=messages, tools=tools
                ):
                    yielded = True
                    yield delta
            except Exception as exc:  # noqa: BLE001 — 어떤 실패든 폴백 대상이다
                if yielded:
                    raise  # 이미 나간 토큰이 있다 — 다시 쓰지 않는다
                # 예외 타입만 남긴다 — 응답 본문에 키가 섞여 들어갈 수 있다 (D40)
                log.warning(
                    "LLM 제공자 폴백: %s → %s (원인 %s). 유료 경로로 전환됐다.",
                    primary_label,
                    fallback_label,
                    type(exc).__name__,
                )
                async for delta in fallback.stream(
                    system=system, messages=messages, tools=tools
                ):
                    yield delta

        return gen()
```

**로거 이름 확인:** `backend/agent/llm.py` 상단에서 로거 변수명을 확인하고(`log` 또는 `logger`) 위 코드의 `log.warning` 을 그것에 맞춘다. `AsyncIterator` 임포트가 없으면 추가한다.

- [ ] **Step 4: `get_client()` 를 폴백 대응으로 바꾼다**

`get_client()` 를 두 부분으로 나눈다 — 기존 본문을 `_build_single_client(provider)` 로 옮기고, `get_client()` 는 그것을 조합한다. 기존 `CachingClient` 배선(D104)은 **가장 바깥**에 그대로 남긴다.

```python
def _build_single_client(provider: str) -> LlmClient:
    """provider 하나에 대한 클라이언트. 기존 get_client() 본문 그대로다.

    (여기에 기존 get_client() 의 provider 분기·키 검증·inner 생성 코드를 그대로
    옮긴다 — CachingClient 배선만 빼고. 모델명은 MAINTQ_LLM_MODEL 을 읽는다.)
    """
    ...


def get_client() -> LlmClient:
    """환경변수로 실제 클라이언트를 만든다 (D56 — 제공자 분기, 기본 gemini).

    `MAINTQ_LLM_FALLBACK_PROVIDER` 와 `MAINTQ_LLM_FALLBACK_MODEL` 이 **둘 다**
    있으면 `FallbackClient` 로 감싼다(2026-08-29). 하나만 있으면 켜지 않는다 —
    절반만 적용하면 "폴백이 켜진 줄 알았는데 아니었다"가 된다.
    """
    provider = (os.environ.get("MAINTQ_LLM_PROVIDER") or "gemini").strip().lower()
    model = os.environ.get("MAINTQ_LLM_MODEL", "").strip()
    inner = _build_single_client(provider)

    fb_provider = (os.environ.get("MAINTQ_LLM_FALLBACK_PROVIDER") or "").strip().lower()
    fb_model = (os.environ.get("MAINTQ_LLM_FALLBACK_MODEL") or "").strip()
    if fb_provider and fb_model:
        # 폴백 클라이언트는 자기 모델명을 봐야 하므로 잠시 바꿔 끼운다.
        prev = os.environ.get("MAINTQ_LLM_MODEL")
        os.environ["MAINTQ_LLM_MODEL"] = fb_model
        try:
            fallback = _build_single_client(fb_provider)
        finally:
            if prev is None:
                os.environ.pop("MAINTQ_LLM_MODEL", None)
            else:
                os.environ["MAINTQ_LLM_MODEL"] = prev
        inner = FallbackClient(
            inner, fallback, primary_label=provider, fallback_label=fb_provider
        )
    elif fb_provider or fb_model:
        log.warning(
            "MAINTQ_LLM_FALLBACK_PROVIDER 와 MAINTQ_LLM_FALLBACK_MODEL 은 함께 "
            "설정해야 한다 — 하나만 있어 폴백을 켜지 않았다."
        )

    # 카세트는 **명시적 옵트인**이다 (D104). 켜지 않으면 위 클라이언트가 그대로 나간다.
    from backend.agent.llm_cache import CachingClient, cache_enabled  # noqa: PLC0415

    if cache_enabled():
        return CachingClient(inner, provider=provider, model=model)
    return inner
```

**주의:** `_build_single_client` 가 `MAINTQ_LLM_MODEL` 을 환경변수에서 읽는 구조 때문에 위처럼 잠시 바꿔 끼운다. 옮기는 과정에서 `model` 을 인자로 받도록 리팩터링해도 좋다 — 그 편이 깨끗하면 `_build_single_client(provider: str, model: str)` 로 바꾸고 위 임시 치환을 지운다.

- [ ] **Step 5: 테스트를 돌려 통과를 확인한다**

Run: `cd /c/Users/ttogl/workspace/MaintQ && python -m pytest backend/agent/ -v`

Expected: PASS — 신규 8건 + 기존 `test_llm_cache.py` 전부 통과.

- [ ] **Step 6: MaintQ 전체 스위트를 돌린다**

⚠️ **정정(2026-08-29, maintq-45 지적):** 이 계획의 초안은 기대값을 "1,075건"으로 적었으나 **틀렸다.** 1,075는 **spikes 33스위트**의 건수이고 pytest는 그와 **별개의 축**이다 — 두 숫자를 섞어 쓰면 안 된다. 기준선은 MaintQ `CLAUDE.md` 「회귀 스위트」 절을 SSOT로 삼는다.

Run: MaintQ `CLAUDE.md` 「회귀 스위트」 절이 지정하는 명령. A2A 8파일군은 **`pytest-asyncio` 없이 돌리면 async 테스트가 전부 `async def functions are not natively supported`로 떨어진다** — 그 절이 지정한 러너(`uv run --with pytest-asyncio` 등)를 그대로 쓴다.

Expected: 해당 절의 기준선 + 이 계획의 신규분. **FAIL 0건이 아니면 커밋하지 않는다.** 건수가 기준선과 다르면 그 차이를 설명할 수 있어야 한다(설명 못 하면 커밋하지 않는다).

**spikes 축도 함께 본다:** `spikes/llm_provider_contract.py` 는 `MAINTQ_LLM_*` 환경변수를 직접 읽으므로 이 계획의 변경에 직접 노출된다. `_ENV_KEYS` 에 신규 환경변수(`MAINTQ_LLM_FALLBACK_PROVIDER`·`MAINTQ_LLM_FALLBACK_MODEL`·`NVIDIA_API_KEY`)가 빠져 있으면, `.env.example` 을 그대로 복사한 사용자 환경에서 그 스파이크가 `GeminiClient` 대신 `FallbackClient` 를 받아 FAIL 한다. 이 계획이 심는 파손이므로 같은 브랜치에서 함께 고친다.

- [ ] **Step 7: `.env.example` 에 폴백 두 줄을 추가한다**

```bash
# 기본 경로가 죽으면(크레딧 소진·인증 실패·모델 404) 자동 전환할 유료 경로.
# **둘 다** 채워야 켜진다. 비워두면 폴백 없이 동작한다(기존과 동일).
MAINTQ_LLM_FALLBACK_PROVIDER=openai
MAINTQ_LLM_FALLBACK_MODEL=gpt-4.1-mini
```

- [ ] **Step 8: 커밋**

```bash
cd /c/Users/ttogl/workspace/MaintQ
git add backend/agent/llm.py backend/agent/test_llm_fallback.py .env.example
git commit -m "feat(llm): FallbackClient — nvidia 실패 시 openai 자동 전환

MaintQ LlmClient 는 stream() 하나짜리 비동기 인터페이스라 InsuQ 의 동기
3메서드 래퍼와 코드를 공유하지 않는다.

첫 델타가 나간 뒤에는 폴백하지 않는다 — 이미 화면에 흘러간 토큰 뒤에
다른 모델로 다시 쓰면 중복·모순 출력이 된다.

폴백 환경변수는 둘 다 있어야 켜진다."
```

---

### Task 6: 실측 검증 + 문서 반영

**왜 필요한가:** 여기까지는 "폴백이 동작한다"만 증명했다. **`openai/gpt-oss-120b` 가 실제로 쓸 만한지는 아직 프로브 1문항이 전부다** — 한국어 비율 0.72는 "한국어로 답했다"는 뜻이지 "정확하다"는 뜻이 아니다.

**Files:**
- Modify: `C:\Users\ttogl\workspace\InsuQ\experiments.md` 또는 `docs/experiments.md` (`ls` 로 실제 위치 먼저 확인)
- Modify: `C:\Users\ttogl\workspace\InsuQ\docs\07_BACKLOG.md` (TASK-H15)
- Modify: MaintQ D122가 기록된 문서 (`grep -rn "D122" /c/Users/ttogl/workspace/MaintQ/docs/` 로 위치 확인)

**Interfaces:**
- Consumes: Task 3·5의 배선
- Produces: 없음 (마지막 작업)

- [ ] **Step 1: 두 시스템을 실제로 띄워 한 번씩 물어본다**

InsuQ·MaintQ를 각 레포의 기존 기동 방법으로 띄우고, 데모에서 쓰는 질문 1건씩을 실제로 통과시킨다. 확인할 것:
- 응답이 한국어로 나오는가
- 근거 인용이 형식을 지키는가
- 로그에 `생성 모델 오버라이드` WARNING 이 뜨고 provider 가 `nvidia` 인가
- **폴백 WARNING 이 뜨지 않는가** (뜬다면 기본 경로가 이미 죽은 것이다)

결과를 그대로 기록한다. 실패하면 Step 3으로 간다.

- [ ] **Step 2: 골든셋을 재측정한다**

TASK-H15 후속 ②를 여기서 소진한다. 서빙 모델이 바뀌었으므로 **거부 지표를 과잉거부와 쌍으로** 본다(EXP-052 전례 — flash-lite 과잉거부 기각).

Run: InsuQ 레포의 기존 평가 명령(`ls eval/` 로 확인, `eval/run.py` 사용)

⚠️ **새 config·리포트 쌍을 만든다.** 기존 `genpath.yaml` 등 4종은 `provider: elice` 이고 `config_sha256` 가 리포트에 박혀 있어 제자리 수정하면 과거 대조가 깨진다(`eval/aggregate_runs.py` 가 `ValueError` 로 죽는다).

예상 비용: 몇 센트.

- [ ] **Step 3: 품질이 미달이면 차점 모델로 바꾼다**

`nvidia/nemotron-3-super-120b-a12b` 가 프로브에서 동률이었다(tool-calling ✅ · 한국어 0.72 · 1.7~2.0s). 모델 문자열만 바꾸면 되고 코드 변경은 없다.

둘 다 미달이면 **기본을 `openai`/`gpt-4.1-mini` 로 되돌리고 폴백을 끈다** — 폴백 구조 자체는 남겨둔다(다음 제공자 전환 때 그대로 쓴다). 이 판단은 사용자에게 확인받는다.

- [ ] **Step 4: `experiments.md` 에 전/후를 남긴다**

당일 기록이 상시 규칙이다(`07_BACKLOG.md` L325). judge 도 바뀌었을 수 있으므로 **EXP-054/055와 직접 비교하지 않는다**는 사실을 함께 적는다.

- [ ] **Step 5: 백로그를 갱신한다**

InsuQ `docs/07_BACKLOG.md` TASK-H15에 후속 ② 소진을 기록한다. 후속 ①(Render 환경변수)은 **여전히 열려 있다** — 재배포 시점에 `MAINTQ_LLM_PROVIDER`·`INSUQ_LLM_PROVIDER` 와 폴백 두 변수를 대시보드에 넣어야 한다는 사실을 명시한다.

MaintQ D122에도 provider가 `openai`/`gpt-4.1-mini` 에서 `nvidia`/`openai/gpt-oss-120b`(폴백 `gpt-4.1-mini`)로 바뀐 사실을 덧붙인다.

- [ ] **Step 6: 커밋·푸시**

```bash
cd /c/Users/ttogl/workspace/InsuQ && git status --short
git add experiments.md docs/07_BACKLOG.md   # 실제 경로로 조정
git commit -m "docs: gpt-oss-120b 서빙 전환 실측 + TASK-H15 후속 2 소진"

cd /c/Users/ttogl/workspace/MaintQ && git status --short
git add docs/  # D122 문서 경로로 조정
git commit -m "docs: D122 — 서빙 provider 를 nvidia/gpt-oss-120b 로 갱신"
```

**푸시는 사용자에게 확인받는다.**

---

## Self-Review

**1. 스펙 커버리지**

| 스펙 요구 | 담당 |
|---|---|
| 기본 `nvidia`/`openai/gpt-oss-120b` | Task 3(InsuQ) · Task 4(MaintQ) ✅ |
| 폴백 `openai`/`gpt-4.1-mini` | Task 3 · Task 5 ✅ |
| 401·403·404 즉시 폴백 | Task 1 ✅ |
| 402·429 1회 재시도 후 폴백 | Task 1 ✅ |
| 5xx·미분류 기존 재시도 후 폴백 | Task 1 ✅ |
| 전환 WARN 로그 (키 없이) | Task 2 · Task 5 ✅ |
| `LLMTurn.provider_used` | Task 2 ✅ |
| 스트리밍 첫 청크 후 폴백 금지 | Task 2 · Task 5 ✅ |
| judge 폴백 금지 | Task 3 ✅ — **특례 코드가 아니라 구조로 보장.** 폴백 설정이 `_apply_generation_override`(서빙 전용)에서만 채워지고 `eval/run.py` 는 그 함수를 타지 않는다 |
| 폴백 미설정 시 기존 동작 | Task 3 · Task 5 ✅ |
| MaintQ `PROVIDERS` 에 nvidia | Task 4 ✅ |
| `.env.example`·배포 문서 | Task 3 · Task 4 · Task 5 ✅ |
| 골든셋 재측정 | Task 6 ✅ |
| 외부 실호출 0건 | 전 Task ✅ |

**2. 플레이스홀더 스캔**

- Task 5 Step 4의 `_build_single_client` 본문을 `...` 로 둔 것은 **의도적이다** — 기존 `get_client()` 본문 40여 줄을 그대로 옮기는 기계적 작업이라 여기 복제하면 원본과 어긋날 위험이 더 크다. "무엇을 옮기고 무엇을 빼는지"(CachingClient 배선만 제외)를 명시했다.
- Task 6의 파일 경로 몇 개를 `ls`/`grep` 으로 먼저 확인하라고 지시했다 — A2A_Q 세션에서 InsuQ `experiments.md` 와 MaintQ D122 문서의 정확한 경로를 확정하지 않았으므로 추정 경로를 단정하지 않았다.
- 그 외 TBD·"적절히 처리" 류 없음. ✅

**3. 타입 일관성**

- `classify_failure(exc) -> str` 이 반환하는 세 상수를 `retry_budget(kind, max_retries)` 가 그대로 받는다 ✅
- `FallbackLLMClient.__init__` 의 키워드 인자(`primary_name`/`fallback_name`)가 Task 2 테스트·Task 3 `build_llm_client` 에서 동일 ✅
- MaintQ `FallbackClient.__init__` 은 `primary_label`/`fallback_label` 로 **이름이 다르다** — 의도적이다. 두 레포는 서로 임포트하지 않고 각자 관례를 따른다. 같은 파일 안에서는 일관된다 ✅
- `LLMTurn.provider_used: str | None = None` — 기본값이 있어 기존 생성부(`llm.py` 내 `LLMTurn(content=..., tool_calls=..., finish_reason=...)`)가 깨지지 않는다 ✅
- `config["generation"]["fallback"]` 의 형태 `{"provider": str, "llm_model": str}` 가 Task 3 Step 3·4·5에서 동일 ✅

**4. 알려진 위험**

- **Task 1 Step 6의 `FakeStatusError` 가 SDK 예외 계층 밖이라 `except` 에 안 잡힐 수 있다.** Step 6 본문에 그 경우의 대처를 적어뒀다.
- **NVIDIA 무료 크레딧 잔량을 조회할 방법이 없다.** 폴백 발동 시점을 예측할 수 없고 WARN 로그가 유일한 사후 신호다 — 스펙의 「미해결」에 기록돼 있다.
