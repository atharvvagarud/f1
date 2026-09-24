# Phase 7 — S4: Candidate Generation + Strategy Comparison

Status: **S4 COMPLETE — READY FOR S5**.

S4 builds the strategy comparison layer. Given one exact `SimulationState` at
T, one target driver and one simulation configuration it generates the
canonical candidate interventions, executes ONE common baseline, evaluates each
statically valid candidate against that baseline under the S3 paired / CRN
substrate, and returns a transparent comparison with complete-valid-pair
deltas, validity accounting and execution-status rates.

S4 does **not** decide which strategy is best, does **not** expose production
uncertainty (CI / SE / significance), and does **not** touch the API or
frontend. S5 owns objective policy and production uncertainty.

Historical Phase-6 checkpoint: `b813ffe1` (`v2-monte-carlo-phase6`).
Frontend foundation: `6c04438` (`v2-frontend-foundation`).
S3 decision inherited: `ADOPT_CRN_WITH_LIMITATIONS`.

---

## 1. Files changed

| File | Change |
|---|---|
| `v2/strategy/paired.py` | **Refactored for baseline reuse.** Adds `BaselineArm`, `InterventionArm`, `run_baseline`, `run_intervention_arm`, `pair_arms`; `run_pair` now composes them. No pairing semantics, no draw, no identity and no result changed (S3 tests remain green). |
| `v2/strategy/candidates.py` | **New.** Canonical candidate space, stable candidate identity, T-only static validity via the canonical simulator validator, deterministic dedup and canonical ordering. |
| `v2/strategy/comparison.py` | **New.** `TargetAggregate`, `CandidateExecutionSummary`, `CandidateComparison`, `StrategyComparisonResult`, `compare_strategies`. One baseline + K intervention arms; complete-valid-pair deltas. |
| `v2/strategy/__init__.py` | Exports the S4 surface. |
| `tests/test_v2_phase7_s4_comparison.py` | **New.** 42 focused S4 tests. |
| `scripts/run_phase7_s4_validation.py` | **New.** Real performance / memory / validity-audit experiment; writes the artifact. |
| `data/v2/strategy/s4_comparison_validation_v1.json` | Generated artifact. **Untracked** (`/data/v2/` is git-ignored by repository policy; reproducible from the script). |

No frozen Phase-6 scientific runtime file changed. `v2/simulation/monte_carlo.py`
retains its S3-authorized hash `d2166075…09e68c68`;
`docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json` is untouched (no new drift).
`docs/PHASE6_FREEZE_MANIFEST.json` is untouched. Nothing is staged, committed
or tagged.

---

## 2. Graphify pre-audit

Pre-edit `graphify query "strategy intervention comparison candidate"` located
the S1–S3 surface (`StrategyIntervention`, `interventions.py`, `paired.py`,
`_resolve_intervention`) and confirmed the single dependency direction
`v2.strategy → v2.simulation`. The audit identified the narrowest place for the
new work: a strategy-owned `candidates.py` (candidate identity/validity, T-only)
and `comparison.py` (shared-baseline orchestration), with `paired.py` split into
reusable baseline / intervention / pairing functions. No second simulation
path, no scalar replay, no trajectory history.

Post-edit `graphify update .`: **9 379 nodes, 23 681 edges, 284 communities**.
AST dependency check: `v2/simulation/*` imports of `v2.strategy` = **0**.
Strategy internal edges: `__init__ → {candidates, comparison, contracts,
interventions, paired}`, `candidates → {contracts}`, `comparison →
{candidates, contracts, paired}`, `paired → {contracts, interventions}`,
`contracts → ∅`; **no Strategy cycle**. `v2/strategy` imports no
`model_lab` / `prediction` / `replay` / `pandas` / `sklearn` material.

---

## 3. Candidate-generation architecture

`v2/strategy/candidates.py`:

- `CANONICAL_CANDIDATE_SPECS` — the canonical action/compound grid;
- `candidate_key` / `candidate_identity` — deterministic scientific identity
  from `(action, requested_compound)`;
