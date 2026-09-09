# F1 Intelligence v2 — Data Platform Architecture

> **Plan:** `V2_PHASE_1_DATA_PLATFORM.md`.
> **Status: D1–D11 COMPLETE (2026-09-08). D5 covers the full measured 2018–2025
> Tier-A Race-session scope: 173 units terminal (171 COMPLETE + 2
> evidence-backed PARTIAL). D6 covers the canonical driver-lap state dataset
> over that scope (189,420 state rows). D7 covers the temporally-safe
> integration of supporting race context (weather, race control, pit history,
> current stint) onto that canonical state (189,420 enriched rows). D8 is the
> measured telemetry decision: telemetry is DEFERRED from the canonical
> Phase-1 dataset (ADR-0001); the FastF1 cache stays the source layer. D9
> covers the derived temporal state + physically-separated outcome labels
> (189,420 derived state rows + 3,458 race-driver labels). D10 audits the
> legacy 2019–2023 checkpoint system against V2 (read-only; no legacy/V2
> behaviour changed). D11 is the final validation gate: 44 findings, 0 failed,
> 0 unresolved BLOCKERs (see `docs/PHASE1_FINAL_VALIDATION.md`).
> D12 documentation/freeze/exit COMPLETE 2026-09-08 — Phase 1 is COMPLETE
> and FROZEN (see `docs/PHASE1_EXIT_REPORT.md`).**
> Sections
> belonging to later stages are present below as explicit stubs only —
> nothing in them is implemented, measured, or decided.
> Nothing here is estimated silently: figures are tagged
> **MEASURED** (observed in this repo/cache), **CALCULATED** (arithmetic on
> measured/verified inputs), **VERIFIED EXTERNAL** (official calendars,
> provider docs), or **ESTIMATED** (clearly labelled sample-based
> projection, never a whole-dataset claim).

**Inputs read:** `V2_PHASE_1_DATA_PLATFORM.md` (complete),
`docs/D0_FOUNDATION_VERIFICATION.md`, `docs/FOUNDATION_REFACTOR_REPORT.md`.

---

## 1. Source strategy (D1 verdict)

Two separate systems, no silent mixing:

```text
A. RICH MODERN LAYER (2018–2025, Race sessions)
   Official F1 livetiming API via FastF1 3.7.0 (pinned)
   → laps / sectors / traps / tyres / stints / pits / track status /
     weather / race control / telemetry+position / session status / results
   → canonical driver-lap Parquet (D6), supporting tables (D7)

B. HISTORICAL RESULTS LAYER (1950–2025, metadata only)
   Jolpica-F1 Ergast-compatible API (https://api.jolpi.ca/ergast/f1),
   via FastF1's bundled Ergast interface (already points at Jolpica — §2.2)
   → seasons / circuits / races / drivers / constructors / results /
     qualifying / sprint / standings / status (+ thin laps/pitstops)
   → separate historical tables (D4). NEVER merged into the ML feature
     matrix without an explicit later design decision.

C. LEGACY BASELINE (2019–2023 checkpoint CSVs + 30 .pkl + ml.inference)
   Frozen. Coexists under existing paths until an explicit migration
   decision (D10 compares; nothing is replaced in Phase 1).
```

**2018 lower boundary: APPROPRIATE.** In-package evidence
(`fastf1/events.py`): FastF1's own backend has "full support for 2018 to
now"; seasons older than 2018 always fall back to Ergast. 2018 is therefore
the genuine start of the rich livetiming era, not an arbitrary cutoff.
Caveat for D5: per-family 2018 coverage (telemetry/position/weather depth)
must be validated race-by-race — uniformity is NOT assumed (see §4).

**2026: EXCLUDED** from the initial canonical dataset per plan (incomplete
season). Jolpica already serves 2026 endpoints, so later addition is a
configuration change, not a rewrite.

---

## 2. FastF1 3.7.0 capability audit

Pinned `fastf1==3.7.0` (verified installed). Evidence: installed package
API + https://docs.fastf1.dev (3.6.1 API reference — API surface unchanged
in 3.7.0 for everything below; verified against installed `core.py`) + 6
bounded cached-session probes (§3).

| Source family | Availability | Granularity / key columns | Loading | Canonical use |
|---|---|---|---|---|
| Event schedule | `get_event_schedule(year)`; keys MEASURED: EventName, OfficialEventName, EventFormat, RoundNumber, Country, Location, EventDate, Session1–5 + dates | Per event | `laps` not needed | Ingestion discovery (D3/D5) |
| Session metadata | `session_info` (meeting/session/country/circuit names + F1 id keys); `f1_api_support` flag per event | Per session | always with load | Provenance + support gating |
| Official results | 20 rows/race MEASURED; cols: Abbreviation, DriverId, DriverNumber, First/Last/BroadcastName, TeamId/TeamName, GridPosition, Position, ClassifiedPosition, Points, Laps, Status, Time, Q1/Q2/Q3 | Per driver/race | with `laps=True` | Labels + grid + DNF semantics |
| Lap timing | ~950–1180 rows/race MEASURED; Time, LapNumber, LapTime, LapStartTime/Date, Sector1–3Time + SectorN SessionTime, Position, Deleted/DeletedReason (needs messages), FastF1Generated, IsAccurate | Per driver/lap | `laps=True` | Core driver-lap table |
| Sectors | S1/S2/S3 97–100% non-null in normal races MEASURED | Per lap | `laps=True` | Canonical lap fields |
| Speed traps | SpeedI1/I2/FL/ST present; I1 weakest (76% Bahrain23 … 100% Belgium21) MEASURED — circuit-dependent | Per lap | `laps=True` | Canonical with missingness recorded |
| Tyres/stint | Compound/TyreLife/Stint/FreshTyre 100% in 5/6 probes; **TyreLife 86% Monaco22** MEASURED (source of the legacy NaN defect) | Per lap | `laps=True` | Canonical; TyreLife missingness is expected, not exceptional |
| Pit in/out | PitInTime/PitOutTime present; non-null = pit laps only (3–7% of rows) MEASURED | Per lap | `laps=True` | Pit/stint derivation (D7) |
| Track status | 100% non-null MEASURED (string of status codes per lap) | Per lap | `laps=True` | Canonical + SC/VSC derivation |
| Weather | 108–161 obs/race MEASURED; AirTemp/TrackTemp/Humidity/Pressure/WindSpeed/WindDirection/Rainfall + Time; ~1/min cadence per docs | Time series | `weather=True` | Separate table; past-only join (D7) |
| Race control | **Property is `race_control_messages`** (`race_control` does not exist in 3.7.0 — D1 probe correction); 73/90 rows MEASURED; Time(datetime64, 0% null), Category (Flag/Other/SafetyCar/Drs/CarEvent), Message, Lap (0% null), Flag/Scope/Sector/RacingNumber sparse | Per message | `messages=True` | Separate table; time-safe join (D7) |
| Telemetry (car) | ~760–850 samples/driver-lap × 18 channels MEASURED (Speed/RPM/Throttle/Brake/nGear/DRS/X/Y/Z/Distance/…); merged output is interpolated — docs recommend `get_car_data`/`get_pos_data` for accuracy | ~Hz time series | `telemetry=True` | Summaries only (D8 decides) |
| Position data | `pos_data` per car number MEASURED (present in 3/6 cached sessions) | Time series | `telemetry=True` | Summaries only |
| Session status | 5 rows/race MEASURED (Started/Finalised/Ends/Finished/Inactive) | Per session | `laps=True` | Validation |
| Deleted/accuracy | Deleted/DeletedReason require messages; IsAccurate has documented criteria (green/yellow, no in/out lap, full sectors, sector-sum check) | Per lap | `laps+messages=True` | Validation + quality flags |
| Ergast interface | Bundled `fastf1.ergast.Ergast`, `BASE_URL=https://api.jolpi.ca/ergast/f1` MEASURED in-package — no migration needed | Per endpoint | on demand | Tier B ingestion (D4) |

**Loading requirements:** `Session.load(laps, telemetry, weather, messages,
livedata)` flags are independent — **selective loading is supported**, so
D3 can skip telemetry/weather/messages per use case. `t0_date` requires
telemetry; `Deleted` requires messages; `driver_info`/`race_control`
attributes do NOT exist (use `results` / `race_control_messages`).

**Cache-completeness warning (MEASURED):** cached sessions are NOT uniform:
German19/Bahrain23/Vegas23 hold full blobs (incl. `car_data`,
`position_data`); Belgian21/Monaco22/British21 hold timing+weather+messages
only. D3/D5 must treat "session loaded" ≠ "all families present" and record
per-family status. Telemetry availability for a session can only be proven
by a telemetry-bearing cache entry or a fresh download.

---

## 3. Bounded probes (evidence base)

Six Race sessions, all served **100% from the existing local cache**
(FastF1 logs: "Using cached data" for every blob; zero network fetches).
Cache delta from probing: +192 KB confined to the **ignored**
`fastf1_http_cache.sqlite` bookkeeping file — no tracked file touched, no
bulk data created.

| # | Session | Role | Rows | Result |
|---|---|---|---|---|
| 1 | 2023 Bahrain | normal, late era | 1056 laps, 20 drivers, 161 wx, 73 RC | Full incl. telemetry (762 samples/lap) |
| 2 | 2019 German | wet | 1059 laps, 20 drivers, 147 wx, 90 RC | Full incl. telemetry (846 samples/lap) |
| 3 | 2023 Las Vegas | new circuit | 946 laps, 20 drivers, 108 wx | Full incl. telemetry (796 samples/lap) |
| 4 | 2021 Belgian | red-flag farce (2 racing laps) | 60 laps, LapTime 33% | Timing only; exclusion-case evidence |
| 5 | 2022 Monaco | wet + slow | 1179 laps, TyreLife 86% | Timing only; source-level NaN evidence |
| 6 | 2021 British | sprint weekend (`EventFormat='sprint'`) | 970 laps, normal richness | Timing only; Race richness unaffected by sprint format |

Sample statistics above are **sample statistics** (n=6, cached 2019–2023
only). No 2018/2024/2025 claims are made from probes.

---

## 4. Rich coverage envelope 2018–2025

| Season | Races | Evidence |
|---|---|---|
| 2018 | 21 | VERIFIED EXTERNAL (official calendar); no local data — D5 must validate per-family coverage |
| 2019 | 21 | MEASURED (cache dirs + 104-race inventory) |
| 2020 | 17 | MEASURED (incl. one-offs: 70th Anniversary, Sakhir, Tuscan, Eifel…; no Australia — cancelled pre-season) |
| 2021 | 22 | MEASURED (incl. first sprint weekends; Saudi/Qatar debuts) |
| 2022 | 22 | MEASURED |
| 2023 | 22 | MEASURED (incl. Las Vegas debut) |
| 2024 | 24 | VERIFIED EXTERNAL (official FIA calendar) |
| 2025 | 24 | VERIFIED EXTERNAL (official FIA 24-round announcement) |

**Target: 173 championship Race sessions (CALCULATED).** Per-family start
years are NOT uniform until D5 measures them: schedule/results are safe
from 2018 (livetiming era); lap/sector/tyre/weather/race-control depth and
telemetry/position completeness per 2018 race are open D5 questions.

---

## 5. Session scope — Race only (D1 recommendation)

Ingest **Race sessions only** in the initial platform. Evidence: (a) the V2
product is race replay/prediction; (b) local cache holds Race sessions
exclusively (verified by directory listing — no Q/FP/Sprint cached);
(c) **no qualifying ingestion is needed for grid data**: `GridPosition`
(plus Q1/Q2/Q3) is present in Race `results` (MEASURED §2); (d) sprint-weekend
Race sessions are equally rich (probe 6). Caveat for D2: on sprint weekends
the GP grid is set by the sprint — `GridPosition` still reflects the actual
starting grid, but D4's sprint-results endpoint should be the cross-check
source. Defer FP/qualifying/sprint-session telemetry until a concrete feature
requires it.

