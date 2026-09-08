# F1 Intelligence v2 --- Phase 2 Temporal Feature Engineering

> **Purpose:** Build a leakage-safe, reproducible, testable
> feature-engineering system on top of the completed Historical Data
> Platform.
>
> **Execution:** OpenCode Desktop + Meta Spark 1.3 Contributor
>
> **Prerequisites:** `V2_FOUNDATION_REFACTOR.md` and
> `V2_PHASE_1_DATA_PLATFORM.md` are complete and their verification
> gates pass.
>
> **Primary rule:** A feature for Driver D at Race R, Lap L may use only
> information legitimately available at or before that race state.

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
-   create past-only driver/constructor/circuit priors
-   create selected telemetry summaries if Phase 1 approved them
-   define future labels separately
-   implement leakage tests
-   generate candidate feature datasets
-   create ablation infrastructure

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
-   use future information
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

Define exactly what "Lap L state" means before feature implementation. A
recommended default is:

> State at Lap L represents information available after the relevant
> driver has completed Lap L, with only source events timestamped at or
> before the corresponding state timestamp eligible.

If the canonical data requires another definition, document it and apply
it consistently.

No feature family may reinterpret the temporal boundary independently.

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

Never use:

``` python
features = all_numeric_columns_except_some_labels
```

Use explicit feature schemas.

------------------------------------------------------------------------

# 5. Feature Registry

Create a central machine-readable registry. Each candidate feature
should record:

``` text
name
family
dtype
unit
description
source
calculation
temporal_requirement
minimum_history
missing_value_policy
version
status
```

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
├── telemetry.py
├── interactions.py
└── labels.py
```

The requirements are clear feature-family ownership, one temporal
contract and shared batch/runtime definitions.

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

High-priority candidates:

``` text
lap_number
total_laps_known
remaining_laps_estimate
race_progress_pct

current_position
grid_position
positions_from_grid

drivers_running
cars_on_lead_lap
```

Be careful with shortened/red-flagged races. Do not use eventual
completed race distance at an earlier state if that fact was not yet
known.

------------------------------------------------------------------------

# 9. F2 --- Gaps

Candidates:

``` text
gap_to_leader
gap_to_car_ahead
gap_to_car_behind

gap_to_leader_change_3
gap_to_leader_change_5

gap_to_ahead_change_3
gap_to_ahead_change_5

gap_from_behind_change_3
gap_from_behind_change_5

gap_to_leader_per_remaining_lap
```

Define sign conventions once and handle lapped cars/caution periods
explicitly.

------------------------------------------------------------------------

# 10. F3 --- Recent Pace

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
windows.

------------------------------------------------------------------------

# 11. Representative Pace Laps

Create a deterministic:

``` text
is_representative_pace_lap
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
are slow. Traffic is part of race performance.

Representative pace candidates:

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
fabricated values.

------------------------------------------------------------------------

# 14. F6 --- Tyres

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

Candidates:

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

Core candidates:

``` text
pit_stop_count_so_far
laps_since_last_pit
last_pit_lap
current_stint
current_compound
```

Future stops must never influence current state.

Higher-complexity candidates:

``` text
estimated_pit_loss
cars_inside_pit_loss_window
estimated_rejoin_position
traffic_after_projected_pit
```

Only implement these if they can be defined from current/past
information. Do not implement strategy recommendations here.

------------------------------------------------------------------------

# 17. F9 --- Traffic

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
confirmed DRS eligibility unless the source/state supports it.

------------------------------------------------------------------------

# 18. F10 --- Closing Rates

Candidates:

``` text
closing_rate_to_ahead_3
closing_rate_to_ahead_5

closing_rate_from_behind_3
closing_rate_from_behind_5

estimated_laps_to_catch_ahead
estimated_laps_until_caught
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

Candidates:

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

Where Phase 1 coverage supports it:

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

Historical priors must use only races before the current race.

Candidates:

``` text
driver_finish_mean_previous_3
driver_finish_mean_previous_5
driver_points_rate_previous_5
driver_dnf_rate_previous_5

