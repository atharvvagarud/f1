# Phase-2 Telemetry ADR Reassessment (F12)

> F12 objective: revisit frozen ADR-0001 (telemetry DEFERRED) against
> evidence gathered during Phase 2 (F0–F11) and select exactly one
> outcome: KEEP DEFERRED / ACTIVATE / REJECT. ADR/status-review stage
> ONLY: no ingestion, no materialization, no telemetry features, no
> registry change, no version bump. Depends on F0–F11 as consumers of
> evidence, reinterpreting none of them.
>
> Decision: **A. KEEP DEFERRED.** No Phase-2 revisit trigger is met;
> no measured evidence justifies activation. `FEATURE_SET_VERSION`
> stays `v8`; the registry stays at 84 definitions with zero telemetry
> concepts registered as features.

## 1. Objective

Determine whether any evidence gathered during Phase 2 (F0–F11)
justifies changing telemetry status from DEFERRED (ADR-0001, Accepted
2026-09-08) to ACTIVE / REQUIRED FOR PHASE 2. The burden of proof is
on activation; the expected outcome is DEFERRED unless strong
measured evidence demonstrates otherwise.

## 2. Original ADR-0001 decision (recovered verbatim from the record)

Source: `docs/adr/ADR-0001-telemetry-retention.md` (Accepted
2026-09-08; plan refs: Phase-1 §31 Telemetry Policy, §9.7, §3.6,
stage D8).

- **Decision: Option D — defer telemetry entirely from the canonical
  Phase-1 dataset.**
- No canonical telemetry Parquet is created; `telemetry_summary`
  stays an explicitly **inactive** contract.
- The FastF1 cache remains the recoverable raw/source layer,
  unchanged and untracked; raw telemetry is never copied into
  `data/v2`.
- D9 must not depend on telemetry.
- No track / replay / RaceState built now; a future asset pipeline
  may read the cache on demand under a separate decision.
- Rejected: A (broad canonical summaries — arbitrary-statistic
  creep), B (small `telemetry_summary` now — cheap but speculative,
  no consumer, DRS era-validation outstanding; lowest-cost path back),
  C (selective rich retention — no narrow use case), raw canonical
  retention (requires very strong justification that does not exist).
- Reversible: Option B estimated at <10 MB canonical output and
  <2 minutes whole-scope build from the existing cache.
- Revisit triggers (any one objectively true): (1) a concrete
  Phase-3 model task demonstrates material predictive gain from
  telemetry summaries in a bounded historical-years experiment (not
  the protected 2025 protocol); (2) a product requirement needs
  channel/positional fidelity the cache cannot serve on demand;
  (3) extraction becomes materially cheaper or source coverage
  materially changes; (4) a future feature explicitly depends on
  canonical raw telemetry; (5) D9/Phase 3 defines a tested lap-level
  summary the cache could no longer reproduce.
- No discrepancies found between this record and the F12 brief's
  summary; all numbers below are re-recovered from the repository,
  not trusted from the prompt.

## 3. Original measured evidence (D8 sample, MEASURED)

Source: `data/v2/reports/data_quality/d8_telemetry_sample.json`
(produced by `v2/d8.py`, read-only over cache + canonical Parquet;
`tests/test_v2_d8.py` green, incl. a future-telemetry mutation test).

- **Sample scope (8 already-cached Race sessions):** 2018-r11
  Germany (sparse era), 2019-r11 Germany (wet/chaotic), 2021-r10
  Britain (sprint weekend), 2021-r12 Belgium (shortened/red-flag),
  2022-r07 Monaco (wet, slow), 2023-r01 Bahrain (normal), 2024-r01
  Bahrain, 2025-r06 Miami (wet/mixed).
- **Coverage:** all 20 cars present in every sample race; telemetry
  covers **7,710 / 7,710** canonical driver-lap windows (**0**
  zero-sample windows); **6,776,940** telemetry samples total.
  Whole scope: car_data blobs for 172/173 sessions (2018-r02 has no
  telemetry blob); position_data for 171.
