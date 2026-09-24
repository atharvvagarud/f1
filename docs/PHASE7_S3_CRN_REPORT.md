# Phase 7 — S3: Paired Monte Carlo / Common Random Numbers

Status: **S3 COMPLETE — CRN ADOPTED WITH LIMITATIONS — READY FOR S4**.

This report is the S3 deliverable. S3 establishes the statistical execution
substrate required to compare ONE frozen Phase-6 baseline against ONE strategy
intervention under shared simulation identities. It deliberately does **not**
generate candidates, rank strategies, define objectives, freeze production
uncertainty, or touch the API/frontend.

Historical Phase-6 checkpoint: `b813ffe1` (`v2-monte-carlo-phase6`).
Frontend foundation: `6c04438` (`v2-frontend-foundation`).

---

## 1. Files changed

| File | Change |
|---|---|
| `v2/simulation/monte_carlo.py` | **Authorized drift.** Adds keyword-only `collect_index_outcomes=False` to `run`/`run_scalar` and `engine.last_index_outcomes`: compact terminal per-index arrays (validity, invalid reason, finish position per roster column) captured from the existing terminal batch/scalar state before aggregation. No draw, no aggregation, no identity and no default product-path change. |
| `v2/strategy/paired.py` | **New.** `PerIndexOutcome`, `PairingDiagnostics`, `PairedDifferences`, `StrategyPairedResult`, `run_pair`, `paired_differences`, `paired_result_identity`, `PAIRED_CONTRACT_VERSION`. |
| `v2/strategy/__init__.py` | Exports the S3 paired surface. |
| `docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json` | S3 authorization record (new `current_sha256`, change surface, stage `S3`). |
| `tests/test_v2_phase6_freeze.py` | Governance test now accepts stage `S3` in addition to `S1`/`S2`. |
| `tests/test_v2_phase7_s3_paired.py` | **New.** 22 focused S3 tests. |
| `scripts/run_phase7_s3_crn_validation.py` | **New.** Predeclared CRN experiment; writes the artifact. |
| `scripts/benchmark_phase7_s3_paired.py` | **New.** 1k/10k performance + memory benchmark. |
| `data/v2/strategy/s3_crn_validation_v1.json` | Generated CRN artifact. **Not tracked** (`/data/v2/` is git-ignored by repository policy; reproducible from the script). |

No other frozen Phase-6 scientific runtime file changed. `docs/PHASE6_FREEZE_MANIFEST.json`
is untouched. Nothing is staged, committed or tagged.

---

## 2. Graphify pre-audit

Pre-edit `graphify query` over the simulation package located `MonteCarloEngine`,
`_ChunkEvolution`, the R5/R6 kernels and the aggregation path. The audit
identified the **narrowest** place to capture per-index outcomes: the existing
terminal batch state inside `MonteCarloEngine.run`'s aggregation loop, where
`evolution.lap`/`evolution.rtime` are already ranked. No second simulation
implementation, no scalar replay, no trajectory history. Proposed dependency
direction: `v2.strategy -> v2.simulation` (unchanged).

Post-edit `graphify update .`: **9 229 nodes, 23 123 edges, 299 communities**.
AST dependency check: `v2/simulation/*` imports of `v2.strategy` = **0**;
`v2/strategy` internal edges `__init__ → {contracts, interventions, paired}`,
`interventions → contracts`, `paired → {contracts, interventions}`; **no cycle**.

---

## 3. Per-simulation outcome contract

`v2.strategy.paired.PerIndexOutcome` (frozen) retains only values genuinely
available from simulation, never full trajectories:

- `simulation_index`
- `valid`
- `winner_driver_id` (`None` when invalid)
- `finishing_order` (empty when invalid)
- `target_finish_position` (`None` when invalid)
- `target_won`, `target_podium` (`None` when invalid)
- `intervention_status`, `intervention_reason` (`None` for the baseline arm)

Invalid trajectories are never imputed. Retention is `O(N·D)` compact ints, not
`O(N·laps)`. `MonteCarloResult` is **not** modified to carry pairing data.
`run_pair` already requires that both arms request per-index collection, so no
Phase-6 product path changes.

---

## 4. Paired runner architecture

`run_pair(state, parameters, config, assumptions, intervention)` executes:

1. baseline `MonteCarloEngine.run(..., intervention=None, collect_index_outcomes=True)`;
2. intervention `MonteCarloEngine.run(..., intervention=intervention, collect_index_outcomes=True)`;
3. projects both arms' raw arrays into `PerIndexOutcome` tuples;
4. builds `PairingDiagnostics` and the paired identity.

