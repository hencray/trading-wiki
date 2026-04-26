def test_pass2_config_constants_resolve():
    from trading_wiki.config import (
        MODEL_PASS2,
        PASS2_LABEL_ROUTES,
        PROMPT_PASS2_CONCEPT_PATH,
        PROMPT_PASS2_TRADE_EXAMPLE_PATH,
        PROMPT_VERSION_PASS2_CONCEPT,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE,
    )

    assert MODEL_PASS2 == "claude-sonnet-4-6"
    assert PROMPT_VERSION_PASS2_TRADE_EXAMPLE == "pass2-trade-example-v1"
    assert PROMPT_VERSION_PASS2_CONCEPT == "pass2-concept-v1"

    assert PROMPT_PASS2_TRADE_EXAMPLE_PATH.is_file()
    assert PROMPT_PASS2_CONCEPT_PATH.is_file()

    te_text = PROMPT_PASS2_TRADE_EXAMPLE_PATH.read_text(encoding="utf-8")
    co_text = PROMPT_PASS2_CONCEPT_PATH.read_text(encoding="utf-8")
    # Sanity: each prompt names its entity type and lists key fields.
    assert "TradeExample" in te_text
    assert "ticker" in te_text
    assert "outcome_classification" in te_text
    assert "Concept" in co_text
    assert "definition" in co_text
    assert "related_terms" in co_text

    # Routing table covers exactly the labels named in spec §4.
    expected_routes = {
        "trade_example": {"example"},
        "concept": {"concept", "qa"},
    }
    assert expected_routes == PASS2_LABEL_ROUTES
