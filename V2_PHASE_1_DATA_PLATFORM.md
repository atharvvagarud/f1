# F1 Intelligence v2 --- Phase 1 Historical Data Platform & Dataset Expansion

> **Purpose:** Expand the cleaned/refactored F1 project into a
> reproducible historical data platform suitable for lap-by-lap
> prediction, replay, simulation, strategy analysis, and later F1
> Intelligence v2 systems.
>
> **Execution environment:** OpenCode Desktop + Meta Spark 1.3
> Contributor
>
> **Prerequisite:** `V2_FOUNDATION_REFACTOR.md` must be complete and its
> regression gates passing.
>
> **Primary rule:** Build the data foundation first. Do **not**
> implement Prediction v2, Monte Carlo, Strategy, What-If, Replay UI,
> Race Engineer AI, or other later product features in this phase.

------------------------------------------------------------------------

# 1. Mission

The original university project primarily uses historical Formula 1 data
from FastF1 for 2019--2023 and creates model datasets at fixed
checkpoints such as Lap 5, 10, 15, 20, and 25.

F1 Intelligence v2 requires a fundamentally richer historical
foundation.

The target is:

``` text
2018 ───────────────────────────── 2025
        RICH F1 INTELLIGENCE ERA

Every supported Grand Prix
Every supported race lap
Every driver

+ timing
+ positions
+ gaps
+ sectors
+ tyres
+ stints
+ pit information
+ track status
+ weather
+ race control where reliable
+ telemetry-derived summaries where justified
+ final outcomes as labels
```

Additionally, where supported through the historical results interface
used by FastF1/Jolpica:

``` text
1950 ───────────────────────────── 2017
        HISTORICAL RESULTS LAYER

Race metadata
Drivers
Constructors
Circuits
Grid/results
Championship/results metadata
Other fields only where genuinely available
```

Do **not** pretend the pre-2018 historical layer has the same richness
as 2018--2025.

------------------------------------------------------------------------

# 2. Core Data Principle

Do not build F1 Intelligence around one enormous hand-maintained CSV.

The canonical flow should be:

``` text
UPSTREAM F1 SOURCES
        │
        ▼
RAW / CACHED INGESTION
        │
        ▼
NORMALISATION
        │
        ▼
QUALITY VALIDATION
        │
        ▼
CANONICAL PARQUET DATA
        │
        ├──────────────► RACE STATE (later phase)
        │
        ├──────────────► REPLAY (later phase)
        │
        └──────────────► FEATURE ENGINE
                              │
                              ▼
                        ML DATASETS / EXPORTS
```

CSV may still be generated for:

-   debugging
-   manual inspection
-   notebooks
-   compatibility
-   selected exports

But CSV must not be the canonical storage architecture.

------------------------------------------------------------------------

# 3. Non-Negotiable Rules

## 3.1 No future-information leakage

For a state representing:

``` text
Race X
Lap Y
Driver Z
```

all state/features must use only information available at or before Lap
Y.

Future outcomes may exist as **labels**, but must never enter the
feature/state side.

Example:

``` text
KNOWN AT LAP 20                  FUTURE LABEL

position = 2                     final_position = 1
gap_to_leader = 3.1              winner = 1
compound = MEDIUM                podium = 1
tyre_age = 12                    points_finish = 1
recent_pace_3 = ...              dnf = 0
```

The right-hand side must never be used to construct the left-hand side.

------------------------------------------------------------------------

## 3.2 Preserve raw provenance

Do not silently mutate source data.

The pipeline should make it possible to determine:

-   source
-   season
-   event/session
-   ingestion time
-   pipeline/schema version
-   transformations applied
-   missing-data state
-   validation state

------------------------------------------------------------------------

## 3.3 Missing data is not zero

Never automatically convert unavailable information into `0` unless zero
is semantically correct.

Use explicit null/missing values and document imputation separately.

------------------------------------------------------------------------

## 3.4 Do not fabricate unavailable history

If a field is unavailable for a race/season:

-   leave it missing
-   record the missingness
-   report it in data-quality output

Do not infer or fabricate values merely to make the dataset complete.

------------------------------------------------------------------------

## 3.5 No V2 model improvements in this phase

Do not:

-   retrain the production predictor
-   replace GroupKFold
-   calibrate probabilities
-   add podium/DNF models
-   modify the ensemble
-   implement Monte Carlo
-   implement strategy recommendations

This phase prepares data for those later changes.

------------------------------------------------------------------------

## 3.6 No unnecessary high-frequency telemetry explosion

Do not make raw high-frequency telemetry the primary ML table.

Prefer:

``` text
raw telemetry
     ↓
deterministic aggregation
     ↓
driver-lap telemetry summaries
```

Retain/cache raw telemetry only according to a documented policy.

------------------------------------------------------------------------

## 3.7 Reproducibility

Given the same:

-   source data
-   pipeline version
-   configuration

the canonical processed dataset should be reproducible.

Use deterministic transformations wherever possible.

------------------------------------------------------------------------

# 4. Target Coverage

