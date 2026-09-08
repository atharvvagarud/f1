# F1 Intelligence v2 — Foundation Refactor Report

> **Stage:** R9 — Foundation Readiness / Final Handoff (final stage of
> `V2_FOUNDATION_REFACTOR.md`).
> **Date:** 2026-09-08.
> **Rule compliance:** No Phase 1 work. No model retraining, no artifact or
> dataset modification, no fixture regeneration, no prediction-semantics
> change, no probability normalisation, no new infrastructure.
> The only production-adjacent change in R9 is the explicitly authorised
> Makefile interpreter-preflight + `--reload-dir` tooling fix (§9).
> Evidence below reuses the completed R0–R8 record in
> `docs/V2_REPOSITORY_AUDIT.md` plus fresh R9 verification runs.
> Nothing is estimated or invented: every number was observed this stage.

---

## 1. Executive Summary

**Original project.** A university F1 in-race winner-prediction application:
FastF1 ingestion scripts → fixed-checkpoint CSV datasets (2019–2023) →
Logistic Regression / HistGradientBoosting / XGBoost pipelines → a FastAPI
prediction backend → a Next.js prediction frontend, plus a legacy Streamlit
app and historical experiment outputs. Full baseline in
`docs/V2_REPOSITORY_AUDIT.md` §§1–11.

**Why Foundation was necessary.** The working system had no automated tests,
one 242-line predictor module mixing six responsibilities, schemas inline in
route code, a 1278-line frontend page, triplicated feature/checkpoint/model
constants, an unrelated duplicated replay prototype, unexplained large files,
three accidental nested Git repositories (and no root repo at all), and no
documented setup/test/build workflow. Any V2 data-platform work layered on
top of that would have had no regression safety net.

**Deliberately preserved.** All prediction behaviour and methodology: the 10
feature columns in order, checkpoints [5, 10, 15, 20, 25], model families and
their tuned artifacts (30 `.pkl`), the 14 dataset CSVs, majority-vote +
XGBoost-tie-break ensemble semantics, response schemas, the 4-route API
contract, the full UI flow, all 42 pipeline scripts, all historical results,
and all known defects/limitations (documented, not fixed).

**Restructured.** `ml/` (`config`, `features`, `inference`) extracted with a
framework-free boundary; FastAPI split into `main` / `routes` / `schemas` /
`services/prediction_service.py`; the frontend page decomposed into a
`features/prediction/` tree (hook, transforms, five component modules);
legacy/duplication removed (~33.7 MB); one root Git repo with a cache-aware
`.gitignore`; a regression suite (Python + frontend); README, env example,
and a Makefile command surface.

**Readiness verdict.** Foundation is **COMPLETE** and the repository is
**READY for D0** (`V2_PHASE_1_DATA_PLATFORM.md`, D0 only). No Foundation
Definition-of-Done item is FAIL (§11). Full regression is green (§5). The
only tooling change (Makefile preflight) is verified to fail loudly on the
broken interpreter and pass on a valid one (§9).

---

## 2. Original Baseline

Verified in R0 (`docs/V2_REPOSITORY_AUDIT.md` §§1–11). All of the following
are **LEGACY** characteristics of the pre-refactor system — recorded here as
history, not as V2 claims:

- Historical (not live) prediction application built on FastF1 session data.
- Data coverage **2019–2023**, **104 races** (lap-10 dataset: 2066 data rows).
- Fixed lap checkpoints **5 / 10 / 15 / 20 / 25**; no arbitrary-lap inference.
- Model families: **Logistic Regression, HistGradientBoosting, XGBoost**,
  trained per checkpoint (`*_multilap`, `model_tuned.pkl` preferred with
  `model.pkl` fallback).
- **FastAPI + Next.js** (React 19, TypeScript, Tailwind v4, Motion) as the
  supported path, plus a **legacy Streamlit** app (`app.py`, byte-identical
  copy at `legacy/streamlit_app.py`, the latter unrunnable from its location).
- Existing `scripts/` pipeline (ingestion → cleaning → training/tuning →
  baselines → analysis → predict CLIs) and `results/` experiment outputs.
