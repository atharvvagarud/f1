# F1 Race Intelligence

Lap-by-lap winner prediction, historical replay, Monte Carlo simulation, and
strategy comparison over frozen Formula 1 data — with temporal-leakage safety
enforced by construction.

This repository is a portfolio case study in building ML systems that cannot
see the future: 189,420 temporally-safe race states, a frozen 2025 one-shot
holdout (Top-1 79.6%, Top-3 97.9%), and a Dockerized two-service local runtime
validated by 3,193 scientific tests. Start here, then read the
[technical case study](docs/case-study/TECHNICAL_CASE_STUDY.md) for depth.

## What It Does

- **Historical replay** — step through 149 races (2018–2024) at 9,644 exact
  checkpoints and inspect the frozen model's cached prediction at each one.
- **Winner prediction** — per-driver win probabilities from a frozen
  LogisticRegression model, served with explicit independent-binary semantics
  (never normalized across the field).
- **Monte Carlo simulation** — up to 10,000 stochastic trajectories from any
  factual race state, aggregated into mutually exclusive win/podium/finish
  distributions.
- **Strategy comparison** — baseline vs candidate pit interventions compared
  with paired simulations, sampling uncertainty, and a classification
  (improvement / degradation / inconclusive). It compares; it never prescribes.
- **Explainability** — exact log-odds decomposition of any served prediction,
  plus checkpoint-to-checkpoint change explanations. Associational, not causal.
- **Model/evidence inspection** — static dossiers for the model, the data, and
  the system's semantic boundaries and limitations.

## Key Results

| Area | Evidence |
|---|---|
| Dataset | 189,420 temporal states × 84 predictive features |
| 2025 one-shot holdout | Log Loss 0.0680, Brier 0.0200, Top-1 79.6%, Top-3 97.9% |
| Replay | 149 races, 9,644 exact checkpoints |
| Scientific validation | 3,193 passed, 5 skipped, 4 xfailed, 0 failures |
| Runtime | Dockerized two-service local deployment, readiness 6/6 |

2025 is the one-shot holdout evaluation season. It is not served by any
production prediction, replay, simulation, or strategy surface.

## Product

Six surfaces, all served from the same frozen artifacts:

- **Predict** (`/`) — 20-driver winner snapshot at an exact race anchor.
- **Replay** (`/replay`) — timeline scrubber over exact checkpoints with
  cached predictions and log-odds explanations. The replay page includes a
  Spatial Track Replay panel (Phase 12): telemetry-derived circuit geometry
  with causal lap/frame-synchronized driver positions (latest observation
  at or before replay time only; 2018–2024 served races) plus historical
  race-status context from the same replay frame. Full semantics, cross-
  validation, and limitations: `docs/PHASE12_FINAL_REPORT.md`.
- **Simulator** (`/simulator`) — Monte Carlo outcome distributions from a
  chosen anchor and seed.
- **Strategy** (`/strategy`) — paired baseline-vs-candidate comparison with
  uncertainty. No best/recommended/optimal labels anywhere.
- **Models** (`/models`) — frozen evaluation evidence, calibration decision,
  and limitations.
- **About** (`/about`) — architecture, dataset statistics, semantic
  boundaries, and limitations.

(Product screenshots are capture-pending; the
[specification](docs/case-study/screenshots/README.md) defines all six.
No mock screenshots are used.)

## Architecture

[System architecture](docs/case-study/diagrams/architecture.md) —
Mermaid source, rendered on GitHub.

Historical F1 data flows through a data platform (173 terminal sessions,
171 complete / 2 partial) into a temporal feature engine that enforces the
exact-T contract. The engine feeds two things: a frozen winner model and
factual race states. Race states fan out to replay, Monte Carlo simulation,
and explainability; simulation feeds strategy comparison. A FastAPI surface
serves all of it to a Next.js frontend. Deployment is deliberately boring:
two containers, a validated artifact bundle, no database, no queue, no
cluster — none was needed. Details and the deployment topology live in the
[case study](docs/case-study/TECHNICAL_CASE_STUDY.md) and
[About dossier](frontend/data/about.v1.json).

Serving keeps a strict separation the diagrams make visible: the prediction
path turns one exact historical state into one frozen model snapshot, while
the simulation path turns the same state into thousands of stochastic
futures. Both read the same artifacts and the same code contracts, but they
answer different questions — "what does the model say about this state" vs
"what happens from here across simulated futures" — and their numbers are
never mixed. That separation is enforced in schemas, response notes, and
frontend copy alike, and it is why the repository can present evaluation
evidence for each path without either record undermining the other.

## Temporal Safety

The load-bearing constraint of the whole project: at race time T, the model
may only see what was observable at or before T.

- State is clocked at exact lap-end time T.
- Rival observations must satisfy state_time ≤ T (same-lap future forbidden).
- No fall-forward: replay serves exact checkpoints only, never nearest-state
  substitution.