---

## 6. Event inclusion/exclusion rules (recommended for D2)

- **Include:** every completed championship Grand Prix 2018–2025 with a
  classified result, including shortened/red-flagged races (Monza-style
  countbacks), wet races, and one-off names (70th Anniversary, Sakhir,
  Eifel, Tuscan, Styrian…) keyed by stable IDs, not display strings.
- **Exclude with explicit record:** cancelled events with no session
  (e.g. 2020 Australia — absent from both cache and inventory), sessions
  with zero usable laps, non-championship sessions.
- **Never silently drop:** 2021 Belgium-type farces (2 racing laps,
  half points) must be ingested then flagged (`partial` + reason), because
  their lap rows are structurally valid but analytically special.
- **Sprints:** the Sprint *race* result is metadata for grid provenance,
  not a driver-lap row source, until a feature requires otherwise.
- **Naming:** EventName display strings change (São Paulo encoding,
  Mexico→Mexico City); canonical keys must use RoundNumber + circuitId +
  season (see §9), never the display name alone.
- **Corrections:** FastF1 synthesises laps (FastF1Generated), fixes stint
  info with warnings (observed in 3 probes), and syncs times with ±10 m
  jitter (documented). D6 must carry `FastF1Generated`/`IsAccurate` as
  quality flags, not silently filter on them.

---

## 7. Historical results source audit (docs only — no calls made)

- **Identity:** Ergast MRD shut down beginning of 2025; **Jolpica-F1 is the
  drop-in successor** (FastF1 3.8.3 docs; jolpica/jolpica-f1 on GitHub).
  Base `https://api.jolpi.ca/ergast/f1` — already the pinned 3.7.0 default.
- **Endpoints (per FastF1 Ergast interface docs, mirrored by Jolpica):**
  seasons, race schedule, drivers, constructors, circuits, finishing
  status, race results, qualifying results, sprint results, driver/
  constructor standings, lap times (driverId/position/time only),
  pit stops. This covers every Tier-B entity in the plan; nothing richer
  (sectors, compounds, weather) exists here — confirming the Tier-B/Tier-A
  split.
- **Pagination/rate limits:** default limit 30; **Jolpica max is 100**
  (Ergast allowed 1000) — D4 must page accordingly; custom User-Agent
  required; Jolpica Terms of Use apply; FastF1 handles caching/rate-limit
  enforcement.
- **Field stability:** Ergast vocabulary is stable and already shared with
  FastF1 (`driverId`, `constructorId`, `circuitId`, `permanentNumber`,
  `code`) — the cross-source join keys. `-1` marks missing ints under
  auto_cast; known differences doc (`ergast_differences.md`) must be read
  in D4 before trusting field parity.
- **Provenance/licensing:** Ergast terms applied historically; Jolpica
  TERMS.md + attribution apply now — D4 must record the chosen terms
  revision. **Quality caveat observed in the wild:** null `status` values
  reported for 2025 results (jolpica-f1 issue #166) — D4 must validate,
  not assume, post-2024 field completeness.
- **No bulk download in D1;** no probe calls were necessary — docs +
  in-package evidence suffice for D2 design.

---

## 8. Source responsibility matrix

| Data domain | Primary source | Fallback | Conflict rule |
|---|---|---|---|
| Season/event metadata (round, dates, format, circuit) | FastF1 schedule (2018+); Jolpica schedule (pre-2018 + cross-check) | Jolpica for 2018+ gaps | FastF1 wins 2018+; record disagreement in quality report |
| Race results (positions, points, status, grid) | FastF1 `results` | Jolpica race results | FastF1 wins for 2018+ (timing-consistent); Jolpica is Tier-B truth pre-2018 |
| Driver-lap timing / sectors / traps | FastF1 livetiming | None (Ergast lap times too thin) | No fallback allowed |
| Tyres / stints / pits | FastF1 laps (Stint/Compound/TyreLife/PitIn-Out) | Jolpica pitstops as cross-check only | FastF1 wins; stints derived, never hand-edited |
| Weather | FastF1 `weather_data` | None | Past-only join; nulls stay null |
| Race control / flags | FastF1 `race_control_messages` | None | Time-safe join; category mapping versioned in D2 |
| Telemetry summary | FastF1 car+pos data | None | Only if D8 says so |
| Historical results 1950–2017 (+2018+ metadata mirror) | Jolpica | None | Jolpica owns Tier B |
| Driver/constructor/circuit identity | Ergast-vocabulary IDs (`driverId`, `constructorId`, `circuitId`) shared by both | — | Stable IDs; display names never keys |

Provenance columns (D2 must require all): source, library/API version,
ingested_at, season, round/event/session keys, endpoint/session reference,
pipeline + schema versions, validation state (see §13).

---

## 9. Identifier findings (input to D2 — final design NOT done)

- **Driver:** `DriverId` is permanent Ergast-style (`max_verstappen` 2019→
  2023 MEASURED); 3-letter `Abbreviation` stable in practice; **`DriverNumber`
  is NOT stable** (VER 33→1). D2 key: `driverId`, with abbreviation/number
  as attributes.
- **Team:** `TeamId` slug changes on rename (`toro_rosso`→`alphatauri`,
  `racing_point`→`aston_martin` MEASURED) — D2 needs a team-identity mapping
  table, not raw TeamId as a long-lived key.
- **Event:** schedule keys MEASURED (`RoundNumber`, `EventName`,
  `OfficialEventName`, `EventFormat`, `Country`, `Location`, `EventDate`,
  Session1–5+dates). D2 key recommendation: `season + round + circuitId`
  (circuitId from Jolpica/schedule cross-check), never display name alone.
- **Session:** `R` (+ `api_path`/session_info F1 id keys) for the rich
  layer; sprint weekends distinguished by `EventFormat`.
- **Lap:** LapNumber within (race, driver) — with FastF1Generated/IsAccurate
  flags alongside, since synthetic/retirement laps exist.

---

## 10. Time semantics (input to D2 temporal contracts)

- `Time` = session time at lap **end** (Timedelta); `LapStartTime`/
  `LapStartDate` give lap start (session-relative + absolute). Absolute time
  has documented jitter (~±10 m across laps when overlapping telemetry).
- `PitInTime`/`PitOutTime` = session times of pit entry/exit (null =
  no stop on that lap). Sector session times (`Sector N SessionTime`) allow
  sub-lap alignment.
- Weather `Time` is source time (seconds since session start after
  conversion) at ~1/min cadence — supports past-only joins; legacy code
  already converts identically.
- Race-control `Time` is datetime64 absolute; `Lap` column present (0% null
  in both measured races) — supports both time- and lap-based joins, with
  `event_time <= state_time` as the D2 contract.
- `t0_date` (stream zero) requires telemetry; `session_start_time` ≠
  scheduled start (derive from status data).
- Post-race-corrected data: `results` (positions/points/status) are final
  outcomes — labels, never state. FastF1 may add/synthesise laps
  (retirements, first-lap minimal rows) — state reconstruction must handle,
  not assume, clean LapNumber sequences.

---

## 11. Weather fallback finding (D0 carried forward)

Legacy `weather_at_time_seconds`
(`scripts/data/build_dataset_multi_race_weather.py:59-98`): takes the latest
weather row with `time_seconds <= t_sec` — safe — **except** when all rows
are after `t_sec`, when it takes the earliest (future) row as "best-effort"
(lines 82–84). For V2 temporal features this is unsafe: a future observation
must never populate a historical lap state merely for being nearest.
Source timing fully supports the correct contract (weather `Time` at
~1/min cadence, MEASURED). **Recommended D2 contract:** past-only join
(`weather_time <= lap_end_time`); empty left side → explicit null +
missingness flag; no nearest-neighbour fallback across the future boundary.
Legacy code is NOT fixed in D1 (frozen baseline).

---

## 12. Expected scale (tagged; superseded by D5 MEASURED values)

Pre-D5 planning estimates are retained below for traceability, but every
figure is now superseded by the D5-measured whole-dataset values (§D5):

- Seasons 2018–2025: **8** (VERIFIED). Races: 21+21+17+22+22+22+24+24 =
  **173 Race sessions** (CALCULATED from MEASURED 2019–2023 cache inventory
  + VERIFIED EXTERNAL official calendars).
- Driver-lap rows: samples 946–1179/race (60 for the farce) MEASURED →
  **~170K rows ESTIMATED**. **D5 MEASURED: 189,420.**
- Weather rows: 108–161/race MEASURED → **~22K ESTIMATED**.
  **D5 MEASURED: 25,779.**
- Race-control rows: 73–90/race MEASURED → **~14K ESTIMATED**.
  **D5 MEASURED: 14,992.**
- Pit-stop/stint records: **~7K ESTIMATED**. **D5 MEASURED: 6,336 pit stops
  and 9,324 stints** (stints derived from laps, no separate download).
- Telemetry: 762–846 samples × 18 channels per driver-lap MEASURED →
  **~100M+ raw samples ESTIMATED** if retained. Raw car/pos streams are ~Hz
  time series versus one canonical row per driver-lap — three orders of
  magnitude. FastF1's cache grew by the telemetry blobs needed to derive
  `t0_date` (see §D5.7 storage); NO telemetry is promoted to canonical
  storage. Retention decision is D8's, informed by D8 benchmarking, not
  this section.

---

## 13. Parquet / dependency input

No engine installed (D0). **Recommendation: `pyarrow`.**
Justification: pandas 2.3.3's Parquet I/O is pyarrow-first (requires
pyarrow ≥ 10.1 for full support); NumPy 2.x support in pyarrow is solid
from the 16.x line; Python 3.11 is supported across all candidate
releases. **Strategy for D2/D3:** add `pyarrow>=16` (exact pin resolved by
a dependency-resolution + round-trip test in the D2/D3 environment, not
guessed here), keep `fastparquet` out unless a measured reason appears.
**Do NOT install in D1** (not assigned by the plan). No CSV fallback for
canonical storage.

---

## 14. Cache strategy input (for D3)

`CACHE ≠ CANONICAL RAW ≠ CANONICAL PROCESSED.` Recommendation: single
centralised helper (absolute path, no cwd dependence) configuring
`fastf1.Cache.enable_cache` at one `data/raw/fastf1_cache/` location;
document location/clearing/offline behaviour in README; keep both caches
local-only and untracked (re-apply the D0 §1 untracking before any
commit); never ingest directly from cache paths into canonical tables —
always through the versioned normalisation step. **Do not move, duplicate,
or commit the 6.6 GB cache in D1.**

---

## 15. Provenance requirements (for D2)

Every canonical row family must carry: `source` (fastf1-livetiming /
jolpica), `source_lib_version` (e.g. fastf1==3.7.0), `ingested_at`,
`season`, `round`, `event/circuit keys`, `session/type`, `api_path` or
endpoint reference, `pipeline_version`, `schema_version`, validation state.
Storage design is D2's; collection discipline starts with D3's first
ingestion.

---

## 16. Data-quality risk register (for D2/D3)

