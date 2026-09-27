# PHASE 9 FINAL FREEZE REPORT (P9-5)

P9-5 is validation + freeze only. No product functionality, no scientific
development. One freeze commit + one annotated tag. DO NOT begin Phase 10.

## Phase-9 objective

Present frozen 2018–2025 model-lab evidence as two static, portfolio-grade
routes — `/models` (validation laboratory) and `/about` (system dossier) —
without retraining, reevaluation, recalibration, new metrics, rankings, or
any 2025 raw-data access.

## P9-0 → P9-5 stage history

- P9-0 (`docs/PHASE9_P9_0_MODELS_ABOUT_AUDIT.md`) — read-only audit; model
  identity, holdout values, folds, candidates, calibration, features, E3,
  safeguards, IA for both routes. No code touched.
- P9-1 (`docs/PHASE9_P9_1_EVIDENCE_CONTRACT_REPORT.md`) — generator
  `scripts/build_phase9_evidence.py` + `frontend/data/models.v1.json` +
  `frontend/data/about.v1.json` + `frontend/features/models/lib/evidence.ts`
  + 17 contract tests. Byte-identical determinism.
- P9-2 (`docs/PHASE9_P9_2_MODELS_IMPLEMENTATION_REPORT.md`) — `/models`
  route (11 section components), `modelsEvidence.ts` entry point, 16 page
  tests, CommandBar MODELS link + narrow-screen internal scroll.
- P9-3 (`docs/PHASE9_P9_3_ABOUT_IMPLEMENTATION_REPORT.md`) — `/about`
  route (12 section components), `aboutEvidence.ts` entry point, 16 page
  tests, CommandBar ABOUT link.
- P9-4 (`docs/PHASE9_P9_4_INTEGRATION_HARDENING_REPORT.md`) — zero-diff
  hardening: 30/30 responsive cells, keyboard/a11y audit, semantic sweep,
  live 5-route product matrix, 197 tests green.
- P9-5 (this report) — final validation + freeze.

## Evidence architecture

Frozen artifacts → `scripts/build_phase9_evidence.py` (hash-guarded,
fail-closed, no `predict_proba`/`fit`/`read_parquet`/`joblib.load`) →
checked-in `frontend/data/{models,about}.v1.json` → typed validators in
`evidence.ts` / `aboutEvidence.ts` → server-rendered static routes. No
evidence API, no fetch, no client recomputation. Development
(`FROZEN_DEVELOPMENT_FOLDS`) and holdout (`FROZEN_ONE_SHOT_2025_HOLDOUT`)
are separate objects; no shared result array exists.

## /models summary

01 production spec (LogReg C=0.01 RAW INDEPENDENT_BINARY ALL_84/v8) ·
02 holdout (PRIMARY log loss 0.0680; SECONDARY Brier/PR-AUC/top-1/top-3;
TECHNICAL ROC/ECE/state-pooled; EARLY/MID/LATE bars) · 03 temporal folds
(D1 2018–2021→2022, D2 →2023, D3 →2024, FINAL_FIT 2018–2024, locked 2025
vault) · 04 dev-only 9-candidate comparison (no ranking) + selection
protocol · 05 dev-only RAW/Platt/Isotonic calibration · 06 84→106 feature
system (8 families) · 07 LOG_ODDS coefficients + in-sample permutation
banner · 08 bounded safeguards · 09 limitations · provenance.

## /about summary

Dossier header (DATA 2018–2025 / SERVED 2018–2024 / FEATURES 84 /
149 races / 9,644 checkpoints) · 7 system threads · FACT/PREDICTION/
SIMULATION/STRATEGY semantics · 8-stage architecture + 9-item not-used
block · 8-capability matrix · Tier-A/B + Phase-2/replay stats + 2025
boundary panel · bounded safeguards · replay-intelligence flow ·
Monte Carlo vs paired-CRN strategy · P1–P8 reproducibility timeline ·
9 limitations · provenance.

## Scientific boundaries

No retrain/refit/retune/recalibration/2025-reevaluation; no Phase-1–8
scientific code modified (verified: staged diff contains zero `v2/`,
`api/`, `ml/`, `data/`, `results/` paths); no new metrics, rankings,
normalized shares, SHAP, causal claims, or one-command-repro claims.

## 2025 firewall