- **No automated tests** of any kind (no `test_*.py`, no frontend tests).
- Repository hygiene issues: no root Git repo, 3 nested `.git`s, `.DS_Store`,
  `__pycache__`, committed `frontend/.next/`, orphaned Windows venv in
  `scripts/venv/`, doc duplication, unexplained 3.9 MB `gpt.txt`, untracked
  6.6 GB FastF1 source cache with no policy.
- Legacy **GroupKFold** evaluation (race-grouped CV) — recorded as a
  limitation, **not** as temporal backtesting and **not** as final V2
  performance. No legacy metric is presented anywhere in this report as a V2
  result.
- **Independent binary winner-probability semantics**: per-driver outputs are
  independent classifier scores in [0, 1]; they are not constrained to sum to
  1 and are not a mutually exclusive race-level distribution. The ensemble
  `confidence_value` is the XGBoost probability of the voted winner, not a
  calibrated race-level confidence.

---

## 3. Foundation Changes

By category (chronological detail in `docs/V2_REPOSITORY_AUDIT.md` §§12–19).

### Repository hygiene (R1, R7)

- 3 nested `.git` dirs removed (histories bundled to `/tmp/r1_git_backups/`
  first); `git init` at root → exactly one intentional repository.
- Removed generated junk only: `frontend/.next/` (regenerated via build),
  13× `.DS_Store`, 8× `__pycache__`, 10× `*.pyc`, orphaned `scripts/venv/`.
- Root `.gitignore` covers macOS/Python/venv/pytest/coverage/Node/Next/IDE/
  temp/log files, both FastF1 caches (`/.fastf1_cache/`,
  `/data/raw/fastf1_cache/`), with an explicit do-not-ignore note protecting
  datasets, model artifacts, results, and the golden fixture.
- R7 untracked the 1113-blob 6.6 GB reproducible FastF1 source cache from the
  index (`git rm -r --cached`, index-only; local cache intact, history
  untouched, no LFS): `git ls-files` 1492 → 379, and R9 confirms the index
  holds **0** `.ff1pkl` files.

### Regression safety (R2)

- New suite, zero production-code changes at the time:
  `tests/{conftest,test_api_baseline,test_prediction_equivalence,
  test_model_loading,test_datasets,test_ensemble,test_known_defects}.py`,
  `frontend/lib/{predictionHelpers,api}.test.ts`, `requirements-test.txt`.
- Golden fixtures (`tests/fixtures/legacy_predictions.json`, generated from
  the unmodified implementation: 6 races × ensemble + 3 model families × 5
  checkpoints) exercised with exact match on winners/ranks/top-5/reasons and
  NaN-aware abs tol 1e-9 on raw probabilities.
- Monaco 2022 HTTP-200 expectations are `xfail(strict=False)` markers, never
  a 500 contract; fixture sha256 asserted in-suite.

### ML/inference architecture (R3)

- New flat `ml/` package — `config.py` (ROOT, CHECKPOINTS, MODELS,
  MODEL_LABELS, path helpers), `features.py` (FEATURE_COLS, order frozen),
  `inference.py` (7 inference functions, verbatim move) — because the
  dependency graph showed scripts are standalone leaves and the only in-repo
  import was `api.main → api.services.predictor`. Placeholder
  `data/training/evaluation` trees were deliberately **not** created.
- Eliminated 5 redundant CHECKPOINTS/FEATURE_COLS/MODELS copies and 2
  MODEL_LABELS copies (api + `app.py` + 3 scripts → single source).
  Training/eval NUM_COLS/CAT_COLS splits intentionally left alone (unifying
  them would require training execution, which is forbidden).

### Backend architecture (R4)

- `api/main.py` → assembly only (app + CORS + `include_router`).
- New `api/routes.py` (`APIRouter`, same 4 paths/methods/handler names),
  `api/schemas.py` (verbatim request models), `api/services/
  prediction_service.py` (health / races / ensemble / single-model use cases
  → `ml.inference`). The temporary R3 re-export shim was deleted after
  inspecting all consumers. Dependency direction: route → service →
  `ml.inference` → artifacts; `ml/` imports nothing from FastAPI.

