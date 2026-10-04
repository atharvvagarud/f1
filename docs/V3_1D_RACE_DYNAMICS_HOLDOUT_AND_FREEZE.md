# V3.1D RACE DYNAMICS SEALED HOLDOUT + FREEZE

## Final verdict

V3.1D COMPLETE — V3.1 FROZEN — READY FOR V3.2. Scientific verdict: **KEEP**.

## Frozen inputs

- Baseline recovery point: phase12-spatial-replay `e99a78f8`.
- Contract v3.1a-v2, SHA `abd5300816d79270b1cd5b9b4952ebe447817f770eeddd2c598d0f07fbd5a0a4`.
- Dynamics sidecar logical SHA `40ef05809e2932d725785a0e991bcecede8d884f2388affec3f56147611696a1` (189,420 rows).
- Phase-2 content `d2ee966c…`, parquet `b0f17b66…`; ALL_84 = 84, CORE = 26, combined = 110.
- V3.1C recommendation ADVANCE_CORE_TO_V3_1D (deltas −0.00294/−0.00348/−0.00288).
- All identities verified exact BEFORE 2025 was opened; any mismatch would have stopped the run.

## Files changed

- `raceintel/model_lab/v3_dynamics_experiment.py` (+V3.1D: FINAL_FIT/holdout materialization, preregistration builder, one-shot runner, pure acceptance-policy function).
- `scripts/run_v3_1d_holdout.py` (new: ordered one-shot pipeline).
- `tests/test_v3_1d_holdout.py` (new: 11 source-safe governance tests).
- `scripts/run_ci_tests.py` (collection pin 3485 → 3496).
- `results/v3/v3_1d_preregistration.json`, `results/v3/v3_1d_holdout_opening.json`,
  `results/v3/v3_1d_race_dynamics_holdout_and_freeze.json`, `results/v3/v3_1d_model_card.json` (new, tracked).
- Ignored generated: `data/v3/v3_1d/` (A/B prediction parquets, final Arm B model artifact).

## Repository safety

HEAD = phase12-spatial-replay = `e99a78f8` at entry. Accumulated V3 work intact, nothing reset.
Nothing staged/committed/tagged/pushed until the Part AM freeze at the end.

## Preregistration

Persisted at `results/v3/v3_1d_preregistration.json` BEFORE any 2025 prediction existed
(identity `b51ad595457062072890344025602d68929713a158e6855b6d8910b352d46e23`).
Pins task/target/eligibility, arm feature sets + exact order (84 / 110, VARIANT_A explicitly
unauthorized), contract + dataset identities, 2018–2024 train / 2025 holdout, frozen
preprocessing, LogReg C=0.01 spec, seed 42, RAW INDEPENDENT_BINARY semantics, metrics,
race-macro aggregation, phase2-thirds stages, paired-race bootstrap (seed 42, B=2000, 95%),
six-clause acceptance policy, five watch-items, RAW-only calibration. Contains zero holdout results.

## Holdout opening

`results/v3/v3_1d_holdout_opening.json`: holdout_season 2025, preregistration identity,
contract/dataset identities, code commit, one_shot true. No wall-clock timestamp (deterministic records).

## FINAL_FIT

Arm A (ALL_84) and Arm B (ALL_84 + 26 CORE) each fit once on 2018–2024 (162,728 eligible,
149 races, 8,926 positives) with TRAIN-only preprocessing (median/mode imputation,
StandardScaler, one-hot; statistics never see 2025). Transformed dims 106 / 132.
Count anchors match frozen FINAL_FIT_EXPECTED exactly.

## Holdout population

2025 resolved through the canonical sealed path (explicit opt-in): 26,692 rows / 24 races /
1,444 positives — matching HOLDOUT_EXPECTED exactly. A/B populations bit-identical
(26,692 eligible rows each). Dynamics NaN removed zero rows.

## Arm A fidelity

Arm A reproduces the frozen FINAL_FIT 2025 baseline within 1e-9 on every Part J metric
(worst abs diff 3.6e-11; per-race LL maps bit-identical, worst 0.0):
LL 0.0680353741, Brier 0.0200141490, ROC 0.9845256886, PR 0.8032379039,
ECE 0.0111081578, Top-1 0.7960622539, Top-3 0.9789986874. No stored M9 prediction
vector exists (M9 persists metrics, not vectors), so fidelity rests on metric +
per-race-map identity — recorded as such.

## Arm A 2025

Race-macro LL 0.0680353741; Brier 0.0200141490; ROC 0.9845256886; PR 0.8032379039;
ECE 0.0111081578; Top-1 0.7960622539 (26,665 states); Top-3 0.9789986874.
Stages: EARLY 0.077468 / MID 0.069800 / LATE 0.056847.

## Arm B 2025

Race-macro LL **0.0634166678**; Brier 0.0185816028; ROC 0.9858633052; PR 0.8253047499;
ECE 0.0093922689; Top-1 0.7941496344; Top-3 0.9848490531.
Stages: EARLY 0.074930 / MID 0.064117 / LATE 0.051294.

## Primary metric

DELTA_LL = LL_B − LL_A = **−0.004619** (B better). Primary V3.1 holdout result.

## Secondary metrics

Brier −0.001433 (better), ROC +0.001338 (better), PR +0.022067 (better). No secondary
overrides the primary; none needs to — all agree.

## Calibration

ECE A 0.011108 → B 0.009392 (delta −0.001716, improves). RAW only; nothing fitted, no transform.

## Top-k

Synchronized adapter, eligible denominator, independent binaries never normalized.
Top-1: 0.79606 → 0.79415 (−0.00191, product-metric wobble, not an acceptance clause).
Top-3: 0.97899 → 0.98485 (+0.00585). Reported honestly; no selection on top-k.

