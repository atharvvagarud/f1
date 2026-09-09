# `DATASET_V2_REPORT.md` — V2 Canonical Dataset Report (D4–D11)

> Plan: `V2_PHASE_1_DATA_PLATFORM.md` §44. Generated from ACTUAL pipeline
> results on 2026-09-08 — nothing estimated. Scope of this issue: **Tier-B
> historical layer (D4 COMPLETE) + Tier-A rich Race layer (D5 COMPLETE) +
> canonical driver-lap state dataset (D6 COMPLETE) + temporally-safe supporting
> race context integration (D7 COMPLETE) + telemetry decision (D8 COMPLETE:
> canonical telemetry DEFERRED) + derived temporal state and outcome labels
> (D9 COMPLETE) + legacy dataset comparison (D10 COMPLETE, read-only) +
> Phase-1 final validation (D11 COMPLETE: 44 findings, 0 failed, 0 unresolved
> BLOCKERs — see `docs/PHASE1_FINAL_VALIDATION.md`)**.
> Full Phase-1 validation belongs to D11 (COMPLETE); D12 documentation,
> freeze and exit (COMPLETE 2026-09-08 — Phase 1 COMPLETE and FROZEN).

# Part 1 — Tier-B historical layer (D4, COMPLETE)

## Coverage

MEASURED (`data/v2/raw/manifests/tierb-full.json`: 76/76 COMPLETE):

- Seasons: 1950–2025, all 76 with canonical output.
- Races: 1149 distinct (season, round) — calendar-shaped per season.
- Circuits: 1145 rows, 77 distinct circuit slugs.
- Drivers: 3248 rows, 879 distinct driver slugs.
- Constructors: 1121 season-scoped rows, 211 distinct slugs.
- Results: 25,784 rows (one per driver per race).
- Standings: 3819 season-final snapshot rows.
- Sparse standings (1952/1953) are source-faithful (backmarker-only lists
  as served upstream, deterministically reproduced byte-identical).

## Dataset Size

MEASURED: 532 Parquet files (`data/v2/processed/<entity>/season=<YYYY>/`,
exactly 7 per season), ~2.6 MB total. 0 temp files. Row counts:
hist_seasons 76; hist_circuits 1145; hist_drivers 3248;
hist_constructors 1121; hist_races 1149; hist_results 25784;
hist_standings 3819.

## Missingness (Tier-B)

Parquet-native nulls, no sentinels (`-1` → null). hist_drivers:
driver_code 80.8% null (pre-code era), permanent_number 88.3% null
(numbers from 2014), date_of_birth/nationality 0.4% null. hist_standings:
standing_position 39.7% null (early unranked lists, tapering to ~0). No
nulls in the other Tier-B tables.

## Failed/Partial Races (Tier-B)

0 FAILED, 0 PARTIAL, 0 SKIPPED. 76/76 COMPLETE. Mid-run transient HTTP 429s
absorbed by the bounded retry budget; orphaned pre-fix outputs rebuilt
byte-identical through the normal transaction.

## Anomalies (Tier-B)

- 1952/1953 degenerate upstream standings (source-faithful sparsity).
- Classification vocabulary: position_text codes R (9043), W (357),
  D (159); `position` never null; 17,780 rows classified-but-not-running;
  16 shared-drive-era rows R/D-coded with points > 0 (verbatim, adjudicated
  as absent from 2018–2025 Tier-A).
- FK violations 0, duplicate PKs 0, null PKs 0, unknown columns 0.

## Readiness (Tier-B)

COMPLETE and validated as the stable results/metadata foundation.

# Part 2 — Tier-A rich Race layer (D5, COMPLETE)

## Coverage (MEASURED, whole 2018–2025 scope)

- Eligible championship Grand Prix Race sessions: **173**.
- Materialised: **173/173 terminal** — COMPLETE 171, PARTIAL 2, FAILED 0,
  SKIPPED 0, PENDING 0, DOWNLOADING 0.
- Per-season COMPLETE/PARTIAL:
  2018 21/0 · 2019 21/0 · 2020 17/0 · 2021 21/1 · 2022 21/1 ·
  2023 22/0 · 2024 24/0 · 2025 24/0.
- Distinct drivers **43**; distinct constructor slugs **16**; distinct
  circuits **31**; all eight seasons present.
- Entity rows (whole scope):

| Entity | Rows |
|---|---|
| races | 173 |
| results | 3,458 |
| driver_laps | **189,420** |
| pit_stops | 6,336 |
| stints | 9,324 |
| weather | 25,779 |
| race_control | 14,992 |

## Dataset Size (Tier-A, MEASURED)

1,211 canonical Parquet files (173 races × 7 entities), ~24 MB
(`driver_laps` ~15.5 MB; per season 2.35–3.35 MB). Largest single race
output 2023-r06-R (~0.17 MB). `data/v2` total (Tier-A + Tier-B): 1,743
files, ~29 MB. 0 temp files.

## Driver-lap quality / missingness (MEASURED; nothing imputed)

Per-season rows and key null counts:

