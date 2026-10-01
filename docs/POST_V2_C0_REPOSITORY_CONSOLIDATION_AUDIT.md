# POST-V2 C0 REPOSITORY CONSOLIDATION AUDIT

> Status: READ-ONLY audit. No file was moved, renamed, deleted, archived,
> committed, or edited to produce this report, except this file itself.
> Frozen reference `v2-final` was not touched. No ZIP was created.

## Final verdict

**C0 COMPLETE — READY FOR C1**, with two load-bearing findings that C1 must
respect (neither blocks C1; both constrain it):

1. The "legacy V1 serving stack" (`ml/` + legacy `api/` routes +
   `data/processed` + `data/interim` + `results/models` + R2 golden tests)
   is **V2_REQUIRED**, not archivable. It ships inside the production Docker
   image and pins the R2 regression suite. C1 must NOT archive it.
2. The working tree contains a live secret (`.env`, ignored, untracked):
   a Gemini API key. It must never be staged or committed. Rotation is
   recommended since the value has existed in a working tree.

## Frozen v2 reference

- `git rev-parse HEAD` → `487f15dee184f32f2adeb94814054eb60c98e505` ✅
- `git tag --points-at HEAD` → `v2-final` ✅
- `v2-final` is an **annotated** tag (tag object
  `6883e743b17efe9652725a3c88e98ba68b4e96ab`); dereferenced commit
  (`v2-final^{commit}`) = `487f15d…` = HEAD ✅ (the earlier apparent
  mismatch was tag-object vs commit hash, now resolved).
- Productionization baseline tag `v2-productionization-phase10`
  (`aa32ecf8…`) still present ✅.
- Recent history: `487f15d feat(v2): freeze F1 Race Intelligence v2` ←
  `3c069b5 …phase 10` ← `440f2a3 …phase 9` ← `7fa9bf9 …phase 8` ←
  `17c04b3 …counterfactual strategy engine`.
- `git diff --cached --stat` → empty. **Nothing staged.** ✅
- Git history is authoritative and must never be rewritten (see Recovery).

## Repository safety

Worktree dirt vs `v2-final` (18 paths, 0 staged, 0 UNKNOWN):

| Path(s) | Worktree state | Category |
|---|---|---|
| `D .claude/helpers/graft-hooks.cjs`, `D .claude/helpers/graft-statusline.cjs`, `D .claude/settings.json`, `D .claude/skills/graft/SKILL.md` | deleted, unstaged | PREEXISTING_OTHER_WORK (graft-era agent tooling, since replaced) |
| `D .cursor/hooks.json`, `D .cursor/hooks/graft-hooks.cjs`, `D .cursor/mcp.json`, `D .cursor/rules/graft.mdc` | deleted, unstaged | PREEXISTING_OTHER_WORK |
| `D .gemini/settings.json`, `D .mcp.json`, `D .ignore` | deleted, unstaged | PREEXISTING_OTHER_WORK (graft MCP + ripgrep re-admit) |
| `M AGENTS.md`, `M GEMINI.md` | modified, unstaged | PREEXISTING_OTHER_WORK (graft block removed, graphify+headroom policy added; net −64/+38 lines) |
| `M opencode.json` | modified, unstaged | PREEXISTING_OTHER_WORK (shadcn + playwright MCP entries) |
| `?? .impeccable/` (20K), `?? .opencode/` (61M node_modules), `?? package.json`, `?? package-lock.json` (148K) | untracked | PREEXISTING_OTHER_WORK (design skill config + opencode plugin env + root shadcn stub) |

- UNKNOWN: **none**. Every dirty path is classified above.
- `graphify-out/` refresh from Part B is ignored (`git check-ignore`
  confirms) and untracked — not a tracked-state mutation.
- `.env` is ignored and untracked (see Generated/cache hygiene for secret note).

## Graphify snapshot

- Command run per Part B: `graphify update .`
- **Nodes: 12174 · Edges: 29328 · Communities: 377**
  (aggregated community view; 188 non-code files skipped; 144/144 AST files).
- Used as primary navigator: `graphify query` for v2/ml dependency shape;
  `grep`/`ls`/`git ls-files` only for docs, results, data, Git state,
  config, assets, and reference checks Graphify cannot answer (DYNAMIC
  imports, Docker COPY, Makefile/CI refs, fixture consumers).
- `graphify-out/` is ignored, untracked, regenerable. No action needed.

## Top-level inventory

Tracked files total: **823**. Purpose key per Part C.

