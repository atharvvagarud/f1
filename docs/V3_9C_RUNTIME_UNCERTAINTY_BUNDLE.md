# V3.9C Runtime Uncertainty Bundle + API

Thin product layer over frozen V3.8 seams. No new prediction stack, no MC2
reruns, no fusion, no score, no frontend. Parents: V3.9A (`e3e2…`), V3.9B
(`a016…`).

## Architecture

```
FixtureProviders (consensus, reused) ──1 fetch/source──▶ V2UncertaintyService
        │                                                        │
        └────────▶ raceintel/uncertainty/bundle.py (pure) ◀──────┘
                        │  disagreement (V3.8C defs, imported)
                        │  monte_carlo_sampling (SE/Wilson, imported)
                        │  simulator_sensitivity (explicit unavailable)
                        ▼
              POST /v2/uncertainty/compare
              GET  /v2/uncertainty/availability
```

`api/main.py` gains 2 lines (import + include). Each source resolved at
most once per request (verified 1+1 fetches; cache repeats free).
Fixture-backed demo: `results/v3/v3_8f/fixtures` (frozen records, both arms
+ valid_trials) — representative of served states, no 2025.

## Bundle

Per common driver: U1 (native probs + family labels, signed/absolute gap,
ranks, Wilson containment) + U2 (k, n, p_hat, SE, Wilson 95%, precision
label) + descriptive gap/SE ratio. Single-arm drivers → explicit
`MISSING_SOURCE`; n≤0 → `INSUFFICIENT_SIMULATIONS`. Field: Spearman,
leaders, top-3 Jaccard. U3 block: `PROVENANCE_UNAVAILABLE`,
`executable: false`, reason + gate version — absence as information.

## Parity / refusals / overhead

- U1 runtime == frozen metric defs (max diff 0.0 on 20-driver fixture).
- U2 runtime == V3.9B recomputation (max diff 0.0); k=0 stays AVAILABLE zero.
- Refusals: 2025→422, unknown→422, malformed→422, corrupt→503. No fallback,
  no invented zeros.
- Overhead: ~0.05ms/bundle (20 drivers) — negligible. Kernel/residuals/
  mc2_batch untouched.

## Classification

**A — RUNTIME_UNCERTAINTY_BUNDLE_VALIDATED.** Recommended next gate: V3.9D
frontend presenting the three panels (sensitivity shown as unavailable),
never a confidence score. Not implemented here.
