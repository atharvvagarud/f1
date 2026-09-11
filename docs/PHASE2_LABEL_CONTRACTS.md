# Phase-2 Label Contracts (F13)

> F13 objective: define, validate and expose the canonical
> supervised-learning TARGET layer for Phase 3. Answers "what exactly
> are we trying to predict, at what grain, with what semantics?"
> Depends on frozen Phase-1 labels (D9 `race_driver_labels`, D5
> results) by reference; reinterprets nothing. Creates NO predictive
> features: `FEATURE_SET_VERSION` stays `v8`, 84 predictive
> definitions untouched. No training, no splits, no F15 matrix.

## 2. Feature / label separation

Two namespaces, two grains, two availability regimes:

```text
driver_lap_state_d9 (189,420 rows, LAP_END)   race_driver_labels (3,458 rows)
   predictive STATE (past-only)                  POST_RACE outcomes (labels)
            \                                            /
             \                                          /  F15 left join
              v                                        v
              feature states  --(race_id, driver_id)--> + labels
```

Labels may consume post-race results; features may not. State tables
carry zero LABEL_ONLY columns (asserted in `v2/d9schema.py` and by
written-Parquet tests). The F13 registry (`v2/labels`) is a different
class, module and version line from `v2/features`.

## 3. Frozen Phase-1 label source

- `race_driver_labels` (D9 label layer, season-partitioned Parquet,
  8 files), built by `v2/d9.py::labels_from_results` from D5
  `results` (FastF1 official outcomes via `v2/tiera.py::
  normalize_results`).
- Frozen derivations (referenced, never reimplemented):
  `classified_flag` = classified_position not null;
  `winner_flag` = position_final == 1 (null iff null);
  `podium_flag` = position_final in 1..3 (null iff null);
  `points_finish_flag` = points > 0 (never null).
- F13 conformance proof: recomputing these formulas over all 3,458
  rows reproduces every frozen flag exactly
  (`test_frozen_derivation_conformance`).

## 4. Source audit (MEASURED over 3,458 rows, 173 races, 43 drivers)

| Column | dtype | nulls | Notes |
|---|---|---|---|
| race_id / season / driver_id / abbreviation | str/Int64/str/str | 0 | stable canonical identity |
| position_final | Int64 | **3** | 1..20; null = source orders nothing (3 W rows) |
| classified_position | Int64 | **451** | 1..20; null = R 420 / W 18 / D 13 |
| position_text | str | 0 | verbatim token (numeric + R/W/D) |
| status_text | str | 0 | verbatim (Finished, +N Laps, Retired, Collision, …) |
| points | float64 | 0 | 0.0..26.0, incl. half-points (0.5/7.5/12.5) |
| laps_completed | Int64 | 0 | 0..87; 94 zeros |
| classified_flag | boolean | 0 | 3,007 True / 451 False |
| winner_flag | boolean | 3 | **173 True, exactly 1 per race (min=max=1)** |
| podium_flag | boolean | 3 | **519 True, exactly 3 per race (min=max=3)** |
| points_finish_flag | boolean | 0 | **1,730 True == (points > 0) exactly** |

Uniqueness: 0 duplicate (race_id, driver_id) keys. Per-season rows:
420/420/340/440/440/440/479/479 (2018–2025). Status top tokens:
Finished 1,995; +1 Lap 536; Lapped 297; Retired 161; +2 Laps 101;
Collision 77; Accident 35; Engine 31; Collision damage 29; …;
Disqualified 16; Did not start / Withdrew / Illness among W rows.

## 5. Label grain

`(race_id, driver_id)` — one final outcome record per race-driver
entry (`LABEL_GRAIN`, `label_primary_key()` agrees). Labels never
vary by lap. Later broadcast: the same race-driver target attaches
to every eligible D9 state of that entry (F15; many-to-one).

## 6. Retained targets (LABEL_SET_VERSION v1, 7 definitions)

