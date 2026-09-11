# F1 Intelligence v2 --- Phase 2 Temporal Feature Engineering

> **Purpose:** Build a leakage-safe, reproducible, testable
> feature-engineering system on top of the completed Historical Data
> Platform.
>
> **Execution:** OpenCode Desktop + Meta Spark 1.3 Contributor
>
> **Prerequisites:** `V2_FOUNDATION_REFACTOR.md` and
> `V2_PHASE_1_DATA_PLATFORM.md` are complete and their verification
> gates pass. Phase 1 is COMPLETE and FROZEN at D12 (see
> `docs/PHASE1_EXIT_REPORT.md`).
>
> **Frozen Phase-1 input (authoritative, see `data/README.md` §10):**
> primary state `driver_lap_state_d9`, grain
> `(race_id, driver_id, lap_number)`, 189,420 accepted rows, temporal
> boundary `state_time_s` = LAP_END; labels `race_driver_labels`,
> grain `(race_id, driver_id)`, 3,458 rows, physically/logically
> separate from predictive state. All availability semantics follow
> `v2/contracts.py` / `v2/d6schema.py` / `v2/d7schema.py` /
> `v2/d9schema.py`. ADR-0001 (telemetry DEFERRED) is authoritative.
> No binary DNF target exists.
>
> **Primary rule:** A feature for Driver D at Race R, Lap L may use only
> information legitimately available at or before that race state's
> `state_time_s` (LAP_END). No lap L+1 or later information.
>
> **Cross-driver synchronization invariant (foundational):** a same-lap
> number cross-driver join is NOT temporally sufficient. For a target
> state with `state_time_s = T`, any rival-derived information must use
> that rival's latest observable state with `state_time_s <= T`. Never
> use a rival observation after T merely because it shares the lap
> number. This applies to gaps, field-relative pace, teammate
> comparisons, traffic, packs, closing rates, field statistics,
> position-relative calculations, and any cross-driver feature. F1 must
> formalize and test this rule before cross-driver features are built.

------------------------------------------------------------------------

# 1. Mission

The university project used a relatively small feature set at fixed Lap
5/10/15/20/25 checkpoints. F1 Intelligence v2 needs a reusable
**Temporal Feature Engine** capable of reconstructing meaningful race
intelligence at arbitrary supported laps.

The goal is not to maximize column count. The goal is:

``` text
CANONICAL HISTORICAL DATA
          |
          v
TEMPORAL FEATURE CONTRACT
          |
          v
     FEATURE ENGINE
          |
    pace / tyres / gaps / traffic / weather / priors
          |
          v
   FEATURE REGISTRY
          |
          v
 LEAKAGE VALIDATION
          |
          v
 ML-READY SNAPSHOTS
```

The same feature definitions should eventually support historical
training, runtime prediction, RaceState, replay, simulation and strategy
without duplicated logic.

------------------------------------------------------------------------

# 2. Hard Scope

This phase MAY:

-   define temporal feature contracts
-   create a feature registry
-   build deterministic race-state features
-   create representative-lap filtering
-   create rolling and relative pace features
-   create tyre/stint/pit features
-   create gap/traffic/closing-rate features
-   create teammate/field context
-   create weather/race-control features
-   create past-only driver/constructor/circuit priors (no
    reliability/DNF-rate priors — DEFERRED, see §22a)
-   create factual grid-position context from existing D5 results
-   run a lightweight telemetry ADR revisit-check (F12; default expected
    result: ADR-0001 DEFERRED holds; no materialization, no telemetry
    features without separate authorization)
-   define future labels separately (explicit race×driver join
    contract; no new targets, no DNF target)
-   implement leakage tests alongside each family (not only at the end)
-   generate candidate feature datasets
-   create ablation family definitions/configuration/fixtures only
    (NO ablation execution, NO model comparison, NO predictive metrics
    — Phase 3 owns execution)

This phase MUST NOT:

-   replace the production winner model
-   retrain production artifacts merely to show new metrics
-   select a new production model
-   implement calibration
-   implement Monte Carlo
-   implement strategy recommendations
-   implement Race Engineer AI
-   implement replay UI
-   implement What-If simulation
-   create opaque fake intelligence scores
-   use future information (including same-lap rival observations with
    `state_time_s` after the target clock)
-   reimplement factual state already supplied by D9 (race progress,
    track-state flags, completed pit counts, laps-since-pit, stint lap
    — reference/pass through instead)
-   build telemetry features or materialize telemetry (ADR-0001
    DEFERRED; F12 revisit-check only)
-   define or use a DNF/reliability event or target (DEFERRED — no
    DNF-rate priors or labels in Phase 2)
-   ingest qualifying sessions or assume qualifying/Q1/Q2/Q3 fields
    exist (only factual `grid_position` from D5 results is available)
-   build projected pit-loss / rejoin-position / catch-time projections
    as ML features (DEFERRED to later Strategy/Simulation work)
-   claim predictive improvement before legitimate chronological
    evaluation

------------------------------------------------------------------------

# 3. Temporal Contract

For:

``` text
features(race_id=R, driver_id=D, lap=L)
```

the engine may access only information known at or before the defined
state boundary for Lap L.

Define exactly what "Lap L state" means before feature implementation.
The frozen definition is:

> State at Lap L represents information available after the relevant
> driver has completed Lap L, i.e. at `state_time_s` = LAP_END (the
> frozen D6/D7/D9 clock). Only source events with event time at or
> before that driver's `state_time_s` are eligible. Features for state
> (race, driver, lap N) may use information available by the end of lap
> N and must not use information from lap N+1 or later.

No feature family may reinterpret the temporal boundary independently.

Race-wide synchronization rule (normative): drivers complete the same
lap number at different session times. For target state clock T, every
cross-driver input (gaps, relative pace, teammate, traffic, packs,
closing rates, field statistics, position-relative quantities) must
resolve each rival/field member to its latest observable state with
`state_time_s <= T`. A join on equal lap number alone is forbidden.
F1 formalizes this rule, its staleness/provenance handling, and its
tests before any cross-driver family is built. Representative
edge cases for design/testing: normal dry race, leader change, lapped
cars, Safety Car, VSC, red flag, missing timing, shortened race,
Belgium 2021, Japan 2022, Monaco/time-limited races.

------------------------------------------------------------------------

# 4. Labels Are Not Features

Keep state and future outcomes structurally separate.

State examples:

``` text
current_position
gap_to_leader
recent_pace_5
compound
tyre_age
pit_stop_count_so_far
```

Future labels:

``` text
winner
podium
points_finish
final_position
dnf
position_gain_to_finish
```

The frozen label layer is `race_driver_labels` at race×driver grain
(3,458 rows). Any training/evaluation dataset construction must join
labels explicitly to LAP_END feature states; labels are never part of
predictive state. `dnf` above is a placeholder name only: Phase 1
defined NO binary DNF/reliability target and Phase 2 must NOT silently
introduce one (see §22a). F13 defines the explicit join contract; no
new targets are created in Phase 2.

Never use:

``` python
features = all_numeric_columns_except_some_labels
```

Use explicit feature schemas.

------------------------------------------------------------------------

# 5. Feature Registry

Create a central machine-readable registry. The registry is an early
Phase-2 primitive (F2): it is metadata + validation, not a
feature store. No Feast, no database, no service. Each candidate
feature should record:

``` text
name
family
dtype
unit
description
source_fields/entities
formula/algorithm reference
temporal_availability rule
cross-driver synchronization requirement
minimum_history
missing_value_policy
predictive_eligibility
version (per feature)
status
```

`source` as a free-text string alone is insufficient — exact source
fields/entities must be listed so contracts are testable.
Identifiers/lineage fields are registered with
`predictive_eligibility = false`.

Suggested statuses:

``` text
candidate
validated
experimental
deprecated
```

Example:

``` text
name: pace_vs_ahead_5
family: pace
unit: seconds/lap
description: Difference between target driver's recent representative pace and the car ahead.
temporal_requirement: completed eligible laps <= current state only
missing: null if a valid comparison cannot be constructed
```

------------------------------------------------------------------------

# 6. Suggested Module Structure

Adapt to the actual refactored repository rather than blindly creating
empty modules.

``` text
ml/features/
├── registry.py
├── engine.py
├── schemas.py
├── temporal.py
├── representative_laps.py
├── race_state.py
├── gaps.py
├── pace.py
├── tyres.py
├── pits.py
├── traffic.py
├── teammate.py
├── race_control.py
├── weather.py
├── historical.py
├── circuit.py
├── labels.py          (label-join contract only; no new targets)
├── interactions.py
└── telemetry.py       (NOT created in Phase 2 — ADR-0001 DEFERRED;
                        F12 revisit-check only)
```

The requirements are clear feature-family ownership, one temporal
contract and shared batch/runtime definitions.

Before feature families (F3), establish reusable, well-tested
primitive temporal operators such as: prior rows for a driver
before/equal T; rolling past window; latest observation <= T;
synchronized rival state <= T; synchronized field snapshot; past
races before an event; within-stint past observations;
validity/min-history helpers. Exact API names are not frozen by this
plan. Do not overengineer a general-purpose time-series framework —
the smallest operator set the families actually share (see also
§33 parity architecture).

------------------------------------------------------------------------

# 7. F0 --- Identifiers

Identifiers are required for joins/debugging but must not automatically
become model features.

``` text
race_id
season
round
driver_id
driver_code
constructor_id
lap_number
```

Explicitly classify identifiers separately from model features.

------------------------------------------------------------------------

# 8. F1 --- Race Progress & Position

Status: MODIFY. Use D9 factual state by reference where available
(`race_progress_frac`, `race_leader_laps_at_state`, `track_state`
flags, pit/stint derivations) — Phase 2 owns NEW predictive
features, not duplication of Phase-1 state. F4 registers the
passthrough layer explicitly.

High-priority candidates:

``` text
lap_number
total_laps_known             (= D5 total_laps_scheduled, PRE_RACE, by reference)
remaining_laps_estimate      (= scheduled − leader laps at clock; never eventual distance)
race_progress_pct            (= D9 race_progress_frac by reference; define any variant explicitly)

current_position             (= D6 position at LAP_END, by reference)
grid_position                (factual D5 results PRE_RACE join; see §24 — qualifying deferred)
positions_from_grid          (grid − current; null-propagating)

drivers_running
cars_on_lead_lap
```

Be careful with shortened/red-flagged races. Do not use eventual
completed race distance at an earlier state if that fact was not yet
known: `remaining_*` uses the PRE_RACE scheduled distance minus the
past-only leader-lap count at the clock. `drivers_running` /
`cars_on_lead_lap` require an explicit past-only derivation rule
(retirement is only known when a driver's laps stop; final
classification is POST_RACE and must not enter). PARTIAL races
(Belgium 2021, Japan 2022) and time-limited races remain first-class:
no silent exclusion; any model-stage filtering is explicit Phase-3
evaluation policy.

------------------------------------------------------------------------

# 9. F2 --- Gaps

Status: MODIFY substantially. Legacy `gap_to_leader` is NOT
authoritative (D10: session-minimum reference + 300 s clipping
defects) and no frozen gap column exists. Rebuild from V2 temporal
state under the §3 synchronization rule.

Reject the assumption that one scalar seconds gap is universally
valid. The gap engine (F6) must produce an explicit factual gap
representation capable of expressing: whether a seconds gap is valid;
the seconds gap when meaningful; lap difference / lapped-car state;
missing/unknown state; and synchronization provenance where useful.
This plan freezes the principles, not the exact final column schema —
F1/F2 finalize the precise contract after inspecting representative
real races:

-   no legacy session-minimum implementation
-   no arbitrary 300-second clipping (investigate outliers, never censor)
-   no same-lap future rival observation (rival `state_time_s <= T` only)
-   no fabricated seconds gap for lapped/invalid cases
-   explicit validity/null semantics
-   factual state only (no projections)

Representative edge cases required during design/testing: normal dry
race, leader change, lapped cars, Safety Car, VSC, red flag, missing
timing, shortened race, Belgium 2021, Japan 2022, Monaco/time-limited
race.

Candidate directions (final names/schemas fixed in F1/F2):

``` text
gap_to_leader                (seconds, nullable, with validity companion)
gap_to_car_ahead
gap_to_car_behind

gap_to_leader_change_3
gap_to_leader_change_5

gap_to_ahead_change_3
gap_to_ahead_change_5

gap_from_behind_change_3
gap_from_behind_change_5

gap_to_leader_per_remaining_lap   (remaining = scheduled − leader laps; see §28 constraints)
```

Define sign conventions once and handle lapped cars/caution periods
explicitly. Change features require eligibility-matched endpoints.
Per-remaining-lap normalizations must use scheduled remaining, never
eventual distance.

