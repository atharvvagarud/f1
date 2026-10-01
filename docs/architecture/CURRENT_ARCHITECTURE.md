# Current Architecture (post-consolidation)

Factual map of the repository after the C1–C3 consolidation. Historical
phase reports describe the same system under its pre-C2 `v2/`
implementation namespace; this document describes it as it is.

## Layers

```text
frozen F1 data (FastF1 / Jolpica, network-gated)
        │
raceintel/data + raceintel/pipeline        data platform (D3–D11)
        │
raceintel/features + raceintel/labels      temporal engine + targets
        │
raceintel/model_lab                        frozen winner model
        │
raceintel/race_state + raceintel/replay    factual states + replay
raceintel/simulation + raceintel/strategy  futures + comparisons
raceintel/explainability                   log-odds evidence
        │
api/  ──────────────────────────────  FastAPI service boundary
        │
frontend/  ─────────────────────────  Next.js product
```

Deployment: two containers (backend :8000, frontend :3000) over a
validated artifact bundle staged by `scripts/prepare_runtime_artifacts.py`.
No database, queue, or orchestrator.

## Package responsibilities

All under `raceintel/` (C2 rename of `v2/`; basenames preserved):

| Package | Responsibility |
|---|---|
| `raceintel/data/` | ingestion, Jolpica, Tier-A/Tier-B, synthetic builders |
| `raceintel/pipeline/` | D-stage builders D6–D11 (+schemas) |
| `raceintel/features/` | temporal feature engine, registry, matrix build |
| `raceintel/labels/` | target construction (side channel) |
| `raceintel/race_state/` | RaceState + reconstruction |
| `raceintel/replay/` | replay, cached predictions, probability timelines |
| `raceintel/simulation/` | empirical estimator, Monte Carlo engine, RNG, params |
| `raceintel/strategy/` | candidates, paired comparison, objectives, uncertainty |
| `raceintel/explainability/` | global/local/timeline explanations |
| `raceintel/model_lab/` | frozen model development (runners, suites, serving) |
| `raceintel/experiments/` | feature-set experiments |
| kernel (`config`, `contracts`, `errors`, `manifests`, `runs`, `storage`, `validation`, `retry`, `prediction`, `cli`) | shared contracts, paths, entry point (`python -m raceintel.cli`) |

## API boundary

`api/` is the HTTP/service boundary and the only layer that imports
FastAPI. Mounts: `/health`, `/ready`, legacy prediction routes
(`/predict/*`, frozen), and the versioned public contract `/v2/...`
(core, replay, simulation, strategy, explanation, timeline-explanation).
Dependency direction is one-way: `api/` → `raceintel/`; `raceintel/`
imports nothing from `api/`, `ml/`, or `scripts/`.

`/v2/` (API contract version) and `raceintel/` (implementation package)
are intentionally different concepts; the namespace is preserved
byte-identically and must not be renamed.

## Legacy compatibility

- `ml/` — frozen legacy serving compatibility behind the legacy
  prediction routes. Required by the production Docker image and the R2
  regression suite. Do not retrain, migrate, or merge into `raceintel/`.
- `v2/` — minimal serialized-artifact compatibility shim (3 files,
  re-export only). Exists because the frozen serving artifact
  `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib` embeds the
  class path `v2.model_lab.preprocessing.FittedPreprocessor`. Remove
  only when no frozen artifact embeds a `v2.*` path. Not implementation.
- `data/processed/`, `data/interim/`, `results/models/` — tracked legacy
  inputs to the serving path and regression suite (legacy format, live
  requirement).

## Artifact / runtime boundary

Tracked release evidence: `results/v2_final_validation/`,
`results/v2_validation/`, `results/v2_model_lab/*.joblib`, freeze
manifests, `tests/fixtures/`. Generated locally, never committed:
`runtime_artifacts/` (Docker staging), `results/v2_replay/`,
`results/v2_explainability/`, `data/v2/simulation/params/`
(asserted by Docker layer 7 + `prepare_runtime_artifacts.py --validate`).

## Scientific-data boundary

Canonical corpus is local-only and ignored: `data/v2/` (processed
parquet, manifests, reports), `data/raw/fastf1_cache/`,
`.fastf1_cache/`. Rebuilt via `raceintel` CLI + builders (see
`data/README.md`); never hand-edited, never committed. Tracked legacy
CSVs stay for the serving path (above).

## Test / validation tiers

- Tier 1 — source-safe CI: `make ci` (`ci-python`: 3,210 collected,
  corpus-dependent deselected; `ci-frontend`: node tests + tsc + lint +
  build). Clean-checkout capable.
- Tier 2 — deployable/runtime: `make preflight` (+`preflight-source`),
  Docker/Compose builds, readiness gate, endpoint/workflow smoke.
- Tier 3 — full scientific regression: `make science` (canonical corpus
  required; complete pytest suite, no Tier-1 deselection).

Tier-1 green never implies Tier-3; the split is architectural (corpus
cannot ship in git). Tests live in `tests/` (layout frozen, phase-named
regression contracts kept).
