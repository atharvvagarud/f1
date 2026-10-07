# V3.2G CAUSAL DRIVER STATUS + HISTORICAL STATE AVAILABILITY

## Final verdict

**V3.2G COMPLETE — NO AUTHORITATIVE STATUS ADMITTED — READY FOR V3.2H**

No repository-accessible historical source carries authoritative causal
driver-status semantics. Every candidate signal fails at least one item
of the ten-point RETIRED_KNOWN admission bar with quantitative evidence.
Coverage is unchanged (2305/9644, 23.90%) with zero unexplained growth,
dry-green MC2 E is bit-exact, and all refusal/API behavior is preserved.

## Frozen baseline

- tag `v3.1-race-dynamics` = commit `64c5af0`, `HEAD` identical.
- Entry dirty state: V3.2A–F work only (4 modified tracked files, all
  V3.2C presence/CI; nothing staged).

## Files changed

- `scripts/analyze_v3_2g_status.py` (Phase A causal tables with freeze
  hash + Phase B offline evaluation; labels joined only after freeze
  verification).
- `scripts/build_v3_2g_results.py`, `scripts/build_v3_2g_summary.py`.
- `scripts/freeze_v3_2f_parity_corpus.py`: V3.2G fix to `cmd_verify`
  only — order-insensitive canonicalization of nested count dicts
  (frozen corpus bytes/hash untouched; the stored file was written with
  `sort_keys=True`, fresh runs build numeric insertion order; values
  were always identical).
- `scripts/ci_corpus_dependent.txt` (+10 nodes), `scripts/run_ci_tests.py`
  (3691).
- `tests/test_v3_2g_driver_status.py` (9 source-safe),
  `tests/test_v3_2g_status_corpus.py` (10 corpus-dependent).
- `docs/V3_2G_CAUSAL_DRIVER_STATUS.md` (this file).
- `results/v3/v3_2g/` (30 files) + `results/v3/v3_2g_driver_status.json`.
- No change to kernel, engine, adapter, presence, parameters, API, or
  any runtime status behavior.

## Repository safety

Entry gate verified first; exit diff is V3.2A–F plus justified V3.2G
research/testing. Nothing staged/committed/tagged/pushed.

## Graphify before / after

`graphify update .` at entry (no topology change) with targeted
queries (RaceState/presence/eligibility, FastF1 ingestion, timing/RC/
position sources); final update at close with dependency-direction
verification (sources → presence → simulator; never labels → resolver).

## Why V3.2G exists

V3.2F proved regime modelling alone caps at +468 checkpoints: 811
TRACK×STALE and 799 WET×STALE states need stale resolution first.
V3.2C proved absence ≠ retirement (407 transient records incl. 6
eventual winners). V3.2G investigates whether any causal at-T source
for driver participation/status exists.

## Source inventory

Eight families inventoried (`source_inventory.json`): driver_laps,
results (LABEL_ONLY), race_control (verbatim, no interpretation),
weather, pit_stops (no garage concept), stints, grid_position (DNS),
raw blobs (car/position/timing-app/session-status — outside the
reproducible pipeline except D8 spatial geometry). 14,992 RC messages
across 173 races; ~171-race blob coverage.

## Source semantics

Code-proven (installed fastf1 3.7.0 + `tiera.py`): `fastf1_generated`
is verbatim synthesis flag; position NaN exactly on generated rows;
RC normalization assigns no meaning; `Status` text is not a DNF signal
(`dnf_flag` derives from classification token only). Timing-app has no
status vocabulary; session-status is session-level; position-data
Status uniformly OnTrack where sampled; pit duration is not retirement
evidence (max 7610s incl. red-flag suspension).

## Position-null provenance

`position_null ⟺ FastF1Generated` exactly (294/294 both directions, 0
non-generated nulls). Chain: FastF1 synthesis → `tiera.py:412` verbatim
→ driver_laps → D6/D7/D9 passthrough → RaceState. Upstream conflates
three generative processes: no-data synthesis, retired-on-track
last-lap synthesis (`_fix_missing_laps_retired_on_track`), missing
final laps of finishers.

## Position-null episode analysis

261 episodes / 294 rows; ALL trailing (0 with later timed rows); 207
terminal-DNF vs 54 classified finishers. Winners with null rows:
Vettel 2018-r02 (lap 57), Bottas 2020-r01 (lap 68), Verstappen 2022-r18
(lap 29) — all trailing feed gaps, plus 4 more podiums (9 top-5).