- **Channels (car_data):** `Time` (session-relative, aligned to the
  D6 state clock), `Date`, `RPM` (int, rpm), `Speed` (int, km/h),
  `nGear` (int), `Throttle` (int, % 0–~104 raw), `Brake` (bool),
  `DRS` (int raw code), `Source`. Null rates 0 in every sample race.
  Position_data: `X/Y/Z` (metres), `Time`, `SessionTime`, `Status`,
  `Date`, `Source`.
- **Scale:** median samples/lap by race — 337 / 394 / 388 / 872
  (Belgium, long SC/red periods outside canonical windows) / 320 /
  368 / 362 / 346; measured ≈59.03 bytes/sample of cached car_data;
  per-race car-data blob 30–84 MB. Shortened 2021 Belgium streams
  1,413,500 samples against only 60 canonical lap rows.
- **Cost:** cached-blob load + lap aggregation ≈0.3–0.4 s/race
  (ADR text) / 0.53 s/race per-race total in the JSON report;
  peak RSS ≈510–550 MiB for the 8-race run. Deferral regret is very
  low; rebuild stays cheap.
- **Cache totals (whole scope):** 16,158,604,515 bytes (≈16.16 GB):
  car_data 7,205,958,572 (172 files), position_data 7,071,728,954
  (171 files), HTTP sqlite 1,685,069,824.
- **Candidate-summary quality:** every candidate computed on 100%
  of sample windows with plausible ranges (per-lap max speed
  241–322 km/h medians by race; throttle-pressed fraction 0.64–0.82;
  brake fraction 0.16–0.32; gear changes 35–46/lap; rpm_p95
  ≈11.2–11.9k). **DRS caveat (measured):** raw `DRS` codes are
  heterogeneous across eras (within-window code=1 fraction 0.06–0.61
  with codes 2/3/8/10/12/14 present; wet 2019 shows 0.61 code=1,
  inconsistent with DRS being disabled in rain) — a naive
  DRS-active fraction is NOT trustworthy without track-zone
  validation.
- **Frozen temporal contract:** any future lap-grain summary for lap
  N may use only telemetry in `[lap_start_s, state_time_s)` of lap N
  (D6 lap-end clock); enforced by `sample_indices_in_window`
  (half-open) and pinned by the D8 mutation test.
- **D11 relevance:** `docs/PHASE1_FINAL_VALIDATION.md` confirms
  `telemetry_summary` absent (inactive per ADR-0001); D9 carries
  zero telemetry dependence (`v2/d9.py` imports no car data).
- **D12/freeze:** Phase 1 exited with the lean canonical scope
  (state + supporting context, no telemetry); F0 verified 189,420
  D9 rows / 3,458 label rows with no post-freeze Phase-1 drift.

## 4. Current Phase-2 feature inventory (registry authority)

Source of truth: `build_f11_registry()` (measured at F12 time).

- **`FEATURE_SET_VERSION = v8`** (`v2/features/registry.py`).
- **84 definitions total: 23 PASSTHROUGH + 61 CANDIDATE**, all
  `predictive_eligible=True`. No PLANNED entries remain (grid was
  superseded to CANDIDATE v2 in F10). Version history: v1 (F2/F4,
  23 passthroughs + planned grid) → v2 (F5, +12) → v3 (F6, +8) →
  v4 (F7, +12) → v5 (F8, +4) → v6 (F9, +9) → v7 (F10, +12) → v8
  (F11, +3). Exactly one bump per stage.