- `StrategyCandidate` — immutable `{action, requested_compound, valid, reason,
  intervention}`;
- `build_candidate` — validates ONE `(action, compound)` against the factual
  state at T;
- `generate_candidates` — canonical set (or caller subset), deterministically
  deduplicated, always returned in canonical order.

Generation depends **only** on the factual state at T, the frozen
`SimulationConfig` and the strategy contract. It never inspects the actual
future race, a final result or oracle material.

---

## 4. Canonical candidate set

```
STAY_OUT
PIT_NOW        × {sampled, SOFT, MEDIUM, HARD}
PIT_NEXT_LAP   × {sampled, SOFT, MEDIUM, HARD}
```

Nine conceptual candidates; `sampled` (`requested_compound=None`) means
baseline-drawn compound. Not all nine need be valid on a given state. Canonical
keys: `STAY_OUT:SAMPLED`, `PIT_NOW:SAMPLED`, `PIT_NOW:SOFT`, `PIT_NOW:MEDIUM`,
`PIT_NOW:HARD`, `PIT_NEXT_LAP:SAMPLED`, `PIT_NEXT_LAP:SOFT`,
`PIT_NEXT_LAP:MEDIUM`, `PIT_NEXT_LAP:HARD`.

---

## 5. Candidate identity / ordering

- Identity is a SHA-256 over `{candidate_contract_version, action,
  requested_compound}`. It distinguishes the sampled compound from every
  explicit compound. List position is never identity. Validity is a derived
  state-dependent projection and is not part of the candidate identity.
- `candidate_identity` accepts the enum or its exact string value, so
  `PIT_NOW` enum and `"PIT_NOW"` hash identically.
- `generate_candidates` normalises to canonical action order. Supplying the
  same subset in a different order yields identical identities/results.
- Producing an explicit `PIT_NOW:HARD` while the driver is already on HARD is a
  distinct candidate from `PIT_NOW:SAMPLED`.

---

## 6. Candidate validity policy

Two layers, kept separate:

- **Static / pre-run invalidity** (`StrategyCandidate.valid=False` with a stable
  `reason`): the candidate is reported but never simulated.
- **Stochastic execution status** (`APPLIED` / `SUPPRESSED` / `SUPERSEDED` /
  `RACE_END_CANCELLED` per realization): reported as execution rates.

`build_candidate` reuses the canonical simulator validator
`v2.simulation.monte_carlo._resolve_intervention`; no eligibility logic is
duplicated. Reachable reasons:

| Reason | Trigger |
|---|---|
| `target_driver_not_in_roster` | Target id absent from the T roster. |
| `anchor_mismatch` | `decision_state_identity` ≠ `state.identity()` (direct/manual only). |
| `decision_lap_mismatch` | `decision_lap` ≠ the target's factual lap at T. |
| `decision_beyond_race` | `decision_lap + action_offset > scheduled_laps`. Covers near-race-end filtering (e.g. `PIT_NEXT_LAP` at `scheduled=2`). |
| `unsupported_compound` | Compound outside the v1 dry set (`SOFT`,`MEDIUM`,`HARD`). |
| `unsupported_action` | Unknown action token. |
| `malformed_intervention` | Structurally impossible combination (e.g. `STAY_OUT` + compound). |
| `pit_dynamics_required` | `config.pit_dynamics_enabled=False`. |

Every reason is a member of the canonical `STRATEGY_INTERVENTION_REASONS`.

---

## 7. Same-compound policy

Requesting the driver's CURRENT dry compound is **valid and retained**. Phase-6
has no per-compound pace delta and the project has no FIA sporting-regulation
rule; the current compound is a supported v1 dry identity and may affect
compound-conditioned transitions/stint grids. It is not removed merely because
it is strategically unusual in the real world. Documented as a deliberate
decision and pinned by test.

---

## 8. Unsupported-state handling

