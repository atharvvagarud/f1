# Phase-2 Temporal Feature Engine — Plan Review (READ-ONLY, pre-F0)

> Scope: review-only audit of `V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md`
> against the frozen Phase-1 platform (D0–D12).
> No Phase-2 code implemented. No frozen file modified. No data ingested.
> No telemetry activated. No DNF target defined. F0 NOT started.
>
> Inputs read in full: `V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md`,
> `docs/PHASE1_EXIT_REPORT.md`, `data/README.md`,
> `docs/DATA_PLATFORM_ARCHITECTURE.md`, `docs/DATASET_V2_REPORT.md`,
> `docs/PHASE1_FINAL_VALIDATION.md`, `docs/LEGACY_V2_DATASET_COMPARISON.md`,
> `docs/adr/ADR-0001-telemetry-retention.md`, `v2/contracts.py`,
> `v2/d6schema.py`, `v2/d7schema.py`, `v2/d9schema.py`, plus targeted
> inspection of `v2/d9.py` and `v2/tiera.py` for semantics verification.

---

## 1. Executive conclusion

The original Phase-2 plan is **directionally sound but technically stale**.
Its temporal-safety instincts (trailing-only windows, past-only priors,
backward weather joins, label separation, leakage tests, no opaque scores,
training-serving parity) remain correct and should be kept. But it was
written **before Phase 1 existed** and therefore makes assumptions the
frozen platform now contradicts or constrains:

1. It treats telemetry as a conditional feature family (F11). ADR-0001 has
   since **DEFERRED telemetry from canonical data**; Phase 2 must not
   depend on it.
2. It assumes qualifying fields exist. Frozen reality: **only
   `grid_position` exists** (D5 `results`, PRE_RACE, from FastF1
   `GridPosition`); `Q1/Q2/Q3` are **explicitly dropped out of contract
   scope** (`v2/tiera.py::normalize_results`), and no quali-session
   ingestion exists. `qualifying_position` / `qualifying_delta_to_teammate`
   are **unavailable without new ingestion**.
3. It lists as "features" several quantities **D9 already derives**
   (`track_status`/`safety_car_active`-equivalents, pit counts,
   laps-since-pit, stint facts, race progress). Re-implementing them as
   features duplicates frozen derived state.
4. Its LAP_END default is right but **not enforced per-family**; several
   families (gaps, closing rates, traffic counts) are only well-defined
   with an explicit cross-driver synchronization rule at LAP_END, which the
   plan never states.
5. Its gap-to-leader family assumes a scalar seconds gap is always
   constructible. Frozen evidence (D10 legacy audit: min-reference +
   300 s clip defects; D9 holds **no gap column**) plus source semantics
   (per-driver lap-end clocks differ; lapped cars; SC bunching; missing
   timing) mean a **single scalar is not always valid** — representation
   must change.
6. Leakage tests are deferred to F14 (end). Given 189,420 LAP_END states
   and per-family temporal contracts, tests must move **alongside each
   family**.
7. Ablation/training/evaluation infrastructure (F16, §§40–42) mixes
   **Phase-3 Model-Lab responsibilities** into Phase 2.

**Recommendation: READY AFTER PLAN REVISION** (see §21–§23).
No blocker requires re-opening Phase 1. All corrections are plan-text
edits plus per-feature contracts to be written in F1/F2 before any
feature code.

---

## 2. Frozen Phase-1 input contract (authoritative)

- **Primary state: `driver_lap_state_d9`**, grain
  `(race_id, driver_id, lap_number)`, **189,420 rows** accepted build,
  per-season 22,337 / 23,676 / 18,352 / 23,758 / 23,577 / 24,422 /
  26,606 / 26,692. PK clean, 0 duplicates, 0 null PKs (D11).
- **Clock: `state_time_s` = LAP_END** (D6 lap-end `Time`, unchanged by
  D7/D9). Features for `(R, D, lap N)` may use only information
  observable at or before `state_time_s(N)`. No lap N+1 or later.
- **Labels: `race_driver_labels`**, grain `(race_id, driver_id)`,
  **3,458 rows** (420/420/340/440/440/440/479/479). Winners 173 (exactly
  one per race), podiums 519, points finishers 1,730, classified 3,007,
  unclassified 451 (R 420 / W 18 / D 13). All LABEL_ONLY,
  `predictive_eligible=False`. Join explicitly; never part of state.
  State tables carry **zero LABEL_ONLY columns** (asserted).
- **Availability vocabulary** (`v2/contracts.py`): `PRE_RACE /
  LAP_START / IN_LAP / LAP_END / POST_RACE / LABEL_ONLY /
  SOURCE_METADATA`. 39 predictive-eligible fields enumerated in D11; all
  LAP_START/IN_LAP/LAP_END. Quality/provenance metadata
  (`source_unit_status`, `shortened_race`, staleness anchors, message
  seqs, boundary lineage) is `SOURCE_METADATA`, never eligible.
  `deleted`/`deleted_reason`/`is_accurate` are conservative POST_RACE,
  never predictive.
- **D6 state columns (predictive-eligible base):** `position`,
  `lap_start_s`, `lap_time_s`, `sector_1/2/3_s`, `sector_*_end_s`
  (IN_LAP), speed traps `speed_i1/i2/fl/st_kmh`, `compound`,
  `tyre_life`, `stint_number`, `fresh_tyre`, `pit_in_s`/`pit_out_s`,
  `track_status` (verbatim code string, IN_LAP). Identifiers/clocks/
  quality flags are non-eligible.
- **D7 enrichment (24 nullable context columns, grain preserved):**
  backward as-of weather values (`wx_*`, 189,420/189,420 attached,
  mean staleness ~30 s, max 477.3 s); latest *timestamped* RC message
  lineage (`rc_last_message_*`; 69 untimestamped 2018-r02 messages never
  attach; 1,024 states without RC lineage); pit last-entry/exit event
  lineage (asymmetric in-only 246 / out-only 159 preserved, never
  manufactured); current-stint **start-side only**
  (`stint_start_lap`, `stint_compound`, `stint_fresh_tyre`,
  `stint_tyre_age_at_start`; 789 stint-null rows preserved; end_lap
  never attached). `predictive_eligible=True` only for wx physical
  quantities + `stint_compound`/`stint_fresh_tyre`.
