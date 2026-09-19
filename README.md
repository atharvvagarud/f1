# F1 Intelligence — Race Intelligence Platform

> **Status: Phase 0 (Foundation Refactor) COMPLETE · Phase 1 (Historical Data
> Platform) COMPLETE & FROZEN · Phase 2 (Temporal Feature Engine) COMPLETE &
> FROZEN · Phase 3 (Model Lab M0–M9) COMPLETE & FROZEN · Phase 4 (Race State
> & Prediction Service R0–R7) COMPLETE & FROZEN · Phase 5 (Historical Race
> Replay) — NEXT.**
> This repository contains two systems: the frozen legacy university
> predictor (**V1**, still serving) and the canonical **V2** platform whose
> frozen winner model (ALL_84 → train-fitted preprocessing →
> LogisticRegression C=0.01, RAW, independent binary probabilities) is
> handed to production via `v2/model_lab/serving.py` +
> `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`. Phase-2 freeze
> report: `docs/PHASE2_FINAL_REPORT.md`; Phase-3 final model card:
> `docs/MODEL_LAB_FINAL_MODEL_CARD.md`; final report:
> `docs/MODEL_LAB_FINAL_REPORT.md`; freeze manifest:
> `docs/MODEL_LAB_FREEZE_MANIFEST.json`; production handoff:
> `docs/MODEL_LAB_P31_HANDOFF_REPORT.md`. Final verification baseline:
> 1540 passed, 4 known xfailed (+ Phase-4 freeze seal).

## Vision (roadmap — planned, not implemented)

F1 Intelligence aims at historical lap-by-lap race intelligence:
probabilistic in-race predictions, historical replay, race simulation,
strategy analysis and explainability. **Implemented (frozen):** exact
historical RaceState reconstruction, frozen ALL_84 feature bridge,
production frozen winner inference, and the V2 historical API
(independent-binary probability semantics, 2018–2024 serving scope).
**Still ROADMAP / PLANNED:** Monte Carlo, strategy engine, replay
(Phase 5 — NEXT), calibration, MLOps and any Race Engineer AI do **not**
exist in this repo.

## Currently implemented

- Foundation refactor: FastAPI/ML separation, characterization tests,
  golden regression fixtures.
- **V2 Phase-1 data platform (frozen):** 1950–2025 historical results
  platform (76 seasons, 1,149 races, 25,784 results); 2018–2025 rich FastF1
  platform (173 Race sessions); resumable/idempotent ingestion with
  manifests; canonical IDs and machine-readable contracts; **189,420
  canonical lap-end states**; temporal weather/race-control/pit/stint
  enrichment; separated outcome labels (3,458 race-drivers); deterministic
  builds; per-stage future-mutation leakage tests; legacy comparison;
  telemetry deferral ADR; final validation gate (44 findings, 0 failed,
  0 unresolved BLOCKERs — `docs/PHASE1_FINAL_VALIDATION.md`).
- **V2 Phase-2 temporal feature engine (frozen):** frozen temporal/
  synchronization contract; feature registry `FEATURE_SET_VERSION=v8`
  (**84** predictive definitions) separated from labels
  `LABEL_SET_VERSION=v1` (**7** targets); leakage/parity red-team audit
  (20 threat classes); canonical model-ready matrix `MATRIX_VERSION=v1`
  (**189,420 × 106**) at
  `data/v2/processed/model_matrix/matrix_version=v1/` + manifest;
  manifest-controlled loaders; ordinal eligibility protected
  (178,963/189,420); ablation/experiment config `ABLATION_CONFIG_VERSION=v1`
  + 11 fixtures; telemetry stays DEFERRED (ADR-0001); regression
  861 passed / 4 xfailed; D11 offline 43/0/0. Full freeze:
  `docs/PHASE2_FINAL_REPORT.md`.
- **V2 Phase-4 race state & prediction service (frozen, contract v1):**
  exact historical RaceState reconstruction from canonical D9 anchors
  (`v2/race_state.py`, `v2/race_state_reconstruction.py`); frozen ALL_84
  feature bridge (`v2/race_state_features.py`, serving-only per-race
  slice cache); production frozen winner inference
  (`v2/prediction.py`, LogisticRegression C=0.01 RAW, one batch
  `predict_proba` per snapshot, independent binary probabilities never
  normalized); versioned V2 HTTP API (`api/v2_routes.py`,
  `api/v2_service.py`, `api/v2_schemas.py`: `/v2/races`,
  `/v2/races/{id}/states`, `/v2/races/{id}/state`,
  `/v2/predictions/winner-snapshot`, 2018–2024 scope, stable
  404/422/503/500 mapping, legacy routes untouched); full-field
  snapshot ~12 s (feature-dominated). Freeze:
  `docs/PHASE4_FINAL_REPORT.md`, `docs/PHASE4_FREEZE_MANIFEST.json`,
  `docs/PHASE4_V2_API_CONTRACT.json`; Phase-5 handoff:
  `docs/PHASE5_REPLAY_HANDOFF.md`.
