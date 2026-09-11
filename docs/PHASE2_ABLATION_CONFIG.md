# Phase-2 Ablation Configuration + Model-Lab Handoff Fixtures (F16)

> F16 objective: freeze the feature-family experiment configuration the
> Phase-3 Model Lab will use for feature-family ablations, controlled
> feature-set comparisons and deterministic fixtures — before any model
> is trained. F16 does NOT evaluate whether a family is useful; it
> defines which feature groups can be added/removed/compared without
> inventing feature lists ad hoc. The canonical F15 matrix is unchanged.

------------------------------------------------------------------------

## 1. Objective

Define and freeze, as configuration metadata only:

- a small interpretable partition of the 84 predictive features into
  primary semantic groups;
- a cumulative (staged) experiment plan;
- a leave-one-group-out (LOGO) experiment plan with deterministic
  interaction-dependency removal;
- simple factual baselines for comparison;
- an `ALL_84` set that must equal the F15 manifest exactly;
- a minimal `resolve_feature_set` API preserving canonical order;
- deterministic representative fixtures for Phase-3 tests;
- a deterministic machine-readable export with a semantic hash.

F16 prepares future experiments. It never runs them.

## 2. Frozen entry state (verified, not assumed)

| Item | Value |
|---|---|
| `FEATURE_SET_VERSION` | `v8` |
| predictive definitions | 84 |
| `LABEL_SET_VERSION` | `v1` |
| label definitions | 7 |
| `MATRIX_VERSION` | `v1` |
| matrix rows | 189,420 |
| matrix predictive columns | 84 |
| matrix metadata / label+companion / task masks | 9 / 8 / 5 |
| matrix `content_hash` | `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db` |
| races / seasons | 173 / 2018–2025 |
| telemetry | absent (ADR-0001 holds) |

Verified by reading the F15 manifest and re-deriving the predictive list
from `build_f11_registry()`. The matrix artifact and manifest were
byte-identical before and after the F16 export.

## 3. Non-modeling scope

F16 contains no estimator import, no train/test fold, no log loss,
Brier, accuracy, calibration, feature importance, SHAP, feature
selection, preprocessing, imputation, encoding or scaling. No family is
declared useful or useless. No production model is selected. This is
pinned by a static source scan and by the absence of model modules in
the F16 dependency graph.

## 4. Registry authority

`v2/experiments/feature_sets.py` resolves every group member from
`build_f11_registry()` metadata. There is no hand-written copy of the
84-name master list. `validate_registry()` fails unless
`FEATURE_SET_VERSION == "v8"`, the predictive count is exactly 84, names
are unique, no canonical label name is present and no `DEFERRED`
definition is predictive. `ALL_84` is derived from the same registry and
is asserted equal to the F15 manifest `predictive_columns`.

## 5. Primary semantic groups

Eight non-overlapping primary groups, chosen to match the approved
Phase-2 families and their factual/derived semantics:

| Group | Meaning | Source families |
|---|---|---|
| `STATE` | factual current race state at LAP_END | race_state, tyre, stint (factual), race_control (current), weather (current) |
| `PACE` | past-only target-driver pace | pace, stint (derived pace) |
| `GAPS` | structured synchronized gap representation | gap |
| `FIELD_CONTEXT` | relative / teammate / field / traffic | relative, teammate, field, traffic |
| `RATES_MOMENTUM` | trailing change rates and momentum | rate, momentum |
| `ENVIRONMENT_HISTORY` | derived weather + race-control history | weather (history), race_control (history) |
| `PRE_RACE_PRIORS` | factual grid + past-only driver/constructor/circuit priors | grid, driver_prior, constructor_prior, circuit |
| `INTERACTIONS` | the three explicit F11 interactions | interaction |

Group order follows the approved F4–F11 computation DAG, with
`INTERACTIONS` last.

## 6. Exact feature → primary group partition (84/84)

Partition computed from the registry; every feature assigned exactly
once. Counts: `STATE 23 · PACE 12 · GAPS 8 · FIELD_CONTEXT 12 ·
RATES_MOMENTUM 4 · ENVIRONMENT_HISTORY 9 · PRE_RACE_PRIORS 13 ·
INTERACTIONS 3`.