| Risk | Evidence | Severity |
|---|---|---|
| Missing TyreLife/compounds at source (Monaco22: 86%) | MEASURED probe | Medium — expected missingness, pipeline-imputed downstream today |
| Incomplete sessions (Belgium21: 60 rows; red flags/shorts) | MEASURED probe + cache | Medium — ingest + flag, never silently drop |
| Uneven cache/session completeness (telemetry present 3/6) | MEASURED listing | Medium — per-family status required (D3/D5) |
| Team renames breaking TeamId continuity | MEASURED 2019→2023 | Medium — mapping table (D2) |
| DriverNumber instability (VER 33→1) | MEASURED | High if used as key — use driverId (D2) |
| Display-name instability (event/driver/team strings) | MEASURED (São Paulo encoding, Mexico City) | High if used as key — stable IDs (D2) |
| Weather future-fallback in legacy logic | MEASURED code (§11) | High for V2 features — past-only contract (D2) |
| Speed-trap circuit variance (I1 76–100%) | MEASURED probes | Low — record missingness |
| Jolpica post-2024 field gaps (null status reports) | External issue report | Medium — validate in D4, don't assume |
| Jolpica max page 100 (vs Ergast 1000) | Provider docs | Low — page accordingly (D4) |
| Rate limits / network failures | Provider + FastF1 docs | Medium — bounded retry + manifests already precedented (D3) |
| FastF1 schema/version drift (3.7.0 pinned) | Package inspection | Medium — pin + record `source_lib_version` |
| Timing corrections / countbacks / synthetic laps | Docs + probe warnings | Medium — carry accuracy flags (D6) |
| DNS/DNF/DSQ classification edge cases | Results Status strings MEASURED | Medium — define `dnf` carefully (D6/D9) |
| Cancelled events (2020 Australia) | Absent from cache+inventory | Low — explicit exclusion list (D2) |

No incident frequencies are invented; severities reflect impact on
correctness, not observed rates.

---

## 17. D2 readiness — NO BLOCKERS

D2 (schemas + contracts) has everything it needs: verified source
capabilities per family, identifier candidates with stability evidence,
time semantics with nullability/edge cases, the weather contract,
scale bounds, the `data/v2/` namespace proposal (D0 §11), and the risk
register above. Only sequenced prerequisites (not blockers): resolve the
`pyarrow` pin when D2/D3 needs to write Parquet. (D0's transient
cache-index flag was resolved by commits `5a4001e`/`999076b`/`5e4c72c`:
HEAD holds 317 files with 0 `.ff1pkl`; keep it that way per §14.)

**D1 gate verdict (plan §D1): actual field availability is understood —
gate SATISFIED. D1 Definition of Done: achieved.**

---

## D2–D11 (COMPLETE below, plus D12 documentation/freeze/exit — Phase 1
COMPLETE and FROZEN, see `docs/PHASE1_EXIT_REPORT.md`)

## D2 — Schema & Data Contracts (COMPLETE 2026-09-08)

Machine-readable artifact: `v2/contracts.py` (stdlib-only: dataclasses +
enum; no pandas/pyarrow/fastf1 imports so contracts evaluate anywhere),
pinned by `tests/test_v2_contracts.py` (10 tests, synthetic only — no
downloaded data, no Parquet, no network). This section is the human-readable
twin; on any divergence the module governs key construction and the text
governs rationale. Legacy `data/processed`, `results/models` and
`ml/inference` paths are untouched; `data/v2/` holds no real data in D2.

### D2.1 Entity relationship overview

```text
races 1──* results        (race_id; official post-race outcomes)
races 1──* driver_laps    (race_id; one driver x one recorded lap)
driver_laps 1──* pit_stops / stints   (same race+driver; event logs)
races 1──* weather        (race_id + observed_at_s; time series)
races 1──* race_control   (race_id + message_seq; raw messages)
driver_laps 1──0/1 telemetry_summary  (same key; OPTIONAL until D8)
hist_seasons / hist_circuits / hist_drivers / hist_constructors
  └── hist_races (season, round_no) ──* hist_results
```

Tier-A entities: races, results, driver_laps, pit_stops, stints, weather,
race_control, telemetry_summary. Tier-B: hist_seasons, hist_circuits,
hist_drivers, hist_constructors, hist_races, hist_results, hist_standings.
Full per-table grains, keys, columns, units, nullability, owners and notes
are encoded in `v2/contracts.py` (`TIER_A_TABLES`, `TIER_B_TABLES`).

### D2.2 Canonical identifier strategy

Deterministic composite strings (reproducible, no UUIDs); display names,
abbreviations and driver numbers are attributes, never keys:

| Concept | Canonical key | Example | Source basis |
|---|---|---|---|
| Season | `season: int` | 2023 | schedule |
| Round | `round_no: int` (post-season stable) | 1 | schedule |
| Event | `event_id = "{season}-r{round:02d}"` | `2023-r01` | derived (round disambiguates multi-event venues) |
| Session | `session_id = "{event_id}-{code}"`, codes R/S/Q/SS/FP1-3 | `2023-r01-R` | derived |
| Race | `race_id` = Race-session id | `2023-r01-R` | derived (EVENT/SESSION/RACE-SESSION kept distinct in prose) |
| Driver | `driver_id` = Ergast slug | `max_verstappen` | fastf1-results = Ergast vocabulary (D1-measured stable 2019→2023) |
| Constructor | `(constructor_id, season)` (renames are new rows) + D4 lineage map | `toro_rosso/2019` | jolpica/fastf1 |
| Circuit | `circuit_id` slug | `albert_park` | jolpica cross-check |
| Lap | `(race_id, driver_id, lap_number)` | — | derived |
| Stint | `(race_id, driver_id, stint_number)` | — | derived |
| Pit stop | `(race_id, driver_id, stop_sequence)` (1-based) | — | derived |
| Weather obs | `(race_id, observed_at_s)` | — | derived |
| RC message | `(race_id, message_seq)` (source order) | — | derived |

`DriverNumber` is an explicitly mutable attribute (VER 33→1 measured);
`TeamId` renames get a D4 lineage table; round numbers are evaluated as
stable post-season with schedule-version provenance (§D2.8).

### D2.3 Time contract

Session-relative times are float64 **seconds** (`*_s`); absolute times are
`timestamp[ns, UTC]` (`*_utc`, only where `t0_date` exists — requires
telemetry). Canonical lap fields: `lap_number` (LAP_START),
`lap_start_s` (LAP_START), `session_time_end_s` + `lap_time_s` + sectors +
traps (LAP_END), `sector_*_end_s` (IN_LAP, sub-lap alignment),
`pit_in_s`/`pit_out_s` (IN_LAP, null = no event),
`observed_at_s` for weather/RC (source time; RC also carries verbatim
`lap_number`). Generic `time` columns are banned. Reference clocks:
session-zero for `*_s` (with documented ±10 m absolute jitter),
UTC stream time for `*_utc`.

### D2.4 Temporal availability vocabulary

`PRE_RACE | LAP_START | IN_LAP | LAP_END | POST_RACE | LABEL_ONLY |
SOURCE_METADATA` (`v2/contracts.py::Availability`). Every column of every
table carries one (tested). Notable rulings: `grid_position` is PRE_RACE
though stored in `results`; `deleted`/`is_accurate` are conservative
POST_RACE; stop/stint/weather/RC event fields are IN_LAP (knowable once the
event completes); `dnf_flag`/`winner_flag` are derived LABEL_ONLY.

### D2.5 Label separation

Outcomes live **only** in `results` (`position_final`,
`classified_position`, `position_text`, `status_text`, `points`,
`laps_completed`, `dnf_flag = (classified_position IS NULL)`,
`winner_flag`, `podium_flag`) and Tier-B `hist_results`/`hist_standings`.
`driver_laps` carries **zero** LABEL_ONLY columns (contract test asserts).
Future training joins labels deliberately by `(race_id, driver_id)`.

### D2.6 Weather / race-control contracts

Weather: past-only join (`observed_at_s <= t`), empty side → null, no
future-nearest fallback (D0/D1 rule, now contractual). Race control: raw
messages preserved verbatim (Time/Category/Message/Status/Flag/Scope/
Sector/RacingNumber/Lap); no semantic states invented in D2; consumption
rule `observed_at_s <= t`; SC/VSC derivation is a future tested transform.

### D2.7 Tyre / stint / pit contracts

Source-observed only: closed compound set
(SOFT/MEDIUM/HARD/INTERMEDIATE/WET/UNKNOWN/TEST_UNKNOWN, null stays null);
`tyre_life` carries the source quirk (includes other sessions);
`duration_s = pit_out_s − pit_in_s` is the only derived pit field;
`end_lap` null = open stint (DNF); unknown compound is never a real
compound; nothing inferred from future laps.

### D2.8 Units / types / nulls / provenance

Durations and session times seconds (`float64`); absolute UTC
`timestamp[ns,tz=UTC]`; speeds km/h; temps °C; humidity %; pressure hPa
(scale verified D1); wind direction degrees (0–359, source int); rainfall
source-bool preserved; `wind_speed` in **m/s — unit resolved in D5 from
authoritative FastF1 source metadata** (`fastf1/_api.py::weather_data`
docstring: "Wind speed [m/s]", value passed through `float()` unconverted);
nullable ints/bools/strings via Parquet-native
nulls — **no sentinels** (Ergast `-1` → null at Tier-B normalisation);
no forward-fill without an explicit temporal rule; no `_x`/`_y` suffixes.
Provenance (source, lib/API version, ingested_at, season/round/event/
session keys, api_path/endpoint, run id, schema version) lives at
**file/partition level + manifest**, not per row; row lineage reconstructs
via partition path + row key.

### D2.9 Schema versioning, layout, validation, conflicts

- Version: `SCHEMA_VERSION = 1`. Breaking = remove/rename/retype a column,
  change a key, tighten nullability. Additive = new nullable column/table.
  Old partitions stay readable; manifests/files stamp the version.
- Layout: `data/v2/processed/<entity>/season=<YYYY>/` (round-level opt-in;
  avoids thousands of ~1K-row files). Atomic unit = one season-entity file
  via temp + atomic rename; deterministic full-partition rebuilds
  (idempotent); partial writes never visible.
- Validation (for D3/D11): PK uniqueness, key-shape, lap_number ≥ 1,
  non-negative durations, driver-membership consistency, weather monotonic
  time, pit/stint ordering — severities `ERROR | WARNING | SOURCE-ANOMALY`
  (`v2/contracts.py::Severity`); unusual-but-legitimate races are flagged,
  never cleaned into normality.
- Conflicts: FastF1 owns 2018+ timing-derived fields; Jolpica is
  validation-only cross-check there (event counts, winner identity) and
  owns Tier B. Conflicts quarantine to the anomaly report with both values
  + provenance; silent overwrite is prohibited. No reconciliation logic
  in D2.
- Tier-B boundary: seven conceptual tables above; time-varying names are
  season-scoped rows; no rich lap tables pre-2018, no null-filled fake
  richness; `positionText`/`status` verbatim; standings included as
  "where useful".
- Machine-readability decision: **stdlib dataclasses + enum + contract
  tests** — smallest approach compatible with D3/D11; no Pydantic/Pandera/
  schema-file dependency introduced.
- PyArrow: **`pyarrow==25.0.1` recommended pin** (scratch-env validated on
  Python 3.11 + pandas 2.3.3 + numpy 2.4.2: nullable int/float/string/bool
  + tz-timestamp round-trip green, nulls preserved). Matches the repo's
  exact-pin policy; the `requirements.txt` addition belongs to D3 env
  setup, which re-verifies on its runner (incl. Linux CI wheels).
- Deliberately deferred: manifest module (D3), validator framework
  (D3/D11), team-lineage table (D4), telemetry-summary columns (D8),
  wind_speed unit confirmation (D3), 2018 per-family depth (D5).
## D3 — Resumable Ingestion Framework (COMPLETE 2026-09-08)