## Tier A --- Rich Race Intelligence Dataset

Target:

``` text
2018–2025
Race sessions
Every supported Grand Prix
Every supported race lap
Every participating driver
```

This is the primary dataset for F1 Intelligence.

Do not assume every field has perfect coverage across every race.

Measure actual coverage.

------------------------------------------------------------------------

## Tier B --- Historical Results Dataset

Target:

``` text
1950–2025
```

where supported by the historical results source available through the
project/FastF1 ecosystem.

This layer is primarily useful for:

-   seasons
-   events
-   circuits
-   drivers
-   constructors
-   grid positions
-   classified results
-   points
-   status
-   historical browsing/statistics

Do not mix this lower-resolution layer directly into the rich 2018--2025
ML feature matrix without an explicit later design decision.

------------------------------------------------------------------------

## Tier C --- 2026

Do **not** make the incomplete 2026 season part of the initial locked
historical ML dataset.

Design ingestion so a completed season can later be added with a
command/configuration change rather than a rewrite.

Desired future behaviour:

``` text
ingest season 2026
```

------------------------------------------------------------------------

# 5. Expected Scale

Do not hardcode or advertise guessed row counts.

The approximate expectation is that driver × lap resolution across
2018--2025 will produce on the order of hundreds of thousands of
race-state rows.

The pipeline must calculate and report the **actual**:

-   seasons
-   events
-   races
-   drivers
-   laps
-   driver-lap rows
-   missing rows
-   invalid rows
-   telemetry rows if retained
-   storage size

Only actual generated numbers may be used in documentation.

------------------------------------------------------------------------

# 6. Canonical Data Layers

Use clear layers.

Suggested structure:

``` text
data/
├── raw/
│   ├── manifests/
│   └── README.md
│
├── interim/
│
├── processed/
│   ├── races/
│   ├── results/
│   ├── laps/
│   ├── stints/
│   ├── pit_stops/
│   ├── weather/
│   ├── race_control/
│   └── telemetry_summary/
│
├── exports/
│   └── README.md
│
└── reports/
    └── data_quality/
```

Adapt this to the post-refactor repository.

Do not create meaningless empty directories.

------------------------------------------------------------------------

# 7. Storage Format

## Canonical analytical format

Prefer:

``` text
Parquet
```

because it provides:

-   typed columns
-   compression
-   efficient column selection
-   faster analytical reads
-   partitioning
-   compatibility with Python data tooling

------------------------------------------------------------------------

## Partitioning

Use practical partitioning.

For large lap-level tables, a reasonable starting point is:

``` text
processed/laps/
  season=2018/
  season=2019/
  ...
  season=2025/
```

Add additional partition keys only if benchmarks/query patterns justify
them.

Avoid thousands of tiny files.

------------------------------------------------------------------------

## CSV exports

Provide optional deterministic exports such as:

``` text
data/exports/driver_lap_dataset.csv
```

only where useful.

The pipeline should be able to regenerate them.

Do not treat exported CSVs as canonical source data.

------------------------------------------------------------------------

# 8. Canonical Identifiers

Create stable identifiers.

At minimum define:

``` text
season
round
event_id / race_id
session_type
driver_id
lap_number
```

Do not rely only on display strings such as `"British Grand Prix"` as
database-style identifiers.

Document ID construction.

Identifiers should remain stable across pipeline runs.

------------------------------------------------------------------------

# 9. Canonical Tables

Exact schemas must be verified against real source coverage before being
frozen.

Create a schema/versioning mechanism rather than assuming this document
lists every final field.

## 9.1 Races

Potential fields:

``` text
race_id
season
round
event_name
official_event_name
country
location
circuit
event_date
race_date
total_laps
session_type
```

Include source/provenance metadata where appropriate.

------------------------------------------------------------------------

## 9.2 Results

One row per driver/race.

Potential fields:

``` text
race_id
season
driver_id
driver_code
driver_number
constructor
grid_position
final_position
classified_position
status
points
laps_completed

winner
podium
points_finish
dnf
```

Outcome flags are labels/metadata, not historical Lap-Y features.

Define `dnf` carefully from classification/status rather than naïve
position logic.

------------------------------------------------------------------------

## 9.3 Driver-Laps

This is the most important canonical table.

One row should represent:

``` text
one driver
at one completed race lap
in one race
```

Potential raw/state fields:

``` text
race_id
season
round
driver_id
driver_code
lap_number

position
lap_time
sector_1_time
sector_2_time
sector_3_time

speed_i1
speed_i2
speed_fl
speed_st

compound
tyre_life
stint
fresh_tyre

pit_in_time
pit_out_time

track_status

is_accurate
deleted
deleted_reason
```

Use actual FastF1/source fields and documented derived fields.

Do not invent fields when unavailable.

------------------------------------------------------------------------

## 9.4 Pit Stops / Stints

Where reliable, represent pit/stint information separately rather than
encoding everything into driver-lap rows.

Potential fields:

``` text
race_id
driver_id
stint
start_lap
end_lap
compound
fresh_tyre
tyre_age_at_start
pit_in_lap
pit_out_lap
```

