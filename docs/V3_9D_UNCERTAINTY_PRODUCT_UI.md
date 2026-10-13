# V3.9D — Uncertainty Intelligence Product UI

Presentation stage on the frozen V3.9C API. No science changed, no contract
changed, U3 not implemented, no scores created.

## Route

`/uncertainty` (`frontend/app/uncertainty/page.tsx` → `UncertaintyView`).
Navigation adds one entry next to `/consensus`; the consensus page is untouched.

## API consumption (runtime boundary)

- `GET /v2/uncertainty/availability` then at most one
  `POST /v2/uncertainty/compare` per selected state, through the typed client
  `features/uncertainty/lib/uncertaintyClient.ts`.
- One compare payload serves all drivers; driver switching is local state and
  issues no request (live-verified: 2 uncertainty requests across anchor,
  refusal, and selection interactions). No polling.
- No import of V3.9A/B/C JSON, historical aggregates, or Python science;
  graph check finds zero frontend→science/result edges.

## Page architecture (race-control hierarchy)

A. Header/state context (race, season, lap, stage, state id) + 3 demo anchors.
B. Field comparison: 20-driver telemetry matrix (model p, sim p, signed Δ
   with direction words, |Δ|, exact average-tie ranks, status chips).
C. Driver inspector: exact U1 values + U2 evidence (k, n, p_hat, SE,
   Wilson 95%) + accessible single-source Wilson visualization.
D. Field telemetry: Spearman 0.667, LEADER DIFFERENT (HAMILTON vs SAINZ),
   top-3 overlap 0.500 — values only.
E. Simulator sensitivity: visible NOT ESTABLISHED panel with regime_std_s /
   rho provenance detail; no numeric bounds; not an error.
F. Scientific context/provenance: family distinction, fusion non-result,
   sampling-only qualification, schema/metric/gate identities.

## Product rules enforced (and tested)

- U1/U2/U3 stay separate; no overall uncertainty, no confidence/trust/
  reliability score, no HIGH/MEDIUM/LOW, no fused probability, no source
  winner, no preferred source, no true-probability claims.
- 0.000 renders as valid AVAILABLE evidence (STROLL sim live-verified);
  null stays null.
- 2025 is product-excluded evidence, never zero; excluded states stop at
  availability with no compare issued and no demo fallback after failures.
- Number contract: native probabilities toFixed(3) with exact-value titles,
  SE/Wilson toFixed(4), deterministic and unit-tested.

## Validation

- 54 new frontend assertions pass; full frontend suite 386/386; tsc clean;
  Next build emits `/uncertainty`.
- Live render validated at 1600/820/390: no viewport overflow, zero + U3 +
  families visible at all widths, refusal states and local selection verified.
- Python collection reconciled exactly: 5148 collected = 5148 baseline
  (V3.9D adds 0 Python nodes).
- 9 frozen-guard failures, all caused solely by the two new untracked V3.9D
  frontend directories tripping pre-freeze worktree-ownership allowlists.
  Zero science/API semantic deltas; guards not weakened — V3.9E re-pins.

## Classification

A. UNCERTAINTY_PRODUCT_UI_VALIDATED — ready for V3.9E freeze.