| season | rows | lap_time null | s1 null | s2 null | s3 null | speedI1 null | speedST null | compound null | tyre_life null | stint null | track_status null |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2018 | 22,337 | 441 | 480 | 78 | 80 | 2,888 | 1,697 | 376 | 354 | 343 | 1,317 |
| 2019 | 23,676 | 284 | 453 | 40 | 43 | 3,305 | 1,802 | 0 | 0 | 0 | 0 |
| 2020 | 18,352 | 443 | 427 | 60 | 97 | 2,837 | 1,479 | 0 | 69 | 0 | 23 |
| 2021 | 23,758 | 455 | 568 | 35 | 39 | 3,245 | 1,833 | 60 | 0 | 0 | 0 |
| 2022 | 23,577 | 527 | 508 | 50 | 73 | 3,417 | 1,775 | 334 | 520 | 0 | 0 |
| 2023 | 24,422 | 439 | 535 | 41 | 107 | 3,775 | 2,150 | 35 | 35 | 0 | 0 |
| 2024 | 26,606 | 225 | 540 | 32 | 53 | 4,146 | 2,184 | 0 | 0 | 0 | 0 |
| 2025 | 26,692 | 355 | 518 | 53 | 56 | 4,400 | 2,215 | 503 | 526 | 446 | 0 |
| **Total** | **189,420** | 3,169 | 4,029 | 389 | 548 | 28,013 | 15,135 | 1,308 | 1,504 | 789 | 1,340 |

Whole-scope: position null 294 (incl. laps of non-starters); fresh_tyre null
0; sector_2/sector_3 missingness is small and concentrated on incomplete
laps. rows/race 60 (2021 Belgium) – 1,534; drivers/race 18–20.

Notable source gaps (preserved verbatim, never repaired):
- 2018: track_status sparsest of the era (China 2018-r03 573 nulls, Germany
  2018-r11 545, Hungary 2018-r12 96, Australia 2018-r01 83); stint_number
  nulls ~21-row sets in six races; 2018 Pirelli compound names
  (SUPERSOFT/HYPERSOFT/ULTRASOFT) kept verbatim (20 units, quality notes).
- Monaco 2022: tyre_life 161 / compound 35 / lap_time 26 null of 1,179 rows.
- Belgian 2021 (farce): all 60 laps compound null, 40 lap_time null.
- 2025 Miami (r06): 446 laps missing compound/tyre_life/stint_number;
  2025 Belgian (r13) smaller tail. 2022 Austria (r11): 359 tyre_life /
  299 compound null. 2023 Canada (wet, r08): 35/35.
- 2021 compound null 60 is entirely the Belgian farce; 2024 has no
  tyre/compound missingness.

## Pit / stint anomaly taxonomy (MEASURED)

- pit_stops 6,336 rows. **pit_in-only 246** (entry without exit — retirements
  in pits), **pit_out-only 159** (entry-less exits — pit-lane starts /
  red-flag procedures), 159 of which have null lap_number. **Negative
  durations 0** (a lap-adjacency pairing defect that manufactured 321
  impossible negative durations was corrected to chronological FIFO
  pairing — see Part 3). No missing pit half is ever inferred.
- stints 9,324 rows. null start/end 0; overlapping stints 0; negative spans
  0; compound null 39; UNKNOWN compounds 0; tyre_age_at_start null 44.
- Per-season pit in-only/out-only: 2018 32/5, 2019 31/12, 2020 23/5,
  2021 50/29, 2022 33/31, 2023 31/18, 2024 25/16, 2025 21/43.

## Weather (MEASURED; unit RESOLVED)

25,779 independent session-relative observations. `wind_speed` unit is
**m/s** — authoritative FastF1 3.7.0 source metadata
(`fastf1/_api.py::weather_data` docstring “Wind speed [m/s]”, value passed
through `float()` unconverted). Range 0.0–10.1; wind_speed null 0.
rainfall true on 1,755 observations (per season 2018 163, 2019 230, 2020 12,
2021 393, 2022 467, 2023 89, 2024 201, 2025 200). Past-only join contract
(`observed_at_s <= t`) unchanged; no future-nearest fallback introduced.

## Race control (MEASURED)

14,992 messages, raw text + 0-based source order, no SC/VSC derivation.
Categories: Flag 8,873, Other 4,906, Drs 524, SafetyCar 443, CarEvent 246.
`observed_at_s` null on exactly 69 messages, all in 2018-r02 (source Utc
gaps), preserved verbatim.

## Classification / DNF evidence (MEASURED)

- `position_text`: numeric 1–20 (classified), R 420 (unclassified
  retirement), W 18 (did-not-start/withdrew), D 13 (disqualified).
- `dnf_flag` true on 451 rows (R+W+D); classified_position null 451;
  all 451 carry 0 points; **0 scoring R/D rows** in 2018–2025. No final ML
  DNF target added (deferred to the label stage); classification evidence
  preserved for that decision.
- `position_final` null on 3 rows — all W rows where FastF1 leaves
  DNS/withdrawn drivers unordered (Jolpica ranks them at the back: the only
  Tier-A vs Tier-B disagreement, see below).

## Identity validation vs D4 (MEASURED)

