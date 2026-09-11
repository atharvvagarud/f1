# Phase-2 Canonical Model-Ready Feature Matrix (F15)

> F15 objective: materialize the canonical Phase-2 model-ready dataset
> from the approved, leakage-audited components — frozen D9 driver-lap
> state identities + all 84 registry-authorized predictive definitions
> + the F13 label layer + required identity/time/grouping metadata —
> into deterministic, versioned, auditable Parquet + manifest.
>
> Assembly/materialization ONLY. No new feature, no new label, no model
> training, no split, no imputation/encoding/scaling, no rebalancing.
> `FEATURE_SET_VERSION=v8` (84) and `LABEL_SET_VERSION=v1` (7) are
> frozen; `MATRIX_VERSION=v1` is a new assembly-only version.

## 2. Frozen entry state (verified)

`FEATURE_SET_VERSION=v8` / 84 definitions; `LABEL_SET_VERSION=v1` / 7
definitions; D9 states 189,420; race-driver labels 3,458; races 173;
no telemetry. Entering baseline: 780 passed / 4 xfailed / 21 frontend /
D11 44-0-0.

## 3. Matrix grain

One row per frozen D9 driver-lap state, identity
`(race_id, driver_id, lap_number, state_time_s)` with a derived
non-predictive `state_id = "race_id|driver_id|lap_number"`. The D9 PK
`(race_id, driver_id, lap_number)` is unique (F0: 0 duplicates), so the
4-tuple is unique too (including the equal-time 2021-r08 Stroll lap 4/5
pair, which differs by `lap_number`).

## 4. Column classes (machine-readable in the manifest)

106 columns total, each mapped to exactly one class:

- **METADATA / IDENTITY (9):** race_id, season, round_no, circuit_id,
  driver_id, constructor_id, lap_number, state_time_s, state_id.
- **PREDICTIVE FEATURES (84):** the registry's predictive definitions,
  in registry (sorted-name) order.
- **LABEL (7 + 1 companion):** final_position, is_winner, is_podium,
  scored_points, position_change_from_state, gains_position_by_finish,
  loses_position_by_finish; companion `classified_flag` (non-predictive,
  carried so ordinal eligibility is reconstructible).
- **TASK ELIGIBILITY (5, non-predictive):** eligible_is_winner,
  eligible_is_podium, eligible_scored_points,
  eligible_ordinal_final_position, eligible_gain_loss.

No ambiguous columns; no feature/label/task name overlap (validated).

## 5. Feature registry authority

`resolve_predictive_names()` reads the predictive set from
`build_f11_registry()`; it fails loudly unless
`FEATURE_SET_VERSION == "v8"`, the count is exactly 84, names are
unique, and no DEFERRED definition is marked predictive. No hand-written
list exists.

## 6. Label registry authority

`resolve_label_names()` reads `build_label_registry()`; fails unless
`LABEL_SET_VERSION == "v1"` and the count is 7. Labels originate from
`v2.labels.builder.build_label_frame` (frozen D9 `race_driver_labels`);
F15 duplicates no target definition.

## 7. State-dependent labels

The 3 F13 SPECIFIED formulas are materialized vectorized and conform to
the frozen `v2.labels.builder` pure functions (2000-row conformance
test): `position_change_from_state = current_position − final_position`
(null-propagating, tie = 0); `gains_position_by_finish = change > 0`;
`loses_position_by_finish = change < 0`. Never called overtaking.

## 8. Ordinal eligibility

`eligible_ordinal_final_position` is the vectorized
`ordinal_training_eligible(classified_flag, final_position)`:
classified + numeric → True; unclassified (incl. W/D back-rank numerics)
→ False; unknown → null. Measured: 178,963 state rows eligible vs
189,420 non-null `final_position` — a Phase-3 ordinal model cannot
silently train on every non-null position. The indicator is task
metadata, not a feature (84 count unchanged).

## 9. Task masks

Five masks, direct consequences of the frozen label contracts:
`eligible_is_winner`/`eligible_is_podium` (label non-null; all 189,420
states), `eligible_scored_points` (all 189,420), ordinal (178,963),
`eligible_gain_loss` (189,126; 294 position-null states excluded). No
train/test mask; no task-selection policy invented. `TASKS` maps each
Phase-3 task to `(label, mask)`.

## 10. No row drops

All 189,420 D9 states are preserved. No global row filtering for pace
history, priors, gap validity, weather, task ineligibility or early-race
history. Missingness is factual state.

## 11. No imputation

No `fillna`/mean/median/zero/forward/back-fill anywhere in the builder
(static scan + no-op). Canonical missingness is exactly as produced by
F4–F11; model preprocessing is Phase 3.

## 12. No encoding

No one-hot/ordinal/standardize/normalize/scale/target/frequency
encoding; no sklearn. Values are stored in their approved semantic
representation (categoricals as strings, booleans nullable, ints
nullable).