## Stage analysis

Frozen phase2-thirds. EARLY −0.002538, MID −0.005683, LATE −0.005553 — all improve.
The predeclared D3-EARLY (+0.0021) watch-item is explicitly compared below.

## Per-race paired analysis

24 races, race-macro LL each arm (full table in machine record §per_race):
19 improved (79.2%), 5 worsened (20.8%); mean delta −0.004619, median −0.004809.
Race remains the statistical unit throughout; states never bootstrapped or pooled for inference.

## Bootstrap

Preregistered paired race bootstrap (seed 42, B=2000, 95% percentile CI on mean LL_B−LL_A):
CI **[−0.007148, −0.002158]** — entirely negative. Method unchanged after seeing results.

## D1/D2/D3/2025 consistency

Deltas B−A: D1 −0.002939, D2 −0.003481, D3 −0.002880, 2025 −0.004619 → **4/4 improvement**
with the largest magnitude on the untouched holdout. No pooling of state rows.

## EARLY watch-item

D1 −0.001427 / D2 −0.000524 improved, D3 +0.002126 regressed. 2025 EARLY: **−0.002538**
with EARLY-only paired CI [−0.005648, +0.000547] (spans zero, consistent direction).
No consistent cross-evidence regression; paired CI not bad-directional → **RESOLVED**
(assessment PASS under the frozen veto rule).

## History-depth watch-item

Same predeclared bins on 2025: full (23,444 states) −0.005659; medium (1,842) +0.001530;
thin (1,406) +0.007237. Thin/medium regression persists descriptively but 87.7% of
holdout states sit in the improving full bin. Diagnostic only — no features modified,
no selection; recorded as a known limitation, not a verdict-changer (no depth clause
exists in the frozen policy).

## Neutralisation watch-item

2025 predefined subgroups: green −0.004450 (23,306), pit-transition −0.007879 (1,625),
neutralised −0.001278 (2,250). The V3.1C D1 neutralised degradation does NOT generalize —
all three 2025 subgroups improve. Masking unchanged.

## Follower correction validation

2025 coverage (structural only, no ablation): last_seconds 73.74%, last_age 73.74%,
slope_l5 52.92%, lap_diff 81.93% — matching V3.1B expectations. No alternative follower
contract compared.

## Coefficient stability

FINAL_FIT Arm B dynamics signs vs D1–D3 majority: 14/26 agree. Ranks move (expected:
2–3× more training data, collinear trajectory family). Descriptive only; 2025 used for
zero selection and zero post-holdout changes.

## Acceptance-policy decision

Frozen six clauses on 2025 (+D1–D3 consistency):
1. PRIMARY: −0.004619 → pass. 2. PAIRED: CI entirely negative → strong.
3. TEMPORAL: 4/4 → pass. 4. SECONDARIES: Brier/ROC/PR all improve → pass.
5. CALIBRATION: ECE improves → pass. 6. STAGE/COMPLEXITY: veto PASS, +26 features
for consistent gains → pass. Verdict: **KEEP**, limitations: none.

## V3.1 verdict

**KEEP** — CORE demonstrates convincing generalization (4/4 temporal direction, strong
paired evidence, all secondaries, better calibration, all stages) with no material
unresolved limitation. Residual notes (thin/medium-bin descriptives, Top-1 product
wobble) are documented limitations, not acceptance failures.

## Serving decision

**ELIGIBLE_FOR_FUTURE_SERVING_PROMOTION**. Actual promotion is a separate explicit stage
(artifact contract, API/replay compatibility, latency, fallback, regression, deployment
evidence). Frozen serving artifact `1116b34f…` verified byte-unchanged (SHA rechecked
post-run).

## Final artifact

`data/v3/v3_1d/final_model_arm_b.joblib` (SHA `9a1aac51…`; estimator + preprocessor +
feature order + provenance incl. contract/dynamics/prereg identities, 2018–2024 train,
C=0.01 spec). Research artifact only; frozen v2 serving model untouched. Model card:
`results/v3/v3_1d_model_card.json` (frozen v2 card unmodified).

## Scientific identities

6/6 exact without regeneration: serving `1116b34f…` (rechecked), phase-2 content
`d2ee966c…` + parquet `b0f17b66…` (parent gate inside the run), explainability
`bae84b61…`, replay `78a3c059…`, simulation r3-v1 through 2024 phase6-r3-empirical
(pinned, untouched). ALL_84 = 84 re-verified in-gate.

## Determinism

Post-persistence exact-spec rerun: prediction max-abs-diff 0.0 both arms, bootstrap
identical, verdict identical. Reproducibility verification, not a second trial.

## Tests

11 source-safe governance tests green (`tests/test_v3_1d_holdout.py`); collection pin
3485 → 3496; V3.1 suites + Model Lab suites + preflight-source + `make ci` per Part AI.

## Known limitations

Thin/medium history-bin descriptives persist (small-n, diagnostic); Top-1 product
wobble −0.0019 (not an acceptance metric); coefficient ranks drift vs folds
(descriptive); single 24-race holdout (CIs honest, not overstated).

## Freeze

One commit `feat(model): add causal race dynamics experiment` + annotated tag
`v3.1-race-dynamics` per Part AM (executed at the final gate only).

## V3.2 handoff

V3.2 = MONTE CARLO 2.0 (not started). Candidate simulation inputs: gap/pace trajectory
slopes, field-spread compression, traffic persistence, last-observed follower gap —
all per-driver descriptive histories. Firewall stands: independent binary winner
probabilities must never be naively averaged with mutually exclusive race-outcome
frequencies.

## Entry gate

All boxes checked (evidence above + `results/v3/v3_1d_race_dynamics_holdout_and_freeze.json`).
