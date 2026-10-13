# MC2 Performance P3-1 — Exact Scalar Interpolation Audit

P3-1 investigated the post-P2B dominant hotspot (scalar `np.interp`
dispatch, ≈5.5s cum of ≈26.3s profiled) and concluded it is already at
its exactness-constrained floor on this runtime. **No production code
changed** (working kernel byte-identical to the P2B tree). V3.8 immutable
(`15df86b`, tag intact).

## Inventory (the single hot site)

`raceintel/simulation/mc2/kernel.py:335` is the only interpolation call
reachable from `run_mc2`: scalar uniform → 17-point fixed immutable
float64 grids (`xp = (0, p1..p15, 1)`, all-`fp` finite, validated at
`ResidualSampler` construction) → `float(np.interp(...))`. Wrapper cost
per call: `asarray` check + `iscomplexobj` (~140ns) + array-function
dispatch + C-call setup ≈ 600ns of ≈1µs. Full inventory:
`results/v3/performance_mc2/p3_1/interpolation_inventory.json`.
(`sample`/`sample_unit`/`_lerp`/loss-model sites are public API or other
features — untouched.)

## Key finding: numpy fuses the multiply-add

Empirical discrimination over knots, `nextafter` both sides, endpoints,
extrapolation, and 60k+ interior points per grid: numpy computes
**`fma(x - x0, (y1 - y0) / (x1 - x0), y0)`** — slope-first, then a
single-rounding fused multiply-add (fp-contraction; build-dependent).
All unfused equivalents mismatch 9–36% of points by 1 ulp
(`scalar_exactness.json`). Python 3.11 has no fast `fma`, so no
pure-Python transcription can be both bit-exact and faster. P3-1B
rejected on exactness economics, not effort.

## Microbenchmarks (real 17-point grids)

- Current `float(np.interp(float(u), xp, fp))`: ≈430ns/call.
- Passing `np.float64` straight through: ≈510ns/call (**17% slower** —
  numpy scalar conversion path; rejected).
- Run-local binding, identical args: ≈423ns/call (≈1.5% of interp cost).

## Components

- **P3-1A** (binding): implemented, exact everywhere (7 P0 hashes, small
  live, RNG), production 23.54s vs 23.60s = **1.0025x** — inside rep
  noise (±1–2%) → **reverted** (P3-1-P29).
- **P3-1B** (transcription): rejected (fma, above).
- P3-1A2/D, caching, vectorization: rejected/deferred per ledger.

## Evidence that the revert is clean

Working `kernel.py` is byte-identical to `p3_1/pre_p31_kernel.py`
(`diff` empty); post-stage profile shows the identical call count
(146,000,933); reverted-tree benchmark 23.69s with all P0 hashes exact;
P1 smoke serial == w1 == w2 == w4 plus executor-5000 fixture match.

## Classification

**C — SCALAR_INTERPOLATION_NOT_WORTHWHILE.** The scalar dispatch floor
is reached under exact semantics. Recommendation (one):
**PERFORMANCE_FREEZE** — single-state latency is ≈7.9s (from ≈28s at
P0); remaining gains need P3-2 vectorization with real scientific risk
for diminishing practical value. Full Tier-1 belongs to the freeze.
Do not start P3-2 automatically.
