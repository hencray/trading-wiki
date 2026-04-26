# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current State: Phase 2A v0.2 shipped; Phase 2A v0.3 next

As of 2026-04-26, Phase 1 (ingestion) and Phase 2A v0.1 + v0.2 (Pass 1 chunk + classify, Pass 2 TradeExample + Concept extraction) are done and committed. Corpus: 8 trade_examples + 48 concepts across 9 routed chunks of two Tier 1 videos at locked prompt versions `pass1-v1`, `pass2-trade-example-v1`, `pass2-concept-v1`. Repo: **`hencray/trading-wiki`** on GitHub (private). 180 tests at 98% coverage.

**Next slice — Phase 2A v0.3:** Strategy/Setup/Rule/MarketCondition entity extraction (cross-chunk, needs Pass 3 entity-resolution scaffolding) + Concept dedup + the v0.2 prompt-iteration backlog (see `PROJECT_PLAN.md` Phase 2 decisions: silent price rescaling, trade-attribution semantics, concept-vs-metaphor classification, term-naming bias, synonym dedup, Pass 1 ↔ Pass 2 contamination check). Trigger for the prompt-iteration work: revisit once more Tier 1 sources are ingested — n=2 videos is too small to commit to prompt rewrites.

What lives where:

- **`PROJECT_PLAN.md`** — authoritative, consolidated plan. Single source of truth for all decisions, phases, scope, constraints, and deliverables. Always read this before proposing code or architecture changes.
- **`ARCHITECTURE.md`** — living module map for the code itself (what goes where, why). Update when modules are added/moved/removed.
- **`trading_wiki/`** — Python package. `handlers/` (one file per source type, all subclass `BaseHandler`), `core/` (reusable mechanics: `db`, `storage`, `audio`, `transcribe`, `youtube`, `pasted_text`, `logging`, `secrets`), `cli.py` (still a `NotImplementedError` stub — Phase-2-prep), `config.py` (still empty — Phase-2-prep).
- **`tests/`** — pytest suite, mirrors the package layout. TDD discipline: failing test before production code.
- **`migrations/`** — numbered SQL files applied by `yoyo-migrations` via `core/db.py`.
- **`brainstorm_edits_v1.md`** — historical patch document. Reference only.
- **`content_inventory.md`** — living inventory of v1 source content for ingestion.
- **`phase0_worksheet.md`** — optional Phase 0 template (skipped 2026-04-22).
- **`.env.example`** — secrets template (real `.env` is gitignored).

## Common commands

All commands run via `uv` (Python pinned to 3.12 by `.python-version`):

- **Install / sync** — `uv sync`
- **Tests** — `uv run pytest` (with branch coverage; the suite is fast — sub-2s)
- **Lint** — `uv run ruff check .`
- **Format check** — `uv run ruff format --check .`
- **Type check** — `uv run mypy trading_wiki tests` (strict mode, plus `pydantic.mypy` plugin)
- **Pre-commit on all files** — `uv run pre-commit run --all-files`

Pre-commit (ruff, ruff-format, gitleaks, mypy) runs automatically on `git commit`. Don't bypass with `--no-verify` — fix the underlying issue.

## Project Shape

The project is a two-deliverable system:

1. **Primary:** a knowledge wiki over ingested trading content (videos, Discord, PDFs, etc.)
2. **Secondary:** an automated trading bot that functions as the acid test of whether the wiki captured real, codifiable edge

If no strategies survive the Phase 5 backtest gauntlet, the wiki remains the deliverable. **Do not lower gates or force marginal strategies through to live trading** — this framing exists to prevent sunk-cost pressure in later phases.

## Load-bearing constraints (shape all design decisions)

These are baked into `PROJECT_PLAN.md` but worth knowing up front:

- **v1 course:** the v1 source content — 60-min bar system, intraday pivot-based
- **Asset class:** stocks only, universe = NASDAQ/QQQ constituents + a liquidity filter
- **Timeframe v1:** 60-min intraday execution + nightly daily-chart scanning. Swing mode (daily + weekly) is a v2 goal.
- **No Level 2 data** — v1 source's "watching it build" filter must use a volume proxy (Polygon 1-min data). L2 upgrade deferred pending Phase 5 Gate 6 results. This is the project's biggest codeability risk.
- **Broker:** Alpaca (paper → live, same API). IBKR deferred.
- **Market data:** Polygon.io Developer tier subscribed; Advanced tier (L2) is an escape hatch, not baseline.
- **PDT rule** at <$25k account conflicts with intraday strategy + $1–2k starter capital — must be resolved by end of Phase 6.

