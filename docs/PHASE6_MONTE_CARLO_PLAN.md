# Phase 6 — Monte Carlo Simulation Engine — R0 Architecture & Contract Plan

Status: **R0 audit/design only — NO simulator implemented, nothing committed.**
Authoritative frozen stack: Phase 1 (data platform) · Phase 2 (temporal
features, `d2ee966c…`) · Phase 3 (winner model, `3164de9e…` / artifact
`1116b34f…`) · Phase 4 (`RaceState`, prediction service) · Phase 5
(historical replay, `v2-historical-replay-phase5`, commit `ddee8710`).

This document is the R0 deliverable. It records what frozen evidence
exists, classifies every simulation input, chooses an architecture, and
stages implementation R1–R8. It does not implement R1.

Repository reality — the actual code and canonical parquet — is
authoritative over reports; every claim below is grounded in an inspected
source (file/line or measured parquet fact).

---

## 1. Frozen input audit

Read and cross-checked against repository reality:

| Frozen surface | Artifact / module | R0 finding |
|---|---|---|
| Phase-1 canonical data | `data/v2/processed/*` | Present; D9 state 2018–2025, labels/results split, side entities (weather, race_control, pit_stops, stints, races). |
| Phase-2 features | `v2/features/*`, ALL_84 / v8 | Frozen; 84 predictive names resolve; pace/stint/gap/track/weather families present. |
| Phase-3 model | `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib` | Frozen `INDEPENDENT_BINARY` winner model; not required for simulation validity. |
| Phase-4 RaceState | `v2/race_state.py`, `v2/race_state_reconstruction.py` | Frozen contract v1; exact-anchor, complete-roster, stdlib-only. |
| Phase-4 prediction | `v2/prediction.py` | Frozen; `ProbabilitySemantics == INDEPENDENT_BINARY`; no normalize path. |
| Phase-4 API service | `api/v2_service.py` | `SERVED_SEASONS = range(2018, 2025)`; loads corpus once; read-only. |
| Phase-5 replay | `v2/replay.py`, `v2/replay_reconstruction.py`, `v2/replay_predictions.py`, `v2/replay_probability_timeline.py` | Frozen; `ReplayFrameId` universal handle; cache read-only; no normalization. |
| Phase-5 tests | `tests/test_v2_phase5_r1..r7`, `test_v2_phase5_freeze.py` | Frozen gate; 348 passed / 5 skipped; 28 freeze assertions. |

No Phase-6 code exists: `grep "simulation|monte"` across `v2/ api/ tests/
scripts/` matches only two comments (`v2/d10.py:835`,
`v2/model_lab/protocol.py:267,554`) and no implementation. No simulator
may import the frozen winner model as a validity dependency
(`docs/PHASE6_MONTE_CARLO_HANDOFF.md` §32).

**Critical semantic distinction, restated and upheld.** Phase-3/4
`winner_probability` is `P(is_winner=1 | state)` from an independent
binary model; it is not a field distribution (`v2/prediction.py:28,36`;
Phase-4 report §11). Phase-6 probabilities will be **mutually exclusive
simulation frequencies**: for each completed trial exactly one driver
finishes P1, so simulated win frequencies over valid trials sum to 1;
positions are unique per trial. No softmax/normalize/field-sum of the
Phase-4 vector is permitted anywhere in Phase 6.

---

## 2. RaceState field inventory

Contract: `v2/race_state.py` (frozen, stdlib-only). Provenance vocabulary
is `FACTUAL_OBSERVED` / `DERIVED_PAST_ONLY` (`race_state.py:44-48`).

### 2.1 `AnchorObservation` (`race_state.py:202`)
| Field | Class | Simulation role |
|---|---|---|
| `race_id` | IDENTITY | Race identity. |
| `anchor_driver_id` | IDENTITY | Provenance of the snapshot (not a simulation field). |
| `anchor_lap_number` | IDENTITY | Per-driver progress of the anchor (not a global lap). |
| `anchor_state_time_s` | IDENTITY | Absolute session time of the anchor lap end. |

### 2.2 `DriverRaceState` (`race_state.py:265`)
| Field | Class | Simulation role at T |
|---|---|---|
| `driver_id` | IDENTITY | Participant key. |
| `observable` | PROVENANCE | Whether any state `<= T` exists; drives inclusion. |
| `observed_lap_number` | FACTUAL_AT_T | Completed laps (own progress). |
| `observed_time_s` | FACTUAL_AT_T | Absolute session time at own last lap end — the race-time coordinate. |
| `observation_age_s` | DERIVED_PAST_ONLY | Staleness; needed for the active/retired decision. |
| `position` | FACTUAL_AT_T | Current classified order. |
| `gap_to_leader_s` / `gap_to_leader_valid` / `gap_to_leader_laps` | FACTUAL/DERIVED | F6 same-lap crossing interval (seconds valid only under green, comparable laps, no suspension; else None + flag). |
| `gap_to_ahead_s` / `gap_to_ahead_valid` / `gap_to_ahead_laps` | FACTUAL/DERIVED | Same rule vs predecessor. |
| `compound` | FACTUAL_AT_T | Current tyre compound (verbatim token; 2018 names included). |
| `tyre_life` | FACTUAL_AT_T | Current tyre age (laps). |
| `fresh_tyre` | FACTUAL_AT_T | New-vs-scrubbed marker. |
| `stint_number` | FACTUAL_AT_T | Stint index. |
| `stint_lap` | DERIVED_PAST_ONLY | Laps completed on current stint (start-side only). |
| `pit_stops_completed_so_far` | DERIVED_PAST_ONLY | Stops taken. |
| `laps_since_last_pit_stop` | DERIVED_PAST_ONLY | Fuel/tyre phase proxy. |
| `constructor_id` | IDENTITY | Team identity. |
| `driver_number` | IDENTITY | Display attribute. |

### 2.3 `RaceContext` (`race_state.py:464`)
`race_leader_laps_at_state` (FACTUAL_AT_T / derived leader progress),
`race_progress_frac` (DERIVED_PAST_ONLY, leader laps / scheduled),
`scheduled_laps` (PRE_RACE factual), `season`, `round_no`, `circuit_id`
(IDENTITY).

### 2.4 `WeatherState` (`race_state.py:508`)
`air_temp_c`, `track_temp_c`, `humidity_pct`, `pressure_hpa`,
`wind_speed`, `wind_direction_deg`, `rainfall` — all FACTUAL_AT_T (strict
backward as-of); `observed_at_s`, `observation_age_s` — PROVENANCE. Null
means no prior observation, never "clear".

### 2.5 `RaceControlState` (`race_state.py:568`)
`track_state` (verbatim token; `all_clear|yellow|safety_car|red_flag|vsc|vsc_ending`
per `v2/d9schema.py:106-114`), `flag_yellow`, `flag_safety_car`,
`flag_red`, `flag_vsc` — FACTUAL_AT_T; `last_message_category`,
`last_message_flag`, `last_message_age_s` — PROVENANCE (message text is
deliberately excluded from the domain).

**Fields explicitly absent from RaceState (but simulation-relevant).**
`lap_time_s` and sector times (present in D9/D6, not projected into the
domain), pit transit/service duration, compound history / stint start
lap, fuel/energy state, car damage, penalties, weather forecast, track
evolution, and any retirement label. Also absent: `shortened_race` and
`source_unit_status` (D9 has them, but they are full-race facts — see
§26 leakage).

---

## 3. Historical-data audit

Canonical entities inspected directly (`data/v2/processed/*`):

| Entity | Grain | Columns that matter to simulation | Coverage (2018–2024) |
|---|---|---|---|
| `driver_lap_state_d9` | race×driver×lap | `lap_time_s`, sector 1–3, speed traps, `compound`, `tyre_life`, `stint_number`, `fresh_tyre`, `pit_in_s`, `pit_out_s`, `track_status`, `state_time_s`, `position`, `race_leader_laps_at_state`, `race_progress_frac`, `pit_stops_completed_so_far`, `laps_since_last_pit_stop`, `stint_lap`, `wx_*`, `rc_*`, `deleted`, `is_accurate` | 162,728 served driver-laps; 149 races; lap-time null 0.85–2.41%/season; `stint_number` null ≤1.67%; `position` null ≤0.24%. |
| `driver_laps` (D6) | race×driver×lap | `session_time_end_s` (== D9 `state_time_s`, verified equal 1056/1056 on 2023-r01), sector splits | same rows |
| `pit_stops` | race×driver×stop | `stop_sequence`, `lap_number`, `pit_in_s`, `pit_out_s`, `duration_s` | 5,452 stops; 5,111 durations; stationary median 23.93 s, p90 37.28 s (heavy tail — drive-through/red-flag outliers); transit median 23.57 s, p10 20.18, p90 30.41 (n=5,565). |
| `stints` | race×driver×stint | `compound`, `fresh_tyre`, `start_lap`, `end_lap`, `tyre_age_at_start`, `pit_in_lap`, `pit_out_lap` | 8,030 stints; median length 19 laps (p10 3, p90 37); compounds MEDIUM/HARD/SOFT + INTERMEDIATE/WET + 2018 SUPERSOFT/ULTRASOFT/HYPERSOFT; `tyre_age_at_start` null 0.47%. |
| `weather` | race×timestamp | all weather scalars + `observed_at_s` | 173 files / 25,779 rows; 44 files contain rainfall. |
| `race_control` | race×message | `message_seq`, `observed_at_s`, `lap_number`, `category`, `flag`, `status`, `message_text` | 173 files; SC/VSC appear under category `SafetyCar`; sector-local yellow under `Flag`. |
| `results` | race×driver | `status_text`, `dnf_flag`, `classified_position`, `points`, `laps_completed`, `grid_position` | 3,458 rows whole scope; used as roster by `V2Service`. |
| `race_driver_labels` | race×driver | `classified_flag`, `status_text`, `points`, `laps_completed`, `position_final` | 2,973 served driver-races; 390 unclassified = 13.1%. |
| `races` | race | `total_laps_scheduled`, `event_format`, `f1_api_support` | 149/149 served races have `total_laps_scheduled`; range 39–87, median 58. |

**Derived temporal facts measured from D9 `track_state` over the 173 race
entities (149 served + 24 in 2025):** at least one safety_car token in 98
races, vsc/vsc_ending in 74, red_flag in 17.

**Retirement evidence (Phase-1, 2018–2024):** 390 DNFs over 162,728
driver-laps ⇒ aggregate per-lap hazard ≈ **0.24%**; DNF exits are spread
across race progress (measured by race-progress-at-exit band: 103 in
0–10%, 55 in 10–25%, 72 in 25–50%, 141 in 50–90%, 19 in 90–100%), with a
clear lap-1 incident concentration. This is enough for a coarse
progress-conditioned hazard, not for driver/team conditioning.

**Limitations.** `state_time_s` is an absolute *session* clock, so lap
time and crossing times are exact but gaps between different laps are not
seconds (F6 `LAPS_APART`). Pit `duration_s` mixes service with penalties
and red-flag time; the robust usable statistic is `pit_out_s - pit_in_s`.
`track_status` is a per-lap code string reduced to a lap-boundary token,
so sub-lap SC/VSC transitions are not observable. `stints.end_lap` is
future inside a live stint and must never be read from a T snapshot.
Fastest-lap bonus, half-points (e.g. 2021 Spa: 12.5/9.0/…) and sprint
scoring are visible as unusual `points` values and require regulation
handling.

**Available in canonical data vs raw FastF1 vs not ingested.**
Canonical: lap/sector times, speed traps, stints, compounds, tyre age,
pit stops (in/out/duration), positions, `state_time_s`, leader progress,
weather samples, race-control messages, results/status. Raw FastF1 only
(not ingested): telemetry (ADR-0001 deferred), per-driver pit-lane
tracing, fuel load, damage, detailed penalty records, sub-lap flag
geometry. Not ingested anywhere: forecast weather, tyre thermal state.

---

## 4. Simulation input gap analysis

| Required quantity | Status | Basis |
|---|---|---|
| Future pace level (base) | CAN_ESTIMATE_FROM_CURRENT_RACE_PAST | Recent clean-green lap times visible in D9 `<= T` (Phase-2 F5 audit: 84.4% eligible). |
| Pace variance | CAN_DERIVE_FROM_PHASE1_HISTORY | Residual spread of eligible lap times. |
| Compound offset | CAN_DERIVE_FROM_PHASE1_HISTORY | Lap times grouped by compound (confounded — §7). |
| Tyre degradation vs age | CAN_DERIVE_FROM_PHASE1_HISTORY (confounded) | Stint lap-time profiles; needs fuel/track-evolution control. |
| Fuel/race-progress trend | CAN_DERIVE_FROM_PHASE1_HISTORY (confounded) | Lap-time trend over race progress; Phase-2 names it a PROXY. |
| Pit decision probability | REQUIRES_NEW_EMPIRICAL_MODEL | Stint-length distributions exist; a causal hazard does not. |
| Pit timing (lap) | CAN_ESTIMATE_FROM_CURRENT_RACE_PAST + REQUIRES_NEW_EMPIRICAL_MODEL | Realized `pit_in_lap` history; future must be drawn. |
| Compound selection at pit | CAN_DERIVE_FROM_PHASE1_HISTORY | Compound-transition frequencies. |
| Pit duration / transit | CAN_DERIVE_FROM_PHASE1_HISTORY | `pit_out_s - pit_in_s` distribution; service outliers need filtering. |
| Pit loss (time) | CAN_DERIVE_FROM_PHASE1_HISTORY (with assumption) | Transit + in/out-lap pace penalty; exact loss needs a model. |
| Traffic / dirty air | REQUIRES_NEW_EMPIRICAL_MODEL | Gap-to-ahead exists; a following penalty does not. |
| Overtaking | REQUIRES_NEW_EMPIRICAL_MODEL (confounded) | Position changes are not overtakes (§9). Deferred/abstracted. |
| Reliability hazard | CAN_DERIVE_FROM_PHASE1_HISTORY | 390 DNFs / 162,728 laps; progress-conditioned. |
| SC/VSC future probability | CAN_DERIVE_FROM_PHASE1_HISTORY (v2 only) | 98 SC / 74 VSC of 173 race entities; generation deferred in v1. |
| Red flag | DEFERRED | Rare, high-impact, position-freezing semantics. |
| Weather evolution | DEFERRED (hold or oracle) | Samples exist but a forecast model does not (§12). |
| Lapped cars / unlapping | CAN_DERIVE (semantics) + SC unlapping DEFERRED | Observable lap deficits. |
| Retirement ground truth | CAN_DERIVE_FROM_PHASE1_HISTORY | results `classified_position` null + last observed lap. |
| Race finish condition | CAN_ESTIMATE | `scheduled_laps` present 149/149; shortening is future-only (§26). |
| Track evolution | NOT_NEEDED_FOR_V1 | Absorbed into fitted constants. |
| Telemetry-level physics | NOT_NEEDED_FOR_V1 | Out of scope. |

---

## 5. Proposed `SimulationState` contract

Design only. `SimulationState` is a value type (immutable) carrying the
minimum needed to evolve one future trajectory. Every field states WHY,
SOURCE, and whether FACTUAL_AT_T or MODELED relative to the anchor.

### 5.1 Root
| Field | Why | Source | Kind |
|---|---|---|---|
| `race_id` | identity/aggregation | RaceState | FACTUAL |
| `simulation_time_s` / `leader_laps_done` | progress cursor | RaceState `state_time_s` + leader lap | FACTUAL→MUTABLE |
| `scheduled_laps` | finish condition | `RaceContext.scheduled_laps` | FACTUAL (PRE_RACE) |
| `circuit_id`, `season`, `round_no` | parameter lookup keys | `RaceContext` | FACTUAL |
| `track_state` | SC/VSC/red handling | `RaceControlState.track_state` | FACTUAL→MUTABLE |
| `weather` | v1 frozen weather | `WeatherState` | FACTUAL (held) |
| `assumption_set_id`, `param_version`, `seed` | provenance/reproducibility | config | MODELED |
| `drivers` | roster | RaceState | mixed |

### 5.2 Per driver (`DriverSimState`)
| Field | Why | Source | Kind |
|---|---|---|---|
| `driver_id`, `constructor_id` | identity / team pace | RaceState | FACTUAL |
| `active` | participant in trials | derived at T (§11) | MODELED (explicit rule) |
| `retired_in_sim`, `retirement_lap` | reliability outcome | engine | MODELED (draw) |
| `lap_number` (completed) | progress | RaceState `observed_lap_number` | FACTUAL→MUTABLE |
| `race_time_s` (last lap end) | cumulative race-time coordinate | RaceState `observed_time_s` | FACTUAL→MUTABLE |
| `position` | classified order | RaceState `position` | FACTUAL→MUTABLE |
| `gap_to_leader_s` | display/traffic | RaceState | FACTUAL |
| `compound` | pace/degradation key | RaceState | FACTUAL→MUTABLE |
| `tyre_life` | degradation input | RaceState | FACTUAL→MUTABLE |
| `stint_number` | stop bookkeeping | RaceState | FACTUAL→MUTABLE |
| `pit_stops` | strategy state | RaceState count | FACTUAL→MUTABLE |
| `pit_plan` | plausible future stops | model/user | MODELED |
| `pace_base_s` | expected clean pace at T | visible D9 history | FACTUAL→(fitted) |
| `pace_latent_s` | evolving pace offset | engine | MODELED (draw) |
| `lapped_by` / `laps_down` | lapped semantics | race_time vs leader | FACTUAL→MUTABLE |
| `observation_age_s` | active decision | RaceState | FACTUAL |

Every modeled field is tagged with one of the provenance categories in
§22. `SimulationState` is cloneable so a later strategy layer can mutate
`pit_plan`/`compound`/assumptions and re-run (§23).

---

## 6. Evolution / time model decision

**Chosen: hybrid lap-step kernel with discrete events resolved at lap
boundaries (candidate D, implemented as A + events).** One step = one
leader lap; pit stops, overtakes, SC state changes and retirements are
evaluated at each lap boundary; within-lap time is the sum of the driver's
lap time for that step.

Rationale, from existing data: the canonical grain is one row per
driver×lap with an exact lap-end clock (`state_time_s`); lap times are the
native observable. Event-driven (B) and continuous-time (C) models would
require event models (overtake onset, pit-lane occupancy) that Phase-1
does not directly observe and that R0 cannot justify. Lap stepping maps
1:1 onto the data, makes lapped-car and pit-cycle semantics exact, and
vectorizes trivially over trials.

Tradeoffs documented: lap stepping under-resolves within-lap passes and
pit-window timing to the lap boundary (accepted, `ponytail:` note in
§27); it cannot represent a pass mid-lap; it is exact for the 2018–2024
lap-grain evidence. Performance: ≤ ~87 steps per trial (§18).

---

## 7. Race-progress representation

