# Static curator table (GitHub Pages)

This folder contains a **static**, read-only version of the BioAnalyzer curator table that can be hosted on **GitHub Pages**.

- `index.html` – single-page app that loads a CSV and renders a sortable/searchable table.
- `data/predictions_sample.csv` – small example CSV so the page works out of the box.

## How curators will typically use this

- Open the GitHub Pages URL (e.g. `https://<org>.github.io/<repo>/curator-table/`).
- Filter/search within the table.
- Click PubMed links to open articles.
- Review predictions visually.

This view is **read-only** – it does **not** save feedback. For entering feedback (ground truth, correctness, comments), use the **Streamlit app** described in `curator_table/README.md` and `docs/CURATOR_TABLE_USER_GUIDE.md`.

## Using your own data

1. Place a CSV under `docs/curator-table/data/`, for example `docs/curator-table/data/predictions.csv`.
2. The CSV should have at least a `PMID` column; recommended columns are the same as the Streamlit app (Title, Journal, Year, and the six `... Status` fields).
3. In the page, change the **Data URL** field to `data/predictions.csv` and click **Load**.

To enable GitHub Pages for this folder, set **Settings → Pages → Source** to the `docs/` folder on your main branch.
