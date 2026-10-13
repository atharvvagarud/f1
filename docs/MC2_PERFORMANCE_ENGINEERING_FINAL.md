# MC2 Performance Engineering — Final (Freeze)

Post-V3.8 deterministic performance programme, frozen. Parent:
`15df86b864fa552c69c4b7a53e22f1fc3b4c4ca1` (`v3.8-model-simulation-consensus`),
the immutable scientific anchor. All changes are implementation-only; model
probabilities, MC2 semantics, RNG identity, event semantics, eligibility,
temporal boundaries, strategy/counterfactual/consensus semantics, and API
contracts are unchanged (parity EXACT everywhere).

## Stages

- **P0 — baseline profiled** (`docs/MC2_PERFORMANCE_P0_BASELINE_PROFILING.md`):
  computational unit = exact full-field state `(race_id, frame_index)`;
  production = 5000 futures/state; original single-state latency ~26–30s
  (CPython/GIL-dominated); canonical fixtures in
  `results/v3/performance_mc2/p0/baseline_fixtures.json` (3 states × 5000,
  7 hashes each). No production change.
- **P1 — state parallelism** (`docs/MC2_PERFORMANCE_P1_MULTIPROCESSING.md`):
  new executor `raceintel/simulation/mc2_batch.py` (above the kernel; no
  kernel change). 15 states × 5000: w1 412.3s → w8 151.2s (2.73x batch
  speedup), exact parity at every worker count.
- **P2A — kernel overhead** (`docs/MC2_PERFORMANCE_P2A_KERNEL_OVERHEAD.md`):
  hoisted loop-invariant work in `mc2/kernel.py` + `mc2/residuals.py`
  (rho validation, innovation scales, decay powers, sampler grids, mechanism
  scalars, inlined pace/AR1 with identical arithmetic). Controlled 3-state:
  86.21s → 47.55s (1.81x, ~45%), exact parity.
- **P2B — event queue** (`docs/MC2_PERFORMANCE_P2B_EVENT_QUEUE.md`):
  per-iteration dict/min/sorted scan → binary heap with identical
  `(time, driver_id)` ordering, same-stamp batch drain, pop-then-push (no
  stale entries). Controlled: 46.67s → 23.71s (1.97x), exact event-trace
  parity (ordinary, 2-way/3-way ties, adversarial insertion order,
  rescheduling, terminal).
- **P3-1 — interpolation rejected** (`docs/MC2_PERFORMANCE_P3_1_INTERPOLATION.md`):
  scalar candidate measured ~1.0025x (noise), reverted. Retained production
  delta: **zero** — kernel byte-identical to pre-P3-1
  (`results/v3/performance_mc2/p3_1/pre_p31_kernel.py`). Recommendation:
  PERFORMANCE_FREEZE.

## Freeze measurements (this stage, same machine/env/corpus/config/reps)

- **Cumulative single-state** (isolated V3.8 worktree vs final tree,
  canonical 3-state corpus × 5000, 2 reps):
  V3.8 medians 31.55 / 27.72 / 29.61s → final 10.70 / 8.77 / 8.18s.
  Per-state 2.947x / 3.159x / 3.621x; **total 88.87 → 27.65s = 3.214x
  (68.9% reduction)**. Direct measurement is authoritative; the stage
  product 1.806×1.969=3.556 is NOT the claim.
  Final single-state latency ≈ 8–11s (mean of medians 9.22s).
- **Final batch** (15-state P1 corpus × 5000, optimized kernel +
  multiprocessing): w1 117.9s → w8 31.1s (**3.79x**, exact w1/w8 hash
  parity; 0.48 states/s, 2409 futures/s at w8).
- **Final profile** (ordinary state × 5000): 146M calls; remaining cost is
  per-event drift/pace arithmetic + sampler interpolation + heap ops —
  documented, deliberately not optimized (see below).

## Why optimization stops here

P1 solved multi-state throughput; P2A removed low-risk repeated overhead;
P2B removed the dominant event-queue overhead; P3-1 proved scalar
interpolation is at an exactness-constrained floor. Further material gains
need cross-simulation vectorization or future-chunk multiprocessing, which
carry materially greater complexity and scientific risk (RNG/draw-order/
rounding exactness). Current single-digit-second state latency suffices for
the present product/research stage. Deferred, not impossible.

## Deferred register

- **A. Cross-simulation vectorization** — likely large benefit; HIGH
  scientific risk; needs an exactness-proof harness first.
- **B. Future-chunk multiprocessing** — helps low-state-count latency; HIGH
  complexity (RNG splitting, checkpoint fan-in).
- **C. Interpolation/vectorized sampling** — P3-1 proved ~1.0025x at the
  exactness floor.
- **D. Drift/pace vectorization** — remaining arithmetic share; benefit
  unproven.

## Freeze artifacts

`results/v3/performance_mc2/freeze/`: programme_manifest,
production_delta_audit, guard_audit, scientific_parity, rng_parity,
event_order_parity, cumulative_single_state_benchmark,
final_batch_benchmark, final_profile, tier1_results, final_validation,
final_card. Freeze checks: `tests/test_perf_mc2_freeze.py` (9 tests;
5067 + 9 = 5076 pinned in `scripts/run_ci_tests.py`).

## Verdict

MC2 PERFORMANCE ENGINEERING FROZEN — DETERMINISTIC OPTIMIZATION COMPLETE —
READY FOR NEXT PROJECT PHASE. No P3-2, no vectorization, no future chunking,
no V3.9 in this programme.
