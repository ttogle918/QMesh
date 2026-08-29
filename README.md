# QMesh — A2A Multi-Agent Orchestration Hub

> **Q 시리즈 (FinAllQ · InsuQ · MaintQ)를 A2A(Agent-to-Agent) 프로토콜로 연결하는 독립 오케스트레이션 허브**  
> 각 도메인 프로젝트는 자기 자리에 그대로 두고, QMesh가 **오케스트레이터 + 공용 계약(Agent Card · Task 스키마) + 통합 배포**를 전담합니다.

```
MCP = 에이전트가 자기 도구를 쓴다 (각 도메인 내부)
A2A = 독립된 타사 에이전트에게 작업(Task)을 위임하고 협업한다 (QMesh가 조율)
```

---

## 0. 왜 별도 레포지토리(QMesh)인가?

- **경계의 물리적 증명**: FinAllQ(금융), InsuQ(보험), MaintQ(제조)는 기술 스택도 소유권도 다른 "독립 회사"입니다. 연결 코드를 특정 프로젝트 안에 종속시키지 않고 외부에 둠으로써 **"누구의 소유도 아닌 중립 프로토콜 계층"**을 형성합니다.
- **블랙박스 유지**: QMesh는 각 프로젝트의 내부 구현(DB, 프레임워크, 내부 프롬프트)을 알지 못합니다. 오직 **Agent Card와 표준 HTTP(A2A)**로만 대화합니다.
- **독립 릴리스**: 각 도메인 프로젝트는 자체 일정으로 배포되며, QMesh는 그 위에서 크로스도메인 협업 워크플로우만 독립적으로 갱신합니다.

---

## 1. 소유권 경계 (Ownership Boundary)

```
┌─────────────────────────────────────────────────────────────┐
│ QMesh (이 레포지토리) 소유                                  │
│  - contracts/ : Agent Card 스키마, Task 요청/응답 JSON Schema │
│  - orchestrator/ : 라우팅, 멀티홉 조율, 크로스도메인 트레이스 │
│  - docker-compose.yml : 전체 시스템 통합 기동 환경          │
└──────────────────────────────┬──────────────────────────────┘
                               │ A2A Protocol (HTTP / JSON Schema)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 각 도메인 레포지토리 소유 (FinAllQ / InsuQ / MaintQ)        │
│  - a2a/ : 자체 A2A 어댑터 (창구 포트 :9001, :9002, :9003)    │
│  - 내부 코어(Spring, LangGraph, DB, VectorStore)는 완전 격리 │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 레포지토리 구조

```
QMesh/
├── README.md                  # 프로젝트 통합 가이드
├── .gitignore                 # 보안/빌드 파일 관리
├── docker-compose.yml         # 3개 도메인 + 오케스트레이터 통합 기동
├── orchestrator/              # A2A 오케스트레이터 (:9000)
│   ├── main.py                #   진입점 & API 라우팅
│   ├── router.py              #   도메인 분류 및 에이전트 위임 결정
│   └── trace.py               #   request_chain_id 기반 크로스도메인 트레이스
├── docs/
│   ├── A2A_IDENTITY.md        # 신원 식별 및 보안 아키텍처 결정서 (SSOT)
│   ├── 11_A2A_SCENARIOS.md    # S5~S8 및 확장 시나리오 명세서
│   ├── agent_cards/           # 각 에이전트 선언서 (Agent Card)
│   │   ├── finallq.json       #   금융/은행/증권 에이전트 (:9001)
│   │   ├── insuq.json         #   보험 심사/약관 에이전트 (:9002)
│   │   └── maintq.json        #   제조 설비보전 에이전트 (:9003)
│   └── schemas/               # Task 요청/응답 표준 JSON Schema (13종)
│       ├── request-withdrawal.json            # [S5] 출금 요청 (2단 승인)
│       ├── advise-hedge.json                  # [S6] 환헤지/자산운용 상담
│       ├── advise-policy-renewal.json         # [S7] 화재보험 갱신 (고장이력 연계)
│       ├── verify-collateral-insurance.json   # [S8] 담보 대출 보험 검증 (멀티홉)
│       ├── assess-loan.json                   # 대출 심사
│       ├── assess-used-equipment-loan.json    # [S13] 중고설비 담보대출 심사
│       ├── advise-financing.json              # [S16] 설비 도입 자금조달 비교
│       ├── advise-replacement-financing.json  # [S15] 전손 교체 금융상담
│       ├── claim-insurance.json               # [S14] 보험금 청구
│       ├── notify-asset-change.json           # [S11] 자산 변동 통지
│       ├── notify-risk-change.json            # [S12] 리스크 변동 통지
│       ├── request-settlement.json            # 정산 요청
│       └── lookup-clause.json                 # 약관 근거 조회 (신규 제안, 선행조건 없음)
└── adapters/                  # 각 레포에 얹을 A2A 어댑터 (Templates + 프로토타입)
    ├── finallq_a2a/           #   FinAllQ request-withdrawal·assess-loan 프로토타입 (A2A_Q 안에서 구현, :9101)
    ├── insuq_a2a/             #   InsuQ lookup-clause 프로토타입 (A2A_Q 안에서 구현, :9102)
    └── maintq_a2a.py          #   템플릿(미착수)
