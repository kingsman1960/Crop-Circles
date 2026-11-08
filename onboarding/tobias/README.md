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
| How we know | method, glossary, every dataset and licence | `app/views/sources.py` |

The hackathon weekend is for validation, the demo and polish, not for starting from scratch.

## Data, briefly

Most of the satellite data was downloaded through NASA AppEEARS. Together with the other sources, it has been cleaned into small app-ready files in `data/processed/`, which are committed to the repo. The raw downloads stay on our machines, so you don't need them to run the app. The *How we know* page lists every dataset.

## Run it

Python 3.11+. From the repo root ([github.com/kingsman1960/Crop-Circles](https://github.com/kingsman1960/Crop-Circles)):

```
pip install -r crop-circles-data-prep/crop-circles-data-prep/prep/requirements.txt -r pipeline/requirements.txt -r requirements.txt
streamlit run app/app.py       # the app
python app/smoke_test.py       # every page renders, in English and German
python app/check_i18n.py       # every text key exists in both languages
```

`python -m pipeline` rebuilds `data/processed/` from the raw data. It only works on a machine that has the raw downloads.

## Codebase map

| folder | what |
|---|---|
| `app/` | Streamlit app. `app.py` sets up navigation, `views/` holds one file per page, `data.py` has the loaders and the planner, `locales/en.toml` and `locales/de.toml` hold all UI text |
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
