# Phase-2 Temporal Semantics + Synchronization Contract (F1)

> F1 deliverable: the normative temporal contract every Phase-2 feature
> must obey. Documentation-first per the revised plan (machine-readable
> registry is F2; primitive operators are F3; no feature families here).
> All measurements taken offline from frozen local D9 artifacts
> (189,420 rows) unless marked SCHEMA (machine-readable contract) or
> DOC (frozen documentation). No code added, no data changed, no
> network used. F0 evidence preserved verbatim where reused.

## 1. Target-state definition

A target predictive state is the tuple

```text
S_target = (race_id, driver_id, lap_number, state_time_s = T)
```

i.e. one row of frozen `driver_lap_state_d9`. The temporal knowledge
boundary for any computation at `S_target` is: **all information
observable at or before T**, subject to each source field's own
Phase-1 availability contract. No row, event, observation, or outcome
with event time after T may affect any feature at T — including rival
rows that share the target's lap number but carry a later
`state_time_s` (F0: same-lap spreads reach 121 s dry, 1,320 s red).

## 2. LAP_END boundary

`state_time_s` is the accepted LAP_END clock (F0: 0 nulls; 0 decreases
across 3,452 driver/race groups; 0 `lap_start_s > state_time_s`). Every
predictive-eligible field of the row is observable at or before T.

Frozen distinction: the target's `lap_number` is **descriptive race
progress for that driver, NOT a global race clock**. Drivers complete
the same lap number at different session times. Any computation that
treats equal lap numbers as simultaneous is temporally invalid. This
distinction is frozen and may not be reinterpreted per family.

## 3. Driver-prefix semantics

For target driver `d` at clock T:

```text
prefix(d, T) = all valid states for driver d in the same race
               with state_time_s <= T,
               ordered by (state_time_s, lap_number)   [§7]
```

This prefix is the ONLY driver-state history available at T. No row
after T may affect any feature at T. Rolling windows, trends, counts,
and stint histories are all computed over this prefix intersected with
an eligibility rule (eligibility masks are F5 business; the prefix rule
is F1).

## 4. Cross-driver synchronization

For target clock T and rival `r`:

```text
sync_state(r, T) = latest state for rival r in the same race
                   with state_time_s <= T,
                   tie-broken deterministically [§7].
                   If none exists: NO OBSERVABLE STATE (null).
```

Forbidden: fall-forward (nearest row regardless of side), nearest(T),
future-nearest, same-lap-number selection, end-of-race aggregates, and
full-season aggregates containing future races — unless the source is
explicitly PRE_RACE and therefore already known. A rival row with
`lap_number == target lap_number` may be used ONLY if it also satisfies
`state_time_s <= T` and is the latest such row. No-fall-forward is
frozen.

## 5. Field snapshot semantics

```text
field_snapshot(S) = { target's own exact state S }
                  + { for every roster participant p != target driver:
                        sync_state(p, T) OR explicit no-observable-state }
```

Rivals are never silently dropped because their observable lap differs
from the target lap (lapped cars, pit sequences, and retirees routinely
differ). Each snapshot entry preserves provenance: rival `driver_id`,
observed `lap_number`, observed `state_time_s`, age `T − observed time`,
and observable yes/no. The snapshot is synchronization infrastructure,
not a feature family; staleness rides along as provenance for
per-feature validity decisions (no global cutoff — see §13).

## 6. Participant-universe decision

Roster source: **D5 `results` identity columns (`race_id`,
`driver_id`) only** — the pre-race entry set, which is genuinely
pre-race factual. No outcome column (`position_final`,
`classified_position`, points, status, flags) may enter any
pre-computation or universe derivation. Rationale: Phase 1 stores no
dedicated entry-list table; the results driver set is the only frozen
roster, and entry identity (as distinct from results) is a pre-race
fact. This is identity-only reuse with documented justification, not a
label leak; F3/F10 must keep outcome columns structurally out of the
roster path and cover it with an identifier-mutation test.

