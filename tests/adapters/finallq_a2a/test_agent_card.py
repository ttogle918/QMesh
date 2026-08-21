from adapters.finallq_a2a.agent_card import load_agent_card


def test_load_agent_card_returns_finallq_card_with_request_withdrawal():
    card = load_agent_card()

    assert card["name"] == "FinAllQ"
    skill_ids = [s["id"] for s in card["skills"]]
    assert "request-withdrawal" in skill_ids
    assert "assess-loan" in skill_ids