------------------------------------------------------------------------

# 10. F3 --- Recent Pace

Status: MODIFY. Rolling windows (3/5/10 candidates) are trailing over
eligible laps only. Every resulting feature must define: eligible
laps, minimum observations, missingness, pit-lap handling,
SC/VSC/yellow/red handling, wet/dry transition handling, and missing
lap-time handling. No centered windows. No future observations.

Candidate trailing features:

``` text
pace_last_1

pace_mean_3
pace_mean_5
pace_mean_10

pace_median_3
pace_median_5

pace_std_3
pace_std_5

pace_trend_3
pace_trend_5
```

All windows must be trailing/past-only. Never use centered rolling
windows. Each windowed stat ships with a sample-count companion
(e.g. `pace_n_3`) and a minimum-observation rule (null when
insufficient — early laps stay null, never backfilled from future).
Pit laps, caution laps, wet/dry transition laps, and null/invalid lap
times are ineligible for representative windows (see §11); raw windows
must document their inclusion policy.

------------------------------------------------------------------------

# 11. Representative Pace Laps

Status: MODIFY. Remove unsupported "clean-air pace" terminology —
frozen data cannot establish clean air (no following-distance channel,
no validated DRS-zone signal, position data not canonical). Use
terminology such as `eligible pace` / `representative eligible pace`
only where the eligibility rule is explicit.

Create a deterministic:

``` text
is_representative_pace_lap   (eligibility mask from frozen fields only)
```

Investigate exclusion/flag rules for:

-   pit-in laps
-   pit-out laps
-   Safety Car
-   VSC
-   red-flag/restart effects
-   first-lap anomalies
-   invalid/deleted timing
-   demonstrable source timing errors

Do not automatically remove traffic-affected laps merely because they
are slow. Traffic is part of race performance. Slowness alone never
excludes; only the explicit mask above does.

Representative eligible pace candidates (each with a sample-count
companion and minimum-observation/null rule):

``` text
representative_pace_mean_3
representative_pace_mean_5
representative_pace_median_3
representative_pace_median_5
representative_pace_std_5
representative_lap_count_3
representative_lap_count_5
```

Expose sample counts where useful.

------------------------------------------------------------------------

# 12. F4 --- Relative Pace

Status: MODIFY. Requires the §3 race-wide synchronization rule: each
rival/field reference resolves to its latest state with
`state_time_s <= T`. Use matched/past-only observations (both sides
eligible windows at the clock).

Highest-priority candidates:

``` text
pace_vs_leader_3
pace_vs_leader_5

pace_vs_ahead_3
pace_vs_ahead_5

pace_vs_behind_3
pace_vs_behind_5

pace_vs_field_median_3
pace_vs_field_median_5

pace_rank_3
pace_rank_5

pace_vs_teammate_3
pace_vs_teammate_5
```

Document the sign convention globally.

------------------------------------------------------------------------

# 13. F5 --- Teammate Context

Status: MODIFY. Requires synchronized state (§3). Define behavior for:
missing teammate, substitute driver, retired teammate, and teammate
without current valid timing (all → null, never fabricated values).
Identity keys on permanent `driver_id` / season-scoped
`constructor_id`, never driver number or display strings.

Candidates:

``` text
teammate_position
gap_to_teammate
position_delta_to_teammate

pace_vs_teammate_3
pace_vs_teammate_5

tyre_age_delta_to_teammate
compound_vs_teammate
pit_stop_delta_to_teammate
```

Handle retired/missing teammates and driver substitutions without
fabricated values. Categorical tyre comparisons (`compound_vs_teammate`)
must not depend on arbitrary string ordering and need an explicit
encoding rule (model-stage categorical treatment), or they are dropped.
No arbitrary ordinal encoding such as SOFT > MEDIUM > HARD.

------------------------------------------------------------------------

# 14. F6 --- Tyres

Status: KEEP. Preserve factual compound/age/stint/fresh information
from frozen state (D6/D7/D9 by reference where available).

Core candidates:

``` text
compound
tyre_age
stint_number
stint_lap
fresh_tyre
laps_since_pit
```

Relative candidates:

``` text
tyre_age_vs_leader
tyre_age_vs_ahead
tyre_age_vs_behind
tyre_age_vs_field_median
tyre_age_vs_teammate
```

Do not encode SOFT/MEDIUM/HARD as a universal numeric strength ordering.

------------------------------------------------------------------------

# 15. F7 --- Stint Pace / Degradation Proxies

Status: MODIFY. Any such feature must be named and described as an
estimate or proxy — prefer `stint_pace_trend` over claims of physical
tyre degradation. Requirements: within-stint past-only observations,
minimum n (null when insufficient), the §11 eligibility mask, and an
explicit confounder warning (fuel burn, traffic, track evolution,
weather drift, warm-up, caution periods). No future stint information
(end lap, next compound, next stop) may enter.

Candidates (proxies, not physical measurements):

``` text
stint_pace_slope
stint_representative_lap_count
pace_loss_recent_5

stint_pace_trend_vs_teammate
stint_pace_trend_vs_same_compound_field
```

Do not call a raw lap-time slope "tyre degradation" without accounting
for confounders such as fuel burn, traffic, track evolution, weather,
warm-up and caution periods.

Use conservative names such as `stint_pace_trend` until validated.

------------------------------------------------------------------------

# 16. F8 --- Pit State

Status: MODIFY. Keep factual past/current pit state. Respect
asymmetric pit boundaries (in-only/out-only preserved in Phase 1):
never manufacture missing pit-in/pit-out events, and never count an
asymmetric stop as completed. D9 completed-stop counts and
laps-since derivations are referenced, not reimplemented.

Core candidates (factual):

``` text
pit_stop_count_so_far
laps_since_last_pit
last_pit_lap
current_stint
current_compound
```

Future stops must never influence current state.

Higher-complexity candidates — DEFERRED to later Strategy/Simulation
work unless a future stage establishes a purely factual feature.
Projected pit/rejoin position needs pit-loss and future-field
assumptions and must not enter the ML feature matrix as a
point-estimate feature:

``` text
estimated_pit_loss                  (DEFERRED)
cars_inside_pit_loss_window         (DEFERRED)
estimated_rejoin_position           (DEFERRED)
traffic_after_projected_pit         (DEFERRED)
```