Measured constraint (F1): the D9 state population (3,452 race-drivers)
is a strict subset of the results population (3,458). Six entrants have
zero state rows — the three known DNS/withdrawn cases (mazepin
2021-r22, mick_schumacher 2022-r02, stroll 2023-r15) plus tsunoda
2022-r02, sainz 2023-r17, albon 2024-r21 (zero completed/recorded laps).
They resolve to permanent no-observable-state, which is correct rather
than missing: no identity is invented, and no future row can ever
appear for them. At clock T the observable subset is drivers with ≥1
state `<= T`; the roster additionally distinguishes "entered but not
yet observed" (early T) from "never observable". No cleaner pre-race
source exists in the frozen platform — recorded here explicitly rather
than worked around.

## 7. Deterministic ordering

`state_time_s` (millisecond precision measured: 1,000 distinct
fractional values; float seconds) is the primary ordering key.
Measured ties: 67 cross-driver tie groups in 189,317 distinct
(race, time) keys (max tie size 5 — simultaneous lap completions are
real); 1 same-driver duplicate timestamp (2021-r08 stroll laps 4/5 at
T=2349.136 — an interrupted/retirement-boundary lap pair with NaN
lap_time on lap 5). Zero negative per-driver deltas otherwise.

Normative order (never dataframe row order):

```text
(state_time_s, lap_number, driver_id)
```

- Within a driver: `state_time_s`, then `lap_number` (covers the
  stroll-type duplicate: lap 4 precedes lap 5 at equal T).
- Across drivers: `state_time_s`, then `driver_id` (byte order; stable,
  content-independent).
- Zero/negative deltas across drivers are legitimate (simultaneous or
  out-of-order completions); only per-driver decreases would contradict
  the platform (0 measured). Missing timestamps: none measured in
  `state_time_s`; any future source with null event times follows the
  untimed-message precedent (never attached — see §8 weather/RC rules
  carried forward).

## 8. Availability-class rules (Phase-1 classes reconciled for LAP_END T)

Phase-1 classifications are unchanged. For a LAP_END target at T:

| Class | Predictive use |
|---|---|
| POST_RACE (`deleted`, `deleted_reason`, `is_accurate`) | NEVER predictive (provenance/quality only) |
| LABEL_ONLY (all label-layer outcomes) | NEVER predictive; never in state |
| SOURCE_METADATA (keys, clocks, `source_unit_status`, `shortened_race`, staleness anchors, message seqs, boundary lineage) | Non-predictive; promotion only via explicit reviewed contract |
| PRE_RACE (`season`, `round_no`, `total_laps_scheduled`, `grid_position` via D5 join) | Available from race start; factual constants only |
| LAP_START (`lap_number`, `lap_start_s`) | Knowable when the lap begins; eligible within prefix |
| IN_LAP (sectors ends, compound/tyre/stint/pit markers, `track_status`, wx values, stint facts) | Eligible once the in-race event completes, i.e. inside `<= T` states |
| LAP_END (position, lap_time_s, sectors, traps, D9 derivations) | Eligible at lap completion, i.e. the target row itself and prefix rows |

## 9. Gap semantic design (for F6; design only, no implementation)

The universal scalar `gap_to_leader_seconds: float` is rejected as the
complete representation. Minimum factual concept set for safe
race-relative separation:

```text
validity/status   — is a seconds separation semantically valid here?
lap_difference    — observed lap index difference (factual, §12)
seconds_separation— T_target_clock − T_rival_clock where valid, else null
rival_age         — T − rival.state_time_s (provenance, §11)
observed laps     — target lap + rival observed lap (provenance)
unknown state     — explicit null with reason (no rival state, missing
                    timing, invalid geometry e.g. red-flag suspension)
```

