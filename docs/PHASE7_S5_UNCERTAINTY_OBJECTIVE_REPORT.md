# Phase 7 — S5: Uncertainty + Explicit Objective Policy

Status: **S5 COMPLETE — READY FOR S6**.

S5 adds two things to the S4 comparison layer:

1. statistically defensible **Monte Carlo sampling uncertainty** for strategy
   differences (paired SE + deterministic paired percentile bootstrap CI), and
2. explicit **user-selected objective semantics** (three single-metric
   objectives, direct candidate-vs-candidate pairing, point-estimate ordering
   with an indistinguishable-from-leader set).

S5 does **not** claim the historically optimal counterfactual strategy,
real-world causal certainty, or superiority beyond simulator assumptions. It
reruns **no** simulation: every value is derived from the per-index terminal
outcomes the S4 comparison already retains.

Historical Phase-6 checkpoint: `b813ffe1` (`v2-monte-carlo-phase6`).
Frontend foundation: `6c04438` (`v2-frontend-foundation`).
S3 decision inherited: `ADOPT_CRN_WITH_LIMITATIONS`.
S4 decision inherited: complete-valid-pair comparison estimand, frozen delta
signs, no ranking/objective/uncertainty.

---

## 1. Files changed

| File | Change |
|---|---|
| `v2/strategy/uncertainty.py` | **New.** `UNCERTAINTY_VERSION`, paired SE, unpaired diagnostic, deterministic paired percentile bootstrap, `UncertaintyResult`, metric/orientation helpers, candidate and pairwise wrappers. |
| `v2/strategy/objectives.py` | **New.** `OBJECTIVE_VERSION`, exactly three objectives, baseline-relative classification, direct candidate-vs-candidate pairing, point-estimate ordering and leader semantics, execution context. |
| `v2/strategy/comparison.py` | **Narrow additive retention.** `CandidateComparison.intervention_outcomes` and `StrategyComparisonResult.baseline_outcomes` now retain the compact terminal per-index outcomes S4 already generated (`repr=False`, `compare=False`, absent from `to_dict()` and identity). No S4 delta, identity, ordering or public payload changed. |
| `v2/strategy/__init__.py` | Exports the S5 surface. |
| `tests/test_v2_phase7_s5_uncertainty.py` | **New.** 28 focused S5 uncertainty tests. |
| `tests/test_v2_phase7_s5_objectives.py` | **New.** 26 focused S5 objective/integration tests. |
| `scripts/run_phase7_s5_validation.py` | **New.** Real EARLY/MID/LATE + 1k/10k + performance/memory experiment; writes the artifact. |
| `data/v2/strategy/s5_uncertainty_validation_v1.json` | Generated artifact. **Untracked** (`/data/v2/` is git-ignored by repository policy; reproducible from the script). |

No frozen Phase-6 scientific runtime file changed. `v2/simulation/monte_carlo.py`
still matches its S3-authorized hash `d2166075…09e68c68`;
`docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json` and
`docs/PHASE6_FREEZE_MANIFEST.json` are untouched (no new drift). No API or
frontend file changed. Nothing is staged, committed or tagged.

---

## 2. Graphify pre-audit

Pre-edit `graphify query "strategy uncertainty objective candidate ordering
decision interpretation"` located the Strategy community (candidates,
comparison, paired, contracts, interventions) and confirmed the single
dependency direction `v2.strategy → v2.simulation`. The audit identified the
narrowest additive layers:

- a Strategy-owned `uncertainty.py` (estimand/SE/bootstrap, reading S4
  per-index outcomes only);
- a Strategy-owned `objectives.py` (single-metric objective view over a
  `StrategyComparisonResult`);
- one narrow Strategy-owned retention change in `comparison.py`, because S4
  discarded the `StrategyPairedResult` after building each comparison and the
  public result carried no per-index data.

Expected file surface was `v2/strategy/uncertainty.py` +
`v2/strategy/objectives.py` + a narrow `comparison.py` retention + `__init__`
exports + tests/script/docs/artifact. No simulation science change.

---

## 3. Uncertainty architecture

`v2/strategy/uncertainty.py` is a pure analysis layer over the retained
terminal outcomes. It exposes:

- `UNCERTAINTY_VERSION = "v1"`, `UNCERTAINTY_SEMANTICS =
  "MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY"`;
