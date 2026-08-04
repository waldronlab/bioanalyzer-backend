#!/usr/bin/env python3
"""
BioAnalyzer Curator Table (with column-level validation + curator ground truth)
=============================================================================
Streamlit dashboard for real-world validation of BioAnalyzer predictions:
sortable/searchable/filterable table, curator feedback by PMID, per-field
value + ontology-mapping confirmation, exportable feedback.

Run: streamlit run curator_table/app.py
Input: CSV or Parquet with PMID (recommended: Title, Journal, Year).
Feedback: results/curator_feedback.csv and .parquet (upserted by PMID + curator_id).
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

# -----------------------------
# Config (env overrides)
# -----------------------------
CONFIG = {
    "feedback_dir": Path(os.getenv("FEEDBACK_DIR", "results")),
    "curator_id_default": os.getenv("USER") or os.getenv("USERNAME", ""),
    "bioanalyzer_version_default": os.getenv("BIOANALYZER_VERSION", ""),
}

CONFIG["feedback_dir"].mkdir(exist_ok=True)
FEEDBACK_CSV = CONFIG["feedback_dir"] / "curator_feedback.csv"
FEEDBACK_PARQUET = CONFIG["feedback_dir"] / "curator_feedback.parquet"

logger = logging.getLogger(__name__)

# -----------------------------
# Schema (single source of truth) - simplified curator-desk schema, see
# docs/CURATOR_DESK_CSV_FORMAT.md: plain value per field, ontology ID for
# the 3 fields mapped to an external ontology, no Status/Mapping-Confidence/
# Priority columns.
# -----------------------------
VALUE_COLUMNS = [
    "Host Species",
    "Body Site",
    "Condition",
    "Sample Size",
    "Sequencing Type",
]
ONTOLOGY_ID_COLUMNS = [
    "Host Species Ontology ID",
    "Body Site Ontology ID",
    "Condition Ontology ID",
]
# Picker metadata (not shown as a table column) - "label|ontology_id;
# label|ontology_id", populated only when a field's mapping tier isn't auto.
ONTOLOGY_CANDIDATES_COLUMNS = [
    "Host Species Ontology Candidates",
    "Body Site Ontology Candidates",
    "Condition Ontology Candidates",
]
BOOLEAN_COLUMNS = ["Differential Abundance", "In bsgdb"]
OPTIONS = {
    "col_feedback": ["Not reviewed", "Correct", "Incorrect", "Unclear"],
}

_safe = lambda col: col.replace(" ", "_")
FEEDBACK_BASE_COLS = [
    "PMID",
    "curator_id",
    "overall_verdict",
    "comment",
    "timestamp",
    "bioanalyzer_version",
]
PRED_PREFIX, TRUE_PREFIX, COL_FB_PREFIX = "pred__", "true__", "col_feedback__"


def _ontology_id_col_for(value_col: str) -> Optional[str]:
    candidate = f"{value_col} Ontology ID"
    return candidate if candidate in ONTOLOGY_ID_COLUMNS else None


def _ontology_candidates_col_for(value_col: str) -> str:
    return f"{value_col} Ontology Candidates"


def _parse_candidates(raw: str) -> list[tuple[str, str]]:
    """Parse the compact 'label|ontology_id; label|ontology_id' string (see
    scripts/cli_rendering.py::_field_ontology_candidates)."""
    if not raw or not str(raw).strip():
        return []
    out = []
    for part in str(raw).split(";"):
        part = part.strip()
        if not part or "|" not in part:
            continue
        label, _, oid = part.partition("|")
        if oid:
            out.append((label.strip(), oid.strip()))
    return out


def _value_col_triplet_names(col: str) -> tuple[str, str, str]:
    """(pred, true, col_feedback) column names for one value column."""
    s = _safe(col)
    return f"{PRED_PREFIX}{s}", f"{TRUE_PREFIX}{s}", f"{COL_FB_PREFIX}{s}"


def _onto_col_pair_names(col: str) -> tuple[str, str]:
    """(pred, true) column names for one ontology-ID column."""
    s = _safe(col)
    return f"{PRED_PREFIX}{s}", f"{TRUE_PREFIX}{s}"


def _feedback_schema() -> list[str]:
    """Full feedback column schema: every value field gets a pred/true/
    col_feedback triplet; the 3 ontology-mapped fields additionally get a
    pred/true Ontology ID pair (no col_feedback - only value fields get the
    'was BioAnalyzer correct?' dropdown)."""
    triplets = [_value_col_triplet_names(c) for c in VALUE_COLUMNS]
    pairs = [_onto_col_pair_names(c) for c in ONTOLOGY_ID_COLUMNS]
    value_triplets = (
        [t[0] for t in triplets] + [t[1] for t in triplets] + [t[2] for t in triplets]
    )
    onto_pairs = [p[0] for p in pairs] + [p[1] for p in pairs]
    return FEEDBACK_BASE_COLS + value_triplets + onto_pairs


# -----------------------------
# Helpers
# -----------------------------
def _make_pmid_link(pmid) -> str:
    try:
        return f"https://pubmed.ncbi.nlm.nih.gov/{int(float(pmid))}/"
    except (TypeError, ValueError):
        return ""


def _safe_int(x) -> Optional[int]:
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


# -----------------------------
# Data loading (unified)
# -----------------------------
@st.cache_data(show_spinner=False)
def _load_data(
    source, is_path: bool, mtime: float = 0.0, size: int = 0
) -> pd.DataFrame:
    """Load from file path (str/Path) or uploaded file; returns empty DataFrame on failure.

    mtime/size are part of the cache key (not just `source`) so that editing
    the underlying file on disk at the same path busts the Streamlit cache
    instead of silently serving a stale DataFrame."""
    if source is None or (is_path and not source):
        return pd.DataFrame()
    if is_path:
        path = Path(source)
        if not path.exists():
            logger.warning("Path does not exist: %s", path)
            return pd.DataFrame()
        buf, ext = path, path.suffix.lower()
    else:
        name = source.name.lower()
        buf = io.BytesIO(source.getvalue())
        ext = (
            ".csv"
            if name.endswith(".csv")
            else (".parquet" if name.endswith((".parquet", ".pq")) else "")
        )
    if ext == ".csv":
        return pd.read_csv(buf)
    if ext in (".parquet", ".pq"):
        return pd.read_parquet(buf)
    raise ValueError("Unsupported format. Use .csv or .parquet.")


def normalize_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize PMID, booleans, derive year/link. Returns empty DataFrame if invalid."""
    if df.empty or "PMID" not in df.columns:
        if not df.empty:
            st.error("Data must contain a 'PMID' column.")
        return pd.DataFrame()
    try:
        df = (
            df.assign(PMID=df["PMID"].apply(_safe_int))
            .dropna(subset=["PMID"])
            .astype({"PMID": int})
        )
    except Exception as e:
        logger.exception("PMID normalization failed: %s", e)
        return pd.DataFrame()
    if "Year" not in df.columns and "Publication Date" in df.columns:
        try:
            df = df.assign(
                Year=pd.to_datetime(df["Publication Date"], errors="coerce").dt.year
            )
        except Exception as e:
            logger.debug("Year derivation from Publication Date failed: %s", e)
    for col in BOOLEAN_COLUMNS:
        if col in df.columns:
            df[col] = df[col].map(
                lambda v: (
                    str(v).strip().upper() in {"TRUE", "T", "1", "YES"}
                    if pd.notna(v)
                    else False
                )
            )
        else:
            df[col] = False
    for col in ONTOLOGY_ID_COLUMNS + ONTOLOGY_CANDIDATES_COLUMNS:
        if col not in df.columns:
            df[col] = ""
        else:
            df[col] = df[col].fillna("")
    df = df.assign(**{"PubMed Link": df["PMID"].apply(_make_pmid_link)})
    return df


