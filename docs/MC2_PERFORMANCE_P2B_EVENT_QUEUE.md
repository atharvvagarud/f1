# MC2 Performance P2B — Exact-Order Event Queue Optimization

P2B replaces the per-iteration legacy event-queue scan
(`pending` dictcomp + `min()` + `sorted()`) with a `heapq` binary heap that
reproduces the current event order **exactly**. No interpolation change, no
vectorization, no future-chunk multiprocessing, no algorithm change.
V3.8 immutable (`15df86b`, tag intact); P2A output is the baseline.

## Legacy order contract (derived from code, not intent)

- Event: `(event_time: float, next_lap, next_age)` in dict `nxt[driver_id]`.
- Selection per iteration: rebuild `pending` (unfinished only),
  `event_t = min(v[0] ...)` (generator over values), batch = driver_ids
  with `v[0] == event_t`, **`sorted()` ascending** — then processed
  one-at-a-time from the frozen batch list.
- Tie rule: exact float equality, then **ascending driver_id string**.
  Proven NOT insertion order: `tie2-BA` (B inserted first, A processed
  first). Dict/insertion order provably irrelevant; stable sort
  unobservable (unique keys).
- Reschedule is always strictly later (`lap_time > 0` enforced), so a
  successor can never rejoin the batch being processed; the frozen batch
  additionally isolates it. One live entry per driver always.
- NaN/inf impossible (finite checks); ±0.0 unobservable (positive clocks).
- No retirement/DNF queue exists in this kernel; terminal drivers record
  `finished` and schedule nothing further.
- Full contract: `results/v3/performance_mc2/p2b/event_order_contract.json`.
- Feasibility gate: **A — EXACT_ORDER_CONTRACT_PROVEN** (no extra metadata).

## Heap design

Entries `(event_time, driver_id, next_lap, next_age)`; comparison decides
on `(time, driver_id)` only (driver_id unique among live entries, payload
never compared). Per iteration: peek `heap[0][0]`, `heappop` the full
same-stamp batch (exact `==`, same operator as legacy), process in pop
order (== driver_id ascending for ties), pop-then-push successors.
Initial roster-order scheduling loop byte-identical (RNG cursor order);
`steps` counted per batch; `finished`/final `(time, did)` ordering
untouched. Design: `heap_design.json`.

Stale entries are **impossible by construction** (no lazy invalidation, no
generations): at most one live entry per driver. Measured on production
config (200 sims): max heap 20 = field size, pushes == pops == 224000,
stale pops 0. No compaction needed.

## Controlled baseline (same env/corpus, 2 reps, 5000 futures)

| state | pre wall | post wall | speedup |
|---|---|---|---|
| ordinary_early | 17.33s | 8.65s | 2.00x |
| complex_late | 14.32s | 7.46s | 1.92x |
| mid_late | 15.02s | 7.60s | 1.98x |
| **total** | **46.67s** | **23.71s** | **1.97x** |

Pre profile (296.2M calls, 51.5s): queue scans ≈21.6s self
(`min` 5.8s + dictcomp 5.7s + `sorted` self 1.3s + genexprs 8.9s).
Post profile (146.0M calls, 26.8s): queue scans gone;
`heappop`+`heappush` ≈ 0.9s; `sorted` only in aggregation (5045 calls).
**New dominant: scalar interpolation dispatch** (`np.interp` wrapper
≈5.5s cum of 26.8s) inside the schedule frame — the P2A-deferred P3-1
candidate, now profile-confirmed. Untouched in P2B.

## Parity (all exact, no tolerance)

- Queue-level: 8 scripted cases (unequal, 2-way ties both insertion
  orders, 3-way, chains, hypothetical same-stamp newcomer, mid-batch
  failure) + 5000 seeded fuzz cases: legacy sequence == heap sequence.
- Live event trace: 83,160 events (80 sims, 2 states), bit-exact
  timestamps: identical. Natural fixtures contain no ties (continuous
  clocks); ties covered synthetically.
- Small-live full outputs: 3 states × {10, 60} sims identical; RNG stream
  identity unchanged.
- Production: post-change 5000-future runs match all 7 P0 canonical
  hashes on every rep; executor-5000 run matches the fixture.
- P1: serial == w1 == w2 == w4 (smoke); orchestration unchanged.

## Pathology / tests / collection

P2B-P1…P30 all zero (`tests/test_mc2_p2b.py`, 13 nodes). P2A-P18/P30
carry explicit stage-aware supersession clauses (heap + EXACT parity +
contract); every other queue change still fails closed. Targeted
regression green (below). Collection: pre-P2B 5040 + 13 P2B nodes = 5053
pin, updated narrowly. Full Tier-1 deferred to the performance freeze
(exact event-trace + canonical parity, targeted green, no cross-cutting
risk).

## Classification

**A — EVENT_QUEUE_OPTIMIZATION_SUCCESSFUL** (exact parity + 1.97x).
Recommended next (and only next): **interpolation/dispatch optimization**
(P3-1), per the post-P2B profile. Do not start automatically.
