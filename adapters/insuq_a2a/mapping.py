"""InsuQ ai-engine QaResponse(dict) -> lookup-clause A2A response(dict) 변환.

원본 응답 모양: InsuQ/ai-engine/insuq_ai/api/schemas.py 의 QaResponse. 그 파이썬
클래스는 import하지 않는다(레포 간 결합 방지) — ai-engine이 HTTP로 실제로 돌려주는
JSON을 dict로 그대로 받는다.

분기 규칙:
1. needs_clarification=True -> input-required (evidence가 비어있어도 우선)
2. 그 외 evidence가 비어있음 -> rejected(no_evidence_found)
3. 그 외 -> completed
"""

from __future__ import annotations


def map_qa_response(qa_response: dict) -> dict:
    if qa_response.get("needs_clarification"):
        return {
            "status": "input-required",
            "confirm_required": qa_response.get("clarify_questions", []),
            "evidence": [],
        }

    formatted_evidence = [_format_evidence(item) for item in qa_response.get("evidence", [])]

    if not formatted_evidence:
        return {
            "status": "rejected",
            "rejection_reason": "no_evidence_found",
            "evidence": [],
        }

    return {
        "status": "completed",
        "answer": qa_response.get("answer"),
        "verdict": qa_response.get("verdict"),
        "evidence": formatted_evidence,
    }


def _format_evidence(item: dict) -> str:
    """"{product} {policy_part} {article_no}[ {clause_no}][, p.{page}]" 형식 문자열 조립.

    clause_no·page 가 없으면(None) 그 토막을 통째로 생략한다 — "p.None"이 나가면
    인용 신뢰가 무너진다.
    """
    text = f"{item['product']} {item['policy_part']} {item['article_no']}"
    clause_no = item.get("clause_no")
    if clause_no is not None:
        text += f" {clause_no}"
    page = item.get("page")
    if page is not None:
        text += f", p.{page}"
    return text
