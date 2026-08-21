from adapters.insuq_a2a.agent_card import load_agent_card


def test_load_agent_card_returns_insuq_card_with_lookup_clause():
    card = load_agent_card()

    assert card["name"] == "InsuQ"
    skill_ids = [s["id"] for s in card["skills"]]
    assert "lookup-clause" in skill_ids
    assert "verify-collateral-insurance" in skill_ids
