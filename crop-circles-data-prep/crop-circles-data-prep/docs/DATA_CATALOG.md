# Data catalog – Crop Circles (Field Shift)

What is in `data/raw/`, how to read it, and what to watch out for. Status as of 2026-11-04.
Paths are relative to this folder (`crop-circles-data-prep/`). Download provenance (URL, time, sha256) is in `data/MANIFEST.csv`; check results are in `data/CHECKS.md`; fetch scripts are `prep/fetch_<dataset_id>.py`.

## Study area and demo fields

`config/study_area.json` – bbox 8.80–9.40 E, 48.95–49.35 N (Heilbronn / Kraichgau).

| id | label | centroid (lat, lon) | area | source polygon |
|---|---|---|---|---|
| F1 | Near Eppingen | 49.144319, 8.918983 | 41.5 ha | OSM way/961878376 |
| F2 | Near Bad Rappenau | 49.245287, 9.120219 | 29.5 ha | OSM relation/2625534 |
| F3 | Near Schwaigern | 49.133532, 9.060868 | 41.9 ha | OSM way/152148766 |

**Each demo field is a block of 11–17 real parcels** (FIONA 2022 shows mixed crops inside). Treat field-level values as block averages. Team decision: keep the fields as they are.

## Index

| # | dataset_id | what | resolution | period | CRS | status |
|---|---|---|---|---|---|---|
| 1 | fields | OSM farmland polygons | vector | snapshot 2026-11-04 | EPSG:4326 | ✅ |
| 2 | nasa_power | daily weather per field | 0.5° × 0.625° (MERRA-2) | 1981-01-01 → 2026-10-31 | point | ✅ |
| 3 | dwd_climate | daily station climate, 7 stations | station | 1947 → 2026-11-03 | point | ✅ |
| 4 | dwd_phenology | crop phase dates (sowing … harvest) | station | 1925 → 2026 | point | ✅ |
| 5 | modis_ndvi | NDVI, 7 MODIS pixels per field | 250 m, 16-day | 2000-12-18 → 2026-10-16 | point | ✅ |
| 6 | soilgrids | texture, SOC, pH, CEC, bulk density | 250 m | static | point | ✅ |
| 7 | dem | NASADEM elevation | 1″ (~30 m) | 2000 | EPSG:4326 | ✅ |
| 8 | gpm_imerg | IMERG Final daily precipitation | 0.1° | 2001-01-01 → 2025-09-30 | point | ✅ |
| 9 | smap | SMAP L3 enhanced soil moisture AM/PM | 9 km | 2015-03-31 → 2026-11-03 | point | ✅ |
| 10 | hls_ndvi | HLS red / NIR / Fmask around each field | 30 m | 2019-01-02 → 2026-11-01 | UTM 32N | ✅ |
| 11 | reference | literature and rules links | – | – | – | ✅ |
| 12 | fiona | BW parcels with declared crop | parcel | 2022–2025 (WFS, whole bbox); 2023–2025 also around F1–F3 (WMS) | EPSG:25832 | ✅ |
| 13 | bk50 | LGRB soil map 1:50 000 (K factor, nFK, …) | polygon | static | EPSG:25832 | ✅ |
| 14 | thuenen_ctm | crop type maps | 10 m | 2017 → 2025 (2025 preliminary) | EPSG:3035 | ✅ |
| 15 | esa_cci_sm | ESA CCI soil moisture COMBINED v09.2 | 0.25° | 2020-01-01 → 2024-12-31 | point | ✅ |
| 16 | c3s_sm | C3S soil moisture COMBINED (CCI algorithm) | 0.25° | 2025-01-01 → 2026-10-10 | point | ✅ |
| 17 | dlr_croptypes | DLR CropTypes v2.1 crop type maps | 10 m | 2017 → 2025 | EPSG:32632 | ✅ |
| 18 | era5_land | ERA5-Land hourly time series (t2m, tp, swvl1–4) | 0.1° | 1981-01-01 → 2026-10-31 | point | ✅ |