| Path | Purpose | Tracked | Size (worktree) | Referenced | Required for v2 | Proposed disposition |
|---|---|---|---|---|---|---|
| `api/` (25 files) | ACTIVE_RUNTIME (legacy + v2 routes/services) | yes | 468K | Docker, tests, frontend | YES | UNCHANGED (C2 may split legacy/v2 subpackages) |
| `ml/` (4 py) | ACTIVE_RUNTIME (legacy serving lib) | yes | 44K | Docker, api, 6+ test files | YES | UNCHANGED |
| `v2/` (121 files) | ACTIVE_SCIENCE (domain system) | yes | 5.2M | Docker, api, tests, scripts | YES | UNCHANGED in C1; rename assessed in Source architecture |
| `frontend/` | ACTIVE_FRONTEND (Next.js app) | partial (115; node_modules/.next ignored) | 724M w/ ignored | Docker, compose, CI | YES | UNCHANGED |
| `tests/` (103 test files + fixtures/helpers) | ACTIVE_TESTING | yes (110) | 11M | CI manifests, Makefile | YES | UNCHANGED in C1; reorganize in C2 |
| `scripts/` (71 files) | mixed ACTIVE_BUILD / HISTORICAL | yes | 1.0M | selective (see Script audit) | PARTIAL | C1 archives LEGACY_UNUSED subset |
| `docs/` (127 files) | ACTIVE_DOCUMENTATION + RELEASE_HISTORY + PHASE_HISTORY | yes | 2.2M | Docker (2 manifests), release evidence | YES (subset) | UNCHANGED in C1; hierarchy in C2/C4 |
| `results/` (202 files) | mixed RELEASE_EVIDENCE / legacy outputs | partial (tracked legacy + final-validation; v2_replay/v2_explainability ignored) | 71M worktree | Docker (serving joblib), tests | PARTIAL | C1 archives LEGACY_UNUSED subset |
| `data/` (15 files tracked) | mixed SOURCE_DATA legacy CSVs + ignored canonical corpus | partial (legacy CSVs tracked; raw/v2 ignored) | 15G worktree (ignored cache) | Docker, tests | PARTIAL | UNCHANGED in C1 |
| `runtime_artifacts/` | GENERATED_RUNTIME (P10-1A bundle staging) | no (ignored) | 155M | Docker COPY, prepare script | YES (locally generated) | UNCHANGED; never commit |
| `Makefile`, `compose.yaml`, `Dockerfile.backend`, `Dockerfile.frontend`, `.dockerignore` | ACTIVE_BUILD / ACTIVE_DEPLOYMENT | yes | small | CI, deploys | YES | UNCHANGED |
| `requirements.txt`, `requirements-test.txt`, `.python-version`, `frontend/package.json` + lock | ACTIVE_BUILD | yes | small | Docker, CI, installs | YES | UNCHANGED |
| `README.md`, `PRODUCT.md` | ACTIVE_DOCUMENTATION | yes | 14K/6K | — | YES | normalize in C4 |
| `docs/case-study/` | CASE_STUDY | yes | small | P11 evidence | YES (release evidence) | UNCHANGED |
| `V2_PHASE_1_DATA_PLATFORM.md`, `V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md`, `V2_PHASE_3_MODEL_LAB.md`, `V2_FOUNDATION_REFACTOR.md.md` (root) | PHASE_HISTORY (duplicated into docs/) | yes | 35–56K ea | none found | NO | ARCHIVE (C1) |
| `req.md`, `section5report.txt` | LEGACY_V1 (lap-10 reproducibility + ablation text) | yes | 3K ea | none found | NO | ARCHIVE (C1) |
| `DESIGN.md` | DEVELOPER_TOOLING (impeccable theme tokens) | yes | 12K | frontend redesign (loose) | NO (runtime) | UNCERTAIN → keep in C1, disposition in C3 |
| `AGENTS.md`, `GEMINI.md`, `opencode.json` | DEVELOPER_TOOLING | yes (dirty, see safety) | small | agents | tooling-only | resolve in C3 (see Developer tooling) |
| `.claude/`, `.cursor/`, `.gemini/`, `.mcp.json`, `.ignore` | DEVELOPER_TOOLING (graft-era, worktree-deleted) | yes (at HEAD) | small | none (graft retired) | NO | resolve in C3 |
| `.impeccable/`, `.opencode/`, root `package.json`, `package-lock.json` | DEVELOPER_TOOLING (untracked) | no | 61M (.opencode) | opencode/shadcn tooling | NO (repo runtime) | resolve in C3 |
| `.fastf1_cache/` | GENERATED_CACHE | no (ignored) | 100M | local runs | local-only | UNCHANGED |
| `data/raw/fastf1_cache/` | GENERATED_CACHE (15G local blobs) | no (ignored; history retains old blobs) | 15G | local science | local-only | UNCHANGED; never commit |
| `.venv/`, `.pytest_cache/`, `__pycache__`, `.next`, `frontend/node_modules` | GENERATED_CACHE | no (ignored) | 567M venv, 724M w/ FE | local | local-only | UNCHANGED |
| `graphify-out/` | GENERATED_CACHE | no (ignored) | 202M | local nav | local-only | UNCHANGED |
| `.env` | LOCAL_ONLY (+ live secret, see hygiene) | no (ignored) | tiny | local | local-only | UNCHANGED; never track; rotate key |
| `.github/workflows/ci.yml` | ACTIVE_BUILD (source CI) | yes | small | CI | YES | UNCHANGED |
| `.DS_Store` | OS junk (ignored) | no | 30K | none | NO | leave (ignored) |
| UNKNOWN | — | — | — | — | — | **none found** |

## V1 definition

"Old-looking" ≠ V1. Adopted test (all must hold for LEGACY_UNUSED):

> **V1 material** = content belonging exclusively to the original
> university-era *F1 In-Race Winner Prediction* (lap-checkpoint snapshot
> classifiers, Streamlit-era workflow, lap-5/10/15/20/25 CSVs and plots,
> one-off training/tuning/prediction scripts) **AND** not required for:
> current v2 runtime, science, tests, reproducibility, release evidence,
> or documentation provenance.

Corollaries proven by this audit:

- `ml/`, legacy `api/` routes/services, `data/processed`, `data/interim`,
  `results/models`, R2 golden tests — look V1 but are **V2_REQUIRED**
  (production Docker image + regression suite depend on them).
- No Streamlit remnants, notebooks, or `app.py` dashboards exist in the
  tree (`git ls-files` grep for streamlit/notebook/app.py/dashboard: empty).
- "V1" in this repo therefore means: **superseded workflow scripts, plots,
  tables, root-duplicate phase docs, and lap-checkpoint analysis outputs** —
  not the legacy serving stack, which is live product surface.

## V1 dependency audit

Reference surfaces checked per candidate: Python/TS imports, runtime
loaders, tests, fixtures, Makefile, scripts, Docker, Compose, CI,
docs, manifests, hash contracts, frontend assets, model/data loaders.

### V2_REQUIRED (removing breaks v2 — DO NOT ARCHIVE)

| Candidate | Required by |
|---|---|
| `ml/` (`config.py`, `features.py`, `inference.py`) | `Dockerfile.backend` COPY; `api/services/prediction_service.py`; `tests/conftest.py`, `test_datasets.py`, `test_ensemble.py`, `test_model_loading.py`, `test_prediction_equivalence.py`, `test_known_defects.py`; `scripts/predict/*` |
| `api/routes.py`, `api/schemas.py`, `api/services/prediction_service.py`, `api/main.py` legacy wiring | `api/main.py` mounts legacy router; frontend home page calls `/predict/ensemble`, `/predict/single-model`; R2 tests |
| `data/processed/`, `data/interim/` (tracked lap CSVs) | `Dockerfile.backend` COPY; `ml/config.py` dataset paths; R2 tests |
| `results/models/` (134 tracked model dirs) | `Dockerfile.backend` COPY; `ml` model loading; `test_model_loading.py` |
| `tests/fixtures/legacy_predictions.json` (+ sha256 pin in `test_known_defects.py`) | R2 golden suite |
| `tests/fixtures/phase7_s1_phase6_baseline.json`, `phase8_e1_baseline.json` | phase-compat tests |
| `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib` | `Dockerfile.backend` COPY + serving SHA check in CI |
| `docs/PHASE4_FREEZE_MANIFEST.json`, `docs/generated/phase2_freeze_manifest.json` | `Dockerfile.backend` COPY (identity inputs on serving paths) |
| `scripts/replay_feature_matrix.py` | `Dockerfile.backend` COPY; imported by `api/v2_explanation_service.py` |
| `scripts/prepare_runtime_artifacts.py`, `check_runtime_environment.py`, `check_science_environment.py`, `run_ci_tests.py` (+ `ci_corpus_dependent.txt`), `run_ci_frontend_tests.py` | Makefile, Docker, CI workflow |
| `frontend/{app,components/prediction,features/prediction,lib/*prediction*}` | live home-page prediction flow (legacy API) |
| `frontend/data/*.v1.json`, `frontend/features/{about,models,replay,simulator,strategy}` | models/about/replay/simulator/strategy pages + frontend tests |