The baseline simulation's existing eligibility is authoritative. If the factual
state itself cannot be evolved (`SimulationUnsupportedError` from `_prepare`:
`wet_track_conditions`, `unknown_track_state`, `neutralized_track_state`,
`red_flag_track_state`, `missing_tyre_age`, `non_contemporaneous_roster_member`,
`parameter_temporal_leak`, …) `compare_strategies` returns a **structured
comparison-level unsupported result**: `supported=False`,
`unsupported_reason=<canonical reason>`, `baseline=None`, and every candidate
`evaluated=False`. A target outside the roster is refused the same way
(`target_driver_not_in_roster`). No candidate-level workaround is manufactured.

---

## 9. Comparison architecture

`v2/strategy/comparison.py`:

- `compare_strategies(state, parameters, config, assumptions,
  target_driver_id, *, candidate_specs=None, execution_policy=…,
  zero_noise=False, chunk_size=…)`:
  1. generate candidates (canonical or supplied subset);
  2. refuse at the comparison level if the target is not in the roster or the
     state is unsupported;
  3. run the baseline **once** (`run_baseline`);
  4. for each **statically valid** candidate run one intervention arm
     (`run_intervention_arm`) and pair it against the shared baseline
     (`pair_arms`);
  5. return `StrategyComparisonResult`.
- Immutable structures: `TargetAggregate`, `CandidateExecutionSummary`,
  `CandidateComparison`, `StrategyComparisonResult`. Compact terminal values
  only — no trajectories, no raw per-index arrays in the public result.

---

## 10. Baseline reuse

`paired.py` now exposes:

- `run_baseline(...) -> BaselineArm` — one executed Phase-6 baseline
  (`intervention=None`) plus its per-index outcomes and digest;
- `run_intervention_arm(...) -> InterventionArm` — one intervention arm;
- `pair_arms(baseline, intervention_arm) -> StrategyPairedResult`;
- `run_pair(...)` composes the three, so S3 behaviour is preserved.

`compare_strategies` executes **ONE baseline + K intervention arms** instead of
the naive `K baselines + K intervention arms`. Each arm is a pure function of
its inputs and runs on independent per-`(seed, index)` streams, so the order and
multiplicity of arm execution cannot change any result.

---

## 11. Baseline-reuse equivalence

Dedicated tests assert, for every one of the nine canonical candidates, that the
shared-baseline comparison is **exactly** equal to an independent S3 `run_pair`:

- paired identity equal;
- baseline and intervention `MonteCarloResult.identity()` equal;
- baseline and intervention per-index outcome tuples equal;
- `PairingDiagnostics` equal.

`run_pair`'s public outputs are therefore unchanged by the refactor. All 22 S3
tests still pass.

---

## 12. Comparison estimand

The **canonical comparison delta** is the mean over **complete valid pairs**
(`both arms valid`) from the S3 paired substrate: `delta_source =
"complete_valid_pairs"`. Arm aggregates keep their own ordinary per-arm valid
denominators (`MONTE_CARLO_FREQUENCY`). Both the pair counts
(`baseline_only_valid`, `intervention_only_valid`, `both_invalid`) and the
canonical delta are reported so the two are auditable; the arm-aggregate
difference is not duplicated.

Rationale: when the two arms' valid sets differ, the arm-aggregate difference is
not an estimator of the same paired contrast; the complete-pair mean is the
consistent paired estimand, and the S3 report's aggregate-reproduction evidence
shows the per-index outcomes reproduce each arm exactly.

---

## 13. Delta semantics

Frozen, documented, single convention:

- `delta_win_probability = mean_pairs( I(candidate wins) − I(baseline wins) )`
  — **positive = candidate improves** the estimated win probability.
- `delta_podium_probability` — the same for podium.
- `delta_expected_finish = mean_pairs( baseline_finish − candidate_finish )`
  — **positive = candidate improves (lowers)** the expected finishing position.

No sign is switched between layers; `paired_differences` in S3 uses the same
orientation.

---

## 14. Validity-denominator policy