| Family | n | Status | Content (summary) |
|---|---|---|---|
| race_state | 3 | passthrough | position, leader laps, progress |
| tyre | 5 | passthrough | compound, tyre_life, fresh_tyre, stint factuals |
| stint | 3 PT + 4 cand | mixed | pit counts, laps-since, stint_lap + in-stint eligible pace mean/median/count/trend |
| race_control | 5 PT + 5 cand | mixed | track_state + 4 flags + state duration, 5-min transitions, yellow/SC-VSC/red exposure |
| weather | 7 PT + 4 cand | mixed | 7 as-of wx values + 5-min air/track deltas, rain-in-window, time-since-rain |
| pace | 8 | candidate | eligible-stream median/mean windows 3/5/10 + counts, representative pace |
| gap | 8 | candidate | leader/ahead seconds + laps + validity + observation ages |
| relative | 1 | candidate | pace vs car ahead |
| teammate | 4 | candidate | relative pace, age, lap difference, position |
| field | 5 | candidate | observable size, ahead/behind counts, comparable rivals, field-median pace |
| traffic | 2 | candidate | in_traffic_2s, nearby within 5 s |
| rate | 2 | candidate | gap-change rates to leader/ahead (OLS, trailing-5) |
| momentum | 2 | candidate | pace change, position change (5-lap) |
| grid | 1 | candidate | grid_position (D5 PRE_RACE join) |
| driver_prior | 5 | candidate | starts, mean finish, points/start, mean grid, recent-5 finish |
| constructor_prior | 4 | candidate | mean finish, points/entry, races, recent-5 points/entry |
| circuit | 3 | candidate | prior races, mean position change, mean pit stops/entry |
| interaction | 3 | candidate | positions_from_grid, pace-in-traffic, gap-rate-in-traffic |

## 5. Information already covered without telemetry

Against the F12 brief's checklist, every item is represented at
driver-lap LAP_END grain with tested temporal contracts:

- **Current race state:** position, leader laps, progress (F4
  passthroughs of frozen D9).
- **Tyres/stints:** compound/age/stint/fresh + in-stint eligible
  pace mean/median/trend with counts (F4/F5).
- **Weather:** 7 as-of values + backward 5-min deltas, rain
  recency/exposure with staleness honesty (F4/F9).
- **Race control:** structural flags + durations, transitions and
  caution exposure over trailing windows (F4/F9).
- **Recent pace:** eligible-stream trailing windows with
  sample-count companions and min-history nulls (F5).
- **Gaps:** factual seconds/laps representation with validity and
  observation-age provenance; lapped/red-flag/ambiguous states are
  null-with-reason, never fabricated (F6).
- **Relative field context:** pace vs ahead/teammate/field-median,
  observable field counts, synchronized positions (F7).
- **Traffic:** factual 2 s / 5 s threshold counts on synchronized
  gaps (F7); no DRS-eligibility inference by design.
- **Rates/momentum:** observed OLS gap-change rates, pace and
  position change; projections banned and absent (F8/F11-gated).
- **Pre-race/grid/history:** factual grid + past-only
  driver/constructor/circuit priors with smoothing, cold-start and
  rename-safe identity (F10).
- **Interactions:** three domain-justified conjunctions on
  validated primitives; polynomial/auto-cross generation banned
  (F11).

Two plausible telemetry values are **already represented at lap
grain from frozen state**: speed-trap descriptors
(`speed_i1/i2/fl/st_kmh`, D6 passthrough-eligible base) and sector
times (`sector_1/2/3_s` + end-times, D6). Telemetry would add a
second representation of concepts the matrix already covers — not a
missing capability.

## 6. Potential telemetry value (conceptual only, NOT implemented)

