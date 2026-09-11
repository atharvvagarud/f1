# Phase-2 Pre-Race Priors (F10)

> F10 race-boundary context in `v2/features/priors.py` (13 features:
> grid 1 + driver 5 + constructor 4 + circuit 3; registry 69→81 with
> grid superseded to v2; schema v6→v7), 26 tests green, full 189,420-row
> constancy audit clean. Depends on F1–F9 without reinterpreting them.
> No reliability, no qualifying expansion, no standings, no labels.

## 2. Temporal boundary

H < R on frozen (season, round_no) via centralized `history_before`
— the structural firewall (current/future inexpressible as priors).
Priors are constant across all laps of R per entity by construction.

## 3. Source tables

History: Tier-B `hist_results` (25,784 rows, 1950–2025) + `hist_races`
(round/circuit mapping) — deep uniform history (2018 targets average
60+ prior starts; only 0.6% zero-history). Target grid: D5 `results.
grid_position` (F2 contract; 3,455/3,458). Circuit facts: D5
`results`/`pit_stops`/`races` (2018+ same-circuit editions).

## 4. Historical support audit

43 drivers / 16 constructor slugs 2018+; starts/driver med 61
(1–173); circuits 31 with 1–10 editions (nurburgring/mugello once);
Tier-B numeric-text 62.9% (classified), W 357 (DNS), R 9,043, D 159
(1 scoring). Redundancy (career aggregates): points↔podium 0.976 →
podium/win rates DROPPED; mean_finish↔points −0.911 kept as distinct
concepts (typical result vs sparse scoring rate).

## 5. Current-race result firewall

`history_before` is the only history path (single + batch); no
expanding/groupby-with-shift anywhere. Current-race outcome mutation
(finish/points/winner/podium/status) and future-race mutation:
identical output (tested). Eligible-prior mutation: relevant prior
moves (dependence proven, not just isolation).

## 6. Grid semantics

D5 `GridPosition` = actual starting slot incl. penalties/sprint
effect. 0 = pit-lane-start code (43 rows, raced + classified):
preserved factually, never re-slotted, never nulled. Null = the 3
known W/DNS rows (pinned by real-data test). No lap-1/qualifying/
teammate inference. Target-grid mutation moves only the grid feature.

## 7–9. Driver philosophy, windows, min-history

Descriptive past-performance summaries (never skill/talent/rating):
starts (always), mean_finish (classified, min 3), points_per_start
(all starts, min 3), mean_grid (earned slots > 0 only, min 3),
recent trailing-5 mean_finish (≥3 classified within). Long + recent
only (no 10/20/all proliferation). Rookies: 0 + nulls, never field
average. No DNF/finish/classified/completion rates (deferred).

## 10. No current-race performance

All laps identical (constancy-tested); target-result mutations move
nothing (tested across finish/points/winner/podium/status).

## 11–13. Constructor philosophy, denominators, identity

Per-entry semantics frozen: points_per_entry (points/entries),
mean_finish per entry, team-races (distinct H with ≥1 starter),
recent trailing-5-races points/entry (≥3 entries). Canonical
season-scoped slugs preserved: force_india/racing_point/renames never
merged (tested); no strength scores.

## 14–18. Circuit philosophy, identity, selection, size, features

Same-`circuit_id` Tier-A editions H < R only (future editions
excluded, tested). Sparse support exposed: count always, summaries
min 2 editions. 3 features: edition count, per-edition pit-stops/
entry mean, per-edition position-change mean (earned+classified
entries only; called position change, never overtaking/strategy).
Caution-fraction circuits deferred (needs lap-level scans — documented).

## 19. Current vs cross-season

Trailing-5 recent + all-prior long (uniform across season
boundaries) instead of current-season-to-date (variable-n).
Constructors get the same pair (competitiveness drift visible in the
recent leg, e.g. Ferrari 12.9 vs long 4.06 for Leclerc 2019).

## 20. Rookie/new-entity behavior

Counts 0 + null summaries (Lawson-2023 spot: 2 starts, null
performance, live constructor/circuit context). Later careers never
leak backwards (5-win future adversary tested).

## 21. Same-race constancy

nunique == 1 per (race, driver) for all 13 features over all 189,420
states (batch-tested). Any lap variation would be a bug.

## 22–23. Chronology / odd rounds

Frozen (season, round_no) keys; never names/dates/filesystem order;
2018→2019 boundary strictly tested. No postponed/cancelled Tier-A
rounds present; canonical race identity used verbatim.

## 24–25. Label firewall / grid distinction

Column-level semantics: grid (PRE_RACE) allowed from the results
table while outcome columns stay unreachable (grid-mutation isolation
tested both directions). No DNF column exists or is added.

## 26–29. Inventory / candidates / reliability / qualifying

13 features (1/5/4/3 — within 8–15). Dropped: win/podium rates
(redundant), caution circuits (heavy), standings, ratings,
difficulty scores. Reliability/DNF explicitly absent (name-search
pinned). Qualifying beyond grid: nothing (no Q1–Q3 ingestion).

## 30–31. Registry / version

GRID/DRIVER_PRIOR/CONSTRUCTOR_PRIOR/CIRCUIT families (existing
taxonomy, no duplicates); temporal PRE_RACE (grid) / PAST_RACES
(priors); sync NONE (correctly no rival claim); exact lineage;
CANDIDATE; grid superseded v1→v2 via the new lifecycle op. Schema
v6→v7 exactly once (+12 net columns). PAST_RACES source exception to
the outcome-lineage guard documented (H<R cutoff is the protection;
outcome NAMES still banned).

## 32–33. Architecture / sweep

One module (`priors.py`): pure driver/constructor/circuit helpers +
grid resolver + centralized cutoff. Batch = per-(race,driver)
precompute once + broadcast (constancy by construction); single =
same helpers live. Chronological accumulator sweep unnecessary: the
history table is complete and static, so per-target cutoff filtering
is exact (deviation from the suggested sweep documented with
rationale).

## 34. Single/batch + mutation/leakage evidence

Parity green (constancy batch + per-request singles). Current/future
result/label/grid mutations isolated per §5; eligible-prior mutation
moves; rookie/future-edition adversaries green; presentation columns
ignored (slug keys only); shuffled inputs stable.

## 35. Full-data coverage (189,420 rows, MEASURED)

Nulls: grid 0.0% (3 W-nulls have no states — pinned separately),
driver summaries 1.8–3.7%, constructor 0.49%, circuit summaries
34.55% (debut/thin venues, honest). Same-race constancy holds
globally. Deterministic rebuild identical.

## 36. Edge cases

2018-r01 Hamilton (deep priors, zero circuit history); Miami debut
(0 editions); Leclerc-2019 (21 starts, Ferrari 971-race context);
Lawson substitute (cold-start done right); VER-2024 (185 starts,
recent 1.0). Contributing races explainable per target; no
race-specific logic.

## 37. Performance (MEASURED)

Full batch 61.6 s (3,458 combos + broadcast); single-state 21 ms.
Cheaper than F6–F8 by design (race boundary, no per-lap recompute).

## 38. Limitations

Tier-B W/D/R vocabulary handled by rule (numeric-text =
classified); pre-2018 shared-drive scoring rows predate Tier-A scope;
circuit features Tier-A-only (new venues null); grid-0/mean-grid
asymmetry documented (§6); no within-season form decay beyond the
trailing-5 leg.

## 39. F11 handoff

F11 consumes: prior columns as background levels (interactions only
there, never here), the cutoff/constancy patterns, and the v7
schema. Matrix materialization, ablation config, and docs exit are
F11+ — untouched here.