---

## 1 · fields

- `data/raw/fields/overpass_response.json` – raw Overpass JSON (`out geom`), 13,464 elements.
- `data/raw/fields/osm_farmland.geojson` – same as GeoJSON FeatureCollection; feature `id` / `properties.osm_id` = `way/…` or `relation/…`, other properties are OSM tags.
- Licence: ODbL 1.0 – "© OpenStreetMap contributors".

## 2 · nasa_power

- `data/raw/nasa_power/F{1,2,3}_daily.csv` – raw API response: a text header between `-BEGIN HEADER-` and `-END HEADER-`, then CSV.
- Read: split the text on `-END HEADER-`, then `pd.read_csv` the rest. Date = `YEAR` + `DOY` (day of year), local solar time.

| column | unit | source |
|---|---|---|
| T2M, T2M_MAX, T2M_MIN | °C | MERRA-2 |
| PRECTOTCORR | mm/day | MERRA-2, bias-corrected |
| RH2M | % | MERRA-2 |
| WS2M | m/s | MERRA-2 |
| ALLSKY_SFC_SW_DWN | MJ/m²/day | CERES SYN1deg |
| GWETTOP, GWETROOT | 0–1 (wetness, top 5 cm / root zone ~1 m) | MERRA-2 |

- Missing: `-999` (only solar 1981–1983 and the last day).
- **F1 and F3 are identical** (same grid cell); solar is identical for all three. Recent days come from GEOS-IT instead of MERRA-2.
- Attribution (POWER referencing guide): "The data was obtained from National Aeronautics and Space Administration (NASA) Langley Research Center's Prediction Of Worldwide Energy Resources (POWER) project funded through the NASA Earth Science Division. The data was obtained from the POWER Project's Daily v2.10.2 on 2026/11/04."

## 3 · dwd_climate

- `data/raw/dwd_climate/stations_selected.csv` – station id, name, lat, lon, height, record start/end, distance to each field, why selected.
- `data/raw/dwd_climate/<station_id>/produkt_klima_tag_<start>_<end>_<id>.txt` – `;`-separated, padded, trailing `eor`. Historical file (quality-controlled, to 2025-12-31) + recent file (last ~500 days, not fully checked). Where both overlap, use historical.
- Columns used: `MESS_DATUM` (YYYYMMDD), `TMK` / `TXK` / `TNK` (°C mean / max / min at 2 m), `RSK` (mm precipitation), plus `SDK` (sunshine h), `UPM` (% RH), `FM` (m/s wind), `SHK_TAG` (cm snow), `QN_3` / `QN_4` (quality level).
- Missing: `-999`, and some dates are simply absent.

| station | name | km to F1 / F2 / F3 | usable record | note |
|---|---|---|---|---|
| 01254 | Eppingen | 1.5 / 19.5 / 10.5 | 1947-07 → 2002-11 | closed; predecessor of 01255 |
| 01255 | Eppingen-Elsenz | 5.7 / 21.6 / 15.9 | 2002-12 → now | **no rows 2019-01 → 2021-06** |
| 03362 | Mühlacker | 19.4 / 35.3 / 22.6 | 1998 → now | ~200 missing T days |
| 03734 | Obersulm-Willsbach | 31.6 / 21.3 / 21.2 | 2004-07 → now | complete |
| 03761 | Öhringen | 44.1 / 29.2 / 34.2 | 1947 → now | complete |
| 04349 | Sachsenheim | 23.6 / 32.2 / 19.6 | 1987-11 → now | complete |
| 15547 | Heilbronn/Neckar | 16.4 / 13.4 / 6.0 | – | **no temperature / precipitation** |

- Licence: CC BY 4.0 – "Source: Deutscher Wetterdienst (DWD), Climate Data Center (CDC)".

## 4 · dwd_phenology