### Frontend architecture (R5)

- `app/page.tsx` 1278 → **114 lines** (layout composition only). New
  `features/prediction/` tree: `hooks/usePrediction.ts`, `lib/
  predictionTransforms.ts` (+ 4 node tests), `components/{PredictionHero,
  EnsembleResults,SingleResults,ResultCards,DriverCards}.tsx`.
- All JSX moved by scripted line-range extraction and verified
  **byte-identical** against git HEAD. Wire protocol unchanged
  (`page → usePrediction → lib/api → backend`); no new dependencies, no
  store library. Dead code removed in transit (6 unused imports + 1 unused
  var, previously lint warnings); the `barClassName` unused-prop warning was
  deliberately kept, not fixed.

### Legacy cleanup (R6)

- Retired with per-item evidence: root `app.py` + `legacy/streamlit_app.py`
  (full parity table, §7 — no Streamlit-only capability found), both
  duplicate `f1-race-replay-main/` trees (~30 MB, unrelated arcade prototype,
  zero references), `gpt.txt` (3.9 MB unreferenced dump, 0 secret hits),
  3 `docs/` duplicate files, `notes.txt` (stale scratch), 1 orphaned
  `requirements.txt` line (streamlit). Total ~33.7 MB.
- Preserved: all 42 `scripts/*.py` (no exact duplicates by md5), all
  artifacts/datasets/fixtures/results evidence.

### Developer tooling (R7, R9)

- New root `README.md` (what/where/setup/run/test/structure/limitations/V2
  pointers; all 13 referenced paths verified), `frontend/.env.example`
  (localhost base only, no secrets; `.gitignore` negation verified both ways),
  root `Makefile` (`backend-dev`, `frontend-dev`, `test-python`,
  `test-frontend`, `typecheck`, `lint`, `build`, `verify`).
- R9 (this stage, the only authorised tooling change): interpreter preflight
  + `--reload-dir` scoping — see §9. No formatter/linter introduced for
  Python (documented as-is per plan); frontend keeps eslint + tsc.

### Verification (R8, R9)

- R8 ran the full battery in two environments (working tree + fresh
  `/tmp/r8fresh` built from pinned requirements): pytest 67 passed + 4
  xfailed, node 21/21, tsc 0, lint 0 errors, build success, live API smoke,
  golden equivalence, artifact/dataset integrity, hygiene/secret scans.
- R9 re-ran the complete battery after the Makefile fix (§5). No behaviour
  change; no new regression.

---

## 4. Final Architecture

Actual final repository layout (top level):

```text
f1-in-race-prediction_main/          # one root Git repository
├── api/
│   ├── main.py                      # FastAPI assembly only
│   ├── routes.py                    # HTTP routing (4 endpoints)
│   ├── schemas.py                   # request contracts
│   └── services/prediction_service.py  # use cases → ml.inference
├── ml/
│   ├── __init__.py  config.py  features.py  inference.py
├── frontend/
│   ├── app/page.tsx                 # 114-line composition
│   ├── features/prediction/{hooks,lib,components}/
│   ├── components/prediction/       # pre-existing ControlsPanel/Tabs/Chart
│   └── lib/                         # api.ts, types, helpers (+ tests)
├── scripts/                         # 42-file pipeline, paths/imports intact
├── tests/ + tests/fixtures/         # pytest suite + golden fixture
├── data/processed/ + data/interim/  # 14 tracked dataset CSVs
├── data/raw/fastf1_cache/           # 6.6 GB source cache, local + ignored
├── results/models/                  # 30 tracked model .pkl
├── results/{analysis,baselines,comparisons,data_quality,debug}/
├── docs/                            # audit + this report + V2 plans
├── Makefile  README.md  requirements.txt  requirements-test.txt
└── .fastf1_cache/                   # runtime HTTP cache, local + ignored
```

Request path (verified by route inspection + live traffic):