- **D9 derived state (10 fields, all past-only):** `track_state`
  (all_clear 170,989 / yellow 6,541 / safety_car 8,237 / red_flag 310 /
  vsc 1,643 / vsc_ending 360 / null 1,340) + `flag_yellow`,
  `flag_safety_car`, `flag_red`, `flag_vsc` (last-code-char transform of
  per-lap TrackStatus, FastF1 3.7.0 mapping; no message-text state
  machine); `race_leader_laps_at_state` (max lap_number with
  `state_time_s <= t`, past-only); `race_progress_frac`
  (leader/scheduled; null when scheduled unknown);
  `pit_stops_completed_so_far` + `laps_since_last_pit_stop` (**full
  stops only**, `pit_out_s <= state_time_s`, 0 on exit lap);
  `stint_lap` (lap − start + 1, null when no start fact).
- **Supporting D5/Tier-B use:** allowed only when a feature genuinely
  needs source history, with its own temporal contract + mutation tests
  (`data/README.md` §10). D5 tables: `races` (incl.
  `total_laps_scheduled`, PRE_RACE; `grid_position` lives in `results`,
  PRE_RACE), `driver_laps`, `pit_stops` (6,336; 0 negative durations),
  `stints` (9,324), `weather` (25,779; wind m/s), `race_control`
  (14,992; 14,923 timestamped). Tier-B (76 seasons, 1,149 races, 25,784
  results) for past-only priors.
- **Telemetry: DEFERRED (ADR-0001, Accepted).** `telemetry_summary`
  INACTIVE; no canonical telemetry bytes; `v2/d9.py` imports no car
  data. Cache (~16.16 GB) is source-only. Phase 2 must not depend on
  telemetry.
- **DNF: no binary target defined.** `classified_flag` /
  `results.dnf_flag` are provisional classification evidence, not a
  modelling target. Do not invent one.
- **PARTIAL/shortened races are first-class:** 2021-r12 Belgium (60
  rows) + 2022-r18 Japan (507 rows) PARTIAL, kept with
  `source_unit_status`/`shortened_race` metadata; plus COMPLETE-but-
  time-limited races flagged `shortened_race=true`. No silent exclusion.
- **Known missingness (preserved, never imputed):** lap_time 3,169;
  s1 4,029; s2 389; s3 548; speed_i1 28,013; speed_st 15,135; compound
  1,308; tyre_life 1,504; stint 789; track_status 1,340 (2018-dominated);
  position 294; 2025-r06 Miami 446 stint-null rows; Belgium 2021 all-60
  compound null. No global imputation is permitted in feature
  generation.

---

## 3. Problems found in the original Phase-2 plan

P1. **Telemetry family (F20/F11, §§29/46) contradicts ADR-0001.**
Plan says "implement if Phase 1 approved them" — Phase 1 decided:
DEFERRED. Any telemetry stage, registry entry, or ablation arm (I in
§40) depending on canonical telemetry is invalid by default.

P2. **Qualifying context (§24/F15) assumes unavailable fields.**
`qualifying_position` and `qualifying_delta_to_teammate` do not exist:
Q1/Q2/Q3 are dropped out of contract scope; no quali-session ingestion
ran (Race-only scope, D1 §5). Only `grid_position` (D5 results,
PRE_RACE) exists, and it is **not in D9 state** — it needs an explicit
D5 join. Sprint-weekend grid provenance needs the D4 sprint cross-check
note carried forward.

P3. **Duplicates D9 derived state as "features".** `track_status`,
`safety_car_active`/`vsc_active`, `pit_stop_count_so_far`,
`laps_since_last_pit`, `current_stint`/`current_compound`,
`race_progress_pct`-equivalents already exist as D9/D7 state with
tested semantics. Plan §§8/14/16/20 re-list them without referencing
D9, inviting re-implementation and drift.

P4. **Temporal boundary stated once (§3) but not operationalized.**
"After the driver completes lap L" is correct LAP_END, but families
F2/F9/F10/F17 compute **cross-driver quantities** (gaps, traffic
counts, spreads, leader-referenced deltas) where each driver's lap-N
ends at a *different* `state_time_s`. The plan never defines the
synchronization rule (each evaluated at the subject's own clock vs a
common race clock), which decides leakage.

P5. **Gap family (§9) assumes scalar-seconds gaps always exist.**
No frozen gap column exists (by design; D10 proved legacy's was
broken). Source clocks are per-driver LAP_END; lapped cars, SC
bunching, red flags, leader changes, and 3,169 null lap times break a
naive `session_time − leader_time` rule. Plan punts all of this to
"handle explicitly" with no representation fallback.

P6. **"Clean-air / representative pace" terminology (§11) overclaims.**
Plan correctly warns against removing slow traffic laps, but then
names outputs `representative_pace_*` and implies clean-air pace is
derivable. Frozen data has **no following-distance sensor, no DRS-zone
validation, no position-data canonical layer** — clean air cannot be
established from lap times + gaps alone.

P7. **Degradation framing (§15/F7) risks overstatement.**
`stint_pace_slope` from raw lap times confounds fuel burn, track
evolution, traffic, weather drift, SC. Plan's caution ("conservative
names") is right but the candidate list still centers slope-as-signal
without requiring confounder controls or minimum-sample rules.

P8. **Pit/rejoin boundary (§16/F8) mixes facts with speculation.**
`estimated_pit_loss`, `estimated_rejoin_position`,
`traffic_after_projected_pit` are strategy/Monte-Carlo quantities
needing pit-loss and future-field assumptions. Plan allows them "if
definable from current/past information" — that bar is never
operationalized, so speculative values could enter the ML matrix.

P9. **Priors (§§22–23/F10) under-specify identity and cold start.**
Season-scoped constructor IDs (`toro_rosso→alphatauri→rb`,
`racing_point→aston_martin`), substitute drivers (bearman/de_vries/
doohan/lawson), driver-number mutability, Jolpica-vs-FastF1 W-row
representation differences, and minimum-history/smoothing rules are
absent despite being measured Phase-1 findings.

P10. **Weather/RC families (§§20–21/F9) blur raw vs derived.**
Plan lists `track_status` alongside `safety_car_periods_so_far` /
`laps_since_caution` without distinguishing D9's tested TrackStatus
flags from new RC-message derivations (which need their own leakage
tests and must handle the 69 untimestamped 2018-r02 messages and the
1,024 no-lineage states). Weather deltas/trends are proposed with no
staleness guard (max 477 s gaps measured).

P11. **Reliability (§§22–23) smuggles a DNF target.**
`driver_dnf_rate_previous_5` / `constructor_dnf_rate_previous_5` as
features require a **historical event definition** of DNF. Phase 1
refused the binary target; R/W/D tokens + nulls + `status_text` are
not interchangeable. Plan never defines the event, so it silently
invents the deferred target.