Only implement these if they can be defined from current/past
information. Do not implement strategy recommendations here. Phase 2
records the factual inputs (gaps behind, track state, tyre age) —
not the projection.

------------------------------------------------------------------------

# 17. F9 --- Traffic

Status: MODIFY. Only factual traffic/pack context supported by the
F6 gap/synchronization engine (§3, §9). Gap-threshold counts resolve
rivals at the target clock; missing/unknown gaps propagate as null
with validity companions, never as zero.

Candidates:

``` text
cars_within_1s_ahead
cars_within_2s_ahead
cars_within_5s_ahead

cars_within_1s_behind
cars_within_2s_behind
cars_within_5s_behind

traffic_density_ahead
traffic_density_behind
```

If DRS-related context is used, do not equate a timing gap alone with
confirmed DRS eligibility unless the source/state supports it. Do not
infer DRS eligibility in Phase 2. Do not claim physical following
distance without data supporting it.

------------------------------------------------------------------------

# 18. F10 --- Closing Rates

Status: MODIFY. Past-observed rate features may be retained with
denominator/time guards. Projected catch-time is DEFERRED (needs
future-field assumptions — Strategy-stage quantity).

Candidates (observed rates retained; projections deferred):

``` text
closing_rate_to_ahead_3
closing_rate_to_ahead_5

closing_rate_from_behind_3
closing_rate_from_behind_5

estimated_laps_to_catch_ahead     (DEFERRED — projected catch time)
estimated_laps_until_caught       (DEFERRED — projected catch time)
```

Protect against near-zero rates, diverging cars, pit laps, cautions and
noisy timing. Use null instead of absurd/infinite values.

------------------------------------------------------------------------

# 19. No Arbitrary Scores

Do not create:

``` text
attack_score = 84
pressure_score = 92
strategy_score = 77
```

unless a score later has a mathematically defined and validated
interpretation.

Prefer transparent underlying variables.

------------------------------------------------------------------------

# 20. F11 --- Race Control

Status: MODIFY. D9 structural track-state flags (`track_state`,
`flag_yellow`/`flag_safety_car`/`flag_red`/`flag_vsc`) are passthrough
by reference — do not re-derive them. New RC-derived features may use
only timestamped messages observable by T (`observed_at_s <= T`). The
69 untimestamped 2018-r02 messages must never be retrospectively placed
into predictive state. No NLP/text embeddings, no LLM-derived
race-state features in Phase 2. Race-control message text and
TrackStatus timing-state are separate information sources: do not treat
RC text as an authoritative track-state state machine unless explicitly
justified with tests.

Candidates (D9 passthrough + new backward-only derivations):

``` text
track_status
safety_car_active
vsc_active
safety_car_periods_so_far
vsc_periods_so_far
laps_since_caution
```

Only events known by the current state are eligible.

Potential field-state features:

``` text
field_spread
top_3_spread
top_5_spread
front_pack_spread
```

Define precisely.

------------------------------------------------------------------------

# 21. F12 --- Weather

Status: MODIFY. Current D7 as-of weather is passthrough by reference.
D7 already performs strict backward weather joins
(`observed_at_s <= T`, empty side → null, no future-nearest). Backward
weather deltas/trends may be added only if they use observations
<= T, define a staleness policy (null honestly when stale — max
measured staleness 477 s), and preserve nulls. No future-nearest
weather. No forecast features unless a future product stage explicitly
introduces them.

Where Phase 1 coverage supports it (passthrough):

``` text
air_temperature
track_temperature
humidity
pressure
rainfall
wind_speed
wind_direction
```

Potential trailing changes:

``` text
track_temperature_change_recent
air_temperature_change_recent
rain_started_recently
```

Use backward/as-of joins. Never select a future observation merely
because it is temporally closer.

Potential interactions to evaluate:

``` text
compound × rainfall_state
compound × track_temperature
tyre_age × track_temperature
```

------------------------------------------------------------------------

# 22. F13 --- Driver Historical Priors

Status: MODIFY. Strictly past-only: for a race in season/year T, no
information from the current race outcome or future races may
contribute. Require: permanent `driver_id` (never number/display
strings), minimum history, smoothing toward the field prior,
cold-start policy (rookies/substitutes → global prior + flag, never
zero), no current-race result, no future race, no full-season
aggregate that leaks future events. Season-to-date aggregates use
strictly prior rounds only. DNF-rate prior removed (see §22a).

Candidates (past-only form/priors; DNF-rate DEFERRED):

``` text
driver_finish_mean_previous_3
driver_finish_mean_previous_5
driver_points_rate_previous_5

driver_season_to_date_finish_mean   (strictly prior rounds only)
driver_season_to_date_points        (strictly prior rounds only)
```

For Race N:

``` text
ALLOWED: Race 1 ... Race N-1
FORBIDDEN: Race N result and all future races
```

Never use final-season statistics for an earlier race.

# 22a. Reliability Priors --- DEFERRED

Reliability priors are DEFERRED from Phase 2. Phase 1 deliberately did
not define a binary DNF/reliability target, and no DNF-rate feature
(`driver_dnf_rate_*`, `constructor_dnf_rate_*`,
`circuit_historical_dnf_rate`) may be built in Phase 2. Do not invent
a DNF/reliability event definition merely to retain the family. Any
future reliability feature requires an explicit later policy defining
the historical event semantics. The binary DNF outcome target remains
undefined/deferred and must not be silently introduced.

------------------------------------------------------------------------

# 23. F14 --- Constructor Historical Priors

Status: MODIFY. Past-only (same rules as §22). Respect season-scoped
constructor identity (`(constructor_id, season)` — renames such as
toro_rosso→alphatauri→rb and racing_point→aston_martin are distinct
rows). Do not silently merge renamed teams across seasons; any lineage
aggregation requires a later explicit mapping/policy. DNF-rate prior
removed (see §22a).

Candidates:

``` text
constructor_finish_mean_previous_3
constructor_finish_mean_previous_5
constructor_points_rate_previous_5
constructor_season_to_date_points   (strictly prior rounds only)
```

Use stable canonical constructor identities where possible.

------------------------------------------------------------------------

# 24. F15 --- Pre-Race / Qualifying Context

Status: MODIFY. Keep factual grid-position context from the existing
D5 results source (PRE_RACE join on `(race_id, driver_id)`, subject to
explicit temporal/source contract and parity; note the 3 W-rows where
FastF1 leaves grid null). Defer all qualifying-derived fields: do NOT
assume `qualifying_position`, Q1/Q2/Q3, or qualifying deltas exist in
the frozen platform — they do not. Do not add qualifying ingestion to
Phase 2. Qualifying-derived features remain deferred unless a later
explicit data extension is approved.

