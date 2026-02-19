#!/usr/bin/env python3
"""
BioAnalyzer Curator Table (with column-level validation + curator ground truth)
=============================================================================

A Streamlit dashboard for real-world validation of BioAnalyzer predictions.

This app supports:
1) A sortable, searchable, filterable table of candidate curatable PubMed articles.
2) A curator feedback workflow aligned by PMID.
3) Column-level correctness checks for each BioAnalyzer field.
4) Curator-provided TRUE labels (ground truth) for each field.
5) Exportable feedback suitable for:
   - confusion matrices
   - per-field error analysis
   - binary + multiclass evaluation
   - MCC decisions on how to treat PARTIALLY_PRESENT

Run:
    streamlit run curator_table/app.py

Input data:
    CSV or Parquet with at minimum:
        - PMID
    Recommended:
        - Title, Journal, Year, Summary
    Expected BioAnalyzer outputs:
        - Host Species Status
        - Body Site Status
        - Condition Status
        - Sequencing Type Status
        - Taxa Level Status
        - Sample Size Status

Status values expected:
    ABSENT | PARTIALLY_PRESENT | PRESENT

Feedback storage:
    results/curator_feedback.csv
    results/curator_feedback.parquet

Design notes
------------
- Feedback is upserted by (PMID, curator_id) to prevent duplicates.
- Feedback rows store BOTH:
    (a) the BioAnalyzer predictions (pred__*)
    (b) the curator's evaluation (col_feedback__*)
    (c) the curator's ground truth labels (true__*)
  This makes benchmarking reproducible even if the input dataset changes.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd
import streamlit as st

# -----------------------------
# Expected prediction columns
# -----------------------------
STATUS_COLUMNS = [
    "Host Species Status",
    "Body Site Status",
    "Condition Status",
    "Sequencing Type Status",
    "Taxa Level Status",
    "Sample Size Status",
]

OPTIONAL_COLUMNS = [
    "Title",
    "Journal",
    "Summary",
    "Processing Time",
    "Year",
    "Publication Date",
]

VALID_STATES = ["ABSENT", "PARTIALLY_PRESENT", "PRESENT"]

# Column-level feedback options (curator judgement of correctness)
COL_FEEDBACK_OPTIONS = [
    "Not reviewed",
    "Correct",
    "Incorrect",
    "Unclear",
]

# True label options (ground truth)
TRUE_LABEL_OPTIONS = [
    "Not reviewed",
    "ABSENT",
    "PARTIALLY_PRESENT",
    "PRESENT",
]

# -----------------------------
# Feedback persistence
# -----------------------------
DEFAULT_FEEDBACK_DIR = Path("results")
DEFAULT_FEEDBACK_DIR.mkdir(exist_ok=True)

FEEDBACK_CSV = DEFAULT_FEEDBACK_DIR / "curator_feedback.csv"
FEEDBACK_PARQUET = DEFAULT_FEEDBACK_DIR / "curator_feedback.parquet"


# -----------------------------
# Helpers
# -----------------------------
def make_pmid_link(pmid) -> str:
    """Return PubMed URL for a PMID."""
    try:
        pid = str(int(float(pmid)))
        return f"https://pubmed.ncbi.nlm.nih.gov/{pid}/"
    except Exception:
        return ""


def safe_int(x) -> Optional[int]:
    try:
        return int(float(x))
    except Exception:
        return None


def normalize_status_value(x: str) -> str:
    """Normalize status values to one of ABSENT/PARTIALLY_PRESENT/PRESENT."""
    if pd.isna(x):
        return ""
    x = str(x).strip().upper()
    if x in VALID_STATES:
        return x

    # Common variants
    if x in {"PARTIAL", "PARTIALLY", "PARTLY"}:
        return "PARTIALLY_PRESENT"
    if x in {"YES", "TRUE"}:
        return "PRESENT"
    if x in {"NO", "FALSE"}:
        return "ABSENT"

    return x


def compute_priority_score(row: pd.Series) -> float:
    """
    Rank candidates by how many fields are predicted present.

    - PRESENT contributes 1.0
    - PARTIALLY_PRESENT contributes 0.5
    """
    score = 0.0
    for col in STATUS_COLUMNS:
        val = str(row.get(col, "")).strip().upper()
        if val == "PRESENT":
            score += 1.0
        elif val == "PARTIALLY_PRESENT":
            score += 0.5
    return score


@st.cache_data(show_spinner=False)
def load_data_from_path(path: str) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()

    suf = path.suffix.lower()
    if suf == ".csv":
        return pd.read_csv(path)
    if suf in (".parquet", ".pq"):
        return pd.read_parquet(path)

    raise ValueError(f"Unsupported format: {suf}. Use .csv or .parquet.")


@st.cache_data(show_spinner=False)
def load_data_from_upload(uploaded) -> pd.DataFrame:
    if uploaded is None:
        return pd.DataFrame()

    name = uploaded.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(uploaded)
    if name.endswith(".parquet") or name.endswith(".pq"):
        return pd.read_parquet(uploaded)

    raise ValueError("Unsupported upload. Use .csv or .parquet.")


def normalize_dataset(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize dataset and derive helper columns."""
    if df.empty:
        return df

    if "PMID" not in df.columns:
        st.error("Data must contain a 'PMID' column.")
        return pd.DataFrame()

    # Normalize PMID
    df["PMID"] = df["PMID"].apply(safe_int)
    df = df.dropna(subset=["PMID"]).copy()
    df["PMID"] = df["PMID"].astype(int)

    # Derive year
    if "Year" not in df.columns and "Publication Date" in df.columns:
        try:
            df["Year"] = pd.to_datetime(df["Publication Date"], errors="coerce").dt.year
        except Exception:
            pass

    # Normalize statuses
    for col in STATUS_COLUMNS:
        if col in df.columns:
            df[col] = df[col].apply(normalize_status_value)

    # Priority score
    df["Priority Score"] = df.apply(compute_priority_score, axis=1)

    # PubMed link
    df["PubMed Link"] = df["PMID"].apply(make_pmid_link)

    return df


