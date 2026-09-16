# P3.1 Production Handoff & Repository Seal Report

P3.1 is a post-freeze engineering handoff, not a modeling stage. Phase 1,
Phase 2 and Phase 3 (Model Lab M0–M9) are FROZEN. No model, feature,
preprocessing, calibration, threshold, split, metric or result changed in
P3.1. The protected 2025 holdout was NOT evaluated in P3.1.

## Files changed

Production handoff (new):

- `v2/model_lab/serving.py` — narrow serving boundary
  (`load_frozen_winner_model`, `FrozenWinnerPredictor.predict_proba`,
  `materialize_serving_artifact`, `describe_serving_artifact`).
- `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib` — tracked
  production artifact (fitted preprocessing + fitted estimator state only).

Holdout seal:

- `v2/model_lab/errors.py` — added `ProtectedHoldoutAlreadyConsumed`
  (subclass of `ProtectedHoldoutError`) and `ServingArtifactError`.
- `v2/model_lab/final_fit.py` — `_refuse_if_holdout_consumed` guard at the
  top of `run_m9` and `evaluate_protected_holdout`, before any
  canonical-matrix load or target materialization.

Fresh-clone behavior:

- `tests/model_lab_helpers.py` (new) — shared skip helpers with a tracked
  vs generated prerequisite policy.
- `tests/test_v2_model_lab_m2/m3/m4/m5/m6/m7/m8/m9.py` — canonical fixtures
  and generated-artifact loaders skip (instead of failing) when gitignored
  prerequisites are absent; identical behavior when present.
- `tests/test_v2_model_lab_m0/m1.py` — `serving.py` added to the
  stage-exemption sets following the established per-stage pattern; the
  P3.1 module owns the stricter successor guard (no `.fit(`, no holdout
  access), enforced in `tests/test_v2_model_lab_p31.py`.

Focused tests:

- `tests/test_v2_model_lab_p31.py` (new, 18 tests).

CORS:

- `api/main.py` — `allow_credentials` `True` → `False` (wildcard origins
  kept for local development; no credentialed cross-origin need, no auth
  redesign).

Docs:

- `README.md` — Phase 3 M0–M9 FROZEN, Phase 4 NEXT; final-model statement;
  final doc links; verification baseline 1307 passed / 4 known xfailed;
  fixed `V2_FOUNDATION_REFACTOR.md` → `V2_FOUNDATION_REFACTOR.md.md` link.
- `docs/MODEL_LAB_PROTOCOL.md`, `docs/MODEL_LAB_EXPERIMENT_FRAMEWORK.md` —
  status headers updated to M0–M9 FROZEN (body history untouched).
- `v2/model_lab/__init__.py` — package docstring updated to M0–M9 FROZEN +
  serving boundary; exports `FrozenWinnerPredictor`,
  `load_frozen_winner_model`, `default_serving_artifact_path`.
- `v2/model_lab/winner.py` — docstring corrected (protected holdout was
  evaluated exactly once by sanctioned M9; now sealed).
- This report (`docs/MODEL_LAB_P31_HANDOFF_REPORT.md`).

## Frozen scientific specification verification

Unchanged and re-verified (`FF.specification_fingerprint()` ==
`3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d`):

- TASK winner, TARGET `is_winner`, MASK `eligible_is_winner`.
- FEATURE SET ALL_84 (84 ordered features, hash `dad1ba72…f241`,
  identical in the M9 metadata descriptor, the F16 registry resolution
  and the serving artifact).
- ESTIMATOR sklearn `LogisticRegression`, C=0.01, l2 (default), lbfgs,
  max_iter=1000, class_weight=None, random_state=42.
- PREPROCESSING frozen train-fitted (median + StandardScaler numeric,
  most-frequent bool, `MISSING` + one-hot unknown=ignore categorical).
- CALIBRATION RAW; BINARY_PROBABILITY / INDEPENDENT_BINARY (never
  normalized across a race); state_equal weighting; no resampling; seed 42.
- FINAL FIT 2018–2024 (149 races, 162728 eligible states, 8926
  positives / 153802 negatives); PROTECTED HOLDOUT 2025.

