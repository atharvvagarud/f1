# PHASE 9 P9-0 MODELS + ABOUT AUDIT

P9-0 is a READ-ONLY audit. No scientific code, frontend, API, data, or
results were modified; nothing staged, committed, or tagged. No
retraining, no 2025 reevaluation, no metric recomputation. All values
below are read from frozen artifacts/reports.

## Final verdict

P9-0 COMPLETE — READY FOR P9-1 (pending the verdict line at the end of
this document; the evidence supports it).

## Graphify-first navigation

- `graphify update .` first: no topology changes (graph stable at
  10,769 nodes / 27,341 edges / 325 communities).
- `graphify query "frozen winner model serving artifact loader
  LogisticRegression"` → `v2/model_lab/serving.py`,
  `v2/model_lab/winner.py`, `v2/model_lab/protocol.py`,
  `v2/model_lab/final_fit.py`, `docs/MODEL_LAB_FINAL_MODEL_CARD.md`.
- `graphify query "temporal evaluation splits expanding window holdout
  2025 model lab"` → `v2/model_lab/splits.py`,
  `docs/MODEL_LAB_CALIBRATION_REPORT.md`, model card holdout section,
  `v2/model_lab/calibration_selection.py`.
- Graphify then gave way to targeted reads of the authoritative
  documents (model card → final report → freeze manifest → holdout
  artifact → M3–M9 stage reports → protocol/splits/metrics code).
  Filesystem inspection was used only for `results/`, `docs/`, and
  manifest/artifact verification.

## Frozen checkpoint

- HEAD: `7fa9bf970c4281b7c7d64fecf8b8e9b207a963d8`
  (`feat(v2): freeze replay intelligence phase 8`).
- Tag at HEAD: `v2-replay-intelligence-phase8`.
- Phases 1–8 frozen reports are authoritative and were not
  re-derived; P9-0 verified only claims that will appear in product.

## Production model identity

Verified against `docs/MODEL_LAB_FINAL_MODEL_CARD.md`,
`docs/MODEL_LAB_FREEZE_MANIFEST.json` (`final_model_specification`),
and `v2/model_lab/serving.py` strict load guards. The prompt's
expected values are all confirmed:

| Field | Value | Authoritative source |
|---|---|---|
| task | `winner` | model card; `EXPECTED_TASK` in serving.py |
| target | `is_winner` | model card ("In-race winner binary probability") |
| eligibility | `eligible_is_winner` | freeze manifest spec; card |
| estimator | `LogisticRegression` | card; `EXPECTED_ESTIMATOR_CLASS` |
| C | 0.01 | card; manifest; `EXPECTED_ESTIMATOR_PARAMS` |
| penalty | l2 (sklearn default, not passed explicitly) | card; manifest |
| solver | lbfgs | card; manifest |
| max_iter | 1000 | card; manifest |
| class_weight | None | card; manifest |
| random_state | 42 (project seed 42) | card; manifest |
| feature set | ALL_84, `FEATURE_SET_VERSION=v8` | card; Phase-2 manifest |
| calibration | RAW (no calibrator fitted) | card; M8 report |
| semantics | INDEPENDENT_BINARY | card; E3; serving |
| training | 2018–2024 FINAL_FIT (149 races, 162,728 eligible, 8,926 pos) | card; M9 artifact |
| holdout | 2025 (24 races, 26,692 eligible, 1,444 pos) | card; M9 artifact |

Serving: `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`
(SHA `1116b34f…eaf3fcaa59f4`, `SERVING_ARTIFACT_VERSION="v1"`,
`EXPECTED_FEATURE_COUNT=84`, `EXPECTED_TRANSFORMED_DIM=106`,
`EXPECTED_TRAINING_SEASONS=(2018..2024)`); spec fingerprint
`3164de9e…8c329c24d`; model fingerprint `81e0e4be…071fbe8dd2076d`.
Loader `load_frozen_winner_model` enforces all of the above strictly.

## Holdout evidence

Source: `data/v2/model_lab/reports/final_holdout_2025_v1.json`
(SHA `2c3a166d…26204ed174a7415` per freeze manifest `holdout_artifact`),
presented in `docs/MODEL_LAB_FINAL_REPORT.md` (M9) and the model card.
READ ONLY — not recomputed. Exact stored values (prompt confirmed):