One baseline + one intervention per call. No candidate generation. Baseline and
intervention reuse the identical `state`, `parameters`, `config` and engine; the
only intentional scientific difference is the intervention. The per-index data
comes from the **actually executed** batch trajectories.

---

## 5. Paired identity

`StrategyPairedResult.identity()` composes: `paired_contract_version`,
`strategy_contract_version`, `intervention_version`, `state_identity`,
`parameter_identity`, `config_identity`, `master_seed`, `simulation_count`,
`target_driver_id`, `intervention_identity`, both arm result identities, both
per-index outcome digests, and the diagnostics. No timestamp, runtime, dict
order or memory address. Tests pin stability and sensitivity to intervention,
seed, count, state and compound.

---

## 6. RNG-domain analysis (shared-randomness contract)

Each simulation index `i` runs on the per-`(master_seed, i)` stream identities;
that is what CRN shares.

| Domain | Stream | Draws | CRN classification |
|---|---|---|---|
| pace/residual | `rng_for_simulation(seed, i)` | 1 per scheduled next-lap completion, global event order | stream `SHARED_BY_INDEX`; attached values `SHARED_UNTIL_DIVERGENCE`, then `EVENT_ORDER_DEPENDENT` |
| pit_timing | `rng_for_domain(seed, i, "pit_timing")` | `D` initial targets + 1 per pit | `SHARED_UNTIL_DIVERGENCE` |
| compound | `rng_for_domain(seed, i, "compound")` | 1 per pit, **always consumed even under explicit override** | `SHARED_UNTIL_DIVERGENCE` |
| pit_loss | `rng_for_domain(seed, i, "pit_loss")` | 1 per pit | `SHARED_UNTIL_DIVERGENCE` |
| reliability | `rng_for_domain(seed, i, "reliability")` | none (`reliability_enabled=True` rejected) | `UNUSED/RESERVED` |
| intervention decision | none (deterministic) | force/suppress/supersede at the target's own completion | `INTERVENTION_SPECIFIC` |

Paired arms therefore share **stochastic stream identities**, not trajectories.
Once the intervention changes race timing, event ordering, event counts,
residual-to-event assignment, pit sequences and finishing order may all differ.
This is documented precisely because it bounds the CRN claim.

---

## 7. Pre-divergence invariance

- **PIT_NOW** acts at the target's own `L_T + 1`; divergence begins there.
- **PIT_NEXT_LAP** leaves `L_T + 1` baseline-normal and forces at `L_T + 2`
  unless a baseline pit at `L_T + 1` supersedes it.
- **STAY_OUT** suppresses the baseline decision at `L_T + 1` (one event only).
- Where the baseline already pits at the decision event, PIT_NOW is
  **baseline-aligned** (replacement, not a second stop) and the arms are
  byte-identical with a null compound. Where PIT_NEXT_LAP is superseded, the
  intervention trajectory equals the baseline. Where STAY_OUT is inert, the
  intervention trajectory equals the baseline.

These boundaries are pinned by tests (see §17).

---

## 8. Divergence diagnostics

`PairingDiagnostics` reports `pairs_total`, `pairs_both_valid`,
`baseline_only_valid`, `intervention_only_valid`, `both_invalid`,
`intervention_applied`, `intervention_suppressed`, `intervention_superseded`,
`intervention_inert` (STAY_OUT reached its event with no baseline pit to
suppress) and `race_end_cancelled`. First-divergence trajectory logging is
deliberately **not** built; the goal is statistical auditability, not trajectory
forensics.

---

## 9. Valid / invalid pair policy

Invalid simulations are never dropped silently and never imputed. Every index
falls in exactly one bucket. Raw paired differences use **complete valid pairs
only**; each arm's aggregate probabilities still use that arm's own valid set
(Phase-6 semantics unchanged).

---

## 10. Raw paired differences and sign semantics

- `d_win_i = I(intervention wins) − I(baseline wins)` (+1 = intervention better).
- `d_podium_i` the same for podium.
- `d_finish_i = baseline_finish_position − intervention_finish_position`
  (+ = intervention improved/lowered the position; − = worsened).

These are raw observations, not recommendations. `paired_differences()` returns
the tuples plus means and sample variances.

---

## 11. Aggregate reproduction