**Chosen: per-driver `(lap_number, race_time_s)` — completed-lap count
plus the absolute session clock at the last completed lap — with positions
derived by sorting.** This is exactly what Phase-1/2 already carry:
`DriverRaceState.observed_lap_number` and `observed_time_s`, and the
frozen F6 gap rule defines a valid seconds gap only for same-lap,
green, non-suspension pairs (`v2/features/gaps.py:154-188`). Between
different laps the frozen semantics are `LAPS_APART`, never seconds.

Consequences:
- Same-lap cars: `race_time_s` difference is the exact gap.
- Different-lap cars: order by laps completed first, then race time.
- A driver one lap down has `lap_number` one lower and is classified
  behind all lead-lap cars at finish.
- **Do not** use `position` as physical race state; it is a derived
  classification (and is ambiguous during pit cycles, measured 3.7%
  multi-holder in F6 `ahead_reference`).
- `state_time_s` is session-relative, so an arbitrary anchor T can be
  advanced by adding simulated lap times; no lap-length metrology needed.

Historical support: `state_time_s` == D6 `session_time_end_s` verified
equal on all 1,056 rows of 2023-r01. Distance/lap+timestamp is therefore
fully evidence-backed; continuous within-lap distance is not and is not
claimed.

---

## 8. Pace model architecture

**Decision: a new, small Phase-6 pace layer estimated offline from
Phase-1, not the frozen ALL_84 engine at run time.** The frozen bridge
costs ~12 s per full-field snapshot (Phase-4 §16); it cannot be called per
simulated lap and is not required for simulation validity. The adapter
computes cheap observable pace summaries from D9 rows `<= T` once per run;
the frozen model is used only for comparison/evaluation.

Per driver `i` at simulated lap `l`, expected lap time:

```
mu_i(l) = base_i(T)
        + fuel_slope * (lap_done(l) - leader_lap_at_T)          # progress delta
        + compound_offset[current_compound_i] - compound_offset[compound_at_T_i]
        + deg_slope[compound_i] * (tyre_age_i(l) - tyre_age_i(T))
        + traffic_penalty_i(l)
        + status_effect(track_state)
```

- `base_i(T)`: robust median of the driver's recent eligible clean-green
  laps visible at T (Phase-2 F5 eligibility policy: lap>1, no pit marker,
  `track_state == all_clear`), falling back to a circuit/era baseline when
  history is thin. Provenance: factual input + fitted prior.
