# F1 Intelligence — Domain Index

Index over the stage-numbered history. This file replaces nothing: every
`V2_*` / `V3_*` / `PHASE*` / `D*` document, script, result, and test keeps
its authority as the frozen record. Numbers like `V3_8D` are experiment
codes — look concepts up here, do not memorize the codes.

All paths below were verified to exist. If a path and this index ever
disagree, the repository wins.

## Repository area map

- `raceintel/` — authoritative production/scientific implementation.
  Domain packages (simulation, model_lab, strategy, …). If domain logic
  exists here, this copy is the one that matters.
- `api/` — HTTP/product composition layer. Thin routes + services over
  `raceintel/` (and the `ml/` legacy path). Composition root: `api/main.py`.
- `frontend/` — product UI (Next.js). App routes, features, clients.
- `ml/` — legacy serving/inference area still used by specific paths
  (the R4 prediction route via `api/services/prediction_service.py`).
- `scripts/` — historical/research entry points and existing frozen
  research code. Flat directory; many stage entry points; some frozen
  scripts contain real domain logic (see `scripts/README.md`).
- `tests/` — test suites, freeze guards, temporal/provenance checks.
  199 test files, collection pinned (currently 5268).
- `results/` — scientific evidence and generated research outputs
  (machine-readable JSON, ledgers, scientific cards).
- `docs/` — scientific reports, freezes, architectural/navigation
  documentation (this file lives here).

Frozen `V3_*` scripts/results/docs/tests are provenance artifacts.
Do not move or rename them casually. Guard allowlists and lineage
references key on their exact paths.

## Current development state

- V3.10 production (`v3.10-pit-wall` == `2c00e7e`) is frozen.
- V3.11A–E are complete and frozen (terminal programme; see
  `docs/V3_11_MC2_COVERAGE_EXPANSION_FINAL.md`).
  Final classifications: A `MC2_COVERAGE_FORENSICS_COMPLETE`, B
  `CAUSAL_STATE_RECONSTRUCTION_REJECTED`, C
  `TRACK_SOURCE_REGIME_FORENSICS_COMPLETE`, D
  `VSC_REGIME_MODEL_INSUFFICIENT_EVIDENCE`, E
  `VSC_EVIDENCE_STILL_INSUFFICIENT`.
- V3.11D/E did NOT authorize VSC integration. Coverage expansion is
  terminal: STOP_V3_11_COVERAGE_EXPANSION.
- MC2 production coverage remains 3678/9644 = 38.14%.
- V3 programme is frozen (see `docs/V3_FINAL_PROGRAMME_SYNTHESIS.md`;
  final tag `v3-final`). Active V3 development has ended.
- Frozen scientific evidence must not be moved or renamed.

## Platform / data ingestion

Authoritative implementation: `raceintel/data/`, `raceintel/pipeline/`
(D6–D11 gates: `d6.py`, `d7.py`, `d8.py`, `d9.py`, `d10.py`, `d11.py` plus
schemas), `raceintel/contracts.py` (stdlib-only canonical contracts).

Status: production, frozen through V3.10.

Key tests: `tests/test_v2_contracts.py`, `tests/test_v2_d7.py`,
`tests/test_datasets.py`.

Frozen evidence: `results/data_quality/`, `results/post_v2_consolidation/`.

Key docs: `docs/DATA_PLATFORM_ARCHITECTURE.md`,
`docs/DATASET_V2_REPORT.md`, `docs/D0_FOUNDATION_VERIFICATION.md`.

Stage lineage: Phase 1 data platform → V2 consolidated baseline.

Current authority: `raceintel/pipeline/` gates + `raceintel/contracts.py`.

## RaceState / temporal state

Authoritative implementation: `raceintel/race_state/` (`race_state.py`,
`race_state_reconstruction.py`, `race_state_features.py`).

Status: production, frozen through V3.10.

Key tests: `tests/test_v2_phase4_*` (7 files: race state + prediction
service phase).

Frozen evidence: `results/v2_validation/`.

Stage lineage: V2 Phase 4 → replay/simulation consumers in Phase 5/6.

Current authority: `raceintel/race_state/`.

Notes: V3.11B causal state reconstruction was REJECTED — no persistence
rules were added; reconstruction semantics remain exactly as frozen.

## Feature engineering

Authoritative implementation: `raceintel/features/` (engine, registry,
contracts, pace/gaps/rates/temporal/interactions).

