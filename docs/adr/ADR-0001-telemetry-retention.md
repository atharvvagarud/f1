# ADR-0001 — Telemetry retention (Phase-1 canonical dataset)

- **Status:** Accepted (2026-09-08). Reversible — see Revisit triggers.
- **Decision owner:** F1 Intelligence v2 data platform (Phase 1).
- **Plan reference:** `V2_PHASE_1_DATA_PLATFORM.md` §31 (Telemetry Policy),
  §9.7 (Telemetry Summary), §3.6, and stage **D8 — Telemetry Decision**.

## Context

The rich FastF1 layer (D5) had to load telemetry/position streams for every
Race session purely so FastF1 could derive `Session.t0_date` (which the
race-control timestamps need). Those streams were cached, never promoted to
canonical storage, and now live in the FastF1 cache (`data/raw/fastf1_cache`,
≈16.2 GB measured: 172 `car_data` blobs ≈7.2 GB, 171 `position_data` blobs
≈7.1 GB, ≈1.7 GB HTTP cache, remainder session/timing blobs).

D8 must decide, from measured evidence, whether telemetry should be retained
as canonical Phase-1 data. The Phase-1 plan already states the sensible
default pipeline is *cache → lap-level aggregation → telemetry_summary* and
that broad raw retention needs strong justification. This ADR records the
measurement and the decision; it does not require reading chat history.

## Measured evidence (D8 sample, MEASURED)

Bounded representative sample — 8 already-cached Race sessions:
2018 Germany (2018-r11), 2019 Germany wet (2019-r11), 2021 Britain sprint
weekend (2021-r10), 2021 Belgium shortened (2021-r12), 2022 Monaco
(2022-r07), 2023 Bahrain (2023-r01), 2024 Bahrain (2024-r01), 2025 Miami
(2025-r06). Full machine-readable numbers:
`data/v2/reports/data_quality/d8_telemetry_sample.json`.

- **Coverage:** all 20 cars present in every sample race; telemetry covers
  **7,710 / 7,710** canonical driver-lap windows (0 zero-sample windows);
  6,776,940 telemetry samples total. Whole scope: car_data exists for 172/173
  sessions (2018-r02 has no telemetry blob); position_data for 171.
- **Channels (car_data):** `Time` (session-relative, aligned to the D6 state
  clock), `Date`, `RPM` (int, rpm), `Speed` (int, km/h), `nGear` (int),
  `Throttle` (int, % 0–~104 raw), `Brake` (bool), `DRS` (int raw code),
  `Source`. Null rates 0 in every sample race. Position_data: `X/Y/Z`
  (metres), `Time`, `SessionTime`, `Status`, `Date`, `Source`.
- **Scale:** median samples/lap 320–872 by race (2018 Germany 337, 2019
  Germany 394, 2021 Britain 388, 2021 Belgium 872, 2022 Monaco 320, 2023
  Bahrain 368, 2024 Bahrain 362, 2025 Miami 346); measured ≈59 bytes/sample
  of cached car_data; per-race car-data blob 30–84 MB. Shortened 2021 Belgium
  streams 1.41M samples while only 60 canonical lap rows exist (long SC/red
  flag periods outside canonical lap windows).
- **Cost:** cached-blob load + lap aggregation ≈0.3–0.4 s/race measured on
  the sample (aggregation dominates). Peak RSS for the 8-race run ≈510–550
  MiB.
- **Data quality of the candidate lap summaries:** every candidate computed
  on 100% of sample windows with plausible ranges (e.g. per-lap max speed
  241–322 km/h medians by race; throttle-pressed fraction 0.64–0.82; brake
  fraction 0.16–0.32; gear changes 35–46/lap; rpm_p95 ≈11.2–11.9k). Gaps:
  raw `DRS` codes are heterogeneous across eras (within-window code=1 fraction
  0.06–0.61 with additional codes 2/3/8/10/12/14 present; wet 2019 shows 0.61
  code=1, inconsistent with DRS being disabled in rain), so a naive
  DRS-active fraction is NOT trustworthy without track-zone validation.

## Temporal contract

Any future lap-grain summary for lap N may use only telemetry observed in
`[lap_start_s, state_time_s)` of lap N (state_time_s = D6 lap-end clock).
No lap N+1 / future-stint / future-race / final-race aggregate may enter. The
sample measurement already enforces this windowing; a future-telemetry
mutation test is included in `tests/test_v2_d8.py`.

## Options considered