### HISTORICAL_EVIDENCE (keep in Git, not runtime)

- All `docs/PHASE*`, `docs/MODEL_LAB_*`, `docs/D0_*`, `docs/DATASET_*`,
  `docs/FOUNDATION_*`, `docs/PHASE1_EXIT*`, `docs/PHASE1_FINAL*`,
  `docs/LEGACY_V2_DATASET_COMPARISON.md`, `docs/V2_REPOSITORY_AUDIT.md`,
  `docs/adr/`, freeze manifests/JSON contracts, `results/v2_final_validation/`
  (P11 manifests incl. 4162-line performance benchmark), `results/v2_validation/`,
  `results/data_quality/` (14 files), `results/debug/` conservatively retained
  pending C1 grep (see UNCERTAIN below).
- `results/v2_model_lab/` serving joblib is V2_REQUIRED (above), not merely historical.

### LEGACY_UNUSED (archive candidates — C1 must re-grep before removal)

| Candidate | Size | Why safe (to be re-verified in C1) |
|---|---|---|
| `scripts/analysis/` (5 plot/importance scripts) | small | no Makefile/Docker/CI refs; outputs in `results/analysis` |
| `scripts/baselines/` (4), `scripts/cleaning/` (3), `scripts/data/` (7), `scripts/models/` (10), `scripts/models_weather/` (4), `scripts/predict/` (3), `scripts/results/` (3), `scripts/utils/` (4: append/compare/smoke/fields) | small | no Makefile/Docker/CI refs; superseded by `v2/` pipeline |
| Top-level one-off scripts: `benchmark_phase4.py`, `benchmark_phase5_replay.py`, `benchmark_phase6_monte_carlo.py`, `benchmark_phase6_product.py`, `benchmark_phase7_s3_paired.py`, `build_simulation_parameters.py`, `capture_phase7_s1_baseline.py`, `run_phase7_s3_crn_validation.py`, `run_phase7_s4_validation.py`, `run_phase7_s5_validation.py`, `run_phase7_s6_red_team.py`, `run_phase7_s6_validation.py`, `validate_phase6_simulation.py`, `validate_replay_prediction_cache.py`, `run_p11_performance_benchmark.py` (evidence kept as JSON; script re-runnable from history), `build_phase9_evidence.py` (only ref: frontend CI test helper — confirm replacement first) | small | zero refs in Makefile/Docker/Compose/CI manifests (verified per-script above) |
| `results/analysis/` (16), `results/baselines/` (13), `results/comparisons/` (8) | ~1.4M | generated lap-checkpoint outputs; no test/Docker refs found |
| Root `V2_PHASE_1/2/3*.md`, `V2_FOUNDATION_REFACTOR.md.md`, `req.md`, `section5report.txt` | ~180K | superseded/duplicated by `docs/`; no refs found |
| `scripts/dev/` (`run_mac.sh`, `run_windows.ps1`, `setup_*.ps1/sh`, `clean_windows.ps1`) | tiny | superseded by Makefile/Docker/Compose |
| Historical `data/raw/fastf1_cache` blobs in **git history** (~47–51M blobs, e.g. `2022-10-23 … position_data.ff1pkl`) | history-only | R7 already removed from index; history retained (see Recovery — do NOT purge) |

### UNCERTAIN (retain; never auto-remove)

- `results/debug/` (7 files) — purpose unclear; C1 greps test/script refs first.
- `DESIGN.md` (tracked theme tokens) — keep through C1; C3 decides track vs ignore.
- `data/sequences/` + `data/models/` (empty dirs) — keep (placeholder?); confirm intentional.
- `scripts/build_replay_prediction_cache.py`, `scripts/build_simulation_parameters.py`
  — regenerable-corpus builders; likely HISTORICAL tooling, but rebuild docs may cite them; C1 confirms.
- `build_phase9_evidence.py` — referenced by `scripts/run_ci_frontend_tests.py`; do not archive until that ref is understood/replaced in C4.

## Proposed V1 archive

Future file (DO NOT CREATE in C0): `f1-race-intelligence-v1-archive.zip`
for external/NAS storage. Proposed contents = LEGACY_UNUSED table above
only (approx: ~43 workflow scripts + 15 one-off/benchmark scripts +
37 result CSVs/PNGs + 6 root docs + dev scripts; total well under 5 MB —
exact byte counts and per-file SHA-256 to be computed in C1 at archive time;
all paths have full Git history at/before `v2-final`, so removal from the
active tree loses no recovery path).

Archive manifest schema (to be written in C1, stored alongside the ZIP,
outside the active repo):

```
archive_schema_version: 1
source_repository: <repo remote / path>
source_reference: v2-final (487f15dee184f32f2adeb94814054eb60c98e505)
archived_paths: [<repo-relative path>, ...]
file_count, byte_count
files: [{path, sha256, bytes}]
classification_rationale: C0 LEGACY_UNUSED + C1 re-grep evidence
archive_sha256: <hex>
verification: extract → file-count match → per-file sha256 match → suite gate
```

Rationale per item: no active references (re-verified in C1), superseded by
the frozen `v2/` pipeline, outputs reproducible or purely illustrative,
history preserved in Git regardless.

## Keep in Git

KEEP_IN_GIT (looks historical, stays):

1. `results/models/` + `data/processed/` + `data/interim/` — production
   Docker inputs + R2 suite inputs (V2_REQUIRED, not history).
2. `ml/` + legacy `api/` serving path — live product surface (home page +
   `/predict/*`).
3. `results/v2_final_validation/`, `results/v2_validation/`,
   `results/v2_model_lab/*.joblib`, freeze manifests, API JSON contracts —
   release/temporal-safety/model-selection evidence.
4. `results/data_quality/` — dataset provenance for Tier-3 science.
5. All `docs/PHASE*`, `MODEL_LAB_*`, case-study, ADR-0001, `V2_REPOSITORY_AUDIT.md`,
   `LEGACY_V2_DATASET_COMPARISON.md` — scientific provenance + migration
   record needed to understand current architecture.
6. `tests/fixtures/*` (incl. legacy golden) + `tests/s6_validation_protocol.py`,
   freeze tests — contracts required by the suite.
7. `docs/generated/phase2_freeze_manifest.json` — Docker identity input.
8. Git history itself (incl. fastf1 blobs) — authoritative recovery; never purged.

## Source architecture

Current layout:

- `api/` — dual-era HTTP layer: legacy prediction routes (`routes.py`,
  `schemas.py`, `services/prediction_service.py` → `ml/`) + six v2 routers
  (`v2_*_routes/schemas/service`: core, replay, simulation, strategy,
  explanation, timeline-explanation). 25 tracked files.
- `ml/` — 4-file legacy serving lib (config, features, inference). Frozen by
  R2 golden tests; Docker-shipped.
