# F1 Intelligence v2 — Data Platform (Phase 1, COMPLETE & FROZEN)

> Phase-1 status: **COMPLETE** (D0–D11, final validation: 44 findings,
> 0 failed, 0 unresolved BLOCKERs — see `docs/PHASE1_FINAL_VALIDATION.md`).
> This document is the data-platform README and the **Phase-2 handoff**.
> Nothing here changes data semantics; the frozen contracts live in `v2/`.

## 1. What the data platform is

Two complementary canonical datasets built from official sources:

- **Rich Tier-A (2018–2025):** per-lap timing, tyres, pits, weather,
  race control and results for **173 championship Race sessions**,
  normalized into typed Parquet and enriched into a leakage-safe
  lap-end state history — **189,420 canonical driver-lap states**.
- **Historical Tier-B (1950–2025):** seasons, circuits, drivers,
  constructors, races, results and standings metadata — **76 seasons,
  1,149 races, 25,784 result rows** — for identity cross-checks and
  past-only historical context.

## 2. Source systems (roles)

- **FastF1 3.7.0 (pinned) → rich Tier-A.** Race timing/context for
  2018–2025 Race sessions only. It does *not* provide rich lap telemetry
  for pre-2018 F1, and its historical Ergast interface is a thin
  results mirror, never a lap source.
- **Jolpica / Ergast-compatible API → historical Tier-B.** Seasons,
  circuits, drivers, constructors, races, results, standings 1950–2025.
  For 2018+ it is a validation cross-check only; FastF1 owns rich fields.
- **Legacy V1 checkpoint CSVs + saved pipelines** (`data/processed/lap*/`,
  `results/models/`, `ml/`, `api/`) are a **frozen regression baseline**,
  not V2 inputs. See `docs/LEGACY_V2_DATASET_COMPARISON.md`.

Source limitations are recorded per stage (2018 sparsity, PARTIAL races,
DNS/withdrawn rows, 2018-r02 untimed race-control, weather staleness gaps;
see `docs/DATASET_V2_REPORT.md`).

## 3. Canonical entities (`data/v2/processed/`)

Tier-B: `hist_seasons`, `hist_circuits`, `hist_drivers`,
`hist_constructors`, `hist_races`, `hist_results`, `hist_standings`.
Tier-A: `races`, `results`, `driver_laps`, `pit_stops`, `stints`,
`weather`, `race_control` (all per-race files under
`season=<YYYY>/`). Derived: `driver_lap_state` (D6), `race_quality` (D6),
`driver_lap_state_d7` (D7), `driver_lap_state_d9` (D9),
`race_driver_labels` (D9). `telemetry_summary` is **INACTIVE by ADR-0001**
(no data, must stay that way unless the ADR is revisited).

## 4. Canonical state grain and clock

- **Grain:** one row per `(race_id, driver_id, lap_number)` — one driver ×
  one race × one observed lap. D6 → D7 → D9 preserve it exactly (189,420).
- **Clock:** `state_time_s` = the lap-END session-relative `Time` (D6,
  unchanged by D7/D9). Every predictive-eligible field is computable from
  information observable at or before `state_time_s`; availability contracts
  (`PRE_RACE / LAP_START / IN_LAP / LAP_END / POST_RACE / LABEL_ONLY /
  SOURCE_METADATA`) are machine-readable in `v2/contracts.py`,
  `v2/d6schema.py`, `v2/d7schema.py`, `v2/d9schema.py`.
- **Label separation:** final outcomes live ONLY in `race_driver_labels`
  (3,458 rows, race×driver grain). State tables carry zero `LABEL_ONLY`
  fields (asserted in tests and in the D11 gate).

## 5. Generated-data locations (all ignored by Git)

- Canonical Parquet: `data/v2/processed/<entity>/season=<YYYY>/`
- Ingestion manifests: `data/v2/raw/manifests/` (`tierb-full.json`,
  `tiera-<YYYY>.json`, `d6/d7/d9-canonical.json`)