Frozen: **comparison delta = complete-valid-pair estimator**, while **arm
aggregates retain their own ordinary valid denominators**. `CandidateComparison`
exposes `valid_pairs`, `baseline_only_valid`, `intervention_only_valid`,
`both_invalid` and `validity_sets_match`. A crafted mismatched-validity test
pins that deltas use only complete pairs and that the counts are exhaustive.

Audit on the 1 000-trial MID all-candidate comparison: **0** candidates with
mismatched validity sets; `total_baseline_only_valid = 0`,
`total_intervention_only_valid = 0`. On this anchor the two estimands coincide,
but the policy is defined for the general case.

---

## 15. Candidate execution-status aggregation

`CandidateExecutionSummary` reports counts and descriptive rates over all
realizations: `APPLIED`, `SUPPRESSED`, `SUPERSEDED`, `RACE_END_CANCELLED`,
plus `inert` (a suppression that suppressed nothing) and `baseline_pit_suppressed
= suppressed − inert`. Rates are `count / pairs_total`. They are descriptive
only — never converted into a quality score.

MID artifact example (1 000 trials): STAY_OUT `suppressed=1000`, `inert=942`;
PIT_NOW `applied=1000`; PIT_NEXT_LAP `applied=942`, `superseded=58`.

---

## 16. STAY_OUT activation semantics

Because S3 found very high inert rates, S4 distinguishes the **requested**
STAY_OUT from realizations where a baseline pit was actually **suppressed**.
`inert` and `baseline_pit_suppressed` are carried into the result. A near-zero
delta is explicitly **not** presented as proof that staying out is strategically
equivalent when the intervention rarely activated; the limitation is in
`StrategyComparisonResult.limitations`.

---

## 17. PIT_NOW semantics

S3 pairing cannot always separate a baseline-aligned replacement pit from a new
forced stop (both are `APPLIED`). S4 therefore documents the limitation and
carries the ordinary execution counts; it does not invent a baseline-alignment
status. The contract states that PIT_NOW can coincide with what the baseline
would have done.

---

## 18. PIT_NEXT_LAP supersession semantics

`superseded` realizations (the baseline already pitted at `L_T + 1`) are counted
separately and never counted as an applied delayed pit. On the MID anchor
PIT_NEXT_LAP is `applied=942`, `superseded=58` (5.8%) — consistent with the S3
supersession finding.

---

## 19. CRN policy

S4 uses the S3 paired / common-random-numbers substrate. The result metadata
carries `pairing_policy = "CRN_ADOPTED_WITH_LIMITATIONS"`. S4 never claims CRN
universally reduces variance; the limitation (shared stream identities, not
trajectories; event ordering may diverge) is in `limitations`.

---

## 20. Probability / counterfactual semantics

- `probability_semantics = "MONTE_CARLO_FREQUENCY"` (the frozen
  `PROBABILITY_SEMANTICS`); never `INDEPENDENT_BINARY`.
- The Phase-3 winner model is not imported or combined with S4 output (pinned
  by an AST firewall test and a runtime check).
- `counterfactual_semantics` states that the state at T is factual, the
  baseline and intervention futures are simulated, and alternative-strategy
  outcomes are counterfactual estimates — not observed ground truth. No
  historical future appears in the result.

---

## 21. Identity / determinism

`StrategyComparisonResult.identity()` composes the comparison / strategy /
intervention / candidate / paired contract versions, the state, parameter and
config identities, `master_seed`, `simulation_count`, `target_driver_id`,
`supported` / `unsupported_reason`, the pairing / delta / probability policies
and the canonically ordered candidate payloads. It contains no timestamp,
runtime, host, PID or dictionary-order dependence.

Same inputs ⇒ same identity, baseline, candidate results and diagnostics.
Changing state, parameters, config, seed, count, target or the candidate set
changes the identity.

---

## 22. Order / subset invariance

- Candidate order invariance: forward vs reversed candidate lists produce an
  identical comparison identity and identical canonical ordering.
- Subset consistency: candidate A alone equals candidate A inside an A/B/C
  comparison (identical `to_dict()`), because the candidate set affects neither
  the RNG nor the shared baseline.
