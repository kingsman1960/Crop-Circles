# Data checks

Short check summary per dataset (written by the fetch run on 2026-11-04). Raw files: `data/raw/<dataset_id>/`, all logged in `MANIFEST.csv`.

## 1 · fields (done)

- OSM Overpass snapshot 2026-11-04T11:12Z, `landuse=farmland` in the bbox: 13,464 polygons (13,227 ways, 237 relations), 0 dropped. Median area 1.75 ha.
- Picked (closest ≥ 20 ha polygon to each placeholder, so at least ~7 MODIS 250 m pixel centres fall inside):

| id | OSM | area | centroid |
|---|---|---|---|
| F1 Eppingen | way/961878376 | 41.5 ha | 49.144319, 8.918983 |
| F2 Bad Rappenau | relation/2625534 | 29.5 ha | 49.245287, 9.120219 |
| F3 Schwaigern | way/152148766 | 41.9 ha | 49.133532, 9.060868 |

- Caveat: OSM farmland polygons are often blocks of several parcels; check against imagery. Change with `prep/fetch_fields.py --pick` and re-run the field-based fetchers.

## 2 · nasa_power (done)

- POWER Daily API v2.10.2, community AG, LST. 3 files, each 16,740 rows, 1981-01-01 → 2026-10-31, no missing days.
- `-999`: only `ALLSKY_SFC_SW_DWN` (1,096 = 1981–1983 before CERES, plus 2026-10-31). All other columns 0.
- F1 and F3 are in the same MERRA-2 cell (0.5° × 0.625°): identical values. `ALLSKY_SFC_SW_DWN` is identical for all three (CERES 1° cell).

## 3 · dwd_climate (done)

- Rule: per field the 3 nearest active stations with ≥ 20 years of record, plus every station within 10 km of a field. 7 stations, 18 MB.
- Missing-value code `-999`. Overlap with POWER shown as first → last date.

| station | name | record | TMK/TXK/TNK -999 | RSK -999 | gaps > 30 d |
|---|---|---|---|---|---|
| 01254 | Eppingen (closed) | 1947-07 → 2002-11 | 3 | 0 | 2002-03 (31 d) |
| 01255 | Eppingen-Elsenz | 2002-12 → 2026-11-03 | 0 | 3 | **2019-01 → 2021-06 (912 d, no rows)** |
| 03362 | Mühlacker | 1998 → 2026-11-03 | 177–216 | 145 | RSK 2002-08 (31 d) |
| 03734 | Obersulm-Willsbach | 2004-07 → 2026-11-03 | 4 | 3 | none |
| 03761 | Öhringen | 1947 → 2026-11-03 | 0 (TXK/TNK 120) | 0 | none |
| 04349 | Sachsenheim | 1987-11 → 2026-11-03 | 0 | 0 | none |
| 15547 | Heilbronn/Neckar | 2016-10 → 2026-11-03 | all | all | no T/precip at all (not usable) |

- 01254 + 01255 together give Eppingen (1.5 / 5.7 km from F1) from 1947, except the 2019–2021 hole.
- Recent files (`_akt`) are not fully quality-controlled; historical wins where both overlap.

## 4 · dwd_phenology (done)