Candidates (factual grid only):

``` text
grid_position
grid_vs_teammate
```

Only include fields with reliable definitions/coverage. These are
pre-race-known and therefore safe for race-lap prediction.

------------------------------------------------------------------------

# 25. F16 --- Circuit Context

Status: MODIFY. Only features computable from frozen historical data
with explicit past-only semantics (for a race in year T: no
information from race T or later). Any street flag, pit-loss estimate,
or circuit classification requires an actual source/definition —
drop/defer unsupported concepts rather than inventing them. DNF-rate
removed (see §22a).

Prefer circuit identity plus past-only historical statistics.

Potential candidates (past-only; each needs min-history + smoothing):

``` text
circuit_id
street_circuit                  (only with a sourced definition; else DEFER)

circuit_historical_position_change
circuit_historical_safety_car_rate
circuit_historical_pit_stop_mean
circuit_historical_pit_loss     (DEFERRED — needs measured pit-loss source)
```

For a 2024 race, historical statistics must not include the 2024 result.

------------------------------------------------------------------------

# 26. F17 --- Field / Pack State

Status: MODIFY. Requires synchronized factual state (§3, F6 gap
engine). Define "pack" algorithmically (explicit gap-threshold /
lap-tolerance rule with null-gap handling) — no vague race-domain
labels without mathematical definitions. Spreads/percentiles resolve
the field at the target clock.

Candidates:

``` text
gap_p1_p2
gap_p1_p3
gap_p1_p5

top_3_spread
top_5_spread

front_pack_size
field_spread
driver_gap_percentile
```

If pack membership is used, define it algorithmically.

------------------------------------------------------------------------

# 27. F18 --- Race Momentum

Status: MODIFY. Only observed historical trend/momentum features with
eligibility-matched endpoints. No model prediction feedback (already
banned below — kept).

Candidates:

``` text
position_change_last_3
position_change_last_5

gap_to_leader_change_3
gap_to_leader_change_5

pace_rank_change_3
pace_rank_change_5
```

Do not feed a model's own future probability evolution back into that
same model unless a later sequential-model experiment explicitly
requires it.

------------------------------------------------------------------------

# 28. F19 --- Domain Interactions

Status: MODIFY. Keep a small interpretable set only after primitive
features exist (F11 runs after F5–F10). Each interaction must have
domain rationale with units and sign conventions. Do not create dozens
of arbitrary polynomial combinations. No projected pit/rejoin
interaction (those inputs are DEFERRED — see §16).

Evaluate interpretable candidates such as:

``` text
gap_to_leader_per_remaining_lap    (remaining = scheduled − leader laps only)

pace_advantage_to_ahead × remaining_laps   (scheduled remaining only)

tyre_age × remaining_laps          (scheduled remaining only)
```

DEFERRED (projected-pit interactions — Strategy stage, not ML features):

``` text
pit_loss_minus_gap_behind
remaining_laps_after_projected_pit
estimated_laps_to_catch_ahead
```

Do not automatically generate polynomial feature combinations.

------------------------------------------------------------------------

# 29. F20 --- Telemetry

Status: DEFERRED per ADR-0001 (authoritative). Telemetry remains
deferred from canonical data. F12 is a lightweight ADR revisit-check
only: evaluate whether ADR-0001 revisit conditions changed (default
expected result: remains DEFERRED). It must NOT materialize telemetry,
build telemetry features, expand ingestion, or create
`telemetry_summary` unless a future explicit architectural decision
supersedes ADR-0001. The candidate summaries below are retained as
reference for such a decision only — they are NOT Phase-2 deliverables.

Candidate lap summaries (reference only, NOT to be implemented):

``` text
max_speed
mean_speed
median_speed

full_throttle_fraction
brake_fraction

mean_rpm
max_rpm

drs_active_fraction
gear_change_count

telemetry_sample_count
```

The list above is context for a future revisit decision, not a build
list. No telemetry feature is implemented or evaluated in Phase 2.

------------------------------------------------------------------------

# 30. Missing-Data Policy

Feature generation preserves meaningful source/derived missingness. No
global imputation during Phase 2. A feature may be null because: source
unavailable; insufficient history; invalid race-state geometry; no
synchronized rival observation; or not applicable (e.g. leader has no
car ahead, last car has none behind). Where useful, explicit
validity/count fields accompany a feature (e.g. `pace_n_*`, gap
validity companions). Model-specific imputation belongs to Phase 3
(Model Lab), computed on past-only training folds — never in the
feature matrix.

Every feature must define missing semantics.

Examples:

``` text
insufficient history
driver retired
no car ahead
no teammate running
weather unavailable
telemetry unavailable
pit information unavailable
```

Do not globally replace nulls with zero.

Model imputation belongs in explicit model preprocessing unless zero is
semantically correct.

------------------------------------------------------------------------

# 31. Early-Lap Behaviour

Rolling features have limited history.

Define deterministic behaviour and expose sample counts where useful.

Never backfill missing early history from future laps.

------------------------------------------------------------------------

# 32. Retirements / Red Flags / Abnormal Races

Test against:

-   retirements
-   Safety Cars
-   VSC
-   red flags
-   restarts
-   shortened races
-   wet races
-   pit-heavy races
-   timing anomalies

Do not assume normal uninterrupted lap progression.

------------------------------------------------------------------------

# 33. Shared Feature Engine Interface

The feature engine must conceptually support single-state/prefix
computation — e.g.:

``` python
feature_engine.build_state_features(race_id=..., lap=...)
```

and/or:

``` python
feature_engine.build_driver_features(
    race_id=...,
    driver_id=...,
    lap=...
)
```

with semantics equivalent to `features_for_state(prefix,
target_state)`: the single-state path accepts only rows with
`state_time_s <= clock` (+ PRE_RACE constants + strictly-prior race
history) and applies the SAME feature definitions/operators as batch.
Historical batch generation must not be the only implementation. Batch
output and single-state/prefix computation must match within numeric
tolerance (parity tests, §37). No pandas-only batch idioms that imply
future access (`shift(-1)`, centered rolling, `bfill`, unmasked
full-race aggregations, lap-number joins without a clock guard). Do not
require premature production serving infrastructure — the requirement
is one shared definition with two entry points, proven by tests.