Implemented modules (all under `v2/`, coexisting with untouched legacy
paths; proven on synthetic frames + one cached session — no bulk data):

- `config.py` — `V2Paths` (explicit root; env `V2_PROJECT_ROOT`; guarded
  discovery), portable relative refs, one `configure_fastf1_cache()` helper
  reusing `data/raw/fastf1_cache` (never moved/duplicated/committed).
- `errors.py` — `ErrorCategory` (TRANSIENT/STORAGE/MISSING/ANOMALY/
  VALIDATION/CONFIG/UNEXPECTED) + `IngestionError`; only TRANSIENT/STORAGE
  are `RETRYABLE`. Orchestration never treats all failures identically.
- `retry.py` — `RetryPolicy` (default 3 attempts, deterministic exponential
  backoff, injectable sleep), `run_with_retry` returning attempt counts.
- `runs.py` — `RunRecord` (uuid run id, UTC start, source + lib version,
  schema version, scope, portable config snapshot — no absolute paths).
- `manifests.py` — JSON manifest, race-scoped units, legal-transition map:
  PENDING→{DOWNLOADING,SKIPPED}; DOWNLOADING→{COMPLETE,PARTIAL,FAILED,
  SKIPPED}; COMPLETE→DOWNLOADING force-only; FAILED/PARTIAL→{DOWNLOADING,
  PENDING} (requeue); SKIPPED→PENDING; SKIPPED requires a reason.
  Crash recovery is exclusive to `recover_stale` (claim-timestamp based);
  "output exists" never implies COMPLETE.
- `storage.py` — temp-in-place + fsync + atomic rename; deterministic
  `processed/<entity>/season=<YYYY>[/round=<NN>]/<entity>__<unit>.parquet`;
  portable relative output refs; temps cleaned on failure.
- `validation.py` — boundary only: contract-column subset, PK present/
  non-null/unique. Anything deeper is D11.
- `ingestion.py` — `run_unit` orchestration (skip-COMPLETE, retry, validate,
  atomic write, manifest update; MISSING→SKIPPED, anomaly→PARTIAL,
  validation→FAILED with no exposed output). Adapters are plain callables
  (`ctx -> AdapterResult`); only `synthetic_adapter` (`synthetic.py`)
  exists — D4/D5 plug real ones without touching the core.
- `cli.py` (`python -m v2.cli`): `validate-config`, `plan` (explicit
  `--season` + `--rounds`, refuses scopeless runs), `run` (`--unit` |
  `--all-pending`, `--force` for deterministic rebuild), `retry`
  (failed/partial → PENDING), `status`. Unknown adapters fail clearly;
  no command can default to 2018–2025 ingestion.
- Dependency: `pyarrow==25.0.1` added to `requirements.txt` (exact pin per
  repo policy; D2 validated the round-trip in scratch env).
- Tests: 40 new (manifests/retry/idempotency/storage/paths/cli), tmp-only,
  offline, no sleeps; full suite 117 passed + 4 xfailed. Cached smoke:
  2023 Bahrain via centralised config — 1056 laps/20 drivers, cache
  byte-identical.
- `.gitignore`: `/data/v2/` generated-data exclusion (code + tests tracked).
- Remains for D4/D5/D11: real adapters, Tier-B ingestion, full-season runs,
  comprehensive validation, quality reports. D3 pass criteria 1–15: all met.

## D4 — Historical Results Layer (COMPLETE 2026-09-08)

Live Tier-B ingestion 1950–2025 through the D3 core (`v2/tierb.py` season
adapter + `v2/jolpica.py` stdlib client). All figures below MEASURED from
`data/v2/raw/manifests/tierb-full.json` + the 532 canonical Parquet files
(git-ignored generated output; code + tests tracked).

### D4.1 Manifest (MEASURED)
- 76/76 units COMPLETE; 0 pending/downloading/partial/failed/skipped.
- Attempts distribution (accumulated across resume cycles): 1:35, 2:1,
  3:3, 4:28, 6:3, 7:6 — all retries bounded TRANSIENT (HTTP 429), all
  recovered; no unexplained terminal states.
- Every COMPLETE unit carries run_id, schema_version=1 and 7 output_refs.

### D4.2 Coverage (MEASURED)
- Seasons 1950–2025: 76/76 with output; 1149 distinct (season, round) races.
- Rows: hist_seasons 76; hist_circuits 1145 (77 distinct circuits);
  hist_drivers 3248 (879 distinct drivers); hist_constructors 1121
  (211 slugs × season-scoped rows); hist_results 25784; hist_standings 3819.
- Per-season race counts follow the official calendar shape (7 in 1950 …
  24 in 2024/2025). Sparse standings are source-faithful: 1952 (3 rows)
  and 1953 (8 rows) are all-null-position backmarker-only lists as served
  upstream — deterministically reproduced byte-identical on rebuild, so NOT
  ingestion truncation (see D4.6). Pre-1958 seasons have driver standings
  only (constructor championship started 1958).

### D4.3 Integrity (MEASURED)
- PK: 0 duplicates, 0 null keys in all 532 files (D3 boundary enforced).
- FK: 0 violations (results→races/drivers/constructors, races→circuits,
  standings→drivers/constructors) across all 76 seasons.
- Storage: 532 Parquet files, ~2.6 MB, exactly 7 per season, 0 temp files.

### D4.4 Operations lessons (decisions, not estimates)
- Manifest persistence: `run` now saves per unit AND persists the
  DOWNLOADING claim before network work (`on_claim` hook) — `status`
  observes live progress; kills lose nothing (proven across 3 stop/resume
  cycles). New `recover-stale` CLI exposes the D3-exclusive stale-claim
  path; `retry` requeues failed/partial. No reconciliation-by-file-exists
  was added, by design (see D4.6).
- Single retry budget: D3 owns retries (default 3); the Jolpica client
  defaults to ONE attempt and only classifies (429/timeout → TRANSIENT,
  finite 30 s timeout, Retry-After capped 60 s). Regression-pinned:
  3-attempt op ⇒ ≤3 HTTP requests.
- Rate respect: default politeness raised 0.5 s → 8.0 s after MEASURED
  429 throttling at ~1 req/s and ~0.3 req/s sustained paces; ~0.12 req/s
  completed 46 units with zero failures. No concurrent writers; stop +
  cooldown + resume on sustained 429 (used twice, manifest preserved).

### D4.5 Classification semantics (evidence, Tier-A `dnf_flag` ON HOLD)
- MEASURED over 25,784 hist_results rows: `position` is NEVER null;
  position_text codes are R (9043), W (357), D (159) — E/F/N absent
  upstream; 17,780 rows are classified-but-not-running (numeric position,
  status ≠ Finished, incl. 1727 with points > 0); 15 R-rows + 1 D-row carry
  points > 0 (shared-drive era).
- Therefore D2's provisional Tier-A `results.dnf_flag` rule ("true iff
  classified_position IS NULL") is NOT mechanically valid on Jolpica
  vocabulary — it would read false for all 9043 retirements. STOPPED as
  instructed: contract unchanged; D5 must derive dnf from official
  classification evidence (Jolpica mapping would be
  positionText ∈ {R,W,D} ⟹ unclassified, with the 16 scoring R/D rows
  adjudicated), never from null position. Tier-B correctly stores verbatim
  `position`/`position_text`/`status` only.

### D4.6 Constructor identity + orphan recovery (decisions)
- Source slugs preserved; (constructor_id, season) grain kept; 142 slugs
  span >1 season; 0 slugs rename across seasons (renames are distinct
  slugs, correctly separate rows). No cross-season lineage guessed; curated
  mapping deferred — deliberately unresolved, not silently merged.
- 57 orphaned seasons (pre-fix persistence bug) were REBUILT through the
  normal transaction, not marked complete: all 399 overlapping files
  rebuilt byte-identical (sha256), 0 content diffs, 112 files newly
  materialised (2006/2010–2022/2024/2025). Byte-identity proves the
  orphans were transactionally complete; the manifest (not file existence)
  remains authoritative.

### D4.7 Provenance (MEASURED)
- 76/76 COMPLETE units hold run_id + schema_version + 7 output_refs;
  provider (jolpica), API identity and client version are code constants.
- Known limitation: per-request fetch logs and RunRecord detail are
  run-ephemeral (not persisted) — D11 may persist run records; Tier-B
  units remain re-derivable (deterministic rebuild verified byte-identical).
- **D4** Historical Results Layer — COMPLETE (see §D4 below; measured
  Tier-B dataset 1950–2025, 76/76 units COMPLETE).
- **D5** Rich 2018–2025 Race Ingestion — COMPLETE 2026-09-08 (full measured
  Tier-A materialization; see §D5 below).
- **D6** Canonical Driver-Lap Dataset — COMPLETE 2026-09-08 (measured
  canonical driver-lap state over the full scope; see §D6 below).
- **D7** Supporting Race Data — COMPLETE 2026-09-08 (temporally-safe
  weather/race-control/pit/stint context on the canonical state; see §D7
  below).
- **D8** Telemetry Decision — COMPLETE 2026-09-08 (measured; canonical
  telemetry DEFERRED; see §D8 below + ADR-0001).
- **D9** Derived Features & Labels — COMPLETE 2026-09-08 (derived temporal
  state + separate outcome labels; see §D9 below).
- **D10** Legacy Dataset Comparison — COMPLETE 2026-09-08 (read-only audit of
  the legacy 2019–2023 checkpoint system vs V2; see §D10 below and
  `docs/LEGACY_V2_DATASET_COMPARISON.md`).

## D5 — Rich 2018–2025 Race Ingestion (COMPLETE 2026-09-08)

Tier-A Race-session ingestion through the D3 core (`v2/tiera.py` FastF1
adapter; lazy fastf1 import keeps module import and tests offline). Seven
entities per unit: races, results, driver_laps, pit_stops, stints, weather,
race_control. NO telemetry retention (D8 owns it), NO Quali/Practice/Sprint
session ingestion, NO lap-state features (D6 owns them), no `telemetry_summary`
files. Broad 2018–2025 scope materialised and validated below. All figures
MEASURED from `data/v2/raw/manifests/tiera-<YYYY>.json` + canonical Parquet.

### D5.1 Final manifest state (MEASURED)

- **173/173 eligible championship Race units terminal**: COMPLETE 171,
  PARTIAL 2, FAILED 0, SKIPPED 0, PENDING 0, DOWNLOADING 0. No stale claims,
  no temp files.
- Per season COMPLETE/PARTIAL: 2018 21/0, 2019 21/0, 2020 17/0,
  2021 21/1, 2022 21/1, 2023 22/0, 2024 24/0, 2025 24/0.
- PARTIAL units: **2021-r12-R (Belgian GP)** — shortened 3/39 laps
  (red-flag farce, half points); **2022-r18-R (Japanese GP)** — shortened
  29/53 laps (red flag + time limit). Both: source faithfully represented,
  lap rows structurally valid, materially different race shape → PARTIAL.
- Every terminal unit carries run_id, schema_version=1 and 7 output_refs
  (all files exist, project-relative paths only).

### D5.2 PARTIAL-semantics adjudication (D5 final gate)

Principle (D3, upheld): **PARTIAL means expected output is materially
incomplete; unusual F1 facts alone never imply PARTIAL.**

Before/after (all earlier proof/gate units re-adjudicated through the
corrected core, not by hand): the intermediate gate recorded **22 PARTIAL**
across the 6 cached proofs + Gate B (17 in 2021) — 21 caused by pit-pairing
quirks (entries≠exits, boundary fallbacks) and 1 by the shortened Belgian
farce. After adjudication those are **0 pit-quirk PARTIAL**:
- 16 formerly PARTIAL pit-quirk units (and 5 proof units) are now COMPLETE
  with a persisted `quality_note` on the manifest (source/domain anomaly:
  source faithfully represented, all contract outputs present/valid).