| Target | Task | Status | Source |
|---|---|---|---|
| final_position | ORDINAL int | CANONICAL | position_final verbatim |
| is_winner | BINARY bool | CANONICAL | winner_flag verbatim |
| is_podium | BINARY bool | CANONICAL | podium_flag verbatim |
| scored_points | BINARY bool | CANONICAL | points_finish_flag verbatim |
| position_change_from_state | CONTINUOUS int | SPECIFIED | formula: current − final (F15) |
| gains_position_by_finish | BINARY bool | SPECIFIED | formula: change > 0 (F15) |
| loses_position_by_finish | BINARY bool | SPECIFIED | formula: change < 0 (F15) |

CANONICAL = frozen column renamed by the builder (no recomputation).
SPECIFIED = formula frozen here (§12), materialized only in F15.
Companion (not a target): `classified_flag` rides along for
conditioning ordinal/ranking use.

## 7. Rejected / deferred targets

- **DNF / reliability** (`is_dnf`, retired, completion, …): DEFERRED
  (§12). `dnf_flag` in D5 results is provisional classification
  evidence, explicitly not a target; no binary event definition
  exists.
- **expected_finish_label**: REJECTED as a label (§32). Expectation
  is model output; the factual target is final_position.
- **Ranking pairs / race groups**: DEFERRED to Phase-3 M10 (no
  materialization in F13; §33 handoff only).
- **Telemetry-derived targets**: none (ADR-0001 holds).
- **Win probability / success / performance labels**: rejected as
  names (§34); labels are observed outcomes.

## 8. Finishing-position semantics

`position_final` = FastF1 official Position, verbatim. All 420 R
rows carry numeric values (retirements ordered by distance); all 13
D rows carry numeric values (disqualified, e.g. 18/19/20); 15 of 18
W rows carry source back-rank numerics (18/19/20); 3 W rows
(mazepin 2021-r22 illness, mick_schumacher 2022-r02 + stroll
2023-r15 withdrew, 0 laps) are null. F13 does NOT re-derive or
second-guess: W/D numerics are source orderings, not earned slots —
documented, with `classified_flag=false` marking the distinction.
No `-1`/`999` sentinels; unsupported ordinal stays null.

## 9. Winner semantics

`is_winner` ⟺ frozen `winner_flag` ⟺ position_final == 1. Never
inferred from last D9 position, laps led, points or grid. Cardinality
measured: exactly 1 per race across all 173 races (no partial-race
exception: Belgium 2021 → verstappen). Builder raises on any
violation (tested with a synthetic double-winner).

## 10. Podium semantics

`is_podium` ⟺ frozen `podium_flag` ⟺ position_final in (1,2,3).
Measured: exactly 3 per race, all 173. Non-classified entries are
False (their numerics never fall in 1..3); the 3 fully-null W rows
stay null (never fabricated False).

## 11. Points semantics

`scored_points` ⟺ frozen `points_finish_flag` ⟺ points > 0 —
"officially scored >0", never "nominal points-paying position".
Verified: 1,730/1,730 exact incl. half-points (Belgium 2021: 12.5/
9/7.5/6/5/4/3/2/1/0.5; sainz 0.5 → True). Points distribution
measured (0.0: 1,728 … 25.0: 135, 26.0: 37 incl. fastest-lap point).
No manual points-rule reconstruction.

## 12. DNF decision: REMAINS DEFERRED

`status_text` mixes Finished, +N Laps, Lapped, Retired, Collision
(77), Accident (35), Engine (31), Collision damage (29), Brakes,
Power Unit, Gearbox, Suspension, Electrical, Exhaust, Driveshaft,
Puncture, Wheel, Steering, Disqualified (16), Did not start,
Withdrew, Illness — 40+ distinct tokens across mechanical /
accident / classification / withdrawal / disqualification causes.
No crude `status != finished` rule is honest; Phase-3 M12 must start
from a binary baseline only if it first fixes an event definition.
F13 creates no DNF column (pinned by test).

## 13. Position-gain/loss decision: SPECIFICATION RETAINED