## 13. No row sampling

No undersample/oversample/balance/stratify/random sample. The matrix is
the complete approved state population.

## 14. Computation DAG (actual code dependencies)

```text
D9 state ──┬── passthrough   (23)
           ├── pace          (12)
           ├── gap           (8)
           ├── environment   (9)
           └── [history H<R]─ priors (13, incl. grid)
D9 + primitives:
  context (12)     <- pace basis + gap geometry (internal batch cache)
  rates   (4)      <- gap results + pace basis (internal batch cache)
  interactions (3) <- merged approved primitive columns only
labels (7)         <- race_driver_labels (many_to_one on race_id,driver_id)
```

## 15. Batch / reuse architecture

`compute_family_frames` calls each family batch exactly once
(spy-verified) and never calls the single-state engine
(`features_for_state`/`features_for_batch` absent from the builder).
No per-state fan-out. Residual duplication: `context_batch` and
`rates_batch` internally recompute the single `pace_median_5` basis and
(for rates) the gap sweep — a known bounded inefficiency (~1–2 min of
the ~6 min build). F15 does not thread caches through frozen calculators
(semantic risk); documented as a later optimization.

## 16. Canonical sort

`(season, round_no, race_id, state_time_s, lap_number, driver_id)` —
deterministic, total, input-order independent (shuffle-subset test).

## 17. Artifact format / location

Parquet (single canonical table) at
`data/v2/processed/model_matrix/matrix_version=v1/model_matrix.parquet`,
plus `manifest.json` in the same directory. No CSV canonical. Frozen
Phase-1 D9 artifacts are untouched.

## 18. Artifact separation decision

One combined Parquet + manifest (not separate feature/label/table
files) to avoid a second GB-scale copy; the manifest's explicit
`predictive_columns` / `label_columns` / `label_companion_columns` /
`task_eligibility_columns` lists are the separation boundary, enforced
by the loader API (§35).

## 19. Manifest

Records: matrix_version, matrix_entity, feature_set_version,
feature_registry_fingerprint, predictive_feature_count,
label_set_version, label_registry_fingerprint, label_count, row_count,
race_count, season_range, column_count, the four column-class lists,
task_contract, canonical_sort, label_join (many_to_one + counts),
source rows, null_counts (all columns), schema_hash, content_hash,
source_fingerprints, artifact paths/bytes, build_seconds. No
machine-specific absolute paths (asserted).

## 20. Versions

`MATRIX_VERSION = "v1"` (assembly/schema contract). It never changes
`FEATURE_SET_VERSION` (v8) or `LABEL_SET_VERSION` (v1).

## 21. Hashes / fingerprints

- Feature registry fingerprint: `FeatureRegistry.fingerprint()`
  (sha256 over canonical JSON).
- Label registry fingerprint: sha256 over `LabelRegistry.to_dict()`.
- `schema_hash`: sha256 over the column-class lists + dtypes.
- `content_hash`: sha256 over `pd.util.hash_pandas_object` of the
  canonically sorted frame (stable for fixed dtypes; never raw Parquet
  bytes, whose writer metadata is unstable).
- `source_fingerprints`: per-source sha256 over sorted
  (relative-path, file-bytes) pairs for D9 states, labels, and the five
  history tables.

Measured: schema_hash `b1ccbc62…`, content_hash `d2ee966c…`.

## 22. Reproducible command

```bash
python -m v2.features.build_matrix [--root R] [--output D] [--force]
```

Builds, validates, writes the artifact + manifest, prints a summary. No
interactive steps, no network. Default behavior: if a valid matching
manifest exists, report "up to date" and skip; `--force` rebuilds.

## 23. Idempotence

Two full builds from the same frozen sources produce identical
row/column counts, schema_hash and content_hash (rebuild test). Output
file byte metadata may differ; the semantic hash does not.

## 24. Atomic writes

Write `*.tmp`, reload-validate, then `os.replace` the Parquet and the
manifest; on any failure the temp files are removed and no partial
artifact is promoted (failure test).

## 25. Schema validation

`validate_matrix` fails on: wrong predictive count (≠84), wrong label
count (≠7), duplicate columns, feature/label/task overlap, unclassified
columns, wrong row count, duplicate identity/state_id, all-null
columns, non-boolean masks. All checked before promotion.

## 26. Row identity

D9 PK unique (0 duplicates); matrix PK unique; `state_id` unique. The
equal-time Stroll pair is preserved as distinct rows (lap 4/5).

## 27. Label validation

189,420 states retained; label join matched 189,420 / missing 0;
binary domains; `final_position` factual; ordinal eligibility
178,963; gain/loss formula conformance; labels constant within
race-driver. No target imputation.

## 28. Feature validation