| Metric | Stored value | Report rounding |
|---|---|---|
| race-macro log loss | 0.0680353741 | 0.068035 |
| race-macro Brier | 0.0200141490 | 0.020014 |
| state-pooled log loss | 0.0678926695 | 0.067893 |
| state-pooled Brier | 0.0198587168 | 0.019859 |
| ROC AUC | 0.9845256886 | 0.984526 |
| PR AUC | 0.8032379039 | 0.803238 |
| ECE (10 equal-width bins) | 0.0111081578 | 0.011108 |
| synchronized top-1 | 0.7960622539 | 0.7961 |
| synchronized top-3 | 0.9789986874 | 0.9790 |

Population: 2025 one-shot holdout, 24 races / 26,692 eligible states /
1,444 positives, eligibility `eligible_is_winner`. Headline
aggregation: race-macro (equal weight per race, then row metric).
Stage log-loss (holdout): EARLY 0.077468 / MID 0.069800 / LATE 0.056847.
Holdout-vs-M7 deltas are descriptive only (different training design;
no overfitting diagnosis, no certainty claim — frozen interpretation
string). /models MUST use full-precision stored values with 4dp
display rounding noted, not the rounded report strings as source.

## Metric semantics

Definitions from `v2/model_lab/metrics.py`, `aggregation.py`,
`calibration.py`, `protocol.py` (metric applicability guards exist:
`require_metric_applicability` fails loudly on semantic mismatch).