- The shortened Belgian race remains PARTIAL (material incompleteness).
- Japanese 2022 (shortened) is the only PARTIAL newly identified.
- Counts: COMPLETE 7 → 171; PARTIAL 22 → 2. 148 COMPLETE units carry
  quality notes (138 pit entry/exit mismatches, 14 stint-boundary fallbacks,
  20 verbatim out-of-set 2018 compound names such as SUPERSOFT/HYPERSOFT/
  ULTRASOFT). Quality provenance is preserved even when a unit is COMPLETE.

### D5.3 Correctness defects found and fixed (smallest, tested)

1. **Mechanical PARTIAL mapping.** The core mapped any adapter anomaly note
   to PARTIAL. `AdapterResult` now separates `anomaly_note` (quality,
   COMPLETE) from `partial_reason` (material incompleteness, PARTIAL);
   `ManifestEntry.quality_note` persists on COMPLETE units. Regression tests.
2. **Pit pairing manufactured impossible durations.** `_ordered_stops`
   paired by lap adjacency; consecutive stops can share a lap number (a car
   exits and re-enters the pits on the same lap before start/finish), which
   mis-mated entries and produced **321 negative durations (−69 s to
   −189 s)** across the dataset. Corrected to chronological FIFO pairing
   (each exit mates the latest preceding entry in session time; monotonic
   within a race, red-flag lap renumbering cannot break it). **Dataset
   result: 0 negative durations.** Regression test uses the real 2025-r01
   back-to-back stop pattern.
3. **Float-NaN → 'nan' text.** `clean_str` stringified NaN floats, so true
   missing compounds became the literal `'nan'` string (and textual missing
   tokens in 2018 flowed into quality notes). `clean_str` now returns None
   for NaN; textual `'nan'`/`'None'`/`'null'` compounds are stored as null.
   2018 compound nulls 33 → 376 (real missingness now counted correctly).
4. **FastF1 soft-fetch failures.** `@soft_exceptions` swallows per-endpoint
   fetch failures (throttle/429), leaving attributes unset so a later access
   raises `DataNotLoadedError`. Mapped to TRANSIENT so the bounded D3 retry
   (cache reuse) owns recovery.
5. **Telemetry load is required, not optional.** FastF1 derives
   `Session.t0_date` ONLY from telemetry/position streams, and
   race-control `observed_at_s` needs t0_date to convert absolute source Utc
   to the session clock. The loader therefore uses the full default load
   (telemetry cached, never promoted to canonical); `telemetry_summary`
   remains an unmaterialised shell.

### D5.4 Pit / stint dataset-wide validation (MEASURED)

- pit_stops rows **6,336**: pit_in-only 246 (entry without exit — e.g.
  retirement in pits), pit_out-only 159 (entry-less exits — pit-lane starts,
  red-flag procedures), lap_number null 159 (those out-only rows),
  **negative durations 0**, per-season pit_in/out-only: 2018 32/5, 2019 31/12, 2020 23/5, 2021 50/29, 2022 33/31, 2023 31/18, 2024 25/16, 2025 21/43.
- stints rows **9,324**: null start/end 0, overlapping stints 0, negative
  spans 0, compound null 39, unknown compound 0, tyre_age_at_start null 44.
- Nothing manufactured: the missing half of a pit stop is never inferred;
  nullability stays source-faithful.

### D5.5 Weather unit (RESOLVED — evidence-backed)

`wind_speed` unit is **m/s** per authoritative FastF1 3.7.0 source metadata:
`fastf1/_api.py::weather_data` documents “Wind speed [m/s]” and passes the
value through `float()` unconverted. Contract column unit updated from
`as-received` to `m/s` (metadata-only, no schema bump; `UNITS_TO_CONFIRM_IN_D3`
removed). Observed range across **25,779 rows: 0.0–10.1**. Wind direction is
degrees (0–359, source int). Rainfall true on 1,755 observations. No
future-nearest weather joins introduced (past-only contract unchanged).

### D5.6 Classification / DNF evidence (MEASURED, no ML target invented)

- results rows **3,458** across 173 races. `position_text` tokens: numeric
  1–20 classified (each 173 for 1–8, tapering to 20 at P20); **R 420**
  (unclassified retirements), **W 18** (did-not-start/withdrew), **D 13**
  (disqualified).
- `dnf_flag` (officially unclassified per classification token only) true on
  **451** rows; all 451 carry 0 points; **0 scoring R/D rows** in 2018–2025
  (the shared-drive-era edge is pre-2018 only). `classified_position` null 451.
- `position_final` null on exactly 3 rows (all W: FastF1 leaves DNS/withdrawn
  drivers unordered — see D5.8 cross-source difference). Final ML binary-DNF
  target policy remains deferred to the label stage; no final label added.

### D5.7 Identity validation vs D4 (MEASURED)

- Unmapped Tier-A driver ids vs D4 hist_drivers: **0**. Unmapped constructor
  slugs vs D4: **0**. Circuit lookups missing: **0**; circuit mismatches: **0**
  (D4 (season,round) key, never fuzzy).
- Race/round counts match D4 per season exactly (173/173).
- Driver-number changes across seasons (attribute, never key):
  max_verstappen 33→1; bearman, de_vries, doohan, lawson (substitute
  numbers). Constructor slug lineage is season-scoped rows in D4
  (toro_rosso→alphatauri→rb, racing_point→aston_martin) — no cross-season
  rename guessed.
- No silent fuzzy matching anywhere; identity is in-session (laps↔results on
  DriverNumber → DriverId slug) with D4 as cross-check only.

### D5.8 Cross-source results vs D4 Tier-B (MEASURED)

All **3,458** Tier-A results matched Tier-B hist_results on
(season, round, driver). Exact disagreements:
- grid 3, position 3 — all the same DNS/withdrew (W) rows
  (2021-r22 mazepin Illness, 2022-r02 mick_schumacher Withdrew, 2023-r15
  stroll Withdrew): FastF1 leaves GridPosition/Position null for drivers it
  does not order; Jolpica ranks them at the back (20 / grid 0 or 20).
  Classification token (W), status, laps, points identical → representation
  difference, not a factual conflict. Both sources kept verbatim.
- points 0, laps 0, team 0, status 0 disagreements.

### D5.9 Driver-lap quality / missingness (MEASURED, nothing imputed)

Total driver-lap rows **189,420**. Per season rows: 2018 22,337; 2019
23,676; 2020 18,352; 2021 23,758; 2022 23,577; 2023 24,422; 2024 26,606;
2025 26,692. Whole-dataset null counts (season detail in
`docs/DATASET_V2_REPORT.md`): position 294; lap_time 3,169; sector_1 4,029;
sector_2 389; sector_3 548; speed_i1 28,013; speed_i2 (larger in 2025);
speed_st 15,135; compound 1,308; tyre_life 1,504; stint_number 789;
fresh_tyre 0; pit_in 185k expected sparse; track_status 1,340 (2018
dominates: 1,317 — 2018 source status codes are sparser, concentrated in
China 2018-r03 573, Germany 2018-r11 545, Hungary 2018-r12 96, Australia
2018-r01 83).
- 2018 caveats confirmed: sector_1 nulls 480, lap_time nulls 441, speed
  traps 2,888–1,697; 2018 Pirelli compound names preserved verbatim.
- Known source gaps preserved: Monaco 2022 (tyre_life 161 null, compound 35,
  lap_time 26 of 1,179 rows); Belgian 2021 all 60 laps compound null;
  Monaco(?) 2025-r06 446 tyre_life/compound/stint null; Austrian 2022-r11
  359 tyre_life / 299 compound null; Canadian 2023-r08 35 tyre_life/compound
  null (wet); Bahrain 2025-r04 40 sector_1 nulls etc.
- rows/race range 60 (Belgian farce) – 1,534; drivers/race 18–20.

### D5.10 Race / session anomalies (reported, never normalised)

- Shortened/red-flagged: 2021 Belgium (3/39), 2022 Japan (29/53) — PARTIAL.
- 2022 Monaco wet + red-flag tyre/compound missingness preserved; 2018
  Chinese GP highest lap_time missingness (156 nulls, incident-heavy);
  DNS/withdrew rows (W) keep null FastF1 positions.
- 2018 Bahrain race-control: 69 messages without source timestamps
  (observed_at_s null, verbatim) — the only such unit in 2018–2025.

### D5.11 Race-control coverage (MEASURED)

14,992 messages; categories Flag 8,873, Other 4,906, Drs 524, SafetyCar 443,
CarEvent 246. Raw text + 0-based source order preserved; no SC/VSC
derivation, no meaning inference. `observed_at_s` null only on the 69
2018-r02 messages above.

### D5.12 Provenance + idempotency (MEASURED)

- 173/173 terminal units hold run_id, schema_version=1 and 7 portable
  project-relative output_refs (all present). No developer-specific absolute
  paths in metadata.
- Rerun of a completed season: `run --all-pending` → “nothing pending”
  (COMPLETE skip). Deterministic `--force` rebuild is byte-identical
  (unit-tested); atomic temp+rename leaves no temp files. Interrupted work
  resumes via `retry`/`recover-stale` (exercised live during 2018 after the
  throttle-era DataNotLoadedError failures — manifest preserved, cache
  reused). No stale DOWNLOADING units remain.

### D5.13 Storage / cache (MEASURED)

- Canonical Tier-A: **1,211 Parquet files (173 races × 7 entities),
  ~24 MB** (largest entity driver_laps ~15.5 MB; per season 2.35–3.35 MB;
  largest single race output 2023-r06-R ~0.17 MB). Full `data/v2` incl.
  Tier-B: 1,743 files, ~29 MB.
- FastF1 cache: 7.75 GB / 1,139 `.ff1pkl` (baseline) → **15 GB / 1,900
  blobs** after D5. Growth **~7.3 GB** is the telemetry/position blobs
  required for `Session.t0_date` (2018/2024/2025 were uncached) — cached,
  never promoted to canonical storage.

### D5.14 D6 readiness

Source ingestion needed no redesign: D6 consumes the seven contracted
entities exactly as measured above. D6 COMPLETE (see §D6 below).

## D6 — Canonical Driver-Lap Dataset (COMPLETE 2026-09-08)

Machine-readable schema: `v2/d6schema.py` (`D6_SCHEMA_VERSION = 1`);
deterministic builder `v2/d6.py` (run: `python -m v2.d6 --all --validate`);
tests `tests/test_v2_d6.py` (synthetic/offline) + `tests/test_v2_d6_realdata.py`
(real-data, session-scoped, skips when `data/v2` absent). The D6 canonical
driver-lap state dataset is what later phases (features D9, RaceState, labels
D7/D9 training construction) consume; it is built from the D5 canonical
parquet + tiera manifests — no D5 ingestion redesign.

### D6.1 Outputs (all under gitignored `data/v2/`)

- `processed/driver_lap_state/season=<Y>/driver_lap_state__d6-<Y>.parquet`
  — canonical state rows, one per (driver x race x lap).
- `processed/race_quality/season=<Y>/race_quality__d6-<Y>.parquet`
  — race-grain source-quality metadata (verbatim D5 status/notes + measured
  leader/scheduled laps). 173 rows whole scope.
- `raw/manifests/d6-canonical.json` — dataset manifest (schema version, row
  reconciliation, per-season stats, file paths, sha256 content checksums).
- `reports/data_quality/d6_schema.json` — machine-readable schema dump;
  `reports/data_quality/d6_validation.json` — measured validation (written by
  the CLI when `--validate`).