Exact definitions must be documented.

------------------------------------------------------------------------

## 9.5 Weather

Store source weather samples separately.

Potential fields:

``` text
race_id
time
air_temperature
humidity
pressure
rainfall
track_temperature
wind_direction
wind_speed
```

Do not prematurely forward-fill future weather into earlier race states.

Later race-state reconstruction must perform only time-safe joins.

------------------------------------------------------------------------

## 9.6 Race Control

Where source data is available and reliable:

``` text
race_id
time
lap
category
status
message
flag
scope
sector
racing_number
```

Preserve raw messages where licensing/storage policy permits.

Derived flags such as Safety Car/VSC should be deterministic
transformations with tests.

------------------------------------------------------------------------

## 9.7 Telemetry Summary

Do not initially make raw telemetry part of the main driver-lap table.

Create deterministic driver-lap summaries where useful.

Candidates may include:

``` text
max_speed
mean_speed
median_speed

mean_throttle
full_throttle_fraction
brake_fraction

mean_rpm
max_rpm

drs_active_fraction

telemetry_sample_count
```

Only retain features that:

1.  have legitimate coverage,
2.  have a clear definition,
3.  can be computed without future leakage,
4.  are useful enough to justify cost/storage.

Do not add telemetry features merely to make the dataset wider.

------------------------------------------------------------------------

# 10. Derived Race-State Features

Separate **canonical source data** from **derived ML/state features**.

Potential later-safe derived fields include:

``` text
gap_to_leader
gap_to_car_ahead

positions_from_grid
positions_gained_so_far

pit_stop_count_so_far
laps_since_last_pit

recent_pace_3
recent_pace_5

pace_vs_leader_recent
pace_vs_field_recent

tyre_age
stint_lap

leader_lap
race_progress
```

Every derived feature must have:

-   a documented definition
-   explicit required inputs
-   temporal boundary
-   unit test
-   missing-data behaviour

------------------------------------------------------------------------

# 11. Temporal Feature Contract

Create a central rule:

``` text
feature(driver, race, lap=Y)
```

may access only records with event/race time corresponding to
information known at or before the end of Lap Y.

No feature implementation may call something equivalent to:

``` text
whole_race_dataframe
    ↓
calculate aggregate using future laps
    ↓
attach result to Lap Y
```

unless the aggregate is strictly filtered to `<= Y`.

------------------------------------------------------------------------

# 12. Labels

Create explicit outcome labels separately from state features.

Candidate labels:

``` text
winner
podium
points_finish
final_position
dnf
gained_position_from_current
lost_position_from_current
```

For position gain/loss at Lap Y:

``` text
current_position_at_Y
vs
final_classified_position
```

This is a future label and must never be available to inference-time
feature code.

------------------------------------------------------------------------

# 13. Schema Separation

Where practical, enforce conceptual separation:

``` text
IDENTIFIERS
+
STATE / OBSERVABLE FEATURES
+
DERIVED PAST-ONLY FEATURES
+
FUTURE LABELS
+
PROVENANCE / QUALITY METADATA
```

Do not leave future labels mixed invisibly among model input columns.

Later ML code should select from an explicit feature schema rather than
using "all numeric columns except a few."

------------------------------------------------------------------------

# 14. Pipeline Architecture

Target:

``` text
FastF1 / historical source
          │
          ▼
   Session discovery
          │
          ▼
      Ingestion
          │
          ▼
   Raw/cache layer
          │
          ▼
    Normalisation
          │
          ▼
     Validation
          │
          ▼
  Canonical Parquet
          │
          ├────────► Data quality reports
          │
          ├────────► Export datasets
          │
          └────────► Feature engineering
```

Keep ingestion separate from feature engineering.

------------------------------------------------------------------------

# 15. Resumable Ingestion

This is mandatory.

Downloading eight rich seasons can be slow and failure-prone.

The pipeline must not require starting from 2018 again after one failed
event.

Use a manifest/checkpoint system.

Example conceptual manifest:

``` json
{
  "season": 2021,
  "round": 10,
  "event": "British Grand Prix",
  "session": "R",
  "status": "complete",
  "attempts": 1,
  "schema_version": "1",
  "ingested_at": "...",
  "rows": {
    "laps": 1000,
    "weather": 123
  }
}
```

Actual values must come from ingestion.

------------------------------------------------------------------------

# 16. Ingestion States

Support states such as:

``` text
pending
downloading
complete
partial
failed
skipped
```

If a session fails:

-   record failure
-   record error class/message
-   continue where safe
-   allow retry
-   do not mark partial data as complete

------------------------------------------------------------------------

# 17. FastF1 Cache Strategy

Use FastF1 caching intentionally.

Do not commit the runtime cache to Git.

Document:

-   cache location
-   how to configure it
-   how to clear it
-   offline/repeat-run behaviour
-   approximate actual cache size after ingestion

The processed canonical dataset must not depend on a developer's
undocumented local cache layout.

------------------------------------------------------------------------

# 18. Rate / Source Respect

