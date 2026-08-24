# Agent 계층도 & AI 노드 흐름도 (InsuQ · MaintQ · FinAllQ)

**작성 기준:** 2026-08-24, 세 레포지토리(`../InsuQ`, `../MaintQ`, `../FinAllQ`)의 실제 코드를 직접 읽어 작성.
**주의:** 각 레포의 기존 문서(`InsuQ/docs/05_ARCHITECTURE.md`, `FinAllQ/docs/architecture.md`)에는 아직 구현되지 않은 구상 단계(aspirational) 다이어그램이 섞여 있습니다. 아래 다이어그램은 **실제 구현된 흐름**을 우선하고, 구상 단계와 다른 부분은 각주로 표시했습니다.

---

## 0. 전체 개요 — Cross-repo A2A 메시

세 시스템 모두 A2A(Agent-to-Agent) 프로토콜로 연결되지만 역할이 다릅니다. **MaintQ는 항상 요청자(client)**이고, FinAllQ와 InsuQ는 응답자(responder)입니다. FinAllQ는 일부 시나리오에서 InsuQ에 대해 2차 홉 요청자 역할도 겸합니다.

```mermaid
flowchart LR
    subgraph MaintQ["MaintQ (설비보전) — 항상 A2A 요청자"]
        MQ_LOOP["backend/agent/loop.py<br/>단일 Agent Loop<br/>(LLM ⇄ MCP 도구, 세션 최대 50회)"]
        MQ_MCP["mcp_server<br/>core 7 / full 20 도구"]
        MQ_A2A["backend/a2a/client.py<br/>call_skill()"]
        MQ_LOOP --> MQ_MCP
        MQ_MCP -->|"search_insurance_clause /<br/>assess_equipment_loan (HTTP 프록시)"| MQ_A2A
    end

    subgraph FinAllQ["FinAllQ (여신) — 응답자 + 2차 홉 요청자"]
        FQ_ADAPTER["a2a_adapter (9101)<br/>request-withdrawal / advise-hedge /<br/>assess-loan / advise-financing 구현<br/>(나머지 3개 스킬은 501)"]
        FQ_INSUQ_CLIENT["insuq_client.py<br/>verify-collateral-insurance"]
        FQ_ADAPTER --> FQ_INSUQ_CLIENT
    end

    subgraph InsuQ["InsuQ (보험) — 응답자"]
        IQ_ADAPTER["a2a_adapter (9102)<br/>lookup-clause만 구현<br/>(나머지 5개 스킬은 501)"]
    end

    MQ_A2A -->|"assess-loan"| FQ_ADAPTER
    MQ_A2A -->|"lookup-clause"| IQ_ADAPTER
    FQ_INSUQ_CLIENT -->|"verify-collateral-insurance"| IQ_ADAPTER

    HUB["A2A_Q (통합 허브)<br/>Agent Card SSOT · A2A_CONTRACTS.md"]
    HUB -.Agent Card 배포.-> MQ_A2A
    HUB -.Agent Card 배포.-> FQ_ADAPTER
    HUB -.Agent Card 배포.-> IQ_ADAPTER
```

> `docs/A2A_CONTRACTS.md`(MaintQ)에는 트리거→스킬 매핑이 10건 정의되어 있지만, 실제로 코드로 연결된 것은 `lookup-clause`·`assess-loan` 2건뿐입니다. 나머지는 계약 문서상으로만 존재합니다.

> **2026-08-24 갱신 — 위 다이어그램의 `InsuQ` 서브그래프는 ai-engine의 `a2a_adapter`(:9102, FastAPI)만
> 그린 것입니다.** 이 어댑터 자체는 지금도 `lookup-clause`만 구현하고 나머지가 501인 것이 맞지만,
> InsuQ에는 이 다이어그램에 없는 **두 번째 A2A 창구**가 있습니다 — `backend`(Spring, :8081)의
> `A2aController`입니다. Sprint 13(A2A 트랙7)이 main에 병합되면서 이 backend 창구가
> `verify-collateral-insurance`·`advise-policy-renewal`·`notify-asset-change`·`claim-insurance`
> 4개 스킬을 실제로 서빙합니다(서비스 간 인증·request_chain_id 감사로그·Idempotency-Key·A2A Task
> 상태머신 포함). **2026-08-24 갱신 — `notify-risk-change`(S14)도 Sprint 14로 구현 완료**
> (Dev→Tester→Reviewer 게이트 통과, `feat/notify-risk-change` → main 머지, 실 컨테이너 재빌드 후
> curl로 정상 판정·대역 경계·Idempotency 재생/충돌·거부 경로 6종 직접 검증).
> 즉 InsuQ의 "구현된 스킬"은 위 다이어그램의 1개(`lookup-clause`)가 아니라 **두 창구를 합쳐 5개 중
> 5개 전부**입니다. 501로 남은 것은 이 다이어그램이 그린 `lookup-clause` 하나뿐입니다. 최신
> 상태는 InsuQ 레포의 `docs/status_audit.html`을 참고하세요(main 커밋 `687d616`).