### D6.2 Canonical grain, identifiers, state_time (all MEASURED)

Grain: one observed driver x one Grand Prix race x one lap number. Source
rows map 1:1 to state rows — the build is lossless by construction and raises
(VALIDATION) instead of silently dropping an unjoinable key. Identifiers are
evidence-backed and never display names: `season`, `round_no`, `event_id`
(`{season}-r{NN:02d}`), `race_id` (`…-R`), `driver_id` (Ergast slug),
`constructor_id` (season-scoped `results.team_id_at_race`), `circuit_id`
(D4 cross-checked), `lap_number`. `driver_number` / `driver_abbreviation` are
attributes only. `state_time_s` = the source lap-end session `Time`
(`driver_laps.session_time_end_s`, renamed): the canonical clock at which the
row becomes available. Contract: **at `state_time_s`, every predictive-
eligible field on the row is observable at or before `state_time_s`**
(PRE_RACE / LAP_START / IN_LAP / LAP_END fields only). Whole-scope
`state_time_s` nulls = 0 and lap-start < state-time holds on every row (0
violations measured); `state_time_s` is strictly increasing over lap number
per (race, driver) (0 violations measured).

### D6.3 Row reconciliation + identity (MEASURED)

- input driver-lap rows **189,420**; canonical state rows **189,420**;
  dropped 0; duplicate input PKs 0; duplicate state PKs 0; null state PKs 0.
- Orphan (race_id, driver_id) driver-lap keys vs results identity: 0.
  Race lookups missing/mismatched: 0. DNS/withdrawn results drivers with no
  recorded lap add zero state rows (correctly absent).
- Distincts in the state table: drivers **43**, constructors **16**,
  circuits **31**, races **173**, seasons **8** (2018–2025).
- Identity join is deterministic and 1:1: results identity columns consumed
  are exactly `race_id/driver_id/team_id_at_race/driver_number/
  driver_abbreviation` — a label column can never enter the state table (the
  builder selects an explicit subset; tests assert the column sets).

### D6.4 Schema / label separation / availability

Full machine-readable field records (name, dtype, unit, nullable, temporal
availability, owner, source, predictive-eligible, description) live in
`v2/d6schema.py` + `d6_schema.json`. The 37 state columns carry **zero**
LABEL_ONLY columns (asserted); final outcomes stay only in the `results`
entity and are joined into training/evaluation sets by explicit later
construction only. `deleted`/`deleted_reason`/`is_accurate` are conservative
POST_RACE quality flags and `fastf1_generated`/identifiers/quality flags are
SOURCE_METADATA — all marked `predictive_eligible=False` so a future feature
schema cannot accidentally consume them. Every LAP_START/IN_LAP/LAP_END field
is predictive-eligible. No `_x`/`_y` suffixes; units follow D2/D5
(wind-speed note is irrelevant here — no weather column; state times are
seconds, speeds km/h).

### D6.5 D7/D9 boundaries honoured (deferrals)

Weather attachment, race-control context, pit/stint history joins and final
outcome (label) materialisation are **D7/D9** concerns: D6 performs none of
them and creates no predictive features. It only denormalises race-level
source-quality metadata (`source_unit_status` verbatim from the D5 manifest;
`shortened_race` = leader observed laps < scheduled, data-derived and
independent of ingestion status) and two 1:1 identity joins.

### D6.6 PARTIAL / shortened races + quality metadata (MEASURED)

- 2021-r12-R (Belgian GP, 60 rows) and 2022-r18-R (Japanese GP) remain fully
  represented: every row carries `source_unit_status='partial'`,
  `shortened_race=true`, and the race-grain table preserves the verbatim
  D5 `partial_reason`.
- `shortened_race=true` is additionally true for the three COMPLETE-but-
  time-limited races the data evidences (2022-r07 Monaco 64/77,
  2022-r17 59/61, 2020-r01 68/71) — quality metadata stays honest while
  `source_unit_status` remains verbatim 'complete'; no eligibility decision is
  made (later Model Lab/task policy decides exclusions).
- Verbose D5 `quality_note` free text is NOT repeated on every lap row: it
  lives only in `race_quality` (one row per race) so it cannot be mistaken
  for a lap feature.

### D6.7 Missingness preservation (MEASURED)

All 24 carried source observation/flag columns show **identical null counts**
in the state table vs the D5 source (0 mismatching columns whole-scope).
Representative preserved gaps re-verified per race in real-data tests:
Monaco 2022 tyre-life/compound, 2021 Belgium compound (all 60 null), 2025
Miami compound/tyre-life/stint, 2018 track status/speed traps. Whole-scope
null counts: position 294, lap_time 3,169, sector_1 4,029, sector_2 389,
sector_3 548, speed_i1 28,013, speed_i2 1,348, speed_fl 6,575, speed_st
15,135, compound 1,308, tyre_life 1,504, stint_number 789, pit_in 183,243,
pit_out 183,330, track_status 1,340. Canonical dtypes: nullable ints
(position/tyre_life/stint_number/lap_number/driver_number) are stored as
parquet `int64` with nulls (pandas nullable Int64) — uniform across all
seasons, replacing the D5 per-file float/int representation of the same
values (a dtype normalisation, never an imputation).

### D6.8 Determinism + leakage (MEASURED)

Rebuild from identical D5 source + manifest is logically identical; a real
double full build produced **identical sha256 checksums on all 16 files**.
Future-data mutation tests (synthetic, offline) prove earlier state is
unchanged when (A) weather observations strictly after `state_time`, (B)
future race-control messages, (C) laps N+1 onward, (D) final results
labels, and (E) future pit/stint evidence are mutated/deleted. Join
cardinality is proven: rows_before == rows_after == state rows and duplicate
PKs = 0 for every enrichment join.

### D6.9 Performance + storage (MEASURED)

Whole 2018–2025 canonical build ≈ **1.4 s** (16 parquet files, ~189K rows,
~173 race rows) on the developer machine; ~0.13–0.19 s per season. Output:
**16 Parquet files, ~12.5 MB** (8 state files 1.2–1.7 MB each, 8 race-quality
files ~10–17 KB each). No premature optimisation applied (single-season files
avoid thousands of tiny race files; the dataset is not distributed-scale).

### D6.10 Phase-2 consumption boundary

`v2/d6.py::state_rows_for_race(...)` is the single deterministic state-row
construction path. Phase-2 feature engineering (D9) and a future RaceState
must read the canonical `driver_lap_state` files (or rebuild a race through
`state_rows_for_race`) rather than implement a second, unrelated lap-row
construction — one implementation for offline training and future
live/replay. RaceState is NOT implemented in D6.

### D6.11 D6 gate (plan §D6) — SATISFIED

The complete driver-lap state table passes integrity validation: PK
uniqueness, FK integrity, schema conformance, label separation, timestamp
validity, deterministic rebuild, measured reconciliation, representative-race
and full-scope validation all green (see `docs/DATASET_V2_REPORT.md` Part 5).

## D7 — Supporting Race Data: temporal context integration (COMPLETE 2026-09-08)

Machine-readable schema: `v2/d7schema.py` (`D7_SCHEMA_VERSION = 1`; base
`D6_SCHEMA_VERSION = 1`); deterministic builder `v2/d7.py`
(run: `python -m v2.d7 --all --validate --coverage`); tests
`tests/test_v2_d7.py` (synthetic/offline) + `tests/test_v2_d7_realdata.py`
(real-data, session-scoped, skips when `data/v2` absent). D7 attaches
temporally-safe supporting race context to the D6 canonical driver-lap state.
It is NOT Phase-2 feature engineering: it owns the source integrations and
their temporal semantics; D9 builds tested features on top. The D6 canonical
grain, columns and `state_time_s` are preserved verbatim — D7 only APPENDS
context columns. No competing state-construction path was created: the D7
base rows are the D6 `driver_lap_state` canonical output (constructed by
`v2/d6.py::state_rows_for_race`).

### D7.1 Outputs (all under gitignored `data/v2/`)

- `processed/driver_lap_state_d7/season=<Y>/driver_lap_state_d7__d7-<Y>.parquet`
  — the D6 canonical state rows (all 37 columns, verbatim order) + 24 D7
  context columns. 8 files whole scope.
- `raw/manifests/d7-canonical.json` — dataset manifest (row reconciliation,
  per-season stats, file checksums, peak RSS, build seconds).
- `reports/data_quality/d7_schema.json` — machine-readable enriched schema
  (every column: dtype/unit/nullable/availability/owner/source/
  predictive_eligible/lineage_kind/description).
- `reports/data_quality/d7_validation.json` — measured validation.
- `reports/data_quality/d7_coverage.json` — measured attachment coverage.

### D7.2 Scope mapping (D7 mission §1; plan §D7)

| D7 output block | D5 source entity | Join key / rule | Expected cardinality | Availability |
|---|---|---|---|---|
| `wx_*` (weather as-of) | `weather` | race_id; latest obs with `observed_at_s <= state_time_s` (strict backward) | many-to-one; <=1 obs/state | IN_LAP values; obs time/age = SOURCE_METADATA lineage |
| `rc_last_message_*` | `race_control` | race_id; latest TIMESTAMPED message with `observed_at_s <= state_time_s` | many-to-one; <=1 msg/state | IN_LAP raw attrs; seq/time/age = SOURCE_METADATA lineage |
| `pit_last_*` | `pit_stops` | (race_id, driver_id); latest entry/exit event with event time `<= state_time_s` | many-to-one per side; <=1 entry + <=1 exit/state | IN_LAP source events |
| `stint_*` | `stints` | (race_id, driver_id); current stint by `stint_number == row.stint_number`; START-side facts only; guard `start_lap <= lap_number` | many-to-one; <=1 stint/state | IN_LAP start-side facts |

### D7.3 Schema / lineage model

D7 adds **24** nullable extension columns (9 weather, 7 race-control, 4 pit,
4 stint) — full machine-readable field records in `v2/d7schema.py` +
`d7_schema.json`. Two lineage kinds are written (model_feature is reserved and
absent): `source_observation` (as-of weather state samples, raw latest-RC
message attributes, pit event times/laps, current-stint start-side facts) and
`derived_temporal_lineage` (which obs/message was selected + its time +
staleness, and the race-control seq). `predictive_eligible=True` ONLY for
source_observation fields that are current-condition state samples (the 7 wx
physical quantities, current-stint compound/fresh flag). Everything
event/boundary/lineage (RC fields, pit event times/laps, stint start-lap /
tyre-age-at-start, wx observed-time/age) is `predictive_eligible=False`:
converting events into state features (counts, since-lap, active flags,
recency) is D9 work with leakage tests. The enriched table carries ZERO
LABEL_ONLY columns (asserted). Enriched PK = D6 PK
`(race_id, driver_id, lap_number)`.

### D7.4 Temporal join rules (all MEASURED, whole scope)

- **Weather — strict backward/as-of only.** Latest observation with
  `observed_at_s <= state_time_s`; no prior observation -> weather fields
  null (no future-nearest, no interpolation, no smoothing, no wetness score,
  no trends). Lineage: `wx_observed_at_s` + `wx_age_s` (staleness).
- **Race control — latest timestamped message at/before the clock.** The
  message's raw seq/lap/category/flag/text are attached verbatim. NO counts,
  NO active-state interpretation (SC intensity / severity / etc. are D9).
  Untimestamped messages never attach and are never invented into history.
