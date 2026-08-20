# 프로젝트: AI 기반 FDS & 기업 자금 관리 대시보드
# API 명세서 (v1.0)

이 문서는 React(Frontend), Spring Boot(Core Backend), FastAPI(AI Backend) 스택을 기반으로 한 B2B 금융 대시보드 API를 정의합니다.

* **Spring Boot Base URL:** `/api/v1`
* **FastAPI Base URL:** `/ai/v1` (AI/MCP 서버)

---

## 1. 🗂️ 핵심 백엔드 (Spring Boot)

### 1.1. 인증 및 권한 (Auth)

B2B 환경을 고려하여 JWT 기반 인증 및 역할(ADMIN, MANAGER, USER) 기반 권한 관리(RBAC)를 전제합니다.

#### 1.1.1. 로그인
* **[POST]** `/api/v1/auth/login`
* **Description:** 이메일, 패스워드로 로그인하여 Access/Refresh 토큰을 발급받습니다.
* **Request Body:**
    ```json
    {
      "email": "user@company.com",
      "password": "password123"
    }
    ```
* **Success Response (200 OK):**
    ```json
    {
      "grantType": "Bearer",
      "accessToken": "ey...",
      "refreshToken": "ey...",
      "userName": "김재무",
      "role": "MANAGER"
    }
    ```
* **Error Response (401 Unauthorized):**
    ```json
    {
      "code": "AUTH_001",
      "message": "이메일 또는 비밀번호가 일치하지 않습니다."
    }
    ```

#### 1.1.2. 회원 가입 (기업 사용자 등록)
* **[POST]** `/api/v1/auth/join`
* **Description:** 신규 사용자를 등록합니다. (실제 B2B에서는 '초대' 방식이 일반적)
* **Request Body:**
    ```json
    {
      "email": "newbie@company.com",
      "password": "new_password123",
      "userName": "박신입",
      "companyId": 1
    }
    ```
* **Success Response (201 Created):**
    ```json
    {
      "userId": 12,
      "email": "newbie@company.com",
      "userName": "박신입",
      "role": "USER"
    }
    ```

---

### 1.2. 계좌 (Accounts)

기업이 보유한 여러 금융사(은행, 카드)의 계좌를 통합 관리합니다.

#### 1.2.1. 통합 계좌 목록 조회
* **[GET]** `/api/v1/accounts`
* **Description:** (인증 필요) 현재 로그인한 기업이 등록한 모든 계좌의 목록과 총 잔액을 조회합니다.
* **Success Response (200 OK):**
    ```json
    {
      "totalBalance": 1500000000,
      "accounts": [
        {
          "accountId": "acc_001",
          "bankName": "A은행",
          "accountNumber": "110-234-567890",
          "balance": 1200000000,
          "accountType": "PRIMARY"
        },
        {
          "accountId": "acc_002",
          "bankName": "B증권",
          "accountNumber": "220-456-789012",
          "balance": 300000000,
          "accountType": "SAVING"
        }
      ]
    }
    ```

#### 1.2.2. 특정 계좌 상세 조회 (거래 내역)
* **[GET]** `/api/v1/accounts/{accountId}`
* **Description:** (인증 필요) 특정 계좌의 상세 정보와 최근 거래 내역을 조회합니다.
* **Success Response (200 OK):**
    ```json
    {
      "accountId": "acc_001",
      "bankName": "A은행",
      "accountNumber": "110-234-567890",
      "balance": 1200000000,
      "history": [
        {
          "transactionId": "t_901",
          "date": "2025-10-27T10:30:00",
          "type": "DEPOSIT",
          "amount": 5000000,
          "memo": "(주)거래처A"
        },
        {
          "transactionId": "t_900",
          "date": "2025-10-26T15:00:00",
          "type": "WITHDRAW",
          "amount": -25000000,
          "memo": "직원 급여 이체"
        }
      ]
    }
    ```

---

### 1.3. 거래 및 결재 (Transfers)

B2B의 핵심인 '결재 라인'이 포함된 송금 기능입니다.

#### 1.3.1. 송금 요청 (결재 상신)
* **[POST]** `/api/v1/transfers/request`
* **Description:** (ROLE: USER, MANAGER) 송금을 위한 결재를 요청(상신)합니다.
* **Request Body:**
    ```json
    {
      "fromAccountId": "acc_001",
      "toBankCode": "088",
      "toAccountNumber": "100-123-456789",
      "amount": 15000000,
      "memo": "10월분 물품 대금"
    }
    ```
* **Success Response (202 Accepted):**
    ```json
    {
      "transferId": "tf_550",
      "status": "PENDING_APPROVAL",
      "requesterName": "박신입",
      "requestedAt": "2025-10-27T21:30:00"
    }
    ```