- Execution-order invariance: running arms A→B→C vs C→A→B yields identical
  paired identities and per-index outcomes for each arm.
- Duplicate policy: identical `(action, compound)` specs are
  deterministic-deduplicated (first occurrence wins); they are never run twice.
  Sampled and explicit-compound candidates are distinct and are not collapsed.

---

## 23. Temporal safety

Candidate generation and comparison use only the state at T, the frozen
configuration, the empirical parameters and the user-assumption intervention.
There is no future-pit, future-compound, future-weather, final-status or oracle
input, and no `compare_strategies` argument can carry one. AST firewall tests
assert `candidates.py`, `comparison.py` and `paired.py` import no
`replay` / `prediction` / `model_lab` / `pandas` / `sklearn` module; a
signature test pins the accepted scientific inputs.

---

## 24. Performance

Representative accepted R7.1 MID anchor (2022-r01-R / perez / lap 30),
seed 20240101, `pit_dynamics_enabled=True`. Artifact values (wall seconds):

| count | candidates | compare_strategies | naive repeated `run_pair` | reuse speedup |
|---:|---:|---:|---:|---:|
| 1 000 | 9 | 11.69 s | 20.72 s | **1.77×** |
| 10 000 | 1 | 22.93 s | 24.41 s | 1.06× |
| 10 000 | 3 | 48.49 s | 69.13 s | **1.43×** |

The K=1 case has no reuse benefit by construction (2 runs either way). The
measured speedups match the structural ratio (K+1 vs 2K runs): 10 vs 18 and
4 vs 6. The nine-candidate 10 000-trial run was intentionally **not** executed
(runtime would be excessive for this gate).

---

## 25. Baseline-reuse savings

Structural: `compare_strategies(K)` = `1 baseline + K intervention`, versus the
naive S3 loop = `K baselines + K interventions`. Measured 1.77× at 1 000/9 and
1.43× at 10 000/3, consistent with run-count ratios of 10/18 and 4/6 plus the
fixed per-arm projection/aggregation cost. No theoretical speedup is claimed
beyond the measured numbers.

---

## 26. Memory

`tracemalloc` peak for comparison runs: **21.99 MB** (1 000 trials, 9
candidates) and **35.18 MB** (10 000 trials, 3 candidates). Retention is
`O(K · N · D)` compact terminal per-index records only; no trajectories are
stored regardless of race length. The public result carries aggregate values,
not the raw per-index arrays.

---

## 27. Validation artifact

`data/v2/strategy/s4_comparison_validation_v1.json`
(`s4-comparison-protocol-v1`): state/seed/counts, per-count timings, naive
comparison and reuse speedups, traced peaks, validity-denominator audit, all
candidate deltas and execution summaries, and the comparison identity. Per
repository policy `/data/v2/` is git-ignored, so the artifact is generated and
untracked; it is reproducible from `scripts/run_phase7_s4_validation.py`.

---

## 28. S1/S2/S3 regression

- S1 contracts / seam / Phase-6 compatibility: pass.
- S2 mechanics: pass.
- S3 paired (22 tests): pass.
- Authorized-drift governance: pass.
- Combined S1+S2+S3+S4+governance run: **160 passed**.

---

## 29. S4 tests

`tests/test_v2_phase7_s4_comparison.py`: **42 passed**. Coverage includes the
canonical set/order/identity, static validity (near-race-end, bad target, anchor
mismatch, unsupported compound/action, decision-lap mismatch, pit dynamics,
STAY_OUT+compound), same-compound policy, duplicate policy, single-baseline
execution, exact baseline-reuse equivalence to `run_pair`, shared-baseline
identity, candidate aggregate / complete-pair delta exactness, delta sign,
validity-denominator policy, execution-status aggregation (STAY_OUT
inertness/suppression, PIT_NEXT_LAP supersession, PIT_NOW application),
unsupported-state propagation, identity stability/sensitivity, candidate-order
invariance, subset consistency, execution-order invariance, determinism,
state/parameter/config immutability, temporal firewall, probability /
counterfactual / CRN semantics, no ranking/objective/CI, and default-off
Phase-6 compatibility.

