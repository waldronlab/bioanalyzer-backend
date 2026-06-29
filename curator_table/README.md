# BioAnalyzer Curator Table

Sortable, searchable online table of BioAnalyzer predictions for **candidate curatable articles** from PubMed, for real-world testing by curators (see [Levi’s suggestion](https://github.com/waldronlab/bioanalyzer-backend/blob/main/docs/CURATOR_TABLE_DESIGN.md)).

A static, zero-cost GitHub Pages version of this table was previously built
and removed (see git history for `docs/curator-table/`) - the Streamlit app
below is the current, supported way to run it.

## Quick start

**Recommended – use the CLI** (Streamlit is included in the main project):

```bash
BioAnalyzer run table
```

Then open http://localhost:8501. Use `--port` to change the port:

```bash
BioAnalyzer run table --port 8502
```

**Alternative – run Streamlit directly** from the repo root (after `pip install -e .` or in Docker):

```bash
streamlit run curator_table/app.py
```

Or from this directory:

```bash
pip install -r requirements.txt   # only if not using main project install
streamlit run app.py
```

## Data format

The app expects a **CSV or Parquet** file with at least:

- **PMID** (required)
- **Title** (recommended)
- The 6 status columns:  
  `Host Species Status`, `Body Site Status`, `Condition Status`,  
  `Sequencing Type Status`, `Taxa Level Status`, `Sample Size Status`  
  (values: `PRESENT`, `PARTIALLY_PRESENT`, `ABSENT`)

Optional: `Journal`, `Summary`, `Year`, `Publication Date`, `Processing Time`.

You can use:

- Exports from the BioAnalyzer CLI/API (e.g. `analysis_results.csv`).
- The validation dataset format (e.g. after merging predictions + metadata into one table with PMID, Title, and the six status columns).

## Features

- **Search** by PMID, title, journal, or summary.
- **Sort** by any column (PMID, Title, or any status).
- **PubMed link** per row (opens in a new tab).
- **Curator feedback**: record verdict (Correct / Incorrect / Uncertain) per PMID; feedback is saved to `curator_feedback.csv` in the current working directory and can be downloaded for later analysis.

## Scale and next steps

- **First version:** 1k–5k rows with a single CSV/Parquet file (as above).
- **Larger runs:** Run a big batch on SuperStudio, export results to CSV/Parquet (or a DB), then point the app at that file (or add a DB backend later).

See **`docs/CURATOR_TABLE_DESIGN.md`** for full design (scale, fields, feedback loop, APIs, and implementation plan).