| Candidate | Genuinely new? | Consistent? | Alignable ≤T? | Circuit geometry? | Volume? | Needed for Phase-2/3? |
|---|---|---|---|---|---|---|
| Speed-trap/straight-line summaries | **No** — D6 traps already present | traps patchy (I1 ~28k nulls) | yes, windowed | yes (layout-dependent) | small as summaries | no |
| Sector/local pace decomposition | **No** — D6 sectors already present | sectors mostly covered | yes, windowed | yes (sector lengths differ) | small | no |
| Throttle/brake usage fractions | yes (new channel) | yes in sample (0 nulls) | yes, windowed | yes (Monaco vs Monza meaning differs) | small as summaries | unproven |
| RPM/gear summaries | yes (new channel) | yes in sample | yes, windowed | yes (gear-count layout-dependent) | small | unproven |
| Acceleration behavior | marginal (derivable from speed deltas; lap-time slopes already modeled as stint-trend proxies) | needs resampling design | risky (interpolation) | yes | small | no |
| Micro-sector/cornering behavior | yes (new granularity) | needs position/track mapping | risky (async channels, map alignment) | **yes — requires corner/track geometry, a new data asset** | position streams are GB-scale | no |
| DRS-active fraction | Apparent only — **measured untrustworthy** (era-heterogeneous raw codes; wet-2019 contradiction) without zone validation | **no** | yes, windowed | yes (zone maps needed) | small | no |

No candidate passes the "genuinely new AND consistently available
AND alignable without new assets AND necessary" conjunction. More
granular data is not assumed to be better data.

## 7. Phase-2 objective test

Can Phase 3 legitimately compare strong models (Logistic
Regression, HGB, XGBoost, LightGBM, CatBoost, ExtraTrees,
Random Forest, ranking/ordinal/survival experiments) using the
current 84-definition set without telemetry? **Yes.** The matrix
covers state, pace, gaps, field context, traffic, rates, weather,
race control, priors and interactions — the defensible minimum
(wave 1) plus the high-complexity wave-2 families the plan review
required before Model Lab. Telemetry is therefore **not REQUIRED**.
The burden of proof for activation is unmet: no ablation or model
result exists (Phase 2 correctly runs no training), so trigger (1)
cannot be satisfied at F12 time by construction.

## 8. Temporal-alignment risk (LAP_END semantics)

Target state at T = the driver's own `state_time_s` (LAP_END).
Any telemetry summary must use only samples with timestamp ≤ T —
the D8 contract already fixes the window as
`[lap_start_s, state_time_s)`. Documented risks a future telemetry
phase must prove it handles:

- Whole-lap summaries accidentally including samples after T
  (late-crossing rivals, flush/delayed packets attributed to the
  wrong lap).
- Asynchronous channels (car_data vs position_data clocks;
  per-driver LAP_END clocks differ by design — the F1 as-of rule
  is the guard).
- Resampling/interpolation across lap boundaries (forbidden unless
  the contract explicitly allows a named method with tests).
- Lap-boundary alignment (pit-in/out laps, SC/VSC laps, red-flag
  laps, first laps — the same eligibility questions F5 answered
  for lap times, unanswered for telemetry).
- Session-time synchronization (Time vs Date vs SessionTime
  channels; timezone/clock validation).
- Late/missing samples (sparse windows must compute-from-what-
  exists or null honestly, per the D8 missingness policy — never
  impute, never borrow from lap N+1).

Future requirement: a telemetry mutation test (mutate/delete all
samples with t > T → state features identical) alongside the
family, mirroring the per-family leakage gates of F4–F11 — not
deferred to a combined suite.

## 9. Granularity mismatch

Canonical grain is driver-lap LAP_END state (189,420 rows);
telemetry is high-frequency time series (median 320–872
samples/lap; 6.78M samples over 7,710 windows). Reduction to safe
driver-lap summaries requires frozen answers to:

- Which samples belong to a completed lap? (D8: half-open
  `[lap_start_s, state_time_s)` — reuse, do not reinvent.)
- Are summaries emitted only after lap completion? (Must be: LAP_END
  availability; no partial-lap telemetry state.)
- How are partial/incomplete laps treated? (Retirements, red flags,
  timing nulls — null-with-reason policy needed.)
- How are pit laps handled? (In/out laps distort speed/throttle/
  brake distributions — eligibility mask needed, as F5 did.)
- How are red/SC/VSC periods handled? (Belgium-2021 pattern: 1.41M
  samples over 60 canonical rows — most samples fall outside
  canonical windows; the contract must say what survives.)
