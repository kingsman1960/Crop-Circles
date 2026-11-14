# Welcome to Crop Circles, Tobias

Everything you need before the hackathon. About 30 minutes of reading, plus running the app once.

## The project in one minute

- **Event:** NASA Space Apps Challenge 2026, challenge *"Field Shift: Adapting Farms with NASA Data"*.
- **Problem:** the reed planthopper (*Pentastiridius leporinus*) spreads SBR / Stolbur in sugar beet. Its nymphs overwinter in winter wheat sown after beet, then fly to the beet fields around it. So it is a neighbourhood problem: one farmer changing their rotation alone helps little.
- **What the app does:** it finds every such "nursery" field in the Kraichgau (around Heilbronn) and ranks which ones should switch crops, and to which crop, so that most of the pressure is removed while soil and water stay safe.
- **Headline finding (2017–2025):** switching the best-placed 20 % of the nursery area removes about a third of the pressure. Switching the same area at random removes about a fifth.
- **Who it is for:** first the sugar-beet farmer (on a phone, in plain words, no indices), then the advisor, and the judges, who must follow one field from data to recommendation in three minutes.

## Where we are

The app already runs end to end, in English and German:

| page | answers | file |
|---|---|---|
| About | what the platform does | `app/views/home.py` |
| My field | the four risks on one field, in plain words | `app/views/field.py` |
| What to grow | rotation options ranked by the farmer's priorities | `app/views/strategies.py` |
| Our region | which wheat-after-beet fields should switch, and to what | `app/views/landscape.py` |
| Neighbours | the regional feed: notes, questions, alerts to the plant-protection office | `app/views/community.py` |
| How we know | method, glossary, every dataset and licence | `app/views/sources.py` |

The hackathon weekend is for validation, the demo and polish, not for starting from scratch.

## The services and how they connect

Read this once; it is the map of everything that was added on top of the first version. The order is the order the data flows.

```
raw downloads  ->  pipeline/  ->  data/processed/  ->  app pages  ->  fact card  ->  copilot (LLM, optional)
(prep/fetch_*.py)   (climate, phenology,  (parquet, json)    (views/*.py)    (copilot.card)   (copilot.ask)
                     strategies, landscape, hls)
                                                     ^
                                      accounts.py gates the pages, picks the fields a person may see
                                                     ^
                                      community.py: the feed; an alert carries the fact card to the office
```

### 1. Data sources and the pipeline (unchanged idea, two more sources)

- Every dataset has a fetch script in `crop-circles-data-prep/crop-circles-data-prep/prep/fetch_<id>.py`, a row in `docs/DATA_CATALOG.md`, a `[[dataset]]` entry in `content/sources.toml` (English) with its German overlay in `content/de/sources.toml`, and a line in `data/MANIFEST.csv`. Follow that pattern for any new source; the *How we know* page lists itself from `sources.toml`.
- **ERA5-Land (Copernicus, dataset 18)** is the newest: hourly temperature, rain and four soil-water layers at each field centre since 1981, fetched through the Climate Data Store time-series API (`prep/fetch_era5_land.py`, needs `~/.cdsapirc`). `pipeline/climate.py` turns it into daily values and it appears on *My field* as the fourth weather source, as the "Warmer than it used to be?" block (monthly temperature against the 1991–2020 mean) and as two soil-moisture series (0–7 cm and 0–1 m). ERA5-Land underestimates downpours, so the erosion story still rests on GPM IMERG.
- `python -m pipeline` rebuilds everything in `data/processed/`; a single step runs as `python -c "from pipeline import climate; climate.main()"`.

### 2. The pages (`app/views/`)

- **My field** reads `daily.parquet`, `indicators.parquet`, `soilmoisture.parquet` and the HLS/ECOSTRESS layers for one field id and writes the four risks in plain words. Every sentence it shows is also collected into `report` (for the printable report and the fact card, see 3).
- **What to grow** ranks the rotation options (`content/strategies.toml`) by the priorities the person sets; the maths is `data.rank_options`.
- **Our region** is the planner: `pipeline/pressure.py` computes planthopper pressure between parcels, the map shows which wheat-after-beet parcels should switch. Clicking a parcel opens its card. The parcels are FIONA (InVeKoS) outlines, i.e. the field shapes farmers draw in their subsidy application, not cadastral plots.
- **Neighbours** and **How we know**: see 4 and 1.

### 3. The copilot (`app/copilot.py`) – an LLM that explains, never computes