- `v2/` — **121 tracked files**: the domain/application system, not a bare
  version namespace: `config/contracts/errors/storage/manifests/runs/retry/
  manifests`, `ingestion/jolpica/tiera/tierb/synthetic`, `features/` (14
  modules: registry, engine, build_matrix, gaps/rates/pace/context/...),
  `labels/`, `model_lab/` (~40 modules), `race_state*.py` ×3, `replay*.py` ×4,
  `simulation/` (12), `strategy/` (7), `prediction.py`,
  `explainability.py`, `local_explainability.py`, `timeline_explainability.py`,
  `validation.py`, `cli.py`, `d6/d7/d8/d9(+schemas)/d10/d11.py`,
  `experiments/feature_sets.py`.
- `frontend/` — Next.js 16/React 19: `app/` (home + replay/simulator/
  strategy/models/about), dual component trees (`components/prediction` +
  `features/prediction` for legacy flow; `features/{replay,simulator,
  strategy,models,about}` for v2), `lib/{api,v2}.ts`.

What `v2/` represents: the **domain/application layer** (data platform →
features → model lab → race-state/replay → simulation → strategy →
explainability), accumulated under a version-number name. Once v3 begins,
top-level `v2/` invites `v3/` sprawl and misreads as "old version".

Options:

- **OPTION A — minimal consolidation.** Keep `api/`, `ml/`, `v2/` names;
  only split `api/` internally (`api/legacy_*` vs `api/v2_*` already
  de-facto) and group `scripts/` + `tests/`. Import churn ~0, test churn ~0,
  Docker/CI untouched. Cheapest, but `v2/` confusion persists into v3.
- **OPTION B — moderate package consolidation (RECOMMENDED).** Keep
  `api/`, `ml/` (frozen), `frontend/`; rename `v2/` → domain name
  (e.g. `raceintel/` or `f1_intelligence/`) with internal subpackages
  (`data/`, `features/`, `models/`, `race_state/`, `replay/`, `simulation/`,
  `strategy/`, `explainability/`, `services/`); keep a thin `v2` compat
  shim only if C5 demands it (prefer none — update imports once). Medium
  import churn (~120 files + tests), one coordinated C2, validated by C5
  equivalence gates. Best clarity-per-risk: v3 features land in domain
  packages, no version sprawl.
- **OPTION C — larger src-layout migration.** B + move to `src/` layout
  (`src/f1_intelligence/...`, `src/api/...`). Highest churn (Docker COPY
  paths, `V2_PROJECT_ROOT` assumptions, `sys.path` inserts in
  `tests/conftest.py` and scripts, CI, docs). Better long-term hygiene,
  but migration risk concentrates in Docker/CI/path coupling with zero
  runtime benefit. **Not recommended now**; revisit only if the repo grows
  a second deployable package.

Recommendation: **OPTION B** in C2, with `ml/` and legacy `api/` routes
explicitly frozen in place (they are hash-pinned by R2 fixtures).

## Scripts

71 tracked files. Responsibility map:

- RUNTIME_PREPARATION: `prepare_runtime_artifacts.py` ✅ · VALIDATION:
  `check_runtime_environment.py`, `check_science_environment.py`,
  `validate_replay_prediction_cache.py`, `validate_phase6_simulation.py`,
  `run_phase7_s*` (6) · BENCHMARK: `benchmark_phase{4,5_replay,6_monte_carlo,
  6_product,7_s3_paired}.py`, `run_p11_performance_benchmark.py` ·
  ARTIFACT_BUILD: `build_replay_prediction_cache.py`,
  `build_simulation_parameters.py`, `build_phase9_evidence.py`,
  `replay_feature_matrix.py` (V2_REQUIRED) · CI: `run_ci_tests.py`,
  `run_ci_frontend_tests.py` (+ `ci_corpus_dependent.txt`) · MAINTENANCE:
  `utils/*` · HISTORICAL (V1 era): `analysis/`, `baselines/`, `cleaning/`,
  `data/`, `models/`, `models_weather/`, `predict/`, `results/` subdirs ·
  ONE_OFF: `capture_phase7_s1_baseline.py`, dev scripts.
- Duplicates: `plot_accuracy_vs_lap.py` vs `make_model_accuracy_vs_lap.py`;
  `evaluate_baselines_cv*.py` ×3 variants; `train_*_multilap.py` families;
  `clean_dataset*.py` ×3 — all inside the archivable HISTORICAL set, so
  resolve by archiving, not by refactoring.
- Makefile references **zero** V1-era scripts (verified) — safe to archive
  the HISTORICAL set once C1 re-greps docs/tests.
- Proposed layout (C2, after C1 archive): `scripts/{data,artifacts,
  validation,benchmarks,ci,maintenance}/` — adjust to evidence; every move
  needs Makefile/CI/docs ref updates in the same stage (C4).

## Tests

103 test files. Subsystem map:

- Scientific contracts: `test_v2_d6/d7/d8/d9(+_realdata)`, `test_v2_features_f*`
  (F2–F15), `test_v2_labels_f13`, `test_v2_tiera/tierb`, `test_datasets.py`.
- Runtime/API: `test_api_baseline.py`, `test_readiness.py`,
  `test_request_observability.py`, `test_serving_config.py`,
  `test_backend_container_contract.py`, `test_frontend_container_contract.py`,
  `test_compose_contract.py`, `test_runtime_artifact_packaging.py`,
  `test_runtime_environment.py`, `test_production_reproducibility_contract.py`.
- Simulation: `test_v2_phase6_r*` (r1–r8), `test_v2_phase6_freeze.py`.
- Strategy: `test_v2_phase7_s*` (s1–s7 + compat/seam/mechanics).
- Replay: `test_v2_phase5_r*` + `test_v2_phase4_*` + `test_v2_paths.py`,
  `test_v2_idempotency.py`, `test_v2_storage.py`, `test_v2_manifests.py`.
- Explainability: `test_v2_phase8_e1/e1_6/e3/e4/e5`.
- Release/evidence: `test_v2_phase4/5/6_freeze.py`,
  `test_science_validation_contract.py`, `test_p11_benchmark_script.py`,
  `test_ci_contract.py`, `test_model_loading.py`,
  `test_prediction_equivalence.py`, `test_ensemble.py`, `test_known_defects.py`.
- Infrastructure: `conftest.py`, `f14_helpers.py`, `model_lab_helpers.py`,
  `s6_validation_protocol.py`, `test_v2_cli.py`, `test_v2_retry.py`,
  `test_v2_contracts.py`, `test_v2_experiments_f16.py`, model-lab m0–m9/p31.
- Naming problem: phase-frozen names (`phase4_r1…`, `phase6_r71`,
  `phase7_s3_paired`) are **regression contracts, not obsolete** — never
  rename for aesthetics; `run_ci_tests.py` pins EXPECTED_COLLECTED=3210 and
  fail-closes on drift.
