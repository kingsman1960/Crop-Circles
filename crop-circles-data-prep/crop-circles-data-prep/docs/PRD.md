# PRD – Field Shift Kraichgau (working title)

NASA Space Apps Challenge 2026 · challenge "Field Shift: Adapting Farms with NASA Data" · team Crop Circles
Status: draft 2026-11-04. Build starts at the hackathon kickoff (Sat 14 Nov 2026).

## 1. One-liner

A web app that lets a farmer on Kraichgau loess pick a field, see how heat, drought, heavy rain, soil and bare-soil periods have hit it, and compare the current rotation with at least three alternatives – each with the reasons, the evidence, the benefits, the gaps and the risks.

## 2. Problem

- Kraichgau (Heilbronn, Baden-Württemberg): erosion-prone loess slopes (Brunotte et al.). Typical rotation: sugar beet → winter wheat → winter barley (+ cover crop).
- The reed planthopper (*Pentastiridius leporinus*) spreads SBR / Stolbur in sugar beet, and southern Germany is hit hardest (LIZ). Its nymphs overwinter in the winter wheat that follows beet; JKI, LIZ and LLG advise breaking exactly that step (no winter wheat after beet: ~80 % fewer adults (LLG), up to 90 % fewer nymphs (LIZ)).
- At the same time: hotter summers, drier springs, more intense summer storms on bare row-crop soil.
- Farmers need to see these pressures for *their* field and weigh rotation options against *their* priorities. The data exists (NASA, DWD, LGRB, Thünen) but is scattered and hard to read.

## 3. Users

| persona | needs | uses the app to |
|---|---|---|
| Farmer (primary), 30–60, smartphone/laptop, not a GIS user | plain language, own field, honest uncertainty | check field conditions, compare rotations, take a summary to the advisor |
| Advisor (LTZ, Maschinenring, sugar company field staff) | evidence and sources | discuss options with farmers, see the data behind each claim |
| Judges / demo audience | understand in 3 minutes | follow one field from data to recommendation |

## 4. Goals and non-goals

Goals
- G1 Field profile in < 10 s: soil, slope, erosion class, climate trends, bare-soil periods.
- G2 Compare ≥ 3 rotation strategies including the existing one, against farmer priorities.
- G3 Every statement traceable to a dataset or a source in `reference/sources.md`.
- G4 Clear about uncertainty and about what needs local expert review.

Non-goals
- No yield or profit prediction. No prescriptive advice ("you must"). No pest forecasting model.
- No user accounts, no farmer data upload in the MVP.
- No coverage beyond the Kraichgau bbox.

## 5. Challenge requirements → product

| challenge asks | product answer |
|---|---|
| decision-support tool using NASA Earth observations + local soil, crop traits, farmer priorities | NASA: POWER, GPM IMERG, SMAP, MODIS, HLS (Landsat/Sentinel), NASADEM; local: BK50, SoilGrids, DWD, FIONA, Thünen; priorities via sliders |
| patterns: temperature, heat stress, rainfall, soil moisture, evaporation, frost risk, extreme precipitation, vegetation stress, water trends | indicator panel (§7) |
| times when fields are typically bare; seasons when crops are vulnerable | bare-soil calendar from NDVI + phenology; vulnerability windows (heat at heading, dry spells at emergence, storms on bare soil) |
| rotations that interrupt pest cycles, reduce water demand, improve infiltration, add income | strategy cards (§8) with planthopper, water, erosion, N and income criteria |
| compare at least three strategies incl. the existing one | S0 + S1–S3 side by side |
| for each: why suggested, evidence, benefits, information gaps, risks needing local review | fixed five-part card layout |
| explain terms (ET, anomalies, NDVI, frost risk, water balance); satellite vs ground | "What is this?" tooltips + a glossary page; POWER/IMERG vs DWD comparison chart |
| SI / statistical approaches, uncertainty, where expertise is needed | transparent rule-based scoring first, optional SI for explanations (§10); uncertainty badge on every score |
| maps: erosion zones, water-stress hotspots, frost-prone areas; timelines, overlays, scenario sliders | map with BK50 K factor × slope, Thünen crop history, DEM; rainfall/temperature scenario slider (P1) |
| farmer-centred: easy, own priorities, support not replace | three-step flow, priority sliders, disclaimer on every recommendation |

## 6. Features

P0 – must have for the demo
1. **Field picker**: map of the Kraichgau with F1–F3 (and context layers); click a field → field page.
2. **Field profile**: soil (BK50 unit, K factor, nFK; SoilGrids texture/SOC/pH), slope from DEM, crop history (Thünen 2017–2025 composition inside the block, FIONA 2022 parcels).
3. **Conditions timeline**: per year and season – heat days, frost after emergence, dry spells, heavy-rain days, climatic water balance, soil-moisture anomaly; long-term trend line (1981 →).
4. **Bare-soil calendar**: months with low NDVI (MODIS 2001 →, HLS 2019 →) next to DWD sowing/harvest dates.
5. **Rotation comparison**: S0 + S1–S3 as cards (why / evidence / benefits / gaps / risks) and a score table per criterion.
6. **Priorities**: sliders (erosion, water, nitrogen, planthopper risk, income stability) re-weight the score table.
7. **Sources & attribution page**: every dataset with licence line (from `DATA_CATALOG.md`).