Unmapped driver ids 0; unmapped constructor slugs 0; circuit lookup
failures 0; circuit mismatches 0; race/round counts match D4 per season.
Driver-number changes observed (attributes, never keys): max_verstappen
33→1; bearman/de_vries/doohan/lawson substitute numbers. Constructor slug
lineage (toro_rosso→alphatauri→rb, racing_point→aston_martin) is
season-scoped in D4; no rename guessed. No silent fuzzy matching.

## Cross-source results vs D4 Tier-B (MEASURED)

All 3,458 Tier-A results matched Tier-B on (season, round, driver).
Disagreements: grid 3, position 3 — all DNS/withdrew (W) rows (2021-r22
mazepin; 2022-r02 mick_schumacher; 2023-r15 stroll). FastF1 keeps
GridPosition/Position null for these; Jolpica orders them at the back.
Classification token, status, laps, points are identical → representation
difference, documented, both sources preserved. points/laps/team/status
disagreements 0. No source overwrites the other.

## Failed / Partial / Anomalies (Tier-A)

- PARTIAL 2, both understood: 2021-r12 Belgian GP (shortened 3/39 laps),
  2022-r18 Japanese GP (shortened 29/53 laps, red flag + time limit).
- 148 COMPLETE units carry persisted quality notes (pit entry/exit
  mismatches 138 units, stint-boundary fallbacks 14, verbatim 2018 compound
  names 20) — anomalies preserved in provenance, not hidden.
- Session anomalies reported, never normalised: 2021 Belgium farce; Monaco
  2022 red-flag/wet missing tyre info; 2018 Bahrain RC messages lacking
  source timestamps; DNS rows keeping null FastF1 positions.

## Provenance (Tier-A)

173/173 terminal units hold run_id, schema_version=1 and 7 portable
project-relative output_refs (all files exist). Source/library version
(fastf1 3.7.0) is a code constant; generated data and the FastF1 cache are
outside Git.

## Storage / cache (MEASURED)

Canonical Tier-A ~24 MB across 1,211 files. FastF1 cache grew from
7.75 GB / 1,139 `.ff1pkl` to 15 GB / 1,900 blobs during D5 (+~7.3 GB):
telemetry/position blobs for the previously-uncached 2018/2024/2025 seasons
plus top-ups, required for `Session.t0_date` (race-control timestamps).
No raw telemetry is promoted to canonical storage (telemetry_summary is an
unmaterialised shell).

## Idempotency / resume (MEASURED)

COMPLETE units skip (`run --all-pending` → nothing pending); deterministic
`--force` rebuilds are byte-identical (unit-tested); interrupted runs resume
via the D3 manifest machinery (exercised live on 2018); no stale DOWNLOADING
units, no temp files, no duplicated logical rows.

# Part 3 — D5 corrections (adjudication record)

- PARTIAL semantics: PARTIAL means material incompleteness; source/domain
  anomalies (pit quirks, boundary fallbacks, verbatim out-of-set compounds,
  cross-source identity notes) are COMPLETE with a persisted `quality_note`.
  Before/after across proof/gate manifests: 22 PARTIAL → 2 PARTIAL
  (16 pit-quirk units re-adjudicated COMPLETE; Belgian farce stayed PARTIAL;
  Japanese 2022 added). Code + tests updated.
- Pit pairing corrected from lap-adjacency to chronological FIFO after the
  dataset-wide validation measured 321 impossible negative durations (real
  consecutive stops can share a lap number). Result: 0 negative durations.
  Regression test uses the real 2025-r01 back-to-back stop pattern.
- NaN compound handling: float NaN no longer stringifies to `'nan'`; textual
  missing tokens stored as null (2018 compound nulls 33 → 376).
- FastF1 `DataNotLoadedError` (soft-fetch failures, e.g. upstream throttling)
  mapped to TRANSIENT; telemetry load kept on because `t0_date` (and hence
  race-control `observed_at_s`) requires it. Canonical output unchanged in
  spirit: no telemetry columns/files.

# Part 4 — D6 canonical driver-lap state dataset (COMPLETE)

All figures MEASURED from the D6 canonical outputs
(`data/v2/processed/driver_lap_state`, `race_quality`, `d6-canonical.json`,
`reports/data_quality/d6_validation.json`); builder `v2/d6.py`, schema
`v2/d6schema.py` (`D6_SCHEMA_VERSION = 1`).

## Coverage / grain / reconciliation

- Grain: one canonical state row per (driver × race × lap). Source = D5
  `driver_laps` + `races` + `results` **identity only** + tiera manifests.
  No weather/race-control/pit/stint/label joins (D7/D9); no features.
- Input driver-lap rows **189,420** → canonical state rows **189,420**;
  **dropped 0**; duplicate input PKs 0; duplicate state PKs 0; null state
  PKs 0. Per-season state rows: 2018 22,337 · 2019 23,676 · 2020 18,352 ·
  2021 23,758 · 2022 23,577 · 2023 24,422 · 2024 26,606 · 2025 26,692.
- Distincts in state table: drivers 43, constructors 16, circuits 31,
  races 173, seasons 8.
- `race_quality`: 173 rows (one per race).

## Canonical identifiers + state time