Status: production, frozen through V3.10.

Key tests: `tests/test_v2_features_f*.py` (F2/F3/F4/F10–F12/F14/F15).

Frozen evidence: `results/v2_validation/`.

Key docs: `docs/PHASE1_EXIT_REPORT.md`, `docs/PHASE1_FINAL_VALIDATION.md`.

Stage lineage: V2 temporal feature engine → consumed by Model Lab,
simulation, replay.

Current authority: `raceintel/features/`.

## Winner prediction

Authoritative production serving: `ml/` (`config.py`, `features.py`,
`inference.py`) via `api/services/prediction_service.py`,
`api/routes.py`, `api/schemas.py` (legacy R4 route family, still mounted).

Model science: `raceintel/model_lab/` with per-stage harnesses
(`v3_3b_harness.py`, `v3_3d_refinement.py`, `v3_4_ensemble.py`,
`v3_dynamics_experiment.py`).

Status: production serving path (legacy R4) + frozen model science.

Key tests: `tests/test_ensemble.py`,
`tests/test_prediction_equivalence.py`, `tests/test_model_loading.py`,
`tests/test_datasets.py`, `tests/test_known_defects.py`,
`tests/test_api_baseline.py`, `tests/test_v3_3*`, `tests/test_v3_4*`,
`tests/test_v3_5*`.

Frozen evidence: `results/models/` (hgb/logreg/xgboost lap checkpoints),
`results/v3/v3_3*`, `results/v3/v3_4*`, `results/v3/v3_5*`
(incl. `v3_3_freeze.json`, `v3_4_freeze.json`, `v3_5_freeze.json`).

Key docs: `docs/MODEL_LAB_FINAL_MODEL_CARD.md`, `docs/V3_5_FINAL_REPORT.md`.

Stage lineage: R4 baseline → Model Lab (M-series) → V3.3 temporal
evaluation → V3.4 ensembles → V3.5 outcome models.

Current authority: serving = `ml/` + `api/services/prediction_service.py`;
science = `raceintel/model_lab/` + frozen V3.3–V3.5 records.

## Model Lab

Authoritative implementation: `raceintel/model_lab/` (52 modules:
protocol, splits, runners, suites, calibration, final fit, `serving.py`).
Serving artifacts consumed in production by `api/v2_service.py` and
`api/readiness.py`.

Status: science infrastructure (frozen) + production serving seam.

Key tests: `tests/test_v2_model_lab_m0.py`,
`tests/test_v2_model_lab_m1.py`, `tests/model_lab_helpers.py`
(helpers), `tests/test_v3_3*`, `tests/test_v3_4*`.

Frozen evidence: `results/v2_model_lab/`, `results/v3/v3_3*`,
`results/v3/v3_4*`.

Key docs: `docs/MODEL_LAB_*.md` (14 reports incl. protocol, calibration,
final model card), `docs/V3_3*`, `docs/V3_4*`.

Stage lineage: V2 Model Lab (M0/M1) → V3.3 temporal evaluation →
V3.4 ensemble selection.

Current authority: `raceintel/model_lab/`.

## Monte Carlo / MC2

Authoritative production: `raceintel/simulation/` (`engine.py`,
`monte_carlo.py`, `mc2_batch.py`, `rng.py`, `state.py`, `params.py`,
`adapter.py`, `regime_support.py`, `presence.py`, `driver_status.py`).

Status: production, frozen through V3.10 + performance engineering.

Key tests: `tests/test_v2_phase6_*` (11 files: simulation engine),
`tests/test_v3_2*` (20 files: MC2 science),
`tests/test_mc2_batch_p1.py`, `tests/test_mc2_p2a.py`,
`tests/test_mc2_p2b.py`, `tests/test_mc2_p3_1.py`,
`tests/test_perf_mc2_p0.py`, `tests/test_perf_mc2_freeze.py`.

Frozen evidence: `results/v3/v3_2*` (incl. `v3_2_freeze.json`,
`v3_2n_final_validation.json`), `results/v3/performance_mc2/`.

Key docs: `docs/V3_2*`, `docs/MC2_PERFORMANCE_*.md` (6 files).

Stage lineage: V2 Monte Carlo engine → V3.2 causal MC2 (a–n) →
deterministic performance engineering (P0–P3.1).

Current authority: production MC2 from V3.2 + later performance
optimizations.