```text
Next.js
   |
   v
FastAPI routes (api/routes.py)
   |
   v
Prediction service (api/services/prediction_service.py)
   |
   v
ml.inference
   |
   +--> legacy model artifacts (results/models/*_multilap, 30 .pkl)
   +--> legacy processed datasets (data/processed + data/interim, 14 CSVs)
```

Where things live: **scripts** in `scripts/` (data/cleaning/models/
models_weather/baselines/analysis/results/predict/utils/dev); **tests** in
`tests/` (Python) and `frontend/{lib,features/...}/` (node:test, no extra
deps); **docs** in `docs/`; **data** in `data/` (tracked processed/interim
CSVs; ignored raw cache); **results** in `results/` (tracked models +
experiment evidence). No Phase-1 Parquet/canonical layers exist — §10
assesses that they can be added alongside, not that they are present.

---

## 5. Behaviour Preservation Evidence

R9 fresh runs (this stage; interpreter `/tmp/r8fresh/bin/python` = py3.11,
sklearn 1.8.0, xgboost 3.2.0, fastapi 0.135.1 — pinned per
`requirements.txt`):

| Check | Result |
|---|---|
| Python suite (`pytest tests/ -q`) | **67 passed, 4 xfailed, 0 failed** (4.28 s) |
| Frontend node tests (3 files) | **21 passed, 0 failed** |
| Golden fixture coverage | 6 races × (ensemble + 3 families) × 5 checkpoints; winners/ranks/top-5 exact, raw probs within 1e-9 — green inside the suite |
| Golden fixture SHA | `8e23031a…c1f65302` — **unchanged since R0** |
| Model artifacts | **30/30 `.pkl` present**, all 15 family×checkpoint tuned artifacts load + score in-suite; `results/` + `data/` show zero Git modifications |
| Datasets | **14/14 CSVs present** (7 processed + 7 interim); schema/inventory/winner-integrity tests green; 104 races, 2019–2023 |
| Frontend build / typecheck / lint | `tsc --noEmit` exit 0; `npm run lint` **0 errors + 1 kept warning** (`barClassName`, pre-existing, deliberately retained); `npm run build` success (static `/`, `/_not-found`) |
| Live API verification | uvicorn `:8137`: `/health` 200 `{"status":"ok"}`; `/races` 200 (**104 races**); Bahrain 2023 ensemble 200 (**VER/VER, lap 25, 3/3 agreement, XGB conf 0.8051** — identical to fixture); hgb single-model 200 |
| Fresh environment | R8-built `/tmp/r8fresh` from pinned requirements resolves exactly and runs the suite green (9.67 s in R8); R9 battery above ran in that same env |
| `py_compile` | `api ml tests scripts` — exit 0 |

Passing vs expected-xfail: the **4 xfails are exactly the Monaco 2022
markers**, all failing-as-expected with intact rationale (NaN serialization
defect, §6). No other xfails or skips. The only warnings are
upstream Starlette/anyio deprecation notices and cosmetic node
typeless-package notes.

---

## 6. Known Legacy Limitations

Retained intentionally. These are **NOT** Foundation failures — they are
deferred V2 work, preserved exactly so later phases can address them against
a truthful baseline:

- **Monaco 2022 NaN serialization defect**: NaN `tyre_life_x` values in
  lap-25 source rows flow into the `top5` payload; Starlette `JSONResponse`
  raises `ValueError: Out of range float values are not JSON compliant` →
  HTTP 500 on both prediction endpoints for this race. Preserved and
  re-verified in R9 (TestClient 500, identical traceback class).
- **GroupKFold is not temporal backtesting** (leakage across seasons
  possible).
- Current winner outputs are **independent binary probabilities/scores**,
  not guaranteed to form a mutually exclusive race-level probability
  distribution.
- Data coverage remains **2019–2023**; prediction checkpoints remain fixed
  at **[5, 10, 15, 20, 25]**.
- Current ensemble is legacy **majority vote with XGBoost tie/confidence
  semantics** (`confidence_value` = XGBoost probability of the voted winner).
