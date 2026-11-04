# Data collection plan – Crop Circles (Field Shift)

Goal: before the hackathon, have every dataset we need sitting in `data/raw/`, checked and logged, so the 48 hours go into analysis and the app.

Study area: arable land around Heilbronn and the Kraichgau (Baden-Württemberg, Germany).
Typical rotation there: sugar beet → winter wheat → winter barley (+ cover crop). Alternatives we will compare: maize or soybean after sugar beet, and cover crops on bare fields.

## 0. Setup (do first)

1. Create the folder layout:

```
config/study_area.json      # bbox + demo fields (I fill the real field coordinates)
prep/                       # fetch scripts only, one per dataset
prep/requirements.txt
data/raw/<dataset_id>/      # untouched downloads
data/MANIFEST.csv           # one row per downloaded file
reference/sources.md        # links + notes for crop traits and rotation advice
.gitignore                  # .netrc, data/raw/, *.zip, .venv/
```

2. `data/MANIFEST.csv` header:

```
file_path,dataset_id,source,product_version,query_or_url,spatial,temporal,downloaded_at_utc,size_bytes,sha256,license,attribution
```

3. Accounts: NASA Earthdata (I set up `~/.netrc` / `earthaccess` login myself). NASA POWER, DWD, SoilGrids and OSM need no account.

## 1. Order of work

| # | dataset_id | Priority | What | Rough size |
|---|---|---|---|---|
| 1 | fields | required | Pick 3 demo arable fields, write them into the config | tiny |
| 2 | nasa_power | required | Daily climate per field, 1981 → now | < 5 MB |
| 3 | dwd_climate | required | Daily station climate near the fields | < 50 MB |
| 4 | dwd_phenology | required | Sowing / emergence / harvest dates of field crops | < 50 MB |
| 5 | modis_ndvi | required | 250 m NDVI time series per field, 2001 → now | < 20 MB |
| 6 | soilgrids | recommended | Soil texture, organic carbon, pH per field | tiny |
| 7 | dem | recommended | 30 m elevation for the bbox (slope → erosion) | < 100 MB |
| 8 | gpm_imerg | recommended | Daily precipitation per field, 2001 → now | < 20 MB |
| 9 | smap | recommended | Soil moisture per field, 2015 → now | < 20 MB |
| 10 | hls_ndvi | recommended | 30 m NDVI around each field, 2019 → now | can be GBs – ask first |
| 11 | reference | required | Source list for crop traits and rotation advice | text only |

Stop after each dataset and report: files, row counts, date range, missing values.

## 2. Dataset tasks

### 1 · fields (required)

- Start from `config/study_area.json`. The three fields there are town-centre placeholders; they must be moved onto real arable fields.
- Help me choose: query OpenStreetMap (Overpass API) for `landuse=farmland` polygons inside the bbox, save as `data/raw/fields/osm_farmland.geojson`, and list a few candidate polygons near each placeholder with area in ha.
- I pick the final fields; you then write their centroid `lat`/`lon` and polygon into the config.
- Attribution: "© OpenStreetMap contributors", ODbL.

### 2 · nasa_power (required)