- Germany-wide files, kept as downloaded (~500 MB): `data/raw/dwd_phenology/annual_reporters_crops_historical/`, `…_recent/`, `immediate_reporters_crops_recent/`. Descriptions in `…/docs/`.
- `stations_selected.csv` – 129 stations within 40 km of Heilbronn that report our crops (`stationsid`, `reporter` annual/immediate, distances).
- Columns: `Stations_id`, `Referenzjahr` (year), `Objekt_id` (crop), `Phase_id`, `Eintrittsdatum` (YYYYMMDD), `Jultag` (day of year), `Qualitaetsniveau`, `Eintrittsdatum_QB`. The `Ruebe` files use upper-case names (`STATIONS_ID`, `REFERENZ_JAHR`, …): normalise headers. Station ids are zero-padded in the station list only.
- Crops (`Objekt_id`): 202 winter wheat, 204 winter barley, 205 winter rapeseed, 215 maize (annual) / 210 maize without variety (immediate), 253 sugar beet; 25 "beet" in the new `Ruebe` files (variety per station-year in `PH_Jahresmelder_Landwirtschaft_Kulturpflanze_Ruebe_Spezifizierung.txt`). **No soybean.**
- Phases (`Phase_id`): 10 sowing, 12 emergence, 13 closed stand (beet), 15 shooting, 18 heading, 19 milk ripeness, 21 yellow ripeness, 24 harvest, 5 flowering, 65 tassel (maize). Full list: `docs/PH_Beschreibung_Phase.txt`.
- Since 2001 within 40 km: 340–490 station-years per crop and main phase (annual reporters); immediate reporters only from 2024.
- Licence: CC BY 4.0 (DWD).

## 5 · modis_ndvi

- Raw: `data/raw/modis_ndvi/appeears/` (AppEEARS point-sample CSVs per product + request JSON + README).
- Derived: `F{n}_MOD13Q1.csv`, `F{n}_MYD13Q1.csv` with `date, pixel_id, lat, lon, ndvi, reliability, vi_quality`.
  - `pixel_id` = `F1_<row>_<col>` in the global MODIS 250 m sinusoidal grid; 7 pixels per field (pixel centre inside the field polygon).
  - **`ndvi` is already scaled by AppEEARS** (−0.2 … 1; scale factor 0.0001 applied, unlike ORNL raw integers).
  - `reliability`: 0 good, 1 marginal, 2 snow/ice, 3 cloudy, −1 fill. `vi_quality`: 16-bit QA field.
- Terra 595 composites (2000-12-18 → 2026-10-16), Aqua 559 (2002-07-04 → 2026-10-08); 23 per full year each. No fill values.

## 6 · soilgrids

- `data/raw/soilgrids/F{n}.json` – `properties.layers[]` with `name`, `unit_measure` (`mapped_units`, `d_factor`), `depths[]` (`label` 0-5cm … 30-60cm, `values` mean / Q0.05 / Q0.95).
- **Divide by `d_factor`**: clay / sand / silt g/kg ÷10 → %; soc dg/kg ÷10 → g/kg; phh2o ÷10 → pH; bdod ÷100 → kg/dm³; cec ÷10 → cmol(c)/kg.
- Licence: CC BY 4.0 – SoilGrids 2.0, ISRIC (Poggio et al. 2021).

## 7 · dem

- `data/raw/dem/dem_bbox.tif` (copy of the AppEEARS file in `appeears/`): NASADEM, EPSG:4326, 1″ × 1″, 2161 × 1441 px, int16 metres, nodata −32768 (none present), 120–523 m.
- For slope: reproject to EPSG:25832 first (degrees ≠ metres).
- Citation: NASA JPL (2020), NASADEM Merged DEM Global 1 arc second V001, LP DAAC.

## 8 · gpm_imerg