- What is done with missing channels? (Per-channel null policy;
  2018-r02 has no blob at all.)
- Is interpolation allowed? (Default no; any exception needs a
  named method + test + registry documentation.)

These are future requirements only — defined here, implemented
never in F12.

## 10. Storage / compute cost

From D8 measurements (no rerun, no invented figures):

- **Raw high-frequency telemetry:** 16.16 GB cache whole-scope
  (car_data ~7.2 GB + position_data ~7.1 GB + HTTP ~1.7 GB);
  per-race car blob 30–84 MB; ~59 B/sample. Canonical retention of
  raw streams would duplicate GB-scale data into `data/v2` for no
  consumer — the cost ADR-0001 refused.
- **Compact lap-level summaries:** estimated <10 MB Parquet for
  ~189,420 rows; build ≈0.3–0.5 s/race from cache; peak RSS
  ~0.5 GiB for 8 races. Cheap to build later — which is precisely
  why deferral has very low regret and needs no urgency.
- The two must never be conflated: approving compact summaries
  later does not approve raw retention.

## 11. Historical coverage

D8 evidence: car_data missing for 2018-r02 (whole race); position
present for 171/173 sessions. Within the sample, coverage is
complete (7,710/7,710 windows, 0 nulls on measured channels) — but
the sample is 8/173 races and cannot prove whole-scope channel
uniformity. A telemetry family that is systematically missing for
early seasons (or channels with era-heterogeneous semantics, as
measured for DRS) would inject season artifacts into training
coverage. Missingness must ride along as explicit nulls with
validity companions (the F6 pattern), never imputation — and any
whole-scope activation needs a full 173-race coverage audit first,
not an 8-race extrapolation.

## 12. Circuit dependence

Raw summaries (mean speed, throttle fraction, brake fraction, gear
changes, rpm aggregates) have layout-dependent meaning: Monaco vs
a Monza-like layout differ structurally, not just in pace. Without
normalization they become weak circuit identifiers rather than
driver-performance signals. Circuit/sector normalization or corner
mapping would require track geometry — a new data asset with no
source, contract, or test in the frozen platform. That scope
belongs to a later dedicated telemetry/track-geometry phase, not
to Phase 2. The current matrix avoids the problem: lap times are
consumed relatively (vs leader/ahead/field/teammate at the same
race), which is intrinsically circuit-conditioned.

## 13. Model-Lab necessity assessment

No. The eight planned model families plus ranking/ordinal/survival
experiments can be evaluated, compared and ablated on the current
84-definition matrix (with the F16 family-grouping fixtures:
A basic state → … → H + priors; telemetry arm explicitly removed).
Model Lab must not be delayed awaiting telemetry: trigger (1) runs
the other direction — telemetry earns activation only AFTER
baselines show a specific unresolved signal on historical years.

## 14. Product-value assessment

Telemetry may eventually enrich driver comparison, corner/sector
visualization, Race Engineer explanations and what-if context —
but each of those is a future product capability needing the raw
position/car streams (GB-scale) via a dedicated asset pipeline
reading the cache, not compact ML summaries. Valuable eventually
≠ required now. Activating canonical telemetry for future UI
appeal would repeat the vanity-metric framing ADR-0001 explicitly
rejected.

## 15. Portfolio / engineering assessment

A well-defended deferral demonstrates scope control, data
architecture judgment, leakage awareness, cost/performance
reasoning and empirical decision-making. "More features" is not
better engineering: the restraint record of Phase 2 (3
interactions kept of many candidates; trend×stint rejected at 0.92
correlation; podium/win rates dropped at 0.976; catch-time and
rejoin projections banned; DRS inference refused) is the same
judgment applied to telemetry. The portfolio signal of F12 is a
revisit-check that did the work and confirmed the prior — not a
build for its own sake.

## 16. Future activation criteria (frozen checklist)

Telemetry may be reconsidered iff ALL of the following hold
(numbered for audit):

