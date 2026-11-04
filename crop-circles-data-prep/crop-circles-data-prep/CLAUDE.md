# Crop Circles – data prep (NASA Space Apps 2026, Field Shift)

This folder collects the raw data our team will use during the hackathon.
The full task list is in @docs/DATA_COLLECTION.md – read it before doing anything.

## Scope rule (important)

Space Apps asks teams to start building their project when the hackathon begins.
Before our local event starts (Sat 14 Nov 2026), this folder is for **data acquisition only**:

- OK: download scripts in `prep/`, downloading, unzipping, checking that files are complete, writing `data/MANIFEST.csv`.
- NOT OK before the event: analysis, indicators, models, scoring logic, plots for the app, any web app code.
- If a task looks like analysis ("compute heat days", "make an NDVI curve"), stop and ask.

## How to work

- One dataset at a time, in the order given in `docs/DATA_COLLECTION.md`.
- For each dataset: write `prep/fetch_<dataset_id>.py`, run it, print a short check (row count, date range, missing values), append rows to `data/MANIFEST.csv`, then tell me what you got.
- Read study area and fields from `config/study_area.json`. Never hard-code coordinates.
- Before writing a fetcher, check the endpoint and parameter names against the official docs linked in the plan. If the docs differ from the plan, follow the docs and tell me.
- Ask before any single download larger than 2 GB, and before anything that runs longer than ~15 minutes.
- Be polite to servers: sleep between requests, retry with backoff, never run requests in parallel against the same service.
- Keep raw files exactly as downloaded under `data/raw/<dataset_id>/`. Never edit them in place.

## Credentials

- NASA Earthdata login lives in `~/.netrc` (or `earthaccess` persisted login) set up by me, not by you.
- Never print, log, copy or commit credentials. Never ask me to paste a password into the chat.
- `.netrc`, `data/raw/` and `*.zip` stay out of git (see `.gitignore`).

## Environment

- Python 3.11+, plain `requests` + `pandas` first. Optional: `earthaccess`, `rasterio`, `wetterdienst`, `phenodata`.
- Install into a local venv in this folder; record versions in `prep/requirements.txt`.