- **No** calibration, **no** RaceState, **no** replay, **no** Monte Carlo,
  **no** strategy, **no** What-If, **no** MLOps, **no** V2 Model Lab.

---

## 7. Removed Legacy Material

Truthfully summarised (per-item evidence in audit §17.1; none of this was
production code serving the supported path):

- **Streamlit retirement** (`app.py`, `legacy/streamlit_app.py`, `legacy/`
  dir): safe because the parity table shows every capability (race/
  checkpoint/model selection, same ensemble rule, probability view, actual
  comparison, top-5) exists in Next.js+FastAPI, nothing Streamlit-only was
  found, and the legacy copy could not even run (broken ROOT-relative paths).
- **Duplicate replay prototype removal** (both `f1-race-replay-main/` trees):
  safe because the trees were byte-identical to each other, are an unrelated
  arcade/GUI project, and have zero references from app/tests/scripts.
- **`gpt.txt` removal** (3.9 MB): safe because it is an unreferenced metrics-
  narration dump with zero secret-pattern hits and no runtime value.
- **Duplicate docs/junk cleanup** (`docs/` copies of root docs, `notes.txt`,
  nested `.git`s, `.DS_Store`, `__pycache__`, orphaned Windows venv): safe
  because originals/bundles were kept or the content was generated and
  regenerable (`.next` rebuilt via `npm run build`).
- **FastF1 cache Git untracking** (1113 blobs, index-only): safe because the
  6.6 GB local cache is intact, ignored going forward, reproducible session
  data (not source of truth — the API/tests use tracked processed CSVs), and
  history was not rewritten.

---

## 8. Repository / Git State

- **One root Git repository** (`e7d3467` baseline commit exists from outside
  the agent session; R3–R9 work sits uncommitted on top — see §12).
  `find -name .git` returns only `./.git`; no nested repos.
- **Cache policy**: `.fastf1_cache/` (runtime HTTP cache) and
  `data/raw/fastf1_cache/` (6.6 GB reproducible source cache) remain
  **local but ignored/untracked** — `git check-ignore` hits both; the index
  holds **0** `.ff1pkl` files (1113 blobs staged as deletions).
- **No Git LFS** for the reproducible cache (documented in `.gitignore`:
  neither cache belongs in Git or LFS).
- **Generated-artifact ignore policy**: `node_modules/`, `.next/`,
  `__pycache__/`, `*.pyc`, venvs, coverage, logs, temp files ignored; the
  index holds no DS_Store/pycache/.next/node_modules/venvs. Datasets, model
  `.pkl`, results evidence, and the golden fixture are explicitly protected
  by a do-not-ignore note.
- **Environment-file policy**: real `.env*` files ignored
  (`frontend/.env.local` verified ignored — localhost pin only);
  `frontend/.env.example` provided for tracking (verified trackable via the
  `.gitignore` negation). **No `.env.local` in any commit.**
- **Public-repository hygiene scan** (R9): secret/key/token pattern grep
  over the worktree (excl. node_modules/.git/.next/cache blobs) → **0 hits**;
  third consecutive clean stage. No machine-specific paths in source; no
  `>50 MB` entries staged or tracked going forward (they exist only in HEAD
  history via the cache being untracked). History was never rewritten.

---

## 9. Developer Workflow

Canonical commands (all verified; Python targets require a working
interpreter — see preflight note):

```bash
# setup
pip install -r requirements.txt            # app deps (pinned: sklearn 1.8.0, xgboost 3.2.0, …)
pip install -r requirements-test.txt       # test-only deps (pytest, httpx)
cd frontend && npm install                 # frontend deps

# backend / frontend development
make backend-dev                            # uvicorn api.main:app --reload (watches api/ ml/), :8000
make frontend-dev                           # Next.js dev server
PYTHON=<venv-python> make backend-dev       # override when bare `python3` is a shim (this machine)

# tests / checks / build
make test-python                            # pytest tests/ -q  →  67 passed, 4 xfailed
make test-frontend                          # node --test (3 files)  →  21 passed
make typecheck                              # tsc --noEmit  →  exit 0
make lint                                   # eslint  →  0 errors, 1 kept warning
make build                                  # next build  →  success
make verify                                 # full battery  →  exit 0 (with valid PYTHON)
```