- Identifiers are evidence-backed: `season`, `round_no`, `event_id`
  (`{season}-r{NN:02d}`), `race_id`, `driver_id` (Ergast slug),
  `constructor_id` (season-scoped), `circuit_id`, `lap_number`.
  `driver_number`/`driver_abbreviation` are attributes only.
- `state_time_s` = source lap-end `Time` (renamed `session_time_end_s`): row
  availability clock. Nulls 0; `lap_start_s <= state_time_s` on every row
  (0 violations); `state_time_s` strictly increasing per (race, driver) over
  lap order (0 violations).
- At `state_time_s`, every predictive-eligible field on the row is observable
  at or before `state_time_s`.

## Label separation

- State table carries **zero LABEL_ONLY columns** (asserted on the written
  parquet; `d6_validation.json`: `state_label_columns_present: []`). Final
  outcomes remain only in `results`; later training/evaluation construction
  joins labels explicitly. POST_RACE (`deleted`/`deleted_reason`/
  `is_accurate`) and SOURCE_METADATA columns are `predictive_eligible=False`.

## Missingness preservation (MEASURED)

- All 24 carried source columns: state null counts == D5 source null counts
  (0 mismatching columns whole-scope). Whole-scope nulls in state:
  position 294, lap_time 3,169, sector_1 4,029, sector_2 389, sector_3 548,
  speed_i1 28,013, speed_i2 1,348, speed_fl 6,575, speed_st 15,135,
  compound 1,308, tyre_life 1,504, stint_number 789, pit_in 183,243,
  pit_out 183,330, track_status 1,340. No imputation anywhere.
- Known source gaps preserved per representative race (real-data tests):
  Monaco 2022 tyre_life/compound; Belgian 2021 compound (all 60 null);
  2025 Miami compound/tyre_life/stint; 2018 track status / speed traps.

## PARTIAL races + quality metadata (MEASURED)

- 2021-r12-R (Belgian GP, 60 rows) and 2022-r18-R (Japanese GP) remain fully
  represented: every state row `source_unit_status='partial'`,
  `shortened_race=true`; `race_quality` keeps verbatim `partial_reason`.
- Data-derived `shortened_race` is also true for the three COMPLETE-but-
  time-limited races (2022-r07 Monaco 64/77, 2022-r17 59/61, 2020-r01
  68/71) while `source_unit_status` stays verbatim 'complete'. D6 decides no
  eligibility; later task policy may exclude.

## Determinism + leakage (MEASURED)

- Deterministic rebuild: two full builds produced identical sha256 on all 16
  files (real-data test asserts checksum equality).
- Mandatory future-data mutation tests (synthetic/offline, all green):
  future weather, future race-control, future laps (N+1 onward), final-result
  label mutation, future pit/stint mutation — earlier state rows unchanged.

## Performance + storage (MEASURED)

- Whole-scope build ≈ 1.40 s (0.13–0.19 s/season). 16 Parquet files,
  ~12.5 MB (8 state files 1.22–1.73 MB each; 8 race-quality files
  ~10–17 KB each).

# Part 5 — Pending / Not started

- Legacy comparison vs 2019–2023 checkpoint CSVs: **COMPLETE (D10,
  2026-09-08)** — see Part 9 and
  `docs/LEGACY_V2_DATASET_COMPARISON.md`. Read-only audit; legacy and V2
  behaviour unchanged.
- Telemetry summary decision: **COMPLETE (D8, 2026-09-08): DEFERRED** — see
  Part 7 and `docs/adr/ADR-0001-telemetry-retention.md`. No canonical
  telemetry data is produced.
- Derived features and label schemas/leakage tests for the foundational
  derived state + outcome labels: **COMPLETE (D9, 2026-09-08)** — see Part 8.
  Phase-2 feature families remain NOT STARTED (Phase 2 engine).
- Full D11 validation/report machinery: **COMPLETE (D11, 2026-09-08)** — see
  `docs/PHASE1_FINAL_VALIDATION.md` and
  `data/v2/reports/data_quality/d11_validation.json` (44 findings, 0 failed,
  0 unresolved BLOCKERs). D12 documentation/freeze/exit: **COMPLETE
  2026-09-08** — see `docs/PHASE1_EXIT_REPORT.md` (Phase 1 COMPLETE/FROZEN).

# Part 6 — D7 temporally-enriched canonical state (COMPLETE)

All figures MEASURED from the D7 canonical outputs
(`data/v2/processed/driver_lap_state_d7`, `d7-canonical.json`,
`reports/data_quality/d7_schema.json` / `d7_validation.json` /
`d7_coverage.json`); builder `v2/d7.py`, schema `v2/d7schema.py`
(`D7_SCHEMA_VERSION = 1`, base `D6_SCHEMA_VERSION = 1`).

## Coverage / grain / reconciliation

- Grain: one enriched canonical state row per (driver × race × lap) — D6
  grain preserved EXACTLY. Base = D6 `driver_lap_state` canonical output
  (constructed by `v2/d6.py::state_rows_for_race`; no competing construction
  path). D5 sources integrated: `weather`, `race_control`, `pit_stops`,
  `stints`.