Do not aggressively parallelise source requests without understanding
upstream behaviour.

Prefer:

-   caching
-   resumability
-   controlled concurrency
-   retry with backoff
-   local reprocessing after initial ingestion

Once raw/source data is cached, transformations should run locally
without repeatedly downloading the same sessions.

------------------------------------------------------------------------

# 19. Retry Behaviour

Implement bounded retries for transient failures.

Do not infinitely retry.

Differentiate where practical:

``` text
network/transient
source unavailable
session missing
parsing/schema error
validation failure
programming error
```

Persist enough information to debug failed races.

------------------------------------------------------------------------

# 20. Data Validation

Every ingested race should pass automated checks.

## Race-level checks

Examples:

``` text
race_id exists
season valid
event metadata present
drivers > 0
laps > 0
results available where expected
```

## Driver-lap checks

Examples:

``` text
lap_number >= 1
position within plausible range or null
lap time positive when present
tyre life non-negative when present
stint positive when present
driver belongs to race
race_id valid
```

## Uniqueness

Define and verify keys.

For driver-lap data, likely:

``` text
race_id + driver_id + lap_number
```

Investigate duplicates rather than silently dropping them.

------------------------------------------------------------------------

# 21. Race Invariants

Create validations such as:

-   no duplicate driver-lap primary keys
-   lap numbers do not exceed legitimate race range without explanation
-   driver identity is stable
-   final results map to known participants
-   impossible positions are rejected/flagged
-   compound values are from known/explicitly unknown categories
-   pit/stint ordering is coherent where data exists

Do not over-constrain unusual races.

Red flags, restarts, shortened races and timing anomalies must be
handled explicitly rather than assumed impossible.

------------------------------------------------------------------------

# 22. Data Quality Report

Generate machine-readable and human-readable reports.

Create something like:

``` text
data/reports/data_quality/
```

and:

``` text
docs/DATASET_V2_REPORT.md
```

Report actual:

-   coverage by season
-   races expected
-   races ingested
-   races failed
-   rows per season
-   drivers per race
-   lap coverage
-   missingness by field
-   compound coverage
-   sector coverage
-   weather coverage
-   race-control coverage
-   telemetry-summary coverage
-   anomalies
-   exclusions
-   storage size

Never invent percentages.

------------------------------------------------------------------------

# 23. Coverage Matrix

Produce a matrix similar to:

``` text
FIELD                2018  2019  2020 ... 2025

position              ...
lap_time               ...
sector_1               ...
compound               ...
tyre_life              ...
weather                ...
race_control           ...
telemetry_summary      ...
```

Populate it from actual data.

This becomes the evidence for deciding which fields are suitable for
production ML.

------------------------------------------------------------------------

# 24. Historical 1950--2017 Layer

Build this separately from the rich lap-level dataset.

Do not spend excessive Phase 1 effort forcing modern features into old
seasons.

Target useful historical entities:

``` text
seasons
races
circuits
drivers
constructors
results
standings where useful
```

If additional lap/pit information exists for portions of history,
preserve it only with explicit coverage metadata.

The application must later be able to communicate:

``` text
Historical results coverage: 1950–2025
Rich race intelligence coverage: 2018–2025
```

only if the completed pipeline verifies those statements.

------------------------------------------------------------------------

# 25. Compatibility With Existing 2019--2023 Data

The original checkpoint datasets are valuable.

Do not immediately delete them.

Create a comparison process.

For races/laps overlapping the old data:

``` text
OLD CHECKPOINT DATA
        │
        ├── compare definitions/values
        │
NEW CANONICAL DATA
```

Compare at least representative:

``` text
2019–2023
Lap 5
Lap 10
Lap 15
Lap 20
Lap 25
```

Investigate discrepancies.

Possible causes include:

-   bug in old pipeline
-   bug in new pipeline
-   upstream FastF1 changes
-   changed data cleaning
-   different missing-data handling
-   corrected source data

Do not force the new dataset to reproduce an old bug merely for
equality.

Document intentional differences.

------------------------------------------------------------------------

# 26. Pipeline Versioning

Introduce lightweight version metadata.

Examples:

``` text
dataset_schema_version
pipeline_version
feature_schema_version
source_version where meaningful
```

Do not build a complex registry yet.

The goal is to make future datasets identifiable and reproducible.

------------------------------------------------------------------------

# 27. Dataset Manifest

Generate a top-level manifest summarising the build.

Conceptually:

``` text
dataset_version
created_at
seasons
schema_version
pipeline_version

race_count
driver_lap_count

successful_events
partial_events
failed_events

tables
file_paths
checksums where justified
```

Use actual values.

------------------------------------------------------------------------

# 28. CLI / Execution Interface

Provide a clear way to operate ingestion.

Adapt to existing project conventions.

Desired capabilities:

``` text
ingest one race
ingest one season
ingest season range
retry failed
validate
build processed data
generate quality report
export CSV
```

Example conceptual commands:

``` bash
python -m ml.data.ingest --season 2023
python -m ml.data.ingest --start-season 2018 --end-season 2025
python -m ml.data.ingest --retry-failed
python -m ml.data.validate
python -m ml.data.report
```

These are examples, not mandatory exact command names.

Document the actual commands.

------------------------------------------------------------------------

# 29. Idempotency

Re-running a completed ingestion should not create duplicate canonical
rows.

The pipeline should either:

-   safely skip already completed/version-compatible events

or

-   deterministically replace/rebuild them

Document the behaviour.

------------------------------------------------------------------------

# 30. Incremental Updates

Design so later additions are easy.

Examples:

``` text
add completed 2026 season
retry one corrected race
rebuild telemetry summaries
upgrade schema
```

Do not require rebuilding every historical season for a trivial isolated
update unless schema changes genuinely require it.

------------------------------------------------------------------------

# 31. Telemetry Policy

Before downloading/processing all telemetry, benchmark a representative
sample.

Measure actual:

-   source/cache size per race
-   processing time
-   processed summary size
-   coverage
-   usefulness of available channels

Then decide the full ingestion policy.

Do not blindly download hundreds of gigabytes because telemetry exists.

A sensible default is:

``` text
FastF1 cache/raw telemetry
        ↓
lap-level aggregation
        ↓
canonical telemetry_summary
```

Raw telemetry should remain outside Git.

------------------------------------------------------------------------

# 32. Weather Temporal Join

Weather data is time-based.

When later associating weather with Lap Y:

use only the most recent observation available at/before the relevant
time, or another explicitly leakage-safe transformation.

Never use a future weather reading to populate an earlier lap.

Add tests.

------------------------------------------------------------------------

# 33. Race Control Temporal Join

Race-control events are also time-sensitive.

A Safety Car event that begins after Lap Y must not be visible in the
Lap Y race state.

Derived state should obey:

``` text
event_time <= state_time
```

or another rigorously defined equivalent.

Add temporal tests.

------------------------------------------------------------------------

# 34. Pit History Temporal Boundary

For Lap Y:

``` text
pit_stop_count
last_pit_lap
current_stint
```

may only reflect pit activity known by Lap Y.

Future stops must not appear.

------------------------------------------------------------------------

# 35. Recent Pace Features

For:

``` text
recent_pace_3 at Lap 20
```

the feature may use only eligible completed laps up to Lap 20.

Define behaviour when fewer than three valid previous laps exist.

Do not backfill from future laps.

------------------------------------------------------------------------

# 36. Race Start / Early Lap Handling

Early laps have less history.

Define deterministic missing-data behaviour.

Example:

``` text
Lap 1:
recent_pace_3 = null

Lap 2:
recent_pace_3 = aggregate of available eligible history
```

or another documented approach.

Do not fabricate a full rolling window.

------------------------------------------------------------------------

# 37. Red Flags / Restarts / Abnormal Races

F1 races are messy.

Identify and test races containing:

-   red flags
-   safety cars
-   VSC
-   shortened races
-   wet races
-   unusual classification
-   retirements
-   pit-lane starts where represented
-   timing anomalies

Do not exclude them silently.

Create an anomaly/exclusion registry if a race genuinely cannot be
represented safely.

------------------------------------------------------------------------

# 38. Exclusion Policy

If data must be excluded:

record:

``` text
race_id
driver_id if applicable
reason
pipeline stage
severity
manual/automatic
```

The final report must state actual exclusions.

------------------------------------------------------------------------

# 39. Tests

## Unit tests

Add tests for:

-   identifier generation
-   schema validation
-   time conversions
-   gap calculations
-   pit-history calculations
-   tyre-age calculations
-   rolling pace
-   labels
-   weather joins
-   race-control joins
-   telemetry aggregation

------------------------------------------------------------------------

## Temporal leakage tests

These are critical.

Construct fixtures where future values are deliberately extreme.

Verify that changing:

``` text
Lap Y+1 ... race finish
```

does not change features generated for:

``` text
Lap Y
```

where those future values should be inaccessible.

------------------------------------------------------------------------

## Integration tests

Test:

``` text
source/cached fixture
      ↓
normalisation
      ↓
canonical table
      ↓
validation
      ↓
derived feature output
```

Avoid requiring live internet for the normal automated test suite.

Use small checked-in fixtures where licensing/size permits.

------------------------------------------------------------------------

## Dataset integrity tests

Verify:

-   key uniqueness
-   valid schema
-   valid seasons
-   race-driver relationships
-   probability labels where applicable are binary
-   final position semantics
-   no future-label columns in feature schema

------------------------------------------------------------------------

# 40. Performance Measurement

Benchmark actual pipeline operations.

At minimum measure:

-   one-race ingestion
-   one-season ingestion where practical
-   processed Parquet read
-   filtering one race
-   filtering one driver
-   filtering one lap state
-   feature-generation runtime
-   telemetry-summary generation if enabled
-   storage size

Do not optimise prematurely.

Record actual measurements in the final report.

------------------------------------------------------------------------

# 41. Do Not Add a Database Yet Unless Required

Parquet should be sufficient for the historical analytical layer during
this phase.