- Labels live in a side channel; feature calculators take no label input.
- Model development used chronological expanding folds, never random splits.
- 2025 was evaluated exactly once, then sealed; every 2025 serving path
  returns 404 `unknown_race`.

A 20-threat adversarial suite mutates all source families just after the
cutoff and proves earlier predictive state is bit-identical — no leakage
detected (evidence wording, never a guarantee). See the
[temporal-safety diagram](docs/case-study/diagrams/temporal-safety.md).

## Prediction Model

LogisticRegression (C=0.01, lbfgs), 84 features (ALL_84 v8), uncalibrated
RAW output — retained over Platt/Isotonic on development evidence. Trained
2018–2024 (FINAL_FIT, 149 races); evaluated once on the 2025 holdout (24
races). Crucially, outputs are **independent per-driver binary winner
probabilities**: they do not sum to 1 across the field and must never be
renormalized into a race-winner distribution. The API says so on every
response.

## Monte Carlo Simulation

Simulation starts from a factual RaceState (exact anchor key — arbitrary
state JSON is never accepted), combines empirical parameters estimated
through 2024 with a deterministic seed, and runs N stochastic trajectories
with mutually exclusive finishing orders per trial. Outputs are win/podium
frequencies, expected finish, and position distributions. Up to 10,000
trials per request; a 10,000-trial run completes in about 16.5 s on local
container infrastructure (Apple M4, concurrency 1).

These frequencies are a different semantic object from Phase-3 winner
predictions — simulated outcome frequencies vs independent binary
estimates — and the simulation validation record does not supersede the
winner-model record. Deferred dynamics are stated plainly: no weather,
safety-car, reliability, traffic, or compound pace effects.

## Strategy Comparison

Baseline (factual continuation) vs up to 4 candidate interventions
(STAY_OUT, PIT_NOW, PIT_NEXT_LAP, compound options) under an explicit
objective — maximize win probability, maximize podium probability, or
minimize expected finish. Baseline and candidates share common random
numbers, so deltas are paired; uncertainty comes from a B=2000 paired
bootstrap, classified as improvement, degradation, inconclusive, or
uncertainty-unavailable. About one second locally for a 100-simulation
comparison. Validation: 99 anchors → 35 eligible states, 83 red-team
checks, 0 blockers.

## Explainability

Every served prediction decomposes exactly: `z = intercept + Σ
contribution_j`, `p = sigmoid(z)`, with intercept plus contributions
reconstructing the logit to residual 0.0 (tolerance 1e-12) and top
positive/negative contributions derived per feature — served on demand in
about 22 ms. Timeline-change explanations difference consecutive
checkpoints. Global permutation evidence is explicitly in-sample
(pre-2025 final fit; no fold estimators survive the freeze, and
retraining is forbidden). No SHAP. All of it associational log-odds, never
causal and never probability increments.

## Validation

Three tiers, kept separate — Tier-1 never implies Tier-3:

- **Tier 1** — source-safe CI (`make ci`): clean-checkout capable, 2480
  passed / 4 xfailed, 0 failures (2,489 of 3,210 collected; corpus-dependent
  nodes deselected).
- **Tier 2** — deployable runtime: validated bundle + Docker/Compose +
  readiness gate + endpoint and workflow smoke.
- **Tier 3** — full scientific regression (`make science`, canonical corpus
  required): 3193 passed / 5 skipped / 4 xfailed, 0 failures in ~57 min.

Skips are file-presence guards (corpus absent vs present), shown as
measured. The two suites answer different questions on purpose: Tier-1
asks "is the source tree sound and deployable", Tier-3 asks "does the
frozen science still reproduce". A green Tier-1 is never presented as
science validation. The corpus itself is canonical local data that cannot
ship in git, which is why the tiers exist at all — the split is
architectural, not a testing gap. See the [validation visual](docs/case-study/diagrams/validation-pyramid.md).

## Performance

Local container HTTP, Apple M4, concurrency 1 ([methodology](docs/PHASE11_P11_3_FINAL_PERFORMANCE_BENCHMARK.md)):

| Operation | p50 | p95 |
|---|---|---|
| Prediction (20-driver snapshot) | 102.2 ms | 109.4 ms |
| Replay cache HIT | 1.0 ms | 1.7 ms |
| Explanation | 22.5 ms | 24.7 ms |
| 10,000-trial simulation | ≈16.5 s | ≈16.6 s |
| Strategy comparison | ≈1.09 s | ≈1.13 s |

Local loopback evidence only — not cloud latency, not throughput, not
browser timing, and endpoint duration is never presented as model
inference latency.

## Running Locally

Requirements: Python 3.11, Node 22, Docker + Compose. The canonical corpus
(Tier-3 data) is not needed to run the product — only the validated
runtime bundle.