Generator hashes (never unpickles) the serving joblib; the only 2025
performance source is `data/v2/model_lab/reports/final_holdout_2025_v1.json`
(SHA `2c3a166d…04ed174a7415`). Grep-verified: no `read_parquet`,
`predict_proba`, `joblib.load`, `.fit(` in generator, evidence layer,
`/models`, `/about`. Product: DATA 2018–2025, SERVING 2018–2024, 2025
FROZEN HOLDOUT / UNSERVED.

## Evidence identities (reverified P9-5, no regeneration)

- Phase-2 matrix parquet: `b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3`
- Phase-2 content hash: `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`
- Winner serving joblib: `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
- Phase-8 replay aggregate: `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298`
- E3 global explanation: `bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f`
- `frontend/data/models.v1.json`: `9ae9b6bb025bb5d271aca365b6b0d72cafb49b4027f5589d731aeddf0bf03685`
- `frontend/data/about.v1.json`: `4e73f0325989193ce899d838b5ae5282354066002c1463037dac368f6407d8c4`
- Generator rerun: byte-identical (`sha256sum -c` OK both files).
- Adversarial probes (temp copies): wrong version, holdout-as-development,
  perm-marked-OOS all rejected by `validateModelsEvidence` (3/3).

## Test evidence

`node --test`: 197 passed / 0 failed (49 suites: 17 evidence + 16 models
+ 16 about + Phase-8 replay/simulator/shell). `tsc --noEmit` clean.
`eslint` clean. `next build` green, all 7 routes prerendered static.
Backend proof via live smoke (below); no backend code touched so no
scientific revalidation was run.

## Responsive / a11y evidence (freeze sample)

Overflow `scrollWidth − clientWidth`: /models 1440+360, /about 1440+360,
/replay 390, /simulator 390, root 390 — all 0. Keyboard: tab lands with
2px solid `:focus-visible` ring; native `<details>` disclosures; 1 h1 per
route; 0 unscoped `<th>` on /models; text (never color-only) direction
labels; strategy outcomes as text. No WCAG certification claimed.

## Live product smoke (production build + backend :8000)

`/` `/replay` `/simulator` `/models` `/about` → 200. Real workflows:
root prediction → "Prediction ready" (independent-binary copy); replay →
149-race registry, frame-0 deep link; simulator → 1,000-trial results
render at frame 100 + exemplary 422 rejection state at default anchor
(`neutralized_track_state`); strategy → comparison with outcome
vocabulary. Zero console errors on static routes; no evidence fetch (RSC
flight only); the single 422 is the documented backend eligibility gate.

## Known limitations

Winner prediction remains independent binary; 2025 frozen holdout/unserved;
permutation is pre-2025 final-fit in-sample; explanations associational, not
causal; contributions are log-odds, not probability points; no SHAP; replay
timeline is checkpoint-granular; track visualization deferred; no live F1
feed; static Models/About evidence is a frozen project snapshot; no WCAG
certification; no cross-family latency benchmark (throughput only).

## Artifact / source provenance

Every metric/candidate/safeguard carries `source_ids` into a 13-entry
registry (`MODEL_CARD`, `MODEL_LAB_FREEZE`, `FINAL_HOLDOUT_2025`,
`M2_BASELINES`, `M3_LOGREG`, `M4_NONLINEAR`, `M5_BAGGED`, `M6_TUNING`,
`M7_BOUNDARY`, `M8_CALIBRATION`, `FEATURE_REGISTRY`,
`E3_GLOBAL_EXPLANATION`, `PHASE8_FREEZE`) with relative paths + SHAs.
Rendered provenance panels show abbreviated hashes; full hashes + relative
source paths in `<details>`. No absolute machine paths.

## Dependency direction

`/models → modelsEvidence → evidence.ts → models.v1.json`;
`/about → aboutEvidence → evidence.ts → about.v1.json` (+ shared models
entry for safeguards/seasons). No dependency from Phase-9 pages to api,
ml, v2 scientific runtime, raw Parquet, or joblib. No Phase-1–8 module
imports Phase-9 code (grep-verified).

## Final commit / tag

Commit `feat(v2): freeze models and about phase 9` (full SHA verifiable via
`git rev-list -n 1 v2-models-about-phase9`). Annotated tag
`v2-models-about-phase9`: "F1 Intelligence v2 — Phase 9 Models + About
freeze", pointing at the freeze commit. Phase-8 commit/tag untouched.
