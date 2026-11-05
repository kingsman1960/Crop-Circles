# Crop Circles – data prep (NASA Space Apps 2026, Field Shift)

This folder collects the raw data our team will use during the hackathon.
The full task list is in @docs/DATA_COLLECTION.md – read it before doing anything.

## Scope (updated 2026-11-04)

- The "no analysis / no app code before the event" rule is lifted: the team decided on 2026-11-04 to start the build early.
- Data prep (this folder) keeps its rules below. App and pipeline live next to it at the repo root:

```
pipeline/        raw -> data/processed (python -m pipeline, from the repo root)
app/             Streamlit app (streamlit run app/app.py); smoke test: python app/smoke_test.py
content/         strategy cards, crop calendars, indicators, glossary, sources (TOML, edited without code)
submission/      SI-use log, demo material
crop-circles-data-prep/data/processed/   small app-ready files, committed
```

- Definition of done (WORKFLOW.md §4): runs from a clean clone with the documented command; every chart shows unit, source and period; every dataset used is in `docs/DATA_CATALOG.md` and `content/sources.toml` with its licence line; no hard-coded coordinates (read `config/study_area.json`); the app reads only `data/processed/` and `content/`.
- Log every SI-assisted step in `submission/si_log.md`.

## How to work

- One dataset at a time, in the order given in `docs/DATA_COLLECTION.md`.
- For each dataset: write `prep/fetch_<dataset_id>.py`, run it, print a short check (row count, date range, missing values), append rows to `data/MANIFEST.csv`, then tell me what you got.
- Read study area and fields from `config/study_area.json`. Never hard-code coordinates.
- Before writing a fetcher, check the endpoint and parameter names against the official docs linked in the plan. If the docs differ from the plan, follow the docs and tell me.
- Ask before any single download larger than 2 GB, and before anything that runs longer than ~15 minutes.
- Be polite to servers: sleep between requests, retry with backoff, never run requests in parallel against the same service.
  Exception (2026-11-04): downloading finished AppEEARS results may run in parallel: 4 files at a time (8 drew repeated HTTP 429).
- Keep raw files exactly as downloaded under `data/raw/<dataset_id>/`. Never edit them in place.

## Credentials

- NASA Earthdata login lives in `~/.netrc` (or `earthaccess` persisted login) set up by me, not by you.
- Never print, log, copy or commit credentials. Never ask me to paste a password into the chat.
- `.netrc`, `data/raw/` and `*.zip` stay out of git (see `.gitignore`).

## Environment

- Python 3.11+, plain `requests` + `pandas` first. Optional: `earthaccess`, `rasterio`, `wetterdienst`, `phenodata`.
- Install into a local venv in this folder; record versions in `prep/requirements.txt`.