1. A Phase-3 bounded experiment on historical years (never the
   protected 2025 protocol) names a SPECIFIC unresolved signal
   (e.g. "braking-phase variance under green") with a precise
   hypothesis — not "telemetry in general".
2. The candidate family has exact formulas, units, temporal rule
   (`[lap_start_s, state_time_s)` window), sync declaration,
   min-history and missingness policy registered BEFORE code.
3. Historical coverage is audited over all 173 races (not the
   8-race sample): per-season/per-driver/per-channel missingness
   published; any systematic gap has a null-with-reason policy.
4. The temporal-alignment contract (§8) is proven by a
   future-mutation test green alongside the family.
5. A compact lap-grain representation is defined (<10 MB class);
   raw-stream retention is a separate asset decision, never
   implied.
6. Whole-scope build/storage cost is measured (D8 method), not
   projected.
7. Era-robustness is proven per channel (the DRS heterogeneity
   finding is the template: zone-validated or excluded).
8. Circuit dependence is handled (relative/normalized form or a
   sourced geometry asset with its own contract).
9. The feature improves held-out chronological evaluation
   materially under the Phase-3 protocol — ablation with/without
   the family, not in-sample fit.

## 17. Smallest responsible future experiment (defined, NOT executed)

1. Select a small representative race sample (reuse the D8 eight
   as the starting seed; add one street and one high-speed circuit
   if missing).
2. Define ONE candidate family (recommended: throttle/brake
   fractions — new information, consistent channels, no geometry
   needed; explicitly NOT DRS until zone validation exists).
3. Aggregate to completed-lap half-open windows only; pit/SC/VSC/
   red laps flagged by the F5 eligibility mask.
4. Prove ≤T alignment with the future-mutation test.
5. Compare frozen-baseline vs +family models on historical years
   (pre-2025), reporting the Phase-3 chronological metric with
   confidence intervals.
6. Measure build/storage cost by the D8 method.
7. Only then propose canonical activation via a new ADR
   superseding ADR-0001 — with a scoped implementation plan, never
   as a side effect of a review stage.

## 18. F12 decision

**A. KEEP DEFERRED** (unanimous on the evidence: §§2–17).

- Not B: no revisit trigger (§2) is objectively true. No model
  experiment exists yet (trigger 1 impossible pre-Phase-3); no
  product requirement exists (trigger 2); extraction cost/coverage
  is unchanged since D8 (trigger 3); no feature depends on raw
  telemetry (trigger 4); no new tested lap summary exists (trigger
  5).
- Not C: telemetry remains plausibly valuable later (position
  streams for track assets; throttle/brake fractions as the
  leading ML candidate). Permanent rejection would destroy option
  value for zero present gain.

## 19. Registry / version impact

- Zero active telemetry features added; active count unchanged
  (84); `FEATURE_SET_VERSION` remains **`v8`**.
- Telemetry concepts persist as deferred documentation only
  (this file + ADR-0001 + the §29 candidate list in the Phase-2
  plan); nothing telemetry-shaped is registered (verified:
  no `telemetry` family, no telemetry-like names, zero
  "telemetry" mentions in `v2/features/`, no `telemetry.py`
  module, no `telemetry_summary` artifact in
  `data/v2/processed/`).
- Had the decision been ACTIVATE, F12 would still implement
  nothing and return NOT READY FOR F13 pending a new scoped
  implementation plan. It was not.

## 20. F13 handoff

- F12 leaves no telemetry state for F13 to consume: the label-join
  contract stage proceeds on the unchanged v8/84-definition
  registry.
- F13 inputs (frozen): `driver_lap_state_d9` (189,420 rows,
  LAP_END), `race_driver_labels` (3,458 rows, race×driver grain),
  v8 registry + engine calculators F4–F11, D8/ADR-0001 evidence
  chain intact.
- No blockers carried forward. No telemetry pre-work required of
  F13. Phase-1 untouched (verified §21 of the F12 test suite).
