from adapters.insuq_a2a.mapping import map_qa_response


def test_completed_with_evidence():
    qa_response = {
        "route": "verdict",
        "answer": "자기부담금은 보통약관 제5조에 따라 20%입니다.",
        "verdict": "지급 사유에 해당할 가능성이 높음",
        "evidence": [
            {
                "product": "든든실손4세대",
                "policy_part": "보통약관",
                "article_no": "제5조",
                "clause_no": "①",
                "page": 13,
                "quote": "자기부담금은 20%로 한다.",
            },
            {
                "product": "든든실손4세대",
                "policy_part": "특별약관",
                "article_no": "제1조",
                "clause_no": None,
                "page": None,
                "quote": "특약 적용 범위는...",
            },
        ],
        "needs_clarification": False,
        "clarify_questions": [],
    }

    result = map_qa_response(qa_response)

    assert result["status"] == "completed"
    assert result["answer"] == qa_response["answer"]
    assert result["verdict"] == qa_response["verdict"]
    assert result["evidence"] == [
        "든든실손4세대 보통약관 제5조 ①, p.13",
        "든든실손4세대 특별약관 제1조",
    ]


def test_rejected_when_no_evidence():
    qa_response = {
        "route": "simple_lookup",
        "answer": None,
        "verdict": None,
        "evidence": [],
        "needs_clarification": False,
        "clarify_questions": [],
    }

    result = map_qa_response(qa_response)

    assert result["status"] == "rejected"
    assert result["rejection_reason"] == "no_evidence_found"
    assert result["evidence"] == []


def test_input_required_when_needs_clarification():
    qa_response = {
        "route": "clarify",
        "answer": None,
        "verdict": None,
        "evidence": [],
        "needs_clarification": True,
        "clarify_questions": ["가입하신 상품명을 알려주세요", "가입 시기를 알려주세요"],
    }

    result = map_qa_response(qa_response)

    assert result["status"] == "input-required"
    assert result["confirm_required"] == qa_response["clarify_questions"]
    assert result["evidence"] == []


def test_needs_clarification_takes_priority_over_empty_evidence():
    """evidence가 비어있어도 needs_clarification=True면 rejected가 아니라 input-required다."""
    qa_response = {
        "evidence": [],
        "needs_clarification": True,
        "clarify_questions": ["상품명을 알려주세요"],
    }

    result = map_qa_response(qa_response)

    assert result["status"] == "input-required"