- `metric_value(outcome, metric)` — per-index objective outcome with positive =
  improvement orientation;
- `compute_uncertainty(baseline_outcomes, candidate_outcomes, *, metric,
  substrate_identity, subject_identity, bootstrap_replicates, confidence_level,
  bootstrap_seed_root, include_unpaired)`;
- `candidate_uncertainty(comparison, candidate_comparison, metric)` and
  `pairwise_uncertainty(comparison, candidate_a, candidate_b, metric)`;
- `comparison_substrate_identity(comparison)` and
  `derive_bootstrap_seed(...)`;
- `UncertaintyResult` (immutable, canonically serializable, stable identity).

**Data-lifetime audit.** S4 previously returned only compact candidate results;
the per-index outcomes existed transiently inside `pair_arms` and were dropped.
S5 therefore extends `comparison.py` **narrowly**: the already-generated
candidate `intervention_outcomes` and the one shared `baseline_outcomes` are
retained on the immutable S4 result. They are excluded from `to_dict()` and from
`StrategyComparisonResult.identity()`, so no S4 public payload, delta, ordering
or identity changes (all 42 S4 tests still pass). Retention is
`O((K+1)·N)` compact terminal records; no trajectories. No new simulation, no
serialization of histories.

**Index alignment.** Pairs are aligned explicitly by `simulation_index`
(every arm is generated from the same config and per-`(seed, index)` substrate),
never by list position. This makes candidate-vs-baseline and candidate-vs-
candidate pairing well defined without rerunning anything.

---

## 4. Canonical estimand

Frozen S4 signs are reused unchanged. For candidate `c` and metric `m`:

```
d_i = o_candidate_i − o_baseline_i        over complete valid pairs
```

with `o` oriented so positive always means improvement:

| Metric | `o` |
|---|---|
| `WIN_PROBABILITY` | `I(driver wins)` |
| `PODIUM_PROBABILITY` | `I(driver podiums)` |
| `EXPECTED_FINISH` | `−finish_position` |

`delta_hat = mean(d_i)` reproduces the S4 canonical candidate delta exactly.
The artifact asserts `point_estimate_reproduces_s4 = true` for all three states
(all three objectives, every evaluated candidate with `n > 0`); the S5 test
`test_s5_point_estimate_reproduces_s4_delta_exactly` pins it bit-for-bit.

The `n = 0` case is the only exception: S4's `paired_differences` returns a
degenerate `0.0` empty-sum sentinel, while S5 reports the mean over zero pairs as
genuinely **undefined** (`point_estimate = None`, `availability = NO_VALID_PAIRS`,
`unavailable_reason = "no_valid_pairs"`). This is documented and never produced
for a non-empty set.

---

## 5. Paired standard error

```
SE_paired = sample_std(d_i, ddof=1) / sqrt(n)
```

The sample variance is computed with the same arithmetic order as S4's
`paired_differences`, so the point estimate and variance are consistent with the
frozen estimand. Explicit handling:

- `n = 0` → point estimate, SE and interval `None`; `NO_VALID_PAIRS`.
- `n = 1` → point estimate defined; `SE = None` (ddof=1 undefined);
  `INSUFFICIENT_PAIRS`.
- constant `d_i` → `SE = 0.0` exactly (mathematically valid).

`UncertaintyResult` never carries a NaN: every undefined field is `None` plus a
structured reason/availability.

---

## 6. Unpaired diagnostic

A non-canonical diagnostic is computed from the two arms independently: the
baseline-metric sample variance over the baseline's own valid set and the
candidate-metric sample variance over the candidate's own valid set,

```
SE_unpaired = sqrt(var_base / n_base + var_candidate / n_candidate)
```

with `se_ratio = paired_se / unpaired_se` where `unpaired_se` is defined and
non-zero. This is exposed only to make the pairing effect visible; the canonical
uncertainty remains paired because the estimand is paired. The ratio is never
used to select "the smaller SE".

---

## 7. Bootstrap contract

- **Unit:** the complete simulation pair. Baseline and candidate are never
  resampled independently; each replicate resamples `n` pair indices with
  replacement from the same paired difference vector.