---

## 1. InsuQ — 보험 약관 Q&A

### 1.1 Agent 계층도

InsuQ는 "멀티 에이전트"가 아니라 **얇은 LangGraph 라우터 + 절차형 파이프라인** 구조입니다. `docs/05_ARCHITECTURE.md`가 언급하는 "Supervisor-Worker 멀티 에이전트"는 향후 계획(Track 2)이며 현재 코드에는 없습니다.

```mermaid
flowchart TD
    API["ai-engine/api/main.py<br/>FastAPI /qa, /qa/stream<br/>(도메인별 그래프 1개씩 컴파일)"]
    API --> GRAPH["agent/graph.py<br/>LangGraph (route → clarify, 2노드)"]
    GRAPH -->|"route != CLARIFY"| PIPE["pipeline.py<br/>answer_question_stream()<br/>(그래프 밖 절차형 코드)"]

    PIPE --> RET["retrieval/*<br/>하이브리드 검색<br/>(vector + BM25 + HyDE + rerank)"]
    PIPE --> DEF1["Defense① 사전 거부<br/>근거 부족 시 즉시 유보"]
    PIPE --> HOP["agent/multihop.py<br/>expand_via_refs() (깊이 2~3)"]
    PIPE --> GEN{"생성 전략"}
    GEN -->|"고정 컨텍스트"| GEN1["_stream_with_fixed_context()"]
    GEN -->|"도구 호출 루프"| TOOLLOOP["tool_loop.py<br/>run_tool_loop_stream()"]
    TOOLLOOP --> T1["tools/clause_tools.py<br/>search_clauses()"]
    TOOLLOOP --> T2["tools/clause_tools.py<br/>get_article()"]
    PIPE --> DEF2["Defense② 사후 검증<br/>인용·조항 불일치 검사"]
    PIPE --> VERDICT["agent/verdict.py<br/>decide() / build_confirm_required()"]

    subgraph A2A["a2a_adapter (별도 프로세스, :9102)"]
        SKILL["POST /a2a/skills/lookup-clause<br/>(구현됨 — 나머지 5개 스킬은 501)"]
    end
    SKILL -->|"HTTP"| API

    style GRAPH fill:#e8f4ff
    style A2A fill:#fff4e6
```

> `ai-engine/insuq_ai/mcp_server/__init__.py`는 빈 스텁입니다. `05_ARCHITECTURE.md`가 그리는 "MCP 서버 노출" 화살표는 아직 구현되지 않았습니다.

### 1.2 AI 노드 흐름도

**(a) 실제 LangGraph — 노드가 2개뿐입니다.** `05_ARCHITECTURE.md`의 `stateDiagram-v2`(Routing→Retrieve→Rerank→HopCheck→Generate→Verdict→...)는 구상 단계이며, 실제 컴파일된 그래프는 아래가 전부입니다.

```mermaid
stateDiagram-v2
    [*] --> route
    route --> clarify
    clarify --> [*]: END

    note right of route
        router.classify(): 키워드 우선 + LLM 3단 분류
        (simple_lookup / verdict / clarify)
        COMPARE → SIMPLE_LOOKUP 강등
    end note
    note right of clarify
        route != CLARIFY면 통과(no-op)
        clarify_enabled=false 또는
        필수 슬롯 충족 시 VERDICT로 강등
        아니면 missing_slots/질문 채움
    end note
```

**(b) 실제 답변 생성 실행 흐름 (그래프 노드가 아닌 절차형 코드)** — `route_and_answer_stream()`이 그래프 밖에서 `pipeline.py`를 호출하는 파이썬 분기입니다.

