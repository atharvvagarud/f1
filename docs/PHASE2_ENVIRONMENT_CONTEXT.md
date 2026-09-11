# Phase-2 Environment Context (F9)

> F9 backward-looking weather + race-control history in
> `v2/features/environment.py` (9 features, registry 60→69, schema
> v5→v6), 28 tests green, full 189,420-row audit clean. Depends on
> F1–F8 without reinterpreting them. F4 currents never duplicated;
> no forecasts, no NLP, no interactions.

## 2. Current-vs-history distinction

F4 owns current values (`wx_*`, `track_state`, flags). F9 owns only
what changed / how long / how much exposure — every F9 value is a
function of history, never a copy of the current row.

## 3. Source tables

Weather: the distinct D5 observation series as carried on D9 rows
(`wx_observed_at_s` + values) along the target's own prefix —
semantically identical to querying the observation table at ≤T, at
lap-cadence sampling (documented, no new table reads, no API change).
Track: the target's own D9 `track_state` token series (the approved
structural abstraction; raw messages and their 69 untimed members
never enter).

## 4–6. Weather cadence, windows, anchor

Measured: strict 60 s cadence, 0 duplicate timestamps, zero nulls,
max gap 480 s, rain transitions in only 44/173 races. Window 300 s
(~5 obs) for all F9 history. Anchor = latest distinct obs ≤ T−300
(never future-nearest); coverage 94.9%, anchor age p50 343 s / p95
412 s / max 3,395 s (factual, uncapped, distributed as measured).

## 7–8. Weather features + delta/sign semantics

`air_temp_change_5min_c`, `track_temp_change_5min_c` = current − anchor
(positive = warmer; °C Phase-1 units). Humidity/pressure/wind deltas
deferred (weak value, compactness kept: 4 weather features).
Delta pair chosen over slopes (one consistent method; slopes add no
distinct information at 60 s cadence).

## 9–10. Rainfall semantics

Boolean source, never intensity. `rain_in_last_5min`: any rainy obs
in (T−300, T] (null only with zero window obs; unknown samples handled
honestly: True on positive evidence only). `time_since_rain_
observed_s`: T − latest rainy obs ≤ T — explicitly NOT "since rain
stopped" (transition semantics unclaimed). No-prior-rain → null
(88.8% of states — rain is rare, correctly).

## 11. Wind-direction decision

Option B: trend deferred (circular math unjustified for the value);
current direction remains the F4 factual. No wrap-around code exists
to test.

## 12–13. Track source + duration

Target's own token series (driver-level exposure, no cross-driver
conflict resolution needed). `current_track_state_duration_s` = T −
first row of the current run: a LOWER bound ("held at least X"),
null only for unknown tokens. Repeated rows never reset (tested).

## 14–15. Transitions + caution exposure

`track_state_changes_5min`: known-token transitions with row time in
(T−300, T] (null transitions uncounted; always defined). Fractions
integrate intervals (t_{i−1}, t_i]→token_i clipped to the window:
`recent_yellow_fraction_5min`, `recent_sc_vsc_fraction_5min`
(combined neutralized-running, documented), `recent_red_fraction_
5min` (session time, never "racing time"). Unknown intervals excluded
from numerator AND denominator (never assumed clear).

## 16. Race-start policy

Option A: fractions over the observable sub-window with ≥60 s
known-covered minimum, else null (early-race honest nulls, measured
2.5%); counts/duration always defined. No silent full-window claims.

## 17–18. Red / SC/VSC/yellow semantics

Red breaks spatial readings (kept separate from SC/VSC — suspension
≠ neutralization); SC/VSC/yellow retained factually with F4 context
for conditioning. No restart/ending/overtake inference of any kind.

## 19–21. Registry / version / architecture

9 defs (WEATHER ×4, RACE_CONTROL ×5), temporal DRIVER_PREFIX, sync
NONE (no rival data — correctly declared), exact D9 lineage, v1,
CANDIDATE. Schema v5→v6 exactly once (+9). One module
(`environment.py`): pure `weather_values` / `track_values` cores
shared by both paths; F3 principles reused, no ingestion duplication.

## 22–23. Single-state / batch paths

Single: exact target → own prefix → cores. Batch: per-(race,driver)
chronological walk maintaining the obs map + token series (same
cores, no per-target rescan beyond the bounded walk).

## 24–25. Parity / leakage tests

Single-vs-batch green (synthetic + 8 real spots + row-shuffle).
Future weather (temp/humidity/pressure/wind/rain), future track
transitions incl. red/SC, future pits/positions/results/labels:
identical at T. Critical rain test green (future rain never advances
`raining_recently`/`time_since_rain`). Invariants pinned (≤T sources,
anchor ≤ T−300, durations ≥ 0, fractions ∈ [0,1], counts ≥ 0, no
inf, frozen null policy).

## 26. Full-data coverage (189,420 rows, MEASURED)

Nulls: air/track deltas 5.56%, rain-bool 0.03%, time-since-rain
88.81%, duration 0.71%, transitions 0%, fractions 2.47% each. Air
−4.1/+1.5 °C p50 0.0; track −9.9/+6.8 °C p50 −0.1; time-since-rain
p50 431 s max 7,304 s; duration p50 1,016 s max 6,138 s;
transitions max 4. Deterministic rebuild identical.

## 27. Edge cases

Germany-2019 wet (raining, SC fraction 1.0), Belgium (early null
deltas, rain true), Japan-2022 (1,352 s green run), Bahrain dry,
Britain, Monaco, 2024/2025 dry+wet — each reviewed observation by
observation; no race-specific code.

## 28. Performance (MEASURED)

Full batch ~8 s (own-history walks, no cross-driver work);
single-state 4.2 ms; suite impact small. No infrastructure.

## 29. Limitations

Lap-cadence (not 60 s) weather sampling along prefixes; anchor ages
to ~3,400 s in gapped races (factual, exposed); unknown-flag
intervals reduce fraction coverage rather than imputing; wet/dry
split pace and compound interactions are F11/Model-Lab business.

## 30. F10 handoff

F10 consumes: environment columns as background context for priors
(no interaction with priors), the exact-state cache pattern, and the
300 s race-clock windowing precedent. Priors, grid join, and matrix
work are F10+ — untouched here.