Per-index outcomes reproduce each arm's aggregate **exactly** (bit-for-bit):
mean win indicator == `win_probability`, mean podium indicator ==
`podium_probability`, mean target finish == `expected_finish`, and position
counts == the stored `finish_position_distribution`. Verified by dedicated
tests and asserted for all 150 experiment configurations
(`all_aggregates_reproduce = true`).

---

## 12. STAY_OUT inert behavior

With the accepted anchors the target usually was not due to pit at `L_T + 1`;
STAY_OUT then suppresses nothing. Inert fractions are 98.9% (EARLY), 94.1%
(MID) and 97.3% (LATE) of trials. Inert realizations are retained (not
discarded) and recorded as `intervention_inert`; the intervention trajectory is
baseline-equivalent.

---

## 13. PIT_NOW baseline-aligned behavior

When the baseline is already due at `L_T + 1`, PIT_NOW replaces that single
decision rather than adding a stop. With a null compound the draw order is
identical and the arms are byte-identical (pinned by test), so PIT_NOW is not
assumed to always create a new stop.

---

## 14. PIT_NEXT_LAP supersession behavior

If the baseline pits at `L_T + 1`, the forced `L_T + 2` pit is `SUPERSEDED`
(`intervention_superseded_by_baseline_pit`); the pair is retained and the
intervention trajectory is baseline-equivalent. Supersession rates: 1.13%
(EARLY), 5.95% (MID), 2.73% (LATE) of PIT_NEXT_LAP trials; 1 962 superseded
pairs overall (out of 150 000).

---

## 15. Explicit-compound cursor alignment

S2 always consumes the baseline `compound` draw even when an explicit compound
overrides it. S3 verifies this keeps the compound-domain cursor aligned: after
a forced pit with an explicit compound, the **next** ordinary pit reads the
subsequent uniform (pinned by a monkeypatched two-target test). What stays
aligned: the number and order of compound/pit_loss/pit_timing draws per pit.
What still diverges: the pace/residual stream's event-to-uniform assignment
once timing changes, plus all downstream event ordering.

---

## 16. Scalar oracle parity

For selected indices, batch-collected per-index outcomes equal the scalar
oracle's `run_scalar(..., collect_index_outcomes=True)` arrays (validity,
finish positions, invalid reasons) for both arms, and the arm identities match.
The scalar path is used only as a parity oracle; the experiment itself is
batch-only.

---

## 17. Chunk / prefix / order invariance and determinism

- **Chunk invariance:** identical paired identity for chunk sizes 1, 7, 64, 512.
- **Prefix invariance:** the first `k` per-index outcomes match between an
  `N`-run and a `k`-run at the same seed.
- **Run-order invariance:** baseline→intervention and intervention→baseline
  produce identical per-index arrays for each arm (no RNG state leaks).
- **Determinism:** repeated `run_pair` calls yield identical identities and
  per-index outcomes.
- **Immutability:** `state`, `parameters` and the intervention are unchanged.
- **No future data:** `paired.py` imports no replay/validation/prediction/oracle
  module; `run_pair` accepts only scientific inputs.

---

## 18. CRN validation protocol (predeclared)

Protocol `s3-crn-protocol-v1`; artifact `data/v2/strategy/s3_crn_validation_v1.json`.

- States: R7.1 accepted anchors **EARLY** (2023-r01-R, alonso, lap 2),
  **MID** (2022-r01-R, perez, lap 30), **LATE** (2022-r01-R, russell, lap 38).
- Actions: STAY_OUT; PIT_NOW (null, SOFT); PIT_NEXT_LAP (null, HARD).
- Count: 1 000 trajectories per run.
- Seeds: predeclared `(20240101, 7, 11, 101, 202, 303, 404, 505, 606, 707)`.
- Paired arm: baseline seed `S`, intervention seed `S`.
- Independent arm: baseline seed `S` (reused), intervention seed
  `S2 = (S·6364136223846793005 + 1442695040888963407) mod 2^63`.

Estimator per seed: paired = mean raw difference over complete valid pairs;
independent = difference of arm aggregates. Variance ratio
`VR = Var(paired) / Var(independent)` across the seed set.

Predeclared decision policy (fixed before running, not tuned): adopt if
median `VR ≤ 0.95`, ≥ 80% of defined cases `< 1`, and no material bias;
adopt-with-limitations if median `< 1` but mixed; no-benefit if median in
`[0.95, 1.05]`; unsafe if median `≥ 1.05` or material bias.

