# V3-0 SCIENTIFIC ARCHITECTURE + BASELINE AUDIT

Read-only audit of the frozen F1 Race Intelligence repository at
`phase12-spatial-replay` (`e99a78f8`). No production source was changed,
no model retrained, no artifact regenerated. Two files created by this
audit; nothing else.

- Entry HEAD: `e99a78f874597dce4639fb56e1b301a08d100506`
- Entry worktree: clean (verified before analysis)
- Graphify before: 12626 nodes / 30251 edges / 363 communities
- Method: Graphify-first navigation, then targeted source + frozen-report
  reads. Metric values below are transcribed from frozen authoritative
  records (provenance cited); predictions were not regenerated.

## Final verdict

V3-0 COMPLETE — READY FOR V3.1 CONTRACT (pending review of this audit).
Baseline safety exact, ALL_84 fully enumerated (84/84) with registry
temporal semantics, metrics match authoritative records to full quoted
precision, six scientific identities exact, worktree contains exactly the
two permitted new files.

## Frozen baseline

- Task: `winner` / label `is_winner` / mask `eligible_is_winner`
  (`raceintel/features/build_matrix.py::TASKS`).
- Feature set: `ALL_84` (registry v8, matrix v1, label-set v1, ablation
  config v1). 84 predictive columns, canonical matrix 189420 rows x 106
  columns, 173 races, seasons 2018-2025.
- Model: `LogisticRegression`, C=0.01, penalty=l2 (sklearn default),
  solver=lbfgs, max_iter=1000, class_weight=None, random_state=42,
  project seed 42, calibration RAW (no calibrator fitted).
- Training: FINAL_FIT 2018-2024 (149 races, 162728 eligible states,
  8926 positives). Holdout: 2025 (24 races, 26692 eligible states,
  1444 positives).