### STATE (23)
- `compound`
- `flag_red`
- `flag_safety_car`
- `flag_vsc`
- `flag_yellow`
- `fresh_tyre`
- `laps_since_last_pit_stop`
- `pit_stops_completed_so_far`
- `position`
- `race_leader_laps_at_state`
- `race_progress_frac`
- `stint_compound`
- `stint_fresh_tyre`
- `stint_lap`
- `track_state`
- `tyre_life`
- `wx_air_temp_c`
- `wx_humidity_pct`
- `wx_pressure_hpa`
- `wx_rainfall`
- `wx_track_temp_c`
- `wx_wind_direction_deg`
- `wx_wind_speed`

### PACE (12)
- `current_stint_eligible_laps`
- `current_stint_pace_mean_s`
- `current_stint_pace_median_s`
- `current_stint_pace_trend_s_per_lap`
- `pace_mean_5`
- `pace_median_10`
- `pace_median_3`
- `pace_median_5`
- `pace_n_10`
- `pace_n_3`
- `pace_n_5`
- `representative_recent_pace_s`

### GAPS (8)
- `ahead_observation_age_s`
- `gap_to_ahead_laps`
- `gap_to_ahead_seconds`
- `gap_to_ahead_seconds_valid`
- `gap_to_leader_laps`
- `gap_to_leader_seconds`
- `gap_to_leader_seconds_valid`
- `leader_observation_age_s`

### FIELD_CONTEXT (12)
- `cars_ahead_observable`
- `cars_behind_observable`
- `field_pace_comparable_rivals`
- `in_traffic_2s`
- `nearby_cars_within_5s`
- `observable_field_size`
- `relative_pace_to_car_ahead_s_per_lap`
- `relative_pace_to_field_median_s_per_lap`
- `relative_pace_to_teammate_s_per_lap`
- `teammate_lap_difference`
- `teammate_observation_age_s`
- `teammate_position`

### RATES_MOMENTUM (4)
- `recent_gap_to_ahead_change_s_per_lap`
- `recent_gap_to_leader_change_s_per_lap`
- `recent_pace_change_s_per_lap`
- `recent_position_change_5laps`

### ENVIRONMENT_HISTORY (9)
- `air_temp_change_5min_c`
- `current_track_state_duration_s`
- `rain_in_last_5min`
- `recent_red_fraction_5min`
- `recent_sc_vsc_fraction_5min`
- `recent_yellow_fraction_5min`
- `time_since_rain_observed_s`
- `track_state_changes_5min`
- `track_temp_change_5min_c`

### PRE_RACE_PRIORS (13)
- `grid_position`
- `prior_circuit_mean_pit_stops_per_entry`
- `prior_circuit_mean_position_change`
- `prior_circuit_races`
- `prior_constructor_mean_finish`
- `prior_constructor_points_per_entry`
- `prior_constructor_races`
- `prior_driver_mean_finish`
- `prior_driver_mean_grid`
- `prior_driver_points_per_start`
- `prior_driver_starts`
- `recent_constructor_points_per_entry_5`
- `recent_driver_mean_finish_5`

### INTERACTIONS (3)
- `positions_from_grid`
- `recent_gap_to_ahead_change_in_traffic_s_per_lap`
- `relative_pace_to_ahead_in_traffic_s_per_lap`

## 7. Factual vs derived distinctions

`STINT`, `RACE_CONTROL` and `WEATHER` each mix factual current state
with derived history, so family alone is insufficient. The partition
splits them by the registry `temporal_rule`:

- Factual stint state (`TARGET_STATE`) → `STATE`;
  derived current-stint pace (`DRIVER_PREFIX`) → `PACE`.
- Current race-control flags / `track_state` (`TARGET_STATE`) →
  `STATE`; duration/transition/fraction history (`DRIVER_PREFIX`) →
  `ENVIRONMENT_HISTORY`.
- Current as-of weather (`BACKWARD_ASOF`) → `STATE`; weather deltas and
  rain recency (`DRIVER_PREFIX`) → `ENVIRONMENT_HISTORY`.

This keeps "where the race is now" separate from "how it got here" and
avoids putting two different domains in one group only because they
share a registry family.

## 8. Grid / prior subgroup decision

`grid_position` is a factual pre-race constant; driver/constructor/
circuit priors are past-race aggregates. They enter together at F10, so
the primary plan groups them as `PRE_RACE_PRIORS`. Two diagnostic
subgroups are frozen so Phase 3 can separate them without changing F16:

- `GRID_ONLY` = `{grid_position}` (1)
- `HISTORICAL_PRIORS_ONLY` = the other 12 pre-race prior features

