# V3.2L CAUSAL DRIVER LIFECYCLE MODEL

## Final verdict

**V3.2L COMPLETE — LIFECYCLE MODEL REJECTED — READY FOR V3.2M**

## Why V3.2L exists

V3.2K rejected direct raw-state reconstruction and handed L a measured residual:
stale drivers whose last-known raw state is Stopped=True but not J-Retired. L asks
whether the simulator can model that lifecycle uncertainty (may resume / may be
terminal / downtime uncertain) and recover a material share of the 3294 STALE
checkpoints. Answer: the opportunity is material (3215 checkpoints) but the model
and mechanism are not admittable. Nothing was weakened for coverage.

## Frozen baseline

Tag `v3.1-race-dynamics` = HEAD `64c5af0`; V3.2A–K dirt only; nothing staged.

## V3.2K inherited evidence

3678/9644; STALE 3294 = RAW_SOURCE_STALE 2866 + LIFECYCLE_AMBIGUOUS 147 + MIXED 281;
7977 offender rows (5661 Stopped, 2067 Retired, ≤178 fresh). Row counts are not
coverage counts.

## Preregistration

`results/v3/v3_2l/preregistration.json`, SHA256 `4c3eb5c8…`, frozen before any
training-label construction. Season-forward folds, logistic-first, empirical
return-time tables, preregistered gates (calibration, return-state, finish,
materiality, multi-driver).

## STALE opportunity reconciliation

2866 vs 5661 reconciled: K's class is checkpoint-level (raw feed equally stale);
5661 is offender-level last-known-state evidence (latest Stopped=True). They
coexist — stale feed AND last-known stopped. No hard stopped-age boundary is
derivable (P(return|age) stays nonzero at all ages), so age is a model feature and
D9-staleness itself corroborates non-progression. STOPPED_TOO_OLD empty by
evidence, never by tuning.

Exclusive checkpoint decomposition (conserved 3294): LIFECYCLE_FULLY_ADDRESSABLE
1874, J_RETIRED_PLUS_LIFECYCLE 1341, LIFECYCLE_PARTIALLY_ADDRESSABLE 37,
NO_CAUSAL_STOP_SIGNAL 3, LAST_STATE_INSUFFICIENT 0, MULTIPLE_OFFENDER_MIXED 17,
OTHER_EXPLAINED 22. Offender classes: ADDRESSABLE 5661, J_RETIRED 2067,
STOPPED_CLEARED 249, NO_STOP_SIGNAL 0. Last-state anchors exist for every
addressable offender (0 insufficient — staleness is age, not missing fields).

## Lifecycle-state contract

STOPPED_UNRESOLVED_AT_T: causally known stopped/non-progressing, not J-Retired,
anchor sufficient. NOT retired/DNF/will-not-return. Stopped=False clearing is
unreliable (73/85 returns lack clearing) — never sticky-forever.

## Episode corpus

476 stopped episodes (2018–2024): CLEAN 211, PIT_CONTEXT 214, INITIAL_UNKNOWN 41,
LATE_SESSION 10, RED/NEUTRALISED 0. Labels (RETURNED 85 / TERMINAL) stored as `y_*`,
strictly separated from causal `x_*`. 40 True→False clearings; cleared→crossing
within 300 s only 19/40.

## Causal features

Elapsed stopped duration, stage/fraction, laps remaining, last position/lap/deficit,
pit state/count, causal tyre state, track at T, race-control ≤T, stop context,
pre-stop pace. No driver identity, no future labels; provenance per feature.

## Temporal evaluation

Folds train ≤2020→2021 (101/24), ≤2021→2022 (125/42), ≤2022→2023 (167/24),
≤2023→2024 (191/20). Race never crosses train/eval. 2025 forbidden.

## Terminal/return baselines

Global terminal 0.858 (constant log-loss ≈0.42); EARLY 0.819, MID 0.816, LATE 0.924.

## Terminal/return model

Logistic regression (numpy IRLS, L2, 7 features + intercept), P(RETURN|X at stop
start). Fold log-loss 0.48/0.15/0.44/0.22; ROC-AUC 0.92/0.96/0.62/0.42; Brier
0.14/0.04/0.12/0.05. Mixed vs baseline, unstable, once below chance.

## Calibration

Fold ECE 0.232/0.083/0.153/0.074 with reliability bins. Poor and unstable across
folds on eval N≤42. FAIL vs prereg gate; high terminal probability never made
deterministic (sigmoid+L2 by construction).

