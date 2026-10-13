# V3.9 Uncertainty Intelligence — Final Freeze Record (V3.9E)

Final stage of the V3.9 Uncertainty Intelligence programme. This document
records what was frozen, the exact evidence behind it, and the boundaries
that remain.

## Programme conclusion (intentionally asymmetric)

- **U1 — MODEL × SIMULATION DISAGREEMENT:** supported, measured, runtime
  available, product presented. Exact parity with frozen V3.8 metric
  definitions revalidated at freeze (20/20 drivers, field metrics exact).
- **U2 — MONTE CARLO SAMPLING PRECISION:** supported, measured, runtime
  available, product presented. Exact parity revalidated (k/n/p_hat/SE/
  Wilson exact; k=0 and k=n boundaries valid; zero stays AVAILABLE).
- **U3 — SIMULATOR SENSITIVITY:** framework defined, provenance insufficient,
  zero executable parameter ranges, NOT EXECUTABLE. Presented in product as
  NOT ESTABLISHED. No numeric values were created during freeze.

V3.9 is NOT a universal uncertainty estimator. It is structured
uncertainty/evidence intelligence with separate families and an explicit
limitation where evidence does not exist.

## What was frozen

- Science: V3.9A contract + V3.9B measurements (277 pairs, 15 race-laps,
  8 races, 2022–2024; descriptives: mean |gap| 0.0318, median 0.0007,
  median Spearman 0.6744, leader agreement 9/14, n=5000 throughout,
  max SE ≈ 0.007071, 187 valid k=0, mean Wilson width ≈ 0.00372 —
  historical evidence, never runtime thresholds).
- Runtime: V3.9C bundle/API (`GET /v2/uncertainty/availability`,
  `POST /v2/uncertainty/compare`; cache-first; no public science controls;
  typed refusals; provenance on every bundle).
- Product: V3.9D `/uncertainty` route (field matrix, driver inspector,
  Wilson visualization, neutral telemetry, U3 limitation, provenance).
- Guards: 23 worktree-ownership reconciliations, each an exact stage-owned
  path admission; no invariant weakened, no test disabled/skipped/xfailed.
- Pins: Python collection 5148 → 5176 (+28 V3.9E freeze tests); frontend
  386/386; tsc clean; Next build emits `/uncertainty`.

## Validation at freeze

- Targeted preflight 648/648 green (all reconciled guards included).
- Authoritative full Tier-1: collected 5176, 4124 passed, 0 failed,
  0 errors, 0 skipped, 0 xpassed, 4 pre-existing xfails, 1048 deselected
  per frozen manifests, 3106s, return code 0.
- Responsive 1600/820/390 re-validated live (no viewport overflow; zero,
  families, U1/U2/U3 visible at all widths). Accessibility contract holds.
- Claim-language and source-neutrality audits: no scores, no winners, no
  fusion in any product surface (matches are negated disavowals only).
- 2025 remains product-excluded end to end; temporal/alignment contracts
  hold; performance freeze untouched (P2A parity EXACT).

## Explicitly NOT done (deferred research register)

U3 sensitivity ranges, Bayesian tyre degradation, MC2 performance work,
model refits, fusion, confidence scoring, V3.10 scope. None was attempted.

## Freeze identity

Tag `v3.9-uncertainty-intelligence` (annotated) on the freeze commit
`feat(uncertainty): freeze v3.9 uncertainty intelligence`. Parent tags
`v3.8-model-simulation-consensus` and `v3.8-mc2-performance` verified
unchanged after tagging. Not pushed.