# -----------------------------
# Feedback persistence
# -----------------------------
def load_feedback() -> pd.DataFrame:
    """Load feedback from parquet then csv; empty DataFrame with schema if missing."""
    for path, reader in [
        (FEEDBACK_PARQUET, pd.read_parquet),
        (FEEDBACK_CSV, pd.read_csv),
    ]:
        if path.exists():
            try:
                return reader(path)
            except Exception as e:
                logger.warning("Failed to load %s: %s", path, e)
    return pd.DataFrame(columns=_feedback_schema())


def save_feedback(df: pd.DataFrame) -> None:
    """Persist feedback to CSV and Parquet; ensure schema."""
    CONFIG["feedback_dir"].mkdir(exist_ok=True)
    for col in _feedback_schema():
        if col not in df.columns:
            df[col] = ""
    df.to_csv(FEEDBACK_CSV, index=False)
    try:
        df.to_parquet(FEEDBACK_PARQUET, index=False)
    except Exception as e:
        logger.warning("Parquet save skipped: %s", e)


def upsert_feedback(existing: pd.DataFrame, row: dict) -> pd.DataFrame:
    """Upsert by PMID + curator_id."""
    for col in _feedback_schema():
        if col not in existing.columns:
            existing[col] = ""
    if not existing.empty:
        mask = (existing["PMID"].astype(str) == str(row["PMID"])) & (
            existing["curator_id"].astype(str) == str(row["curator_id"])
        )
        if mask.any():
            for k, v in row.items():
                existing.loc[mask, k] = v
            return existing
    return pd.concat([existing, pd.DataFrame([row])], ignore_index=True)