driver_season_to_date_finish_mean
driver_season_to_date_points
```

For Race N:

``` text
ALLOWED: Race 1 ... Race N-1
FORBIDDEN: Race N result and all future races
```

Never use final-season statistics for an earlier race.

------------------------------------------------------------------------

# 23. F14 --- Constructor Historical Priors

Candidates:

``` text
constructor_finish_mean_previous_3
constructor_finish_mean_previous_5
constructor_points_rate_previous_5
constructor_dnf_rate_previous_5
constructor_season_to_date_points
```

Use stable canonical constructor identities where possible.

------------------------------------------------------------------------

# 24. F15 --- Pre-Race / Qualifying Context

Candidates:

``` text
grid_position
qualifying_position
grid_vs_teammate
qualifying_delta_to_teammate
```

Only include fields with reliable definitions/coverage. These are
pre-race-known and therefore safe for race-lap prediction.

------------------------------------------------------------------------

# 25. F16 --- Circuit Context

Prefer circuit identity plus past-only historical statistics.

Potential candidates:

``` text
circuit_id
street_circuit

circuit_historical_position_change
circuit_historical_dnf_rate
circuit_historical_safety_car_rate
circuit_historical_pit_stop_mean
circuit_historical_pit_loss
```

For a 2024 race, historical statistics must not include the 2024 result.

------------------------------------------------------------------------

# 26. F17 --- Field / Pack State

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

Evaluate interpretable candidates such as:

``` text
gap_to_leader_per_remaining_lap

pace_advantage_to_ahead × remaining_laps

estimated_laps_to_catch_ahead

pit_loss_minus_gap_behind

remaining_laps_after_projected_pit

tyre_age × remaining_laps
```

Do not automatically generate polynomial feature combinations.

------------------------------------------------------------------------

# 29. F20 --- Telemetry

Only implement if the Phase 1 telemetry decision supports it.

Candidate lap summaries:

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

Mark telemetry features experimental until evaluated. They may be more
useful for pace, degradation, simulation or anomaly detection than
direct outcome prediction.

------------------------------------------------------------------------

# 30. Missing-Data Policy

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

Create a clear interface conceptually similar to:

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

## Future mutation

1.  Build features at Lap L.
2.  Record output.
3.  Mutate Lap L+1 through race finish.
4.  Rebuild Lap L.
5.  Assert earlier features are unchanged where future data should be
    inaccessible.

## Label mutation

Change:

``` text
winner
final_position
podium
points
dnf
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

Prepare reproducible family-based experiments:

``` text
A — basic race state

B — A + relative pace

C — B + tyres

D — C + pits

E — D + traffic / closing rate

F — E + race control / weather

G — F + teammate context

H — G + historical priors

I — H + telemetry
```

Do not assume later sets perform better.

Do not select a production model during this phase.

------------------------------------------------------------------------

# 41. Future Evaluation Metrics

The ablation infrastructure should support later legitimate evaluation
using:

``` text
log loss
Brier score
calibration error
top-1 where appropriate
top-3 where appropriate
latency
```

Actual Prediction v2 evaluation must use the approved chronological
protocol, not legacy GroupKFold claims.

------------------------------------------------------------------------

# 42. Stage-of-Race Analysis

Prepare for evaluation by race progress:

``` text
early
mid
late
```

Define buckets mathematically using race progress rather than hardcoded
race-specific laps.

Do not create separate production models yet.

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
F0  Verify Data Platform
 ↓
F1  Define Temporal Contract
 ↓
F2  Build Feature Registry & Schemas
 ↓
F3  Implement Race-State / Gap Features
 ↓
F4  Implement Representative Pace Engine
 ↓
F5  Implement Relative Pace / Momentum
 ↓
F6  Implement Tyre / Stint / Pit Features
 ↓
F7  Implement Traffic / Closing Rate
 ↓
F8  Implement Teammate / Field Context
 ↓
F9  Implement Race-Control / Weather
 ↓
F10 Implement Historical / Circuit Priors
 ↓
F11 Evaluate Telemetry Candidate Features
 ↓
F12 Implement Selected Domain Interactions
 ↓
F13 Build Label Layer
 ↓
F14 Full Leakage & Parity Test Suite
 ↓
F15 Batch Candidate Feature Dataset
 ↓
