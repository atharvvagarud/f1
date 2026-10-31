# Docs quick map

The [GitHub Wiki](https://github.com/atharvvagarud/f1/wiki) is the guided
documentation. This file maps the current repository docs. The full
versioned engineering and scientific record lives in
[INDEX.md](INDEX.md).

Historical phase reports are frozen records: they describe the repository
as it was (the `v2/` implementation namespace predates the C2 rename to
`raceintel/`), not as it is. Current architecture lives in
[architecture/CURRENT_ARCHITECTURE.md](architecture/CURRENT_ARCHITECTURE.md);
setup and commands live in
[development/DEVELOPMENT.md](development/DEVELOPMENT.md).

## Getting started

- Root [README.md](../README.md): product, capabilities, running, testing.
- [development/DEVELOPMENT.md](development/DEVELOPMENT.md): bootstrap,
  dev servers, validation, Docker/Compose, generated artifacts.
- [../data/README.md](../data/README.md): data platform, canonical
  entities, build/validate commands.

## Architecture

- [architecture/CURRENT_ARCHITECTURE.md](architecture/CURRENT_ARCHITECTURE.md):
  post-consolidation system layers, package responsibilities, boundaries.
- [DATA_PLATFORM_ARCHITECTURE.md](DATA_PLATFORM_ARCHITECTURE.md): Tier-A /
  Tier-B platform design.
- [case-study/diagrams/architecture.md](case-study/diagrams/architecture.md):
  system diagram (Mermaid).
- [case-study/diagrams/deployment.md](case-study/diagrams/deployment.md):
  deployment topology.

## Scientific methodology

- [DATASET_V2_REPORT.md](DATASET_V2_REPORT.md): canonical dataset report.
- [PHASE2_FINAL_REPORT.md](PHASE2_FINAL_REPORT.md): temporal feature
  engine, exact-T contract.
- [PHASE2_FEATURE_REGISTRY.md](PHASE2_FEATURE_REGISTRY.md): feature registry.
- [MODEL_LAB_FINAL_REPORT.md](MODEL_LAB_FINAL_REPORT.md) and
  [MODEL_LAB_FINAL_MODEL_CARD.md](MODEL_LAB_FINAL_MODEL_CARD.md): model
  development and the frozen winner model.

## Evaluation

- [PHASE11_P11_7_FINAL_V2_FREEZE.md](PHASE11_P11_7_FINAL_V2_FREEZE.md):
  final freeze: 2025 one-shot holdout, scientific validation outcome.
- [PHASE11_P11_3_FINAL_PERFORMANCE_BENCHMARK.md](PHASE11_P11_3_FINAL_PERFORMANCE_BENCHMARK.md):
  local container latency methodology and numbers.
- Freeze manifests: [PHASE4_FREEZE_MANIFEST.json](PHASE4_FREEZE_MANIFEST.json),
  [PHASE5_FREEZE_MANIFEST.json](PHASE5_FREEZE_MANIFEST.json),
  [PHASE6_FREEZE_MANIFEST.json](PHASE6_FREEZE_MANIFEST.json),
  [PHASE7_STRATEGY_FREEZE_MANIFEST.json](PHASE7_STRATEGY_FREEZE_MANIFEST.json),
  [generated/phase2_freeze_manifest.json](generated/phase2_freeze_manifest.json).

## Simulation and strategy

- [PHASE6_MONTE_CARLO_PLAN.md](PHASE6_MONTE_CARLO_PLAN.md) and
  [PHASE6_VALIDATION_REPORT.md](PHASE6_VALIDATION_REPORT.md): simulation.
- [PHASE7_STRATEGY_PLAN.md](PHASE7_STRATEGY_PLAN.md) and
  [PHASE7_STRATEGY_FINAL_REPORT.md](PHASE7_STRATEGY_FINAL_REPORT.md): strategy.
- Diagrams: [case-study/diagrams/monte-carlo.md](case-study/diagrams/monte-carlo.md),
  [case-study/diagrams/strategy.md](case-study/diagrams/strategy.md).

## Spatial replay

- [PHASE12_FINAL_REPORT.md](PHASE12_FINAL_REPORT.md): spatial program
  final report (circuit and pit geometry).
- [PHASE12_P12_0_SPATIAL_DATA_ARCHITECTURE_AUDIT.md](PHASE12_P12_0_SPATIAL_DATA_ARCHITECTURE_AUDIT.md)
  through
  [PHASE12_P12_8_RACE_STATUS_SPATIAL_CONTEXT.md](PHASE12_P12_8_RACE_STATUS_SPATIAL_CONTEXT.md):
  spatial data contract, ingestion, geometry, resolver, API, renderer,
  replay integration.

## V3 programme

- [V3_FINAL_PROGRAMME_SYNTHESIS.md](V3_FINAL_PROGRAMME_SYNTHESIS.md):
  frozen V3 synthesis and final identities.
- [V3_11_MC2_COVERAGE_EXPANSION_FINAL.md](V3_11_MC2_COVERAGE_EXPANSION_FINAL.md):
  terminal MC2 coverage result (3678/9644, 38.14%).
- [MC2_PERFORMANCE_ENGINEERING_FINAL.md](MC2_PERFORMANCE_ENGINEERING_FINAL.md):
  MC2 performance engineering record.
- [V3_10_PIT_WALL_FINAL.md](V3_10_PIT_WALL_FINAL.md): pit-wall workspace
  final report.

## Case study

- [case-study/README.md](case-study/README.md): evidence index.
- [case-study/TECHNICAL_CASE_STUDY.md](case-study/TECHNICAL_CASE_STUDY.md): depth.
- [case-study/PORTFOLIO_FACT_SHEET.md](case-study/PORTFOLIO_FACT_SHEET.md): facts.

## Deployment and runtime

- [PHASE10_P10_1A_RUNTIME_ARTIFACT_CONTRACT.md](PHASE10_P10_1A_RUNTIME_ARTIFACT_CONTRACT.md):
  artifact bundle contract.
- [PHASE10_P10_1B_RUNTIME_BOOTSTRAP_CONTRACT.md](PHASE10_P10_1B_RUNTIME_BOOTSTRAP_CONTRACT.md):
  bootstrap contract.
- [PHASE10_P10_1C_BACKEND_CONTAINER.md](PHASE10_P10_1C_BACKEND_CONTAINER.md),
  [PHASE10_P10_1D_FRONTEND_CONTAINER.md](PHASE10_P10_1D_FRONTEND_CONTAINER.md),
  [PHASE10_P10_1E_COMPOSE_RUNTIME_VALIDATION.md](PHASE10_P10_1E_COMPOSE_RUNTIME_VALIDATION.md):
  containers and Compose validation.
- [PHASE10_P10_2_CONTINUOUS_INTEGRATION.md](PHASE10_P10_2_CONTINUOUS_INTEGRATION.md):
  CI design.

## Architecture decisions

- [adr/ADR-0001-telemetry-retention.md](adr/ADR-0001-telemetry-retention.md):
  telemetry retention.
- [adr/ADR-0002-v2-shim-retention.md](adr/ADR-0002-v2-shim-retention.md):
  `v2/` pickle-compatibility shim retention (post-V3).

## Historical phase reports

Frozen by phase, newest last: Phase 1 (`PHASE1_EXIT_REPORT.md`,
`PHASE1_FINAL_VALIDATION.md`), Phase 2 (`PHASE2_*`), Phase 4
(`PHASE4_*`), Phase 5 (`PHASE5_*`), Phase 6 (`PHASE6_*`), Phase 7
(`PHASE7_*`), Phase 8 (`PHASE8_*`), Phase 9 (`PHASE9_*`), Phase 10
(`PHASE10_*`), Phase 11 (`PHASE11_*`), Phase 12 (`PHASE12_*`), V3
(`V3_*`, `MC2_*`, `MODEL_LAB_*` where V3-scoped). Foundation records:
`D0_FOUNDATION_VERIFICATION.md`, `FOUNDATION_REFACTOR_REPORT.md`,
`LEGACY_V2_DATASET_COMPARISON.md`.

## Post-V2 consolidation

- [POST_V2_C0_REPOSITORY_CONSOLIDATION_AUDIT.md](POST_V2_C0_REPOSITORY_CONSOLIDATION_AUDIT.md)
- [POST_V2_C1_V1_ARCHIVE_HISTORICAL_CLEANUP.md](POST_V2_C1_V1_ARCHIVE_HISTORICAL_CLEANUP.md)
- [POST_V2_C2_STRUCTURAL_CONSOLIDATION.md](POST_V2_C2_STRUCTURAL_CONSOLIDATION.md)
- [POST_V2_C3A_PONYTAIL_HYGIENE_AUDIT.md](POST_V2_C3A_PONYTAIL_HYGIENE_AUDIT.md)
- [POST_V2_C3B_REPOSITORY_HYGIENE_IMPLEMENTATION.md](POST_V2_C3B_REPOSITORY_HYGIENE_IMPLEMENTATION.md)
- [POST_V2_C4_REFERENCE_COMMAND_DOCUMENTATION_NORMALIZATION.md](POST_V2_C4_REFERENCE_COMMAND_DOCUMENTATION_NORMALIZATION.md)
- [POST_V2_C5_FULL_EQUIVALENCE_RUNTIME_VALIDATION.md](POST_V2_C5_FULL_EQUIVALENCE_RUNTIME_VALIDATION.md)
- [POST_V2_C6_CLEAN_BASELINE_FREEZE.md](POST_V2_C6_CLEAN_BASELINE_FREEZE.md)

## Release evidence

Machine-readable P11 records: `results/v2_final_validation/`
(serving model identity, performance benchmark, release audits).
