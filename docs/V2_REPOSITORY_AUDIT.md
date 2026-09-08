# V2 Repository Audit — R0 Baseline & Inventory

> **Stage:** R0 — Baseline & Inventory (V2_FOUNDATION_REFACTOR.md)
> **Date:** 2026-09-08
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