## Production serving architecture

- Format: joblib mapping (`format: v2-serving-winner-logreg-raw`,
  `format_version: v1`) holding the fitted `FittedPreprocessor`
  (train-fitted ColumnTransformer state) and the fitted
  `LogisticRegression` object — the existing stack's simplest faithful
  representation. No custom model runtime; numerical behavior unchanged
  (exact 0.0 equivalence, see below).
- Location: `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`
  (tracked; fresh clones contain it).
- Creation: `materialize_serving_artifact()` runs the M9 pre-unlock gate
  (frozen spec, C, RAW, ALL_84, preprocessing contract, FINAL_FIT window,
  Phase-2 hashes, holdout firewall — no 2025 targets), then
  `materialize_final_fit` (count/season anchors, rejects any 2025 leak)
  and one `fit_final_model`; verifies ordered features, dim 106 and
  estimator parameters before `joblib.dump`. Heavy imports (data,
  final_fit) are function-local.
- Loading: `load_frozen_winner_model()` validates envelope, task,
  feature set, RAW, semantics, exactly 84 ordered names + hash,
  transformed dim 106, estimator class, recorded AND live-object
  parameters (C/solver/max_iter/class_weight/random_state), training
  seasons, preprocessor-column agreement and coefficient shapes before
  returning the predictor. Any mismatch raises `ServingArtifactError`;
  nothing is silently substituted.
- API startup never refits: loading needs only joblib/numpy/pandas/
  sklearn + the frozen preprocessing class. A subprocess test asserts
  that importing `v2.model_lab.serving` pulls in no runner, tuning,
  final-fit, holdout or calibration-selection machinery.
- Serving dependencies: `v2.model_lab.preprocessing` (fitted-state class),
  `v2.model_lab.errors`, `v2.config`, sklearn/pandas/numpy/joblib.
  Tuning (`tuning*`), evaluation runners (`runner`, `model_runner`,
  `run_*`), experiment orchestration and holdout access are excluded by
  construction (module-source guard + import test).
- Batch prediction: `FrozenWinnerPredictor.predict_proba(frame)` takes the
  observable race field as one DataFrame with exactly the 84 ordered
  columns, preserves row identity/order, checks finite input, finite
  output and [0, 1] range, and returns independent per-driver
  probabilities (no cross-race normalization).

## Production artifact identity