Notes: V3.11 track-regime work is research-only and not integrated.
Coverage 3678/9644 = 38.14%.

## Strategy

Authoritative implementation: `raceintel/strategy/` (Phase-7 S1–S5:
`contracts.py`, `candidates.py`, `comparison.py`, `objectives.py`,
`paired.py`, `interventions.py`, `uncertainty.py`) plus V3.6 Strategy 2.0
(`v3_contracts.py`, `v3_engine.py` — thin orchestration reusing Phase-7
S3/S4/S5 verbatim).

API: `api/v2_strategy_*` (`POST /v2/strategies/compare`) and
`api/v2_strategy_v3_*` (`POST /v2/strategies/compare-v3`,
`GET /v2/strategies/v3/availability`). Both mounted in `api/main.py`.

Frontend: `frontend/features/strategy/`, `frontend/app/strategy/page.tsx`
(both `strategyMachine` and `strategy2Machine` clients exist).

Status: production, frozen through V3.10.

Key tests: `tests/test_v2_phase7_*` (9 files),
`tests/test_v2_phase7_s7_strategy_api.py`, `tests/test_v3_6*` (7 files).

Frozen evidence: `results/v3/v3_6*` (incl. `v3_6_freeze.json`),
`runtime_artifacts/v3_strategy_cache/` (generated, reproducible).

Key docs: `docs/V3_6A_STRATEGY_LANDSCAPE_AND_SCIENTIFIC_CONTRACT.md`,
`docs/V3_6B_STRATEGY_CONTRACTS_ACTION_VALIDITY_AND_ELIGIBILITY.md`,
`docs/V3_6C_PAIRED_MC2_STRATEGY_ENGINE.md`.

Stage lineage: V2 Phase-7 strategy → V3.6 Strategy 2.0 paired engine.