---

## 19. Paired vs independent results

All 150 configurations (3 states × 5 action/compound cells × 10 seeds),
150 000 complete valid pairs; every arm aggregate reproduced.

| stage | action | compound | VR win | VR podium | VR finish | sup / inert |
|---|---|---|---:|---:|---:|---:|
| EARLY | STAY_OUT | null | n/a | 0.000 | 0.006 | 0 / 9 887 |
| EARLY | PIT_NOW | null | n/a | 0.552 | 0.322 | 0 / 0 |
| EARLY | PIT_NOW | SOFT | n/a | 1.000 | 1.068 | 0 / 0 |
| EARLY | PIT_NEXT_LAP | null | n/a | 0.400 | 0.684 | 113 / 0 |
| EARLY | PIT_NEXT_LAP | HARD | n/a | 1.000 | 2.214 | 113 / 0 |
| MID | STAY_OUT | null | 0.041 | 0.032 | 0.080 | 0 / 9 405 |
| MID | PIT_NOW | null | 0.537 | 0.525 | 0.970 | 0 / 0 |
| MID | PIT_NOW | SOFT | 0.837 | 1.071 | 1.487 | 0 / 0 |
| MID | PIT_NEXT_LAP | null | 0.286 | 2.150 | 2.615 | 595 / 0 |
| MID | PIT_NEXT_LAP | HARD | 0.371 | 1.760 | 2.867 | 595 / 0 |
| LATE | STAY_OUT | null | 0.000 | 0.000 | 0.016 | 0 / 9 727 |
| LATE | PIT_NOW | null | n/a | 0.869 | 0.284 | 0 / 0 |
| LATE | PIT_NOW | SOFT | n/a | 0.971 | 0.482 | 0 / 0 |
| LATE | PIT_NEXT_LAP | null | n/a | 0.904 | 0.832 | 273 / 0 |
| LATE | PIT_NEXT_LAP | HARD | n/a | 0.842 | 0.719 | 273 / 0 |

`n/a` = variance ratio undefined because both estimators are constant (no
variation across seeds), which is reported rather than forced to zero.

---

## 20. Variance ratios summary

- Defined ratios: 36 of 45 metric cells.
- Median **0.702**; min `0.0` (paired variance exactly zero); max `2.867`.
- Below 1: **72.2%**; at or below 0.95: **66.7%**.
- By action (median VR): STAY_OUT `0.011`, PIT_NOW `0.853`, PIT_NEXT_LAP `0.873`.

Pairing materially reduces estimator variance where the intervention is
STAY_OUT (and generally for PIT_NOW with a null compound), is roughly neutral
to mildly helpful for PIT_NOW/PIT_NEXT_LAP with explicit compounds, and is
occasionally **worse** (VR up to 2.87) once the trajectories diverge strongly
and the paired difference loses its shared-environment benefit. That mix is why
the decision is not an unqualified adoption.

---

## 21. Correlation diagnostics

Pearson correlation of baseline vs intervention outcomes over complete valid
pairs (per-config seed means; correlations are reported `undefined` under
constant outcomes rather than forced to zero):

- finish position: defined in 15/15 configs, mean `r ≈ 0.264`;
- podium indicator: defined in 11/15 configs, mean `r ≈ 0.331`;
- win indicator: defined in 5/15 configs, mean `r ≈ 0.320`.

The modest positive correlation is consistent with shared streams surviving
partial divergence.

---

## 22. Bias check

Paired and independent estimators agree closely. Maximum absolute seed-mean
difference across all metric cells is **0.088** (EARLY PIT_NOW SOFT, finish;
the other cells are `< 0.08`). The predeclared conservative bias rule (flag if
a seed-mean difference exceeds 4 standard errors of the independent seed-mean)
detected **no material bias**. Reported as actual differences, not significance
theatre.

---

## 23. CRN decision

`ADOPT_CRN_WITH_LIMITATIONS`.

Rationale: pairing is mechanically valid, aggregate reproduction is exact, no
bias or invariance violation was found, and the median variance ratio is well
below 1 — but the effect is mixed: roughly one third of defined cases show no
improvement (VR ≥ 0.95) and a minority are worse than independent sampling
under strong divergence. S4/S5 may use paired/CRN execution, but must not
globally claim "CRN reduces variance" and should keep the independent-vs-paired
distinction visible where the evidence is mixed.

---

## 24. Performance