### R9 Makefile tooling fix (authorised §3 of the R9 brief)

**Preflight.** `check-python` probes the configured interpreter with
`$(PYTHON) -c 'print("py-preflight-ok")'` and fails non-zero unless the exact
marker returns on stdout. An exit-0-only shim therefore fails (no output ≠
success). `backend-dev` and `test-python` depend on it; `PYTHON ?= python3`
override retained; no machine-specific path; no new dependency manager.

- Broken/no-op shim: `make check-python` → `error: PYTHON='python3' is not a
  functional Python interpreter…`, make **Error 1** (verified).
- Valid override: `make PYTHON=/tmp/r8fresh/bin/python check-python` → pass
  (verified); `make PYTHON=/tmp/r8fresh/bin/python verify` → **exit 0**.
- `backend-dev` recipe validity: `make -n` shows the full uvicorn command;
  the identical module target booted live on `:8137` in R9 smoke.

**Reload-dir.** The R8 recommendation was accepted: the pinned
**uvicorn 0.41.0 supports `--reload-dir`** (verified via `--help`), and
`backend-dev` now passes `--reload-dir api --reload-dir ml`, so the watcher
no longer scans the repository root containing the 6.6 GB
`data/raw/fastf1_cache/`. `api/` + `ml/` cover exactly the backend runtime
(schemas/routes/service + config/features/inference). Strictly tooling-only:
no route, schema, service, or inference code was touched.

---

## 10. Phase 1 Readiness

Assessed against `V2_PHASE_1_DATA_PLATFORM.md` (D0–D3 scope only):

- **Is the repository ready for D0?** **Yes.** D0 requires reading the
  Foundation plan + this report, running relevant regression tests, and
  confirming the application is operational with a understood post-refactor
  structure — all true (§5, §4). The single expected gap noted in R8 (this
  report not yet existing) is now closed.
- **Are existing regression tests sufficient to protect the legacy app while
  the new data platform is introduced?** **Yes.** 67 Python tests
  (contract, golden equivalence, model loading, dataset integrity, ensemble
  branches, defect markers) + 21 frontend tests + tsc/lint/build gates pin
  current behaviour; fixture sha is asserted in-suite so silent prediction
  drift fails loudly.
- **Is FastF1 cache handling suitable?** **Yes.** Both caches local-only,
  ignored, documented in README + `.gitignore`; the processed canonical-data
  work in Phase 1 must not depend on any developer's cache layout, and the
  current layout already satisfies that (API/tests run offline from tracked
  CSVs — verified in R7/R8).
- **Can future Parquet/canonical layers be introduced without replacing the
  legacy dataset immediately?** **Yes.** `data/processed/laps/season=…`
  partitioning can coexist with the legacy checkpoint CSVs; the `scripts/`
  stage layout can evolve into ingestion modules; `ml/` runtime boundaries do
  not conflict with future ingestion/validation layers.
- **Are current scripts/data paths understood?** **Yes** — centralised
  `ml/config.py` path helpers, audited `scripts/` inventory (audit §§1.3,
  14.1), and canonical dataset/model locations in README.
- **Any blockers to D0–D3?** **None.** No code, schema, or data blockers
  found. (D1+ will need live FastF1/network access for source auditing — an
  environment property of that phase, not a Foundation defect.)

No Phase-1 answers were implemented — assessment only, per scope.

---

## 11. Foundation Definition of Done

Evaluated against every exit criterion in `V2_FOUNDATION_REFACTOR.md` §18
(R0–R8 stage DoDs are additionally all recorded complete in the audit,
§§11–19). Scale: **PASS** / **DEFERRED-BY-DESIGN** / **FAIL**.

