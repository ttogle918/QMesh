# LLM 제공자 통일 + 자동 폴백 — 설계 (2026-08-29)

## 배경

2026-08-29 Elice 계정 종료가 확정되면서 InsuQ·MaintQ 두 레포가 **각자 따로** OpenAI로
갈아탔고, 그 결과 서빙 모델이 갈렸다.

| 레포 | 현재 provider / 모델 | 근거 |
|---|---|---|
| InsuQ | `openai` / `gpt-4o-mini` | TASK-H15, 커밋 `9c4c941` |
| MaintQ | `openai` / `gpt-4.1-mini` | D122, 커밋 `e963f9e` |
| FinAllQ | **없음** | LLM 설정 자체가 없다(`LLM_PROVIDER`·`OPENAI_API_KEY` 매치 0건, 2026-08-29 확인) |
| A2A_Q | **없음** | 계약·문서 레포 |

같은 데모를 구성하는 두 시스템이 서로 다른 모델을 쓰는 상태이고, 둘 다 유료 경로다.
발표가 끝난 뒤의 용도는 **포트폴리오·구직용 유지 + 평가 재측정 + 개발/데모 재현**이므로
"항상 살아 있을 것"이 가장 중요하고, 비용은 낮을수록 좋다.

### 비용 전제 정정

TASK-H15 후속 ②는 골든셋 재측정을 "LLM 호출 비용 때문에 보류"로 적어뒀지만, 실제
골든셋은 20~50문항 규모다(`화재재물_goldenset.json` 20건 등). 1회 재측정은 대략
입력 10만 · 출력 2.5만 토큰으로, `gpt-4.1-mini` 기준으로도 **몇 센트**다.
아껴야 할 대상은 평가 배치가 아니라 **유료 키를 상시 물고 있는 것 자체**다.

## 결정

| 역할 | provider | 모델 | 근거 |
|---|---|---|---|
| 기본 | `nvidia` | `openai/gpt-oss-120b` | NVIDIA NIM 무료 티어. 실측 tool-calling ✅ · 한국어 비율 0.72 · 1.5~2.0s |
| 폴백 | `openai` | `gpt-4.1-mini` | 안정 유료 경로. 기본과 같은 OpenAI 계열이라 전환 시 출력 드리프트가 가장 작다 |

두 레포가 기본·폴백을 **똑같이** 쓴다 — 이것으로 `4o-mini`/`4.1-mini` 불일치가 사라진다.

### 모델 선정 실측 (2026-08-29, `integrate.api.nvidia.com/v1`, 83개 모델 목록)

한국어 비율은 응답 문자열의 한글 문자 비율을 파이썬에서 계산한 값이다.

| 모델 | tool-calling | 인자 파싱 | 한국어 | 응답 | 판정 |
|---|---|---|---|---|---|
| `openai/gpt-oss-120b` | ✅ | ✅ | 0.72 | 1.5~2.0s | **채택** |
| `nvidia/nemotron-3-super-120b-a12b` | ✅ | ✅ | 0.72 | 1.7~2.0s | 동률 차점 |
| `nvidia/nemotron-3-nano-30b-a3b` | ❌ 호출 안 함 | — | 0.70 | 1.7s | 탈락 |
| `google/gemma-4-31b-it` | ✅ | ✅ | 0.73 | **46.2s** | 탈락(속도) |
| `nvidia/nemotron-3.5-lightning-30b-a3b` | ✅ | ✅ | **0.03** | 0.8s | 탈락(영어로 답함) |
| `deepseek-ai/deepseek-v4-flash-0731` | ✅ | ✅ | **0.00** | 31~62s | 탈락(추론 토큰이 본문을 다 먹음) |
| `moonshotai/kimi-k2.6`, `01-ai/yi-large`, `nvidia/nemotron-nano-3-30b-a3b` | 404 | — | — | — | 탈락 |
| `mistralai/mistral-nemotron` | 500 | — | — | — | 탈락 |

**크레딧을 덜 먹는 소형 모델로 내리는 길은 없다** — 30B급은 tool-calling을 안 하거나
(nemotron-3-nano) 한국어를 안 쓰거나(lightning) 46초가 걸린다(gemma-4-31b).

**Qwen은 이 엔드포인트에 없다.** 검색 결과는 build.nvidia.com에 Qwen3 계열이 있다고
하지만, 이 계정의 `/v1/models` 83개에 Qwen은 한 건도 없다.

