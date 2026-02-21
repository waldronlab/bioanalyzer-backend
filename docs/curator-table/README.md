# Curator table on GitHub Pages (static, zero server cost)

This folder contains a **static** curator table: a single HTML page that loads a CSV and shows a sortable, searchable table with PMIDs linked to PubMed. It is designed to be hosted on **GitHub Pages** so Levi and curators can use it without running any server (minimal cost).

## What’s here

- **`index.html`** – Single-page app: fetches a CSV, renders a table, client-side search and column sort. PMID column links to `https://pubmed.ncbi.nlm.nih.gov/{PMID}`.
- **`data/predictions_sample.csv`** – Minimal sample CSV so the page works out of the box. Replace or add your own file (e.g. `data/predictions.csv`) for real runs.

## Enabling GitHub Pages

1. In your GitHub repo: **Settings → Pages**.
2. Under **Build and deployment**:
   - **Source**: Deploy from a branch.
   - **Branch**: `main` (or your default branch), folder **`/docs`**.
3. Save. After a short delay, the site will be at:
   - `https://<org>.github.io/<repo>/`
   - The curator table will be at: `https://<org>.github.io/<repo>/curator-table/`

So the table URL is: **`https://<org>.github.io/<repo>/curator-table/`** (or `.../curator-table/index.html`).

## Using your own data

1. Add a CSV to this folder, e.g. `data/predictions.csv`, with at least a **PMID** column. Recommended columns (same as the Streamlit app): PMID, Title, Journal, Year, Host Species Status, Body Site Status, Condition Status, Sequencing Type Status, Taxa Level Status, Sample Size Status.
2. In the table page, set **Data URL** to `data/predictions.csv` and click **Load** (or leave the default to use the sample).
3. Commit and push; GitHub Pages will serve the updated CSV and the table will load it.

You can also point **Data URL** to a full URL of a CSV hosted elsewhere (e.g. raw GitHub URL of a file in another repo), as long as that URL is CORS-friendly.

## Streamlit vs static table

| | Streamlit (Docker) | Static (GitHub Pages) |
|---|-------------------|------------------------|
| **Run** | `BioAnalyzer run table` (runs Streamlit in Docker) | Just open the Pages URL; no run step |
| **Cost** | Needs a machine/container running | Free (GitHub Pages) |
| **Feedback** | Saves curator feedback (e.g. to CSV/Parquet) | View-only; no server to store feedback |
| **Data** | Load from local CSV/Parquet or DB | Load from CSV in repo or any CSV URL |

For **viewing and sharing** the predictions table with curators at minimal cost, use the **GitHub Pages** static table. For **collecting curator feedback** (correct/incorrect, ground truth labels), use the **Streamlit** app via `BioAnalyzer run table` (or export feedback via another mechanism and merge offline).
