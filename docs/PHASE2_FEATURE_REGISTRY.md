# Phase-2 Feature Registry + Parity Skeleton (F2)

> F2 infrastructure: authoritative feature metadata, versioning, and
> computation contracts. Depends on F1 (`docs/PHASE2_TEMPORAL_SEMANTICS.md`,
> applied without reinterpretation). Registers 23 frozen Phase-1
> passthroughs + 1 planned grid contract (24 definitions, fingerprint
> `bbee9c3b79c34b8b…`; re-derive via `build_f2_registry().fingerprint()`).
> No substantive family implemented; engine calculators raise
> `NoCalculatorError`. Stdlib-only modules; 30 F2 tests green.

## 2. F1 dependency

Every temporal concept here is F1 verbatim: LAP_END target `T`,
per-driver progress (never global time), `prefix(d,T)`, `sync_state`
(latest rival `<= T`, no fall-forward/nearest/same-lap), field
snapshots with age provenance, age-vs-gap distinction, roster from D5
results identity only, `(state_time_s, lap_number, driver_id)` order.
The registry records which F1 operator each feature requires; F3
implements them.

## 3. Module architecture

```text
v2/features/
    __init__.py    (public surface; families MUST NOT be added here in F2)
    contracts.py   (vocabulary, FeatureDef, FeatureRequest/Result, tolerances)
    registry.py    (validation, label guard, registry, F2 inventory builder)
    engine.py      (skeleton interfaces + parity equality semantics)
```

Deliberately absent: `pace.py`, `gaps.py`, `traffic.py`, `priors.py`,
`weather.py`, `telemetry.py` — later stages only, when authorized.

## 4. Feature definition schema

`FeatureDef` (frozen dataclass): name, family (`FeatureFamily`), version
(int ≥ 1), dtype (`int64|float64|bool|string`), unit (explicit or
`unitless`), description, sources (≥1 exact `entity.field`),
formula_ref, temporal_rule (`TemporalRule`), sync (`SyncRequirement`),
min_history (`MinHistory`), missing (`MissingPolicy` +
`fallback_description` iff fallback), availability
(`v2.contracts.Availability`), predictive_eligible, status
(`FeatureStatus`). `availability` is required so POST_RACE/LABEL_ONLY
misuse is mechanically rejectable.

## 5. Family/status vocabulary

Families: `race_state, pace, tyre, stint, gap, relative, teammate,
field, traffic, rate, momentum, weather, race_control, driver_prior,
constructor_prior, circuit, grid, interaction`. Statuses:
`passthrough` (frozen reuse), `planned` (contracted, later-stage
implementation), `candidate`, `validated`, `experimental`, `deferred`,
`deprecated`. Status never implies model quality. Cross-driver
families (`gap, relative, teammate, field, traffic, rate`) must declare
non-`NONE` sync when predictive. Deferred concepts (telemetry,
reliability/DNF, rejoin/catch-time, qualifying-derived) are NOT
registered as features (see §20).

## 6. Versioning

Two levels: per-feature `version` (bump on any definition change:
formula, sources, temporal rule, sync, missingness, dtype/unit) and
matrix/schema `FEATURE_SET_VERSION` (`"v1"` — bump on
add/remove/rename/retype of any feature). `REGISTRY_VERSION` tracks
this module's schema. Metadata-only description clarifications do not
bump versions. Registry order is deterministic (sorted by name);
fingerprint = sha256 over canonical JSON.

## 7. Lineage rules

Sources are exact `entity.field` strings (e.g.
`driver_lap_state_d9.lap_time_s`, `results.grid_position`), ≥1 per
feature. Vague lineage (`FastF1`, `race data`, bare table names without
a field) is rejected. Lineage identifies origin; temporal availability
still controls eligibility — a listed source authorizes nothing by
itself.

## 8. Temporal-rule metadata

`TARGET_STATE | DRIVER_PREFIX | SYNCHRONIZED_FIELD | PAST_RACES |
PRE_RACE_CONSTANT | BACKWARD_ASOF`. No same-lap variant exists by
design (asserted by test). Operators themselves are F3; the registry
records the requirement.

## 9. Synchronization declaration