```

---

## 3. 통신 토폴로지 (완전 삼각형 + 멀티홉)

```
                   MaintQ (제조 설비보전)
                         :9003
                        /     \
    S5 출금 요청 (2단 승인)     S7 화재보험 갱신 (고장이력 연계)
    S6 환헤지 상담             S11 자산변동 통지 / S14 보험금 청구
                      /         \
                     /           \
  FinAllQ (은행 · 증권) ────────── InsuQ (기업/화재 보험)
        :9001        S8 담보대출 검증        :9002
                     S13 비례보상 검증 (멀티홉 릴레이)

       [ QMesh Orchestrator :9000 ] ← 통합 진입점 및 분산 트레이스 수집
```

| 도메인 | 에이전트 | 기술 스택 | A2A 창구 포트 |
|---|---|---|---|
| **조율** | **QMesh Orchestrator** | Python / FastAPI | `:9000` |
| **금융** | **FinAllQ** | Java Spring Boot + Python LangGraph + PostgreSQL (pgvector) | `:9001` |
| **보험** | **InsuQ** | Java Spring + Python FastRAG + PostgreSQL / H2 | `:9002` |
| **제조** | **MaintQ** | Python FastAPI + SQLite + VectorStore | `:9003` |

> 💡 **이종 스택의 캡슐화**: 각 프로젝트의 내부 DB, 백엔드 프레임워크는 외부에 노출되지 않으며, 오직 표준화된 A2A 창구 포트로만 협업합니다.

### 3-1. 실제 사용 패키지 (2026-08-24 실측 — 4개 레포 전수 확인)

**A2A 통신 자체엔 전용 SDK가 없다** — 4개 레포 전부 `FastAPI`+`httpx`+`pydantic`
(Python 3곳) 또는 Spring MVC 직접 구현(InsuQ backend `A2aController`)으로 이 레포의
JSON Schema 계약을 손으로 구현한다. FinAllQ `backend-core`(Java)는 `pom.xml`에
A2A·agent 관련 의존성이 0건 — `a2a_adapter`가 서비스 계정으로 기존 REST API를 그대로
호출하는 구조라 backend-core는 A2A를 아예 인지하지 못한다.

에이전트 오케스트레이션/LLM 패키지는 프로젝트마다 다르다:

| 레포 | 그래프 프레임워크 | LLM SDK | 비고 |
|---|---|---|---|
| **MaintQ** | 없음(자체 Agent Loop) | `anthropic` + `google-genai` + `openai>=3.3.1` — 5종(`gemini`/`anthropic`/`elice`/`openai`/`nvidia`)을 `MAINTQ_LLM_PROVIDER` 한 줄로 갈아 끼운다(`backend/agent/llm.py::PROVIDERS`). **기본 `nvidia`(`openai/gpt-oss-120b`, NIM 무료 티어) + `openai`(`gpt-4.1-mini`) 자동 폴백** | `mcp>=1.28`로 도구(7~20종) 오케스트레이션, `pgvector`로 매뉴얼 검색 |
| **InsuQ** | `langgraph>=0.2.50`(2노드) | `openai>=1.54` — NVIDIA/Gemini/Elice/OpenAI 4개 provider를 `base_url`만 바꿔 감싸는 범용 클라이언트(`generation/llm.py::PROVIDERS`). **실경로는 `openai`(`gpt-4.1-mini`), 폴백 없음** | `mcp>=1.2`, `qdrant-client[fastembed]`, `sentence-transformers`(리랭커) |
| **FinAllQ** | `langgraph==1.2.10` | **없음** — LLM을 아예 안 씀(절대 원칙). `plan`/`synthesize` 노드가 규칙기반/템플릿이라 LLM 호출 0건 | `ai/`(FDS·스미싱 탐지)도 `scikit-learn` 고전 기법뿐, 임베딩·벡터DB 미사용 |

상세 조사 근거는 `docs/session_log/2026-08-24.md` §7 참고(크로스세션으로 FinAllQ·InsuQ
세션에 직접 확인받음).

> **2026-08-29 갱신** — 표의 "LLM SDK"는 **설치된 SDK와 실제 서빙 경로가 다를 수 있다.**
> 두 시스템 모두 provider를 환경변수로 갈아 끼우는 구조라 이 괴리가 반복해서 생긴다
> (직전까지 MaintQ 행이 `google-genai` 실사용으로 적혀 있었으나 D122 이후 사실이
> 아니었다). 그래서 이제 각 행에 **실경로**를 함께 적는다.
>
> **두 시스템이 서로 다른 모델을 쓰는 것은 타협이 아니라 실측 결과다.** 원래는 둘 다
> NVIDIA NIM 무료 티어로 통일하려 했고(`docs/superpowers/plans/2026-08-29-llm-provider-unification.md`),
> MaintQ는 통과했지만 InsuQ는 기각됐다:
>
> - **MaintQ ✅** — `openai/gpt-oss-120b`로 도구 5종을 정확한 인자로 순차 호출하고
>   안전 블록·A2 규칙까지 유지했다. 폴백도 가짜 키 실기동으로 실증했다
> - **InsuQ ❌** — `gpt-oss-120b`가 **`tools` 키를 생략하는 강제답변 턴**
>   (`tool_loop.py::_final_turn`, D14a)에서 출력을 전부 추론에 쏟고 본문을 비운다
>   (`finish_reason=stop`이라 `max_tokens`와 무관). 차점 `nemotron-3-super-120b-a12b`는
>   게이트는 통과하나 과잉거부 0.148·되묻기 정확도 0.5로 **이미 기각된 flash-lite 수준**
>   이다(EXP-056). 검색 지표가 3모델 동일해 차이가 생성 모델에서만 온다는 게 통제됐다
>
> 즉 **파이프라인 구조가 모델 적합성을 가른다** — InsuQ에는 도구를 끄고 답변을 강제하는
> 턴과 8초 라우터·30초 레이턴시 예산이 있고 MaintQ에는 없다. 두 레포의 폴백 래퍼는
> 각자 구현했다(InsuQ는 동기 3메서드, MaintQ는 비동기 `stream()` 하나라 코드를
> 공유하지 않는다). InsuQ 폴백이 비어 있는 것도 의도적이다 — 유일한 대안이 게이트를
> 통과하지 못해, 켜두면 장애 시 더 나쁜 모델로 떨어진다.

---

## 4. 핵심 관통 원칙 & 거버넌스

### ① "돈과 계약이 움직이는 곳에는 반드시 사람의 승인 (Human-in-the-Loop)"
- AI 에이전트는 **요청서, 제안서, 심사 초안까지만** 작성합니다.
- 실제 계좌 출금, 대출 실행, 보험 계약 체결은 반드시 **승인권자의 결정** 뒤에 실행됩니다.
- 자금이 이동하는 작업(S5)은 **2단 승인 계단**(요청 부서 승인 ➔ 집행 부서 재무 승인)을 거칩니다.

### ② 신원 식별: Actor(토큰) vs Subject(페이로드) 분리
- **Actor (인증, Who calls)**: 비대칭 서명된 파트너 액세스 토큰으로 위조 불가능한 신원 증명.
- **Subject (대상, Whose data)**: 페이로드의 `finallq_company_id`, `building_id`, `policy_id`로 처리 대상 명시.
- **3단계 자격증명 스코프**:
  1. `조회/상담` (위험도 0): 제안 및 정보 조회만 가능
  2. `심사` (위험도 저): 심사 결과 판정 (실행 권한 없음)
  3. `자금이동` (위험도 고): `input-required` 기반 2단 승인 필수

### ③ 크로스도메인 분산 트레이스 (`request_chain_id`)
- 모든 A2A 요청/응답 헤더에 `request_chain_id`를 전파하여, `MaintQ ➔ FinAllQ ➔ InsuQ`로 이어지는 멀티홉 여정을 단일 타임라인으로 추적 및 감사 로그에 기록합니다.

---

## 5. 핵심 시나리오 요약

| ID | 시나리오명 | 통신 경로 | 성격 | 주요 스킬 |
|---|---|---|---|---|
| **S5** | 발주 승인 ➔ 출금 요청 | MaintQ ➔ FinAllQ | 자금이동 (2단 승인) | `request-withdrawal` |
| **S6** | 환헤지 / 여유자금 운용 상담 | MaintQ ➔ FinAllQ | 제안/상담 (위험 0) | `advise-hedge` |
| **S7** | 화재보험 갱신 (고장이력 연계) | MaintQ ➔ InsuQ | 상담 + 데이터 연계 | `advise-policy-renewal` |
| **S8** | 담보 대출 심사 시 보험 검증 | MaintQ ➔ FinAllQ ➔ InsuQ | **멀티홉 릴레이** | `assess-loan`, `verify-collateral-insurance` |
| **S11** | 설비 개조/폐기 자산변동 통지 | MaintQ ➔ InsuQ | 원장 갱신 통지 | `notify-asset-change` |
| **S13** | 중고설비 담보대출 (비례보상) | MaintQ ➔ FinAllQ ➔ InsuQ | 멀티홉 심사 | `assess-used-equipment-loan`, `verify-collateral-insurance` |
| **S14** | 설비 사고 발생 보험금 청구 | MaintQ ➔ InsuQ | 청구 접수/조사 | `claim-insurance` |
| **S15** | 전손 교체 금융 상담 | MaintQ ➔ FinAllQ | 연쇄 금융 제안 | `advise-replacement-financing` |
| **S16** | 신규 설비 도입 자금조달 비교 | MaintQ ➔ FinAllQ | 비교 상담 | `advise-financing` |

---

## 6. 빠른 시작 (Quick Start)

### 1) 환경 설정
```bash
cp .env.example .env
# 각 도메인 에이전트 주소 및 목업 인증 토큰 설정
```

### 2) 통합 기동
```bash
docker-compose up -d
```

### 3) 에이전트 헬스체크 및 Agent Card 조회
```bash
# Orchestrator 상태 확인
curl http://localhost:9000/health

# FinAllQ Agent Card 확인
curl http://localhost:9001/.well-known/agent-card.json
```

---

## 7. 관련 문서
- [신원 식별 및 보안 아키텍처 결정서 (A2A_IDENTITY.md)](docs/A2A_IDENTITY.md)
- [A2A 크로스도메인 시나리오 상세 명세 (11_A2A_SCENARIOS.md)](docs/A2A_SCENARIOS.md)
- [표준 Task 스키마 정의 (docs/schemas/)](docs/schemas/)
