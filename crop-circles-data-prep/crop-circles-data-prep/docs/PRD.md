# PRD – Field Shift Kraichgau (working title)

NASA Space Apps Challenge 2026 · challenge "Field Shift: Adapting Farms with NASA Data" · team Crop Circles
Status: draft 2026-11-04, revised the same day: the product's core is now the landscape planner (§1, §6 item 0). Build started early by decision of the team lead.

## 1. One-liner

**Landscape Shift.** The reed planthopper is a neighbourhood problem: its nymphs overwinter in winter wheat sown after sugar beet and fly to the beet around it. The app shows every such "nursery" in the Kraichgau from 10 m crop maps, and tells a sugar company or an advisor **which** fields should switch – and to what crop – so that the most pressure is removed while soil and water stay safe (NASA terrain, rain and climate data). Measured on 2017–2025: switching the best-placed 20 % of the nursery area removes 30–44 % of the pressure; the same area at random removes about 20 %.

Under it, the field view: a web app that lets a farmer on Kraichgau loess pick a field, see how heat, drought, heavy rain, soil and bare-soil periods have hit it, and compare the current rotation with at least three alternatives – each with the reasons, the evidence, the benefits, the gaps and the risks.

## 2. Problem

- Kraichgau (Heilbronn, Baden-Württemberg): erosion-prone loess slopes (Brunotte et al.). Typical rotation: sugar beet → winter wheat → winter barley (+ cover crop).
- The reed planthopper (*Pentastiridius leporinus*) spreads SBR / Stolbur in sugar beet, and southern Germany is hit hardest (LIZ). Its nymphs overwinter in the winter wheat that follows beet; JKI, LIZ and LLG advise breaking exactly that step (no winter wheat after beet: ~80 % fewer adults (LLG), up to 90 % fewer nymphs (LIZ)).
- At the same time: hotter summers, drier springs, more intense summer storms on bare row-crop soil.
- Farmers need to see these pressures for *their* field and weigh rotation options against *their* priorities. The data exists (NASA, DWD, LGRB, Thünen) but is scattered and hard to read.

## 3. Users

**Primary: the sugar-beet farmer in the Kraichgau.** 30–60, opens the app on a phone in the yard or a
laptop in the office, a few times a season – not every day. Knows the fields, the crops and the weather in litres per m²;
is not a GIS user and does not read K factors, z-scores or "pressure indices". Wants three answers: *What threatens my
field? What should I grow after this year's beet? Does it help if I change alone?*

**Secondary: the advisor** – sugar-company field staff, LTZ, Maschinenring. Sits with the farmer or runs the growers'
meeting. Uses *Our region* and the switch list, and opens the details and sources to back up what the farmer sees.

**Also: judges and the demo audience** – must follow one field from data to recommendation in three minutes.

| page | for | answers |
|---|---|---|
| About (landing) | first-time visitors, judges | what the platform does and how to use it; one button opens the platform |
| My field (start of the platform) | farmer | the four risks on my field in plain words, with a level and what helps; the best-matching rotation |
| What to grow | farmer + advisor | the options against what I grow now, ranked by what matters to me |
| Our region | advisor (farmer reads the headline) | which wheat-after-beet fields should switch, and to what |
| How we know | advisor, judges | words explained, every dataset and licence, the method |

### Writing for farmers (applies to every screen)

1. Every number comes with what it means: a level (low / medium / high), a comparison ("7 of the last 10 years",
   "22 days a year, against 9 in 1981–2010") or a fraction ("about a third less").
2. Units farmers use: litres per m² for rain and water, days, hectares, °C, "a drop of 6 m over 100 m" for slope.
   No z-scores, K·S, ET0 or index values on the main screens – those stay in *How we know* and in tooltips.
3. Headings are the farmer's questions or plain statements ("Soil washing away", "What to grow after sugar beet").
4. One control before the first answer; expert settings are folded away.
5. Scores are shown as five dots plus words against today's rotation ("a little worse", "much better"), not decimals.
6. Each risk card ends with "What helps" and its source; general agronomy that is not from our sources says so.
7. The tool supports, it does not decide: no "you must", and every page closes with the disclaimer.

## 4. Goals and non-goals

Goals
- G1 Field profile in < 10 s: soil, slope, erosion class, climate trends, bare-soil periods.
- G2 Compare ≥ 3 rotation strategies including the existing one, against farmer priorities.
- G3 Every statement traceable to a dataset or a source in `reference/sources.md`.
- G4 Clear about uncertainty and about what needs local expert review.
- G5 Show that coordinated, targeted switching removes more planthopper pressure than the same effort spent at random, and which crop fits each switched field.

