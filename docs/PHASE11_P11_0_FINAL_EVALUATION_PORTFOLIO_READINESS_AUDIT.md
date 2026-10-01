# PHASE 11 P11-0 FINAL EVALUATION & PORTFOLIO READINESS AUDIT

Read-only audit. No code, test, README, Docker, CI, or science changes.
No benchmarks executed, no suites rerun, nothing staged/committed/tagged.
All numbers below cite their authoritative frozen source.

## Final verdict

P11-0 COMPLETE — READY FOR P11-1. The system is fully built and frozen;
what remains is disposition (12 stale pins), measurement (final
benchmark), evidence selection (demo race, visuals), and writing
(README + case study). No unresolved scientific contract blocks release.

## Frozen baseline

HEAD `3c069b529f568dd25ea4a8213a6579afad631c0e`, tag
`v2-productionization-phase10` pointing at HEAD. Graphify updated, no
topology changes.

## Repository safety

`git status --short`: 11 worktree deletions + 3 modifications
(`AGENTS.md`, `GEMINI.md`, `opencode.json`) + 5 untracked
(`.impeccable/`, `.opencode/`, root `package.json`/`package-lock.json`)
= PREEXISTING_OTHER_WORK only. Nothing staged. Untouched.

## Authoritative evidence reviewed

Phase reports/manifests inventoried (88 docs): Phase 1
(`PHASE1_EXIT_REPORT.md`, `DATASET_V2_REPORT.md`,
`DATA_PLATFORM_ARCHITECTURE.md`); Phase 2 (`PHASE2_FINAL_REPORT.md`,
`PHASE2_CANONICAL_MATRIX.md`, `PHASE2_TEMPORAL_SEMANTICS.md`,
`PHASE2_LEAKAGE_PARITY_AUDIT.md`, `generated/phase2_freeze_manifest.json`);
Phase 3 (`MODEL_LAB_FINAL_REPORT.md`, `MODEL_LAB_FINAL_MODEL_CARD.md`,
`MODEL_LAB_CALIBRATION/TUNING/BASELINE/NONLINEAR/BAGGED_TREES_REPORT.md`,
`MODEL_LAB_P31_HANDOFF_REPORT.md`, `MODEL_LAB_FREEZE_MANIFEST.json`);
Phase 4 (`PHASE4_FINAL_REPORT.md`, `PHASE4_R6_HARDENING_REPORT.md`,
`PHASE4_FREEZE_MANIFEST.json`, `PHASE4_V2_API_CONTRACT.json`);
Phase 5 (`PHASE5_FINAL_REPORT.md`, `PHASE5_FREEZE_MANIFEST.json`,
`PHASE5_REPLAY_API_CONTRACT.json`); Phase 6
(`PHASE6_VALIDATION_REPORT.md`, `PHASE6_FINAL_REPORT.md`,
`PHASE6_FREEZE_MANIFEST.json`); Frontend Foundation
(`FRONTEND_FOUNDATION_FREEZE_REPORT.md`, `FRONTEND_DESIGN_SYSTEM.md`);
Phase 7 (`PHASE7_STRATEGY_FINAL_REPORT.md`, S3–S7 reports,
`PHASE7_STRATEGY_FREEZE_MANIFEST.json`); Phase 8 (E1–E7 reports,
`PHASE8_FINAL_FREEZE_REPORT.md`); Phase 9
(`PHASE9_FINAL_FREEZE_REPORT.md`, P9-0–P9-4); Phase 10 (P10-0–P10-5,
P10-4R). Plus `PRODUCT.md`, `frontend/data/about.v1.json`,
`frontend/data/models.v1.json`, `docs/adr/`.

## Current product inventory

Six surfaces, all routes verified live in code:

- PREDICT `/`: V1 `POST /predict/ensemble|/single-model`; V2
  `GET /v2/races|/states|/state`, `POST /v2/predictions/winner-snapshot`
  (`api/v2_routes.py:81-127`). Per-driver independent-binary
  probabilities. Limits: 2018–2024, never normalized, ~12 s full-field.