Do not automatically introduce PostgreSQL/TimescaleDB.

A database may become useful when:

-   serving race state
-   storing prediction metadata
-   supporting interactive APIs
-   model monitoring
-   user simulations

Those are later architectural decisions.

------------------------------------------------------------------------

# 42. Documentation

Create/update:

``` text
docs/
├── DATA_PLATFORM_ARCHITECTURE.md
├── DATASET_V2_REPORT.md
└── architecture/
    └── 001-historical-data-platform.md
```

Exact ADR numbering may be adjusted to existing documentation.

------------------------------------------------------------------------

# 43. `DATA_PLATFORM_ARCHITECTURE.md`

Document:

-   upstream sources
-   rich vs historical coverage
-   ingestion flow
-   canonical tables
-   storage format
-   partitioning
-   identifiers
-   temporal boundaries
-   raw/cache policy
-   processed data policy
-   telemetry policy
-   update strategy
-   schema/versioning approach

------------------------------------------------------------------------

# 44. `DATASET_V2_REPORT.md`

This report must be generated from actual pipeline results.

Include:

## Coverage

Actual seasons/races.

## Dataset Size

Actual row/file/storage counts.

## Missingness

Actual field coverage.

## Failed/Partial Races

Actual list.

## Anomalies

Actual findings.

## Legacy Comparison

Differences vs 2019--2023 checkpoint datasets.

## Telemetry Coverage

Actual measured coverage.

## Known Limitations

Be explicit.

## Readiness

State whether the data platform is ready for the next phase.

------------------------------------------------------------------------

# 45. Execution Phases

Execute sequentially.

``` text
D0  Verify Foundation Refactor
 ↓
D1  Source & Coverage Audit
 ↓
D2  Schema & Data Contracts
 ↓
D3  Resumable Ingestion Framework
 ↓
D4  Historical Results Layer
 ↓
D5  Rich 2018–2025 Race Ingestion
 ↓
D6  Canonical Driver-Lap Dataset
 ↓
D7  Weather / Race Control / Pit / Stint Integration
 ↓
D8  Telemetry Sampling & Summary Decision
 ↓
D9  Temporal Derived Features & Labels
 ↓
D10 Legacy Dataset Comparison
 ↓
D11 Full Validation & Quality Report
 ↓
D12 Documentation & Phase Exit
```

------------------------------------------------------------------------

# D0 --- VERIFY FOUNDATION REFACTOR

Before data work:

-   read `V2_FOUNDATION_REFACTOR.md`
-   read `docs/FOUNDATION_REFACTOR_REPORT.md`
-   run relevant regression tests
-   confirm existing application remains operational
-   understand the post-refactor repository structure

If the foundation refactor is incomplete or materially broken, STOP.

Do not layer a new data platform over an unstable refactor.

------------------------------------------------------------------------

# D1 --- SOURCE & COVERAGE AUDIT

Inspect the actual FastF1 APIs/data objects used by this installed
project version.

Create a source-field inventory.

For representative races from:

``` text
2018
2020
2022
2024
2025
```

inspect actual availability for:

-   laps
-   timing
-   sectors
-   compounds
-   tyre life
-   stints
-   pit data
-   weather
-   race control
-   telemetry channels
-   results
-   driver/team metadata

Use representative unusual races too.

Do not assume documentation guarantees perfect historical coverage.

Produce an initial coverage report before locking the schema.

### D1 Gate

Do not proceed until actual field availability is understood.

------------------------------------------------------------------------

# D2 --- SCHEMA & DATA CONTRACTS

Define:

-   canonical IDs
-   schemas
-   types
-   units
-   nullable fields
-   provenance fields
-   primary/unique keys
-   temporal contracts
-   label separation
-   schema version

Create machine-readable schema validation where practical.

### D2 Gate

Schemas and leakage boundaries must be documented and tested before full
historical ingestion.

------------------------------------------------------------------------

# D3 --- RESUMABLE INGESTION FRAMEWORK

Implement:

-   session discovery
-   cache configuration
-   manifests
-   bounded retries
-   partial/failure states
-   idempotent writes
-   structured logging
-   single-race ingestion
-   season ingestion
-   range ingestion
-   retry-failed operation

Test with a very small subset first.

### D3 Gate

Demonstrate:

``` text
start ingestion
interrupt
resume
```

without duplicate or corrupted canonical output.

------------------------------------------------------------------------

# D4 --- HISTORICAL RESULTS LAYER

Ingest the broad historical layer where supported.

Target:

``` text
1950–2025
```

for stable results/metadata entities.

Measure actual coverage.

Do not block the rich dataset on obscure historical anomalies.

### D4 Gate

Historical layer has:

-   validated IDs
-   race metadata
-   results
-   documented actual coverage
-   missingness/exclusions report

------------------------------------------------------------------------

# D5 --- RICH 2018--2025 RACE INGESTION

Ingest race sessions season by season.

Recommended operational sequence:

``` text
2018
validate

2019
validate

...

2025
validate
```

Do not download eight seasons and inspect only at the end.