- Proposed C2 structure: `tests/{unit,integration,scientific,contracts,api,
  simulation,strategy,release}/` + keep phase-frozen basenames; update the
  CI corpus manifest + collection pin in the same move.

## Documentation

127 tracked files. Buckets:

- CURRENT_PRODUCT: `README.md`, `PRODUCT.md`, `docs/case-study/*`
  (TECHNICAL_CASE_STUDY, STORYBOARD, PORTFOLIO_FACT_SHEET, ASSET_MANIFEST,
  diagrams ×11), `docs/FRONTEND_DESIGN_SYSTEM.md`.
- CURRENT_DEVELOPER: `Makefile` (self-doc), `docs/PHASE10_P10_2_*`,
  `P10_3_*`, `P10_4*_ *`, `compose.yaml` header, Dockerfiles, `data/README.md`.
- CURRENT_SCIENTIFIC: `docs/PHASE2_*` (19), `MODEL_LAB_*` (14),
  `DATASET_V2_REPORT.md`, `DATA_PLATFORM_ARCHITECTURE.md`, `docs/adr/`.
- RELEASE_HISTORY: `docs/PHASE10_P10_*`, `docs/PHASE11_P11_*` (8),
  `PRODUCT.md` deltas.
- PHASE_HISTORY: `docs/PHASE1_*`, `PHASE4/5/6/7/8/9_*`, freeze manifests —
  keep as evidence.
- LEGACY_V1: root `V2_PHASE_1/2/3*.md` (dup of early docs), `req.md`,
  `section5report.txt`, `DESIGN.md` (tooling-adjacent).
- STALE: graft-era tooling docs (already removed from worktree AGENTS/GEMINI).
- DUPLICATE (reconcile in C4, not C1): `README.md` vs `PRODUCT.md` vs
  case-study narrative overlap; root phase docs vs `docs/`.
- Proposed hierarchy (C2/C4): `docs/{architecture,development,science,
  case-study,releases,history/{v1,v2-phases}}/`; README stays the single
  entry point linking product → case-study → releases → science.

## Results / artifacts

- TRACKED_RELEASE_EVIDENCE: `results/v2_final_validation/` (6 incl.
  4162-line benchmark JSON), `results/v2_validation/` (3),
  `results/v2_model_lab/*.joblib` (serving model).
- TRACKED_SCIENTIFIC_EVIDENCE: `results/data_quality/` (14),
  `results/debug/` (retain pending C1 grep).
- RUNTIME_REQUIRED_IGNORED: `results/v2_replay/` (56M checkpoints +
  manifests), `results/v2_explainability/` (global artifact + sha),
  `data/v2/simulation/params/…` — generated locally, asserted by Docker
  Layer 7 + `prepare_runtime_artifacts.py --validate`; never commit.
- REPRODUCIBLE_GENERATED: `data/v2/processed` (98M), `data/v2/model_lab`
  (4.4M), `data/v2/strategy` (2.4M) — rebuilt via `v2.cli` + builders.
- HISTORICAL_V1 (archive in C1): `results/analysis`, `results/baselines`,
  `results/comparisons` (~1.4M).
- DISPOSABLE: `results/debug/` if C1 grep proves unreferenced (else keep).
- Large paths recorded: `results/v2_replay` 56M, `results/models` 13M
  (tracked, Docker-required — keep), `runtime_artifacts` 155M (ignored).

## Data

- SOURCE_DATA: FastF1/Jolpica upstream (network-gated, `V2_ALLOW_NETWORK`).
- CANONICAL_TIER_A: `data/v2/processed` (98M ignored; 189,420 driver-lap
  states per README) — rebuild via Phase-1 pipeline; required locally for
  Tier-3 science + artifact rebuilds.
- CANONICAL_TIER_B: `data/v2` historical metadata (ignored) — same handling.
- FEATURE_MATRIX: `data/v2/processed/model_matrix` + `data/v2/model_lab`.
- FIXTURE: `tests/fixtures/*` (tracked, tiny) + `data/processed`,
  `data/interim` (tracked 2.5M legacy CSVs — Docker + R2 inputs).
- CACHE: `.fastf1_cache` (100M), `data/raw/fastf1_cache` (15G) — local-only.
- GENERATED: `runtime_artifacts/data` (merged bundle view).
- LEGACY: lap-checkpoint CSVs are legacy-*format* but V2_REQUIRED (above).
- UNKNOWN: none. Empty `data/sequences/`, `data/models/` retained as-is.
- Stays out of Git: everything ignored today (`data/v2/`, raw cache,
  runtime bundle). No dataset moves in consolidation.

## Generated / cache hygiene

| Path | `.gitignore` cover | Verdict |
|---|---|---|
| `__pycache__/`, `*.pyc` | ✅ | OK |
| `.pytest_cache/`, `.mypy_cache/`, `.coverage`, `htmlcov/` | ✅ | OK |
| `.venv/`, `venv/`, `scripts/venv/` | ✅ | OK (567M local) |
| `frontend/node_modules/`, `frontend/.next/`, `out/`, `build/` | ✅ | OK |
| `.DS_Store`, `Thumbs.db` | ✅ | OK |
| `.fastf1_cache/`, `/data/raw/fastf1_cache/` | ✅ | OK |
| `/data/v2/` | ✅ | OK |
| `results/v2_replay/`, `results/v2_explainability/` | ✅ | OK |
| `/runtime_artifacts/` | ✅ | OK |
| `graphify-out/` | ✅ | OK |
| `.env`, `.env.*` | ✅ | OK coverage — **but `.env` contains a live `GEMINI_API_KEY`
  (redacted here). Never stage. Recommend rotation; consider `.env.example`
  (present, safe) as the only documented template.** |
| `.opencode/` (61M), `.impeccable/`, root `package.json`/`package-lock.json` | ❌ GAP | untracked + unignored: every `git status` is noisy. C3 must decide track-vs-ignore per tool (see Developer tooling). |
| `.claude/`, `.cursor/`, `.gemini/`, `.mcp.json`, `.ignore` | ❌ (tracked at HEAD; worktree-deleted) | C3 must decide: re-track graft successor or remove + ignore. |

No `.gitignore` edits in C0 (forbidden). Gaps recorded for C3.

## Developer tooling