- REPLAY `/replay`: `GET /v2/races/{id}/replay/timeline|frames|predictions|probability-timeline`
  (`api/v2_replay_routes.py`). Exact RaceState + HIT-only cached
  checkpoints (149 races / 9644). Limits: checkpoints only, 2025 unserved.
- SIMULATE `/simulator`: `POST /v2/simulations/race`
  (`api/v2_simulation_routes.py:69`). Outcome frequencies (1k/10k).
  Limits: dry/clear only, no DNF/SC/VSC/weather/traffic.
- STRATEGY `/strategy`: `POST /v2/strategies/compare`
  (`api/v2_strategy_routes.py:76`). Baseline vs ≤9 candidates, paired
  deltas + sampling CIs. Limit: never a recommendation (enforced).
- MODELS `/models`: static validated dossier (11 sections, no fetch).
  Limits: in-sample permutation, one-season holdout, RAW uncalibrated.
- ABOUT `/about`: static technical dossier (12 sections, contract v1).

Do not advertise: live feeds, calibration, MLOps, optimizer, live APIs.

## Architecture inventory

Data: Tier-B (76 seasons, 1149 races) + Tier-A FastF1 (2018–2025, 173
sessions) → D6/D7/D9 lap-end states (189,420, delta 0) → Phase-2
F4–F11 → ALL_84 → F15 matrix 189,420×106 → M0–M9 → LogReg C=0.01 RAW
→ `serving.py` + serving joblib. Labels side-channel only.
Serving: RaceState → ALL_84 bridge → `predict_proba` → V2 API;
RaceState → MC engine → frequencies → CRN strategy compare;
Prediction → E2 cache → global/local/timeline explainability → Replay UI.
Shell: FastAPI + Next.js 16 + `runtime_artifacts/` bundle + two
containers + Compose (`/ready` gate) + three-tier CI.
Diagrams to create later: (a) end-to-end swimlane, (b) replay
HIT/404/503 sequence, (c) CRN pairing, (d) deployment, (e) semantics
legend. None created in P11-0.

## Semantic boundaries

Authoritative: `frontend/data/about.v1.json:293-336` (+ `not_to_confuse_with`).
PREDICTION = independent binary, never normalized (CLEAR in UI/API).
SIMULATION = mutually exclusive frequencies (CLEAR in code; verify
SimulatorView copy repeats frequency≠probability). STRATEGY = paired
counterfactuals, never best/optimal (CLEAR in code/tests; README header
lacks the qualifier; `PRODUCT.md` denies existence — STALE).
EXPLAINABILITY = associational log-odds, never causal, no SHAP (CLEAR in
evidence; spot-check Replay panels for causal verbs later).
Unclear surfaces: `README.md:33-44`, `PRODUCT.md:40-58`, timeline chart
legends (checkpoint-only label to verify).

## Dataset evidence

Tier-B: 76 seasons 1950–2025, 1149 races, 25,784 results, 3819
standings, 77 circuits, 879 drivers (`DATASET_V2_REPORT.md` P1).
Tier-A: 2018–2025, 173/173 sessions (171 COMPLETE; PARTIAL
2021-r12-R Belgium, 2022-r18-R Japan); 43 drivers, 16 constructors,
31 circuits; 173 races, 3458 results, 189,420 driver laps, 6336 pit
stops, 9324 stints, 25,779 weather, 14,992 race-control (P2).
Matrix: 189,420×106 (9 meta + 84 predictive + 7 labels + 1 companion +
5 masks); registry fp `a04d5475…`; content `d2ee966c…`, parquet
`b0f17b66…`; state prevalence winner 5.47% / podium 16.42% /
points 54.63%; stages EARLY 64,016 / MID 63,437 / LATE 61,967
(`PHASE2_CANONICAL_MATRIX.md`, `PHASE2_FINAL_REPORT.md`).

## Temporal-safety evidence