# -----------------------------
# UI
# -----------------------------
def render_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")
    search = (
        st.sidebar.text_input(
            "Search (PMID, title, journal, condition)",
            placeholder="e.g. obesity, 2019, Lactobacillus",
        )
        .strip()
        .lower()
    )
    year_range = None
    if "Year" in df.columns:
        years = df["Year"].dropna()
        if not years.empty:
            min_y, max_y = int(years.min()), int(years.max())
            year_range = st.sidebar.slider("Year range", min_y, max_y, (min_y, max_y))
    da_only = st.sidebar.checkbox(
        "Only differential abundance papers",
        value=True,
    )
    hide_bugsigdb = st.sidebar.checkbox("Hide papers already in BugSigDB", value=False)
    needs_mapping_only = st.sidebar.checkbox(
        "Only papers needing an ontology mapping",
        value=False,
        help="Show rows where at least one of Host Species/Body Site/Condition has no Ontology ID yet.",
    )
    out = df.copy()
    if search:
        mask = out["PMID"].astype(str).str.contains(search, na=False)
        for col in ["Title", "Journal", "Condition"]:
            if col in out.columns:
                mask = mask | out[col].astype(str).str.lower().str.contains(
                    search, na=False
                )
        out = out.loc[mask]
    if year_range and "Year" in out.columns:
        out = out[(out["Year"] >= year_range[0]) & (out["Year"] <= year_range[1])]
    if da_only and "Differential Abundance" in out.columns:
        out = out[out["Differential Abundance"] == True]  # noqa: E712
    if hide_bugsigdb and "In bsgdb" in out.columns:
        out = out[out["In bsgdb"] != True]  # noqa: E712
    if needs_mapping_only:
        present_onto_cols = [c for c in ONTOLOGY_ID_COLUMNS if c in out.columns]
        if present_onto_cols:
            missing_any = pd.Series(False, index=out.index)
            for col in present_onto_cols:
                missing_any = missing_any | (out[col].astype(str).str.strip() == "")
            out = out[missing_any]
    return out


