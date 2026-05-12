"""Phase 2B — Review queue auto-populator + hard-gate checks.

Triggers (auto-queue items matching these):
- low_confidence_entity: any Pass 2 entity with confidence='low' → severity=medium
- contradicts_relationship: any entity_relationship with predicate='contradicts'
  → severity=high
- codeability_4plus: any Strategy with codeability_score >= 4 → severity=high
  AND `is_hard_gate=1` (cannot enter Phase 4 without review)
- borderline_merge: any concept_resolution with llm_verdict='unclear'
  → severity=medium

Hard gates: items with `is_hard_gate=1 AND status='pending'` block downstream
work that depends on the referenced entity. Phase 4 strategy formalization
calls ``check_hard_gate_for_strategy(strategy_id)`` before promoting a
Strategy to backtest candidate.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import structlog

from trading_wiki.core.secrets import Settings

_log = structlog.get_logger(__name__)


@dataclass
class QueuePopulateResult:
    low_confidence_added: int = 0
    contradicts_added: int = 0
    codeability_added: int = 0
    borderline_merge_added: int = 0
    skipped_duplicates: int = 0
    by_trigger: dict[str, int] = field(default_factory=dict)

    @property
    def total_added(self) -> int:
        return (
            self.low_confidence_added
            + self.contradicts_added
            + self.codeability_added
            + self.borderline_merge_added
        )


_LOW_CONFIDENCE_TABLES: list[tuple[str, str]] = [
    ("trade_example", "trade_examples"),
    ("concept", "concepts"),
    ("strategy", "strategies"),
    ("setup", "setups"),
    ("rule", "rules"),
    ("market_condition", "market_conditions"),
]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _entity_already_queued(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: int,
    trigger: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM review_queue
        WHERE target_kind = 'entity'
          AND entity_type = ?
          AND entity_id = ?
          AND trigger = ?
        """,
        (entity_type, entity_id, trigger),
    ).fetchone()
    return row is not None


def _relationship_already_queued(
    conn: sqlite3.Connection, *, relationship_id: int, trigger: str
) -> bool:
    row = conn.execute(
        """
        SELECT 1 FROM review_queue
        WHERE target_kind = 'relationship'
          AND relationship_id = ?
          AND trigger = ?
        """,
        (relationship_id, trigger),
    ).fetchone()
    return row is not None


