# V3.1C RACE DYNAMICS CONTROLLED TEMPORAL EXPERIMENT

## Final verdict

V3.1C COMPLETE — ADVANCE CORE TO V3_1D. Arm B (ALL_84 + CORE, same
frozen LogReg C=0.01 RAW) improves race-macro log loss on all three
development folds with 2/3 paired race-level CIs excluding zero in the
improving direction; all secondaries and calibration green; stage veto
PASS. No 2025 data touched.

## Frozen inputs

- Contract v3.1a-v2 `abd53008…0f07fbd5a0a4`; sidecar logical
  `40ef0580…611696a1` (189,420 rows, 26 CORE + 3 VARIANT).
- Phase-2 content `d2ee966c…`, parquet `b0f17b66…`; ALL_84 = 84;
  combined = 110. All verified pre-run (fail-closed).

## Files changed

- `raceintel/model_lab/v3_dynamics_experiment.py` (new harness; reuses
  splits/task/preprocessing/estimator/metrics/stages/calibration/top-k/
  experiment-identity; defines nothing twice).
- `scripts/run_v3_1c_experiment.py` (new runner: fidelity gate → A/B/C
  → analyses → artifacts).
- `tests/test_v3_1c_experiment.py` (9 source-safe unit tests),
  `tests/test_v3_1c_corpus.py` (4 Tier-3 corpus tests, manifest-pinned).
- `scripts/ci_corpus_dependent.txt` (+4 pins), `scripts/run_ci_tests.py`
  (3471 → 3484 collection pin).
- `results/v3/v3_1c/v3_1c_summary.json` (tracked run record),
  `results/v3/v3_1c_race_dynamics_controlled_experiment.json` (tracked
  machine record); prediction parquets under ignored `data/v3/v3_1c/`.

## Repository safety

HEAD = phase12-spatial-replay = `e99a78f8`. All V3 work intact;
nothing staged/committed/tagged/pushed.

## Graphify

`graphify update .` at entry and exit; navigation via model_lab
communities (splits, preprocessing, logreg, metrics, winner, results).
Direction: frozen matrix + V3.1 sidecar → experiment harness →
existing Model Lab → predictions/evaluation. No reverse dependencies,
no API/frontend/spatial/simulation/strategy coupling.

## Experiment architecture

`load_joined_frame` verifies all identities then 1:1-joins the sidecar
onto the frozen matrix (189,420 × 135; augmented manifest carries
84 + 26 predictive columns). `materialize_v3` mirrors
`splits.materialize` (mask-first, M0 audit, X/y + identity) with
explicit V3 names since the registry only knows the frozen 84.
`run_v3_arm` fits preprocessing TRAIN-only, fits
`TC.build_estimator(logistic_regression, {C: 0.01})`, emits typed
INDEPENDENT_BINARY predictions, and evaluates through the canonical
runner chain. Manifests reuse `EX.build_config` identity. Bootstrap is
paired race resampling (seed 42, B=2000, 95% CI).

## Feature sets

ALL_84 (84, canonical order), V3_1_DYNAMICS_CORE (26, contract order),
ALL_84_PLUS_V3_1_DYNAMICS_CORE (110 = 84 ++ 26, disjoint, deterministic).
VARIANT_A never resolved as an arm.

## Missingness / preprocessing

Frozen pipeline unchanged: numerics median+StandardScaler,
booleans most-frequent unscaled, categoricals MISSING+one-hot, fit on
TRAIN only. Mechanical routing: float64/Int64 → numeric via
`to_numeric`, pandas `boolean` → boolean block; NaN preserved into
train-fitted imputation (pinned by unit test). No zero-fill, no global
imputation, no new scaler/encoder. Transformed dims: A 106, B 132,
C 26.

## Model specification

LogisticRegression C=0.01, l2, lbfgs, max_iter=1000, class_weight=None,
random_state=42, RAW positive-class probabilities, all arms/folds. No
tuning of any kind.

## Split contract

D1 2018–2021/2022 (88,123/23,577 eligible), D2 2018–2022/2023
(111,700/24,422), D3 2018–2023/2024 (136,122/26,606) via
`resolve_development_fold`. 2025 absent from every partition
(asserted per fold; prediction seasons exactly {2022, 2023, 2024}).

## Holdout firewall