- Validation evidence: `data/v2/reports/data_quality/` (`d6/d7/d9`
  validation+coverage, `d8_telemetry_sample.json`,
  `d10_legacy_comparison.json`, `d11_validation.json`)
- **FastF1 cache is not data:** `data/raw/fastf1_cache/` (~16.16 GB) is
  local-only source infrastructure (session blobs + HTTP cache). Never
  quote it as dataset size; never commit it. Canonical processed data is
  ~74.1 MB (D11 measurement).

## 6. Build / validate / inspect (real commands)

```bash
python -m v2.d6 --all --validate        # canonical lap state
python -m v2.d7 --all --validate --coverage   # temporal enrichment
python -m v2.d9 --all --validate        # derived state + labels
python -m v2.d10                        # legacy comparison audit (read-only)
python -m v2.d11                        # final validation gate
python -m v2.cli plan --season YYYY --rounds N [N ...]   # bounded scope
V2_ALLOW_NETWORK=1 python -m v2.cli run --adapter fastf1 --unit <race-id>
python -m v2.cli status --manifest tiera-<YYYY>.json    # read-only
```

Full rich rebuilds require network, take substantial time, and grow the
local cache — do not casually rerun them if the cache already exists.
Validation-only commands (`status`, the `d10` audit, pytest) need no network
(D11 verified validators never import fastf1).

## 7. Manifests and reports

`data/v2/raw/manifests/` records per-unit status
(`COMPLETE` 171 + `PARTIAL` 2 for Tier-A; 76/76 COMPLETE for Tier-B),
provenance (run id, schema version, 7 output refs) and quality notes.
The manifest — never file existence — is authoritative. Reports under
`data/v2/reports/data_quality/` are the measured evidence behind
`docs/DATASET_V2_REPORT.md`.

## 8. Telemetry decision (ADR-0001, authoritative)

Canonical telemetry is **DEFERRED**: no telemetry Parquet exists, and Phase 2
must not depend on telemetry by default. The FastF1 cache remains the
recoverable raw layer. Revisit only via the ADR's explicit triggers.

## 9. Known limitations (consolidated)

PARTIAL races (2021 Belgium, 2022 Japan — kept, never synthesized); 2018
TrackStatus sparsity; 69 untimestamped race-control messages in 2018-r02
(never invented into history); source weather staleness gaps; 3 FastF1-null
final positions; telemetry deferred; no binary DNF target; no Phase-2
rolling/relative/degradation/traffic/prior/strategy features; no
chronological Model-Lab evaluation yet; no V2 production prediction model yet.

## 10. What Phase 2 should consume — Phase-2 input contract (authoritative)

**Primary state: `driver_lap_state_d9`** — grain
`(race_id, driver_id, lap_number)`, 189,420 rows in the accepted build,
clock `state_time_s = LAP_END`. Phase-2 features may use only information
observable at or before that `state_time`.

**Labels: `race_driver_labels`** — grain `(race_id, driver_id)`, 3,458 rows.
Join explicitly for training/evaluation; never part of canonical state.

**Allowed sources:** D9 state; D5 normalized supporting tables where a new
temporal feature genuinely needs source history (with its own temporal
contract + future-mutation tests); D9 labels only in explicit target
construction; Tier-B history for past-only priors/context. Do not bypass
canonical state semantics casually.

**Telemetry:** `telemetry_summary = INACTIVE` (ADR-0001). Do not depend on
telemetry; do not activate it here.

**DNF:** no binary reliability target was defined. `status != Finished`,
null position, and R/W/D tokens are NOT interchangeable DNF labels — a later
phase needs a separate documented task policy.

**Gap to leader:** legacy `gap_to_leader_seconds` is NOT authoritative
(D10: min-reference + clipping defects). Rebuild with correct temporal
semantics in Phase 2; do not copy the legacy implementation.

**Phase-2 entry conditions:** start only from this contract. Every feature
must declare source fields, temporal availability, formula/unit/missingness,
avoid post-state information, carry future-mutation leakage tests, preserve
training-serving parity, and be registered in the feature registry (Phase-2
scope, not created here).
