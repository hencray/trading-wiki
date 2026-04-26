# Content Inventory (template)

*Local-only document. Copy this file to `content_inventory.md` (gitignored) and fill in your own ingestion plan. Tracks what's in scope for Phase 1 ingestion.*

*Last updated: YYYY-MM-DD*

---

## Summary

- **Core videos:** TBD
- **Adjacent / deep-dive videos:** TBD
- **Duration range:** TBD
- **PDFs:** TBD
- **Discord:** ingestion via paste-in (see `handlers/discord.py`)
- **Course-platform text content:** ingestion via paste-in (see `handlers/course_platform.py`)

**Estimated audio volume:** *(videos × average duration)*
**Estimated Whisper cost:** *($0.006/min × estimated minutes)*

---

## Core videos

| # | Title | Duration | Source (local path / URL) | Transcribed | Notes |
|---|---|---|---|---|---|
| 1 |  |  |  | ☐ |  |

## Adjacent / deep-dive videos

| # | Title | Duration | Source | Transcribed | Notes |
|---|---|---|---|---|---|
| 1 |  |  |  | ☐ |  |

## Discord

- Server: *(name)*
- Channels in scope: *(channel list)*
- Ingestion method: copy/paste from a member-view export
- Raw pastes stored under `content/discord/` (gitignored); normalised transcripts committed as `.md` in `transcripts/discord/`

## Course-platform text content

- Ingestion method: user provides text content directly (no platform scraping)
- Content shape: *(describe)*
- Rough volume: *(estimate)*
- Handler: shared pasted-text normaliser, with `source_type=course_platform` metadata

---

## Ingestion status

- Phase 1 handlers implemented: *(list)*
- Items ingested: **0 / TBD**

## Update log

- **YYYY-MM-DD:** initial inventory captured.