- The page builds a **fact card**: its own sentences, the figures with their sources, the priorities, the ranked options and the dataset names, in the reader's language (`copilot.card`). The model gets that card as its only knowledge and is told to answer from it alone.
- Every number in the answer that is not on the card is listed under the answer as "please check" (`copilot.unverified`). That is the guard against invented figures.
- It is **off until a key exists**: copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml` and fill `[copilot] api_key` (any OpenAI-compatible endpoint; Qwen Flash on DashScope is the default). `secrets.toml` is gitignored; never commit a key.
- Where it shows: the "Ask about this field" box at the bottom of *My field* and *What to grow*, with preset questions.

### 4. Accounts and the Neighbours page (`app/accounts.py`, `app/views/community.py`)

- **Sign-in gate.** `app.py` calls `accounts.gate()` on every platform page. Without an account in the session the sign-in card shows and the page stops. Accounts live in `app/platform.db` (SQLite, stdlib only, gitignored, created and seeded on first run; delete the file to reset).
- **Demo accounts**, password `demo` for all: `demo` (a farm with F1, F2 and F3), `anna` / `jonas` / `lea` (one farmer per demo field), `berater` (advisor), `amt` (the plant-protection office), `admin` (administrator). The card shows them, so the jury can sign in too.
- **Who sees what.** `data.field_picker` asks `accounts.my_fields()`: a farmer gets only their own field(s) and no field switch; advisor, office and admin get every field. Nothing else in the app knows about roles.
- **Adding parcels.** On *Our region* a farmer can add any clicked parcel to their farm ("Add this parcel to my farm"). *My field* then lists those parcels with their crop history. Their weather and soil figures need a pipeline run for that parcel's centre (every climate source is a point request, about a minute per parcel for ERA5-Land); the page says so.
- **The feed.** Posts have a kind: a note, a question, or an **alert to the office** (suspected pest or disease). Alerts go to the officials' *Inbox* tab until someone from the office replies in the thread. The alert's author gets a "send as e-mail" button whose body carries the fact card from 3, so the office receives the figures with the question. No e-mail is sent automatically. The administrator sees an *Accounts* tab and can delete posts.
- **Known limits.** A browser reload starts a new Streamlit session, so it asks to sign in again (page links keep the session). Streamlit Community Cloud forgets `platform.db` on every redeploy. A real deployment swaps the card for `st.login` (Google / Keycloak via OIDC) and points `accounts.DB` at a hosted database; the rest stays.

### 5. Tests and checks

- `python app/smoke_test.py` opens every page for every field and language as the administrator and checks the sign-in card (wrong password refused, `anna` lands on F1 without a field switch).
- `python app/check_i18n.py` checks that every text key used in the code exists in `en.toml` and `de.toml` with the same placeholders. Both run in a few minutes.
- `python app/copilot.py` and `python app/accounts.py` run their self-checks.

## Data, briefly

Most of the satellite data was downloaded through NASA AppEEARS; the ERA5-Land series come from the Copernicus Climate Data Store. Together with the other sources, it has been cleaned into small app-ready files in `data/processed/`, which are committed to the repo. The raw downloads stay on our machines, so you don't need them to run the app. The *How we know* page lists every dataset.

## Run it

Python 3.11+. From the repo root ([github.com/kingsman1960/Crop-Circles](https://github.com/kingsman1960/Crop-Circles)):

```
pip install -r crop-circles-data-prep/crop-circles-data-prep/prep/requirements.txt -r pipeline/requirements.txt -r requirements.txt
streamlit run app/app.py       # the app; sign in with a demo account (password: demo), see section 4 above
python app/smoke_test.py       # every page renders, in English and German, plus the sign-in card
python app/check_i18n.py       # every text key exists in both languages
```

Optional: the copilot box needs an API key in `.streamlit/secrets.toml` (copy `secrets.example.toml`); the app runs without it.

`python -m pipeline` rebuilds `data/processed/` from the raw data. It only works on a machine that has the raw downloads.

## Codebase map

| folder | what |
|---|---|
| `app/` | Streamlit app. `app.py` sets up navigation and the sign-in gate, `views/` holds one file per page, `data.py` has the loaders and the planner, `accounts.py` the accounts, farms and feed (SQLite), `copilot.py` the fact card and the LLM call, `locales/en.toml` and `locales/de.toml` hold all UI text |
| `pipeline/` | Python steps that turn raw data into processed data. `pressure.py` is the pressure maths, which the app also uses |
| `content/` | strategy cards, texts, glossary and sources as TOML, so content can be edited without touching code |
| `crop-circles-data-prep/crop-circles-data-prep/` | fetch scripts (`prep/`), study area (`config/study_area.json`), docs (`docs/`), data |
| `submission/` | demo material and the log of AI-tool use |

**Coming from Rails:** there is no request/response cycle. Streamlit reruns the page script from top to bottom on every click, so a file in `app/views/` is controller and template in one. `st.cache_data` plays the role of a cache, and `app/locales/*.toml` works like Rails i18n files.

## How we work

- `main` always runs. Work on short branches (`feat/…`, `data/…`, `fix/…`), keep PRs small, and get one reviewer.
- No secrets in the repo. `.netrc` and API keys stay in your home folder.
- Never hard-code UI text: add keys to both `en.toml` and `de.toml`. Run `smoke_test.py` and `check_i18n.py` before opening a PR.
- If an AI tool helped with a step, add one line to `submission/si_log.md`. Space Apps asks how such tools were used.

## The event

- **When:** Sat 14 to Sun 15 Nov 2026, 48 hours, in Heilbronn. Venue and start time: TODO
- **Fri 13 Nov:** the Project Submission and Judging guides come out, and we adjust the scope to match.
- **Rhythm:** a 5-minute stand-up every 3 hours. Feature freeze at hour 24, content freeze at hour 36, code freeze at hour 40, submission by hour 44.
- **Roles** are assigned at kickoff: data, app, agronomy/content, pitch.
- **Team chat:** TODO

## Reading order

1. This page.
2. [PRD](../../crop-circles-data-prep/crop-circles-data-prep/docs/PRD.md), sections 1, 3 and 12 (the idea, the users, what success looks like).
3. Click through the app: *Our region*, then *My field* (F1), then *What to grow*.
4. [first_task_radar.md](first_task_radar.md): a first task we think suits you.

## Before the 14th (all optional)

- [ ] Send us your GitHub username so we can give you repo access.
- [ ] Run the app locally once.
- [ ] Read the radar task and tell us whether it appeals to you, or whether you'd rather work on something else (app, validation, pitch).
- [ ] If you take the radar task: create a free NASA Earthdata login.
