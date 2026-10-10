# V3.6D HISTORICAL STRATEGY EVALUATION

## Final verdict

**V3.6D COMPLETE — REFINEMENT NOT WARRANTED — READY FOR V3.6F**

## Scientific question

V3.6A wording, unchanged: "Given a causal race state at decision time T,
how do plausible strategy interventions change the simulated distribution
of future race outcomes under paired stochastic futures?" D evaluates the
engine's scientific behavior — reproducibility, stability, coverage,
interpretability — never counterfactual accuracy against team choices.
All results are SIMULATOR-CONDITIONAL COUNTERFACTUAL ESTIMATES.

## Protocol

`results/v3/v3_6d/evaluation_protocol.json`, schema
`v3.6d-evaluation-protocol-v1`, frozen BEFORE any result was inspected
(mtime-guarded by test). Seasons 2018–2024; anchors at canonical
fractions {1/3, 2/3} (K=2/race); target = anchor driver; all 9 actions.
Layer 1: n=200 broad. Layer 2: n=5000 × first 8 eligible (canonical
order). Seeds {20240101, 12345, 99991} × 6 states; counts {200, 1000,
5000} × 6 states; CRN paired-vs-independent helper; repro × 4 states.
Magnitude bands and POSITIVE/NEGATIVE/UNCERTAIN rule frozen a priori.
Refinement gate: reproducibility mismatch, pathology, CRN-worse
(ratio>1.05 AND flip>20%), zero-pair>5%, systematic misclassification.

## Protocol identity

`0c2bf7fb6e46a948d811587a64aac89cb10cfe0bf67485ed9ff3b457d64088fc`
(sha256 canonical; test-pinned). Protocol file untouched since freezing;
one analyzer-side disambiguation documented below (ratio direction).

## Historical population

298 candidates (149 races × 2) → 71 MC2-eligible (23.8%). Eligibility via
frozen `prepare_initial_state`, no status resolver (matches strategy
product-path conservatism). Seasons all represented (2018:4 … 2024:15);
stages EARLY 19 / MID 34 / LATE 18. Layer 1: 71 states × 9 actions = 639
comparisons, 639/639 evaluated, 71/71 supported. Layer 2: 8 × 5000-run.

## Sampling

Deterministic canonical-order anchors; no manual selection; sampling
payload contains zero strategy fields (test-verified). Target rule =
anchor driver (no winner/famous/controversy filtering).

## Compute budget

Estimate ~2110 s; actual: screen 15 s, Layer 1 ~250 s, Layer 2 ~1125 s.
Real-state cost ≈ 3 s per 200-sim/9-action comparison; 5000-run ≈
45–180 s/state. No brute-force corpus; V3.6F cache design input.

## Coverage

Candidate 298 → MC2-eligible 71 → strategy-supported 71. Comparison
support 100% of eligible; complete-pair support: all evaluated
alternatives report requested/complete/excluded (excluded≈0 at n=200;
5000-run 5000/5000 complete on validation state).

## Unsupported states

STALE_ROSTER_OBSERVATION 165 (55%), UNSUPPORTED_TRACK_STATE 25, WET 25,
MISSING_TYRE 6, MISSING_DRIVER 6. Dominant cause is roster staleness
(conservative no-resolver path), not strategy logic. No new rules created.

## Action coverage

All 9 actions valid wherever statically admissible (639/639 evaluated;
zero ACTION-level invalids in this sample — decision laps had room and
compounds known). STAY_OUT inert≈91% of futures; PIT_NOW applied≈high;
PIT_NEXT_LAP superseded where baseline pits first. Validity vs execution
kept separate throughout.

## Reproducibility

4/4 reruns bit-identical (identity + numerics). Blocker-free.

## Seed stability

3 seeds × 6 states × 2 actions. Win-delta spread median 0.0 (max 0.115);
finish-delta spread median 0.17 (max 0.625). Raw all-metric sign
consistency 33% — driven by noise-level effects. Material effects are
stable: every |Δwin|≥0.15 and |Δfinish|≥0.79 held sign across seeds
(2019-r02-R PIT_NOW: win −0.15…−0.20, finish −1.06…−1.30). Sub-small
effects are seed-sensitive at n=200 by construction — the reason
production uses 5000 + paired intervals.

## Simulation-count stability

Median |Δ(200→5000)|: win 0.006, podium 0.012, finish 0.20;
|Δ(1000→5000)|: win 0.0, podium 0.007, finish 0.04. Production count
unchanged (diagnostic only).

## CRN variance

Informative states (n=3): paired/indep win-SE ratios 0.85/0.93/0.96 —
all favor paired. Degenerate states (n=3): both SEs exactly 0
(uninformative ties). No state favors independent. CRN helps modestly
where variance exists; never hurts. Disambiguation: the frozen gate's
label ("CRN systematically worse") fixes the ratio as paired/indep;
median 0.93 < 1.05 → gate does not fire. Protocol file unchanged.