- Log loss (binary, race-macro): mean per-race mean surprisal; lower
  better. PRIMARY headline (all selection used it). Meaningful for
  independent-binary probabilities (each driver's P(win) scored
  against that driver's outcome).
- Brier: mean squared probability error; lower better. SECONDARY.
  Same applicability as log loss; less sensitive to tail errors.
- ROC AUC: rank discrimination over pooled states; higher better.
  SECONDARY/TECHNICAL. Inflated by class imbalance optics — label as
  discrimination, not quality.
- PR AUC: precision-recall area, sensitive to ~5.5% prevalence;
  higher better. SECONDARY. More informative than ROC here.
- ECE (10 equal-width bins): mean |accuracy − confidence|; lower
  better. Calibration section only. Small-sample bins caveat.
- Synchronized top-1/top-3: fraction of races where the actual winner
  is the model's top-1 / in top-3 ranked drivers per race
  (`winner_top1_accuracy`, race_winner grouping). SECONDARY, fan-legible.
  Do NOT call "accuracy" without the synchronized-race qualifier.
- State-pooled variants: diagnostics, never headlines (large races
  would dominate). No composite score; no plain "accuracy".

## Temporal evaluation design

Frozen in `v2/model_lab/protocol.py` + `splits.py` (protocol v1,
semantic hash `0168f1d7…15cb3ef53ce`). Actual folds (NOT the prompt's
2018–2019→2020 sketch):

| Fold | Train | Validate |
|---|---|---|
| D1 | 2018–2021 (88,123 states, 81 races) | 2022 (23,577 / 22) |
| D2 | 2018–2022 (111,700 / 103) | 2023 (24,422 / 22) |
| D3 | 2018–2023 (136,122 / 125) | 2024 (26,606 / 24) |
| FINAL_FIT | 2018–2024 (162,728 / 149) | — (single all-data fit) |
| HOLDOUT | — | 2025 (26,692 / 24), one-shot |

Guards (fail-closed): train strictly before validation; 2025 unreachable
from development paths (`ProtectedHoldoutError`); M0 count audits pinned
per fold/task. Aggregation headline race-macro; state-pooled diagnostic.
Stage buckets: thirds of `race_progress_frac` (EARLY/MID/LATE, M0 policy).
Selection (M6/M7): nested inner folds inside outer TRAIN only
(D1-I1, D2-I1/I2, D3-I1/I2/I3); outer validation touched once.
Calibration (M8): calibrator fit on LAST train season only.
Visual for /models: three expanding bars (growing train 2018–20xx →
one highlighted validation season) + FINAL_FIT full bar + locked 2025
vault. Do not render the prompt's example structure.

## Candidate models

All on task `winner`, ALL_84, seed 42, protocol v1, same D1–D3 —
comparable on race-macro log loss means ONLY (different families, same
protocol/population; still label as development, never a holdout
leaderboard):

| Stage | Candidates | Dev race-macro log-loss mean |
|---|---|---|
| M2 baselines | CURRENT_LEADER/CURRENT_ORDER 0.834627, GRID_POLE 1.705803, CLASS_PRIOR 0.212238, RECENT_PACE N/A | floor |
| M3 | LogReg C=1.0 | 0.071797 |
| M4 | HGB 0.138305, XGB 0.109063 | nonlinear fixed specs |
| M5 | ExtraTrees 0.081475, RandomForest 0.088137 | bagged fixed specs |
| M6 | tuned LogReg (outer mean 0.069804) vs tuned ExtraTrees (0.075927); vs M3/M5 refs per-fold | nested tuning |
| M7 | C ∈ {0.003, 0.01, 0.03, 0.1} → global C=0.01 | boundary resolution |
| M8 | RAW 0.077027 vs Platt 0.079699 vs Isotonic 0.102793 | calibration |
| M9 | FINAL_FIT LogReg C=0.01 RAW → holdout 0.068035 | one-shot |

No fake leaderboard: a comparison table is defensible ONLY over
development race-macro means with the "different complexity, same
protocol, development-only" caption. M4/M5/M6 numbers must never be
mixed with M9 holdout numbers in one ranking.

## Model-selection evidence

From `docs/MODEL_LAB_FINAL_REPORT.md` §"Why Logistic Regression,
C=0.01, RAW" — three separated claims, no retrospective invention:

1. Measured: LogReg competitive development quality at the lowest
   complexity/cost class (M4 nonlinear worse on log loss; M5 bagged
   worse; M6 tuned LogReg ≈ M3 reference).
2. Measured: C=0.01 from the M7 predeclared global rule (aggregate
   inner log-loss fallback, lowest aggregate mean 0.0827198539; no
   strict per-fold majority — per-fold selections split D1→0.003,
   D2→0.01, D3→0.03; state this honestly).
3. Measured: RAW from the M8 predeclared rule (Platt regressed on
   D1/D3, Isotonic badly; only D2 showed small gains → material
   regressions flagged True).

Engineering considerations the evidence supports: single linear model,
~479k states/s throughput, no calibration layer to maintain, exact
log-odds decomposition enabling Phase-8 explanations. Do NOT claim
latency superiority over trees (no head-to-head latency benchmark in
evidence), "best" generalization, or interpretability beyond
coefficient/permutation evidence. Hyperparameter uncertainty is
documented as a limitation (M7).

## Calibration evidence

M8 evaluated RAW vs Platt (sigmoid) vs Isotonic on D1–D3 with the
calibration season withheld from the base fit. Cross-fold means: RAW
log loss 0.077027 / Brier 0.022289 / ECE 0.012683 / top-1 0.750508;
Platt 0.079699 / 0.022688 / 0.014913; Isotonic 0.102793 / 0.023415 /
0.015020. Reliability tables per fold exist (empty bins, largest gap,
under/over-confident counts). /models SHOULD show: ECE + a reliability
note + the 3-method comparison table (it justifies RAW). Verdict line:
"RAW retained; neither calibrator improved development probability
quality under the predeclared rule." No recalibration, ever.

## Stage-performance evidence

Stage rule thirds of `race_progress_frac` (protocol.py). Holdout
race-macro log loss: EARLY 0.077468 → MID 0.069800 → LATE 0.056847
(expectable: late-race states carry more information). Development
stage metrics exist in stage artifacts; NEVER mix dev and holdout
series without explicit labels. A 3-bar EARLY/MID/LATE holdout chart
is justified; caption "prediction gets easier as the race unfolds —
this is information, not learning."

## Feature evidence

ALL_84 verified (`FEATURE_SET_VERSION=v8`; Phase-2 manifest
`a04d5475…`; serving enforces 84→106). Exact family counts:

STATE 23 · PACE 12 · GAPS 8 · FIELD_CONTEXT 12 · RATES_MOMENTUM 4 ·
ENVIRONMENT_HISTORY 9 · PRE_RACE_PRIORS 13 · INTERACTIONS 3 = 84.

Preprocessing (train-fitted only): median+StandardScaler numerics,
most-frequent booleans (float, unscaled), `MISSING` sentinel +
train-vocabulary one-hot categoricals (unknown=ignore) → 106 dims.
Design: family-level overview (8 rows with counts + one-line meaning),
expandable to canonical feature names from the E3 artifact's
`canonical_groups`; never dump all 84 + 106 transformed dims by
default. Interaction source registry: `build_f11_registry`.

## Explainability evidence

E3 artifact `results/v2_explainability/global_winner_logreg_v1.json`
(SHA `bae84b61…`, gitignored but required at runtime):

- Coefficients (70 numeric + booleans + categorical blocks;
  intercept −5.57417). Largest |standardized| coefficients:
  `gap_to_leader_seconds` −1.073 (GAPS),
  `position` −0.645 (STATE),
  `cars_ahead_observable` −0.617 (FIELD_CONTEXT),
  `prior_driver_mean_finish` −0.573 (PRE_RACE_PRIORS),
  `gap_to_ahead_seconds` −0.501 (GAPS). Signs read on standardized
  log-odds scale; negative = associated with lower model log-odds.
- Permutation (race-macro log-loss delta, seed 42, 5 repeats,
  state-within-race): top `gap_to_leader_seconds` mean Δ 0.0270,
  then `gap_to_ahead_seconds_valid` 0.0235. Population:
  PRE_2025_FINAL_FIT_IN_SAMPLE (162,728 rows the artifact was fit on;
  2025 excluded; NOT temporally out-of-sample).
- /models SHOULD show coefficients (exact, model-internal) AND may
  show permutation top-N with the in-sample banner permanently
  visible. Never bare-label it "feature importance"; required label:
  "permutation sensitivity (in-sample, 2018–2024 fit rows)".

## Temporal-safety evidence

Product-safe bounded claim: "No temporal leakage was detected under
the implemented adversarial test suite." Forbidden: "zero leakage",
"leakage impossible", "perfect safety". Concrete safeguards to list:
race-wide synchronization; `observed_at_s/state_time_s <= T`;
no fall-forward (Phase-2 parity audit `PHASE2_LEAKAGE_PARITY_AUDIT.md`);
exact checkpoint identity (no tolerance joins); labels/masks never in
design matrix; 2025 firewall (`ProtectedHoldoutError`, one-shot M9
opt-in); post-T mutation tests; preprocessing fit on TRAIN only.

## Performance evidence

Strictly separated, all REAL and labeled:

- Model inference (M9 harness): holdout transform 0.0557 s +
  predict 0.0557 s over 26,692 states → 478,741.84 states/s;
  single-state mean 0.008571 s (harness, not API SLA).
- Replay cache build (E1): ~11.8 s/checkpoint single-core (frozen
  temporal recomputation dominates; E1.6 matrix backend is the fast
  path). Offline only.
- E4 local / E5 change (E7 warm TestClient): p50 ~24.5 ms / ~41.8 ms
  (full API incl. services, not pure inference).
- Never fuse these into one "model latency" number.

## /models information architecture

Technical model-card / evaluation-lab in BRUTALIST MOTORSPORT
TELEMETRY (existing design system; terminal/workstation, no KPI
cards). Sections (adjusted: calibration folded into holdout-adjacent
evidence; comparison labeled development-only):

01 PRODUCTION MODEL — spec table (Part A) + serving artifact + SHAs.
   Source: freeze manifest, serving.py. Static. Caveat: one frozen
   specification, not "best of all possible models".
02 HOLDOUT PERFORMANCE — 9 stored metrics (primary log loss;
   secondary Brier/PR-AUC/top-k; technical ROC/state-pooled) + stage
   thirds chart + reliability note. Source: M9 artifact. Static.
   Caveat: one season, 24 races.
03 TEMPORAL EVALUATION — expanding-window diagram (actual D1–D3 +
   FINAL_FIT + locked 2025) + guards list. Source: protocol/splits.
   Static diagram. Caveat: dev folds had less training data than
   FINAL_FIT.
04 DEVELOPMENT COMPARISON — M2→M8 means table, dev-only caption.
   Source: stage reports. Static. Caveat: not a holdout ranking.
05 CALIBRATION — RAW/Platt/Isotonic table + ECE + verdict. Source: M8.
   Static. Caveat: dev population, withheld-season design.
06 FEATURE SYSTEM — 8 families + preprocessing + 84→106. Source:
   Phase-2 manifest, E3 groups. Static + expandable detail.
07 GLOBAL MODEL EVIDENCE — top coefficients + permutation top-N with
   in-sample banner. Source: E3 artifact. Static snapshot with
   provenance hash (NOT recomputed client-side).
08 SAFEGUARDS + LIMITATIONS — bounded leakage claim + 10 Phase-8
   limitations + M7 uncertainty + one-season holdout. Static.

## System capability inventory

| Capability | Does | Does NOT | Status |
|---|---|---|---|
| Data platform | 1950–2025 results + 2018–25 FastF1 canonical states | live feeds | frozen P1 |
| Feature engine | ALL_84 temporal-safe matrix 189,420×106 | telemetry | frozen P2 |
| Model Lab | dev protocol + frozen LogReg winner | retraining UI | frozen P3 |
| RaceState+prediction | exact state + independent-binary inference | normalized distribution | frozen P4 |
| Replay | 149 races, factual frames + checkpoints | 2025 serving | frozen P5/P8 |
| Replay intelligence | cached predictions, timelines, E3/E4/E5 explanations | causal/SHAP | frozen P8 |
| Monte Carlo | stochastic mutually-exclusive outcomes | predictions | frozen P6 |
| Strategy | paired CRN counterfactual comparison | optimizer | frozen P7 |

## System semantics

Four visually separated concepts (distinct icons/colors/copy; shared
glossary): HISTORICAL FACT (observed at T) vs MODEL PREDICTION
(frozen LogReg independent-binary P(win)) vs STOCHASTIC SIMULATION
(Monte Carlo outcome frequencies, mutually exclusive) vs STRATEGY
COMPARISON (paired CRN deltas). Never share a chart axis or the word
"probability" without its qualifier.

## Architecture evidence

Implemented: Next.js frontend (`/replay`, `/simulator`, `/strategy`;
nav in `CommandBar.tsx` — no /models or /about yet), FastAPI backend,
Phase-2 Parquet matrix, frozen sklearn joblib, E2 replay cache,
Monte Carlo engine, strategy engine. Verified ABSENT (must never
claim): Postgres, Timescale, Redis, WebSockets, Celery/RQ, MLflow,
Kubernetes, Kafka, live F1 feeds. Contracts:
`PHASE5_REPLAY_API_CONTRACT.json`, `PHASE6_SIMULATION_API_CONTRACT.json`.

## Dataset evidence

Verified in `PHASE1_EXIT_REPORT.md` / `PHASE1_FINAL_VALIDATION.md`:

- Tier-A 2018–2025: 173 sessions (171 COMPLETE + 2 PARTIAL:
  2021-r12, 2022-r18), 3,458 results, 189,420 driver laps, 6,336 pit
  stops, 9,324 stints, 25,779 weather rows, 14,992 race-control rows.
- Tier-B 1950–2025: 76 seasons, 1,149 races, 25,784 results.
- Phase-2: 189,420 states, 84 predictive features, 106 columns.
- Replay: 149 served races (2018–2024), 9,644 checkpoints, 189,610
  observable predictions. Always label 2025 as holdout-only, never
  served.

## Reproducibility evidence

Safe to show: `make` targets (`test-python`, `test-frontend`,
`typecheck`, `lint`, `build`, `verify`), freeze tags
(`v2-data-platform-phase1` … `v2-replay-intelligence-phase8`),
manifests (Phase-2/5/6 freeze, E2/E7/E8), artifact SHA table, seed 42,
pinned interpreter (Python 3.11.15, sklearn 1.8.0), validation reports
per phase. Do NOT claim one-command full reproduction (data ingestion
+ backfills are heavyweight, documented per-phase).

## /about information architecture

01 WHAT THIS IS — one-paragraph v2 definition + status strip (8
   frozen phases + tags). Source: README, freeze manifests.
02 SYSTEM SEMANTICS — 4-concept panel (Part O). Static.
03 ARCHITECTURE — implemented stack only + "not used" list (Part P).
   Static diagram.
04 DATA PLATFORM — Tier-A/B + Phase-2 stats (Part Q). Static.
05 TEMPORAL SAFETY — bounded claim + safeguard list. Static.
06 MODEL + SIMULATION — pointer summaries linking to /models +
   simulation/strategy semantics. Static, no duplicated numbers.
07 ENGINEERING — test suites, guards, fail-closed API states.
   Source: test inventory, route error maps.
08 REPRODUCIBILITY — tags/manifests/hashes/commands (Part S). Static.
09 LIMITATIONS — consolidated P3/P8 limitations. Static.

## Static-vs-API decision

BUILD-TIME STATIC checked-in data for everything on /models and
/about: all numbers are frozen evidence (M9 artifact, E3 snapshot,
manifests). Rationale: immutable, small (KBs), zero new attack
surface, provenance recorded per section (artifact path + SHA).
READ FROM EXISTING ARTIFACT at build time via a documented derivation
script (P9-1) that copies values verbatim — no new read-only API, no
dynamic recomputation, no database. Exception: none identified; if a
future phase needs live cache stats, revisit then.

## Portfolio credibility audit

Demonstrated honestly: temporal evaluation (D1–D3 + holdout diagram),
probabilistic metrics (log-loss-led), calibration awareness (M8,
ECE), feature engineering (84 families), leakage prevention (bounded
claim + audits), simulation/strategy semantics (separated),
reproducibility (tags/hashes), testing (suite inventory),
integration (nav + API error maps). Oversell risks flagged:
comparison table (mitigate: dev-only caption, no holdout mixing);
ROC 0.98 (mitigate: pair with PR-AUC + prevalence note); top-1 79.6%
(mitigate: "synchronized, 24-race holdout" qualifier); permutation
chart (mitigate: permanent in-sample banner); latency (mitigate:
three labeled numbers, no single claim); "production" (mitigate:
"frozen research artifact serving locally", no scale claims).

## What not to build

Live/retraining playground; new 2025 evaluation or any holdout
touching; dynamic importance recomputation; SHAP; LLM-generated
explanations; MLOps/drift dashboards; live telemetry; metrics DB;
WebSocket status; composite model score; accuracy-led headlines;
cross-protocol leaderboards; causal language; normalized "win
shares"; any new API for frozen numbers.

## Proposed Phase-9 stages

- P9-1 — frozen evidence contract/data: build-time derivation script
  + checked-in JSON (verbatim M9/E3/manifest values + provenance) +
  schema test. Files: `scripts/`, `frontend/lib/`, `tests/`. Risk:
  transcription error (mitigate: byte-compare test vs artifacts).
- P9-2 — /models implementation: 8 sections per IA, existing design
  system. Files: `frontend/app/models/`, components. Risk: language
  oversell (mitigate: forbidden-language test mirroring E7 Part P).
- P9-3 — /about implementation: 9 sections per IA + nav entries.
  Files: `frontend/app/about/`, `CommandBar`. Risk: conflating the
  four semantics (mitigate: review against Part O).
- P9-4 — integration/responsive/a11y: nav, 6-width pass, keyboard/
  ARIA, `tsc`/`eslint`/`next build`. Risk: low.
- P9-5 — validation + freeze: targeted gate, freeze report/manifest,
  commit + tag. Risk: none scientific (product-only).

## Known evidence gaps

1. No head-to-head inference-latency benchmark across families
   (cannot claim speed superiority — state throughput only).
2. Inter-fold variance is high on some metrics (e.g. D2 vs D1 log
   loss) — show per-fold columns, not means alone.
3. M7 per-fold selections split (D1→0.003, D2→0.01, D3→0.03); global rule transparently
   documented — surface it, don't hide it.
4. E3 artifact is gitignored: /models must embed a provenance-stamped
   static snapshot, not read the artifact at runtime.
5. RECENT_PACE baseline is N/A (documented, not hidden).

## P9-1 entry gate

- [x] production model identity verified (§Production model identity)
- [x] frozen holdout metrics sourced (§Holdout evidence)
- [x] no holdout recomputation performed (read-only; artifact SHA
  untouched)
- [x] metric definitions verified (§Metric semantics)
- [x] temporal evaluation protocol verified (actual D1–D3, §Temporal)
- [x] actual candidate models inventoried (§Candidate models)
- [x] model-selection evidence separated from inference
  (§Model-selection evidence, three claims)
- [x] calibration evidence inventoried (§Calibration evidence)
- [x] stage evidence classified development vs holdout (§Stage)
- [x] ALL_84 family evidence verified (§Feature evidence)
- [x] E3 evidence limitations preserved (§Explainability evidence)
- [x] temporal-safety claims bounded (§Temporal-safety evidence)
- [x] real performance evidence classified correctly (§Performance)
- [x] /models architecture supported by evidence (§/models IA)
- [x] implemented system capabilities inventoried (§Capability inv.)
- [x] prediction/simulation/strategy semantics separated (§Semantics)
- [x] dataset statistics verified (§Dataset evidence)
- [x] reproducibility claims verified (§Reproducibility evidence)
- [x] /about architecture supported by evidence (§Architecture)
- [x] static-vs-API decision justified (§Static-vs-API decision)
- [x] overselling risks documented (§Portfolio credibility audit)
- [x] implementation stages proposed (§Proposed Phase-9 stages)
- [x] no scientific code modified (only this audit doc created)
- [x] no 2025 reevaluation (frozen artifact read only)
- [x] nothing staged/committed/tagged (verify below)