- **V1 legacy predictor (frozen):** tuned Logistic Regression /
  HistGradientBoosting / XGBoost pipelines plus majority-vote ensemble
  (XGBoost tie-break) over lap 5/10/15/20/25 snapshots, served by the
  FastAPI backend + Next.js frontend. Race-grouped CV methodology (not
  temporal validation). Do not modify or retrain.

## Architecture (implemented only)

```text
Jolpica / Ergast-compatible historical data (1950–2025, Tier-B)
              +
FastF1 rich timing data, Race sessions 2018–2025 (Tier-A)
              ↓
      ingestion / normalization (v2/, manifests, atomic writes)
              ↓
     D6 canonical lap state (189,420 rows, state_time_s = LAP_END)
              ↓
    D7 temporal enrichment (weather / race control / pit / stint)
              ↓
  D9 structural derived state (189,420 rows)
              ↓
  Phase-2 feature engine: temporal operators + families F4–F11
              ↓
  84-feature predictive surface → F15 canonical matrix
  (data/v2/processed/model_matrix/matrix_version=v1/, 189,420 × 106)
              ↓
  F16 ablation config + fixtures → Phase 3 Model Lab M0–M9 (FROZEN):
  frozen winner model (LogReg C=0.01, RAW) → P3.1 production handoff
  (v2/model_lab/serving.py + results/v2_model_lab/ artifact)

official results  →  D9 outcome labels, race×driver (3,458 rows, separate)
                  →  F13 label contracts → F15 label join

FastF1 raw telemetry/cache  →  DEFERRED by ADR-0001 (source-only, ~16 GB)

V1 serving (frozen): ml/ + api/ + frontend/ over data/processed/lap*/
```

## Reproducibility

- Python 3.11; create an environment and install the exact pins:
  `pip install -r requirements.txt -r requirements-test.txt`
  (pins include scikit-learn==1.8.0 / xgboost==3.2.0 — **required** to
  unpickle the saved legacy pipelines).
- Node.js 22 + npm for `frontend/` (`npm install`).
- If `python3` on your machine is a non-functional shim, override the
  interpreter explicitly, e.g. `make PYTHON=/path/to/python3.11 <target>`
  (see `make check-python`).
- Optional env vars: `V2_PROJECT_ROOT` (explicit repo root for V2 tooling),
  `V2_ALLOW_NETWORK=1` (explicit opt-in for live FastF1 ingestion only),
  `NEXT_PUBLIC_API_BASE` (frontend → backend URL, see
  `frontend/.env.example`).

## Data instructions

Full guide: [`data/README.md`](data/README.md) (coverage, sources, entities,
grain/clock, label separation, build/validate commands, manifests, reports,
telemetry decision, limitations, Phase-2 input contract).

In short: canonical Parquet lives under `data/v2/processed/` (gitignored,
reproducible — do not commit it); ingestion manifests under
`data/v2/raw/manifests/`; validation evidence under
`data/v2/reports/data_quality/`; the FastF1 cache under
`data/raw/fastf1_cache/` is local-only source infrastructure (~16 GB, never
committed, never quoted as dataset size — canonical data is ~74 MB).
Validate an existing build with `python -m v2.d11` (acceptance gate);
rebuild deterministically with `python -m v2.d6/d7/d9 --all --validate`.
A full rich FastF1 rebuild needs network, takes substantial time and grows
the cache — don't rerun it casually.

## Run the backend (V1, frozen behaviour)

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
python -m pytest tests/ -q                                  # backend + ML safety net + V2 (1540 passed, 4 known xfailed + freeze seal)
node --test lib/predictionHelpers.test.ts lib/api.test.ts \
  features/prediction/lib/predictionTransforms.test.ts      # frontend tests (21, from frontend/)
