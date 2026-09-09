# V2 Repository Audit — R0 Baseline & Inventory

> **Stage:** R0 — Baseline & Inventory (V2_FOUNDATION_REFACTOR.md)
> **Date:** 2026-09-08
> **Historical record:** this document records the R0 baseline state
> (pre-refactor). Current status lives in `README.md`.
> **Rule compliance:** No refactoring performed. No models retrained or modified.
> No prediction behaviour changed. No V2 features implemented.
> Only additions: this document and `tests/fixtures/legacy_predictions.json`
> (golden baseline fixtures generated from the current implementation).

---

## 1. Current architecture (actual, verified)

```text
FastF1 (cached sessions, data/raw/fastf1_cache, 2019-2023)
  ↓  scripts/data/build_dataset_multi_race*.py
Interim checkpoint snapshots (data/interim/lap{5,10,15,20,25}/)
  ↓  scripts/cleaning/clean_dataset*.py
Clean checkpoint datasets (data/processed/lap{5,10,15,20,25}/base/dataset_clean.csv)
  ↓  scripts/models/*, scripts/models_weather/*, scripts/baselines/*
Trained pipelines (results/models/{logreg,hgb,xgboost}_lap{lap}_multilap/model_{tuned,}.pkl)
  ↓  api/services/predictor.py  (CHECKPOINTS=[5,10,15,20,25], MODELS=[logreg,hgb,xgb])
FastAPI backend (api/main.py)  →  Next.js frontend (frontend/)  |  Streamlit app (app.py)
```

### 1.1 Backend (`api/`)

- `api/main.py` (50 lines): FastAPI app `F1 Race Winner Predictor API`, CORS wide open.
  Exactly 4 routes, matching the plan's expectation:
  `GET /health`, `GET /races`, `POST /predict/ensemble`, `POST /predict/single-model`.
- `api/services/predictor.py` (242 lines): single module doing dataset access,
  model discovery/loading (`model_tuned.pkl` preferred, `model.pkl` fallback),
  feature selection (`FEATURE_COLS`, 10 columns), prediction, race filtering,
  majority-vote ensemble with XGBoost tie-break, and response formatting.
- Pydantic request models are inline in `main.py` (`RaceRequest`, `SingleModelRequest`).
- No tests, no schemas/ layer, no config layer. `ROOT` derived from file path
  (`parents[2]`), so backend only works from this exact checkout layout.

### 1.2 Frontend (`frontend/`)

- Next.js 16.1.6 + React 19 + TypeScript + Tailwind v4 + `motion` + `lucide-react`.
- Routes: single page (`app/page.tsx`, ~1200+ lines) with tab views
  (overview / table / chart / drivers) for ensemble and single-model modes.
- Already partially modularised: `components/prediction/` (ControlsPanel,
  PredictionTabs, ProbabilityChart), `lib/api.ts`, `lib/predictionTypes.ts`,
  `lib/predictionHelpers.ts`.
- API access centralised in `lib/api.ts`; base URL from
  `NEXT_PUBLIC_API_BASE`, default `http://127.0.0.1:8000`
  (also pinned in `frontend/.env.local`).
- No frontend tests. ESLint: 0 errors, 7 unused-var warnings (see §5).

### 1.3 ML / data pipeline (`scripts/`, `data/`, `results/`)

- `scripts/data/`: FastF1 ingestion (`build_dataset_multi_race*.py`,
  single-race + missing-race repair + weather variants + field inspector).
- `scripts/cleaning/`: `clean_dataset*.py` (base / multilap / weather).
- `scripts/models/`: train + tune per family (logreg / hgb / xgboost, multilap).
- `scripts/models_weather/`: weather-variant training/tuning.
- `scripts/baselines/`: baseline + CV evaluation (incl. multilap + weather).
- `scripts/analysis/`: error analysis, feature importance, accuracy-vs-lap plots,
  winner-probability evolution.
- `scripts/results/`: comparison-table generators (base / weather / master).
- `scripts/predict/`: `predict_race_winner*.py` incl. ensemble CLI.
- `scripts/utils/`: interim append, race-set compare, FastF1 smoke test.
- `scripts/dev/`: mac/windows setup + run scripts (see §7 blockers).
- `scripts/venv/`: **Windows-only venv** (pyvenv.cfg points at
  `C:\Users\Atharva\...`, `Scripts/` layout) — unusable on macOS/Linux.
- Datasets: `data/processed/lap{5,10,15,20,25}/base/dataset_clean.csv`
  (lap10: 2067 rows incl. header → 2066 data rows; 104 races),
  plus lap10 weather + snapshots variants; `data/interim/` mirrors per lap.
  `data/models/` and `data/sequences/` are **empty directories**.
- Models: `results/models/` holds 21 dirs. The API uses only
  `{logreg,hgb,xgboost}_lap{5,10,15,20,25}_multilap` (15 dirs, each with
  `model.pkl` + `model_tuned.pkl` + CV metrics/tuning CSVs).
  Non-multilap (`logreg_lap10`, `hgb_lap10`, `xgboost_lap10`) and
  `*_weather_lap10*` dirs are legacy artifacts not loaded by the API.
- Results: `results/{analysis,baselines,comparisons,data_quality,debug}/`
  with CV summaries, master comparisons (.csv + .md), quality/integrity
  reports, feature-importance artifacts. Preserved as evidence; not deleted.

### 1.4 Legacy / duplicated apps

- `app.py` (root Streamlit app, 595 lines) and `legacy/streamlit_app.py`
  are **byte-identical** (`diff` clean) and duplicate the FastAPI predictor
  logic (same `FEATURE_COLS`, `CHECKPOINTS`, `MODELS`, majority-vote +
  XGBoost tie-break), plus matplotlib charts.
- The legacy copy is **non-functional as placed**: its `ROOT` resolves to
  `legacy/`, which contains no `data/` or `results/`, so dataset/model
  lookup fails. The root `app.py` resolves correctly.
- `repo/f1-race-replay-main/` and `legacy/repo/f1-race-replay-main/` are
  **duplicates** (differ only by `.DS_Store`); an unrelated arcade/GUI race
  replay project, each with its own nested `.git`.
- `req.md`, `notes.txt`, `section5report.txt` exist **identically at both
  root and `docs/`** (doc duplication).
- `gpt.txt` (3.9 MB) at root: unexplained large file, contents not audited.

---

## 2. What currently works (verified this stage)

