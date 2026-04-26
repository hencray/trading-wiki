# trading-wiki

A framework for ingesting trading content (videos, Discord, pasted text), extracting structured knowledge with LLMs, and acid-testing the resulting strategies via backtest → paper → live.

## What this is

The repository contains the framework only:

- **Ingestion pipeline** — handlers per source type, transcription via Whisper, content-addressed storage.
- **Extraction pipeline** — multi-pass LLM extraction (chunk + classify, then per-type entity extraction) with locked, versioned prompts.
- **Schema and migrations** — SQLite via yoyo-migrations, Pydantic v2 models with strict typing.
- **Phased gauntlet** — a 7-gate backtest gauntlet, ≥6-week paper trading, then a small starter-capital live phase. Deliberately conservative: if no strategies survive, the wiki is the deliverable.

## What this is *not*

- It does **not** include any ingested content. The author's working corpus (course videos, transcripts, and the extracted SQLite DB) is private and is excluded by `.gitignore`.
- It does **not** include hand-review notes for any extracted content (`docs/superpowers/reviews/` is gitignored).
- It is **not** financial advice. The `live` phase has hard rules and starts at $1–2k.

## Quick start

```bash
uv sync
cp .env.example .env  # then fill in the keys you intend to use
uv run pytest
```

`.env` keys (all optional — supply the ones you need):

- `ANTHROPIC_API_KEY` — extraction
- `OPENAI_API_KEY` — Whisper transcription
- `POLYGON_API_KEY` — market data (Phase 4+)
- `ALPACA_API_KEY_ID` / `ALPACA_API_SECRET_KEY` — broker (Phase 6+)

## Project shape

- **`PROJECT_PLAN.md`** — authoritative phased plan, scope, and gates.
- **`ARCHITECTURE.md`** — module map.
- **`CLAUDE.md`** — guidance for working with Claude Code in this repo.
- **`trading_wiki/`** — the Python package. `handlers/`, `core/`, `extractors/`.
- **`tests/`** — pytest suite, mirrors the package layout.
- **`migrations/`** — numbered SQL files applied via yoyo.
- **`prompts/`** — locked, versioned LLM prompts.

## Status

Phase 1 (ingestion) and Phase 2A v0.1 + v0.2 (Pass 1 + Pass 2 entity extraction) are implemented. Phase 2A v0.3 (Strategy / Setup / Rule extraction + Pass 3 entity-resolution scaffolding) is next. See `PROJECT_PLAN.md` for the full roadmap.

## License

MIT — see `LICENSE`.