Exact-T LAP_END clock; latest-rival-≤T sync (same-lap future forbidden,
121 s dry spreads); 20-class adversarial suite (100 forbidden-mutation
cases bit-identical); label firewall (calculators take no label input);
2025 unlocked once (M9) then sealed (`ProtectedHoldoutAlreadyConsumed`);
expanding folds D1–D3, never random splits; R7.1 whole-state refusal
for stale rosters; replay exact checkpoints, no snapping
(`PHASE2_TEMPORAL_SEMANTICS.md`, `PHASE2_LEAKAGE_PARITY_AUDIT.md`,
P31 handoff, `PHASE6_VALIDATION_REPORT.md` §20).
Case-study facts (evidence-worded, max 6): exact-T + ≤T sync;
20-threat suite, no leakage detected; label firewall by construction;
one-shot 2025 then sealed; R7.1 refusal over stopped-car simulation;
chronological folds. Never claim "zero leakage guaranteed".

## Model evidence

LogReg C=0.01/lbfgs/iter1000, ALL_84 (106 transformed), train-fitted
median/scaler + mode-bool + one-hot pipeline; FINAL_FIT 2018–2024
(149 races, 162,728 states); 2025 one-shot holdout (24 races, 26,692).
2025 race-macro: log loss **0.068035**, Brier **0.020014**,
ROC-AUC 0.984526, PR-AUC 0.803238, ECE 0.011108, top-1 **0.7961**,
top-3 **0.9790**; stages EARLY 0.077468 / MID 0.069800 / LATE 0.056847.
Dev: M7 outer LL 0.071374; M8 RAW beats Platt/isotonic (kept RAW per
guards). Candidates beaten: XGB 0.109063, HGB 0.138305, ET 0.081475
(`MODEL_LAB_*` reports). README → top-1/top-3 + LL/Brier; case study →
add AUCs + ECE + stage split + dev→holdout delta; appendix → full
race-macro + pooled + folds + bins + fingerprints. Never lead with
ROC-AUC alone.

## Monte Carlo evidence

Contract v1 (`r4-engine`/`r5-mc`/`r6-pit`/`r3-v1` params, PCG64,
MONTE_CARLO_FREQUENCY). 42 states / 23 races (2020–2024; EARLY 23 /
MID 11 / LATE 8; 75 excluded with reasons). Race-macro R6:
LL 1.2237, Brier 0.02669, top-1 0.643, top-3 0.881, MAE 2.4452,
RPS 0.09280, ECE 0.01899 (beats R5-no-pit 2.225, leader 4.276).
Timings: 1k early 2.42 s / 10k early 24.59 s (all 10k ≤60 s);
prod memory ~170 MB. Limits: empirical params, constructor-shared
pace, free-air only, no DNF/SC/VSC/weather, over-pitting ~0.3–0.4,
coverage 42/23. Still needed: P11-owned production latency sign-off
(`PHASE10_P10_3` explicitly defers measured performance to P11).

## Strategy evidence

Actions STAY_OUT/PIT_NOW/PIT_NEXT_LAP; 9 canonical candidates;
compound changes identity only (no pace delta). CRN
`ADOPTED_WITH_LIMITATIONS` (stream identities, not trajectories;
median VR 0.702 S3 / 0.922 S6 — mixed, never universal). Estimand =
mean over complete valid pairs (405,000 pairs, 0 mismatches).
Bootstrap B=2000 95% sampling-only CIs
(`IMPROVEMENT/DEGRADATION/INCONCLUSIVE`). 3 objectives, no default,
no weighting, no recommendation. Validation: 99 anchors → 35
eligible; 83 red-team checks, 0 failures; F2 latency → S7 caps.
Claimable only with qualifiers: simulated counterfactuals, sampling
uncertainty, CRN limits, no traffic/pace-delta, single decision.
**Compares candidates; never outputs a universal best.**

## Replay evidence