## Sanity scenarios

Bounds: all frequency deltas ∈ [−1,1]; finish deltas within roster;
639/639 distributions sum to 1; zero invalid-actions-with-metrics; 4
inert-but-noticeable flags (∓0.015 podium/top on ~6.5% effective mass —
small-band per protocol, plausible, not pathological).

## Intervention sensitivity

|Δwin| distribution: median 0.0 pp; bands zero(<1pp)/small/moderate/large
reported in artifact. |Δfinish| median 0.8 pos. Forced stops typically
cost positions under frozen mechanics (median Δfinish −0.8,
downside median 0.48) — a descriptive mechanic, not a verdict on teams.

## Effect distributions

Per action × outcome medians/IQR/min/max in artifact. Win effects
concentrated at 0 (median 0, q75 0); podium q25 −0.04; top10 median
−0.03; finish median −0.8 (q25 −1.73, q75 −0.16).

## Objective disagreement

Podium-up + downside-up: 3.4%. Finish-up + win-down: 0.2%. Top10-up +
podium-down: 3.0%. Trade-offs exist but are uncommon — and their
existence justifies NO_SINGLE_UNIVERSAL_PRIMARY_UTILITY either way; no
weights created.

## Leader stability

Per-objective point-estimate leaders recorded; adjacent-checkpoint
analysis N/A (one checkpoint/race by design). Seed/count leader
agreement follows point stability above. No global leader exists.

## Stage analysis

Comparisons EARLY 171 / MID 306 / LATE 162. Median |Δwin| 0.0 pp all
stages; median |Δfinish| EARLY 0.99 → MID 0.78 → LATE 0.69 (shrinking
remaining-distance opportunity, as mechanics predict). No stage-specific
logic introduced.

## Race/circuit heterogeneity

Per-race medians in artifact; no circuit corrections introduced. No
execution anomalies beyond frozen semantics.

## PIT_NOW vs PIT_NEXT_LAP

Paired same-state/same-compound rows in artifact (median |Δwin diff|,
supersession rates). Descriptive only; neither called superior.

## STAY_OUT vs reference

n=71: suppression 100% of comparisons contain suppressed futures;
mean inert 91%; differs-from-reference (real suppression) 91.6%.
Validates the B distinction: STAY_OUT ≠ NO_INTERVENTION, usually inert,
sometimes behaviorally real.

## Compound analysis

SAMPLED vs explicit compounds: effects arise only through stint
sampling/transitions (no pace delta — frozen limitation, disclosed).
Empirically near-indistinguishable; reported clearly, not overread. No
E candidacy (mechanics-limited, not a defect).

## V3.5 consistency diagnostic

34 matched (race,driver,lap) states: MC2 no-intervention win freq vs
frozen `l2_logistic.proj_is_top1` — mean|diff| 0.026, median 0.0003,
correlation 0.91. Broadly compatible stories; no averaging/blending/
calibration performed. V3.8 owns fusion.

## Case studies

Algorithmic selection (no race names in rule): median-effect
(2018-r06-R/hulkenberg/STAY_OUT ≈ zeros), high-uncertainty
(2023-r06-R/leclerc/PIT_NEXT_LAP:HARD — mixed signs, wide intervals),
tradeoff (2018-r03-R/hamilton/PIT_NOW:HARD — win/pod up, downside 0.30),
inert/superseded (2021-r07-R/leclerc/STAY_OUT — all zeros), strong
(2020-r05-R/bottas/PIT_NOW:SOFT — forced stop costs ≈3.3 positions).
Full vectors, uncertainty, execution, identities in artifact. Language:
"Under the frozen MC2 simulator…" throughout; no should-have/proves.

## Plausibility audit

5/5 PLAUSIBLE, 0 QUESTIONABLE, 0 PATHOLOGICAL (strict defs:
impossible positions, out-of-bounds, invalid-with-metrics, sum≠1,
leakage). Engineering sanity, not ground truth.

## Counterfactual ground-truth limitation

History reveals the factual trajectory only. Team-choice divergence is
not error; agreement is not validation. D validates engine behavior.

## Refinement decision

**REFINEMENT_NOT_WARRANTED.** Gates: reproducibility_ok=true;
pathological=0; CRN ratio 0.93 (helps); zero-pair≈0%; no systematic
misclassification. Small effects, zero-crossing intervals, and team
divergence are explicitly not defects. V3.6E skipped per plan.

## Known limitations

No-resolver conservative eligibility; one target/state; Layer-1 n=200
(most intervals withheld); Layer-2 n=5000 on 8; V3.5 join 34 states;
forced-stop cost reflects frozen free-air mechanics.

## Next stage

V3.6F: runtime/API/cache integration on the validated engine. No
contract, engine, or parameter changes outstanding.