Principles (frozen): no session-minimum reference; no 300 s-style
clipping; no same-lap future rival observation; no fabricated seconds
for lapped/invalid cases; explicit validity/null semantics; factual
state only. Exact column names are F1/F2 business after the edge-case
evidence below — this plan freezes the concept set, not the schema.

## 10. Real-race edge-case evidence (all MEASURED D9 snapshots)

Notation: target (driver, lap, T) → rival sync (observed lap, age,
lapdiff). Verdict = whether seconds separation is factually valid.

A. Normal dry (2023-r01-R, alonso lap 28, T=6558.658, P6, all_clear):
VER lap 28 age 35.9 s lapdiff 0; PER lap 28 age 22.5 s; HAM lap 28 age
1.8 s. Verdict: valid — same observed lap, small ages, green track.
B. Leader change (2019-r04-R: P1 holders bottas→hamilton→leclerc…;
target hamilton lap 30, T=5259.101, P3): BOT lap 30 age 1.0 s;
VER lap 29 age 94.5 s lapdiff 1 (VER's lap 30 falls after T — a
same-lap join would have consumed future data). Verdict: valid with
lapdiff≠0 carried; reference (leader) must re-resolve every state.
C. Lapped traffic (2023-r01-R, sargeant lap 55, T=9295.129, P12):
VER lap 55 age 95.1 s lapdiff 0. Verdict: seconds computable as clock
difference but MUST pair with lap-deficit/position context — 95 s on
equal lap index spans more than a lap of race time and misleads
without it.
D. Safety Car (2025-r01-R, norris lap 35, T=7879.860, P1,
safety_car): VER lap 34 age 98.7 s lapdiff 1; PIA lap 34 age 115.3 s.
Verdict: computable; valid only with caution flag attached — bunching
compresses gaps and ages inflate across slow laps; consumers must
condition on `track_state`.
E. VSC (2021-r21-R, hamilton lap 30, T=9343.507, vsc): VER lap 30 age
1.7 s. Verdict: valid; tight sync under neutralized running.
F. Red flag (2022-r18-R, ocon lap 2, T=4068.088, red_flag, lap_time
NaN): VER lap 2 age 6.8 s; LEC lap 2 age 3.9 s. Verdict: seconds
separation INVALID as a race gap — clocks tick in suspension while
cars sit in pit lane; represent as lapdiff + validity=false.
G. Missing timing (2018-r04-R, alonso lap 2, T=836.495, lap_time NaN,
safety_car; race holds 156 null lap_times): HAM lap 2 age 35.6 s.
Verdict: sync resolves (clocks present); any pace-derived use of the
target lap is null — missingness propagates, never interpolated.
H. Belgium 2021 (hamilton lap 2, T=15768.059; max 3 laps/driver):
VER lap 2 age 3.3 s; NOR lap 1 age 174.5 s lapdiff 1. Verdict: sync
works; windows are ~empty (counts expose this); no exclusion.
I. Japan 2022 (alonso lap 14, T=13180.390, P7, all_clear): VER lap 14
age 29.0 s; OCO lap 14 age 7.1 s. Verdict: valid post-red-flag
racing state.
J. Monaco/time-limited (2022-r07-R, norris lap 30, T=11679.044,
lap_time NaN): VER lap 30 age 19.9 s; LEC lap 30 age 14.6 s.
Verdict: sync resolves; NaN lap_time → pace-null with reason; progress
uses scheduled distance (§15), never the truncated observed total.

## 11. Observation age vs race gap (frozen distinction)

`T − rival.state_time_s` is OBSERVATION AGE (sync provenance). It is
NOT automatically the physical race gap. Clock differences may be
interpreted as race separation only when the semantics are valid:
both cars racing under green, comparable observed laps, no suspension
(F-red), no caution-compressed bunching without flag conditioning
(D), no lapped-index ambiguity without lap-deficit context (C).
F3/F6 must carry both quantities under distinct names and test that no
code path substitutes one for the other. H-Belgium (174.5 s age across
SC-slow laps) and F-red (6.8 s age, zero racing) are the canonical
counterexamples.

