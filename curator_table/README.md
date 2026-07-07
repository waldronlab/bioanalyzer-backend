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

The app expects a **CSV or Parquet** file (BioAnalyzer's `curator_desk_csv`
export - see `docs/CURATOR_DESK_CSV_FORMAT.md`) with at least:

- **PMID** (required)
- **Title** (recommended)
- The 5 value columns:
  `Host Species`, `Body Site`, `Condition`, `Sample Size`, `Sequencing Type`
- The 3 ontology ID columns (optional, but needed for the mapping picker):
  `Host Species Ontology ID`, `Body Site Ontology ID`, `Condition Ontology ID`
  (plus their `... Ontology Candidates` counterparts, used to populate the
  mapping picker's suggestions when a mapping isn't auto-applied)

Optional: `Journal`, `Year`, `Differential Abundance`, `In bsgdb`.

You can use:

- Exports from the BioAnalyzer CLI/API (e.g. `BioAnalyzer analyze --file pmids.txt --format csv -o predictions.csv` - `curator_desk_csv` is an accepted alias for the same format).
- Any other CSV/Parquet with at least PMID and the value columns above.

## Features

- **Search** by PMID, title, journal, or condition.
- **Sort** by Year, PMID, or Title.
- **Filter** by year range, differential abundance, BugSigDB status, or "needs an ontology mapping".
- **PubMed link** per row (opens in a new tab).
- **Curator feedback**: correct values, confirm/pick ontology mappings (Host Species/Body Site/Condition), and record a Correct/Incorrect/Uncertain verdict per field and per PMID; feedback is saved to `curator_feedback.csv` in the current working directory and can be downloaded for later analysis.

## Scale and next steps

- **First version:** 1k–5k rows with a single CSV/Parquet file (as above).
- **Larger runs:** Run a big batch on SuperStudio, export results to CSV/Parquet (or a DB), then point the app at that file (or add a DB backend later).

See **`docs/CURATOR_TABLE_DESIGN.md`** for full design (scale, fields, feedback loop, APIs, and implementation plan).
