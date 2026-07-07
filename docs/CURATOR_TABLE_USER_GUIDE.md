# Curator Table – User Guide

## 1. Purpose and audience

This guide is for **curators** who will use the BioAnalyzer **curator table** to review candidate articles, confirm/correct BioAnalyzer's extracted values and ontology mappings, and provide feedback (ground truth + correctness) on BioAnalyzer's predictions.

There are **two ways** you may see the table:
- A **read‑only web table** (hosted on GitHub Pages) – for **browsing** predictions.
- A **Streamlit app** – for **entering feedback** that is saved and later used for evaluation.

This guide explains what you see and **how to review and record feedback**. You can use the link here https://waldronlab.io/curator-desk/ to access the curator's table

## 2. What you need

- A web browser and a link to either:
  - The **static curator table** (GitHub Pages URL), or
  - The **interactive Streamlit table** (URL provided by the team).
- Access to **PubMed** (no login required) to read abstracts/full text for each PMID.
- Basic familiarity with the five curator-desk fields:
  1. Host Species
  2. Body Site
  3. Condition
  4. Sample Size
  5. Sequencing Type

  (Taxa Level is a sixth field BioAnalyzer's API tracks internally, but it is not shown in the curator table — curators assign it directly during BugSigDB curation, not from this tool.)

For the **Streamlit feedback app**, you will also choose:
- A short **curator ID/initials** (e.g. `RO`, `levi`, etc.).

## 3. Understanding the columns

Typical columns in the table:

- **PMID** – PubMed identifier for the article. Click the PubMed link to open the article.
- **Year / Title / Journal** – basic metadata for quick scanning.
- **Host Species / Body Site / Condition / Sample Size / Sequencing Type** – BioAnalyzer's extracted values, shown as plain text.
- **Ontology ID columns** (`Host Species Ontology ID`, `Body Site Ontology ID`, `Condition Ontology ID`) – the ontology term BioAnalyzer mapped the value to (NCBITaxon, UBERON, EFO respectively). **An empty Ontology ID cell means that field needs a curator-confirmed mapping.**
- **Differential Abundance** – `Yes`/`No`, whether the paper reports specific microbial taxa as statistically more/less abundant between groups.
- **In bsgdb** – `Yes`/`No`, whether this PMID is already present in BugSigDB.

There are no `PRESENT`/`PARTIALLY_PRESENT`/`ABSENT` status columns or a Priority score in this view — BioAnalyzer still computes that internally for its own QA, but the curator-facing table shows plain values instead.

## 4. Using the filters and table

When you open the **Streamlit** curator table you will see:

- A **filter sidebar** on the left:
  - Free‑text **Search** (by PMID, title, journal, condition).
  - A **Year range** slider (if Year is available).
  - **Only differential abundance papers** checkbox (on by default).
  - **Hide papers already in BugSigDB** checkbox.
  - **Only papers needing an ontology mapping** checkbox – shows rows where at least one of Host Species/Body Site/Condition has no Ontology ID yet.
- A main **table** of "Candidate curatable articles":
  - You can **sort** by Year, PMID, or Title.
  - You can control how many rows to show at once.

Recommended workflow:
1. Filter by **year** or **keywords** relevant to your curation task.
2. Optionally check **"Only papers needing an ontology mapping"** to focus on rows that need your attention.
3. Use the **PubMed** link to open the article in a new tab when needed.

## 5. Curator feedback workflow (Streamlit app)

When feedback is enabled, scroll below the table to the **"Curator feedback"** section.

### 5.1 Selecting a paper to review

1. In the main table, apply filters and sorting.
2. Use **"Quick select for feedback"**:
   - Choose a **PMID** from the drop‑down of currently displayed rows.
   - This will prefill the feedback form with the selected paper's info.

### 5.2 Filling the feedback form

In the **feedback form** you will see fields similar to:

- **Curator ID / initials** – enter your identifier (e.g. `RO`, `levi`). This ties feedback to you.
- **PMID** – prefilled when you use "Quick select"; you can also type it manually.
- **Title** – shown for context (read‑only).
- **Overall paper verdict** – choose one:
  - `Curatable` – paper looks appropriate for BugSigDB curation.
  - `Not curatable` – not appropriate (e.g. wrong organism/body site, not microbiome, insufficient data).
  - `Uncertain` – unclear from the abstract/full text.
  - `Not reviewed` – you did not actually review this paper.
- **Comment (optional)** – free‑text notes, such as:
  - Why a prediction is wrong.
  - Important edge cases.
  - Reasons a paper is or is not curatable.
- **BioAnalyzer version (optional)** – version, commit, or Docker tag shown by your coordinator (helps track model changes).

### 5.3 Field‑by‑field validation (ground truth + ontology mapping)

Below the main fields you will see **per‑field controls** for each of the five value fields (Host Species, Body Site, Condition, Sample Size, Sequencing Type):

1. The app shows **BioAnalyzer's predicted value** as plain text.
2. You provide:
   - **Curator value** – type the corrected value if BioAnalyzer's prediction is wrong or incomplete (leave blank to accept the prediction as-is).
   - **"Was BioAnalyzer correct for this field?"**: `Correct` / `Incorrect` / `Unclear` / `Not reviewed`.
3. For **Host Species, Body Site, and Condition** specifically, you also see an **ontology mapping** control:
   - BioAnalyzer's predicted Ontology ID (or a note that none was found).
   - A drop‑down of suggested candidates (when the mapping wasn't auto‑applied), plus a **"Confirm predicted"** option and an **"Other (enter manually)"** option for typing an ontology ID yourself (e.g. `NCBITaxon:9606`).

Guidelines:
- If BioAnalyzer's value and mapping both look right, you can leave the value field blank and just confirm/leave the ontology mapping as predicted.
- If a field is ambiguous or wrong, use the comment box to explain why.
- For ontology mappings flagged as needing review (empty Ontology ID, or a candidate list shown), please pick the correct one or enter it manually — this is the main thing curators are asked to help with beyond value corrections.

### 5.4 Saving feedback

1. After filling **Curator ID**, **PMID**, overall verdict, and (optionally) field‑level judgements, click **"Save feedback"**.
2. If something is missing (e.g. curator ID or PMID not numeric), you will see an error message at the top of the form.
3. On success, you will see a message like:
   > Saved feedback for PMID 12345678 (curator=RO).

Feedback is stored in the project's `results/` directory as:
- `curator_feedback.csv`
- `curator_feedback.parquet` (if the environment supports it)

Each feedback row includes:
- PMID, curator ID, timestamp, and BioAnalyzer version.
- The **predicted values** (and, for the three ontology-mapped fields, predicted Ontology IDs) for each field.
- Your **corrected values**/**confirmed or corrected Ontology IDs**.
- Your **Correct/Incorrect/Unclear/Not reviewed** judgement per value field.

### 5.5 Reviewing existing feedback

Below the form you will see an **"Existing feedback"** table that lists past entries, sorted by most recent first. This helps you:
- Avoid duplicating work on the same PMID.
- Check what other curators have already said (if allowed by your coordinator).

## 6. Static GitHub Pages table (read‑only)

If you are given a **GitHub Pages URL** (e.g. ending in `/curator-table/`):

- This is a **read‑only** version of the curator table, with the same mapping picker available in its feedback form.
- You can:
  - Search within the table.
  - Sort by columns.
  - Click PubMed links.
  - Fill in the feedback form and pick/confirm ontology mappings, same as the Streamlit app.
- Because this page is static, **saving downloads a CSV** for you to submit via your usual process (e.g. a GitHub issue) rather than saving directly to a shared file.

## 7. What happens with your feedback

Your feedback is used to:
- Confirm/correct BioAnalyzer's extracted values and ontology mappings.
- Compare BioAnalyzer's predictions against curator **ground truth**.
- Decide how mature the system is for use in BugSigDB and other curation workflows.

Coordinators may export `curator_feedback.csv` and combine it with prediction data to:
- Re‑run validation scripts.
- Tune models and prompts.
- Identify systematic failure modes (e.g. certain journals, years, or conditions, or ontology terms that consistently need correction).

## 8. Tips and best practices for curators

- Prefer **quality over quantity** – a smaller set of carefully reviewed papers is more useful than many shallow reviews.
- When in doubt, use **"Unclear"** or **"Not reviewed"** instead of guessing.
- Use the **comments** box to document tricky cases (mixed populations, multiple body sites/conditions, etc.).
- Prioritize papers flagged as **needing an ontology mapping** — that's the fastest way to add value on top of BioAnalyzer's automated extraction.
- If you see repeated problems (e.g. BioAnalyzer always mislabels a certain sequencing type), mention this in comments or in a separate email/issue.

If anything in this guide is unclear, curators should contact the project coordinator for clarification or updated instructions.