def _queue_entity(
    conn: sqlite3.Connection,
    *,
    entity_type: str,
    entity_id: int,
    trigger: str,
    severity: str,
    is_hard_gate: bool,
) -> bool:
    """Insert one row; returns True if inserted, False if it was a duplicate."""
    if _entity_already_queued(conn, entity_type=entity_type, entity_id=entity_id, trigger=trigger):
        return False
    conn.execute(
        """
        INSERT INTO review_queue
        (target_kind, entity_type, entity_id, trigger, severity, is_hard_gate,
         status, queued_at)
        VALUES ('entity', ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (entity_type, entity_id, trigger, severity, int(is_hard_gate), _now()),
    )
    return True


def _queue_relationship(
    conn: sqlite3.Connection,
    *,
    relationship_id: int,
    trigger: str,
    severity: str,
    is_hard_gate: bool,
) -> bool:
    if _relationship_already_queued(conn, relationship_id=relationship_id, trigger=trigger):
        return False
    conn.execute(
        """
        INSERT INTO review_queue
        (target_kind, relationship_id, trigger, severity, is_hard_gate,
         status, queued_at)
        VALUES ('relationship', ?, ?, ?, ?, 'pending', ?)
        """,
        (relationship_id, trigger, severity, int(is_hard_gate), _now()),
    )
    return True


def populate_queue(db_path: Path | None = None) -> QueuePopulateResult:
    """Scan all entities + relationships and add items matching trigger
    criteria to the ``review_queue``. Idempotent — running twice doesn't
    create duplicates."""
    db_path = Path(db_path) if db_path is not None else Settings().db_path
    result = QueuePopulateResult()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row

        # Trigger 1: low-confidence entities (severity=medium)
        for entity_type, table in _LOW_CONFIDENCE_TABLES:
            for row in conn.execute(f"SELECT id FROM {table} WHERE confidence = 'low' ORDER BY id"):
                inserted = _queue_entity(
                    conn,
                    entity_type=entity_type,
                    entity_id=int(row["id"]),
                    trigger="low_confidence_entity",
                    severity="medium",
                    is_hard_gate=False,
                )
                if inserted:
                    result.low_confidence_added += 1
                else:
                    result.skipped_duplicates += 1

        # Trigger 2: contradicts relationships (severity=high)
        for row in conn.execute(
            "SELECT id FROM entity_relationships WHERE predicate = 'contradicts' ORDER BY id"
        ):
            inserted = _queue_relationship(
                conn,
                relationship_id=int(row["id"]),
                trigger="contradicts_relationship",
                severity="high",
                is_hard_gate=False,
            )
            if inserted:
                result.contradicts_added += 1
            else:
                result.skipped_duplicates += 1

        # Trigger 3: Strategy codeability >= 4 (severity=high, HARD GATE)
        for row in conn.execute(
            "SELECT id FROM strategies WHERE codeability_score >= 4 ORDER BY id"
        ):
            inserted = _queue_entity(
                conn,
                entity_type="strategy",
                entity_id=int(row["id"]),
                trigger="codeability_4plus",
                severity="high",
                is_hard_gate=True,
            )
            if inserted:
                result.codeability_added += 1
            else:
                result.skipped_duplicates += 1

        # Trigger 4: Pass 3 unclear verdicts on concept resolutions
        # (severity=medium, soft gate)
        for row in conn.execute(
            "SELECT concept_id FROM concept_resolutions WHERE llm_verdict = 'unclear' "
            "ORDER BY concept_id"
        ):
            inserted = _queue_entity(
                conn,
                entity_type="concept",
                entity_id=int(row["concept_id"]),
                trigger="borderline_merge",
                severity="medium",
                is_hard_gate=False,
            )
            if inserted:
                result.borderline_merge_added += 1
            else:
                result.skipped_duplicates += 1

        conn.commit()

    result.by_trigger = {
        "low_confidence_entity": result.low_confidence_added,
        "contradicts_relationship": result.contradicts_added,
        "codeability_4plus": result.codeability_added,
        "borderline_merge": result.borderline_merge_added,
    }
    _log.info(
        "pass2b.queue.populate.ok",
        total_added=result.total_added,
        skipped_duplicates=result.skipped_duplicates,
        **result.by_trigger,
    )
    return result


def check_hard_gate_for_entity(
    db_path: Path,
    *,
    entity_type: str,
    entity_id: int,
) -> tuple[bool, list[str]]:
    """Return ``(allowed, blocking_triggers)``. If any pending hard-gate row
    exists for this entity, ``allowed=False`` and ``blocking_triggers`` lists
    the trigger names. Otherwise ``allowed=True, []``.
    """
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT trigger FROM review_queue
            WHERE target_kind = 'entity'
              AND entity_type = ?
              AND entity_id = ?
              AND is_hard_gate = 1
              AND status = 'pending'
            """,
            (entity_type, entity_id),
        ).fetchall()
    triggers = [str(r[0]) for r in rows]
    return (len(triggers) == 0, triggers)


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m trading_wiki.pass2b.queue",
        description="Populate the Phase 2B review queue from current entity state.",
    )
    parser.add_argument("--db-path", type=Path, default=None)
    args = parser.parse_args(argv)

    db_path = args.db_path if args.db_path is not None else Settings().db_path
    result = populate_queue(db_path)
    print(
        f"Queue populated: {result.total_added} new items "
        f"({result.skipped_duplicates} skipped duplicates)."
    )
    for trigger, count in result.by_trigger.items():
        print(f"  {trigger}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
