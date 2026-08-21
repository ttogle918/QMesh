"""FinAllQ Agent Card 로더 — docs/agent_cards/finallq.json 을 그대로 서빙한다.

파일을 복제하지 않는다 — 원본은 docs/agent_cards/에 있고(A2A_Q 계약 문서 원칙, drift
방지), 여기서는 읽기만 한다.
"""

from __future__ import annotations

import json
from pathlib import Path

_AGENT_CARD_PATH = Path(__file__).resolve().parents[2] / "docs" / "agent_cards" / "finallq.json"


def load_agent_card() -> dict:
    return json.loads(_AGENT_CARD_PATH.read_text(encoding="utf-8"))