Subgroups are diagnostic and do not alter the primary partition.

## 9. Interaction dependencies

Dependencies are read from `v2/features/interactions.py`
`REQUIRED_PRIMITIVES`, mapped to primary groups (never a second table):

| Interaction | Required primitives | Required groups |
|---|---|---|
| `positions_from_grid` | `grid_position`, `position` | `PRE_RACE_PRIORS`, `STATE` |
| `relative_pace_to_ahead_in_traffic_s_per_lap` | `relative_pace_to_car_ahead_s_per_lap`, `in_traffic_2s` | `FIELD_CONTEXT` |
| `recent_gap_to_ahead_change_in_traffic_s_per_lap` | `recent_gap_to_ahead_change_s_per_lap`, `in_traffic_2s` | `FIELD_CONTEXT`, `RATES_MOMENTUM` |

## 10. Interaction removal policy (frozen)

1. **Cumulative:** `INTERACTIONS` is appended only in the final stage,
   after every parent primitive group is present.
2. **Leave-one-group-out:** removing a primary group also removes every
   interaction whose required primitive is a member of that group. The
   removed interactions are recorded explicitly per configuration.

Consequences: removing `FIELD_CONTEXT` removes both traffic-gated
interactions; removing `STATE` or `PRE_RACE_PRIORS` removes
`positions_from_grid`; removing `RATES_MOMENTUM` removes the
traffic-gated gap rate. No orphan interaction survives its parent.

## 11. Cumulative plan

`CUMULATIVE_00_STATE → … → CUMULATIVE_07_INTERACTIONS`, following the
F4–F11 DAG. Each rung adds exactly one semantic group. This answers
"what incremental descriptive value appears as richer temporal context
is introduced?" — it does **not** claim causal contribution.

## 12. Cumulative counts (exact)

| Config | Groups | Features |
|---|---|---|
| `CUMULATIVE_00_STATE` | STATE | 23 |
| `CUMULATIVE_01_PACE` | + PACE | 35 |
| `CUMULATIVE_02_GAPS` | + GAPS | 43 |
| `CUMULATIVE_03_FIELD_CONTEXT` | + FIELD_CONTEXT | 55 |
| `CUMULATIVE_04_RATES_MOMENTUM` | + RATES_MOMENTUM | 59 |
| `CUMULATIVE_05_ENVIRONMENT_HISTORY` | + ENVIRONMENT_HISTORY | 68 |
| `CUMULATIVE_06_PRE_RACE_PRIORS` | + PRE_RACE_PRIORS | 81 |
| `CUMULATIVE_07_INTERACTIONS` | + INTERACTIONS | 84 |

Monotonic (`C0 ⊂ C1 ⊂ … ⊂ C7`) and `C7 == ALL_84`.

## 13. LOGO plan

`ALL_MINUS_<GROUP>` = `ALL_84` minus the group, minus any interaction
whose parent primitive belongs to that group (section 10).

## 14. LOGO counts (exact)

| Config | Removed | Features |
|---|---|---|
| `ALL_MINUS_STATE` | STATE + `positions_from_grid` | 60 |
| `ALL_MINUS_PACE` | PACE | 72 |
| `ALL_MINUS_GAPS` | GAPS | 76 |
| `ALL_MINUS_FIELD_CONTEXT` | FIELD_CONTEXT + 2 traffic interactions | 70 |
| `ALL_MINUS_RATES_MOMENTUM` | RATES_MOMENTUM + `recent_gap_to_ahead_change_in_traffic_s_per_lap` | 79 |
| `ALL_MINUS_ENVIRONMENT_HISTORY` | ENVIRONMENT_HISTORY | 75 |
| `ALL_MINUS_PRE_RACE_PRIORS` | PRE_RACE_PRIORS + `positions_from_grid` | 70 |
| `ALL_MINUS_INTERACTIONS` | INTERACTIONS | 81 |

## 15. Simple baseline configurations

| Config | Exact columns | Count |
|---|---|---|
| `CURRENT_ORDER_ONLY` | `position` | 1 |
| `MINIMAL_RACE_STATE` | `grid_position`, `position`, `race_progress_frac` | 3 |

Baselines are intentionally tiny and factual. The nullable pit-lane
grid code (0) is preserved; no imputation or engineered convenience
values are added. These are feature configurations, not the non-ML
racing heuristics ("current leader wins" etc.) that belong to Phase-3
evaluation code.

