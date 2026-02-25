# Curator Table – User Guide

## 1. Purpose and audience

This guide is for **curators** who will use the BioAnalyzer **curator table** to review candidate articles and provide feedback (ground truth + correctness) on BioAnalyzer’s predictions.

There are **two ways** you may see the table:
- A **read‑only web table** (hosted on GitHub Pages) – for **browsing** predictions.
- A **Streamlit app** – for **entering feedback** that is saved and later used for evaluation.

Your coordinator will tell you which link to use. This guide explains what you see and **how to review and record feedback**.

## 2. What you need

- A web browser and a link to either:
  - The **static curator table** (GitHub Pages URL), or
  - The **interactive Streamlit table** (URL provided by the team).
- Access to **PubMed** (no login required) to read abstracts/full text for each PMID.
- Basic familiarity with the six BugSigDB fields:
  1. Host Species
  2. Body Site
  3. Condition
  4. Sequencing Type
  5. Taxa Level
  6. Sample Size

For the **Streamlit feedback app**, you will also choose:
- A short **curator ID/initials** (e.g. `RO`, `levi`, etc.).

## 3. Understanding the columns

Typical columns in the table:

- **PMID** – PubMed identifier for the article. Click the PubMed link to open the article.
- **Title / Journal / Year** – basic metadata for quick scanning.
- **Priority Score** – higher scores are more likely to be useful for curation (used for sorting / triage).
- **Six “Status” columns** (one per field):
  - `Host Species Status`
  - `Body Site Status`
  - `Condition Status`
  - `Sequencing Type Status`
  - `Taxa Level Status`
  - `Sample Size Status`

Each status is one of:
- `PRESENT` – BioAnalyzer believes the information is clearly present.
- `PARTIALLY_PRESENT` – some evidence is present, but incomplete/ambiguous.
- `ABSENT` – BioAnalyzer did **not** find clear evidence for that field.

The Streamlit app may also show:
- **Summary** – short text summary or curation‑readiness summary.
- **PubMed Link** – one‑click link to the article on PubMed.

## 4. Using the filters and table

When you open the **Streamlit** curator table you will see:

- A **filter sidebar** on the left:
  - Free‑text **Search** (by PMID, title, journal, summary).
  - Multi‑select filters for each **Status** column.
  - A **Year range** slider (if Year is available).
- A main **table** of “Candidate curatable articles”:
  - You can **sort** by Priority Score, PMID, Title, or any Status column.
  - You can control how many rows to show at once.

Recommended workflow:
1. Filter by **year** or **keywords** relevant to your curation task.
2. Sort by **Priority Score** (highest first) or another column of interest.
3. Use the **PubMed** link to open the article in a new tab when needed.

## 5. Curator feedback workflow (Streamlit app)

When feedback is enabled, scroll below the table to the **“Curator feedback”** section.

### 5.1 Selecting a paper to review

1. In the main table, apply filters and sorting.
2. Use **“Quick select for feedback”**:
   - Choose a **PMID** from the drop‑down of currently displayed rows.
   - This will prefill the feedback form with the selected paper’s info.

### 5.2 Filling the feedback form

In the **feedback form** you will see fields similar to:

- **Curator ID / initials** – enter your identifier (e.g. `RO`, `levi`). This ties feedback to you.
- **PMID** – prefilled when you use “Quick select”; you can also type it manually.
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

### 5.3 Field‑by‑field validation (ground truth)

Below the main fields you will see **per‑field controls** for each of the six Status columns:

For each field (Host Species, Body Site, Condition, Sequencing Type, Taxa Level, Sample Size):
1. The app shows **BioAnalyzer’s predicted status** (e.g. `PRESENT`, `PARTIALLY_PRESENT`, `ABSENT`).
2. You provide two judgements:
   - **Curator TRUE label** for that field (ground truth), chosen from:
     - `PRESENT`
     - `PARTIALLY_PRESENT`
     - `ABSENT`
     - `Not reviewed` (if you did not check this field)
   - **“Was BioAnalyzer correct for this field?”**:
     - `Correct`
     - `Incorrect`
     - `Unclear`
     - `Not reviewed`

Guidelines:
- Use **`PRESENT`** only when the field is clearly described.
- Use **`PARTIALLY_PRESENT`** when some evidence exists but is incomplete, ambiguous, or mixed.
- Use **`ABSENT`** when the field is truly not supported by the text.
- If you did not look at a particular field, leave it as **`Not reviewed`**.

### 5.4 Saving feedback

1. After filling **Curator ID**, **PMID**, overall verdict, and (optionally) field‑level judgements, click **“Save feedback”**.
2. If something is missing (e.g. curator ID or PMID not numeric), you will see an error message at the top of the form.
3. On success, you will see a message like:
   > Saved feedback for PMID 12345678 (curator=RO).

Feedback is stored in the project’s `results/` directory as:
- `curator_feedback.csv`
- `curator_feedback.parquet` (if the environment supports it)

Each feedback row includes:
- PMID, curator ID, timestamp, and BioAnalyzer version.
- The **predicted statuses** for each field.
- Your **true labels** for each field.
- Your **Correct/Incorrect/Unclear/Not reviewed** judgement per field.

### 5.5 Reviewing existing feedback

Below the form you will see an **“Existing feedback”** table that lists past entries, sorted by most recent first. This helps you:
- Avoid duplicating work on the same PMID.
- Check what other curators have already said (if allowed by your coordinator).

## 6. Static GitHub Pages table (read‑only)

If you are given a **GitHub Pages URL** (e.g. ending in `/curator-table/`):

- This is a **read‑only** version of the curator table.
- You can:
  - Search within the table.
  - Sort by columns.
  - Click PubMed links.
- You **cannot** save feedback from this page; use the Streamlit app if you need to enter feedback.

## 7. What happens with your feedback

Your feedback is used to:
- Compute **confusion matrices** and accuracy metrics for each field.
- Compare BioAnalyzer’s predictions against curator **ground truth**.
- Decide how mature the system is for use in BugSigDB and other curation workflows.

Coordinators may export `curator_feedback.csv` and combine it with prediction data to:
- Re‑run validation scripts.
- Tune models and prompts.
- Identify systematic failure modes (e.g. certain journals, years, or conditions).

## 8. Tips and best practices for curators

- Prefer **quality over quantity** – a smaller set of carefully reviewed papers is more useful than many shallow reviews.
- When in doubt, use **“Unclear”** or **“Not reviewed”** instead of guessing.
- Use the **comments** box to document tricky cases (mixed populations, multiple body sites, etc.).
- If you see repeated problems (e.g. BioAnalyzer always mislabels a certain sequencing type), mention this in comments or in a separate email/issue.

If anything in this guide is unclear, curators should contact the project coordinator for clarification or updated instructions.