**`deepseek-v4-flash` 탈락 사유는 이미 알려진 실패 모드다** — 추론 토큰이 `max_tokens`를
소진해 본문이 비어 나온다. InsuQ `llm.py`가 `LENGTH_FINISH_REASON` 판정으로 잡도록
만들어둔 바로 그 패턴이라(골든셋 gs-005 실측 버그), 서빙에 쓸 수 없다.

### 로컬 LLM(Qwen 등)을 접은 이유

- 이 머신에 **NVIDIA GPU가 없다** — Intel Iris Xe 내장, i7-1360P, RAM 32GB, `nvidia-smi` 없음
- CPU 추론이면 8B Q4 기준 한국어 답변 한 건에 30~60초 — 데모에서 못 쓴다
- 결정적으로 **포트폴리오 서빙에 원리적으로 불가능하다.** 배포 환경이 이 노트북에
  접근할 수 없고, 노트북이 꺼지면 채용 담당자에겐 죽은 사이트다
- 배치 평가 전용으로는 성립하지만, 그 배치가 이미 몇 센트라 절약할 것이 없다

(Ollama는 이 머신에 이미 설치돼 있다 — v0.33.2, `llama3.2:1b`. 이 설계는 그것을 쓰지 않는다.)

## 설계

### ① 폴백을 재시도와 분리한다

InsuQ `llm.py`에는 이미 재시도 정책이 있다(`MAX_RETRIES=3`, `BACKOFF_BASE_S=2.0`,
`DEFAULT_TIMEOUT_S=60.0`). 폴백은 그 **바깥 한 겹**으로 얹고, 실패 유형에 따라 진입
시점을 달리한다.

```
complete_turn() / stream_turn()
 ├ primary(nvidia, openai/gpt-oss-120b)
 │    401 · 403 · 404          → 재시도 없이 즉시 폴백
 │    402 · 429 (크레딧·rate)   → 1회만 재시도 후 폴백
 │    5xx · 타임아웃 · 연결실패  → 기존 재시도 정책 소진 후 폴백
 │    그 외 모든 오류           → 5xx와 같은 경로(기존 재시도 소진 후 폴백)
 └ fallback(openai, gpt-4.1-mini)
      여기서도 실패하면 기존과 동일하게 예외를 던진다(조용히 빈 응답을 내지 않는다)
```

분류되지 않은 오류의 기본 경로를 **5xx 쪽**으로 두는 이유: 크레딧 소진이 어떤 상태
코드로 오는지 문서로 확정하지 못했다. 알 수 없는 오류를 "즉시 폴백"으로 두면 일시
장애에도 유료 경로로 새고, "폴백 안 함"으로 두면 죽는다. 재시도 후 폴백이 두 실패
모두를 피한다.

**구현 위치 — 호출부를 바꾸지 않는다.** `llm.py`는 "제공자 추가는 `PROVIDERS`에 한 줄
넣는 것으로 끝나야 하고, 호출부는 바뀌지 않아야 한다"를 모듈 원칙으로 못박고 있다.
따라서 폴백은 `complete_turn()` 본문을 고치는 대신 **`LLMClient` Protocol을 구현하는
래퍼**(`FallbackLLMClient`)로 만들고, `build_llm_client()`가 폴백 설정이 있을 때만 그것을
반환한다. 두 개의 `OpenAICompatClient`를 감싸는 형태이며 기존 호출부는 한 줄도 바뀌지
않는다.

**이 분리가 설계의 핵심이다.** 401에 3번 지수 백오프하는 것은 순수 낭비이고(키가
틀린 것이 2초 뒤에 맞아지지 않는다), 반대로 일시적 5xx에 곧바로 유료 경로로 넘어가면
돈이 샌다.

`404`를 폴백 트리거에 넣는 근거는 위 실측이다 — `/v1/models` 목록에 있는 모델이
실제로는 404를 뱉는 경우를 5개 중 3개에서 봤다. **모델 목록은 호출 가능성을 보장하지
않는다.**

### ② 전환을 조용히 하지 않는다

폴백이 발동하면:
- `logger.warning`으로 **어느 provider에서 무슨 오류로 넘어갔는지** 남긴다 —
  세 진입점 모두에서. 이것이 유일하게 보편적인 신호 경로다
- `LLMTurn`(frozen dataclass)에 `provider_used` 필드를 추가해 `complete_turn()` 호출부가
  알 수 있게 한다

