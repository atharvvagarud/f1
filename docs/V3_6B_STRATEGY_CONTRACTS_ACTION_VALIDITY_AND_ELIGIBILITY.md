# V3.6B STRATEGY CONTRACTS + ACTION VALIDITY + ELIGIBILITY

## Final verdict

**V3.6B COMPLETE — EXECUTION CONTRACT FROZEN — READY FOR V3.6C** (pending
focused-test gate).

V3.6A decisions preserved exactly; no internal contradiction found. The only
judgment call was Part Y delta signs: the frozen Phase-7 standardized
paired-effect orientation (positive = improvement, including the inverted
expected-finish convention) is REUSED via Part Y's own escape clause, because
raw alt−ref units would flip the shipped `delta_expected_finish` field and
break OPTION-2 API/frontend compatibility.

## Frozen parent

Tag `v3.5-outcome-distribution`, commit
`6df5d41d3ebead9a1c9b4f0f40ed20a21ce0bff1`. Entry: HEAD matched, only V3.6A
untracked files present, nothing staged. V3.6A contract identity recomputed
and matched: `2d29c19b…0a919b0ae59b`.

## V3.6A provenance

Verdict `V3.6A COMPLETE — STRATEGY CONTRACT FROZEN — READY FOR V3.6B`;
contract `2d29c19b47b24035f0d1c503fccc8cd4090595b4ebb2a980001d0a919b0ae59b`.
Preserved: scientific question, OPTION 2, V3.5 C-role, closed 9 actions,
NO_SINGLE_UNIVERSAL_PRIMARY_UTILITY, 5000 paired futures, MC-only
uncertainty, V3.7/V3.8 boundaries.

## Reuse audit

| Structure | Verdict | Source |
|---|---|---|
| StrategyAction enum | REUSE_VERBATIM | `strategy/contracts.py` (s1) |
| Requested compounds | REUSE_VERBATIM | `SUPPORTED_REQUESTED_COMPOUNDS` |
| Candidate representation | REUSE_VERBATIM | `strategy/candidates.py` (s4) |
| Eligibility representation | REUSE_VERBATIM | 8 `STRATEGY_INTERVENTION_REASONS` |
| Comparison request/result | WRAP | S4 `compare_strategies` / `StrategyComparisonResult` |
| Simulation config | WRAP | `SimulationConfig` at count 5000 |
| Intervention object | REUSE_VERBATIM | `StrategyIntervention` (s1/v1) |
| Uncertainty result | REUSE_VERBATIM | S5 `UNCERTAINTY_VERSION=v1` |
| Strategy identity/provenance | WRAP | state/config/result identities |
| Comparison key object | NEW_REQUIRED | `v3_contracts.StrategyComparisonKey` |
| Trade-off vector schema | NEW_REQUIRED | `TRADE_OFF_FIELDS` |
| Unsupported-result builder | NEW_REQUIRED | `build_unsupported_result` |

No duplicate enum created. New module: `raceintel/strategy/v3_contracts.py`
(pure: frozen dataclasses, validation, canonical serialization, identity
hashing; no execution, no API wiring).

## Strategy action contract

`StrategyAction` str-enum {STAY_OUT, PIT_NOW, PIT_NEXT_LAP} (s1) × compound
{None=SAMPLED, SOFT, MEDIUM, HARD}; `candidate_key` = `ACTION:COMPOUND`;
`candidate_identity` = sha256(version + action + compound); STAY_OUT +
compound = contract error; provenance pinned USER_ASSUMPTION. Deterministic,
no free-form strings (`strategy_action_value` coerces/rejects).

## Closed action set

Exactly 9 = STAY_OUT×1 + PIT_NOW×4 + PIT_NEXT_LAP×4, in canonical order
(`CANONICAL_CANDIDATE_SPECS`); first-occurrence dedup by key; caller order
cannot affect identity. Generation uses factual T + frozen config only —
never future data. Validity filters remove; never invents.

## Baseline/reference contract

`SIMULATED_NO_INTERVENTION_REFERENCE`: same causal RaceState(T), same MC2
mechanics, `intervention=None`, executed once as the shared arm (BaselineArm
pattern). Explicitly NOT STAY_OUT (an intervention, often inert), NOT
historical future, NOT team strategy, NOT optimal. Separate reference KIND,
not an action identity.

## StrategyComparisonKey

Frozen dataclass, canonical declaration order, `identity()` =
`canonical_sha256` of ordered mapping, version
`v3.6b-comparison-key-v1`. Fields: key_version, race_id, decision_lap,
state_identity, target_driver_id, reference_kind, alternative_identity
(candidate_identity), simulator_identity, parameter_identity,
simulation_count, master_seed, outcome_schema_version. Season/round/session
excluded (inside state_identity); future fields impossible by construction.

## RaceState identity