- D6 base rows **189,420** → D7 enriched rows **189,420**; row delta **0**;
  duplicate enriched PKs **0**; null PKs **0**; race set == D6 (**173/173**).
- Per-season enriched rows identical to D6: 2018 22,337 · 2019 23,676 ·
  2020 18,352 · 2021 23,758 · 2022 23,577 · 2023 24,422 · 2024 26,606 ·
  2025 26,692.
- Output: 8 Parquet files, ~17.3 MB (`data/v2/processed/driver_lap_state_d7`).

## Schema changes (D7 vs D6 — additive only)

24 nullable context columns appended after the verbatim D6 state columns
(full field records in `v2/d7schema.py` + `d7_schema.json`; every column
specifies dtype / unit / nullable / availability / owner / source /
predictive_eligible / lineage_kind / description):

| Family | Columns | Lineage kind |
|---|---|---|
| Weather as-of (backward) | `wx_observed_at_s`, `wx_age_s`, `wx_air_temp_c`, `wx_track_temp_c`, `wx_humidity_pct`, `wx_pressure_hpa`, `wx_wind_speed` (m/s), `wx_wind_direction_deg`, `wx_rainfall` | values = source_observation; observed_at_s / age = derived_temporal_lineage |
| Race control (latest timed message) | `rc_last_message_seq`, `rc_last_message_observed_at_s`, `rc_last_message_age_s`, `rc_last_message_lap_number`, `rc_last_message_category`, `rc_last_message_flag`, `rc_last_message_text` | seq/time/age/lap = derived_temporal_lineage; raw attrs = source_observation |
| Pit history (as-of) | `pit_last_in_lap`, `pit_last_in_s`, `pit_last_out_lap`, `pit_last_out_s` | source_observation (event lineage) |
| Current stint (start side) | `stint_start_lap`, `stint_compound`, `stint_fresh_tyre`, `stint_tyre_age_at_start` | source_observation (state sample compound/fresh; boundary lineage start-lap/age) |

`predictive_eligible=True` only for the current-condition source-observation
state samples (the 7 wx physical quantities, `stint_compound`,
`stint_fresh_tyre`); event/boundary/lineage fields are `False` — converting
events into features (counts, since-lap, active flags, recency) is D9 work.
No LABEL_ONLY columns (asserted); enriched PK unchanged.

## Temporal joins performed (as-of semantics)

- Weather: strict backward as-of — latest obs with `observed_at_s <=
  state_time_s`; no prior -> null (no future-nearest / interpolation /
  smoothing / wetness / trends).
- Race control: latest TIMESTAMPED message with `observed_at_s <=
  state_time_s`; untimed messages never attach.
- Pit: latest entry / latest exit event with event time `<= state_time_s`;
  asymmetric in-only/out-only preserved; exit laps resolved 1:1 from the
  canonical pit-out marker.
- Stint: current stint by `stint_number`; START-side facts only, guard
  `start_lap <= lap_number`; eventual stint end NEVER attached.
- Temporal violations whole scope: **0** (weather / race-control / pit-entry /
  pit-exit / stint-start-lap / wx-age / rc-age all 0).

## Weather attachment coverage (MEASURED)

- States with prior weather **189,420/189,420** (100%); without prior: 0.
  Per-season coverage fraction 1.0 in all 8 seasons.
- Weather staleness (`wx_age_s`): min 0 s, mean ≈30.2 s, p50 ≈30.1 s,
  p95 ≈57.1 s, max **477.3 s**.
- Source-gap anomalies (no data between observations — honest, never
  repaired): 2020-r01-R (100 rows >60 s stale, max 477 s), 2023-r14-R
  (27 rows >60 s, max 339 s), 2018-r09-R (9 rows, max 92 s).
- Wet evolution spot checks green: 2019 Germany 1,033 rain-attached states;
  2022 Monaco 453; 2021 Belgium (farce) 60/60; 2022 Japan 458; 2025 Miami
  49; dry Bahrain (2018/2023/2024) 0.

## Race-control coverage + untimestamped handling (MEASURED)

- Source messages **14,992**: timestamped **14,923**, untimestamped **69**
  (all 2018-r02-R).
- Attachable under D7 semantics = timestamped (14,923). Distinct messages
  attached at least once **10,359**; states with RC lineage **188,396**
  across **172** races.
- 1,024 states without RC lineage: 998 = all of 2018-r02-R (its 69 messages
  have no source timestamps and are never invented into history / assigned to
  laps; preserved verbatim in the source `race_control` table); 26 =
  2020-r11-R early laps before the first timestamped message.
- Temporal violations: 0.

## Pit / stint attachment coverage (MEASURED)

- States with observable pit history **134,314** (`pit_last_in` 131,894;
  `pit_last_out` 131,211); states with current stint context **188,631**
  (absent on exactly the 789 D6 `stint_number`-null rows — e.g. 2025 Miami
  446, 2018 Germany 21 — preserved, never inferred).
- Source pit boundaries preserved: full 5,931 · pit_in-only 246 ·
  pit_out-only 159. 2,898 states have an observable entry as their most
  recent pit event with no observable exit (retirements in pits / boundary
  cases — source-faithful).