- **Pit — as-of entry/exit events.** Only events with `pit_in_s`/`pit_out_s`
  `<= state_time_s` attach. Asymmetric source boundaries preserved
  (pit_in-only 246 / pit_out-only 159): an in-only stop contributes an entry
  but no exit; the missing side is never manufactured. Exit-event laps are
  resolved 1:1 from the canonical lap carrying that `pit_out_s`. No counts,
  no next-pit, no eventual-stop exposure.
- **Stint — current-stint START-side facts only.** Matched by the row's own
  `stint_number`; start lap, fitted compound, fresh flag and tyre-age-at-start
  attach. A source stint's eventual `end_lap`/exit boundary is FUTURE
  information at earlier in-stint states and is NEVER attached; earlier
  compounds are never inferred from later stints; tyre age is never backfilled
  from future laps.

### D7.5 Grain / reconciliation / integrity (MEASURED)

- D6 base rows **189,420** → D7 enriched rows **189,420**; row delta **0**;
  duplicate enriched PKs **0**; null PKs **0**; race set identical to D6
  (**173/173**); column order exactly the D6 schema then the 24 extensions.
- Temporal violations whole scope **0**: `wx_observed_at_s`,
  `rc_last_message_observed_at_s`, `pit_last_in_s`, `pit_last_out_s` all
  `<= state_time_s`; `stint_start_lap <= lap_number`; weather/RC staleness
  non-negative. Enforced per-family by as-of construction and re-asserted in
  validation.
- Missingness preserved: weather rows with no prior obs stay null (0 whole
  scope — every state has a prior obs); 789 states carry no current-stint
  context (exactly the D6 `stint_number` nulls, e.g. 2025 Miami 446,
  2018 Germany 21); current-stint compound nulls mirror source stint
  compound nulls (39 source rows). Nothing is imputed or repaired.

### D7.6 Coverage (MEASURED; reported as coverage, not model metrics)

- **Weather:** 189,420/189,420 states carry a prior weather observation
  (100%: every race has an obs before its first lap-end); staleness min 0 s,
  mean ~30.2 s, p50 ~30.1 s, p95 ~57.1 s, max **477.3 s**. Per-season
  coverage fraction 1.0 in all 8 seasons. Source-gap anomalies (large
  staleness, no data missingness): 2020-r01-R (100 rows >60 s, max 477 s),
  2023-r14-R (27 rows >60 s, max 339 s), 2018-r09-R (9 rows, max 92 s) —
  honest source gaps, never repaired.
- **Race control:** 14,992 source messages (14,923 timestamped, 69
  untimestamped — all in 2018-r02-R). 10,359 distinct messages attached at
  least once (a message only becomes 'latest' for a state if no newer message
  precedes it; messages superseded between state times legitimately never
  attach). 188,396 states carry RC lineage across 172 races; 1,024 states do
  not (998 = all of 2018-r02-R, whose messages have no source timestamps;
  26 = 2020-r11-R early laps before the first timestamped message). Temporal
  violations 0. The 2018-r02-R limitation is documented and intentional: the
  69 messages stay in the source `race_control` table verbatim and are never
  assigned to laps.
- **Pit/stint:** 134,314 states carry observable pit history (pit_last_in on
  131,894; pit_last_out on 131,211); 188,631 states carry current-stint
  context. Source pit boundaries preserved: full 5,931, pit_in-only 246,
  pit_out-only 159. 2,898 states have an unpaired observable entry as their
  most recent pit event (entry without an observable exit — source-faithful,
  includes retirements in the pits). 0 future-end exposure; temporal
  violations 0.

### D7.7 Determinism + leakage (MEASURED)

- Double whole-scope rebuild: identical sha256 on all 8 files.
- Synthetic mandatory tests (30, offline): weather A/B/C/D/E/F/G; RC
  latest-timestamped + untimed never-invented + future-message no-effect +
  deterministic tie-break; pit future-event mutation/deletion/addition no
  effect on earlier state; same-lap boundary; asymmetric in-only/out-only
  preserved; stint eventual-end/future-compound mutation no effect on earlier
  in-stint state; no tyre-age backfill; source-order shuffles produce
  identical output; a consolidated future-mutation suite at a state cutoff
  across weather/race-control/pit/stint/future-laps/final-results proves
  earlier state is unchanged.

### D7.8 Performance + storage (MEASURED)

Whole 2018–2025 D7 build ≈ **8.0 s** (0.78–1.12 s/season), peak RSS ~326 MiB,
output **8 Parquet files, ~17.3 MB** (2.0–2.4 MB/season). Enrichment is
straightforward pandas as-of logic over the small per-race populations — no
distributed infrastructure introduced.

### D7.9 Phase-2 consumption boundary

`v2/d7.py::enrich_race_state(...)` is the single deterministic D7 enrichment
path (pure, per-race, reusable for the full build, one race, or a state-time
cutoff). Future RaceState/replay can rebuild a race through
`d6.state_rows_for_race(...)` then `d7.enrich_race_state(...)`; D9 features
consume the D7 enriched state (or the D5 canonical supporting tables) and
implement their own definitions + leakage tests. RaceState / Replay / Monte
Carlo / Strategy / Phase-2 features are NOT implemented in D7.

### D7.10 D7 gate (plan §D7) — SATISFIED

Supporting tables have documented schemas and temporal semantics and the
time-safe as-of integration is measured end-to-end: D6 grain preserved exactly
(189,420 → 189,420), every attachment at-or-before `state_time_s` (0
violations), weather backward-only, untimestamped RC never invented, future
pit/stint facts cannot leak (mutation tests green), missingness honest,
PARTIAL races represented, schema/lineage machine-readable, deterministic
rebuild byte-identical, full-scope build validated, performance measured,
generated outputs outside Git, D6 regressions green. D9 can proceed without
redesigning the temporal joins.

## D8 — Telemetry Decision: measurement + retention decision (COMPLETE 2026-09-08)

D8 is a DECISION stage (plan §31 / §D8). Evidence + candidate-summary
prototype: `v2/d8.py` (offline, read-only over the cache); reproducible
machine-readable measurement
`data/v2/reports/data_quality/d8_telemetry_sample.json`; decision record
`docs/adr/ADR-0001-telemetry-retention.md`; offline tests
`tests/test_v2_d8.py`. **Decision: DEFER telemetry from the canonical Phase-1
dataset (Option D).** No canonical telemetry Parquet is created; the FastF1
cache (≈16.2 GB, untracked) stays the recoverable raw/source layer;
`telemetry_summary` remains an explicitly INACTIVE contract; D9 must not
depend on telemetry. Broad/raw canonical retention is NOT implemented
(requires explicit approval per plan §D8).

### D8.1 Representative sample (MEASURED)

8 already-cached Race sessions (one per plan bucket): 2018-r11 Germany,
2019-r11 Germany (wet), 2021-r10 Britain (sprint), 2021-r12 Belgium
(shortened), 2022-r07 Monaco, 2023-r01 Bahrain, 2024-r01 Bahrain, 2025-r06
Miami. Sample scope: 8 races · 20 cars each · **7,710 canonical driver-lap
windows covered (7,710/7,710, 0 zero-sample)** · **6,776,940 telemetry
samples**.

### D8.2 Channels / units (MEASURED)

`car_data` streams carry `Time` (session-relative; aligned to the D6 state
clock — verified), `Date` (UTC), `RPM` (rpm), `Speed` (km/h), `nGear`,
`Throttle` (raw %, up to ~104), `Brake` (bool), `DRS` (raw int code),
`Source`. Channel null rates 0 across the sample. `position_data` carries
`X/Y/Z` (metres), `SessionTime`, `Time`, `Date`, `Status`, `Source`. Car data
exists for 172/173 sessions whole scope (2018-r02 has none); position data for
171.

### D8.3 Scale / cost (MEASURED; whole-scope figures PROJECTED where labelled)

Median samples/lap by race 320–872; **≈59 measured bytes/sample** of cached
car_data; per-race car blob 30–84 MB; load+aggregate ≈0.3–0.4 s/race measured;
8-race run peak RSS ≈510–550 MiB. Whole scope (PROJECTED, linear
extrapolation): car_data 7,206 MB across 172 sessions + position_data 7,072 MB
across 171 (file-size MEASURED); a lap-grain summary build over all 189,420
state rows would cost roughly ≈1 minute of aggregation from the cache and a
few-MB table (Option B cost). No whole-scope sample-count claims are made from
the 8-race sample.

### D8.4 Candidate lap-level summaries evaluated (sample; NOT materialized)

A small set with exact formulas (`v2/d8.py::summarize_lap`): sample_count,
speed max/mean/p95 (km/h), rpm mean/p95, throttle-pressed fraction (>0),
brake fraction, DRS-active fraction (raw code==1), gear-change count — all
computed on `[lap_start_s, state_time_s)` (LAP_END availability; no
future-lap/future-race data). Computability 100% on sample windows with
plausible ranges. **Data-quality caveat:** raw `DRS` semantics are
era-inconsistent (within-window code==1 fraction 0.06–0.61 across sample
races; wet 2019 shows 0.61 despite DRS being disabled in rain; codes 2/3/8/
10/12/14 also occur), so a trustworthy DRS feature needs track-zone
validation, not naive raw-code use.

### D8.5 Utility assessment (model vs product, separated)

- **Model utility:** no Phase-1/Phase-3 requirement depends on telemetry; a
  predictive-utility experiment was deliberately skipped (allowed by the D8
  brief) because it would expand D8 into Model-Lab territory for a signal D9
  does not consume; revisit trigger #1 covers a future bounded Phase-3 test.
- **Product utility (replay / track / Race Engineer):** served better by the
  cache + a future dedicated track/replay asset pipeline than by canonical
  duplication. Raw `position_data`/`car_data` (≈7.1 + ≈7.2 GB whole scope)
  would be duplicated unnecessarily if canonicalised now; nothing is built.
- **Temporal contract:** any future lap summary must use only
  `[lap_start_s, state_time_s)`; future-telemetry mutation test green
  (`tests/test_v2_d8.py`).

### D8.6 Storage options compared

A (broad canonical summaries), B (small lap-grain telemetry_summary), C
(selective rich for a narrow case), D (defer). Estimated canonical storage:
A/B small (few–<10 MB) but speculative; C medium; D zero. Extract/build: B
cheap (measured ≈0.3–0.4 s/race). Decision = D: no canonical consumer, no
product requirement in Phase 1, era-robustness work (DRS etc.) belongs to a
stage that needs the feature, and deferral is low-regret (Option B remains
cheap to activate). See ADR-0001 for full rationale + revisit triggers.

### D8.7 D8 gate (plan §D8) — SATISFIED

Telemetry availability measured on representative data; channels/units
documented; scale/cost measured + honestly projected; temporal safety defined;
candidate summary set evaluated; model vs product utility separated; storage
alternatives compared; evidence-backed ADR written (ADR-0001); no canonical
telemetry data created; cache safe (size unchanged across D8 runs) and
untracked; regressions green; D9 knows telemetry is unavailable/deferred.

## D9 — Derived Temporal State + Outcome Labels (COMPLETE 2026-09-08)

Machine-readable schema: `v2/d9schema.py` (`D9_SCHEMA_VERSION = 1`; base
`D7_SCHEMA_VERSION = 1`); deterministic builder `v2/d9.py`
(run: `python -m v2.d9 --all --validate`); tests `tests/test_v2_d9.py`
(18 synthetic/offline) + `tests/test_v2_d9_realdata.py` (8 real-data,
session-scoped, skips when `data/v2` absent). D9 implements ONLY the
foundational deterministic derived state and outcome-label layer assigned by
plan §D9 (§§9.6/10/12/34 semantics). Phase-2 feature families are NOT
implemented; telemetry remains deferred (ADR-0001).

