# V3.7D HISTORICAL EVALUATION + EMPIRICAL GATE

## Final verdict

V3.7D COMPLETE — REFINEMENT NOT WARRANTED — READY FOR V3.7F

## Frozen parent

V3.6 `v3.6-strategy-2.0` (`1eb46263…`). D is evaluation-only: V3.7A/B
contracts, V3.7C engine, MC2 seam, V3.6, API, frontend, cache untouched.

## A/B/C provenance

- A `v3.7a-counterfactual-contract-v1` /
  `1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12`
- B `v3.7b-counterfactual-execution-contract-v1` /
  `1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970`
- C `v3.7c-counterfactual-engine-v1`
  (V3.7C COMPLETE — COUNTERFACTUAL ENGINE VALIDATED — READY FOR V3.7D)
- C seam SHA256 at D entry: `045f392e…` (verified unchanged at D exit).

## Protocol identity

`results/v3/v3_7d/evaluation_protocol.json`
(`v3.7d-evaluation-protocol-v1`), frozen BEFORE any results; protocol
hash recorded in the evaluation card. No post-hoc edits.

## Candidate population

All 71 V3.6D SIMULATION_CAPABLE anchors (2018–2024; 2025 excluded).
V3.6D sampled before V3.7 existed: no favorable-case selection possible.

## Sampling policy

Exhaust the eligible population in sample.json order (within the 60–100
target band, so no subsampling bias).

## Selected anchors

Per-anchor meta (race, target, decision lap, state identity, stage,
factual position, tyre age, remaining laps, roster, rival) stored in
run records.

## Evaluation matrix

Per anchor: reference once + PIT_IN_N {1,2,3,5} (+8 if eligible) in
MEDIUM, N=2 SOFT override probe, multi-stop (2/MEDIUM + 8/HARD),
two-driver (target + factual nearest rival, N=2 MEDIUM each),
plan-vs-plan (N2 vs N5; single vs multi-stop). All at 5000 futures,
seed 20240101, through the validated engine only.

## Single-stop coverage

70 adapted anchors × horizons {1,2,3,5}(+8 where eligible) in MEDIUM +
N=2 SOFT probe: all supported, 5000/5000 complete pairs throughout.
Execution declines sensibly with horizon (N1 100% → N8 67.6%;
supersession 0% → 32.4%). N2 and N2_SOFT execution identical
(compound affects no trigger timing).

## Multi-stop coverage

Template N=2 MEDIUM + N=8 HARD: 70/70 supported, 5000/5000 pairs.
609448 executed events vs 90552 superseded (of 700000): second stops
execute when the natural schedule cooperates, supersede otherwise —
exactly the conservative B semantics. Chronological, state-continuous.

## Multi-driver coverage

70/70 supported, 5000/5000 pairs, order-invariant identity verified.
Joint ordering propagates with no stacking/traffic/team-order claims.
Note: B requires rival != targets, so co-target rival retention is N/A
(single-target P(ahead) coverage is complete); the runner initially
passed the co-target as rival and received contract-faithful
RIVAL_NOT_PRESENT (evaluation-side correction, not an engine defect).

## Plan-vs-plan

N2-vs-N5 and single-vs-multi-stop: 70/70 supported, 5000/5000 pairs,
BASE/ALT orientation exact (deltas recomputed from raw arrays in C
tests; spot-verified here).

## Reference-vs-plan

630 supported comparisons, all with canonical
SIMULATED_NO_INTERVENTION_REFERENCE (P15=0) and exact delta orientation
(P14=0).

## Outcome distributions

Descriptive medians (expected-finish delta, ref-vs-plan): N1 −1.05, N2
−0.94, N3 −0.84, N5 −0.68, N8 −0.46; multi-stop −2.31 (full
distributions in artifact). Early forced stops cost ~1 simulated
position (pit-loss mechanics) — a mechanical observation, never a
strategy recommendation.

## Position-gain sentinel

B1 orientation independently recomputed from raw per-future positions
on a 12-anchor subset (P5→P2=+3 pattern verified at contract level).

## Pit-count sentinel

Per-future pit counts independently recomputed from raw arrays on the
subset (forced + natural per frozen C semantics).

## Ahead-of-rival sentinel

Joint-order recomputation on the subset; no V3.5, no history, no
substitution.

## Lifecycle analysis

Execution dominates short horizons; supersession rises monotonically
with N; no unexpected INVALID after eligibility (P10=0); no
CANCELLED/TERMINAL anomalies. Behavior explainable under frozen B
semantics throughout.

## Horizon analysis

Eligibility 100% at all N (within remaining-lap rule); execution
100/91/87/79/68% for N=1/2/3/5/8. No cap warranted: longer horizons
degrade gracefully to supersession (valid mechanics, not pathology).
Verdict: NO_CAP_WARRANTED; product may note execution falloff.

## CRN analysis

Independent-stream diagnostic (no engine change): paired/independent
95% CI width ratios median 0.90 (n=6, all <1). CRN usefully narrows
comparative intervals; no variance-reduction guarantee claimed.

## Simulation-count stability

Median |Δ(1000−5000)| = 0.047, |Δ(2500−5000)| = 0.012 positions on
expected-finish deltas (12 anchors, run_arm pairing). Production stays
5000.

## Seed stability

Between-seed spread median 0.061, max 0.208 positions. No severe
sensitivity; production seed unchanged.

## Reproducibility

4/4 exact (P1=0).

## Temporal safety

C poison/structural tests re-run green (Tier A below). Evaluator
audited: anchors/targets/rivals/plans/compounds all factual or
preregistered; sample.json carries no post-T outcomes into selection
(eligibility/stage predate V3.7).

## V3.6 parity

16/16 bit-identical (P17=0) on 8 real anchors at 5000 futures. Seam
SHA256 `045f392e…` identical at D entry and exit.

## Pathology report

All P1–P17 zero (one scanner over-strictness on unavailable rival
deltas corrected to flag only true NaN/inf; re-verified zero).

## Performance observations

Matrix 9631 s wall for 71 anchors (~700 arm-runs ≈ 3.5M futures at
5000 each: ~14 s/comparison on this machine). Engineering observation
only; no optimization in D.

## Known limitations

Simulator-conditional only; no weather/SC/retirement generation; no
state editing; no stacking/traffic/team models; compound pace caveat;
conservative supersession; time-loss research-only; V3.5 excluded;
spatial context-only; 2025 unsupported.

## Refinement gate

REFINEMENT_NOT_WARRANTED (blocking invariants 0; repro 4/4; temporal,
pairs, parity intact; no recomputation mismatch; no order dependence;
no P11/P12; 700 supported comparisons; explainable lifecycle; no
evidence-backed correction necessary). V3.7E = SKIPPED_BY_V3.7D_GATE;
next = V3.7F.

## E/F readiness

V3.7E SKIPPED. V3.7F ready: runtime/API/cache integration against the
frozen engine; no scientific decisions outstanding.

## Scientific card identity

`v3.7d-evaluation-card-v1`,
`96debc6392c79019abedc3a51c7c26fb1536e97cabb3fed3136c43ed7c2b19c3`.