```mermaid
flowchart TD
    START(["질문 수신"]) --> ROUTE["route 노드: 의도 분류"]
    ROUTE -->|"CLARIFY 확정"| ASK["clarify 노드: 되묻기 응답"] --> ENDA(["END"])
    ROUTE -->|"CLARIFY 아님"| PSTART["pipeline.answer_question_stream() 호출"]
    PSTART --> SEARCH["하이브리드 검색"]
    SEARCH --> D1{"근거 있음?"}
    D1 -->|"아니오"| REFUSE["Defense① 사전 거부"] --> ENDA
    D1 -->|"예"| HOPCHECK["참조조항(refs) 확장 (깊이 2~3)"]
    HOPCHECK --> GENN["생성: 고정 컨텍스트<br/>또는 도구 호출 루프"]
    GENN --> DEF2["Defense② 사후 검증<br/>(인용/조항 불일치 검사)"]
    DEF2 --> VERDICT{"판정 3단계"}
    VERDICT -->|"가능성 높음/낮음"| OUT["근거 인용 + 답변"] --> ENDA
    VERDICT -->|"판단 유보"| FALLBACK["분쟁조정 사례 폴백 검색"] --> GENN
```

---

## 2. MaintQ — 설비 보전 에이전트

### 2.1 Agent 계층도

LangGraph를 쓰지 않는 **단일 에이전트 루프**(`backend/agent/loop.py`) 구조입니다. 라우터/서브에이전트 분기가 없고, 도구 실행만 MCP 서버로 위임합니다.

```mermaid
flowchart TD
    UI["정비사 UI"] --> API["FastAPI /api/chat<br/>routers/chat.py"]
    API --> LOOP["agent/loop.py :: run_turn()<br/>단일 Agent Loop<br/>(세션당 최대 LLM 호출 50회)"]
    LOOP --> LLM["agent/llm.py<br/>LlmClient (Gemini 2.5 Flash)"]
    LOOP --> MCPC["agent/mcp_client.py<br/>McpClient (stdio, lifespan 단일 세션)"]
    MCPC --> MCPS["mcp_server/server.py<br/>FastMCP(&quot;maintq&quot;)"]

    subgraph CORE["core 프로파일 (7개, 항상 등록)"]
        C1["lookup_error_code / rag_search_manual /<br/>search_inventory / find_alternative_parts /<br/>get_supplier_quotes / get_error_history"]
        C7["create_po_draft (유일한 쓰기 도구)"]
    end
    subgraph FULL["full 프로파일 추가 (13개)"]
        F1["check_disposal_blockers 외 11개"]
        F2["search_insurance_clause (A2A 프록시)"]
        F3["assess_equipment_loan (A2A 프록시)"]
    end
    MCPS --> CORE
    MCPS --> FULL

    F2 -->|"HTTP"| A2AR["routers/a2a.py<br/>/api/a2a/lookup-clause"]
    F3 -->|"HTTP"| A2AR2["routers/a2a.py<br/>/api/a2a/assess-loan"]
    A2AR --> A2ACLI["a2a/client.py<br/>call_skill(partner)"]
    A2AR2 --> A2ACLI
    A2ACLI -->|"InsuQ :9102"| IQ["InsuQ a2a_adapter"]
    A2ACLI -->|"FinAllQ :9101"| FQ["FinAllQ a2a_adapter"]

    style LOOP fill:#e8f4ff
```

> `mcp_server` 프로세스는 파트너 자격증명을 직접 들고 있지 않고, 인증은 `backend/a2a/auth_header.py::build_auth_header()`가 담당합니다(D15/D93 설계 원칙 — 단 **스킴 자체는 2026-08-24에 D120으로 Basic에서 Bearer+`X-A2A-Partner-Id`로 교체**됐습니다. InsuQ·FinAllQ 실 인증 필터와 대조한 결과였습니다).

### 2.2 AI 노드 흐름도 — Agent Loop 제어 흐름

LangGraph가 없으므로 "노드 그래프"보다 **루프백 엣지가 있는 플로우차트**가 실제 구조에 더 가깝습니다 (`run_turn()`, `backend/agent/loop.py:316-656`).