Current authority: AUTHORITY_NOT_YET_FORMALIZED. Both families are live
and additive (the 2.0 route file states Phase-7 is "untouched and
unimported"; the package `__init__.py` exports Phase-7 only). No
repository evidence marks either family legacy, deprecated, or canonical.
Strategy 2.0 is newer and reuses Phase-7 machinery; that alone does not
make it canonical. Do not retire either without a formal decision.

## Counterfactuals

Authoritative implementation: `raceintel/counterfactual/`,
`api/v2_counterfactual_*`, `frontend/features/counterfactuals/`,
`frontend/app/counterfactuals/page.tsx`.

Status: production, frozen through V3.10.

Key tests: `tests/test_v3_7*` (7 files).

Frozen evidence: `results/v3/v3_7*/` (incl. `v3_7d_historical_evaluation`),
`runtime_artifacts/v3_7_counterfactual_cache/` (generated, reproducible).

Key docs: `docs/V3_7A_COUNTERFACTUAL_LANDSCAPE_AND_SCIENTIFIC_CONTRACT.md`,
`docs/V3_7C_COUNTERFACTUAL_EXECUTION_ENGINE.md`,
`docs/V3_7D_HISTORICAL_EVALUATION_AND_EMPIRICAL_GATE.md`,
`docs/V3_7H_FINAL_VALIDATION_FREEZE.md`.

Stage lineage: V2 counterfactual strategy engine → V3.7 counterfactuals.

Current authority: `raceintel/counterfactual/` + V3.7 records.

## Consensus

Authoritative implementation: `raceintel/consensus/` (adapters,
alignment, contracts, metrics, product, trajectories),
`api/v2_consensus_*`, `frontend/features/consensus/`,
`frontend/app/consensus/page.tsx`.

Status: production, frozen through V3.10.

Key tests: `tests/test_v3_8*` (11 files).

Frozen evidence: `results/v3/v3_8*/`.

Key docs: `docs/V3_8*` (8 files).

Stage lineage: V3.8 model-simulation consensus.

Current authority: `raceintel/consensus/` + V3.8 records.

## Uncertainty

Authoritative implementation: `raceintel/uncertainty/`,
`api/v2_uncertainty_*`, `frontend/features/uncertainty/`,
`frontend/app/uncertainty/page.tsx`.

Status: production, frozen through V3.10.

Key tests: `tests/test_v3_9*` (4 files),
`tests/test_v2_phase7_s5_uncertainty.py`.

Frozen evidence: `results/v3/v3_9*/`.

Key docs: `docs/V3_9*` (5 files).

Stage lineage: Phase-7 S5 sampling uncertainty → V3.9 uncertainty
intelligence.

Current authority: `raceintel/uncertainty/` + V3.9 records.

## Spatial replay

Authoritative implementation: `raceintel/spatial/`,
`raceintel/replay/` (`replay.py`, `replay_predictions.py`,
`replay_probability_timeline.py`, `replay_reconstruction.py`),
`api/v2_spatial_*`, `api/v2_replay_*`, `frontend/lib/spatial.ts`,
`frontend/features/replay/`, `frontend/app/replay/page.tsx`,
`frontend/app/spatial/page.tsx`.

Status: production, frozen through V3.10.

Key tests: `tests/test_spatial_*.py` (8 files: api, contracts,
firewall, geometry, ingestion, manifest, resolver, validation),
`tests/test_v2_phase5_*` (7 files: historical replay),
`tests/test_v2_phase8_*` (5 files: replay intelligence).

Frozen evidence: `results/phase12/`, `results/v2_replay/` (generated,
reproducible — not committed).

Key docs: `docs/PHASE12_*.md` (spatial program reports).

Stage lineage: V2 historical replay (Phase 5) → replay intelligence
(Phase 8) → Phase-12 spatial program.

Current authority: `raceintel/spatial/` + `raceintel/replay/`.

## Pit Wall

Authoritative implementation: product composition over telemetry +
replay + strategy. `frontend/app/pit-wall/page.tsx`,
`frontend/features/pit-wall/` (components, hooks, lib),
`api/v2_telemetry_*`.

Status: production, frozen at V3.10.

Key tests: `tests/test_v3_10b_workspace_ownership.py`,
`tests/test_v3_10f_telemetry.py`.

Frozen evidence: `results/v3/v3_10a/` … `results/v3/v3_10i/`.

Key docs: `docs/V3_10_PIT_WALL_FINAL.md`,
`docs/V3_10A_PIT_WALL_INFORMATION_ARCHITECTURE.md`,
`docs/V3_10B_SHARED_WORKSPACE_STATE.md`,
`docs/V3_10C_PIT_WALL_SHELL.md`,
`docs/V3_10D_RACE_CONTROL_EVENT_TIMELINE.md`,
`docs/V3_10E_DRIVER_INTELLIGENCE.md`,
`docs/V3_10F_DRIVER_TELEMETRY.md`,
`docs/V3_10G_CONTEXTUAL_DECISION_EXPLORATION.md`,
`docs/V3_10H_PRODUCT_POLISH.md`.

Stage lineage: V3.10 integrated race intelligence workspace
(`v3.10-pit-wall`).

Current authority: V3.10 pit-wall records (HEAD).

## Track regime research

Research implementation (NOT production): `scripts/v3_11c_*.py`
(sources, regimes, ledger), `scripts/v3_11a_mc2_coverage_forensics.py`
(coverage forensics).

Status: frozen research (committed at the V3.11 freeze). V3.11C verdict:
TRACK_SOURCE_REGIME_FORENSICS_COMPLETE — forensics only, no regime
simulation, no eligibility change.

Key tests: `tests/test_v3_11a_forensics.py`,
`tests/test_v3_11c_track_forensics.py`.

Evidence: `results/v3/v3_11a/`, `results/v3/v3_11c/` (incl.
`track_candidate_ledger.csv`, `scientific_card.json`).

Key docs: `docs/V3_11A_MC2_COVERAGE_FORENSICS.md`,
`docs/V3_11C_TRACK_SOURCE_REGIME_FORENSICS.md`.

Stage lineage: V3.2F/V3.2H regime precursors
(`results/v3/v3_2f*`, `results/v3/v3_2h_regime_models.json`) →
V3.11A coverage forensics → V3.11C track-source/regime forensics.

Current authority: research verdicts in the V3.11A/V3.11C scientific
cards. No production integration authorized.

## VSC research

Research implementation (NOT production): `scripts/v3_11d_*.py`
(episodes, analysis, protocol, `v3_11d_vsc_model.py`, validation).

Status: frozen research (committed at the V3.11 freeze). V3.11D verdict:
VSC_REGIME_MODEL_INSUFFICIENT_EVIDENCE — no production integration
authorized, no eligibility change.

Key tests: `tests/test_v3_11d_vsc_model.py`.

Evidence: `results/v3/v3_11d/` (incl. `vsc_episode_dataset.csv`,
`scientific_card.json`).

Key docs: `docs/V3_11D_VSC_REGIME_MODEL.md`.

Stage lineage: V3.2F/V3.2H VSC precursors → V3.11C recommendation
(VSC as the only F2-feasible regime) → V3.11D validation.

Current authority: research verdict in the V3.11D scientific card.
VSC integration explicitly NOT authorized.

## API

Authoritative implementation: `api/main.py` (composition root, 13
routers), `api/config.py`, `api/observability.py`, `api/readiness.py`,
`api/routes.py` + `api/schemas.py` (R4 family),
`api/v2_routes.py` + `api/v2_schemas.py` + `api/v2_service.py`,
per-domain triples (`api/v2_*_routes/schemas/service.py`),
`api/services/prediction_service.py`.

Status: production, frozen through V3.10.

Key tests: `tests/test_api_baseline.py`, `tests/test_readiness.py`,
`tests/test_request_observability.py`,
`tests/test_backend_container_contract.py`,
`tests/test_compose_contract.py`, `tests/test_ci_contract.py`,
`tests/test_production_reproducibility_contract.py`.

Stage lineage: R4 baseline → V2 route families (R5) → P10
productionization → V3.x domain additions (additive only).

Current authority: `api/main.py` mount list.

## Frontend

Authoritative implementation: `frontend/app/` (routes incl. consensus,
counterfactuals, models, pit-wall, replay, simulator, spatial,
strategy, uncertainty), `frontend/features/` (11 domains),
`frontend/components/`, `frontend/lib/` (`v2.ts` app-wide client,
`api.ts`, `spatial.ts`, prediction helpers).

Status: production, frozen through V3.10.

Key tests: colocated `frontend/lib/*.test.ts`,
`scripts/run_ci_frontend_tests.py` gate.

Key docs: `docs/FRONTEND_DESIGN_SYSTEM.md`,
`docs/FRONTEND_FOUNDATION_FREEZE_REPORT.md`.

Stage lineage: race intelligence workspace foundation → per-domain
features → V3.10 pit-wall workspace.

Current authority: `frontend/` as frozen at V3.10.

## Legacy model areas (ml / model_lab / v2)

Repository evidence only; nothing here is moved, deleted, or retired.

- `ml/` — HAS production consumers. Used by
  `api/services/prediction_service.py` (the mounted R4 prediction route)
  plus prediction/ensemble tests (`tests/test_ensemble.py`,
  `tests/test_prediction_equivalence.py`, `tests/test_model_loading.py`,
  `tests/test_datasets.py`, `tests/test_known_defects.py`,
  `tests/conftest.py`). Legacy serving/inference seam: keep working.
- `raceintel/model_lab/` — science infrastructure AND production serving
  seam. `raceintel/model_lab/serving.py` is imported by
  `api/v2_service.py` and `api/readiness.py`. The 52-module package holds
  both frozen experiment machinery and live serving artifacts.
- `v2/` — NO importers found in `raceintel/`, `api/`, `scripts/`, or
  `tests/` (only `v2/__init__.py` + `v2/model_lab/preprocessing.py` plus
  caches). Appears unused/dead, BUT it is intentionally tracked baseline
  code (see the V2 canonical-data comment in `.gitignore`). Do not delete
  or relocate without a provenance review and a recorded decision. No ADR
  exists yet.

## SAFE START FOR AGENTS

1. Read `docs/INDEX.md` first.
2. Use Graphify before broad file reads.
3. Identify whether target code is production, research, or frozen.
4. Do not modify frozen stage evidence without explicit authorization.
5. Prefer authoritative `raceintel/` modules over copying logic into
   `scripts/`.
6. Preserve temporal safety / provenance / holdout rules.
7. Check stage-specific scientific docs before altering model behavior.

## POST-V3 ARCHITECTURE BACKLOG

Source: the read-only architecture audit (HTML report kept outside the
repo — do NOT copy it in). Listed here without implementing:

- C1 — deepen model_lab suite orchestration
- C2 — API registration seam
- C4 — reconcile model worlds / v2 legacy
- C5 — split frontend v2.ts client
- C7 — derive guard pins from one source
- C8 — strategy legacy/canonical cleanup

DO NOT IMPLEMENT DURING ACTIVE V3 DEVELOPMENT unless separately
authorized.