def render_table(df: pd.DataFrame) -> Optional[int]:
    if df.empty:
        st.warning("No rows match your filters.")
        return None
    st.subheader("Candidate curatable articles")
    st.caption(
        "Tip: an empty Ontology ID cell means that field needs a curator-confirmed mapping."
    )
    sort_options = ["PMID"]
    if "Year" in df.columns:
        sort_options.insert(0, "Year")
    if "Title" in df.columns:
        sort_options.append("Title")
    sort_col = st.selectbox("Sort by", options=sort_options, index=0)
    ascending = st.checkbox("Ascending", value=False)
    if sort_col in df.columns:
        df = df.sort_values(by=sort_col, ascending=ascending, na_position="last")
    st.divider()
    max_rows = st.slider("Rows to display", 50, 2000, 300, 50)
    df_show = df.head(max_rows).copy()
    want = (
        ["PMID", "PubMed Link", "Title", "Journal", "Year"]
        + list(VALUE_COLUMNS)
        + list(ONTOLOGY_ID_COLUMNS)
        + ["Differential Abundance", "In bsgdb"]
    )
    display_cols = [c for c in want if c in df_show.columns]
    df_show = df_show[display_cols]
    st.dataframe(
        df_show,
        use_container_width=True,
        height=650,
        column_config={
            "PubMed Link": st.column_config.LinkColumn("PubMed", display_text="Open")
        },
    )
    st.metric("Rows after filtering", len(df))
    st.metric("Rows displayed", len(df_show))
    st.divider()
    st.subheader("Quick select for feedback")
    selected = st.selectbox(
        "Select a PMID from currently displayed rows",
        options=[""] + df_show["PMID"].astype(str).tolist(),
        index=0,
    )
    return int(selected) if selected else None


def render_column_level_validation(
    selected_row: pd.Series, selected_pmid: Optional[int]
) -> dict[str, str]:
    """Per-field value + ontology-mapping confirmation. Returns
    true__*/col_feedback__* for value fields and true__* for ontology ID fields.

    Widget keys are namespaced by selected_pmid so that switching PMIDs gets
    fresh widget state instead of Streamlit reusing the previous paper's
    session-state values (Streamlit ignores a widget's value= default once
    its key already has session state)."""
    st.markdown("### Field-by-field validation (ground truth)")
    st.caption(
        "For each field, correct BioAnalyzer's predicted value if needed. For "
        "Host Species/Body Site/Condition, confirm or pick the ontology mapping."
    )
    out: dict[str, str] = {}
    left, right = st.columns(2)
    for pane, cols in zip([left, right], [VALUE_COLUMNS[:3], VALUE_COLUMNS[3:]]):
        with pane:
            for col in cols:
                if col not in selected_row.index:
                    continue
                safe = _safe(col)
                pred = str(selected_row.get(col, "")).strip()
                st.markdown(f"**{col}**")
                st.write(f"BioAnalyzer predicted: `{pred}`")
                true_key = f"{TRUE_PREFIX}{safe}"
                out[true_key] = st.text_input(
                    f"Curator value for {col}",
                    value="",
                    key=f"ui__{true_key}__{selected_pmid}",
                )
                fb_key = f"{COL_FB_PREFIX}{safe}"
                out[fb_key] = st.selectbox(
                    f"Was BioAnalyzer correct for {col}?",
                    options=OPTIONS["col_feedback"],
                    index=0,
                    key=f"ui__{fb_key}__{selected_pmid}",
                )

                onto_col = _ontology_id_col_for(col)
                if onto_col and onto_col in selected_row.index:
                    onto_safe = _safe(onto_col)
                    predicted_id = str(selected_row.get(onto_col, "")).strip()
                    st.write(
                        f"Ontology ID: `{predicted_id}`"
                        if predicted_id
                        else "Ontology ID: _(none - needs mapping)_"
                    )
                    candidates = _parse_candidates(
                        str(selected_row.get(_ontology_candidates_col_for(col), ""))
                    )
                    option_labels = ["Not reviewed"]
                    option_values = [""]
                    if predicted_id:
                        option_labels.append(f"Confirm predicted: {predicted_id}")
                        option_values.append(predicted_id)
                    for label, oid in candidates:
                        if oid == predicted_id:
                            continue
                        option_labels.append(f"{label} ({oid})")
                        option_values.append(oid)
                    option_labels.append("Other (enter manually)")
                    option_values.append("__other__")
                    onto_true_key = f"{TRUE_PREFIX}{onto_safe}"
                    choice_idx = st.selectbox(
                        f"Ontology mapping for {col}",
                        options=range(len(option_labels)),
                        format_func=lambda i: option_labels[i],
                        index=0,
                        key=f"ui__{onto_true_key}__{selected_pmid}",
                    )
                    chosen_value = option_values[choice_idx]
                    if chosen_value == "__other__":
                        chosen_value = st.text_input(
                            f"Enter ontology ID manually for {col}",
                            value="",
                            key=f"ui__{onto_true_key}__manual__{selected_pmid}",
                        ).strip()
                    out[onto_true_key] = chosen_value
                st.divider()
    return out