- Future-end fields excluded by construction (`end_lap` etc. never present);
  eventual stint endings / future compounds cannot affect earlier in-stint
  state (mutation tests green).

## Leakage + determinism + integrity (MEASURED)

- Synthetic suite (30 tests, offline) green incl. weather A–G, RC
  untimed-policy, pit/stint future-mutation, consolidated future-mutation
  suite at a state cutoff (weather / RC / pit / stint / future laps / final
  results), source-order shuffles -> identical output.
- Deterministic rebuild: two whole-scope builds produced identical sha256 on
  all 8 files.
- PK/FK/label integrity: duplicate PKs 0, null PKs 0, LABEL_ONLY columns 0,
  race set == D6, column order == schema, validation findings 0.

## Performance + storage (MEASURED)

Whole-scope D7 build ≈ **8.0 s** (0.78–1.12 s/season); peak RSS ~326 MiB;
output **8 Parquet files, ~17.3 MB** (2.0–2.4 MB/season). No
Spark/Dask/database infrastructure (pandas as-of over 189K rows).

## Known limitations (D7)

1. 2018-r02-R race-control messages (69) have no source timestamps and carry
   NO RC lineage on any canonical state (documented; never invented).
2. Weather staleness gaps in 2020-r01-R / 2023-r14-R / 2018-r09-R (source
   observation gaps; as-of attaches the last prior observation).
3. RC "latest message" is a raw-message context anchor, NOT an interpretation
   of current track state (SC/red-flag active-state derivation is D9 and must
   read the raw `race_control` table with its own leakage tests).
4. Pit/stint context exposes as-of event lineage and current-stint start-side
   facts only; counts / laps-since-pit / stint-end-aware features are D9.
5. PARTIAL races (2021 Belgium 60 rows, 2022 Japan 507 rows) remain fully
   represented with `source_unit_status`/`shortened_race` metadata.

## Readiness

The D6 canonical driver-lap state now carries temporally-safe supporting race
context (weather as-of, race-control lineage, pit history, current stint)
with documented schemas/temporal semantics, measured coverage and zero future
attachments. The D8 telemetry decision is complete (deferred). D9 derived
temporal state + separate outcome labels are complete (see Part 8) without
telemetry and without redesigning the temporal joins. D10 legacy comparison
is complete (see Part 9); D11 final validation is complete (44 findings,
0 failed, 0 unresolved BLOCKERs); D12 documentation/freeze/exit is complete
(see `docs/PHASE1_EXIT_REPORT.md`) — Phase 1 COMPLETE and FROZEN.

# Part 7 — D8 telemetry decision (COMPLETE: DEFERRED)

Decision record: `docs/adr/ADR-0001-telemetry-retention.md`. Evidence
measurement: `v2/d8.py` + `data/v2/reports/data_quality/d8_telemetry_sample.json`
(gitignored). All figures below MEASURED on the bounded 8-race sample unless
labelled PROJECTED.

## Sample (MEASURED)

8 already-cached Race sessions (one per plan bucket): 2018-r11 Germany ·
2019-r11 Germany (wet) · 2021-r10 Britain (sprint) · 2021-r12 Belgium
(shortened) · 2022-r07 Monaco · 2023-r01 Bahrain · 2024-r01 Bahrain ·
2025-r06 Miami. All 20 cars per race; **7,710/7,710** canonical driver-lap
windows covered (0 zero-sample); **6,776,940** telemetry samples.

## Channels / units (MEASURED)

`car_data`: `Time` (session-relative, aligned to the D6 state clock), `Date`
(UTC), `RPM` (rpm), `Speed` (km/h), `nGear`, `Throttle` (raw %, up to ~104),
`Brake` (bool), `DRS` (raw int), `Source` — channel null rates 0 across the
sample. `position_data`: `X/Y/Z` (metres), `SessionTime`, `Time`, `Date`,
`Status`, `Source`. Whole scope file presence (MEASURED by cache file): car
data 172/173 sessions (2018-r02 none), position data 171.

## Scale / cost

Median samples/lap by race 320–872; ≈59 bytes/sample of cached car data;
per-race car blob 30–84 MB; cached-blob load + lap aggregation ≈0.3–0.4 s/race
measured; 8-race peak RSS ≈510–550 MiB. Whole-scope cache (MEASURED, file
sizes): ≈16.16 GB total (car_data 7,206 MB / 172; position_data 7,072 MB /
171; HTTP cache ≈1.69 GB). Whole-scope sample count is NOT claimed from the
sample (PROJECTED only if a build is ever run).

## Candidate summaries evaluated (sample; NOT materialized)

A small set with exact formulas (`summarize_lap`): sample_count, speed
max/mean/p95 (km/h), rpm mean/p95, throttle-pressed fraction, brake fraction,
DRS-active fraction (raw code==1), gear-change count — LAP_END available,
windowed to `[lap_start_s, state_time_s)`. Computability 100% on sample
windows; plausible ranges. Caveat: raw `DRS` semantics are era-inconsistent
(within-window code==1 fraction 0.06–0.61 across sample races; wet 2019 0.61
despite DRS disabled in rain; codes 2/3/8/10/12/14 occur) — a trustworthy DRS
feature needs track-zone validation.