- `data/raw/gpm_imerg/F{n}_daily.csv` – Giovanni format: 14 `key,value` header lines (product, unit, `undef`, cell lat/lon, …), a blank line, then `Timestamp (UTC),Data`.
- Unit mm/day; `undef` −9999.9 (none present); 9,039 days each.
- Cells (0.1°): F1 49.15/8.95, F2 49.25/9.15, F3 49.15/9.05 – three different cells.
- **Ends 2025-09-30** (latest IMERG Final V07 granule); use POWER / DWD after that.
- Citation: Huffman et al. (2023), GPM IMERG Final Precipitation L3 1 day 0.1° V07, GES DISC, doi:10.5067/GPM/IMERGDF/DAY/07.

## 9 · smap

- Raw: `data/raw/smap/appeears/`; derived `F{n}.csv`: `date, lat, lon, sm_am, qual_am, sm_pm, qual_pm`.
- SPL3SMP_E.006, 9 km EASE-Grid 2.0, m³/m³; fill −9999; `qual_*` = retrieval quality bit flag (0 = recommended quality).
- The three fields are in three different 9 km cells. ~59 % of days have a value (the rest: no retrieval); F2 has more `qual` 1 days – filter on `qual = 0`.

## 10 · hls_ndvi

- `data/raw/hls_ndvi/F{n}/appeears_<2019-2021|2022-2023|2024-now>/` – one GeoTIFF per scene and band: L30 `B04` (red), `B05` (NIR); S30 `B04` (red), `B8A` (NIR narrow); both `Fmask`.
- Box: field bbox, at least 1 km per side, + 60 m. Native UTM 32N, 30 m.
- Reflectance scale 0.0001. NDVI: L30 (B05 − B04)/(B05 + B04), S30 (B8A − B04)/(B8A + B04). Mask cloud, cloud shadow, adjacent, snow and water with `Fmask` bits (see HLS v2.0 user guide).
- 12,399 files (60 MB); per field ~440 L30 and 840–970 S30 scenes, 2019-01-02 → 2026-11-01. Names: `<product>_<band>_doy<YYYYDDD>_aid0001_32N.tif`.

## 11 · reference

- `reference/sources.md` – Kraichgau rotation / erosion (Brunotte et al.), reed planthopper rotation advice (JKI, LIZ, LLG), soybean N credit, Space Apps rules. Notes fields are for the team.

## 12 · fiona

- `data/raw/fiona/fiona_bbox_p00.json` … `p05.json` – GeoJSON FeatureCollections, **coordinates in EPSG:25832** (set the CRS explicitly when reading); 114,345 parcels.
- Properties: `NC` (crop code), `Bezeichnung` (crop name, German), `Kulturartengruppe`, `OeVF-code`, `FAKT-Code`, `FAKT-Massnahme`, `Antragsjahr` (2022), `geo_id`, `object_id`.
- Top crops in the bbox: vineyards, meadows, winter wheat, spring barley, grain maize, sugar beet, winter barley.
- 2023–2025 (added 2026-11-14): `fiona_bbox_<year>_p*.json` from the `_ab2023` WFS (404 on 2026-11-05, answers again), `python fetch_fiona.py <year>`; 126,997 / 126,104 / 122,773 parcels. Same properties, but `OER-Code` instead of `OeVF-code`; `object_id` is not stable across years. Not yet used by the pipeline.
- Team export: `data/export/fiona_kraichgau_2022-2025.zip` (one GeoJSON per year + README with the licence line, 115 MB, not in git).
- Licence: dl-de/by-2-0 – "Datengrundlage: MLR (2026), Datenlizenz Deutschland – Namensnennung – Version 2.0, https://mlr.baden-wuerttemberg.de".

## 13 · bk50

- Geometry: `data/raw/bk50/geola_bod_ke_p00.gml` … `p04.gml` – GML 3.1.1, EPSG:25832, 14,085 soil-unit polygons (503 units). Attributes `Kartiereinheit` (key), `Legendentext`, `Legende`, `Link` (unit PDF).
- Thematic tables (same polygons, no geometry; join on `Kartiereinheit`, values are unique per unit):

