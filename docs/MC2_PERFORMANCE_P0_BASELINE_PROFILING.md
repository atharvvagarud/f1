# MC2 Performance P0 — Baseline + Profiling + Optimization Plan

Audit-only stage. **No production code changed. V3.8 immutable** (commit
`15df86b`, tag `v3.8-model-simulation-consensus`, untouched).

## V3.8 baseline verification

- HEAD == `15df86b`; tag resolves to HEAD; status clean at entry; ancestry OK.
- V3.8 scientific/product behavior unchanged by P0 (P0 adds only
  `results/v3/performance_mc2/p0/`, this doc, and `tests/test_perf_mc2_p0.py`).

## Tier-1 reporting reconciliation

Authoritative rerun: collected **5002**, passed **3950**, failed **0**,
xfailed **4**, deselected **1048**, 3284.35s. Runner line: selected 3959,
deselected 1043 (manifest nodes). Reconciliation: one bare manifest node
(`test_v2_phase6_r71.py::test_accepted_state_matches_pre_fix_result_identity`)
covers 6 parametrizations (+5) → 1043 + 5 = 1048 items; 5002 − 1048 = 3954
run = 3950 passed + 4 xfailed. Skipped/xpassed/errors all zero. Reporting
only — no V3.8 change.

## Motivating workload (V3.8D)

280 timed `run_mc2` calls at 5000 futures, 5425.2s total (~19.4s/run);
prep + overhead ~21s. Production semantics: E_AR1_RESIDUAL, seed 20240101.

## Computational unit (§7 answer, with evidence)

One MC2 run = one **full-field** simulation for one **exact factual field
state** `(race_id, frame_index/state_time_s)` — `run_mc2` takes no
target-driver parameter and returns full-field distributions; per-row
extraction is presentation-only.

The lap-sharing hypothesis is **refuted**: `mc2_checkpoint.json` holds 277
runs across **277 distinct (race, frame)** states (every group size 1).
Each driver row on a nominal lap maps to a different timeline frame
(driver-specific `state_time_s`), i.e. a scientifically distinct T.
Cross-row simulation reuse would change T and is invalid. Input classes:
field-state inputs are per-exact-T (A-as-instantiated-per-T); mechanisms
embed per-driver state at T (B within the field input); extraction is C;
every stored run is D (separate simulation required).

## Duplicate-work audit (summary)

Already reused: race params/service/grid caches. Not reusable: per-state
prep (distinct T), cross-row simulation (refuted above). Within-run
overhead (the actual prize): per-step `validate_rho` ×3 (16.9M calls),
`DriverMechanism` rebuild per step (5.7M), `DynamicsInput` per event
(5.6M), scalar `np.interp` per draw (5.6M × 3 asarray), per-step
min/sorted/dict scans (22.4M min), constant domain-tag sha256 per sim,
O(n²) checkpoint rewrites. Full table: `duplicate_work_audit.json`.

## Checkpoint audit (summary)

`mc2_checkpoint.json` (1.3MB): keyed by bare `state_id`, full-field
payloads, dict-membership resume, full-dict rewrite every 5 rows. No
version stamp → incompatible science could be silently resumed; unsuitable
for parallel writers (needs per-worker files or single-writer merge +
version-stamped keys). Frozen; unchanged. Full audit: `checkpoint_audit.json`.

## Profiling evidence

cProfile at production 5000 (ordinary state; 538M calls): `schedule`
68.0s cum (67.5%), `mc2_residual_step` 24.6s, `mc2_expected_pace_s` 19.1s,
`sample_unit` 14.9s, `combined_drift` 11.7s, `min` 11.4s, `ar1_step` 10.2s,
dataclass init/post-init 16.4s combined, `validate_rho` 6.1s,
`sorted` 6.0s, pending-dictcomp 5.9s. Clean scale series (same state):
100→0.616s, 500→3.077s, 1000→6.116s, 2500→15.309s, 5000→30.519s —
**linear** (~6.1ms/future, ~0 setup). Production 5000 on 3 states:
30.5/26.5/27.8s. RSS flat (~150–190MB, no leak/pressure).

Conclusion: per-event **Python overhead** dominates; native kernels are
minor. Full tables: `profile_summary.json`, `baseline.json`.

## CPU / GIL / memory

Single-core bound; ~90% of time is CPython bytecode under the GIL
(closures, dict ops, dataclass churn, per-call dispatch). GIL-releasing
NumPy kernels (PCG64 bulk draw, interp core) are ~10% and already fast.
No memory pressure, no swapping. Threads rejected.

## RNG architecture (summary)

PCG64 `SeedSequence([seed, sim_id, tag, dim])` per simulation (own MC2
domain `mc2-ar1`, never perturbing R3/R6); bulk `random(bound)` per sim,
consumed in event order; aggregation order-independent. Reordered
trials/drivers, chunked trials, any worker count: **no risk** — streams
are keyed by scientific identity. Chunk invariance documented in code.
Full map: `rng_audit.json`.

## Vectorization / parallelism / threading

- Vectorization: pace/drift/sampler-pool arithmetic SAFELY_VECTORIZABLE
  across sims (verify bit-identity); AR1 recursion sequential within
  (sim, driver) but parallel across sims (needs proof); event queue
  SEMANTICALLY_RISKY (order drives RNG cursor) — use order-exact heap.
- Parallelism rank: **A states (1) > C chunks (2) > B races (3, subsumed) >
  D drivers (rejected: would 20× duplicate field sims)**.
- Threads: rejected (GIL-bound). Full analysis: `parallelism_options.json`.

## Serial parity fixtures

`baseline_fixtures.json`: 3 states × 5000, config identity
(`mc2-r1-research+mc2-kernel-v1+mc2-rng-v1+…`, rho 0.264), 7 canonical
hashes each; in-process double-run bit-identical. Parity standard: exact
equality over eligibility/refusal/counts/frequencies/distributions/orders
(+ strategy/counterfactual where MC2 reused); serial(1)==parallel(N).

## Optimization plan (evidence-derived)

- **P1** (low risk/complexity): outer multiprocessing over states +
  within-run chunking; near-linear expected; parity via fixtures; rollback
  to serial flag. Benchmark matrix workers 1/2/4/6/8 (wall, CPU, RSS,
  parity, thermal — do not assume 8 beats 4/6).
- **P2** (medium): kill per-event Python overhead (hoist validation/scale,
  mutable mechanism state, drift tables, vectorized sampler, heap queue,
  checkpoint redesign); each sub-item independently revertible.
- **P3** (high validation): exact cross-sim NumPy vectorization with
  bit-identity proof. Full plan: `optimization_plan.json`.

## P0 pathology

P0-P1…P0-P20 all zero (checked in `tests/test_perf_mc2_p0.py`).

## Verdict

**MC2 PERFORMANCE P0 COMPLETE — BASELINE PROFILED — READY FOR P1.**
Do not implement P1 here. Do not start V3.9.