## Utility + decision

Model utility: no Phase-1/3 requirement depends on telemetry; the D8 brief
permits skipping the predictive experiment where it would expand scope, which
was done (justified in ADR-0001). Product utility (replay/track/Race
Engine): served by the cache + a future dedicated track/replay asset pipeline,
not canonical duplication. Storage options A/B/C/D compared in ADR-0001.
**FINAL RETENTION DECISION: D — telemetry deferred from the canonical
Phase-1 dataset.** No canonical telemetry artifacts created; `telemetry_summary`
contract explicitly inactive; cache unchanged (size identical across D8 runs)
and untracked; D9 must not depend on telemetry. Revisit triggers are recorded
in ADR-0001.

# Part 8 — D9 derived temporal state + outcome labels (COMPLETE)

Machine-readable schema `v2/d9schema.py` (`D9_SCHEMA_VERSION = 1`); builder
`v2/d9.py`; tests `tests/test_v2_d9.py` (18, offline) +
`tests/test_v2_d9_realdata.py` (8, real-data, session-scoped). All figures
below MEASURED from `data/v2/processed/driver_lap_state_d9` +
`race_driver_labels` + `d9-canonical.json` + `d9_validation.json`.

## Derived temporal state (MEASURED)

- Grain preserved: D7 **189,420 → D9 189,420** (delta 0; per season identical
  to D6/D7). Duplicate PKs 0; null PKs 0; LABEL_ONLY outcome columns in state
  0; temporal violations 0 (leader-laps ≥ own lap; progress ∈ [0,1];
  laps-since ≥ 0; stint_lap ≥ 1; flag consistency).
- 10 derived fields (schema in `v2/d9schema.py`): `track_state` +
  `flag_yellow`/`flag_safety_car`/`flag_red`/`flag_vsc` (deterministic
  FastF1-3.7.0 TrackStatus-code transform at the lap boundary; NO message-text
  state machine; untimestamped messages unused); `race_leader_laps_at_state`;
  `race_progress_frac`; `pit_stops_completed_so_far`; `laps_since_last_pit_stop`
  (full stops only, past-only); `stint_lap` (current-stint start side only).
- Track-state whole-scope tokens: all_clear 170,989 · yellow 6,541 ·
  safety_car 8,237 · red_flag 310 · vsc 1,643 · vsc_ending 360 · null 1,340
  (2018 source sparsity preserved).
- Phase-2 feature families (pace/relative/degradation/traffic/priors/momentum/
  strategy/interactions/telemetry) are NOT implemented.

## Outcome labels (MEASURED, physically separated)

- Grain: one race × one driver = the official result population. Rows:
  **3,458** (per season 420 · 420 · 340 · 440 · 440 · 440 · 479 · 479).
  Duplicate PKs 0; null PKs 0. Source: authoritative FastF1 official results
  (D5); never inferred from the final observed lap; D4 Tier-B used read-only.
- Semantics: factual `position_final`, `classified_position`, `position_text`
  (token), `status_text`, `points`, `laps_completed`; derived facts
  `classified_flag` (classified), `winner_flag` (final pos 1), `podium_flag`
  (final pos ≤3), `points_finish_flag` (points > 0, incl. half-points races).
  All LABEL_ONLY / predictive_eligible=False.
- Winners: **173** (exactly one per race, 0 exceptions). Podium rows 519;
  points-finisher rows 1,730; classified 3,007; unclassified 451
  (position_text R 420 / W 18 / D 13). Final position null on exactly the 3
  DNS/withdrawn rows (2021-r22 mazepin, 2022-r02 mick_schumacher, 2023-r15
  stroll).
- **DNF decision:** binary modelling target DEFERRED; factual classification
  preserved; `results.dnf_flag` remains provisional unclassified evidence.

## Leakage / separation / determinism / performance (MEASURED)

- 18 offline synthetic tests + 8 real-data tests: track-code mapping &
  unknown-honesty, flag consistency, leader-laps past-only & ties, pit
  future-stop mutation (earlier rows unchanged; asymmetric stops never
  counted), stint-lap guard, label facts (no DNF column), final-result
  mutation boundary (state UNCHANGED, labels change), future-mutation suite at
  a cutoff, deterministic rebuild (identical sha256 on all 16 files),
  telemetry-deferred invariant.
- Cross-source label comparison vs D4 Tier-B (3,458 compared, all matched):
  position_final disagreements 0 on non-null rows; the 3 FastF1-null /
  Jolpica-ranked W rows reported (`fastf1_null_jolpica_ranked`), never
  overwritten; position_text/points disagreements 0.
- PARTIAL/shortened races represented (2021 Belgium 60 rows, 2022 Japan 507,
  Monaco 2022 etc.) with D6 quality metadata.
- Performance: full build ≈4.6 s (0.43–0.68 s/season); peak RSS ≈367 MB; 16
  Parquet files ≈17.7 MB (8 derived-state files ≈17.6 MB, 8 label files
  ≈0.09 MB).

## Baseline limitations (D5/D6, carried forward into D7/D8/D9)

1. 2018 is the sparsest Tier-A season (track-status and trap coverage),
   faithfully preserved and measured.