- Path: `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`
- SHA-256:
  `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
- sklearn version: 1.8.0
- Feature count: 84; ordered feature hash:
  `dad1ba7259db8b02f0850387d0e5b8cda616b59516112fc8cd5d5dc2910fd241`
- Transformed dimension: 106
- Estimator class: `LogisticRegression`
- Estimator parameters: C=0.01, solver=lbfgs, max_iter=1000,
  class_weight=None, random_state=42
- Frozen spec fingerprint:
  `3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d`
- Phase-2 references: matrix content hash
  `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`;
  training seasons 2018–2024; 149 races / 162728 eligible states
  (positives 8926, negatives 153802, from M9 anchors).
- M9 freeze manifest: `docs/MODEL_LAB_FREEZE_MANIFEST.json` (unchanged).

## Development-fixture equivalence

- Fixture: D1 validation season (2022) eligible winner rows via
  `SPLITS.materialize(canonical, "winner", "D1", "ALL_84")`
  (2025 never touched; max validation season asserted < 2025).
- Reference predictor: fresh `FF.fit_final_model` on FINAL_FIT 2018–2024.
- Loaded serving predictor: `load_frozen_winner_model()` from the tracked
  artifact.
- Max absolute probability difference: **0.0** (exact equality, PASS).
- Also verified: exactly 84 ordered inputs, transformed dim 106,
  identical missing/unknown-category handling (shared frozen
  preprocessor), finite outputs in [0, 1], row identity/order preserved,
  batch call.

## Protected holdout seal

- Existing holdout artifact SHA before P3.1:
  `2c3a166df1a1af1d20f24fafc6a17283de1cdd1eea2b5f67a26204ed174a7415`
- SHA after P3.1: identical (byte-identical; refused re-runs never open
  the file for writing).
- Second-access behavior: `FF.run_m9(allow_protected_holdout=True)` and
  `FF.evaluate_protected_holdout(..., allow_protected_holdout=True)` raise
  `ProtectedHoldoutAlreadyConsumed` (a `ProtectedHoldoutError`) whenever
  the canonical artifact (or an explicit `--out` target) exists.
- Refusal occurs before target materialization: verified by monkeypatching
  `DATA.load_canonical` to record calls — zero calls before the raise.
- Ordinary holdout firewall intact: `SPLITS.get_split(HOLDOUT)`,
  `RUN.resolve_development_fold`, `FF.materialize_holdout` and
  `FF.evaluate_protected_holdout` without opt-in all raise.
- The recorded `materialization_access_count: 1` /
  `target_evaluation_count: 1` in the artifact describe the single
  sanctioned M9 run; no persistent global counter was fabricated — the
  canonical artifact itself is the durable consumed marker.
- Confirmation: 2025 targets were NOT evaluated in P3.1 (no holdout
  materialization, no metric computation; seal tests use temp paths and
  mocks only).

## Fresh-clone behavior

`tests/model_lab_helpers.py` encodes the policy: TRACKED prerequisites
(committed source/tests/docs) still FAIL when missing; GENERATED
prerequisites (gitignored `data/v2/` matrix, experiment dirs, suite
summaries) SKIP clearly. Converted: `canonical` fixtures in
m2–m9, synthetic-frame schema loads in m3/m4/m5, suite-summary loaders in
m4/m5/m6/m7/m8, M6/M3 and M7 artifact reads in m7/m8, and the M9
pre-unlock test. When artifacts ARE present, all assertions run
unchanged. Tracked-doc checks (freeze manifest, model card, final report)
still fail hard when missing.

## Documentation corrections

As listed under Files changed. No historical numerical result was altered;
stale status claims (M2-next, no-model-trained, pre-holdout winner-adapter
note, broken foundation-refactor link, Phase-2-era test counts) corrected
at the status/header level only.

## CORS change

`api/main.py`: `allow_credentials=True` → `False` with wildcard origins
retained. The frontend performs no credentialed cross-origin requests, so
local development behavior is preserved with no authentication redesign.
Pinned by `test_api_cors_disallows_credentialed_wildcard`.

## Verification

Medium regression gate (P3.1 + M0/M1/M1.1/M2/M3/M4/M5/M6/M7/M8/M9 + API):

- Command: `pytest tests/test_v2_model_lab_m0.py ... _m9.py
  _p31.py tests/test_api_baseline.py -q` (13 files,
  `/opt/homebrew/bin/python3.11`, pytest 9.1.1)
- Result: **475 passed, 0 failed, 0 skipped, 0 xfailed** in ~300 s.
- Note: an earlier gate run showed 472 passed + 2 failed, both being the
  M0/M1 "no estimator" contract guards tripped by the new serving module;
  resolved via the sanctioned stage-exemption pattern with a stricter P3.1
  successor guard; the final rerun is fully green.

Full repository pytest was not repeated: P3.1 changes are narrowly scoped
(new serving module, additive guard, test-only helpers, one-line CORS
change, status-level docs) and the medium gate covers every directly
affected contract. D11 was not rerun: no Phase-1/Phase-2 surface changed.

## Frozen hash verification

All before/after pairs identical (before values captured pre-change, see
P3.1 task log; representative values):

- Phase-2 parquet: `b0f17b66…a1590b3`
- Phase-2 manifest: `b6a63f5e…764d6cbc62`
- Phase-2 ablation: `bb59d936…44ed86f2f5a7`
- Phase-2 freeze manifest doc: `ced17eb9…9365b4ce`
- M0 protocol JSON: `6a02b4c2…445cf18545e01`
- M2–M8 stage artifacts + preunlock + holdout + final metadata + freeze
  manifest + model card + final report: unchanged (full table in the
  final task report).
- New: serving artifact
  `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
  (additive only; no historical hash replaced).