149 races / 9644 checkpoints (64.72/race) / 162,639 frames;
189,610 observable + 3206 nulls (`NO_OBSERVATION_AT_SNAPSHOT`);
aggregate SHA `78a3c059…`; matrix reuse exact (3,764/3,764, diff 0.0);
~200–225× build speedup; 1e-12 tolerances everywhere (observed
≤7.1e-15); 2025 → 404 on all paths.
Demo race: **`2022-r01-R`** wins on frozen evidence (S3/S4/S5/S6
perez lap-30 anchors all bands + S7 latency ref + P10 smokes + E7
sample membership). Runner-up `2019-r01-R` (E7 membership only).
Pair with E7-documented replay trace (e.g. HAMILTON@2018-r01-R/f20)
for screenshot-identical explanation evidence; else SELECTION REQUIRED
in a later stage (confirm by live run, no generation in P11-0).

## Explainability evidence

E3: intercept −5.574…, log-odds math only, family partition STATE 23 /
PRIORS 13 / FIELD 12 / PACE 12 / ENV 9 / GAPS 8 / RATES 4 / INTER 3.
Permutation = **PRE_2025_FINAL_FIT_IN_SAMPLE** (no fold estimators
survive; retraining forbidden): baseline 0.072498; top
`gap_to_leader_seconds` 0.027004, `gap_to_ahead` 0.023535, `position`
0.013136. E4: exact logit decomposition (≤1e-12, observed ≤1.8e-15),
on-demand p50 ~20–24.5 ms, no cache. E5: `dz=Σdc`, intercept cancels,
invariant ≤3.9e-15 over 630 validations; p50 ~38–42 ms. SHAP
deliberately dropped (not installed; tests assert absence).
Case-study visuals: E3 Top-8 permutation table (with in-sample
caption); E4 top-5± panel; E5 change panel + timeline Δpp. Log-odds
rows only, never probability-points.

## Engineering evidence

Tier-1 Python: pins 3191/2466/725; clean `1956/501/4`, dev
`2457/4`, 0 failures (`P10-4R`, `P10-5`). Tier-1 Frontend:
`16/17` → 180/180 + tsc/lint/build/lockfile clean. P10 contracts:
142 passed (final explicit run). Docker: backend 2.86 GB/py3.11/UID
10001, frontend 553 MB/node22/UID 1000, read-only + tmpfs,
no mounts. Config/readiness (`/ready` all-ok, `lru_cache` 3.7→0.3 ms)/
observability (templated paths, 0 tracebacks)/bundle
(1939 files, `e4008425…`, ignored)/clean-env (negative proof + full
smoke) all green (`P10-5`, `P10-4`).

## Existing performance evidence

PORTFOLIO_READY: R6 builder 5.4–6.9× + parity 0.0; E1 cost breakdown
(11.8 s/ckpt, `predict_proba` 0.30%); E2 backfill 578.3 s, p95 5.14 s;
replay serving (cached 0.68 ms, frame p95 39.5 ms, timeline p95
2.75 ms); E7 TestClient p50/p95 (frame 28.9/30.1, E4 24.5/24.7, E5
41.8/41.9 ms); CI budgets (30 s + 5 min clean; 43 min dev).
INFORMATIVE_ONLY: E1 parallel micro (load-contaminated); readiness
sanity; MC/strategy smokes (N stated, single sample); full-field ~12 s;
startup ~2 s; frontend build. NEEDS_REMEASUREMENT: frontend<200 ms
(not measured); leader-lap helper; any MC/strategy latency claim.
No p99 anywhere in serving evidence. Final measured table = P11-owned
deferred item.

## Missing performance evidence

End-to-end production latency/throughput sign-off on the frozen
serving path (explicitly deferred by P10-3). No p99. No browser-engine
frontend timing.

## Final benchmark plan