F16 Build Ablation Infrastructure
 ↓
F17 Documentation & Phase Exit
```

------------------------------------------------------------------------

# 47. Stage Gates

## F0 --- Verify Data Platform

Read:

``` text
V2_PHASE_1_DATA_PLATFORM.md
docs/DATA_PLATFORM_ARCHITECTURE.md
docs/DATASET_V2_REPORT.md
```

Confirm canonical schemas, coverage, missingness and Phase 1 quality
gates.

STOP if the data platform is incomplete or materially unstable.

## F1 --- Temporal Contract

Document state-time, lap-completion, source-event, rolling-window,
weather, race-control, pit and historical-prior cutoff semantics.

Add core temporal tests before mass feature implementation.

## F2 --- Registry & Schemas

Implement registry, metadata, statuses, feature/identifier/label
separation and feature-set versioning.

## F3--F13 --- Feature Families

Implement incrementally. Run targeted unit/leakage tests after each
family. Do not wait until the entire engine is complete.

## F14 --- Leakage & Parity

Run every mandatory leakage mutation test and batch/runtime parity test.
Any unexplained failure blocks completion.

## F15 --- Batch Dataset

Generate the first full candidate feature set in Parquet and report
actual rows/features/null rates/runtime/storage.

This is a candidate dataset, not automatically the final production
feature set.

## F16 --- Ablation Infrastructure

Create configuration/tooling for later chronological family-by-family
experiments. Do not select a production model.

## F17 --- Documentation

Generate the required architecture, registry and report documents, then
STOP.

------------------------------------------------------------------------

# 48. Quality Gates

## Temporal Safety

``` text
[ ] State-time contract documented
[ ] No future lap access
[ ] No future weather access
[ ] No future race-control access
[ ] No future pit access
[ ] Historical priors are past-only
[ ] Labels cannot enter feature schema
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
ESSENTIAL
─────────
Race state
Gaps
Representative pace
Relative pace
Tyres
Pit state
Traffic
Race control

HIGH VALUE
──────────
Closing rates
Teammate context
Weather
Stint pace trend
Historical driver priors
Historical constructor priors

EXPERIMENTAL / EVALUATE
───────────────────────
Circuit priors
Complex pit-window features
Telemetry
Additional interactions
```

Priority does not imply proven predictive value.

------------------------------------------------------------------------

# 50. Anti-Patterns

Never:

``` text
use centered rolling windows
calculate full-race averages for early laps
use final season statistics for earlier races
use future weather because it is closest in time
use future pit stops in current state
select all numeric columns as features
create opaque racing/AI scores without definitions
maintain separate training and API feature implementations
assume more features means a better model
```

------------------------------------------------------------------------

# 51. Definition of Done

Phase 2 is complete when:

1.  A single authoritative temporal contract exists.
2.  A machine-readable feature registry exists.
3.  Feature families are modular and documented.
4.  Race-state/gap features exist.
5.  Representative pace filtering exists.
6.  Trailing pace features are leakage-safe.
7.  Relative pace features exist.
8.  Tyre/stint/pit features exist.
9.  Traffic/closing-rate features exist where valid.
10. Teammate/field context exists where valid.
11. Race-control/weather features use backward-only joins.
12. Historical priors are past-only.
13. Telemetry is included only if justified by Phase 1 evidence.
14. Labels are structurally separate.
15. Future-mutation tests pass.
16. Historical-prior leakage tests pass.
17. Training-serving parity passes.
18. Candidate features are generated in typed Parquet.
19. Actual missingness/coverage is reported.
20. Feature-set versioning exists.
21. Ablation infrastructure is ready.
22. No unsupported new production prediction claim has been made.
23. No later F1 Intelligence feature has been implemented.
24. `docs/FEATURE_ENGINE_ARCHITECTURE.md` exists.
25. `docs/FEATURE_REGISTRY.md` exists.
26. `docs/FEATURE_ENGINE_REPORT.md` exists.

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
5.  Protect temporal boundaries before optimizing features.
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
F0 — VERIFY DATA PLATFORM
```

Do not begin mass feature generation until the source dataset, temporal
boundary, registry and leakage-testing framework are verified.
