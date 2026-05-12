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

    # Routing table covers the v0.2 base routes plus Slice 6 additions
    # (strategy + setup; setup also routes on `strategy`-labeled chunks).
    expected_routes = {
        "trade_example": {"example"},
        "concept": {"concept", "qa"},
        "strategy": {"strategy"},
        "setup": {"strategy"},
    }
    assert expected_routes == PASS2_LABEL_ROUTES


def test_pass2_trade_example_v2_constants_present() -> None:
    from trading_wiki.config import (
        PROMPT_PASS2_TRADE_EXAMPLE_V2_PATH,
        PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2,
    )

    assert PROMPT_VERSION_PASS2_TRADE_EXAMPLE_V2 == "pass2-trade-example-v2"
    assert PROMPT_PASS2_TRADE_EXAMPLE_V2_PATH.is_file()
    assert PROMPT_PASS2_TRADE_EXAMPLE_V2_PATH.name == "pass2_trade_example_v2.md"


def test_pass2_trade_example_v2_prompt_adds_only_numeric_scale_rule() -> None:
    from trading_wiki.config import (
        PROMPT_PASS2_TRADE_EXAMPLE_PATH,
        PROMPT_PASS2_TRADE_EXAMPLE_V2_PATH,
    )

    v1 = PROMPT_PASS2_TRADE_EXAMPLE_PATH.read_text(encoding="utf-8")
    v2 = PROMPT_PASS2_TRADE_EXAMPLE_V2_PATH.read_text(encoding="utf-8")

    # v2 must contain the new rule
    assert "Preserve numeric scale" in v2
    assert "Never apply a unit conversion" in v2
    # v1 must NOT contain the new rule (sanity check we didn't edit v1)
    assert "Preserve numeric scale" not in v1
    # v2 must contain every line of v1 except for the new bullet's surroundings
    # (sanity: it's a strict superset of v1 verbatim)
    v2_lines = v2.splitlines()
    for line in v1.splitlines():
        if line.strip():
            assert line in v2_lines, f"v2 missing v1 line: {line!r}"