- **Replicates:** `B = 2000` (`DEFAULT_BOOTSTRAP_REPLICATES`).
- **Level:** 95% (`DEFAULT_CONFIDENCE_LEVEL = 0.95`).
- **Quantile method:** pinned `numpy.quantile(..., method="linear")`
  (`QUANTILE_METHOD`); NumPy 2.4.2 behavior is pinned by an exact regression
  test and an independent in-test reimplementation.
- **Interval:** 2.5th and 97.5th percentiles of the replicate means.
- **Memory:** the replicate loop bounds peak memory at `O(n)` (never
  `O(B · n)`).

```
CI_semantics = "a Monte Carlo resampling interval for the estimated paired
simulation delta", never a confidence interval for the true real-world causal
effect of the pit strategy.
```

This is stated verbatim in the module, the report and the artifact limitations.

---

## 8. Bootstrap determinism / identity

**Separate RNG.** The bootstrap uses a Strategy statistical-analysis
`numpy.random.default_rng` stream and a Strategy-owned seed. It never touches the
simulation, pit-timing, pace/residual, compound or pit-loss RNG. Changing the
bootstrap seed root changes only the interval; it cannot change a simulated
outcome. Changing the simulation seed changes the paired observations and hence
the interval (expected).

**Seed derivation.** `bootstrap_seed = H(bootstrap_seed_root, substrate_identity,
subject_identity, metric, uncertainty_version)` truncated to 64 bits, where
`substrate_identity` excludes the candidate payload (state/parameter/config
identity, master seed, count, target). Therefore:

- per candidate/metric and per candidate-pair/metric the stream is independent
  (no mutable RNG shared across candidate iteration);
- candidate A's bootstrap stream is unchanged whether A is evaluated alone or
  among nine candidates (subset consistency).

**Identity.** `UncertaintyResult.identity()` includes the uncertainty version,
semantics, CI method, quantile method, metric, substrate identity, subject
identity, availability/reason, complete-pair count, confidence level, replicate
count, bootstrap seed and the numeric estimates. No runtime, timestamp or
dictionary order.

---

## 9. Small-n / constant-difference policy

Production default is 1 000 trajectories; lower complete-pair counts arise only
from invalid simulations. The chosen, documented policy:

- `MIN_VALID_PAIRS_FOR_CI = 30`. Below 30 complete pairs a percentile bootstrap
  interval is unstable and is **withheld** (`INSUFFICIENT_PAIRS`,
  `unavailable_reason = "insufficient_complete_pairs"`). The point estimate and
  (when `n >= 2`) the paired SE are still reported. `n = 0` is
  `NO_VALID_PAIRS`.
