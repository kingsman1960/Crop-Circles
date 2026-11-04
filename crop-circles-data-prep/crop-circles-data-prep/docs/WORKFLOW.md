# Workflow – how the team builds during the hackathon

Applies from the kickoff (Sat 14 Nov 2026). Until then only data work (`docs/DATA_COLLECTION.md`) and documents like this one.

## 1. Roles

Fill in names at kickoff. One person can hold two roles.

| role | owns | main files |
|---|---|---|
| Data lead | processed data layer, indicator code, data catalog | `pipeline/`, `data/processed/` |
| App lead | Streamlit app, maps, charts, deployment | `app/` |
| Agronomy / content lead | strategies, thresholds, card text, sources | `content/`, `reference/sources.md` |
| Pitch lead | demo script, video, submission form, SI-use log | `submission/` |

## 2. Repository layout (created at kickoff)

```
crop-circles-data-prep/      # this folder: raw data, fetch scripts, docs (exists)
  data/raw/                  # untouched downloads (git-ignored)
  data/processed/            # small app-ready files (parquet / geojson / png), committed if < 100 MB total
pipeline/                    # raw -> processed, one script per output, re-runnable
app/                         # Streamlit app (pages, components)
content/                     # strategy cards, glossary, texts (markdown / yaml)
submission/                  # demo script, screenshots, SI-use log
```

Rules
- The app reads only `data/processed/`. Never raw files at runtime.
- Each pipeline script writes one output and prints a short check (rows, range, missing).
- Content (strategy text, thresholds, glossary) lives in `content/`, not in code, so the agronomy lead can edit it.

## 3. Git

- `main` always runs. Work on short branches `feat/<topic>`, `data/<topic>`, `fix/<topic>`.
- Small PRs, one reviewer (anyone), merge within the hour. Pull `main` before starting a new task.
- Commit raw data never; processed data only if small. No secrets (`.netrc`, `.cdsapirc`, API keys) – they live in the home folder.
- Tag the submitted version: `git tag submission`.

## 4. Task flow

1. Pick the top open task from the board (GitHub Issues or a shared list) in `docs/PLAN.md` order.
2. Write the acceptance check first (what must be visible / which number must come out).
3. Build → run locally → push → PR → merge.
4. Post a one-line update in the team chat: done / blocked / next.

Definition of done
- Runs from a clean clone with the documented command.
- Shows units, source and period on every chart.
- Data used is listed in `DATA_CATALOG.md` with its licence line.
- No hard-coded coordinates (read `config/study_area.json`).

## 5. Working with Claude Code

- At kickoff, update `crop-circles-data-prep/CLAUDE.md`: lift the "no analysis / no app code" rule, add the repo layout above and the definition of done.
- Give Claude one task at a time with the acceptance check; point it to `DATA_CATALOG.md` for file formats.
- Ask it to log every SI-assisted step (prompt purpose, what was kept) in `submission/si_log.md` – the submission must describe how SI tools were used.
- Keep credentials out of prompts and logs.

## 6. Rhythm (48 h)

| when (from kickoff) | ritual |
|---|---|
| H0 | kickoff: roles, read Project Submission + Judging guides, freeze scope (P0 list) |
| every 3 h | 5-min stand-up: done / next / blocked |
| H12 | first end-to-end demo with dummy numbers (field page + one card) |
| H24 | feature freeze for P0; only P1 if P0 is green |
| H36 | content freeze: card texts, thresholds, sources final |
| H40 | code freeze except bug fixes; record demo video |
| H44 | submission done; buffer until the deadline |

## 7. Submission checklist (complete on 13 Nov when the guide is out)

- [ ] Project page on spaceappschallenge.org filled in (title, summary, challenge)
- [ ] Link to the running app and to the repository
- [ ] Demo video / slides as required by the guide
- [ ] Data and resources list with attributions (from `DATA_CATALOG.md`)
- [ ] Description of SI tool use (`submission/si_log.md`)
- [ ] Team members and roles
- [ ] Everything checked against the Judging and Awards Guide
