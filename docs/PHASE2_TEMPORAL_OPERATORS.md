# Phase-2 Temporal Operators (F3)

> F3 executable F1 semantics: deterministic, side-effect-free primitives
> in `v2/features/temporal.py` (+38 tests in
> `tests/test_v2_features_f3.py`). Depends on F1
> (`docs/PHASE2_TEMPORAL_SEMANTICS.md`) and F2
> (`docs/PHASE2_FEATURE_REGISTRY.md`); interpretation unchanged. No
> feature calculation, no families, no label joins. Pandas-based like
> `v2/d9.py`; no new dependencies.

## 3. Module/API architecture

Single module `v2/features/temporal.py` (one module is enough; no
per-primitive sprawl). Pure functions plus two frozen dataclasses and
one index class; caller frames never mutated (copies on return);
required columns validated explicitly (`TemporalError`, never silent
inference); exact-target misses raise `TargetNotFoundError`.

## 4. Deterministic ordering

All selection sorts internally by `(state_time_s, lap_number,
driver_id)` (F1 §7); input row order never matters (shuffle-tested).
The measured same-driver tie (2021-r08 stroll laps 4/5, T=2349.136)
orders lap 4 before lap 5 and is pinned by test. Cross-driver ties
(max observed size 5) resolve by driver_id.

## 5. driver_prefix

`driver_prefix(states, race_id, driver_id, T)` → rows with
`state_time_s <= T`, inclusive, temporally ordered; empty when nothing
observable; source unmodified; all columns preserved. Future-mutation
tested (post-T rows never affect output).

## 6. latest_at_or_before

`latest_at_or_before(frame, time_col, T, tie_cols=("lap_number",))`
→ last row with `time <= T`, or None. No fall-forward (a future row
0.001 s after T is rejected — tested); deterministic ties (+driver_id
where present). Small on purpose: not a query framework, no nearest
mode.

## 7. synchronized_driver_state

Returns frozen `SyncState(observable, race_id, driver_id,
observed_lap, observed_time_s, observation_age_s, values)`. Latest
`<= T` or `observable=False` with nulls. Age always `>= 0` when
observable (pinned); huge ages stay observable provenance (100 s test
plus real Monaco staleness spot). No same-lap preference, no
retirement inference, no final-result use.

## 8. synchronized_field_snapshot

`synchronized_field_snapshot(states, race_id, driver_id, lap_number,
T, roster)` → `FieldSnapshot` with the EXACT target row plus one
`SyncState` per roster member (unobservable members kept, never
dropped — covers the six known zero-state entrants). Entries ordered
by `driver_id`, never final position. Target identity must match a D9
row exactly (`resolve_target`); close timestamps raise.

## 9. Participant roster

`extract_roster(results_like)` → `{race_id: [sorted driver_ids]}` from
an explicit identity allow-list (`race_id`, `driver_id`). Outcome
columns cannot enter (mutating points/winner/positions leaves the
roster identical — tested). Lives in `temporal.py`: it is small,
temporal (identity-at-time), and needs no module of its own. Not a
label join (F13): outcomes are structurally unreachable.

## 10. within_stint_prefix

Current-stint rows of the driver's prefix sharing the target row's
`stint_number`. Start-side facts only: `end_lap`, future pit-out, and
eventual length are never read (a fabricated `end_lap` column is
provably ignored — tested). Null/absent stint on the target row →
empty. Shuffle-stable; later pit events have no effect.

## 11. past_races_before

`past_races_before(races, season, round_no)` → strictly earlier races
by canonical `(season, round_no)` ordering (never lexical race_id —
adversarial non-chronological ids tested), deterministic order,
current/future excluded, no outcome aggregation or selection. Future
result mutation cannot alter the list. Selects eligible races only;
priors are F10.

## 12. rolling_past_observations

`rolling_past_observations(prefix, T, mask, window)` → latest-`window`
masked rows, target included when eligible (LAP_END), re-asserted
`<= T`, nulls preserved, no centered windows. Eligibility policy and
min-n live with the caller (F5); this operator only selects. Window
< 1 raises.

## 13. Observation-age semantics

`observation_age_s(T, t) = T − t`, `>= 0` enforced (negative raises).
Named provenance only — the words gap/time_gap/race_gap/distance
appear nowhere in the module. Large ages imply nothing about
retirement (tested + documented).

## 14. Active/running limitation

No `is_running`/`is_retired`/active symbols exist in the module
(asserted by test). Vocabulary is `observable` / `has-prior-state`
(via null vs row). Stale stays stale.

## 15. Partial/red-flag behavior

No exclusions, no cadence or equal-lap assumptions. Real-data spots:
Belgium 2021 (60 rows — snapshot over all 20 drivers, all outputs
`<= T`), Japan 2022 red-flag sync, Monaco 2022 stale-but-observable.
All pass; artifacts skipped cleanly when canonical data is absent.

## 16. Mutation-test coverage

F1 §19 A–M implemented: same-lap future rival, later-lap future
rival, future timing/value mutation (falls back to older state —
correct, documented), future deletion, full reorder, future-duplicate
flooding, no-prior state, timestamp ties (cross- and same-driver),
missing states, PARTIAL, red flag, presentation-identifier mutation
(temporal selection identical; only the presentation payload differs —
asserted at the selection level). 38 tests, all green.

## 17. Identifier safety

Selection keys `(race_id, driver_id)` exclusively. Number/
abbreviation/team-display mutations provably invisible to selection;
roster uses the same keys. Ordering tie-break uses the stable
`driver_id`, never display strings.

## 18. Performance measurements (MEASURED, local D9, 189,420 rows)

`RaceIndex` build 1.59 s; single rival lookup 113.7 µs; frame-path
field snapshot 21.98 ms/target; index-path snapshot 2.07 ms/target
(~10×); whole-scope all-pairs sync (3.59M lookups) 314 s
single-threaded. Peak RSS ≈ 0.7 GB with the full D9 frame resident
(index overhead itself small). Honest reading: the frame path is the
correctness reference; batch-scale work (F4+ matrices) must use the
index path, with parity tests between them (see §19).

## 19. Parity handoff

One semantics implementation serves both future engines: frame
functions (reference) and `RaceIndex` (batch vehicle) share contracts,
and `test_index_matches_frame_semantics` pins identical selection on
every row of the synthetic race. `results_equal` (F2) compares future
outputs. No separate training/serving synchronization exists.

## 20. Limitations

Pandas-bound (consistent with D9); per-target frame snapshots are too
slow for whole-scope batch (use the index); `rolling_*` takes
caller-aligned masks (alignment contract documented); roster is
identity-only by design (entry timing nuances stay F10 business).

## 21. F4/F5/F6 handoff

F4 resolves passthroughs with `resolve_target`/`driver_prefix`;
F5 builds eligibility masks over `rolling_past_observations` +
`within_stint_prefix`; F6 consumes `sync_lookup`/snapshots with the
§9–§13 validity doctrine. Constants (min-n, thresholds) remain
unfrozen per plan.