Authoritative: `SimulationState.identity()` (canonical sha256; includes
race/season/round/circuit, laps, time, drivers, environment). Both arms
carry identical `state_identity`; mismatch → `anchor_mismatch`. No second
hash created.

## Simulation configuration

`SimulationConfig` (WRAP) with simulator MC2-E, count **5000**, CRN enabled
via shared seed family (default root 20240101), complete-pair requirement,
outcome schema `v3.6b-outcome-vector-v1`. Deterministic `config.identity()`
(seed included). MC2 parameters untouched.

## CRN contract

Same state, simulator, count, root seed/seed family, per-index stream
identity where structurally valid; only the intervention differs. Pair
identity = (comparison key, simulation_index). Valid pair = both sides
valid; incomplete → excluded and counted, never unpaired-substituted.
Stream rule: per-(master_seed, index[, domain]) PCG64; streams shared, not
trajectories.

## Intervention mapping

| Action | Directly modified | Unchanged | Simulated consequences |
|---|---|---|---|
| STAY_OUT | suppress target pit once at L_T+1; no compound; age untouched | everything else; future stops allowed | execution status; futures |
| PIT_NOW | forced pit L_T+1; compound/sampled; age→0; pit-count+1 | downstream outcomes | rejoin, times, order, status |
| PIT_NEXT_LAP | planned forced pit L_T+2; L_T+1 baseline-normal; age/count on execution | historical T+1 (unused) | SUPERSEDED if baseline pits L_T+1; non-execution statuses |

Never mutated: future position/winner/gaps/pace/status/weather/safety car.

## PIT_NOW semantics

Forced stop at L_T+1 replacing baseline decision; frozen draw order
compound→loss→stint; R6 empirical pit-loss grids; age reset 0; free-air
rejoin emerges from mechanics. Phase-7 behavior reused unchanged.

## PIT_NEXT_LAP semantics

A plan at T, not knowledge of T+1: simulator evolves L_T+1 with baseline
mechanics; forced stop at L_T+2 unless baseline pits first (SUPERSEDED) or
retirement/terminal/race-end intervenes (non-executed status, counted, never
imputed). No historical T+1 input.

## STAY_OUT semantics

Suppress-at-current-opportunity (L_T+1) ONLY — forbids nothing in the
future. Frequently inert (SUPPRESSED + null reason = INERT). Near-zero delta
with high inert rate is NOT equivalence evidence.

## Compound policy

Enum {SOFT, MEDIUM, HARD, SAMPLED}; dry-only scope stated explicitly (MC2
defers wet); unknown/missing → `unsupported_compound`, never simulated; no
FIA inventory implied; no pace effect (frozen limitation).

## Action validity matrix

Validator: `_resolve_intervention` via `build_candidate` (reused; no second
validator). Conditions: target present/nonterminal REQUIRED; decision lap
REQUIRED; MC2 eligible REQUIRED; pit dynamics REQUIRED; compounds known
REQUIRED (for pit actions); laps remaining REQUIRED; planned-stop
executable-in-principle REQUIRED (PIT_NEXT_LAP); in-pit context DEFERRED;
wet DEFERRED→unsupported. T-safe data only.

## Inert actions

INERT = syntactically valid, no effective intervention (STAY_OUT with no
baseline pit to suppress; pit coinciding with baseline). Simulated and
marked (rates disclosed); pre-simulation identity-proof of inertness is not
available, so filtering-before-simulation is NOT adopted. Never reported as
equivalence.

## Superseded actions

SUPERSEDED = execution status when baseline mechanics moot the plan
(PIT_NEXT_LAP vs baseline pit at L_T+1); performance-irrelevant. No
cross-candidate dedup needed: the 9 identities are structurally distinct and
state-conditional sameness is reported via execution rates, not removal.
Nothing removed for looking worse.

## StrategyEligibility

Zero new reason codes. Composes frozen MC2 eligibility + 8 strategy reasons:
COMPARISON-level = `target_driver_not_in_roster` (+ engine-level
unsupported); ACTION-level = the other 7; DIAGNOSTIC-only = 5 execution
statuses (+ INERT reading). A-role candidates from V3.6A all resolve to
existing codes (`PIT_DYNAMICS_UNAVAILABLE`≈`pit_dynamics_required`,
`INVALID_*`≈`unsupported_*`, `PLANNED_STOP_NOT_EXECUTABLE`→execution
statuses + `decision_beyond_race`).

## Eligibility hierarchy

STATE (MC2: can the state evolve?) → ACTION (is this intervention valid
here?) → COMPARISON (can reference + ≥1 alternative pair?). One invalid
action never collapses siblings; state-eligible ≠ all-actions-valid.

## Unsupported result contract

`build_unsupported_result`: supported=false, level, reason_code,
human_reason, state/action identities, provenance; `metrics` ALWAYS empty —
no zero-filled deltas, no NaN, no fallback simulator.