| file | attribute | classes (readme_dBK50) |
|---|---|---|
| `geola_bod_ke_kfa.gml` | `kfa-Wert` – ABAG K factor (arable) | 1 < 0.1, 2 0.1–0.2, 3 0.2–0.3, 4 0.3–0.5, 5 0.5–0.7, 6 0.7–1.0; `( )` locally; `-` grassland/forest |
| `geola_bod_ke_nfk.gml` | `nfk-Wert` – usable field capacity to 1 m | 1 < 50, 2 50–90, 3 90–140, 4 140–200, 5 ≥ 200 mm |
| `geola_bod_ke_kf.gml` | `KF` – saturated conductivity | 1 < 1 … 6 ≥ 300 cm/d; `/` topsoil/subsoil |
| `geola_bod_ke_lk.gml` | `LK` – air capacity | classes, see readme |
| `geola_bod_ke_gruustawr.gml` | `Grund/Stauwasser` | 1, 2, 4 |

- `fk`, `kak`, `natbod`, `akiwas_ln`, `gesbew_ln`: **no values in the WFS** (unit + PDF link only).
- Licence: dl-de/by-2-0 – "Datenquelle: Regierungspräsidium Freiburg – LGRB, https://www.lgrb-bw.de".

## 14 · thuenen_ctm

- `data/raw/thuenen_ctm/CTM_GER_<year>_rst_<v202|v302>_bbox.tif` – bbox window of the national COGs, unchanged values. EPSG:3035, 10 m, 4431 × 4501 px, int32, nodata −9999 (~41 %: forest, settlements).
- v202 (Blickensdörfer et al. 2022 method): 2017–2024. v302 (Pham et al. 2024 method): 2024, 2025 (preliminary, "2025_08"). Use v202 for the 2017–2024 sequence.
- Legend `CTM_GER_LegendEN_rst_v202.clr` (code R G B A name): 1101 winter wheat, 1102 winter barley, 1103 winter rye, 1201 spring barley, 1202 spring oat, 1300 maize, 1401 potato, 1402 sugar beet, 1501 winter rapeseed, 1502 sunflower, 1602 cultivated grassland, 1603 vegetables, 1611 peas, 1612 broad bean, 1613 lupin, **1614 soy**, 200 permanent grassland, 3001 small woody features, 3002 other agricultural, 3003 fallow, 3004 other, 3011 small woody (other land), 4001 grapevine, 4002 hops, 4003 orchard.
- Accuracy reports: `*_accuracy_*.pdf`. Licence: CC BY 4.0 (Thünen Institute, Zenodo).

## 15 · esa_cci_sm

- `data/raw/esa_cci_sm/cci_sm_combined_v09.2_daily.csv` – `date, lat, lon, sm, sm_uncertainty, flag, freqbandID`; two cells: 49.125/8.875 (F1) and 49.125/9.125 (F2, F3).
- `sm` m³/m³, fill −9999.0; `flag` bit field (0 = valid; 1 = snow / frozen); 95–96 % valid days.
- Licence: CC BY 4.0 – ESA CCI Soil Moisture v09.2 (Dorigo et al. 2017; Gruber et al. 2019; Preimesberger et al. 2021).

## 16 · c3s_sm

- Raw: `data/raw/c3s_sm/c3s_sm_combined_daily_<year>_<version>.zip` – one global NetCDF per day (3 zips, 1.2 GB). GDAL cannot open the NetCDFs inside the zip on Windows: extract first.
- Derived: `c3s_sm_combined_daily.csv` – `date, lat, lon, sm, sm_uncertainty, flag, source_zip`, same two cells as dataset 15; 648 days, 94–97 % valid.
- Versions: v202505 icdr 2025-01 → 2026-08, v202505_2 from 2026-09-01 (CDS notice: v202505 has many gaps on 1–20 Sep 2026).
- **Version step at 2024/2025** against CCI v09.2 – compare the overlap before joining the series.
- Licence: Copernicus licence (CC-BY) – "Contains modified Copernicus Climate Change Service information (2026)".