Exactly 84 predictive columns; no all-null feature; no constant
feature; finite floats; boolean domains; integer domains; fraction
bounds; ages ≥0 (F14 invariants re-applied to the materialized matrix).

## 29. Engine parity

Seven representative states (2018 sparse, 2025, Monaco wet, Belgium
2021 partial, Japan 2022 red, 2023 normal, Baku 2019 pit-lane starter)
recomputed through the F14-approved single-state engine: all 84
columns equal (null-aware). Family-by-family batch parity was proven in
F4–F14; F15 proves the written artifact.

## 30. Shuffle determinism

A two-race subset assembled from shuffled input has an identical
content_hash (input row order is irrelevant; canonical sort is total).

## 31. Full matrix audit

- rows 189,420; columns 106; metadata 9; predictive 84; label 8 (7+1
  companion); task masks 5.
- races 173; seasons 2018–2025; drivers 43.
- in-memory ~229 MB; Parquet 24,334,356 bytes (~24.3 MB); reload
  seconds-scale.
- all-null predictive columns: none; constant predictive columns: none;
  non-finite floats: none; duplicate identities: none.
- content_hash `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`.

## 32. Season coverage (measured)

| season | races | rows | ordinal-eligible | winner-True |
|---|---|---|---|---|
| 2018 | 21 | 22,337 | 20,363 | 1,266 |
| 2019 | 21 | 23,676 | 22,112 | 1,263 |
| 2020 | 17 | 18,352 | 17,313 | 1,034 |
| 2021 | 22 | 23,758 | 22,584 | 1,299 |
| 2022 | 22 | 23,577 | 22,087 | 1,295 |
| 2023 | 22 | 24,422 | 23,361 | 1,325 |
| 2024 | 24 | 26,606 | 25,766 | 1,444 |
| 2025 | 24 | 26,692 | 25,377 | 1,444 |

No season is altered to equalize coverage; 2020 (short season) and
2018 (sparse era) differences are genuine.

## 33. Race-stage coverage (diagnostic)

Progress thirds (`race_progress_frac`): early 64,016 / mid 63,437 /
late 61,967. Windowed families are naturally sparser early (min-history)
— structural, not a defect. No stage feature is created.

## 34. Class prevalence (no rebalancing)

State-level: winner 5.47%, podium 16.42%, scored-points 54.63%, gain
39.84%, loss 28.41%. Measured only; no weights/oversampling.

## 35. Leakage scan

Predictive set contains no label/target-mask/outcome-alias/future-only
field; the only outcome access is F10's approved H<R historical path
(F14 static audit). No telemetry column/family/artifact.

## 36. Physical feature/label separation + loader contract

The loader selects X explicitly from the manifest — never
`df.drop(labels)`:

```python
load_features(paths)            # predictive (+ optional metadata)
load_labels(paths)              # labels + companion + masks
load_task(task, paths)          # -> (X, y, eligibility_mask)
```

`load_task` returns raw approved semantics: no split, no imputation, no
encoding, no scaling, no rebalancing, no model import. The mask is the
frozen eligibility contract and must be honoured by Phase 3.

## 37. Task-loader safety

`load_task("final_position")` returns the ordinal mask
(`eligible_ordinal_final_position`, 178,963), never
`final_position.notna()` (which would select all 189,420). Gain/loss
tasks use `eligible_gain_loss`; y is null exactly where the mask is
False. Binary tasks use their exact F13 contracts.

## 38. Performance (measured)

Source load + full build ≈349 s (~5.8 min) on this machine; the heavy
families are rates (~106 s), context (~92 s), gap (~79 s), priors
(~63 s) extrapolated from the 2023 subset (44.8 s). Peak memory
dominated by the ~229 MB frame. This is ~270× faster than naive
per-state fan-out (F14: ≈26 h) and materially better than the required
bar. Dominant stages: gap/context/rates sweeps. Remaining opportunity:
thread precomputed pace/gap caches into context/rates (semantics-safe
later; not done in F15).

## 39. Limitations

- `context`/`rates` internally recompute the `pace_median_5` basis and
  the gap sweep (bounded, documented).
- `content_hash` is stable for a fixed pandas/pyarrow version; cross-
  version drift is possible (documented, not a semantic change).
- W/D back-rank `final_position` values are factual source orderings;
  ordinal use must go through the eligibility mask.
- The combined Parquet means labels physically co-reside with features;
  separation is enforced by the manifest-driven loader, not by file
  boundaries.

## 40. F16 handoff

F16 consumes: the canonical matrix + manifest at
`data/v2/processed/model_matrix/matrix_version=v1/`, the `TASKS` contract
and `load_task` loader, the family partition (for ablation groupings),
and the eligibility masks. No model training/splitting is performed in
F15. F16 (ablation-family configuration + Model-Lab fixtures) may rely
on `manifest["predictive_columns"]` and the family registry but must
not alter the matrix.