| Check | Command (run from repo root unless noted) | Result |
|---|---|---|
| Dataset load | `python -c` pandas read of lap10 clean CSV | OK: 2066 rows, 104 races, 2019–2023 |
| Model load (logreg/hgb/xgb) | `joblib.load` of `_multilap/model_tuned.pkl` | OK (with sklearn-version warning outside pinned env, see §7) |
| `GET /health` | TestClient + live uvicorn `:8123` | 200 `{"status":"ok"}` |
| `GET /races` | TestClient | 200, 104 races |
| `POST /predict/ensemble` (Bahrain 2023) | TestClient | 200, final VER / actual VER, lap 25, 3/3 agreement |
| `POST /predict/single-model` ×3 (Bahrain 2023) | TestClient | 200 for logreg/hgb/xgboost |
| Golden fixture generation (6 races × ensemble + 3 singles × 5 laps) | direct predictor calls | OK → `tests/fixtures/legacy_predictions.json` (90 KB, 8 faithful NaN tokens, see §6) |
| Python compile check | `py_compile` on api, app, key scripts | OK |
| Frontend `tsc --noEmit` | `(frontend) ./node_modules/.bin/tsc --noEmit -p .` | PASS, exit 0 |
| Frontend `npm run lint` | `(frontend) npm run lint` | 0 errors, 7 unused-var warnings (§5) |
| Frontend `npm run build` | `(frontend) npm run build` | SUCCESS (static prerender `/`, `/\_not-found`) |
| Live uvicorn boot | `python -m uvicorn api.main:app --port 8123` | Boots; `/health` 200 (but see §7 NaN 500 bug) |

No test suite exists (no `test_*.py`, no frontend tests) — there was nothing to run.

---

## 3. What should remain (reusable)

- Checkpoint datasets (`data/processed/...`, `data/interim/...`) — training/eval evidence.
- `results/models/*_multilap` tuned pipelines — runtime artifacts the API loads.
- `results/{baselines,comparisons,data_quality,analysis}` — historical evidence.
- Predictor semantics in `api/services/predictor.py` + `app.py` (feature list,
  checkpoint list, ensemble rule) — behaviour to preserve, not logic to copy.
- FastAPI route contract (`/health`, `/races`, `/predict/ensemble`,
  `/predict/single-model`) — frontend depends on it.
- Frontend page flow + `lib/api.ts`, types/helpers, prediction components.
- `scripts/` pipeline (ingestion → cleaning → training → evaluation) as
  operational reference, even where paths need centralising later.
- `docs/req.md` reproducibility guide content (dedupe with root copy in R1/R6).

---

## 4. What requires restructuring (structural, not behavioural)

1. `api/services/predictor.py` mixes dataset access, model loading, feature
   selection, inference, ensemble voting, and response shaping in one module.
2. Pydantic models inline in `api/main.py`; no schemas/services/core split.
3. Hardcoded `FEATURE_COLS` / `CHECKPOINTS` / `MODELS` duplicated across
   `api/services/predictor.py` and `app.py` (+ legacy copy) — triplicated.
4. `app/page.tsx` is ~1200+ lines (all modes/tabs/cards in one client component).
5. No backend or frontend tests; no `tests/` layout (created only fixtures in R0).
6. No root git repo (see §7); nested `.git` under `frontend/`, `repo/...`, `legacy/repo/...`.
7. Root `.gitignore` lacks FastF1 cache, `*.pkl`/dataset policy, coverage;
   junk present (`.DS_Store`, `__pycache__`, `frontend/.next/` tracked-in-place).
8. `scripts/venv/` (Windows venv) committed; setup scripts assume a root `venv/`
   that does not exist; `run_mac.sh` depends on macOS `osascript` Terminal.
9. Empty placeholder dirs `data/models/`, `data/sequences/` with no README/policy.
10. Doc duplication (root ↔ `docs/`) and oversized unexplained `gpt.txt`.

---

## 5. Existing failures / warnings (verbatim, pre-existing)

1. **HTTP 500 on some races (pre-existing bug, NOT fixed in R0):**
   `POST /predict/ensemble` and `/predict/single-model` for
   `2022 Monaco Grand Prix` return 500 on a live server:
   `ValueError: Out of range float values are not JSON compliant`.
   Root cause: NaN `tyre_life_x` values in the lap-25 dataset rows flow into
   the `top5` response payload; Starlette `JSONResponse` cannot serialise NaN.
   Affects all 3 models for this race. 5/6 fixture races return 200.
2. **sklearn version warning outside pinned env:** unpickling
   `model_tuned.pkl` (trained with sklearn 1.8.0) under sklearn 1.6.1 emits
   `InconsistentVersionWarning` (SimpleImputer/StandardScaler/Pipeline/OneHotEncoder).
   Baseline runs in §2/§6 used an isolated env with sklearn==1.8.0 + xgboost==3.2.0
   (matching `requirements.txt`) — no warnings there.
3. **ESLint:** 0 errors, 7 warnings — unused `Table2`, `LayoutGrid`,
   `EnsembleSummaryRow`, `SingleSummaryRow`, `SingleLatest`, `isCorrect`,
   `barClassName` (in `frontend/app/page.tsx`).
4. **Legacy Streamlit copy broken paths** (§1.4) — fails dataset lookup as placed.
5. **No git identity:** repo root is not a git repository (`fatal: not a git repository`);
   no commit history exists at top level.

---

## 6. Golden prediction baseline (representative outputs)

Stored in `tests/fixtures/legacy_predictions.json` — generated 2026-09-08 from
the **unmodified** implementation via direct `run_ensemble_prediction` /
`run_single_model_prediction` calls (5 checkpoints × 3 models per race).
The file contains 8 bare `NaN` tokens that faithfully record actual outputs
(Monaco rows); it parses with Python `json` defaults but is not strict JSON —
flagged for R2 to handle without altering values.

| Race | Ensemble final | Actual | Match? | Singles (logreg/hgb/xgb latest) | HTTP |
|---|---|---|---|---|---|
| 2023 Bahrain GP | VER (3/3, XGB conf 0.8051) | VER | ✅ | VER/VER/VER | 200 |
| 2021 Abu Dhabi GP | HAM | VER | ❌ (recorded as-is) | HAM/HAM/HAM | 200 |
| 2019 German GP | HAM | VER | ❌ (recorded as-is) | HAM/HAM/HAM | 200 |
| 2022 Monaco GP | PER | PER | ✅ | PER/PER/PER | **500 (NaN bug)** |
| 2023 Las Vegas GP | PER | VER | ❌ (recorded as-is) | PER/PER/PER | 200 |
| 2020 70th Anniversary GP | VER | VER | ✅ | VER/VER/VER | 200 |

Coverage: seasons 2019/2020/2021/2022/2023; all 5 checkpoints; all 3 model
families; ensemble path; a repaired 2023 race (Las Vegas); a one-off event name
(70th Anniversary); one NaN-triggering race (Monaco 2022). Full per-checkpoint
summaries + latest top-5s are in the fixture file. "Wrong" predictions above are
the system's real current behaviour and must be preserved until the relevant V2
phases — they are characterisation data, not bugs to fix in the refactor
(except the NaN 500, which is a serving crash, still out of R0 scope to fix).

---

## 7. Environment & blockers documented

- `requirements.txt` pins Python 3.14-era deps (fastf1 3.7.0, sklearn 1.8.0,
  xgboost 3.2.0, fastapi 0.135.1, streamlit 1.55.0, …).
- No working root `venv/` exists. `scripts/venv/` is a Windows venv, unusable here.
- A pre-existing user venv (`~/.venvs/f1-in-race-prediction`, py3.9) has
  fastf1/pandas/sklearn-1.6.1 but **lacks** fastapi/uvicorn/xgboost/streamlit —
  insufficient for the full app.
