# POST-V2 C2 STRUCTURAL CONSOLIDATION

> Behavior-preserving migration `v2/` → `raceintel/`. No scientific,
> model, feature, simulation, strategy, API-contract, or frontend change.
> `v2-final` untouched. Nothing staged, committed, tagged, or pushed.

## Final verdict

**C2 COMPLETE — READY FOR C3**

## Frozen v2 reference

- HEAD `487f15dee184f32f2adeb94814054eb60c98e505` = `v2-final^{commit}` ✅
- Tag intact; history unrewritten; `git diff --cached` empty throughout.
- Plain `mv`/`rm`-style worktree operations only (no `git mv`/`git rm`).

## Repository safety

Pre-mutation: 127 dirty paths, all classified (C0 report / C1 report /
C1 record / 106 C1 removals intact / PREEXISTING_OTHER_WORK / ignored
generated). Zero UNKNOWN before mutation. C1 deletions verified intact
(106/106) and never restored. C1 archive identity re-verified
(`ea466002…`, 106 files).

## Graphify before

`graphify update .` post-C1: **11363 nodes / 27731 edges / 326 communities**.
Used for importer/import mapping; `git grep` for dynamic, string, Docker,
Makefile, CI, manifest, and fixture references.

## Behavioral contract

Frozen pre-migration: public API paths (legacy `/predict/*`, `/v2/*`,
`/health`, `/ready`); `python -m v2.cli` entry; serving + Phase-2 +
replay + explainability + simulation identities (Part V values); CI
collection pin 3210; frontend routes `/ /replay /simulator /strategy
/models /about`; Docker backend+frontend; Makefile entry points.
C2 changed internal import paths only; all externally observable
semantics preserved (proven by unchanged collection + identities + green
suite).

## Package design

`raceintel/` derives from the actual `v2/` layout (Option B, moderate):

- `raceintel/data/` ← ingestion, jolpica, synthetic, tiera, tierb
- `raceintel/pipeline/` ← d6/d7/d8/d9 (+schemas), d10, d11 (D-stage builders)
- `raceintel/race_state/` ← race_state, race_state_features,
  race_state_reconstruction
- `raceintel/replay/` ← replay, replay_predictions,
  replay_probability_timeline, replay_reconstruction
- `raceintel/explainability/` ← explainability, local_explainability,
  timeline_explainability
- `features/`, `labels/`, `model_lab/`, `simulation/`, `strategy/`,
  `experiments/` moved whole (layout unchanged; `model_lab` name kept —
  stable responsibility + single pickle-rename dimension)
- kernel top level: `__init__`, `cli`, `config`, `contracts`, `errors`,
  `manifests`, `prediction`, `retry`, `runs`, `storage`, `validation`
- 5 new docstring-only `__init__.py` (new subpackages). Basenames
  preserved everywhere (no second rename dimension).

## v2 occurrence classification

- IMPLEMENTATION_NAMESPACE (migrated): `v2.*` imports, `v2/` fs paths,
  `python -m v2.*`, root-discovery `v2/` checks, Dockerfile `COPY v2/`
  (kept only for shim), `ADAPTER_SOURCE` provenance string.
- PUBLIC_CONTRACT (kept): `/v2/` API routes, `frontend/lib/v2.ts`,
  `api/v2_*` module names.
- ARTIFACT_IDENTITY (kept): `data/v2/*`, `results/v2_*`, pickle path
  `v2.model_lab.preprocessing` (via shim), manifest fields, version
  labels (`"v2"` versions, `matrix_version`).
- HISTORICAL_REFERENCE (kept): frozen phase docs/commands, P11/format
  strings, drift JSON `v2-monte-carlo-phase6` tag.
- TEST_PROVENANCE (updated where path-asserting): firewall/probe/glob
  strings now assert `raceintel.*` with identical power (verified green).
- STALE_NAME (fixed): code docstrings/prog strings pointing at moved
  modules; `data/README.md` commands/tree refs.

## Package migration

121 files `v2/` → `raceintel/` via plain `mv` (content-preserving);
`v2/` worktree removed (only ignored detritus remained). 5 new inits +
3-file pickle shim added. Import rewrite: exact mapping script
(`v2.` prefix + relocation table + `from v2 import` fixer), 222 files,
0 residual refs; verified by re-grep sweeps (imports, dynamic
`__import__`/`import_module`, subprocess `python -m`, AST/glob paths,
firewall strings, prog strings, `ADAPTER_SOURCE`).

## Subsystem mapping

Full old→new table with new SHA-256 per file in
`results/post_v2_consolidation/c2_structural_migration_record.json`
(121 moved). New subpackage per responsibility; no fragmentation beyond
existing boundaries (one new container: `pipeline/`, `data/`,
`race_state/`, `replay/`, `explainability/` for previously loose
top-level modules).