| Item | Provider/purpose | Used? | Disposition (C3, not now) |
|---|---|---|---|
| `.claude/` (graft skill + hooks + settings) | graft repo-graph (retired) | NO (files deleted in worktree) | REMOVE from tracking + ignore, or replace with graphify successor |
| `.cursor/` (hooks, graft MCP, rules) | graft in Cursor (retired) | NO | REMOVE + ignore |
| `.gemini/settings.json`, `.mcp.json` (graft MCP) | graft MCP server | NO | REMOVE + ignore |
| `.ignore` (`!graft/` re-admit) | ripgrep carve-out for graft tree | NO (graft gone) | REMOVE with graft cleanup |
| `AGENTS.md` / `GEMINI.md` (worktree mods) | F1 agent policy + graphify/headroom sections | YES | KEEP_TRACKED (already the post-graft policy; C3 ratifies) |
| `opencode.json` (shadcn + playwright MCP) | opencode assistants | YES (worktree) | KEEP_TRACKED (C3 ratifies; contains no secrets) |
| `.opencode/` (61M: plugins + node_modules) | opencode runtime env | local-only | KEEP_LOCAL_IGNORED (add to `.gitignore` in C3) |
| `.impeccable/` (design tokens) | impeccable design skill | local-only | KEEP_LOCAL_IGNORED unless frontend work needs it tracked |
| root `package.json` (shadcn stub) + `package-lock.json` | shadcn CLI pin | dev-only | UNCERTAIN: track if shadcn stays in workflow, else REMOVE (lockfile without src is noise) |
| `DESIGN.md` | theme tokens (impeccable output) | loosely (frontend redesign) | UNCERTAIN → C3 with frontend owner |
| `.env` | local env + **live Gemini key** | local-only | KEEP_LOCAL_IGNORED; rotate key; never track |

No secrets found in tracked files (key lives only in ignored `.env`).
No tooling mutated in C0.

## Dependencies

`requirements.txt` (45 pins) → use map:

- REQUIRED_RUNTIME: `fastapi`, `uvicorn`, `pandas`, `numpy`, `scikit-learn`
  (saved pipelines pin 1.8.0), `xgboost` (3.2.0), `joblib`, `pyarrow`,
  `python-multipart`, `tabulate` (CLI tables), `requests` (+ `requests-cache`
  FastF1 cache), `fastf1` (Tier-A ingestion; runtime reads processed corpus).
- REQUIRED_SCIENCE: `scipy`, `matplotlib` (legacy plots + reports),
  `python-dateutil`, `pytz`, `tzdata`.
- REQUIRED_TEST: `requirements-test.txt`: `pytest`, `httpx` only. ✅ minimal.
- REQUIRED_BUILD: none in Python (no setup.py/pyproject — intentional;
  stdlib + Makefile + Docker).
- DEVELOPER_TOOLING: root `shadcn` npm stub (untracked); frontend deps below.
- POSSIBLY_UNUSED (C3 to prove, never assume): `signalrcore`, `timple`,
  `RapidFuzz`, `PyJWT`, `cryptography`, `cffi`, `pycparser`, `pillow`,
  `fonttools`, `contourpy`, `cycler`, `kiwisolver`, `pyparsing`,
  `msgpack`, `platformdirs`, `url-normalize`, `websockets`, `cattrs`,
  `attrs`, `certifi`, `charset-normalizer`, `idna`, `urllib3`, `six`,
  `threadpoolctl`, `typing_extensions`, `packaging` — most are transitive
  (fastf1/sklearn/matplotlib trees). **Do not remove without `pipdeptree`
  evidence + Docker rebuild proof.** Conservative default: keep.
- `frontend/package.json`: next 16.1.6, react 19, tailwind 4, motion,
  lucide-react, TS/eslint — all REQUIRED_BUILD/RUNTIME for the app. No
  duplication with root stub (different ecosystems).
- No `requirements*.txt` vs frontend duplication. No new deps proposed.

## Entry points

Legitimate current entry points (canonical set for post-cleanup):

| Surface | Canonical command |
|---|---|
| Backend dev | `make backend-dev` (`uvicorn api.main:app`) |
| Backend prod | `make backend-prod` (single-process uvicorn) |
| Frontend dev/build/start | `make frontend-dev` / `make build` / `make frontend-start` |
| Full verification | `make verify` (py tests + FE tests + tsc + lint + build) |
| Ordinary CI | `make ci` (`ci-python` + `ci-frontend`) |
| Tier-3 science | `make science` (needs canonical corpus) |
| Deploy gates | `make preflight` (bundle) / `preflight-source` (fresh clone) |
| Docker/Compose | `make docker-{backend,frontend,compose}-{build,run,up,down}` |
| V2 data CLI | `python -m v2.cli <plan\|run\|plan-tierb\|status>` (+ `V2_ALLOW_NETWORK=1` for live) |
| Artifact bundle | `python scripts/prepare_runtime_artifacts.py [--validate]` |
| Env checks | `scripts/check_{runtime,science}_environment.py` |
| Benchmarks (evidence) | `scripts/run_p11_performance_benchmark.py`, `benchmark_phase*.py` |

Stale/competing: `scripts/dev/*.ps1/*.sh` (supersede with Makefile);
`scripts/predict/predict_race_winner*.py` ×3 (supersede with API + v2 CLI);
phase-specific `run_phase7_*`/`capture_*` (evidence done — archive, keep
runnable from history). Post-cleanup: one way per surface (table above).

## Naming

- `f1-in-race-prediction` (directory name): HISTORICAL_CORRECT at freeze;
  public identity is now **F1 Race Intelligence**. Directory rename is
  outside Git's tracking — recommend separately (cheap, local-only), C6.
- "winner prediction" in `api/main.py` docstring + 7 `docs/*` reports:
  HISTORICAL_CORRECT (describes the legacy surface accurately). DO_NOT_TOUCH
  in frozen reports; SHOULD_RENAME only in live code comments during C4.
- `v2/` package: CURRENT_BUT_ACCEPTABLE until C2; SHOULD_RENAME to domain
  name per Source architecture (Option B). MUST_RENAME nothing (no trademark
  / collision issues found).
- Old titles in frozen phase reports: HISTORICAL_CORRECT — DO_NOT_TOUCH.
- `PRODUCT.md`/`README.md` already use "F1 Race Intelligence" ✅.

## Dead code

Graphify-first + caller analysis (framework/CLI/test/dynamic-loading aware):

- PROVEN_DEAD: **none claimed**. Every unreferenced script is a CLI/manual
  entry point (no-import ≠ dead), and every unreferenced function needs the
  C3 pass with coverage data. C0 refuses to certify deletions without it.
- LIKELY_DEAD (C3 to prove with coverage + C5 gates): duplicate plot pair
  (`plot_accuracy_vs_lap.py` / `make_model_accuracy_vs_lap.py` — but both
  archive with HISTORICAL set anyway); `scripts/utils/smoke_test_fastf1.py`
  (network-gated manual smoke); `tune_*` families (superseded by frozen
  model-lab artifacts).
- EXTERNALLY_REFERENCED (keep or archive-as-history, never "delete"):
  all benchmark/validation one-offs (evidence generators, docs-cited);
  `replay_feature_matrix.py` (Docker-imported); `build_*` scripts (rebuild
  provenance).