### D9.1 Outputs (all under gitignored `data/v2/`)

- `processed/driver_lap_state_d9/season=<Y>/driver_lap_state_d9__d9-<Y>.parquet`
  — the D7 enriched canonical state (all 61 columns verbatim) + **10 D9
  derived temporal-state columns**. 8 files, ~17.6 MB.
- `processed/race_driver_labels/season=<Y>/race_driver_labels__d9-<Y>.parquet`
  — the physically separated outcome-label layer (one row per race × driver).
  8 files, ~0.09 MB.
- `raw/manifests/d9-canonical.json`, `reports/data_quality/d9_schema.json`,
  `reports/data_quality/d9_validation.json` (validation + cross-source).

### D9.2 Derived-state fields (implementation map)

| Field | Source | Formula | Availability | Eligible |
|---|---|---|---|---|
| `track_state` | D6/D7 `track_status` code | last code char → token (FastF1 3.7.0 mapping: 1 all_clear · 2 yellow · 4 safety_car · 5 red_flag · 6 vsc · 7 vsc_ending) | IN_LAP | yes |
| `flag_yellow` / `flag_safety_car` / `flag_red` / `flag_vsc` | `track_state` | equality; vsc = vsc\|vsc_ending | IN_LAP | yes |
| `race_leader_laps_at_state` | lap_number, state_time_s | max completed lap with state_time <= row state_time | LAP_END | yes |
| `race_progress_frac` | leader laps, total_laps_scheduled | leader / scheduled | LAP_END | yes |
| `pit_stops_completed_so_far` | D5 pit_stops (full stops) | count pit_out_s <= state_time_s | LAP_END | yes |
| `laps_since_last_pit_stop` | D5 pit_stops (full stops) | lap_number − exit lap (≤ state_time) | LAP_END | yes |
| `stint_lap` | D7 `stint_start_lap` | lap_number − stint_start_lap + 1 | LAP_END | yes |

Grain preserved exactly: **D7 189,420 → D9 189,420** (delta 0). Every field is
computable at/ before `state_time_s` (state_time contract unchanged). Unknown/
missing source values → null (never invented certainty).

### D9.3 Race-control decision (source-derived flags, no message state machine)

D7 deliberately kept raw latest-message context. D9 does NOT build a
message-text state machine: FastF1 3.7.0 already broadcasts an authoritative
per-lap `TrackStatus` code channel (documented in
`fastf1.api.track_status_data`), carried verbatim into D6/D7 as `track_status`
(IN_LAP). D9 converts the code in effect at the lap boundary (LAST character
of the per-lap string, appended chronologically as FastF1 scans status
changes) into deterministic contemporaneous flags. This avoids guessing
ambiguous message semantics (SC/red-flag end timing, sector-local yellows)
and keeps the 69 untimestamped 2018-r02 messages unused for reconstruction.
Whole-scope token counts: all_clear 170,989 · yellow 6,541 · safety_car 8,237
· red_flag 310 · vsc 1,643 · vsc_ending 360 · null 1,340 (2018 source
track_status sparsity preserved).

### D9.4 Outcome-label layer (physically separate)

Grain: one race × one driver — the official 2018–2025 result population.
Source: authoritative FastF1 official `results` (D5); never inferred from the
final observed lap; D4 Tier-B used only as a read-only cross-check (never
overwritten). Columns (all LABEL_ONLY / POST_RACE, predictive_eligible=False):
`position_final`, `classified_position`, `position_text`, `status_text`,
`points`, `laps_completed`, and derived facts `classified_flag`
(classified_position not null), `winner_flag` (position_final==1),
`podium_flag` (position_final in 1..3), `points_finish_flag` (points > 0,
incl. half-points shortened races).

**DNF decision:** the binary modelling target is DEFERRED. Factual
classification is preserved (`classified_flag`); `results.dnf_flag` stays
provisional unclassified evidence, NOT a task target. Phase 2/3 must define
any reliability policy.

### D9.5 Validation + labels (MEASURED)

- State: 189,420 rows; duplicate PKs 0; null PKs 0; LABEL_ONLY outcome
  columns present 0; temporal violations 0 (leader-laps≥own-lap, progress in
  [0,1], laps-since≥0, stint_lap≥1, flag-consistency).
- Labels: 3,458 rows (per season 420/420/340/440/440/440/479/479); duplicate
  PKs 0; null PKs 0. Winners 173 (exactly one per race, 0 exceptions); podium
  rows 519; points-finisher rows 1,730; classified 3,007; unclassified 451
  (R 420 / W 18 / D 13). Final position null on exactly the 3 DNS/withdrawn
  rows (2021-r22 mazepin, 2022-r02 mick_schumacher, 2023-r15 stroll).
- Cross-source vs D4 Tier-B (3,458 compared, all matched): position_final
  disagreements 0 on non-null rows; the known 3 FastF1-null / Jolpica-ranked
  W rows are REPORTED (`fastf1_null_jolpica_ranked`), never overwritten;
  position_text disagreements 0; points disagreements 0.
- PARTIAL/shortened races represented: 2021 Belgium 60 rows, 2022 Japan 507
  rows, Monaco 2022 etc. with D6 quality metadata intact.

### D9.6 Leakage boundary + determinism + performance (MEASURED)

- 18 synthetic offline tests incl. track-code mapping/unknown-honesty, flag
  consistency, leader-laps past-only/ties, pit future-stop mutation (earlier
  rows unchanged; in-only/out-only never counted), stint-lap guard, label
  facts/no-DNF, and the final-result mutation boundary (state unchanged,
  labels change). Consolidated future-mutation suite at a state cutoff
  (future laps / pit stops / stint facts / results) proves earlier derived
  state identical. 8 real-data tests over representative races (2023 Bahrain,
  2019 Germany wet, 2022 Monaco, 2021 Belgium, 2021 Britain, 2022 Japan, a
  2018 race, 2024 Bahrain, 2025 Miami) + the telemetry-deferred invariant.
- Deterministic double whole-scope rebuild: identical sha256 on all 16 files.
- Performance: full build ≈4.6 s (0.43–0.68 s/season); peak RSS ≈367 MB; 16
  Parquet files ≈17.7 MB total.

### D9.7 D9 gate (plan §D9) — SATISFIED

Leakage tests pass; derived state grain 189,420→189,420; state_time contract
valid; state carries zero LABEL_ONLY outcomes; labels are separate, factual,
evidence-backed with the binary DNF target deferred; telemetry deferred;
173-race build validates; deterministic rebuild; PK/FK/label integrity clean;
Phase-2 feature families absent; PARTIAL races represented; performance
measured; generated outputs outside Git; regressions green. D10 can compare V2
vs legacy without redesigning D9.

## D10 — Legacy Dataset Comparison (COMPLETE 2026-09-08)

Read-only audit of the frozen legacy 2019–2023 checkpoint system against V2:
pure analysis utility `v2/d10.py` (`python -m v2.d10`), machine-readable
evidence `data/v2/reports/data_quality/d10_legacy_comparison.json`
(gitignored), human report
`docs/LEGACY_V2_DATASET_COMPARISON.md`, offline tests `tests/test_v2_d10.py`.
No legacy file, model, or V2 semantic was changed; nothing retrained.

### D10.1 Inventory (MEASURED)

Seven tracked CSVs: 5 ACTIVE base checkpoint datasets (lap5/10/15/20/25,
17 cols each; 2019–2023; lap10 has 2,067 rows / 104 races, the others
1,918–1,996 rows / 103 races; 33 drivers; exactly one winner row per race;
0 duplicate keys) + lap-10 weather variant (2,075 rows, 25 cols, INACTIVE —
no consumer) + lap-10 Bahrain snapshot (20 rows, value-equal to base except
the event-name string, INACTIVE). Active serving models: 15 checkpoint slots
(`{logreg,hgb,xgboost}_lap{5,10,15,20,25}_multilap`), all serving tuned
pipelines; recorded GroupKFold CV summaries exist per slot.

### D10.2 Findings that matter

- **lap-10 gap column is broken by construction**: stored gaps use the
  session-minimum reference (not the leader) and the `[0,300]` cleaning clip
  then censors 672/2,067 base rows (32.5%) and 764/2,075 weather rows at
  exactly 300.0 (2019 Belgium lap10 is 20/20 rows at 300). lap{5,15,20,25}
  follow the documented position-1 rule instead. The correct per-state gap is
  deferred to Phase 2 (not rebuilt in D9/D10).
- **lap-10 grain is not uniform**: 1,971/2,067 rows match V2 lap-10 states
  exactly; 96 rows have no lap-10 V2 row but share an exact session-time V2
  row at laps < 10 (retired-driver latest-≤10 rows, incl. all 20 Belgium farce
  rows = drivers' lap-3 rows). lap{5,15,20,25} map 100%.
- **track_status numerics are mangled**: 776 rows carry multi-char codes
  coerced to ints (`'41'→41`, `'124'→124`); V2 keeps verbatim codes + D9 flags.
- **Value equality elsewhere**: on 9,775 matched rows, driver identity,
  position, session/lap time, compound, tyre life, stint, fresh flag and both
  pit markers agree exactly; missingness is identical (no legacy imputation).
- **Weather future-fallback**: confirmed-risk code, but 0 confirmed rows in
  the shipped data (1,995/2,075 observations recovered with `observed_at_s <=
  leader_time`; the 80 unmatched rows are all 2019 Mexico with a
  single-channel wind-direction offset = upstream-source difference).
- **Labels**: 2,069 distinct race-drivers constant across checkpoints, all
  matched to D9 labels with 0 mismatches; 11 V2-only first-lap-DNS/retirement
  rows have no legacy observation (expected coverage difference).
- **Evaluation**: 5-fold GroupKFold by race (recorded per-slot top-1/top-3 /
  logloss, e.g. lap25 LR .688/.912/.095), pooled full-data refit; race-group
  separation is valid but NOT chronological backtesting. Probabilities are
  independent per-driver binary scores (2023 Bahrain tuned XGB sums ≈0.91,
  not a race distribution); ensemble = latest-checkpoint majority vote with
  XGBoost tie-break/confidence. Legacy models cannot consume V2 (schema,
  grain, semantics differ) — no shims, by plan.

### D10.3 D10 gate (plan §D10) — SATISFIED

No unresolved high-impact discrepancy: every legacy column is classified
(A–F, no G), every significant difference is explained (matching / expected
difference / legacy issue / upstream-source difference; no new-pipeline
issue), the comparison is reproducible, and legacy/V2 behaviour is unmodified.
D11 can validate Phase 1 without reopening the legacy architecture.

- **D6** Canonical Driver-Lap Dataset — COMPLETE (see §D6 above).
- **D7** Supporting Race Data — COMPLETE (see §D7 above).
- **D8** Telemetry Decision — COMPLETE 2026-09-08 (measured; decision:
  DEFER canonical telemetry; see §D8 above + ADR-0001).
- **D9** Derived Features & Labels — COMPLETE 2026-09-08 (derived temporal
  state + separate outcome labels; see §D9 above).
- **D10** Legacy Dataset Comparison — COMPLETE 2026-09-08 (read-only audit;
  no behaviour changed; see §D10 above + comparison doc).
- **D11** Full Validation & Quality Report / `docs/DATASET_V2_REPORT.md` —
  COMPLETE 2026-09-08 (44 findings, 0 failed, 0 unresolved BLOCKERs; see
  `docs/PHASE1_FINAL_VALIDATION.md`).
- **D12** Documentation & Phase Exit — COMPLETE 2026-09-08 (data README,
  root README, Phase-2 handoff, freeze, exit report; see
  `docs/PHASE1_EXIT_REPORT.md`).