## Import migration

Surfaces: `raceintel/` internals, `api/` (15 files), `scripts/` survivors,
`tests/` (~90 files), Dockerfile, `prepare_runtime_artifacts.py` anchor +
protected list, `raceintel/config.py` discovery, test fake-roots, freeze/
drift/governance assertions, `data/README.md`. Watch items cleared:
no `importlib` misses (found + fixed `run_models`/`run`/`d11` subprocess
+ `__import__`), no patch-target misses (none exist), pickle path via
shim (identity `FP1 is FP2` verified).

## Compatibility decisions

- Pickle audit: ONLY `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`
  embeds a repo path (`v2.model_lab.preprocessing.FittedPreprocessor`,
  1 occurrence); all 30 legacy `results/models/*.pkl` are sklearn-only.
- Shim (minimal, documented, transitional): `v2/__init__.py` +
  `v2/model_lab/__init__.py` + `v2/model_lab/preprocessing.py`
  (re-export only). No duplicate implementation tree (worktree `v2/` =
  3 stubs). `joblib.load` verified working through the real serving path.
- Removal condition recorded: only when no frozen artifact embeds `v2.*`.

## API structure

No structural change (import repair only). Legacy stack untouched.
Direction verified: `api/` → `raceintel/`; zero FastAPI/Starlette imports
in `raceintel/` or `ml/`; `raceintel/` imports nothing from
`api`/`ml`/`scripts`. Public endpoints byte-identical (`/v2/` namespace
preserved deliberately).

## ml policy

`ml/` fully retained (V2_REQUIRED legacy serving contract). Zero changes.
Role documented: frozen legacy serving compatibility; future v3
architectures supersede explicitly, not here.

## Script decision

Survivors enumerated (14): `prepare_runtime_artifacts`,
`check_runtime_environment`, `check_science_environment`,
`replay_feature_matrix`, `run_ci_tests` (+manifest), `run_ci_frontend_tests`,
`benchmark_phase4/phase5_replay` (hash-pinned), `build_phase9_evidence`,
`build_replay_prediction_cache`, `build_simulation_parameters`,
`capture_phase7_s1_baseline`, `run_p11_performance_benchmark`,
`validate_phase6_simulation` — all PERMANENT_* / HISTORICAL_BUT_REFERENCED.
**DEFERRED movement to C4**: reorganization would churn CI/Makefile/
manifest/provenance refs for cosmetic gain. Only import/path repairs done.

## Test-layout decision

**KEEP_TEST_LAYOUT** (explicit): all 103 paths unchanged, node IDs
unchanged, collection pin 3210 intact. Only import/path/firewall content
repaired. Moving tests would risk selector manifests + phase provenance
for zero behavioral gain.

## Docker/runtime changes

`Dockerfile.backend`: `COPY raceintel/`, `COPY v2/` kept (shim),
comments updated. No architecture change (backend+frontend only; no
infra). Content verified by container-contract tests (120-test batch
green). Image build deferred to C5 (contract tests cover COPY surface).

## CI contract

Unchanged: `EXPECTED_COLLECTED=3210`, no manifest edits, no pin changes.
Collection verified 3210 pre- and post-migration (content edits only).

## Focused validation

Incremental rounds, all green: kernel/api/contracts (89) →
features/labels/tier (190) → governance P4/P6/S6 (111) → replay P5
(102+28+168) → simulation R (414+71+...) → strategy S (176+103) →
explainability E (131) → model-lab M (187+278+52) → legacy R2 (62) →
runtime/container (120) → misc (333+17+17+196). Failures found during
migration (missed dynamic/probe/hash refs) were fixed and re-run green —
9 governance/probe/file-path misses total, zero scientific.

## Final validation

- `make preflight-source`: pass (pre + post).
- `make ci`: ci-python `collected=3210 selected=2489 deselected=721`,
  **2480 passed, 4 xfailed, 0 failed**; ci-frontend exit 0 (npm ci +
  node tests + tsc + lint + build + lockfile diff).
- Tier-3 (`make science`) NOT run: source-safe CI (all contracts that can
  run source-safe) + identities + line-level purity audit establish
  equivalence; C5 owns Tier-3. No scientific contract was touched.

## Frozen artifact loadability

Serving joblib loads via shim through `raceintel.model_lab.serving`
(`describe_serving_artifact` hash exact; API ensemble path exercised by
`test_api_baseline`). Replay/explainability/simulation artifacts load
(exercised by green R/E/S suites). No regeneration, no reserialization.

## Scientific identities

All exact: serving `1116b34f…`; phase-2 content `d2ee966c…`; parquet
`b0f17b66…`; explainability `bae84b61…`; replay `78a3c059…`; simulation
`r3-v1__through-2024`. Manifest records intact.

