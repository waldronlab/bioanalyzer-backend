#!/usr/bin/env python3
"""
BioAnalyzer Curator Table (with column-level validation + curator ground truth)
=============================================================================

Streamlit dashboard for real-world validation of BioAnalyzer predictions:
sortable/searchable/filterable table, curator feedback by PMID, column-level
correctness + ground truth, exportable feedback for confusion matrices and MCC.

Run: streamlit run curator_table/app.py
Input: CSV or Parquet with PMID (recommended: Title, Journal, Year, Summary).
Status values: ABSENT | PARTIALLY_PRESENT | PRESENT.
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
    "curator_id_default": os.getenv("USER", ""),
    "bioanalyzer_version_default": os.getenv("BIOANALYZER_VERSION", ""),
}

CONFIG["feedback_dir"].mkdir(exist_ok=True)
FEEDBACK_CSV = CONFIG["feedback_dir"] / "curator_feedback.csv"
FEEDBACK_PARQUET = CONFIG["feedback_dir"] / "curator_feedback.parquet"

logger = logging.getLogger(__name__)

# -----------------------------
# Schema (single source of truth)
# -----------------------------
STATUS_COLUMNS = [
    "Host Species Status",
    "Body Site Status",
    "Condition Status",
    "Sequencing Type Status",
    "Sample Size Status",
]
MAPPING_CONFIDENCE_COLUMNS = [
    "Host Species Mapping Confidence",
    "Body Site Mapping Confidence",
    "Condition Mapping Confidence",
]
OPTIONS = {
    "valid_states": ["ABSENT", "PARTIALLY_PRESENT", "PRESENT"],
    "col_feedback": ["Not reviewed", "Correct", "Incorrect", "Unclear"],
    "true_label": ["Not reviewed", "ABSENT", "PARTIALLY_PRESENT", "PRESENT"],
}

_safe = lambda col: col.replace(" ", "_")
FEEDBACK_BASE_COLS = [
    "PMID", "curator_id", "overall_verdict", "comment", "timestamp", "bioanalyzer_version",
]
PRED_PREFIX, TRUE_PREFIX, COL_FB_PREFIX = "pred__", "true__", "col_feedback__"


def _feedback_schema() -> list[str]:
    """Full feedback column schema (dynamic from STATUS_COLUMNS)."""
    derived = [
        f"{PRED_PREFIX}{_safe(c)}" for c in STATUS_COLUMNS
    ] + [
        f"{TRUE_PREFIX}{_safe(c)}" for c in STATUS_COLUMNS
    ] + [
        f"{COL_FB_PREFIX}{_safe(c)}" for c in STATUS_COLUMNS
    ]
    return FEEDBACK_BASE_COLS + derived


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


def _normalize_status(x: str) -> str:
    if pd.isna(x):
        return ""
    x = str(x).strip().upper()
    if x in OPTIONS["valid_states"]:
        return x
    if x in {"PARTIAL", "PARTIALLY", "PARTLY"}:
        return "PARTIALLY_PRESENT"
    if x in {"YES", "TRUE"}:
        return "PRESENT"
    if x in {"NO", "FALSE"}:
        return "ABSENT"
    return x


def _priority_score(row: pd.Series) -> float:
    """Confidence-weighted priority score (spec §6.4 + long-term vision)."""
    weights = {"PRESENT": 1.0, "PARTIALLY_PRESENT": 0.5}
    score = 0.0
    for i, col in enumerate(STATUS_COLUMNS):
        base = weights.get(str(row.get(col, "")).strip().upper(), 0.0)
        if base == 0:
            continue
        conf = 1.0
        if i < len(MAPPING_CONFIDENCE_COLUMNS):
            map_col = MAPPING_CONFIDENCE_COLUMNS[i]
            if map_col in row.index and pd.notna(row.get(map_col)):
                try:
                    conf = float(row.get(map_col))
                except (TypeError, ValueError):
                    conf = 1.0
        score += base * conf
    if row.get("has_differential_abundance") in (True, "TRUE", "True", 1, "1"):
        try:
            da_conf = float(row.get("differential_abundance_confidence", 0) or 0)
            score += 0.25 * da_conf
        except (TypeError, ValueError):
            pass
    return round(score, 3)


# -----------------------------
# Data loading (unified)
# -----------------------------
@st.cache_data(show_spinner=False)
def _load_data(source, is_path: bool) -> pd.DataFrame:
    """Load from file path (str/Path) or uploaded file; returns empty DataFrame on failure."""
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
        ext = ".csv" if name.endswith(".csv") else (".parquet" if name.endswith((".parquet", ".pq")) else "")
    if ext == ".csv":
        return pd.read_csv(buf)
    if ext in (".parquet", ".pq"):
        return pd.read_parquet(buf)
    raise ValueError(f"Unsupported format. Use .csv or .parquet.")


def normalize_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize PMID, statuses, derive year/link/priority. Returns empty DataFrame if invalid."""
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
            df = df.assign(Year=pd.to_datetime(df["Publication Date"], errors="coerce").dt.year)
        except Exception:
            pass
    for col in STATUS_COLUMNS:
        if col in df.columns:
            df = df.assign(**{col: df[col].apply(_normalize_status)})
    for col in ("has_differential_abundance", "in_bugsigdb"):
        if col in df.columns:
            df[col] = df[col].map(
                lambda v: str(v).strip().upper() in {"TRUE", "T", "1", "YES"}
                if pd.notna(v)
                else False
            )
        else:
            df[col] = False
    if "differential_abundance_confidence" not in df.columns:
        df["differential_abundance_confidence"] = 0.0
    df = df.assign(
        **{"Priority Score": df.apply(_priority_score, axis=1)},
        **{"PubMed Link": df["PMID"].apply(_make_pmid_link)},
    )
    return df


