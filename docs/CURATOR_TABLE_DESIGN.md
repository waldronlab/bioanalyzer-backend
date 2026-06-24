# Curator Table: Design & Implementation Plan


## 1. Scale & storage

| Scale | Approach | Storage | Notes |
|-------|----------|---------|--------|
| **1k–10k PMIDs** | MVP / first version | **Flat file (CSV or Parquet)** | Single file, load in memory in Streamlit. Fast to build and iterate. |
| **10k–50k PMIDs** | Growth | **Parquet** or **SQLite** | Parquet: columnar, good for filtering. SQLite: simple queries, no extra server. |
| **50k–500k+ PMIDs** | Production / SuperStudio | **PostgreSQL or SQLite** + batch jobs on SuperStudio | Run large BioAnalyzer batch on SuperStudio; store results in DB; table reads from DB. |

**Recommendation for first version:**  
- Target **~1k–5k PMIDs** with a **single CSV or Parquet file** (e.g. exported from a batch run or from existing validation exports).  
- Design the app so we can **swap the data source** later (e.g. replace CSV with SQLite/API) without changing the UI.

---

## 2. Minimum Fields in the Table

Suggested **minimum columns** for the sortable table:

| Column | Source | Notes |
|--------|--------|--------|
| **PMID** | BioAnalyzer / PubMed | Link to `https://pubmed.ncbi.nlm.nih.gov/{PMID}` |
| **Title** | PubMed / BioAnalyzer | For quick scanning |
| **Year** | PubMed (publication_date) | For sorting/filtering |
| **Journal** | PubMed / BioAnalyzer | Optional but useful |
| **Host Species** | BioAnalyzer | Status + value |
| **Body Site** | BioAnalyzer | Status + value |
| **Condition** | BioAnalyzer | Status + value |
| **Sequencing Type** | BioAnalyzer | Status + value |
| **Taxa Level** | BioAnalyzer | Status + value |
| **Sample Size** | BioAnalyzer | Status + value |
| **Confidence** | BioAnalyzer | e.g. average or min across fields |
| **Curation summary** | BioAnalyzer | One-line readiness summary |
| **Evidence snippet** (optional) | BioAnalyzer | Short quote per field if we store it; can add later |

**Status values:** `PRESENT` / `PARTIALLY_PRESENT` / `ABSENT` (same as validation).

We can start with **PMID, Title, Year, Journal, the 6 field statuses, and one confidence score**, then add evidence snippets in a second iteration if curators want them.

---

## 3. Curation Feedback Loop

**My Recommendation:** **Yes – support a lightweight feedback loop** so curators can mark predictions as correct/incorrect/uncertain.

- **MVP:** One extra column or side panel: **Curator verdict** (e.g. Correct / Incorrect / Uncertain / Not reviewed).  
- Store verdicts in a **separate file or table** (e.g. `curator_feedback.csv` or `curator_feedback` table) keyed by PMID (and optionally field name if we want field-level feedback later).  
- **Read-only candidate list** can be the default view; feedback is optional and only saved when the curator submits.  
- Later we can use this data to recompute accuracy and confusion matrices (real-world benchmarking).

---

## 4. External APIs & Local Storage

| Concern | Approach |
|---------|----------|
| **PubMed E-utilities** | BioAnalyzer already calls them. For the **table**, we do **not** call PubMed at display time: we use **cached metadata** (title, year, journal) that was stored when the batch was run. So the table is a view over **precomputed results**. |
| **Storing metadata locally** | **Yes.** Batch run (on the machine or SuperStudio) writes: PMID, title, year, journal, and all BioAnalyzer fields + confidence to CSV/Parquet/DB. The curator table only reads that. |
| **SuperStudio** | Used for **running the big batch** (e.g. 50k–500k PMIDs). Results are then copied to a shared store (file or DB) and the table reads from that. |


---

## 5. Tech Stack (First Version)

- **UI:** **Streamlit** (Python, fits BioAnalyzer stack; quick to ship).  
- **Data:** **Pandas** + **CSV or Parquet** (same shape as current validation/export).  
- **Table:** Sortable and searchable via **Streamlit’s native dataframe + filters**, or **st.data_editor** / **streamlit-aggrid** if we need more interactivity.  
- **Feedback:** Form or buttons per row → append to `curator_feedback.csv` (or SQLite) with PMID, verdict, optional comment, timestamp.

---

## 6. Implementation Plan

1. **Define CSV/Parquet schema** for “predictions table” export (from BioAnalyzer batch or from existing validation CSVs).  
2. **Build Streamlit app** that:
   - Loads one or more prediction files (CSV/Parquet).
   - Shows a **sortable, searchable** table (PMID, title, year, journal, 6 statuses, confidence, summary).  
   - Links PMID to PubMed.  
   - Optional: **curator feedback** (Correct / Incorrect / Uncertain) stored in a separate file/table.  
3. **Document** how to run a batch (CLI or API) and export the result into the format the table expects.  
4. **Later:** Point the table at a DB or at results from a SuperStudio batch and add evidence snippets if needed.



## 7. Where the Code Lives

- **Design:** `docs/CURATOR_TABLE_DESIGN.md` (this file).  
- **App:** `curator_table/` (Streamlit app + README).  
- **Data format:** Same as existing BioAnalyzer export (e.g. `analysis_results.csv` / curator-desk CSV shape, see `docs/CURATOR_DESK_CSV_FORMAT.md`); see `scripts/eval/confusion_matrix_analysis.py` for column names (`create_validation_dataset.py`, previously referenced here, no longer exists in the repo).