Folds resolve only through development-only resolvers (HOLDOUT/2025
raise, no opt-in) plus explicit `assert_no_holdout_request`
(D1/D2/D3 pass; 2025/HOLDOUT/FINAL_FIT raise — unit-tested). 2025
output scan: prediction artifacts contain seasons 2022–2024 only; the
only "2025" strings in V3.1C outputs are firewall/policy text.

## Arm A reproduction

Two-tier gate, both green. (1) Fidelity: harness at M7 per-fold C
values (D1 0.003, D2 0.01, D3 0.03) reproduces stored M7 outer metric
nodes — LL/Brier/ROC/PR race-macro values, full per-race LL maps, ECE,
top-1/top-3 — with worst abs diff 0.0 (bit-exact, all 3 folds).
(2) C=0.01 path: D2 fidelity ran at C=0.01 exactly; no stored C=0.01
full-train prediction vectors exist anywhere (verified: predictions are
in-memory only in every Model Lab runner), so prediction-level identity
rests on the in-harness bit-exact rerun (max abs diff 0.0) plus exact
per-race-map agreement. M8 RAW values are not a valid baseline (M8 base
fits train-minus-last-season). B/C interpreted only after this gate.

## Population equality

A/B/C eligible state sets bit-identical per fold (state_id-hash
equality; 23,577 / 24,422 / 26,606). Dynamics NaN drops no rows
(median/mode imputation inside the frozen pipeline).

## Arm A results

Race-macro LL: D1 0.083615, D2 0.042917, D3 0.082916. Brier
0.024783/0.010951/0.024548. ROC 0.9731/0.9949/0.9713. PR
0.7159/0.9183/0.7714. ECE 0.01143/0.01280/0.01278. Top-1
0.6494/0.9050/0.7519. Top-3 0.9651/0.9977/0.8822.

## Arm B results

Race-macro LL: D1 0.080675, D2 0.039436, D3 0.080036. Brier
0.023980/0.010003/0.022852. ROC 0.9748/0.9956/0.9723. PR
0.7311/0.9265/0.7759. ECE 0.00789/0.01146/0.01278. Top-1
0.6720/0.9131/0.7546. Top-3 0.9633/0.9978/0.8877.

## Arm C results

Race-macro LL: D1 0.120429, D2 0.093575, D3 0.108725 (diagnostic;
not expected to beat A/B). Standalone signal moderate: ROC
0.9233/0.9523/0.9231, PR up to 0.7859. Poor C performance is not
evidence against incremental usefulness in B.

## Primary metric comparison

Deltas B−A: D1 −0.002939, D2 −0.003481, D3 −0.002880 (mean −0.0031).
Per-race table (fold/race/A/B/delta) embedded in arm results
(per_race_log_loss maps); race is the statistical unit throughout.

## Secondary metrics

Brier, ROC-AUC, PR-AUC all improve on all folds (no AUC-without-LL
victory claimed; LL improves too).

## Calibration

ECE RAW-only: D1 0.01143→0.00789, D2 0.01280→0.01146, D3
0.01278→0.01278. No degradation anywhere; no transform fitted.

## Top-k

Synchronized adapter, eligible denominator, independent binaries never
normalized. Top-1: +0.0226/+0.0081/+0.0027. Top-3: −0.0018/+0.0001/
+0.0055 (reported, not selected on).

## Stage analysis

MID/LATE improve on every fold (−0.0040 to −0.0060). EARLY: D1
−0.0014, D2 −0.0005, D3 +0.0021 (single-fold wobble, ~2% of base).

## Per-race paired comparison

Paired race LL deltas: D1 mean −0.00294/median −0.00342 (77% improved),
D2 −0.00348/−0.00337 (82%), D3 −0.00288/−0.00240 (71%).

## Bootstrap

Paired race resampling, seed 42, B=2000, 95% percentile CI on
mean(LL_B − LL_A): D1 [−0.005248, −0.000581] (excludes 0, negative),
D2 [−0.005192, −0.001924] (excludes 0, negative), D3 [−0.006812,
+0.001764] (spans 0, consistent direction). Deterministic (identity
re-verified).

## Fold consistency

3/3 improvement with magnitudes −0.0029/−0.0035/−0.0029. No adverse
fold hidden.

## Stage veto