## 16. ALL_84

`ALL_84` resolves to exactly the F15 manifest `predictive_columns` in
canonical (registry/name-sorted) order; asserted equal to
`build_f11_registry()` predictive names and to
`manifest["predictive_columns"]`.

## 17. Feature-group contract

`FeatureGroup` (frozen dataclass): `name`, `description`, `rationale`,
`source_families`, `dependencies`, `version` (1), `status` ("frozen"),
`features` (resolved names, canonical order). `FeatureSet`: `name`,
`kind` (`all|baseline|cumulative|logo`), `description`, `features`,
`groups`, `rationale`. This is configuration metadata, not a generic
experiment framework.

## 18. Config version

`ABLATION_CONFIG_VERSION = "v1"`, independent of and never mutating
`FEATURE_SET_VERSION` (`v8`), `LABEL_SET_VERSION` (`v1`) or
`MATRIX_VERSION` (`v1`). Required versions are declared explicitly and
checked against the manifest.

## 19. Machine-readable export

`write_ablation_config(paths)` writes
`data/v2/processed/model_matrix/matrix_version=v1/ablation_config.json`
(a separate artifact beside the F15 manifest; never a matrix copy).
`ablation_config_dict()` returns the same structure in memory and
`render_ablation_config()` returns canonical JSON text. Recorded
fields: config version, required feature/label/matrix versions, primary
groups, semantic subgroups, interaction dependencies and policy,
named feature sets (cumulative, LOGO, baselines, `ALL_84`),
fixture metadata, partition audit, registry fingerprint, config hash.
Repeated export is byte-identical.

## 20. Matrix compatibility

`validate_manifest_compatibility(manifest)` fails loudly unless
`matrix_version == v1`, `feature_set_version == v8`,
`label_set_version == v1`, the predictive count is 84, the predictive
list equals the canonical registry list exactly, and no metadata/
label/companion/task-mask column appears in the predictive list.

## 21. Resolution API

`resolve_feature_set(name, manifest=None, registry=None)` returns an
ordered tuple of predictive names. It validates the manifest when
supplied, preserves canonical order, rejects unknown configuration
names and missing/forbidden features, and never infers columns from
dataframe contents. `group_features`, `partition_audit`,
`interaction_dependencies`, `validate_registry`,
`validate_feature_names`, `resolve_fixture` and `get_feature_set` round
out the configuration surface.

## 22. Overlap policy

Primary groups partition `ALL_84` exactly once: 84 assigned, zero
unassigned, zero multiply assigned (asserted by `partition_audit`).
`GRID_ONLY` / `HISTORICAL_PRIORS_ONLY` are diagnostic subgroups that
overlap their parent group but do not alter the primary partition.

## 23. Target independence

Feature configurations carry no prediction target. The same
configuration is usable for winner, podium, points, ordinal finish and
gain/loss subject to the F15 task eligibility masks. No
target-specific feature set is created; `resolve_feature_set` accepts
no target/task parameter.

## 24. Experiment fixtures

Eleven deterministic canonical states (not model results) selected to
exercise loader behaviour, later temporal splits, feature-set
resolution, task masks and later preprocessing. Fixture selection uses
stable `state_id` (`race_id|driver_id|lap_number`), never row offsets.

## 25. Fixture manifest

| Fixture | state_id | Coverage | Rationale |
|---|---|---|---|
| `era_2018_caution_mid` | `2018-r01-R\|ricciardo\|27` | 2018, mid, dry, caution | sparse-era mid state under Safety Car |
| `era_2025_dry_late` | `2025-r01-R\|norris\|41` | 2025, late, dry | newest era, late dry state |
| `stage_early_dry_2023` | `2023-r01-R\|alonso\|5` | 2023, early, dry | history-limited windows/null handling |
| `stage_mid_dry_2023` | `2023-r01-R\|alonso\|28` | 2023, mid, dry | normal operating point |
| `stage_late_dry_2023` | `2023-r01-R\|alonso\|50` | 2023, late, dry | deepest history |
| `wet_2019_germany` | `2019-r11-R\|hamilton\|20` | 2019, mid, wet | rain + intermediate tyres |
| `partial_wet_2021_belgium` | `2021-r12-R\|hamilton\|2` | 2021, partial, wet | PARTIAL race, null compound |
| `partial_red_2022_japan` | `2022-r18-R\|ocon\|2` | 2022, partial, red, wet | red-flag invalidity |
| `pit_lane_start_2019` | `2019-r04-R\|kubica\|49` | 2019, late, pit_lane | grid_position 0 preserved |
| `rookie_substitute_2023` | `2023-r13-R\|lawson\|30` | 2023, mid, rookie | cold-start priors |
| `mask_position_null_2018` | `2018-r01-R\|sirotkin\|5` | 2018, early, mask_edge | position null → ordinal/gain-loss mask False, binary True |