2. Certain races carry source-level missingness that is not imputed (Monaco
   2022, Belgian 2021 farce, 2025 Miami, 2022 Austria, 2023 Canada wet).
3. Three DNS rows keep FastF1-null numeric positions (Jolpica orders them);
   documented cross-source difference, both sources preserved.
4. PARTIAL units (2021 Belgium, 2022 Japan) are materially shortened races;
   downstream consumers must treat them as such. The canonical D6/D7/D9 dataset
   keeps them with `source_unit_status`/`shortened_race` metadata rather than
   excluding them.
5. Per-request fetch logs and RunRecord detail are run-ephemeral.

## D9 additions to limitations

6. Derived track-state flags reflect the source per-lap TrackStatus at the lap
   boundary; precise sub-lap SC/red-flag start/end times are NOT reconstructed
   (a RaceState reading raw status events/messages would own that).
7. `laps_since_last_pit_stop` is defined on the exit lap of fully-observed
   stops (0 on the exit lap); it is not a tyre-age label.
8. Binary DNF is deferred; `results.dnf_flag` remains provisional unclassified
   evidence, not a modelling target.

# Part 9 — D10 legacy dataset comparison (COMPLETE, read-only)

Audit utility `v2/d10.py`; evidence
`data/v2/reports/data_quality/d10_legacy_comparison.json` (gitignored);
human report `docs/LEGACY_V2_DATASET_COMPARISON.md`; tests
`tests/test_v2_d10.py` (8, offline). Nothing was modified: no legacy file or
model changed, no V2 semantic changed, nothing retrained.

## Legacy inventory (MEASURED)

- 5 ACTIVE base checkpoint files (lap5/10/15/20/25, 17 cols, 2019–2023,
  1,918–2,067 rows, 103–104 races, 33 drivers, exactly one winner row per
  race, 0 duplicate keys); grain verified race×driver×checkpoint.
- lap-10 weather variant (2,075 rows, 25 cols, INACTIVE) + lap-10 Bahrain
  snapshot (20 rows, INACTIVE).
- 15 active serving slots
  (`{logreg,hgb,xgboost}_lap{5,10,15,20,25}_multilap/`), all serving tuned
  pipelines; recorded GroupKFold CV summaries per slot.

## Coverage / overlap (MEASURED)

Legacy: 2019–2023, 103 (lap5/15/20/25) / 104 (lap10) races, 9,871 base rows.
V2: 2018–2025, 173 races, 189,420 states, 3,458 labels; driver abbreviations
identical across 2019–2023. Row mapping to V2 `(race, number, lap X)`:
lap5/15/20/25 100% (1,996 + 1,955 + 1,935 + 1,918); lap10 1,971/2,067
(95.4%) — 96 unmatched rows all share an exact session-time V2 counterpart
at laps < 10 (41 lap-1, 24 lap-3 incl. the 20 Belgium farce rows, rest spread
over laps 2/4/6–9): retired-driver latest-≤10 rows mislabelled lap 10 (old
FastF1 inventory; current FastF1 3.7/V2 has no such rows).

## Value / target agreement (MEASURED)

- On 9,775 matched rows: driver identity/number, position, session/lap time,
  compound, tyre life, stint, fresh flag, both pit markers agree **exactly**
  (nulls shared; 0 null-vs-value differences). Single-char track codes agree
  exactly; 702 matched rows carry multi-char codes that legacy mangles into
  integers.
- Winner labels: 2,069 distinct race-drivers constant across checkpoints, all
  matched to D9 labels, **0 mismatches**; 11 V2-only first-lap-DNS/retirement
  rows have no legacy observation (expected coverage difference).

## Discrepancy classification (plan vocabulary)

- **matching**: all equivalent source values above; cleaning that binds
  nowhere (lap_time/tyre_life/position clip bounds hit by 0 shipped rows).
- **expected difference**: continuous per-lap state vs 5 fixed checkpoints;
  69 V2-only seasons/races; duplicated checkpoint target vs race-grain labels.
- **legacy issue**: lap-10 gap column (min-rule + 300 s clip → 672/2,067 base
  rows pinned, 2019 Belgium 20/20 at 300); lap-10 non-uniform grain;
  track-status int coercion (776 rows); gap clip censoring 682 rows.
- **upstream-source difference**: 20 Belgium lap-10 rows from an older FastF1
  inventory (current FastF1 3.7 has laps 1–3 only); 2019 Mexico weather
  wind-direction offset in 80 rows.
- **new pipeline issue: none.**
- **unresolved: none.** D10 gate satisfied.
- Temporal safety: weather future-fallback is confirmed-risk code with **0**
  confirmed rows in the shipped data; checkpoint construction/cleaning/race
  grouping/winner duplication confirmed safe; season-mixing GroupKFold is a
  leakage risk only for chronological validity (not feature leakage).
- Evaluation: 5-fold GroupKFold by race (pooled seasons, full-data refit);
  recorded CV means quoted in the comparison doc; probabilities are
  independent per-driver binary scores (≈0.91 field sum on 2023 Bahrain),
  ensemble = latest-checkpoint majority/XGBoost. Legacy models cannot consume
  V2 (no shims).
