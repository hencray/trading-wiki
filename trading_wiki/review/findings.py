"""Read/write the per-content_id markdown findings file used by the review UI."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

EntityType = Literal["trade_example", "concept"]
Status = Literal["accept", "needs_fix", "skip"]

REVIEWS_DIR = Path("docs/superpowers/reviews")


@dataclass(frozen=True)
class Finding:
    entity_type: EntityType
    entity_id: int
    status: Status
    chunk_id: int
    chunk_label: str
    prompt_version: str
    reviewed_at: datetime
    notes: str


def findings_path_for(content_id: int, base_dir: Path | str = REVIEWS_DIR) -> Path:
    """Return the markdown findings path for ``content_id`` under ``base_dir``."""
    return Path(base_dir) / f"content{content_id}.md"


_HEADER_RE = re.compile(r"^## item:(?P<type>trade_example|concept):(?P<id>\d+)\s*$")
_FIELD_RE = re.compile(r"^- (?P<key>\w+): (?P<value>.*)$")
_REQUIRED_FIELDS = (
    "status",
    "chunk_id",
    "chunk_label",
    "prompt_version",
    "reviewed_at",
    "notes",
)


def _parse_block(header_line: str, body_lines: list[str]) -> Finding:
    m = _HEADER_RE.match(header_line)
    if m is None:
        raise ValueError(f"malformed header: {header_line!r}")
    entity_type = cast(EntityType, m.group("type"))
    entity_id = int(m.group("id"))

    fields: dict[str, str] = {}
    for line in body_lines:
        fm = _FIELD_RE.match(line)
        if fm is None:
            continue
        fields[fm.group("key")] = fm.group("value")

    missing = [k for k in _REQUIRED_FIELDS if k not in fields]
    if missing:
        raise ValueError(f"item:{entity_type}:{entity_id} missing fields: {missing}")
    status = cast(Status, fields["status"])
    return Finding(
        entity_type=entity_type,
        entity_id=entity_id,
        status=status,
        chunk_id=int(fields["chunk_id"]),
        chunk_label=fields["chunk_label"],
        prompt_version=fields["prompt_version"],
        reviewed_at=datetime.fromisoformat(fields["reviewed_at"].replace("Z", "+00:00")),
        notes=fields["notes"],
    )


def read_findings(path: Path | str) -> list[Finding]:
    """Parse a findings markdown file. Missing file → []. Last write wins on duplicate ids."""
    p = Path(path)
    if not p.exists():
        return []
    lines = p.read_text().splitlines()

    by_key: dict[tuple[EntityType, int], Finding] = {}
    i = 0
    while i < len(lines):
        if lines[i].startswith("## item:"):
            header = lines[i]
            j = i + 1
            body: list[str] = []
            while j < len(lines) and not lines[j].startswith("## "):
                body.append(lines[j])
                j += 1
            f = _parse_block(header, body)
            by_key[(f.entity_type, f.entity_id)] = f
            i = j
        else:
            i += 1
    return list(by_key.values())


def _format_block(f: Finding) -> str:
    notes = re.sub(r"\s+", " ", f.notes).strip()
    reviewed_at = f.reviewed_at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        f"## item:{f.entity_type}:{f.entity_id}\n"
        f"- status: {f.status}\n"
        f"- chunk_id: {f.chunk_id}\n"
        f"- chunk_label: {f.chunk_label}\n"
        f"- prompt_version: {f.prompt_version}\n"
        f"- reviewed_at: {reviewed_at}\n"
        f"- notes: {notes}\n"
    )


def append_finding(path: Path | str, finding: Finding, *, content_id: int) -> None:
    """Append ``finding`` as a new block to the markdown file.

    Creates the file and parent directory on first write. Newlines in
    ``finding.notes`` are collapsed to single spaces so the markdown stays
    parseable by ``read_findings``.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    block = _format_block(finding)
    if not p.exists():
        p.write_text(f"# Review — content_id={content_id}\n\n{block}")
        return
    existing = p.read_text()
    if existing.endswith("\n\n"):
        sep = ""
    elif existing.endswith("\n"):
        sep = "\n"
    else:
        sep = "\n\n"
    p.write_text(existing + sep + block)


def reviewed_ids(findings: list[Finding]) -> set[tuple[EntityType, int]]:
    """Return the set of ``(entity_type, entity_id)`` pairs already reviewed."""
    return {(f.entity_type, f.entity_id) for f in findings}