- R0 verification used an **isolated temp env** (`/tmp/r0baseline`, py3.11,
  fastapi + uvicorn + pandas + sklearn==1.8.0 + xgboost==3.2.0 + httpx) so the
  repo was not touched. Node v22.23.1 / npm 10.9.8 used for frontend checks
  against the existing `frontend/node_modules`.
- `scripts/dev/setup_mac.sh` / `run_mac.sh` were inspected only, not executed
  (they would create `venv/` and open Terminal windows via `osascript`).
- Data coverage verified: exactly seasons **2019–2023**, 104 races in lap-10
  dataset — consistent with the plan's "approximately" statement.
- Caches: root `.fastf1_cache/` (~100 MB, HTTP sqlite) is runtime cache;
  `data/raw/fastf1_cache/` (~6.6 GB, `.ff1pkl` session data) is source cache.
  Plan's R1 hygiene applies to the former, never the latter.

---

## 8. Known ML limitations (documented, NOT fixed — per plan §2.5)

1. GroupKFold CV is not true temporal validation (leakage across seasons possible).
2. Per-driver win probabilities are independent binary outputs, not a
   race-level distribution (rows need not sum to 1).
3. Ensemble is a simplistic latest-checkpoint majority vote with XGBoost
   tie-break; `confidence_value` is the XGBoost driver's probability, not a
   calibrated race-level confidence.
4. Predictions exist only at fixed checkpoints [5, 10, 15, 20, 25] — no
   arbitrary-lap inference.
5. Feature set is a fixed 10-column list with pipeline-imputed NaNs; NaN
   source values can leak into API responses (§5.1).
6. Methodology/tuning/CV splits are historical artifacts; limitations stay
   until their V2 phases.

---

## 9. Migration risks (for R1–R8)

1. **No root git history** — R1/R8 "one intentional Git root" needs `git init`
   + nested-`.git` triage (frontend has uncommitted changes; two arcade-replay
   nested repos are duplicates).
2. Path coupling: `ROOT = Path(__file__).resolve().parent(s)` in
   `api/services/predictor.py`, `app.py`, and every script — moving files
   breaks dataset/model resolution unless a path/config source of truth lands first.
3. Pickle compatibility: pipelines unpickled with sklearn 1.8.0/xgboost 3.2.0;
   any env or relocation change must re-run golden fixtures before/after.
4. `model_tuned.pkl`-preferred loading: moving/renaming model dirs changes
   which artifact loads (`model.pkl` fallback) — silent behaviour change risk.
5. Feature-order sensitivity: consolidating `FEATURE_COLS` must preserve order
   expected by saved pipelines.
6. NaN-serving crash (§5.1) will trip any new regression test that asserts
   HTTP 200 for all races — fixtures must encode the current 500 behaviour
   until a deliberately-approved fix lands.
7. `frontend/.next/` + `node_modules/` present in place; `.env.local` pins
   localhost — CI/dev wiring must not depend on them.
8. Large/unversioned data (6.6 GB FastF1 cache) and `gpt.txt` (3.9 MB) need an
   explicit artifact policy before any `.gitignore`/cleanup step.

---

## 10. Conflicts with V2_FOUNDATION_REFACTOR.md assumptions

1. Plan §3 says "Historical data primarily covers 2019–2023" / "approximately"
   Lap 5–25 — verified exact: 2019–2023, 104 races, laps {5,10,15,20,25}. No conflict.
2. Plan implies a single repo to clean — **actual: no git repo at root at all**,
   with 3 nested `.git` instances. R1's "Git root" task is really `git init` + triage.
3. Plan §7 asks "does Streamlit contain anything unique?" — finding: the two
   Streamlit files are identical to each other, and the legacy copy cannot run
   (broken ROOT-relative paths), so parity analysis is API+root-app vs Next.js.
4. Plan's target `docs/` layout (`architecture/`, audit, report) does not exist
   yet; actual `docs/` holds duplicated copies of root docs.
5. Plan R0 example fixture path `tests/fixtures/legacy_predictions.json` was
   adopted exactly; note the NaN strict-JSON caveat (§6) the plan does not mention.