## 12. Lap-difference semantics

`target_lap − rival_observed_lap` is a factual index difference. It
does NOT alone tell who is physically ahead: a lapped car can share
the leader's lap index early in a lap (C: lapdiff 0, 95 s apart, P12
vs P1); a car that just pitted shows lapdiff 1 while physically
adjacent; under SC the field compresses across lap indices (D);
position + track context disambiguate. Lap difference is therefore a
companion to seconds separation and position — never a standalone
"ahead/behind" signal. Leaders crossing the timing line create
transient lapdiff±1 pairs that the as-of rule resolves without special
cases.

## 13. Snapshot staleness (full-D9 MEASURED)

Per target over all rivals (189,299 targets with ≥1 rival):
median rival age p50 48.2 s / p90 80.9 s / p95 90.9 s / p99 128.7 s
(max 7,731 s). Stalest-rival age per target: p50 1,276 s / p90 4,501 s
/ p95 5,153 s / p99 6,998 s (max 10,927 s). Only 31.9% of targets have
ALL rivals within 120 s; 60.2% have ≥1 rival older than 600 s —
dominated by retired drivers' frozen last states (expected and
correct: their last observable state persists).

Decision: NO global staleness threshold in F1. Staleness is preserved
as provenance and consumed as per-feature validity information (pace
windows, gaps, traffic each define their own recency contract in
F5–F7). A global cutoff would either admit retirees as "current" or
discard valid slowed-but-running cars (SC/VSC/red-tail ages).

## 14. Active/running limitation (honest)

The frozen platform cannot establish exact "currently running"
semantics at T: retirement is a future-absence fact, and the only
authoritative running/classification evidence (final status,
`classified_position`) is POST_RACE/LABEL_ONLY and banned from state.
F1 defines four observable tiers and stops there: (a) roster
participant (D5 identity); (b) participant with synchronized state at
T; (c) participant not recently observed (stale sync, age carried —
MAY be retired, slow, or garage-held; unknown); (d) never observable
(the six zero-state entrants). No retirement inference from future
absence. Any per-feature "active" heuristic (e.g. age caps for traffic
counts) is downstream policy with an explicit contract and test — not
a platform fact. Documented limitation, not a gap to patch silently.

## 15. Progress semantics

D9 `race_leader_laps_at_state` (max completed lap with time ≤ T;
past-only by construction, group-max tie rule) and
`race_progress_frac` (leader laps ÷ PRE_RACE scheduled distance) are
the authoritative passthrough pair for Phase 2 (F4 registers them; F6+
consumes). Confirmed past-only; no eventual-distance content. Any
`remaining_*` concept = scheduled (PRE_RACE, sourced from D5
races/quality with its own contract) minus leader laps at T. Consuming
the eventually observed race total at an earlier state is banned —
this is the progress analogue of the sync rule and matters most in
PARTIAL/time-limited races.

## 16. Partial/red-flag semantics

Synchronization assumes nothing about race shape: cars need not share
lap counts (H: 3 laps max; I: 29 of 53); lap cadence may collapse
(SC/VSC/suspension); scheduled distance need not complete (progress
stays on scheduled denominator); a stale rival is not necessarily
retired (§14). 2021-r12 (60 rows, PARTIAL) and 2022-r18 (507 rows,
PARTIAL) synchronize normally with thin histories; red-flag states
resolve sync but suspend seconds-gap validity (F). No exclusion, no
special-case code paths — the same rule, with validity companions
doing the work.

## 17. F3 primitive contracts (specified, not implemented)