Minimal suite (W warmup, N samples, `perf_counter`, pinned env
py3.11.15/node22/arm64, dev + container, p50/p95/p99):
winner-snapshot (2023-r01-R alonso lap28, W5/N50 + isolated bridge
span); replay HIT (frame 0, W5/N100); explanation (f0 verstappen,
W5/N50); timeline change (f20, W3/N50 + f1 404 control); MC
(2022-r01-R perez lap30, N_sims {10,100,1000}, W2/20 runs, engine +
HTTP spans); strategy (same anchor, {100,1000}, W2/10 runs);
readiness (cold restarts vs warm polls). Rules: no frontend<200 ms
claim without browser measurement; no p99 from N<100; request-duration
≠ inference-latency wording enforced. NOT executed in P11-0.

## Stale-test disposition

12 instances, 7 node-IDs (r71 node ×6 params). All are frozen-constant
drift after legitimate evolution — never behavior regressions; each
invariant is validated elsewhere (current manifests, live smokes):

1. `test_v2_phase4_freeze::test_frozen_module_hashes_match` →
   REPLACE_WITH_CURRENT_CONTRACT (retire Phase-4 hash gate).
2. `test_v2_phase5_freeze::test_freeze_manifest_file_hashes_match` →
   REPLACE_WITH_CURRENT_CONTRACT (narrow to still-frozen files).
3. `test_v2_phase5_freeze::..._generated_cache_not_required` →
   UPDATE_STALE_EXPECTATION (invert: cache-present when bundled).
4. `test_v2_phase5_freeze::..._documents_authorized_api_main_drift` →
   UPDATE_STALE_EXPECTATION (extend drift chain to P10-3).
5. `test_v2_phase5_r7::test_head_and_phase4_tag_intact` →
   UPDATE_STALE_EXPECTATION (re-pin 440f2a3 / v2-models-about-phase9).
6. `test_v2_phase6_r6::test_pit_disabled_reproduces_r5_result_identity` →
   UPDATE_STALE_EXPECTATION (re-baseline post-R6/R7.1).
7–12. `test_v2_phase6_r71::test_accepted_state_matches_pre_fix_result_identity[×6]` →
   UPDATE_STALE_EXPECTATION per param (regenerate post-fix identities);
   xfail-archaeology only if science owners insist (rename + strict-off).

No DELETE_REDUNDANT_TEST: every gate names a real invariant; only the
pinned constant is wrong. Disjoint from corpus debt (runner-enforced).

## Corpus-dependent test assessment

718 nodes / 31 reason groups = predominantly expected architecture
(ignored corpus cannot ship in git; P10-4 proved uniform
corpus-absence signatures, 0 true regressions) with a small avoidable
tail (missing skip guards: F14 `_HAS_D9`, fixture-time loads,
builder-CLI fail-closed; 1 frontend file-atomicity:
`evidence.test.ts` poisons 15 source-safe tests). Do NOT rewrite 718
tests. No canonical Tier-3 release command exists (`make science`
missing) — genuine P11 gap. Tier-1 must never be presented as Tier-3
coverage.

## Final validation matrix

A. SOURCE-SAFE: `make preflight-source`, `make ci-python`,
`make ci-frontend` (fresh clone, no bundle/corpus; ~30 s + ~5 min
clean). Block on any fail/pin-drift/lockfile-diff.
B. DEPLOYABLE: bundle validate → `make preflight` → compose build/up →
endpoint + workflow smoke + `docker inspect` posture → down
(arm64 + bundle). Block on preflight/SHA/smoke/posture/traceback.
C. FULL SCIENTIFIC: `pytest tests/ -q` undelected + `python -m v2.d11`
with corpus (~57 min). Block on anything outside the 12 stale pins;
stale pins → disposition, never silent deselect. Canonical command
to be created in P11-1.
D. PERF BENCHMARK: plan above (minutes). Block portfolio claims on
missing warmup/samples/env or mislabeled latency.
E. CASE-STUDY: fixed race walkthrough on Tier-2 (API↔UI bytes, 2025
firewall, semantics visible, 0 console errors). Block publish on
mismatch/leak/errors.

## Reproducibility audit