def _safe_field_name(col: str) -> str:
    """Convert 'Host Species Status' -> 'Host_Species_Status'."""
    return col.replace(" ", "_")


def _default_feedback_columns() -> List[str]:
    """Defines the full schema for feedback rows."""
    base = [
        "PMID",
        "curator_id",
        "overall_verdict",
        "comment",
        "timestamp",
        "bioanalyzer_version",
    ]

    # Predicted statuses
    pred_cols = []
    for col in STATUS_COLUMNS:
        safe = _safe_field_name(col)
        pred_cols.append(f"pred__{safe}")

    # True labels (curator ground truth)
    true_cols = []
    for col in STATUS_COLUMNS:
        safe = _safe_field_name(col)
        true_cols.append(f"true__{safe}")

    # Column-level feedback (Correct/Incorrect/etc.)
    col_feedback_cols = []
    for col in STATUS_COLUMNS:
        safe = _safe_field_name(col)
        col_feedback_cols.append(f"col_feedback__{safe}")

    return base + pred_cols + true_cols + col_feedback_cols


def load_feedback() -> pd.DataFrame:
    """Load feedback from parquet/csv or return empty with schema."""
    if FEEDBACK_PARQUET.exists():
        try:
            df = pd.read_parquet(FEEDBACK_PARQUET)
            return df
        except Exception:
            pass

    if FEEDBACK_CSV.exists():
        try:
            df = pd.read_csv(FEEDBACK_CSV)
            return df
        except Exception:
            pass

    return pd.DataFrame(columns=_default_feedback_columns())


def save_feedback(df: pd.DataFrame) -> None:
    """Save feedback in CSV and optionally parquet."""
    DEFAULT_FEEDBACK_DIR.mkdir(exist_ok=True)

    # Ensure schema
    for col in _default_feedback_columns():
        if col not in df.columns:
            df[col] = ""

    df.to_csv(FEEDBACK_CSV, index=False)

    try:
        df.to_parquet(FEEDBACK_PARQUET, index=False)
    except Exception:
        # Parquet may fail if pyarrow isn't installed
        pass


def upsert_feedback(existing: pd.DataFrame, row: Dict) -> pd.DataFrame:
    """Upsert by PMID + curator_id."""
    if existing.empty:
        return pd.DataFrame([row])

    # Ensure schema
    for col in _default_feedback_columns():
        if col not in existing.columns:
            existing[col] = ""

    mask = (existing["PMID"].astype(str) == str(row["PMID"])) & (
        existing["curator_id"].astype(str) == str(row["curator_id"])
    )

    if mask.any():
        for k, v in row.items():
            existing.loc[mask, k] = v
        return existing

    return pd.concat([existing, pd.DataFrame([row])], ignore_index=True)