#### 1.3.2. 송금 승인 (FDS 연동)
* **[POST]** `/api/v1/transfers/{transferId}/approve`
* **Description:** (ROLE: MANAGER, ADMIN) 대기 중인 송금을 승인합니다. **(★ 핵심 FDS 호출 지점 ★)**
* **Success Response (200 OK) - [FDS: ALLOW]:** (정상 승인 완료)
    ```json
    {
      "transferId": "tf_550",
      "status": "COMPLETED",
      "message": "송금이 정상적으로 완료되었습니다."
    }
    ```
* **Success Response (202 Accepted) - [FDS: REQUIRE_2FA]:** (추가 인증 필요)
    ```json
    {
      "transferId": "tf_550",
      "status": "PENDING_2FA",
      "message": "FDS 탐지: 고위험 거래로 분류되어 추가 인증(OTP)이 필요합니다."
    }
    ```
* **Error Response (403 Forbidden) - [FDS: BLOCK]:** (거래 차단)
    ```json
    {
      "transferId": "tf_550",
      "status": "BLOCKED",
      "code": "FDS_001",
      "message": "FDS 탐지: 비정상 거래로 분류되어 자동 차단되었습니다. (사유: E01, E05)"
    }
    ```

#### 1.3.3. 승인 대기 목록 조회
* **[GET]** `/api/v1/transfers/pending`
* **Description:** (ROLE: MANAGER, ADMIN) 내가 승인해야 할 송금 요청 목록을 조회합니다.
* **Success Response (200 OK):**
    ```json
    [
      {
        "transferId": "tf_550",
        "requesterName": "박신입",
        "amount": 15000000,
        "toBankName": "신한은행",
        "toAccountNumber": "100-123-456789",
        "requestedAt": "2025-10-27T21:30:00"
      }
    ]
    ```

---

## 2. 🧠 AI / FDS (FastAPI)

Spring Boot 백엔드 서버가 내부적으로 호출하는 AI 서버 API입니다.

### 2.1. (FDS) 실시간 이상거래 탐지
* **[POST]** `/ai/v1/fds/predict`
* **Description:** (Called by Spring Boot) 송금 승인 시점에 거래 데이터를 받아 위험도를 실시간으로 분석합니다.
* **Request Body:**
    ```json
    {
      "userId": 12,
      "userRole": "USER",
      "amount": 15000000,
      "toAccountNumber": "100-123-456789",
      "accessIp": "121.121.121.121",
      "accessTime": "21:30:00",
      "device": "MOBILE_APP",
      "userPatterns": {
        "avgAmount": 1200000,
        "usualTime": ["09:00-18:00"],
        "recentAccessLocation": "SEOUL"
      }
    }
    ```
* **Success Response (200 OK):**
    ```json
    {
      "riskScore": 0.85,
      "action": "BLOCK",
      "reasonCodes": ["E01", "E05"]
    }
    ```
    * `action`: "ALLOW" (승인), "REQUIRE_2FA" (추가 인증), "BLOCK" (차단)
    * `reasonCodes`: FDS 룰 코드 (E01: 평소 시간대 아님, E05: 평균 금액 10배 초과 등)

### 2.2. (XAI) 설명 가능한 FDS
* **[POST]** `/ai/v1/fds/explain`
* **Description:** (Called by Spring Boot or React) FDS 탐지 사유 코드를 자연어로 설명합니다. (FDS 관리자 대시보드용)
* **Request Body:**
    ```json
    {
      "reasonCodes": ["E01", "E05"],
      "lang": "ko"
    }
    ```
* **Success Response (200 OK):**
    ```json
    {
      "explanation": "이 거래는 [평소 거래 시간(09~18시) 외 발생(E01)], [평균 송금액(120만원) 대비 10배 초과(E05)] 사유로 위험도가 높게 측정되었습니다."
    }
    ```

### 2.3. (AI Agent) 재무 비서 챗봇 (LangGraph)
* **[POST]** `/ai/v1/agent/chat`
* **Description:** (Called by React) LangGraph 기반 AI 재무 비서에게 자연어 질문을 합니다.
* **Request Body:**
    ```json
    {
      "userId": 10,
      "companyId": 1,
      "query": "최근 3개월간 가장 지출이 많았던 거래처 Top 3 알려줘."
    }
    ```
* **Success Response (200 OK):**
    ```json
    {
      "query": "최근 3개월간 가장 지출이 많았던 거래처 Top 3 알려줘.",
      "answer": "내부 데이터를 분석한 결과, 최근 3개월간 지출액 기준 Top 3 거래처는 다음과 같습니다.\n1. (주)A부품 (1억 2천만원)\n2. (주)B로지스 (8천만원)\n3. (주)C솔루션 (5천 5백만원)"
    }
    ```