PASS. Rule requires consistent cross-fold EARLY regression AND paired
CI excluding zero in the bad direction. Observed: 2/3 EARLY improve;
D3 +0.0021 alone against larger MID/LATE gains and an overall fold gain.
D3-EARLY is a V3.1D watch-item.

## Missingness subgroup diagnostics

D1 depth bins (predeclared): full (n=20,583) Δ −0.0041; medium
(n=1,702) Δ +0.0024; thin (n=1,292) Δ +0.0077. Thin states have higher
base LL under both arms. Diagnostic only; no selection, no contract
change proposed.

## Pit / neutralisation diagnostics

D1 factual subgroups: green Δ −0.0044 (n=19,624), pit-transition Δ
−0.0057 (n=1,650), neutralised Δ +0.0067 (n=2,750). Diagnostic only.

## Follower correction diagnostics

D1 coverage: level/age 69.9%, slope 45.8%, lap-diff 79.8%. Post-fit:
all follower features present with finite transformed variance every
fold; signs consistent 3/3 (age −, slope +, lap-diff −; level small,
D3 sign differs at |coef| ≤ 0.014). Non-selective; contract stays
CORE-frozen.

## Coefficient diagnostics

Model-space coefs, Arm B: no zero-variance inputs in any fold (no
constant/never-observed/pathological feature — structural gate
passed). Dynamics ranks span #6–#129; top-5 every fold are frozen
features (gap_to_leader_seconds #1). Small coefs noted, never
selected on.

## Variant-A governance

VARIANT_A NOT run. V3.1A authorizes it only under predeclared
promotion evidence; no mechanical trigger was predeclared, so no
authorization can be claimed after seeing CORE results. 2025 stays
locked regardless.

## Acceptance-policy application

Six clauses on D1–D3: (1) primary 3/3 negative; (2) D1/D2 CIs exclude
zero, D3 consistent-but-wide; (3) 3/3 consistency; (4) secondaries
improve everywhere; (5) ECE improves-or-equal everywhere; (6) veto
PASS, +31% features for consistent gain. Verdict: ADVANCE.

## V3.1C recommendation

ADVANCE_CORE_TO_V3_1D. Watch-items for V3.1D: D3 CI width, D3-EARLY
wobble. The holdout must still be consumed exactly once, by V3.1D.

## Determinism

Arm B D1 rerun: max abs prediction diff 0.0. Bootstrap identity
re-verified. Fidelity worst diff 0.0. Seeds fixed (42 everywhere).

## Performance

Per arm/fold timings in machine record (materialize ~0.1 s, fit
~1 s, top-k ~8 s, total ~10–20 s; full 12-gate + 9-arm run ≈ 6 min).
Engineering evidence only.

## Predictive firewall

ALL_84 = 84 re-verified; no `dyn_` inside; combined sets separate. No
model trained outside arms; no predictions outside D1–D3; no 2025
anything; no frozen artifact regenerated.

## Scientific identities

6/6 exact without regeneration (serving preflight, phase-2 pair
build-verified, explainability/replay/simulation pinned in untouched
files; full suite green).

## Tests

10 unit (source-safe, green) + 4 corpus (Tier-3, manifest-pinned).
Collection pin 3471 → 3485 (10 unit + 4 corpus). `make ci` green
(python 2744 passed; frontend tests/tsc/lint/build green).

## Known limitations

No stored C=0.01 full-train vectors (documented substitution); D3 CI
wide; single-season stages; M8 RAW not comparable; thin-bin small-n.
Incidental: full-suite runs exposed a pre-existing `id()`-reuse flake
in `test_estimator_fresh_per_c_and_only_c_varies` (failed once under
suite memory pressure, passes alone); fixed minimally by holding built
estimators alive for the test duration — freshness guard semantics
unchanged (a reused object would still show duplicate ids). M0/M1
source-scan guards extended per the repo's stage-ownership convention
(V3 module added to owned sets; stricter V3 successor guard owned by
`test_v3_1c_experiment.py`).

## V3.1D handoff

Frozen CORE + C=0.01 RAW; FINAL_FIT 2018–2024; one-shot 2025;
predeclared acceptance (V3.1A six clauses); watch D3-EARLY;
VARIANT_A still unauthorized; no post-holdout tuning.

## Entry gate

All boxes checked (evidence above + machine record).