# -----------------------------
# Feedback persistence
# -----------------------------
def load_feedback() -> pd.DataFrame:
    """Load feedback from parquet then csv; empty DataFrame with schema if missing."""
    for path, reader in [(FEEDBACK_PARQUET, pd.read_parquet), (FEEDBACK_CSV, pd.read_csv)]:
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
        mask = (
            (existing["PMID"].astype(str) == str(row["PMID"]))
            & (existing["curator_id"].astype(str) == str(row["curator_id"]))
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
    search = st.sidebar.text_input(
        "Search (PMID, title, journal, summary)",
        placeholder="e.g. obesity, 2019, Lactobacillus",
    ).strip().lower()
    status_filters = {
        col: st.sidebar.multiselect(col, options=OPTIONS["valid_states"], default=[])
        for col in STATUS_COLUMNS
        if col in df.columns
    }
    year_range = None
    if "Year" in df.columns:
        years = df["Year"].dropna()
        if not years.empty:
            min_y, max_y = int(years.min()), int(years.max())
            year_range = st.sidebar.slider("Year range", min_y, max_y, (min_y, max_y))
    da_only = st.sidebar.checkbox(
        "Only differential abundance papers",
        value=True,
        help="Show papers where has_differential_abundance is TRUE (spec §8.2 default)",
    )
    min_da_conf = st.sidebar.slider(
        "Min differential abundance confidence",
        0.0,
        1.0,
        0.0,
        0.05,
    )
    hide_bugsigdb = st.sidebar.checkbox("Hide papers already in BugSigDB", value=False)
    out = df.copy()
    if search:
        mask = out["PMID"].astype(str).str.contains(search, na=False)
        for col in ["Title", "Journal", "Summary"]:
            if col in out.columns:
                mask = mask | out[col].astype(str).str.lower().str.contains(search, na=False)
        out = out.loc[mask]
    for col, allowed in status_filters.items():
        if allowed:
            out = out[out[col].isin(allowed)]
    if year_range and "Year" in out.columns:
        out = out[(out["Year"] >= year_range[0]) & (out["Year"] <= year_range[1])]
    if da_only and "has_differential_abundance" in out.columns:
        out = out[out["has_differential_abundance"] == True]  # noqa: E712
    if min_da_conf > 0 and "differential_abundance_confidence" in out.columns:
        out = out[out["differential_abundance_confidence"].fillna(0) >= min_da_conf]
    if hide_bugsigdb and "in_bugsigdb" in out.columns:
        out = out[out["in_bugsigdb"] != True]  # noqa: E712
    return out


def render_table(df: pd.DataFrame) -> Optional[int]:
    if df.empty:
        st.warning("No rows match your filters.")
        return None
    st.subheader("Candidate curatable articles")
    st.caption("Tip: Sort by Priority Score to review the most promising candidates first.")
    sort_options = ["Priority Score", "PMID"]
    if "Title" in df.columns:
        sort_options.append("Title")
    sort_options.extend(c for c in STATUS_COLUMNS if c in df.columns)
    sort_col = st.selectbox("Sort by", options=sort_options, index=0)
    ascending = st.checkbox("Ascending", value=False)
    if sort_col in df.columns:
        df = df.sort_values(by=sort_col, ascending=ascending, na_position="last")
    st.divider()
    max_rows = st.slider("Rows to display", 50, 2000, 300, 50)
    df_show = df.head(max_rows).copy()
    want = ["PMID", "PubMed Link", "Priority Score", "Title", "Journal", "Year"] + list(STATUS_COLUMNS) + ["Summary"]
    display_cols = [c for c in want if c in df_show.columns]
    df_show = df_show[display_cols]
    st.dataframe(
        df_show,
        use_container_width=True,
        height=650,
        column_config={"PubMed Link": st.column_config.LinkColumn("PubMed", display_text="Open")},
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


def render_column_level_validation(selected_row: pd.Series) -> dict[str, str]:
    """Per-column correctness + curator true label UI. Returns col_feedback__* and true__*."""
    st.markdown("### Field-by-field validation (ground truth)")
    st.caption(
        "For each field, provide the curator TRUE label. "
        "Optionally mark whether BioAnalyzer's predicted status was correct."
    )
    out = {}
    left, right = st.columns(2)
    for pane, cols in zip([left, right], [STATUS_COLUMNS[:3], STATUS_COLUMNS[3:]]):
        with pane:
            for col in cols:
                if col not in selected_row.index:
                    continue
                safe = _safe(col)
                pred = str(selected_row.get(col, "")).strip()
                label = col.replace(" Status", "")
                st.markdown(f"**{label}**")
                st.write(f"BioAnalyzer predicted: `{pred}`")
                true_key = f"{TRUE_PREFIX}{safe}"
                out[true_key] = st.selectbox(
                    f"Curator TRUE label for {label}",
                    options=OPTIONS["true_label"],
                    index=0,
                    key=f"ui__{true_key}",
                )
                fb_key = f"{COL_FB_PREFIX}{safe}"
                out[fb_key] = st.selectbox(
                    f"Was BioAnalyzer correct for {label}?",
                    options=OPTIONS["col_feedback"],
                    index=0,
                    key=f"ui__{fb_key}",
                )
                st.divider()
    return out


def render_feedback_section(selected_pmid: Optional[int], dataset_df: pd.DataFrame) -> None:
    st.subheader("Curator feedback")
    st.caption("Feedback is stored locally in results/. Entries are upserted by PMID + curator_id.")
    feedback_df = load_feedback()
    selected_row = None
    if selected_pmid is not None:
        try:
            selected_row = dataset_df.loc[dataset_df["PMID"] == selected_pmid].iloc[0]
        except Exception:
            selected_row = None
    title_prefill = str(selected_row.get("Title", "")) if selected_row is not None and "Title" in selected_row.index else ""

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
        field_validation = render_column_level_validation(selected_row) if selected_row is not None else {}
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
            if selected_pmid is not None and pid != selected_pmid and pid not in dataset_df["PMID"].values:
                st.warning("PMID not in current dataset; feedback will still be saved.")
            row = {
                "PMID": int(pid),
                "curator_id": curator_id,
                "overall_verdict": overall_verdict,
                "comment": comment.strip(),
                "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
                "bioanalyzer_version": bioanalyzer_version,
            }
            for col in STATUS_COLUMNS:
                s = _safe(col)
                row[f"{PRED_PREFIX}{s}"] = (
                    str(selected_row.get(col, "")).strip()
                    if selected_row is not None and col in selected_row.index else ""
                )
                row[f"{TRUE_PREFIX}{s}"] = field_validation.get(f"{TRUE_PREFIX}{s}", "Not reviewed")
                row[f"{COL_FB_PREFIX}{s}"] = field_validation.get(f"{COL_FB_PREFIX}{s}", "Not reviewed")
            feedback_df = upsert_feedback(feedback_df, row)
            save_feedback(feedback_df)
            logger.info("Saved feedback for PMID %s (curator=%s)", pid, curator_id)
            st.success(f"Saved feedback for PMID {pid} (curator={curator_id}).")

    st.divider()
    st.subheader("Existing feedback")
    if feedback_df.empty:
        st.info("No feedback recorded yet.")
        return
    compact_cols = [c for c in FEEDBACK_BASE_COLS if c in feedback_df.columns] + [
        k for c in STATUS_COLUMNS for k in (f"{PRED_PREFIX}{_safe(c)}", f"{TRUE_PREFIX}{_safe(c)}", f"{COL_FB_PREFIX}{_safe(c)}")
        if k in feedback_df.columns
    ]
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

- Curators review predictions and capture feedback by PMID.
- Stored: predicted statuses, curator ground truth, correctness flags.
- Export suitable for confusion matrices, per-field error profiling, MCC for PARTIALLY_PRESENT.
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
        uploaded = st.sidebar.file_uploader("Upload dataset", type=["csv", "parquet", "pq"])
        if uploaded:
            try:
                raw_df = _load_data(uploaded, is_path=False)
            except Exception as e:
                st.error(f"Could not load file: {e}")
                logger.exception("Upload load failed")
                return
    else:
        path = st.sidebar.text_input("Path to CSV/Parquet", placeholder="e.g. analysis_results.csv").strip()
        if path:
            try:
                raw_df = _load_data(path, is_path=True)
            except Exception as e:
                st.error(str(e))
                return
    if raw_df.empty:
        st.info("Upload a dataset or provide a file path to begin.")
        st.stop()
    df = normalize_dataset(raw_df)
    if df.empty:
        st.error("Dataset loaded, but no valid rows found after normalization.")
        st.stop()
    missing = [c for c in STATUS_COLUMNS if c not in df.columns]
    if missing:
        st.warning(
            "Some expected status columns are missing. Priority and filtering will be partial.\n\n"
            f"Missing: {missing}"
        )
    filtered_df = render_filters(df)
    selected_pmid = render_table(filtered_df)
    st.divider()
    render_feedback_section(selected_pmid, filtered_df)
    st.sidebar.divider()
    st.sidebar.header("Notes")
    st.sidebar.markdown(
        f"Feedback: `{FEEDBACK_CSV}` and `{FEEDBACK_PARQUET}`. "
        "Tip: set `BIOANALYZER_VERSION` or `FEEDBACK_DIR` in environment."
    )


if __name__ == "__main__":
    main()
