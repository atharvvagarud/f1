# V3.6C PAIRED MC2 STRATEGY ENGINE

## Final verdict

**V3.6C COMPLETE — PAIRED MC2 ENGINE VALIDATED — READY FOR V3.6D** (pending
final Tier A confirmation below; all suites green at time of writing).

## Frozen parent

`v3.5-outcome-distribution` / `6df5d41d3ebead9a1c9b4f0f40ed20a21ce0bff1`.

## A/B provenance

A `2d29c19b…0a919b0ae59b` and B `df821fe13e…443e3644` recomputed-MATCHED at
entry; B readiness `ready=true, remaining=0`. B decisions preserved exactly;
C required zero new scientific decisions.

## Architecture

Thin orchestration (`raceintel/strategy/v3_engine.py`, ~640 lines,
`v3.6c-engine-v1`): S4 `compare_strategies` executes (one shared reference,
one arm per valid candidate, same seed family); the layer derives widened
aggregates, paired trade-off deltas, paired MC uncertainty, keys, leaders,
provenance. Public surface: `compare_v3_strategies` (+ singular
`compare_v3_strategy`). No API route, no frontend import, no serving.

## Reused Phase 7 components

Candidate validity/keys/identities (S1/S4), `run_baseline` /
`run_intervention_arm` / `pair_arms` / `paired_differences` flow via S4
(S3), `candidate_uncertainty` + `derive_bootstrap_seed` +
`comparison_substrate_identity` (S5), execution statuses/rates, reason
codes, delta orientation, terminology. Extended-metric uncertainty
(TOP5/TOP10/DOWNSIDE) uses the identical paired algorithm, proven
bit-identical to S5 on shared metrics by test.

## Engine interface

Typed frozen dataclasses (`V3ArmAggregate`, `V3Delta`,
`V3AlternativeResult`, `V3StrategyResult`); deterministic `to_dict()` for
later API/cache/frontend use. Specs are `(action, compound)` pairs only;
malformed specs raise; unknown values become ACTION-level invalid (never
simulated).

## Reference arm

`SIMULATED_NO_INTERVENTION_REFERENCE` via S4 `run_baseline`
(`intervention=None`), same state/config/count/seed as every alternative.
Proven ≠ STAY_OUT semantically (pinned kind) and behaviorally (STAY_OUT
suppresses a real baseline pit on the `scheduled=11, stint=2.0` fixture:
suppressed=8, inert=0).

## Alternative arms

Resolved through frozen `build_candidate`/`generate_candidates` (no second
validator). Invalid → ACTION-level not-evaluated with frozen reason; no
intervention-arm simulation (call-count test proves reference-only path).

## MC2 execution

Frozen MonteCarloEngine seam (MC2-E identity `MC2-E (E_AR1_RESIDUAL)` in
provenance). No parameter/table/eligibility/RNG/pit-loss/pace/finish-order
change. `intervention=None` parity verified load-bearing (arm identity ==
direct run identity).

## CRN

Same count/root/seed-family/index-streams across reference and all
alternatives; only the intervention differs. Single shared reference for
multi-action comparisons ([A] vs [A,B] science identical). Provenance
persists seed family + identities.

## Complete-pair accounting

Pair = (key, index); excluded on either-side invalidity; requested /
complete / excluded persisted per alternative; identical membership across
all estimands (each delta's `valid_pairs` == `complete_pairs`).

## Outcome aggregates

Per arm over the complete-pair set (Part N choice documented; S4
own-denom aggregates untouched): win/pod/top5/top10 frequency,
expected/median/q25/q75 (linear quantile), valid-pair count, position
distribution + roster_size. Displayed ref/alt values reconcile exactly
with deltas.

## Position distribution

Mutually exclusive target positions over complete pairs; sums to 1
(1e-9); roster explicit; varying sizes handled.

## Trade-off deltas

Frozen positive-improvement orientation: Δfreq = alt−ref; Δfinish =
ref−alt. Verified against displayed aggregates.

## Downside risk

Paired-only P(alt worse than ref), ties excluded, [0,1]; diagnostic, not
an objective (no leader).

## Execution diagnostics

S4 summary reused verbatim (denominator `pairs_total`): applied /
suppressed / superseded / inert / race-end-cancelled + rates +
`baseline_pit_suppressed`. Non-execution never read as performance.

## Uncertainty

S5 verbatim for win/pod/finish; identical machinery for top5/top10/
downside (own metric names, derived seeds). Paired SE = std(ddof=1)/√n;
B=2000/95%/linear/pair-unit bootstrap; n≥30 for intervals; no
independent-arm formula. Every delta labelled
MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY / "95% MC interval".

## Eligibility

STATE (S4 unsupported passthrough) → ACTION (frozen reasons) →
COMPARISON (NO_VALID_PAIRS on zero content). Siblings never collapse.

## Unsupported states

`metrics` always empty (provenance `eligibility_status.metrics == {}`);
no zeros/NaN/fallbacks.

## Determinism

Same inputs → bit-exact identity + numerics (aggregates, deltas, SE/CI,
execution) across reruns.

## Action-order invariance

[A,B,C] vs [C,A,B] identical per action key (order-independent RNG: no
position dependence).

## MC2 reference parity

PASS: `run_baseline` result identity + outcome digest == direct
`intervention=None` run. Load-bearing, green.

## Phase 7 compatibility

PASS: candidate identities, pair counts, exclusion buckets, win/pod/
finish deltas, execution — identical where contracts overlap; V3
extensions purely additive. Phase 7 untouched (guard test).

## Synthetic invariants

12/12 pure-math tests green (zero/±1 deltas, orientation both ways,
downside .75, ties, distribution sum, median/quartiles, membership,
zero-pair shape, tie order).

## Real MC2 smoke validation

Synthetic-but-real seam states (`pit_field` + R6 pit params through the
actual MonteCarloEngine): all 9 actions, 4 compounds, inert (4/4),
superseded (6/6), race-end-cancelled (6/6), suppression-of-real-pit —
all as frozen semantics predict. Historical-state evaluation belongs to
V3.6D by contract.

## 5000-run validation

PIT_NOW @5000/seed 20240101: executed, 5000/5000 complete, 0 excluded,
6 deltas + comparison identity, 0.6 s micro-state. Numbers not
interpreted.

## Runtime

Micro-state: ~8–10k sims/s; 500-action 3-way ≈ 0.2 s. Real-state latency
governed by S7 measures (1k/4 ≈ 6.7 s) — V3.6F design input. No premature
optimization.

## Temporal safety

Anchor-mismatch rejection verified; public specs cannot carry future
fields; only simulator-generated futures enter. Leakage suites green.

## V3.5 separation

AST import audit + module audit: no `v3_5`/`outcome` dependency in engine
or contracts; no probability/calibration/PAVA usage.

## Known limitations

Synthetic-state validation only; dry-only; no compound pace delta; no
DNF/points/weather-SC; single-driver single-decision; CRN with
limitations; micro-state perf.

## V3.6D readiness

Ready: engine validated, contracts frozen, provenance deterministic.
V3.6D owns historical scientific evaluation + stability/coverage per the
V3.6A-designed (never executed) plan.