- **Constant difference:** `SE = 0`, and the bootstrap interval legitimately
  collapses to `[d, d]`. The metadata still states sampling-uncertainty-only;
  a zero SE is never translated into "certain strategy advantage", and a
  constant zero is classified `INCONCLUSIVE` ("no Monte Carlo difference
  observed"), never "equivalent in reality".

---

## 10. CI semantics

The interval describes how precisely the paired simulation delta has been
estimated under Monte Carlo sampling. It is not parameter, model-form,
pit-loss, pace, traffic, compound-effect, future-weather or real-world
counterfactual uncertainty. It is not a hypothesis test: no p-value, no
significance and no multiple-comparison correction are produced. Pairwise
intervals are exploratory diagnostics, not a family-wise inferential procedure.

---

## 11. Objective contract

`v2/strategy/objectives.py` defines exactly three objectives and no weighted
score:

```
MAXIMIZE_WIN_PROBABILITY    -> WIN_PROBABILITY
MAXIMIZE_PODIUM_PROBABILITY -> PODIUM_PROBABILITY
MINIMIZE_EXPECTED_FINISH    -> EXPECTED_FINISH
```

- `StrategyObjective` is an explicit enum; `objective_value` rejects anything
  else.
- `evaluate_objective(comparison, objective, ...)` has **no default objective**;
  the caller must select it. Comparison without an objective remains valid (S4).
- Every objective selects exactly ONE existing canonical paired metric. Metrics
  are never combined (`0.5·win + …`, `utility`, `strategy_score` do not exist).
- `StrategyObjectiveResult` is an immutable additive view with
  `candidate_evaluations`, `point_estimate_order`, `baseline_relative_counts`,
  `pairwise_comparisons`, `leader_by_point_estimate`,
  `indistinguishable_from_leader`, `distinguishable_from_leader`, explicit
  sampling semantics and limitations, plus a stable identity.
- An unsupported S4 comparison yields an empty objective result
  (`comparison_supported = False`), never a fabricated one.

`OBJECTIVE_VERSION = "v1"`. A bump is required if the objective set,
objective→metric mapping, classification rule, candidate-vs-candidate method or
leader semantics change.

---

## 12. Objective mappings

Each objective reuses the canonical paired delta already oriented positive =
improvement, so all three share one direction (higher is better). For
`MINIMIZE_EXPECTED_FINISH` the canonical `baseline_finish − candidate_finish`
orientation is preserved; no sign is flipped in the objective layer.

---

## 13. Baseline-relative classification

For candidate `c` against the shared baseline, using the candidate's own paired
difference distribution (complete valid pairs):

| Condition | Classification |
|---|---|
| CI low > 0 | `IMPROVEMENT` |
| CI high < 0 | `DEGRADATION` |
| otherwise | `INCONCLUSIVE` |
| interval withheld / `n = 0` | `UNCERTAINTY_UNAVAILABLE` |

Baseline is the reference (`baseline_reference_value = 0.0`), not another
candidate. A candidate may be worse than baseline; all candidates being
`INCONCLUSIVE`/`DEGRADATION` is a valid result and no intervention is forced to
be preferred.

---

## 14. Direct candidate-vs-candidate comparison

Separate baseline-relative intervals are **never** compared by CI overlap. For
candidates A and B the direct paired difference is built on the same simulation
indices:

```
d_AB_i = o_A_i − o_B_i     (positive = A improves over B)
```

and classified with the same 95% paired bootstrap rule. This is scientifically
preferable and is what `PairwiseObjectiveComparison` records. A dedicated test
builds A and B whose baseline-relative intervals overlap but whose direct
A-vs-B difference is an exact constant, proving the direct method is used rather
than an overlap heuristic.

Maximum candidate count is 9, so there are at most 36 pairwise comparisons.
No simulation is rerun; the retained per-index outcomes are reused.

---

## 15. Pairwise validity policy

For candidate A vs B the denominator is the candidate A/B complete valid set:

```
both_valid, a_only_valid, b_only_valid, both_invalid
```

Baseline validity is **not** required for A-vs-B and is not mixed in. Candidate-
vs-baseline uses the S4 complete-valid-pair set. Denominators are explicit and
never silently mixed.

---

## 16. Point-estimate ordering / leader semantics

`point_estimate_order` sorts evaluated candidates by descending point estimate,
breaking exact ties by canonical candidate order (a display tie-break only, not
a scientific equivalence). `leader_by_point_estimate` is the first entry.
`indistinguishable_from_leader` lists candidates whose direct pairwise interval
does not distinguish them from the leader (`INCONCLUSIVE` or
`UNCERTAINTY_UNAVAILABLE`); `distinguishable_from_leader` lists the rest. The
leader is a simulator point-estimate label only — there is no
`best_strategy` field and no recommendation.

---

## 17. Inert / superseded context

Each `CandidateObjectiveEvaluation` carries the S4 execution summary
(`applied_rate`, `suppressed_rate`, `superseded_rate`, `inert_rate`,
`race_end_cancelled_rate`). On the MID 1 000-trial anchor:

| Candidate | applied | suppressed | superseded | inert |
|---|---:|---:|---:|---:|
| `STAY_OUT` | 0.000 | 1.000 | 0.000 | **0.942** |
| `PIT_NOW` (all compounds) | 1.000 | 0.000 | 0.000 | 0.000 |
| `PIT_NEXT_LAP` (all compounds) | 0.942 | 0.000 | 0.058 | 0.000 |

A near-zero STAY_OUT delta with 94.2% inert realizations is reported as such and
is explicitly **not** presented as evidence that staying out has no effect.

---

## 18. Synthetic validation

`tests/test_v2_phase7_s5_uncertainty.py` (28 tests) and
`tests/test_v2_phase7_s5_objectives.py` (26 tests) pin, with hand-computed
reference values:

- paired point estimate and SE against manual arithmetic; unpaired SE and
  `se_ratio`;
- `n = 0`, `n = 1`, `n < 30`, constant zero / positive / negative, sparse and
  constant win/podium, numeric finish;
- complete valid pair denominator and invalid-pair exclusion;
- bootstrap determinism, an exact pinned result
  (`seed 17267596991454761751`, `CI = [0.3333333333333333, 0.7]` for a fixed
  vector) and an independent in-test reimplementation;
- bootstrap seed isolation per metric/subject and seed-root isolation of the
  interval from the observations;
- classification improvement/degradation/inconclusive/unavailable;
- direct pairwise A>B, A<B, A=B, explicit A/B validity counts, and the direct
  method vs CI-overlap;
- objective mappings, no default objective, no weighted score, ordering, leader
  ambiguity, all-worse and all-inconclusive results, inert/superseded context,
  order/subset/pairwise-subset invariance, determinism and identity stability.

---

## 19. EARLY / MID / LATE validation

Real accepted R7.1 anchors, seed `20240101`, 1 000 trajectories, all canonical
valid candidates (9), all three objectives. `point_estimate_reproduces_s4 =
true` for all three states.

| Stage | Objective | IMPROVE | DEGRADE | INCONCLUSIVE | Leader | Indist. from leader |
|---|---|---:|---:|---:|---|---:|
| EARLY | WIN | 0 | 0 | 9 | STAY_OUT | 8 |
| EARLY | PODIUM | 0 | 0 | 9 | STAY_OUT | 8 |
| EARLY | FINISH | 0 | 8 | 1 | STAY_OUT | 0 |
| MID | WIN | 0 | 8 | 1 | STAY_OUT | 0 |
| MID | PODIUM | 0 | 8 | 1 | STAY_OUT | 0 |
| MID | FINISH | 0 | 8 | 1 | STAY_OUT | 0 |
| LATE | WIN | 0 | 0 | 9 | STAY_OUT | 8 |
| LATE | PODIUM | 0 | 8 | 1 | STAY_OUT | 0 |
| LATE | FINISH | 0 | 8 | 1 | STAY_OUT | 0 |

No thresholds or results were tuned. On these anchors the forced pit / delayed
pit candidates are not distinguishable improvements over baseline, and
`STAY_OUT` (the near-baseline candidate) is the point-estimate leader. Pairwise
status counts (36 comparisons/stage) mix `IMPROVEMENT`/`DEGRADATION`/
`INCONCLUSIVE`; e.g. MID FINISH is `DEGRADATION 16 / IMPROVEMENT 16 /
INCONCLUSIVE 4`. Example SE/CI (MID, WIN): `PIT_NOW:SAMPLED` `pe = −0.055`,
`paired_se = 0.0122`, CI `[−0.080, −0.031]`, `DEGRADATION`. Example (MID,
FINISH): `STAY_OUT:SAMPLED` `pe = −0.025`, `paired_se = 0.0306`, CI
`[−0.085, 0.030]`, `INCONCLUSIVE`.

---

## 20. 1k vs 10k stability

MID, fixed 3-candidate subset (`STAY_OUT`, `PIT_NOW`, `PIT_NEXT_LAP`), same
seed, 1 000 vs 10 000 trajectories. Paired SE shrinks by ~3.2–3.4× (close to
`sqrt(10)` without being hard-coded), CI widths shrink proportionally, and every
classification is stable:

| Objective | Candidate | pe 1k | pe 10k | se 1k | se 10k | CI width 1k | CI width 10k | cls |
|---|---|---:|---:|---:|---:|---:|---:|---|
| WIN | PIT_NOW | −0.0550 | −0.0575 | 0.0122 | 0.0037 | 0.0490 | 0.0146 | DEGRADE → DEGRADE |
| WIN | STAY_OUT | −0.0030 | −0.0004 | 0.0022 | 0.0007 | 0.0090 | 0.0029 | INCONCLUSIVE → INCONCLUSIVE |
| PODIUM | PIT_NOW | −0.1900 | −0.1534 | 0.0202 | 0.0065 | 0.0760 | 0.0249 | DEGRADE → DEGRADE |
| FINISH | PIT_NOW | −1.0560 | −0.8586 | 0.1041 | 0.0333 | 0.4231 | 0.1309 | DEGRADE → DEGRADE |
| FINISH | PIT_NEXT_LAP | −0.8950 | −0.7650 | 0.1010 | 0.0322 | 0.4060 | 0.1289 | DEGRADE → DEGRADE |

Point estimates move within the respective intervals; no classification flips.

---

## 21. Paired vs unpaired diagnostics

Across the 1 000-trial candidates/metrics with a defined ratio (54 cells,
`se_ratio = paired_se / unpaired_se`): median **0.959**, min **0.0** (paired
variance exactly zero, e.g. an inert `STAY_OUT`), max **1.005**, and **88.9%**
below 1. Pairing reduces estimated sampling SE for most candidate/metric cells,
is roughly neutral for a minority, and offers no universal benefit — consistent
with the S3 limited-CRN finding. The ratio is diagnostic only; the canonical
uncertainty remains paired.

---

## 22. Performance

S5 analysis after the S4 comparison already exists (uncertainty for every
candidate plus all three objectives, `B = 2000`):

| Configuration | S4 comparison (s) | S5 analysis (s) | analysis/comparison |
|---|---:|---:|---:|
| 1 candidate / 1k | 2.29 | 0.113 | 0.049 |
| 9 candidates / 1k | 11.68 | 4.880 | 0.418 |
| 3 candidates / 10k | 46.08 | 1.583 | 0.034 |

The statistical layer is substantially cheaper than Monte Carlo execution and
never reruns a simulation. The 9-candidate case is the heaviest because it runs
`1 + 36` bootstrap intervals in addition to 9 candidate intervals.

## 23. Memory

`tracemalloc` peak of the S5 analysis only: **0.11 MB** (1 candidate/1k),
**0.16 MB** (9 candidates/1k), **0.17 MB** (9 candidates/1k, EARLY), and
**0.17 MB** (9 candidates/1k, LATE). Retention is compact terminal records; the
bootstrap loop is `O(n)` per interval. No trajectory history is stored.

---

## 24. Temporal / counterfactual semantics

Uncertainty and objectives use only the state at T, the frozen parameters, the
frozen config and the retained simulated per-index outcomes. There is no
future-pit, future-compound, final-status or oracle input. AST firewall tests
confirm `uncertainty.py` and `objectives.py` import no
`replay`/`prediction`/`model_lab`/`pandas`/`sklearn` module.
`probability_semantics = "MONTE_CARLO_FREQUENCY"` and the S4 counterfactual
semantics are unchanged and still carried on the comparison. Every interval is
labelled Monte Carlo sampling uncertainty, not a real-world causal claim.

---

## 25. Validation artifact

`data/v2/strategy/s5_uncertainty_validation_v1.json`
(`s5-uncertainty-objective-protocol-v1`) records: protocol/uncertainty/objective/
comparison/candidate versions, the bootstrap configuration, seed and count,
per-stage supported flag, comparison identity and timings, S4-reproduction flag,
all objectives (baseline-relative counts, leader, indistinguishable/
distinguishable sets, pairwise status counts, candidate SE/CI/classification and
execution context), the paired-vs-unpaired diagnostics, the 1k/10k stability
table, the performance measurements and the limitations. `/data/v2/` is
git-ignored by policy, so the artifact is generated and untracked; it is
reproducible from `scripts/run_phase7_s5_validation.py`.

---

## 26. S1–S4 regression

- S1 contracts / seam / Phase-6 compatibility: pass.
- S2 mechanics: pass.
- S3 paired: pass.
- S4 comparison: pass (42 tests; the narrow retention changed no public result).
- Authorized-drift governance (`tests/test_v2_phase6_freeze.py`): pass.
- Combined regression run: **888 passed, 7 failed** (the 7 failures are the
  pre-existing environment-drift pinned-identity assertions described below).

---

## 27. S5 tests

- `tests/test_v2_phase7_s5_uncertainty.py`: **28 passed**.
- `tests/test_v2_phase7_s5_objectives.py`: **26 passed**.
- Total S5: **54 passed**. Coverage includes all items listed in §18 plus the
  no-simulation-rerun test (monkeypatched engine), S4 compatibility,
  probability/counterfactual semantics, and the temporal firewall.

---

## 28. Phase-6 regression

- `tests/test_v2_phase6_freeze.py` (governance + API contract hash): pass.
- R1–R5: pass.
- R6: 1 **pre-existing** failure
  (`test_pit_disabled_reproduces_r5_result_identity`).
- R7: pass. R7.1: 6 **pre-existing** failures
  (`test_accepted_state_matches_pre_fix_result_identity[...]`).
- These are the same environment-drift pinned identities disclosed in the S3 and
  S4 reports (numpy 2.4.2); the S1 compatibility fixture captured on this
  environment still passes byte-for-byte. `v2/simulation/monte_carlo.py` is
  byte-identical to the S3-authorized hash, and S5 changed no simulation file,
  so these failures cannot be S5-caused.

---

## 29. API regression

`api/` was not modified. The Phase-6 API contract hash test and the
`POST /v2/simulations/race` route test (`tests/test_v2_phase6_r8.py`) pass. No
strategy route exists yet (S7).

---

## 30. Authorized drift

No new Phase-6 runtime modification. `v2/simulation/monte_carlo.py` still
matches its S3-authorized hash
`d2166075e2d4b90bf4604ac3d586fe4d07f1ae577cb413ec8991317309e68c68`;
`docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json` retains stage `S3`;
`docs/PHASE6_FREEZE_MANIFEST.json` is untouched. No simulation runtime change
was required, so there is no new freeze conflict.

---

## 31. Graphify final result

`graphify update .` (see the final run report for exact node/edge/community
counts). AST dependency check: `v2/simulation/*` imports of `v2.strategy` = 0;
Strategy internal edges add `uncertainty → ∅`, `objectives → uncertainty` and
`__init__ → {…, objectives, uncertainty}`; **no Strategy cycle**. Neither
`uncertainty.py` nor `objectives.py` imports API/frontend/model_lab/replay/
oracle/historical-future material.

---

## 32. Scientific limitations

1. Sampling uncertainty only. It excludes parameter, model-form, pit-loss, pace,
   traffic, compound-effect, future-weather and real-world counterfactual
   uncertainty.
2. The interval is a Monte Carlo resampling interval for the paired simulation
   delta, not a confidence interval for a real-world causal effect.
3. Estimates are simulator-conditional Monte Carlo frequencies; alternative
   strategy outcomes are counterfactual and not observable truth.
4. Pairwise intervals are exploratory and not a family-wise procedure; no
   p-values, no multiple-comparison correction.
5. The bootstrap seed is a statistical-analysis seed and never a simulation seed;
   changing the simulation seed changes the interval by changing the
   observations.
6. No traffic/overtaking model and no per-compound pace delta (inherited from
   Phase-6/S4); compound differences are largely stint/transition + noise.
7. CRN is adopted with limitations: pairing reduces estimated SE in most but not
   all cells; `se_ratio` is diagnostic only.
8. `leader_by_point_estimate` and the ordering are simulator point-estimate
   labels only; they are never recommendations.
9. The small-n threshold (`< 30`) withholds the interval; it does not imply the
   point estimate is accurate.

---

## 33. Git safety

Only additions/edits listed in §1; the artifact is untracked by policy. No
`reset`/`restore`/`checkout`/`clean`/`stash`/`add .`/`commit`/`tag`. Tags
`v2-monte-carlo-phase6` and `v2-frontend-foundation` preserved. Nothing staged.
No simulation, API or frontend file modified. S6 not started.

---

## 34. S5 definition of done

All DoD items satisfied: S0–S4 docs/code read; Graphify pre-audit; paired
uncertainty; exact S4 point-estimate reproduction; paired SE; unpaired
diagnostic; SE ratio; explicit n=0/n=1 policy; constant-difference policy;
deterministic paired bootstrap with the pair as unit; bootstrap RNG separated
from simulation RNG; stable bootstrap identity; 95% CI; documented small-n
policy; sampling-only semantics; `UNCERTAINTY_VERSION`; exactly three
objectives; no default objective; no weighted score; exact mappings;
baseline-relative classification; direct candidate-vs-candidate pairing; no
CI-overlap heuristic; explicit pairwise validity counts; point-estimate
ordering; ambiguous leader handling; baseline can remain preferable;
inert/superseded context retained; order/subset/pairwise-subset invariance;
determinism; synthetic uncertainty and pairwise validation; EARLY/MID/LATE
validation for all three objectives; MID 1k/10k stability; paired/unpaired
diagnostic; performance and memory measured; no simulation rerun in the
statistical layer; artifact and report created; S1–S4 green; S5 tests green;
Phase-6 and API regression checked; no simulation runtime drift; Graphify
updated; `simulation → strategy = 0`; no cycle; API/frontend untouched; nothing
staged or committed; no tag; S6 not started.

Final verdict: **S5 COMPLETE — READY FOR S6**.
