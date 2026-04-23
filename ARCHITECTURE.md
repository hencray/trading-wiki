# Architecture

Authoritative scope, phasing, and decisions live in `PROJECT_PLAN.md`. This document captures the load-bearing structure of the code itself — what goes where and why. Update as the implementation evolves; archive obsolete sections rather than delete.

## Pipeline shape

```
Source → Handler → ContentRecord → Storage (SQLite + filesystem)
                                 → Phase 2 extraction (later)
```

Every source type plugs in as a handler conforming to a single interface. The ingest CLI dispatches to the right handler based on input type. Core modules (`db`, `storage`, `transcribe`, `logging`, `secrets`) are shared infrastructure that handlers depend on but do not own.

## Handler contract

`handlers/base.py` will define:
- `ContentRecord` — standardized output of every handler. Fields per `PROJECT_PLAN.md` §Phase 1: `source_type`, `source_id`, `title`, `author`, `created_at`, `ingested_at`, `raw_text`, `segments[]`, `parent_id`, `metadata`.
- `BaseHandler` — abstract interface. Minimum surface: `can_handle(source) -> bool`, `ingest(source) -> ContentRecord`.

To add a new source type: drop a new `handlers/foo.py` subclassing `BaseHandler`. No core changes required. This is the project's primary extension seam.

## Storage layout

- **SQLite DB** holds all `ContentRecord` rows. Path comes from `.env`.
- **Raw source files** content-addressed at `storage/{source_type}/{hash}.{ext}`.
- **Transcripts** persisted to disk as `.txt` / `.srt` alongside the DB row, so re-extraction never needs the original media file.

The DB must be rebuildable from committed transcripts via a migration. Raw videos stay local (gitignored under `content/`); transcripts and DB schema travel with the repo. See the cloud-portability seam below.

## Cloud-portability seam

Ingestion (raw video → transcript) is the **only** strictly-local step. Phase 2 onward must run against committed transcripts plus a migration-defined SQLite rebuildable from them. No phase later than 1 may require access to raw video files. This is what lets remote Claude Code / Claude iOS sessions work against the GitHub repo.

## Module map (target end-of-Phase-1 state)

| Path | Role |
|---|---|
| `handlers/base.py` | `ContentRecord` + `BaseHandler` interface |
| `handlers/local_video.py` | local video → ffmpeg audio → Whisper |
| `handlers/youtube.py` | YouTube → yt-dlp → existing subs or Whisper |
| `handlers/discord.py` | pasted-text normaliser (author / timestamp / thread heuristics) |
| `handlers/{pdf,epub,article}.py` | stubs — implement post-Phase-1 |
| `core/db.py` | SQLite schema + queries |
| `core/storage.py` | content-addressed file storage helpers |
| `core/transcribe.py` | Whisper API wrapper |
| `core/logging.py` | `structlog` JSON setup |
| `core/secrets.py` | `.env` loader + validators |
| `cli.py` | `ingest <url-or-file>` dispatcher |
| `config.py` | shared paths, model names, tunables |

## Discipline (from CLAUDE.md / PROJECT_PLAN.md)

- `structlog` JSON logging from day one — not retrofitted later.
- `.env` + `python-dotenv` from day one — never commit secrets.
- Pin package versions when adding dependencies.
- The `Strategy` interface (Phase 4) will be reused verbatim by backtest, paper, and live code paths. No adapters. The same discipline applies here: handlers conform to one `BaseHandler` interface, no per-handler adapters in the CLI.

## What this doc is not

- Not a substitute for `PROJECT_PLAN.md`. Phase decisions, gates, and timelines live there.
- Not a frozen contract. Phase 1 will refine the `ContentRecord` schema and storage details — update this file when that happens.