---

## 30. Phase-6 regression

- `tests/test_v2_phase6_r8.py` (simulation API regression): pass.
- R5: pass.
- R6: 1 **pre-existing** failure (`test_pit_disabled_reproduces_r5_result_identity`)
  — a pinned identity assertion that fails on this environment (numpy 2.4.2),
  identical to the drift disclosed in the S3 report.
- R7: pass. R7.1: 6 **pre-existing** failures
  (`test_accepted_state_matches_pre_fix_result_identity[...]`) — the same
  environment-drift pinned identities disclosed in S3.
- `v2/simulation/monte_carlo.py` is byte-identical to the S3-authorized hash
  (`d2166075…09e68c68`), so these failures cannot be S4-caused; the strategy
  tests do not import any simulation test.

No Phase-6 baseline drift: the S1 compatibility fixture still reproduces and the
governance hash test passes.

---

## 31. API regression

`api/` was not modified. The Phase-6 API contract hash test and the
`POST /v2/simulations/race` route test pass (`test_v2_phase6_freeze.py`,
`test_v2_phase6_r8.py`). No strategy route exists yet (S5+).

---

## 32. Authorized drift

No new Phase-6 runtime modification. `v2/simulation/monte_carlo.py` still
matches the S3-authorized current hash; `docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json`
retains stage `S3`. The S4 candidate/validity layer imports the canonical
private validator read-only rather than changing the simulator.

---

## 33. Graphify final result

`graphify update .`: **9 379 nodes, 23 681 edges, 284 communities**. AST check:
`v2/simulation/* → v2.strategy` = **0**; no Strategy-related cycle;
`v2/strategy` imports no historical-future / oracle / Phase-3 material.

---

## 34. Scientific limitations

1. Estimates are simulator-conditional Monte Carlo frequencies; alternative
   strategy outcomes are counterfactual and not observable truth.
2. No traffic/overtaking model: positions are free-air rejoin estimates.
3. No per-compound pace delta: compounds change identity / stint grid /
   transitions only.
4. CRN shares stream identities, not trajectories; event ordering may diverge
   after the intervention, so pairing is not a universal variance reduction.
5. STAY_OUT is frequently inert; near-zero deltas are not equivalence proofs.
6. PIT_NOW can coincide with a baseline-aligned pit; execution status cannot
   always separate it from a new stop.
7. No production uncertainty is exposed (S5).
8. The validity-denominator policy is defined for mismatched valid sets even
   though the benchmark anchor showed none.

---

## 35. Git safety

Only additions/edits listed in §1; the artifact is untracked by policy. No
`reset` / `restore` / `checkout` / `clean` / `stash` / `add .` / `commit` /
`tag`. Tags `v2-monte-carlo-phase6` and `v2-frontend-foundation` preserved.
Nothing staged. S5 not started.

---

## 36. S4 definition of done

All DoD items satisfied: candidate generator, canonical set, stable identity,
explicit validity policy, unsupported-state handling, documented same-compound
policy, no future data, baseline executed once, baseline reuse exact vs S3
`run_pair`, one baseline + K arms, candidate aggregates, complete-pair deltas,
frozen delta signs, denominator policy, status counts, effective rates,
STAY_OUT inertness visible, PIT_NEXT_LAP supersession visible, PIT_NOW
limitation visible, CRN-with-limitations metadata, `MONTE_CARLO_FREQUENCY`,
counterfactual semantics, no ranking/objective/CI, canonical ordering, duplicate
policy, subset/order/execution invariance, comparison identity, determinism,
immutability, performance + memory measured, S1/S2/S3/S4 green, Phase-6 and API
regression checked, no unauthorized drift, report created, graphify updated,
`simulation → strategy = 0`, no cycle, API/frontend untouched, nothing staged or
committed, no tag, S5 not started.

Final verdict: **S4 COMPLETE — READY FOR S5**.