Also support batch generation.

The same mathematical implementation must power:

``` text
historical training
AND
runtime inference
```

This prevents training-serving skew.

------------------------------------------------------------------------

# 34. Batch Generation

Support:

``` text
single race
single season
season range
full supported rich dataset
```

Use typed Parquet.

Example:

``` text
data/processed/features/
└── feature_set=v1/
    ├── season=2018/
    ├── ...
    └── season=2025/
```

Avoid thousands of tiny files.

------------------------------------------------------------------------

# 35. Feature-Set Versioning

Record:

``` text
feature_set_version
registry_version
source_dataset_version
pipeline_version
generated_at
```

Do not overwrite materially different feature definitions under the same
version.

Generate a feature manifest containing actual:

``` text
feature_count
families
rows
seasons
null_rates
generation_time
storage_size
```

------------------------------------------------------------------------

# 36. Mandatory Leakage Tests

Leakage tests ship alongside each family (F4–F11 gates) — F14 is the
combined adversarial suite, not the first time leakage is tested.

General invariant: compute at cutoff T → mutate/delete information
after T → recompute → features at/before T must remain identical.

## Future mutation

1.  Build features at Lap L.
2.  Record output.
3.  Mutate Lap L+1 through race finish (including rival future laps —
    same-lap rival rows with `state_time_s` after the target clock —
    future pits, future stint boundaries/endings, future weather,
    future race control, future race results, future driver results,
    future races, future-season data).
4.  Rebuild Lap L.
5.  Assert earlier features are unchanged where future data should be
    inaccessible.

## Label mutation

Change (frozen `race_driver_labels` outcome facts only — no DNF target
exists, so none is mutated):

``` text
winner_flag
position_final
podium_flag
points
points_finish_flag
```

State features must not change.

## Future weather

Change weather after the state timestamp. Earlier state must not change.

## Future race control

Insert a Safety Car after Lap L. Lap L state must not change.

## Future pit

Insert/change a pit stop after Lap L. Lap L state must not change.

## Historical prior

Change future-race results. Priors for an earlier race must not change.

## Rolling-window fixture

Create synthetic laps with an extreme future Lap L+1. Features at L must
remain unchanged.

------------------------------------------------------------------------

# 37. Training-Serving Parity

For selected historical states compare:

``` text
batch-generated feature row
vs
runtime single-state feature row
```

They must match within appropriate numeric tolerance.

Do not maintain separate implementations.

------------------------------------------------------------------------

# 38. Feature Quality Checks

For every generated feature set report actual:

``` text
dtype
unit
minimum
maximum
median where meaningful
missing rate
unique count
infinities
suspicious outliers
```

Do not silently clip suspicious values. Investigate first.

------------------------------------------------------------------------

# 39. Suspicious Predictive Power

Correlation is not proof of feature validity.

If a feature appears implausibly predictive of winner/final position,
perform a leakage audit before celebrating it.

Ask:

> Could this feature contain information from after the prediction
> state?

------------------------------------------------------------------------

# 40. Ablation Framework

Phase 2 defines ablation family groupings and creates

``` text
A — basic race state

B — A + relative pace

C — B + tyres

D — C + pits

E — D + traffic / closing rate

F — E + race control / weather

G — F + teammate context

H — G + historical priors
```

(Reliability/DNF arm removed: §22a DEFERRED. Telemetry arm removed:
ADR-0001 DEFERRED.)

Phase 2 defines ablation family groupings and creates
configuration/fixtures for later chronological experiments ONLY. NO
ablation execution, NO model training, NO model comparison, and NO
predictive metrics in Phase 2 — execution belongs to Phase 3
(Model Lab).

Do not assume later sets perform better.

Do not select a production model during this phase.

------------------------------------------------------------------------

# 41. Future Evaluation Metrics

Phase 2 creates NO predictive metrics and runs NO evaluation. The
ablation fixtures (§40) are shaped so Phase 3 can later apply its
chronological evaluation protocol (which owns metric choice and any
use of log loss, Brier score, calibration error, top-k, or latency).
No metric thresholds or model comparisons appear in the Phase-2 exit
report. Actual Prediction v2 evaluation must use the approved
chronological protocol, not legacy GroupKFold claims.

------------------------------------------------------------------------

# 42. Stage-of-Race Analysis

Phase 2 prepares race-progress bucketing definitions only (early / mid
/ late) for later Phase-3 evaluation. Prepare for evaluation by race
progress:

``` text
early
mid
late
```

Define buckets mathematically using race progress rather than hardcoded
race-specific laps.

Do not create separate production models yet. No evaluation is run in
Phase 2.

------------------------------------------------------------------------

# 43. Explainability Compatibility

Feature names and semantics must remain human-readable.

Prefer:

``` text
pace_vs_ahead_5
```

not:

``` text
f_047
```

Document units and signs so later SHAP/feature-importance outputs can be
explained truthfully.

------------------------------------------------------------------------

# 44. Performance

Benchmark actual:

``` text
one driver-state build
one complete lap/race-state build
one race batch
one season batch
full dataset batch where practical
```

Record actual runtime, memory where practical and output size.

Do not invent benchmark claims.

------------------------------------------------------------------------

# 45. Documentation

Create:

``` text
docs/FEATURE_ENGINE_ARCHITECTURE.md
docs/FEATURE_REGISTRY.md
docs/FEATURE_ENGINE_REPORT.md
```

Where practical, generate `FEATURE_REGISTRY.md` from the
machine-readable registry.

The final report must contain actual:

-   feature-set version
-   source dataset version
-   candidate feature count
-   families implemented
-   deferred features
-   missingness
-   leakage-test results
-   parity-test results
-   performance measurements
-   known limitations
-   recommended families for first Prediction v2 experiments

Do not claim improvement without a legitimate experiment.

------------------------------------------------------------------------

# 46. Execution Stages

Execute sequentially:

