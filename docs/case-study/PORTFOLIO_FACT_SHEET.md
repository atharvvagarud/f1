# Portfolio Fact Sheet (P11-5 source — facts only, no prose)

## Project

F1 Intelligence v2: in-race winner-prediction intelligence over frozen
historical Formula 1 data. Six surfaces: Predict, Replay, Simulator,
Strategy, Models, About. Local deployable runtime, no live feed.

## Dataset

Tier B (1950–2025): 76 seasons, 1149 races, 25784 results (priors
only). Tier A (2018–2025): 173 terminal sessions (171 COMPLETE, 2
PARTIAL: 2021-r12-R, 2022-r18-R), 189420 driver laps, 3458 results,
6336 pit stops, 9324 stints, 25779 weather rows, 14992 race-control
rows. Temporal matrix: 189420 states, 84 predictive features, 106
columns.

## Temporal safety

Exact-T LAP_END clock; rival observations ≤T; label firewall by
construction; no fall-forward; exact replay checkpoints; chronological
folds D1–D3; 2025 sealed after one-shot use. 20-threat adversarial
suite: no leakage detected (never "zero guaranteed").

## Model

LogisticRegression C=0.01 (lbfgs, max_iter 1000), ALL_84 v8, RAW
(retained over Platt/Isotonic), INDEPENDENT_BINARY, FINAL_FIT
2018–2024 (149 races, 162728 states).

## Holdout results

2025 ONE-SHOT HOLDOUT (24 races, 26692 states), race-macro: Log Loss
0.0680, Brier 0.0200, ROC-AUC 0.9845, PR-AUC 0.8032, ECE 0.0111,
Top-1 79.6%, Top-3 97.9%. Stages: EARLY 0.077468 / MID 0.069800 /
LATE 0.056847.

## Replay

149 races, 9644 exact checkpoints, HIT-only cached predictions
(≈1 ms), 189610 observable + 3206 nulls (served as null). 2025 → 404.

## Simulation

Factual RaceState + phase6-r3-empirical params through 2024 +
deterministic seed → mutually exclusive trajectories. Validation
(42 states / 23 races): LL 1.2237, Brier 0.02669, Top-1 0.643,
Top-3 0.881, MAE 2.4452, RPS 0.0928, ECE 0.01899. 10k trials ≈16.5 s
container. Assumes: free-air, constructor-shared pace, no DNF/SC/VSC/
weather/traffic; over-pitting ≈0.3–0.4; compound = identity only.

## Strategy

STAY_OUT / PIT_NOW / PIT_NEXT_LAP (+ compound options); objectives
WIN/PODIUM/FINISH (required, no default); paired CRN deltas + B=2000
bootstrap; classifications IMPROVEMENT / DEGRADATION / INCONCLUSIVE /
UNCERTAINTY_UNAVAILABLE. 99 anchors → 35 eligible; 83 checks, 0
blockers; CRN VR median 0.922 (mixed, never universal). Compares only;
≈1.1 s container.

## Explainability

LOG_ODDS decomposition (intercept + contributions reconstruct logit
within 1e-12), associational not causal, missingness preserved,
on-demand ≈22 ms. Permutation evidence in-sample; no SHAP.

## Validation

Tier-1 clean: 1971 passed / 501 skipped / 4 xfailed, 0 failures.
Tier-3: 3193 passed / 5 skipped / 4 xfailed, 0 failures (57:28).
Stale debt 0; corpus-dependent 721 (architecture, not debt).

## Performance

Local container HTTP, Apple M4, concurrency 1: predict p50 102.2 ms /
p95 109.4 ms; replay HIT p50 1.0 / p95 1.7 ms; explanation p50 22.5 /
p95 24.7 ms; 10k simulation ≈16.5 s; strategy ≈1.09 s. Local-only;
no browser/throughput/cloud claims.

## Deployment

Exactly two Compose services, non-root, read-only rootfs, /tmp tmpfs,
no mounts, no secrets, network ingestion OFF, CORS localhost:3000
only, /health liveness vs /ready 6-check readiness. Bundle
runtime-artifacts-v1 (1939 files, SHA `e4008425…`). arm64 only; no
cloud deployment.

## Limitations

Independent-binary (unnormalized); 2025 unserved; MC empirical
assumptions; weather/SC/VSC/reliability deferred; compound pace
limitation; single-decision strategy; associational explanations;
checkpoint granularity; no spatial track; no live feed; no DB/Redis/
worker by design; bundle required; arm64 only; no browser validation;
no WCAG certification; Tier-3 corpus + ≈1 h; endpoint duration ≠
inference latency.
