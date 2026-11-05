# Plan – Crop Circles, NASA Space Apps 2026

Draft 2026-11-04. Product scope: `docs/PRD.md`. Team process: `docs/WORKFLOW.md`. Data: `docs/DATA_CATALOG.md`.

## 1. Phases

| phase | dates | goal | exit criterion |
|---|---|---|---|
| A · Data | now → Fri 13 Nov | all raw data in place, checked, catalogued | datasets 5, 9, 10, 16 downloaded and in `CHECKS.md`; catalog complete |
| B · Rules & resources | Fri 13 Nov | read Project Submission + Judging guides and challenge resources | PRD §12/§13 and this plan updated; new datasets (if any) queued |
| C · Build day 1 | Sat 14 Nov, H0–H24 | processed data + P0 app end to end | F1 page with real indicators and S0–S3 cards on `main` |
| D · Build day 2 | Sun 15 Nov, H24–H48 | P1 polish, content, demo, submission | submitted, tagged `submission` |

Phase A open items
- [x] SMAP (2015-03-31 → 2026-11-03) and HLS (12,399 files, 2019 → 2026-11-01) downloaded and checked.
- [x] MODIS NDVI (Terra 2000-12-18 → 2026-10-16, Aqua 2002-07-04 → 2026-10-08) downloaded and checked on 5 Nov.
- [x] C3S soil moisture 2025-01-01 → 2026-10-10 downloaded (2024/2025 version step not checkable without an overlap year).
- [ ] Re-check FIONA for a newer `Antragsjahr` on 13 Nov (only 2022 today).
- [ ] Team: names for the four roles, laptops with the venv working (`prep/requirements.txt`).

## 2. Architecture

```
data/raw/ (≈1.5 GB, local only)
   │  pipeline/  (Python: pandas, rasterio, pyproj; run once, minutes)
   ▼
data/processed/ (< 100 MB, committed; one file per output, all fields inside, column `field`)
   fields.geojson                  F1–F3 polygons + profile attributes (soil, slope, K, nFK, FIONA crops)
   parcels.geojson                 FIONA 2022 parcels inside the blocks
   daily.parquet                   merged daily weather (POWER, IMERG, DWD nearest) + ET0
   indicators.parquet              yearly indicators (§7 of the PRD) per source
   scenarios.parquet               indicator means for +0/1/2 °C × 100/90/80 % spring rain
   phenology.parquet               DWD regional median phase dates per crop and year
   ndvi.parquet                    MODIS NDVI per date (when AppEEARS is done)
   soilmoisture.parquet            POWER GWET, CCI + C3S, SMAP (when done) with anomalies
   crops.parquet, crop_transitions.parquet   Thünen class shares per year; what followed beet
   layers/*.png + *.json           map overlays (K factor × slope, crop map 2024) with bounds
   strategies.json                 S0–S4 per-field scores, field facts, monthly bare-soil calendar
   landscape_parcels.parquet       every FIONA parcel that was beet or a nursery: position, K·S, nFK, crop per year 2017–2025
   landscape_seasons.parquet       per season: nursery ha (beet in y-1 -> winter wheat in y) and beet ha per parcel
   landscape_summary.json          regional numbers per season, targeted vs. random switching
content/*.toml                     strategy cards + rule scores, crop calendars, indicators, glossary, sources
   │
   ▼
app/ (Streamlit)
   Home (map, field picker) → Field page (profile, timeline, bare-soil calendar)
   → Strategies (cards, priority sliders, score table) → Sources
```

Choices
- Streamlit: fastest path, the team already used it (GeoAX). Maps: folium (`streamlit-folium`) or pydeck.
- Parquet for tables, GeoJSON for vectors, pre-rendered PNG overlays for rasters (no tile server).
- Scores are computed in the pipeline, not in the app, so the app stays thin and fast.
- Deployment: Streamlit Community Cloud (free) or a single container; decide at H0.

## 3. Work breakdown (hackathon)

Estimates in focused hours. P0 first; P1 only after the H12 demo works.