**반환 타입이 진입점마다 달라서 신호 경로가 균일하지 않다.** `complete_turn()`은
`LLMTurn`을 돌려주므로 필드를 실을 수 있지만, `stream_turn()`은 `Iterator[str]`,
`complete()`는 `str`이라 메타를 실을 자리가 없다. 이 둘에서는 **WARN 로그가 전부**다.
이 비대칭을 없애려고 반환 타입을 바꾸지는 않는다 — 그건 호출부를 다 건드리는 일이고
이번 목표가 아니다.

이것이 없으면 "왜 이번 달 청구서가 있지?"가 된다. Elice 장애 때 겪은 조용한 강등
(생성 실패가 전부 거부 응답으로 둔갑)을 반복하지 않기 위한 것이기도 하다.

### ②-1 평가 judge는 폴백하지 않는다

`build_judge_client()`는 평가 채점용 클라이언트를 만든다. **여기에는 폴백을 붙이지
않고, 실패하면 그대로 죽게 둔다.**

한 번의 골든셋 실행 중간에 judge가 nvidia에서 openai로 넘어가면 **앞부분과 뒷부분이
서로 다른 모델로 채점된 리포트**가 나온다. 그 리포트는 자기 자신과도 비교 불가능하고,
겉보기엔 정상이라 알아채기 어렵다. 서빙에서는 "죽는 것보다 비싼 게 낫다"가 맞지만,
평가에서는 **"오염된 숫자보다 실패가 낫다"**가 맞다.

`build_llm_client()`만 폴백을 적용하고 `build_judge_client()`는 손대지 않는다.

API 키는 기존 원칙대로 **코드·로그·리포트 어디에도 남기지 않는다**(`llm.py` 모듈
docstring).

### ③ 설정

기존 명명 규칙(`<REPO>_LLM_*`)을 그대로 따른다.

```
# InsuQ — ai-engine/.env
INSUQ_LLM_PROVIDER=nvidia
INSUQ_LLM_MODEL=openai/gpt-oss-120b
INSUQ_LLM_FALLBACK_PROVIDER=openai
INSUQ_LLM_FALLBACK_MODEL=gpt-4.1-mini

# MaintQ — .env
MAINTQ_LLM_PROVIDER=nvidia
MAINTQ_LLM_MODEL=openai/gpt-oss-120b
MAINTQ_LLM_FALLBACK_PROVIDER=openai
MAINTQ_LLM_FALLBACK_MODEL=gpt-4.1-mini
```

**폴백 변수가 비어 있으면 폴백 없이 기존 동작 그대로다.** 이미 배포된 환경이 이
변경으로 깨지지 않게 하기 위한 기본값이다(사용자 확인 완료). 대가로, 폴백 변수를
설정하지 않은 채 배포하면 폴백이 꺼진 상태가 된다 — `.env.example`에 네 줄을 모두
기본값으로 넣어 이 함정을 줄인다.

### ④ 레포별 변경 범위

**InsuQ** — `ai-engine/insuq_ai/generation/llm.py`
- `PROVIDERS`에 `nvidia`(`https://integrate.api.nvidia.com/v1`, `NVIDIA_API_KEY`)가
  **이미 있다** — provider 추가 0줄
- `NVIDIA_API_KEY`도 `ai-engine/.env`에 이미 있다(2026-08-29 확인)
- `FallbackLLMClient`(`LLMClient` Protocol 구현)를 신설하고 `build_llm_client()`가
  폴백 설정이 있을 때만 반환한다. `complete()`·`complete_turn()`·`stream_turn()`
  세 진입점을 모두 위임한다
- `stream_turn()`은 재시도 경계가 다르다(첫 청크 수신 후에는 재시도하지 않는다 —
  중복 출력 방지). **폴백도 같은 경계를 따른다: 첫 청크가 나간 뒤에는 폴백하지 않는다.**
  이미 사용자 화면에 토큰이 흘러간 뒤에 다른 모델로 다시 쓰면 중복·모순 출력이 된다
- `LLMTurn`에 `provider_used` 필드 추가(frozen dataclass이므로 기본값을 줘서 기존
  생성부가 깨지지 않게 한다)
- `build_judge_client()`는 **손대지 않는다**(②-1)
- `.env.example`·`docs/08_DEPLOYMENT.md` 환경변수 표 갱신

**MaintQ** — `backend/agent/llm.py`
- `PROVIDERS`가 튜플이다(`("gemini", "anthropic", "elice", "openai")`, L503) —
  InsuQ의 `ProviderSpec` dict와 구조가 다르다. **구조를 통일하지 않는다**(범위 밖):
  `"nvidia"` 항목과 base_url 매핑만 최소 추가한다