- ACTIVE: everything in V2_REQUIRED + CI/Makefile/Docker/Compose closures.
- UNCERTAIN: `results/debug/*`, `DESIGN.md`, frontend `data/*.v1.json`
  regeneration path (re-check in C3 whether a builder exists).

## Duplication

Harmful-to-v3 only (no abstraction for line-count's sake):

1. **Dual serving stacks** (`ml/`+legacy api vs `v2/`+v2 api; dual frontend
   trees; `FEATURE_COLS` vs `features/registry.py`; `ml/config.py` vs
   `v2/config.py` vs `api/config.py`; `prediction_service.py` vs
   `v2_service.py`). Era-separated, each frozen/pinned — document the
   boundary in C4, do NOT unify (unification breaks R2 pins + Docker).
2. **Duplicate setup docs** (`README.md` vs `PRODUCT.md` vs case-study
   narrative; root phase docs vs `docs/`). Reconcile pointers in C4.
3. **Triplicated lap-variant scripts** (`*_multilap.py`, `*_weather.py`,
   `evaluate_baselines_cv*`). Resolved by C1 archive, no refactor needed.
4. **Benchmark helpers** per phase (`benchmark_phase*.py`, `run_phase7_*`).
   Historical record — archive, don't abstract.
5. Non-harmful (leave): config triple (different responsibilities:
   legacy checkpoints / V2 paths / serving env); per-phase freeze tests
   (regression contracts by design).

## Proposed post-v2 structure

Legend: [UNCHANGED] [MOVE] [RENAME] [ARCHIVE] [DELETE] [NEW].

```
f1-race-intelligence/                      # [RENAME] directory only (C6, local)
├── api/                                   # [UNCHANGED] location; internal split:
│   ├── legacy/                            # [NEW] routes.py, schemas.py, services/prediction_service.py [MOVE]
│   └── v2_*.py                            # [UNCHANGED] six v2 routers/services (re-home under services/ in B)
├── raceintel/                             # [RENAME] from v2/ (Option B, C2)
│   ├── data/                              # ingestion.py, jolpica.py, tiera.py, tierb.py, synthetic.py [MOVE]
│   ├── features/                          # features/* [MOVE]
│   ├── models/                            # model_lab/* [MOVE]
│   ├── race_state/                        # race_state*.py, d6/d7/d9 scaffolds [MOVE]
│   ├── replay/                            # replay*.py [MOVE]
│   ├── simulation/                        # simulation/* [MOVE]
│   ├── strategy/                          # strategy/* [MOVE]
│   ├── explainability/                    # *explainability*.py [MOVE]
│   ├── validation.py, contracts.py, ...   # shared kernel [MOVE]
│   └── cli.py                             # [MOVE] (entry: python -m raceintel.cli)
├── ml/                                    # [UNCHANGED] frozen legacy serving lib
├── frontend/                              # [UNCHANGED]
├── scripts/
│   ├── ci/                                # run_ci_*.py, ci_corpus_dependent.txt [MOVE]
│   ├── data/                              # v2 builders (build_*, replay_feature_matrix.py) [MOVE]
│   ├── validation/                        # check_*, validate_* [MOVE]
│   ├── benchmarks/                        # benchmark_* (kept, organized) [MOVE]
│   └── maintenance/                       # utils survivors [MOVE]
├── tests/
│   ├── unit/ integration/ scientific/      # [NEW] re-homed by subsystem [MOVE]
│   ├── contracts/ api/ simulation/ strategy/ release/  # [NEW] [MOVE]
│   └── fixtures/                          # [UNCHANGED]
├── docs/
│   ├── architecture/ development/ science/ # [NEW] curated current docs [MOVE]
│   ├── case-study/                        # [UNCHANGED]
│   ├── releases/                          # P10/P11 release audits [MOVE]
│   └── history/{v1,v2-phases}/            # [NEW] frozen phase reports [MOVE]
├── data/                                  # [UNCHANGED] (tracked legacy CSVs stay; corpus stays ignored)
├── results/                               # [UNCHANGED] minus C1 archive set [ARCHIVE subset]
├── runtime_artifacts/                     # [UNCHANGED] ignored bundle staging
├── Dockerfile.backend, Dockerfile.frontend, compose.yaml, Makefile  # [UNCHANGED] (path edits only for RENAME/MOVE)
├── requirements.txt, requirements-test.txt, frontend/package.json   # [UNCHANGED]
└── ARCHIVED → f1-race-intelligence-v1-archive.zip (external/NAS, NOT in tree)  # [ARCHIVE]
```

[DELETE] applies to nothing in-tree (archive, don't delete; history stays).
Supports spatial replay, race dynamics, Monte Carlo 2.0, multi-model lab,
ensembles, distributions, strategy 2.0, counterfactuals, uncertainty,
pre-race intel as new subpackages under `raceintel/` — no version sprawl.

## Migration risks

- `v2/` → `raceintel/` RENAME: **MEDIUM** (import churn ~120 files + tests;
  mitigated by single coordinated C2 + C5 equivalence; Docker COPY + CI +
  docs coupling).
- `api/` internal legacy/v2 split: **LOW** (additive moves, router mounts
  stable; frontend paths unchanged).
- `scripts/` + `tests/` re-home: **MEDIUM** (CI corpus manifest +
  EXPECTED_COLLECTED pin + Makefile/CI refs must move atomically).
- `docs/` re-home: **LOW** (Docker refs only 2 manifest paths — keep those
  stable or move atomically).
- `results/` + root-doc archive: **LOW** (no active refs; C1 re-grep +
  C5 suite proves).
- `src/` layout (Option C): **HIGH** — DO NOT PERFORM (Docker COPY,
  `V2_PROJECT_ROOT`, conftest `sys.path`, CI coupling; no runtime benefit).
- Dependency/tooling purges: **MEDIUM-HIGH** — DO NOT PERFORM beyond
  `.gitignore` gap fixes without `pipdeptree` + Docker rebuild proof.
- Rewriting Git history to purge fastf1 blobs: **HIGH / FORBIDDEN** —
  destroys `v2-final` recovery. Never.
- No numeric overall score (per spec). Rule: any MEDIUM+ change ships with
  its C5 gate green or rolls back.

## Consolidation roadmap

- **C1 — V1 archive + historical cleanup.** Scope: create external ZIP from
  LEGACY_UNUSED list only (after C1 re-grep), remove active-tree copies,
  keep history. Allowed: archive + delete listed paths + manifest. Forbidden:
  import/source/test/config/dep changes; `v2/` rename; tooling resolution.
  Gate: ZIP verifies (count+hashes+archive SHA) + `make ci` green +
  `preflight-source` green. Rollback: `git checkout v2-final -- <paths>` /
  full `git checkout v2-final`.
- **C2 — source/package/script/test structural consolidation.** Scope:
  Option-B rename + `api/` split + `scripts/` + `tests/` + `docs/` re-home.
  Allowed: moves + import updates + manifest/pin updates. Forbidden:
  behavior changes, dep changes, deletions beyond C1 set. Gate: `make verify`
  + `make science` (Tier-3 where corpus exists) + Docker builds. Rollback:
  C2 branch revert to C1 freeze tag.
- **C3 — dead code/dependency/tooling/cache hygiene.** Scope: `.gitignore`
  gaps (`.opencode/`, `.impeccable/`), graft-era tracked tooling verdict,
  proven-dead removals with coverage evidence, `pipdeptree`-backed dep
  review (no removals without Docker rebuild proof). Forbidden: structural
  renames, science changes. Gate: `make ci` + clean `git status` on fresh
  clone + Docker build. Rollback: C3 revert to C2 tag.
- **C4 — references/imports/commands/docs normalization.** Scope: doc
  pointers (README single entry), naming touch-ups in live code only,
  canonical entry-point docs, stale cross-refs. Forbidden: moves/deletes.
  Gate: docs lint (links), `make verify`. Rollback: C4 revert.
- **C5 — full regression + runtime/scientific equivalence.** Scope: run
  everything (`make verify`, `make science`, Docker + Compose smoke,
  `prepare_runtime_artifacts --validate`, benchmark parity vs
  `results/v2_final_validation/`). No changes except fixes for regressions
  found. Gate: all green + artifact-hash parity. Rollback: stage-tag chain.
- **C6 — clean post-v2 baseline freeze.** Scope: tag + release note +
  (optional, local-only) directory rename to `f1-race-intelligence`.
  Forbidden: any code change. Gate: HEAD == new freeze tag, dirt-free
  (modulo ignored). Recovery: `v2-final` + C-stage tags + V1 ZIP.

## V1 archive safety plan

C1 workflow (designed here, executed there):

1. Enumerate approved paths (LEGACY_UNUSED list + C1 re-grep sign-off).
2. `sha256sum` every source file → manifest rows.
3. Write manifest (schema above) with source_reference `v2-final`.
4. `zip -X -r` the archive **outside** the repo (e.g. `/tmp/` or user dir).
5. `unzip -t` integrity check.
6. Extract to temp dir → file-count match.
7. Per-file hash match against manifest.
8. `shasum -a 256` archive → record.
9. User copies ZIP to NAS (this environment cannot verify NAS arrival
   unless a NAS path is mounted and explicitly supplied — do not claim it).
10. Only then `git rm` approved paths from active tree.
11. Run `make ci` + `preflight-source` after removal.
12. Commit C1 with manifest reference (hashes, not the ZIP).

## Recovery strategy

- Primary: `git checkout v2-final` — full frozen release, always. Then
  re-apply stage work from stage tags (C1…C6 each tag their completion).
- V1 ZIP is convenience/external storage only — never the sole recovery
  path; Git history is authoritative for every tracked file.
- Historical fastf1 blobs stay in history (R7 removal already effective in
  the index); never `filter-branch`/`filter-repo`.
- Pre-work snapshot for every stage: `git tag <stage>-start <sha>` +
  `git status` clean-check; rollback = checkout the tag.

## C1 handoff

C1 may start when this audit is accepted. C1 input checklist:

1. LEGACY_UNUSED inventory (§ Proposed V1 archive) + per-item sizes/hashes
   to compute at runtime.
2. Re-grep each candidate against: imports, tests, fixtures, Makefile, CI,
   Docker/Compose, docs, manifests, frontend assets — two-person rule:
   any hit → move to UNCERTAIN, do not archive.
3. Special care: `build_phase9_evidence.py` (frontend-CI ref — resolve in C4
   terms before archiving); `run_p11_performance_benchmark.py` (keep
   evidence JSON regardless); `results/debug/` (default keep).
4. FORBIDDEN in C1: touching `ml/`, legacy `api/`, `data/processed`,
   `data/interim`, `results/models`, fixtures, `v2/` name, deps, tooling,
   `.gitignore`, history.
5. Gates: archive verifies ( § V1 archive safety plan steps 5–8) + `make ci`
   + `preflight-source` green post-removal.
6. Secret hygiene: rotate the `.env` Gemini key out-of-band; never stage `.env`.

## Entry gate

- [x] HEAD = `487f15dee184f32f2adeb94814054eb60c98e505` (v2-final commit)
- [x] v2-final tag verified (annotated; dereferences to HEAD)
- [x] nothing staged (`diff --cached` empty)
- [x] all dirty paths classified (18/18 PREEXISTING_OTHER_WORK; 0 UNKNOWN)
- [x] Graphify updated (12174 nodes / 29328 edges / 377 communities)
- [x] top-level repository inventoried
- [x] V1 definition established (exclusive-origin + non-requirement test)
- [x] every V1 candidate classified (V2_REQUIRED / HISTORICAL_EVIDENCE /
      LEGACY_UNUSED / UNCERTAIN)
- [x] active references checked (imports, tests, fixtures, Makefile, scripts,
      Docker, Compose, CI, docs, manifests, hashes, frontend, loaders)
- [x] V2_REQUIRED V1-looking material identified (ml/ + legacy api/data/
      results + R2 suite + Docker closure)
- [x] HISTORICAL_EVIDENCE identified
- [x] LEGACY_UNUSED identified
- [x] UNCERTAIN material retained (explicit list; never removable)
- [x] proposed V1 archive inventory produced
- [x] archive safety rationale provided
- [x] KEEP_IN_GIT list produced
- [x] source architecture audited
- [x] v2/ namespace specifically assessed (domain layer, not version tag)
- [x] minimal/moderate/src-layout options compared
- [x] one source-layout option recommended (OPTION B)
- [x] scripts audited
- [x] tests audited
- [x] docs audited
- [x] results/artifacts audited
- [x] data audited
- [x] generated/cache hygiene audited (incl. `.gitignore` gaps + secret note)
- [x] developer tooling dirt explicitly dispositioned
- [x] dependencies audited
- [x] entry points audited
- [x] naming audited
- [x] dead-code candidates evidence-classified (no false PROVEN_DEAD)
- [x] duplication audited
- [x] target repository tree proposed (2–4 levels, change-legend)
- [x] migration risks classified (LOW/MEDIUM/HIGH, no numeric score)
- [x] C1–C6 roadmap produced (scope/allowed/forbidden/gate/rollback each)
- [x] archive verification workflow designed
- [x] recovery strategy documented
- [x] only C0 audit report created
- [x] nothing moved / renamed / deleted
- [x] no ZIP created
- [x] no dependencies changed
- [x] no source/tests/config changed
- [x] nothing staged/committed/tagged
- [x] v2-final remains untouched
- [x] C1 handoff explicit