Non-goals
- No yield or profit prediction. No prescriptive advice ("you must"). No pest forecasting model: the planner applies the published rotation rule (no wheat after beet) in space, it does not predict infestation.
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
0. **Landscape planner**: nurseries (winter wheat on last year's beet) per FIONA parcel from the Thünen maps 2017–2025; pressure on every beet parcel (Σ nursery ha × e^(−d / r), r = flight distance 0.5–2 km as a setting); a ranked list of nurseries to switch, each with the crop that replaces the wheat (maize, soybean or pea, by erosion, water and income side effects); targeted vs. random comparison; CSV export; the pressure on F1–F3 before and after.
1. **Field picker**: map of the Kraichgau with F1–F3 (and context layers); click a field → field page.
2. **Field profile**: soil (BK50 unit, K factor, nFK; SoilGrids texture/SOC/pH), slope from DEM, crop history (Thünen 2017–2025 composition inside the block, FIONA 2022 parcels).
3. **Conditions timeline**: per year and season – heat days, frost after emergence, dry spells, heavy-rain days, climatic water balance, soil-moisture anomaly; long-term trend line (1981 →).
4. **Bare-soil calendar**: months with low NDVI (MODIS 2001 →, HLS 2019 →) next to DWD sowing/harvest dates. Done for F1–F3 with HLS (share of the field bare per month).
4a. **This season from space** (*My field*): HLS 30 m tells winter cereal and sugar beet apart per parcel, so the newest season (2026) shows which of last year's beet parcels became planthopper nurseries and which parcels carry beet now – a year before the Thünen map. Rule checked against Thünen 2019–2025 on F1–F3: winter cereal or not after beet 40/41; beet found 33/46, 33 of 44 beet calls right. The June window was added after F2 showed late maize still green in autumn (before: 32 of 56 calls right). Against the farmers' FIONA declarations 2022–2025: winter cereal after beet 22/23; arable parcels winter cereal or not 238/260; beet found 19/28, 19 of 24 calls right.
4b. **Summer green since 2001** (*My field*, weather tab): MODIS June–August NDVI per year; the least green summers are named and checked against the 5 driest summers (NASA POWER water balance). F1: 3 of 4, F2: 2 of 4, F3: 4 of 4.
4f. **Second crop map for the region** (*Our region*): DLR CropTypes v2.1 next to Thünen. The planner runs on both: the right fifth removes 32–36 % (DLR) vs 30–37 % (Thünen) of the pressure in every season 2018–2025; DLR confirms 93–95 % of the Thünen nursery area parcel by parcel (2025: 84 %, Thünen 2025 preliminary). Shown as the DLR nursery area on the KPI, 'both maps agree' in the map tooltip and the switch list, and a check line in the expert view.
4c. **Winter cover** (*My field*, bare-soil tab): HLS November–December NDVI of every parcel that grows a spring crop next year; green (≥ 0.5) = cover crop, else bare. Checks the rotation model's assumption of a cover crop before beet: F1 4 of 14 beet crops, F2 10 of 11, F3 4 of 7 (2020–2025).
4d. **The soil right now** (*My field*, soil-moisture tab): SMAP topsoil and POWER root zone of the last 14 days against the same days in every earlier year (3 Nov 2026: wetter in 10 of 11 years, root zone 44 of 45).
4e. **Page to print** (*My field*): every finding of the page in words as one HTML page for the advisor.
5. **Rotation comparison**: S0 + S1–S3 as cards (why / evidence / benefits / gaps / risks) and a score table per criterion.
6. **Priorities**: sliders (erosion, water, nitrogen, planthopper risk, income stability) re-weight the score table.
7. **Sources & attribution page**: every dataset with licence line (from `DATA_CATALOG.md`).

P1 – should have
8. Erosion map: K factor × slope × crop cover by month (simplified ABAG) as a map layer.
9. Scenario slider: +1/+2 °C, −10/−20 % spring rain → indicator shifts.
10. Satellite vs ground: POWER / IMERG vs DWD station for the same days.
11. German / English toggle. Done as i18n: `app/locales/<tag>.toml` per language, content overlays in `content/<tag>/`, locale-aware numbers and dates; a new language is a new file (README › Languages).

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
| planthopper pressure (landscape) | Σ over nurseries of nursery ha × e^(−distance / r) at each beet parcel; nursery = winter wheat on last season's beet | Thünen CTM, FIONA |
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

1. My field (start): four risk cards in plain words (planthopper, soil washing away, dry summers, heat), the best-matching rotation, the block on the map, the numbers behind it.
1b. Our region: the planthopper finding in one sentence, one question ("how many fields switch?"), the map, the demo fields before and after, the switch list as CSV; expert settings folded away.
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

- A judge can repeat the one finding: "switching the best-placed 20 % of wheat-after-beet fields removes about a third of the planthopper pressure; random switching removes a fifth".
- A judge can go overview → planner → F1 → rotations in under 3 minutes and repeat the reason S1 or S2 ranks first.
- All four challenge "for each strategy" items are visible for every strategy.
- At least six NASA datasets used visibly; each chart names its source.
- Demo script and video follow the Project Submission Guide (published 13 Nov).

## 13. Risks and open questions

| risk / question | mitigation |
|---|---|
| Fields are parcel blocks; MODIS pixels mix crops | show block-level values honestly; use HLS + Thünen for parcel-scale views |
| AppEEARS outputs (MODIS, SMAP, HLS) not ready | All in on 2026-11-05: HLS F1–F3 (→ 2026-11-01), MODIS (→ 2026-10-16), SMAP (→ 2026-11-03). The app still falls back to MODIS for bare-soil months and to POWER GWET + CCI for soil moisture when a download is missing |
| Indicator thresholds not validated | cite source per threshold; mark as "screening" |
| No price / contract data | list as information gap on every card; user slider for income weight only |
| Challenge resources (13 Nov) may add required datasets | review on 13 Nov, update this PRD |
| Judging criteria unknown until 13 Nov | re-check §12 against the Judging and Awards Guide |
| Planthopper flight distance not in our sources | a setting (0.5 / 1 / 2 km); results shown for each – the ranking barely changes |
| Planner not validated against SBR / Stolbur incidence | call it a relative pressure screening; ask LIZ / ISIP for monitoring data |
| FIONA parcel outlines only for 2022; Thünen 2025 preliminary; 2023 beet area about half of other years in the map | stated on the planner; re-run when newer maps or parcels appear |