`NONE | SYNCHRONIZED_RIVAL | SYNCHRONIZED_FIELD`, bound to F1
`sync_state` / `field_snapshot`. Predictive cross-driver-family
features with `NONE` are rejected at registration. It is impossible to
declare same-lap synchronization — the vocabulary has no such value.

## 10. Missingness contracts

`PRESERVE_SOURCE_NULL | NULL_IF_INSUFFICIENT_HISTORY |
NULL_IF_INVALID_GEOMETRY | NULL_IF_NO_SYNC_STATE |
NULL_IF_NOT_APPLICABLE | DETERMINISTIC_FALLBACK` (fallback only with a
written mathematical justification). Descriptive only; no imputation is
encoded, no model fill values exist, and global imputation stays
banned. Passthroughs use `PRESERVE_SOURCE_NULL` (grid: not-applicable
for the 3 W-nulls).

## 11. Minimum-history representation

`NONE | COUNT(n ≥ 1) | POLICY_REF(reference)`. F2 sets NO family
constants (no pace min-n, no smoothing values — see §22); later stages
fill `COUNT`/`POLICY_REF` with evidence. Invalid declarations (n < 1,
empty ref, history on `NONE`) are rejected.

## 12. Unit policy

Explicit unit required; `unitless` is the canonical marker for
fractions, counts, booleans, categoricals. Passthrough units are taken
from frozen Phase-1 schemas (seconds, laps, position, °C, %, hPa, m/s,
degrees, fraction, stops, none/n-a where frozen).

## 13. D9 passthrough inventory (23 registered, F2 scope)

`position`, `race_leader_laps_at_state`, `race_progress_frac`,
`track_state`, `flag_yellow`, `flag_safety_car`, `flag_vsc`,
`flag_red`, `pit_stops_completed_so_far`, `laps_since_last_pit_stop`,
`stint_lap`, `compound`, `tyre_life`, `fresh_tyre`, `wx_air_temp_c`,
`wx_track_temp_c`, `wx_humidity_pct`, `wx_pressure_hpa`,
`wx_wind_speed`, `wx_wind_direction_deg`, `wx_rainfall`,
`stint_compound`, `stint_fresh_tyre` — all `PASSTHROUGH`, version 1,
dtype/unit/availability/eligibility read from frozen schemas at build
time (drift-impossible; test-pinned). No recomputation. Non-predictive
provenance (staleness anchors, message seqs, boundary lineage,
quality flags) is NOT registered (test asserts zero overlap).

## 14. Grid planned contract

`grid_position` (`grid` family, `PLANNED`, PRE_RACE, `results.grid_position`,
3,455/3,458 with 3 known W-nulls, `NULL_IF_NOT_APPLICABLE`). Only the
grid field + `(race_id, driver_id)` identity join path; outcome columns
excluded by the label guard. The join implementation belongs to F10 —
registration as `PLANNED` records intent without pretending an ACTIVE
feature. No qualifying fields exist or are registered.

## 15. Label guard

`label_outcome_fields()` derives from Phase-1 metadata (D9 label layer
+ D5 results `LABEL_ONLY`, plus DNF belt-and-braces). Predictive
definitions matching an outcome by name OR sourcing one are rejected
(tested for `winner_flag`, `position_final`, `points`,
`race_driver_labels.*`, and `hist_results.dnf_flag`). No binary DNF
field exists and none is added.

## 16. Request/result contracts

`FeatureRequest(race_id, driver_id, lap_number, state_time_s)` with
deterministic `.key()`; carries no labels by construction.
`FeatureResult` carries target identity + `feature_set_version` +
sorted `(name, value)` pairs (None = null) + optional provenance.
Provenance is excluded from parity equality by default.

## 17. Engine skeleton

`features_for_state` / `features_for_batch` define the F1/F2
interfaces and raise `NoCalculatorError` (a `NotImplementedError`):
no calculators exist, and unfinished computation must fail explicitly
— no dummy zeros, no placeholder probabilities, no fabricated values.
Passthrough resolution belongs to F4 and is NOT implemented here.

## 18. Parity semantics

Invariant: `batch_features(S) == features_for_state(prefix_to_S, S)`
per feature-set versi
...[truncated 1109 chars]