```bash
python scripts/prepare_runtime_artifacts.py --validate  # VALID: 1939 files
make preflight                                          # deployable gate
make docker-compose-up                                  # backend :8000, frontend :3000
curl localhost:8000/ready
make docker-compose-down
```

Native development: `make backend-prod` (single-process uvicorn, no
reload) and `cd frontend && npm run dev`. If `python3` on your machine is
a non-functional shim, prefix with `make PYTHON=/path/to/python3.11
<target>`.

A quick end-to-end check against the running stack exercises the frozen
anchor used throughout validation (2019-r01-R, Bottas, lap 1):

```bash
curl "localhost:8000/v2/races/2019-r01-R/state?anchor_driver_id=bottas&anchor_lap_number=1&anchor_state_time_s=2106.767"
curl -X POST localhost:8000/v2/predictions/winner-snapshot \
  -H 'Content-Type: application/json' \
  -d '{"race_id":"2019-r01-R","anchor_driver_id":"bottas","anchor_lap_number":1,"anchor_state_time_s":2106.767}'
```

The snapshot returns independent per-driver probabilities that do not sum
to 1 — that is the semantics working as specified, not a bug. Requests
for any 2025 race return 404 `unknown_race`: the holdout firewall, live.

## Testing

- `make ci` — ordinary source-safe CI (Python + frontend, clean-checkout
  safe).
- `make science` — full scientific regression over the canonical local
  corpus (~1 h, single-core). Fails early without the corpus; downloads
  and generates nothing.
- `make preflight-source` — tracked-declarations gate for fresh clones.
- `make preflight` — deployable gate: source + validated bundle +
  network-off.

## Technology

Python 3.11, FastAPI + uvicorn, scikit-learn (LogisticRegression),
pandas/parquet, NumPy; Next.js 16, React 19, Tailwind v4; Docker +
Compose; pytest, node:test, TypeScript, eslint. Nothing else runs the
system — no database, queue, or orchestrator by design.

## Limitations

Independent binary probabilities (never a race distribution); 2025
evaluated but never served; simulation assumes free-air,
constructor-shared pace with weather/safety-car/reliability/traffic
deferred; strategy compares single decisions, never prescribes;
explanations are associational with in-sample permutation evidence;
checkpoint-granular timeline, no spatial track; no live feed; arm64
validation only, no cloud deployment, no browser-engine or WCAG
certification; Tier-3 needs the canonical corpus (~1 h). The full
matrix is in the [fact sheet](docs/case-study/PORTFOLIO_FACT_SHEET.md).

## Technical Case Study

Depth lives in [docs/case-study/TECHNICAL_CASE_STUDY.md](docs/case-study/TECHNICAL_CASE_STUDY.md):
problem, data platform, temporal engineering, model development, holdout
results, serving, replay, explainability, simulation, strategy, product,
productionization, validation, performance, difficulties, limitations,
future work — each with evidence, trade-offs, and mathematics where it
clarifies.

## Repository Guide

- `api/` — FastAPI surface (`/health`, `/ready`, legacy prediction routes,
  and the versioned `/v2/...` public API routes with schemas, services,
  readiness, observability). `/v2/` is the API contract version, not the
  implementation package.
- `raceintel/` — current race-intelligence implementation: data platform
  stages (`data/`, `pipeline/`), temporal features (`features/`), labels
  (`labels/`), race state (`race_state/`), replay (`replay/`), Monte Carlo
  simulation (`simulation/`), strategy (`strategy/`), explainability
  (`explainability/`), model lab (`model_lab/`), experiments (`experiments/`).
- `ml/` — frozen legacy serving compatibility (legacy pipelines behind the
  legacy prediction routes; covered by regression contracts, do not retrain
  or migrate).
- `v2/` — minimal compatibility shim only (re-exports
  `raceintel.model_lab` so the frozen serving artifact, which embeds the
  `v2.model_lab.preprocessing.FittedPreprocessor` class path, keeps
  loading). Not active implementation.
- `frontend/` — Next.js 16 product (`app/`, `features/`) plus static
  evidence dossiers (`frontend/data/about.v1.json`,
  `frontend/data/models.v1.json`).
- `scripts/` — runtime/CI/benchmark tooling (artifact prep, preflights,
  Tier-1 selectors, P11-3 benchmark).
- `tests/` — 3,210 tests across Tier-1/Tier-3.
- `docs/` — start at [docs/README.md](docs/README.md): phase reports and
  freeze manifests; `docs/case-study/` — portfolio evidence layer;
  `results/v2_final_validation/` — machine-readable P11 validation records.

## Future Work

Explicitly future, not implemented: spatial track replay; learned race
dynamics (weather, safety-car, reliability, overtaking, compound pace);
richer multi-stop strategy search; outcome-distribution modelling; model
ensembles only if held-out evidence supports them. v2 is frozen as
described above.
