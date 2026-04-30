# Trading System Project Plan

*Started: April 16, 2026*
*Last updated: 2026-04-29*
*Status: **Phase 1 complete, Phase 2A v0.1 + v0.2 + v0.2.1 + v0.2.2 SHIPPED. Review-UI dev tool shipped 2026-04-26 as a separate slice (not Phase 2B). Tier 1 corpus expanded to 12 videos on 2026-04-28 (95 chunks / 12 trade_examples / 112 concepts). Pass 2 idempotency fix shipped 2026-04-29 via new `pass2_runs` table (zero-entity runs now properly recorded).** Pass 1 (chunk + classify) shipped 2026-04-25 with `pass1-v1` locked. Pass 2 (TradeExample + Concept entity extraction) shipped 2026-04-26: ran against both Tier 1 videos (8 trade_examples + 48 concepts across 9 routed chunks); 5+5 stratified hand-review passed §2(6) bar at 5/5 + 5/5; prompt versions `pass2-trade-example-v1` + `pass2-concept-v1` locked. Schema-fit findings carried forward as v0.3 prompt-iteration backlog (revisit once more Tier 1 sources are ingested). Review UI: local Streamlit page at `trading_wiki/review/app.py` with stratified/random/all sampling, three-state status, markdown findings file per `content_id` (gitignored). 208 unit tests + 2 integration tests, 97% coverage.*

**Status legend:** 🔲 Not started · 🟡 Planning · 🟠 In progress · 🟢 Complete · ⚫ Archived

---

## 🎯 Project Overview

**Goal:** Build a system that digests stock trading content (videos, PDFs, articles, etc.) and turns it into an automated stock trading bot.

**Answers from kickoff Q&A:**
- End goal: **Fully automated trading bot that executes trades**
- Technical level: **Some coding — can follow along with guidance**
- Content volume: **Medium (hundreds of items, ongoing ingestion)**
- **v1 course: the v1 source content** — see Project Specifics section

---

## ⚠️ Reality Check / Honest Caveats

Training a bot on trading content to autonomously execute trades is a path that has burned a lot of smart people and money. Two things to keep separate:

1. **Extracting strategies from content** → doable, LLMs are good at this
2. **Those strategies actually making money live** → hard. Most online trading content is survivorship bias, vibes, or outright bad. Backtests lie. Markets adapt.

**Guiding principle:** Build research pipeline → prove strategies on historical data → paper trade → only then risk real money. Skipping steps is how accounts get drained.

---

## 📐 Scope — what success looks like if trading doesn't pan out

**Primary deliverable:** a structured, searchable knowledge system over trading content — useful on its own regardless of whether live trading ever makes money.

**Secondary deliverable:** a trading bot, which functions as the acid test of whether the knowledge system captured real, codifiable edge.

**If < 1 strategy survives Phase 5 gauntlet after a full course dump:** the project's output is Phases 1–3 (ingestion, extraction, wiki). Do not force strategies through the gauntlet. Do not lower gates. The wiki is the win.

This framing exists to prevent sunk-cost pressure from pushing bad strategies to live trading in Phase 7.

---

## 🎓 Project Specifics — v1 source (v1 course)

### Course

**v1 course content:** **the v1 source content**

Core system summary:
- 60-minute bar-based (deliberately avoids 1-minute chart noise)
- Premise: stocks trade from supply to supply and demand to demand
- Nightly prep: scan daily charts, curate watchlist of 3–5 high-value ideas
- Preferred universe: highly liquid high-beta names (NVDA, TSLA, AMZN, similar)
- Execution via predetermined pivot points + confirmation via Level 2 / order flow
- 5-Minute Rule: exit if trade doesn't build momentum within 5 min of pivot cross
- Never chase: if initial confirmation missed, stand down
- Minimum 2:1 to 3:1 reward-to-risk
- Scaled exits: 50% at ATR/whole number, 25% at next S/D zone, 25% runner with stop moved to breakeven

Indicator stack:
- Bollinger Bands: 20 SMA, 2σ
- Simple Moving Averages: 5, 10, 20, 50, 100, 200
- Exponential Moving Averages: 20, 50, 100, 200
- Linear Regression Line: 50-period linear weighted moving average (confirms direction)

Swing mode (secondary per course): use daily chart confirmations instead of 60-min; previous day's low = long stop, previous day's high = short stop.

### Asset class

**Stocks only.** Universe further filtered to **NASDAQ / QQQ constituents with adequate liquidity** for v1. Specific liquidity threshold (e.g., 20-day avg $ volume, min market cap) to be set in Phase 1 universe module.

No options, futures, or crypto in v1.

### Timeframes

- **Scanning (v1):** daily chart (nightly prep, matches course workflow)
- **Executing (v1):** 60-min intraday bars
- **v2 goal:** also support weekly + daily scanning → daily execution for swing trades (requires extending Strategy interface for overnight holds, gap risk, swing stop logic)

### Known codeability risks for v1 source (must be addressed in Phase 4)

**1. Level 2 / order flow confirmation — MAJOR**

The "watching it build" filter (L2 depth, lot sizes, order flow) is a core v1 source pillar. **We do NOT have L2 access.**

Impact:
- Backtesting cannot replicate this filter as taught
- Phase 4 must choose one of:
  - (a) **Proxy approach** — substitute 1-min volume + trade-print size from Polygon as best available approximation
  - (b) **Skip the filter entirely** — accept higher false-positive rate, compensate with tighter stops / lower size
  - (c) **Upgrade to Polygon Advanced** — adds cost, resolve after Phase 5 gauntlet results if the proxy version fails
- Expected codeability score for "watching it build" filter: **2/5 without L2, ~3/5 with volume proxy**
- Expected impact on Phase 5 Gate 6 (cost stress test): the proxy may introduce slippage the backtest doesn't model; plan to stress-test accordingly

**2. Scaled exit state complexity**

3-stage partial-fill exit logic (50%/25%/25% with stop-to-breakeven after first scale) adds meaningful state complexity to `Strategy.on_bar()` and `on_fill()`. Codifiable but requires careful Phase 4 spec and testing:
- Track partial fills across bars
- Update stop-loss on first scale (move to BE)
- Handle edge cases: partial fill that doesn't complete, runner hits stop before next scale, etc.

**3. Subjective qualifiers**

Phrases that will require Phase 4 tagged assumptions:
- "long distribution" → how many bars of consolidation qualifies?
- "tight risk" → how tight, relative to ATR or absolute?
- "is the trade worth it?" → RR ≥ 2:1 as hard gate, plus what else?
- "large lot sizes" (if we had L2) → how large is large?
- "premium face card" setups → what specifically distinguishes from non-premium?

Expected: each v1 source strategy will need ~5–10 tagged assumptions to reach a codable spec.

### Expanding beyond v1 source

Future courses will be added through the same ingestion + extraction pipeline. The schema's credibility tiers and source provenance are designed for multi-course curation. Phase 1 handlers (video, YouTube, Discord, PDF, EPUB, article) are source-agnostic. Adding a course = new Tier 1 source, same extraction run.

---

## 📋 Phased Plan

**Calendar vs effort:** Total effort is roughly 250–480 hours of focused solo work. At 5–10 hrs/week, that's a 6–18 month project before Phase 7, not 12 weeks. Phase headings below use *effort* estimates, not calendar weeks, except Phase 6 which has a hard calendar-duration gate.

---

### Phase 0: Course smoke test (2–4 hours, do this FIRST)

Before building any infrastructure, do a manual test on v1 source content:
1. Watch 3–5 random hours of the v1 source content.
2. Attempt to write one complete strategy spec by hand (using the Phase 4 spec template — even a rough version).
3. Count tagged assumptions needed.

**Pass:** can draft at least one spec with < 50% assumption rate → course is codifiable, proceed.
**Ambiguous:** 50–75% assumptions → proceed cautiously, pick a different starter strategy if this one is fuzzy.
**Fail:** can't produce a spec at all, or every rule is "feel" / "discretion" → treat v1 source as a knowledge-wiki-only input and consider adding a second course.

**Given what we already know about v1 source (intraday pivots, explicit indicator stack, scaled exits):** expect PASS with 30–50% tagged assumption rate. The L2 gap and subjective qualifiers will drive most of that.

**Status:** 🔲 Must complete before Phase 1

---

### Phase 1: Ingestion Pipeline (~30–60 hours)

Build the system that eats content and produces clean, structured text.

**Starting content (v1 source course):**
- Local video files
- YouTube links
- Discord chat exports
- Twitter/X tweets & threads

**Future content (expand to):**
- PDFs
- EPUBs
- Web articles / blog posts
- Other courses in various formats

**Tooling by source type:**
- Local videos → extract audio (ffmpeg) → OpenAI Whisper API
- YouTube → `yt-dlp` → use existing subs if human-made, else Whisper API
- Discord → manual copy/paste of messages → pasted-text handler normalises (author, timestamp, thread heuristics) → store. Sidesteps DCE ToS violation — no user token, no throwaway account needed.
- Twitter/X → depends on access — `snscrape` (may be broken), paid API, or manual export
- PDFs → `pdfplumber` / `PyMuPDF`, OCR fallback for scanned
- EPUBs → `ebooklib`
- Web articles → `trafilatura`

**Transcription decision:** OpenAI Whisper API (user has experience with it)

**Architecture principle:** Modular pipeline — each source type is a plugin. Core contract: take source → return standardized content record. Easy to add new source types without touching core.

**Ingestion mode:** Ad-hoc as things are found (not batch overnight)