P1 – should have
8. Erosion map: K factor × slope × crop cover by month (simplified ABAG) as a map layer.
9. Scenario slider: +1/+2 °C, −10/−20 % spring rain → indicator shifts.
10. Satellite vs ground: POWER / IMERG vs DWD station for the same days.
11. German / English toggle.

P2 – nice to have
12. Click any FIONA parcel in the bbox (not only F1–F3).
13. One-page PDF / print summary for the advisor meeting.
14. SI chat that answers "why is S2 ranked first for me?" from the computed facts only.

## 7. Indicators (to compute during the hackathon)

Definitions are proposals; thresholds to be checked against sources on day 1.

| indicator | definition (draft) | data |
|---|---|---|
| heat days | days with Tmax ≥ 30 °C; also inside the wheat heading–milk window (DWD phases 18–19) | POWER, DWD, phenology |
| frost after emergence | days Tmin ≤ −2 °C between emergence and closed stand / shooting | POWER, DWD, phenology |
| dry spell | ≥ 14 consecutive days with P < 1 mm, by season | IMERG, POWER, DWD |
| heavy rain days | P ≥ 20 mm/day, May–July (row crops still open) | IMERG, DWD |
| climatic water balance | P − ET0 (Hargreaves from T and radiation), monthly | POWER |
| soil-moisture anomaly | z-score vs day-of-year climatology (SMAP 2015 →, CCI/C3S 2020 →) | SMAP, CCI, C3S |
| bare-soil period | NDVI < 0.3 (to calibrate), length and season | MODIS, HLS |
| erosion risk | K factor class × slope class × months bare in May–Aug × heavy-rain days | BK50, DEM, NDVI, IMERG |
| planthopper risk | rule: winter wheat directly after sugar beet = high; maize/pea/soy/fallow after beet = low (JKI / LIZ / LLG) | reference |
| N credit | legume before cereal: +30–50 kg N/ha (soy), peas higher | reference |
| water demand | crop water use in the season of highest deficit (Kc table) vs water balance | literature + POWER |

## 8. Rotation strategies (initial set)

| id | rotation | why it is on the list |
|---|---|---|
| S0 existing | sugar beet → winter wheat → winter barley (+ cover crop before beet) | baseline; most common in the region |
| S1 planthopper break | sugar beet → grain maize → winter wheat (+ cover crop) | removes wheat directly after beet (JKI / LIZ advice); maize is a known regional crop |
| S2 legume | sugar beet → soybean → winter wheat (+ cover crop) | breaks the pest cycle, N credit for wheat, soy is growing in BW |
| S3 soil cover | S0 with mulch seeding of beet and cover crops on every bare window | erosion focus on loess slopes (Brunotte et al.); keeps the familiar sequence |
| S4 (optional) pea | sugar beet → field pea → winter wheat | LIZ lists pea after beet; short season, early harvest |

Each card states what the data shows for *this* field (e.g. "F1: 3 of 5 recent Mays had ≥ 2 heavy-rain days while beet fields were bare") and what we do not know (prices, contracts, local pest pressure, machinery).

## 9. User flow

1. Landing: one sentence, map, "pick your field".
2. Field page, top: profile tiles (soil, slope, erosion class, water storage, last crops).
3. Middle: conditions timeline and bare-soil calendar, each with a one-line "what this means".
4. Priorities: five sliders with defaults.
5. Strategies: S0–S3 cards + score table, re-ordered by priorities; uncertainty badge per score.
6. Footer: "This tool supports, it does not replace, your judgment and local advice." + sources.

## 10. SI use (to be declared in the submission)

- Day 1: rule-based, transparent scores (explainable, no training data needed).
- Optional: an LLM writes the plain-language card text and answers questions **only from the computed numbers and `reference/sources.md`**, with citations; never invents numbers.
- Optional: a simple model (e.g. random forest) relating weather windows to NDVI dips, if time allows; reported with its uncertainty.
- Space Apps asks teams to describe how "SI tools" were used: keep a log from kickoff.

## 11. Non-functional requirements

- Runs locally with one command and on a free host (Streamlit Community Cloud or similar).
- App reads only small processed files (`data/processed/`, target < 100 MB total); raw data stays out of the repo.
- First paint < 3 s, field page < 5 s on a laptop.
- Readable on a phone (single column).
- Every chart: unit, source, period. Every dataset's licence line on the sources page.
- No personal data. FIONA shown as parcel crops only (no applicant data is in the WFS).

## 12. Success criteria / demo

- A judge can go landing → F1 → strategies in under 3 minutes and repeat the reason S1 or S2 ranks first.
- All four challenge "for each strategy" items are visible for every strategy.
- At least six NASA datasets used visibly; each chart names its source.
- Demo script and video follow the Project Submission Guide (published 13 Nov).

## 13. Risks and open questions

| risk / question | mitigation |
|---|---|
| Fields are parcel blocks; MODIS pixels mix crops | show block-level values honestly; use HLS + Thünen for parcel-scale views |
| AppEEARS outputs (MODIS, SMAP, HLS) not ready | still processing on 2026-11-04; fall back to POWER GWET + CCI for soil moisture, Thünen for crop cover |
| Indicator thresholds not validated | cite source per threshold; mark as "screening" |
| No price / contract data | list as information gap on every card; user slider for income weight only |
| Challenge resources (13 Nov) may add required datasets | review on 13 Nov, update this PRD |
| Judging criteria unknown until 13 Nov | re-check §12 against the Judging and Awards Guide |
