# Crop Circles – Field Shift Kraichgau

NASA Space Apps Challenge 2026, challenge "Field Shift: Adapting Farms with NASA Data". The reed planthopper is a neighbourhood problem: its nymphs overwinter in winter wheat sown after sugar beet. The landscape planner finds those fields across the Kraichgau and ranks which ones should switch – and to what crop – so the most pressure is removed while soil and water stay safe. The field view shows how heat, drought, heavy rain and bare soil have hit one field and compares its rotation with three alternatives. Any parcel on the region map can be clicked for its role in the plan and its crops since 2017. Product: `crop-circles-data-prep/crop-circles-data-prep/docs/PRD.md`.

## The evidence: the flight distance was measured, not guessed

The planner weights every wheat-after-beet field ("nursery") by e^(−distance / r). Our sources give no number for *r*, so it could have been a dice roll. It is not:

- **Sample.** Every declared sugar-beet parcel in the Kraichgau bbox for 2023–2025 (FIONA declarations, 2,500–2,900 parcels a season; **3,476 parcel-seasons** with usable satellite data), with its boundary-to-boundary distance to the nearest nursery.
- **Measurement.** HLS S30 (Sentinel-2, NASA LP DAAC) NDVI, GNDVI and NDRE in two windows, June 1–25 and August 15 – September 10, read straight from the cloud-optimised GeoTIFFs (`prep/fetch_hls_region.py`, no AppEEARS queue, 35 minutes for three seasons). One value per parcel and season.
- **Test.** Beet within 50 m of a nursery loses more canopy from June to late summer than beet within 50 m of other wheat: **NDRE −0.029 (p < 0.001)**, the same sign in every index and every season, unchanged with soil (K·S, plant-available water), parcel size and distance to any field edge in the model; standard errors clustered by 2 km cell (`pipeline/planthopper_region.py`).
- **Distance.** Fitting the decline as e^(−distance / r) over every beet parcel, with *r* profiled from 50 m to 3 km, the likelihood peaks at **250–350 m** (best 350 m; 250 m with the generic edge effect in the model) and falls off clearly on both sides: 50–100 m and 1 km or more fit worse. The effect is gone by about 200 m. The planner's default moved from 1 km to **0.5 km** (slider 0.25 / 0.5 / 1 km) on that basis.
- **What it is not.** An exposure–symptom association, not a diagnosis: drought and Cercospora yellow beet too, sugar content was not measured, and the control parcels are still within the adults' reach (which biases the difference towards zero).

Full report with tables and figures: [`submission/planthopper_region_report.pdf`](submission/planthopper_region_report.pdf) (regenerate with `python submission/planthopper_region_report.py`). The same charts are on the *How we know* page of the app under *How it is worked out*.

## The crop planner: your own rotation, 2026–2030

At the bottom of *What to grow*, a farmer plans the coming years on their own block instead of only picking one of the ready-made rotations.