6. `data/models/` + `data/sequences/` (plan's suggested data layout names) exist
   but are **empty** — no content to migrate there.

---

## 11. R0 Definition of Done — status

- [x] Current architecture documented (§1)
- [x] Application run / blockers documented (§2, §5, §7)
- [x] Model locations known (§1.3)
- [x] Dataset locations known (§1.3)
- [x] API behaviour recorded (§1.1, §2, §6)
- [x] Frontend behaviour recorded (§1.2, §2)
- [x] Representative prediction outputs captured (§6 + fixture file)
- [x] Migration risks documented (§9)

**R0 is complete. No source, model, dataset, or behaviour change was made.**
Awaiting explicit approval before R1.

---

## 12. R1 addendum — Repository Hygiene (2026-09-08)

### 12.1 Data / artifact policy (classification)

| Class | Paths | Policy |
|---|---|---|
| SOURCE CODE | `api/`, `app.py`, `frontend/app|components|lib`, `scripts/*/*.py`, configs | Tracked; refactored in R3–R5 |
| DATASET | `data/processed/`, `data/interim/`, `data/raw/fastf1_cache/` | Tracked; never deleted; not in `.gitignore` |
| MODEL ARTIFACT | `results/models/*_multilap/` (runtime) + legacy `*_lap10`/`_*weather*` dirs | Tracked; preserved; relocation only with fixture re-verification (R3) |
| EXPERIMENT RESULT | `results/{analysis,baselines,comparisons,data_quality,debug}/` | Tracked; preserved as evidence |
| GOLDEN FIXTURES | `tests/fixtures/legacy_predictions.json` | Tracked; byte-identical since R0 (sha256 `8e23031a…c1f65302`) |
| CACHE (runtime) | `/.fastf1_cache/` | Ignored, kept in working tree for offline runs |
| CACHE (source) | `data/raw/fastf1_cache/` | Tracked source cache (see §7) |
| GENERATED BUILD | `frontend/.next/`, `frontend/node_modules/`, `__pycache__/`, `*.pyc` | Ignored; `.next`/`__pycache__` removed in R1, regenerable |
| ENVIRONMENT | `venv/`, `.venv/`, `scripts/venv/` (removed, was orphaned Windows env) | Ignored; recreated via `scripts/dev/setup_*` |
| TEMPORARY/JUNK | `.DS_Store`, `*.tmp/*.bak/*.swp`, `*.log`, coverage output | Ignored; `.DS_Store` removed in R1 |

### 12.2 Nested-repo / duplicate-tree verdicts (inspected before action)

- `frontend/.git`: single boilerplate commit (`a999772`); real app work
  uncommitted in worktree. History bundled to
  `/tmp/r1_git_backups/frontend.git.bundle`; metadata removed.
- `repo/f1-race-replay-main/.git` and `legacy/repo/f1-race-replay-main/.git`:
  same single commit (`87c0203`), clean trees, and the two working trees are
  **identical** (`diff -rq --exclude=.git` clean). Histories each bundled to
  `/tmp/r1_git_backups/{repo,legacy}-replay.git.bundle`; metadata removed.
  The duplicate trees themselves are **preserved** — consolidation is R6 scope.
- `legacy/streamlit_app.py` vs `app.py`: byte-identical, preserved (R6 scope).

### 12.3 Removals (generated/junk only, no source/data/models/docs)

- 3 nested `.git` dirs (histories bundled first, §12.2).
- `scripts/venv/` (13 MB orphaned Windows venv; zero references; setup
  scripts create root `venv/`, which never existed here).
- `frontend/.next/` (regenerated during R1 verification via `npm run build`).
- 13× `.DS_Store`, 8× `__pycache__` dirs, 10× `*.pyc`.

### 12.4 Git root

- `git init` at project root → single intentional root; no nested repos remain
  (`find -name .git` returns only `./.git`).
- **No commit made in R1** (not authorised); everything currently untracked.
  Note: `data/` contains the 6.6 GB source cache — commit/packaging strategy
  (e.g. LFS or cache exclusion) is deferred, not decided here.
- Root `.gitignore` extended: `/.fastf1_cache/`, `.venv/`, `scripts/venv/`,
  coverage outputs, temp files; plus an explicit do-not-ignore artifact note.

### 12.5 R1 Definition of Done — status

- [x] Generated junk removed (§12.3)
- [x] Git structure clear — one root, no nested repos (§12.4)
- [x] `.gitignore` correct — caches/env/build ignored, datasets+models+results kept (§12.1)
- [x] Valuable model artifacts remain (30 `.pkl`, verified §12.6)
- [x] Valuable evaluation artifacts remain (195 files under `results/`)
- [x] Historical datasets remain (14 CSVs under `data/processed`+`data/interim`)
- [x] FastF1 runtime cache not treated as source (ignored + classified CACHE)
- [x] Application behaviour unchanged (baseline re-verified, §12.6)

### 12.6 R1 verification record (post-cleanup)

- Fixture file sha256 unchanged: `8e23031a…c1f65302` (byte-identical).
- Artifact counts unchanged: 14 dataset CSVs, 30 model `.pkl`, 195 `results/` files.
- TestClient: `/health` 200; `/races` 200 (104 races); ensemble Bahrain 2023 →
  VER/VER 3/3 (matches fixture); singles logreg/hgb/xgboost → VER (match).
- Monaco 2022 still HTTP 500 on both endpoints — documented R0 baseline issue,
  intentionally not fixed in R1.
- Frontend `tsc --noEmit` pass; `npm run lint` 0 errors + same 7 warnings;
  `npm run build` success (fresh `.next` regenerated).
- `py_compile` on api/app/key scripts: OK.

**R1 is complete. Awaiting explicit approval before R2.**

---

## 13. R2 addendum — Characterisation & Regression Tests (2026-09-08)

### 13.1 Suite layout (new files only; zero production-code changes)

```text
tests/
├── conftest.py                   # harness: NaN-tolerant fixture loader, tolerances, shared fixtures
├── test_api_baseline.py          # A: 4-route contract, schemas, probability bounds
├── test_prediction_equivalence.py# B: recompute-vs-fixture for 6 races x (ensemble + 3 models)
├── test_model_loading.py         # C: all 15 family x checkpoint artifacts load + score
├── test_datasets.py              # D: schema, inventory (104 races, 2019-2023), winner integrity
├── test_ensemble.py              # E: majority / tie-break / fallback branches + reason strings
└── test_known_defects.py         # F+G: fixture sha256, NaN root cause, Monaco xfail markers
frontend/lib/
├── predictionHelpers.test.ts     # H: pure formatting/tone/naming helpers (node:test, no deps)
└── api.test.ts                   # H: endpoint URLs, methods, bodies, env override, errors
requirements-test.txt             # pytest==9.1.1, httpx==0.28.1 (test-only deps)
```

Run commands (interpreter must satisfy requirements.txt with
scikit-learn==1.8.0 / xgboost==3.2.0 plus requirements-test.txt):

```text
python -m pytest tests/ -q                    # backend + ML safety net
node --test lib/predictionHelpers.test.ts lib/api.test.ts   # frontend (from frontend/)
```

### 13.2 Tolerances

- Winners, ranks, top-5 order, reasons, counts, laps, 4dp-rounded summary
  probabilities: **exact** match.
- Raw probabilities: NaN-aware **abs tol 1e-9** (same artifacts + same libs
  are deterministic; the tol absorbs only FP/BLAS noise — any methodological
  change dwarfs it or flips exact checks).

### 13.3 NaN / Monaco handling

- Fixture kept byte-identical (sha256 `8e23031a…c1f65302` asserted in-suite);
  the 8 faithful bare-`NaN` tokens are parsed by the harness
  (`parse_constant` → `float('nan')`), never cleaned in the file.
- Monaco 2022: root cause pinned by passing tests (NaN `tyre_life_x` in
  lap-25 source rows and in the recomputed payload); HTTP-200 expectations
  are `xfail(strict=False)` markers — green-through-XPASS when deliberately
  fixed, never a 500 contract. Unknown-race behaviour pinned as HTTP 500
  (unhandled ValueError, both endpoints).

### 13.4 Verification record (post-R2)

- `pytest tests/`: **71 collected — 67 passed, 4 xfailed, 0 failed (~5 s)**.
- `node --test` frontend: **17 passed, 0 failed**.
- `py_compile` (api/app/key scripts): OK. `tsc --noEmit`: exit 0.
  `npm run lint`: 0 errors + the same 7 pre-existing warnings (test files add none).
  `npm run build`: success.
- Fixture sha256 unchanged; artifact counts unchanged; no prod file modified.

### 13.5 Known gaps (still risky, out of R2 scope)

- No DOM/component tests (would need vitest/jsdom or Playwright — deferred
  as framework churn); page rendering, race/checkpoint/model selection flows,
  chart rendering and loading/error states are covered only by tsc/lint/build.
- No live server/client round-trip test (TestClient is in-process); no
  Streamlit execution test (legacy copy has broken paths — R6 scope).
- Training/tuning/evaluation scripts are compile-checked only, never executed
  (would retrain / hit network).

### 13.6 R2 Definition of Done — status

- [x] Meaningful backend tests exist (A)
- [x] ML behaviour has regression protection (B, C, D, E)
- [x] Golden fixtures exercised with tolerances (B, G)
- [x] Critical frontend behaviour has basic protection (H: API layer + helpers; gates preserved)
- [x] Test commands documented (§13.1)
- [x] Tests pass against the pre-refactor behaviour (§13.4)

### 13.7 Recommended commit boundary (not committed — awaiting instruction)

```text
test: add legacy regression safety net (R2)
```

Scope when committed: `tests/`, `frontend/lib/*.test.ts`,
`requirements-test.txt`, `docs/V2_REPOSITORY_AUDIT.md` (§13). R0+R1 baseline
files (`tests/fixtures/`, §12) belong in the earlier `refactor: establish
legacy baseline` / hygiene boundary per the plan's Git strategy.

**R2 is complete. Awaiting explicit approval before R3.**

---

## 14. R3 addendum — Python/ML Restructuring (2026-09-08)

### 14.1 Dependency graph actually found (drove the plan)

- Scripts are standalone leaf entry points: zero cross-imports between
  `scripts/*/*.py`; the only in-repo import was
  `api/main.py → api.services.predictor`.
- Every script resolves the project root from its own location
  (`parents[2]`; one outlier in `scripts/utils/` uses `parents[1]` — untouched).
- `FEATURE_COLS` was copied verbatim in 6 places, `CHECKPOINTS` in 6,
  `MODEL_LABELS` in 3. Training scripts instead use a NUM_COLS/CAT_COLS
  split feeding their imputation/encoding pipelines — unifying those would
  need training execution (forbidden), so they are out of R3 scope.
- Physical `scripts/ → ml/` moves were rejected: same-depth relocation
  keeps `parents[2]` working, but it would break the documented
  `python scripts/...` CLI entry points (req.md) with no dependency
  justification. `scripts/` stays where it is, now importing shared
  constants from `ml/`.

### 14.2 Old → new module mapping

| Before | After | Change |
|---|---|---|
| `api/services/predictor.py` (242 lines: constants + paths + 7 inference fns) | `ml/config.py` (ROOT, CHECKPOINTS, MODELS, MODEL_LABELS, path helpers) + `ml/features.py` (FEATURE_COLS, order frozen) + `ml/inference.py` (7 fns, verbatim) | Extract; `diff` shows only header/import changes |
| — | `ml/__init__.py` | New package marker + re-exports |
| `api/services/predictor.py` | Same path, thin re-export shim | Keeps `api.main`, callers, R2 tests working; R4 owns services |
| `app.py` constant blocks | `from ml.config / ml.features import …` | Dedup; Streamlit logic untouched |
| 3 scripts' constant blocks (`predict_race_winner_ensemble.py`, `predict_race_winner_all_checkpoints.py`, `plot_winner_probability_evolution.py`) | Same + 2-line `sys.path` root bootstrap | Dedup; all logic/CLI untouched |
| `legacy/`, training/eval/cleaning/data scripts, `api/main.py` | Untouched | R6 / later scope, or NUM_COLS split (see §14.1) |

Resulting tree: `ml/{__init__,config,features,inference}.py` (flat — no
`data/training/evaluation` placeholders; the graph did not justify them).

### 14.3 Duplication eliminated / path assumptions changed

- Eliminated: 5 redundant copies of CHECKPOINTS/FEATURE_COLS/MODELS and
  2 of MODEL_LABELS (api + app.py + 3 scripts → single source in `ml/`).
- Remaining (intentional): `legacy/streamlit_app.py` copy (R6),
  NUM_COLS/CAT_COLS in training/eval scripts (needs training to verify).
- Path assumptions: `ml/config.ROOT = parents[1]` (== old roots);
  the 3 scripts bootstrap `sys.path` with their existing `parents[2]`;
  `app.py` reuses its existing `sys.path.append(ROOT)`.
- Compatibility: `api.services.predictor` re-exports all 14 public names;
  no caller or test import changed.

### 14.4 Verification record (after every step; full battery at completion)

- `pytest tests/`: **71 collected — 67 passed, 4 xfailed (Monaco), 0 failed**,
  incl. full golden-equivalence recompute (unchanged fixture sha
  `8e23031a…c1f65302`).
- Script operability: `--help` on both predict scripts; full
  `predict_race_winner_ensemble.py --year 2023 --event "Bahrain Grand Prix"`
  → VER/VER lap 25 (matches API + fixture).
- `app.py` executed with stubbed streamlit/matplotlib: constants identical
  to `ml/`, dataset paths resolve.
- Artifacts: 30 `.pkl`, 14 CSVs, no file under `results/`/`data/` modified
  since R0 (mtime check); no model/dataset content touched.
- Live uvicorn smoke: `/health` 200, Bahrain ensemble 200
  (VER/VER/25/0.8051 — identical), Monaco ensemble still 500 with the
  identical NaN traceback (defect preserved, not fixed).
- Frontend (untouched): node tests 17/17, `tsc` exit 0, lint 0 errors +
  same 7 warnings, `npm run build` success.
- `py_compile` across ml/api/app/edited scripts: OK.
- **Behaviour differences detected: none.**

### 14.5 Deferred to R4 / R6

- R4: real FastAPI service-layer split (the shim is temporary by design).
- R6: `legacy/` retirement, `repo/` vs `legacy/repo/` consolidation,
  Streamlit-vs-Next.js parity verdict.
- Training/eval NUM_COLS/CAT_COLS unification (needs training execution).
- Commit strategy for the 6.6 GB source cache (still undecided).

### 14.6 R3 Definition of Done — status

- [x] ML/data responsibilities are understandable (§14.1–14.2)
- [x] Inference reusable independently from API routing (`ml.inference`, no framework imports)
- [x] Feature definitions not unnecessarily duplicated (§14.3)
- [x] Training remains operational (CLI verified; methodology untouched)
- [x] Evaluation scripts remain available (untouched + compile-verified)
- [x] Model artifacts remain loadable (15/15 in-suite)
- [x] Golden predictions remain equivalent (fixture sha + full recompute)
- [x] No V2 ML behaviour introduced

**R3 is complete. Awaiting explicit approval before R4.**

---

## 15. R4 addendum — FastAPI/Backend Restructuring (2026-09-08)

### 15.1 Responsibility mapping (old → new)

| Before | After |
|---|---|
| `api/main.py` (app + CORS + 2 Pydantic models + 4 routes) | `api/main.py` (app + CORS + `include_router` only) |
| inline `RaceRequest` / `SingleModelRequest` | `api/schemas.py` (verbatim move, validation frozen) |
| routes calling `api.services.predictor` fns directly | `api/routes.py` (`APIRouter`, same paths/methods/handler names, delegates to service) |
| `api/services/predictor.py` (R3 re-export shim) | `api/services/prediction_service.py` (use cases: health, races, ensemble, single-model → `ml.inference`); **shim deleted** |
| `ml.inference` (already framework-free) | Unchanged, now the sole computation owner |

Resulting tree:

```text
api/
├── main.py                 # assembly only
├── routes.py               # HTTP routing (4 endpoints)
├── schemas.py              # request contracts
└── services/
    └── prediction_service.py  # orchestration → ml.inference
ml/{__init__,config,features,inference}.py   # unchanged from R3
```

Call path: `routes.py → prediction_service.py → ml/inference.py → artifacts`.
`ml/` imports nothing from `api/`/`fastapi` (verified by inspection).

### 15.2 Shim verdict

`api/services/predictor.py` **removed**. All consumers were inspected:
`api/main.py` (rewritten), 5 R2 test files (import-only migration to
`ml.config` / `ml.features` / `ml.inference`, assertions untouched), and no
script/frontend references existed. Suite re-run green before and after
deletion. No compatibility retention needed.

### 15.3 Endpoint comparison before/after

- Paths+methods identical (`GET /health`, `GET /races`,
  `POST /predict/ensemble`, `POST /predict/single-model` — via OpenAPI).
- Handler names identical → same operationIds under this FastAPI version.
- No `response_model` added (serialization, incl. Monaco NaN failure, untouched).
- Request fields/defaults/validation unchanged (schemas moved verbatim).
- CORS, app title, error propagation (ValueError → 500) unchanged.

### 15.4 Verification record

- `pytest tests/`: **71 collected — 67 passed, 4 xfailed (Monaco), 0 failed**,
  run after each step (schemas+service+routes; test migration; shim deletion).
- Fixture sha `8e23031a…c1f65302` unchanged; full golden-equivalence green.
- Live uvicorn smoke: `/health` 200, `/races` 104, Bahrain ensemble 200
  (VER/VER/25/0.8051), single-model hgb 200 (VER), Monaco ensemble 500 with
  the identical NaN traceback.
- Artifacts: 30 `.pkl`, 14 CSVs, zero files under `results/`/`data/`
  modified since R0; no newly discovered defects (the `_IncludedRouter`
  introspection shape is a FastAPI-version detail, not a behaviour change).
- Frontend (untouched): node 17/17, `tsc` 0, lint 0 errors + same 7
  warnings, build success. `py_compile` across api/ml: OK.

### 15.5 Deferred to R5 / R6

- R5: frontend modularisation (page.tsx still ~1200 lines).
- R6: `legacy/` + `repo/` duplication verdicts, Streamlit parity.
- Still open: commit strategy for the 6.6 GB source cache; no commit made
  in R4. Note: a baseline commit (`e7d3467`) now exists in the repo root
  from outside this session; R3+R4 changes sit uncommitted on top.

### 15.6 R4 Definition of Done — status

- [x] Backend structure is modular (§15.1)
- [x] Route logic is thin (one-line delegation)
- [x] Prediction logic is reusable (`ml.inference`, framework-free)
- [x] Schemas are explicit (`api/schemas.py`)
- [x] Configuration is understandable (`ml/config.py`, unchanged from R3)
- [x] Existing frontend can still communicate (contract §15.3 + frontend API tests green)
- [x] Golden predictions remain equivalent (§15.4)
- [x] API tests pass (§15.4)

**R4 is complete. Awaiting explicit approval before R5.**

---

## 16. R5 addendum — Frontend Restructuring (2026-09-08)

### 16.1 Original page.tsx responsibilities (1278 lines)

State ×10 (races/year/event/mode/model/loading/results/error/activeTab),
2 effects, 2 memos + chart/grouping memos, `handlePredict`, full hero JSX
(3 states), 8 tab-section blocks, and 5 local presentational components —
with API access already centralised (`lib/api.ts`) and types/helpers already
single-sourced (`lib/predictionTypes.ts`, `lib/predictionHelpers.ts`).

### 16.2 Resulting tree (new electorate in `features/`)

```text
frontend/
├── app/page.tsx (114 lines — layout composition only)
├── features/prediction/
│   ├── hooks/usePrediction.ts        # all page state + effects + handlePredict
│   ├── lib/predictionTransforms.ts   # pure chart/grouping transforms (+ tests)
│   └── components/
│       ├── PredictionHero.tsx        # hero card, 3 states
│       ├── EnsembleResults.tsx       # 4 ensemble tab blocks
│       ├── SingleResults.tsx         # 4 single-model tab blocks
│       ├── ResultCards.tsx           # ConfidenceBar/OverviewCard/ChartInsightCard
│       └── DriverCards.tsx           # DriverCard/CompactDriverRow
├── components/prediction/            # unchanged (ControlsPanel/Tabs/Chart)
└── lib/                              # unchanged + PredictionMode/ModelId aliases
```

Call path: `page → usePrediction → lib/api → backend` (unchanged wire
protocol; no fetch outside `lib/api.ts`; no new dependencies; no store lib).

### 16.3 Move mechanics / fidelity proof

All JSX moved by scripted line-range extraction from the pre-R5 file and
verified **byte-identical** against git HEAD (`/tmp/verify_r5.py`: all 8
blocks PASS). Only headers (imports/props) are new; prop names match the
original hook variables so moved JSX needed zero edits. Dropped as dead
code in transit: unused `isCorrect` var + 6 unused imports (were lint
warnings). Deliberately not fixed: `barClassName` unused prop (warning kept).

### 16.4 Verification record

- `node --test` (all three files): **21 passed, 0 failed** (17 pre-existing + 4 transform tests).
- `tsc --noEmit`: exit 0. `npm run lint`: 0 errors, 1 warning (was 7; 6
  removed with dead code, none added). `npm run build`: success.
- Production SSR smoke (`next start` + curl `/` → 200): preview-state HTML
  contains all 10 key copy/control strings (hero, Controls, selectors,
  mode buttons, run button) — restructured tree renders without crashing.
- Backend battery (frontend-only change, per R5 gate list): `pytest`
  67 passed + 4 xfailed; fixture sha unchanged; 30 `.pkl` / 14 CSVs intact.
- Visual-equivalence basis: byte-identical markup + unchanged classes/DOM +
  same component tree order + successful prerender. Post-prediction
  interactive states (tabs after Predict, chart after data) cannot be
  exercised without a browser (no headless browser available; no test
  framework added per constraints) — residual risk documented, not observed.
- **Behavioural/visual differences detected: none.**

### 16.5 Deferred to R6 / V2 UI

- R6 owns Streamlit-vs-Next.js parity and legacy retirement (unchanged).
- Future V2 navigation/replay/simulator UI: not started. Cosmetic polish
  encountered: none applied.

### 16.6 R5 Definition of Done — status

- [x] Primary page is easier to understand (1278 → 114 lines, §16.2)
- [x] API access is centralised (unchanged `lib/api.ts`, contract tests green)
- [x] Types are organised (single source + mode/model aliases; no dupes found)
- [x] Major prediction UI responsibilities are modular (§16.2)
- [x] Current UI still works (§16.4)
- [x] Frontend tests pass (21/21)
- [x] Production build succeeds

**R5 is complete. Awaiting explicit approval before R6.**

---

## 17. R6 addendum — Legacy & Duplication Cleanup (2026-09-08)

### 17.1 Candidate verdicts (all inspected before action)

| Candidate | Verdict | Evidence |
|---|---|---|
| root `app.py` (Streamlit) | REMOVE | Full parity with Next.js+FastAPI (table §17.2); zero imports/references; logic now in `ml/`+API; retired, not migrated |
| `legacy/streamlit_app.py` | REMOVE | Same as above + broken `ROOT` paths (never ran from `legacy/`) |
| `legacy/` dir | REMOVE | Emptied by the above; removed |
| `repo/f1-race-replay-main/` | REMOVE | Byte-identical to legacy copy; unrelated arcade/GUI prototype; zero references; ~15 MB duplicated PNG/gif assets |
| `legacy/repo/f1-race-replay-main/` | REMOVE | Same; `legacy/` emptied → dir removed |
| `repo/` dir | REMOVE | Emptied by the above; removed |
| `gpt.txt` (3.9 MB) | REMOVE | Unreferenced AI metrics-narration dump; 0 secret-pattern hits; no runtime value |
| `docs/{req,notes,section5report}.txt/.md` | REMOVE (dupes) | Byte-identical to root copies; zero references to the `docs/` copies; root originals kept |
| `requirements.txt` streamlit pin | REMOVE (line) | Last `import streamlit` owners deleted; matplotlib kept (analysis scripts still use it) |
| `results/debug/*` (README + 6 tiny CSVs) | PRESERVE | Header-only failure CSVs + archival README = dataset-alignment evidence, ~1 KB |
| All 42 `scripts/*.py` | PRESERVE | No exact duplicates (md5); training/eval needed for Phases 1–3 |
| 30 `.pkl`, 14 CSVs, fixture, `results/` evidence | PRESERVE | Untouched (mtime-verified); counts re-verified |
| `frontend/README.md`, root docs, V2 plans | PRESERVE | No action (README work is R7) |

### 17.2 Streamlit parity table (retirement basis)

```text
Feature                    Streamlit    Next.js/FastAPI
Race selection             yes          yes
Checkpoint selection       yes          yes (all 5 laps)
Model selection            yes          yes
Ensemble (majority+XGB)    yes          yes (same rule)
Probability view           yes (mpl)    yes (SVG + bars)
Actual result comparison   yes          yes (winner + rank)
Top-5 drivers              yes          yes
Unique Streamlit-only cap. NONE FOUND
```

Post-R3 re-diff: the two Streamlit files differed only in the constant
block (`app.py` → `ml/` imports); all UI/logic identical. `notes.txt`
references a nonexistent `app_test.py` (stale scratch note, kept as-is
at root as harmless history).

### 17.3 Removed inventory (~33.7 MB)

- 2 replay trees (74 files, ~30 MB) + 2 emptied parent dirs
- `app.py`, `legacy/streamlit_app.py`, `legacy/` dir
- `gpt.txt` (3.9 MB, 34k lines)
- 3 `docs/` duplicate files; 1 requirements line
- History note: R1 git bundles of the removed nested `.git`s remain at
  `/tmp/r1_git_backups/` (outside repo, ephemeral).

### 17.4 Verification record

- After each deletion: referencegrep clean (only legit `api.main:app`
  match + audit history), targeted pytest green, final full `pytest`:
  **67 passed, 4 xfailed (Monaco), 0 failed**.
- Frontend: node 21/21, `tsc` 0, lint 0 errors + 1 kept warning, build ok.
- Live smoke: `/health` 200, Bahrain 200 (VER/VER/0.8051), Monaco 500
  identical traceback. Fixture sha unchanged. `py_compile` ok.
- Secret/hygiene scan (patterns for keys/tokens/passwords, repo-wide
  excl. caches/node_modules/.git): **0 hits**; no machine paths in
  source; only env file is the ignored localhost `.env.local`.
- **Behavioural differences detected: none.** No regressions; nothing restored.

### 17.5 Newly discovered risks / deferred

- The outside-session baseline commit tracks **1492 files incl. 1113
  FastF1 cache blobs + 176 pkl/csv** — cache-in-git inflates the repo and
  must be addressed (untrack + LFS/`.gitignore` strategy) in R7+; R6 did
  not rewrite history or commit (81 deletions sit unstaged).
- `notes.txt` staleness (`app_test.py`) noted, kept.
- R7 owns: README, `.env.example`, command docs, formatter strategy,
  and the cache-tracking decision above.

### 17.6 R6 Definition of Done — status

- [x] Streamlit status explicitly decided (retired, parity table §17.2)
- [x] Useful functionality preserved (all in `ml/`+API+Next.js; debug evidence kept)
- [x] Unnecessary duplication reduced (~33.7 MB, §17.3)
- [x] Dead code removal justified (§17.1 evidence per item)
- [x] Documentation reflects the supported path (§17.1; README deferred to R7)
- [x] Regression suite passes (§17.4)

**R6 is complete. Awaiting explicit approval before R7.**

---

## 18. R7 addendum — Tooling + Developer Experience (2026-09-08)

### 18.1 Tracked FastF1 cache — findings and action

- Baseline commit tracked **1113 `.ff1pkl` blobs** under
  `data/raw/fastf1_cache/` (reproducible FastF1 session cache; largest
  ~52 MB). Verified: zero non-cache files among them (extensions all
  `.ff1pkl`); no app/test/script reads them at runtime (API/tests use
  `data/processed` CSVs); `.fastf1_cache/` was never tracked.
- Action: `git rm -r --cached data/raw/fastf1_cache` (**index only**).
  Local 6.6 GB cache intact; `git ls-files` 1492 → **379**; `.gitignore`
  now covers `/data/raw/fastf1_cache/` (root-scoped) with a no-LFS note.
- Verified after: `git check-ignore` hits both cache paths; datasets/API
  tests pass offline (18/18 subset); history untouched (no filter-repo/BFG;
  baseline commit retains blobs historically).
- Kept tracked: 14 processed/interim CSVs, 30 `.pkl`, 176 result CSVs,
  fixture, source, docs.

### 18.2 Docs / env / notes.txt

- New root `README.md`: what the app does, canonical architecture, backend
  + frontend setup/run, all test/typecheck/lint/build commands (== `make`
  targets), dataset/model locations, cache-not-versioned rule, Monaco
  defect, legacy-eval disclaimer, V2 plan pointers. Not a portfolio study.
- All 13 README-required paths verified present. Stale Streamlit/legacy
  setup references: none remain outside audit history.
- New `frontend/.env.example` (localhost base only, no secrets);
  `frontend/.gitignore` negation added so the example is tracked while
  real `.env*` files stay ignored (verified both ways).
- `notes.txt` verdict: REMOVE — stale scratch (done-XGBoost TODO,
  nonexistent `app_test.py`); setup commands preserved in README + scripts.

### 18.3 Dependencies / setup scripts

- `requirements.txt`: only change is the R6 streamlit-line removal.
  Audited imports: only `streamlit` was orphaned; `tabulate/signalrcore/
  timple/PIL/scipy` have no direct importers but are transitive pins —
  kept conservatively. No upgrades; sklearn/xgboost pins frozen.
- `requirements-test.txt`, `frontend/package.json`: unchanged, match use.
- `scripts/dev/{setup,run,clean}_{mac,windows}`: all reference canonical
  paths (`api.main:app`, root `venv/`, `npm run dev`); no Streamlit/legacy/
  stale paths found → preserved as-is. (`run_mac.sh` stays macOS-GUI-only;
  `make backend-dev/frontend-dev` are the plain cross-platform equivalent.)

### 18.4 Commands / formatting / hygiene

- New root `Makefile` (single system): `backend-dev`, `frontend-dev`,
  `test-python`, `test-frontend`, `typecheck`, `lint`, `build`,
  `verify` (= full battery). `make verify` exit 0.
- Formatting: no Python formatter/linter configured in-repo — documented
  as-is per plan (no rewrite, no pre-commit hooks; frontend keeps
  eslint + tsc).
- Hygiene: index holds no DS_Store/pycache/.next/node_modules/venvs;
  ignored working files verified (caches, `.env.local`, build output);
  secret-pattern rescan: **0 hits**.

### 18.5 Verification record

- `make verify` exit 0 (pytest 67+4xf, node 21/21, tsc 0, lint 0 err +
  1 kept warning, build success). Live smoke: `/health` 200, Bahrain 200
  (VER/0.8051), Monaco 500 identical. Fixture sha unchanged; 30 `.pkl` /
  14 CSVs intact, unmodified since R0.
- **Behavioural differences detected: none.**

### 18.6 Recommended staging/commit procedure (NOT executed — await approval)

The worktree currently holds staged cache-untracking + unstaged R3–R7
work. When approved, commit as logical boundaries (do NOT lump):

```bash
git status --short          # review first; expect only intended paths
git add ml/ api/ tests/ requirements-test.txt
git commit -m "refactor: reorganise ml modules and FastAPI backend (R3/R4)"
git add frontend/ Makefile
git commit -m "refactor: modularise prediction frontend; add dev commands (R5/R7)"
git add README.md requirements.txt frontend/.env.example \
  docs/V2_REPOSITORY_AUDIT.md .gitignore frontend/.gitignore
git commit -m "docs: README, env example, hygiene (R1/R6/R7)"
git rm -r --cached data/raw/fastf1_cache   # already staged; verify with git status
git commit -m "chore: stop tracking FastF1 cache (R7)"
```

Deletions (`app.py`, `legacy/`, `repo/`, `gpt.txt`, `notes.txt`, doc
dupes, shim) stage with the commits above via `git add -A` per boundary —
verify each `git status` before committing. Never commit `.fastf1_cache/`,
`data/raw/fastf1_cache/`, `node_modules/`, `.next/`, `.env.local`.

### 18.7 R7 Definition of Done — status

- [x] New engineer can find what/where/how-to-run-how-to-test (§18.2)
- [x] Cache-in-git resolved without history rewrite (§18.1)
- [x] Env example safe + ignored correctly (§18.2)
- [x] Deps match canonical app, pins frozen (§18.3)
- [x] One obvious command surface (§18.4)
- [x] Formatter strategy explicit (§18.4)
- [x] Full battery green with zero behaviour change (§18.5)

**R7 is complete. Awaiting explicit approval before R8.**

---

## 19. R8 addendum — Full Regression Verification (2026-09-08, gate stage, no code changes*)

(*One audit-doc section is the only file modified in R8.)

### 19.1 Git / repository hygiene: PASS

- Exactly one `.git`, no nested repos. Both FastF1 caches present locally,
  both ignored, 1113 raw-cache blobs staged for untracking (pure deletions,
  zero additions). `node_modules`, `.next`, `__pycache__`, `.env.local`
  ignored; `.env.example` trackable. No tracked generated junk. Secret
  rescan: **0 hits**. >50 MB entries exist only in HEAD history (the cache
  being untracked) — none staged/tracked going forward. No commit, no
  history rewrite.

### 19.2 Fresh environments: PASS (with one documented caveat)

- Fresh `/tmp/r8fresh` (py3.11) built from `requirements.txt` +
  `requirements-test.txt`: pins resolve exactly (sklearn 1.8.0, xgboost
  3.2.0, fastapi 0.135.1, fastf1 3.7.0). In it: imports ok, all 15 tuned
  artifacts deserialize, `pytest` **67 passed, 4 xfailed in 9.67 s**,
  `py_compile` over api/ml/all-42-scripts ok. No network F1 data needed.
- Frontend: lockfile resolves, no invalid/missing (only optional
  platform shims flagged extraneous — noise). `npm ci` deliberately NOT
  run (would wipe the verified tree); gates below run on the documented
  tree. tsc 0, lint 0 err + 1 kept warning, build success, node 21/21.

### 19.3 Golden / API / models / datasets / contract: PASS

- Full golden suite in both envs: ensemble + 3 model families × 5 laps ×
  6 races — winners/ranks/top-5/reasons exact, raw probs within 1e-9.
  Fixture sha `8e23031a…c1f65302` unchanged. **No regressions.**
- API: OpenAPI shows exactly the 4 routes/methods; TestClient + live
  uvicorn: `/health` 200, `/races` 104, Bahrain ensemble 200
  (VER/VER/25/0.8051), hgb single 200, unknown-race 500 (legacy),
  Monaco 500 identical NaN traceback (defect preserved).
- Models: 30 `.pkl` present, aggregate sha `8723b9…` recorded, 0 modified
  since R0, all load + score. Datasets: 14 CSVs, aggregate sha `f085f7…`
  recorded, 0 modified; all laps 2019–2023 with 1-winner-per-race integrity.
- Contract: frontend ModelIds == backend MODELS; ensemble response keys ==
  frontend `EnsembleResult`; endpoint URLs asserted in api.test.ts.

### 19.4 Workflow / xfails / architecture: PASS with findings

- `make test-frontend/typecheck/lint/build` genuinely verified; `make
  verify` exit 0. `make backend-dev` / `frontend-dev` construction
  correct — frontend-dev served 200 live; backend-dev serves 200 when run
  with a working interpreter (`PYTHON=<venv-python>`), no orphans left.
- **Finding (environment, not repo): this machine's bare `python3`
  (3.14 shim) produces no output and exits 0, so `make test-python` /
  `backend-dev` with default `PYTHON=python3` are vacuous HERE.** Recipe
  construction is correct for a normal machine; real pytest numbers above
  come from working interpreters. Recommended follow-up (not applied in
  R8 freeze): Makefile preflight asserting a functional interpreter
  (e.g. `$(PYTHON) -c "import sys, pytest"`) and `--reload-dir api ml`
  to avoid watching the 6.6 GB cache dir. Also: one transient `npm`
  enoent during R8 re-verified green on immediate retry (infra noise).
- xfails: exactly the 4 Monaco markers, all failing-as-expected with
  intact rationale. No other xfails/skips. Warnings: Starlette/anyio
  deprecation notices (upstream), node typeless-package notes (cosmetic).
- Architecture: `ml/` has no FastAPI imports; frontend has no prediction
  computation; no references to Streamlit/legacy/replay/deleted modules.
- Secrets/hygiene: 0 hits, third consecutive stage.

### 19.5 Phase-1 readiness: READY except one expected item

- Parquet home (`data/processed/laps/season=…`) can coexist with legacy
  CSVs; `scripts/` stage layout can evolve into ingestion modules;
  `ml/` runtime boundaries don't conflict with ingestion/validation
  layers; cache handling matches the Phase-1 strategy (local-only,
  documented); `tests/` layout supports new data-platform tests.
- **Gap: Phase-1 D0 requires `docs/FOUNDATION_REFACTOR_REPORT.md`, which
  is R9's deliverable — by plan, not a surprise.** No other blockers.

### 19.6 R8 pass criteria (all must hold)

1. [x] Non-xfail tests pass (67 + 21, two envs) 2. [x] Golden equivalent
3. [x] Fixture unchanged 4. [x] Models/datasets unchanged
5. [x] Frontend builds 6. [x] API contract intact
7. [x] Workflow succeeds (with the §19.4 caveat documented, not hidden)
8. [x] No new regression 9. [x] No critical hygiene issue
10. [x] No Foundation blocker for R9 (only the expected R9 report itself)

**R8 PASSES. Awaiting explicit approval before R9.**