## Time-to-return model

30 returns only. Empirical downtime quantiles + conditional-on-age tables
(A=0/60/180/300/600 with inverse-CDF sampling rule that never returns before T).
Descriptive; predictive validation needs admitted scope. Thin data → return-state
gate FAIL.

## Stopped-age survival

P(eventual return|still stopped at A): 0.142 at 0 s → ~0.03–0.05 past 300 s, flat
~0.027 tail. Informative but low; supports age-conditioning, not a boundary.

## Last-known state sufficiency

Anchors complete for all 5661 addressable offenders. Sufficiency is not the
blocker — kernel hold/resume support is (see Return mechanism).

## Return mechanism

Design-only: hold (no progress) for sampled conditional downtime, resume anchor
with advanced clock, no teleports/gaps. BLOCKER: MC2 kernel reschedules every
active driver each event and ends at first finisher — hold/resume is a dynamics
change to frozen MC2-E science. NOT IMPLEMENTED.

## Terminal mechanism

Design-only: sampled-terminal = simulated-future non-progression, never retirement
at T. Same kernel-hold requirement.

## Finish classification

Current FinishOrder ranks the full roster by (−laps, race_time), retired=False
hardcoded — terminal unrepresentable. A defensible rule exists (distance rank +
explicit terminal flag, no result labels) but needs a results-contract extension +
revalidation. DEFINABLE-BUT-UNIMPLEMENTED.

## Concurrent stopped drivers

Multi-offender checkpoints common; crash-cluster dependence plausible and
unmodelled. Full multi-driver integration unsafe; preregistered scope would start
single-driver-only.

## RNG contract

Domains `mc2-lifecycle-terminal`, `mc2-lifecycle-return-time` reserved
(design-only); existing MC2-E streams untouched; zero draws consumed.

## Research simulator

NOT_RUN — B-arm not built (kernel + contract blockers); evaluation population
(3294) frozen for any future arm.

## Outcome validation

NOT_RUN — no B-arm; model-level validation in artifacts; V3.2E-style backtest
needs admitted integration.

## Winner/top-5 sanity firewall

Probabilistic by construction; short-return episodes exist; winner episodes listed;
historical continuation always permitted. PASS as non-determinism.

## Future poison

PASS by construction (50 probes): every feature provably ≤ stop start.

## Admission decision

REJECT_LIFECYCLE_MODEL: (1) poor unstable temporal calibration; (2) small training
population (211 CLEAN, 30 returns; 214 pit-context excluded); (3) return branch
needs frozen-science kernel change + finish contract extension; (4) concurrent
dependence unmodelled. Opportunity (3215) preserved as evidence; no gates weakened.

## Runtime integration

NOT_APPLICABLE. Priority order (canonical → J → L → refusal) stands unexercised.

## Coverage projection

FULLY 1874 → 5552/9644 (57.6%); +J+L 1341 → 6893/9644 (71.5%). STALE-primary checkpoints pass all earlier gates by construction
(contemporaneous check is last), so projection is exact under admission. NOT
realized — mechanism rejected.

## Coverage before / after

3678/9644 → 3678/9644. Gain +0.

## Coverage attribution

Empty; exact match.

## Coverage by stage / season / race

Identical (no integration).

## Remaining STALE

Count unchanged (3294); character completely renewed by L decomposition.

## Complexity / product value

Zero runtime lines admitted; no overhead; gain 0; value preserved as evidence +
pit-context lead (214 routine-stop episodes) for a future phase.

## Tests

27 L tests green; Tier-1 ledger 3760→3787.

## Scientific identities

L prereg `4c3eb5c8cdfe9ebf44555de540ee1378d0b12089d5c8cbc44dea7c0de6c48533`;
J corpus `8229a8606…`; K prereg `567260af…`; dry-green `7ae97c3c…`;
decision REJECT_LIFECYCLE_MODEL.

## Known limitations

Small-N folds; pit-context excluded from training; age-grid survival coarse (60 s);
return-time N=30; RED/NEUTRALISED stop regimes unobserved in D9 track snapshot;
labels assume D9-crossing = competitive return.

## V3.2M recommendation

Do not retry full lifecycle without (a) a kernel hold/resume science proposal or
(b) a pit-context-only restricted scope (214 routine episodes, near-certain return,
simpler mechanism). Otherwise recommend FINAL V3.2 validation/freeze at 3678/9644
with STALE characterized as measured.
