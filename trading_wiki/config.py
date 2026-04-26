"""Shared configuration constants and paths."""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent

# ─── Phase 2A — Pass 1 (chunk + classify) ──────────────────────
MODEL_PASS1 = "claude-sonnet-4-6"
PROMPT_VERSION_PASS1 = "pass1-v1"
PROMPT_PASS1_PATH = _REPO_ROOT / "prompts" / "pass1.md"