- Prediction semantics: independent per-driver binary probabilities.
  THE WINNER MODEL OUTPUT IS NOT A NORMALIZED FIELD DISTRIBUTION.
  Confirmed in `docs/MODEL_LAB_FINAL_MODEL_CARD.md` ("its probabilities
  are not normalized to sum to 1") and enforced by the M1.1
  prediction-semantics guard (`PredictionKind.BINARY_PROBABILITY`;
  top-k adapter refuses distribution treatment).

## Repository topology

- `raceintel/features/` — Phase-2 temporal feature engine (F2 engine,
  F4 passthrough, F5 pace, F6 gaps, F7 context, F8 rates, F9
  environment, F10 priors, F11 interactions, registry, contracts,
  `build_matrix`).
- `raceintel/labels/` — label registry; `CANONICAL_LABEL_NAMES` is the
  outcome-name guard no feature calculator may import values from.
- `raceintel/model_lab/` — M0 protocol, data/splits/tasks/preprocessing,
  metrics, calibration_selection, runner, suite, final_fit, winner
  (synchronized top-k adapter), predictions, errors.
- `raceintel/experiments/feature_sets.py` — F16 ablation config:
  `ALL_84`, primary groups, cumulative/logo/baseline sets, fixtures.
- `raceintel/race_state/` — RaceState + RaceStateFeatureBridge
  (frozen ALL_84 bridge for serving).
- `raceintel/replay/`, `raceintel/simulation/`, `raceintel/strategy/`,
  `raceintel/explainability/`, `raceintel/spatial/` — serving-time
  systems, each with its own semantic contract (see boundaries).
- `raceintel/prediction.py` — RacePredictionEngine (serving).
- `results/` — frozen evidence (`v2_model_lab`, `v2_final_validation`,
  `v2_replay`, `v2_explainability`, `phase12`, ...). `results/v3/`
  created by this audit to hold the machine record only.
- `docs/` — frozen reports (Phase-2 final, Model Lab Mx, Phase-11/12);
  this audit adds exactly one file here.

## Current scientific system

One causal chain, four temporal scopes:

1. `driver_lap_state_d9` (as-of state at lap boundary, exact clock T)
   -> family calculators (F4-F11) -> F15 canonical matrix (v1).
2. Model Lab (M0-M9): expanding-window folds D1/D2/D3 on 2018-2024,
   FINAL_FIT on 2018-2024, one-shot 2025 holdout (M9, now sealed by
   `ProtectedHoldoutAlreadyConsumed`).
3. Serving: RaceState at T -> RaceStateFeatureBridge -> frozen LogReg
   -> independent binary probabilities -> synchronized top-k adapter
   (RaceIndex `state_time_s <= T`, never same-lap fallback).
4. Adjacent systems consume the same frozen state with DIFFERENT
   semantics: replay = exact historical checkpoints (HIT-only);
   simulation = Monte Carlo frequencies over mutually exclusive
   outcomes; strategy = single-decision CRN paired comparison, never a
   recommendation; explainability = associational LOG_ODDS (residual 0
   within 1e-12); spatial (Phase-12) = presentation-only historical
   replay, zero predictive coupling.

## Frozen winner baseline

Per `docs/MODEL_LAB_FINAL_MODEL_CARD.md`,
`docs/MODEL_LAB_FINAL_REPORT.md`, and
`results/v2_final_validation/p11_2_validation_summary.json`
(`model_evaluation.metrics`, source
`data/v2/model_lab/reports/final_holdout_2025_v1.json`):

- estimator LogisticRegression C=0.01, ALL_84, RAW, INDEPENDENT_BINARY.
- FINAL_FIT 2018-2024 -> one-shot 2025 holdout. No refit, no tuning on
  2025. Preprocessing: 70 numeric (train-median + StandardScaler),
  11 boolean (train-mode, float cast, unscaled), 3 categorical
  (compound, stint_compound, track_state; `MISSING` sentinel +
  train-vocabulary one-hot, unknown=ignore; ~105 dense columns).
- Development reference (M7 frozen-global outer D1-D3): race-macro log
  loss 0.071374, Brier 0.020662, ROC-AUC 0.979514, PR-AUC 0.796692,
  top-1 0.7629 (descriptive; different training design than FINAL_FIT,
  not an overfitting diagnosis).

## ALL_84 feature inventory

84/84 enumerated from `build_f11_registry()` (predictive_eligible).
Order below is registry order. Columns: name | family | dtype |
temporal_rule | status. Descriptions/sources/missing-policies are in
the machine record (`feature_inventory`).

STATE (23 = factual current state at T):
position | race_state | int64 | target_state | PASSTHROUGH;
race_leader_laps_at_state | race_state | int64 | target_state |
PASSTHROUGH; race_progress_frac | race_state | float64 |
target_state | PASSTHROUGH; compound | tyre | string | target_state |
PASSTHROUGH; fresh_tyre | tyre | bool | target_state | PASSTHROUGH;
stint_compound | tyre | string | target_state | PASSTHROUGH;
stint_fresh_tyre | tyre | bool | target_state | PASSTHROUGH;
tyre_life | tyre | int64 | target_state | PASSTHROUGH (source
quirk: includes laps in other sessions);
laps_since_last_pit_stop | stint | int64 | target_state |
PASSTHROUGH; pit_stops_completed_so_far | stint | int64 |
target_state | PASSTHROUGH (fully-observed stops only);
stint_lap | stint | int64 | target_state | PASSTHROUGH (start side
only, never eventual end); flag_red | race_control | bool |
target_state | PASSTHROUGH; flag_safety_car | race_control | bool |
target_state | PASSTHROUGH; flag_vsc | race_control | bool |
target_state | PASSTHROUGH; flag_yellow | race_control | bool |
target_state | PASSTHROUGH; track_state | race_control | string |
target_state | PASSTHROUGH (FastF1 3.7.0 TrackStatus mapping);
wx_air_temp_c, wx_humidity_pct, wx_pressure_hpa, wx_rainfall,
wx_track_temp_c, wx_wind_direction_deg, wx_wind_speed | weather |
float64/float64/float64/bool/float64/float64/float64 | backward_asof |
PASSTHROUGH (latest observation at/before T).

PACE (12 = past-only driver pace, driver_prefix):
current_stint_eligible_laps (int64), current_stint_pace_mean_s,
current_stint_pace_median_s,
current_stint_pace_trend_s_per_lap (OLS slope, documented PROXY ONLY
- confounded, never physical degradation) | stint; pace_mean_5,
pace_median_10, pace_median_3, pace_median_5, pace_n_10, pace_n_3,
pace_n_5 (window counts), representative_recent_pace_s (median of
latest 10 requiring >= 8) | pace. All NULL_IF_INSUFFICIENT_HISTORY.

GAPS (8 = synchronized geometry, synchronized_field):
ahead_observation_age_s (float64, provenance, not the gap);
gap_to_ahead_laps (int64); gap_to_ahead_seconds (float64, VALID only);
gap_to_ahead_seconds_valid (bool); gap_to_leader_laps (int64,
negative = laps down); gap_to_leader_seconds (float64, VALID only);
gap_to_leader_seconds_valid (bool); leader_observation_age_s
(float64, provenance). Laps-apart/red/ambiguous -> seconds null +
valid=False by construction.

FIELD_CONTEXT (12 = synchronized relative context):
cars_ahead_observable, cars_behind_observable,
field_pace_comparable_rivals, observable_field_size,
relative_pace_to_field_median_s_per_lap (target minus median over
comparable rivals, >= 5 contributors, target excluded) | field;
relative_pace_to_car_ahead_s_per_lap | relative (unique predecessor
only); relative_pace_to_teammate_s_per_lap, teammate_lap_difference,
teammate_observation_age_s, teammate_position | teammate;
in_traffic_2s (measured band, never DRS), nearby_cars_within_5s |
traffic.

RATES_MOMENTUM (4 = backward-looking change only):
recent_gap_to_ahead_change_s_per_lap, recent_gap_to_leader_change_s_per_lap
| rate (OLS slope over trailing same-rival valid-seconds points
within 5 target laps, >= 2; negative = closing; no catch-time, no
projection); recent_pace_change_s_per_lap (median-5 now vs anchor at
lap <= N-5), recent_position_change_5laps (anchor position minus
current; positive = gained; never called overtakes) | momentum.

ENVIRONMENT_HISTORY (9 = how the environment got here):
air_temp_change_5min_c, rain_in_last_5min, time_since_rain_observed_s
(time since rain OBSERVED, not since rain stopped),
track_temp_change_5min_c | weather driver_prefix;
current_track_state_duration_s (lower bound), recent_red_fraction_5min
(session time, not racing time), recent_sc_vsc_fraction_5min,
recent_yellow_fraction_5min, track_state_changes_5min (always defined,
0 allowed) | race_control driver_prefix.

PRE_RACE_PRIORS (13 = genuinely pre-race):
grid_position | grid | int64 | pre_race_constant (pit-lane 0
preserved as factual code); prior_constructor_mean_finish,
prior_constructor_points_per_entry, prior_constructor_races,
recent_constructor_points_per_entry_5 (trailing 5) |
constructor_prior; prior_driver_mean_finish, prior_driver_mean_grid,
prior_driver_points_per_start, prior_driver_starts,
recent_driver_mean_finish_5 (trailing 5) | driver_prior;
prior_circuit_mean_pit_stops_per_entry,
prior_circuit_mean_position_change, prior_circuit_races |
circuit. All temporal_rule past_races, PRE_RACE availability,
thresholds frozen (>= 3 classified/starts/entries, >= 2 editions).

INTERACTIONS (3 = F11, approved primitives only):
positions_from_grid (grid - position; grid 0 excluded) |
interaction target_state; recent_gap_to_ahead_change_in_traffic_s_per_lap
(ahead gap-rate gated on factual traffic, null outside) |
interaction synchronized_field;
relative_pace_to_ahead_in_traffic_s_per_lap (ahead-relative pace
gated on factual traffic, null outside) | interaction
synchronized_field.

Counts check: dtype 45 float64 / 25 int64 / 11 bool / 3 string (= 70
numeric + 11 bool + 3 categorical in preprocessing). Temporal:
synchronized_field 24 / driver_prefix 23 / target_state 17 /
past_races 12 / backward_asof 7 / pre_race_constant 1. Availability:
LAP_END 54 / IN_LAP 17 / PRE_RACE 13. Status: 61 CANDIDATE / 23
PASSTHROUGH. Partition: STATE 23 / PACE 12 / GAPS 8 / FIELD_CONTEXT 12
/ RATES_MOMENTUM 4 / ENVIRONMENT_HISTORY 9 / PRE_RACE_PRIORS 13 /
INTERACTIONS 3. Total 84.

## Feature-family map

Registry families (18) -> ablation primary groups (8): race_state,
tyre, stint(target_state), race_control(target_state),
weather(backward_asof) -> STATE; pace, stint(driver_prefix) -> PACE;
gap -> GAPS; relative, teammate, field, traffic -> FIELD_CONTEXT;
rate, momentum -> RATES_MOMENTUM; weather(driver_prefix),
race_control(driver_prefix) -> ENVIRONMENT_HISTORY; grid,
driver_prior, constructor_prior, circuit -> PRE_RACE_PRIORS;
interaction -> INTERACTIONS. The three mixed families (stint,
race_control, weather) split by registry `temporal_rule` - the same
rule the family docs use to separate factual state from derived
history. Derived from repository semantics
(`primary_group_name()`), not imposed.

## What the model knows at T

- Current position, race progress (leader-lap fraction of scheduled
  distance), leader laps completed.
- Leader gap (seconds when same-lap VALID, else laps + validity flag +
  observation age); car-ahead gap ditto; sync provenance ages.
- Recent pace: trailing eligible-lap medians/means (3/5/10), window
  counts, stint summaries, in-stint trend proxy, median-5 change rate.
- Relative pace to ahead / field median / teammate; teammate state.
- Field shape: observable counts ahead/behind, field size (honest
  observable count), comparable-rival count, traffic flags (2 s band,
  5 s neighbourhood).
- Change rates: gap-to-leader/ahead OLS slopes (5-lap, same-rival),
  position change over 5 laps.
- Tyre factual state: compound, fresh flag, stint compound/fresh,
  tyre life (with quirk), stint lap, laps since stop, completed stops.
- Track/race status now + recent history: flags, track_state token,
  state duration, 5-min transition count and red/SC-VSC/yellow
  fractions.
- Weather now (7 as-of channels) + 5-min deltas, rain recency/flag.
- Pre-race: grid slot + driver/constructor/circuit historical priors
  and trailing-5 recent forms.
- Three gated interactions: positions-from-grid, traffic-gated gap
  rate, traffic-gated relative pace.

## What the model does not know

Evidence-based absences from ALL_84 (not assumptions):

- No gap trajectory beyond the two 5-lap OLS slopes: no multi-horizon
  slopes, no gap acceleration/curvature, no ahead/behind asymmetry
  beyond current values, no gap-to-behind at all.
- No position-trajectory shape: only a single 5-lap delta; no
  per-lap path, no volatility of position.
- No pace volatility: no variance/IQR/range of recent laps, no
  outlier-robust spread, no lap-to-lap delta sequence.
- No tyre-degradation trajectory: in-stint trend is one OLS proxy
  with confounders documented; no age-conditioned pace residual, no
  compound-relative degradation, no stint-length expectation.
- No pit-cycle state: no laps-to-expected-window, no undercut/overcut
  threat, no out-lap/in-lap flags, no stop-duration expectation; pit
  history is counts only.
- No field compression/expansion: no spread statistic (leader to
  last, compressed index), no SC-bunching residual after restart.
- No behind-threat: no gap to car behind, no pace of pursuer, no
  defence descriptor.
- No DRS/proximity outcome: `in_traffic_2s` is a measured band,
  explicitly never DRS.
- No DNF/reliability signal: no retirement history feature, no
  mechanical-risk descriptor (reliability deferred by design).
- No weather forecast: only as-of observations + trailing history.
- No qualifying pace beyond grid + priors: no session-time pace.
- No sector/telemetry detail: lap times only; telemetry deferred.
- No strategy intent: no planned stop, no target stint length, no
  compound plan (Phase-7 strategy compares counterfactuals at
  simulation time, not from features).

## Representation redundancy

Deliberate, documented overlaps (understand, do not remove):

- pace_mean_5 / pace_median_5 / pace_median_3 / pace_median_10 /
  representative_recent_pace_s: five transforms of the same trailing
  eligible-lap distribution (mean vs median, 3/5/10 horizons, strict
  >= 8 variant). Different robustness/coverage operating points.
- pace_n_3/5/10 + current_stint_eligible_laps: explicit history-depth
  companions to every windowed summary (early-race null-depth is
  observable, not silent).
- gap seconds / laps / valid / observation-age quartets (leader,
  ahead): absolute value + fallback geometry + validity bit +
  provenance age. The model sees all four; validity gates meaning.
- current_stint_pace_mean/median vs pace_median_5: stint-scoped vs
  trailing-window summaries of overlapping laps (ablation splits them
  deliberately: stint facts in STATE, derived stint pace in PACE).
- relative_pace_to_car_ahead vs relative_pace_to_ahead_in_traffic:
  ungated primitive + traffic-gated interaction (F11 dependency policy
  removes the interaction with its parent group).
- recent_gap_to_ahead_change vs ..._in_traffic: same gating pattern.
- positions_from_grid = grid_position - position: exact linear
  redundancy with two STATE/PRIOR inputs, kept as the interpretable
  interaction (dependence recorded in REQUIRED_PRIMITIVES).
- wx_* as-of (7) vs 5-min deltas/recency (4): level vs change split
  across STATE / ENVIRONMENT_HISTORY.
- flags/track_state (levels) vs duration/fractions/transitions
  (history): same token stream, disjoint temporal rules.
- prior_driver_points_per_start vs recent_driver_mean_finish_5 (and
  constructor pair): all-time vs trailing-5 views of the same history.
- tyre_life vs stint_lap vs laps_since_last_pit_stop: three
  differently-sourced age counters with different null semantics and
  quirks - subtle; v3 must not reconstruct any of them casually (see
  Temporal semantics).

## Temporal semantics

Rules (registry authority): target_state = value at the lap-boundary
state (passthrough or exact combination of contemporaneous values);
driver_prefix = own states with time <= T only; synchronized_field =
own state + latest rival states with state_time_s <= T (RaceIndex,
no fall-forward, stale kept, retirement never inferred);
past_races = strictly prior races (hist_results, thresholds frozen);
pre_race_constant = factual grid; backward_asof = latest weather
observation at/before T.

Trace examples: position <- D9 position @T (current state).
pace_median_5 <- eligible lap_time_s over own prefix <= T, in-lap /
pit laps / non-green excluded by the eligibility predicate (past-only
rolling history). gap_to_leader_seconds <- T_target - T_leader where
leader state = latest leader observation <= T AND same-lap AND green
geometry; else null + valid=False (current synchronized geometry, not
a forecast). recent_gap_to_leader_change <- OLS over trailing
same-leader valid-seconds points within 5 target laps (descriptive
momentum over history, needs >= 2 points). prior_driver_mean_finish
<- mean classified finish over all prior starts >= 3 (pre-race prior,
frozen history bundle). grid_position <- results join, identity only
(pre-race constant).

Subtle features v3 must not reconstruct differently: tyre_life
(source quirk - includes other-session laps); stint_lap (D7
current-stint start, start side only); laps_since_last_pit_stop (0 on
exit lap; fully-observed stops only); pit_stops_completed_so_far
(asymmetric in-only/out-only never counted); race_progress_frac
(scheduled-distance reference, NOT observed==scheduled);
current_stint_pace_trend (documented confounded proxy);
time_since_rain_observed_s (since observed, NOT since stopped);
recent_red_fraction_5min (session time, not racing time);
in_traffic_2s (measured band, never DRS); observable_field_size
(honest observable count, NOT running field); relative pace family
(excludes target / requires unique predecessor / >= 5 contributors).

## Current model capability

LogisticRegression over ALL_84 with the frozen preprocessing can
express: linear additive log-odds effects in the ~105-column
transformed space (70 standardized numerics, 11 raw 0/1 bools,
one-hot categoricals with MISSING level); monotone smooth responses
to any single standardized input; explicit two-way structure only
where F11 hand-built it (3 interactions); field-relative reasoning
only where F7 synchronized it into per-row values (relative pace,
teammate, counts).

It cannot express from this representation: nonlinear thresholds or
saturations (no splines/bins; e.g. "gap < 1 s matters discontinuously"
must be linear in seconds); interactions beyond the three explicit
ones (e.g. tyre-age x compound, gap x stage, SC-flag x gap-rate are
all additive unless the F11 term exists); sequence/trajectory shape
(single slopes and 5-lap deltas are points, not paths - no curvature,
no regime detection); cross-driver joint structure (each row scored
independently; field coupling exists only as precomputed per-row
columns); time-varying effects (one global coefficient vector for
EARLY/MID/LATE); unobserved-state reasoning (nulls enter via median
imputation - the model sees the median, not the missingness, except
through the MISSING categorical level and pace_n_* counts).

Every limitation above is tied to the frozen transform + linear
family, not a generic critique: with the same ALL_84, a nonlinear
family (V3.3 territory, explicitly NOT V3.1) could in principle learn
thresholds and interactions the LogReg cannot. V3.1 must therefore
hold the family fixed to attribute gains to representation.

## Race Dynamics definition

Race Dynamics = causal descriptors of how a driver's competitive state
is changing over recent historical time ([T-W, T], source_time <= T
for every input), rather than only the current state at T.

Fit to this engine: the engine already computes driver_prefix and
synchronized_field histories through RaceIndex + lap eligibility, so
[T-W, T] descriptors are constructible with the same causal
machinery; the F8 rate/momentum family proves the pattern. The
definition excludes: any input with source_time > T; full-race
aggregates that include the future; future-defined cohorts; post-race
statistics; simulation outputs; spatial geometry as dynamics input.

Candidate verdicts: position trajectory (5-lap delta exists) =
PARTIALLY_PRESENT; gap trajectory (two 5-lap OLS slopes) =
PARTIALLY_PRESENT; pace trajectory (median-5 change rate + stint
trend proxy) = PARTIALLY_PRESENT; relative pace (levels only, no
trajectory) = PARTIALLY_PRESENT (levels present, dynamics MISSING);
tyre degradation trajectory (confounded proxy only) =
PARTIALLY_PRESENT with a NOT_JUSTIFIED physical reading (proxy
status must stay); traffic evolution (instantaneous flags only) =
MISSING; pit-cycle evolution (counts only) = MISSING; field
compression/expansion = MISSING; race-state transition dynamics
(counts/fractions exist, transition-triggered resets do not) =
PARTIALLY_PRESENT; momentum/change rates at multiple horizons =
PARTIALLY_PRESENT (one horizon each); gap acceleration / curvature /
volatility = MISSING; behind-threat dynamics = MISSING (no behind
gap at all); weather-trajectory coupling beyond 5-min deltas =
NOT_JUSTIFIED for V3.1 (deferred with weather).

## State vs dynamics

STATE = "what is true now": position(T), gap_to_leader_seconds(T),
pace_median_5(T), tyre_life(T), flag_safety_car(T).
DYNAMIC = "how has it changed": slope(gap_to_leader over T-k..T),
pace_median_5(T) - pace_median_5(anchor), position(anchor) -
position(T), stint-trend slope, transition counts/fractions.

ALL_84 lies mostly on the STATE side: 23 STATE passthroughs + 7
as-of weather + priors/grid (constants) + gap/relative/field levels
(~20) are pure state; the dynamic content is exactly 4 RATES_MOMENTUM
+ 9 ENVIRONMENT_HISTORY + 4 stint/pacesummaries with trend semantics
+ pace_n_* depths - i.e. dynamics exist but at single fixed horizons
(5 laps / 5 min / trailing-5 / in-stint) with no multi-horizon,
volatility, curvature, or behind-relative descriptors.

## Causal window contract

For a dynamic feature evaluated at state time T: every source
observation (own laps, rival sync states, weather observations,
track-state rows) must satisfy source_time <= T. Admissible history
is [T-W, T]; (T, T+W] is forbidden. Consequences: rival inputs reuse
RaceIndex sync_lookup (latest rival state <= T, same rule as gaps and
the winner adapter); own-lap inputs reuse the F5 eligibility
predicate over the driver prefix; weather inputs reuse backward-asof
+ (T-300, T] conventions; lap-boundary states evaluate at
state_time_s of the lap end; irregular spacing is handled by
time-based windows with explicit coverage/minimums, never by assuming
uniform lap cadence; red-flag laps keep their invalidity handling
(no silent inclusion); pit in/out laps keep F5 ineligibility.

## Window design space

Units: laps (race-natural, comparable across eras), seconds
(clock-true under SC/VSC/red distortion), state counts (robust to
missing laps). Recommended experimental space, not constants:
horizons {3, 5, 10} laps x {trailing-lap, trailing-time-300s} framing
for pace/gap slopes; in-stint scope vs fixed trailing scope as a
design axis; minimum-observation grids {2, 3, 5} with
NULL_IF_INSUFFICIENT_HISTORY. Trade-offs: early race has no history
-> partial-window + explicit depth features (pace_n_* pattern),
never silent zeros; SC/VSC compress gaps and distort pace ->
condition or mask (see Neutralisation); pit laps contaminate trailing
windows -> reuse F5 eligibility (exclude) + test masked vs unmasked;
variable lap length / red flags / irregular spacing -> prefer
time-anchored windows with lap-count guards, report coverage.
V3.1 must select horizons by temporal-CV evidence (D1-D3), not by
intuition; the search itself runs under the frozen split/metric
contract.

## Dynamic feature candidates

Small interpretable set (each: concept; inputs<=T; min history;
nulls; edge cases; overlap; leakage risk; V3.1 suitability):

1. gap_to_leader multi-horizon slopes (3/10-lap OLS alongside frozen
   5-lap): same-rival valid-seconds points; min 2 (3-lap) / 3
   (10-lap); null when insufficient; SC/pit contamination per
   Sections Pit/Neutralisation; overlaps frozen 5-lap slope
   (collinearity expected - test incremental value); leakage low
   (sync<=T + eligibility reuse). SUITABLE (core V3.1).
2. gap acceleration (slope-of-slopes, leader + ahead): needs >= 3
   slope points; null early; noisy - needs shrinkage/median
   variant; overlaps rates; leakage low. PROVISIONAL (test after 1).
3. pace volatility (IQR/range of trailing eligible laps, 5/10):
   min 3/5; null early; SC/pit laps excluded by eligibility;
   orthogonal to medians (new information). SUITABLE.
4. relative-pace trajectory (change in relative_pace_to_field_median
   over 5 laps): needs rival sync at both ends; null when
   contributors < 5 at either end; cohorts recomputed per endpoint
   from <=T states only (never a full-race cohort). SUITABLE with
   cohort-freeze rule.
5. behind-threat dynamics: NEW gap_to_behind_seconds (mirror of ahead
   geometry, same VALID rule) + its 5-lap slope: symmetric
   construction; null when no behind/leader; genuinly new info.
   SUITABLE (state + dynamic pair).
6. field spread / compression index (e.g. P90-P10 of synchronized
   valid gaps, or leader-to-median): race-level descriptor broadcast
   to rows, computed from <=T sync states; undefined under red;
   new info. SUITABLE.
7. traffic persistence (fraction of last 5 laps in_traffic_2s):
   min coverage rule; null when geometry invalid throughout;
   overlaps instantaneous flag (level vs persistence). SUITABLE.
8. stint-age-conditioned pace residual (pace_median_5 minus
   stint-median at same stint age - descriptive, NOT a degradation
   model): needs stint history; null first laps of stint; overlaps
   trend proxy; MUST keep proxy wording (no physical claim).
   PROVISIONAL.
9. pit-transition indicators (in-lap/out-lap/recent-stop flags from
   past-only pit observables): factual past-only; new info;
   doubles as contamination control. SUITABLE (also serves Pit).
10. neutralization-conditioned dynamics (SC/VSC fraction x gap-slope
    interaction built from frozen primitives, F11-style): follows
    interaction dependency policy; SUITABLE as the controlled
    neutralization treatment.
11. Weather-trajectory couplings beyond 5-min: NOT_JUSTIFIED for
    V3.1 (weather deferred; keep existing deltas).
12. Telemetry/sector/trajectory shapes: NOT_JUSTIFIED (no source in
    D9; out of scope).

## Relative competitive dynamics

Recommended references, all computable causally: car ahead (unique
predecessor, existing pattern) and NEW car behind (symmetric mirror);
leader (existing); field median over per-endpoint comparable rivals
(>= 5 contributors, target excluded, cohorts never defined from
future results); teammate (existing sync pattern); stint-age cohort
descriptive only. Forbidden: cohorts defined by final result
("top-3 finishers' pace"), full-race aggregates, any grouping whose
membership needs post-T truth. Behind-gap construction must mirror
the F6 ahead geometry exactly (same-lap, VALID rule, red/ambiguous
exclusions) to inherit its causal audit.

## Pit-cycle effects

Hypotheses to test (not assumptions): H1 raw trailing windows that
include in/out laps are contaminated (F5 eligibility already excludes
them from pace inputs - gap slopes need the same audit); H2 masking
contaminated laps from slope inputs + adding explicit
pit-transition indicators dominates both raw and mask-only; H3
in-stint-scoped windows behave differently from fixed-trailing
windows around stops (segment: restart slope baselines at stint
start); H4 fresh-tyre transition effects are absorbed by tyre-state
levels + indicators without needing pace deltas. Design: reuse F5
eligibility for pace-side inputs; audit gap-slope inputs lap by lap
around the 6336 recorded stops; compare raw vs masked vs
masked+indicators under the frozen metric hierarchy; never use
eventual stint end or stop outcome (future) as input.

## Neutralisation effects

Under yellow/SC/VSC gaps compress and pace is unrepresentative; under
red, geometry is invalid (existing VALID rule) and session time still
accumulates (red fraction uses session time deliberately).
Experimental treatments: T0 evaluate-only (no special handling -
measures the problem); T1 status-conditioned dynamics (F11-style
gated slopes, null outside); T2 window masking (exclude
neutralized laps from slope inputs + coverage/depth companions); T3
neutralization indicator + fraction features only (already partly in
ENVIRONMENT_HISTORY). Compare T0-T3 on stage-split and SC-affected
race subsets; predeclare T2 (mask + indicators) as the default
hypothesis with T1 as the interaction-form alternative. No treatment
may look ahead to the restart or the SC outcome.

## Early-race behavior

Policy: minimum observations per dynamic feature (e.g. slopes >= 2
valid points, medians >= 3, strict representative >= 8 - follow the
frozen ladder); partial windows compute over available eligible laps
(never pad with zeros); every windowed summary ships with an explicit
depth companion (pace_n_* pattern generalized); NULL_IF_INSUFFICIENT_HISTORY
propagates to preprocessing (train-median imputation downstream, as
today - silent only at the model-matrix layer, explicit at the
feature layer); fallback is state-only by construction (dynamic terms
null -> imputed median -> near-zero standardized contribution).
Silent zero-filling of a slope or delta is forbidden (zero slope =
"stable", which is a claim, not a missing value). Report EARLY-stage
metrics separately; early-race regression is a veto (see Acceptance).

## Target/task audit

Frozen task contract offers: winner, podium, points, final_position,
gain, loss (+ position_change companion). Eligibility columns:
eligible_is_winner/is_podium/scored_points (binary, 189420),
eligible_ordinal_final_position (178963),
eligible_gain_loss (189126).

Per-candidate: podium (label available, same binary machinery,
balanced ~3x winner; belongs V3.5 outcome-distribution, NOT V3.1);
top-k finish / position distribution (needs ordinal/distributional
machinery; V3.5); position gain/loss (masks available, product-useful
for strategy; later, needs its own calibration story); DNF/
reliability (intentionally absent from Model-Lab tasks - "DNF is
intentionally absent" per errors.py; needs new labels + hazard
framing; research track, not V3.1); pit-window/strategy outcome
(needs simulation-grounded labels; V3.6 after MC2.0). V3.1 stays on
the winner task: it isolates representation effects, reuses the
sealed evaluation path, and keeps every comparison paired.

## V3.1 target decision

V3.1 uses the SAME frozen winner task (is_winner under
eligible_is_winner). Rationale: (1) isolates the representation
change - any metric movement is attributable to features, not to a
new label/mask/prevalence regime; (2) reuses the frozen split,
preprocessing, calibration, top-k, stage, and race-macro machinery
without redefinition; (3) preserves comparability with the M7/M9
evidence chain; (4) avoids inventing new leakage surface (new labels
need new audits). New tasks enter from V3.5 onward on the v3 feature
foundation.

## Experimental control

Minimum scientifically useful comparison (same family, same
hyperparameters, same splits, same preprocessing recipe refit
train-only):

- Arm A (frozen): ALL_84 + LogReg C=0.01 RAW. Reproduction of the
  frozen baseline; must match recorded development values within
  tolerance before any claim.
- Arm B (test): ALL_84_PLUS_V3_DYNAMICS + LogReg C=0.01 RAW.
  The representation experiment.
- Arm C (diagnostic): V3_RACE_DYNAMICS_* only + LogReg C=0.01 RAW.
  Measures standalone signal and overlap (expect below A; the
  question is B-A, with C explaining why).

Later, never first: Arm D (ALL_84 + dynamics + nonlinear family) -
reserved for V3.3; running D first contaminates attribution (family x
representation confound). Calibration stays evaluation-only across
A-C (M8 architecture reused, no refit inside the comparison).

## Feature-set versioning

ALL_84 is immutable: no rename, no redefinition, no in-place
extension. New named sets follow the F16 vocabulary pattern
(`raceintel/experiments/feature_sets.py` conventions):
V3_RACE_DYNAMICS_* (dynamics-only sets, one per experimental rung),
ALL_84_PLUS_V3_DYNAMICS[_<rung>] (cumulative test sets). Registry
authority extends: every v3 definition gets family, temporal_rule
(must be driver_prefix or synchronized_field with causal proof),
min_history, missing policy, availability, status; predictive
membership resolves from the registry, never from hand lists;
manifest compatibility (matrix/feature/label/ablation versions +
content hashes) fails loudly on drift. The F11 interaction dependency
policy generalizes: gated/derived dynamics record required primitives
and are removed with their parent group in ablations.

## Split/evaluation contract

Unchanged for V3.1: D1 train 2018-2021/val 2022, D2 train
2018-2022/val 2023, D3 train 2018-2023/val 2024 (expanding window,
TRAIN strictly before VAL); FINAL_FIT 2018-2024; protected 2025
holdout evaluated only under the M9 seal (single locked run at the
end, never for selection). Race-macro headline + state-pooled
diagnostic; EARLY/MID/LATE thirds of race_progress_frac; RAW
calibration evaluation-only; synchronized top-k adapter unchanged;
state_equal training weights. No new split: within-season (R -> R+1)
stays an unadopted secondary per protocol; inventing a new split for
v3 would break comparability with M7/M9.

## Metric hierarchy

Predeclared, in order: (1) PRIMARY probabilistic: race-macro log loss
(the loss the LogReg optimizes, race-aggregated so long races cannot
dominate); (2) secondary probabilistic/discrimination: race-macro
Brier, ROC-AUC, PR-AUC (PR-AUC matters at 5.4% prevalence); (3)
calibration: ECE (10 equal-width bins) - must not degrade; (4)
ranking/product: synchronized top-1 / top-3 (share the eligible
denominator; k-way claims additionally need observable_field_size >=
k). State-pooled log loss/Brier are diagnostics. No cherry-picking:
the hierarchy is fixed before V3.1 runs; the primary metric governs
the keep/drop call, the rest can veto (especially calibration and
EARLY-stage).

## Race-macro vs state-pooled

Race-macro (mean of per-race metrics, races equal) is authoritative
for selection because state counts vary by race length, SC periods,
and retirements - state-pooling lets long/neutralized races dominate
and rewards fitting their idiosyncrasies. State-pooled stays as a
diagnostic (large macro/pooled divergence flags race-composition
effects). Uncertainty also lives at race level (resample unit =
race; row-level resampling forbidden - 189420 rows are not independent
samples). V3.1 claims are race-macro claims.

## Stage-specific evaluation

Buckets frozen: EARLY [0, 1/3), MID [1/3, 2/3), LATE [2/3, 1] on
race_progress_frac (Phase-2 thirds: 64016/63437/61967 states).
Headline stage evidence (2025 holdout race-macro log loss): EARLY
0.077468 / MID 0.069800 / LATE 0.056847 - dynamics must be reported
per stage because trailing-history features are thinnest exactly
where EARLY is already weakest. Rule: report overall + all three
stages for every arm; an overall win that hides EARLY regression
fails acceptance; SC-affected and partial-race subsets get
descriptive splits.

## Acceptance policy

No fixed improvement threshold. Keep Race Dynamics iff ALL hold:
(1) repeated temporal-fold evidence - primary metric moves the same
direction on D1/D2/D3 (no per-fold cherry-pick); (2) holdout
consistency - the single locked 2025 run agrees in direction (no
tuning on it, ever); (3) calibration non-degradation (ECE + reliability
shape checked, M8 guards reused); (4) no stage veto - EARLY does not
regress beyond race-level noise; (5) uncertainty quantified -
race-level paired deltas with bootstrap CIs exclude a pure-noise
reading at the predeclared level; (6) complexity cost justified -
feature count, missingness burden, and compute vs the measured gain.
"Race Dynamics does not improve winner prediction" is an acceptable,
publishable result that still delivers the audited dynamic-feature
contract to V3.2.

## Statistical comparison

Unit = race (predictions correlate within race; states are not
independent evidence). Method: paired race-level metric deltas
(B minus A per race) on the primary metric; race-level bootstrap
CIs (resample races, never rows); fold dispersion across D1-D3 as
the second variance view; descriptive SC/partial/stage subsets.
Row-level t-tests, pooled-state CIs, and any method treating 189420
states as independent are forbidden. Implement in V3.1 (design only
in V3-0), reusing UNCERTAINTY_POLICY (race_level_bootstrap_and_
fold_dispersion).

## Calibration policy

V3.1 evaluates calibration only (ECE + reliability curves per arm,
RAW throughout). No calibration transform is fitted inside the
representation experiment: fitting Platt/isotonic on top of Arm B
would confound representation gain with post-hoc reshaping, and M8
already rejected both transforms for this family/task under
predeclared guards. If Arm B degrades ECE while improving log loss,
that is a veto-grade finding, not a prompt to calibrate it away.
Calibration research (if ever) belongs post-V3.3 with its own
M8-style temporal architecture (calibration season = last season of
train, never outer labels).

## V3.2 boundary

V3.2 (Monte Carlo 2.0) consumes dynamic state as SIMULATION INPUTS,
not as model features: dynamic pace state, degradation-proxy state,
field-compression descriptors feed the empirical parameter
estimation / residual structure of the simulator. Interface only:
versioned parameter set (r3-v1 pattern) + scientific hash +
through-season provenance; RaceState-anchored II
ntervention API unchanged. The semantic firewall stands: simulation
frequencies (mutually exclusive outcomes, sum to 1) and winner-model
probabilities (independent binaries, do not sum to 1) must never be
naively averaged or fused without held-out evidence.

## V3.3 boundary

V3.3 (Multi-Model Lab) owns model-family experiments: XGBoost,
LightGBM, neural/sequence models, and any hyperparameter search.
V3.1 must not try them - one confound at a time. Handoff: the frozen
v3 dynamic feature contract + Arm B evidence (including the null
result, if null) become V3.3's input vocabulary; family comparison
reruns Arms A-C under identical splits/metrics with the family as the
single change. M4/M5/M6/M7 precedent (trees rejected for LogReg on
probability quality + cost) is the bar a new family must clear, with
the same predeclared hierarchy.

## V3.4 boundary

Ensemble evidence rule: no averaging without held-out proof. An
ensemble enters only if a predeclared combination rule (weights fixed
on development folds, never on 2025) beats the best single arm on
the primary metric with race-level paired evidence + calibration
non-degradation. Naive probability averaging is additionally
forbidden across the ML/simulation semantic gap (see V3.8). Arm C
(dynamics-only) exists partly to inform whether a late specialist
ensemble is even plausible - and the answer may be no.

## V3.5 boundary

Outcome Distribution replaces independent binaries with a coherent
richer outcome object (finish-position distribution / top-k /
podium/points jointly). Mathematical gap: current outputs are
per-driver P(win) with no cross-driver constraint; V3.5 needs either
a categorical race-level head (sums to 1) or a calibrated ordinal
model, with its own eligibility, prevalence, and calibration story
per outcome. Prerequisites: frozen v3 features, V3.1 representation
verdict, V3.3 family verdict, and a task/label audit per outcome
(podium/points/final_position/gain/loss masks already exist - reuse,
don't reinvent). V3.1 must not pre-build distributional heads.

## V3.6 boundary

Strategy 2.0 improves the single-decision CRN paired comparison only
after MC2.0 exists: richer counterfactual candidates (pit-window,
compound, stint-length) simulated under the v3-fed simulator, same
no-recommendation contract (compare, never prescribe; BEST/
RECOMMENDED/OPTIMAL stay forbidden in API + UI). Needs simulation-
grounded outcome labels (see Target audit). No strategy change in
V3.1.

## V3.7 boundary

Counterfactual = simulated alternative under an intervention plan,
always labeled with its anchor (race, driver, T, seed,
parameter identity) and its uncertainty; historical replay fact =
exact checkpoint served HIT-only. Never present a simulated
counterfactual as what happened; surfaces keep FACT vs SIMULATION
wording separated (claim-matrix precedent). V3.7 research needs the
MC2.0 + Strategy2.0 stack first.

## V3.8 boundary

Model x Simulation consensus research must respect the semantic
mismatch: ML outputs independent P(win); simulation outputs
mutually-exclusive frequencies. Legitimate future work: comparison
studies (agreement/disagreement anatomy), decision-theoretic use
(expected-value under each view with stated assumptions), or
evidence-gated fusion with predeclared weights and held-out proof.
Naive averaging is not a fusion method. Requires V3.2 + V3.3 done.

## V3.9 boundary

Uncertainty sources, availability now vs later: data missingness
(explicit nulls + depth companions - available); calibration
uncertainty (M8 coefficients/intervals descriptive - available);
simulation variance (CRN + bootstrap precedent, B=2000 - available);
model uncertainty (no posterior/ensemble yet - needs V3.3/V3.4);
scenario sensitivity (needs MC2.0 + Strategy2.0). V3.9 composes these
into per-prediction uncertainty; it cannot precede the systems that
produce them.

## V3.11 pre-race boundary

Pre-race is a SEPARATE task with its own label/mask/split story, using
only legitimately pre-race information (grid, historical priors,
circuit history, qualifying if audited - session results, never
in-race states). Feeding fake Lap-0 values into the 84-feature
in-race model is forbidden (the model expects lap-boundary
synchronized state; Lap 0 has no gaps, no pace, no sync field).
V3.11 builds a distinct estimator; the in-race model stays untouched.

## Phase-12 spatial boundary

Phase-12 spatial data (observation parquet + circuit/pit geometry +
causal resolver + frame-index API + SVG renderer) is PRESENTATION and
HISTORICAL STATE for replay. Default NO: coordinates, geometry, and
resolver internals must not become V3.1 predictive features merely
because they exist - they add un-audited leakage surface (telemetry
timing, future-anchored geometry) for zero justified gain, and would
couple modelling to a presentation system. Legitimate future research
(separate track): circuit-descriptor priors (e.g. overtaking-difficulty
context from geometry, versioned per circuit) - only as pre-race
context with its own audit, never as in-race dynamics, never in V3.1.
V3.1 has zero dependency on Phase-12 artifacts.

## V3 repository architecture

Extend, don't fork: no disconnected `v3/` universe. Proposed homes:

- `raceintel/features/dynamics/` - v3 dynamic calculators (one module
  per family: gap_slopes, pace_volatility, behind_threat,
  field_compression, traffic_persistence, pit_transitions), each with
  the F5/F6-style causal contract + tests.
- `raceintel/features/registry.py` - extended with v3 definitions
  (new names, new families; ALL_84 entries untouched).
- `raceintel/experiments/feature_sets.py` - new named sets
  (V3_RACE_DYNAMICS_*, ALL_84_PLUS_V3_DYNAMICS) under the same
  partition/version/hash discipline.
- `raceintel/experiments/v3_manifests.py` (new) - experiment manifest
  read/write/verify (see manifest design).
- `raceintel/model_lab/` - reused unchanged (protocol, splits,
  metrics, preprocessing recipe, winner adapter).
- `results/v3/` - versioned experiment artifacts (matrices, schemas,
  predictions, evaluations, trained states) with provenance sidecars.
- `docs/` - per-stage V3 reports (contract, construction, experiment,
  evaluation/freeze), following the Phase/M-stage report precedent.

Boundaries: dynamics definitions never import labels, simulation, or
spatial; experiments never mutate frozen registries in place;
evaluation never touches 2025 except under seal.

## Artifact versioning

Every v3 artifact carries: source dataset identity (matrix version +
content hash), feature contract (registry fingerprint + feature-set
name + semantic hash), split identity (fold ids + seasons), model
spec (family + hyperparameters + seed + preprocessing recipe),
code commit, and parameter identities where relevant. Naming:
`<artifact>_v3<stage>_<rung>_v<n>.json/parquet` beside (never over)
frozen v2 paths; content hashes stored inside manifests, not just in
filenames; predictions and evaluations are immutable once written
(new version on rerun, never overwrite). Provenance chain must
resolve v3 artifact -> feature contract -> matrix content hash ->
code commit without human memory.

## Experiment manifest

Machine-readable manifest per experiment (fields derived from frozen
conventions - protocol identity, F16 config hash, M9 final spec,
matrix manifest): experiment_id, task, feature_set, feature_contract
(hash + registry fingerprint + set semantic hash), dataset_identity
(matrix version + content hash + rows/races/seasons), split_identity
(fold ids + train/val seasons + seed), model_family,
hyperparameters, preprocessing recipe id, seed, train_period,
validation_period, holdout_period (2025, sealed until the locked
run), metrics (full hierarchy values + stage splits + top-k),
prediction_artifact (hash), model_artifact (hash or metadata-only
pointer), code_commit, calibration (method + evaluation-only flag),
parent_experiment (for rungs). Designed in V3-0, implemented in
V3.1A before any feature computation.

## Reproducibility

V3 requirements: deterministic feature construction (same inputs ->
byte-identical outputs; parity-tested batch vs single-state like
F2); frozen temporal splits (no new split without protocol
amendment); fixed seeds wherever sampling occurs (bootstrap,
simulation, any stochastic estimator); content hashes on every
artifact; machine-readable reports (no metric transcription by hand -
reports render from evaluation JSON); no notebook-only experiments
(every claim traces to a committed manifest + code); race-level
identity preserved end to end (state_id/race_id on every row).

## Compute discipline

Order cheap falsification first: (1) feature-contract tests (registry
invariants, causal unit tests on fixtures - seconds); (2) single-fold
smoke (D3 slice or one season - minutes); (3) full temporal CV
(D1-D3 - the current full fit is sub-second preprocessing + ~0.4 s
model fit + ~10 s canonical evaluation, so the gate is matrix
construction, not training); (4) locked holdout (once); (5) only then
model-family search (V3.3). Matrix build dominates cost: 189420 x 106
canonical today; dynamics add columns, not rows - profile the
dynamics calculators on one race before full-matrix construction.
Never concurrent heavy builds without evidence it is safe; cheap
static checks (lint, contract tests) run in parallel freely.

## Leakage threat model

| Threat | Risk | Mitigation | Test |
|---|---|---|---|
| Rolling windows incl. future laps | HIGH | source_time <= T predicate in every calculator | adversarial future-mutation suite (D11 pattern) |
| Future lap completion (leader laps ahead) | HIGH | scheduled-distance reference only; never observed==scheduled | progress-frac invariant tests |
| Pit outcomes (eventual stop result) | HIGH | fully-observed-past-only stops; never eventual end | asymmetric in/out-only stop fixtures |
| Result-derived fields (final position in running features) | HIGH | label firewall (calculators take no label input) | F13-style label-exclusion tests |
| Future-defined cohorts | HIGH | per-endpoint <=T cohorts, min contributors | cohort-membership audit tests |
| Season aggregates incl. current season | MEDIUM | past_races strictly prior; thresholds frozen | prior-history boundary tests |
| Post-race statistics (points, standings) | MEDIUM | priors from hist_results prior seasons only | provenance tests |
| Global normalization | MEDIUM | train-only fit, transform-only val (M3) | preprocessing scope tests |
| Target-derived filtering (eligibility as feature) | MEDIUM | masks never enter design matrix (forbidden lists) | forbidden-column tests |
| Simulation outputs as features | HIGH | forbidden: sim frequencies are post-T outcomes | import firewall test (dynamics never import simulation) |
| Spatial artifacts as features | MEDIUM | excluded from V3.1 by boundary | dependency-direction test |
| Imputation leaking val stats | MEDIUM | train-fitted medians/modes/vocabularies | refit-parity tests |
| Holdout tuning | HIGH | 2025 sealed; selection on D1-D3 only | ProtectedHoldout seal + review gate |
| Telemetry timing side-channels | LOW now | lap-time sources only; telemetry deferred | source-allowlist test |

## Failure modes

How v3 could lie to us, and the guardrail each gets: feature leakage
(adversarial D11-style suite, mandatory for every new calculator);
state weighting (race-macro authority; pooled is diagnostic);
race imbalance (per-race deltas + SC/partial subsets, not pooled
triumphs); hyperparameter overfitting (family fixed in V3.1; tuning
only in V3.3 under nested chronology); holdout tuning (seal + single
locked run); metric cherry-picking (predeclared hierarchy, primary
governs, rest veto); complexity without generalization (acceptance
clause 6 + Arm C diagnostic); calibration degradation (ECE veto, no
post-hoc rescue); early-race regression (stage veto); silent
missingness (NULL_IF_INSUFFICIENT_HISTORY + depth companions, zero-fill
forbidden); season availability drift (per-season coverage audit;
2018 sparse-era vs 2025 fixtures must both pass).

## V3 experimental ladder

V3-0 audit (this document) -> V3.1A dynamics contract (registry
definitions, causal proofs, manifest design implemented, NO
computation) -> V3.1B feature construction (calculators + fixtures +
matrix extension + parity tests) -> V3.1C controlled experiment
(Arms A/B/C, D1-D3, frozen hierarchy) -> V3.1D evaluation + freeze
(locked 2025 run, report, keep/drop verdict, contract freeze) ->
V3.2 MC2.0 (dynamic-state-fed simulation) -> V3.3 multi-model (family
as the single change) -> V3.4 ensemble (evidence-gated only) ->
V3.5 outcome distribution (new heads on frozen v3 features) ->
V3.6 strategy 2.0 -> V3.7 counterfactuals -> V3.8 consensus ->
V3.9 uncertainty -> V3.10 explorer -> V3.11 pre-race (separate task).
Each rung has a contract gate: the next rung starts only on a frozen,
reviewed contract, never on a promising intermediate.

## V3.1 implementation plan

Stages and gates (no code in V3-0):

- V3.1A CONTRACT (first thing built): v3 registry definitions for the
  candidate set (Section Dynamic feature candidates, items 1,3,4,5,6,7,9,10
  as the opening rung; 2,8 provisional), each with family,
  temporal_rule, min_history, missing policy, edge cases, and a causal
  proof sketch; experiment-manifest implementation; window-space
  declaration (horizons x framings x minimums grid). Gate A: contract
  review - every definition shows source_time <= T by construction.
- V3.1B CONSTRUCTION: calculators + fixture states (early/SC/pit/red/
  rookie cases mirroring F16 fixtures) + extended matrix + batch/single
  parity + D11-style adversarial suite for the new calculators. Gate B:
  all causal tests green, manifest hashes stable.
- V3.1C EXPERIMENT: Arm A reproduction (must match M7 development
  values within tolerance) then Arms B/C on D1-D3 under the frozen
  hierarchy; window selection by CV evidence. Gate C: predeclared
  analysis - no post-hoc arm redefinition.
- V3.1D EVALUATION/FREEZE: locked single 2025 run, stage + calibration
  + race-level paired analysis, keep/drop verdict under the Acceptance
  policy (null is acceptable), contract freeze + report. Stop/go gate:
  keep (all six acceptance clauses) / drop (publish null + keep the
  audited contract for V3.2 inputs) / revise (one P1-level fix, then
  re-run C-D - never silent iteration).

What is frozen before computation: registry definitions, window grid,
arms, hierarchy, acceptance clauses, manifest schema. Experiments
before model changes: all of V3.1C precedes any V3.3 family work.

## Scientific identities

Reverified without regeneration (exact, from
`results/v2_final_validation/p11_2_validation_summary.json`
`scientific_identities` + `docs/PHASE11_P11_7_FINAL_V2_FREEZE.md` +
`docs/PHASE9_P9_0_MODELS_ABOUT_AUDIT.md`):

- Serving: `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
- Phase-2 content: `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`
- Phase-2 parquet: `b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3`
- Explainability: `bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f`
- Replay: `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298`
  (149 races / 9644 checkpoints)
- Simulation: `r3-v1` through 2024 `phase6-r3-empirical`
  (scientific hash `4c2f85f0...23ff3f140`, parameter version
  `r3-v1.2024.4c2f85f08f1c`)

6/6 exact. No regeneration performed.

## Known uncertainties

- M7 development reference (0.071374 LL) vs FINAL_FIT holdout
  (0.068035 LL) differ by training design (multi-fold less-data fits
  vs single all-data fit predicting one season ahead) - descriptive,
  no overfitting claim licensed.
- Holdout is one season (24 races); dynamics evidence will inherit
  this width - race-level CIs will be wide; the ladder accepts that.
- M6 nested-tuning and M8 calibration-season-withheld references are
  design variants, not alternative baselines - Arm A reproduces the
  M7/CHAPTER head comparison only.
- 2018 sparse-era and the two partial races (2021-r12-R, 2022-r18-R)
  stress missingness paths; dynamics deepen that stress (more nulls
  early) - the depth-companion + stage-veto design is the answer, not
  certainty.
- Telemetry, DNF, weather-forecast, and qualifying-pace information
  ceilings are unmeasured - V3.1 cannot distinguish "dynamics don't
  matter" from "the needed dynamics aren't in lap data".
- Graphify counts (12626/30251/363) are navigation metadata, not
  scientific evidence.

## Entry gate

- [x] phase12-spatial-replay is exact HEAD (`e99a78f8`)
- [x] entry worktree clean (verified before analysis; no repair needed)
- [x] Graphify-first used (update + targeted queries before broad reads)
- [x] current task verified (`winner`/`is_winner`/`eligible_is_winner`)
- [x] baseline model verified (LogReg C=0.01, full spec, RAW)
- [x] baseline metrics verified (7/7 to full quoted precision + stages)
- [x] ALL_84 exactly enumerated (84/84 from registry, no hand list)
- [x] all 84 features semantically classified (family/dtype/temporal)
- [x] temporal semantics traced (rule per family + subtle-feature list)
- [x] model capability separated from feature capability
- [x] current knowledge map completed (knows, evidence-linked)
- [x] missing-information map evidence-based (absences, not assumptions)
- [x] Race Dynamics precisely defined (causal [T-W,T] definition)
- [x] state vs dynamics distinction explicit (spectrum placed)
- [x] dynamic candidates classified against existing features
  (ALREADY/PARTIALLY/MISSING/NOT_JUSTIFIED per candidate)
- [x] causal window contract defined (source_time <= T)
- [x] window-size experiment strategy defined (grid + CV selection)
- [x] pit-cycle contamination considered (H1-H4 + design)
- [x] SC/VSC/red effects considered (T0-T3 + default hypothesis)
- [x] early-history behavior considered (minimums + depths, no zeros)
- [x] task/target audit completed (6 tasks + DNF + strategy outcomes)
- [x] V3.1 target explicitly chosen (same frozen winner task)
- [x] controlled experimental arms designed (A/B/C, D deferred)
- [x] ALL_84 remains immutable (new-set naming designed, not built)
- [x] new feature-set naming/versioning designed (F16-pattern)
- [x] temporal splits preserved (D1-D3/FINAL/HOLDOUT unchanged)
- [x] metric hierarchy predeclared (LL > Brier/AUCs > ECE > top-k)
- [x] race-macro authority addressed (macro selects, pooled diagnoses)
- [x] EARLY/MID/LATE evaluation addressed (buckets + veto)
- [x] acceptance policy allows null result (explicit)
- [x] race-level paired statistical comparison designed (bootstrap)
- [x] calibration policy defined (evaluation-only, RAW)
- [x] V3.1 separated from Multi-Model Lab (family fixed; V3.3 owns it)
- [x] MC2.0 boundary defined (inputs interface, semantic firewall)
- [x] Ensemble boundary defined (evidence-gated, no naive averaging)
- [x] Outcome Distribution boundary defined (new heads, prerequisites)
- [x] Strategy2 boundary defined (post-MC2.0, no recommendation)
- [x] Counterfactual boundary defined (fact vs simulated, labeled)
- [x] MLxsimulation semantic mismatch preserved (never averaged)
- [x] uncertainty boundary defined (available now vs later)
- [x] pre-race kept separate (distinct task, no Lap-0 fakery)
- [x] Phase-12 spatial data excluded from V3.1 (default NO + reason)
- [x] V3 repository architecture proposed (extend, homes per layer)
- [x] artifact versioning designed (provenance chain)
- [x] experiment manifest designed (fields from frozen conventions)
- [x] reproducibility contract defined (determinism + hashes + no
  notebooks)
- [x] compute policy defined (cheap falsification first)
- [x] leakage threat model completed (14 threats with tests)
- [x] misleading-improvement failure modes documented (11 + guardrails)
- [x] V3 experimental ladder proposed (gates per rung)
- [x] concrete V3.1 implementation plan produced (A-D + gates)
- [x] six scientific identities exact (no regeneration)
- [x] no model retrained
- [x] no artifact regenerated
- [x] no production source changed
- [x] exactly two audit files created
- [x] nothing staged
- [x] nothing committed
- [x] nothing tagged
- [x] nothing pushed