./node_modules/.bin/tsc --noEmit -p .                       # typecheck (from frontend/)
npm run lint                                                # eslint (from frontend/)
npm run build                                               # production build (from frontend/)
```

Phase-2 build/validate (from the repo root, offline):

```bash
python -m v2.features.build_matrix [--force]   # canonical matrix (idempotent)
python -m v2.d11 --skip-fresh-env              # D11 acceptance gate (offline; 43/0/0)
```

## Data, models, caches

- V1 datasets: `data/processed/lap{5,10,15,20,25}/base/dataset_clean.csv`
  (2019–2023 checkpoints). Tracked, do not modify.
- V1 models: `results/models/{logreg,hgb,xgboost}_lap{LAP}_multilap/`
  (`model_tuned.pkl` preferred at runtime). Tracked, do not modify/retrain.
- V2 canonical data: `data/v2/` — generated, ignored, reproducible.
  Do not add to Git/LFS.
- FastF1 caches (`.fastf1_cache/`, `data/raw/fastf1_cache/`) are
  **local-only and not version-controlled**. Do not add to Git/LFS.
- Golden fixtures: `tests/fixtures/legacy_predictions.json` — byte-frozen
  R0 baseline; never regenerate to hide drift.

## Known legacy defect (characterized, frozen)

Monaco 2022 predictions return HTTP 500: NaN `tyre_life_x` in the source
rows breaks JSON serialization. Documented in `docs/V2_REPOSITORY_AUDIT.md`
(§5.1) and pinned by `xfail` tests. Do not fix opportunistically.

## Docs index

- `data/README.md` — data-platform README + Phase-2 handoff (start here
  for data)
- `docs/DATA_PLATFORM_ARCHITECTURE.md` — accepted architecture (D0–D11)
- `docs/DATASET_V2_REPORT.md` — measured dataset report
- `docs/PHASE1_FINAL_VALIDATION.md` — D11 acceptance gate (44/0/0)
- `docs/PHASE1_EXIT_REPORT.md` — Phase-1 exit record (freeze, DoD, handoff)
- `docs/PHASE2_FINAL_REPORT.md` — Phase-2 final report + freeze (start here
  for features/labels/matrix)
- `docs/PHASE2_CANONICAL_MATRIX.md` · `docs/PHASE2_ABLATION_CONFIG.md` ·
  `docs/PHASE2_LEAKAGE_PARITY_AUDIT.md` · `docs/PHASE2_TEMPORAL_SEMANTICS.md`
  — Phase-2 matrix, ablation config, leakage/parity audit, temporal contract
- `docs/generated/phase2_freeze_manifest.json` — machine-readable freeze
- `docs/MODEL_LAB_PROTOCOL.md` — Phase-3 M0 evaluation protocol (frozen) +
  `docs/generated/model_lab_protocol_v1.json` / `model_lab_split_audit_v1.json`
- `docs/MODEL_LAB_EXPERIMENT_FRAMEWORK.md` — Phase-3 M1 experiment framework
  (loader, splits, masks, metrics, aggregation, baselines, results)
- `docs/MODEL_LAB_FINAL_MODEL_CARD.md` — frozen winner model card (M9)
- `docs/MODEL_LAB_FINAL_REPORT.md` — Phase-3 culmination report (M0–M9)
- `docs/MODEL_LAB_FREEZE_MANIFEST.json` — Phase-3 machine-readable freeze
- `docs/MODEL_LAB_P31_HANDOFF_REPORT.md` — P3.1 production handoff +
  repository seal record
- `docs/PHASE4_FINAL_REPORT.md` — Phase-4 final report + freeze (start
  here for RaceState/prediction/V2 API)
- `docs/PHASE4_FREEZE_MANIFEST.json` — Phase-4 machine-readable freeze
- `docs/PHASE4_V2_API_CONTRACT.json` — frozen V2 API surface
- `docs/PHASE5_REPLAY_HANDOFF.md` — Phase-5 historical replay handoff
- `docs/LEGACY_V2_DATASET_COMPARISON.md` — V1↔V2 audit (D10)
- `docs/adr/ADR-0001-telemetry-retention.md` — telemetry deferral decision
- `V2_PHASE_1_DATA_PLATFORM.md` — Phase-1 plan (complete)
- `V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md` — Phase-2 plan (complete/frozen)
- `V2_PHASE_3_MODEL_LAB.md` — Phase-3 plan (M0–M9 complete/frozen)
- `V2_FOUNDATION_REFACTOR.md.md` · `docs/V2_REPOSITORY_AUDIT.md` ·
  `docs/FOUNDATION_REFACTOR_REPORT.md` — foundation history
- `req.md` — reproducibility notes