- `NVIDIA_API_KEY`가 `.env`에 **없다**(임베딩용 `NVIDIA_EMBED_MODEL`은 쓰지만 키는
  미설정). 키 추가 필요 — InsuQ `ai-engine/.env`의 것과 같은 키를 재사용한다
- 폴백 래퍼 추가, `.env.example` 갱신

**FinAllQ · A2A_Q** — 변경 없음.

## 테스트

기존 관례를 따라 **외부 API 실호출 0건**으로 검증한다(InsuQ 932 passed가 이미 그렇다).

- 🧪 401 → primary 호출이 **정확히 1회**, 폴백 호출 1회 (재시도 낭비 방지)
- 🧪 404 → 동일하게 즉시 폴백
- 🧪 429 → primary 2회(최초+재시도 1회) 후 폴백
- 🧪 500 → 기존 재시도 정책 소진(3회) 후 폴백
- 🧪 폴백에서도 실패 → 예외가 그대로 올라온다(빈 응답으로 삼키지 않는다)
- 🧪 폴백 변수 미설정 → 기존 동작 그대로, 폴백 호출 0회 (회귀)
- 🧪 분류되지 않은 오류(임의 예외) → 5xx와 같은 경로를 탄다
- 🧪 폴백 발동 시 WARN 로그에 provider·오류 유형이 있고 **API 키는 없다**
- 🧪 `stream_turn()` 첫 청크 수신 후 스트림 중단 → 폴백하지 않는다
- 🧪 `complete_turn()` 성공 시 `LLMTurn.provider_used`가 실제 사용된 provider다
  (폴백 발동 시엔 폴백 provider가 실린다)
- 🧪 **`build_judge_client()`는 폴백을 갖지 않는다** — 폴백 설정이 있어도 반환값이
  `FallbackLLMClient`가 아니고, primary 실패 시 예외가 그대로 올라온다 (②-1)
- 🧪 두 레포 전체 스위트 회귀

## 실측 검증

골든셋 재측정 1회를 이 변경의 검증으로 돌린다(TASK-H15 후속 ②를 여기서 소진).
서빙 모델이 `gpt-4o-mini`/`gpt-4.1-mini` → `openai/gpt-oss-120b`로 바뀌므로
EXP-052(flash-lite 과잉거부 기각) 전례대로 **거부 지표를 과잉거부와 쌍으로** 본다.
결과는 `experiments.md`에 전/후로 남긴다. 예상 비용 몇 센트.

## 범위 밖

- **Render 등 배포 환경변수 갱신** — TASK-H15 후속 ①. 재배포 시점에 함께 처리하기로
  이미 결정돼 있다(사용자 인지·수용). 이 설계는 로컬 `.env`와 `.env.example`까지만 다룬다.
- **평가 config 4종의 `provider: elice`** — `genpath.yaml`·`genpath_no_annex.yaml`·
  `track1_flash.yaml`·`track1_lite.yaml`. `config_sha256`가 리포트에 박혀 있고
  `eval/aggregate_runs.py`가 해시 불일치 시 `ValueError`로 죽어, 주석 한 줄만 붙여도
  과거 리포트 대조가 깨진다. 재측정은 **새 config·리포트 쌍**으로 한다.
- **MaintQ `PROVIDERS` 구조를 InsuQ `ProviderSpec` 형태로 통일하는 리팩터링** — 이번
  목표(모델 통일 + 폴백)에 필요하지 않다.
- **`elice` provider 항목 제거** — D115 자산 유지 결정에 따라 두 레포 모두 남겨둔다.
- **FinAllQ에 LLM 도입** — 지금 LLM을 쓰지 않으며, 쓸 이유가 없다.

## 미해결

- **NVIDIA 무료 크레딧 잔량을 모른다.** 소진 시점을 예측할 수 없어, 폴백이 언제
  발동할지도 알 수 없다. ②의 WARN 로그가 이걸 사후에 알려주는 유일한 수단이다.
  잔량 조회 API를 찾으면 헬스체크로 승격할 수 있다.
- **`openai/gpt-oss-120b`의 한국어 품질을 골든셋으로 재기 전까지는 프로브 1문항이
  전부다.** 0.72라는 한국어 비율은 "한국어로 답했다"는 뜻이지 "정확하다"는 뜻이 아니다.
  실측 검증 절이 이것을 닫는다.
