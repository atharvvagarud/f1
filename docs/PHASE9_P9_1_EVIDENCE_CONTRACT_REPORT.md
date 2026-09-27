# PHASE 9 P9-1 FROZEN EVIDENCE CONTRACT REPORT

P9-1 creates the static evidence layer for /models and /about. No UI,
no backend routes, no scientific changes. P9-0
(`docs/PHASE9_P9_0_MODELS_ABOUT_AUDIT.md`) is the authoritative design;
this report records what was built from it.

## Contract design

Two versioned JSON files plus one TypeScript module:

- `frontend/data/models.v1.json` (~30 KB) — production spec,
  holdout, development, selection, calibration, features,
  coefficients, permutation, safeguards, performance, limitations.
- `frontend/data/about.v1.json` (~10 KB) — capabilities, four
  semantics, architecture, dataset stats, reproducibility,
  limitations.
- `frontend/features/models/lib/evidence.ts` — explicit union types
  (`MetricRole`, `EvaluationClass`, `ProbabilitySemantics`,
  `SystemSemanticId`), version constants, and hand-written
  fail-closed validators. No `any`, no `Record<string, any>` blobs.
- Generator `scripts/build_phase9_evidence.py` derives both JSONs
  from frozen artifacts only. No new backend API (frozen numbers do
  not need serving).

Development and holdout live in separate objects
(`development_evidence` vs `holdout_evidence`); no shared
`model_results` array exists anywhere in the contract.

## Source registry

13 stable source IDs (`MODEL_CARD`, `MODEL_LAB_FREEZE`,
`FINAL_HOLDOUT_2025`, `M2_BASELINES`, `M3_LOGREG`, `M4_NONLINEAR`,
`M5_BAGGED`, `M6_TUNING`, `M7_BOUNDARY`, `M8_CALIBRATION`,
`FEATURE_REGISTRY`, `E3_GLOBAL_EXPLANATION`, `PHASE8_FREEZE`) with
relative paths and SHAs where artifacts are concerned. Every metric,
candidate, safeguard, and performance record carries `source_ids`;
the node test asserts all IDs resolve.

## Identity guards

The generator fails closed on: winner serving file SHA, Phase-2
content hash + parquet SHA (via manifest), E3 artifact SHA, holdout
report SHA (via freeze manifest), task/feature-set/holdout-access
flags on all seven Model Lab reports, M8 RAW selection, E3 evidence
class, 84/106 counts, family sum, and Phase-8 corpus counts. Any
drift raises `EvidenceError` before any output is written.

## Model spec, holdout, development, calibration, features

As specified in P9-0 and verified by test: LogReg C=0.01 RAW
INDEPENDENT_BINARY ALL_84/v8; 9 holdout metrics at stored precision
under `FROZEN_ONE_SHOT_2025_HOLDOUT` with EARLY/MID/LATE stages;
D1–D3 folds plus FINAL_FIT/HOLDOUT; 9 comparable development
candidates with per-fold log loss; M8 RAW/Platt/Isotonic under
`FROZEN_DEVELOPMENT_CALIBRATION`; 8 families summing to 84 with
per-family names extracted from the E3 artifact (not hand-copied).

## Explainability, safeguards, performance, capabilities, semantics

Coefficients preserve LOG_ODDS (intercept −5.57417, top-10 by |coef|);
permutation preserves `PRE_2025_FINAL_FIT_IN_SAMPLE` as a structural
field with an explicit not-out-of-sample note (object named
`permutation_evidence`, never `feature_importance`). Safeguards carry
the bounded statement verbatim (no boolean "no leakage").
Performance has four separate classes, no universal `latency_ms`.
Eight capabilities with does/does-not/semantics. Four system
semantics with `not_to_confuse_with`. Architecture lists implemented
items plus an explicit `not_used` block. Dataset stats verified
(173/171+2, 189420, 3458/6336/9324/25779/14992; Tier-B 76/1149/25784;
replay 149/9644/189610) with 2025-NOT-served scope note.
Reproducibility: 8 freeze tags, 5 hashes, seed 42, 5 manifests, 6
make targets, no one-command claim. Limitations use stable IDs on
both pages.

## 2025 firewall

Generator contains no `predict_proba`, `read_parquet`,
`joblib.load`, `pickle.load`, or `.fit(` (test-grepped); it hashes
the serving joblib without unpickling it. The only 2025 performance
source is the frozen holdout report. No new 2025 metric, chart, or
calibration can be derived from this layer.

## Language red-team

Generated copy scanned for: best/most-accurate model, perfectly
calibrated, zero leakage, true reason, probability contribution,
production-scale, real-time F1, live prediction, composite scores,
generic accuracy — all absent. "Caused" absent.

## Determinism

Generator run twice: byte-identical output (`sha256sum -c` OK).

## File SHAs (P9-1 evidence identities)

- `frontend/data/models.v1.json`:
  `9ae9b6bb025bb5d271aca365b6b0d72cafb49b4027f5589d731aeddf0bf03685`
- `frontend/data/about.v1.json`:
  `4e73f0325989193ce899d838b5ae5282354066002c1463037dac368f6407d8c4`

## Tests

`frontend/features/models/lib/evidence.test.ts`: 17 subtests green
(contract versions, validators, identity, holdout-verbatim,
roles/no-composite/no-accuracy, dev/holdout separation, folds,
families, calibration, permutation class, bounded safeguards,
unserved-2025, four semantics, dataset stats, source resolution,
language red-team, generator firewall). Full frontend gate: 165
passed, 0 failed; `tsc` clean; `eslint` clean. No backend test
changes (no backend touched).

## Graphify final

`graphify update .` — no topology changes reported (stable graph).
Direction: the generator reads frozen evidence (`data/`, `docs/`,
`results/`) and writes `frontend/data/`; frontend evidence types
import JSON only; no Phase-1–8 scientific module imports Phase-9
code; no new scientific cycle and no backend dependency.

Graph: 10,769 nodes · 27,341 edges · 325 communities (unchanged).

## Repository safety

No `reset/restore/checkout/clean/stash/add/commit/tag` performed.
Nothing staged (`git diff --cached` empty). Pre-existing tooling
work untouched. New files only: generator, 2 JSONs, TS contract,
node test, this report — all uncommitted, awaiting the P9-5 freeze.

## P9-2 entry gate

All boxes satisfied by the evidence above: versions frozen;
registry complete; identities guarded; spec/holdout/folds/
candidates/calibration/families/permutation/safeguards/performance/
capabilities/semantics/stats/repro/limitations encoded; TS explicit;
tests + red teams green; byte-identical determinism; SHAs recorded;
no backend/API; no scientific modification; nothing staged.
