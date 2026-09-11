# Phase-2 Interactions (F11)

> F11 three domain-justified interactions in
> `v2/features/interactions.py` (registry 81→84, schema v7→v8), ~20
> tests green, full 189,420-row audit clean. Depends on F4–F10 as pure
> consumers; restraint was the design goal and the outcome (3 of many
> candidates; trend×stint rejected at 0.92 correlation).

## 2. Why interactions are intentionally limited

Phase-3 trees (HGB/XGBoost/LightGBM/CatBoost) learn nonlinear
conjunctions themselves; hand-built interactions earn their place
only through domain meaning or linear-model/interpretability value.
Every candidate needed a one-sentence distinction answer; vague
"models may find this useful" justifications were rejected.

## 3. Primitive inventory (registry authority, 81 defs)

Passthrough 23 (position, progress, flags, pits/stint, tyres, wx);
pace/stint 12; gaps 8; teammate/field/traffic/relative 12; rates 4;
weather/RC 9; grid + priors 12 + grid. All with dtype/unit/
missingness/temporal/sync semantics per their stage docs.

## 4–5. Candidate process + measurements

Full-scope merged primitive frame (189,420 rows) measured per
candidate: coverage, input/result missingness, distribution,
correlation with inputs, regime constancy, extremes. Retention bar:
distinct question + acceptable coverage + non-pathological values.

## 6–8. Retained interactions

1. `positions_from_grid` = grid − position (grid>0 required; + = ahead
   of slot). Rationale: the only factual summary of race progress
   against the starting slot. Coverage 98.65%, med 0, p05/95 ∓6/7.
2. `relative_pace_to_ahead_in_traffic_s_per_lap` = ahead-relative pace
   iff `in_traffic_2s` is True (null otherwise). Rationale: pace
   matters most when the factual gap is small; the null-gated form
   names the regime explicitly. Coverage 34.03%.
3. `recent_gap_to_ahead_change_in_traffic_s_per_lap` = ahead gap-rate
   iff in traffic (null otherwise). Rationale: descriptive closing
   rate under factual pressure, never a projection. Coverage 30.48%.

## 9. Rejected candidates

trend×stint_lap (0.92 corr with trend — near-identity, compounds
estimates); weather×tyre/pace (strategy/causal claims unavailable);
RC×pace (primitives suffice); grid×progress (rate-like extremes);
prior×current (pseudo-ratings); teammate×field (score-like);
gap×gap-rate projection (banned); position×momentum (redundant);
all ratios/polynomials/auto-crosses (banned categorically).

## 10–12. No-polynomial / model-capability / missingness rules

No generator, DSL, sklearn transformers, hashing, or arbitrary
normalization — three named formulas only. Trees-overlap
acknowledged; linear/interpretability value documented per feature.
Validity never broader than inputs: nulls propagate; unknown never
becomes zero.

## 13–14. Tri-state semantics

`in_traffic_2s` True→value, False→null, None→null (tested all three;
legitimate 0.0 pace preserved distinctly from null). Same rule for
the rate gate.

## 15–16. Temporal/synchronization inheritance

Strictest-input rule: traffic-gated features inherit
SYNCHRONIZED_FIELD (pace RIVAL + gap FIELD geometry);
positions_from_grid is TARGET_STATE (PRE_RACE grid consumed as a
constant, documented, not re-labeled). No cross-driver marking is
NONE where rivals contribute.

## 17–19. Registry / version / architecture

INTERACTION family ×3, v1, CANDIDATE, exact `features.*` lineage,
formula refs, NONE/PRE... (per-feature above). Schema v7→v8 exactly
once (+3). One module: pure `interaction_values` core + thin
single/batch wrappers; no engine, DSL, or plugins.

## 20–21. Single-state / batch paths

Single: engine resolves required primitives through approved
calculators (history-gated for grid), then the pure core. Batch:
vectorized formulas over merged primitive batch columns (same core
semantics per row). No raw history lookups in F11.

## 22–23. Parity / mutation / isolation

Core parity synthetic + full real-engine paths (future lap-time
mutation identical; current-position mutation moves only
positions_from_grid; unrelated compound mutation moves nothing).
Tri-state, shuffle, and registry-version suites green.

## 24. Full-data coverage (189,420 rows, MEASURED)

Nulls: positions_from_grid 1.35% (grid-0/null/position-null),
pace-in-traffic 65.97%, rate-in-traffic 69.52%. Ranges: pfg
−18/+19; pace ±23 (0.06% SC-chaos extremes, investigated factual —
2020 Austria sequencing, both inputs valid, unclipped); rate −181/+2.
Deterministic rebuild identical; no label columns; no inf.

## 25. Redundancy audit

Gated pace vs raw: 1.0000 (subset by construction — regime mask is
the information, documented); gated rate vs raw: 1.0000 (same);
positions_from_grid vs position −0.25 / vs grid +0.42 (distinct).
Near-identity triggers reconsideration per policy — here it is the
documented design (same quantity, gated regime), not accidental
duplication; trend×stint at 0.92 was rejected on exactly this rule.

## 26. Edge cases

Baku-2019 kubica-49 (pit-lane → all null), hamilton/bottas-30
(coherent gated values), Bahrain/Germany/Belgium/Monaco/Japan/2025
spots green; partial-race behavior nominal.

## 27. Performance (MEASURED)

Single 0.3 s (live primitive recompute); F11 arithmetic itself
vectorized-trivial; full audit dominated by primitive batches (~6
min). F15 must compute primitives once and reuse — noted as the
matrix-build pattern.

## 28. Limitations

Gated features inherit all input limitations (staleness, SC regimes,
eligibility); traffic threshold 2 s is a conventional band, not a
physical constant; positions_from_grid is slot-relative, not
overtake counting.

## 29. F12 handoff

F12 consumes: the 84-definition registry, v8 schema, and the
primitive-reuse audit pattern. Telemetry revisit-check, label-join
contract, canonical matrix, ablation fixtures, and exit docs are
F12+ — untouched here.