`position_change_from_state = current_position − final_position`
(positive = finishes ahead of current slot). Factual on both inputs;
null-propagating (null iff either null); ties → 0 with both
booleans False. Captures pits/retirements/penalties/passes/
incidents indiscriminately — never called "overtake". Retained as a
frozen formula (SPECIFIED status) answering Phase-3 T5; lap-level
materialization belongs to F15, so the race-driver builder stays
lap-unaware. Measured eligibility: 189,126/189,420 states (294
current-position nulls; 0 final-null states in D9 scope);
gains 75,355 / losses 53,729 / same 60,042.

## 14. Eligibility / missingness

Race-driver level: only the 3 fully-null W rows lack ordinal/winner/
podium (scored_points always defined). State level (broadcast):
all 189,420 states carry valid constant labels; gain/loss null for
294 position-null states. F13 drops no feature rows; Phase 3 chooses
task populations. No imputation anywhere.

## 15. Label contracts

`v2/labels/contracts.py`: `LabelDef` (name, version ≥1, dtype from
{bool,int64,float64}, description, exact `entity.field` sources,
grain, derivation, null policy, task, status) + `LabelRegistry`
(sorted, duplicate-rejecting) + `LABEL_SET_VERSION="v1"` +
`LABEL_GRAIN` + `CANONICAL_LABEL_NAMES` (guard set only).

## 16. Label registry / version

`build_label_registry()` → 7 definitions, all v1. Independent
`LABEL_SET_VERSION="v1"` (contract identity + builder manifest
stamp); `FEATURE_SET_VERSION` unaffected (still `v8`). No shared
code with the feature registry (separate class by §15 requirement).

## 17. Builder architecture

`v2/labels/builder.py`: `build_label_frame` (validates PK
uniqueness, required columns, exactly-one-winner-per-race;
renames frozen columns; sorts deterministically; returns frame +
manifest) + pure state formulas + `join_labels_for_f15`. Reads only
the frozen label artifact; never touches features; never mutates
Phase 1. Builder output manifest (measured): 3,458 rows / 173 races
/ 43 drivers / 173 winners / 519 podiums / 1,730 points / 3 final
nulls; rebuild byte-identical (tested).

## 18. Source firewall

```text
RESULTS / LABEL SOURCE  ->  LABEL BUILDER  ->  canonical frame
```

Feature calculators never import label modules and never receive
label values: engine paths take `(request, registry, states,
names, history)` — no labels parameter exists (pinned by
source-scan test over all calculator modules and by the §23
real-engine mutation test). The single shared edge is the
outcome-NAME guard set (metadata only), imported inside
`label_outcome_fields()` — values cannot flow through it.

## 19. Feature registry freeze (verified before AND after)

`FEATURE_SET_VERSION == v8`; `len(build_f11_registry()) == 84`;
`v2/features` diff empty in F13 (one additive guard import reading
a name set; zero definition changes — F2 suite still 30/30 green).
No blocker encountered.

## 20. Future F15 join contract (defined, NOT executed)

`join_labels_for_f15(states, labels)`: left join on
`(race_id, driver_id)` with `validate="many_to_one"`; feature
identity and row count preserved (asserted); labels constant within
race-driver (broadcast, not recomputed); missing labels explicit via
match report. Invariants: label key unique; no fuzzy/name/number
joins (slugs only — presentation mutation provably ignored);
stateless label keys (6) ride along honestly for F15 population
decisions. No F15 Parquet written in F13.

## 21. Identity

Canonical keys only: `race_id` + permanent Ergast-slug
`driver_id`. Abbreviation/number/display mutations provably inert
(tested: full-abbreviation rewrite → identical canonical frame;
join uses keys only).

## 22. Leakage guards

`label_outcome_fields()` now unites: D9 LABEL_FIELDS +
`RESULTS.label_columns()` + dnf belt-and-braces + the 7 canonical
target names (exact-match only — no substring bans, avoiding the
`pressure` collision class). Registration of any predictive feature
named like a target raises `InvalidFeatureError` (tested per name);
zero overlap between the 84 features and 7 labels (measured).

## 23. Mutation tests