Path exists: py3.11 (`3.11.15` validated, preflight rejects 3.14) +
node22 + Docker/Compose + bundle create/validate + env vars + dev/prod
commands (`P10-1B`, `Makefile`). Gaps: README install/test section
superseded (old counts, `npm install`, bare pytest, no bundle/preflight
/Docker/tiers); bootstrap unlinked from README; `.python-version` vs
validated-vs-system unexplained; no Tier-3/benchmark command;
`compose.yaml` comment stale re observability ("out of scope until
later P10" — P10-3 already landed).

## README audit

GOOD: purpose, capabilities, architecture ASCII, replay, prediction,
model pointers, dataset, installation pins, dev commands,
reproducibility hashes. PARTIAL: Monte Carlo / strategy / explainability
(body missing or header-only), leakage (pointer only), runtime_artifacts
(buried), testing tiers (old counts), limitations (one defect only),
results (pointer only). MISSING: Docker/Compose section, repo tree,
screenshots/demo. STALE: `PRODUCT.md` (pre-Phase-7 denial vs shipped
strategy), Phase-6/7/8 body bullets, test counts (1540 vs 3191/180),
`node --test` instructions. No rewrite in P11-0.

## Recruiter two-minute audit

CLEAR: what it does, difficulty, stack, how-to-run (dev path).
BURIED: measured results (holdout only in model card /models page),
Docker path, technical decisions (ADRs, audits). TOO_DEEP: full
architecture (90+ docs). MISSING: screenshots/demo.

## Technical-interview audit

Inspectable: data contracts, leakage controls, model eval, sim
assumptions, strategy method, explainability, tests, deployment,
limitations (contracts + audits + manifests all present). Gaps: no
role-based docs-map (flat list only); bundle requirement invisible;
no single leakage START-HERE; no API-contract index page; unsupported-
reason catalog code-only; tier map undocumented; no changelog for
PRODUCT.md staleness.

## Visual asset audit

CURRENT: metric tables, freeze manifests, `about.v1.json` stats.
USEFUL but STALE: 7 `results/analysis/*.png` (V1 era — label or
regenerate). NOT_PORTFOLIO_READY: frontend boilerplate SVGs.
MISSING: all product screenshots, GIFs, videos, architecture diagrams.
Minimum set later: Predict hero + Replay timeline + Simulator
distribution + Strategy compare + Models holdout + About arch
screenshots; 30–60 s replay GIF; swimlane + semantics legend;
holdout table + calibration snapshot (RAW-retained note). None created.

## Claim audit

strategy-best/optimal/recommended: SUPPORTED-as-negative (forbidden by
design + tests). model-best: NEEDS_QUALIFICATION (tolerance rule,
frontend guards). calibrated: CONTEXT_DEPENDENT (RAW retained, ECE is
measurement). explainable: SUPPORTED with associational qualifier.
production-grade: NEEDS_QUALIFICATION (packaging yes, forecasting no).
real-time/live: UNSUPPORTED (no live infra; `about-page.test.ts`
forbids). zero-leakage: NEEDS_QUALIFICATION (evidence wording only).
accurate/AI-powered/SOTA: UNSUPPORTED (absent; tests forbid).
10,000: SUPPORTED as cap. Per-surface check of SimulatorView copy +
Replay explanation panels for causal verbs still open (flagged).

## V2/future-work boundary

Deferred (must not ship as v2): spatial replay, tyre/pace/pit/DNF/
overtaking/SC/VSC/weather models, MC 2.0, ensembles (V1-only),
strategy 2.0, pre-race intel, calibration/MLOps/Race-Engineer-AI,
telemetry (ADR-0001). Blurred: README header (Ph6/7/8 COMPLETE) vs
body + PRODUCT.md (omit/deny) — fix wording, not science.

## Portfolio metrics plan

Recommend 5 (all frozen, sourced): (1) **189,420** temporally-safe
race states, 84 features (`PHASE2_CANONICAL_MATRIX.md`); (2) **149**
historical races served, 2018–2024 (`PHASE5_FREEZE_MANIFEST.json`);
(3) 2025 holdout top-1 **0.796** / top-3 **0.979**
(`MODEL_LAB_FINAL_MODEL_CARD.md`); (4) holdout log loss **0.068** /
Brier **0.020** (same); (5) **9644** replay checkpoints, exact to
1e-12 (`PHASE8_E7_FINAL_VALIDATION_REPORT.md`); engineering spare:
2457 + 180 Tier-1 tests, fail-closed (`P10-5`). No fabricated values;
no ROC-AUC-led headline.

## Documentation source-of-truth map

dataset → `DATASET_V2_REPORT.md` + `generated/phase2_freeze_manifest.json`;
matrix → `PHASE2_CANONICAL_MATRIX.md`; temporal → `PHASE2_TEMPORAL_SEMANTICS.md` +
`PHASE2_LEAKAGE_PARITY_AUDIT.md`; model metrics → `MODEL_LAB_FINAL_MODEL_CARD.md` +
`MODEL_LAB_FINAL_REPORT.md`; replay → `PHASE5_FREEZE_MANIFEST.json` + E2/E7 reports;
simulation → `PHASE6_VALIDATION_REPORT.md` + `PHASE6_FREEZE_MANIFEST.json`;
strategy → `PHASE7_STRATEGY_FINAL_REPORT.md` + S3/S5/S6;
explainability → E3/E4/E5 reports; product → `PHASE9_FINAL_FREEZE_REPORT.md` +
`about.v1.json`/`models.v1.json`; productionization → `PHASE10_P10_5_*` + P10-4R;
CI contracts → `scripts/run_ci_tests.py` + `run_ci_frontend_tests.py`.
Rule for P11: never copy numbers from README/PRODUCT.md/old reports —
always from this map.

## Proposed Phase-11 roadmap

- P11-1 Test Debt + Release Validation Contract: dispose 12 stale pins
  per table; add `make science` (+ Tier-3 invocation doc); fix
  `compose.yaml` stale comment. Files: 7 test files, `Makefile`,
  docs note. Expensive: full `pytest` with corpus (~57 min) to confirm.
  Gate: Tier-3 green modulo documented expectations + pins updated.
- P11-2 Final Scientific + Engineering Validation: run matrix A–C
  (Tier-1 both, Tier-2 smoke, Tier-3 full) on frozen tree; record
  evidence. Expensive: ~1 h CI + smoke. Gate: all green, evidence logged.
- P11-3 Final Performance Benchmark: execute benchmark plan; publish
  table. Expensive: minutes + container time. Gate: p50/p95/p99 per row,
  wording rules enforced.
- P11-4 Case Study Evidence + Visual Assets: confirm 2022-r01-R
  (+ E7 replay trace), capture screenshots/GIF, build 5 diagrams,
  E3/E4/E5 tables. Expensive: manual capture. Gate: API↔UI byte match,
  semantics visible, 0 console errors.
- P11-5 README + Technical Case Study: rewrite README per hierarchy;
  write case study per outline; fix PRODUCT.md staleness or retire it.
  Gate: recruiter/investor read-through + claim audit re-run.
- P11-6 Final Release Audit: repeat P11-0 checks against new docs;
  verify source-of-truth compliance, link integrity, license/secret
  sweep. Gate: zero STALE/MISSING, entry-gate boxes ticked.
- P11-7 V2 Final Freeze: one commit + annotated tag. Gate: tag == HEAD,
  tree clean of release work.

## Time/cost estimate

P11-1 MEDIUM (test edits + 57-min validation). P11-2 MEDIUM-HIGH
(~1–2 h machine time, mostly unattended). P11-3 LOW-MEDIUM (minutes
runtime + table writing). P11-4 MEDIUM (manual screenshots/diagrams;
GIF tooling may need install). P11-5 MEDIUM-HIGH (writing-heavy).
P11-6 LOW (audit). P11-7 LOW (commit/tag). Do not buy speed by
weakening validation, dropping percentiles, or inventing numbers.

## Risks/blockers

1. Stale-pin edits touch frozen-era tests — wrong edits could mask real
   invariants; mitigate by per-instance review + full Tier-3 re-run.
2. `evidence.test.ts` file-atomicity poisons 15 source-safe frontend
   tests — small refactor needed for a fully honest Tier-1 story.
3. No Tier-3 canonical command — must be created, not assumed.
4. Screenshot/GIF capture needs a browser + running stack; container
   images exist, procedure is manual.
5. README rewrite risks reintroducing stale numbers — enforce
   source-of-truth map + claim re-audit in P11-6.
6. PRODUCT.md contradicts shipped product — decide fix-vs-retire in
   P11-5, do not leave contradictory.
7. Single-maintainer hardware (arm64 macOS, single-core-bound suite) —
   full validations take ~1 h; schedule, don't skip.

## P11-1 handoff

Start with the 12-row stale disposition table above + `make science`
contract. Inputs: this report, `scripts/run_ci_tests.py`,
`scripts/ci_corpus_dependent.txt`, P10-4R §Q-equivalent, the 7 test
files. First action: re-read the 7 nodes' current code context, apply
UPDATE/REPLACE per row, re-run Tier-3, record evidence. Do not bundle
README/benchmark/visual work into P11-1.

## Entry gate

- [x] frozen Phase-10 HEAD verified (`3c069b5`)
- [x] Phase-10 tag verified (`v2-productionization-phase10`)
- [x] nothing staged
- [x] remaining dirty state classified (PREEXISTING_OTHER_WORK only)
- [x] authoritative freeze reports reviewed (88 docs inventoried)
- [x] current README audited (GOOD/PARTIAL/MISSING/STALE per topic)
- [x] product inventory complete (6 surfaces, routes verified)
- [x] architecture inventory complete (flows + shell + diagram list)
- [x] FACT/PREDICTION/SIMULATION/STRATEGY boundaries audited
- [x] dataset numbers sourced (Tier-B/A + matrix + eligibility)
- [x] temporal-safety evidence inventoried (9 items + 6 case facts)
- [x] model metrics inventoried (holdout + stages + candidates + calibration)
- [x] MC metrics inventoried (42/23 + race-macro + timings + limits)
- [x] strategy evidence inventoried (actions/CRN/deltas/CI/objectives/83 checks)
- [x] replay evidence inventoried (149/9644/cache/speedup/tolerances + demo pick)
- [x] explainability evidence inventoried (E3/E4/E5 + SHAP rationale + visuals)
- [x] engineering evidence inventoried (tiers kept separate)
- [x] existing performance measurements classified (14 items)
- [x] missing benchmark evidence identified (prod sign-off, p99, browser timing)
- [x] final benchmark methodology proposed (7 ops, W/N/p50/p95/p99)
- [x] all 12 stale test instances individually dispositioned (table, no vague items)
- [x] corpus-dependent Tier-3 testing assessed (mixture + `make science` gap)
- [x] final validation matrix designed (A–E with commands/runtimes/blocks)
- [x] reproducibility gaps identified (5 items)
- [x] README gaps classified (21 topics)
- [x] recruiter two-minute audit complete
- [x] technical-interview audit complete (6 gaps)
- [x] visual assets inventoried (minimum set specified)
- [x] claim audit complete (10 claim families)
- [x] v2/future boundary audited (deferred list + blurred spots)
- [x] 4–6 portfolio metrics recommended (5 + spare)
- [x] documentation source-of-truth map created
- [x] remaining P11 stages proposed from evidence (P11-1–P11-7)
- [x] time/cost estimated (LOW→MEDIUM-HIGH per stage)
- [x] risks/blockers explicit (7 items)
- [x] only P11-0 report created (this file; unstaged)
- [x] nothing staged/committed/tagged
- [x] P11-1 handoff explicit
