"""Phase 2A Pass 3 — Concept entity resolution.

Embeds each Concept row via OpenAI text-embedding-3-small, finds
similarity-search candidate pairs via sqlite-vec, asks Opus 4.7 to verify
each pair, persists verdicts to ``concept_resolutions``.

Spec: docs/superpowers/specs/2026-05-11-pass3-concept-resolution-design.md
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import sqlite_vec  # type: ignore[import-untyped]
import structlog

_log = structlog.get_logger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_MODEL_VERSION = "text-embedding-3-small-v1"
EMBEDDING_DIM = 1536
EMBED_INPUT_MAX_CHARS = 8000
DEFAULT_THRESHOLD = 0.85


@dataclass(frozen=True)
class CandidatePair:
    concept_a_id: int
    concept_b_id: int
    cosine_similarity: float


@dataclass
class ResolveResult:
    embeddings_written: int
    candidate_pairs: list[CandidatePair]
    verifications: list[dict[str, Any]]
    total_embedding_tokens: int = 0
    total_llm_cost_usd: float = 0.0


@contextmanager
def _connect_with_vec(db_path: Path) -> Iterator[sqlite3.Connection]:
    """Open a sqlite3 connection with the sqlite-vec extension loaded."""
    conn = sqlite3.connect(Path(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _ensure_vec0_table(conn: sqlite3.Connection) -> None:
    """Create the ``concept_embeddings`` vec0 virtual table if absent."""
    conn.execute(
        f"""
        CREATE VIRTUAL TABLE IF NOT EXISTS concept_embeddings USING vec0(
            concept_id INTEGER PRIMARY KEY,
            embedding FLOAT[{EMBEDDING_DIM}]
        )
        """
    )


def _l2_distance_to_cosine_similarity(distance: float) -> float:
    """Convert L2 distance between unit vectors to cosine similarity.

    For unit-length vectors a, b: ||a - b||² = 2 - 2·cos(a,b).
    So cos(a,b) = 1 - dist²/2.
    """
    return 1.0 - (distance**2) / 2.0


def _embed_input_for_concept(term: str, definition: str) -> str:
    """Build the string to embed for a concept row. Truncates to
    ``EMBED_INPUT_MAX_CHARS`` so we don't blow the embedding model's
    token budget on pathologically-long definitions."""
    text = f"{term}: {definition}"
    return text[:EMBED_INPUT_MAX_CHARS]


def embed_concepts(
    db_path: Path,
    *,
    openai_client: Any,
    model: str = EMBEDDING_MODEL,
    prompt_version: str = "pass2-concept-v1",
) -> tuple[int, int]:
    """Embed every concept at ``prompt_version`` that doesn't yet have an
    embedding in ``concept_embeddings``. Returns ``(rows_written, input_tokens)``.

    ``openai_client`` must expose ``embeddings.create(input=..., model=...)``
    and return an object with ``.data[i].embedding`` (list[float]) and
    ``.usage.total_tokens``.
    """
    with _connect_with_vec(db_path) as conn:
        _ensure_vec0_table(conn)
        rows = conn.execute(
            """
            SELECT c.id, c.term, c.definition
            FROM concepts c
            LEFT JOIN concept_embeddings e ON e.concept_id = c.id
            WHERE c.prompt_version = ? AND e.concept_id IS NULL
            ORDER BY c.id
            """,
            (prompt_version,),
        ).fetchall()

        if not rows:
            _log.info("pass3.embed.no_new_concepts", model=model)
            return 0, 0

        inputs = [_embed_input_for_concept(r["term"], r["definition"]) for r in rows]
        response = openai_client.embeddings.create(input=inputs, model=model)
        token_count = int(getattr(response.usage, "total_tokens", 0))

        with conn:
            for row, data in zip(rows, response.data, strict=True):
                vec = list(data.embedding)
                if len(vec) != EMBEDDING_DIM:
                    raise ValueError(
                        f"unexpected embedding dim {len(vec)} for concept_id={row['id']}; "
                        f"expected {EMBEDDING_DIM}"
                    )
                conn.execute(
                    "INSERT INTO concept_embeddings(concept_id, embedding) VALUES (?, ?)",
                    (row["id"], sqlite_vec.serialize_float32(vec)),
                )

        _log.info(
            "pass3.embed.ok",
            model=model,
            rows_written=len(rows),
            input_tokens=token_count,
        )
        return len(rows), token_count


def find_candidate_pairs(
    db_path: Path,
    *,
    threshold: float = DEFAULT_THRESHOLD,
    top_k: int = 10,
) -> list[CandidatePair]:
    """Find pairs of concepts whose embeddings have cosine similarity
    ``>= threshold``. Excludes self-matches and de-dupes (a,b) vs (b,a).

    ``top_k`` is the KNN search depth per query concept. With 112 concepts
    this is overkill, but keeps the implementation honest for larger
    corpora.
    """
    pairs: dict[tuple[int, int], float] = {}
    with _connect_with_vec(db_path) as conn:
        _ensure_vec0_table(conn)
        concept_ids = [
            int(r[0])
            for r in conn.execute("SELECT concept_id FROM concept_embeddings ORDER BY concept_id")
        ]
        max_distance = math.sqrt(2.0 * (1.0 - threshold))
        for cid in concept_ids:
            # Fetch this concept's embedding to use as query
            row = conn.execute(
                "SELECT embedding FROM concept_embeddings WHERE concept_id = ?", (cid,)
            ).fetchone()
            if row is None:
                continue
            query_blob = row["embedding"]
            for neighbor_id, distance in conn.execute(
                """
                SELECT concept_id, distance FROM concept_embeddings
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
                """,
                (query_blob, top_k),
            ):
                if neighbor_id == cid:
                    continue
                if distance > max_distance:
                    continue
                key = (min(cid, int(neighbor_id)), max(cid, int(neighbor_id)))
                cos_sim = _l2_distance_to_cosine_similarity(float(distance))
                # Keep highest similarity per pair
                prior = pairs.get(key)
                if prior is None or cos_sim > prior:
                    pairs[key] = cos_sim

    return [
        CandidatePair(concept_a_id=a, concept_b_id=b, cosine_similarity=s)
        for (a, b), s in sorted(pairs.items())
    ]


def _load_concept_for_llm(conn: sqlite3.Connection, *, concept_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, term, definition FROM concepts WHERE id = ?", (concept_id,)
    ).fetchone()
    return dict(row) if row else None


def verify_pair_with_llm(
    concept_a: dict[str, Any],
    concept_b: dict[str, Any],
    *,
    anthropic_client: Any,
    model: str = "claude-opus-4-7",
) -> tuple[str, str, float]:
    """Ask Opus 4.7 whether two concepts refer to the same entity.

    Returns ``(verdict, reason, cost_usd)``. Verdict is one of
    ``"same"``, ``"different"``, ``"unclear"``.

    Schema-enforced via tool_use, mirroring the pattern in
    ``trading_wiki/core/llm.py``.
    """
    tool_schema = {
        "name": "submit_verdict",
        "description": "Submit your verdict on whether two concept entities are the same.",
        "input_schema": {
            "type": "object",
            "properties": {
                "verdict": {
                    "type": "string",
                    "enum": ["same", "different", "unclear"],
                },
                "reason": {"type": "string", "maxLength": 500},
            },
            "required": ["verdict", "reason"],
            "additionalProperties": False,
        },
    }
    prompt = (
        "Two concept entities have been extracted from a trading-education corpus. "
        "Decide whether they refer to the SAME underlying concept (just stated with "
        "different wording / phrasing) or DIFFERENT concepts.\n\n"
        f"Concept A (id={concept_a['id']}):\n"
        f"  term: {concept_a['term']}\n"
        f"  definition: {concept_a['definition']}\n\n"
        f"Concept B (id={concept_b['id']}):\n"
        f"  term: {concept_b['term']}\n"
        f"  definition: {concept_b['definition']}\n\n"
        "Return 'same' only if both rows describe the same concept and could be "
        "merged. Return 'different' if they describe distinct concepts (even if "
        "related). Return 'unclear' if the definitions are too vague to decide."
    )
    response = anthropic_client.messages.create(
        model=model,
        max_tokens=1024,
        tools=[tool_schema],
        tool_choice={"type": "tool", "name": "submit_verdict"},
        messages=[{"role": "user", "content": prompt}],
    )
    tool_block = next(b for b in response.content if getattr(b, "type", None) == "tool_use")
    verdict = str(tool_block.input["verdict"])
    reason = str(tool_block.input["reason"])
    # Cost estimate using Opus 4.7 pricing: $5 / $25 per MTok input/output
    usage = response.usage
    input_tokens = int(getattr(usage, "input_tokens", 0))
    output_tokens = int(getattr(usage, "output_tokens", 0))
    cost = (input_tokens / 1_000_000) * 5.0 + (output_tokens / 1_000_000) * 25.0
    return verdict, reason, cost


def _existing_resolutions(conn: sqlite3.Connection, *, embedding_model_version: str) -> set[int]:
    """Return concept_ids that already have a resolution at this model version."""
    rows = conn.execute(
        "SELECT concept_id FROM concept_resolutions WHERE embedding_model_version = ?",
        (embedding_model_version,),
    ).fetchall()
    return {int(r[0]) for r in rows}


def _persist_resolution(
    conn: sqlite3.Connection,
    *,
    concept_id: int,
    canonical_concept_id: int,
    similarity_score: float | None,
    llm_verdict: str,
    llm_reason: str,
    embedding_model: str,
    embedding_model_version: str,
) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO concept_resolutions
        (concept_id, canonical_concept_id, similarity_score, llm_verdict,
         llm_reason, embedding_model, embedding_model_version, resolved_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            concept_id,
            canonical_concept_id,
            similarity_score,
            llm_verdict,
            llm_reason,
            embedding_model,
            embedding_model_version,
            datetime.now().isoformat(timespec="seconds"),
        ),
    )


def resolve_concepts(
    db_path: Path,
    *,
    openai_client: Any,
    anthropic_client: Any,
    threshold: float = DEFAULT_THRESHOLD,
    embedding_model: str = EMBEDDING_MODEL,
    embedding_model_version: str = EMBEDDING_MODEL_VERSION,
    prompt_version: str = "pass2-concept-v1",
) -> ResolveResult:
    """Drive the full Pass 3 Concept resolution pipeline.

    Embeds missing concepts, finds candidate pairs above threshold, asks
    Opus to verify each unresolved pair, persists verdicts.
    """
    rows_written, embed_tokens = embed_concepts(
        db_path,
        openai_client=openai_client,
        model=embedding_model,
        prompt_version=prompt_version,
    )
    pairs = find_candidate_pairs(db_path, threshold=threshold)

    verifications: list[dict[str, Any]] = []
    total_llm_cost = 0.0
    with _connect_with_vec(db_path) as conn:
        resolved_ids = _existing_resolutions(conn, embedding_model_version=embedding_model_version)
        # Group concepts that are "same" so canonical = min(group)
        same_groups: dict[int, set[int]] = {}

        for pair in pairs:
            a, b = pair.concept_a_id, pair.concept_b_id
            if a in resolved_ids and b in resolved_ids:
                # Already verified at this model version; skip.
                continue
            concept_a = _load_concept_for_llm(conn, concept_id=a)
            concept_b = _load_concept_for_llm(conn, concept_id=b)
            if concept_a is None or concept_b is None:
                continue
            verdict, reason, cost = verify_pair_with_llm(
                concept_a, concept_b, anthropic_client=anthropic_client
            )
            total_llm_cost += cost
            verifications.append(
                {
                    "concept_a_id": a,
                    "concept_b_id": b,
                    "cosine_similarity": pair.cosine_similarity,
                    "verdict": verdict,
                    "reason": reason,
                    "cost_usd": cost,
                }
            )
            if verdict == "same":
                # Union-find: merge groups containing a or b
                group_key_a = next((k for k, g in same_groups.items() if a in g or k == a), a)
                group_key_b = next((k for k, g in same_groups.items() if b in g or k == b), b)
                merged_members = (
                    same_groups.get(group_key_a, {group_key_a})
                    | same_groups.get(group_key_b, {group_key_b})
                    | {a, b}
                )
                new_key = min(merged_members)
                # Clean up old keys
                same_groups.pop(group_key_a, None)
                same_groups.pop(group_key_b, None)
                same_groups[new_key] = merged_members

        # Persist resolutions: for each pair we verified, write a row.
        with conn:
            for v in verifications:
                _persist_resolution(
                    conn,
                    concept_id=v["concept_a_id"],
                    canonical_concept_id=_canonical_for(v["concept_a_id"], same_groups),
                    similarity_score=v["cosine_similarity"],
                    llm_verdict=v["verdict"],
                    llm_reason=v["reason"],
                    embedding_model=embedding_model,
                    embedding_model_version=embedding_model_version,
                )
                _persist_resolution(
                    conn,
                    concept_id=v["concept_b_id"],
                    canonical_concept_id=_canonical_for(v["concept_b_id"], same_groups),
                    similarity_score=v["cosine_similarity"],
                    llm_verdict=v["verdict"],
                    llm_reason=v["reason"],
                    embedding_model=embedding_model,
                    embedding_model_version=embedding_model_version,
                )

    return ResolveResult(
        embeddings_written=rows_written,
        candidate_pairs=pairs,
        verifications=verifications,
        total_embedding_tokens=embed_tokens,
        total_llm_cost_usd=total_llm_cost,
    )


def _canonical_for(concept_id: int, same_groups: dict[int, set[int]]) -> int:
    """Return the canonical (lowest-id) concept_id for ``concept_id``'s group.
    If the concept isn't in any merged group, it is its own canonical."""
    for canonical, members in same_groups.items():
        if concept_id in members:
            return canonical
    return concept_id
