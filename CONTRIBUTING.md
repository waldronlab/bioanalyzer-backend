# Contributing

Thanks for contributing to BioAnalyzer. This is a working research tool used
by an active lab (waldronlab) - the guidance below exists to keep changes
safe to merge quickly, not to slow you down.

## Before you start

- For anything beyond a small fix, open an issue or check existing ones
  first - this avoids duplicate work on the extraction pipeline, which
  several scripts/tests/the curator-desk CSV format all depend on having a
  stable shape.
- Read [`CLAUDE.md`](CLAUDE.md) first. It's the canonical description of
  what's actually implemented (as opposed to `docs/ARCHITECTURE.md`, which
  is partly an aspirational roadmap - `CLAUDE.md` says so explicitly).
  [`docs/DEVELOPER_GUIDE.md`](docs/DEVELOPER_GUIDE.md) and
  [`docs/FOLDER_STRUCTURE.md`](docs/FOLDER_STRUCTURE.md) cover how to extend
  it and where things live.

## Setting up

```bash
git clone git@github.com:waldronlab/bioanalyzer-backend.git
cd bioanalyzer-backend
pip install -e .[dev]
cp .env.example .env   # fill in NCBI_API_KEY, EMAIL, and one LLM provider key
```

Or use Docker (`./install.sh && BioAnalyzer build`) - see the root
[README.md](README.md) for both paths.

## Making a change

1. Branch off `main`: `git checkout -b <type>/<short-description>` (e.g.
   `fix/host-species-mouse-misclassification`).
2. Make the change. Prefer small, reviewable commits over one large diff -
   this codebase's history is full of "one concern per commit" for exactly
   this reason.
3. Add or update tests for anything you change in `app/`. If you're fixing
   a bug, add a regression test that fails before your fix and passes
   after - see "Test conventions" in `docs/DEVELOPER_GUIDE.md`.
4. Run the full check sequence locally before opening a PR:

```bash
pytest tests/ -v
black app/ tests/ scripts/cli.py scripts/main.py
flake8 app/ tests/ scripts/cli.py scripts/main.py --max-line-length=120 \
  --extend-ignore=E203,W503,E501,F401,F403,F811,F841,W291,W293,E402,E722,F541
bandit -r app/ -ll
```

   `./scripts/format_code.sh` / `./scripts/fix_linting.sh` run Black in a
   throwaway container if you'd rather not install it locally.

## What CI checks

`.github/workflows/ci.yml` runs on every push/PR to `main`/`develop`
(skipped for docs-only changes): tests (Python 3.10 and 3.11), Black,
Flake8, Bandit, a Safety dependency-vulnerability scan, and a Docker
build-and-smoke-test. All of those block merge except the **type-check
(mypy) job, which is explicitly non-blocking** - CI runs it for visibility,
but pre-existing and new mypy findings don't fail the build. Fix mypy
issues you introduce when it's easy to do so, but don't feel obligated to
resolve unrelated pre-existing ones in the same PR.

## Scientific-accuracy changes need extra care

Anything touching `app/normalization/*.py`, `app/services/bugsigdb_analyzer/`,
or the extraction prompts in `app/models/gemini_qa.py` /
`app/services/bugsigdb_analyzer/constants.py` affects what curators see as
the "ground truth" extracted from a paper. If you're changing classification
logic (not just refactoring), explain the *before* and *after* behavior for
a concrete example in your PR description, not just "fixes edge case" -
this has been the difference between a reviewable change and one that
needs a follow-up question every time so far.

## Credential safety

Never commit `.env`, API keys, or real PMIDs/data that could identify a
specific patient cohort beyond what's already in the published paper.
Any exception text that reaches a log line or an HTTP response must go
through `app.utils.credential_masking.mask_exception_message()` first -
see `docs/DEVELOPER_GUIDE.md` for the pattern and why it's not optional.

## Two repositories

`curator_table_r/` is a separate git repository (remote
`waldronlab/curator-desk`) nested inside this one for local convenience.
Changes to it need their own PR against that repo, not this one - see
[`docs/FOLDER_STRUCTURE.md`](docs/FOLDER_STRUCTURE.md).