## Position-null semantic decision

**UNSAFE_FOR_RUNTIME**. Provenance shows feed-gap synthesis, not a
retirement signal; promotion would falsely terminate 3 winners.

## Race-control taxonomy

Flag 8873 / Other 4906 / Drs 524 / SafetyCar 443 / CarEvent 246.
Driver families: STOPPED 63 rows (`CAR N (XXX) STOPPED AT TURN T`,
scope null, season-skewed incl. 2023 zero); **RETIRED family: 0 rows
corpus-wide**.

## Race-control temporality

STOPPED messages carry `observed_at_s` + lap; usable at T only when
timestamped ≤ T. Latency (message − last timed row): p50 97.5s, p90
159.9s, max 417.4s. Never backdate: pre-signal checkpoints stay
ACTIVE/UNKNOWN.

## Race-control status evidence

STOPPED precision vs DNF 57/62 (0.919) but: 9/62 later timing rows
(14.5%), 5/62 non-terminal incl. winner Perez 2021-r06, 14/62 distinct
problematic (22.6%), recall vs terminal absence 0.103, 2023 silent.
STOPPED ≠ RETIRED (nothing to collapse — RETIRED never emitted).

## Timing-feed status evidence

No timing field carries stopped/retired/out/pit/garage vocabulary
(`deleted` = track limits, `is_accurate` = timing accuracy,
`fastf1_generated` = synthesis flag, `source_unit_status` uniformly
complete). Nothing to promote.

## Session vs driver status

Session-status is session-level only
(Inactive/Started/Finished/Finalised/Ends). Explicitly separated; never
driver status.

## Pit / garage semantics

No garage-entry concept in source. 369 stops >120s include red-flag
suspensions and repair-then-return. Duration alone is not retirement
proof (and was never used as such).

## Observation lifecycle

Per-driver lap sequences are contiguous (0 lap-jump interruptions
corpus-wide). Transience lives at checkpoint grain (407 V3.2C stale
records) and in 9 stopped-then-observed rows. Trailing ends are
feed-cutoff vs absence — indistinguishable at T.

## Source agreement

513 terminal-absence episodes: trailing-generated 163, STOPPED 53, both
43, **neither 340 (66.3%)**. Even agreed weak signals admit classified
finishers (3 in the 50-episode intersection).

## Offline-label firewall

Causal tables frozen first (hash `1465c11b…`, hash-verified before any
join); `results` labels joined in Phase B evaluation only. Static test
forbids truth-column references in all runtime status/eligibility
modules; the frozen `label_outcome_fields()` exclusion set re-verified.

## Candidate status signals

C1 explicit RETIRED RC (support 0 — DEAD); C2 timing terminal status
(no vocabulary — DEAD); C3 position lifecycle (261 — UNSAFE); C4
STOPPED∩trailing (50 — REJECTED); C5 STOPPED alone (62 — REJECTED). No
ML, no brute-force combinations.

## Candidate evaluation

Primary metric FALSE TERMINAL EXCLUSIONS: C3 would exclude 3W/7P/9T5;
C5 1W/1P/1T5 + 9 later-rows (14/62 bad); C4 3 classified + 6 later-rows.
Precision/recall reported diagnostically only.

## Winner / top-5 safety

Any winner exclusion is disqualifying. C3: 3 winners. C5: Perez
2021-r06 (STOPPED after final row — post-race stop archetype). Zero
unexplained transient exclusions (vacuous; admission would violate it).

## Season stability

STOPPED counts 2018:25 … 2023:0, 2024:3. Feed emission is
season-unstable without source provenance; season-scoped hacks refused.

## Signal latency

p50 +97.5s post-retirement; pre-signal states stay non-terminal, which
further caps any message-keyed recovery even if admitted.

## Driver-status contract

**Not created** (`v3.2g-driver-status-v1` reserved only). UNKNOWN
remains valid; refusals stand; V3.2C DNS semantics byte-untouched (DNS
is pre-race participation, never conflated with RETIRED_KNOWN).

## Admission decision

**NO_AUTHORITATIVE_STATUS_ADMITTED**. Every candidate fails ≥1 bar
item (table in `admission_decision.json`). No runtime resolver
implemented (Parts AE/AF gate: implement only if admitted).

## Temporal poison tests

No resolver → vacuous for status; label-firewall static test green;
pipeline poison suites inherited green (V3.2C/V3.2F).

## Transient protection

