"""Shared configuration constants and paths."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# ─── Phase 2A — Pass 1 (chunk + classify) ──────────────────────
MODEL_PASS1 = "claude-sonnet-4-6"
PROMPT_VERSION_PASS1 = "pass1-v1"
PROMPT_PASS1_PATH = _REPO_ROOT / "prompts" / "pass1.md"

# ─── Phase 2A — Pass 2 (TradeExample + Concept extraction) ──────
MODEL_PASS2 = "claude-sonnet-4-6"

PROMPT_VERSION_PASS2_TRADE_EXAMPLE = "pass2-trade-example-v1"
PROMPT_PASS2_TRADE_EXAMPLE_PATH = _REPO_ROOT / "prompts" / "pass2_trade_example.md"

PROMPT_VERSION_PASS2_CONCEPT = "pass2-concept-v1"
PROMPT_PASS2_CONCEPT_PATH = _REPO_ROOT / "prompts" / "pass2_concept.md"

# Pass 2 label-based routing (spec §4). Keys are entity-type identifiers used
# internally by the dispatcher; values are the set of Pass 1 chunk labels that
# route to that entity-type's extractor. Strict — labels not in any value-set
# are skipped in v0.2.
PASS2_LABEL_ROUTES: dict[str, set[str]] = {
    "trade_example": {"example"},
    "concept": {"concept", "qa"},
}