## Phased approach — gates are non-negotiable

Phase 0 (smoke test) → 1 (ingestion) → 2 (extraction) → 3 (wiki) → 4 (strategy formalization) → 5 (backtest gauntlet) → 5½ (dashboard) → 6 (paper, ≥6 weeks) → 7 (live, $1–2k starter).

**Phase 0 was skipped 2026-04-22 by user decision** — the risk that v1 source is not cleanly codifiable is carried forward into Phase 1/2 rather than answered up front. This skip does not generalise: the remaining phases and gates are still non-negotiable.

When working on any phase, consult the corresponding section of `PROJECT_PLAN.md`. Do not skip the remaining phases or gates. In particular:

- Phase 5 runs a **7-gate gauntlet** every time, every strategy — no exceptions.
- Phase 6 has a **rules-based duration gate** (≥6 weeks, ≥40 trades, ≥1 market event survived, ≥1 killswitch triggered, ≥1 recovery verified, etc.) — not "when I feel ready."
- Phase 7 rule: **no new strategies or logic after entering live.** Anything new goes back through Phase 5 → 6 first.

## Stack

Installed (see `pyproject.toml` for version floors, `uv.lock` for exact pins):

- Python 3.12 (pinned via `.python-version`)
- `pydantic` (v2) + `pydantic-settings` for models and the `Settings` loader
- `structlog` for JSON-format structured logging
- `python-dotenv` for `.env` loading
- `yoyo-migrations` for SQLite schema migrations
- `sqlite-vec` (installed; the vec0 virtual table is deferred until Phase 2 picks an embedding model + dim)
- `openai` (Whisper API)
- `yt-dlp` (YouTube)
- Dev: `ruff`, `mypy`, `pytest`, `pytest-cov`, `pre-commit`

Planned but not yet installed (add when the phase that needs them starts):

- Claude API SDK (`anthropic`) — Phase 2 extraction (Opus 4.7 / Sonnet 4.6 / Haiku 4.5, stakes-tiered)
- `pandas-ta` (pinned) for indicators — Phase 4
- Streamlit — Phase 2B (review queue) and Phase 5½ (dashboard)

Obsidian (Phase 3 wiki browsing) is a tool the user runs locally, not a Python dep. Pin versions when packages are added. Match TradingView conventions where v1 source examples depend on specific indicator behavior.

## When editing `PROJECT_PLAN.md`

- Update the `*Last updated:*` line at the top.
- New decisions go under **Decisions Made**, grouped by phase.
- Status icons: 🔲 Not started · 🟡 Planning · 🟠 In progress · 🟢 Complete · ⚫ Archived.
- Never delete completed/archived content — move to archived sections instead.

## When writing code

- TDD discipline: failing test → minimum code to pass → refactor. One behavior per cycle. The Phase 1 work was built this way; keep doing it.
- `core/` holds reusable mechanics; handlers (and later, extractors / strategies) compose them. Don't put orchestration in `core/`.
- `BaseHandler` (in `handlers/base.py`) is the only extension seam for new source types. `ContentRecord` and `Segment` are Pydantic v2 models with `extra="forbid"` — typos in field names raise instead of silently dropping data.
- The `Strategy` interface is designed once (in Phase 4) and reused verbatim by backtest, paper, and live code paths. No adapters.
- Signal / Setup / Strategy are separate abstraction layers — pure boolean detectors, contextual filters with preconditions, and full strategies with exits/sizing respectively.
- Backtest reports are dated and immutable — never overwrite, never edit post-hoc.
- Research journal: log hypothesis + prediction **before** running any backtest; fill in result after. This is the discipline that prevents overfitting-by-iteration.

## Cloud-portability seam (don't break this)

Ingestion (raw video → transcript) is the **only** strictly-local step. Phase 2 onward must run against committed transcripts plus a migration-defined SQLite rebuildable from them. No phase later than 1 may require access to raw video files. This is what lets remote Claude Code / Claude iOS sessions work against the GitHub repo. Raw videos stay local under `content/` (gitignored).