- Germany-wide files kept as downloaded (≈ 512 MB, mostly the 1925–2024 historical files; the plan's "< 50 MB" estimate was low).
- 152 phenology stations within 40 km of Heilbronn, 129 with data for our crops (`stations_selected.csv`).
- **Soybean: not in the DWD crop programme** (no file).
- Station-years since 2001 within 40 km (annual reporters = historical + recent; immediate reporters only from 2024):

| crop | sowing (10) | emergence (12) | harvest (24) | annual last year |
|---|---|---|---|---|
| winter wheat | 461 | 445 | 493 | 2026 |
| winter barley | 399 | 405 | 469 | 2026 |
| sugar beet | 355 (+19 "Rübe/Zucker-Rübe" 2021–26) | 362 | 371 | 2026 |
| maize | 444 | 477 | 455 | 2026 |
| winter rapeseed | 345 | 342 | 402 | 2026 |

- Immediate reporters 2024–2026: 11–18 station-years per phase (5–6 stations); beet only sowing/emergence/closed stand, no harvest.
- All other phases are kept too (see the script output, e.g. heading, yellow ripeness, flowering).

## 5 · modis_ndvi (done)

- MOD13Q1.061 + MYD13Q1.061 via AppEEARS point sample, 7 pixels per field (pixel centre inside the polygon) → `F{n}_MOD13Q1.csv`, `F{n}_MYD13Q1.csv`. AppEEARS restarted the task once on 4 Nov; done 5 Nov 08:29 CET.
- Terra: 595 composites, 2000-12-18 → 2026-10-16 (the first composite starts before 2001-01-01). Aqua: 559 composites, 2002-07-04 → 2026-10-08. 23 per full year for both.
- No fill or NaN in `ndvi`; values −0.09 … 0.98 (AppEEARS applies the 0.0001 scale). Median of good-quality values 0.51–0.56.
- `reliability` per field and product: 0 good 63–75 %, 1 marginal 17–25 %, 2 snow/ice 2–3 %, 3 cloudy 6–14 %.

## 6 · soilgrids (done)

- 3 JSON files, 7 properties × 4 depths × (mean, Q0.05, Q0.95), no nulls. Values are integers in mapped units (divide by `d_factor` given in each layer, e.g. clay g/kg ÷ 10 → %).
- All three are silt-dominated (silt ~55–60 %, clay ~27–34 %), as expected for Kraichgau loess.

## 7 · dem (done)

- NASADEM_NC.001 `NASADEM_HGT` via AppEEARS area request → `dem_bbox.tif` (copy of the AppEEARS GeoTIFF).
- EPSG:4326, 1″ × 1″ (~30 m), 2161 × 1441 px, int16, nodata −32768; bounds 8.79986–9.40014 E, 48.94986–49.35014 N → bbox fully covered; 0 nodata pixels; 120–523 m.

## 8 · gpm_imerg (done)

- GPM_3IMERGDF.07 via the Giovanni in the Cloud time-series API (point = the 0.1° cell containing the centroid).
- 3 files, each 9,039 rows, 2001-01-01 → **2025-09-30** (latest Final daily granule in CMR; Final run lags ~1 year now), no missing days, 0 `undef` (-9999.9), unit mm/day.
- Cell centres: F1 49.15/8.95, F2 49.25/9.15, F3 49.15/9.05 (three different cells).
- The API returned HTTP 500 for ~1 h earlier on 2026-11-04 and then recovered; the Hydrology Data Rods service is discontinued.

## 9 · smap (done)

- SPL3SMP_E.006 via AppEEARS point sample at the three centroids → `F{n}.csv`, each 4,149 days, 2015-03-31 → 2026-11-03, no missing dates.
- Three different 9 km cells (no identical values between fields; r = 0.95–0.97).
- Valid (≠ −9999): AM 59–60 %, PM 59 % per field, the same share every year (57–62 %); the rest are days without a retrieval (no overpass or retrieval skipped, `qual` 7). sm 0.02–0.45 m³/m³.
- `qual` 0 (recommended) on most valid days; F2 has many more `qual` 1 days (~740 vs ~80) – use `qual = 0` when comparing fields.

## 10 · hls_ndvi (done)

- 9 AppEEARS area tasks (3 fields × 2019–2021 / 2022–2023 / 2024–now), 12,399 files, 60 MB, all logged in MANIFEST. Each task also holds Fmask lookup tables, QA statistics, the request JSON and a README.
- Per field: L30 441–442 scenes, S30 843 (F1) / 966 (F2, F3) scenes; each with red, NIR and Fmask. 2019-01-02 → 2026-11-01 (doy 2026305).
- L30 ~33 scenes/year 2019–2021, ~70/year from 2022 (Landsat 9). S30 100–140/year.
- EPSG:32632, 30 m, boxes 34–47 × 34–39 px, nodata −9999. Scenes are not cloud-filtered: most need masking with Fmask.
- Download note: the AppEEARS token was rejected once mid-download (HTTP 403); re-runs resume (files with the bundle's size are skipped, tasks in MANIFEST are skipped). Downloads ran 4 files at a time (8 drew HTTP 429).

## 12 · fiona (done)

- 114,345 parcels in the bbox (= server count), 6 pages, unique `object_id`s, all `Antragsjahr` 2022 (the only year the WFS serves). EPSG:25832.
- Most common: vineyards 33,150, meadows 21,359, winter wheat 10,668, spring barley 5,057, grain maize 3,080, sugar beet 3,034, winter barley 2,889.
- **The OSM demo "fields" are blocks of several parcels**: F1 holds 17 parcels (sugar beet ×6, winter wheat ×3, …), F2 12, F3 11 (mixed crops). Decision 2026-11-04: keep F1–F3 as they are (re-fetching everything costs too much); treat field-level signals as block averages.

## 13 · bk50 (done)

- `geola_bod_ke` (soil units with geometry): 14,085 polygons in 5 pages (= server count), 503 soil units, EPSG:25832.
- Thematic attribute tables (14,085 rows each, 0 units with conflicting values → join by `Kartiereinheit` is safe):
  - with values: K factor `kfa-Wert` (erodibility classes), `nfk-Wert`, `LK`, `KF`, `Grund/Stauwasser`.
  - **without values in the WFS** (only unit, legend text, PDF link): `fk`, `kak`, `natbod`, `akiwas_ln`, `gesbew_ln`. The class values exist only in the WMS styling / the per-unit PDFs.
- `readme_dBK50.pdf` kept (licence §8.1).

## 14 · thuenen_ctm (done)

- 10 clipped rasters: v202 2017–2024, v302 2024 and 2025 (preliminary, "2025_08"). Each EPSG:3035, 10 m, 4431 × 4501 px, int32, nodata −9999 (~41 % of the bbox: forest, settlements).
- 24 classes present each year; legend (`*.clr`, EN/DE) includes winter wheat 1101, winter barley 1102, maize 1300, sugar beet 1402, winter rapeseed 1501, **soy 1614**, peas 1611, fallow 3003.
- 2024 v202 vs v302: same class totals, not pixel-identical.

## 15 · esa_cci_sm (done, auxiliary)

- COMBINED v09.2 via CEDA OPeNDAP. Decision 2026-11-04: recent years only, 2020-01-01 → 2024-12-31 (1978–2019 skipped; SMAP covers 2015 →).
- `cci_sm_combined_v09.2_daily.csv`: 3,654 rows = 1,827 days × 2 cells, no missing days, no duplicates. Fill `-9999.0`, unit m³/m³.
  - 49.125 N 8.875 E (F1): 1,759 valid (96 %), sm 0.19–0.38; invalid days are flag 9 (56) / 13 (12). `flag` is a bit field (meanings in the file's `flag_meanings`); 9 and 13 both include bit 1 = snow cover or temperature below zero.
  - 49.125 N 9.125 E (F2, F3): 1,730 valid (95 %), sm 0.21–0.35; flags 9 (80), 13 (16), 64 (3), 1 (1).

## 16 · c3s_sm (done, auxiliary)

- CDS `satellite-soil-moisture`, COMBINED daily icdr: 3 zips (2025 v202505 675 MB, 2026-01→08 v202505 417 MB, 2026-09→10 v202505_2 90 MB), one global NetCDF per day.
- `c3s_sm_combined_daily.csv`: 1,296 rows = 648 days × 2 cells, 2025-01-01 → **2026-10-10**, no missing days, no duplicates.
  - 49.125 N 8.875 E: 626 valid (97 %); 49.125 N 9.125 E: 606 valid (94 %). Flags as in CCI (9, 13, 1).
- CDS notice applied: v202505 has many gaps on 1–20 Sep 2026 → September/October taken from v202505_2.
- Version step CCI v09.2 → C3S v202505 cannot be checked yet (no overlap year). Mean sm: CCI 2024 0.303 / 0.289, C3S 2025 0.275 / 0.278 – different years, not a version comparison. If needed, fetch C3S 2024 (~650 MB) for an overlap check.

## 11 · reference (done)

- `reference/sources.md`: links for all four topics. The 2026 Project Submission Guide is not out yet (FAQ: 13 Nov 2026), listed under "Not found / to check".
