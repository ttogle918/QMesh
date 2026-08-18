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
│   └── schemas/               # Task 요청/응답 표준 JSON Schema (12종)
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
│       └── request-settlement.json            # 정산 요청
└── adapters/                  # 각 레포에 얹을 A2A 어댑터 견본 (Templates)
    ├── finallq_a2a.py
    ├── insuq_a2a.py
    └── maintq_a2a.py
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