**Inspiration:** Something like [kapa.ai-style](https://www.kapa.ai/) LLM-backed wiki over the ingested corpus

**Storage:** Local files + SQLite DB (simple, single machine)

**Twitter/X:** Deferred — not in v1

**Discord:** resolved 2026-04-22 — pasted-text handler, not DiscordChatExporter. User pastes relevant channels/messages as found.

**Course platform text:** user extracts and hands over content directly (resolved 2026-04-22 — platform-specific scraping not needed). Handler accepts text blobs with source metadata; likely shares the Discord paste-in normaliser.

**Build order for v1:**
1. Core scaffolding: `ContentRecord`, DB schema, storage layout, base handler interface
2. Local video handler (v1 source content in hand, fastest feedback loop)
3. YouTube handler (reuses transcription code)
4. Discord handler (pasted-text normaliser — much simpler than DCE path)
5. Stubs for PDF / EPUB / article (implement later)

**Project layout:**
```
trading-research/
  handlers/
    base.py          # ContentRecord + BaseHandler interface
    local_video.py
    youtube.py
    discord.py
    pdf.py           # stub
    epub.py          # stub
    article.py       # stub
  core/
    db.py            # SQLite schema + queries
    storage.py       # file storage helpers
    transcribe.py    # Whisper API wrapper
    logging.py       # structured logging setup (structlog)
    secrets.py       # .env loader + validators
  cli.py             # `ingest <url-or-file>` dispatcher
  config.py
```

**ContentRecord schema:**
- `source_type`, `source_id` (URL, file hash, message ID)
- `title`, `author`, `created_at`, `ingested_at`
- `raw_text` — cleaned text content
- `segments[]` — timestamped chunks for videos/long content
- `parent_id` — for Discord replies, tweet threads, course modules
- `metadata` — flexible JSON (duration, channel, server, etc.)

Raw source files stored content-addressed: `storage/{source_type}/{hash}.{ext}`
Transcripts saved to both DB and disk as `.txt`/`.srt` for re-processing.

**Status:** 🟢 Complete (2026-04-25) — Phase 0 skipped; all v1 handlers landed. ✅ Package layout · ✅ Tooling (`uv` + `pyproject.toml` + `ruff` + `mypy --strict` + `pytest` + `pre-commit` + GitHub Actions CI with ffmpeg) · ✅ `ContentRecord`/`Segment`/`BaseHandler` (Pydantic v2, `extra="forbid"`) · ✅ SQLite schema + `yoyo-migrations` applier + roundtrip helpers · ✅ `structlog` JSON logging · ✅ Pydantic-settings `Settings` loader · ✅ `core/storage.py` (SHA-256 + sharded paths) · ✅ `core/transcribe.py` (Whisper API wrapper, injected client) · ✅ `core/audio.py` (ffmpeg subprocess → 32 kbps mono mp3) · ✅ `core/youtube.py` (yt-dlp wrapper, injected factory) · ✅ `core/pasted_text.py` (shared text-paste mechanic) · ✅ `LocalVideoHandler` · ✅ `YoutubeHandler` · ✅ `DiscordHandler` (pasted-text, `discord:<path>`) · ✅ `CoursePlatformHandler` (pasted-text, `course:<path>`) · ✅ `PdfHandler` / `EpubHandler` / `ArticleHandler` stubs. **93 tests at 98% coverage.** Phase-2-prep open items (not Phase 1 gates): CLI dispatcher (`cli.py` still raises `NotImplementedError`), shared `config.py` (still empty).

---

### Phase 2: Knowledge Extraction (~60–120 hours)

**Goal:** Turn raw ingested content into structured, queryable knowledge about strategies, concepts, rules, and trade examples — with full provenance back to source.

**Core challenge:** Trading content is messy. A 45-min video might have one fully-explained strategy, three half-mentioned ones, psychology talk, dated market commentary, and a killer nugget at minute 38. Can't just throw the transcript at an LLM and hope.

**Solution: Multi-pass extraction pipeline + human review loop + chart extraction sub-pipeline**

---

#### 2A. Multi-pass Text Extraction

**Pass 1 — Segmentation & Classification**
Chunk content (by time/thread/section) and classify each chunk as:
- Strategy description
- Concept / education
- Example / trade recap
- Psychology / mindset
- Market commentary (dated)
- Q&A
- Noise (intros, sponsorships, tangents)

**Pass 2 — Entity Extraction** (structured JSON output)
For each classified chunk, extract entities:
- Strategies → name, thesis, entry/exit rules, timeframe, instruments, indicators, risk mgmt
- Setups → name, preconditions, trigger, required indicators, market condition hints
- Concepts → term, definition, related concepts
- Trade examples → instrument, direction, entry/exit, outcome, lessons
- Rules/heuristics

**Pass 3 — Entity Resolution** (LLM + embeddings)
Same strategy (or setup) described in multiple sources merges into ONE entry with multiple source links.
- Embed each new extracted entity
- Vector-search existing entities for similarity
- If similarity > threshold → LLM: "same thing? merge or create new"
- Preserve provenance always

**Pass 4 — Relationship Building**
- Strategy X **uses** Setup Y
- Setup Y **uses** Indicator Z
- Strategy X **is a variant of** Strategy A
- Concept B **is a prerequisite for** Setup Y
- Trader M **teaches** Strategy X

---

#### 2B. Human Review Pipeline (first-class, not an afterthought)

**Queue triggers** — items added to review queue when:
- Low-confidence extractions (LLM flagged uncertainty)
- Borderline merges (similarity in 65–80% gray zone)
- High-stakes entities (Tier 1 course content always reviewed)
- First extraction from each new source (catches prompt failures early)
- Conflicts (two sources disagree about a strategy)

**Hard gates** (won't enter graph without review):
- Strategies with `codeability_score ≥ 4` (we might trade these — don't trust LLM alone)
- Cross-tier merges (Tier 1 course merging with Tier 4 Discord is suspicious)

**Review UI** (Streamlit, shared app with wiki)
- `/review` page with prioritized queue
- Per-item: LLM extraction, source excerpt + timestamp link, Accept / Edit / Reject / Merge-with actions
- Keyboard shortcuts for fast review
- Bulk actions ("accept all high-confidence strategies from this video")

**Feedback loops** (reviews = training data for prompt improvement)
- Rejection reasons captured (optional "why?" field)
- Edit diffs tracked (LLM output vs human correction)
- Systematic errors surfaced over time → feed into prompt revisions

**Realistic effort:** ~50–150 review items for an 80-hour course, 1–2 min each = few hours total, spread across project.

---

#### 2C. Chart Extraction Sub-Pipeline

**Goal:** Extract sample chart data from videos and other content, recreate in wiki using real price data.

**Phased approach:**

*Chart v1 (easy wins):*
- Extract images from PDF pages
- Extract image attachments from Discord exports
- Extract images from EPUBs
- Run vision model on each to: classify (is this a chart?), extract ticker/timeframe/date/indicators, describe annotations

*Chart v2 (video frames):*
- `ffmpeg` scene-change detection → sample frames at visual transitions (~20–50 unique scenes per video vs hundreds at fixed intervals)
- Vision classification: chart or not
- De-dupe via image embedding similarity
- Link each chart to transcript window (chart at 12:34 + spoken context 12:30–14:05)

*Chart v3 (recreation) — EXPLICITLY DEFERRED TO V2+:*
The full chart-recreation pipeline (price data pull, re-rendering, annotation overlay) is a real engineering project that competes with Phase 4 (the actual bottleneck). **V1 stops at v2 (frames linked to transcript windows).** Revisit v3 only after Phase 7 is running stably.

Original v3 scope (deferred):
- For each identified chart: pull real price data (yfinance/Polygon) for the ticker + date range
- Re-render chart in Plotly or Lightweight Charts
- Overlay presenter's annotations (entry/stop/targets) as described
- Store *coordinates* not screenshots (avoids copyright, enables interactivity)

**Bonus (when v3 lands):** Can re-render with updated data — "here's the NVDA breakout he showed in March 2024, plus what happened after."

**Honest tradeoffs:**
- Vision model accuracy: good for tickers, okay for indicators, questionable for exact price levels — needs human review
- Cost: meaningful but not prohibitive at scene-change sample rate
- Complexity: Chart v2–v3 are a real project — treat as separate workstream, not blocker for main pipeline

---

#### 2D. Schemas

Strategy:
```
{
  "id", "name", "aliases": [],
  "thesis", "category", "timeframe", "instruments",
  "entry_rules", "exit_rules", "risk_management",
  "indicators_used", "prerequisites",
  "setups_used": [<setup_id>],
  "sources": [{"content_id", "timestamp", "excerpt"}],
  "chart_examples": [<chart_id>],
  "codeability_score": 1-5,
  "confidence": "high|medium|low",
  "review_status": "pending|approved|rejected",
  "credibility_tier": 1-5
}
```

Setup (first-class entity):
```
{
  "id", "name", "aliases": [],
  "description", "preconditions", "trigger",
  "indicators_used", "market_conditions": [],
  "parent_strategy_ids": [],
  "sources": [...],
  "review_status"
}
```

Chart:
```
{
  "id", "source_content_id", "source_timestamp",
  "ticker", "timeframe", "date_range",
  "indicators": [], "annotations": [],
  "pattern_description",
  "linked_strategy_id", "linked_setup_id",
  "linked_transcript_excerpt",
  "image_hash",
  "confidence", "review_status"
}
```

Concept, TradeExample, Rule, MarketCondition: similar structure + `review_status` field.

**Codeability score rubric:**
- **5** — pure boolean on OHLCV + standard indicators. No judgment. Example: "buy on 20-day breakout, sell at 2 ATR stop."
- **4** — one minor judgment call, easily defaulted. Example: "buy on breakout with 'strong' volume" → default strong = >1.5x 20-day avg.
- **3** — 2–3 judgment calls, each defaultable but needs tagged assumptions. Example: "wait for confirmation, enter on retest."
- **2** — mostly judgment, some rules. Example: "read the tape for exhaustion, enter on reclaim." Probably not codable without ML.
- **1** — pure discretion / "feel." Example: "trade what you see." Goes in fuzzy backlog.

Gates: score ≥ 3 → human review required. Score ≥ 4 → Phase 4 candidate. Score ≤ 2 → fuzzy backlog.

---

#### 2E. LLM Strategy

**Stakes-based tiering (not task-type-based):**

- **Opus 4.7** for high-stakes operations that directly feed tradeable strategies:
  - Entity resolution across Tier 1 (course) content
  - Codeability scoring
  - Final strategy formalization for backtesting candidates
- **Sonnet 4.6** for everything else in the main pipeline (extraction, relationships, chart vision)
- **Haiku 4.5** as future optimization for Pass 1 classification once we have cost data

Rationale: misclassifying a Discord chunk doesn't matter. Merging two different strategies into one polluted entry does — that strategy might become a trading bot. Spend the extra on judgment calls that matter.

**Realistic cost estimate for 80-hour course:**
- Raw audio transcription (Whisper API): ~$30–50
- Multi-pass extraction (4 passes, Sonnet-majority): ~$50–150
- Chart vision (Sonnet, scene-change sampled): ~$20–60
- Entity resolution + relationships on top: ~$10–30
- **Total Phase 2 cost: ~$110–290**

The delta from Sonnet-everywhere to stakes-tiered is small (~$20–30). The absolute number matters more — budget $300 for extraction of the first course.

Pricing reference (as of April 2026):
- Opus 4.7: $5 / $25 per MTok
- Sonnet 4.6: $3 / $15 per MTok
- Haiku 4.5: $1 / $5 per MTok

Vision: Sonnet 4.6 for chart extraction (capable enough, cheaper than Opus).

---

**Credibility tiering** (set at Phase 1, propagated through)
- Tier 1: Core course content from instructor (the v1 source's primary videos)
- Tier 2: Instructor's Q&A / live sessions
- Tier 3: Other traders / guests in course
- Tier 4: Student discussion / Discord chatter
- Tier 5: Random internet content (later)

**Provenance (non-negotiable)**
Every extracted fact keeps: `content_id`, `timestamp`/location, `excerpt`. So we can re-watch the exact 90 seconds where any claim came from.

**Caching & re-runs**
- Raw transcripts + chart frames frozen in Phase 1 storage
- Each extraction tagged with prompt version
- Can re-extract old content with improved prompts, diff results
- Never re-transcribe unless source changes

**Storage:** SQLite + `sqlite-vec` for embeddings (one-file simplicity). Move to Postgres if graph scale demands.

**Status:** 🟠 In progress (Phase 2A v0.1 + v0.2 + v0.2.1 + v0.2.2 SHIPPED 2026-04-25 / 2026-04-26 / 2026-04-28 / 2026-04-29; corpus = 12 videos / 95 chunks / 12 trade_examples / 112 concepts; v0.3 = Strategy/Setup/Rule/MarketCondition + Concept dedup + prompt-iteration backlog (now unblocked, n=12), not yet started)

---

### Phase 3: Research Wiki (~20–40 hours)

**Adopt Karpathy's LLM-Wiki pattern as the UX layer — on top of the structured DB from Phase 2.**

The structured SQLite DB (entities + graph) is the skeleton. The markdown wiki layer on top is the flesh — human-browsable, auto-maintained, git-versioned.

**Architecture — three layers (per Karpathy):**
1. **Raw sources** — immutable, from Phase 1 storage
2. **Structured DB** — Phase 2 extractions (the queryable ground truth)
3. **Markdown wiki** — auto-generated from #2, maintained incrementally, lives in Obsidian vault / git repo

**What we steal from the Karpathy pattern:**
- `CLAUDE.md` / schema file telling the LLM the wiki's conventions, page formats, workflows (co-evolves with project)
- `index.md` — content catalog, updated on every ingest
- `log.md` — chronological append-only record of ingests, queries, lint runs
- **"Answers become pages"** — when you query the wiki and get a useful synthesis, file it back as a new page. Explorations compound.
- **Lint pass** — periodic health check for contradictions, stale claims, orphans, missing pages
- **Obsidian as the UI** — point it at the auto-generated markdown folder → free graph view, backlinks, search, mobile, git

**What we do NOT take from the pattern:**
- Pure LLM-maintained wiki with no structured DB — at hundreds of sources with financial stakes, the typed schema underneath is non-negotiable. Critics in the thread are right: raw LLM-wikis collapse past ~1000 files.
- Git-as-only-database — fine for the wiki layer, not for operational data (review queue, extraction runs, embeddings)

**The flow:**
- Phase 2 produces a new `Strategy` entity → auto-generates `wiki/strategies/breakout-retest.md` with sections pulled from the structured data + source excerpts
- New source mentions existing strategy → wiki page gets updated, `log.md` gets an entry
- Conflict detected → lint flags it, review queue picks it up
- User asks "which v1 source strategies work in low-volume markets?" → LLM reads relevant pages, synthesizes, optionally files answer as `wiki/synthesis/low-volume-strategies.md`

**Streamlit app shrinks:** instead of being the wiki UI, Streamlit becomes just:
- Review queue interface
- Ingestion dashboard
- Chart viewer / editor
- Natural-language Q&A over DB + wiki (the "query" operation)

Browsing the wiki itself happens in Obsidian.

**Wiki page structure (tentative, encoded in the schema file):**
```
wiki/
  index.md
  log.md
  schema.md (or CLAUDE.md)
  strategies/
    <strategy-name>.md
  setups/
    <setup-name>.md
  concepts/
    <concept-name>.md
  traders/
    <trader-name>.md
  trade-examples/
    <ticker>-<date>.md
  charts/
    <chart-id>.md  (with embedded re-rendered chart when v3 lands)
  synthesis/
    (user-initiated exploration answers)
```

Each strategy page has required sections: Thesis, Setups Used, Entry Rules, Exit Rules, Risk Mgmt, Indicators Used, Sources (with excerpts + timestamps), Chart Examples, Codeability Score, Review Status, Related Strategies.

**Status:** 🔲 To build after Phase 2 delivers extractions

---

### Phase 4: Strategy Formalization (~40–80 hours — budget 3x if motivation matters)

**Goal:** Turn wiki strategies into deterministic Python code with unambiguous rules. If it can't be coded, it wasn't a strategy.

**The translation problem:** wiki content has rules like *"wait for reclaim with strong volume and confirmation, enter on retest"* — four ambiguities in one sentence. Phase 4 is the discipline of forcing every rule to become a deterministic function of market data. No judgment calls, no vibes.

---

**Workflow**

*Step 1 — Candidate selection*
Query wiki for strategies with `codeability_score ≥ 3` and `credibility_tier ≤ 2`. Expect ~10–20 candidates from a full v1 source course dump. **For first-pass v1: pick the 3–5 with highest codeability_score and Tier 1 credibility.** Resist the urge to formalize all 10 — Phase 4 is the project's highest human-bottleneck phase, and breadth here delays the Phase 5 feedback loop. Additional candidates can be formalized after initial gauntlet results.

**Expected v1 source candidates:** the foundational "pivot + premium face card" setup at minimum. Swing-trade variants likely secondary candidates.

*Step 2 — Specification interview (LLM-driven, human corrects)*
LLM walks through each candidate with a structured question list, pulling in source excerpts, proposing defaults, flagging ambiguities. User corrects/overrides. For every ambiguity that can't be resolved from source, an explicit tagged assumption is recorded.

Questions covered: exact trigger condition (boolean on OHLCV + indicators), exact timing (bar close? tick?), exact size (fixed / % equity / vol-adjusted), exact exit (target / stop / time / trail), universe (tickers + filters), edge cases (gaps, halts, earnings, splits).

**v1-specific interview topics:**
- Pivot calculation: exact formula from daily chart
- "Long distribution" definition: number of bars, volatility threshold
- Volume proxy for "watching it build" (since no L2): what Polygon feature?
- 5-minute rule: exact bar interval / clock time
- Scale-out triggers: ATR formula, "next S/D zone" definition (manual or algorithmic?)
- Runner stop: exactly when does BE stop move? After first scale fill confirms?
- Watchlist curation: daily chart setup detector or manual feed to bot?

*Step 3 — Setup validation via extracted examples*
After formalizing a setup, run the detector over historical dates of the extracted `TradeExample`s from v1 source course content. Does it fire when the author said it should? Mismatch = formalization is wrong, back to spec interview. Effectively a cheap Gate 0 before the gauntlet.

*Step 4 — Spec → Python*
Spec becomes code. Mostly mechanical because spec is unambiguous. LLM-assisted, human reviews every line — this code might trade real money.

*Step 5 — Dry-run sanity check*
Run on a week of historical data with verbose logging. Triggers where expected? Obvious bugs (entering every bar, never exiting, inverted signals)? Catches ~80% of coding errors before backtest pollution.

---

**Strategy Spec format (markdown with YAML frontmatter)**

```yaml
---
id: v1-strategy-v1
source_strategy_id: <wiki id>
spec_version: 1
status: draft | ready | archived
assumptions:
  - "Long distribution = ≥ 8 bars of consolidation on 60-min chart with BB width < 1.5x 20-bar avg (L2 unavailable, using volume proxy)"
  - "5-minute rule = 5 bars on 1-min chart post-entry; if high-of-entry-bar not exceeded by bar 5, exit"
  - "Scale 1 ATR target = entry + 1 * ATR(14, 60-min)"
  - "Volume confirmation proxy = current 1-min volume > 3x trailing 20-min average"
---

# Universe, Timeframe, Setup, Entry, Stops, Targets, Edge Cases
# Every field either concrete or explicit tagged assumption
```

Each spec field traces back to wiki source excerpts.

---

**Common Strategy Interface (build this FIRST before any strategy)**

```python
class Strategy:
    def universe(self, date: Date) -> list[Ticker]: ...
    def on_bar(self, bar: Bar, state: StrategyState) -> list[Order]: ...
    def on_fill(self, fill: Fill, state: StrategyState) -> list[Order]: ...
    def on_close_of_day(self, state: StrategyState) -> list[Order]: ...
```

Standard event-driven. Same interface is used by backtest engine (Phase 5), paper trader (Phase 6), and live executor (Phase 7). Strategy that passes backtest is literally the same code that runs live — no translation step for bugs to sneak into.

Upfront cost: ~few days to design properly. Payoff: cleanest foundation for everything downstream.

**Signal / Setup / Strategy abstraction layers** (cleaner than monolithic `on_bar`):
- **Signals** — pure functions, boolean "is pattern present?" (e.g. `is_60min_pivot_breakout(bars)`)
- **Setups** — signals + filters + context (e.g. `pivot_breakout + long_distribution + in_uptrend + volume_proxy_confirmed`)
- **Strategies** — setups + entry timing + exits + sizing

Scanner (Phase 5½) can run at Signal/Setup layer without full Strategy layer. Code reuse across strategies. Tests per layer.

---

**Repo layout**

```
strategies/
  _interface/
    base.py          # Strategy ABC + StrategyState + Bar/Order/Fill types
    testing.py       # shared dry-run harness
  v1-strategy/
    spec.md
    strategy.py
    test_strategy.py
    notes.md
    versions/
      v1_spec.md
      v2_spec.md
  ...

signals/              # pure boolean pattern detectors
setups/               # signals + filters + context
indicators/           # pinned indicator library wrappers (pandas-ta default)
```

Git repo, each strategy is its own folder, specs + code travel together.

---

**Technical indicators library**

**Default: `pandas-ta`** (pure Python, no C dependency, widely used).

Wrap all indicator calls in `indicators/` module with consistent interface. Pin version. Document any discrepancies vs TradingView (v1 source course likely uses TradingView, so alignment matters for matching course-claimed results).

If backtest results fail to approximate course examples, first suspicion: indicator discrepancy. Second: data provider differences.

---

**Testing tiers per strategy (required before advancing phases)**

- *Unit:* every signal, every setup detector, every cost model function
- *Golden-record:* "this strategy on this historical window produces exactly these trades" — catches regressions
- *Property-based:* random valid OHLCV → no crashes, no infinite loops, no NaN orders
- *Replay:* record a paper session, replay offline, assert identical behavior

Effectively Gate 0 of the backtest gauntlet. Explicit in `test_strategy.py` template.

---

**Jupyter dev-mode (dev velocity multiplier)**

Modify code → run backtest → wait → look at report → repeat = too slow for exploration.

Notebook harness: load historical data once, instantiate Strategy, step through bars interactively, inspect state, visualize signals on chart. This is how quant shops actually work. Cheap to add.

---

**The assumptions problem**

Realistically 30–50% of spec fields will need tagged assumptions because source content was vague. For v1 source, the L2 gap alone drives a chunk of these. Every assumption is: tagged with what it fills in for, versioned (v1 vs v2 can try different values), testable (backtest both, see which matches claimed results).

Over time you learn which assumptions matter (volume window: usually doesn't; stop placement: usually does).

---

**Fuzzy Strategies Backlog**

Strategies that resist formalization — "read the tape," "feel the market," "trade what you see" — go into `strategies/_fuzzy_backlog.md` rather than being dropped. Real human skills that don't reduce to rules. Potential future ML project: train classifiers on labeled examples. **Not in v1.** Flag and park.

Expected v1 source entries in fuzzy backlog: any pure "watching it build" variant that can't be proxied with volume, any "premium face card" distinctions that resist codification.

---

**Human effort**

Most human-intensive phase of the project. LLM can't resolve ambiguities — only user can (or inferred instructor intent from multiple sources). Budget 1–3 hours per strategy realistic, **3x that if motivation is a concern**. Across 3–5 candidates = ~15–45 hours of focused work.

**Deliverable (first pass):** 3–5 strategy folders with clean spec + working Python + passing dry-run sanity checks. Plus a fuzzy backlog for future work. Remaining candidates formalized after initial gauntlet results.

**Status:** 🟡 In planning

---

### Phase 5: Backtesting (~60–120 hours)

**One-sentence thesis:** If a strategy can't beat transaction costs on out-of-sample data across multiple market regimes with realistic execution assumptions, it doesn't exist. That sentence rules out ~90% of retail trading content. Good.

---

**The landmines to actively avoid**
- **Lookahead bias** — using information not available at the time (classic: using day's close to decide day's entry)
- **Survivorship bias** — testing today's QQQ on historical data misses failed names. Universe must be point-in-time.
- **Overfitting** — trying 500 param combos until one works, then "testing" on OOS that's now effectively in-sample
- **Ignoring costs** — commissions, slippage, spread, borrow fees, market impact
- **Regime bias** — momentum looks great in 2009–2021, fails in 2022. Mean-reversion: opposite.
- **Data snooping** — backtesting on the same period the v1 source used for examples = circular

---

**Framework decision: CUSTOM on top of the Phase 4 `Strategy` interface**

Rationale: we already designed an event-driven `Strategy` ABC in Phase 4. Building our own runner on top gives maximum control over cost modeling, execution assumptions, regime filtering, and walk-forward orchestration. No adapter layer between backtest code and live code — same `on_bar` runs both.

Tradeoff: more upfront engineering vs using `backtrader`. Accepted because (a) our abstraction is already designed, (b) we want custom gauntlet protocol tooling, (c) we need full control over cost/slippage models.

Use `vectorbt` opportunistically for quick parameter sweeps (it's great for vectorized exploration) before running the expensive full event-driven gauntlet.

---

**Data: Polygon.io Developer tier (user already has this)**

Capabilities it unlocks:
- Unlimited API calls
- 5+ years of historical tick-level data
- Minute and second aggregates
- Options data (greeks, open interest, historical contracts) — not used in v1
- Corporate actions (splits, dividends) handled correctly
- Point-in-time correct (important for Gate 5 walk-forward)

**Level 2 / order book depth: NOT in Developer tier.** This is the gap that forces v1 source's "watching it build" filter to use a proxy (or be dropped). Polygon Advanced adds L2 — revisit if Phase 5 Gate 6 shows slippage blowing up the proxy version.

Build a local data cache from day 1 — don't hit the API during backtests:
- Pull historical bars once, store as Parquet files partitioned by ticker/date
- Live updates via API only for recent data
- Universe history: snapshot QQQ / Nasdaq-100 constituents monthly so we can reconstruct point-in-time tradeable universes

---

**The 7-Gate Gauntlet (STRICT — all gates every time, no exceptions)**

For every strategy from Phase 4:

*Gate 1 — Dry run* (already done in Phase 4)

*Gate 2 — Single-period full backtest*
2-year window with realistic costs. Does the equity curve look like instructor's claimed results? If grossly misaligned → debug implementation before proceeding.

*Gate 3 — Multi-regime backtest*
Run separately on:
- 2017 (calm uptrend)
- Mar–Jun 2020 (crash + V-recovery)
- 2022 (sustained bear / high vol)
- 2023 (narrow AI bubble uptrend — relevant for QQQ names)
- 2024–present (choppy)
A regime-specific strategy isn't automatically bad — but you need to KNOW which regime it's for and build a detector.

*Gate 4 — Parameter sensitivity*
Sweep every parameter ±50%. Stable results across sweep = good. Large P&L swings from tiny param changes = overfit.

*Gate 5 — Walk-forward validation*
Optimize on data up to T, trade T → T+6mo with locked params, re-optimize, repeat. Simulates real-world use. In-sample wins that fail walk-forward = overfit.

*Gate 6 — Cost stress test*
Re-run the winning backtest with 2x assumed costs AND 2x assumed slippage. Survives? Edge is real. Fails? Edge is too thin for live. **Especially important for v1 source given the L2 proxy — if the proxy is optimistic, Gate 6 should expose it.**

*Gate 7 — Kill decision*
Pass = advance to Phase 6 paper trading. Fail at any gate = archive with post-mortem in `strategies/<name>/archived/`. Never delete — future-you might learn from it.

**Expected attrition: 2–4 survivors per 10 candidates.** Given v1 source starts with 3–5 candidates, expect **1–2 survivors to Phase 6**. If everything passes, the testing is broken.

**What if 0–1 strategies survive the gauntlet?**

Do NOT proceed to Phase 6 with marginal candidates. Options, in order:
1. Re-run Phase 0 smoke test on a different course — maybe v1 source was too L2-dependent for codification without L2 access
2. Return to Phase 2/4 with better prompts or a different extraction approach
3. Upgrade to Polygon Advanced for L2, re-run Phase 4 spec with real L2 features, re-run gauntlet
4. Accept the wiki as the project's deliverable (per the top-level Scope section)

**Kill criteria:** if after 2 full course dumps zero strategies survive, the project's primary scope is formally the knowledge system. Phases 6–7 archived as future work, not abandoned — the wiki remains useful and the infrastructure stays intact for a future course with better codifiability.

---

**Cost model (must be realistic)**
- Commissions: zero for stocks at Alpaca/IBKR (accurate)
- SEC/FINRA fees: yes, small but real
- Spread crossing: 50% of quoted spread on market orders (conservative)
- Slippage: model as function of position size vs avg volume (larger = worse)
- Borrow fees for shorts: use actual data where available, conservative estimate otherwise
- Overnight financing for margin: applicable if holding multi-day leveraged

---

**Infrastructure**

```
backtesting/
  engine/
    runner.py              # event loop over bars, calls strategy.on_bar
    cost_model.py          # commissions, slippage, spread
    regime_definitions.py  # named date ranges
    universe_history.py    # point-in-time QQQ/Nasdaq-100 membership
    data_cache.py          # Parquet local cache over Polygon
  protocols/
    full_gauntlet.py       # runs gates 2-6 automatically
    param_sweep.py
    walk_forward.py
  reports/
    <strategy>/<run_date>/
      equity_curve.png
      trade_log.csv
      stats.json
      regime_breakdown.md
      sensitivity_heatmap.png
      verdict.md            # human-written conclusion
```

Reports are **dated and immutable**. Never overwrite, never edit post-hoc. This protects against the subtle form of overfitting where you "keep iterating" while pretending you're not.

---

**The meta-discipline: research journal**

Every backtest run gets logged BEFORE looking at results:

```markdown
## 2026-05-03 v1-strategy-v1 run #3
- Hypothesis: 1.5 ATR stop vs 1 ATR will reduce max DD
- Prediction: lower max DD, slightly lower CAGR
- Result: [filled in AFTER run]
- Kept or killed: [filled in]
```

Writing the prediction before seeing results is what keeps you honest. If a strategy only "keeps improving" with tweaks, the journal shows the pattern and you kill it.

---

**Wiki integration**

Every backtest verdict gets filed back to the strategy's wiki page:

```markdown
## Backtest History
- 2026-05-01 v1 (with volume proxy): failed Gate 3 (only worked 2023). Archived.
- 2026-05-15 v2 (tighter distribution filter): passed 1–5, marginal Gate 6. Advanced to paper.
- 2026-06-10 v2 retest with updated data: confirmed, still passing.
```

Wiki stays current; at a glance you see alive / dead / uncertain.

---

**What Phase 5 produces**
- Custom backtesting engine built on Phase 4 `Strategy` interface
- Polygon-backed local data cache (Parquet)
- Automated 7-gate gauntlet protocol
- Dated, immutable backtest reports per run
- Research journal with pre-registered hypotheses
- 1–2 strategies from first v1 source pass surviving to Phase 6 (expected)
- Wiki pages updated with verdicts

**Status:** 🟡 In planning

---

### Phase 5½: Strategy Command Center (cross-cutting — scaffolded in Phase 5, grows through 7)

**Not a standalone phase — a cross-cutting UI layer that evolves alongside Phases 5, 6, 7. Scaffolding built during Phase 5, panels added as new capabilities come online.**

**Purpose:** The single view you use to operate the system. Answers "what is this strategy, how well does it work, what is it finding right now, and how does it compare to alternatives?"

---

**Views**

*Portfolio Overview (`/`)*
- Total P&L across all live/paper strategies
- Current positions + exposure
- Risk gate utilization (distance to killswitches)
- Capital allocation per strategy
- System health indicators (bot heartbeat, data feed status, last reconciliation)

*Strategy Comparison (`/strategies`)*
- Sortable table: row per strategy, columns for CAGR, Sharpe, max DD, win rate, profit factor, status, current candidates
- Status badges: research / backtested / paper / live / archived
- Today's open candidates count per strategy
- Correlation matrix — are strategies actually diversified or just different words for same thing?
- Regime fit — which strategies match current market conditions

*Strategy Detail (`/strategies/<name>`)*
- Overview header: name, thesis, status, codeability score, credibility tier, source links
- Backtest: equity curve, key stats, regime breakdown, parameter sensitivity heatmaps
- Current candidates: tickers matching setup RIGHT NOW, ranked by signal strength
- Recent trade history (paper or live)
- Live performance vs backtest (if running): slippage tracking, fill quality
- Links to: wiki page, spec.md, code, archived versions

*Candidates Feed (`/candidates`)*
- Today's setups across ALL strategies (including research-only)
- Filterable by strategy, ticker, signal strength
- Deep link to the strategy that generated each candidate

*Review Queue (`/review`)* — Phase 2 extraction review
*Ingestion (`/ingest`)* — Phase 1 ingestion dashboard
*System (`/system`)* — bot health, logs tail, risk gate status, incident feed

One Streamlit app, multiple pages, one deployment.

---

**The Scanner — new runtime component**

Continuous process that runs strategy setup-detection logic against current market data WITHOUT placing orders.

Implementation: reuses Phase 4's `Strategy` interface. Call `universe()` + `on_bar()` against live data with orders muted. Stores ranked candidate list, updates on schedule (bar close for intraday, EOD for swing).

**Scanner runs on ALL strategies, including unvetted research-only ones.**

Why this is valuable: watch a strategy behave before committing to full backtest. If the setup fires constantly on garbage, you learn that cheaply. If it rarely fires but picks good names, that's a signal. Turns the dashboard into a research acceleration tool, not just a monitor.

Scanner storage: SQLite table `candidates`:
```
candidate_id, strategy_id, ticker, timestamp,
signal_strength, setup_details (JSON),
hypothetical_entry, hypothetical_stop, hypothetical_target
```

Never writes orders. Ever. Isolated by code path, not just config.

---

**"Possible performance" for non-live strategies — BOTH interpretations**

*Interpretation A — Retroactive (concrete, honest)*
For any strategy (including research-only), run a mini-backtest on the last 30/60/90 days. Show: "what would this strategy have done on MY recent data?" Lets you compare research strategies against paper strategies on the same time window.

*Interpretation B — Forward-looking projection (speculative, labeled as such)*
Monte Carlo simulation from backtest stats: expected returns, drawdown distributions, time-to-recovery at user-specified capital and sizing.

**Important discipline:** Interpretation B gets prominently labeled "PROJECTION — not a forecast, based on historical stats that may not repeat." Forward-looking projections are where overconfidence lives. Honest UI mitigates but doesn't eliminate the risk. User should read these as "stress test under assumption of stationarity" not "what will happen."

---

**Evolution across phases**

*Phase 5 build — scaffolding:*
- Streamlit app shell, page structure
- Portfolio/Strategies/Strategy-Detail pages reading from backtest reports
- Scanner (runs against historical replay for development)
- Interpretation A retroactive mini-backtest engine
- Interpretation B Monte Carlo calculator

*Phase 6 additions — live data:*
- Scanner starts running against real-time Alpaca data
- Strategy Detail adds "live performance" panel (paper)
- Candidates feed becomes live
- System health page wired to bot heartbeat
- Risk gate utilization display

*Phase 7 additions — real money:*
- Live positions + real P&L in Portfolio Overview
- Incident feed on System page (from Phase 7 incident log)
- Tightened risk limits displayed
- Daily/weekly/monthly report archive browsable

---

**Layout**

```
dashboard/
  app.py                      # Streamlit entry point
  pages/
    01_portfolio.py
    02_strategies.py
    03_strategy_detail.py
    04_candidates.py
    05_review.py              # wraps Phase 2 review
    06_ingest.py              # wraps Phase 1 ingest
    07_system.py
  components/
    equity_curve.py
    regime_breakdown.py
    candidates_table.py
    risk_gauge.py
    montecarlo_viz.py
  data/
    backtest_loader.py        # reads dated backtest reports
    live_state_loader.py      # reads live SQLite
    scanner_output.py         # reads candidates table
    wiki_loader.py            # reads wiki DB for strategy metadata

scanner/
  runner.py                   # continuous setup-detection process
  storage.py                  # candidates table writes
  replay.py                   # historical replay mode for dev
```

---

**What Phase 5½ produces**
- Single operator UI for the whole system
- Scanner continuously surfacing candidates from every strategy (even research-only)
- Retroactive mini-backtest capability for fast comparison
- Forward-looking Monte Carlo with honest labeling
- A foundation that grows without rewrites across Phases 5 → 6 → 7

**Status:** 🟡 In planning

---

### Phase 6: Paper Trading (≥ 6 weeks calendar time — the duration gate cannot be compressed)

**Purpose:** Not to prove the strategy works (Phase 5 did that). To prove the SYSTEM works under conditions that can't be simulated — data feeds, order routing, partial fills, real-time events, and operator psychology.

---

**What paper trading actually tests**

1. **System reliability** — can the bot run unattended for weeks without crashing? Recover from data feed outages? Restart cleanly?
2. **Execution quality** — do live fills match backtested fills? Slippage within assumption? (Especially critical for the L2-proxy version of v1 source.)
3. **Live data vs historical** — do signals fire the same way on raw live data as on cleaned historical?
4. **Real-world events** — earnings, halts, circuit breakers, Fed days, OpEx, holidays
5. **Operator psychology** — can YOU watch the bot lose money / take dumb trades / survive drawdowns without intervening? **If you can't resist intervening in paper, you absolutely can't in live.**

---

**Broker: Alpaca (paper) — v1 only**

Rationale:
- Same REST + WebSocket API as live; flip a flag to go live
- Free, fake $100k, good Python SDK (`alpaca-py`)
- Market/limit/stop/bracket orders, fractional shares, shorts

Caveats:
- Paper fills too generous (instant @ mid). Real will be worse. Budget for this in the comparison reports.
- No automatic state reset on runaway bots
- Options paper is limited (defer options to Phase 7+)

IBKR paper deferred — revisit if/when options or futures become v2 scope.

---

**Hosting: Local now, VPS later**

v1 runs on user's local machine. Simple, zero cost, fast iteration.

Requirements even for local:
- Always-on during market hours (wake settings, screen lock behavior)
- Stable internet (cellular hotspot backup ideal)
- `systemd`/`launchd` or equivalent for auto-restart on crash
- Clean shutdown handlers so positions/state aren't corrupted on restart

**Migration trigger to VPS:** any of →
- Missed trades due to local machine issues (internet drop, sleep, update reboot)
- Going live with real money (VPS mandatory — no "my laptop died" excuses with real capital)
- Running multiple strategies that need different maintenance windows

VPS target when we migrate: $5–10/month DigitalOcean or Hetzner. Designed for this from day 1 — `config/` drives environment, no hardcoded paths, SQLite works the same everywhere.

---

**What must exist BEFORE Phase 6 starts — non-negotiable**

*State persistence*
- Every position, pending order, strategy internal state in SQLite
- Bot can be killed and restarted at any moment without losing context
- Startup always reconciles DB state with broker's actual state (source of truth = broker)

*Risk gate (MUST exist before first paper trade)*
- Max daily loss → flatten + halt
- Max position size per ticker
- Max portfolio concentration
- Max open positions
- Per-strategy loss limits (one bad strategy can't drain the account)
- Manual kill switch — one command flattens everything
- **Deliberately trigger each killswitch at least once during paper to verify it works.** Paper-trading with untested killswitches teaches you that you don't actually have killswitches.

*Logging + monitoring*
- Structured logs for every bot decision (signal fired, order sent, fill received, risk check fail)
- Real-time Streamlit dashboard: positions, today's trades, P&L, bot health, recent signals
- Alerts (email/SMS/Discord webhook): unexpected drawdown, unusual volume, repeated rejections, data feed disconnection

---

**Layout**

```
execution/
  runtime/
    bot.py                    # main event loop
    broker/
      base.py                 # BrokerInterface (so IBKR etc. can swap later)
      alpaca.py               # paper + live, same code
    market_data/
      alpaca_ws.py
      reconciliation.py       # cross-check with Polygon cache
    state_manager.py          # DB-backed strategy state
    risk_gate.py              # killswitches — blocks orders before broker
    reporting.py
  dashboard/
    app.py                    # live Streamlit
  config/
    strategies.yaml           # which strategies live, at what size
    risk_limits.yaml
```

Note: `broker/base.py` is the same pattern as Phase 4's `Strategy` interface. Bot talks to `BrokerInterface`. Alpaca today, IBKR/others tomorrow, bot code unchanged.

---

**Weekly comparison report: paper vs backtest**

Generated automatically each week for each live strategy:
- Signal count: bot took N vs backtest would have taken M on same period. N ≠ M → live/historical data discrepancy → investigate.
- Fill quality: avg slippage vs assumption. Worse than assumption → update cost model → re-run Phase 5. Strategies may get eliminated here.
- P&L: within normal backtest variance? If live much worse, something's broken. Almost never "the market changed."

**v1-specific:** the volume-proxy version of "watching it build" is the #1 suspect if live signals diverge from backtest. Track proxy performance explicitly.

Strategy whose paper results meaningfully diverge from backtest → back to Phase 5 or killed. Don't hope for convergence.

---

**Duration gate — rules-based, not feelings-based**

Advance to Phase 7 only when ALL of:
- ≥ 6 weeks elapsed
- ≥ 40 trades taken by the strategy
- ≥ 1 significant market event survived (earnings / halt / gap / Fed day / OpEx)
- ≥ 1 boring week where the bot took ≤ 2 trades and you still reviewed the logs daily (tests your ability to stay engaged when nothing's happening — the dangerous state)
- ≥ 1 killswitch deliberately triggered and verified
- ≥ 1 data-feed outage, crash, or manual restart recovered cleanly without state corruption or missed fills
- Weekly comparison reports show paper P&L within expected variance of backtest

---

**What Phase 6 produces**
- Production-grade bot running unattended, locally (VPS migration path ready)
- 6–12+ weeks of paper history per strategy
- Verified risk gates (proven by deliberate triggers)
- Verified recovery (proven by deliberate/actual restart)
- Live dashboard showing health + performance
- Comparison reports proving live fills track backtest assumptions
- A trained operator (you) who has watched the bot do dumb things and not intervened
- 1 strategy (from Phase 5's 1–2 survivors) cleared for real money

**Status:** 🟡 In planning

---

### Phase 7: Live Trading (only if Phase 6 gates passed)

**The single most important rule:** Phase 7 is Phase 6 with real money and smaller size. No new strategies, no new logic, no new features. Anything new goes back through Phase 5 → Phase 6 first. If you violate this rule, everything before it was theater.

---

**Starting capital: $1–2k**

Rationale:
- Bugs not caught in paper WILL manifest in first 30 days. Want them to cost hundreds, not thousands.
- Psychology at 1% of net worth vs 10% vs 30% is genuinely different. Learn gradually, not at scale.
- If system can't find edge on $2k, it won't find it on $200k. Starting small is information.

**Scaling schedule**
- Week 1–4: Tiny. ONE strategy. 20% of planned position sizes. Watch everything.
- Week 5–12: If weeks 1–4 match expectations → scale to full planned position sizes, still one strategy
- Month 4+: Consider adding a second strategy — ONLY if it independently completed its own Phase 6 with 3+ months of paper
- Beyond: Grow capital only as real-money track record justifies (real-money Sharpe, real-money DD, real-money recovery)

---

**Risk limits: TIGHTER than Phase 6**

Approach: conservative by default, loosen only after 3+ months of real-money data. Never loosen during drawdown.

Starting live limits:
- Max daily loss: 1.5% (vs Phase 6's typical 3%)
- Max position size: 50–70% of what backtest assumed optimal
- Max portfolio concentration: strict first 3 months
- Weekly drawdown halt: after -X% in a week, halt for the week and review
- All Phase 6 killswitches still active

Revenge-loosening (tightening or loosening limits mid-drawdown) is a known failure pattern. Limits get changed in writing, in advance, during calm periods, never in the moment.

---

**What's different from Phase 6**

*Taxes* — every trade is a taxable event. Cost basis, wash sales, ST vs LT tracking. Factor tax drag into expected returns: 20% pre-tax CAGR at high turnover ≈ ~14% post-tax.

*Broker reality* — real rejections from PDT rules (<$25k accounts), hard-to-borrow shorts, halts, regulatory blocks. Bot must handle gracefully, NOT retry into infinite loops.

**PDT warning specific to v1 source:** the strategy is intraday with a 5-minute rule. That's day-trading pattern behavior. With <$25k account, you're PDT-capped at 3 day trades per 5 business days. **Starting capital of $1–2k will rapidly trigger PDT limits** on a successful intraday strategy. Options:
- Accept the PDT constraint and only take 3 trades / 5 days (strategy frequency likely supports this)
- Raise starting capital above $25k (conflicts with "tiny starter" discipline)
- Extend strategies to swing mode (v2 goal — daily/weekly bars, held overnight, PDT doesn't apply)
- Use cash account (no PDT, but T+2 settlement restricts turnover differently)

This should be resolved at the latest during Phase 6 capital planning, not discovered on day 1 of Phase 7.

*Corporate actions* — splits, dividends, spinoffs, tender offers happen during multi-week holds. State reconciliation must handle all of these.

*Your psychology at scale* — 5% DD on paper ≠ 5% DD on $2k ≠ $50k. Expect to surprise yourself.

---

**New engineering requirements (not needed in paper)**

*Reconciliation with extreme paranoia*
- Every startup: reconcile DB state vs broker state. Discrepancy = halt.
- End of every trading day: full reconciliation. Discrepancy = halt.
- Positions in DB must always match broker. Trade logs must match.
- Bugs in reconciliation cost real money. Be paranoid.

*Alerting that reaches you*
- Phone push for: killswitch triggers, broker rejections, data feed disconnection during market hours
- Daily summary email/text even when nothing happened (silence is ambiguous — was it healthy or dead?)

*Dead man's switch*
- No heartbeat for N minutes during market hours → alert
- Still no heartbeat at M minutes → separate process attempts to flatten positions

*VPS migration complete before live*
- No "my laptop died" excuses with real capital
- $5–10/mo DigitalOcean or Hetzner
- Proper monitoring, restart-on-crash, log retention

---

**Incident log discipline (committed)**

Every anomaly → written incident report, no exceptions. Format:
```
# [YYYY-MM-DD] <slug>
- What happened:
- When (exact timestamp):
- What the bot did:
- What I did:
- Root cause:
- Fix:
- Prevention (what stops recurrence):
```

Files in `execution/live_ops/incidents/`. **Reviewed monthly.** Compounds into an institutional memory of what can go wrong.

---

**Exit criteria (turning the bot off isn't failure, it's the system working)**

- Strategy dies: 3+ months real results materially worse than backtest, explanations exhausted → archive, back to Phase 4/5
- Regime shift: regime detector fires, bot off for unsupported regimes
- Bug discovered: kill trading, fix, re-paper, resume
- Life changes: if can't give the attention needed, turn it off. Unattended bots are how people lose everything at 3am.

Goal: extract edge safely when edge exists. Not "run forever."

---

**Ongoing operations (budget for real work)**

- **Weekly:** review logs, incidents, P&L, comparison reports
- **Monthly:** strategies' performance vs backtest, wiki updates, incident log review
- **Quarterly:** re-run Phase 5 gauntlet on live strategies with fresh data (confirm edge hasn't decayed)
- **Annually:** full audit — strategies, infra, costs, taxes, risk framework

Budget ~2–4 hours/week. If you can't, reduce scope.

---

**Layout (mostly reuse from Phase 6)**

```
execution/
  runtime/
    bot.py                    # same bot, live mode
    broker/
      alpaca.py               # same class, live API key instead of paper
    reconciliation.py         # NEW — exhaustive state checks
    deadman.py                # NEW — heartbeat + fail-closed
  live_ops/
    incidents/
      YYYY-MM-DD-<slug>.md    # every anomaly
    reports/
      daily/ weekly/ monthly/
  config/
    live_risk_limits.yaml     # tighter than paper
    strategies_live.yaml      # explicit opt-in per strategy
```

---

**What Phase 7 produces**
- Real trading with real (small) capital
- Daily/weekly/monthly reporting
- Growing incident log (real data)
- A living system being tuned, not rebuilt
- A track record informing what's next: more strategies? more capital? turn it off?

---

**Honest final note**

Most retail algo trading projects don't make money. Phase 7 is where we find out which category this one is in. Even if trading doesn't work out, we will have built:
- A genuinely useful knowledge-digestion system
- A rigorous research methodology
- Production-grade execution infrastructure
- Deep, specific understanding of trading psychology

Those are valuable regardless. The bot making money is the cherry, not the point.

**Status:** 🟡 In planning

---

## 🧱 Tentative Tech Stack
- Python 3.12 throughout (pinned via `.python-version`, managed by `uv`)
- `uv` for env + deps (loose constraints in `pyproject.toml`, exact pins in `uv.lock`)
- `ruff` (lint + format), `mypy --strict` + `pydantic.mypy`, `pytest` + `pytest-cov`, `pre-commit` (ruff + mypy + gitleaks + hygiene hooks), GitHub Actions CI
- Claude API (Opus 4.7 / Sonnet 4.6 / Haiku 4.5) for extraction
- OpenAI Whisper API for transcription
- Polygon.io Developer tier for market data (Advanced tier revisit if L2 needed)
- Alpaca for execution (paper → live)
- SQLite + `sqlite-vec` → Postgres when outgrown · `yoyo-migrations` for schema versioning
- Pydantic v2 + `pydantic-settings` for typed models and env loading
- `pandas-ta` for indicators (pinned version)
- Streamlit for dashboards / review UI / ingestion UI
- Obsidian for wiki browsing (reads auto-generated markdown)
- `structlog` for structured logging from Phase 1

---

## ✅ Decisions Made

### Top-level
- Fully automated execution is the end goal
- "Some coding" skill level — plan assumes guided Python work
- Medium volume ingestion (hundreds of items, ongoing)
- Phased approach with hard gates between research → backtest → paper → live
- **Scope framing:** wiki-primary / trading-secondary — project deliverable is valuable even if no strategies survive gauntlet

### v1 content & market
- **v1 course: the v1 source content** (v1 source) — intraday 60-min bar system, pivot-based
- **Asset class: stocks only** — no options/futures/crypto in v1
- **Universe: NASDAQ / QQQ constituents + liquidity filter** — narrows scope, matches course's preferred names (NVDA, TSLA, AMZN)
- **Timeframe v1: intraday execution on 60-min bars + nightly daily-chart scan**
- **Timeframe v2 goal: daily + weekly scanning for swing mode**
- **L2 / order flow: not available** — backtesting uses volume proxy via Polygon 1-min data; L2 upgrade deferred pending Phase 5 gauntlet results

### Phase 1
- OpenAI Whisper API for audio transcription
- Ingest-as-found workflow (not batch)
- Modular pipeline — each source type is a pluggable handler
- Target UX inspiration: kapa.ai-style LLM wiki over ingested content
- Local file storage + SQLite (no cloud in v1)
- Twitter/X deferred — not in v1
- v1 build order: scaffolding → local video → YouTube → Discord → (stubs for PDF/EPUB/article)
- Structured logging with `structlog` from day 1
- Secrets via `.env` + `python-dotenv` from day 1
- **Discord ingestion: pasted text, not DiscordChatExporter** — user copies messages from a member-view export and the handler normalises. Sidesteps DCE ToS violation; eliminates throwaway-account requirement.
- **Course platform text:** user extracts and provides content directly (resolved 2026-04-22). No platform-specific scraper. Handler accepts text blobs with source metadata; probably shares the Discord pasted-text handler.
- **Transcripts persisted as `.md` files in repo** (alongside SQLite index). Enables cloud-portable Phase 2 work; SQLite is a derived, rebuildable index, not the source of truth.
- **Project layout** (resolved 2026-04-22): real Python package at `trading_wiki/`, tests mirror at `tests/`, migrations at `migrations/`. `pyproject.toml` (PEP 621) is the single source of truth for deps and tool config. Python pinned to 3.12 via `.python-version`.
- **Tooling layer frontloaded** (resolved 2026-04-22): `uv` for env+deps (loose constraints in pyproject, exact pins in committed `uv.lock`); `ruff` for lint+format; `mypy --strict` (with `pydantic.mypy` plugin) checking both `trading_wiki/` and `tests/`; `pytest` + `pytest-cov` (branch coverage on); `pre-commit` running ruff, mypy, gitleaks, and basic hygiene hooks; GitHub Actions CI runs the full pre-commit suite plus pytest on push to main and on every PR.
- **TDD discipline** (resolved 2026-04-22): RED → GREEN → REFACTOR with one behavior per cycle. Production code only after a failing test. Currently 26 tests at 97% coverage.
- **`ContentRecord` and `Segment` are Pydantic v2 models** with a shared `_StrictModel` base that sets `extra="forbid"` so typos in field names raise instead of silently dropping data. `Segment` carries optional float `start_seconds`/`end_seconds` so the same model serves video transcripts and untimestamped text. `BaseHandler` is an `abc.ABC` with abstract `can_handle` and `ingest` — the only extension seam for new source types.
- **SQLite schema** (resolved 2026-04-22): synthetic `INTEGER PRIMARY KEY` on `content` with `UNIQUE(source_type, source_id)`; ISO-8601 TEXT for timestamps; JSON TEXT for `metadata`; segments normalized into a separate table with `FK ... ON DELETE CASCADE` and `UNIQUE(content_id, seq)`; nullable `embedding_id` column reserved for the future `sqlite-vec` virtual table. Indexes on `source_type`, `parent_id`, `content_id`.
- **`sqlite-vec` virtual table deferred** to a later migration once Phase 2 picks an embedding model and dim (voyage-3 = 1024 / openai-3-small = 1536 / openai-3-large = 3072). The `embedding_id` column is in place; the vec0 table is not.
- **Migrations:** `yoyo-migrations` (numbered SQL files in `migrations/`) chosen over Alembic — lightweight, no SQLAlchemy coupling, applier is a 10-line wrapper in `core/db.py`.
- **Settings loader:** `pydantic-settings` `Settings` class — `SecretStr | None` for all API keys (redacted in repr/logs, missing values explicit rather than blank strings), `Literal[...]` for `log_level` so typos raise immediately, `Path` for `db_path` and `content_dir`. All keys optional and default to `None` so the project remains runnable without credentials for systems not yet built; calling code validates at the use site.
- **`.env.example` updated** (2026-04-22): `DISCORD_USER_TOKEN` block removed. Pasted-text Discord ingestion needs no env vars.
- **Handler architecture** (resolved 2026-04-22 with task #4): handlers are thin orchestration on top of `core/` building blocks. The pattern is "core has the reusable mechanics; handlers compose them per source type." For media handlers, the mechanics are storage + audio + transcribe; for paste-text handlers, just file-read.
- **Content-addressed storage** (`core/storage.py`, 2026-04-22): SHA-256 of file contents → `{storage}/{type}/{sha[:2]}/{sha}{ext}`. Sharded subdir keeps directory listings sane with thousands of files. `store_file` is idempotent — re-storing the same file is a no-op.
- **Whisper wrapper** (`core/transcribe.py`, 2026-04-22): uses `verbose_json` with `timestamp_granularities=["segment"]` so we get `Segment` objects with start/end seconds back, not just plain text. The OpenAI client is injected so tests pass a `MagicMock` and production callers construct one from `Settings.openai_api_key`.
- **Audio extraction** (`core/audio.py`, 2026-04-22): ffmpeg subprocess → mono 16 kHz **32 kbps** mp3. At that bitrate ~3 hours of audio fits comfortably under Whisper's 25 MiB upload limit. CI installs ffmpeg via `apt-get` so audio + handler tests actually run on the GitHub runner instead of being skipped.
- **`LocalVideoHandler`** (2026-04-22): `source_id` = SHA-256 of the video; original video stored content-addressed under `storage/local_video/`; extracted audio cached at `content/local_video/audio/{sha}.mp3` so re-ingesting the same file skips ffmpeg. `metadata` records source/stored/audio paths for traceability.
- **`YoutubeHandler`** (2026-04-24): `source_id` = YouTube video ID (canonical, no SHA needed since YouTube IDs are already unique). Audio cached at `content/youtube/audio/{video_id}.mp3`. URL recognition via regex covering `youtube.com/watch?v=`, `youtu.be/`, `m.youtube.com`, http or https. Original video file is **not stored** locally — YouTube hosts it and we only need the audio for transcription. `yt-dlp`'s `YoutubeDL` class is injected as `ydl_factory` so tests use a `MagicMock` context manager and production code uses the real class.
- **YouTube subtitle fast-path deferred** (2026-04-24): the handler currently always uses Whisper. When subtitles (human-made VTT/SRT, not auto-captions) are available, skipping Whisper would save API cost — meaningful for long v1 source videos. Add this as a follow-up; current handler works, just isn't cost-optimal.
- **`StrictModel` is public** (renamed from `_StrictModel` 2026-04-22 with task #4): `TranscriptionResult` and `YoutubeMetadata` reuse the `extra="forbid"` config without redeclaring it. Cross-module model imports are fine — `handlers/base.py` is the canonical home for shared model bases, `core/` modules import from there.
- **`core/pasted_text.py`** (2026-04-25): factored out as the shared mechanic backing both `DiscordHandler` and `CoursePlatformHandler`. `ingest_pasted_text(path, source_type, storage_dir) -> ContentRecord` reads the file as UTF-8, content-addressed-stores it under the caller's `source_type`, and packages a `ContentRecord` with `raw_text` = file contents verbatim. No message parsing — authors, timestamps, threads, replies are deferred to Phase 2 LLM extraction. Reason it's in `core/` not `handlers/`: matches the project's pattern that `core/` owns reusable mechanics and handlers compose them per source type. Keeps the two handler classes ~25 lines each.
- **`DiscordHandler`** (2026-04-25): source format `discord:<path>`. Strips the prefix and delegates to `ingest_pasted_text` with `source_type="discord"`. No env vars needed (the 2026-04-22 pasted-text decision deleted `DISCORD_USER_TOKEN`).
- **`CoursePlatformHandler`** (2026-04-25): source format `course:<path>`. Same shape as `DiscordHandler` but with `source_type="course_platform"` so credibility tier (Tier 1 in v1 source) and provenance stay distinct downstream. Splitting into two handler classes (rather than one parameterised handler) keeps the dispatch surface obvious — each source type appears in its own file in `handlers/` per the existing convention.
- **PDF / EPUB / article stubs** (2026-04-25): `PdfHandler` / `EpubHandler` / `ArticleHandler` implement the `BaseHandler` interface. `can_handle` returns the right boolean (`.pdf`, `.epub`, `http(s)://` respectively); `ingest` raises `NotImplementedError("… deferred to post-Phase-1")`. Excluded from coverage by the existing `raise NotImplementedError` rule in `pyproject.toml`. `ArticleHandler.can_handle` is intentionally broad — overlap with `YoutubeHandler` on YouTube URLs is the CLI dispatcher's concern, not the handler's.

### Phase 2
- **Phase 2A v0.2.2 = Pass 2 idempotency fix via `pass2_runs` table — SHIPPED 2026-04-29.** Both per-chunk extractors (`extract_trade_examples_for_chunk`, `extract_concepts_for_chunk`) gated their idempotency check on entity-row presence — fine when the LLM produced ≥1 entity, but indistinguishable from "never ran" when the LLM produced 0 entities. Surfaced when cid=10's te count went 0 → 1 between two batch runs (the chunk was routed to TradeExample, the first call returned `[]`; the second call ran the LLM again and happened to surface 1 entity). Concept extractor had the same latent bug, less observable because chunks routed to Concept rarely return `[]`. Fix: new `pass2_runs(source_chunk_id, extractor, prompt_version, entity_count, run_at)` table with `UNIQUE(chunk, extractor, prompt_version)`; both extractors check `pass2_run_exists` before calling, and `record_pass2_run` after every successful call (regardless of entity count). Migration `0005-pass2-runs.sql` includes backfill DML for existing entity rows (32 chunks across te/co); chunks that previously ran with 0 entities cannot be reconstructed and re-call the LLM once before becoming idempotent. Smoke test on the 10-video corpus: 5 zero-entity TradeExample chunks re-called for $0.04, all returning `[]` again (no DB delta); next batch run will be fully idempotent at $0.00. 2 new tests covering empty-result idempotency for both extractors. Tests now 210 unit + 2 integration. Removes the v0.3 follow-up that was added in v0.2.1.
- **Phase 2A v0.2.1 = +10 Tier 1 videos ingested, Pass 1 coverage-retry bug fix — SHIPPED 2026-04-28.** Ingested 10 additional Tier 1 videos via `LocalVideoHandler` in ~217s (~$0.50 Whisper); content_id 3-12, 1035 new segments. Ran Pass 1 + Pass 2 over all 10 at locked prompt versions. Two videos hit a latent bug in Pass 1's coverage-retry path: when `validate_coverage` failed, the retry appended a plain text user message after an assistant turn ending in a `tool_use` block — Anthropic's API requires a `tool_result` block referencing the prior `tool_use_id` (matching the convention `core/llm.py`'s schema-validation retry already uses). Untested at v0.1 because both prior videos passed coverage on first call. Fix: `_find_last_tool_use_id` helper + `tool_result`-shaped retry message; existing test stubs that asserted the buggy plain-string behavior were rewritten to use realistic SDK shape (`SimpleNamespace` `tool_use` blocks). Re-run after the fix succeeded on both failing videos. **Surfaced follow-up (added to v0.3 scope):** Pass 2 `trade_example` extractor is **non-idempotent** — re-runs call the LLM regardless of existing rows for the same `(source_chunk_id, prompt_version)` pair (Concept extractor *is* idempotent). Surfaced when one chunk's te count went 0 → 1 between the failed first run and the post-fix re-run. **Corpus after this slice:** 12 content rows / 95 chunks / 12 trade_examples / 112 concepts. **Unblocks** the v0.2 prompt-iteration backlog gate (n: 2 → 12 videos).
- **Review UI dev tool — SHIPPED 2026-04-26.** Local Streamlit page (`trading_wiki/review/app.py`) for hand-reviewing Pass 2 entities. Sidebar picks content_id + entity types (`trade_example`, `concept`) + sample mode (`stratified` / `all` / `random`) + N. Main pane shows extracted JSON next to source chunk text; status radio (accept / needs_fix / skip) + notes textarea + "Save & next" button. Findings written to `docs/superpowers/reviews/content<id>.md` (gitignored, one file per content_id). Resume across sessions by parsing the markdown for already-reviewed `(entity_type, entity_id)` pairs. Three pure modules (`sampling.py`, `findings.py`, view-only `app.py`) plus three new read-only DB helpers (`list_content_summaries`, `list_trade_examples_for_content`, `list_concepts_for_content`). No schema changes. Explicitly **not** Phase 2B — no queue triggers, no hard gates, no prompt-feedback loops, no `reviews` DB table; this is QoL tooling for the next hand-review cycle. Smoke-tested against the live DB; the spec/plan/findings all live under gitignored `docs/superpowers/`.
- **Phase 2A v0.2 = Pass 2 (TradeExample + Concept), per-type extractors, label-routed — SHIPPED 2026-04-26.** Vertical-ish slice extending Pass 1's plumbing to two distinct entity types in one slice — TradeExample (numeric prices when clean, NULL when vague) and Concept (term + definition + related_terms, no synonym canonicalization). New `extractors/pass2/` package with one file per entity type; dispatcher routes by Pass 1 label (`example` → TradeExample; `concept`/`qa` → Concept). Migrations 0003 + 0004. Per-chunk resilience added at the dispatcher. Strategy/Setup/Rule/MarketCondition deferred to v0.3 (cross-chunk, need Pass 3); Concept dedup deferred to v0.3. **v0.2 validation:** ran against the v1 source content's primary videos with zero failed chunks, all single-attempt at Sonnet 4.6. Hand-review of stratified spot-checks passed the acceptance bar; prompt versions **locked** at `pass2-trade-example-v1` and `pass2-concept-v1`. **CLI bug fix landed mid-review:** the documented `python -m trading_wiki.extractors.pass2 --content-id N` invocation was unreachable (CLI block placed in `__init__.py`'s `if __name__` guard rather than `__main__.py`); added `__main__.py`, removed the dead block, added a subprocess regression test. 180 unit tests + 2 integration tests, 98% coverage. **v0.3 prompt-iteration backlog** (revisit once more sources are ingested — n=2 is too small to commit to prompt rewrites): silent price rescaling, trade-attribution semantics, concept-vs-metaphor classification, term-naming bias toward the speaker's words, synonym dedup, and Pass 1 ↔ Pass 2 prompt-context contamination check.
- **Phase 2A v0.1 = Pass 1 only, one Tier 1 video — SHIPPED 2026-04-25.** Vertical slice: chunk + classify a real Tier 1 video with Sonnet 4.6, write to a new `chunks` table. Implementation: `core/llm.py` (schema-via-tool-use Anthropic SDK wrapper), `extractors/pass1.py` (transcript builder, coverage validator, idempotent `extract()`), migration `0002-chunks.sql`, `prompts/pass1.md` (version-stamped via `PROMPT_VERSION_PASS1`). **v0.1 validation:** ingested + chunked the v1 source's primary videos at `prompt_version=pass1-v1`; **first prompt iteration passed acceptance review without revision.** Pass 1 produced 17 sensibly-labeled chunks per 60-min part, with two `medium`-confidence flags falling on borderline transitional content (correctly hedged). Schema-validation retry logic worked as designed: one part's first call had over-length summaries; the retry-with-feedback fixed all of them. Embeddings, entity extraction, resolution, relationships, review UI, and chart pipeline remain deferred to later slices. **Next slice: v0.2 = Pass 2 (entity extraction → Strategy/Setup/Concept JSON).**
- **Phase 1 follow-up surfaced 2026-04-25:** `core/audio.py` default of 32 kbps mono mp3 produced files exceeding Whisper's 25 MiB sync upload limit for 3+ hour videos. Lowered to 16 kbps in commit `28f81ab`; new test asserts via ffprobe so the regression can't recur silently. Whisper also exhibits a hallucination loop on long silent audio (it transcribed a 10-min break in Part 02 as a single sentence repeated dozens of times, which Pass 1 correctly labeled `noise` but the underlying transcript is unusable for Pass 2). Acceptable for v0.1; revisit if Pass 2 starts pulling junk content from `noise`-labeled chunks.
- **LLM tiering:** Stakes-based — Opus 4.7 for high-stakes judgment (entity resolution of Tier 1 content, codeability scoring, strategy formalization), Sonnet 4.6 for everything else, Haiku 4.5 as future optimization
- **Extraction strategy:** Extract everything, tag low-confidence for review (not aggressive filtering)
- **Architecture:** Multi-pass pipeline (Classify → Extract → Resolve → Relate)
- **Graph:** Full entity resolution + relationship graph (accepting the added complexity)
- **Provenance:** Non-negotiable — every fact links back to source + timestamp + excerpt
- **Human review:** First-class pipeline feature with queue, gates, and feedback loops (not an afterthought)
- **Chart extraction:** Phased sub-pipeline — v1 (images from PDFs/Discord), v2 (video scene-change frames). v3 (recreation with real price data) explicitly deferred to post-Phase-7
- **Setup as first-class entity** between Concept and Strategy
- **Market conditions / regime** tagged at extraction time
- **Codeability rubric** (1–5) defined

### Phase 3
- **Wiki pattern:** Karpathy's LLM-Wiki pattern as UX layer on top of structured DB (not replacing it). Obsidian for browsing, auto-generated markdown, index.md + log.md + schema.md conventions

### Phase 4
- **Spec interview:** LLM-driven questioning, human corrects/overrides
- **Interface:** Build common `Strategy` interface FIRST, before any individual strategy — same interface used across backtest / paper / live
- **Signal / Setup / Strategy layers:** separate pure detectors, contextual filters, and full strategies
- **Indicators:** `pandas-ta` default, pinned, wrapped in `indicators/` module
- **Setup validation via extracted examples** runs before Phase 5 (cheap Gate 0)
- **Fuzzy strategies:** Keep in backlog (not dropped), potential future ML project, not v1
- **Repo:** Git-tracked `strategies/` folder, each strategy = own directory with spec + code + tests + notes + versions
- **Assumptions:** Tagged, versioned, testable — 30-50% of fields expected to need them, this is information not failure
- **First pass:** 3–5 strategies, not 10–15 — protect against Phase 4 motivation collapse
- **Testing tiers:** unit + golden-record + property-based + replay required
- **Jupyter dev-mode** for interactive iteration

### Phase 5
- **Framework:** Custom engine built on Phase 4 `Strategy` interface (maximum control, no adapter layer between backtest/paper/live). `vectorbt` opportunistically for fast param sweeps.
- **Data:** Polygon.io Developer tier (already subscribed). Build local Parquet cache, pull once, don't hit API during backtests.
- **Gauntlet:** All 7 gates strict, every time, no exceptions. Expected 1–2 survivors per 3–5 v1 source candidates.
- **Reports:** Dated + immutable, never overwrite. Research journal logs hypothesis BEFORE running backtest.
- **Wiki integration:** Verdicts filed back to strategy's wiki page
- **0-survivor branch:** re-smoke-test different course, OR upgrade to Polygon Advanced for L2, OR accept wiki-only scope

### Phase 5½
- **Strategy Command Center:** Cross-cutting Streamlit dashboard, scaffolded in Phase 5, grown through 6 & 7. Single operator UI.
- **Scanner:** Continuous setup-detection process runs on ALL strategies (including research-only) — orders muted by code path, writes to `candidates` table
- **Possible performance:** Both interpretations — retroactive mini-backtest (concrete) + forward-looking Monte Carlo (labeled as projection, not forecast)

### Phase 6
- **Broker:** Alpaca only for v1 (same API paper/live, flip a flag)
- **Hosting:** Local v1, designed from day 1 to migrate to $5–10/mo VPS. VPS mandatory before live trading.
- **Risk gates:** Non-negotiable — must exist before first paper trade, each deliberately triggered to verify
- **Duration gate:** RULES-BASED (not "when I feel ready") — ≥6 weeks, ≥40 trades, ≥1 event survived, ≥1 boring week, ≥1 killswitch verified, ≥1 recovery verified, paper P&L tracking backtest. All criteria required before Phase 7.

### Phase 7
- **Starting capital:** $1–2k — truly tiny, maximum learning, scale only as real-money track record justifies. **PDT constraint flagged** — must be resolved by end of Phase 6.
- **Risk limits:** Tighter than Phase 6 at start. Loosen only after 3+ months real-money data. Never loosen during drawdown.
- **Incident log:** Every anomaly = written report. Reviewed monthly. Non-negotiable discipline.
- **VPS:** Migration from local to VPS is MANDATORY before going live

### Cross-cutting
- **Feature store:** Deferred but budgeted for mid-Phase-5 (when 3+ strategies share indicators)
- **Observability:** Structured logging from Phase 1, metrics by Phase 5
- **Secrets management:** `.env` + gitleaks from day 1
- **Repo hosting:** **GitHub public, MIT** (flipped from private 2026-04-26 with full source-identifier redaction; original-private decision was 2026-04-22). Videos stay local (`.gitignore`d under `content/`); ingested transcripts, the SQLite DB, hand-reviews, per-slice plans/specs, and the filled `content_inventory.md` all stay local too. Everything framework-level — code, prompts, migrations, schema, this plan, `ARCHITECTURE.md`, `CLAUDE.md` — is committed so remote Claude Code sessions and Claude iOS can work against GitHub.
- **Cloud-portability seam:** ingestion (raw video → transcript) is the only strictly-local step. Phase 2 onward must run against committed transcripts + a migration-defined SQLite rebuildable from them — never require access to the raw video files.
- **ARCHITECTURE.md:** Maintain living architecture doc alongside plan

---

## 🚀 Opportunities for Improvement (review findings)

### 🎯 Setup Understanding (extraction + knowledge) — PULLED INTO V1
- **Setup as first-class entity** between Concept and Strategy (Schema updated)
- **Market conditions / regime per setup** (extraction-time tagging)
- **Setup validation via extracted examples** (cheap Gate 0 in Phase 4)

### 🛠 Implementation (code architecture + dev velocity) — PULLED INTO V1
- **Signal / Setup / Strategy abstraction layers**
- **Technical indicators library decision:** `pandas-ta` default, pinned
- **Explicit testing tiers per strategy:** unit + golden-record + property-based + replay
- **Jupyter dev-mode** for interactive iteration

### 📐 Cross-cutting (project health) — PULLED INTO V1
- **Living ARCHITECTURE.md**
- **Observability from Phase 1** (structlog + JSON logs)
- **Secrets management from day 1** (.env + gitleaks)
- **Named Risks section** (see below)

### Deferred (but budgeted for mid-Phase-5)
- **Feature store for precomputed bar features** — start with ad-hoc computation, formalize when 3+ strategies share indicators

---

## ⚠️ Named Risks

*Risks we acknowledge but don't necessarily solve. Named risks hurt less than surprise risks.*

**Legal / ToS**
- Course vendor may assert derivative-works claim over extracted content — mitigation: keep pipeline for personal use only, don't publish the wiki, don't monetize derivative models
- ~~Discord ToS prohibits self-bots / user-token automation (DiscordChatExporter route) — enforcement against personal archiving is rare but not zero. Mitigation: throwaway Discord account joined only to target server~~ **Resolved 2026-04-22:** ingestion approach changed to pasted text (no user token, no automation). Risk no longer applies.

**Platform / vendor**
- Polygon / Alpaca / OpenAI / Anthropic pricing or API changes that break the pipeline or change economics
- Broker outage during volatile market with open positions
- Model deprecation (Opus 4.7 → Opus 5.x etc.) — prompts may not transfer cleanly. Pin model IDs in config, plan for re-validation when migrating.
- Alpaca paper-fill model is more generous than live. Expect 5–20% worse fill quality live vs paper; build comparison reports around this assumption.

**Market / strategy — v1-specific**
- **L2 gap** — v1 source's "watching it build" filter is fundamentally L2-dependent. Proxy may work, may not. If Gate 6 fails consistently, either upgrade to Polygon Advanced or strategy doesn't survive without L2.
- v1 source's backtest period overlaps with the QQQ mega-cap bull run (2020–2021, 2023). Multi-regime testing (Gate 3) must separately prove performance in 2022 bear.
- Strategies that passed gauntlet decay silently in live — quarterly re-gauntlet (already planned) catches this, but only after losses
- Corporate actions (splits, mergers) creating stale-data bugs in bot
- **PDT rule constraint** at <$25k account — intraday strategy + starter capital = PDT trigger. Resolve by end of Phase 6 (see Phase 7 notes).

**Human / project**
- User loses interest before Phase 7 (the statistical default for side projects) — Phase 4 is the most likely collapse point
- Life change that removes attention bandwidth for ongoing ops (already addressed in Phase 7 exit criteria)
- Over-attachment to a strategy the data says is dead (the "just one more tweak" trap)
- Scaling capital faster than track record justifies after a good month
- Prompt-engineering rework when current models are deprecated — pin model IDs, plan for re-validation migration

---

## 🧩 Pre-Phase-1 Decisions

*All resolved. Remaining checkboxes are things to execute before code, not decisions to make.*

- [x] **Phase 0 smoke test** — **skipped 2026-04-22** (user opted out). Risk that the v1 source content is not cleanly codifiable is carried forward into Phase 1/2 rather than answered up front.
- [x] **Specific course identity** — **the v1 source content** ✅
- [x] **Asset class** — **Stocks only, QQQ/Nasdaq-100 + liquidity filter** ✅
- [x] **Timeframe** — **Intraday (60-min) + daily scan v1; daily/weekly swing v2** ✅
- [x] **Repo hosting** — **GitHub public, MIT** ✅ (flipped 2026-04-26 with redaction; original private 2026-04-22)
- [x] **Discord ingestion path** — pasted text (not DCE) ✅ (2026-04-22, supersedes prior DCE-verification task)

## 🧩 Deferrable Decisions

- [ ] **Capital level** (by Phase 5) — affects which strategies are even viable (minimum tick size, borrow fees, margin). PDT-resolution decision lives here.
- [ ] **Indicator library** (by Phase 4) — default `pandas-ta`; revisit if v1 source TradingView alignment issues appear
- [ ] **Broker secondary** (by Phase 7+) — if options/futures become in-scope, IBKR vs Tradier vs stay on Alpaca
- [ ] **Polygon Advanced upgrade** (decision point after Phase 5 Gate 6) — only if L2 proxy version fails stress test

---

## 📌 Next Steps

### Immediate actions
- [x] ~~Phase 0 smoke test~~ — **skipped 2026-04-22** (see Pre-Phase-1 Decisions)
- [x] ~~Verify DiscordChatExporter~~ — **superseded 2026-04-22**, pasted-text approach
- [x] **Course content inventory** — captured locally in `content_inventory.md` (gitignored; template at `content_inventory.example.md`); rough: ~12 core videos + ~10 adjacent, 10 min to ~3 hrs each, no PDFs, Discord via paste, course-platform text TBD
- [x] **`.env.example` + `.gitignore`** — done 2026-04-21
- [x] **Repo hosting** — **GitHub public, MIT** (flipped 2026-04-26 with redaction; original private 2026-04-22)
- [x] ~~Clarify format of course-platform text content~~ — **resolved 2026-04-22:** user provides content directly; no platform-specific handler needed
- [x] ~~`git init` + push to new GitHub private repo~~ — **resolved 2026-04-22:** repo `hencray/trading-wiki` already existed from 2026-04-21; today's pre-Phase-1 work committed as `70d13b1` and pushed to `origin/main`.

### Phase 1 kickoff checklist
- [x] ~~Set up repo structure~~ — done 2026-04-22 (`trading_wiki/` package, `tests/`, `migrations/`, `ARCHITECTURE.md`)
- [x] ~~Build `ContentRecord` + SQLite schema + base handler interface~~ — done 2026-04-22, TDD'd
- [x] ~~Add `structlog` JSON logging~~ — done 2026-04-22 (`trading_wiki/core/logging.py`)
- [x] ~~Add `.env` + `python-dotenv`, optional `gitleaks` pre-commit~~ — done 2026-04-22 (pydantic-settings `Settings`; gitleaks runs in pre-commit + CI)
- [x] ~~Implement local video handler~~ — done 2026-04-22 (`LocalVideoHandler` + `core/storage.py` + `core/transcribe.py` + `core/audio.py`; ffmpeg subprocess + Whisper API)
- [x] ~~Implement YouTube handler~~ — done 2026-04-24 (`YoutubeHandler` + `core/youtube.py`; yt-dlp wrapper, video_id as source_id, audio cached at `content/youtube/audio/{video_id}.mp3`)
- [x] ~~Implement Discord handler (pasted-text normaliser)~~ — done 2026-04-25 (`DiscordHandler` + `core/pasted_text.py`; `discord:<path>` prefix, content-addressed storage, no message parsing in v1)
- [x] ~~Implement course-platform text handler~~ — done 2026-04-25 (`CoursePlatformHandler`; `course:<path>` prefix, reuses `core/pasted_text.py` with `source_type="course_platform"`)
- [x] ~~Stubs for PDF / EPUB / article handlers~~ — done 2026-04-25 (`PdfHandler` / `EpubHandler` / `ArticleHandler`; `can_handle` matches extension/scheme, `ingest` raises `NotImplementedError`)

### Phase 1 follow-ups (Phase 2 prep, not Phase 1 gates)
- [ ] Implement CLI dispatcher (`trading_wiki/cli.py`) — `trading-wiki ingest <url-or-file>` walks handlers in priority order, returns first `can_handle=True`. Decide handler precedence (specific → generic) when wiring; at minimum YouTube before article so HTTPS YouTube URLs route correctly.
- [x] ~~Populate `trading_wiki/config.py`~~ — done 2026-04-25 as part of Phase 2A v0.1 (`MODEL_PASS1`, `PROMPT_VERSION_PASS1`, `PROMPT_PASS1_PATH`).

---

## 🗂️ Notes & Miscellaneous

### Brainstorm Pile
*(unfiltered ideas, park them here)*
-

### Resources / Links to Check
-

### Things to Decide Later
-

---

*End of consolidated project plan v1. Future edits: update `Last updated` date at top, append to Decisions Made, archive outdated sections rather than deleting.*
