"""Streamlit review page for Pass 2 extracted entities.

Run: ``uv run streamlit run trading_wiki/review/app.py``
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

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


def _sidebar(db_path: Path) -> tuple[int | None, list[EntityType], SampleMode, int, bool]:
    st.sidebar.header("Review filters")
    summaries = list_content_summaries(db_path)
    if not summaries:
        st.sidebar.warning("No content found. Ingest something first.")
        return None, [], "stratified", 5, False

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
    mode = cast(
        SampleMode, st.sidebar.selectbox("Sample mode", options=["stratified", "all", "random"])
    )
    n = int(st.sidebar.number_input("N", min_value=1, max_value=999, value=5))
    show_reviewed = st.sidebar.checkbox("Show already-reviewed", value=False)
    return int(content_id), types, mode, n, show_reviewed


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


def main() -> None:
    st.set_page_config(page_title="Trading Wiki — Review", layout="wide")
    st.title("Trading Wiki — Pass 2 Review")

    db_path = DEFAULT_DB_PATH
    if not db_path.exists():
        st.error(f"DB not found at {db_path}. Set TRADING_WIKI_DB or run ingestion first.")
        return

    content_id, types, mode, n, show_reviewed = _sidebar(db_path)
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

    exclude = set() if show_reviewed else reviewed_ids(existing)
    items = sample_items(
        db_path,
        content_id=content_id,
        entity_types=types,
        mode=mode,
        n=n,
        exclude_ids=exclude,
    )

    st.caption(f"{len(items)} item(s) to review | {len(existing)} already in {findings_file}")

    if not items:
        st.success("Nothing left to review for these filters.")
        return

    item = items[0]
    _render_item(item)
    _render_form(item, content_id, findings_file)


if __name__ == "__main__":
    main()
