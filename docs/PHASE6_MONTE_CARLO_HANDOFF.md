# Phase 6 — Monte Carlo Simulation Handoff

Phase 5 (Historical Race Replay) is **FROZEN** (replay contract v1,
prediction contract v1, probability-timeline contract v1, tag
`v2-historical-replay-phase5`). Phase 6 is expected to introduce the
**Monte Carlo simulation engine**. This document states what Phase 6 may
rely on as frozen and enumerates the architecture questions that Phase-6
R0 must answer. It does NOT design or implement the simulator.

## What Phase 6 may rely on as frozen

- **Phase-1 canonical data platform** — the D9 driver-lap state corpus and
  its side entities (weather, race control, pit stops, stints,
  results/roster), all deterministic and versioned.
- **Phase-2 temporal feature engine** — the frozen ALL_84 / v8 feature
  matrix and its semantic identities (`content_hash
  d2ee966c…`, matrix manifest SHA `b6a63f5e…`).
- **Phase-3 frozen winner model** — the serving artifact
  (`1116b34f…`), specification fingerprint (`3164de9e…`), and frozen
  `ModelIdentity`.
- **Phase-4 RaceState / prediction service** — exact-anchor `RaceState`
  reconstruction, the ALL_84 bridge, `RacePredictionEngine`, and the
  `INDEPENDENT_BINARY` probability semantics.
- **Phase-5 replay timeline and historical-state navigation** —
  `ReplayFrame` / `ReplayTimeline` (one frame per exact unique
  `state_time_s`, deterministic representative), `ReplayReconstructor`
  (exact `state_at`, first/previous/next/last/jump-to-leader-lap), the
  model-free `CheckpointSeries`, the read-only cache contract, and the
  probability-timeline projection. `ReplayFrameId` is the universal handle
  for simulation initial conditions and branch points.

## Key distinction: probabilities vs simulated outcomes

- **Phase-5 `winner_probability`** is an `INDEPENDENT_BINARY` model
  output: P(is_winner = 1 | state). It is not normalized across the
  field; the sum over drivers may be below or above 1; null means "not
  observed", not 0.
- **Phase-6 simulation outcomes** should eventually be **mutually
  exclusive simulated finishing outcomes** derived from simulation
  frequencies (one simulated winner per trial). Win probabilities
  estimated from independent simulation trials form a distribution across
  the field.
- **Do not** normalize Phase-5 probabilities and call the result a
  simulation probability. Do not treat the Phase-5 probability vector as
  a race-outcome distribution. Any conversion between the two is a new,
  explicit Phase-6 semantic that must be defined and validated, not
  assumed.

## Phase-6 R0 open questions

Phase-6 R0 owns the answers. Existing frozen evidence may settle some of
these; where it does, say so rather than inventing new semantics.

1. Simulation state contract: what exactly is carried per driver and per
   trial, derived from the frozen `RaceState`?
2. Race-state adapter: how does a `RaceState` (and a `ReplayFrame`) become
   a simulation initial condition without re-deriving facts?
3. Remaining-laps representation: leader progress vs scheduled laps vs
   per-driver laps under lapping.
4. Pace model: what frozen pace features (or new model) drive lap-time
   distributions, and their provenance.
5. Degradation model: tyre/stint degradation representation and provenance.
6. Pit-stop model: when cars pit and how many stops.
7. Pit-loss model: track-position/time cost of a stop.
8. Traffic model: how cars interact when positions converge.
9. Overtake model: probability/ability to pass, and clean-air effects.
10. Reliability model: mechanical retirements and incidents.
11. Safety-car / VSC / red-flag handling: how suspensions and bunching are
    simulated without contradicting frozen factual representations.
12. Weather handling: whether/how evolving weather is modelled or held
    constant from the factual as-of state.
13. Lapped-car semantics: how lapped traffic and blue flags are simulated.
14. Retirement semantics: distinguish simulated retirement from Phase-5's
    "no further observation" (never infer retirement from staleness).
15. Deterministic RNG: seeds, reproducibility, and how trial results are
    recorded.
16. Vectorization strategy: numpy/torch/other; per-trial vs batch.
17. Benchmark protocol: 1k / 10k / 50k trials on a fixed fixture set.
18. Simulation output schema: per-trial finishing order and metadata.
19. Finish-order validity: no duplicate/missing drivers, complete roster.
20. Mutually exclusive win probabilities: how they are computed and
    validated against the simulation frequencies.
21. Podium / points / expected-finish aggregation.
22. Reproducibility metadata: seed, model identity, data identity,
    contract versions, and simulator version.
23. Calibration/validation strategy against historical races (and the
    2025 protected-holdout policy).
24. Which historical inputs are factual vs modelled assumptions.
25. API boundary: new `/v2` routes, read-only vs generate-on-request.
26. Cache/precompute boundary: what is precomputed, keyed like the Phase-5
    cache, and how invalidation works.
27. Frontend integration boundary: how simulation results attach to the
    existing replay UI without disturbing frozen replay semantics.
28. Strategy-engine reuse requirements: what a later strategy phase needs
    from the simulator.

## Constraints carried forward

Exact-anchor semantics (no interpolation without explicit new
semantics), complete-roster rendering, no probability renormalization of
Phase-5 outputs, 2018–2024 serving scope, and the untouched legacy and
frozen Phase-4 routes. No production backfill is a freeze requirement.

## Explicitly out of scope for this document

No implementation, no simulator interfaces, no strategy types, and no
Explanation schemas. Phase 6 was NOT implemented in Phase 5 R8.