P12. **Missingness (§30) is correct in principle but per-family
fallback rules are missing.** "Do not globally replace nulls" is
stated; what null *means* for `gap_to_ahead` (no car ahead / leader),
early-lap windows, retired teammates, 2018 track-status nulls, Miami
2025 stint nulls is never specified.

P13. **Leakage architecture (§36/F14) is end-loaded.**
All mutation tests live in F14 after F3–F13 build everything. A family
built without its mutation test for 5+ stages invites baked-in
leakage (especially priors, weather, RC, pit futures, stint ends).

P14. **Phase-2/Phase-3 boundary violated (§§40–42/F16).**
Ablation *infrastructure* is fine; but §§40–42 specify evaluation
metrics (log loss/Brier/calibration/top-k), stage-of-race analysis,
and family ladders A–I that pre-judge the Model Lab's chronological
protocol and model comparison. Phase 2 must stop at feature matrices
+ fixtures + descriptive quality reports.

P15. **Stage order (F0–F17) needs repair.** F3 builds race-state/gap
features before the primitive temporal operators and registry
versioning are proven; gaps (highest leakage risk) come before
representative-pace primitives they depend on; priors (needing
Tier-B identity work) sit late with no cold-start gate; rejoin
speculation (F8-high-complexity) precedes parity/leakage scaffolding.