## Outcome vector

Per arm (reference + alternative): win/pod/top5/top10 frequency [0,1],
expected/median/q25/q75 finish (positions), valid/invalid counts, position
distribution. Paired-only: downside probability. Schema
`v3.6b-outcome-vector-v1`. No score.

## Expected-points decision

**DEFERRED**: no points table in frozen summaries, varying field sizes,
season/fastest-lap scoring complications, unmodeled DNFs. V3.6 not expanded
for one metric.

## Downside-risk decision

**IN SCOPE** as paired-only diagnostic: DOWNSIDE_PROBABILITY = mean over
complete pairs of I(finish_alt > finish_ref) ∈ [0,1]; lower = less harm.
No arbitrary N; complements (not redundant with) the mean finish delta.

## Position distribution

[(position 1-based, frequency)] + roster_size; sums to 1 over valid
futures; invalid counted separately; field-size explicit. Never V3.5
marginals.

## Paired delta conventions

Δwin/pod/top5/top10 = alt − ref (freq, + = improvement); Δexpected_finish
= ref − alt (pos, + = improved). Frozen Phase-7 standardized paired-effect
orientation reused (Part Y escape clause invoked; raw units would break
shipped API/frontend + V3.6A freeze).

## Trade-off vector

`StrategyOutcomeDelta`: 6 paired deltas in frozen order, each with paired
SE + 95% MC interval + classification. Objective leaders
(win/pod=max, expected-finish=min point estimate) = largest/best estimate
only — NOT recommended/optimal/proven.

## Uncertainty

S5 v1 reused verbatim: paired SE = std(ddof=1)/√n; B=2000 paired-percentile
bootstrap, 95%, linear, pair-as-unit; MIN_VALID_PAIRS_FOR_CI=30; bootstrap
seeds per (substrate,subject,metric), never touching sim RNG. Binary and
finish metrics share the paired machinery (EXPECTED_FINISH via negated
position, bit-identical to S4). Every interval labelled
MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY. No TV/Wasserstein distances
(deferred — distributions + interpretable deltas suffice).

## Complete-pair policy

Identical valid-pair membership for ALL estimands in a comparison; exclude
on either-side invalidity; report requested/complete/excluded +
`validity_sets_match`. Point deltas for n≥1 (n=0 → NO_VALID_PAIRS);
intervals need n≥30; no new comparison-level threshold invented (C/D
validation may revisit with evidence).

## Execution rate

Status rates divide by `pairs_total` (requested simulations) — S4 doctrine
reused; invalid-inclusive accounting preserved. Diagnostic only: execution
failure ≠ strategy failure.

## Seed identity

{master_seed, simulation_count, stream rule}; pair (key, index)
reproducible; statistical seeds derived independently. No raw RNG state in
public schemas.

## Temporal safety

Forbidden at T: future pits/compounds/laps/result/position/unknown
status/safety-car/weather, historical post-T action, V3.5 post-race labels.
Allowed: causal RaceState(T), static circuit info, pre-T history, frozen
allowed-history params, simulator-generated stochastic futures.

## V3.5 consistency role

Excluded from candidate generation, intervention, simulation, scoring,
ranking, eligibility, uncertainty (mechanically: no import path exists and
none is added). V3.6D offline diagnostic only: MC2 no-intervention win
frequency vs frozen V3.5 p_win; output-modifying use forbidden; no
averaging/normalization/fusion.

## Historical context

POST_HOC_CONTEXT in V3.6D case studies only. Frozen separation:
SIMULATED_REFERENCE (computed, causal) vs HISTORICAL_OBSERVED_FUTURE
(displayed, post-hoc).

## Result provenance

12 fields: contract/comparison/RaceState/MC2/config/reference/action
identities + count + complete pairs + seed family + outcome schema +
eligibility status. Compact dict, no redundant payloads.

## V3.6C implementation boundary

C implements: paired engine on MC2-E seam, outcome vector, paired
downside, key emission, provenance. C invents: nothing above. Forbidden:
new actions/compounds/signs/weights/uncertainty/codes, V3.5 in
computation, post-T inputs, API/frontend changes.

## Known limitations

Dry-only; no compound pace delta; no DNF/points/weather-SC evolution;
single-driver single-decision; CRN with limitations; 2025 unserved;
counterfactuals simulator-conditional; comparison-level minimum deferred
to C/D evidence.

## V3.6C recommendation

Implement the thin paired layer per this contract: reuse
`run_baseline`/`run_intervention_arm`/`pair_arms` flow against the frozen
MC2-E seam, extend per-arm aggregates (top5/top10/median/quartiles),
compute the paired downside estimand, emit `StrategyComparisonKey` +
provenance on every result, and prove determinism + complete-pair
accounting on a small state sample before any corpus work.