``` text
F0  Phase-1 Handoff Verification (verify D12 freeze, D9/labels, no
    Phase-1 drift; no feature implementation)
 ↓
F1  Temporal Semantics + Synchronization Contract (LAP_END, race-wide
    cutoff rule, cross-driver synchronization, gap principles,
    representative edge-case audit; freeze semantics before
    implementation)
 ↓
F2  Feature Registry + Parity Skeleton (registry metadata contract,
    per-feature versioning, batch/single-state interface contract;
    no substantive families yet)
 ↓
F3  Primitive Temporal Operators (rolling past windows, latest <= T,
    synchronized rival/field snapshots, past-race operators,
    within-stint prefix operators, validity/min-history helpers;
    tests + mutation tests)
 ↓
F4  D9 Factual Passthrough Layer (register/reuse D9 structural state;
    no duplicated derivation; establishes canonical output + manifest
    early; family tests)
 ↓
F5  Eligibility + Pace Family (recent pace, representative eligible
    pace, stint pace-trend proxy, tyre factual features as
    appropriate; family leakage tests)
 ↓
F6  Gap Engine (factual gap representation, lapped/missing validity,
    synchronization provenance, representative edge cases; leakage
    tests)
 ↓
F7  Relative / Teammate / Field / Traffic (synchronized cross-driver
    features, algorithmic pack definitions, relative pace; family
    tests)
 ↓
F8  Rates + Momentum (observed closing-rate style features, trend
    features, denominator/time guards; NO projected catch time;
    family tests)
 ↓
F9  Race-Control + Weather Temporal Context (passthrough plus
    backward-only derived trends/counts; staleness/timestamp policies;
    tests)
 ↓
F10 Past-Only Priors + Grid/Circuit Context (driver, constructor,
    circuit, factual grid; smoothing/cold-start; future-race mutation
    tests; NO reliability/DNF prior)
 ↓
F11 Thin Domain Interactions (small explicit interpretable set on
    validated F5–F10 inputs; no projected-pit terms; tests)
 ↓
F12 Telemetry ADR Revisit-Check (evaluate whether ADR-0001 revisit
    conditions changed; default expected result: remains DEFERRED; no
    telemetry implementation without separate authorization)
 ↓
F13 Label Join Contract (explicit race×driver training/evaluation
    join; labels separate from predictive state; state outcome-free;
    no new targets)
 ↓
F14 Combined Adversarial Leakage + Parity Validation (all families,
    cross-driver future mutations, future races/results, batch vs
    prefix parity)
 ↓
F15 Canonical Feature Matrix (deterministic versioned Parquet output,
    manifests/validation, descriptive quality report; no model
    training)
 ↓
F16 Ablation-Family Configuration + Model-Lab Handoff Fixtures
    (family groupings, configuration/fixtures ONLY; NO ablation
    execution, NO predictive metrics)
 ↓
F17 Documentation / Final Phase-2 Validation / Exit (architecture,
    generated registry, quality report, limitations, Phase-3 handoff,
    final regression)
```

------------------------------------------------------------------------

# 47. Stage Gates

## F0 --- Verify Data Platform

Verify the D12 freeze: read `V2_PHASE_1_DATA_PLATFORM.md`,
`docs/DATA_PLATFORM_ARCHITECTURE.md`, `docs/DATASET_V2_REPORT.md`,
`docs/PHASE1_EXIT_REPORT.md`, and `data/README.md` §10 (Phase-2 input
contract). Confirm canonical schemas, coverage, missingness and
Phase 1 quality gates, D9 state/label grains, and no Phase-1 drift.

STOP if the data platform is incomplete or materially unstable. No
feature implementation in F0.

## F1 --- Temporal Contract

Document LAP_END state-time semantics, the race-wide cutoff rule, the
cross-driver synchronization rule (rival `state_time_s <= T`), gap
representation principles, rolling-window, weather (backward-only +
staleness), race-control (timestamped-only), pit/stint (no future
stops/ends), and historical-prior cutoff semantics. Audit the
representative edge cases (normal dry, leader change, lapped cars, SC,
VSC, red flag, missing timing, shortened races, Belgium 2021, Japan
2022, Monaco/time-limited).

Add core temporal tests before mass feature implementation. Freeze
semantics before implementation.

## F2 --- Registry & Schemas

Implement registry, metadata (including source fields/entities,
temporal-availability rule, cross-driver synchronization requirement,
predictive eligibility, per-feature version), statuses,
feature/identifier/label separation, feature-set versioning, and the
batch/single-state parity-skeleton interface contract. No substantive
feature families yet.

## F3--F13 --- Feature Families & Operators

Implement incrementally (operators first, then F4 passthrough, then
families). Run targeted unit/leakage tests after each family. Do not
wait until the entire engine is complete. F12 is an ADR revisit-check
only (default: telemetry remains DEFERRED); F13 creates the label-join
contract without new targets.

## F14 --- Leakage & Parity

Run every mandatory leakage mutation test and batch/runtime parity test.
Any unexplained failure blocks completion.

## F15 --- Batch Dataset

Generate the first full candidate feature set in Parquet and report
actual rows/features/null rates/runtime/storage.

This is a candidate dataset, not automatically the final production
feature set.

## F16 --- Ablation Configuration + Handoff Fixtures

Create family-grouping definitions, configuration, and Model-Lab
handoff fixtures for later chronological family-by-family experiments.
NO ablation execution, NO model training, NO predictive metrics. Do not
select a production model.

## F17 --- Documentation

Generate the required architecture, registry and report documents, then
STOP.

------------------------------------------------------------------------

# 48. Quality Gates

## Temporal Safety

``` text
[ ] State-time contract documented (LAP_END + race-wide cutoff rule)
[ ] Cross-driver synchronization rule documented and tested
[ ] No future lap access (including same-lap rival future observations)
[ ] No future weather access
[ ] No future race-control access (untimestamped messages never placed)
[ ] No future pit/stint-end access
[ ] Historical priors are past-only (no current-race, no future races)
[ ] Labels cannot enter feature schema; no DNF target introduced
[ ] D9 factual state referenced, not reimplemented
[ ] Telemetry untouched (ADR-0001 holds unless separately superseded)
```

## Feature Engineering

``` text
[ ] Feature registry exists
[ ] Units documented
[ ] Sign conventions documented
[ ] Missingness documented
[ ] Feature families modular
[ ] Batch/runtime definitions shared
```

## Testing

``` text
[ ] Unit tests pass
[ ] Future mutation tests pass
[ ] Label mutation tests pass
[ ] Rolling-window tests pass
[ ] Historical-prior leakage tests pass
[ ] Training-serving parity passes
```

## Data Quality

``` text
[ ] No unexplained infinities
[ ] Suspicious outliers reported
[ ] Missingness measured
[ ] Coverage measured
[ ] No silent row dropping
```

## Reproducibility