P16. **Minor but binding:** `total_laps_known`/`remaining_laps_estimate`
(§8) must reference **scheduled** (PRE_RACE) vs **observed leader
laps** explicitly — eventual completed distance is future information
at early states in PARTIAL/time-limited races. `drivers_running` /
`cars_on_lead_lap` need a past-only derivation rule (retirement is
only known when the driver's laps stop + classification is POST_RACE).
`compound_vs_teammate` (§13) as a string is not a model feature without
an encoding rule (and SOFT/MEDIUM/HARD ordering is rightly banned —
keep the ban). `wind_direction` circularity (0–359°) needs a
representation rule, not raw degrees in a linear model.

---

## 4. Feature-family KEEP / MODIFY / DEFER / REMOVE matrix

Verdict definitions: KEEP = build as planned (with §5 contracts);
MODIFY = build only with stated semantic changes; DEFER = valid later,
not in first feature set; REMOVE = do not build (duplicates frozen
state, needs unavailable data, or belongs elsewhere).

| ID | Family (plan §) | Verdict | Reason (one line) |
|----|-----------------|---------|-------------------|
| A | Race progress / current position (§8/F1) | MODIFY | Keep `position`, leader-lap progress on **scheduled** distance; D9 already owns progress/pit/stint derivations — reference, don't rebuild; define `drivers_running` past-only rule |
| B | Gap to leader / relative gaps (§9) | MODIFY | Rebuild required (legacy NOT authoritative); scalar not always valid — adopt §6 multi-field representation + sync rule |
| C | Recent pace windows (§10) | MODIFY | Keep trailing-only; add eligibility masks (pit/SC/VSC/yellow/red/wet-transition/null) + sample-count columns; no centered windows |
| D | Representative pace (§11) | MODIFY | Keep deterministic flag + counts, but rename: **eligible-pace**, not "clean-air"; clean-air claim REMOVE-d unless provable |
| E | Relative pace (§12) | MODIFY | Highest value; requires gap-sync rule + eligibility-matched windows + sign convention; else leakage/noise |
| F | Tyre state (§14) | KEEP | Observed facts (`compound`, `tyre_life`, `stint_lap`, fresh) + relative deltas; keep no-numeric-ordering ban; add missingness rule |
| G | Stint/degradation (§15/F7) | MODIFY | Conservative proxies only (`stint_pace_trend_*`, never "degradation"); require min-sample + confounder-exclusion masks; slope without controls DEFER |
| H | Pit state / pit-window (§16/F8) | MODIFY | Factual past-pit state KEEP; projected/rejoin quantities DEFER to Monte Carlo (see §8) |
| I | Rejoin estimates (§16) | DEFER | Needs pit-loss + future-field assumptions — strategy-stage quantity, not ML feature |
| J | Traffic / pack state (§17/F9) | MODIFY | Keep threshold counts **only** under frozen gap-sync rule with null-gap policy; DRS-eligibility inference REMOVE |
| K | Closing rates / catch-time (§18) | MODIFY | Keep rates with zero/near-zero/divergence guards (null, not inf); catch-time estimates DEFER unless guards proven |
| L | Teammate-relative (§13) | MODIFY | Keep with retired/substitute/missing-teammate null policy; string `compound_vs_teammate` needs encoding rule or REMOVE |
| M | Driver historical priors (§22) | MODIFY | Past-only with Tier-B+D5 identity rules, min-history, smoothing, cold-start; DNF-rate component DEFER to §12 decision |
| N | Constructor priors (§23) | MODIFY | Same as M + season-scoped ID lineage; no cross-season rename merging |
| O | Grid / qualifying (§24) | MODIFY | `grid_position` + `positions_from_grid` KEEP via explicit D5-results join (PRE_RACE); `qualifying_position`/deltas **DEFER — unavailable** (Q columns dropped, no quali ingestion) |
| P | Circuit context (§25) | MODIFY | `circuit_id` + past-only rates KEEP with min-history + small-sample smoothing; `street_circuit` needs a sourced lookup or REMOVE; pit-loss history DEFER |
| Q | Race-control context (§20) | MODIFY | D9 flags KEEP by reference; new RC-message counts/recency MODIFY with own temporal contract (timestamped-only, 2018-r02 policy); NLP/embeddings/LLM REMOVE |
| R | Weather context (§21) | MODIFY | Current as-of values KEEP by reference (D7); backward deltas/trends MODIFY with staleness caps; forecasts REMOVE; future-nearest REMOVE |
| S | Reliability priors (§§22–23 part) | DEFER | Past-only reliability prior allowed **only** with explicit event definition; binary DNF target stays deferred — default DEFER (see §12) |
| T | Field / pack structure (§26) | MODIFY | Spreads/percentiles KEEP under gap-sync rule; pack-membership needs algorithmic definition + null-gap policy |
| U | Momentum/trend (§27) | MODIFY | Position/gap/rank changes KEEP with eligibility-matched endpoints; model-probability feedback REMOVE (already banned) |
| V | Domain interactions (§28) | MODIFY | Keep small interpretable set with units/signs; per-remaining-lap normalization must use **scheduled** remaining, not eventual; polynomial auto-expansion REMOVE; projected-pit terms DEFER with H/I |
| W | Telemetry-derived (§29/F11) | DEFER | ADR-0001: no canonical telemetry; no Phase-2 dependency. Revisit only via ADR triggers |

No family is adopted wholesale; every retained family needs the §5
contract fields before implementation.

---

## 5. Detailed semantic corrections (per retained family)

Every retained feature MUST declare before code: canonical name,
family, dtype, unit, description, exact source fields, formula,
temporal availability, minimum history, missingness policy,
predictive eligibility, feature version. Opaque scores
(`pace_score`, `strategy_score`, `driver_quality_score`, …) remain
banned unless mathematically explicit and interpretable (keep plan
§19/§50 bans).

- **A. Progress/position.** `current_position` = D6 `position`
  (LAP_END) by reference. `total_laps_known` = D5
  `total_laps_scheduled` (PRE_RACE) by reference — never the eventual
  observed total at an earlier state. `race_progress_frac` = D9 by
  reference. Any `remaining_laps_*` = scheduled − leader-laps (both
  past-only at clock); never scheduled − eventual. `drivers_running` /
  `cars_on_lead_lap`: define past-only rule (e.g. drivers with a state
  row at/after clock − grace; lead-lap via lap-count vs leader-laps at
  clock, not final classification). `positions_from_grid` = grid (D5
  results PRE_RACE join) − current position; null when either null
  (esp. the 3 W-rows with null FastF1 positions).
- **B/E/J/K/T.** All cross-driver quantities share one frozen **sync
  rule** (see §6): evaluated at the subject's `state_time_s` using each
  rival's latest state with `state_time_s <= subject clock`
  (as-of join), never rival lap-N+1. Deltas carry the rival's staleness
  where material.
- **C/D/E.** Windows 3/5/10 are trailing over **eligible laps only**
  (`is_eligible_pace_lap`, see §7). Store `*_n` (sample count) beside
  every windowed stat. `pace_std_*`/`pace_trend_*` require min-n
  (e.g. std n≥3, trend n≥3) else null. First laps: unavailable until
  enough eligible history — null, never backfilled from future.
- **F.** `compound` stays categorical (closed set incl.
  INTERMEDIATE/WET + verbatim 2018 names where present; null stays
  null). Relative tyre-age deltas are integer lap differences with
  null-propagation when either side null (Miami 2025 / Monaco 2022
  patterns). No numeric compound-strength ordering.
- **G.** Only `stint_pace_trend_*` / `pace_loss_recent_5`-as-proxy
  names until validated with confounder controls. Slope features must
  document exclusion masks (pit/SC/VSC/yellow/red/wet-transition) and
  min-n; within-stint residual approaches need an explicit fuel/track-
  evolution disclaimer and stay experimental.
- **H/I.** Factual: completed-stop count / laps-since (D9 by
  reference). Anything with "estimated/projected" in the name is a
  **strategy quantity**, not a Phase-2 ML feature (see §8).
- **L.** Teammate = other driver with same `constructor_id`
  (season-scoped) in the same race. Substitute/missing/retired
  teammate → null, never fabricated. Pace-vs-teammate uses
  eligibility-matched windows on both sides.
- **M/N/P.** Past-only over Tier-B + D5 results; race N may use races
  1..N−1 only (season boundary: no current-season future rounds; no
  final-season aggregates at earlier rounds). Season-to-date aggregates
  are allowed only from strictly prior rounds of the same season.
  Smoothing (e.g. Laplace/shrinkage to field mean) + min-history +
  cold-start (rookie/substitute → global prior, flagged) must be in
  the contract. Constructor identity is `(id, season)`; renames are
  distinct — no silent lineage merging.
- **O.** `grid_position`: D5 `results` PRE_RACE join on
  `(race_id, driver_id)`; document the 3 W-row nulls + Jolpica
  back-ranking difference (both sources preserved; FastF1 nulls stay
  null). No qualifying times/deltas without new ingestion (see §10).
- **Q.** Two layers kept separate: (i) D9 TrackStatus flags by
  reference; (ii) new RC-message features (counts-since, laps-since-
  caution, last-category recency) computed from **timestamped messages
  only** (`observed_at_s <= clock`), with the 2018-r02 all-untimed
  policy (null lineage, never invented) and 2020-r11 early-lap
  no-prior-message nulls. No text embeddings, no LLM features, no
  message-text state machine unless explicitly justified with tests.
- **R.** Current as-of `wx_*` by reference (D7). Deltas/trends are
  backward differences between the as-of observation and the latest
  prior observation ≥k seconds/laps earlier; cap staleness (e.g. null
  the trend if `wx_age_s` exceeds threshold or the support gap exceeds
  the measured anomaly bands); no interpolation, no smoothing, no
  future-nearest, no forecasts. `wind_direction` circular: use
  sin/cos components or binned sectors, never raw 0–359° as linear.
  `rain_started_recently`: backward transition on the as-of bool
  series only.
- **T/U/V.** Spreads = percentiles/max−min over as-of gap vector with
  null-gap policy stated. `driver_gap_percentile` needs tie + null
  rules. Momentum endpoints must both be eligible states (no pit/SC
  endpoints unless the feature explicitly allows them). Interaction
  terms carry compound units (e.g. s/lap × laps = s) and sign
  conventions in the registry.

---

## 6. Gap-to-leader design recommendation (no implementation)

**Proposed semantics.** For subject state `(R, D, lap N)` with clock
`t = state_time_s(N)`:

1. For every rival `D'` in race R, take rival's latest state with
   `state_time_s <= t` (backward as-of; ties share group maximum,
   mirroring D9's leader-lap construction). Rival lap `n'` and rival
   `state_time_s(t')` are both known at `t`.
2. Primary representation is a **struct, not a scalar**:
   - `gap_to_leader_s`: `t − t_leader`, where `t_leader` is the
     leader-reference clock at `t` (the max rival `state_time_s <= t`
     among drivers on the lead lap), **nullable**;
   - `gap_to_leader_laps`: leader-laps-at-`t` − subject-lap-N (integer;
     covers lapped cars where seconds mislead);
   - `gap_to_leader_valid`: enum/bool reason
     (`ok | subject_or_leader_time_null | leader_ambiguous_sc_red |
     timing_missing`);
   - companions `gap_to_ahead_s` / `gap_from_behind_s` with
     `rival_driver_id` + `rival_staleness_s = t − t_rival` so
     consumers see sync error.
3. `gap_to_leader_s = 0` iff subject is the as-of leader at `t`
   (not via session-minimum). Legacy min-reference is banned (D10:
   672/2,067 lap-10 rows pinned at 300 s; 2019 Belgium 20/20 at 300).
   No `[0,300]`-style clipping — investigate outliers, never censor
   (plan §38 already requires this; enforce for gaps).
4. **Edge cases:** same-lap timing (multiple drivers share identical
   `state_time_s` → group-max rule, zero gaps among the group are
   legitimate); lapped cars (seconds gap keeps growing across laps —
   always pair with the lap-deficit field); missing timing (3,169 null
   lap times; 294 null positions; 1,340 null track_status) → null gap,
   never interpolated; SC/VSC (field bunches; gaps compress — valid
   but must be consumed with `track_state`; consider a
   `gap_under_caution` flag rather than dropping); red flags (clock
   jumps; leader ambiguous — `valid=false`, null seconds); leader
   changes (reference re-resolves every state; no session-fixed
   leader); source semantics (per-driver LAP_END clocks differ by
   design — the as-of rule IS the leakage guard; rival lap-N+1 with
   `state_time_s > t` is forbidden even if its lap number equals N).
5. **What D9 already gives:** `race_leader_laps_at_state` provides the
   lap-index side. Phase 2 adds only the time-difference side + rival
   resolution + validity struct, with future-mutation tests (mutate any
   rival state with time > `t` → subject gaps unchanged).

If a consumer needs "one number", the registry must still document it
as `gap_to_leader_s | null` + `gap_to_leader_laps` + validity — a bare
scalar column alone is **not approved**.

---

## 7. Pace / degradation recommendations

- **Eligibility mask first.** Define `is_eligible_pace_lap` from
  frozen fields only: exclude pit-in/out laps (`pit_in_s`/`pit_out_s`
  non-null), laps under SC/VSC/yellow/red (`track_state != all_clear`
  → ineligible for representative windows; kept for raw windows with a
  flag), first lap of race + first lap after restart/red (warm-up /
  formation effects), null/invalid lap times, `deleted` handling per
  POST_RACE policy (provenance only — decide explicitly whether
  stewards-deleted laps enter pace; default exclude with a flag), wet/
  dry transition laps (rainfall bool change ±1 lap → ineligible for
  representative windows). Traffic-affected laps stay **eligible**
  (plan §11 is right: traffic is performance) — slowness alone never
  excludes.
- **Windows:** trailing 3/5/10 over eligible laps with
  `representative_lap_count_*` beside every stat. Raw
  `pace_mean/median_*` and representative `eligible_pace_mean/median_*`
  coexist; document which one each downstream consumer uses. Median is
  the default central tendency (robust to the long-tail lap-time
  distribution under yellows/pits that slip the mask); mean is
  reported alongside, never alone, for skewed windows. `pace_std`
  n≥3, trend/slope n≥3 (else null).
- **Terminology:** "representative" means "passes the eligibility
  mask". **Do not call anything "clean-air pace"** — frozen data
  cannot establish clean air (no following-distance channel, no
  validated DRS-zone signal, position data not canonical). If a future
  asset pipeline provides validated proximity, revisit with proof.
- **Wet/dry:** rainfall transitions split windows (no window spanning
  a dry→wet boundary is "representative"). Compound changes do not
  auto-split raw windows but must be exposed (`compound_changes_in_
  window`) so the Model Lab can condition.
- **PARTIAL races:** Belgium 2021 (60 rows, max 3 laps/driver) yields
  almost no eligible windows — nulls, not exclusion. Japan 2022 (507
  rows) yields short windows with counts exposed. Time-limitedथा races
  (Monaco 2022 64/77 etc.) behave normally with progress on scheduled
  distance.
- **Degradation conservatism:** within-stint slope/residual over
  eligible laps is **justified only as a proxy** (`stint_pace_trend`,
  units s/lap/lap) with min-n (≥4 eligible in-stint laps), exclusion
  masks above, and an explicit fuel/track-evolution confounder note in
  the registry. No future stint-end information (end_lap, next
  compound, next stop lap) may enter. Cross-driver
  `stint_pace_trend_vs_same_compound_field` needs compound-matched,
  eligibility-matched, caution-matched cohorts — default DEFER to a
  second wave unless the cohort rule + tests are written first.

---

## 8. Pit / rejoin boundary

- **Phase-2 factual set (build):** `pit_stops_completed_so_far`,
  `laps_since_last_pit_stop`, `stint_lap` (all D9 by reference — do
  not recompute); plus thin wrappers the registry defines once:
  `laps_since_last_pit_entry` (incl. in-only boundary cases, nullable),
  `last_pit_exit_lap`, `stint_tyre_age_now = stint_tyre_age_at_start +
  stint_lap − 1` (null-propagating; note TyreLife includes other
  sessions — source quirk, document it). Asymmetric stops are never
  "completed"; in-only/out-only rows affect only the entry/exit-side
  fields, never the completed count.
- **Strategy quantities (DEFER to Monte Carlo/Strategy, not ML
  features):** `estimated_pit_loss`, `cars_inside_pit_loss_window`,
  `estimated_rejoin_position`, `traffic_after_projected_pit`,
  `remaining_laps_after_projected_pit`, `pit_loss_minus_gap_behind`.
  Each needs pit-loss (circuit- and condition-dependent, unmeasured in
  Phase 1), future-field-movement assumptions, and caution-risk
  conditioning. Putting a point-estimate rejoin position into the
  feature matrix bakes those assumptions into every downstream model.
  Phase 2 may record the *inputs* (gaps behind, track_state, tyre age)
  — not the projection.
- **Rule of thumb for the plan edit:** any feature whose formula
  contains "projected", "estimated rejoin", or "after pit" moves to
  the DEFERRED table with owner "Strategy stage".

---

## 9. Priors design (no implementation)

- **Universe:** Tier-B `hist_results` (1950–2025, 25,784 rows) +
  Tier-A D5 `results`/D9 labels (2018+, 3,458 rows) for recent-form
  features. For target race in season T, round r: eligible history =
  all races with `(season < T) OR (season == T AND round < r)`.
  Season-to-date aggregates use strictly prior rounds only. Final-
  season totals are banned at earlier rounds.
- **Minimum history / smoothing / cold start:** e.g. rolling
  k ∈ {3, 5} prior-race means/rates require n≥3 scored events else
  null + `prior_n` exposed; shrinkage toward era field-mean for n < 5
  (document λ); rookies/substitutes/returnees (no eligible history) →
  global prior + `is_cold_start=true`, never 0. Exact constants are
  F10 contract work, not this review.
- **Season boundaries:** points-system changes and field-size drift
  are absorbed by shrinkage + per-season standardisation notes; no
  cross-era numeric comparison without a normalisation rule.
- **Substitute drivers:** identity is `driver_id` slug (stable);
  `driver_number` never keys. Mid-season swaps (bearman/de_vries/
  doohan/lawson patterns) attach history to the *driver*, not the
  seat; seat-level features are out of scope for wave 1.
- **Constructor renames/season-scoped IDs:** `(constructor_id,
  season)` grain preserved (`toro_rosso→alphatauri→rb`,
  `racing_point→aston_marton` are distinct). No lineage merging; a
  curated mapping table is a separate decision, not a silent join.
- **DNF-rate components:** blocked on §12 — no prior may use an
  event definition Phase 1 refused to fix.

---

## 10. Qualifying / grid availability finding

- **Available now:** `grid_position` (D5 `results`, PRE_RACE, from
  FastF1 `GridPosition`). Covers all 173 races except the 3 W-rows
  where FastF1 leaves it null (2021-r22 mazepin, 2022-r02
  mick_schumacher, 2023-r15 stroll — Jolpica back-ranks them; both
  preserved, FastF1 nulls stay null). Sprint-weekend grids reflect the
  actual starting grid (sprint effect included); D4 sprint-results
  endpoint is the documented cross-check.
- **NOT available:** `qualifying_position`, `qualifying_delta_to_
  teammate`, Q1/Q2/Q3 times. `normalize_results` drops Q columns out
  of contract scope; no quali/FP/sprint-session ingestion ran
  (Race-only scope). Any plan candidate needing them requires **new
  source ingestion** (FastF1 quali sessions or Jolpica qualifying
  endpoint) — explicitly out of frozen scope; mark DEFERRED with
  dependency "new ingestion + contract + leakage tests", do NOT modify
  Phase-1 ingestion in this review.
- **Plan edit:** §24/F15 keeps `grid_position`,
  `positions_from_grid` (grid − position, null-propagating),
  `grid_vs_teammate` (both grids PRE_RACE, null-propagating). Strike
  or DEFER every `qualifying_*` candidate.

---

## 11. Weather / race-control design

- **Weather:** D7 as-of values are the feature (by reference). Phase 2
  adds only (a) backward deltas (`track_temp_change_last_k`,
  `air_temp_change_last_k`, pressure/humidity equivalents) as
  `wx(t) − wx(t−k)` over timestamped observations with staleness caps,
  and (b) `rain_started_recently` / `rain_stopped_recently` as backward
  bool transitions. No interpolation, no smoothing, no wetness index,
  no forecast columns. Staleness anomalies (2020-r01 max 477 s etc.)
  are carried as `wx_age_s` context, never repaired.
- **Race control:** keep D9 TrackStatus flags as the *timing-state*
  signal. New RC features (only if justified): `sc_periods_so_far`,
  `vsc_periods_so_far` (count of *entered* caution states from the
  TrackStatus token series up to clock — deterministic, no text),
  `laps_since_caution` (leader-laps since last non-`all_clear` token),
  `last_rc_category` recency from timestamped messages only. The 69
  untimestamped 2018-r02 messages never contribute; 2020-r11 early-lap
  nulls stay null. Multi-code strings (e.g. `'41'`, `'124'` — 702+
  matched legacy rows affected) are handled by the last-char rule with
  unknown-honesty (unknown → null), never int-coerced (legacy defect,
  D10 §9). No NLP, no embeddings, no LLM-derived state.

---

## 12. Reliability decision

- **Prior (predictive feature): DEFER by default.** A past-only
  reliability prior is admissible only with a written historical event
  definition that does not silently invent the deferred binary target,
  e.g. "unclassified (R/W/D token) in official classification" with
  the 16 pre-2018 scoring-R/D shared-drive rows adjudicated and the 3
  FastF1-null/Jolpica-ranked W-rows handled — plus min-history,
  smoothing, cold-start rules from §9. Without that definition in the
  registry, `driver_dnf_rate_previous_5` /
  `constructor_dnf_rate_previous_5` / `circuit_historical_dnf_rate`
  stay DEFERRED.
- **Target (outcome): stays DEFERRED.** No `dnf` label column is added
  in Phase 2. Factual `classified_flag` / `position_text` /
  `status_text` remain available as facts for the later task-policy
  decision. Do not add `dnf` to the label layer "for convenience".

---

## 13. Missingness policy (per family)

Phase-1 nulls are preserved; Phase 2 propagates them. Global
`fillna(0)` / median imputation inside feature generation is banned
(plan §30 kept and enforced). Per-family defaults:

| Situation | Policy |
|-----------|--------|
| Insufficient window history (early laps) | null + `*_n` count column; never backfill from future |
| No car ahead (leader) / behind (last) | gap/rival fields null + `has_car_ahead/behind` bool where needed |
| Rival timing missing at clock | gap null + validity reason; never interpolate rival clock |
| Retired/missing teammate | teammate fields null |
| Weather/RC no-prior (2018-r02 RC, 2020-r11 early) | null lineage; derived counts start at 0 only where "periods so far" is defined as count-of-entered-states (document the 0-vs-null choice per feature) |
| Tyre/stint nulls (Miami 2025 etc.) | null-propagate through deltas/ages; compound stays categorical-null |
| 2018 track_status nulls (1,317) | `track_state` null → caution-gated windows treat lap as ineligible (explicit), counts treat as not-caution only if the contract says so |
| Speed-trap nulls (I1 28,013) | traps are lap descriptors, not pace inputs by default; any trap feature is experimental with null policy stated |
| Grid nulls (3 W-rows) | `positions_from_grid` null |

Model-specific imputation lives in the Model Lab (Phase 3), with
statistics computed on past-only training folds — never in the
feature matrix.

---

## 14. Partial / shortened-race policy

No automatic exclusion at feature-generation time. `source_unit_
status` + `shortened_race` ride along as non-predictive metadata.
Consequences per family: rolling windows yield short/null histories
with counts (Belgium 2021: ~3 laps max — nearly all null); progress
uses scheduled distance so Belgium shows progress ≈ 3/39 + leader-lap
rule still past-only; caution-heavy flag distributions are valid
inputs; priors are unaffected (race-level history). Any
model-stage filtering (e.g. "exclude <10-lap races from evaluation")
belongs to explicit Phase-3 evaluation policy with a stated rule —
never a silent `WHERE laps > X` in feature code.

---

## 15. Training–serving parity architecture

- **One implementation, two entry points.** Pure per-race functions
  `compute_features_for_state(race_state_prefix, race_id, driver_id,
  lap)` (single state, prefix-only inputs) + batch driver
  `build_race_features(race_id)` / `build_season_features(season)`.
  Batch is a loop over the single-state path (or a vectorised
  equivalent proven equal by parity tests) — never a separate pandas
  pipeline with its own windowing logic. D9 already models this
  (pure per-race helpers reusable for full build / one race / cutoff).
- **Prefix-only inputs.** The single-state path accepts only rows with
  `state_time_s <= clock` (+ PRE_RACE constants + strictly-prior race
  history). Anything needing "the whole race DataFrame" must filter
  to the prefix inside the function; code review rejects unfiltered
  `.groupby(race_id)` over full history.
- **No pandas-only batch idioms that imply future access:**
  `shift(-1)`, `rolling(center=True)`, `bfill`, full-race
  `cumsum`/`cummax` without a clock mask, `merge` on lap_number
  without a `state_time <= clock` guard. Prefer `searchsorted` on
  sorted clocks (D9's leader-lap/pit-history pattern) or masked
  groupby over the prefix.
- **Parity test (kept from plan §37, strengthened):** random sampled
  states across seasons/conditions (incl. PARTIAL races, SC races, wet
  races, 2018 sparse races): batch row == single-state row within
  float tolerance; registry version + source dataset version pinned in
  both paths.

---

## 16. Leakage-test architecture (strengthened)

Keep plan §36's six mutation suites; promote them from F14-only to
**per-family gates** (each family PR/stage runs its own subset) plus a
final combined suite. Required matrix:

- **Cutoff invariance (every family):** build at lap N → record →
  mutate/delete ALL source info with event time > `state_time_s(N)`
  (future laps, weather obs, RC messages, pit events, stint records/
  endings, results) → rebuild → features at/before cutoff identical.
- **Label mutation:** flip `winner_flag`/`position_final`/`points`/
  `classified_position` → state features unchanged, labels change.
- **Future-race mutation (priors):** alter results of races after
  target race (same season future rounds + future seasons) → priors
  for target race unchanged. Include season-boundary and substitute-
  driver cases.
- **Future-pit/stint:** insert/change a stop or stint end after lap N
  (incl. asymmetric in-only/out-only insertions) → lap-N pit/stint/
  pace features unchanged; completed-count only moves when a *past*
  exit is inserted.
- **Future weather/RC:** insert obs/message after clock (incl. SC
  after lap N) → lap-N wx/RC/track_state features unchanged;
  untimestamped-message insertion never attaches.
- **Future lap-time:** extreme lap N+1 (e.g. 300 s or null→value) →
  lap-N windows unchanged (catches centered-window / full-race-agg
  bugs). Synthetic rolling-window fixture per plan, kept.
- **Stint-end:** set/alter `end_lap` of the current stint → in-stint
  lap-N features unchanged.
- **Identifier mutation:** change driver_number/abbreviation/display
  names → features unchanged (keys are slugs).

Any unexplained failure blocks the family and phase exit (keep plan
F14 gate language).

---

## 17. Feature-registry recommendation

Minimum useful schema (machine-readable, stdlib-first like
`v2/contracts.py`; Parquet sidecar or JSON, not a store):

```text
name, family, dtype, unit, description, source_fields[],
formula, temporal_availability, minimum_history,
missingness_policy, predictive_eligible, feature_version, status
```

Keep plan §5's fields; **add** `source_fields[]` (exact, testable —
plan's `source` string is too loose), `predictive_eligible` (D11-style
gate; identifiers/lineage are registered but False), and require
`feature_version` per feature (not just set-level). Statuses
`candidate / validated / experimental / deprecated` kept. Generate
`docs/FEATURE_REGISTRY.md` from the registry (plan §45 kept). No
Feast/database/online store. Registry + version + manifest
(`feature_set_version`, `registry_version`,
`source_dataset_version=d9-canonical id`, `pipeline_version`,
`generated_at`, row/family/null/runtime/storage stats) is the
phase-exit evidence.

---

## 18. Phase-2 / Phase-3 responsibility boundary

- **Phase 2 owns:** temporal contracts, registry, feature families +
  per-family leakage tests, single-state/batch engine with parity,
  typed Parquet candidate matrices + manifest, descriptive
  feature-quality reports (dtype/unit/min/max/median/null-rate/unique/
  inf/outlier per §38 — description, not selection).
- **Phase 3 owns:** chronological evaluation protocol, model training/
  comparison, ablation *execution*, metric claims (log loss/Brier/
  calibration/top-k/latency), stage-of-race evaluation, model
  selection, calibration, and any imputation inside model pipelines.
- **Plan corrections:** F16 becomes "ablation *configuration +
  fixtures*" (family-subset manifests + deterministic row splits +
  label-join helper, no training, no metric ranking). §§40–42 move to
  Phase-3 plan; Phase 2 may keep §§38–39 (quality checks + suspicious-
  power leakage audit) as its own exit gates. "Recommended families
  for first experiments" stays a *recommendation list*, never a
  superiority claim.

---

## 19. Revised F0–F17 stage recommendation

Original order is sequential-gated and mostly right; revise to put
contracts/operators/tests before risky features and to split the
end-loaded gates:

```text
F0  Verify Data Platform (unchanged — read contracts/manifests/reports; STOP if unstable)
 ↓
F1  Freeze Temporal Contract (LAP_END + cross-driver as-of sync rule + PRE_RACE/prior-cutoff/weather/RC/pit/stint rules + core temporal tests BEFORE features)
 ↓
F2  Registry / Schemas / Versioning + parity harness skeleton (metadata layer first; no features yet)
 ↓
F3  Primitive temporal operators (prefix filter, as-of join, trailing-window helper, count/exposure helper — tested once, reused everywhere)
 ↓
F4  Race-state passthrough + factual pit/stint wrappers (D9/D7 by reference; no recomputation; establishes canonical output + manifest early)
 ↓
F5  Eligibility mask + pace windows (raw + eligible, with counts) — pace primitives before anything that consumes them
 ↓
F6  Gap engine (struct representation + sync rule + validity) — after pace primitives; highest-risk family gets operators + tests ready
 ↓
F7  Relative pace / teammate-relative / field spreads / traffic counts (consume F5–F6; shared guards)
 ↓
F8  Closing rates / momentum / cautious trends (consume F5–F7; divergence/zero guards; catch-time DEFERRED by default)
 ↓
F9  Race-control + weather derivations (timestamped-only RC; backward wx deltas with staleness caps)
 ↓
F10 Priors: driver / constructor / circuit + grid passthrough (Tier-B identity work, min-history/smoothing/cold-start; DNF-rate DEFERRED)
 ↓
F11 Domain interactions, thin + interpretable (only on validated F5–F10 inputs; projected-pit terms excluded)
 ↓
F12 Telemetry revisit CHECK (default: confirm DEFERRED per ADR-0001; no build unless an ADR trigger is objectively met)
 ↓
F13 Label-join layer (explicit race×driver join helper + fixtures; no label in state; NO new targets incl. DNF)
 ↓
F14 Combined leakage + parity suite (all families; sampled historical states incl. PARTIAL/SC/wet/2018-sparse)
 ↓
F15 Batch candidate matrix (typed Parquet, season-partitioned, manifest + quality report)
 ↓
F16 Ablation configuration + fixtures ONLY (subset manifests + split helpers; no training, no model comparison)
 ↓
F17 Documentation + phase exit (architecture + generated registry + engine report with actual counts/tests/perf/limitations)
```

Changes vs plan §46: registry/versioning/parity-skeleton before
features; operators before families; factual passthrough before
derived; pace before gaps; gaps before consumers; RC/weather after
core kinematics; priors after identity rules are written; telemetry
demoted to a check; labels adjacent to batch (not mid-features);
leakage per-family (in F4–F11 gates) + combined F14; F16 stripped to
config/fixtures.

---

## 20. Complexity / value assessment

- **High-value + low/medium complexity (wave 1):** eligibility mask;
  raw + eligible trailing pace (3/5) with counts; relative pace vs
  leader/ahead/field-median (3/5); tyre observed state + age deltas;
  factual pit/stint wrappers; grid passthrough; current wx as-of;
  D9 flags by reference; position/progress passthrough. Defensible
  Model-Lab input on its own.
- **High-value + high complexity (wave 2, needs operators+tests
  first):** gap engine (struct + validity); traffic counts;
  field spreads/percentiles; closing rates (not catch-time);
  teammate-relative pace; backward wx deltas; RC counts/recency;
  driver/constructor/circuit priors with smoothing/cold-start.
- **Questionable value (justify or drop):** 10-lap windows on short
  races (keep only with counts; rarely eligible early); speed-trap
  features (28k+ nulls, circuit-dependent); `street_circuit` without a
  sourced lookup; `wind_direction` raw; string
  `compound_vs_teammate`; multi-interaction terms before base families
  validate.
- **Better suited to Monte Carlo / Strategy (not ML features):**
  rejoin position, pit-loss windows, traffic-after-projected-pit,
  remaining-after-projected-pit, pit_loss_minus_gap_behind,
  estimated laps-to-catch (point estimates with future assumptions).
- **Dependent on unavailable data (DEFER with dependency):**
  `qualifying_*`, Q-deltas, telemetry summaries, DRS-eligibility,
  clean-air pace, forecast weather, pit-loss history.
- **Leakage-risk hotspots:** gaps (rival future), pace windows
  (centered/full-race aggs), priors (current/future races,
  final-season stats), weather (future-nearest), RC (message-text
  state machine, untimed messages), pit/stint (future stops/ends),
  progress/remaining (eventual distance), labels (any outcome in
  state).

Goal is the smallest defensible temporal set for the Model Lab, not
maximum column count (plan §1/§50 principle kept).

---

## 21. Required edits to V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md

1. §2/§29/F11/F16-§40: replace telemetry family with ADR-0001 DEFER
   default + revisit triggers; remove telemetry ablation arm.
2. §3/F1: freeze LAP_END + add cross-driver as-of sync rule,
   PRE_RACE/prior-cutoff, stint-end/pit-future bans as normative text.
3. §8/F3: reference D9 derived fields by name (progress, pit counts,
   stint_lap, track flags) as passthrough; define
   `remaining = scheduled − leader` + `drivers_running` past-only
   rule; ban eventual-distance use.
4. §9/F3: replace scalar gap list with §6 struct + validity +
   rival-staleness + no-clip rule.
5. §§10–12/F4–F5: add eligibility mask + `*_n` counts + min-n rules;
   rename "representative" → "eligible"; ban "clean-air" claim;
   document sign conventions.
6. §15/F7: rename to trend/proxy; require masks + min-n +
   confounder note; cohort-comparison terms default DEFER.
7. §16/F8: split factual (build) vs projected/rejoin (DEFER to
   Strategy); list deferred terms explicitly.
8. §§22–23/F10: add identity/cold-start/smoothing/season-boundary/
   rename rules; remove or gate DNF-rate features on §12 definition.
9. §24/F15: keep grid trio; move all `qualifying_*` to DEFERRED with
   "new ingestion required".
10. §§20–21/F9: separate D9-flags-by-reference from new RC/wx
    derivations; add timestamped-only + 2018-r02 + staleness-cap
    rules; ban forecasts/NLP/LLM/int-coercion.
11. §30–§31: add per-family null table (§13) + early-lap counting
    rule; ban global imputation in generation.
12. §36/F14 + §§46–47: move mutation tests per-family; keep combined
    F14; add prior/future-race + stint-end + identifier suites (§16).
13. §33/§37: mandate single-state-prefix + batch-loop parity
    architecture; ban listed future-implying idioms.
14. §5/§35: extend registry schema (`source_fields[]`,
    `predictive_eligible`, per-feature version) + generation rule.
15. §§40–42/F16: strip to config/fixtures; move metrics/model
    comparison/chronological protocol to Phase 3.
16. §46: adopt §19 stage order (operators early, pace before gaps,
    telemetry-as-check, labels late, per-family leakage).
17. §§49/51: re-tier priorities per §20 waves; add wave-1 exit as the
    defensible-minimum gate.

---

## 22. Blockers before F0

None require re-opening Phase 1. F0 may be authorized once the
following are recorded (plan-text or F1-contract decisions, no code):

1. Plan revision per §21 applied (or an accepted amendment note) —
   otherwise F-stages will build telemetry/qualifying/rejoin features
   against unavailable or deferred sources.
2. LAP_END + cross-driver sync rule frozen in writing (F1) — gaps,
   traffic, spreads, and relative pace are undefined without it.
3. Gap representation decision (§6 struct vs scalar) accepted —
   highest-leakage family; do not start F6 without it.
4. DNF-event definition for priors either written or explicitly
   deferred (S-priors stay out until then).
5. Registry schema + versioning + parity harness skeleton order
   confirmed (F2 before F4+) so per-feature contracts have somewhere
   to live.

---

## 23. Recommendation

**READY AFTER PLAN REVISION.**

The plan's safety instincts are right; its pre-Phase-1 assumptions
about telemetry, qualifying, gaps, D9 duplication, stage order, and
the Phase-2/Phase-3 boundary are not. Apply the §21 edits, freeze the
§22 decisions, then authorize F0 → F1 → F2 before any feature family
code. Do not authorize feature implementation directly against the
plan as written.

---

*Review artifacts: this file only. No modification to
`V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md`, frozen Phase-1 code/
contracts/data, or feature-engine modules. No retraining, no new
ingestion, no telemetry activation, no DNF target, no F0 execution.*
