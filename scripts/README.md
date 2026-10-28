# scripts/

## Role today

`scripts/` contains historical research/stage entry points and frozen
provenance-sensitive scripts. It grew organically: builders, analyzers,
runners, freezers, validators, and CI gates live here side by side
(139 Python scripts plus this README and
`ci_corpus_dependent.txt`; no subdirectories).

Two facts matter:

1. Some historical scripts contain real domain logic (research models,
   ledgers, regime analyses). That is how past stages were built.
2. Frozen `v3_*` scripts are provenance artifacts. Guard allowlists and
   lineage references key on their exact paths.

These must NOT be retroactively moved during active V3 development.
Reorganizing frozen stages would break provenance links for cosmetic
benefit. Index over them (`docs/INDEX.md`); do not relocate them.

V3 Final note: active V3 development has ended with the V3 Final freeze
(`v3-final`). The forward rule above now governs any future work.

## Navigation (post-V3)

`scripts/` is flat on purpose: frozen paths are referenced by guards,
manifests, and lineage records, so the directory is navigated by index,
not by folder structure. The scripts fall into five groups.

### 1. Runtime packaging and preflight (current infrastructure)

- `prepare_runtime_artifacts.py` — P10-1A packager (not a science
  builder). Stages validated bytes into `runtime_artifacts/` with a
  deterministic manifest. Stdlib only, fails closed.
- `check_runtime_environment.py` — P10-1B preflight. `--source` checks
  tracked declarations (fresh-clone state); `--deployable` additionally
  requires a valid staging bundle and network-off posture. Stdlib only.
- `check_science_environment.py` — P11-1 Tier-3 preflight. Fails early
  when the canonical local scientific corpus is absent. Stdlib only.
- `ci_corpus_dependent.txt` — sibling manifest (not a script) listing
  the pytest node IDs excluded from Tier-1 normal CI. Read by
  `run_ci_tests.py`; node IDs pin exact test paths.

### 2. CI selectors (current infrastructure)

- `run_ci_tests.py` — Tier-1 Python gate: collects the source-safe
  suite from a fresh checkout and shells out to pytest. Contains no
  science.
- `run_ci_frontend_tests.py` — Tier-1 frontend gate: runs tracked
  `frontend/**/*.test.ts` except corpus-dependent files.

### 3. Serving-path module (production surface)

- `replay_feature_matrix.py` — E1.6 identity-lookup backend resolving
  replay checkpoints to exact frozen matrix rows. Imported by serving
  code and baked into `Dockerfile.backend`. One-way offline
  dependency: it may import frozen domain code; frozen code must never
  import it. Treat as production, not research.

### 4. Canonical corpus builders and measurement tools

Offline, deterministic developer entry points. Never on the request
path; never run them to "refresh" frozen results.

Builders:

- `build_replay_prediction_cache.py` — replay checkpoint backfill.
- `build_simulation_parameters.py` — Phase-6 R3 parameter artifact.
- `build_spatial_geometry.py` / `build_spatial_observations.py` —
  P12-3 / P12-2 spatial corpus entry points.
- `build_v3_race_dynamics.py` — V3.1 dynamics sidecar.
- `build_phase9_evidence.py` — read-only derivation of the tracked
  `/models` and `/about` evidence consumed by contract tests.

Measurement and probes (explicitly not CI):

- `run_p11_performance_benchmark.py` — P11-3 release measurement.
- `mc2_batch_benchmark.py` — MC2 batch-executor parity proof.
- `benchmark_phase4.py` / `benchmark_phase5_replay.py` —
  historical reproducible harnesses (descriptive timings only).
- `probe_spatial_api.py` / `probe_spatial_resolver.py` — real-corpus
  spatial validation and resolver inspection.

### 5. Frozen research and reproduction scripts (the bulk)

Everything not named in groups 1–4: `v3_*`-coded experiment scripts
(`run_` / `analyze_` / `build_` / `freeze_` / `audit_` / `validate_` /
`verify_` / `project_` / `recount_` / `recompute_` / `finalize_` /
`fetch_` prefixes plus bare `v3_*` names), phase-coded drivers such as
`validate_phase6_simulation.py` and `capture_phase7_s1_baseline.py`,
and program-record generators such as `v3_final_freeze.py` (which
emitted `results/v3/final/`).

- Their stage-numbered names encode scientific lineage: experiment
  codes, preregistration steps, and freeze sequence.
- Exact paths may be referenced by guard allowlists, manifests, docs
  lineage, and release records.
- They are not candidates for cosmetic renaming or relocation.
- They must not receive new reusable domain logic. Some contain real
  domain logic because that is how past stages were built; that is
  history, not a pattern to extend.

### Where new work goes

- New reusable domain/scientific logic → `raceintel/`
  (forward rule below).
- New scripts → thin orchestration, CLI parsing, and
  artifact/report generation only, with domain-first names.
- When in doubt whether a script is operational or frozen:
  operational scripts are the 18 scripts named in groups 1–4;
  everything else is frozen reproduction.

## FORWARD RULE (new work only)

For NEW work from this point onward:

- Reusable domain/scientific logic should live in `raceintel/` under an
  appropriate domain-owned module/package.
- `scripts/` should primarily contain thin executable entry points,
  orchestration, CLI parsing, and artifact/report generation.
- `scripts/` should not become a second authoritative source tree.
  Deletion test: deleting `scripts/` must delete wiring — never the only
  copy of a model.
- Exceptions must be justified explicitly (in the stage doc and the
  script header).

This rule applies only to NEW work. Do NOT move or rewrite existing
frozen `v3_*` scripts to comply with it.

## Naming guideline for new work

Prefer domain-first names:

Good:

- `vsc_duration_analysis.py`
- `tyre_persistence.py`
- `track_regime_validation.py`

Avoid using stage numbers as the main semantic name where possible.
Stage identity may remain in artifact metadata, result directories,
scientific cards, and docs lineage.

Do NOT rename existing files.