def render_feedback_section(
    selected_pmid: Optional[int], dataset_df: pd.DataFrame, full_df: pd.DataFrame
) -> None:
    st.subheader("Curator feedback")
    st.caption(
        "Feedback is stored locally in results/. Entries are upserted by PMID + curator_id."
    )
    feedback_df = load_feedback()
    selected_row = None
    if selected_pmid is not None:
        try:
            selected_row = dataset_df.loc[dataset_df["PMID"] == selected_pmid].iloc[0]
        except Exception as e:
            logger.debug("Selected-row lookup failed for PMID %s: %s", selected_pmid, e)
            selected_row = None
    title_prefill = (
        str(selected_row.get("Title", ""))
        if selected_row is not None and "Title" in selected_row.index
        else ""
    )

    with st.form("feedback_form", clear_on_submit=False):
        curator_id = st.text_input(
            "Curator ID / initials",
            value=CONFIG["curator_id_default"],
            placeholder="e.g. Ronald Ouma",
        ).strip()
        fb_pmid = st.text_input(
            "PMID",
            value=str(selected_pmid) if selected_pmid else "",
            placeholder="e.g. 31215600",
        ).strip()
        if title_prefill:
            st.write(f"**Title:** {title_prefill}")
        overall_verdict = st.selectbox(
            "Overall paper verdict",
            options=["Curatable", "Not curatable", "Uncertain", "Not reviewed"],
            index=0,
        )
        comment = st.text_area(
            "Comment (optional)",
            placeholder="Evidence, edge case, missing field, false positive reason, etc.",
            height=90,
        )
        bioanalyzer_version = st.text_input(
            "BioAnalyzer version (recommended)",
            value=CONFIG["bioanalyzer_version_default"],
            placeholder="e.g. 1.0.0, commit SHA, docker tag",
        ).strip()
        field_validation = (
            render_column_level_validation(selected_row, selected_pmid)
            if selected_row is not None
            else {}
        )
        if selected_row is None:
            st.info("Select a PMID above to enable field-level validation.")
        submitted = st.form_submit_button("Save feedback")

        if submitted:
            if not curator_id:
                st.error("Please provide curator_id (initials or username).")
                return
            if not fb_pmid:
                st.error("Please provide a PMID.")
                return
            pid = _safe_int(fb_pmid)
            if pid is None:
                st.error("PMID must be numeric.")
                return
            if (
                selected_pmid is not None
                and pid != selected_pmid
                and pid not in full_df["PMID"].values
            ):
                st.warning("PMID not in current dataset; feedback will still be saved.")
            row = {
                "PMID": int(pid),
                "curator_id": curator_id,
                "overall_verdict": overall_verdict,
                "comment": comment.strip(),
                "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
                "bioanalyzer_version": bioanalyzer_version,
            }
            for col in VALUE_COLUMNS:
                pred_key, true_key, fb_key = _value_col_triplet_names(col)
                row[pred_key] = (
                    str(selected_row.get(col, "")).strip()
                    if selected_row is not None and col in selected_row.index
                    else ""
                )
                row[true_key] = field_validation.get(true_key, "")
                row[fb_key] = field_validation.get(fb_key, "Not reviewed")
            for onto_col in ONTOLOGY_ID_COLUMNS:
                pred_key, true_key = _onto_col_pair_names(onto_col)
                row[pred_key] = (
                    str(selected_row.get(onto_col, "")).strip()
                    if selected_row is not None and onto_col in selected_row.index
                    else ""
                )
                row[true_key] = field_validation.get(true_key, "")
            feedback_df = upsert_feedback(feedback_df, row)
            save_feedback(feedback_df)
            logger.info("Saved feedback for PMID %s (curator=%s)", pid, curator_id)
            st.success(f"Saved feedback for PMID {pid} (curator={curator_id}).")

    st.divider()
    st.subheader("Existing feedback")
    if feedback_df.empty:
        st.info("No feedback recorded yet.")
        return
    compact_cols = (
        [c for c in FEEDBACK_BASE_COLS if c in feedback_df.columns]
        + [
            k
            for c in VALUE_COLUMNS
            for k in _value_col_triplet_names(c)
            if k in feedback_df.columns
        ]
        + [
            k
            for c in ONTOLOGY_ID_COLUMNS
            for k in _onto_col_pair_names(c)
            if k in feedback_df.columns
        ]
    )
    st.dataframe(
        feedback_df.sort_values("timestamp", ascending=False)[compact_cols],
        use_container_width=True,
        height=380,
    )
    st.download_button(
        "Download feedback CSV",
        data=feedback_df.to_csv(index=False),
        file_name=FEEDBACK_CSV.name,
        mime="text/csv",
    )