After every season:

-   validate
-   update manifest
-   generate summary
-   inspect failures

### D5 Gate

Every targeted race must be one of:

``` text
complete
partial + documented
failed + documented
explicitly excluded + documented
```

No unknown state.

------------------------------------------------------------------------

# D6 --- CANONICAL DRIVER-LAP DATASET

Build the normalized driver-lap table.

Requirements:

-   stable keys
-   typed schema
-   Parquet output
-   season partitioning
-   no duplicate keys
-   clear null semantics
-   deterministic build
-   source provenance

Generate actual row counts.

### D6 Gate

The complete driver-lap table passes integrity validation.

------------------------------------------------------------------------

# D7 --- SUPPORTING RACE DATA

Integrate separate canonical datasets for:

-   weather
-   race control
-   pit/stint information
-   results

Do not flatten everything prematurely.

Implement time-safe joins only where required.

### D7 Gate

Supporting tables have documented schemas and temporal semantics.

------------------------------------------------------------------------

# D8 --- TELEMETRY DECISION

Before full telemetry expansion:

1.  select representative races
2.  measure cache size
3.  measure processing cost
4.  inspect channel coverage
5.  build candidate lap summaries
6.  assess usefulness

Write a short decision record.

Choose one:

``` text
A. process telemetry summaries for all supported races
B. process selected channels only
C. defer telemetry summaries because cost/coverage is not justified yet
```

Any choice is acceptable if supported by actual evidence.

Do not use telemetry scale as a portfolio vanity metric.

------------------------------------------------------------------------

# D9 --- DERIVED FEATURES & LABELS

Implement only foundational, deterministic features that are useful to
the next Race State / ML phases.

Do not build the entire future feature set.

Every feature requires:

-   definition
-   temporal contract
-   test
-   missing-value policy

Create explicit label schemas.

### D9 Gate

Leakage tests pass.

------------------------------------------------------------------------

# D10 --- LEGACY COMPARISON

Compare the new canonical system against the original 2019--2023
checkpoint data.

Use representative races/checkpoints and automated comparison where
practical.

Classify discrepancies.

Do not blindly overwrite new values to match legacy outputs.

Document:

``` text
matching
expected difference
legacy issue
new pipeline issue
upstream-source difference
unresolved
```

### D10 Gate

No unexplained high-impact discrepancy remains hidden.

------------------------------------------------------------------------

# D11 --- FULL VALIDATION & QUALITY REPORT

Run the complete dataset build/validation.

Generate actual:

-   race count
-   driver-lap count
-   season counts
-   field coverage
-   missingness
-   failure list
-   exclusions
-   anomaly list
-   storage size
-   processing benchmarks
-   telemetry decision/results

Create `docs/DATASET_V2_REPORT.md`.

------------------------------------------------------------------------

# D12 --- DOCUMENTATION & PHASE EXIT

Finish:

``` text
docs/DATA_PLATFORM_ARCHITECTURE.md
docs/DATASET_V2_REPORT.md
architecture ADR
data README
root README data instructions
```

Then STOP.

Do not automatically begin Race State or Prediction v2.

------------------------------------------------------------------------

# 46. Quality Gates

## Gate A --- Coverage

``` text
[ ] 2018–2025 race target enumerated
[ ] Every target race has explicit ingestion status
[ ] Historical results layer coverage measured
[ ] Coverage matrix generated
```

## Gate B --- Integrity

``` text
[ ] Schemas validated
[ ] Primary keys unique
[ ] No silent duplicate removal
[ ] Missing values handled explicitly
[ ] Provenance available
```

## Gate C --- Temporal Safety

``` text
[ ] Labels separated from features
[ ] Rolling features are past-only
[ ] Pit history is past-only
[ ] Weather joins are time-safe
[ ] Race-control joins are time-safe
[ ] Automated future-leakage tests pass
```

## Gate D --- Reproducibility

``` text
[ ] Pipeline is resumable
[ ] Pipeline is idempotent
[ ] Dataset version recorded
[ ] Schema version recorded
[ ] Build manifest generated
```

## Gate E --- Storage

``` text
[ ] Canonical data stored in Parquet
[ ] Partitioning documented
[ ] FastF1 cache excluded from Git
[ ] CSV treated as export, not canonical storage
```

## Gate F --- Documentation

``` text
[ ] Architecture documented
[ ] Actual coverage documented
[ ] Actual missingness documented
[ ] Actual failures documented
[ ] Legacy comparison documented
[ ] Telemetry decision documented
```

------------------------------------------------------------------------

# 47. Git / Artifact Policy

Do not commit:

``` text
FastF1 runtime cache
temporary downloads
Python caches
build output
huge raw telemetry dumps
```

without an explicit repository artifact decision.

Determine whether canonical datasets/model artifacts belong:

-   directly in Git
-   Git LFS
-   release artifacts
-   external/object storage
-   reproducible local build

Document the decision.

Do not casually commit multi-GB data.

------------------------------------------------------------------------

# 48. Cost-Conscious OpenCode / Spark Behaviour