Each fixture records name, state_id, race/driver/constructor identity,
season, round, lap, rationale, coverage tags and expected task-mask
states. No predictions or metrics are stored.

## 26. Fixture safety

Fixtures are testing aids, not evaluation samples. F16 assigns no
`train` / `validation` / `test` / `holdout` split label; the temporal
evaluation protocol is frozen in Phase 3 / M0. `validate_fixtures`
checks existence exactly once, identity agreement, availability of all
84 predictive columns, expected task-mask states and the absence of
unclassified (prediction/metric) columns.

## 27. Fixture stability

Fixture identity is the canonical `state_id`, which is stable under row
reordering; validation resolves it from the canonical matrix and fails
if it is not present exactly once. `df.iloc[...]` is never the fixture
identity.

## 28. Phase-3 handoff

Minimal, model-free surface:

```python
from v2.experiments import feature_sets as A

A.resolve_feature_set("ALL_MINUS_GAPS", manifest)   # ordered predictive names
A.resolve_feature_set("MINIMAL_RACE_STATE", manifest)
A.resolve_fixture("wet_2019_germany")               # FixtureDef
A.load_canonical_matrix(paths)                       # (matrix, manifest)
A.load_task("winner", paths)                         # (X, y, eligibility_mask)
A.validate_fixtures(matrix, manifest)                # report
```

No estimator, no split, no preprocessing is provided or imported.

## 29. Deterministic hash

`semantic_hash()` = SHA-256 over canonical JSON of config version,
required versions, primary groups/features, subgroups, interaction
dependencies and policy, named feature sets and fixture identities.
Paths and timestamps are excluded. Measured:
`c88bcbaafe72ff2a615f24563d631f4e313cbc1d41e23b3818d3f9d86f6b087c`.
Repeated export hashes identically.

## 30. Drift behaviour

Explicit failure (never silent adaptation) when:

- `FEATURE_SET_VERSION` changes or the registry predictive count leaves
  84 / a feature is added or removed;
- the manifest feature/label/matrix version changes;
- the manifest predictive list gains/loses a feature or reorders;
- a label, task mask or metadata column enters a configuration;
- a duplicate feature occurs in a configuration;
- an interaction dependency points to an unknown/unpartitioned feature;
- an unknown primary group or configuration name is requested;
- a fixture `state_id` is missing or duplicated.

A future feature version requires a deliberate
`ABLATION_CONFIG_VERSION` update; F16 v1 will not absorb new columns.

## 31. Matrix immutability

F16 writes only `ablation_config.json` beside the F15 manifest. The
`model_matrix.parquet` and `manifest.json` byte hashes and the manifest
`content_hash` were identical before and after export (tested), and
F16 contains no matrix-build call.

## 32. Performance (measured)

| Operation | Time |
|---|---|
| `validate_registry` | ~0.4 ms |
| `build_primary_groups` | ~0.5 ms |
| `build_feature_sets` | ~1.5 ms |
| `resolve_feature_set("ALL_84")` | ~1.6 ms |
| `ablation_config_dict` / `render_ablation_config` | ~9 ms |
| `validate_fixtures` | one canonical matrix load (~1 s) + row lookups |

F16 never rebuilds the 189,420-row matrix.

## 33. Limitations

- Primary groups are a semantic partition, not a claim that groups are
  independent; cross-family statistical correlation is not measured.
- `GRID_ONLY` / `HISTORICAL_PRIORS_ONLY` are diagnostic only.
- Fixtures span 2018–2025 but are a small convenience sample, not an
  evaluation population.
- The config hash changes if any grouping metadata changes; it is not a
  content hash of the matrix.

## 34. F17 handoff

F17 consumes: the frozen F16 configuration and hash, the F15 manifest +
matrix, the label/task contracts, and the fixtures. F17 owns the
Phase-2 architecture/registry/quality documentation and the final
Phase-2 validation and exit; it must not train models or start Phase 3.