## 17 · dlr_croptypes

- `data/raw/dlr_croptypes/CROPTYPES_DE_P1Y_<year>_V021_bbox.tif` – bbox window of the national COGs, unchanged values. EPSG:32632, 10.003 m, 4392 × 4453 px, uint8, 0 = no data / non-cropland (~51 %).
- Legend `LEGEND_CropTypes_v21.txt`: 11 winter wheat, 12 winter barley, 13 winter rye, 14 other winter cereals, 21 spring wheat, 22 spring barley, 23 spring oat, 30 maize, 40 legumes, 41 soy, 42 lupin, 50 potato, **60 sugar beet**, 71 rapeseed, 72 sunflower, 83 permanent grassland, 84 forage, 90 vineyard, 100 fruit trees / woody, 110 hops, 111 other agricultural, 120 vegetables.
- Class F1 (`ACCURACIES_CropTypes_Germany.txt`, 2017–2025): sugar beet 0.89–0.95, winter wheat 0.72–0.84.
- Unlike Thünen, spelt and triticale are not winter wheat (class 14): the planner counts 11 + 14 as the wheat after beet.
- Licence: CC BY 4.0 – DLR CropTypes v2.1 (Gessner et al. 2025; Asam et al. 2022).

## 18 · era5_land

- `data/raw/era5_land/<field>_hourly.zip` – CDS `reanalysis-era5-land-timeseries` at each field centre (`location`), one zip per field with three CSVs (`valid_time, t2m` K; `tp` m per hour, not accumulated; `swvl1..swvl4` m³/m³), 401,760 hourly rows each, 1981-01-01 → 2026-10-31. Fetch: `prep/fetch_era5_land.py` (~1 min per field).
- Pipeline: daily max/min/mean °C, daily mm, soil water 0–7 cm and the 0–1 m column (layers 1–3 weighted 7/21/72 cm) → `daily.parquet` (`*_era5`), `indicators.parquet` (source `ERA5`), `soilmoisture.parquet` (`ERA5-Land 0–7 cm`, `ERA5-Land 0–1 m`).
- Check (F1, 2015–2024 means): 848 mm/yr, 11.4 heat days, 0.6 downpour days ≥ 20 mm in May–July (IMERG ≈ 2–3): ERA5 smooths convective rain, so it is a comparison column, not the downpour source.
- Licence: Copernicus licence (CC-BY) – "Contains modified Copernicus Climate Change Service information (2026)"; Muñoz Sabater (2019), doi:10.24381/cds.e2161bac.

## Gaps and caveats (summary)

- Fields are parcel blocks; MODIS (250 m) and all climate grids are coarser than one parcel. HLS (30 m), Thünen (10 m) and FIONA are the only parcel-scale sources.
- FIONA 2023 on is published as `WMS_LW-BW_FIONA_Flaecheninformation_ab2023` (layers `lw:v_fiona_flaecheninformation_2023` … `_2025`). Its bulk WFS (`…_ab2023`, listed in the Geoportal BW metadata) answered 404 on 2026-11-05, so `prep/fetch_fiona_wms.py` asks the WMS (GetFeatureInfo, JSON with polygon) at one point inside every FIONA 2022 parcel of the HLS boxes plus the uncovered pieces of each block → `data/raw/fiona/wms_ab2023/F*_20*.geojson`. Region-wide history 2017–2025 still comes from Thünen.
- Soybean: in Thünen maps (1614) and FIONA codes, not in DWD phenology.
- Precipitation after 2025-09-30: POWER and DWD only.
- Space Apps challenge resources (partner datasets) are published on 2026-11-13 – check and add here.