def main() -> None:
    st.set_page_config(page_title="BioAnalyzer Curator Table", layout="wide")
    st.title("BioAnalyzer Curator Table")
    st.markdown(
        """
This dashboard provides a **sortable, searchable, filterable** table of BioAnalyzer predictions.

- Curators review extracted values and ontology mappings, and capture feedback by PMID.
- Stored: predicted values/ontology IDs, curator ground truth, correctness flags.
        """
    )
    st.sidebar.header("Data source")
    data_source = st.sidebar.radio(
        "Choose input mode",
        options=["Upload CSV/Parquet", "Use file path"],
        index=0,
    )
    raw_df = pd.DataFrame()
    if data_source == "Upload CSV/Parquet":
        uploaded = st.sidebar.file_uploader(
            "Upload dataset", type=["csv", "parquet", "pq"]
        )
        if uploaded:
            try:
                raw_df = _load_data(uploaded, is_path=False)
            except Exception as e:
                st.error(f"Could not load file: {e}")
                logger.exception("Upload load failed")
                return
    else:
        path = st.sidebar.text_input(
            "Path to CSV/Parquet", placeholder="e.g. analysis_results.csv"
        ).strip()
        if path:
            try:
                _p = Path(path)
                _stat = _p.stat() if _p.exists() else None
                raw_df = _load_data(
                    path,
                    is_path=True,
                    mtime=_stat.st_mtime if _stat else 0.0,
                    size=_stat.st_size if _stat else 0,
                )
            except Exception as e:
                st.error(str(e))
                logger.exception("Path load failed")
                return
    if raw_df.empty:
        st.info("Upload a dataset or provide a file path to begin.")
        st.stop()
    df = normalize_dataset(raw_df)
    if df.empty:
        st.error("Dataset loaded, but no valid rows found after normalization.")
        st.stop()
    missing = [c for c in VALUE_COLUMNS if c not in df.columns]
    if missing:
        st.warning(
            "Some expected value columns are missing. The table and filtering will be partial.\n\n"
            f"Missing: {missing}"
        )
    filtered_df = render_filters(df)
    selected_pmid = render_table(filtered_df)
    st.divider()
    render_feedback_section(selected_pmid, filtered_df, df)
    st.sidebar.divider()
    st.sidebar.header("Notes")
    st.sidebar.markdown(
        f"Feedback: `{FEEDBACK_CSV}` and `{FEEDBACK_PARQUET}`. "
        "Tip: set `BIOANALYZER_VERSION` or `FEEDBACK_DIR` in environment."
    )


if __name__ == "__main__":
    main()