## Git classification

Committed (Phase-3/P3.1): `v2/model_lab/` (new tracked tree),
`tests/test_v2_model_lab_*.py` + `tests/model_lab_helpers.py`,
`docs/MODEL_LAB_*.md`, `docs/generated/model_lab_protocol_v1.json`,
`docs/generated/model_lab_split_audit_v1.json`,
`results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`, `README.md`,
`api/main.py`, this report.

Intentionally ignored/generated (excluded): `data/v2/**` (canonical
matrix, experiments, suite reports incl. absolute-path provenance
strings, protected holdout artifact per gitignored-data policy),
`graphify-out/`, caches, FastF1 caches.

Unrelated dirty files left untouched: `.claude`/`.cursor`/`.gemini`/
`.ignore`/`.mcp.json` deletions, `.gitignore`, `AGENTS.md`, `GEMINI.md`,
`opencode.json` modifications, `.opencode/`, root `package.json` /
`package-lock.json`, `.DS_Store`.

Absolute-path note: earlier Model Lab reports under `data/v2/` contain
local absolute provenance paths, but they are gitignored generated
artifacts excluded from the seal commit, and their bytes are covered by
the freeze manifest — therefore NOT modified. Tracked docs contain no
absolute paths. No `REPOSITORY SEAL BLOCKED` condition arose.

## Commit/tag result

- Commit: the seal commit carrying this report, referenced by tag
  `v2-model-lab-phase3`
  (`feat(v2): freeze model lab and add production inference handoff`) —
  79 files, Phase-3/P3.1 scope only; unrelated worktree changes
  (IDE/harness deletions and config modifications, `.opencode/`, root
  `package.json`/`package-lock.json`) left untouched and uncommitted.
- Tag: `v2-model-lab-phase3` (annotated) on the seal commit.
- Fresh checkout contains all required Phase-3 code, tests, docs and the
  tracked serving artifact; gitignored `data/v2/` regenerates via the
  versioned pipelines.

## Graphify result

- `graphify update .`: SUCCESS — 5746 nodes, 12275 edges, 272 communities
  (aggregated community view; 64 files re-extracted, AST-only, no API
  cost). Output stays in gitignored `graphify-out/`.

## Deferred Ponytail findings

All explicitly deferred items from the P3.1 brief remain untouched
(legacy scripts deletion, runner/suite consolidation, helper/schema
deduplication, prediction_service layering, D10/D11 semantics, storage
refactors, results cleanup, requirements/frontend redesign, WebSockets,
RaceState, Phase 4 scope, general style cleanup).

## Findings by severity

- BLOCKER: none.
- MAJOR: M0/M1 "no estimator" contract guards initially failed on the new
  serving module; resolved via the established stage-exemption pattern
  plus a stricter P3.1 successor guard (no fit, no holdout access) —
  verified passing.
- MINOR: serving loader initially validated only recorded estimator
  params, not the live object; hardened to cross-check both (covered by
  the tampered-C rejection test).
- NOTE: the default `python3` (homebrew 3.14) does not execute code in
  this shell session; all verification used `/opt/homebrew/bin/python3.11`
  (sklearn 1.8.0, pytest 9.1.1). README documents interpreter override
  via `make PYTHON=`.

## Scientific freeze conflicts

NONE.

## Unresolved blockers

None.

## P3.1 Definition of Done

- [x] frozen scientific specification unchanged
- [x] no protected 2025 target evaluation
- [x] final holdout artifact byte-identical
- [x] production serving artifact created
- [x] serving artifact validated
- [x] no API-startup refit
- [x] narrow serving interface exists
- [x] development equivalence passed
- [x] second protected evaluation mechanically blocked
- [x] ordinary holdout firewall intact
- [x] fresh-clone artifact behavior corrected
- [x] stale Phase-3 docs corrected
- [x] CORS issue corrected
- [x] medium regression gate passed
- [x] required hashes unchanged
- [x] repository seal attempted safely
- [x] Graphify updated
- [x] Phase 4 NOT started