- Docs: https://power.larc.nasa.gov/docs/ (parameter dictionary: https://power.larc.nasa.gov/docs/tutorials/parameters/)
- Endpoint (verify in docs): `GET https://power.larc.nasa.gov/api/temporal/daily/point`
- Query per field: `community=AG`, `latitude`, `longitude`, `start=19810101`, `end=<last full month>`, `format=CSV`
- Parameters: `T2M, T2M_MAX, T2M_MIN, PRECTOTCORR, RH2M, WS2M, ALLSKY_SFC_SW_DWN, GWETTOP, GWETROOT`
  (check each name exists in the AG community; drop and report any that don't)
- `-999` means missing. Solar parameters start later than temperature – that's expected.
- Output: `data/raw/nasa_power/<field_id>_daily.csv` (+ keep the raw response header).
- Check: first/last date, number of days, count of `-999` per column.
- Attribution: copy the acknowledgement text from the POWER website into MANIFEST.

### 3 · dwd_climate (required)

- Source: https://opendata.dwd.de/climate_environment/CDC/observations_germany/climate/daily/kl/ (`historical/` and `recent/`).
- Steps: download the station description file, find the 3 stations nearest to each field that are still active and have long records, download their zip files, extract the `produkt_klima_tag_*` files.
- Variables we need: daily mean / max / min temperature and precipitation (check the column codes in the dataset description PDF in the same folder).
- `wetterdienst` may be used instead of manual download if it is simpler.
- Output: `data/raw/dwd_climate/<station_id>/…` plus `data/raw/dwd_climate/stations_selected.csv` (id, name, lat, lon, height, distance to each field, record start/end).
- Check: overlap period with NASA POWER, missing-value code, gaps longer than 30 days.
- Attribution: as required by DWD (check the licence note on opendata.dwd.de).

### 4 · dwd_phenology (required)

- Source: https://opendata.dwd.de/climate_environment/CDC/observations_germany/phenology/
  - `annual_reporters/crops/` (historical + recent) – long records, but the current year is usually published later.
  - `immediate_reporters/crops/` (recent) – use this for 2026.
- Crops: winter wheat, winter barley, sugar beet, maize, winter rapeseed, soybean (if present).
- Phases: sowing/drilling, emergence, and harvest at minimum; keep all phases that exist for these crops.
- Stations: within ~40 km of Heilbronn; save the station list with distances.
- `phenodata` (https://pypi.org/project/phenodata) can list and download these; direct HTTP is fine too.
- Output: `data/raw/dwd_phenology/…` plus `stations_selected.csv`.
- Check: per crop and phase, how many station-years we have since 2001.

### 5 · modis_ndvi (required)

- Products: MOD13Q1 v061 (Terra) and MYD13Q1 v061 (Aqua), 250 m, 16-day. Layers: NDVI and pixel reliability (and VI quality if available).
- Option A (no login): ORNL DAAC MODIS/VIIRS Land Product Subsets web service. Check the docs for the subset endpoint, band names and the per-request date limit; loop over date chunks with a pause.
- Option B: NASA AppEEARS point or area request (Earthdata login) for the three field polygons.
- Period: 2001-01-01 → latest available.
- Output: long-format CSV per field and product: `date, pixel_id, ndvi_raw, reliability`.
- Check: about 23 composites per year per product; note the NDVI scale factor from the product docs (do not apply it – raw stays raw).

### 6 · soilgrids (recommended)

- ISRIC SoilGrids 2.0 REST point query (verify endpoint and current limits in the docs: https://rest.isric.org).
- Properties: clay, sand, silt, soc, bdod, phh2o, cec. Depths: 0–5, 5–15, 15–30, 30–60 cm. Values: mean and the 5 % / 95 % quantiles.
- Output: `data/raw/soilgrids/<field_id>.json`
- Licence: CC BY 4.0 (ISRIC).

### 7 · dem (recommended)

- NASADEM or SRTMGL1 (30 m), clipped to the bbox, from LP DAAC via `earthaccess` or AppEEARS.
- Output: `data/raw/dem/dem_bbox.tif` (+ original tiles if downloaded as tiles).
- Check: CRS, resolution, no-data value, bbox fully covered.

### 8 · gpm_imerg (recommended)

- GPM IMERG Final daily, version 07 (check the exact short name on GES DISC).
- Easiest: area-averaged daily time series over a small box around each field (NASA Giovanni export), or OPeNDAP point subsetting.
- Period: 2001-01-01 → latest Final run.
- Output: `data/raw/gpm_imerg/<field_id>_daily.csv`

### 9 · smap (recommended)

- SMAP enhanced L3 soil moisture (9 km, daily) – check the current product version in the AppEEARS product list.
- AppEEARS point request for the three fields, 2015-04 → latest.
- Output: `data/raw/smap/<field_id>.csv`

### 10 · hls_ndvi (recommended, ask before downloading)

- HLSL30 and HLSS30 v2.0, only the bands needed for NDVI plus Fmask (L30: red B04, NIR B05; S30: red B04, NIR B8A – verify in the HLS user guide).
- Area: 1 km box around each field. Period: 2019 → now, growing seasons first.
- Prefer an AppEEARS area request (clipped server-side). Estimate the size first and ask me.
- Output: `data/raw/hls_ndvi/<field_id>/…`

### 11 · reference (required, no scraping)

- Create `reference/sources.md` with links and one-line notes for:
  - typical rotations on Kraichgau loess slopes and erosion (Brunotte et al., openagrar)
  - reed planthopper (Schilf-Glasflügelzikade) and rotation advice: JKI regional recommendation, LIZ series, LLG Sachsen-Anhalt
  - soybean in Baden-Württemberg and nitrogen left for the next crop (top agrar)
  - Space Apps rules: participant FAQ, project submission guide
- Links only plus my notes. Do not download paywalled articles.

## 3. Done when

- [ ] `config/study_area.json` has 3 real arable fields with polygons
- [ ] Datasets 2–5 and 11 are in `data/raw/` and logged in `MANIFEST.csv`
- [ ] Each dataset has a short check summary (dates, counts, missing values) in `data/CHECKS.md`
- [ ] Recommended datasets 6–10 downloaded or explicitly skipped with a reason in `data/CHECKS.md`
- [ ] No analysis or app code exists yet