```text
driver_prefix(driver, T) -> ordered rows, guarantee: state_time_s <= T;
  missing: empty (driver never observed — the six zero-state cases);
  order: (state_time_s, lap_number).
latest_at_or_before(history, T) -> latest row <= T or null;
  guarantee: never future-nearest; ties by (lap_number, driver_id).
synchronized_driver_state(rival, T) -> sync_state per §4 or null with
  reason (no prior state); keys (race_id, driver_id) only.
synchronized_field_snapshot(target, T) -> §5 struct with per-rival
  (lap, time, age, observable) provenance; roster per §6.
within_stint_prefix(driver, T) -> prefix rows since current stint start
  (start side only; stint end NEVER exposed).
past_races_before(event) -> strictly prior races (season, round) <
  target event; no current/future; season-to-date = prior rounds only.
rolling_past_observations(driver, T, eligibility, k) -> trailing
  eligible prefix rows with count n; n < minimum -> null + count.
```

Each ships with: typed inputs/outputs, the temporal guarantee above,
null/missing behavior, deterministic ordering, and a future-mutation
test from §19. API names provisional; semantics frozen.

## 18. Parity contract

```text
batch_features(S) == prefix_features(S)
```

within deterministic numeric tolerance: batch generation over history
must equal single-state computation over `prefix(d,T)` + roster +
PRE_RACE constants using the SAME operators. Batch is a loop over (or
a vectorisation proven equal to) the single-state path — never a
separate windowing implementation. Implemented and tested later (F2
skeleton, F14 proof); F1 freezes the invariant only. No serving
infrastructure.

## 19. Mutation-test specification (F3+ template)

For state S at T: compute → mutate/delete ALL source information with
event time > T → recompute → output at/before T identical.
Synchronization-specific cases (none may change `sync_state(r,T)` or
any feature at T): add rival future state at same lap number (the
Bahrain-121 s hazard); add rival future state at later lap; mutate
rival future timing; delete rival future states; reorder source rows;
duplicate invalid future candidates. Plus: no prior rival state (null
stable); timestamp ties (deterministic); missing states (null, not
fabricated); PARTIAL race (thin but stable); red flag (validity
stable). Identifier mutation (§20) rides the same harness.

## 20. Identifier rules

Synchronization keys on `(race_id, driver_id)` only — permanent Ergast
slugs, stable across seasons (F0 reconfirmed). Never `driver_number`
(mutable: VER 33→1, substitutes), abbreviations, or display/team names
(renames are distinct season-scoped slugs). Tests mutate presentation
identifiers (number/abbreviation/team display) and assert identical
temporal selection. Roster joins use the same keys.

## 21. Performance recommendation

Scale: 189,420 targets × ~19 rivals across 173 races. Measured naive
per-target binary-search pass: 4.2 s whole-scope (~3.6M pair
resolutions) — synchronization is cheap. Recommended F3/F6 strategy:
per-race sort by (driver, state_time_s) once, `searchsorted`
per rival per target (or as-of merge join), snapshot materialisation
only where a family needs it. Obviously bad: per-target full-race
scans (quadratic), row-order dependence, Python-level per-row merges
without indices. No Redis/database/distributed systems; pandas+numpy
suffice (D7/D9 precedent: 4–8 s whole-scope builds).

## 22. Unresolved questions (for F2/F3/F6, non-blocking)

Exact gap-struct column names (concept set frozen in §9); window
minimum-n and prior-smoothing constants (F5/F10 contracts);
per-feature staleness/validity thresholds (F5–F7, informed by §13 —
no global value set here); `drivers_running` derivation constants
(F4); roster-path hardening tests (F3). None blocks F2.

## 23. F2/F3/F6 handoff

F2 takes: registry schema with `temporal_availability`,
`cross_driver_synchronization_requirement`, and per-feature version
fields; parity-skeleton interface honouring §18. F3 takes: §17
primitive contracts + §19 mutation template + §20 identifier rules +
§21 strategy. F6 takes: §9 concept set + §10 evidence + §§11–13
validity doctrine. Entry expectation for F2: semantics frozen here;
no implementation exists yet (verified: no `v2/features/`, no
registry, no operators — see F1 regression notes).
