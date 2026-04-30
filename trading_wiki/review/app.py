"""Streamlit review page for Pass 2 extracted entities.

Run: ``uv run streamlit run trading_wiki/review/app.py``
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import pandas as pd
import streamlit as st

from trading_wiki.core.db import list_content_summaries
from trading_wiki.review.findings import (
    Finding,
    Status,
    append_finding,
    findings_path_for,
    read_findings,
    reviewed_ids,
)
from trading_wiki.review.sampling import EntityType, ReviewItem, SampleMode, sample_items

DEFAULT_DB_PATH = Path(os.environ.get("TRADING_WIKI_DB", "data/research.db"))

ViewMode = str  # "Browse" | "Sample"


def _entity_label(item: ReviewItem) -> str:
    """One-line summary of the entity for the overview table."""
    d = item.entity_data
    if item.entity_type == "concept":
        return str(d.get("term") or "")
    ticker = d.get("ticker") or "—"
    direction = d.get("direction") or ""
    return f"{ticker} {direction}".strip()


def _sidebar(
    db_path: Path,
) -> tuple[ViewMode, int | None, list[EntityType], SampleMode, int, bool]:
    st.sidebar.header("Review")
    view = st.sidebar.radio("View", options=["Browse", "Sample"], horizontal=True)

    summaries = list_content_summaries(db_path)
    if not summaries:
        st.sidebar.warning("No content found. Ingest something first.")
        return view, None, [], "stratified", 5, False

    label_for = {s["id"]: f"{s['id']}: {s['title']} ({s['source_type']})" for s in summaries}
    content_id = st.sidebar.selectbox(
        "Content",
        options=[s["id"] for s in summaries],
        format_func=lambda i: label_for[i],
    )

    types: list[EntityType] = []
    if st.sidebar.checkbox("trade_example", value=True):
        types.append("trade_example")
    if st.sidebar.checkbox("concept", value=True):
        types.append("concept")

    if view == "Sample":
        mode = cast(
            SampleMode,
            st.sidebar.selectbox("Sample mode", options=["stratified", "all", "random"]),
        )
        n = int(st.sidebar.number_input("N", min_value=1, max_value=999, value=5))
    else:
        mode = "all"
        n = 0

    show_reviewed = st.sidebar.checkbox("Show already-reviewed", value=False)
    return view, int(content_id), types, mode, n, show_reviewed


def _render_item(item: ReviewItem) -> None:
    left, right = st.columns(2)
    with left:
        st.subheader(f"{item.entity_type} #{item.entity_id}")
        st.caption(f"prompt_version={item.prompt_version}")
        st.json(item.entity_data)
    with right:
        st.subheader(f"chunk #{item.chunk_id} ({item.chunk_label})")
        st.text(item.chunk_text)


def _render_form(item: ReviewItem, content_id: int, findings_file: Path) -> None:
    with st.form(key=f"form-{item.entity_type}-{item.entity_id}"):
        status = cast(
            Status,
            st.radio(
                "Status",
                options=["accept", "needs_fix", "skip"],
                horizontal=True,
            ),
        )
        notes = st.text_area("Notes", value="")
        submitted = st.form_submit_button("Save & next")
    if submitted:
        finding = Finding(
            entity_type=item.entity_type,
            entity_id=item.entity_id,
            status=status,
            chunk_id=item.chunk_id,
            chunk_label=item.chunk_label,
            prompt_version=item.prompt_version,
            reviewed_at=datetime.now(tz=UTC),
            notes=notes,
        )
        append_finding(findings_file, finding, content_id=content_id)
        st.success(f"Saved {item.entity_type}:{item.entity_id} as {status}")
        st.rerun()


def _overview_df(items: list[ReviewItem], reviewed: set[tuple[EntityType, int]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in items:
        rows.append(
            {
                "reviewed": "✓" if (item.entity_type, item.entity_id) in reviewed else "",
                "type": item.entity_type,
                "id": item.entity_id,
                "label": _entity_label(item),
                "chunk_label": item.chunk_label,
                "chunk_id": item.chunk_id,
                "prompt_version": item.prompt_version,
            }
        )
    return pd.DataFrame(rows)


def _render_browse(
    items: list[ReviewItem],
    reviewed: set[tuple[EntityType, int]],
    content_id: int,
    findings_file: Path,
) -> None:
    if not items:
        st.success("Nothing to browse for these filters.")
        return

    df = _overview_df(items, reviewed)
    event: Any = st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
        key=f"overview-{content_id}",
    )
    selection = getattr(event, "selection", None) if event is not None else None
    rows_attr = getattr(selection, "rows", None) if selection is not None else None
    selected_rows = list(rows_attr) if rows_attr else []
    if not selected_rows:
        st.info("Pick a row above to review it.")
        return

    item = items[selected_rows[0]]
    st.divider()
    _render_item(item)
    _render_form(item, content_id, findings_file)


def main() -> None:
    st.set_page_config(page_title="Trading Wiki — Review", layout="wide")
    st.title("Trading Wiki — Pass 2 Review")

    db_path = DEFAULT_DB_PATH
    if not db_path.exists():
        st.error(f"DB not found at {db_path}. Set TRADING_WIKI_DB or run ingestion first.")
        return

    view, content_id, types, mode, n, show_reviewed = _sidebar(db_path)
    if content_id is None:
        return
    if not types:
        st.info("Pick at least one entity type in the sidebar.")
        return

    findings_file = findings_path_for(content_id)
    try:
        existing = read_findings(findings_file)
    except ValueError as exc:
        st.error(f"Findings file is malformed: {exc}")
        return

    reviewed = reviewed_ids(existing)
    exclude = set() if show_reviewed else reviewed
    items = sample_items(
        db_path,
        content_id=content_id,
        entity_types=types,
        mode=mode,
        n=n,
        exclude_ids=exclude,
    )

    st.caption(f"{len(items)} item(s) shown | {len(existing)} already in {findings_file}")

    if view == "Browse":
        _render_browse(items, reviewed, content_id, findings_file)
        return

    if not items:
        st.success("Nothing left to review for these filters.")
        return

    item = items[0]
    _render_item(item)
    _render_form(item, content_id, findings_file)


if __name__ == "__main__":
    main()
