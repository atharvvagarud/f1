# PHASE 10 P10-1A RUNTIME ARTIFACT PACKAGING CONTRACT

P10-1A packages frozen Phase 1-9 outputs. No science was recreated:
no retraining, refitting, recalibration, feature/label changes, RaceState,
replay, Monte Carlo, strategy, or 2025-evaluation changes. No Dockerfiles,
compose files, CI workflows, readiness endpoints, or observability
middleware were created (those are P10-1B and later, NOT started).

## Final verdict

P10-1A COMPLETE — READY FOR P10-1B. The exact runtime-generated artifact
set is identified, the deterministic packager
(`scripts/prepare_runtime_artifacts.py`) plus manifest schema exists,
12 focused tests pass, the current workspace stages to a validated
`runtime_artifacts/` bundle (1939 files, 157,647,360 bytes), canonical
sources are byte-identical before/after, and the P10-1C handoff is explicit.

## Frozen baseline

- HEAD: `440f2a370aff56c799e69b65781199b158064fa0`
  (`440f2a3 feat(v2): freeze models and about phase 9`)
- Tag on HEAD: `v2-models-about-phase9` — matches.
- Phase 1-9: FROZEN. Independent-binary winner probabilities preserved
  (packager asserts `INDEPENDENT_BINARY` in two independent artifacts).

## Repository safety

Baseline recorded before work: HEAD/tag as above,
`git diff --cached --stat` empty (nothing staged). Pre-existing unrelated
work preserved untouched: deleted-unstaged tooling (`.claude/`, `.cursor/`,
`.gemini/`, `.ignore`, `.mcp.json`), modified `AGENTS.md`/`GEMINI.md`/
`opencode.json`, untracked `.impeccable/`, `.opencode/`, root
`package.json`/`package-lock.json`, root `.env`, `frontend/.env.local`.
Owned changes only: `scripts/prepare_runtime_artifacts.py` (new),
`tests/test_runtime_artifact_packaging.py` (new), this document (new),
`.gitignore` (+6-line staging entry). Nothing staged, committed, tagged,
reset, restored, or cleaned. `runtime_artifacts/` is gitignored and
untracked.

## Graphify / navigation

`graphify update .` failed once: `command not found: graphify`
(no CLI on this machine). Not retried. Fallback used throughout:
targeted `Read`/`Grep` for consumers (`api/v2_*_service.py`,
`v2/config.py`, `v2/features/build_matrix.py`,
`v2/simulation/params.py`, `v2/model_lab/serving.py`,
`v2/replay_predictions.py`, `v2/explainability.py`) plus
`git ls-files` / `git check-ignore` / `du` / `shasum` for artifact state.
No broad tree dumps relied on for conclusions.

## Runtime artifact set

| ID | Class | Path(s) | Consumer(s) | Tracked? | Req? | Size |
|---|---|---|---|---|---|---|
| A | Canonical V2 serving corpus | `data/v2/processed/**` (full tree) | `load_v2_service` (states/results/races 2018-2024), `load_history` (hist_*, results, races, pit_stops, season=* globs), reconstructor, prediction engine, replay/explain/sim/strategy stacks | ignored/generated | required | 98.5 MB, 1786 files |
| B | Simulation parameter bundle | `data/v2/simulation/params/r3-v1__through-2024/manifest.json` (single file) | `api/v2_simulation_service.py`, `api/v2_strategy_service.py` via `parameter_storage_dir(root, 2024)` + `load_simulation_parameters` | ignored/generated | required | 292 KB, 1 file |
| C | Replay prediction cache | `results/v2_replay/checkpoints/*.json` (149) + `phase8_e2_cache_manifest_v1.json` | `api/v2_replay_service.py` (read-only; per-file `cache_key` check vs live scientific inputs), replay-prediction / probability-timeline / local+timeline explanation endpoints | ignored/generated | required | 58.7 MB, 150 files |
| D | Global explainability artifact | `results/v2_explainability/global_winner_logreg_v1.json` + `.sha256` sidecar | `api/v2_explanation_service.py` via `v2.explainability` (OUTPUT_REL) | ignored/generated | required | 147 KB, 2 files |
| E | Frozen serving model | `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib` | winner-snapshot, replay identity, explanations, sim adaptation via `v2/model_lab/serving.py` | TRACKED — referenced by SHA, never copied into bundle | required | 17,401 B |
| F | V1 runtime resources | `data/processed/**`, `data/interim/**` (~2.5 MB), `results/models/**` (13 MB) | V1 legacy routes via `ml/inference.py` | TRACKED — normal image inputs, NOT in bundle | required (V1 preserved) | ~15.5 MB |

Clean-clone availability: A-D absent (all ignored); E-F present (tracked).

## Canonical V2 runtime subset

RUNTIME_REQUIRED: the whole `data/v2/processed/` tree (all entities, all
seasons on disk). NOT pruned, deliberately:

- `api/v2_service.py:_read_entity` filters `season={2018..2024}` for
  `driver_lap_state_d9`/`results`/`races`, BUT
- `v2/features/build_matrix.py:load_history` reads `hist_results`,
  `hist_races`, `results`, `races`, `pit_stops` with `season=*` globs
  (unfiltered — includes any season present), and
- the frozen matrix manifest asserts `feature_rows == 189420` and
  `content_hash == d2ee966c…` over the corpus as built.

Pruning 2025 (or any) season dirs would require proving no consumer reads
them — the `season=*` globs prove the opposite risk. Per policy, the
slightly larger proven-safe subset wins: 98.5 MB staged vs 109 MB total
`data/v2`.

RESEARCH_ONLY (excluded): `data/v2/model_lab/`, `data/v2/reports/`,
`data/v2/strategy/` (s3-s6 validation JSONs), `data/v2/simulation/validation/`,
`data/v2/raw/` (manifests only), root `d11_r8*.json`,
`results/{analysis,baselines,comparisons,debug,data_quality,v2_validation}`,
`results/v2_replay/replay_build_manifest_v1.json` (build log with absolute
host paths, no serving consumer — regener
...[truncated 9113 chars]