# -----------------------------
# UI rendering
# -----------------------------
def render_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.header("Filters")

    search = st.sidebar.text_input(
        "Search (PMID, title, journal, summary)",
        placeholder="e.g. obesity, 2019, Lactobacillus",
    ).strip().lower()

    status_filters = {}
    for col in STATUS_COLUMNS:
        if col in df.columns:
            status_filters[col] = st.sidebar.multiselect(
                col,
                options=VALID_STATES,
                default=[],
            )

    year_range = None
    if "Year" in df.columns:
        years = df["Year"].dropna()
        if not years.empty:
            years = years.astype(int)
            min_y, max_y = int(years.min()), int(years.max())
            year_range = st.sidebar.slider(
                "Year range",
                min_value=min_y,
                max_value=max_y,
                value=(min_y, max_y),
            )

    out = df.copy()

    # Search
    if search:
        mask = pd.Series(False, index=out.index)
        mask |= out["PMID"].astype(str).str.contains(search, na=False)
        for col in ["Title", "Journal", "Summary"]:
            if col in out.columns:
                mask |= out[col].astype(str).str.lower().str.contains(search, na=False)
        out = out.loc[mask]

    # Status filters
    for col, allowed in status_filters.items():
        if allowed:
            out = out[out[col].isin(allowed)]

    # Year filter
    if year_range and "Year" in out.columns:
        out = out[(out["Year"] >= year_range[0]) & (out["Year"] <= year_range[1])]

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
    for c in STATUS_COLUMNS:
        if c in df.columns:
            sort_options.append(c)

    sort_col = st.selectbox("Sort by", options=sort_options, index=0)
    ascending = st.checkbox("Ascending", value=False)

    if sort_col in df.columns:
        df = df.sort_values(by=sort_col, ascending=ascending, na_position="last")

    st.divider()
    max_rows = st.slider("Rows to display", 50, 2000, 300, 50)
    df_show = df.head(max_rows).copy()

    display_cols: List[str] = ["PMID"]
    if "PubMed Link" in df_show.columns:
        display_cols.append("PubMed Link")

    for c in ["Priority Score", "Title", "Journal", "Year"]:
        if c in df_show.columns:
            display_cols.append(c)

    for c in STATUS_COLUMNS:
        if c in df_show.columns:
            display_cols.append(c)

    if "Summary" in df_show.columns:
        display_cols.append("Summary")

    df_show = df_show[display_cols]

    st.dataframe(
        df_show,
        use_container_width=True,
        height=650,
        column_config={
            "PubMed Link": st.column_config.LinkColumn("PubMed", display_text="Open"),
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
    if selected:
        return int(selected)
    return None


def render_column_level_validation(selected_row: pd.Series) -> Dict[str, str]:
    """
    Render per-column correctness + curator true label UI.
    Returns a dict with keys:
      - col_feedback__X
      - true__X
    """
    st.markdown("### Field-by-field validation (ground truth)")

    st.caption(
        "For each field, provide the curator TRUE label (ground truth). "
        "Optionally also mark whether BioAnalyzer's predicted status was correct."
    )

    out = {}

    left, right = st.columns(2)
    halves = [STATUS_COLUMNS[:3], STATUS_COLUMNS[3:]]

    for pane, cols in zip([left, right], halves):
        with pane:
            for col in cols:
                if col not in selected_row.index:
                    continue

                safe = _safe_field_name(col)
                pred = str(selected_row.get(col, "")).strip()
                label = col.replace(" Status", "")

                st.markdown(f"**{label}**")
                st.write(f"BioAnalyzer predicted: `{pred}`")

                # Curator true label
                true_key = f"true__{safe}"
                true_choice = st.selectbox(
                    f"Curator TRUE label for {label}",
                    options=TRUE_LABEL_OPTIONS,
                    index=0,
                    key=f"ui__{true_key}",
                )
                out[true_key] = true_choice

                # Optional correctness judgement
                fb_key = f"col_feedback__{safe}"
                fb_choice = st.selectbox(
                    f"Was BioAnalyzer correct for {label}?",
                    options=COL_FEEDBACK_OPTIONS,
                    index=0,
                    key=f"ui__{fb_key}",
                )
                out[fb_key] = fb_choice

                st.divider()

    return out


def render_feedback_section(selected_pmid: Optional[int], dataset_df: pd.DataFrame) -> None:
    st.subheader("Curator feedback")
    st.caption("Feedback is stored locally in results/. Entries are upserted by PMID + curator_id.")

    feedback_df = load_feedback()

    selected_row = None
    title_prefill = ""

    if selected_pmid is not None:
        try:
            selected_row = dataset_df.loc[dataset_df["PMID"] == selected_pmid].iloc[0]
        except Exception:
            selected_row = None

    if selected_row is not None and "Title" in selected_row.index:
        title_prefill = str(selected_row.get("Title", ""))

    with st.form("feedback_form", clear_on_submit=False):
        curator_id = st.text_input(
            "Curator ID / initials",
            value=os.getenv("USER", ""),
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
            value=os.getenv("BIOANALYZER_VERSION", ""),
            placeholder="e.g. 1.0.0, commit SHA, docker tag",
        ).strip()

        # Field-by-field validation
        field_validation = {}
        if selected_row is not None:
            field_validation = render_column_level_validation(selected_row)
        else:
            st.info("Select a PMID above to enable field-level validation.")

        submitted = st.form_submit_button("Save feedback")

        if submitted:
            if not curator_id:
                st.error("Please provide curator_id (initials or username).")
                return
            if not fb_pmid:
                st.error("Please provide a PMID.")
                return

            pid = safe_int(fb_pmid)
            if pid is None:
                st.error("PMID must be numeric.")
                return

            row = {
                "PMID": int(pid),
                "curator_id": curator_id,
                "overall_verdict": overall_verdict,
                "comment": comment.strip(),
                "timestamp": pd.Timestamp.now(tz="UTC").isoformat(),
                "bioanalyzer_version": bioanalyzer_version,
            }

            # Always store predictions into feedback (reproducibility)
            for col in STATUS_COLUMNS:
                safe = _safe_field_name(col)
                pred_key = f"pred__{safe}"

                if selected_row is not None and col in selected_row.index:
                    row[pred_key] = str(selected_row.get(col, "")).strip()
                else:
                    row[pred_key] = ""

            # Store curator true labels + correctness
            for col in STATUS_COLUMNS:
                safe = _safe_field_name(col)

                true_key = f"true__{safe}"
                fb_key = f"col_feedback__{safe}"

                row[true_key] = field_validation.get(true_key, "Not reviewed")
                row[fb_key] = field_validation.get(fb_key, "Not reviewed")

            feedback_df = upsert_feedback(feedback_df, row)
            save_feedback(feedback_df)

            st.success(f"Saved feedback for PMID {pid} (curator={curator_id}).")

    st.divider()
    st.subheader("Existing feedback")

    if feedback_df.empty:
        st.info("No feedback recorded yet.")
        return

    compact_cols = [
        "PMID",
        "curator_id",
        "overall_verdict",
        "timestamp",
        "bioanalyzer_version",
    ]

    # Add prediction + true + feedback columns in a readable order
    for col in STATUS_COLUMNS:
        safe = _safe_field_name(col)
        for k in [f"pred__{safe}", f"true__{safe}", f"col_feedback__{safe}"]:
            if k in feedback_df.columns:
                compact_cols.append(k)

    compact_cols = [c for c in compact_cols if c in feedback_df.columns]

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


# -----------------------------
# Main
# -----------------------------
def main():
    st.set_page_config(page_title="BioAnalyzer Curator Table", layout="wide")
    st.title("BioAnalyzer Curator Table")

    st.markdown(
        """
This dashboard provides a **sortable, searchable, filterable** table of BioAnalyzer predictions for
candidate curatable PubMed articles.

### Why this is useful
- Lets curators review predictions in a real-world workflow
- Captures feedback aligned by PMID
- Stores:
  - BioAnalyzer predicted statuses
  - curator ground truth statuses
  - curator correctness flags

This makes the exported feedback suitable for:
- confusion matrices
- per-field error profiling
- MCC decisions for PARTIALLY_PRESENT
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
            "Upload dataset",
            type=["csv", "parquet", "pq"],
        )
        if uploaded:
            try:
                raw_df = load_data_from_upload(uploaded)
            except Exception as e:
                st.error(f"Could not load file: {e}")
                return
    else:
        path = st.sidebar.text_input(
            "Path to CSV/Parquet",
            placeholder="e.g. analysis_results.csv",
        ).strip()
        if path:
            try:
                raw_df = load_data_from_path(path)
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
            "Some expected status columns are missing. "
            "Priority scoring and filtering will be partial.\n\n"
            f"Missing columns: {missing}"
        )

    filtered_df = render_filters(df)
    selected_pmid = render_table(filtered_df)

    st.divider()
    render_feedback_section(selected_pmid, filtered_df)

    st.sidebar.divider()
    st.sidebar.header("Notes")
    st.sidebar.markdown(
        f"""
Feedback files are saved to:

- `{FEEDBACK_CSV}`
- `{FEEDBACK_PARQUET}` (if parquet supported)

Tip: set an environment variable to track versions:

- `BIOANALYZER_VERSION=commit_sha`
        """
    )


if __name__ == "__main__":
    main()
