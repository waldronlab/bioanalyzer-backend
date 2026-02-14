"""
BioAnalyzer Curator Table – sortable, searchable table of predictions for real-world testing.

Run: streamlit run curator_table/app.py
Data: CSV or Parquet with columns PMID, Title, (optional) Journal, and the 6 *Status columns.
"""

import streamlit as st
import pandas as pd
from pathlib import Path

# Expected status columns (BioAnalyzer output)
STATUS_COLUMNS = [
    "Host Species Status",
    "Body Site Status",
    "Condition Status",
    "Sequencing Type Status",
    "Taxa Level Status",
    "Sample Size Status",
]

# Optional columns we can show if present
OPTIONAL_COLUMNS = ["Journal", "Summary", "Processing Time", "Year", "Publication Date"]


def load_data(path: str) -> pd.DataFrame:
    """Load CSV or Parquet into a DataFrame."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame()
    suf = path.suffix.lower()
    if suf == ".csv":
        return pd.read_csv(path)
    if suf in (".parquet", ".pq"):
        return pd.read_parquet(path)
    raise ValueError(f"Unsupported format: {suf}. Use .csv or .parquet.")


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure we have PMID and standard status columns; derive Year if possible."""
    if df.empty:
        return df
    if "PMID" not in df.columns:
        st.error("Data must contain a 'PMID' column.")
        return pd.DataFrame()
    # Year from publication date or other column if present
    if "Year" not in df.columns and "Publication Date" in df.columns:
        try:
            df["Year"] = pd.to_datetime(df["Publication Date"], errors="coerce").dt.year
        except Exception:
            pass
    return df


def make_pmid_link(pmid) -> str:
    """Return PubMed URL for a PMID."""
    try:
        pid = str(int(float(pmid)))
        return f"https://pubmed.ncbi.nlm.nih.gov/{pid}/"
    except (ValueError, TypeError):
        return ""


def render_table(df: pd.DataFrame) -> None:
    """Render sortable/searchable table and optional feedback."""
    if df.empty:
        st.info("No data to display. Load a CSV or Parquet file with BioAnalyzer predictions.")
        return

    st.subheader("Candidate curatable articles")
    st.caption("Sort using the column selector; search in the text box below.")

    # Search
    search = st.text_input("Search (PMID, title, journal, summary)", key="search")
    if search:
        search = search.strip().lower()
        mask = pd.Series(False, index=df.index)
        for col in df.select_dtypes(include=["object"]).columns:
            mask |= df[col].astype(str).str.lower().str.contains(search, na=False)
        df = df.loc[mask]
    if df.empty:
        st.warning("No rows match the search.")
        return

    # Sort
    sort_col = st.selectbox(
        "Sort by",
        options=["PMID", "Title"] + [c for c in STATUS_COLUMNS if c in df.columns],
        key="sort_col",
    )
    ascending = st.checkbox("Ascending", value=True, key="asc")
    if sort_col in df.columns:
        df = df.sort_values(by=sort_col, ascending=ascending, na_position="last")

    # Columns to show: PMID (as link), Title, Journal, Year, status columns, Summary if present
    display_cols = ["PMID", "Title"]
    for c in ["Journal", "Year"] + STATUS_COLUMNS:
        if c in df.columns and c not in display_cols:
            display_cols.append(c)
    if "Summary" in df.columns:
        display_cols.append("Summary")
    display_cols = [c for c in display_cols if c in df.columns]
    table_df = df[display_cols].copy()

    # Add PubMed link column
    table_df["PubMed"] = table_df["PMID"].apply(
        lambda x: f"[Open]({make_pmid_link(x)})" if pd.notna(x) else ""
    )
    # Reorder so link is after PMID
    cols = ["PMID", "PubMed"] + [c for c in display_cols if c != "PMID"]
    table_df = table_df[[c for c in cols if c in table_df.columns]]

    st.dataframe(
        table_df,
        use_container_width=True,
        column_config={
            "PubMed": st.column_config.LinkColumn("PubMed", display_text="Open"),
        },
        height=min(600, 80 + 35 * len(table_df)),
    )

    st.metric("Rows shown", len(table_df))

    # Optional: curator feedback (one verdict per PMID)
    st.subheader("Curator feedback")
    st.caption("Record your verdict for a paper to support real-world benchmarking.")
    feedback_file = Path("curator_feedback.csv")
    with st.form("feedback_form"):
        fb_pmid = st.text_input("PMID", key="fb_pmid", placeholder="e.g. 31215600")
        verdict = st.selectbox(
            "Verdict",
            options=["Correct", "Incorrect", "Uncertain", "Not reviewed"],
            key="verdict",
        )
        comment = st.text_area("Comment (optional)", key="fb_comment", height=80)
        submitted = st.form_submit_button("Save feedback")
        if submitted and fb_pmid and fb_pmid.strip():
            try:
                row = {
                    "PMID": fb_pmid.strip(),
                    "verdict": verdict,
                    "comment": (comment or "").strip(),
                    "timestamp": pd.Timestamp.now().isoformat(),
                }
                new_df = pd.DataFrame([row])
                if feedback_file.exists():
                    existing = pd.read_csv(feedback_file)
                    existing = pd.concat([existing, new_df], ignore_index=True)
                else:
                    existing = new_df
                existing.to_csv(feedback_file, index=False)
                st.success(f"Saved verdict for PMID {fb_pmid}.")
            except Exception as e:
                st.error(f"Could not save feedback: {e}")
    if feedback_file.exists():
        fb_df = pd.read_csv(feedback_file)
        st.download_button(
            "Download feedback CSV",
            data=fb_df.to_csv(index=False),
            file_name=feedback_file.name,
            mime="text/csv",
            key="dl_feedback",
        )


def main():
    st.set_page_config(page_title="BioAnalyzer Curator Table", layout="wide")
    st.title("BioAnalyzer Curator Table")
    st.markdown(
        "Sortable, searchable table of BioAnalyzer predictions for **candidate curatable articles**. "
        "Use this for real-world testing by curators."
    )

    # Data source: file upload or path
    data_source = st.radio(
        "Data source",
        options=["Upload CSV/Parquet", "Use file path"],
        key="data_source",
    )

    df = pd.DataFrame()
    if data_source == "Upload CSV/Parquet":
        uploaded = st.file_uploader("Choose a file", type=["csv", "parquet"], key="upload")
        if uploaded:
            try:
                if uploaded.name.lower().endswith(".csv"):
                    df = pd.read_csv(uploaded)
                else:
                    df = pd.read_parquet(uploaded)
            except Exception as e:
                st.error(f"Could not load file: {e}")
    else:
        path = st.text_input(
            "Path to CSV or Parquet (e.g. analysis_results.csv or ../validation_dataset.csv)",
            value="",
            key="path",
        )
        if path:
            try:
                df = load_data(path.strip())
            except Exception as e:
                st.error(str(e))

    df = normalize_columns(df)
    render_table(df)

    st.sidebar.header("About")
    st.sidebar.markdown(
        "Data should contain **PMID** and the 6 status columns: "
        "Host Species Status, Body Site Status, Condition Status, "
        "Sequencing Type Status, Taxa Level Status, Sample Size Status. "
        "Optional: Title, Journal, Summary, Year."
    )
    st.sidebar.markdown("See `docs/CURATOR_TABLE_DESIGN.md` for scale, fields, and feedback plan.")


if __name__ == "__main__":
    main()