- **Features ignore labels (§23, real engine):** all-84 result at
  2023-r01-R state 500 computed; in-memory label copy mutated
  radically (all winners False, all positions 20, all points 0);
  recompute identical (`results_equal`). Engine has no labels input
  by construction.
- **Labels respond to results (§24):** source flip
  (verstappen 2023-r01 P1→P5) flips `is_winner` True→False and
  `final_position` →5; frozen-formula conformance over all 3,458
  rows green.
- **Future-race isolation (§25):** rewriting all 2025-r01 labels
  leaves every 2024-r01 label byte-identical (per-row purity, no
  cross-race aggregation exists).

## 24. Invariants

Binary: True/False/null only, per null policies. Ordinal: positive
int or null; no sentinels, no infinities. Winner 173 (1×173 races);
podium 519 (3×173); points 1,730 == points>0. Deterministic rebuild
identical (frame + manifest).

## 25. Abnormal races

Belgium 2021 (2021-r12-R, PARTIAL): 20 factual rows; winner/
podium/points all valid; half-points flow through `points > 0`
honestly (10 scorers incl. sainz 0.5). Short distance invalidates
nothing — official results are the source. Japan 2022 (2022-r18-R,
PARTIAL/time-affected): 20 rows, 1 winner. No race-ID special cases
anywhere (cardinality rule is uniform; both races satisfy it).

## 26. Stateless participants

6 label keys have zero D9 states and keep their labels:
mazepin 2021-r22, mick_schumacher 2022-r02, tsunoda 2022-r02,
stroll 2023-r15, sainz 2023-r17 (W, 47 laps, pos 20),
albon 2024-r21. "Participant/result exists" ≠ "predictive state
exists". F15 decides populations; F13 deletes nothing. Conversely 0
state keys lack labels (3,452/3,452 covered).

## 27. Full label audit

§4 table + distributions: position_final 1..20 (+3 null);
classified 1..20 (+451 null: R 420/W 18/D 13); points 0..26;
laps_completed 0..87; winner 173; podium 519; points 1,730;
classified 3,007. Deterministic rebuild verified. No duplicate keys,
no unsupported statuses (verbatim tokens preserved, never coerced).

## 28. Conceptual lap coverage (no matrix written)

Left-join key audit over all 189,420 D9 states: 189,420 matched, 0
missing, for every constant label. Gain/loss eligible 189,126
(99.84%). Per-season matched states: 22,337 / 23,676 / 18,352 /
23,758 / 23,577 / 24,422 / 26,606 / 26,692 with winner-True states
1,266 / 1,263 / 1,034 / 1,299 / 1,295 / 1,325 / 1,444 / 1,444.

## 29. Class prevalence (measured, never rebalanced)

Race-driver: win 5.01% / podium 15.02% / points 50.03%. Broadcast
state-level: win 5.5% (10,370) / podium 16.4% (31,106) / points
54.6% (103,482). No rebalancing, oversampling, or class weights in
F13 (Phase-3 business).

## 30. Ranking-task handoff (Phase-3 M10)

`final_position` supports race-grouped ranking: group key
(race_id [+ lap for state-level]) over broadcast rows; unclassified
entries carry source orderings with `classified_flag=false` for
explicit eligibility decisions; ties beyond P20 impossible (max 20
classified). No pairs/groups materialized here.

## 31. Limitations

- W/D back-rank numerics are source orderings, not earned results;
  ordinal consumers must decide the `classified_flag` policy (F13
  documents, does not decide).
- The 3 fully-null W rows can never supply ordinal/winner/pod targets.
- 294 states lack `current_position` (gain/loss null there).
- `status_text` richness is preserved but unmodeled (DNF deferred).
- Builder validates, not repairs: corrupt sources raise.

## 32. F14 handoff

F14 consumes: v8/84 registry (frozen), v1/7 label registry,
validated builder + join contract, mutation-suite evidence. No
telemetry, no DNF, no matrix, no F14 tests written. F13 leaves zero
label-shaped state inside feature code.
