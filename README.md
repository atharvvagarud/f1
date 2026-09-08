# F1 In-Race Winner Prediction

Predict the eventual winner of a historical Formula 1 race (seasons
2019–2023) from an in-race snapshot at lap 5 / 10 / 15 / 20 / 25, using
tuned Logistic Regression, HistGradientBoosting and XGBoost pipelines plus
a majority-vote ensemble (XGBoost tie-break).

> Status: working foundation under behaviour-preserving refactor towards
> F1 Intelligence v2. See `V2_FOUNDATION_REFACTOR.md` (current plan) and
> `docs/V2_REPOSITORY_AUDIT.md` (baseline + per-stage record). The stored
> model evaluation is **legacy methodology (race-grouped CV, not temporal
> validation)** — do not present it as final V2 performance.

## Architecture (canonical)

```text
ml/                    # shared ML library: config, features, inference
  config.py            # checkpoints, models, artifact paths (single source)
  features.py          # inference FEATURE_COLS (order frozen by pipelines)
  inference.py         # loading + single-model + ensemble (framework-free)
api/                   # FastAPI backend: main → routes → schemas → services → ml
  main.py / routes.py / schemas.py / services/prediction_service.py
frontend/              # Next.js + React + TypeScript + Tailwind
  app/page.tsx         # composes features/prediction (hook + components)
  features/prediction/ # usePrediction hook, result components, transforms
  lib/api.ts           # sole backend client (NEXT_PUBLIC_API_BASE)
scripts/               # standalone stage CLIs: data → cleaning → models → baselines → analysis
data/processed|interim # checkpoint datasets (tracked)
results/models         # 30 tuned pipelines (tracked) + historical evaluation outputs
tests/                 # pytest regression suite + tests/fixtures/legacy_predictions.json
```

Retired in R6: the Streamlit UI (`app.py`) — full parity with Next.js +
FastAPI, no unique capability. Use the web app below.

## Prerequisites

- Python 3.11+ with `pip install -r requirements.txt`
  (pins include scikit-learn==1.8.0 / xgboost==3.2.0 — **required** to
  unpickle the saved pipelines) plus `-r requirements-test.txt` for tests.
- Node.js 22 + npm for `frontend/` (dependencies in `frontend/package.json`).

## Run the backend

```bash
python -m uvicorn api.main:app --reload --port 8000
# GET  /health   GET /races
# POST /predict/ensemble  {"year": 2023, "event": "Bahrain Grand Prix"}
# POST /predict/single-model  {"year": 2023, "event": "Bahrain Grand Prix", "model": "xgboost"}
```

## Run the frontend

```bash
cd frontend && npm install && npm run dev   # http://localhost:3000
```

Point it at the backend with `NEXT_PUBLIC_API_BASE` (see
`frontend/.env.example`; default `http://127.0.0.1:8000`).

## Verify (or `make verify`)

```bash
python -m pytest tests/ -q                                  # backend + ML safety net (71 tests)
node --test lib/predictionHelpers.test.ts lib/api.test.ts \
  features/prediction/lib/predictionTransforms.test.ts      # frontend tests (21, from frontend/)
./node_modules/.bin/tsc --noEmit -p .                       # typecheck (from frontend/)
npm run lint                                                # eslint (from frontend/)
npm run build                                               # production build (from frontend/)
```

## Data, models, caches

- Datasets: `data/processed/lap{5,10,15,20,25}/base/dataset_clean.csv`
  (104 races, 2019–2023) + `data/interim/` mirrors. Tracked, do not modify.
- Models: `results/models/{logreg,hgb,xgboost}_lap{LAP}_multilap/`
  (`model_tuned.pkl` preferred at runtime). Tracked, do not modify/retrain.
- FastF1 caches (`.fastf1_cache/`, `data/raw/fastf1_cache/`) are
  **local-only and not version-controlled** (reproducible blobs; the app
  and tests run offline from the processed datasets). Do not add to Git/LFS.
- Golden fixtures: `tests/fixtures/legacy_predictions.json` — byte-frozen
  R0 baseline; never regenerate to hide drift.

## Known legacy defect

Monaco 2022 predictions return HTTP 500: NaN `tyre_life_x` in the source
rows breaks JSON serialization. Documented in `docs/V2_REPOSITORY_AUDIT.md`
(§5.1) and pinned by `xfail` tests. Do not fix opportunistically — it has
a planned home in later V2 work.

## V2 plans

`V2_FOUNDATION_REFACTOR.md` (active) · `V2_PHASE_1_DATA_PLATFORM.md` ·
`V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md` · `V2_PHASE_3_MODEL_LAB.md`
(future phases — not started). Reproducibility notes: `req.md`.