## Scientific firewall

Line-level purity audit over 121 moves + 222 in-place edits: every
changed line is import/path/docstring/prog-string mechanics; zero
additive/deleted logic blocks; zero non-mechanical edits outside the
documented governance-test evolved sets, shim, inits, record, reports,
`data/README`, Dockerfile. Forbidden list (features, labels, temporal,
model, preprocessing, probabilities, RaceState, replay, simulation RNG,
strategy, uncertainty, explainability math, 2025 firewall) untouched —
proven by green scientific suites + identities.

## Graphify after

`graphify update .`: **11390 nodes / 27740 edges / 322 communities**.
No `raceintel`→FastAPI edges; no orphaned `v2/` implementation modules
(worktree `v2/` = shim only); no parallel implementation trees.

## Git diff audit

Categories: C0 (report) / C1 (report+record+106 removals intact) /
C2_MOVE (121 deletions under `v2/` + 121 untracked under `raceintel/`) /
C2_IMPORT_REPAIR (~200 tracked M) / C2_RUNTIME_REPAIR (Dockerfile,
prepare anchor/protected, config discovery, data/README) /
C2_REPORT + C2_RECORD (new) / PREEXISTING_OTHER_WORK (untouched) /
EXPECTED_LOCAL_GENERATED (ignored). Verify: C1 removals remain removed;
PREEXISTING_OTHER_WORK untouched; nothing staged. Zero UNKNOWN.

## Deferred work

Script/test reorganization (C4), broad docs normalization (C4), Docker
image build (C5), Tier-3 science (C5), `v2/` shim removal (post-pickle
future), directory rename to `f1-race-intelligence` (C6, local-only).

## C3 handoff

C2 leaves: `raceintel/` domain package + 3-file `v2/` pickle shim,
import-repaired `api/`/`scripts/`/`tests/`, updated Dockerfile + root
discovery, C2 migration record with per-file hashes. C3 (dead code/deps/
hygiene) may now proceed: `.gitignore` gaps, graft-era tooling verdict,
coverage-backed dead-code removal, `pipdeptree` dep review. C3 must NOT
break the 8 C1-retained script importers, freeze-test evolved sets, or
the pickle shim. Full `make ci` ≈45 min budget note for C5.

## Entry gate

- [x] HEAD still equals v2-final
- [x] v2-final unchanged
- [x] nothing staged
- [x] all preexisting dirt classified
- [x] zero UNKNOWN before mutation
- [x] C0/C1 reports read
- [x] C1 archive record read
- [x] Graphify-first navigation used
- [x] current v2 modules responsibility-mapped
- [x] target raceintel structure explicitly designed
- [x] version-name occurrences classified
- [x] implementation namespace migrated
- [x] no blind global v2 string replacement (token tables + sweeps)
- [x] active imports repaired (222 files, 0 residual)
- [x] serialized artifact module-path risk audited (1 path, shim)
- [x] compatibility shims only where justified (pickle only)
- [x] no duplicate full implementation tree (3 stubs)
- [x] API dependency direction preserved (one-way, verified)
- [x] domain package does not depend on FastAPI
- [x] ml/ retained
- [x] surviving scripts individually classified
- [x] C1-retained script references preserved
- [x] script movement explicitly justified or deferred (deferred, C4)
- [x] test-layout move/keep decision explicit (KEEP, evidenced)
- [x] scientific regression contracts preserved (evolved sets, P11-1 pattern)
- [x] frontend routes unchanged
- [x] API public paths unchanged
- [x] /v2 API namespace preserved
- [x] Docker/runtime paths repaired where necessary
- [x] no infrastructure added
- [x] CI selector contract preserved (3210, no pin changes)
- [x] focused tests run incrementally (all rounds green)
- [x] make preflight-source green
- [x] make ci green (2480/0 + frontend exit 0)
- [x] Tier-3 decision documented (deferred to C5, justified)
- [x] serving artifact loads (shim + service path)
- [x] replay artifacts load (R suites)
- [x] explainability artifact loads (E suites)
- [x] simulation parameters load (S suites + manifest)
- [x] all frozen scientific identities exact (6/6)
- [x] no artifact regeneration
- [x] scientific firewall clean (line-level audit)
- [x] Graphify refreshed after migration
- [x] dependency direction checked
- [x] cycles checked (no new; suite green)
- [x] orphaned old implementation checked (shim only)
- [x] C1 removals remain removed (106/106)
- [x] PREEXISTING_OTHER_WORK untouched
- [x] C2 record created (121 moves + hashes)
- [x] C2 report created (this file)
- [x] all final dirty paths classified
- [x] zero UNKNOWN
- [x] nothing staged / committed / tagged / pushed
- [x] C3 handoff explicit
