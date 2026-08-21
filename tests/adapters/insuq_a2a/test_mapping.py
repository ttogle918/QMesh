import json
import re
from pathlib import Path

from adapters.insuq_a2a.mapping import _format_evidence, map_qa_response


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


def test_completed_forwards_confirm_required_when_present():
    qa_response = {
        "answer": "일부 보장됩니다.",
        "verdict": "지급 사유에 해당할 가능성이 높음",
        "evidence": [
            {
                "product": "든든실손4세대",
                "policy_part": "보통약관",
                "article_no": "제5조",
                "clause_no": None,
                "page": None,
            }
        ],
        "needs_clarification": False,
        "clarify_questions": [],
        "confirm_required": ["가입 시기를 확인해 주세요"],
    }

    result = map_qa_response(qa_response)

    assert result["status"] == "completed"
    assert result["confirm_required"] == ["가입 시기를 확인해 주세요"]


def test_format_evidence_omits_empty_string_clause_no():
    result = _format_evidence(
        {"product": "든든실손4세대", "policy_part": "특별약관", "article_no": "제1조", "clause_no": "", "page": None}
    )

    assert result == "든든실손4세대 특별약관 제1조"


def test_format_evidence_output_matches_schema_pattern():
    schema_path = Path(__file__).resolve().parents[3] / "docs" / "schemas" / "lookup-clause.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    pattern = re.compile(schema["response"]["properties"]["evidence"]["items"]["pattern"])

    cases = [
        {"product": "든든실손4세대", "policy_part": "보통약관", "article_no": "제5조", "clause_no": "①", "page": 13},
        {"product": "든든실손4세대", "policy_part": "특별약관", "article_no": "제1조", "clause_no": None, "page": None},
        {"product": "든든실손4세대", "policy_part": "특별약관", "article_no": "제1조", "clause_no": "", "page": None},
        {"product": "든든실손4세대", "policy_part": "보통약관", "article_no": "제2조", "clause_no": "3항", "page": 7},
    ]

    for case in cases:
        formatted = _format_evidence(case)
        assert pattern.match(formatted), f"{formatted!r} does not match schema pattern {pattern.pattern!r}"
