# V3.9A Uncertainty Intelligence — Scientific Contract

Contract + audit + synthetic validation ONLY. No production uncertainty
computation, no API, no UI, no MC2 reruns, no model training. Parents:
V3.8 consensus (`15df86b…`, tag `v3.8-model-simulation-consensus`) and the
frozen MC2 performance programme (`32466c…`, tag `v3.8-mc2-performance`,
3.214x, Tier-1 5076/4024/0). Performance engineering stays frozen.

## Taxonomy (vector, never a scalar)

- **U1 — Model × Simulation disagreement** (PRIMARY): V3.1B Logistic vs
  MC2-E on identical `(state_id, driver_id)`, via V3.8C metrics reused
  unchanged (rank, leader, top-k/Jaccard, signed/absolute gap with
  simulation-minus-model orientation, directional-temporal). Disagreement is
  NOT confidence, error probability, epistemic/aleatoric variance, or
  calibration error. Logistic stays unnormalized; MC2 stays mutually
  exclusive simulation frequency.
- **U2 — MC sampling uncertainty** (PRIMARY): `p_hat=k/n` (n = valid
  futures), SE `sqrt(p(1-p)/n)`, Wilson 95% (registered safer method;
  non-degenerate at 0/1). Describes estimate precision ONLY — not simulator,
  real-world, disagreement, parameter, or correctness uncertainty.
  `k=0` is VALID zero, not missing; `n=0`/refused is
  INSUFFICIENT/UNSUPPORTED, never zero-filled. Production n=5000 → max SE
  ≈ 0.0071. Outcome spread ("how varied were simulator outcomes?") is
  explicitly NOT sampling uncertainty.
- **U3 — Simulator sensitivity** (PRIMARY framework, NO executable range
  yet): variation under predeclared defensible perturbations. Eligible for
  research: `regime_std_s` (empirical std+n). Needs provenance: `rho`
  (range must come from frozen per-fold estimates). Unsupported: per-state
  derived anchor/slopes. Fixed: dynamics decay, seed/count/arm, innovation
  scale (follows rho). Arbitrary ±% ranges prohibited. Future comparisons
  use common random numbers; topology breaks must be reported.

Secondary: model-family disagreement, outcome-distribution spread,
strategy/counterfactual MC sampling (reference frozen V3.6/V3.7 vocabulary;
intervals stay MC sampling uncertainty, never causal confidence).
Deferred: temporal instability, Bayesian tyre degradation (pre-race prior +
online ≤T updates only; never full-race fit, never future laps).
Rejected for primary: V3.4 ensemble. Epistemic/aleatoric labels prohibited
without a supporting construction. No universal confidence scalar, ever.

## Alignment, temporal safety, 2025

Exact `(state_id, driver_id)` (+race/frame/stage/boundary); no zero-fill,
dropping, nearest-state, cross-lap, remapping, or future borrowing. Runtime
evidence is outcome-blind (≤T only); labels offline-only. 2025 stays
REVEALED_HOLDOUT / PRODUCT-EXCLUDED.

## Provenance, status, language, product

Every future quantity carries family/sources/versions/identities/counts.
Statuses: AVAILABLE, MISSING_SOURCE, UNSUPPORTED_STATE, NOT_APPLICABLE,
INSUFFICIENT_SIMULATIONS, PROVENANCE_UNAVAILABLE — never 0. Allowed:
"Model and simulator disagree on the leading driver",
"The simulator assigns X probability based on 5000 futures",
"Finite Monte Carlo sampling interval: …",
"Output is sensitive to the registered parameter perturbation."
Prohibited: "90% certain", "highly confident", "10% chance the model is
wrong", "interval captures the true race probability", "simulator knows
the uncertainty". Product shows three separate panels (WHY, not a scalar).

## Classification

**B — UNCERTAINTY_CONTRACT_PARTIALLY_SUPPORTED**: U1+U2 fully supported;
U3 framework ready but no executable perturbation range exists yet.
Recommended V3.9B: compile rho per-fold provenance, derive regime_std
perturbation from empirical SE, implement U1/U2 measurement on frozen
evidence (no MC2 reruns), keep U3 in research until ranges are registered.
