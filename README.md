# Crop Circles – Field Shift Kraichgau

NASA Space Apps Challenge 2026, challenge "Field Shift: Adapting Farms with NASA Data". The reed planthopper is a neighbourhood problem: its nymphs overwinter in winter wheat sown after sugar beet. The landscape planner finds those fields across the Kraichgau and ranks which ones should switch – and to what crop – so the most pressure is removed while soil and water stay safe. The field view shows how heat, drought, heavy rain and bare soil have hit one field and compares its rotation with three alternatives. Any parcel on the region map can be clicked for its role in the plan and its crops since 2017. Product: `crop-circles-data-prep/crop-circles-data-prep/docs/PRD.md`.

## Run

Python 3.11+. The venv in `crop-circles-data-prep/crop-circles-data-prep/.venv` has everything; for a new one:

```
pip install -r crop-circles-data-prep/crop-circles-data-prep/prep/requirements.txt -r pipeline/requirements.txt -r requirements.txt
```

From the repo root:

```
streamlit run app/app.py          # the app (reads only data/processed/ and content/)
python -m pipeline                # rebuild data/processed/ from data/raw/ (~2-3 min, raw data is local only)
python -m pipeline.landscape --bw # Our region for all of Baden-Württemberg (needs the --bw downloads below)
python -m pipeline.landscape_geo  # just the parcel outlines for Our region (when only the FIONA export changed)
python app/smoke_test.py          # every page renders for F1–F3, in English and German
python app/check_i18n.py          # every key used in code exists; translations keep the placeholders
```

All AppEEARS downloads (MODIS NDVI, SMAP, HLS for F1–F3), FIONA 2023–2025 around the demo fields (`prep/fetch_fiona_wms.py`) and the DLR CropTypes maps (`prep/fetch_dlr_croptypes.py`) are in as of 2026-11-05. ECOSTRESS surface temperature and evaporative stress at the field centres (`prep/fetch_ecostress.py`, one AppEEARS point request) feeds the "seen from space" block on *My field*; without the download the block is simply left out. After a new download, run `python -m pipeline` again: the bare-soil, soil-moisture, summer-green and from-space sections pick it up.

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
| `pipeline/` | `geo.py` soil, slope, crop maps, map layers · `phenology.py` crop calendar · `climate.py` weather, indicators, scenarios, soil moisture, NDVI · `strategies.py` rotation model and scores · `landscape.py` crop sequence of every parcel, nurseries · `pressure.py` the pressure maths (shared with the app) · `hls.py` HLS 30 m: what grows on each parcel this season and bare-soil months · `croptype.py` the probability model behind it (tested year by year against FIONA and Thünen) |
| `content/` | strategy cards and rule scores, crop calendars and model parameters, indicator texts, risk-card texts (`plain.toml`), glossary, sources (TOML – edit without touching code) |
| `app/` | Streamlit app for farmers first (PRD §3): `app.py` (theme, navigation), `i18n.py` (language, numbers, dates), `locales/` UI text per language, `data.py` (loaders, planner, ranking), `plain.py` (numbers into words), `views/` landing page, My field, What to grow, Our region, How we know; `assets/screens/` landing-page screenshots |
| `submission/` | SI-use log, demo material |