- **Shape the plots.** The map starts from the block's FIONA plots. *Cut* draws a line across plots, *Merge* joins touching plots (shift-click), *Undo* steps back. Geometry is worked out in metres (UTM 32N), so areas stay true; pieces under 0.05 ha are refused.
- **Paint crops.** Six crops (sugar beet, winter wheat, barley, maize, peas, potatoes), each with its family and its climate fit for this field (FAO EcoCrop, adapted to south Germany, from the field's own weather and soil). While a crop is picked, every plot shows how it fits the rotation: red breaks a rule (for example beet back within two years: beet cyst nematodes), light red is possible with a risk, green is a good fit. Hover for the reason. A plot's history is the crops declared on its area in every FIONA year, so it stays right after a cut.
- **Linked years.** One map per year, 2026–2030. Each year's plan is the history of the next, so plan the earlier year first.
- **Neighbours.** The parcels around the block are drawn faded and dashed (view only), with the planthopper's flight range (0.5 km). In 2026 last season's beet parcels show as likely nurseries; later years are grey until someone shares a plan.
- **Shared plans.** Each year's plan is saved to Supabase (`crop_plans`, created by `supabase_crop_plans.sql`). Other farmers' plans appear without names, as outlines and crops only, and replace the estimates in the planthopper pressure.
- **Your plan against the best match.** Both are scored the same way, over the same three years on the same plots, on six criteria weighted by the priority sliders: keeping the soil, water in dry months, nitrogen, the planthopper, steady income and the rotation rules. A plot left unpainted in the first year counts as green fallow; an unpainted later year is filled in from the best match and marked *auto*. The page warns when land is unpainted and when fallow alone makes a plan look better than it is.

Code: `app/planner.py` (the page section), `app/plot_editor/` (the editable map), `app/rotation.py` (rotation rules), `app/ecocrop.py` (climate fit), `app/neighbours.py` (the parcels around the block), `app/plans_store.py` (saved plans), `app/plan_metrics.py` (the comparison).

## Run

Python 3.11+. The venv in `crop-circles-data-prep/crop-circles-data-prep/.venv` has everything; for a new one:

```
pip install -r crop-circles-data-prep/crop-circles-data-prep/prep/requirements.txt -r pipeline/requirements.txt -r requirements.txt
```

From the repo root:

```
streamlit run app/app.py          # the app (reads only data/processed/ and content/)
python -m pipeline                # rebuild data/processed/ from data/raw/ (~5 min, raw data is local only)
python submission/planthopper_region_report.py   # the evidence report (PDF) from data/processed/
python -m pipeline.landscape --bw # Our region for all of Baden-Württemberg (needs the --bw downloads below)
python -m pipeline.landscape_geo  # just the parcel outlines for Our region (when only the FIONA export changed)
python app/smoke_test.py          # every page renders for F1–F3, in English and German
python app/check_i18n.py          # every key used in code exists; translations keep the placeholders
```

All AppEEARS downloads (MODIS NDVI, SMAP, HLS for F1–F3), FIONA 2022–2025 for the whole bbox (`prep/fetch_fiona.py <year>`; the planner uses the declarations for 2023–2025 and the Thünen map before), the region-wide HLS parcel indices (`prep/fetch_hls_region.py`) and the DLR CropTypes maps (`prep/fetch_dlr_croptypes.py`) are in as of 2026-11-15. ECOSTRESS surface temperature and evaporative stress at the field centres (`prep/fetch_ecostress.py`, one AppEEARS point request) feeds the "seen from space" block on *My field*; without the download the block is simply left out. After a new download, run `python -m pipeline` again: the bare-soil, soil-moisture, summer-green and from-space sections pick it up.

*Our region* also covers all of Baden-Württemberg (switch at the top of the page). Its raw data comes from the same fetchers run with `--bw` (`fetch_fiona.py`, `fetch_bk50.py`, `fetch_thuenen_ctm.py`, `fetch_dlr_croptypes.py`, `fetch_dem.py`; about 4 GB, 1–2 hours) and is turned into the `landscape_*_bw` files by `python -m pipeline.landscape --bw`.

## Languages

English and German. The language comes from `?lang=de`, else the browser, else English; the picker sits top right. UI text lives in `app/locales/<tag>.toml` (BCP 47 tags, dotted keys, `{named}` placeholders, CLDR plural forms as `.one`/`.other`); content text in `content/*.toml` (English) with overlays in `content/<tag>/` that replace only the fields they name. Numbers, percentages, months and chart axes are formatted by Babel and Vega for the active locale.

To add a language, e.g. French:

1. Copy `app/locales/en.toml` to `app/locales/fr.toml` and translate the values (keep the keys and `{placeholders}`).
2. Optionally copy the text fields of `content/*.toml` into `content/fr/` and translate them; anything missing falls back to English.
3. Run `python app/check_i18n.py` and `python app/smoke_test.py`, and take new screenshots for `app/assets/screens/fr/` (the landing page uses the English ones until then).

The picker and the smoke test find the new file on their own.

## Layout

| folder | what |
|---|---|
| `crop-circles-data-prep/crop-circles-data-prep/` | raw data, fetch scripts, docs; `data/processed/` = app-ready files (committed, ~7 MB) |
| `pipeline/` | `geo.py` soil, slope, crop maps, map layers · `phenology.py` crop calendar · `climate.py` weather, indicators, scenarios, soil moisture, NDVI · `strategies.py` rotation model and scores · `landscape.py` crop sequence of every parcel, nurseries · `pressure.py` the pressure maths (shared with the app) · `hls.py` HLS 30 m: what grows on each parcel this season, bare-soil months, NDVI / GNDVI / NDRE · `croptype.py` the probability model behind it (tested year by year against FIONA and Thünen) · `planthopper_region.py` the region-wide edge test and the flight-distance fit · `planthopper_edge_effect.py` the earlier demo-block version (preliminary) |
| `content/` | strategy cards and rule scores, crop calendars and model parameters, indicator texts, risk-card texts (`plain.toml`), glossary, sources (TOML – edit without touching code) |
| `app/` | Streamlit app for farmers first (PRD §3): `app.py` (theme, navigation), `i18n.py` (language, numbers, dates), `locales/` UI text per language, `data.py` (loaders, planner, ranking), `plain.py` (numbers into words), `views/` landing page, My field, What to grow, Our region, Neighbours, How we know; `planner.py`, `plot_editor/`, `rotation.py`, `ecocrop.py`, `neighbours.py`, `plans_store.py`, `plan_metrics.py` the crop planner; `accounts.py` sign-in and the feed (Supabase); `assets/screens/` landing-page screenshots |
| `submission/` | SI-use log, demo material, the evidence report (`planthopper_region_report.pdf` and its script) |