| # | Criterion | Verdict |
|---|---|---|
| 1 | Existing application functionality preserved | **PASS** (§5: identical predictions, contract, UI render) |
| 2 | Existing prediction behaviour has regression protection | **PASS** (golden suite + tol + sha assertion) |
| 3 | Clear repository structure | **PASS** (§4) |
| 4 | Clear ML/backend/frontend boundaries | **PASS** (route→service→`ml.inference`; `features/prediction/`) |
| 5 | Duplicate prediction logic reduced | **PASS** (constants single-sourced; Streamlit/replay dupes removed) |
| 6 | Generated/cache files separated from source | **PASS** (ignore policy + cache untracking, §8) |
| 7 | Legacy Streamlit status resolved | **PASS** (retired on parity evidence, §7) |
| 8 | Automated tests protect important behaviour | **PASS** (67+21, gates green) |
| 9 | Setup/development instructions accurate | **PASS** (README + Makefile, all commands verified) |
| 10 | Frontend builds successfully | **PASS** (R9 build green) |
| 11 | Backend starts successfully | **PASS** (live `:8137` smoke) |
| 12 | Existing model artifacts load successfully | **PASS** (15/15 tuned artifacts in-suite) |
| 13 | Existing prediction endpoints work | **PASS** (health/races/ensemble/single-model) |
| 14 | Golden prediction fixtures match | **PASS** (sha unchanged; equivalence green) |
| 15 | This report exists | **PASS** (this file) |
| 16 | Known limitations documented, not silently "fixed" | **PASS** (§6 + Monaco xfail markers) |
| 17 | No V2 product features implemented | **PASS** (no RaceState/replay/Monte Carlo/strategy/What-If/DB/MLOps/Model Lab; Phase-1 layers absent by design) |

**Foundation DoD verdict: COMPLETE — zero FAIL items.** (Two plan-quality
gates are implicitly DEFERRED-BY-DESIGN: DOM-level frontend interaction
testing, which would require a new test framework, and live client/server
round-trip testing beyond TestClient + manual smoke — both documented as
known gaps in audit §13.5, neither blocking.)

---

## 12. Exact Phase 1 Handoff

**NEXT AUTHORISED PLAN:** `V2_PHASE_1_DATA_PLATFORM.md`

**NEXT AUTHORISED STAGE:** **D0 only** — Verify Foundation Refactor
(read the Foundation plan + this report, run the regression suite, confirm
the application is operational, understand the post-refactor structure).
If D0 finds the foundation materially broken, STOP — do not layer the data
platform over it.

**Phase 2** (`V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md`) and **Phase 3**
(`V2_PHASE_3_MODEL_LAB.md`) remain **out of scope**. No D1+ ingestion,
schema, Parquet, telemetry, feature, or Model Lab work is authorised by this
handoff.

---

## Appendix A — R9 verification log (commands run from repo root)

```bash
/tmp/r8fresh/bin/python -m pytest tests/ -q
# 67 passed, 4 xfailed, 0 failed in 4.28s
node --test lib/predictionHelpers.test.ts lib/api.test.ts \
  features/prediction/lib/predictionTransforms.test.ts   # (from frontend/)
# 21 passed, 0 failed
/tmp/r8fresh/bin/python -m compileall -q api ml tests scripts  # exit 0
./node_modules/.bin/tsc --noEmit -p .                            # (frontend/) exit 0
npm run lint                                                     # 0 errors, 1 kept warning
npm run build                                                    # success
make PYTHON=/tmp/r8fresh/bin/python verify                       # exit 0
make check-python                  # Error 1 with guidance (broken shim)
make PYTHON=/tmp/r8fresh/bin/python check-python                 # pass
shasum -a 256 tests/fixtures/legacy_predictions.json
# 8e23031af4a680a4d493e9a6052d342defccfbf4c6db1d89c3ed31c1f6530228
/tmp/r8fresh/bin/python -m uvicorn api.main:app --port 8137     # live smoke green
git status --short  # §12 of the R9 completion report (in chat): only intended paths
secret-pattern grep excl. caches/node_modules/.git              # 0 hits
```

No fixture regeneration was performed at any point in R9.
