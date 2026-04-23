# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current State: Pre-code planning phase

As of 2026-04-22, this directory contains pre-Phase-1 planning docs and scaffolding — no Python code yet. Repo: **`hencray/trading-wiki`** on GitHub (private). Files on disk:

- **`PROJECT_PLAN.md`** — authoritative, consolidated plan. Single source of truth for all decisions, phases, scope, constraints, and deliverables. Always read this before proposing code or architecture changes.
- **`brainstorm_edits_v1.md`** — historical patch document applied to produce `PROJECT_PLAN.md`. Reference only; do not treat as current guidance.
- **`content_inventory.md`** — living inventory of v1 source content in scope for Phase 1 ingestion.
- **`phase0_worksheet.md`** — optional Phase 0 smoke-test template (Phase 0 was skipped by user; file retained for possible later use).
- **`.env.example`** — secrets template (real `.env` is gitignored).
- **`.gitignore`** — standard Python + project-specific ignores.

There is no build, lint, test, or run command because there is no Python code yet.

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

## Planned stack (not installed yet)

- Python throughout
- Claude API (Opus 4.7 / Sonnet 4.6 / Haiku 4.5, stakes-tiered) for extraction
- OpenAI Whisper API for transcription
- SQLite + `sqlite-vec` for storage and embeddings
- `pandas-ta` (pinned) for indicators, wrapped in an `indicators/` module
- Streamlit for dashboards (review queue, ingestion, Strategy Command Center)
- Obsidian for wiki browsing (reads auto-generated markdown)
- `structlog` for structured logging from Phase 1
- `.env` + `python-dotenv` for secrets from day 1

Pin versions when packages are added. Match TradingView conventions where v1 source examples depend on specific indicator behavior.

## When editing `PROJECT_PLAN.md`

- Update the `*Last updated:*` line at the top.
- New decisions go under **Decisions Made**, grouped by phase.
- Status icons: 🔲 Not started · 🟡 Planning · 🟠 In progress · 🟢 Complete · ⚫ Archived.
- Never delete completed/archived content — move to archived sections instead.

## When writing code (when the time comes)

- Phase 1 scaffolding must include: `structlog` JSON logging, `.env` loader, SQLite schema, `ContentRecord`, base handler interface, `ARCHITECTURE.md`. All before the first handler implementation.
- The `Strategy` interface is designed once (in Phase 4) and reused verbatim by backtest, paper, and live code paths. No adapters.
- Signal / Setup / Strategy are separate abstraction layers — pure boolean detectors, contextual filters with preconditions, and full strategies with exits/sizing respectively.
- Backtest reports are dated and immutable — never overwrite, never edit post-hoc.
- Research journal: log hypothesis + prediction **before** running any backtest; fill in result after. This is the discipline that prevents overfitting-by-iteration.