| # | task | owner | est. | prio | depends |
|---|---|---|---|---|---|
| 1 | Update CLAUDE.md, repo skeleton, run command, deploy "hello" app | App | 1 | P0 | – |
| 2 | `fields.geojson` with profile: BK50 join (K, nFK, KF), SoilGrids, DEM slope stats | Data | 3 | P0 | – |
| 3 | `daily_<field>`: POWER + IMERG + nearest DWD, unified columns, gap flags | Data | 3 | P0 | – |
| 4 | Indicators: heat, frost, dry spell, heavy rain, water balance (yearly + seasonal) | Data | 4 | P0 | 3 |
| 5 | NDVI series + bare-soil periods (MODIS; HLS if ready) | Data | 4 | P0 | – |
| 6 | Crop history per block from Thünen 2017–2025 (+ FIONA 2022) | Data | 2 | P0 | – |
| 7 | Soil-moisture series + anomaly (SMAP, CCI, C3S) | Data | 2 | P1 | – |
| 8 | Strategy definitions S0–S4 with sources; scoring rules per criterion | Agronomy | 4 | P0 | 4, 5 |
| 9 | Card texts (why / evidence / benefits / gaps / risks) per field | Agronomy | 3 | P0 | 8 |
| 10 | App: home map + field picker | App | 2 | P0 | 1, 2 |
| 11 | App: field page (tiles, timeline charts, bare-soil calendar) | App | 5 | P0 | 4, 5, 6 |
| 12 | App: strategies page (cards, sliders, score table) | App | 4 | P0 | 8, 9 |
| 13 | Sources & attribution page from the catalog | App | 1 | P0 | – |
| 14 | Erosion map layer (K × slope × bare months) | Data + App | 3 | P1 | 2, 5 |
| 15 | Scenario slider (+°C, −rain) | Data + App | 3 | P1 | 4 |
| 16 | Satellite vs station comparison chart | App | 1 | P1 | 3 |
| 17 | DE / EN toggle | App | 2 | P1 | 12 |
| 18 | SI explanations (LLM over computed facts, cited) | App | 3 | P2 | 9 |
| 19 | Demo script, video, slides, SI-use log | Pitch | 5 | P0 | 11, 12 |
| 20 | Submission form, final checks | Pitch | 2 | P0 | 19 |

P0 total ≈ 45 focused hours → fits a team of 3–4 in 48 h with buffer; P1 ≈ 12 h.

## 4. Day plan

| block | Data lead | App lead | Agronomy lead | Pitch lead |
|---|---|---|---|---|
| H0–H2 | 2 | 1, 10 | 8 (draft list) | guides, judging criteria |
| H2–H8 | 3, 4 | 10, 13 | 8 thresholds + sources | story + demo outline |
| H8–H12 | 5, 6 | 11 (dummy data) | 9 for F1 | screenshots plan |
| H12 | **end-to-end demo with real F1 data** | | | |
| H12–H24 | 7, 14 | 11, 12 | 9 for F2, F3 | script draft |
| H24–H36 | 15, fixes | 16, 17 | content freeze (H36) | 19 |
| H36–H44 | fixes | fixes, deploy | proofreading | video, 20 |
| H44–H48 | buffer | buffer | buffer | submit |

## 5. Cut list (in this order if time runs out)

1. P2 items (SI chat, PDF export, any-parcel click).
2. DE / EN toggle → English only.
3. Scenario slider.
4. HLS → MODIS only for NDVI.
5. Strategy S4 → keep S0–S3 (challenge needs ≥ 3 incl. existing).
6. F2, F3 → demo on F1 only, others "coming soon".

## 6. Risks

| risk | likelihood | impact | response |
|---|---|---|---|
| AppEEARS tasks (MODIS / SMAP / HLS) still not done by 13 Nov | low–med | high (NDVI) | MODIS via ORNL subset service fallback; Thünen for crop cover |
| Indicator thresholds disputed | med | med | cite source per threshold, label "screening" |
| Parcel-block mixing confuses users | med | med | show block composition (Thünen / FIONA) on the field page |
| Deployment issues at the end | med | high | deploy "hello" app at H1, redeploy after every merge |
| Scope creep | high | high | P0 freeze at H0, cut list above |
| Judging criteria favour something we lack | med | med | read guide on 13 Nov, adjust PRD before kickoff |

## 7. Open decisions (before or at kickoff)

- 2026-11-04: product core changed to the landscape planner (PRD §1, §6 item 0); `pipeline/landscape.py`, `pipeline/pressure.py`, `app/views/landscape.py`. UI restyled to one ink chrome with a single data hue.
- 2026-11-04: build started early (decision of the team lead); P0 pages and P1 erosion map, scenario slider and satellite-vs-ground chart exist. Check the Space Apps Participant Terms on whether pre-event code must be declared.
- Team members and roles – the plan must also work for a single person: kickoff work then shrinks to MODIS/SMAP refresh, review of `content/` texts and thresholds, demo and submission.
- Hosting target (Streamlit Community Cloud vs container).
- Whether to include the SI chat at all (P2) – depends on judging guide.
- Final app name.
