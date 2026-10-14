# V3.10F — Sector/Lap + Tyre-Stint Telemetry

Historical, causal, selected-driver telemetry behind progressive disclosure.
Answers: where did this driver gain/lose time, and what tyre/stint evidence
is known at the replay state. Not modelling, not strategy, not MC2.

## Source

Frozen D9 corpus (`driver_lap_state_d9`) + `stints` entity. Full audit:
`results/v3/v3_10f/telemetry_source_audit.json` (149 races, 162,728 laps).

- Replay payloads carry NO lap_time/sector fields (verified) — estimation
  from frame deltas is forbidden, so one race-scoped read-only endpoint was
  required: `GET /v2/races/{race_id}/replay/telemetry`
  (`api/v2_telemetry_{schemas,service,routes}.py`; additive, firewall-tested).
- Observation boundary: lap row `state_time_s <= T`. The replay frame grid
  IS the unique `state_time_s` grid, so every lap row's own time is a frame
  anchor time. One restart tie in 2,973 driver-races (2021-r08-R stroll
  laps 4/5); ordered by lap number.
- Lap time coverage 98.27%; S1 97.84% (lap-1 S1 always null — standing
  start); compound 99.51%; stint 99.79%. 2,540 rows carry sectors without a
  lap time (shown factually).

## Causal rules

- **Completed laps only.** Final lap_time/S1/S2/S3 reveal together at the
  lap boundary. IN_LAP sector-end timestamps exist but are not exposed.
- **Reference = best completed lap so far** (min over `<=T`, synthetic rows
  excluded). Deleted status is POST_RACE and must not filter; pit/SC laps
  are not excluded (a pit lap can never be the minimum). No future baselines.
- **Deltas are descriptive** (`S1 +0.112 vs best LAP n`). No qualitative or
  causal language anywhere.
- **Stints:** completed (`end_observed <= T`) show full ranges; active shows
  only frame-known facts (compound from frame state, start lap, stint age);
  future stints — including their count — are hidden.
- **In-progress lap** shows its number with values unavailable, only while
  the replay advances and the driver is within a lap of the leader. No
  retirement inference (no causal signal exists).
- **Missing** stays null (`—`), never zero. Raw `tyre_life` includes
  other-session laps — the UI says STINT AGE, never tyre age.

## Product

Selected-driver region, after intelligence: `TELEMETRY` with native
`[LAP/SECTORS]` and `[TYRE HISTORY]` disclosures, default closed. Stacked
factual rows (no wide tables, no charts, no team colors). One request per
race, cached; driver switches re-slice locally with zero refetch.

## Validation

- Frontend 540/540 (513 + 27 new), typecheck/lint/build clean.
- Python collection 5186 (5179 + 7); backend suite 7/7; guards pass.
- Live: 2021-r01-R f200/f400 causal reveal + driver re-slice verified;
  1600/820/390 closed+open with zero overflow; keyboard operable; zero
  console errors. Pathology V3.10F-P1…P20 all zero.

Next gate: V3.10G (strategy + counterfactual integration). Not implemented here.