Representative MID anchor (2022-r01-R / perez / lap 30), seed 20240101,
`PIT_NOW` null compound:

| count | baseline aggregate | paired baseline+intervention | overhead | paired per sim |
|---:|---:|---:|---:|---:|
| 1 000 | 1.10 s | 3.56 s | 3.24× | 3.56 ms |
| 10 000 | 10.91 s | 35.04 s | 3.21× | 3.50 ms |

Paired execution performs **two** simulations, so ~2× is expected; the extra
~1.2× is per-index projection into immutable `PerIndexOutcome` records. This is
not an optimization regression, but it is a documented S4 candidate for lazy or
vectorized projection. No pathological overhead was observed.

---

## 25. Memory

Traced `tracemalloc` peak for the paired run (both arms, per-index retention):
**20.9 MB** at 1 000 trials and **27.0 MB** at 10 000 trials. Process peak-RSS
delta for an aggregate-only run is ~13 MB. Retention is `O(N·D)` terminal
records only; no trajectory histories are stored regardless of race length.

---

## 26. Temporal safety

Pairing derives only from the state at T, the frozen parameters, the config,
the `(seed, index)` identities, the intervention and the simulated outcomes.
No historical finishing order is an input. Real anchors use the point-in-time
state and parameters fit strictly before the target season. `paired.py` imports
no replay/oracle module.

---

## 27. Default-off Phase-6 compatibility

`collect_index_outcomes` defaults to `False` and `intervention` to `None`: the
Phase-6 product path is byte-identical and `last_index_outcomes` stays `None`.
The S1 compatibility fixture (`tests/fixtures/phase7_s1_phase6_baseline.json`,
captured on this environment before S3) still reproduces exactly, and the S2
scalar/batch parity tests still pass.

---

## 28. Authorized drift

`docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json` now records stage `S3`,
`current_sha256` `d2166075e2d4b90bf4604ac3d586fe4d07f1ae577cb413ec8991317309e68c68`
for `v2/simulation/monte_carlo.py`, with the bounded S3 change surface. No other
Phase-6 scientific runtime file drifted; the governance hash test passes.

---

## 29. Regression verification

- S1 contracts/seam/compat: pass (fixture unchanged).
- S2 mechanics: pass.
- S3 paired: 22 tests pass.
- Authorized-drift governance: pass.
- Relevant Phase-6: R5 all pass; R6/R7/R7.1 pass except a set of **pre-existing**
  pinned-identity assertions that fail identically on the pre-S3 runtime in this
  environment (numpy 2.4.2). This is environment drift recorded before S3, not
  Phase-6 baseline drift from S3; the S1 compatibility fixture captured on this
  same environment passes byte-for-byte. See §31.
- Simulation API regression (`tests/test_v2_phase6_r8.py`): pass.
- Full repository suite was **not** run (per S3 verification level).

---

## 30. CRN artifact

Machine-readable: `data/v2/strategy/s3_crn_validation_v1.json`
(`s3-crn-protocol-v1`). It records the protocol, states/races/stages, actions,
compounds, count, seeds, paired and independent estimator values, variance
ratios, bias differences, correlations, supersession/inert counts, validity
counts, decision, policy and limitations. Per repository policy `/data/v2/` is
git-ignored, so the artifact is **generated and untracked**; it is reproducible
from `scripts/run_phase7_s3_crn_validation.py`.

---

## 31. Scientific limitations

1. The variance ratio is measured on a predeclared but finite seed set, so the
   ratios themselves are noisy.
2. Several metric cells have undefined variance ratios (both estimators
   constant); these are reported as `n/a`, not as a benefit.
3. CRN does not survive strong divergence: a minority of PIT_NOW/PIT_NEXT_LAP
   explicit-compound cases show VR > 1.
4. Counterfactual levels remain unobservable truth; S3 validates machinery, not
   realised intervention outcomes.
5. Explicit compounds change only compound identity / stint grid / future
   transitions; Phase-6 has no identified per-compound pace delta, so compound
   effects are small and noise-dominated.
6. The pre-existing pinned R5/R7.1 identity drift in this environment is outside
   S3's control and is disclosed, not hidden.
7. Per-index projection adds ~1.2× cost over the two simulations; acceptable for
   S3, optimizable in S4 if needed.

---

## 32. Git safety

Only additions/edits listed in §1; `data/v2/strategy/s3_crn_validation_v1.json`
is untracked by policy. Nothing staged, nothing committed, no tag. S4 is not
started.