Corpus: 9 stopped-then-observed rows, 407 V3.2C transient records
(55 top-5/6 winners, cited frozen), winner-null cases. All candidates
violate preservation or are dead.

## Projected coverage

0 for every candidate (no admissible rule; projecting rejected rules
would be dishonest). Latency note recorded for future message-keyed
work.

## Projected blocker intersections

N/A without admission. V3.2F handoff cited: TRACK-only 292, WET-only
176, TRACK×STALE 811, WET×STALE 799.

## Runtime implementation

None (gate: only if admitted). Architecture for future admission
recorded (sources → resolver → presence → V3.2C → MC2 E; labels never
imported).

## Dry-green parity

V3.2F 50-corpus `verify`: **PARITY_OK**, hash `7ae97c3c…` unchanged.
Previously supported states eligible with identical fields/seeds/
outputs (Part AH gate PASS).

## Newly recovered-state validation

N/A — zero newly supported states.

## Actual coverage before / after

2305/9644 (23.90%) → 2305/9644 (23.90%). Gain +0 (+0.0pp).

## Coverage by season

Unchanged: 2018 8.7%, 2019 40.2%, 2020 18.5%, 2021 21.3%, 2022 23.2%,
2023 22.9%, 2024 31.1%.

## Coverage by stage

Unchanged: EARLY 39.6%, MID 23.2%, LATE 10.1%. Status semantics would
have helped LATE most — quantified as the cost of this verdict.

## Coverage by race

Unchanged: 103 races ≥1 support, 46 zero-support, median 9.38%,
≥50%: 30, ≥75%: 15, ≥95%: 7, full: 0. Full table in `race_coverage.json`.

## Remaining blockers

Primary: STALE 4667, TRACK 1165, WET 801, DRIVER 354, TYRE 198,
TERMINAL 154. All-blocker sets: STALE 6407, TRACK 1317, WET 1157,
TYRE 342.

## Recovery accounting

0 newly eligible; per-resolution maps empty; unexplained growth 0.

## False-admission audit

No admission occurred. Counterfactual exclusions recorded (C3: 3/7/9;
C5: 1/1/1) as the evidence that admission would have violated the ZERO
rule.

## API behavior

Unchanged: unsupported/unknown status → explicit 422
`simulation_unsupported`; no fallback; no hidden driver removal (no
resolver exists to remove anyone).

## Performance

Status-resolution overhead N/A (no resolver). MC2 itself untouched and
unoptimized per non-goals.

## External-source decision

**Corpus inadequate for authoritative causal status.** Required
information class (specification only, no integration, no provider
fabricated): timestamped official retirement/driver-status events —
on-track retirement time per driver, causally timestamped at or before
T.

## V3.2H regime handoff

Status recovery failed → V3.2H opportunity map is the V3.2F map
unchanged: TRACK-only 292, WET-only 176 behind the STALE wall (811/799
intersections). Suggested priority stands: VSC, wet feasibility, SC,
yellow (needs spatial semantics), red deferred. No regimes implemented
here.

## Known limitations

Coverage flat at 23.90%; 66.3% of terminal absences signalless;
position-Status sampled one race; STOPPED recall 0.10; authoritative
status needs an external event feed.

## Entry gate

All applicable boxes hold: baseline exact; V3.2A–F intact (parity +
primaries reproduced); graphify-first; MC2 E untouched; all status
sources inventoried with traced semantics; null provenance identified
and return behavior measured (all-trailing); null/STOPPED/PIT_IN never
promoted from correlation; RC taxonomized with temporality; STOPPED≠
RETIRED separated; timing fields investigated; session≠driver
separated; pit/garage investigated; lifecycle + agreement produced;
truth joined post-freeze with import firewall; small interpretable
candidate set, all semantically grounded; false-terminal metric
primary; winners/top-5 protected; seasons + latency reported; no
backdating; UNKNOWN valid; poison/transient/T1-T2 handled (T1-T2
vacuous with Perez counterexample recorded); projections computed
(zeros, honestly); no runtime change (gate respected);
NO_AUTHORITATIVE_STATUS_ADMITTED accepted; DNS unchanged; parity
bit-exact; coverage recomputed (unchanged) by season/stage/race;
blockers + accounting + false-admission reported; no unjustified
branching; API fail-closed; no resolver to benchmark; external need
specified; V3.2H map produced; no regimes/science/training/serving/
Strategy-2.0/frontend/cache; CI green (below); identities exact;
nothing staged/committed/tagged/pushed; V3.2H not started.