- Degradation and compound terms are **deltas from T**, so `base_i(T)`
  (already measured on the driver's current worn tyre) is not
  double-counted. A pit resets `tyre_age` to the new compound's start age
  and changes the compound offset.
- Stochastic variance: per-lap noise drawn around `mu_i(l)` (§13, §17).

Separated explicitly: `mu_i(l)` is *expected* pace; per-lap standalone
noise is *variance*. Traffic is a mean shift caused by a car ahead; it is
not variance. Fuel trend is a per-lap mean trend, not noise.

Components estimated offline: `fuel_slope`, `compound_offset[·]`,
`deg_slope[·]`, `sigma`, `traffic_penalty`. No training happens in R0.

---

## 9. Tyre degradation decision

Historical data supports **empirical, confounded** degradation work.
Grouping: circuit × compound × regulation era (2018–2021/2022–2024 as
parameter versions) × tyre-age; team/driver only if a later stage shows
enough data. Evidence: 8,030 stints, median 19 laps; lap-time null
≤2.4%; Phase-2 measured that compound changes are categorical and that
`current_stint_pace_trend` is an explicit PROXY with documented
confounders.

Confounders to control or document: fuel burn (lap times improve with
race progress), track evolution (rubbering in), traffic, wet/dry
transitions, SC/VSC laps, pit in/out laps, damage, deleted/`is_accurate`
laps. v1 approach: restrict fitting to green, pit-free, lap>1, accurate
laps; fit a joint model of `(compound offset, tyre-age slope, race-
progress trend)` per circuit-era, or, if identification is unstable,
impose a documented fuel-slope assumption and fit only compound offsets
and degradation slopes. Every fitted coefficient is tagged
HISTORICALLY_ESTIMATED with the confounder list in the parameter
artifact. **Never claim tyre age alone gives causal degradation.**

---

## 10. Pit model decision

Separated concerns and v1 policy:
1. **Pit decision** — REQUIRES_NEW_EMPIRICAL_MODEL. v1 uses a
   historically-plausible *target stint length*: draw a target stint
   length per compound from the empirical stint-length distribution
   (median 19, p10 3, p90 37) conditioned on circuit-era and starting
   compound; pit when `tyre_age` reaches the target (or at race end).
   This is simple, reproducible, and openly non-optimal.
2. **Pit timing** — the stop occurs on the target lap; a user/scenario
   may override (`Assumptions.forced_pit_laps`).
3. **Compound selection** — draw from empirical compound-transition
   frequencies (e.g. SOFT→MEDIUM/HARD), with the 2018 compound-name set
   handled per era.
4. **Pit-lane time loss** — sample `pit_out_s - pit_in_s` from the
   circuit-conditioned empirical transit distribution (median 23.57 s,
   p10 20.18, p90 30.41) minus the racing-segment baseline, plus the
   observed in-lap/out-lap pace penalty. Service variation from
   `duration_s` after excluding the heavy tail (drive-through/red flag).
5. **Rejoin traffic** — falls out of the cumulative-time ordering (§7).

Strategy optimization is explicitly **not** a Phase-6 goal; v1 simulates
historically plausible pit behaviour. Strategy replaces only the
`pit_plan`/`Assumptions` layer (§23).

---

## 11. Traffic / overtaking decision

Position changes in raw data are **not** overtakes — they are confounded
by pit cycles, retirements, SC reorder and timing artifacts. R0 does not
call every change a pass.

**v1 abstraction (honest, implementable):** positions are the sorted
order of `(lap_number desc, race_time_s asc)`. A faster car closes on the
car ahead naturally. To avoid unrealistic instant passes, apply a
**following penalty / passing threshold**: a car may not be re-ordered
ahead of the car directly in front within the same lap unless its
cumulative-time advantage exceeds a documented threshold; otherwise its
lap time is the leader's effective lap time plus a small dirty-air
penalty. The threshold and penalty are HISTORICALLY_ESTIMATED where
identifiable and otherwise USER_ASSUMPTION, versioned in parameters.

A calibrated probabilistic overtake model (per circuit, pace delta,
tyre delta) is **DEFERRED**; identifying on-track passes requires the
confounder filtering above and is a later empirical sub-phase. This keeps
v1 defensible rather than inventing an overtake rate.

---

## 12. Reliability decision

Evidence supports a **coarse empirical hazard**: 390 DNFs / 162,728
driver-laps (0.24%/lap) with a non-constant progress profile (87% of DNFs
in the 0–25% band are lap-1 incidents; a second concentration at 50–90%)
and 13.1% of served driver-races unclassified. Retirement can be derived
from Phase-1 without a new label: per 2018–2024 race, an unclassified
`race_driver_labels` row plus the driver's last observed D9 lap gives an
exit lap.

**Chosen v1 level: (2) simple historical hazard by race progress**, with
driver/team/season conditioning **DEFERRED** (under-powered and easily
overfit). Implementation contract:
- hazard `h(progress_band)` estimated offline from 2018–2024; applied per
  active driver-step with an explicit RNG stream;
- a retired driver receives `classified=False`, no finishing position,
  and contributes only to `dnf_probability`;
- retirement is a **simulated** state, never inferred from Phase-5
  staleness (the handoff forbids that: "retirement is never inferred
  from staleness").

The engine supports reliability as an explicit switch; the baseline
milestone runs without it until R7 calibration passes, then enables it by
default and surfaces `dnf_probability`. This respects "do not fake
reliability" while using the real 0.24%/lap evidence.

---

## 13. SC / VSC / red-flag decision

Factual coverage: SC tokens in 98 races, VSC in 74, red in 17 (of 173 race
entities). The frozen RaceState exposes the current token verbatim; it
does **not** guarantee how long the current regime lasts.

**v1 policy:**
- At a green anchor: future track state is assumed **all_clear**
  (no stochastic incident generation). Generation is DEFERRED.
- At an SC/VSC anchor: apply the factual current state to a modeled
  remnant (drawn from the empirical SC/VSC duration distribution,
  derivable from Phase-1 `track_state` runs), then all_clear.
- At a red-flag anchor: simulation is **unsupported in v1** (positions
  freeze, restart order and free tyre changes are a separate model). The
  API returns an explicit `simulation_unsupported` reason rather than
  faking a restart.
- A later what-if phase may inject an external event schedule. The engine
  accepts `Assumptions(track_state_schedule=…)`, kept separate from
  factual state.

This prefers a scientifically honest limitation over fake incident
generation.

---

## 14. Weather decision

Historical weather exists (173 files, 25,779 samples, 44 with rain) but no
forecast model exists. **v1 policy: hold weather fixed at the current
factual as-of `WeatherState` for the remainder.** Rationale: a Monte Carlo
run at T presented as a prediction must not silently consume actual
future weather.

**Temporal rule (critical):** actual future weather may be used **only**
in an explicitly labelled `ORACLE_EVALUATION_ONLY` mode (e.g. to isolate
pace-model error from weather error). The normal API path never reads
weather rows with `observed_at_s > T`; a leakage test poisons future
weather rows and asserts byte-identical output. Stochastic weather
evolution and user-supplied weather scenarios are DEFERRED; the latter is
accepted only via `Assumptions`.

---

## 15. Lapped-car semantics

Required semantics, defined before implementation:
- **Leader**: maximum `lap_number`; ties broken by earliest `race_time_s`.
- **On lead lap**: `lap_number == leader_lap`.
- **Lapped**: `lap_number < leader_lap`; `laps_down = leader_lap - lap_number`.
- **Finishing one or more laps down**: classified after every lead-lap
  finisher, ordered by laps completed then `race_time_s`.
- **Being lapped**: a driver whose cumulative race time is more than one
  full lap behind is exposed to blue flags; v1 never forces a driver onto
  the leader's lap and never awards a lapped car a lead-lap position.
- **SC unlapping**: DEFERRED (only meaningful once SC events are
  simulated). v1 does not unlap cars during an SC remnant.
- Lapped drivers may finish laps down if the leader crosses the scheduled
  distance first; their classification preserves their own lap count.

The finish condition is leader-based: when the leader completes
`scheduled_laps`, the trial ends and every driver's progress at that
instant is classified. This avoids forcing all drivers onto the leader's
lap and matches Phase-5's "members keep their own observed laps, never
forced to the anchor lap" doctrine.

---

## 16. Finish / classification contract

For each trial, per driver: `classified: bool`, `finish_position: int | None`,
`laps_completed: int`, `race_time_s: float`, `retired: bool`.

Ordering key for classified drivers: `(laps_completed DESC,
race_time_s ASC, driver_id ASC)` — the `driver_id` tie-break makes ties
deterministic (continuous noise makes exact ties measure-zero in
practice). Retired drivers get `finish_position = None`.

Invariants (checked by `validation`, never hidden by pandas ranking):
1. exactly one driver finishes P1 among classified drivers;
2. `finish_position` values are unique and form `1..K` (K = classified
   count) with no gaps;
3. every input roster member appears exactly once;
4. a retired driver has no `finish_position`;
5. `laps_completed >= 0`; `race_time_s` finite and non-decreasing in the
   ordering key;
6. if reliability is disabled, K equals the active-driver count and no
   driver is retired;
7. winner's `laps_completed == scheduled_laps` (when a clean finish);
8. lapped-driver ordering is consistent with the ordering key.

The contract is explicit rather than relying on `pandas.rank`, so an
invalid state raises instead of producing a plausible-looking table.

---

## 17. Monte Carlo output contract

### 17.1 `SimulationRunResult` (one trial)
`simulation_id` (deterministic), `race_id`, `seed`, `param_version`,
`assumption_set_id`, `finishing_order` (tuple of driver_id),
`classified`/`retired` flags, `laps_completed`, `race_time_s`,
`winner_id`, `valid: bool` + `invalid_reason`.

### 17.2 `DriverSimulationSummary` (per driver)
`driver_id`, `win_probability`, `podium_probability`,
`points_probability`, `expected_finish` (over classified outcomes),
`expected_points`, `finish_position_distribution`
(`{position → frequency}` + a `DNF` bucket), `dnf_probability`
(null when reliability disabled).

### 17.3 `MonteCarloResult` (aggregate)
`race_id`, `anchor` identity, `simulation_count`,
`valid_simulation_count`, `invalid_simulation_count`, `seed`,
`param_version`, `assumption_set_id`, `model versions` (simulator,
pace/degradation/pit/reliability, contract), `runtime_s`, and one
`DriverSimulationSummary` per roster member in `driver_id` order.

Raw finishing orders: not returned by default for 10k/50k. The contract
allows a bounded `sample_orders` (e.g. ≤100) and always exposes the
per-position distributions and counts that the aggregates are derived
from. Returning 10,000 full trajectories is not justified for HTTP.

---

## 18. Probability invariants

For N valid trials (invalid trials are reported and excluded from
probabilities, never silently dropped):
1. `sum(win_probability) == valid_winner_trials / N`, and equals 1 within
   floating tolerance when every valid trial has exactly one winner.
2. `sum(podium_probability) == (podium places awarded) / N`; with a
   complete race and ≥3 classified, the numerator equals `3·N` up to
   trials where fewer than 3 classify (which v1 records explicitly).
3. Per driver, the `finish_position_distribution` over
   `{1..K, DNF}` sums to 1 across valid outcomes (DNF mass only when
   reliability is enabled).
4. `0 <= p <= 1` for every probability; `NaN` is never a probability.
5. `expected_finish_i = Σ_k p_i(k)·k` over classified positions only;
   the DNF convention is stated in the summary (`expected_finish` is
   over classified outcomes; `dnf_probability` is separate). A DNF never
   silently becomes position 0 or field size.
6. No driver occupies two positions in one trial; no position holds two
   drivers (per-trial invariants, §16).
7. Points: `points_probability = P(finishing position scores under the
   race's regulation map)`. `expected_points` uses a per-era scoring map
   audited from Phase-1 (standard 25-18-15-12-10-8-6-4-2-1; fastest-lap
   bonus 2019+; half-points; sprint excluded because sprint races are not
   served). **Do not hardcode modern points across eras:** the map is
   selected by `season` (and the fastest-lap regime), and `expected_points`
   is null when the map is unknown. Fastest-lap attribution is a modeled
   sub-problem and is DEFERRED from `expected_points` in v1; the
   regulation-difference is recorded, not silently summed.

---

## 19. RNG / reproducibility contract

- Explicit `master_seed: int` in `SimulationConfig`; no module-global
  `random`/`np.random` anywhere (pinned by source scan test).
- `numpy.random.SeedSequence(master_seed).spawn(n_sims)[i]` seeds one
  `numpy.random.Generator` per simulation → simulation and outcome are a
  pure function of `(seed, i, inputs, params, code_version)`.
- `simulation_id` is deterministic (e.g. `f"{race_id}:{seed}:{i}"`).
- Random draws are made in a fixed, documented order; the draw layout is
  part of the contract.
- **Parallelization (when added) must not alter results:** workers
  process fixed-size contiguous chunks whose streams derive from
  `SeedSequence(master_seed).spawn(n_chunks)`; changing the worker count
  does not change chunk boundaries or outputs. v1 is single-process (§20).
- Goal: same state + config + seed + versions → byte-equivalent aggregate
  result. Tests assert this on 1k and 10k, and assert that changing the
  seed changes results.

---

## 20. Performance / vectorization architecture

Inspect current dependencies (`requirements.txt`): NumPy 2.4.2, pandas
2.3.3, scikit-learn, scipy, no Numba, no torch. R0 adds no dependency.

**Chosen: single-process NumPy batch vectorization, shape
`(n_sims, n_drivers)`, Python loop over ≤ ~87 laps.** Per lap, all
simulations advance with array operations; pit/SC/traffic decisions are
vectorized boolean masks; retirements are per-(sim, driver) masks. This
is the least-complex architecture that plausibly meets the target.

Fallbacks, only if measurement demands them: `numba` (new dependency —
discouraged) or `multiprocessing` with the fixed-chunk RNG contract. Not
v1.

Benchmark protocol (executed in R7, not R0): fixed fixtures (one early-,
one mid-, one late-race state; one SC state; one red state), sizes 1k /
10k / 50k, within-run and multi-run timing, `sims/sec`, peak RSS via
resource sampling, recorded to a benchmark JSON. **Provisional engineering
target to validate (not invented as a guarantee): 10k trials in ≤ 60 s
single-process on the developer machine**, with 1k interactive and 50k
batch/offline. If measurement contradicts it, the target moves, not the
science.

---

## 21. Historical validation strategy

One historical race has one realized outcome; a high probability for the
actual winner is not validation. Evaluation is across many states/races:

- **Protocol**: sample anchor states across 2018–2024 (e.g. per-race
  checkpoints like Phase-5's), run N trials, compare the simulated
  distribution to the single realized finish.
- **Metrics**: win log loss and Brier, podium Brier, position-distribution
  scoring (ranked probability score), expected-finish MAE, and
  calibration/reliability curves, each with a uniform-over-field and a
  no-simulation baseline (order by current position).
- **Clustering**: repeated correlated states from one race are correlated;
  report race-macro aggregates (per-race mean metric) as Phase 2/3 did,
  and bootstrap at the race level.
- **Chronological discipline**: fit parameters on strictly earlier
  seasons than the evaluated states; report a chronological split (e.g.
  fit 2018–2022, evaluate 2023–2024). No future leakage.
- **2025**: never evaluated or served without a deliberate, documented
  policy decision; the protected holdout remains sealed.
- **Internal consistency**: with noise disabled, a simulation launched
  from the last factual frame must reproduce the factual finishing order
  (a strong smoke test, not a replacement for calibration).
- The frozen Phase-5 `INDEPENDENT_BINARY` probabilities are used only as a
  comparison signal (per-driver calibration), never normalized into a
  distribution.

---

## 22. Parameter-estimation boundary

Split: **offline empirical estimation → versioned artifacts → runtime.**
Parameters (fuel slope, compound offsets, degradation slopes, per-lap
sigma, pit transit/service distributions, stint-length targets,
compound-transition frequencies, SC/VSC remnants, retirement hazard,
passing threshold) are estimated by a dedicated offline script from
Phase-1 canonical data, written to a versioned manifest, and loaded
read-only at run time. Never estimated ad hoc inside an HTTP request.

Proposed location (repo convention: artifacts under `data/v2/…`,
serving-free): `data/v2/simulation/params/<param_version>/` with a
`manifest.json` (version, training seasons, source data identity,
estimator description, per-parameter provenance/confounders). Runtime
binds `param_version` into `SimulationIdentity`, and `MonteCarloResult`
echoes it. Estimation windows exclude the evaluated race/season
(no future leakage). Parameters are separate from runtime `RaceState`.

The frozen `PriorHistory` / Phase-2 machinery is *not* reused as the
runtime parameter source; Phase-6 parameters are their own artifact.

---

## 23. Provenance model

Exactly one tag per important input/parameter:
- `FACTUAL_AT_T` — copied from the anchor snapshot at or before T
  (position, compound, tyre age, gaps, leader lap, track state, weather,
  scheduled laps).
- `HISTORICALLY_ESTIMATED` — fitted offline from Phase-1 history
  (degradation, fuel slope, pit distributions, hazard, passing threshold).
- `STOCHASTIC_DRAW` — realized inside a trial from a modelled
  distribution (per-lap noise, pit timing/service, retirement, SC
  remnant).
- `USER_ASSUMPTION` — supplied via `Assumptions` and never confused with
  fact (forced pit, compound override, injected track-state schedule,
  weather scenario).
- `ORACLE_EVALUATION_ONLY` — actual future data used only in a labelled
  evaluation mode (future weather, future pit laps, realized result),
  never in the prediction path.

This taxonomy is what a later What-If UI reads to distinguish
"what actually was true" from "what we assumed" (§24).

---

## 24. Replay / API boundary

**Engine seam (no HTTP, no React):**
```
ReplayFrame -> to_anchor() -> RaceStateReconstructor.reconstruct()
  -> RaceState (+ per-race D9 slice for pace history)
  -> SimulationStateAdapter.build(state, race_states, params, config)
  -> MonteCarloEngine.run(sim_state, config, params, assumptions)
  -> MonteCarloResult
```
`MonteCarloEngine` imports no API, no model, no feature engine, and no
replay cache. It is runnable from plain Python tests/benchmarks. The
frozen winner model is optional and used only for comparison. The engine
does not depend on replay-cache prediction artifacts.

**Proposed API (design only):**
`POST /v2/simulations/race`
```
{ "race_id": "...", "frame_index": 123, "simulation_count": 1000,
  "seed": 12345, "assumptions": { } }
```
`frame_index` is preferred (Phase-5 universal handle); an explicit exact
4-part anchor is accepted as an alternative. Output: `MonteCarloResult`
aggregate, optional bounded `sample_orders`. Error mapping mirrors frozen
conventions (`404 unknown_race`/`unknown_frame`, `422` malformed,
`409/422 simulation_unsupported` for red-flag anchors,
`503` parameter artifact unavailable). Serving scope stays 2018–2024;
any 2025 id → 404.

**Sync vs async:** v1 is synchronous for small counts (a measured,
configurable `max_synchronous_simulations`, provisional ≤ 2,000 pending
the R7 benchmark). 10k/50k are documented as batch/offline or future
async; do **not** add Celery/Redis for cost alone before measurement.

The route reuses the already-loaded corpus/reconstructor by read-only
reference, exactly as `build_v2_replay_service` does
(`api/v2_replay_service.py:371-392`), avoiding a second corpus load.

---

## 25. Strategy / What-If reuse boundary

`SimulationState` is a cloneable value; `SimulationConfig` and
`Assumptions` are separate from factual state. A later strategy layer
runs the same engine with mutated assumptions, e.g.
`Assumptions(forced_pit_laps={driver: lap}, compound_override=..., track_state_schedule=...)`.
The base engine never hardcodes historical pit choices — historical
plausibility lives only in the default `pit_plan` estimator, which is
replaceable. This is exactly the "clone state, modify allowed
assumptions, run the same engine" interface required by R0-Y / R0-Z.
Strategy optimization and What-If remain unimplemented in Phase 6 R0 and
out of v1 scope.

---

## 26. Leakage threat model

| Threat | Boundary | Planned mitigation | Test |
|---|---|---|---|
| Actual future lap times | adapter reads D9 `<= T` | filter `state_time_s <= T` and `lap_number <= observed_lap` | poison future lap times → byte-identical SimulationState/result |
| Future positions | RaceState `<= T` only | rely on frozen exact-anchor reconstruction | future position mutation fixture |
| Future pit stops | D9 `pit_in_s/pit_out_s > T` | adapter reads visible stops only; future drawn from params | poison future pit rows |
| Future compounds / tyre ages | D9 rows `> T` | same `<= T` filter; never read `stints.end_lap` | poison future compound/stint |
| Future weather | `WeatherState` as-of + adapter | v1 holds weather; ORACLE mode gated | poison future `wx_*` |
| Future race-control events | `RaceControlState` as-of | v1 holds current state; no future messages read | poison future RC rows |
| Final result / status | results/labels not runtime inputs | adapter never joins results; only offline estimation uses them | import/scan test; no labels in runtime modules |
| Future retirements | reliability is simulated | never infer retirement from staleness; draws only | stale-driver fixture under red flag |
| Future winner / model labels | not inputs | engine independent of labels and of the winner model | source scan |
| Full-race aggregate stats | e.g. `shortened_race`, `observed_leader_laps`, aggregate `points` | never read at T; scheduled distance is PRE_RACE | source scan + poison aggregate columns |
| Parameters fit on the target's future | offline estimator windows | exclude evaluated race/season; chronological split | parameter manifest records window; split test |
| Parameters fit on later seasons | same | training seasons recorded and enforced | manifest assertion |

Reused frozen protections (RaceIndex `<= T`, exact anchor, label
name-guards, prior strictly-past) are not duplicated, only relied on.

---

## 27. Failure modes

Validation boundaries, each raising a typed error rather than emitting an
invalid result:
- NaN/Inf lap time, negative lap time, impossible gap → reject the step;
- duplicate position / duplicate driver / missing driver → reject trial;
- negative tyre age or pit loop (stop count beyond a bound) → reject;
- all drivers retired → invalid trial, counted and reported;
- infinite race (leader never reaches scheduled laps) → step cap → invalid;
- SC deadlock (never returns to green) → bounded remnant → invalid;
- lapped-driver ordering corruption → invariant check;
- invalid probability aggregation (sums outside tolerance, `p` outside
  `[0,1]`) → reject result;
- RNG nondeterminism → reproducibility test.

`valid=False` trials carry an `invalid_reason` and are excluded from
probabilities but always reported in counts. `ponytail:` the in-lap
approximation and lap-boundary event resolution are known ceilings;
upgrade paths are within-lap sub-stepping and an event queue if later
evidence justifies them.

---

## 28. Module architecture

Proposed `v2/simulation/` package (consistent with `v2/features/`,
`v2/labels/`), 8 modules, no circular imports:
- `state.py` — `SimulationState`, `DriverSimState`, `Environment`,
  provenance tags (stdlib-only).
- `config.py` — `SimulationConfig`, `Assumptions`, `SimulationIdentity`,
  versions, RNG seed contract.
- `params.py` — parameter-artifact schema + read-only loader.
- `pace.py` — pace/degradation model (`mu_i(l)`, variance); includes tyre
  logic.
- `pits.py` — pit decision/timing/compound/loss.
- `engine.py` — lap-step kernel, traffic/ordering, SC remnant, finish.
- `aggregation.py` — `SimulationRunResult`, `DriverSimulationSummary`,
  `MonteCarloResult`, probability invariants.
- `adapter.py` — `RaceState` (+ D9 slice) → `SimulationState`; leakage
  filters.

Dependency direction: `state/config/params` are leaves → `pace/pits` →
`engine` → `aggregation` → `adapter` (imports frozen `v2.race_state`).
API imports adapter/engine/aggregation only. The engine imports no
`api.*`, no `v2.model_lab`, no feature engine, no replay cache. A later
revision may merge `params` into `config` and `pits` into `engine`; R1
decides with the smallest working shape.

---

## 29. Phase-6 roadmap (R1–R8)

**R1 — Simulation contracts + deterministic RNG.** Scope: `state.py`,
`config.py` (incl. RNG), provenance tags, `SimulationIdentity`; no
evolution. Inputs: frozen RaceState inventory (§2). Outputs: typed
immutable contracts. Tests: field/invariant/seed-stream unit tests,
no-global-RNG source scan. Verification: FAST. STOP gate: any need to
change `RaceState`/`Phase-5` semantics ⇒ freeze conflict, halt.

**R2 — RaceState → SimulationState adapter.** Scope: `adapter.py`;
pace-history extraction from D9 `<= T`; active-set rule. Outputs:
factual `SimulationState`. Tests: exact-anchor mapping, stale/zero-state,
red-flag active rule, future-poisoning fixtures. Verification: MEDIUM
(needs `data/v2`). STOP gate: any future-row read ⇒ defect, halt.

**R3 — Empirical parameter layer.** Scope: offline estimator script +
versioned manifest; pace/degradation/pit/stint/hazard/passing-threshold
parameters; chronological windows. Outputs: `data/v2/simulation/params/
<v>/`. Tests: reproducibility, no-leakage windows, schema. Verification:
MEDIUM + measured. STOP gate: any parameter using the evaluated race's
future ⇒ halt.

**R4 — Deterministic evolution kernel.** Scope: `engine.py` with noise
disabled; lap stepping, cumulative-time ordering, finish/classification,
invariants (`aggregation.py` validation). Tests: one winner, unique
order, lapped field, late/partial race, last-frame reproduction.
Verification: MEDIUM. STOP gate: pandas ranking masking an invalid state
⇒ defect, halt.

**R5 — Stochastic Monte Carlo + aggregation.** Scope: RNG draws, 1k
trials, `MonteCarloResult`, probability invariants. Tests:
determinism/reproducibility, seed sensitivity, probability sums,
zero/one edge cases, small field. Verification: MEDIUM. STOP gate:
probability sum outside tolerance ⇒ defect, halt.

**R6 — Pits / traffic / lapped dynamics (+ optional reliability).**
Scope: `pits.py`, traffic/passing threshold, SC remnant, lapped semantics;
reliability switch with hazard. Tests: pit event, SC/VSC anchor, lapped
ordering, DNF accounting, RNG parallel-determinism contract. Verification:
MEDIUM. STOP gate: reliability calibration not shown ⇒ keep default off.

**R7 — Historical validation + performance hardening.** Scope: §21
protocol, 1k/10k/50k benchmark, leakage/adversarial matrix, calibration
report, provisional target assessment. Verification: FULL
(`pytest tests/` serialized per AGENTS.md), frontend untouched.
STOP gate: leakage found or target unmet ⇒ fix Phase-6 code only.

**R8 — API + frontend + freeze.** Scope: `/v2/simulations/race` router
(additive include only), schemas/service, optional replay-UI simulation
panel, freeze manifest, final report, commit/tag. Verification: FULL
review. STOP gate: any frozen Phase-1–5 hash drift ⇒ halt, diagnose.

---

## 30. V1 includes / defers

**PHASE-6 V1 INCLUDES**
- lap-step hybrid kernel from an arbitrary 2018–2024 replay frame/state;
- factual `RaceState` → `SimulationState` adapter with strict `<= T`;
- offline-estimated pace, compound offset, fuel trend, tyre degradation,
  per-lap variance;
- historically-plausible pit model (target stint length, compound
  transition, transit/service distributions) and pit-loss;
- cumulative-time ordering with a documented following/passing
  threshold; lapped-car classification;
- optional empirical progress-conditioned retirement hazard (default off
  until R7 calibration passes, then on);
- factual current SC/VSC remnant; all_clear assumed afterward;
- weather held at the current as-of state;
- deterministic RNG, simulation ids, versioned parameters;
- `MonteCarloResult` with win/podium/points probabilities, expected
  finish, position distributions, expected points, optional DNF;
- historical validation (chronological split, race-macro reporting) and
  1k/10k/50k benchmarks;
- synchronous API for small counts; batch/offline documented for large.

**PHASE-6 V1 DEFERS**
- stochastic SC/VSC/red event generation; red-flag-anchor simulation;
- evolving/stochastic weather; forecast consumption (except labelled
  ORACLE evaluation);
- strategy optimization and what-if mutation (interfaces preserved);
- calibrated probabilistic overtaking; SC unlapping;
- driver/team/season-conditioned reliability;
- fastest-lap attribution in `expected_points`; sprint scoring (sprints
  are not served);
- async job infrastructure (Celery/Redis) unless benchmarks prove it;
- frontend simulation UI if R8 budget is tight (backend contract first).

---

## 31. Open questions / blockers

1. **Active-set / retirement rule at T**: exact threshold on
   `observation_age_s`, and its interaction with red flag and long pit
   stops, must be specified in R1 before any race evolution. Blocker for
   R2/R4.
2. **Points regulation policy**: confirm handling of fastest-lap bonus
   and half-points in `expected_points`; verify the exact per-season map
   from Phase-1 (unusual values observed: 26, 12.5). Decision needed by
   R5.
3. **SC/VSC remnant model**: identify and validate the empirical
   duration distribution from `track_state` runs; decide whether v1
   supports SC anchors or returns `simulation_unsupported` like red.
4. **Degradation identification**: whether `(compound offset, deg slope,
   fuel trend)` is jointly identifiable per circuit-era, or whether a
   documented fuel-slope assumption is required. R3 decision.
5. **Passing threshold**: evidence base for the threshold/penalty (fit vs
   documented assumption). R6 decision.
6. **Reliability default**: enable in v1 only if R7 calibration is
   credible; otherwise ship with the switch off.
7. **Synchronous limit**: the measured basis for
   `max_synchronous_simulations` and the 10k latency target (R7).
8. **Validation anchor sampling**: which states per race (reuse Phase-5
   checkpoint policy?) and the statistical power at 149 races.

None of these blocks R1 contracts; they must be resolved at the stated
stage.

---

## Appendix A — R0 DoD checklist

Tracked in the R0 final response (`# PHASE 6 R0 REPORT`); every item
marked with the verification actually performed in R0.

## Appendix B — Verification notes

R0 performed: document reading, frozen-source inspection, canonical
parquet column/coverage inspection, feature-set resolution, and small
read-only factual computations (gap/time equality, pit transit, stint
length, SC/VSC/red race counts, DNF hazard, points values). No simulator,
no model training, no production backfill, no full-suite pytest, no
10k benchmark (no simulator exists).

---

# Phase 6 — R1 Implementation Record

Status: **R1 COMPLETE — contracts + deterministic RNG only; nothing
simulated, nothing committed.** This record is appended to the R0 plan; it
does not rewrite R0.

## R1-A Files changed

New, narrowly scoped (no frozen Phase-1–5 source touched):

| Path | Contents |
|---|---|
| `v2/simulation/__init__.py` | Public re-exports + one-line dependency-direction note. |
| `v2/simulation/errors.py` | `SimulationError`, `SimulationContractError`, `SimulationValidationError`, `SimulationRNGError`. |
| `v2/simulation/state.py` | Contract version authority, `Provenance`, `DriverStatus`, canonical JSON/SHA-256 helpers, `SimulationEnvironment`, `DriverSimState`, `SimulationState`. |
| `v2/simulation/config.py` | `SimulationConfig`, `Assumptions`, `ParameterIdentity`, `simulation_request_identity`. |
| `v2/simulation/rng.py` | `seed_sequence_for_simulation`, `rng_for_simulation`, versioned `PCG64`. |
| `v2/simulation/results.py` | `DriverFinish`, `FinishOrder`, `SimulationRunResult`, `PositionFrequency`, `DriverSimulationSummary`, `MonteCarloResult`, `MONTE_CARLO_FREQUENCY`. |
| `tests/test_v2_phase6_r1.py` | 157 focused R1 tests. |

No `params.py`, `pace.py`, `pits.py`, `engine.py`, `aggregation.py`, or
`adapter.py` were created.

## R1-B R0 contract refinements (audited, speculative fields removed)

R1 froze *contracts*, not unvalidated model assumptions. Refinements vs
the R0 §5/§17 sketches:

- **Removed from the R1 state contract** (owning stage in brackets):
  `pace_base_s`, `pace_latent_s` (R3/R4); `pit_plan`, `retired_in_sim`,
  `retirement_lap` (R6); `gap_to_leader_s`/`laps_down` as stored fields
  (derivable from `race_time_s`/`lap_number`); `gap_to_ahead_s` traffic
  state (R6); `assumption_set_id`/`param_version`/`seed` as state fields —
  they belong to the config/identity seam, not the factual starting state.
- **`active: bool` → `DriverStatus` enum** (`ACTIVE`/`RETIRED`), with
  `observation_age_s` kept separate so ACTIVE-but-stale is structurally
  possible and retirement is never inferred.
- **Environment uses one verbatim `track_state` token**, not duplicated
  `flag_*` booleans: the frozen `flag_*` fields are a deterministic view of
  the same channel, and two sources of truth invite drift.
- **`SimulationConfig` has no production maximum**: a runtime cap is
  benchmark-backed and belongs to a later stage.
- **`Assumptions` carries zero controls** in R1 (R0's forced pit laps,
  compound overrides, track-state schedules, weather scenarios all
  remain DEFERRED); it is a minimal versioned object whose provenance is
  pinned to `USER_ASSUMPTION`.
- **Points/fastest-lap/half-points are not represented**: R1 exposes
  `expected_points` only as a nullable field; the regulation map is R5.

## R1-C Module architecture

`errors` (leaf) ← `state` ← `config`, `results`, `rng`. No cycles. The
package imports only the stdlib, the frozen Phase-1 track-token vocabulary
(`v2.d9schema.TRACK_STATE_TOKENS`), and the frozen Phase-4 `WeatherState`
value object. It imports no `v2.prediction`, `v2.model_lab`,
`v2.replay*`, `v2.race_state_features`, sklearn/joblib, pandas, FastAPI, or
API layer (AST + subprocess-import tests).

## R1-D Contract version and provenance

- `SIMULATION_CONTRACT_VERSION = "v1"` is defined exactly once, in
  `state.py`; every other module imports it. It participates in state
  identity, request identity, and RNG domain separation.
- `Provenance` is a `str`-`Enum` with the exact R0 vocabulary
  (`FACTUAL_AT_T`, `HISTORICALLY_ESTIMATED`, `STOCHASTIC_DRAW`,
  `USER_ASSUMPTION`, `ORACLE_EVALUATION_ONLY`). `provenance_value()`
  accepts only the enum or its exact value and rejects free-form strings. It
  is attached where source materially matters (Assumptions are pinned
  `USER_ASSUMPTION`), not to every scalar.

## R1-E State contract

`SimulationState` (immutable): `simulation_contract_version`, `race_id`,
`season`, `round_no`, `circuit_id`, `anchor_frame_index` (optional Phase-5
handle), `scheduled_laps`, `leader_laps_done`, `simulation_time_s`,
`drivers`, `environment`. `DriverSimState` (immutable): `driver_id`,
`lap_number`, `race_time_s`, `position`, `compound`, `tyre_age`,
`stint_number`, `pit_count`, `constructor_id`, `status`,
`observation_age_s`. `SimulationEnvironment`: `track_state`,
`weather` (frozen `WeatherState`).

Invariants: non-empty roster, unique non-empty `driver_id`, canonical
`driver_id` ordering, per-driver `lap_number <= leader_laps_done`, lapped
drivers permitted, deterministic serialization. Numeric boundaries reject
NaN/±Infinity, negative race time/lap/tyre-age/pit-count/observation-age,
`position < 1`, `stint_number < 1`, `scheduled_laps < 1`,
`leader_laps_done > scheduled_laps`, and numpy/bool scalar leakage.

## R1-F Lapped and retirement representation

Lapped states are first-class: drivers may hold different completed-lap
counts and are never forced onto the leader's lap. Retirement is an
explicit `DriverStatus.RETIRED`; no hazard is implemented and retirement
is never inferred from staleness.

## R1-G RNG architecture

`SeedSequence([master_seed, simulation_id, version_domain_tag])` →
`PCG64` → `Generator`, one stream per simulation id. No `np.random` global
state, no `random` global state, no implicit/time-based seed, no UUID. The
domain tag is a deterministic 32-bit digest of the contract version, so the
stream is a documented function of `(seed, id, version)`. Parallel
invariance holds because the stream depends only on the simulation id, not
on spawn count, chunking, or worker count.

## R1-H Identity and serialization

`canonical_json` (sorted keys, compact separators, `allow_nan=False`) and
`canonical_sha256`. `SimulationState.identity()`, `SimulationConfig.identity()`,
`Assumptions.identity()`, `ParameterIdentity.identity()` compose into
`simulation_request_identity()`. No timestamp/hostname/PID/UUID/memory
address. Driver input order does not change identity. `MonteCarloResult`
excludes wall-clock `runtime_s` from `identity()`.

## R1-I Parameter identity seam

`ParameterIdentity` is all-or-none: `contract_only()` (the R1 default,
explicit "not supplied") or a full `(set_id, version, hash)`. No parameter
files were created, nothing estimated, no production version invented.

## R1-J Result contracts

`FinishOrder` enforces one entry per starting driver, unique ids, unique
contiguous classified positions `1..K`, explicit retired drivers without
positions, and lapped drivers. `SimulationRunResult` requires a complete
classification when valid and a non-empty reason when invalid.
`DriverSimulationSummary` bounds probabilities to `[0,1]`, rejects
non-finite expected values/duplicate distribution keys, and does not
enforce sum-to-one. `MonteCarloResult` enforces
`valid + invalid == requested`, unique/ordered summaries, roster-matched
`sample_orders`, and pins probability semantics.

## R1-K Probability semantic

`PROBABILITY_SEMANTICS = "MONTE_CARLO_FREQUENCY"` with an explicit note:
empirical frequencies over valid simulated outcomes, never a
renormalization of `INDEPENDENT_BINARY`. No aggregation implemented.

## R1-L Tests and verification

- `tests/test_v2_phase6_r1.py`: **157 passed** in ~0.2 s. Covers version,
  provenance, state construction/ordering/validation, lapped and retired
  states, environment, config, assumptions, parameter seam, RNG determinism
  (100× repeat, id/seed sensitivity, request-order and chunk invariance),
  global-RNG firewall (runtime + AST), state/request identity sensitivity,
  canonical serialization, result contracts, probability bounds,
  classification invariants, sample orders, scientific separation, and the
  generic-season/2025 boundary.
- FAST frozen regression: `test_v2_phase5_freeze.py` **28 passed**;
  `test_v2_phase4_r1.py` + `test_v2_phase5_r1.py` **111 passed**.
  `test_v2_phase4_freeze.py` has one pre-existing, Phase-5-authorized
  failure (`api/main.py` drift to SHA `2840271a…`, which is exactly the
  `phase4_frozen → phase5_final` drift recorded in
  `docs/PHASE5_FREEZE_MANIFEST.json`); R1 did not touch `api/main.py`.
- Deferred/unaffected: full-suite pytest not run; frontend untouched
  (`DEFERRED — UNAFFECTED`); no training, inference, replay-cache
  generation, or parameter estimation.

## R1-M Known deferrals and R2 readiness

Deferred to their owning stages: pace/degradation (R3), pit/traffic/
reliability/lapped dynamics and retirement hazard (R6), engine/aggregation
(R4/R5), API/frontend (R8). The active-set / retirement rule at T (R0 §31
open question 1) is intentionally NOT resolved in R1: R1 provides only the
structural `DriverStatus` seam; R2 must specify the `observation_age_s`
threshold rule when it builds the adapter.

R2 can proceed: `SimulationState`, `DriverSimState`, and
`SimulationEnvironment` are the adapter's target types, and the factual
Phase-5 replay frame identity has an explicit `anchor_frame_index` seam.

---

# Phase 6 — R2 Implementation Record

Status: **R2 COMPLETE — factual adapter only; nothing simulated, nothing
staged, nothing committed, no tag.** Appended to the R0 plan and the R1
record; neither is rewritten.

R2 owns the one-way factual adapter
`RaceState -> from_race_state() -> SimulationState`. There is NO pace,
degradation, pit, overtaking, traffic, reliability, or stochastic-draw
code here, and no Monte Carlo, parameter estimation, API, or frontend.

## R2-A Files changed

New:
- `v2/simulation/adapter.py` — the adapter (pure `from_race_state`
  function + stable `SimulationUnavailableError` reason taxonomy).
- `tests/test_v2_phase6_r2.py` — 94 focused R2 tests.

Modified:
- `v2/simulation/state.py` — **narrow R2-Z refinement only**: `tyre_age`
  is now nullable (`int | None = None`, validated by `_opt_int(..., >= 0)`)
  so an unrecorded factual tyre age is preserved as null (evidence below).
- `tests/test_v2_phase6_r1.py` — one added R1 regression asserting null
  `tyre_age` is preserved and zero remains distinct; no other R1 test
  changed.
- `docs/PHASE6_MONTE_CARLO_PLAN.md` — this record.

No frozen Phase-1–5 source was touched. Nothing was staged or committed.

## R2-B Exact mapping (every field)

Root `SimulationState`:

| Target field | RaceState source | Null | Notes |
|---|---|---|---|
| `race_id` | `RaceState.race_id` | required | identity |
| `season` / `round_no` / `circuit_id` | `RaceContext.*` | preserved | verbatim |
| `scheduled_laps` | `RaceContext.scheduled_laps` | **required** | null => unavailable |
| `leader_laps_done` | `RaceContext.race_leader_laps_at_state` | **required** | null => unavailable |
| `simulation_time_s` | `RaceState.state_time_s` | required | exact T, no rounding |
| `anchor_frame_index` | caller-supplied Phase-5 handle | optional | adapter never imports replay |
| `environment.track_state` | `RaceControlState.track_state` | preserved | verbatim token |
| `environment.weather` | frozen `WeatherState` | preserved | same value object |

Per observed `DriverSimState`:

| Target field | `DriverRaceState` source | Null | Notes |
|---|---|---|---|
| `driver_id` | `driver_id` | required | canonical ordering |
| `lap_number` | `observed_lap_number` | required | driver's OWN progress |
| `race_time_s` | `observed_time_s` | required | driver's OWN clock `<= T` |
| `position` | `position` | preserved | not required unique |
| `compound` | `compound` | preserved | verbatim, era names kept |
| `tyre_age` | `tyre_life` | preserved | nullable after refinement |
| `stint_number` | `stint_number` | preserved | nullable |
| `pit_count` | `pit_stops_completed_so_far` | **required** | null => unavailable |
| `constructor_id` | `constructor_id` | preserved | identity |
| `status` | (none) | n/a | ALWAYS `ACTIVE` |
| `observation_age_s` | `observation_age_s` | preserved | factual staleness |

Information loss (accepted, documented): `gap_to_*`, `fresh_tyre`,
`stint_lap`, `laps_since_last_pit_stop`, `driver_number`, and the redundant
`flag_*` booleans are not represented. The R1 contract deliberately dropped
gaps and the duplicated flag view; the others are derivable or display-only
and belong to later stages, not to the starting coordinate.

## R2-C Active-set decision

The adapter preserves the COMPLETE factual roster whenever it adapts: every
observable member is emitted, including stale, gap-invalid, lapped, and
not-yet-finished drivers. It never drops a member silently. There is no
adapter-level active/inactive split and no observation-age threshold:
staleness is metadata, not existence. This resolves R0 §31 open question 1
at the adapter seam — the adapter keeps structurally ACTIVE; the retirement
hazard threshold (if any) belongs to R6.

## R2-D Pre-first observation decision (evidence-backed)

**Decision: refuse, losslessly.** If any roster member has no observation
at or before T (`RaceState.unobservable_driver_ids` non-empty), the adapter
raises `SimulationUnavailableError(reason="unobserved_roster_member")`
listing the members. It does NOT include them with fabricated lap/time and
does NOT drop them.

Evidence: the frozen `RaceState` cannot distinguish a pre-first driver from
a permanent zero-state entrant in a single snapshot (its own contract says
so). Measured: the first `2023-r01-R` frame has 19 of 20 members
unobserved; 5 of 149 served races contain a results-roster member that never
appears in D9 at all. Only "complete roster observed" is honest under the
R1 contract, which requires a real `lap_number` and `race_time_s` per
driver and has no not-yet-observed status. A history-based
non-participant policy is deferred to a later stage; until then those early
frames/races are explicitly unsupported (map to `simulation_unsupported` at
the API), never silently mis-started.

## R2-E Stale / retirement policy

Stale never implies retired. Every observed driver is emitted
`DriverStatus.ACTIVE` regardless of observation age, missing compound,
missing tyre age, missing position, or gap invalidity. No retirement is
derived from any of those. Pinned by
`test_stale_not_marked_retired`,
`test_retirement_not_derived_from_large_observation_age`,
`test_retirement_not_derived_from_missing_tyre_and_compound`, and the
all-ACTIVE assertions over four real fixtures. Future simulated retirement
is R6.

## R2-F Simulation time / leader progress

`simulation_time_s` equals `RaceState.state_time_s` exactly (no rounding, no
nearest frame, no lap-end approximation). `leader_laps_done` comes from
`RaceContext.race_leader_laps_at_state`, never from the anchor driver's
lap. Pinned with a synthetic lapped-anchor case (anchor lap 8, leader 10)
and the shared-T fixture.

## R2-G Driver progress / lapped semantics

Each driver keeps its own `observed_lap_number` and `observed_time_s`; no
driver is forced onto the leader lap. The 2023-r01-R final frame carries a
spread of completed laps and all are preserved. The R1 invariant
`lap_number <= leader_laps_done` is checked by the adapter; a factual
violation raises `SimulationUnavailableError`.

## R2-H Tyre / stint / pit mapping

Only factual `<= T` fields are copied: `tyre_life`, `compound`,
`stint_number`, `pit_stops_completed_so_far`. There is no look-forward to
the next stint, no inferred next compound, no inferred future pit, and no
backfill from later rows. Nulls are preserved (see R2-J).

## R2-I Environment mapping

`track_state` is the frozen token verbatim; `weather` is the frozen
`WeatherState` value object (strict backward as-of). No future weather, no
forecast, no future race-control schedule is read. The adapter imports no
weather/race-control data source, only `RaceState`.

## R2-J Null policy

Nulls stay null; none is flattened. `None` never becomes `0`, `""`, a fake
position, `T`, or the leader lap. For the three R1 root fields that cannot
hold null (`scheduled_laps`, `leader_laps_done`, `pit_count`), a factual
null raises a deterministic `SimulationUnavailableError` with a stable
reason instead of a fabricated value. `tyre_age` was the one factual null
that the R1 contract could not represent (evidence: the `2022-r07-R`
`norris-30` state has 11 drivers whose latest `<= T` row has null
`tyre_life`; season null rate 0.14–2.2%), so it received the narrow
refinement below.

## R2-K Provenance

Everything the adapter supplies is `FACTUAL_AT_T` (or the past-only
observation-age derivation). The adapter exports
`ADAPTER_PROVENANCE = Provenance.FACTUAL_AT_T`, `ADAPTER_SOURCE`, and
`ADAPTER_VERSION`; it does not explode the schema with redundant per-scalar
tags. It never labels anything `HISTORICALLY_ESTIMATED`,
`STOCHASTIC_DRAW`, `USER_ASSUMPTION`, or `ORACLE_EVALUATION_ONLY`, and it
performs no modelling.

## R2-L Deterministic identity

Same RaceState (+ same optional frame handle) -> byte-identical
`SimulationState.to_dict()`/`canonical_json` -> identical `identity()`.
Identity changes when a represented fact changes (position, compound,
tyre age, lap, race time, weather, track state, scheduled distance, or the
frame handle). Driver input order does not matter (R1 canonicalizes).
No wall time, PID, hostname, UUID, seed, or simulation count is included.

## R2-M Replay seam

Verified externally composed:
`ReplayFrame -> ReplayReconstructor.state_at() -> RaceState ->
from_race_state() -> SimulationState`. The adapter has NO `v2.replay*`
import (AST + runtime firewall tests); the caller passes
`anchor_frame_index` if it wants the handle recorded. No reverse
dependency exists.

## R2-N Adversarial result

For the 2023-r01-R `alonso-28` state (plus a 3-fixture matrix), every
strictly-future D9 row was poisoned with extreme position, lap, compound,
tyre-age, stint, pit, weather, track/race-control, leader-progress, and
label/status/result values, then `RaceState` was rebuilt with the frozen
machinery and adapted again. Canonical serialization and identity were
byte-identical before/after. **No leakage was detected under the implemented
adversarial test suite.** (Not a proof of leak-freedom.)

## R2-O Adapter performance

Benchmark (n=200, 20-driver full field, 2023-r01-R @ alonso-28, conversion
only — reconstruction excluded): **mean 0.048 ms, p50 0.046 ms,
p95 0.053 ms**. No gate invented; recorded as an indicative number.

## R2-P Tests and verification

- `tests/test_v2_phase6_r1.py` + `tests/test_v2_phase6_r2.py`:
  **252 passed** (R1 158 incl. the null-tyre-age regression; R2 94) in
  ~4 s.
- FAST/MEDIUM frozen regression: `test_v2_phase4_r2.py` +
  `test_v2_phase5_r2.py` + `test_v2_phase5_freeze.py`: **91 passed**.
- R2 covers: field mapping, identity, driver ordering, leader progress,
  stale drivers, pre-first refusal, retirement firewall, lapped drivers,
  race-time coordinate, tyres/stints/pits, observation-age invariant,
  weather, track state, null policy, replay seam, shared-T regression,
  partial/red/early/lapped fixtures, future-data poisoning, label/model
  firewall, 2025 boundary, deterministic errors, and performance.
- Not run: full-suite pytest, frontend, training, inference, replay-cache
  generation, parameter estimation. Frontend `DEFERRED — UNAFFECTED`.

## R2-Q R1 contract refinement (R2-Z)

One narrow refinement, forced by real evidence and recorded above:
`DriverSimState.tyre_age` became nullable (`int | None`) to preserve a
factual null that the frozen `RaceState` legitimately carries. Counterexample
and null rates are in R2-J. No other R1 field changed; the refinement does
not undermine any Phase-1–5 semantic (null stays distinct from zero), so
this is not a scientific freeze conflict.

## R2-R Graphify

`graphify update .` exit **0**: **7661 nodes, 18465 edges, 288
communities** (`graph.json`, `graph.html`, `GRAPH_REPORT.md` refreshed; not
staged). Direct AST audit of `v2/simulation/*.py`: `adapter.py` imports only
`__future__` + `v2.race_state` (plus internal `v2.simulation`), `state.py`
imports `v2.d9schema` + `v2.race_state`, `rng.py` imports `numpy`; no module
imports `adapter`, so there is no cycle. No model/feature/replay-prediction
dependency; no new god node (adapter adds a small isolated component).

## R2-S Known deferrals and R3 readiness

Deferred: a history-based permanent-non-participant policy (to reduce the
refused early frames / 5 did-not-start races); pace-history extraction from
D9 `<= T` (explicitly NOT part of the R2 factual adapter — R0 §29 placed it
in R2 scope, but the adapter's contract is the factual
`RaceState -> SimulationState` projection and pace baselines are a modelled
R3 input); retirement/pace/pit/traffic dynamics (R6); engine/aggregation
(R4/R5); API/frontend (R8).

R3 can proceed: `SimulationState` is now factually constructed from the
frozen Phase-5 replay seam, deterministic, and leak-tested under the
implemented adversarial suite.

---

# Phase 6 — R3 Implementation Record

Status: **R3 COMPLETE — offline empirical parameter layer + read-only
loader only; nothing simulated, nothing staged, nothing committed, no tag.**
Appended to the R0 plan, the R1 record, and the R2 record; none is
rewritten.

R3 owns estimation contracts, an offline estimator, a deterministic
versioned artifact, parameter identity, a read-only runtime loader,
support/fallback metadata, chronological estimation boundaries, leakage
tests, and diagnostics. It does NOT simulate races, make pit decisions,
model overtaking/traffic/reliability, generate SC/VSC, forecast weather, or
touch the API/frontend.

## R3-A Files changed

New:
- `v2/simulation/params.py` — parameter-artifact contract + stdlib-only
  read-only loader (`SupportEntry`, `ParameterFamily`,
  `SimulationParameterSet`, `load_simulation_parameters`,
  `parameter_storage_dir`).
- `v2/simulation/estimator.py` — offline estimator (pandas/numpy), isolated
  from the runtime loader.
- `scripts/build_simulation_parameters.py` — explicit-cutoff CLI.
- `tests/test_v2_phase6_r3.py` — 83 focused R3 tests.

Modified:
- `v2/simulation/__init__.py` — re-export the R3 parameter API.
- `docs/PHASE6_MONTE_CARLO_PLAN.md` — this record.

No frozen Phase-1–5 source was touched and no R1/R2 module was modified.
Nothing was staged or committed. Storage policy (R3-F): artifacts live under
`data/v2/simulation/params/…`, which `.gitignore` keeps untracked
(`/data/v2/` is generated + reproducible), exactly like the canonical Parquet
they derive from — so **no generated parameter artifact is added to Git**.

## R3-B Canonical-data audit (2018–2024)

Directly measured over `data/v2/processed` (2018–2024 only):

- `driver_lap_state_d9`: **162,728 driver-laps · 149 races · 40 drivers ·
  31 circuits · 16 constructors**.
- Null rates: `lap_time_s` 1.73%, `compound` 0.50%, `tyre_life` 0.60%,
  `stint_number` 0.21%, `position` 0.16%, `track_state` 0.82%.
- Compound vocabulary (rows): HARD 57,896 · MEDIUM 54,017 · SOFT 30,269 ·
  INTERMEDIATE 7,768 · SUPERSOFT 6,034 · ULTRASOFT 4,319 · WET 733 ·
  HYPERSOFT 887 · null 805. The 2018-only legacy names
  (SUPERSOFT/ULTRASOFT/HYPERSOFT) are kept verbatim; wet compounds are
  INTERMEDIATE/WET.
- `track_state` (rows): all_clear 146,547 · safety_car 6,981 · yellow 5,877 ·
  vsc 1,359 · null 1,340 · vsc_ending 314 · red_flag 310.
- `pit_stops` 5,452 stops (5,111 with both `pit_in_s`/`pit_out_s`);
  `stints` 8,030 (median length 19, p10 3, p90 37); `weather` 21,998 rows /
  149 races.
- **Eligibility funnel** (each step applied cumulatively, R3-B rule):
  162,728 total → 159,914 positive lap time → 150,622 no pit marker →
  138,238 green `all_clear` → **136,932 lap>1** (this equals the frozen F5
  eligible count) → 134,882 `is_accurate` → 133,627 not deleted →
  127,368 dry compound → 127,160 compound+age present → **124,040 final
  eligible dry laps**. Excluded at the margin: 9,292 pit markers, 12,384
  non-green, 1,306 opening laps, 2,050 inaccurate, 1,255 deleted, 6,259
  wet/missing compound, 3,120 rainfall laps.
- Eligible by era: 66,864 (2018–2021) / 57,176 (2022–2024). By compound:
  HARD 49,454, MEDIUM 43,525, SOFT 22,624, SUPERSOFT 5,027, ULTRASOFT 2,832,
  HYPERSOFT 578.

## R3-C Eligible-lap contract (versioned)

`ELIGIBILITY_RULE_VERSION = "r3-eligibility-v1"`. A lap is an eligible
**dry** pace lap iff ALL hold: `lap_time_s` present and `> 0`; no
`pit_in_s`/`pit_out_s` marker; `track_state == "all_clear"`; `lap_number > 1`;
`is_accurate` true; `deleted` false; `compound` in the DRY set; `tyre_life`
present; `wx_rainfall` not true. The rule is a strict tightening of the
frozen F5 pace eligibility (adds `is_accurate`, `deleted`, compound/age, and
the dry/rain filter). It is deterministic, testable, and reported in every
artifact. Slow traffic laps are NOT removed — there is no evidence-backed
rule for that — so they remain in the residual (see R3-L).

## R3-D Temporal estimation boundary

Estimation is chronological by construction: the estimator reads only
seasons `2018..through_season`, `through_season` is required, must be in
`[2018, 2024]`, and `SimulationParameterSet` rejects any artifact whose
`estimation_seasons` exceed the cutoff or leave 2018–2024. **2025 is never
read** (the loader only ever opens `season=YYYY` for `YYYY <= through`, and a
2025 file physically present in the tree is proven ignored by test). No
Phase-3 holdout, winner prediction, or replay-prediction cache is touched.

## R3-E Parameter artifact contract

`PARAMETER_CONTRACT_VERSION = "r3-v1"`; `PARAMETER_SET_ID =
"phase6-r3-empirical"`. The artifact (`SimulationParameterSet`) carries:
contract + estimator + eligibility versions, cutoff + estimation seasons,
source-data identity (row counts + per-entity content fingerprint), regimes
(dry/wet compounds, eras), policies, grouping hierarchy, support thresholds,
13 parameter families, factual diagnostics, creation metadata, and a
`scientific_hash`. Every value is a `SupportEntry` exposing
`sample_count`, `support_level` (`strong|weak|unavailable`),
`fallback_level` (`exact|circuit|season|era|compound|global|deferred|none`),
`group_key`, `observed_min/max`, and `identifiability`
(`identified|weak|deferred`). The loader validates contract version,
structure, finiteness, probability validity, observed ranges, and
transition distributions sum-to-one, and rejects a tampered artifact by
re-deriving the hash.

## R3-F Parameter identity / storage

`scientific_hash` = SHA-256 over everything except `creation_metadata`, so it
changes when data, eligibility, parameters, or the estimation window change
and does NOT change for timestamps/paths/hostnames.
`parameter_identity()` returns the R1 `ParameterIdentity`
(`set_id`/`version`/`hash`), where `version = "r3-v1.<through>.<hash[:12]>"`.
Canonical location `data/v2/simulation/params/r3-v1__through-<YYYY>/`
(generated, untracked). Determinism verified byte-for-byte: two builds of
`--through-season 2024` produced identical `manifest.json`
(SHA-256 `4d2f9db5…`), scientific hash
`4c2f85f08f1ce66cc6477982b2d5c97e9547f70927224b8e949ebe123ff3f140`,
artifact size 291,982 bytes, 13 families / 484 entries.

## R3-G/H Pace representation, grouping, fallback

Adopted decomposition: `mu_i(l) = base(circuit,era[,constructor]) +
progress_slope·(lap−ref) + degradation_slope·(tyre_age−ref) + residual`.
`base` is the circuit-era median clean lap time (a cold-start/fallback
anchor; R4 may prefer a driver's observed pace). Evidence-backed hierarchy:
- pace base: `circuit|era → circuit → global` (53 circuit-era groups; 30
  circuit fallbacks; the global absolute value is flagged `weak` because a
  global lap time is not circuit-comparable);
- constructor pace offset (median race-median-removed relative pace):
  `constructor|season → constructor|era → 0` (70 season offsets);
- progress slope: `circuit|era (n≥2000) → era → global` (31 circuit-era
  groups; thresholds `SLOPE_MIN_N=2000`, `DIST_GROUP_MIN_N=30`,
  `STINT_GROUP_MIN_N=25`, `CONSTRUCTOR_MIN_N=200`, `PIT_CIRCUIT_MIN_N=25`,
  all recorded in the artifact);
- degradation: `era → global` only;
- pit: `circuit → global`; stint: `era|circuit|compound → era|compound →
  compound → global` (118 circuit groups);
- transitions: `compound → GLOBAL`.

## R3-I Race-progress trend (adopted)

Pooled within (race × driver) joint OLS of relative pace on progress and
tyre age gives a consistent, precise negative trend: **global −0.0521 s/lap;
2018–2021 −0.0516; 2022–2024 −0.0528**; all 7 per-season estimates lie in
[−0.057, −0.049] and all 31 circuit-era estimates are negative. Adopted and
named **race-progress pace trend** — never causally attributed to fuel.

## R3-J Compound effect (deferred — not forced)

Compound-associated pace is **not identifiable with stable sign/magnitude**:
across-driver and within-driver/first-stint designs disagree (e.g. era-2
SOFT vs HARD flips sign with standard errors comparable to the point
estimate), consistent with confounding by strategy, fuel, and tyre age. Per
the scientific-priority rule the artifact stores `compound_offset_s` as
`identifiability="deferred"`, `fallback_level="deferred"`, no fabricated
value; the crude marginal point estimates are recorded only in diagnostics
(`compound_effect_observed_weak`) and are explicitly NOT adopted.

## R3-K Tyre degradation (broad pooled only)

Per-compound within-stint slopes are negative (fuel dominates: e.g.
−0.032/−0.020 s/lap) — degradation is NOT separately identifiable within a
single stint. Controlling for the adopted progress trend and using
cross-stint/field variation yields a positive, stable pooled slope:
**2018–2021 +0.0228; 2022–2024 +0.0264; global +0.0243 s/lap**, positive in
all 7 seasons. Decision **B**: only broad pooled per-era degradation is
defensible; it is marked `identifiability="weak"` and is explicitly
conditional on the progress trend and not causal. No per-compound or
per-circuit degradation is emitted.

## R3-L Stochastic residual model

Residuals after removing driver-race level + progress + age: heavy-tailed,
heteroskedastic, and positively autocorrelated. Global std **1.506 s**, MAD
scale **0.632 s**, lag-1 autocorrelation **0.264** (era-1 0.271 / era-2
0.264). The artifact stores an empirical zero-median quantile distribution
(15 quantiles) per era and globally — not a Gaussian — and clipping is
bounded by the observed support.

## R3-M Correlation assumption (documented, not silent)

v1 assumes **independent per-lap residual draws**. The measured within
driver-race lag-1 autocorrelation of 0.264 (driven by track evolution /
weather / traffic) violates that; the artifact records both the assumption
and the limitation, so trial outcomes are known not to be independent across
laps. No covariance model is attempted at R3.

## R3-N/O/P Pit loss, stint length, compound transitions

- **Pit loss.** `pit_lane_transit_s = pit_out_s − pit_in_s`, filtered to
  [8, 120] s (5,452 stops; 4,742 in-window), per circuit where
  n≥25 (28 circuits) and globally (median 23.66 s). Component penalties are
  reported separately (green in-lap n=3,560; out-lap n=3,681). The
  **effective 2-lap pit loss** = green in-lap + out-lap excess over the
  driver's clean pace, matched per stop (n=3,237; global median 23.23 s,
  p90 40.19 s) — this is the race-time cost the engine adds, distinct from
  raw pit-lane transit.
- **Stint length.** Observed lengths (behaviour, not optimal strategy):
  global median 19 laps (p10 3, p90 37); distribution by
  `era|circuit|compound` (118 groups) with documented fallbacks; wet
  compounds retained under their own keys.
- **Compound transitions.** 5,044 within race×driver consecutive-stint
  transitions; every current compound plus a `GLOBAL` fallback row sums to 1
  within 1e-6; legacy 2018 names kept verbatim.

## R3-Q/R Wet–dry and SC/VSC/red policy

Wet/dry: dry pace uses DRY compounds only and excludes rainfall laps; wet /
intermediate lap pace is DEFERRED (8,501 wet-compound rows excluded from dry
estimation). SC/VSC/red: all neutralized and unknown `track_state` laps are
excluded from normal pace (`all_clear` required); red/SC/VSC laps may inform
a later event model but are not used in R3.

## R3-T/U/V Support, read-only loader, offline estimator

`load_simulation_parameters(source)` reads `manifest.json` (or a directory),
validates contract version/structure, re-derives the scientific hash, and
returns the typed set read-only — no estimation, no mutation, no canonical
data, no winner model. The estimator (`v2/simulation/estimator.py`) is
isolated from the loader; `scripts/build_simulation_parameters.py` requires
`--through-season`.

## R3-W/X Determinism and adversarial result

Two builds of identical inputs/config produced byte-identical artifacts
(SHA-256 `4d2f9db5…`). **Future poisoning:** mutating all D9 lap times in a
season strictly after the cutoff and rebuilding `--through-season 2018` left
the scientific hash AND the full artifact bytes unchanged. **In-window
mutation:** mutating 2018 lap times changed the scientific hash; mutating a
2018 stint `end_lap` also changed it. **No leakage was detected under the
implemented adversarial test suite** (not a proof of leak-freedom).

## R3-Y/Z Label and 2025 firewalls

The estimator reads only `driver_lap_state_d9`, `stints`, `pit_stops`,
`races` — never `race_driver_labels`, `results`, Phase-2 labels, Phase-3
holdout/winner artifacts, or replay predictions (import + source scans and a
labels-absent estimation test). `through_season=2025` is rejected by both the
estimator and the artifact contract; a physically-present 2025 file is
ignored (proven by test).

## R3-AA/AB Diagnostics and scope

The artifact embeds factual diagnostics: the full eligibility funnel,
eligible counts by season/era/compound/circuit, wet-lap and rain-race counts,
per-era residual std/MAD/lag-1, degradation/progress support, pit/stint
sample counts, transition counts, fallback-usage potential, and the
documented residual-independence note. Nothing is fabricated as performance
or accuracy. R3 does NOT estimate overtake probability, traffic penalty,
reliability hazard, SC/VSC/red occurrence, weather transitions, or strategy
value (asserted by test).

## R3-AC/AF Validation and performance

Validation covers finiteness, nonnegative scales, probability bounds,
transition sum-to-one, positive support, valid observed ranges, known
compounds/regimes, and hash consistency; tampering is rejected
deterministically. Performance (single process, developer machine):
full 2018–2024 estimator **1.13 s**; artifact **291,982 bytes**; read-only
loader **≈4.1 ms** and **≈2.3 MB** peak Python allocation. No optimization
was required.

## R3-AD/AE Tests and verification

- `tests/test_v2_phase6_r1.py` + `r2` + `r3`: **335 passed** (~6.6 s); R3
  alone **83 passed**.
- MEDIUM relevant regression: `test_v2_d9.py`, `test_v2_d9_realdata.py`,
  `test_v2_phase4_r1..r6.py`, `test_v2_phase5_freeze.py`:
  **269 passed in 19:07**.
- Not run: full-suite pytest, model inference, replay-prediction cache
  generation. Frontend `DEFERRED — UNAFFECTED`.

## R3-AH Graphify

See the final R3 response for the measured `graphify update .` result
(exit code, nodes/edges/communities, and the import/cycle audit). Graphify
output is not staged.

## R4 readiness

`SimulationParameterSet` is immutable, versioned, hash-addressed, and
read-only; `parameter_identity()` plugs into the R1 request identity. R4 may
consume `pace_base`, `progress_slope`, `degradation_slope`, the residual
distribution, pit loss, stint length, and compound transitions directly, and
must apply the deferred compound offset as an explicit zero/assumption
rather than reading a fabricated value.

---

# Phase 6 — R4 Implementation Record

Status: **R4 COMPLETE — deterministic race-evolution kernel only; nothing
staged, nothing committed, no tag.** Appended to the R0 plan and the R1/R2/R3
records; none is rewritten.

R4 owns the zero-noise lap-step kernel that turns a factual `SimulationState`
and a validated `SimulationParameterSet` into a structural
`SimulationRunResult`. It adds no stochasticity, no Monte Carlo aggregation,
no pit/strategy, no traffic/overtaking, no reliability/retirement, no SC/VSC
generation, no red-flag restart, no weather evolution, and no API/frontend.

## R4-A Files changed

New:
- `v2/simulation/engine.py` — the deterministic kernel: adopted-parameter
  selection, start-state validation, event-driven lap stepping, expected
  pace, classification, and the stable unsupported/invalid taxonomies.
- `tests/test_v2_phase6_r4.py` — 79 focused R4 tests.

Modified:
- `v2/simulation/__init__.py` — re-export the R4 engine API and update the
  package dependency-direction note.
- `docs/PHASE6_MONTE_CARLO_PLAN.md` — this record.

No frozen Phase-1–5 source was touched. No R1/R2/R3 contract module was
modified. `v2/simulation/pace_context.py` was **not** created (see R4-C).

## R4-B Adopted R3 parameter subset (R4-A audit)

Adopted by the deterministic kernel:

| Family | Role | Hierarchy actually used |
|---|---|---|
| `pace_base_s` | absolute clean dry lap anchor | `circuit\|era` (exact) |
| `pace_base_fallback_s` | base fallback | `circuit`, then `global` (weak) |
| `constructor_pace_offset_s` | team relative pace | `constructor\|season`, `constructor\|era`, `global` (0) |
| `race_progress_slope_s_per_lap` | progress trend | `circuit\|era`, `era`, `global` |
| `degradation_slope_s_per_lap` | pooled tyre-age slope | `era`, `global` |

Deliberately **not** used: the R3 `lap_residual_distribution_s` (R4 is
deterministic — no random draw); `compound_offset_s` (R3 marked it
`identifiability="deferred"`, `fallback_level="deferred"`, no value — R4 must
not invent one); and every pit/stint/compound-transition family (R6). The
`stint_length_laps["global"].observed_max` is read **only** as the observed
tyre-age support upper bound used to clamp the degradation effect (R4-F); it
is not used as a pit/strategy parameter.

The `Selection` object returned by `select_pace_parameters()` exposes the
chosen family/key/value plus `support_level`, `fallback_level`, and
`identifiability` for every adopted effect, so a weak/global fallback is
inspectable and can never masquerade as a circuit-specific measurement
(R4-Z). It is separate from `SimulationRunResult`, which stays unbloated.

## R4-C Pace-anchor decision (R4-I)

**Decision: option C — the defensible R3 baseline hierarchy, with no
driver-specific current-pace term, and no new past-only pace seam.**

Audit finding: `SimulationState` carries no lap-time history; R2 deliberately
did not bypass `RaceState` to read D9 `<= T` lap times, and the R1 contract
has no `pace_base`/`pace_latent` field. Therefore no driver-specific factual
pace anchor exists in the R4 inputs. R4 anchors each driver at
`base(circuit, era) + constructor_offset(constructor)` and adds only
delta-from-anchor trends. Two drivers of the same constructor therefore share
one pace anchor; this is a documented R4 limitation, not hidden. A
temporal-safe past-only pace-context adapter is the natural R5+ upgrade if
calibration shows the shared anchor is too coarse; it was **not** added now
because R4 does not require it to be correct or honest.

## R4-D Deterministic pace equation

With `reference_lap = leader_laps_done` (the factual race progress at ``T``)
and the driver's own factual tyre age at ``T`` as the degradation anchor:

```
mu_i(l) = base(circuit, era) + constructor_offset(constructor)
        + race_progress_slope * (l - reference_lap)
        + degradation_slope * (clamp(age_i(l)) - clamp(age_i(T)))
```

`clamp(.)` bounds the tyre age to `[0, observed_max(stint_length_laps.global)]`
(77 laps in the through-2024 artifact). There is no residual draw, no compound
delta, no traffic term, no pit term, and no reliability term. `expected_lap_time_s()`
is a public pure function over the selection so the equation is unit-tested.

## R4-E Race-progress effect (R4-L)

R3's adopted trend is a negative per-lap slope (`global -0.0521 s/lap`;
era-1 `-0.0516`; era-2 `-0.0528`), named **race-progress pace trend** in code
and docs — never "fuel burn". It is applied as a delta from the factual leader
progress at ``T`` (the R0 §8 reference), so the era-average trend already
embedded in the R3 `base` is not re-applied from lap 0. Tests pin the sign
(negative delta for the leader's next lap; positive for an earlier-progress
lapped car) and monotonic slowdown over the race.

## R4-F Degradation effect (R4-M)

Only the broad pooled per-era slope is used (`global +0.0243 s/lap`;
era-1 `+0.0228`; era-2 `+0.0264`, all `identifiability="weak"`). It is a delta
from the driver's factual age at ``T``. The effect is **clamped** to the
observed age support via the global `stint_length_laps` observed maximum
(77 laps) because the R3 scalar degradation entries carry no observed
age range; the clamp is exposed through `selection.age_support_max_laps` and
tested. No per-compound and no per-circuit degradation is created. A
nonpositive/nonfinite expected lap time cannot be emitted: the kernel either
rejects (nonpositive/nonfinite) as an invalid run or guards finiteness.

## R4-G Compound policy (R4-N)

The deferred R3 compound offset is applied as an explicit zero: compound is
carried through but has no pace effect. Tests prove SOFT/MEDIUM/HARD/null all
produce a byte-identical classification, and that a poisoned
`compound_offset_s` entry (value 1000 s) changes nothing. Wet compounds
(`INTERMEDIATE`/`WET`) are rejected as wet-pace unsupported (R4-H); a null
compound is accepted as the dry baseline because compound has no R4 effect.

## R4-H Kernel evolution semantics (R4-O/P)

Event-driven, one lap per event:

1. each driver's next completion time is `race_time_s + mu_i(next_lap, age+1)`;
2. the driver with the globally earliest next completion is advanced;
   all drivers sharing that exact completion time are advanced together in
   `driver_id` order (deterministic ties);
3. a driver completing `scheduled_laps` ends the race (the leader-based finish
   condition); remaining drivers keep the laps they completed at that instant;
4. a hard bound `roster_size * scheduled_laps + roster_size` caps the loop and
   yields `invalid_reason="iteration_limit_exceeded"` if ever exceeded.

Lap stepping is not synchronous: a driver is never forced onto the leader's
lap, so lapped semantics are preserved.

## R4-I Race-clock semantics (R4-P)

`race_time_s` is each driver's own last-completed-lap absolute session clock
and is advanced only by that driver's own `mu`. `simulation_time_s` is the
factual anchor ``T`` and is not used as a global increment. Classification is
taken at the instant the leader completes the scheduled distance (R0 §15),
exactly as the frozen lap-end clock grain supports; within-lap progress is
neither observed nor claimed.

## R4-J Lapped-driver semantics (R4-Q)

Lapped cars evolve from their own `(lap_number, race_time_s)`. With a zero
progress trend, a field starting at laps `(5, 4, 3)` over `scheduled=7` ends
`(7, 6, 5)` — the leader's distance, then one and two laps down, exactly the
R4-Q contract. With the real negative trend a lapped car can fall a further
lap at the finish instant; this is a documented free-air artifact, never a
forced relap and never an inferred retirement.

## R4-K Ordering / free-air semantics (R4-R/S)

Position is derived from simulated progress by
`(laps_completed DESC, race_time_s ASC, driver_id ASC)` (R0 §16), verified
against the final trace. The `driver_id` tie-break makes exact ties
deterministic (tested). This is **free-air deterministic ordering**: a faster
car can legally reorder ahead through cumulative time, but this is not a
traffic/overtake simulation and no arbitrary passing threshold is added
(traffic/overtaking belong to R6). No overtake events are inferred.

## R4-L Tyre-age and pit policy (R4-T/U)

Each completed simulated lap increments `tyre_age` by one and keeps `compound`,
`stint_number`, and `pit_count` unchanged. A factual `tyre_age=None` is
**rejected** (`missing_tyre_age`) rather than converted to 0. There is no pit
model: tyre age may exceed realistic stint lengths over a long run, which is
documented as an R4 limitation and never silently auto-pitted.

## R4-M Supported start states and unsupported taxonomy

Supported: an all-`ACTIVE`, fully observed roster with non-null tyre ages,
`track_state == all_clear`, no rainfall, dry/absent compounds, a represented
factual leader progress, and a known circuit+season (era).

Rejected deterministically (`SimulationUnsupportedError` with a stable
reason): `red_flag_track_state`, `neutralized_track_state` (yellow / safety_car
/ vsc / vsc_ending), `unknown_track_state` (null is not green),
`wet_track_conditions` (rainfall true), `wet_compound_state`,
`missing_tyre_age`, `retired_driver_unsupported`, `missing_circuit_id`,
`missing_season`, `unsupported_season`, `parameter_temporal_leak`,
`missing_pace_parameter`, `leader_progress_not_represented`. No SC/VSC state is
silently converted to green and no red-flag restart is invented.

## R4-N Temporal parameter policy (R4-AD/AE)

An explicit `ExecutionPolicy` distinguishes
`RETROSPECTIVE_PRODUCT` (a frozen production parameter set may include the
target season; the run is a retrospective simulation) from
`HISTORICAL_BACKTEST` (the parameter cutoff must be **strictly before** the
evaluated target season). `PaceParameterSelection.leakage_free` is
`through_season < target_season`, and `HISTORICAL_BACKTEST` refuses a
leakage-tainted combination with `parameter_temporal_leak`. It is therefore
impossible to accidentally run a "leakage-free" historical backtest with
future-estimated parameters; the full R7 evaluator is not implemented.

## R4-O Determinism, RNG independence, numerical safety

No RNG is used: the kernel imports no `numpy`/`random`, reads no seed, and
`master_seed` has no effect on its result (the R1 request identity still
depends on the seed; the kernel does not). `simulation_id` is a deterministic
structural identity (`race_id:parameter_version:state_identity[:16]:0`) with
`simulation_index=0`; repeated runs are byte-identical across engine
instances. Numeric guards reject a nonfinite or nonpositive expected lap time
and a nonfinite race clock, returning `SimulationRunResult(valid=False, ...)`
with a stable `INVALID_RUN_REASONS` token instead of a fabricated
classification.

## R4-P Tests

`tests/test_v2_phase6_r4.py` (79 passed) covers: supported-state validity and
one-winner classification; red/SC/VSC/yellow/unknown rejection; wet
weather/compound rejection and null-compound acceptance; null tyre-age and
retired-driver rejection; parameter selection and circuit→global fallback;
per-driver constructor offsets; the expected-pace equation and age clamping;
progress sign/reference; degradation growth and support clamp; no invented
compound effect (including a poisoned offset); lap/race-time monotonicity;
lapped-field semantics; leader-based completion; ordering and exact ties;
free-air reordering; tyre-age increment; no-pitting; full-roster
classification; zero-noise determinism; seed independence and no-RNG source
scan; the structural iteration bound; nonpositive/nonfinite pace rejection;
temporal policy behavior; AST/runtime import and canonical-data firewalls;
representative real fixtures (ordinary mid-race, late race, yellow, red);
the last-frame completion smoke; and a performance smoke. The real fixtures
use the frozen Phase-5 replay seam only to build the factual
`SimulationState`.

## R4-Q Verification

- `tests/test_v2_phase6_r1..r4`: **414 passed** (~7.5 s; R4 alone 79).
- FAST frozen regression: `test_v2_phase4_r1.py` + `test_v2_phase4_r2.py` +
  `test_v2_phase5_freeze.py` **104 passed**; `test_v2_phase5_r1.py` +
  `test_v2_phase5_r2.py` **98 passed**.
- Not run: full-suite pytest, the R3 MEDIUM gate (no frozen dependency
  changed), model inference, replay-cache generation. Frontend
  `DEFERRED — UNAFFECTED`.

## R4-R Performance (single process, developer machine)

20-driver `2023-r01-R`, 300 runs each (evolution only, warm):

| Fixture | leader laps | lap events | mean | p50 | p95 | peak allocation |
|---|---|---|---|---|---|---|
| early | 2 | 1099 | 3.95 ms | 3.79 ms | 4.40 ms | ~1.5 MiB |
| mid | 28 | 579 | 2.84 ms | 2.75 ms | 2.92 ms | ~1.5 MiB |
| late | 40 | 361 | 2.51 ms | 2.40 ms | 2.81 ms | ~1.5 MiB |

Peak allocation is dominated by `parameter_version`'s scientific-hash
serialization (R3 calls it once per run); R5 should hoist that once per
Monte Carlo batch. No gate is invented; the kernel is clearly fast enough for
R5 to prototype vectorization against.

## R4-S Graphify

`graphify update .` exit **0**: **7980 nodes, 19466 edges, 285 communities**
(refreshed, not staged). AST audit: `engine.py` imports only
`errors`/`state`/`params`/`results` (plus stdlib); no module imports `engine`,
so there is no cycle and the dependency direction is downstream. No
canonical-data, winner-model, feature-engine, replay-prediction, or API
dependency (pinned additionally by AST and subprocess-import tests). No new
god node: the engine is a small downstream component.

## R4-T Known limitations

- Shared constructor pace anchor (no driver-specific current pace), so
  same-constructor drivers are pace-identical.
- Session-clock continuity is assumed: a red-flag-affected race whose anchor
  ``T`` has already returned to `all_clear` can carry corrupted lap/clock
  offsets that R4 cannot detect from `SimulationState`; such historical races
  should be excluded by the caller / R7 protocol, and R4's fixtures avoid them.
- The stop-at-leader-finish contract classifies lead-lap cars behind on
  `scheduled_laps - 1` at the finish instant (R0 §15), not with a credited
  final lap.
- Lap-boundary resolution only; no within-lap progress.
- The degradation age support is proxied by the global observed maximum stint
  length because R3 stores no age range on the scalar degradation entries.
- Free-air ordering is not an overtaking/traffic model; no pitting, no
  reliability, no SC/VSC generation, no weather evolution.

## R4-U R5 readiness

The kernel is deterministic, RNG-free, numerically guarded, and fast
(2.5–4 ms per 20-driver run). R5 can: (1) call `select_pace_parameters()` once
and reuse the selection, (2) hoist `parameter_version`/`scientific_hash()`
once per batch, (3) add the R3 residual draw around `expected_lap_time_s()`
and vectorize across trials, and (4) reuse `FinishOrder`/`SimulationRunResult`
unchanged. `MonteCarloResult` remains unimplemented, as required.

---

# Phase 6 — R5 Implementation Record

Status: **R5 COMPLETE — stochastic Monte Carlo engine + aggregation only;
nothing staged, nothing committed, no tag.** Appended to the R0 plan and the
R1/R2/R3/R4 records; none is rewritten.

R5 is the first stochastic stage. It adds the R3 empirical residual draw to
the frozen R4 deterministic kernel, runs many deterministically seeded
trajectories (scalar oracle + chunked vectorized batch), and aggregates valid
finishing classifications into `MONTE_CARLO_FREQUENCY` probabilities. It adds
no pit model, no traffic/overtaking model, no reliability/DNF, no SC/VSC/red
generation, no weather evolution, no points table, and no API/frontend.

## R5-A Files changed

New:
- `v2/simulation/monte_carlo.py` — empirical residual sampler, per-trajectory
  RNG pools, scalar stochastic oracle, chunked vectorized batch evolution,
  integer-count aggregation, probability invariants, `MonteCarloEngine`.
- `tests/test_v2_phase6_r5.py` — 51 focused R5 tests.
- `scripts/benchmark_phase6_monte_carlo.py` — explicit-fixture 1k/10k/50k
  benchmark + convergence diagnostic (no generation, no training, no 2025).

Modified:
- `v2/simulation/__init__.py` — re-export the R5 API; dependency note updated.
- `docs/PHASE6_MONTE_CARLO_PLAN.md` — this record.

No frozen Phase-1–5 source was touched. No R1/R2/R3/R4 module was modified
(R4 is consumed read-only through its public API plus two validated pure
private helpers, `_validate_start_state` / `_validate_temporal`; R4 behavior
is unchanged and its 79 tests remain green).

## R5-B R4 semantics pinned (R5-A audit)

R5 preserves, and does not silently change, every R4 semantic: supported
all-`ACTIVE`, fully observed, green, dry, non-null-tyre-age start states;
event-driven lap completion (the globally-earliest next completion advances;
exact ties advance together in `driver_id` order); the expected-pace equation
(`base + constructor_offset + progress_slope·(l−ref) + degradation_slope·(clamp(age)−clamp(anchor_age))`);
support clamp; the deferred compound offset applied as an explicit zero;
lapped drivers evolving from their own `(lap_number, race_time_s)`;
leader-based race completion; free-air `(laps DESC, race_time ASC, driver_id)`
ordering; the structural iteration bound; and the RETROSPECTIVE_PRODUCT /
HISTORICAL_BACKTEST temporal policy. All R4 tests stay green.

## R5-C Stochastic pace equation

```
lap_time_i(l) = mu_i(l) + epsilon
```

`mu_i(l)` is unchanged R4 `engine.expected_lap_time_s`; `epsilon` is one R3
empirical residual draw (R5-D). With `epsilon = 0` the trajectory is
byte-identical to R4.

## R5-D Empirical quantile sampling

`select_residual_sampler()` selects R3 `lap_residual_distribution_s` by
`era` then `global`. The stored 15-point `(probabilities, quantile_values)`
plus `observed_min/max` define the grid
`(0, observed_min), (p_1, q_1), …, (p_m, q_m), (1, observed_max)`; a uniform
`u` is linearly interpolated over that grid (`np.interp`, numpy only — no
scipy). Draws are deterministic for a fixed `u`, finite, and bounded by the
observed support. No Gaussian/uniform replacement noise or hardcoded seconds.
Invalid (nonfinite/nonpositive) lap times are not repaired: they invalidate
the trajectory.

## R5-E Residual centering (diagnostic only)

The artifact residual is zero-median and heavy-tailed. A 1,000,000-draw
diagnostic of the actual through-2024 artifact:

| group | mean (s) | median (s) | std (s) | min (s) | max (s) |
|---|---|---|---|---|---|
| 2018-2021 | +0.1628 | −0.0001 | 1.6967 | −5.5533 | 69.3284 |
| 2022-2024 | +0.1307 | −0.0001 | 1.7439 | −10.0712 | 64.1115 |
| global | +0.1455 | −0.0001 | 1.7328 | −10.0499 | 69.3182 |

The sample mean is slightly positive because the distribution is centered on
the median, not the mean. R5 does **not** recenter/rescale to force a zero
mean; the distribution is used as stored.

## R5-F Independence assumption (prominent v1 limitation)

R3 measured lag-1 residual autocorrelation ≈0.264 and deferred a correlation
model, so **R5 v1 assumes independent per-lap residual draws**
(`RESIDUAL_INDEPENDENCE_ASSUMPTION = "independent_per_lap_v1"`). Simulated
trajectories therefore understate lap-to-lap persistence. No AR(1)/covariance
model is invented.

## R5-G/H RNG and draw-order contract

Each trajectory `i` uses `rng_for_simulation(master_seed, i, contract_version)`
(R1 `PCG64` stream). Draws are consumed in deterministic event order: the
earliest next-lap completion first, drivers sharing that exact completion in
canonical `driver_id` order, one uniform per rescheduled driver. No global
RNG, no worker RNG, no time seed. Chunk size and execution order never change
which draw belongs to which driver/event.

## R5-J/K Scalar oracle and zero-noise parity

`run_trajectory_scalar()` is the simple per-trajectory event loop (R4
semantics plus residual). `zero_noise=True` removes the residual effect and
the classification is asserted byte-identical to `DeterministicRaceEngine`
on synthetic and real fixtures (`test_zero_noise_scalar_matches_r4_exactly`,
`test_real_zero_noise_matches_r4`). Same `(seed, index)` is deterministic;
`zero_noise` also ignores seed/index as expected.

## R5-L/M/N Batch / vector architecture

`MonteCarloEngine.run()` evolves a chunk as `(chunk, drivers)` numpy arrays
while preserving per-trajectory event semantics (the earliest driver per
trajectory advances; it never synchronously advances all drivers). Each
trajectory's per-lap uniforms are pre-drawn once into a bounded pool
(`max_residual_draws = Σ(scheduled_laps − lap_number)`), then consumed
sequentially in event order. The scalar oracle consumes the identical pool in
the identical order, so the two paths are bit-identical.

## R5-O/P Chunk and prefix invariance

Scientific identity is independent of `chunk_size` (tested at 1/7/64/1024)
and `chunk_size` is not part of request identity. Simulation ids are `0..N−1`
and the stream depends only on `(seed, id, version)`, so the first 100
trajectories of a 1000-simulation request equal a standalone 100-simulation
request (tested via retained sample orders).

## R5-S..W Aggregation

Aggregation accumulates integer per-driver position counts
`position_counts[driver, position]` from each valid classification, then
divides once by `valid_simulation_count`. Win counts are the position-1
column; podium counts are positions ≤3; per-driver position distributions are
`count/valid` over `1..field_size`; `expected_finish` is the mean of that
distribution. `valid + invalid == requested`; invalid trajectories are
counted with a deterministic internal reason and excluded (never rerun with a
new seed, never counted as zero-probability). If `valid_count == 0`, a
deterministic `SimulationValidationError` is raised.

## R5-AA Probability invariants (enforced, not repaired)

Checked before a result is built: winner-count total `== valid`; `Σ win == 1`
(no normalization); podium-count total `== valid·min(3, field_size)`;
`Σ podium == min(3, field_size)`; every driver's position-count total
`== valid`; every distribution sums to 1; every probability finite and
`[0,1]`; `expected_finish ∈ [1, field_size]`. A violation raises
`SimulationValidationError`, never a silent renormalization.

## R5-X DNF / points deferrals

DNF buckets are absent and `dnf_probability` is null: reliability is not
implemented (R6). Points are not fabricated: `points_probability` and
`expected_points` are null (the points-regulation contract is not
implemented). `reliability_enabled=True` is rejected deterministically rather
than fabricating a no-DNF result.

## R5-AI Temporal parameter policy

`ExecutionPolicy` is preserved: `HISTORICAL_BACKTEST` with parameters whose
`through_season >= target_season` raises
`SimulationUnsupportedError(parameter_temporal_leak)`; `RETROSPECTIVE_PRODUCT`
allows in-window parameters. A 2025 target season is rejected (`unsupported_season`).

## R5-AJ/AK Firewalls

AST import audit of `monte_carlo.py`: no `pandas`, `sklearn`, `joblib`,
`fastapi`, `v2.prediction`, `v2.model_lab`, `v2.replay*`, `v2.race_state`,
`v2.d11`, `v2.features`, `v2.labels`, or API import; no global-RNG tokens;
no `read_parquet`/canonical-data access. A fresh-subprocess import test proves
`v2.prediction`, `v2.model_lab`, and `pandas` are not loaded. Monte Carlo
frequencies come solely from simulated outcomes and are never a normalization
of `INDEPENDENT_BINARY` scores.

## R5-AL 2025 boundary

Runtime Monte Carlo reads only `SimulationState` + `SimulationParameterSet` +
`SimulationConfig` + `Assumptions`; the benchmark uses only 2018–2024
fixtures; no 2025 protected target is accessed.

## R5-AC/AB Reproducibility and non-degeneracy

Same seed → identical scientific identity; a different seed changes a
suitable fixture's outcomes. Real early-race state (2023-r01-R, lap 2, 20
drivers, N=1000): 5–6 distinct winners and all 20 drivers occupying multiple
positions, i.e. not accidentally deterministic.

## R5-AD Convergence diagnostic

Early-race competitive fixture, win probability ± binomial SE
`sqrt(p(1−p)/N)`:

| N | max_verstappen | perez | sainz/leclerc |
|---|---|---|---|
| 1,000 | 0.5970 ± 0.0155 | 0.3980 ± 0.0155 | 0.0030 ± 0.0017 |
| 10,000 | 0.5920 ± 0.0049 | 0.4025 ± 0.0049 | 0.0021 ± 0.0005 |
| 50,000 | 0.5945 ± 0.0022 | 0.3997 ± 0.0022 | 0.0027 ± 0.0002 |

This is a convergence diagnostic only; no model accuracy is claimed.

## R5-AE/AF Benchmark (single process, developer machine, warm)

`scripts/benchmark_phase6_monte_carlo.py`, chunk size 512, seed 20240101,
actual through-2024 artifact:

| fixture | leader laps | remaining | N | wall time | sims/s | valid/invalid |
|---|---|---|---|---|---|---|
| early | 2 | 55 | 1,000 | 0.618 s | 1,619 | 1000 / 0 |
| early | 2 | 55 | 10,000 | 6.200 s | 1,613 | 10000 / 0 |
| early | 2 | 55 | 50,000 | 27.512 s | 1,817 | 50000 / 0 |
| mid | 28 | 29 | 1,000 | 0.254 s | 3,944 | 1000 / 0 |
| mid | 28 | 29 | 10,000 | 2.539 s | 3,939 | 10000 / 0 |
| mid | 28 | 29 | 50,000 | 12.546 s | 3,985 | 50000 / 0 |
| late | 40 | 17 | 1,000 | 0.347 s | 2,881 | 1000 / 0 |
| late | 40 | 17 | 10,000 | 1.884 s | 5,308 | 10000 / 0 |
| late | 40 | 17 | 50,000 | 8.968 s | 5,576 | 50000 / 0 |

10k is 1.9–6.2 s (excellent/strong); 50k is 9.0–27.5 s; all 10k cases are
well under the R0 provisional 60 s target. Interpretation (not a scientific
claim): <5 s excellent, 5–15 s strong — the early full-distance case is the
worst and still 6.2 s. No optimization was required, so no profiling was
performed.

## R5-AG Memory

Peak RSS in the benchmark was 154–167 MB across 1k/10k/50k (chunked; only
current trajectory state + aggregate counts are retained). No 50k × events ×
drivers history is materialized; only the first `sample_orders` finishing
orders are retained.

## R5-AH Trace policy

The batch engine collects no per-event traces. The scalar oracle also returns
only the final classification; trace-level debugging is not exposed in R5.

## R5-AP Tests and R5-AQ benchmark script

`tests/test_v2_phase6_r5.py` (**51 passed**) covers quantile interpolation and
pinning, support bounds, deterministic draws, stream/index/seed sensitivity,
the independence contract, scalar determinism, zero-noise R4 parity, draw
order via scalar/batch parity, chunk and prefix invariance, invalid
accounting (including zero-valid and reliability rejection), winner/podium
aggregation, position distributions, expected finish, no DNF/points, sample
order determinism, probability invariants, non-degeneracy, seed sensitivity,
temporal policy, 2025 boundary, import/source/global-RNG/canonical-data
firewalls, a fresh-process import, real scalar/batch parity, a real 1k smoke,
and a performance smoke.

`scripts/benchmark_phase6_monte_carlo.py` loads explicit 2018–2024 fixtures
through the frozen Phase-5 replay seam, adapts via R2, loads the explicit R3
artifact, and reports wall time, sims/s, valid/invalid counts, peak RSS, and
win-probability SE. Output is reproducible except timing/memory.

## R5-AR Verification

- `tests/test_v2_phase6_r1..r5`: **465 passed** (~8.8 s; R5 alone 51).
- FAST frozen regression: `test_v2_phase4_r1.py` + `test_v2_phase4_r2.py` +
  `test_v2_phase5_freeze.py` + `test_v2_phase5_r1.py` + `test_v2_phase5_r2.py`:
  **202 passed**.
- The 19-minute R3 MEDIUM gate was not rerun (no frozen dependency changed).
- Not run: full-suite pytest, model inference, replay-cache generation.
  Frontend `DEFERRED — UNAFFECTED`.

## R5-AS Graphify

See the final R5 response for the measured `graphify update .` result (exit
code, nodes/edges/communities, and the import/cycle audit). Graphify output is
not staged.

## R5 Known limitations

- Independent per-lap residual draws (R5-F); no autocorrelation model.
- Shared constructor pace anchor inherited from R4 (no driver-specific current
  pace), so same-constructor drivers are pace-identical; the R3 residual adds
  variance but not driver-specific skill.
- Lap-boundary resolution only; no within-lap progress, pit, traffic,
  reliability, SC/VSC generation, or weather evolution (all R6+).
- The residual endpoint extrapolation to `observed_min/max` slightly widens
  the sampled tail relative to the raw stored quantiles (diagnostic std
  ≈1.70–1.74 s vs artifact std ≈1.51 s); this is bounded by the observed
  support and does not change any R4 semantics.
- Probabilities are simulation frequencies, not calibrated forecasts; no
  historical validation/accuracy is claimed in R5.

## R5 R6 readiness

`MonteCarloResult` is populated with deterministic scientific identity,
integer-count auditable frequencies, and probability invariants. R6 can add
pit/traffic/lapped dynamics and an optional reliability hazard behind the
existing `SimulationConfig.reliability_enabled` switch and extend aggregation
with a DNF bucket and points maps, without changing the R5 residual sampler,
RNG/draw-order contract, scalar oracle, or batch/scalar parity guarantees.

---

# Phase 6 — R6 Implementation Record

Status: **R6 COMPLETE — pit / tyre / compound / lapped race dynamics behind an
opt-in switch; traffic/overtaking and reliability explicitly DEFERRED; nothing
staged, nothing committed, no tag.** Appended to the R0 plan and the R1–R5
records; none is rewritten.

R6 adds historically plausible pit behaviour to the R5 stochastic engine:
per-stint tyre-age pit targets, one-shot effective pit loss, R3 compound
transitions, tyre-age resets, stint/pit counters, and lapped-car coherence.
It adds no strategy optimisation, no what-if UI, no calibrated
overtaking/traffic model, no reliability/DNF hazard, no SC/VSC/red generation,
no weather evolution, no points scoring, and no API/frontend.

## R6-A Files changed

New:
- `tests/test_v2_phase6_r6.py` — 58 focused R6 tests.

Modified:
- `v2/simulation/config.py` — one narrow field, `pit_dynamics_enabled`
  (default `False`), plus an R5-compat identity policy.
- `v2/simulation/rng.py` — additive `rng_for_domain` + `SIMULATION_RNG_DOMAINS`.
- `v2/simulation/monte_carlo.py` — R6 quantile grids, `PitParameterSet` /
  `select_pit_parameters`, `MonteCarloDiagnostics`, scalar and vectorized pit
  evolution, optional diagnostics.
- `v2/simulation/__init__.py` — re-export the R6 API.
- `scripts/benchmark_phase6_monte_carlo.py` — additive `--pit-dynamics`,
  mechanics/parameter reporting, pit diagnostics.
- `docs/PHASE6_MONTE_CARLO_PLAN.md` — this record.

No frozen Phase-1–5 source was touched. No R1/R2/R3/R4/R5 module contract was
changed; `v2/simulation/engine.py` (R4) is untouched and its 79 tests remain
green. No new parameter artifact was created (R6 consumes existing R3 families
read-only). `v2/simulation/dynamics.py` and `v2/simulation/reliability.py`
were **not** created.

## R6-B R5 baseline preservation (release-blocking)

Before any change, the R5 baseline was pinned: `tests/test_v2_phase6_r1..r5`
= **465 passed**, plus the `MonteCarloResult.identity()` of the three
representative fixtures (early `ee315af7…`, mid `93b18a58…`, late `977c63ed…`)
and their scalar/batch parity. After R6:

- `SimulationConfig(10, 1).to_dict()` is byte-identical to the R5 payload
  (`{simulation_count, master_seed, sample_orders, reliability_enabled}`): the
  R6 switch is omitted from the serialized identity at its `False` default, so
  an R5-compatible request keeps a byte-identical identity (it IS recorded and
  changes identity once enabled).
- The three real fixtures reproduce the pinned R5 identities exactly
  (`test_pit_disabled_reproduces_r5_result_identity`).
- With `pit_dynamics_enabled=False` no pit draw is consumed (pools are never
  built) and no pace/RNG stream shifts; `rng_for_simulation` still constructs
  `SeedSequence([seed, simulation_id, tag])` (pinned by test).
- `collect_diagnostics` never changes the scientific result.

## R6-C Configuration refinement

One field only: `SimulationConfig.pit_dynamics_enabled: bool = False`.
`reliability_enabled` already existed. **No traffic knob is exposed** because
no traffic model is implemented. The default is `False` — the explicit
R5-equivalent mode — because the R6 mechanics are validated by R7 before any
production default changes. Identity policy: the field is omitted from
`to_dict()`/`identity()` when `False` and present when `True`.

## R6-D..F Pit decision semantics (evidence, not strategy)

R3 `stint_length_laps` is *observed behaviour*, not optimal strategy, and R6
uses it as such: a driver draws a per-stint **target tyre age**; when a
completed lap's tyre age reaches the target and the race is still running, the
driver stops. This is never called optimal and is replaceable by a later
strategy layer.

- **Initial stint (R6-E):** the target is drawn *conditional on exceeding the
  driver's factual tyre age*, using the quantile-grid CDF inverse and the
  conditional-quantile transform `u' = F(a) + u·(1−F(a))` (then rounded to an
  integer `≥ age+1`). A factual age at or beyond the observed support falls
  back to `age+1` (documented). No retroactive or negative remaining stint is
  ever produced (`test_initial_target_is_never_retroactive_when_age_exceeds_support`).
- **Future stints (R6-F):** after a pit, an unconditional target is drawn from
  the selected compound's distribution, clamped to `≥ 1`.
- Hierarchy actually used: `stint_length_laps[era|circuit|compound] →
  [era|compound] → [compound] → [global]` (R3-G hierarchy, unchanged).

## R6-G Compound transition policy

At a simulated pit the next compound is drawn from the R3
`compound_transition_probability` row for the current compound
(`GLOBAL` for a null/unknown current compound). **Dry filtering:** targets not
in `DRY_COMPOUNDS` are removed and the dry mass renormalized, because R6 has
no wet pace model; a row with no dry mass falls back to `GLOBAL` (R6-G). No
invented compound preference is introduced. Note: R3 transitions are pooled
across eras, so legacy 2018 names (e.g. `SUPERSOFT`) can appear as targets
with their observed (small) frequencies; this is R3-faithful, not fabricated.

## R6-H Tyre / stint / pit update (pinned convention)

The Phase-1 RaceState convention was inspected, not guessed: in D9 the
**out-lap row carries `tyre_life == 1`** (verified on 2023-r01-R `alonso`:
lap 14 = in-lap SOFT age 17, lap 15 = out-lap HARD age 1; `stints.tyre_age_at_start`
= 1 for fresh stints). R6 therefore resets the internal age to `0` at the pit
so that the next scheduled lap becomes age `1`; the trace exposes
`out_lap_tyre_age == 1`. On each pit: `pit_count += 1`,
`stint_number = pit_count + 1`, `compound = selected`, age reset, new target
drawn, and the sampled loss added to `race_time_s`.

## R6-I Pit loss

R6 uses `pit_effective_loss_s` — the R3 **effective 2-lap race-time cost**
(green in-lap + out-lap excess over the driver's clean pace), circuit-keyed
with a global fallback — NOT the stationary `duration_s` and NOT raw
`pit_lane_transit_s`. It is sampled from the empirical quantile grid and added
**exactly once** per pit. Because the kernel already charges clean pace for the
in- and out-laps, adding the effective excess yields the real two-lap cost.
No hardcoded seconds appear anywhere (`test_pit_loss_is_applied_exactly_once_per_pit`).

## R6-J/AA/AB Event ordering and edges

- Pit eligibility is evaluated **after** the lap is completed, in two passes:
  (1) apply the whole event batch's lap completions and finish flags; (2) for
  non-finished drivers, pit (if target reached and the race is not over), then
  reschedule. Two passes preserve the exact R5 pace draw order.
- At a pit the draws are consumed in fixed order: **compound → pit loss →
  next target** (documented).
- A pit is suppressed on the step the race ends anywhere in that trajectory
  (R6-AB final-lap edge; `test_final_lap_pit_is_suppressed`).
- Ties (same completion time) are processed in canonical `driver_id` order
  exactly as R4/R5; pits within a shared batch are ranked by driver index.

## R6-K RNG domain separation

`rng_for_domain(master_seed, simulation_id, domain, contract_version)` adds a
stable SHA-256-derived 32-bit domain word as a fourth entropy element. Domains:
`pit_timing`, `compound`, `pit_loss`, `reliability` (reserved). The R5 pace
stream `rng_for_simulation` is untouched, so enabling R6 mechanics cannot shift
an R5 draw. Python `hash()` is not used. Per trajectory each domain is
pre-drawn once into a bounded pool (timing `field + remaining`, compound/loss
`remaining`) and consumed sequentially, so scalar and batch see identical
draws (R6-L, `test_pace_stream_construction_is_unchanged`).

## R6-M/N Scalar oracle and exact batch parity

The scalar oracle (`run_trajectory_scalar(..., pit_dynamics=True)`) evolved
first and is trace-observable (pit lap, compound before/after, pit/pit-count
counters, loss, `out_lap_tyre_age`, next target). Synthetic deterministic
distributions pin the expected laps (4 and 8 for a 4-lap target), one-shot
loss, compound sequence, and counters. Batch/scalar parity with pits is exact
for N = 10/25/100 (`test_scalar_batch_pit_exact_parity`), and chunk-size
(1/7/64/1024) and prefix invariance hold (`test_chunk_invariance_with_pits`,
`test_prefix_invariance_with_pits`).

## R6-O/P/Q Traffic / overtaking evidence decision — DEFERRED

R3 deliberately did **not** estimate a calibrated overtaking or following
penalty (position changes are confounded by pit cycles, retirements, SC and
timing artefacts), and no `traffic_penalty`/`passing_threshold` family or
defensible constant exists. Per R6-P/Q R6 does **not** invent one: no traffic
knob, no parameter, no threshold. Free-air deterministic ordering
`(laps DESC, race_time ASC, driver_id)` is retained. `TRAFFIC_DEFERRED_NOTE`
records the decision; a calibrated overtake model remains a later empirical
sub-phase.

## R6-R/S/T/U Reliability evidence decision — DEFERRED

R3 deliberately did **not** estimate a retirement hazard and no reliability
family exists in the artifact. Although a coarse progress-conditioned hazard is
derivable from the 390 measured DNFs, R6 chooses to DEFER it rather than add an
unvalidated additive hazard artifact and DNF aggregation semantics ahead of R7
validation. Consequently: reliability stays off; `reliability_enabled=True` is
rejected deterministically (never faked); DNF stays `None`; points stay `None`
(no modern points table is hardcoded, per R6-V). `RELIABILITY_DEFERRED_NOTE`
records the decision. Retirement is still never inferred from staleness.

## R6-Y Lapped-car semantics

Lapped drivers evolve from their own `(lap_number, race_time_s)`, may pit, and
are never forced onto the leader's lap; a pit does not force a relap. The
leader completing `scheduled_laps` still terminates the race and every driver
keeps their own completed laps (`test_lapped_driver_can_pit_coherently`). No SC
unlapping (no SC generation).

## R6-Z / R6-AD Pit-induced order and probability invariants

A pit changes cumulative timing and can therefore reorder cars; this is a
factual pit-time consequence, never labelled an overtake
(`test_pit_induced_reorder_is_a_factual_time_consequence`). All R5 probability
invariants remain true with pits enabled and no reliability: `Σ win == 1`,
`Σ podium == min(3, field)`, every position distribution sums to 1, `DNF is
None`, `valid + invalid == requested`, and no renormalization is applied.

## R6-AE Pit diagnostics

Descriptive only (`MonteCarloDiagnostics`, exposed via
`MonteCarloEngine.last_diagnostics` when `collect_diagnostics=True`; never part
of the scientific result identity): pit-count distribution, mean pits/driver,
fraction with zero pits, fraction with ≥2 pits, compound-transition counts,
sampled pit-loss summary, and sampled stint-target summary. They are
simulation diagnostics, not validated accuracy.

## R6-AF Historical plausibility smoke

On the real R3 artifact (2023-r01-R, `alonso` lap 2, N=100): mean stops/driver
≈ 3 (broad historical band 1–5), all transition targets dry, simulated
stint-target p50 inside a broad band around the R3 global median (~19 laps),
and sampled pit losses bounded by the circuit's observed support. This is a
plausibility smoke, not model validation; nothing is tuned on 2025.

## R6-AG R5 vs R6 descriptive comparison

Same representative states and seeds, R5-compatible mode vs pit-enabled mode:
pit loss and tyre reset shift cumulative times, spreading win/podium mass and
changing classifications. Example (2023-r01-R, `alonso` lap 2, N=1000, seed
20240101): R5 win mass concentrates on `max_verstappen`/`perez`; with pits the
faster strategy-and-loss interaction spreads and shifts probabilities. This is
descriptive only; no improvement is claimed.

## R6-AH/AI/AJ Performance

Benchmark protocol repeated for the mid fixture with the R6 mechanics enabled
(1k/10k/50k) plus early/late at 10k; mechanics, parameter identity, seed,
chunk size, N, fixture, wall time, memory, valid/invalid and pit diagnostics
are recorded, and JSON is written. (Measured numbers in the benchmark table
below; no optimization was introduced and parity was never sacrificed.)


### R6-AI Benchmark (single process, developer machine, warm)

`scripts/benchmark_phase6_monte_carlo.py --pit-dynamics`, chunk size 512,
seed 20240101, actual through-2024 artifact, R6 mechanics enabled
(`pit_dynamics`), diagnostics collected:

| fixture | leader laps | remaining | N | wall time | sims/s | valid/invalid | mean pits/driver | peak RSS |
|---|---|---|---|---|---|---|---|---|
| early | 2 | 55 | 1,000 | 2.379 s | 420 | 1000 / 0 | 3.06 | 189 MB |
| early | 2 | 55 | 10,000 | 23.786 s | 420 | 10000 / 0 | 3.06 | 260 MB |
| early | 2 | 55 | 50,000 | 119.357 s | 419 | 50000 / 0 | 3.06 | 497 MB |
| mid | 28 | 29 | 1,000 | 1.242 s | 805 | 1000 / 0 | 1.82 | 497 MB |
| mid | 28 | 29 | 10,000 | 12.510 s | 799 | 10000 / 0 | 1.82 | 497 MB |
| mid | 28 | 29 | 50,000 | 62.294 s | 803 | 50000 / 0 | 1.82 | 497 MB |
| late | 40 | 17 | 1,000 | 0.724 s | 1382 | 1000 / 0 | 1.07 | 497 MB |
| late | 40 | 17 | 10,000 | 7.224 s | 1384 | 10000 / 0 | 1.07 | 497 MB |
| late | 40 | 17 | 50,000 | 36.082 s | 1386 | 50000 / 0 | 1.08 | 497 MB |

R6 10k is 7.2–23.8 s vs the R5 baseline 1.9–6.2 s (~2–4× the work for many
more pit events), and every 10k case is well inside the broad Phase-6 60 s
target; 50k is 36–119 s. Memory (peak RSS) reaches ~497 MB on the largest
diagnostics-collecting run (dominated by the retained sampled pit-loss /
stint-target diagnostics lists at 50k; the scientific run without diagnostics
is lower). No optimization (Numba/multiprocessing) was introduced and parity
was never sacrificed; R6-AJ's "profile before optimizing" condition was not
triggered because the target is met.

## R6-AL Tests

`tests/test_v2_phase6_r6.py` (**58 passed**) covers: R5 config payload and real
result-identity preservation; config refinement; domain-separated RNG (stable
words, no `hash()`, unchanged pace stream construction); quantile grid /
CDF / conditional stint draw and integer clamping; initial-target
non-retroactivity; pit parameter selection and missing-family rejection; dry
filtering and null-compound global fallback; scalar pit oracle (laps, one-shot
loss, compound sequence, counters, tyre reset, out-lap age 1); final-lap pit
suppression; scalar/batch exact parity (10/25/100), chunk and prefix
invariance, seed determinism/sensitivity; lapped-car pitting; pit-induced
reorder; diagnostics consistency; R5 probability invariants with pits;
traffic and reliability deferral; no fabricated DNF/points; temporal and 2025
firewalls; residual-SD carry-forward; a performance smoke; import/source
firewalls and a fresh-process import; and real-data non-degeneracy,
scalar/batch parity, stint-target plausibility, and pit-loss support bounds.

## R6-AN Verification

- `tests/test_v2_phase6_r1..r6`: **523 passed** (~11.5 s; R6 alone 58).
- FAST frozen regression: `test_v2_phase4_r1.py` + `test_v2_phase4_r2.py` +
  `test_v2_phase5_freeze.py` + `test_v2_phase5_r1.py` + `test_v2_phase5_r2.py`:
  **202 passed**.
- The 19-minute R3 MEDIUM gate was not rerun (no frozen dependency changed).
- Not run: full-suite pytest, model inference, replay-cache generation.
  Frontend `DEFERRED — UNAFFECTED`.

## R6-AP Graphify

See the final R6 response for the measured `graphify update .` result (exit
code, nodes/edges/communities, and the import/cycle audit). Graphify output is
not staged.

## R6-AC Known limitations

- Pit timing is historically plausible behaviour, **not** strategy optimisation;
  the stint-length draw is the R3 observed distribution.
- R3 compound transitions are pooled across eras, so legacy 2018 compound names
  can be drawn with their observed (small) frequencies.
- Initial stint targets use the factual tyre age as the stint floor because
  `SimulationState` does not store the stint-start age; a factual age beyond
  the observed support falls back to `age+1` (documented).
- The effective pit loss is applied once at the pit (the kernel already charges
  clean pace for the in/out laps), a lap-boundary 2-lap approximation.
- Traffic/overtaking and reliability/DNF remain DEFERRED; free-air ordering is
  retained and `dnf_probability`/`expected_points` stay `None`.
- Diagnostics are descriptive and uncalibrated.
- The R5 residual-SD discrepancy (sampled ~1.70–1.74 s vs artifact ~1.51 s)
  and the independent-per-lap residual assumption carry forward unchanged
  (R6-AK); R7 owns the validation decision.

## R6 R7 readiness

The R6 pit model is opt-in, domain-separated, scalar/batch-exact, and
R5-compatible when disabled. R7 can: (1) run the historical validation protocol
with pits enabled and parameters estimated strictly before each evaluated
season, (2) assess whether the pit model plus the carried-forward residual-SD
discrepancy materially affects finishing-order calibration, (3) decide the
production default for `pit_dynamics_enabled`, and (4) revisit
traffic/overtaking and reliability only after a defensible estimation stage.


# Phase 6 — R7 Implementation Record

Status: **R7 COMPLETE AS A SCIENTIFIC VALIDATION GATE — SCIENTIFIC DECISION:
R7 BLOCKED — SIMULATION CONTRACT ISSUE.** Appended to the R0 plan and the
R1–R6 records; none is rewritten. R7 adds no product feature, no tuning, no
API, and no frontend; nothing is staged, committed, or tagged. Full details
and tables: `docs/PHASE6_VALIDATION_REPORT.md`.

## R7-A Files changed

New:
- `v2/simulation/validation.py` — evaluation-only validation utilities
  (protocol, selection, metrics, calibration, bootstrap, pit comparison,
  residual audit, variance-matched diagnostic parameter set). Imports only
  the stdlib + NumPy + Phase-6 contracts; no pandas, no prediction/model_lab,
  no replay, no API (AST-pinned).
- `scripts/validate_phase6_simulation.py` — explicit-protocol, explicit-seed
  driver; generates temporal artifacts (`through_season = season - 1`),
  selects states, runs baselines + R5/R6, writes deterministic artifacts
  under `data/v2/simulation/validation/` (untracked). Rejects 2018/2019/2025.
- `tests/test_v2_phase6_r7.py` — 39 focused tests.
- `docs/PHASE6_VALIDATION_REPORT.md` — the scientific report.

Modified:
- `v2/simulation/monte_carlo.py` — R7-BUG-1 only: `_ChunkEvolution` seeds
  `pit_count` from the factual start count (scalar parity; scientific result
  identity unchanged).
- `scripts/benchmark_phase6_monte_carlo.py` — additive `--no-diagnostics`
  and `diagnostics_enabled` reporting for the R7-AC memory diagnostic.
- `v2/simulation/__init__.py` — re-export the R7 validation surface.
- `tests/test_v2_phase6_r6.py` — unchanged science; no change required.
- `docs/PHASE6_MONTE_CARLO_PLAN.md` — this record.

No frozen Phase-1–5 source was touched. No R1–R5 contract changed. No new
parameter artifact family was invented (R7 consumes R3 read-only).

## R7-B Protocol

`r7-validation-v1`; identity
`d071b09b40bc6f79853f8d90a0744b73aec887f0efa0e863820bc6c53028ab20`.
Evaluation seasons 2020–2024 (2018/2019 excluded: ≤1 prior estimation
season; 2025 never eligible), cutoff `through = season - 1`, stages
25/50/75 %, nearest-supported leader-lap checkpoint with frozen tie-break
and radius `max(3, round(0.10·scheduled_laps))`, broad N=1000, calibration
N=10000, seed 20240101, log eps 1e-6, predeclared bins, baselines
CURRENT_ORDER/CURRENT_LEADER/GRID_ORDER/R4_DETERMINISTIC/R5_NO_PIT,
race-level bootstrap 1000/seed 42, exclude-unsupported policy.

## R7-C/D Temporal artifacts

Expanding chronology 2019→2023 cutoffs (see report §3). The through-2024
artifact is not overwritten; each temporal artifact was rebuilt and
hash-verified during the run.

## R7-E/F/G Coverage

39 systematically selected races → 117 stage candidates → 42 supported
states across 23 races (EARLY 23 / MID 11 / LATE 8). 75 exclusions reported
with reasons, dominated by `non_contemporaneous_roster_member` (52).

## R7-H/I/J-K-L-M/N/O Historical truth, baselines, metrics

Truth is derived from canonical results per state roster and never enters a
simulation input (adversarial test). Baselines are factual; the Phase-3
winner model is not used. Winner log loss/Brier, top-k, expected-finish MAE,
normalized RPS, position NLL, calibration bins/ECE, and MC standard error are
computed; no opaque composite score.

## R7-P..R Stage/season/perf results

On contemporaneous states R6 race-macro winner log loss 1.224 (R5 2.225,
CURRENT_LEADER 4.276, R4 4.605, GRID 7.237), Brier 0.0267, MAE 2.445, RPS
0.0928, Spearman 0.798, top-1 0.643, top-3 0.881; metrics improve
monotonically EARLY→MID→LATE. Honest nuance: per state R6 beats the
current-leader winner baseline only 13/42; its macro advantage comes from
eliminating catastrophic misses (no winner LL >10 vs R5's four).

## R7-Q/R Pit behaviour

Simulated total stops per driver are distributionally plausible but
systematically high by ≈0.3–0.4 (worst +1.06). The R6 `~3.06` early finding
is reproduced (3.061) against factual 2.60: an unconditional observed
stint-length distribution is sampled until the race ends, so it does not
plan to the finish. Diagnosis: modelling limitation; not retuned.

## R7-S/T Residual audit and sensitivity

Sampled std matches the grid's piecewise-linear std (ratio ≈1.00); the
artifact-std gap (6–22 %) is endpoint/tail weighting in the quantile grid
(upper endpoint gaps 19–57 s). A variance-matched diagnostic changes headline
metrics by ≈0.02–0.04 and is immaterial. Production sampler retained.

## R7-U/V/W R5 vs R6, deterministic, bootstrap

R6 improves RPS and avoids catastrophic winner misses; R5 is marginally
better on MAE and per-state winner LL. R4 deterministic is clearly weaker.
Race-level bootstrap gives winner LL 1.246 [0.822, 1.771].

## R7-X/Y Failure and limitation attribution

Worst winner misses are first-time-winner/comeback races (2024 Hungary,
2022 Hungary, 2024 Baku); largest MAE at early-race 2020 checkpoints.
Labelled hypotheses; the only causally established failure is the
non-contemporaneous-state defect below.

## R7-Z Defects

- **R7-BUG-1** batch pit diagnostics seeded `pit_count` from 0; fixed to the
  factual count (scalar parity, result identity unchanged).
- **R7-BUG-2** non-contemporaneous (stale/retired) drivers are accepted by
  the runtime and evolved as ACTIVE, producing nonsense winners. No runtime
  change; R7 excluded them via a predeclared contemporaneity criterion. This
  is the blocker: production/live snapshots routinely contain retired cars
  and the engine gives no rejection signal. R8 must reject them (or model
  retirement).

## R7-AB/AC Performance and memory

10k runs 7.3–24.6 s (target ≤60 s), all trajectories valid; production
memory (no diagnostics retention) at 10k ≈170 MB vs 204.5 MB with
diagnostics; 430 MB is the diagnostics-retaining whole-benchmark peak.

## R7-AD/AE/AF/AG/AH Artifacts, script, tests, adversarial, 2025

Deterministic artifacts under `data/v2/simulation/validation/`
(`r7_protocol_v1.json`, `r7_validation.json`, `r7_validation_raw_v1.json`,
`r7_benchmark.json`, `r7_memory.json`). 39 R7 tests cover protocol identity,
selection/radius, contemporaneity, truth separation, metrics, calibration,
MC uncertainty, bootstrap, pit comparison, residual audit,
variance-matched diagnostic, aggregation, AST/import firewalls, the 2025
rejection path, the deterministic dry-run artifact, R7-BUG-1 parity, and the
temporal adversarial suite. 2025 is pinned structurally.

## R7-AI Verification

`tests/test_v2_phase6_r1..r7`: **562 passed** (R7 39). Frozen FAST
regression (`test_v2_phase4_freeze`, `phase4_r1/r2`,
`test_v2_phase5_freeze`, `phase5_r1/r2`): **212 passed, 1 pre-existing
failure** — `test_v2_phase4_freeze.py::test_frozen_module_hashes_match`
mismatches `api/main.py` only, an unrelated working-tree change present
before R7 (R7 touched no API file). The R3 MEDIUM gate was not rerun (no
frozen R3 dependency changed). Frontend DEFERRED — UNAFFECTED.

## R7-AJ Documentation / R7-AK Graphify

See `docs/PHASE6_VALIDATION_REPORT.md`. `graphify update .`: 8461 nodes,
20988 edges, 292 communities; no `v2/simulation/* → prediction/model_lab/
replay/api/features` edge; nothing imports `v2/simulation/validation.py`
except its script and test; no new god node. Graphify output not staged.

## R7 Definition of Done

Complete except the contract-safety gate: the frozen runtime still accepts
non-contemporaneous states, so the scientific decision is **R7 BLOCKED —
SIMULATION CONTRACT ISSUE**. Nothing staged, committed, or tagged.

---

# Phase 6 — R7.1 Implementation Record (Contemporaneous Active-Roster Safety)

Status: **R7.1 COMPLETE — R7 CLOSED, READY FOR R8.** Appended to the R0 plan
and the R1–R7 records; none is rewritten. R7.1 introduces the smallest
temporally safe simulation-start eligibility contract demanded by the
R7-BUG-2 blocker. Nothing is staged, committed, or tagged.

## R7.1-A Files changed

Modified:
- `v2/simulation/engine.py` — runtime eligibility surface:
  `REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER` (added to
  `ENGINE_UNSUPPORTED_REASONS`), `CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES =
  3.0`, `contemporaneous_roster_offenders()`, and a contemporaneity pass in
  `_validate_start_state(initial_state, selection)`. `_validate_start_state`
  now takes the `PaceParameterSelection` so the bound uses the selected
  circuit|era expected lap time. Constants exported via `__all__`.
- `v2/simulation/monte_carlo.py` — call site only: `_prepare` passes the
  selection to `_validate_start_state`.
- `v2/simulation/validation.py` — `R7_MAX_OBSERVATION_LAP_TIMES` aliases
  `engine.CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES` (single authority);
  otherwise unchanged (evaluation-only).
- `scripts/validate_phase6_simulation.py` — `support_status` calls
  `_validate_start_state(state, selection)` and surfaces the runtime reason;
  the evaluator no longer applies its own `is_contemporaneous` criterion.
- `tests/test_v2_phase6_r4.py`, `r5`, `r6`, `r7` — real fixtures that used
  the R7-BUG-2-unsafe `2023-r01-R` lap-28/lap-40 state (stale retired
  `piastri`) moved to contemporaneous real states (`2022-r01-R` perez@30 /
  russell@38; `2023-r07-R` final frame). R6's mid/late
  `R5_BASELINE_IDENTITIES` pins were recomputed for the new fixtures (early
  unchanged); no scientific mechanics/expectations changed.
- `docs/PHASE6_VALIDATION_REPORT.md` — addendum (original blocked result
  preserved); this record.

New:
- `tests/test_v2_phase6_r71.py` — 32 focused R7.1 tests.
- `docs/PHASE6_MONTE_CARLO_PLAN.md` — this record.

`v2/simulation/adapter.py` is **unchanged** (sha `b42f1f77…`); `RaceState`
semantics are untouched. No frozen Phase-1–5 source changed. No parameter
artifact changed. No pace/residual/pit/seed/count/race-set changed.

## R7.1-B Defect, reproduction, and audit

R7-BUG-2: the kernel advances every driver from its own factual
`(lap_number, race_time_s)`, so a driver whose latest observation is far older
than T advances from a stale clock and can beat the field. Reproduced
pre-fix at `2020-r07-R` MID (`giovinazzi` win p≈0.904 vs actual `hamilton`,
winner LL 13.82; `sainz`, `russell` also stale). All 99 raw states audited
offline; "has a later row"/final status used for diagnosis only. Over 1 836
contemporaneous driver-observations the observation age (in expected lap
times) is p50 0.62 / p90 0.95 / p95 1.11 / p99 1.77; the 144
non-contemporaneous drivers have median 21.4, max 94.8. 64/99 raw frames
carried a driver older than 3 lap times. The 16 "later-row" drivers above the
bound are all unsafe-coordinate cases (terminal-status Accidents/Retirements,
and the 2020-r09 Mugello red-flag clock discontinuity which the raw artifact
shows was pathological). Documented residual ambiguity: 6 recently-retired
drivers within 3 lap times are not detected (max residual pre-fix LL 1.90).

## R7.1-C Rule, layer, and semantics

Dimensionless race-relative bound `observation_age_s <= 3.0 × pace_base_s`
(circuit|era), i.e. a conservative margin above the contemporaneous p99. The
rule is eligibility, never retirement; it never reads final status, future
rows, or any post-T signal. Enforcement is in engine start-state validation,
before any stochastic draw. The whole state is rejected with the stable reason
`non_contemporaneous_roster_member`; no driver is dropped, reclassified, or
advanced. `stale != retired` is preserved (the adapter is unchanged and still
emits `ACTIVE`).

## R7.1-D Evidence, parity, performance, and protocol rerun

- **Parity (eligibility-only).** 15 pre-fix raw accepted states across 5
  races (EARLY/MID/LATE) reproduce their recorded `state_identity` and
  `r6_result_identity` byte-for-byte post-fix; the R7.1 suite pins 6 and adds
  early/mid/late real fixtures. Adversarial future/final-status poisoning
  leaves accepted identity and rejected reason identical (**no leakage was
  detected under the implemented adversarial test suite** — not a proof).
- **Performance.** `contemporaneous_roster_offenders` on a 20-driver state:
  mean **0.697 µs**, p50 **0.667 µs**, p95 **0.75 µs** — negligible against a
  trial (N=100 ≈ 38 ms wall).
- **Protocol rerun (unchanged).** `scripts/validate_phase6_simulation.py`
  rerun with the original predeclared protocol: **42 accepted states**, 75
  exclusions (52 `non_contemporaneous_roster_member`), runtime 679.8 s.
  Byte-identical to the preserved manual clean run
  (`r7_validation_clean_v1.json`): all 42 state and result identities equal;
  winner LL 1.2237, Brier 0.02669, MAE 2.4452, RPS 0.09280, ECE 0.01899; vs
  raw pre-fix winner LL 4.491. This is exclusion of unsupported inputs, not an
  accuracy improvement. The runtime now itself determines every exclusion.
- Artifacts (untracked): `r7_validation_raw_v1.json` (preserved pre-fix),
  `r7_validation_clean_v1.json` (preserved manual clean),
  `r7_validation.json` (post-fix runtime).

## R7.1-E Verification and firewalls

- `tests/test_v2_phase6_r1..r7` + `r71`: **594 passed** (R7.1 32).
- FAST frozen regression (`test_v2_phase4_freeze`, `phase4_r1/r2`,
  `test_v2_phase5_freeze`, `phase5_r1/r2`): **212 passed, 1 pre-existing
  failure** — `test_v2_phase4_freeze.py::test_frozen_module_hashes_match`
  mismatches `api/main.py` only (`2840271a…` vs recorded), the unrelated
  Phase-5-authorized drift present before R7.1; no API/frozen file was touched.
- R7.1 tests cover: the constant/derivation margin, boundary and null-age
  behaviour, runtime rejection before any draw, stale-not-retired /
  no-driver-dropped, valid lapped and temporarily-stale drivers, the
  2020-r07-R regression and raw-artifact blocker pin, evaluator-runtime
  alignment, accepted-state pre-fix identity parity, early/mid/late real
  fixtures, the future/final-status adversarial suite, runtime source/AST
  firewalls (no evaluation import, no data stack, no final-status/future
  tokens), eligibility performance, and the 2025 firewall.
- Not run: full-suite pytest (per scope), R3 MEDIUM gate (no frozen R3
  dependency changed), training/inference, replay-cache generation. Frontend
  `DEFERRED — UNAFFECTED`.

## R7.1-F Graphify

See the final R7.1 response for the measured `graphify update .` result (exit
code, nodes/edges/communities, and the import/cycle audit). Graphify output is
not staged.

## R7.1 Decision

Unsafe states are rejected deterministically, valid lapped/active states are
preserved, the temporal firewall holds, and accepted-state metrics are
non-pathological and byte-identical to the clean run. **R7 CLOSED — READY FOR
R8.** Nothing staged, committed, or tagged.