```mermaid
flowchart TD
    START(["사용자 메시지 수신"]) --> G1{"세션 LLM 호출 ≥ 50?"}
    G1 -->|"예"| ENDX(["END: 대화 종료 안내"])
    G1 -->|"아니오"| CTX["장비 모델 조회 + 도구 목록 로드<br/>+ 히스토리에 사용자 메시지 추가"]
    CTX --> TURNLOOP["LLM 스트림 호출 시작<br/>(최대 10회/턴)"]

    TURNLOOP --> G2{"턴 LLM 호출 ≥ 10?"}
    G2 -->|"예"| WRAP["강제 종료"] --> POST
    G2 -->|"아니오"| STREAM["LLM 스트림 수신<br/>(text / tool_use / end / error)"]
    STREAM -->|"error"| FAIL["실패 토큰 emit"] --> ENDX
    STREAM --> FLUSH["text 버퍼 flush<br/>(필요 시 safety 블록 선삽입)"]
    FLUSH --> PENDING{"tool_use 요청 있음?"}
    PENDING -->|"없음"| POST["루프 종료 → 후처리"]
    PENDING -->|"있음"| TOOLCHECK{"턴 도구 호출 ≥ 8<br/>또는 직전과 동일 호출?"}
    TOOLCHECK -->|"예"| WRAP2["도구 실행 중단 안내"] --> POST
    TOOLCHECK -->|"아니오"| CALL["tool_call emit → MCP 도구 실행<br/>→ tool_result emit"]
    CALL --> HIST["결과를 히스토리에 추가<br/>(replacement_ctx/pages/repeated 갱신)"]
    HIST --> TURNLOOP

    POST --> CITE{"인용 페이지 있음?"}
    CITE -->|"예"| CITEBLK["citation 블록 emit"] --> POCHECK
    CITE -->|"아니오"| POCHECK{"po_created?"}
    POCHECK -->|"예"| POCARD["po_card(draft) emit"] --> ENDX2(["END"])
    POCHECK -->|"아니오"| REPCHECK{"repeated<br/>(반복 고장 감지)?"}
    REPCHECK -->|"예"| HOLD["po_card(hold) emit<br/>(발주 보류, S3 정책)"] --> ENDX2
    REPCHECK -->|"아니오"| ENDX2
```

---

## 3. FinAllQ — 여신 심사 / 금융

### 3.1 Agent 계층도

FinAllQ는 세 시스템 중 유일하게 **실제 LangGraph 오케스트레이터**(`mcp/hub`)를 갖고 있지만, `docs/architecture.md:28`이 명시하듯 **이 그래프 안에 LLM은 없습니다** — 계획(plan)과 합성(synthesize) 모두 규칙/템플릿 기반입니다.

```mermaid
flowchart TD
    subgraph Mesh["A2A 메시"]
        MAINTQ["MaintQ (요청자)"] -->|"assess-loan 등"| ADAPTER
        ADAPTER["a2a_adapter (9101)<br/>request-withdrawal/advise-hedge/<br/>assess-loan/advise-financing 구현<br/>(나머지 3개 스킬은 501)"]
        ADAPTER -->|"2차 홉: verify-collateral-insurance"| INSUQ["InsuQ a2a_adapter"]
        ADAPTER --> FQCLIENT["finallq_client.py<br/>backend-core REST 래핑"]
    end

    UI["프론트엔드"] --> BC["backend-core<br/>AgentQueryController"]
    BC --> AQS["AgentQueryService → McpQueryClient"]
    AQS -->|"X-User-Authorization 전달"| HUB["mcp/hub<br/>/mcp/v1/orchestrate/query"]
    HUB --> RUNNER["GraphRunner.run_query()<br/>(Redis 캐시 확인 후 그래프 실행)"]
    RUNNER --> GRAPH["graph/flows/query_flow.py<br/>LangGraph StateGraph"]

    GRAPH -->|"channel=node (3종)"| AGENTCLI["AgentClient / AgentRegistry"]
    AGENTCLI --> FDS["mcp/agents/fds<br/>fds.score"]
    AGENTCLI --> PORT["mcp/agents/portfolio<br/>portfolio.rebalance"]
    AGENTCLI --> SMS["mcp/agents/sms_detector<br/>sms.classify"]

    GRAPH -->|"channel=backend (17종)"| BACKCLI["BackendClient"]
    BACKCLI --> BC

    FDS -.SSOT 로직 재사용.-> AISVC["ai/ FastAPI 서비스<br/>(규칙/템플릿 기반, LLM 없음)"]
    PORT -.-> AISVC
    SMS -.-> AISVC

    style GRAPH fill:#e8f4ff
    style AISVC fill:#f0f0f0
```