``` text
[ ] Feature set versioned
[ ] Source dataset version recorded
[ ] Manifest generated
[ ] Deterministic generation where expected
```

## Documentation

``` text
[ ] Architecture documented
[ ] Registry documented
[ ] Actual feature counts reported
[ ] Deferred features reported
[ ] Known limitations reported
[ ] No unsupported performance claims
```

------------------------------------------------------------------------

# 49. Priority Order

Prioritise roughly:

``` text
WAVE 1 (defensible minimum for the Model Lab)
────────
Eligibility mask + raw/eligible trailing pace with counts
Relative pace (synchronized)
Factual tyre state
Factual pit/stint wrappers (D9 by reference)
Factual grid context
Current as-of weather + D9 flags by reference
Position/progress passthrough

WAVE 2 (needs operators + gap engine + tests first)
───────────
Gap engine (factual representation + validity)
Traffic counts + field spreads/percentiles (synchronized)
Closing rates, observed only (no catch-time projections)
Teammate-relative pace (synchronized)
Backward weather deltas + RC counts/recency
Driver/constructor/circuit priors (past-only, smoothed, cold-start)

DEFERRED (not Phase-2 features)
────────
Reliability/DNF priors and DNF target (§22a)
Qualifying-derived fields (Q1/Q2/Q3/deltas — no ingestion)
Telemetry summaries (ADR-0001)
Rejoin/pit-loss projections + projected-pit interactions (Strategy)
Catch-time projections
Clean-air pace claims, DRS-eligibility inference
```

Priority does not imply proven predictive value.

------------------------------------------------------------------------

# 50. Anti-Patterns

Never:

``` text
use centered rolling windows
join cross-driver rows on lap number without the state_time_s <= T rule
calculate full-race averages for early laps
use final season statistics for earlier races
use future weather because it is closest in time
use future pit stops or future stint endings in current state
copy the legacy session-minimum gap or 300 s clipping
encode SOFT/MEDIUM/HARD as an ordinal strength without model-stage justification
select all numeric columns as features
create opaque racing/AI scores without definitions
maintain separate training and API feature implementations
assume more features means a better model
invent a DNF/reliability event to keep a prior family
```

------------------------------------------------------------------------

# 51. Definition of Done

Phase 2 is complete when:

1.  A single authoritative temporal contract exists (LAP_END +
    cross-driver synchronization frozen).
2.  A machine-readable feature registry exists and is authoritative
    (per-feature versions, source fields, sync requirements).
3.  Reusable primitive temporal operators are implemented and tested.
4.  Retained feature families are implemented, modular and documented
    (deferred families recorded with reasons — telemetry, reliability/
    DNF, qualifying-derived, rejoin/catch-time projections).
5.  D9 factual state is referenced by passthrough, not reimplemented.
6.  Representative eligible-pace filtering exists (no clean-air claims).
7.  Trailing pace features are leakage-safe with counts/minimums.
8.  Relative pace features exist (synchronized, sign-documented).
9.  Tyre/stint/factual-pit features exist (asymmetric boundaries
    respected).
10. Traffic/closing-rate features exist where valid (observed rates
    only; no catch-time projections).
11. Teammate/field context exists where valid (synchronized, missing-
    teammate policy).
12. Race-control/weather features use backward-only/timestamped-only
    joins with staleness policy.
13. Historical priors are past-only (smoothed, cold-start; no DNF
    prior).
14. Telemetry remains explicitly resolved (ADR-0001 revisit-check
    recorded; no materialization without separate authorization).
15. Labels are structurally separate (explicit join contract; no new
    targets, no DNF target).
16. Every family has temporal leakage tests (cutoff/future-mutation,
    including cross-driver and future-race mutations).
17. Historical-prior leakage tests pass.
18. Training-serving (batch/single-state prefix) parity is demonstrated.
19. Candidate features are generated in deterministic versioned typed
    Parquet with manifest.
20. Actual missingness/coverage is reported; missingness preserved
    (no global imputation).
21. Descriptive feature-quality report exists (no predictive-
    performance claims required).
22. Ablation-family configuration + Model-Lab handoff fixtures exist
    (NO ablation execution, NO metrics, NO model comparison).
23. No unsupported new production prediction claim has been made; no
    winning model or accuracy improvement is required.
24. No later F1 Intelligence feature has been implemented.
25. `docs/FEATURE_ENGINE_ARCHITECTURE.md` exists.
26. `docs/FEATURE_REGISTRY.md` exists (generated from the registry).
27. `docs/FEATURE_ENGINE_REPORT.md` exists (with Phase-3 handoff and
    limitations).

Then:

``` text
PHASE 2 — TEMPORAL FEATURE ENGINE
              |
              v
           COMPLETE
              |
              v
        STOP AND REPORT
              |
              v
     WAIT FOR USER APPROVAL
              |
              v
 NEXT: RACE STATE / PREDICTION V2
```

------------------------------------------------------------------------

# 52. Final Instructions to OpenCode / Meta Spark 1.3

Read this entire document before changing code.

1.  Verify Phase 1 first.
2.  Begin at F0.
3.  Work sequentially.
4.  Use actual canonical schemas, not assumptions in this plan.
    Frozen D9 state/label grains and ADR-0001 hold; qualifying,
    telemetry, DNF-target, and rejoin/catch-time assumptions in older
    drafts are superseded by the status lines in §§8–29.
5.  Protect temporal boundaries before optimizing features — LAP_END
    plus the §3 cross-driver synchronization rule (rival
    `state_time_s <= T`); reference D9 factual state instead of
    re-deriving it.
6.  Treat suspiciously strong features as potential leakage.
7.  Never use future outcomes to engineer current state.
8.  Keep labels structurally separate.
9.  Share feature definitions between batch training and runtime
    inference.
10. Generate machine-readable feature metadata.
11. Use scripts/summaries for large datasets rather than loading huge
    raw tables into LLM context.
12. Do not implement every candidate merely because it appears here.
13. Mark unsupported/unjustified candidates as deferred.
14. Record actual counts, missingness, runtime and test results.
15. Do not claim predictive improvement without legitimate chronological
    evaluation.
16. Complete the leakage suite before phase exit.
17. Produce the required reports.
18. Stop after F17.
19. Do not automatically start the next phase.

## First action

``` text
F0 — PHASE-1 HANDOFF VERIFICATION
```

Do not begin mass feature generation until the source dataset, temporal
boundary, registry and leakage-testing framework are verified.
