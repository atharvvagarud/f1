# V3.8C AGREEMENT + DISAGREEMENT METRICS

## Final verdict

V3.8C COMPLETE — CONSENSUS METRICS VALIDATED — READY FOR V3.8D. Metrics-contract + implementation stage: deterministic source-vs-source diagnostics with no ground truth, no thresholds, no fusion, no quality ordering.

## Frozen parent

- Commit: `30fe18908a41d95113c189274598269a95ef44ca`
- Tag: `v3.7-counterfactual-engine`

## A provenance

Contract `v3.8a-consensus-contract-v1`, identity `d0b8785a…9b9a67b` (recomputed at entry). Taxonomy, target compatibility, fail-closed rules, poison blacklist, and 2025 status all inherited unchanged.

## B provenance

Contract `v3.8b-source-alignment-contract-v1`, identity `d212803f…1dfbfde7` (recomputed at entry). C consumes `NativePrediction`/`ComparisonFrame`/`MultiSourceFrame`/`SupportAccounting` without reimplementing joins, weakening identity checks, or transforming native values.

## Architecture

`raceintel/consensus/metrics.py` (`v3.8c-consensus-metrics-v1`) + `trajectories.py` (`v3.8c-consensus-trajectories-v1`): B frames in, typed metric records out. No dependency upward into evaluation/API/frontend/strategy/counterfactuals; no frozen source imports C.

## Metric taxonomy

RANK_AGREEMENT, LEADER_AGREEMENT, TOP_K_AGREEMENT, MAGNITUDE_DISAGREEMENT, DIRECTIONAL_TEMPORAL_RELATIONSHIP, MC_SAMPLING_CONTEXT. No consensus/confidence/certainty/quality/source-winner score exists anywhere in C.

## Common driver universe

State metrics run on the explicit B pair-comparable intersection, and every metric record carries candidate/A/B/common counts plus exclusions — a 12/20 computation stays visibly 12/20.

## Rank construction

Descending native value, rank 1 highest. Input order never affects values; canonical driver ordering only for serialization.

## Tie handling

AVERAGE RANK frozen (`{0.8,0.5,0.5,0.2}` → `{1,2.5,2.5,4}`). Ties never broken by identity, row/source order, or randomness. Dedicated tie matrix fixtures: no ties, leader tie, interior tie, boundary-crossing tie, all-tied one/both sides, two-driver, single-driver states.

## Spearman

Pearson on average ranks over ≥2 common drivers; zero rank variance → explicit UNSUPPORTED (never 0/1/NaN); tied drivers retained. Verified +1/−1/partial against hand computation and scipy to 1e-13.

## Kendall tau-b

Tie-aware tau-b (concordant/discordant/single-side/full ties counted separately); degenerate → UNSUPPORTED; never substituted by Spearman. Verified against scipy.

## Rank displacement

`rank_b − rank_a` per driver; positive means B ranks the driver numerically lower. Descriptive only — never better/worse. Reversing A/B negates exactly (tested).

## Leader sets

Tie-safe sets of all drivers sharing the best native value; `leader_exact_match` (set equality) and `leader_overlap` (non-empty intersection) kept as distinct diagnostics, never collapsed.

## Leader scope

`COMMON_UNIVERSE_LEADER_SET` unless both sources provably cover the full candidate universe (`FULL_FIELD_LEADER_SET`). Partial-universe leaders are never called predicted race leader unqualified.

## Top-k agreement

Boundary-tie-inclusive sets with `requested_k` + `effective_set_size` recorded; never cuts through a tie. Intersection/union/Jaccard plus directional top-k coverages; top-1 defers to leader-set diagnostics rather than pretending a tie-expanded singleton is unique.

## Magnitude disagreement

Same state/driver/compatible target/available/finite only. `signed_gap = p_b − p_a`, `absolute_gap = |·|`. Cross-target magnitude refused at the compatibility gate.

## Signed-gap orientation

Positive = source B numerically higher. Explicitly not more correct, confident, or better. Reversal negates (tested); absolute gap symmetric (tested).

## V3.5 P_win lineage

`information_lineage_relation`: SHARED_OR_DERIVED_LINEAGE for the V3.1B↔V3.5-control WIN pair (mathematical agreement computable as a diagnostic, never two votes); DISTINCT_MECHANISM elsewhere. Carried on metric records involving the pair.

## State-level magnitude summary

Mean/median/max/RMS absolute gap over common drivers with n and coverage — never called error, loss, or calibration error; no weighted combinations.