| Option | Description | Storage (canonical) | Extract/build cost | Complexity | Temporal safety | Downstream utility today |
|---|---|---|---|---|---|---|
| **A** | Canonical telemetry-derived summaries broadly (many stats per lap) | small (est. <10 MB parquet) but wide & arbitrary | low | low | safe if windowed | speculative — no Phase-1 consumer; risks "arbitrary statistics" creep |
| **B** | Small lap-grain `telemetry_summary` table (the ~10 candidates) | small (~189,420 rows, est. a few MB) | low (≈0.3–0.4 s/race measured) | low | safe if windowed | speculative — no Phase-1 consumer; feature definitions untested vs eras |
| **C** | Selective richer telemetry for one narrow use case | medium | medium | medium | needs per-case design | no narrow use case exists yet in Phase 1 |
| **D** | Defer entirely from canonical Phase-1 data | 0 canonical bytes | 0 recurring | none added | n/a | none now; cache keeps everything recoverable |

Rejected framing: "telemetry exists so it must be canonical" and "scale as a
vanity metric" are explicitly disallowed by the plan (§3.6, §31).

## Decision

**Option D — defer telemetry entirely from the canonical Phase-1 dataset.**

- No canonical telemetry Parquet is created (`telemetry_summary` stays an
  explicitly inactive contract).
- The FastF1 cache remains the recoverable raw/source layer, unchanged and
  untracked. Nothing in D8 deletes or reorganizes it (measured: cache size
  unchanged across the D8 measurement runs).
- Raw telemetry is never copied into `data/v2`.
- D9 must not depend on telemetry.
- No interactive track / replay / RaceState is built now; if those arrive
  later they can read the cache on demand or through a dedicated asset
  pipeline, decided separately from the ML dataset.

## Rationale

1. **No justified consumer.** Nothing in Phase 1 (D6/D7 state, D9 features,
   labels) needs telemetry. The product capabilities telemetry *might* power
   (historical replay, track visualisation, Race Engineer explanations) are
   future and are not Phase-1 deliverables; retaining data for a hypothetical
   product path duplicates large volume into the canonical store without a
   requirement.
2. **Model utility is unproven and not needed yet.** No Phase-3 evaluation
   protocol exists that depends on telemetry; the protected 2025 evaluation
   design is intentionally untouched. Building a "utility experiment" now
   would substantially expand D8 into Model-Lab territory for a signal D9 does
   not require — explicitly allowed to be skipped by the D8 brief.
3. **Product utility is better served by the cache.** Interactive track /
   replay needs *positional fidelity*, which is the raw `position_data`/
   `car_data` streams (≈7.1 GB + ≈7.2 GB). Canonicalising them would duplicate
   large data; a future track asset pipeline can consume the cache directly.
4. **Measured cost/coverage do not justify urgency.** Lap summaries would be
   cheap to build later (measured ≈0.3–0.4 s/race, ~59 B/sample) — deferral
   has very low regret and costs nothing.
5. **Era-robustness risk.** Raw telemetry channels (notably DRS) carry
   era-inconsistent semantics (measured); any summary feature needs careful
   validation. Without a consumer that work is premature.
6. **Honesty constraint.** Poor-quality/imputation-prone channels should not
   be hidden; with no consumer there is nothing to hide or justify.

## Consequences

- Positive: Phase-1 canonical scope stays lean (state + supporting context,
  no telemetry); no new storage/architecture burden; no temporal-contract debt
  on a telemetry table; D9 proceeds telemetry-free; cache stays the single
  recoverable telemetry source.
- Negative/neutral: if a later stage needs telemetry summaries, a small build
  step is required (cheap, measured); a future track feature needs its own
  asset decision.
- `v2/d8.py` (measurement + candidate-summary prototype + tests) is retained
  as reproducible evidence and as the seed of any future Option B work.

## Rejected alternatives

- **Option A (broad canonical summaries):** arbitrary-statistic creep,
  speculative, rejected.
- **Option B (small telemetry_summary now):** cheap, but speculative with no
  Phase-1 consumer and era-validation work (DRS etc.) that only D9/Phase 3
  could justify. Rejected *for now*; the lowest-cost path back.
- **Option C (selective rich retention):** no narrow use case exists yet.
- **Raw canonical retention:** explicitly not implemented without approval
  (plan §D8 mission §19); requires a very strong justification that does not
  exist.

## Revisit triggers

Revisit this decision when any of the following is objectively true:

1. A concrete Phase-3 model task demonstrates (with a bounded experiment on
   historical years, not the protected 2025 protocol) material predictive
   gain from telemetry summaries.
2. A product requirement (track/replay/Race Engineer) needs positional or
   channel fidelity that the cache cannot serve on demand.
3. Telemetry extraction becomes materially cheaper or source coverage
   materially changes (e.g. provider stops serving the streams, making the
   cache the only copy).
4. A future feature explicitly depends on canonical raw telemetry.
5. D9/Phase 3 defines a lap-level summary with a tested definition that the
   cache could no longer reproduce.

The decision is reversible: Option B is estimated at <10 MB canonical output
and <2 minutes of whole-scope build from the existing cache.