> `docs/architecture.md`의 기존 mermaid 다이어그램에는 `G[LLM / LangGraph - 설명용]` 노드가 있지만, 이는 이 그래프보다 먼저 작성된 오래된/구상 단계 다이어그램이며 실제 구현(LLM 없음)과 다릅니다.

### 3.2 AI 노드 흐름도 — 실제 LangGraph (`mcp/hub/app/graph/flows/query_flow.py`)

```mermaid
flowchart TD
    START(["질의 수신 (GraphState 초기화)"]) --> PLAN["plan 노드<br/>규칙 기반 키워드 매칭으로<br/>최대 3개 도구 선정 (LLM 아님)"]
    PLAN --> P1{"계획된 도구 있음?"}
    P1 -->|"없음"| SYN
    P1 -->|"있음"| SELECT["tool_select 노드<br/>steps++"]

    SELECT --> S1{"steps > max_steps<br/>또는 cursor 끝?"}
    S1 -->|"예"| SYN["synthesize 노드<br/>화이트리스트 필드만 템플릿 조립<br/>(LLM 아님)"]
    S1 -->|"아니오"| CALL["tool_call 노드<br/>인자 도출 + 실행<br/>(node/backend 채널)"]

    CALL --> OBSERVE["observe 노드<br/>결과 분류: OK / SKIPPED / FAILED"]
    OBSERVE --> O1{"재시도 가능한 FAILED?<br/>(5xx/timeout, 최대 2회/도구)"}
    O1 -->|"예 (retry_pending)"| CALL
    O1 -->|"아니오"| SELECT

    SYN --> RESPOND["respond 노드<br/>auth_header 제거 후 응답"]
    RESPOND --> ENDX(["END"])
```

---

## 4. 세 시스템 비교 요약

| 항목 | InsuQ | MaintQ | FinAllQ |
|---|---|---|---|
| **그래프 프레임워크** | LangGraph (2노드만) | 없음 (직접 구현 루프) | LangGraph (6노드) |
| **그래프 안 LLM 존재?** | 예 (생성은 그래프 밖 파이프라인) | 예 (루프 안에서 매 턴 호출) | **아니오** (plan/synthesize 모두 규칙 기반) |
| **실제 "멀티 에이전트"?** | 아니오 (단일 라우터 + 절차형 파이프라인) | 아니오 (단일 에이전트 루프) | 부분적 (하위 MCP 에이전트 노드 3종: fds/portfolio/sms, LLM 없는 결정론적 서비스) |
| **A2A 역할** | 응답자 (스킬 1/6 구현) | 항상 요청자 | 응답자 + 2차 홉 요청자 (스킬 4/7 구현) |
| **도구 호출 방식** | LLM 도구 호출 루프 (선택적) | LLM 도구 호출 루프 (매 턴 필수 아님) | 그래프 노드가 도구 채널(node/backend) 직접 호출 |
| **루프/재시도 상한** | 없음 (그래프 자체가 짧음) | 세션 50회 / 턴 10회 / 도구 8회 | 도구별 재시도 최대 2회 |
| **기존 문서와의 차이** | `05_ARCHITECTURE.md`의 6노드 상태도는 구상 단계, 실제는 2노드 | `09_RUNTIME.md`는 시퀀스 다이어그램만 보유 (정확) | `architecture.md`의 LLM 노드는 구상 단계, 실제는 LLM 없음 |

---

**관련 문서:**
- `InsuQ/docs/05_ARCHITECTURE.md` — 기존 mermaid (일부 구상 단계)
- `MaintQ/docs/09_RUNTIME.md` — 기존 시퀀스 다이어그램 (실제 흐름과 일치)
- `FinAllQ/docs/architecture.md` — 기존 mermaid (FDS 흐름, 일부 구상 단계)
- `docs/A2A_CONTRACTS.md` (MaintQ) — 나가는 요청 트리거→스킬 매핑 (10건 정의, 2건 구현)
- `docs/presentation/README.md` (본 레포) — 세 프로젝트 성능/기술 비교 요약
