# MC2 Performance P2A — Low-Risk Kernel Overhead Elimination

P2A removes provably redundant loop-invariant/construction overhead with
**bit-identical** output. No vectorization, no heap, no chunking, no API
change. V3.8 immutable (`15df86b`, tag intact).

## Controlled baseline (same env/states, 2 reps)

5000 futures: ordinary 31.42s / complex 26.98s / mid 27.80s (total 86.21s).
Fresh profile confirmed P0 hotspots (538M calls).

## Ledger → implementation

SAFE_P2A (all accepted as one parity-gated hot-loop group, §17-adapted for
interdependence): P2A-1 validation hoisting (validate_rho 16.9M→per-run),
P2A-2 constant tag/dim/scale hoisting, P2A-4 mechanism-evolution without
dataclass rebuilds (5.7M→0; public `mc2_residual_step` untouched), P2A-3
drift precomputation (5.6M `DynamicsInput`→0; memoized decay powers;
public drift functions untouched), P2A-5 sampler grid arrays (asarray
16.8M→5.6M; scalar interp arithmetic unchanged). P2A-6 (call inlining)
NOT pursued (two-sources-of-truth cost vs ~5%). Deferred: heap (P2B),
interp/cross-sim vectorization (P3), future chunking (later).

Public validators, exception types, op order, RNG streams/draws/order all
unchanged; no shared mutable state (per-sim local dicts; P1 isolation
valid).

## Results

Post medians: 17.14 / 14.95 / 15.47s (total 47.55s) → **1.81× total, 1.81×
median (45% reduction)**. Calls 538M→296M. Eliminated from profile:
residual_step, expected_pace, sample_unit, combined_drift, dataclass
churn, validate_rho, _clip, asarray. New dominants (≈57%): event-queue
min/sorted/dictcomp/genexpr + interp dispatch + schedule frame → P2B.

## Parity

EXACT on all 7 canonical hashes + valid counts (3 states × reps), P0
fixture match, executor w1==w2==w4, executor-5000 fixture match. Invalid
inputs rejected identically (explicit tests).

## P1 interaction

Executor compatible without changes; each P1 worker is ~1.8× faster.
No full-matrix rerun (not the P2A gate).

## Pathology / tests / collection

P2A-P1…P30 all zero. Targeted regression green (below). Collection:
pre-P2A 5028 + P2A nodes → pin updated narrowly. Full Tier-1 deferred to
the performance freeze (kernel changed but parity+targeted green, no
cross-cutting failures).

## Classification

**A — LOW_RISK_OVERHEAD_OPTIMIZATION_SUCCESSFUL.** Recommended next:
**P2B event-loop/data-structure optimization** (proof obligations in
`deferred_candidates.json`). Do not start automatically.