## MC sampling standard error

`SE_MC = sqrt(p(1−p)/n)` from B-provided trial counts; finite-MC sampling variability only — not model, real-world, or outcome uncertainty. `n ≤ 0` unsupported; `n` never inferred. p=0/1 yields SE 0 under the plug-in formula (documented, never claimed as certainty).

## MC sampling interval

Wilson 95% bounded interval, deterministic, no bootstrap; non-zero width at p=0/1 where appropriate (e.g. p=0,n=5000 → (0, 0.00077)). Labeled MONTE CARLO SAMPLING INTERVAL exclusively.

## MC-context diagnostics

Absolute gap + SE + Wilson interval + inside-boolean exposed together; no significance threshold, no confidence-disagreement score; inside means numeric containment only, not equivalence. No z-score language.

## Multi-source summary

Per-state structure over `MultiSourceFrame` holding separate pairwise diagnostics (rank, leader, magnitude where compatible, top-k, coverage) — never collapsed to one number, no majority vote, no consensus leader.

## Pair ordering

Canonical registry-ordinal ordering; symmetric metrics value-identical under reversal; oriented metrics follow explicit A→B and negate on reversal (tested).

## Primary pair

V3_1B_LOGISTIC vs MC2_E — the main distinct-mechanism winner comparison. Secondaries: V3.1B↔V3.5-control, XGB↔MC2, V3.1B↔XGB, V3.5-top-k↔MC2-derived where exposed. Secondary volume never obscures the primary pair.

## Temporal trajectories

Ordered exact-state sequences per race/pair/target; no interpolation, fill, or nearest-lap. Per-driver gap/displacement series with explicit non-comparable observations.

## Directional change

Consecutive-comparable deltas with lap deltas; numeric deltas primary; CONVERGING/DIVERGING/UNCHANGED purely descriptive (gap decreased/increased/exactly equal); no meaningful-change threshold.

## Missing temporal states

Non-consecutive observations (e.g. laps 10→15) record `lap_delta` and missing-intermediate counts where determinable; never presented as continuous observation.

## Stage aggregation

Pure EARLY/MID/LATE utilities (mean/median/support/race counts over supplied values) on frozen labels; no historical summarization in C.

## Race-macro aggregation

Per-race aggregates as the primary equal-weight unit; state-pooled weighting never forced by the API.

## Undefined metrics

Eight stable reasons (insufficient drivers, zero variance, incompatible target, unavailable source, missing/invalid MC n, no comparable states, metadata mismatch), always explicit UNSUPPORTED + reason — never 0/NaN/inf.

## Support accounting

Every metric retains candidate/A/B/common/excluded accounting; missing never becomes zero; native zero stays numeric zero; partial universes qualified.

## Temporal safety

C consumes B outputs only; no historical parquet, result table, label, or future-event reads; no outcome-grounded imports (structural tests); A/B poison blacklist carried forward.

## Ground-truth boundary

No actual/observed/correct-source/accuracy field in code, contracts, or results (structural tests). C cannot declare any view better; ground truth first appears in D.

## Fusion prohibition

No averaging, blending, stacking, meta-models, combined probabilities, majority votes, consensus leaders, or confidence/certainty scores — not even placeholder interfaces (structural tests).

## Threshold prohibition

No LOW/MEDIUM/HIGH, no 5/10/20pp cutoffs anywhere; continuous descriptive quantities only (structural test).

## Validation fixtures

Hand-computable mathematical fixtures: perfect/reversed/partial rank agreement, leader agreement/disagreement/ties, top-k exact/partial/empty/boundary-tie, zero/known/oriented gaps, MC n fixtures incl. p=0/1 edges, partial support, decreasing/increasing/missing temporal gaps. Nothing selected on real historical performance.

## Reproducibility

Pure deterministic functions; no clock/RNG/state; permutation-invariant outputs; identical inputs → identical records (tested).

## Known limitations

Metrics describe numeric relationships between source-native views, not real-world value; rank metrics need ≥2 common drivers; zero-variance states are UNSUPPORTED (not agreement); MC context is sampling-only; V3.5 P_win↔V3.1B agreement is lineage-linked, not independent corroboration; thresholds and interpretation belong to D.

## V3.8D readiness

D applies these frozen metrics to the historical corpus (race-macro primary, stage/year views secondary), uses support accounting for eligibility reporting, and decides the fusion gate — without redefining any metric.
