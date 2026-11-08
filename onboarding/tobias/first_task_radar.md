# Possible first task: radar for the winter gap

This is a proposal, not an assignment. We picked it because it fills a real gap and matches your background.

## Why

- The bare-soil calendar and the winter-cover check on *My field* rely on optical imagery (HLS, 30 m). In November and December most parcels get only one to three clear pictures. Those are exactly the months the planthopper story depends on: wheat sown after beet, cover crops, bare soil.
- The status of the current season (which of last year's beet parcels became nurseries in 2026) rests on how green a parcel looks in late winter and April. No crop map confirms it yet.
- Radar sees through clouds.

## Candidate data

Both are NASA products, free through the ASF DAAC with an Earthdata login (ASF Vertex, `asf_search` or `earthaccess`).

| | OPERA RTC-S1 | NISAR GCOV |
|---|---|---|
| what | Sentinel-1 backscatter (C-band), terrain-corrected, 30 m | L-band polarimetric covariance, geocoded |
| coverage | near-global, from October 2023 | calibrated data from 17 June 2026; the backlog from September 2025 is being released through the end of 2026 |
| winters we could use | 2023/24, 2024/25, 2025/26, the current one | the current one; 2025/26 only once the backlog is out |

OPERA is probably the practical choice for the 48 hours. NISAR is the more interesting story, if enough data exists for our area.

## Questions to answer first (before the 14th, if you have time)

1. How many acquisitions per month cover the study area (bbox in `config/study_area.json`)?
2. On a handful of parcels around F1 (outlines in `data/processed/parcels.geojson`), does VV/VH separate bare soil, winter cereal and a cover crop? A quick notebook plot is enough.
3. Is it worth building in 48 hours? An honest "we checked, and here is what radar adds" is also a good outcome.

## What "done" could look like

1. `prep/fetch_<name>.py` downloads the data for the bbox into `data/raw/` (git-ignored). Use an existing fetch script as the pattern. New packages go in `prep/requirements.txt`.
2. A pipeline step writes one small file to `data/processed/`, one row per parcel and date with a `field` column, and prints a short check (rows, date range, missing values).
3. One block in the bare-soil tab of *My field* (`app/views/field.py`). For example: "radar shows bare soil in December where optical had no clear picture". Its text goes in `app/locales/en.toml` and `de.toml`.
4. The dataset and its licence go in `content/sources.toml`, which feeds the *How we know* page.
5. `python app/smoke_test.py` passes.