This phase may involve many files and large datasets.

To reduce unnecessary agent/API usage:

1.  Read the relevant data modules first.
2.  Plan before editing.
3.  Implement one D-stage at a time.
4.  Use scripts for repetitive inspection rather than asking the LLM to
    inspect thousands of rows.
5.  Generate machine-readable summaries.
6.  Ask the LLM to reason over summaries, not raw multi-GB datasets.
7.  Run targeted tests after small changes.
8.  Avoid repeatedly rescanning generated data.
9.  Do not paste enormous Parquet/CSV contents into agent context.
10. Store progress in repository documentation/manifests so later
    sessions can resume cheaply.

------------------------------------------------------------------------

# 49. Important Anti-Patterns

Do NOT:

``` text
download everything into one giant CSV
```

Do NOT:

``` text
use final race results as Lap-Y features
```

Do NOT:

``` text
forward-fill data from the future
```

Do NOT:

``` text
drop every row containing a null
```

Do NOT:

``` text
silently exclude difficult races
```

Do NOT:

``` text
store telemetry just because it is available
```

Do NOT:

``` text
make the ML model responsible for raw data ingestion
```

Do NOT:

``` text
make React/frontend code read raw FastF1 files
```

Do NOT:

``` text
introduce PostgreSQL/Kafka/Spark/Kubernetes just to call this "big data"
```

------------------------------------------------------------------------

# 50. Architecture Boundary After This Phase

At phase completion, we want:

``` text
                   HISTORICAL RESULTS
                    1950–2025*
                         │
                         │
FASTF1 RACE DATA         │
2018–2025                │
      │                  │
      ▼                  ▼
          INGESTION
              │
              ▼
         NORMALISATION
              │
              ▼
          VALIDATION
              │
              ▼
      CANONICAL PARQUET
              │
       ┌──────┼─────────┐
       │      │         │
       ▼      ▼         ▼
     laps   weather   results
       │      │         │
       └──────┼─────────┘
              ▼
       TEMPORAL FEATURES
              │
              ▼
         ML-READY DATA
```

`*` Only to the extent actually verified by the completed pipeline.

The next phase can then build a canonical Race State representation on
top of this data platform.

------------------------------------------------------------------------

# 51. Definition of Done

Phase 1 Data Platform is complete when:

1.  Rich race coverage for 2018--2025 has been attempted systematically.

2.  Every targeted race has a recorded status.

3.  Broad historical results coverage has been built and measured.

4.  Driver-lap data exists at all available laps rather than only Lap
    5/10/15/20/25.

5.  Canonical analytical data uses typed Parquet storage.

6.  Data ingestion is resumable.

7.  Data ingestion is idempotent.

8.  Data schemas are documented.

9.  Stable race/driver identifiers exist.

10. Labels are explicitly separated from features.

11. Automated temporal leakage tests exist and pass.

12. Weather/race-control joins obey temporal boundaries.

13. Missing data is reported rather than fabricated.

14. Data-quality reports contain actual measured coverage.

15. Legacy 2019--2023 checkpoint data has been compared against the new
    pipeline.

16. Telemetry policy has been decided from actual measurements.

17. FastF1 runtime caches are excluded from source control.

18. The pipeline can later add a completed season without architectural
    rewrite.

19. `docs/DATA_PLATFORM_ARCHITECTURE.md` exists.

20. `docs/DATASET_V2_REPORT.md` exists.

21. No later F1 Intelligence product feature has been implemented.

Then:

``` text
PHASE 1 — HISTORICAL DATA PLATFORM
               │
               ▼
            COMPLETE
               │
               ▼
       STOP AND REPORT
               │
               ▼
      WAIT FOR USER APPROVAL
               │
               ▼
   NEXT: RACE STATE ENGINE
```

------------------------------------------------------------------------

# 52. Final Instructions to OpenCode / Meta Spark 1.3

Read this document completely before modifying the repository.

Then:

1.  Verify the Foundation Refactor is complete.
2.  Start at **D0**.
3.  Work sequentially.
4.  Verify assumptions against the actual code and installed FastF1
    version.
5.  Do not implement later V2 features.
6.  Do not blindly download all historical data before validating the
    ingestion architecture.
7.  Establish schemas and resumability first.
8.  Validate each season during ingestion.
9.  Record actual coverage rather than assumptions.
10. Protect every temporal boundary against future leakage.
11. Use Parquet as canonical analytical storage unless a measured
    technical reason requires otherwise.
12. Keep CSV as an export/compatibility format.
13. Do not expose raw source data directly to the frontend.
14. Do not introduce unnecessary infrastructure.
15. At the end, generate the required reports.
16. Report exact commands executed, actual dataset counts, failures,
    exclusions, tests, storage sizes, and benchmarks.
17. Stop after D12.
18. Do not begin the Race State Engine without explicit user approval.

## First action

Begin with:

``` text
D0 — VERIFY FOUNDATION REFACTOR
```

Do not start mass historical ingestion until D0--D3 have established a
verified, resumable, leakage-safe data pipeline.
