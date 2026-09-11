# Phase-2 D9 Factual Passthrough Layer (F4)

> F4 connects frozen D9 factual state to the feature engine as true
> passthroughs: `v2/features/passthrough.py` + engine dispatch, 23
> registered definitions resolved, 22 tests green, full 189,420-row
> audit clean. Depends on F1 (exact target), F2 (registry/contracts),
> F3 (`resolve_target`). No recomputation, no new families.

## 2. F1/F2/F3 dependencies

F1 exact-target semantics (`resolve_target`: no close-timestamp
substitution); F2 registry as the sole inventory + `FeatureResult`
contracts + `NoCalculatorError` + `results_equal`; F3 operators reused,
not duplicated. F1/F2/F3 contracts unreinterpreted.

## 3. Exact passthrough inventory (registry order, sorted-by-name)

`compound`, `flag_red`, `flag_safety_car`, `flag_vsc`, `flag_yellow`,
`fresh_tyre`, `laps_since_last_pit_stop`, `pit_stops_completed_so_far`,
`position`, `race_leader_laps_at_state`, `race_progress_frac`,
`stint_compound`, `stint_fresh_tyre`, `stint_lap`, `track_state`,
`tyre_life`, `wx_air_temp_c`, `wx_humidity_pct`, `wx_pressure_hpa`,
`wx_rainfall`, `wx_track_temp_c`, `wx_wind_direction_deg`,
`wx_wind_speed` (23). Groups: race state (3), track state (5),
pit/stint (3 + stint factuals under tyre), tyre (5), weather (7).
`grid_position` is PLANNED (F10 join) and explicitly NOT resolved.

## 4. Registry-driven resolution

`_target_definitions` validates each definition, requires status
PASSTHROUGH and a single `driver_lap_state_d9.<own-name>` source;
default resolves the whole passthrough set, explicit `names=` subsets
allowed. Requested PLANNED/CANDIDATE/DEFERRED/unregistered names raise
`NoCalculatorError` — never fabricated. Only approved registered
passthroughs can enter a `FeatureResult`.

## 5. Exact target semantics

Target `(race_id, driver_id, lap_number, state_time_s)` must match a
D9 row exactly; close timestamps raise `TargetNotFoundError`. No
backward/forward fallback for the target; no cross-driver sync needed
(single-row copy).

## 6. Null policy

D9 null → result null, always: compound/tyre/stint nulls (Monaco,
Miami patterns), `laps_since_last_pit_stop` pre-first-stop nulls
(32.09%), pit-lineage nulls. No 0/-1/`"UNKNOWN"`/median/fill unless the
D9 cell literally holds that value (tested). Imputation stays Phase-3.

## 7. Type representation

Canonical result scalars: numpy int→`int`, float→`float`, NaN/NA/NaT→
`None`, numpy bool→`bool`, str→`str`; anything else raises
`TemporalError` rather than coercing meaning. Types pinned by test
(position int, progress float, flags bool, track/compound str).

## 8. Single-state path

`features_for_state(request, registry, states[, names])` →
`passthrough_for_state`: validate → exact lookup → copy 23 values →
`FeatureResult` with `feature_set_version="v1"` + minimal provenance
(`source=driver_lap_state_d9`, `calculator=passthrough`).

## 9. Batch path

`passthrough_batch(states, registry[, names])` → DataFrame
`[identity × 4 | 23 features]` in registry order, sorted, input
unmutated (tested). Vectorized column selection — no recomputation.
Not the F15 canonical matrix (no manifest/versioned artifact).

## 10. Parity evidence

Single-vs-batch equality via `results_equal` on sampled targets +
full-scope audit comparison; engine `features_for_batch` returns per-
request results through the same definitions. Passthrough parity is
exact (copy, not recomputation). All green.

## 11. Future-mutation evidence

Add/delete future driver rows, future rival rows, future timing
changes, row reorder, future-row deletion, future label-table presence:
target result identical (tested). Target-row mutation is the only
change that moves the result.

## 12. Source-isolation evidence

Mutating the target's `compound` changes only `compound`; mutating
non-registered (`source_unit_status`), non-predictive, or label
decoys changes nothing (tested). Registry-driven isolation holds.

## 13–15. Track-state / weather / pit-stint handling

Copied exactly: no TrackStatus reinterpretation, no RC text/state
machine, no flag "correction"; no weather rejoin/interpolation/trend/
delta/forecast (F9 owns context); no pit-history reconstruction,
no missing pit-out inference, no stint-end use, no pit-window/rejoin
(F-strategy). D9 values are final.

## 16. Feature-set version decision

No definition, schema, or registry change in F4 → NO version bumps:
per-feature versions stay 1, `FEATURE_SET_VERSION` stays `"v1"`,
`REGISTRY_VERSION` unchanged. Enabling the calculator is engine
implementation only, per F2 policy (policy covers definition/schema
changes, not calculator availability). Documented here as required.

## 17. Full-data audit (MEASURED, 189,420 rows)

Batch over all D9 states: row count, identity frame, per-feature
values AND null masks all equal source (NaN-aware, all 23 features);
output columns exactly identity+23; zero label/outcome columns.
Clean — encoded as `test_full_scope_audit` (runs in ~2 s).

## 18. Performance (MEASURED)

Single-state lookup 6.88 ms (pandas masked lookup; fine for
inference/replay cadence; batch path exists for bulk). Full-scope
vectorized batch 0.07 s. No optimization needed; per-row loops
correctly avoided in batch.

## 19. Limitations

Single-state path is pandas-bound (matches D9 tooling); `names=`
subsets preserve registry relative order; provenance minimal by
design; grid/labels/matrices remain later stages.

## 20. F5 handoff

F5 consumes: `resolve_target`/`driver_prefix`/`rolling_past_observations`
(F3), registry validation patterns, `canonical_scalar` conventions,
and these passthroughs as window inputs (`lap_time_s` is notably NOT
a passthrough — F5 sources it directly per its own contract). No F5
constants, masks, or statistics were created here.
