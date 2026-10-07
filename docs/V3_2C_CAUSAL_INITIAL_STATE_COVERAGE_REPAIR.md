# V3.2C CAUSAL INITIAL-STATE ADAPTER + COVERAGE REPAIR

Contract-realization stage. V3.2B froze what Monte Carlo 2.0 may consume;
V3.2C integrates the frozen `mc2-field-v1` presence contract into the
simulation initial-state path and repairs only coverage recoverable
without future information. No stochastic science was changed: no pace
equation, no anchor, no slope, no AR(1), no residual, no traffic, no
overtaking, no DNF sampling, no wet/SC evolution, no pit-behavior change,
no refit, no training, no serving promotion, no cache, no frontend,
no Phase-7 change, no V3.2D science.

## Final verdict

V3.2C COMPLETE — READY FOR V3.2D

Actual coverage after safe repair: **2305/9644 (23.9%)**, +31 states over
the R3 baseline, zero eligibility regressions, all previously valid
states bit-exact, all poison/parity/RNG/strategy gates green. The only
admitted recovery source is the frozen DNS exclusion; no retirement rule
was admitted; tyre backfill was rejected on evidence.

## Frozen baseline

- Tag `v3.1-race-dynamics` = `64c5af094bd1304e23a5c7d3d5b782b0eef11aca`;
  HEAD identical at entry (verified `git rev-parse HEAD` and
  `git rev-parse v3.1-race-dynamics^{commit}`).
- Entry dirty state: exactly the 8 accumulated V3.2A/B files, nothing
  staged. V3.2A/B evidence intact and unmodified throughout.

## Files changed

Modified (4 tracked):

- `api/v2_service.py` — additive pre-race grid-slot map (`grid_slots`);
  identity + `grid_position` columns only, no outcome field touched.
- `api/v2_simulation_service.py` — additive DNS filtering before the
  unchanged `from_race_state` call; optional `grid_by_race` (None =
  exact pre-V3.2C behavior); frozen 422 error types preserved.
- `scripts/ci_corpus_dependent.txt` — registered 101 corpus-dependent
  V3.2 nodes (1 V3.2A + 3 V3.2B + 97 V3.2C Tier-3 nodes).
- `scripts/run_ci_tests.py` — `EXPECTED_COLLECTED` 3496 → 3616 with
  per-stage accounting comment (6 V3.2A + 12 V3.2B + 102 V3.2C tests).

New (V3.2C):

- `raceintel/simulation/presence.py` — causal initial-state adapter
  (`v3.2c-presence-v1`); stdlib + raceintel imports only.
- `scripts/freeze_v3_2c_parity_corpus.py` — pre-change parity freezer.
- `scripts/audit_v3_2c_coverage.py` — DNS-aware full-catalogue audit.
- `scripts/analyze_v3_2c_signals.py` — offline at-T signal diagnostics.
- `tests/test_v3_2c_presence_adapter.py` — 25 adapter/poison/policy tests.
- `tests/test_v3_2c_parity.py` — 77 parity/RNG/strategy/API nodes.
- `results/v3/v3_2c_parity_corpus.json` — 70-entry frozen corpus.
- `results/v3/v3_2c_coverage.json` — full 9644-state eligibility audit.
- `results/v3/v3_2c_signal_diagnostics.json` — offline measurements.
- `docs/V3_2C_CAUSAL_INITIAL_STATE_COVERAGE_REPAIR.md` (this file).
- `results/v3/v3_2c_causal_initial_state_coverage.json` — machine record.

Untouched (frozen): `adapter.py`, `engine.py`, `state.py`,
`monte_carlo.py`, `params.py`, `validation.py`, `field_contract.py`,
strategy, replay, race-state, model-lab, frontend, parameters, replay
artifacts. Nothing staged, committed, tagged, or pushed.

## Repository safety

Entry gate passed (Part A): HEAD = tag = `64c5af0…`, 8 dirty V3.2A/B
files, nothing staged. Exit state: only the paths listed above, nothing
staged, no commit/tag/push. Replay artifacts byte-verified against the
frozen build manifest (149/149 hashes match, 9644 checkpoints).

## Graphify before / after

- Before (inherited V3.2A record; `graphify update .` at entry reported
  no topology changes): nodes 13164, edges 31207, communities 354.
- After (final `graphify update .` at close): nodes 13462, edges
  32037, communities 372 (+298/+830/+18 from V3.2C sources: presence
  module, service seams, scripts, tests). Targeted queries/path tracing
  used for field contract, RaceState, replay construction, adapter, validation, roster, grid/DNS,
  tyre/track/weather provenance, R4/R5/R6, R8 service, Phase-7 callers.
- Dependency direction preserved: state/adapter contract feeds the
  simulator; the simulator never feeds historical-state construction;
  no model-lab → simulator edge; no frontend edge; no new cycle.

## V3.2B contract inheritance

Field contract `mc2-field-v1`, full identity
`713d6e4df22bf09664ca3c6a2a99fea1941c57492d5afe55fb836e7bdab32691`
(verified live via `contract_identity()`), six presence levels used
exactly once in `presence.classify_roster`. Sole frozen exclusion:
`EXCLUDE_DNS_PRE_RACE`. `EXCLUDE_SIGNALED_STALE` stays a measured
candidate (never applied). Track/weather/terminal policies preserved
verbatim. Coverage baseline 2274/9644 inherited; projected +138
corrected to actual +31 with exact accounting (below).

## Pre-change parity corpus

Frozen BEFORE any simulation-source modification (new files only;
adapter/engine untouched — verified by diff):
`results/v3/v3_2c_parity_corpus.json`, schema `v3.2c-parity-v1`.
70 entries (10/season, 2018–2024; stages 43 EARLY / 18 MID / 9 LATE —
late skew is honest: late states are usually stale/refused). Per entry:
race, frame, stage, frozen versions, parameter identity, and arms:
pits-off R3 arm (n=100, seed 20240101) for all 70 + pits-on arm for the
first 20. Each arm pins `result_identity`, `request_identity`, roster,
valid/invalid counts, top driver. LATE under-representation reflects
refusal reality, not selection bias (first capable frame per band).

## Field-contract integration

`raceintel/simulation/presence.py` binds `field_contract.py` once:
`classify_roster` → `dns_exclusions` → `without_drivers` →
unchanged `from_race_state` → terminal check → `select_pace_parameters`
→ `_validate_start_state` + `_validate_temporal` → typed
`EligibilityResult`. Contract semantics are never duplicated; the
frozen module is the single classifier. No kernel file imports the
adapter.

## DNS source proof

DNS = unobserved at every T (zero D9 rows) AND no pre-race grid slot
(`grid_position` null). Grid is determined in qualifying — strictly
before the race — and carried as metadata on the results entity; only
its null-ness is ever read. Forbidden sources (final classification,
`dnf_flag`, `position_final`, `winner_flag`, future rows) are never
read by grid extraction, presence classification, or exclusion: proven
by permanent tests that mutate all of them (results-level and D9
evidence-level poisoning) with byte-identical eligibility. Proven cases:
mazepin 2021-r22-R (Illness, 0 laps), stroll 2023-r15-R (Withdrew),
mick_schumacher 2022-r02-R (Withdrew). Without a grid map the adapter
claims no DNS and refuses (strictly conservative; tested).

## DNS implementation

`dns_exclusions` returns proven-DNS ids (deterministic order);
`without_drivers` removes them from the `RaceState` copy (anchor can
never be DNS — guarded); the service adapts the filtered state through
the unchanged `from_race_state`. With no DNS member the state object is
untouched → previously valid requests adapt bit-identically (proven by
corpus + live service identity match).

## Transient-absence protection

Pinned fixtures (observed at T, stale vs bound, later D9 rows prove
transience, top-5 finishes): 2020-r08-R frame 490 gasly (eventual
WINNER), sainz (P2), stroll (P3); 2020-r09-R frame 122 bottas (P2),
albon (P3). Tests poison all future results and require: presence
`STALE_UNRESOLVED`, never excluded, state refused (not driver dropped),
winner retained in the active field. Full-corpus offline labels confirm
the danger: 407 transient records, 55 top-5, 6 eventual winners —
any absence-implies-retirement rule would drop live contenders.

## Retirement policy

No generic retirement inference exists in V3.2C. `STALE_UNRESOLVED`
→ refuse the STATE (`STALE_ROSTER_OBSERVATION`), never remove the
driver. No `RETIRED` status is ever produced anywhere in the path
(tested). V3.2B's causality finding stands: at T the system observes
absence, and absence is not retirement.

## STOPPED diagnostic

Offender-level re-evaluation (9801 records; ANY RC STOPPED message
observed ≤T naming the car + behind≥2 guard): precision 0.933,
recall 0.122 (V3.2B: ~0.90/0.125 — reproduced). Season breakdown is
fatal: recall 0.319 (2018) → 0.228 (2021) → 0.057 (2022) → 0.000
(2023); 82 false positives concentrated in 2018 (38) and 2019 (44).
The feed is a season-unstable artifact, not a contract basis. Further:
`RaceState` carries no message text at all, so a runtime rule would
need new attribution plumbing (multi-car "CARS 3 AND 23" formats,
number→driver mapping) with no frozen semantics. Verdict:
MEASURE_ONLY / REJECT_RUNTIME_RULE.

## PIT_IN diagnostic

Terminal no-signal offenders ending with `pit_in` on the last row:
0.442 (V3.2B sampled 0.42 on a subset — reproduced on the full corpus). Rule form
(pit_in_last + not stopped + behind≥2): precision ~0.99 but 30 known
false positives (25 in 2023, 4 in 2020-r15 red-flag, 1 in 2024) —
including barely-stale rejoins (perez 2023-r16, age 1.3–2.3x) that a
garage rule would drop while live. Recall 0.32–0.51 by season.
Verdict: DEFER (measurement only; 30 FPs fail the admission bar).

## Other retirement signals

Small interpretable set, offender-level, all seasons: behind≥2 (204
FPs — reject), behind≥5 (188 FPs — reject), age>10x (79 FPs, season
precision 0.90–1.0 — reject), position_null (0 FPs in all 7 seasons,
recall 0.42–0.66 — see below; still rejected).

position_null audit (the strongest temptation, +1899 states potential):
5564 offender records with null tail position, 0 FP; corpus-wide, all
294 null-position D9 rows are terminal tails (0 with later rows);
1899 stale states have all-null offenders, all all-terminal. REJECTED
anyway: correlation without a documented feed mechanism (V3.2B: "a
large coefficient is not a mechanism"); would contradict the frozen
causality finding without a dedicated feed-semantics program; single-FP
catastrophe risk (removing a live contender) vs coverage gain;
feed-behavior fragility precedent (RC STOPPED collapse 33%→0% recall).
Recorded as the prime V3.2D lead with exact numbers, not as a rule.

## Retirement-rule decision

ADMIT_NONE. No candidate meets all seven admission-bar criteria
(causal, future-free, interpretable, near-zero FP, season-stable,
deterministic, poison-testable). This is the explicitly acceptable
V3.2C result. The refusal default (REFUSE THE STATE, never REMOVE THE
DRIVER) is preserved end to end.

## Tyre backfill investigation

628 null-tyre driver-checkpoints across the 198 MISSING_TYRE states:
for each, last ≤T known (compound, age) + barrier scan (compound /
stint / pit-count discontinuity, pit transition on the at-T row, pit
event between, never-observed). Result: 172 NEVER_OBSERVED_TYRE
(nothing to carry — incl. wholesale-null early-2018 starts) and 456
with ≥1 state-changing barrier (stint changes dominate: 120 pure
stint-change, 151 stint+pit-count+pit-between, 141 compound+stint+pit,
27/16 with at-T transitions). CLEAN_CARRY: 0/628.

## Tyre backfill decision

REJECT_BACKFILL. No candidate admits a causal carry: every case is
either sourceless or separated from T by a pit/stint/compound event.
A bounded rule would recover 0 states while risking crossed pit
events. Default REMAIN_REFUSAL stands; revisit only with new
tyre-provenance evidence (V3.2D+, not a refill).

## Track / weather preservation

DRY_GREEN is the sole supported initial; yellow/SC/VSC/VSC_ending/red/
null stay refused (exact engine reasons pinned by test:
`neutralized_track_state`, `red_flag_track_state`,
`unknown_track_state`); wet stays refused (`wet_track_conditions`,
`wet_compound_state` — API-proven 422). Coverage was not bought by
relaxing any policy: TRACK 1138→1165 and WET 801→801 movements are
DNS-unblocked states reaching the unchanged validators (accounted).

## Terminal policy

`leader_laps_done >= scheduled_laps` stays TERMINAL refusal (151→154;
the +3 are DNS-race final checkpoints now reaching the unchanged
check). Deterministic boundary, tested on 2024-r15-R last frame. No
future-after-the-fact simulation.

## Adapter architecture

State preparation (`presence.py`) is fully separated from stochastic
evolution (R4/R5/R6 untouched, never import the adapter). Order:
RaceState → presence classification → DNS exclusion → R2 adaptation →
terminal → parameter selection → start-state validation → unchanged
engine. No historical inference lives in the kernel.

## Eligibility result

`EligibilityResult` (frozen dataclass): eligible, taxonomy reason,
detail, per-driver presence, excluded DNS ids, active ids, field
contract version+identity, adapter version, and the start state when
eligible. Deterministic; raises nothing. The service seam keeps raising
the frozen exception types (422 mapping unchanged); the typed result
drives audit/tests/new callers.

## Failure taxonomy

V3.2A tokens reused verbatim, no proliferation, one primary reason per
state (audit order fixed). Adapter/engine reason maps restated in
`presence.py` (runtime code never imports scripts) with identical
semantics to the V3.2A classifier.

## R3 parity

70/70 corpus entries bit-exact post-change on BOTH arms (70 pits-off
+ 20 pits-on): `result_identity`, `request_identity`, roster order,
valid/invalid counts, top driver — all identical. 100% of previously
valid checkpoints remain valid (zero race-level regressions across
all 149 races). Live service check: previously valid request returns
the identical `scientific_result_identity` with and without the grid
map. No "small numerical difference" — BIT-EXACT.

## RNG parity

Same-seed equality ✓; chunk 64 vs 512 invariance ✓ (pinned to corpus
identity); presence classification interleaved between runs changes
nothing (consumes no RNG — tested); R6 pit domain separation untouched
(pits-on arms bit-exact). RNG stream positions preserved exactly.

## Strategy compatibility

Phase-7 untouched (strategy service still calls bare `from_race_state`;
no import added). Pinned comparison (2018-r01-R frame 90, target
alonso, 32 runs, pits off): identity
`f54e95a1…889771`, supported, green. CRN pairing and scenario
semantics unchanged for previously supported states. If strategy
science had moved, the gate would have stopped the stage — it did not.

## Actual overall coverage

2305/9644 (23.90%) eligible; 7339 refused. Baseline 2274 → +31.
Eligible races 103 (101 + the two repaired zero-coverage races);
zero-coverage races 48→46; fully covered races 0; median race coverage
0.094 (R3: 0.091).

## Coverage by season

2018: 121/1386 (8.7%, +0). 2019: 547/1361 (40.2%, +0). 2020: 208/1127
(18.5%, +0). 2021: 299/1401 (21.3%, +29 — 2021-r22-R). 2022: 333/1435
(23.2%, +0; 2022-r02-R stays refused on the tsunoda gap as predicted).
2023: 323/1412 (22.9%, +2 — 2023-r15-R). 2024: 474/1522 (31.1%, +0).

## Coverage by stage

EARLY 1218/3080 (39.6%), MID 748/3222 (23.2%), LATE 339/3342 (10.1%).
Recovered states: 20 EARLY + 11 MID + 0 LATE — late-race retirement
accumulation remains the binding constraint (not hidden). Convention
note: stages are assigned from `RaceState` progress for every
classifiable state (V3.2A left 492 adapter-refused states stageless);
eligible counts are directly comparable, denominators differ by that
documented convention.

## Coverage by race

Full per-race table persisted in `results/v3/v3_2c_coverage.json`
(`races` + per-checkpoint `checkpoints`). Exactly two races improved
(2021-r22-R 0→29, dominant failure now STALE; 2023-r15-R 0→2,
STALE). Zero regressions in any of the other 147 races. Largest
improvements are exactly the V3.2B-predicted DNS races — direction
predicted, magnitude corrected (below).

## Failure counts after repair

STALE 4667, TRACK 1165, WET 801, MISSING_DRIVER 354, MISSING_TYRE 198,
TERMINAL 154, others 0, CAPABLE 2305 (sums to 9644). Deltas vs R3:
STALE +77, TRACK +27, TERMINAL +3, MISSING_DRIVER −138, CAPABLE +31,
WET/TYRE unchanged. Every delta is a DNS-unblocked state reaching the
unchanged validator (proven: only MISSING_DRIVER states can change
verdict, since DNS removal only deletes roster members — the
−138/+107/+31 arithmetic is airtight).

## Recovery accounting

`sum(recovery sources) = eligible_new − eligible_baseline`:
DNS_EXCLUSION 31 + TYRE_BACKFILL 0 + RETIREMENT_RULES 0 = 31 = 2305 −
2274. The 29 + 2 split by race is listed per-checkpoint
(`dns_recovered` in the coverage record). No unexplained increase.

On the V3.2B +138 projection: it counted states where DNS was A
blocker, not the SOLE blocker. 107 of those 138 carry independent
blockers (77 stale retirements, 27 neutralised/track, 3 terminal)
revealed once DNS is removed. The projection's race-level prediction
(2021-r22 + 2023-r15 recover, 2022-r02 stays refused) holds exactly;
only the magnitude is corrected. PROJECTED_ELIGIBILITY was never
actual coverage — this stage makes that distinction empirical.

## False-admission audit

All 31 recovered states: excluded members are true non-participants
(mazepin Illness/0 laps/unclassified; stroll Withdrew/0
laps/unclassified — offline labels only); eventual winners
(verstappen 2021-r22, sainz 2023-r15) hold grid slots and are never
excludable; no tyre fill involved; no unknown state assumed (full
roster grid facts present); all 31 simulate 100/100 valid and
deterministically. No winner/top-finisher removed anywhere. Green.

## Temporal poison tests

Permanent suite: results-level poisoning (dnf/position/winner/status/
points/laps mutated — grid + eligibility byte-identical), D9
evidence-level poisoning (future tyre/pit-in/pit-out rows fabricated —
verdict identical), V3.2B-inherited future-row invisibility (T1 active
despite later factual DNF; T2 stale never claims retirement; presence
inputs identical under poison). Runtime sources contain no
dnf/winner/position-final/classified/status/label token (source
scanned). The AF gate is green.

## Replay identity

Aggregate `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298`
inherited from V3.2A/B provenance; all 149 per-race artifacts
re-verified byte-identical against the frozen build manifest (0
mismatches, 9644 checkpoints). The adapter interprets existing causal
replay state; nothing regenerated or altered.

## Parameter identity

`phase6-r3-empirical`, content hash
`4c2f85f08f1ce66cc6477982b2d5c97e9547f70927224b8e949ebe123ff3f140`
(verified live; matches V3.2A record and the R8 frozen pin). No
regeneration, no refit.

## Versioning

Engine science versions UNCHANGED: simulation contract `v1`,
`r4-engine-v1`, `r5-monte-carlo-v1`, `r6-pit-dynamics-v1`, parameters
`r3-v1`. New: initial-state/eligibility contract
`v3.2c-presence-v1` (presence.py) over the unchanged field contract
`mc2-field-v1`. The stochastic kernel is NOT called MC2.0 (no
V3.2D science exists yet); API payloads still report the R3/R4/R5/R6
identities. R3 identity never overwritten.

## Performance

Presence overhead 0.03 ms/state (prepare 0.09 ms vs adapter 0.05 ms)
— negligible against ~70–500 ms per 100-run simulation. Full
9644-state eligibility scan: 507.8 s wall (~53 ms/state, dominated by
`RaceState` reconstruction). No optimization needed.

## API compatibility

Previously valid `POST /v2/simulations/race` requests: identical
`scientific_result_identity` (live old-vs-new service check +
corpus pits-on arm match through the production path). DNS-repaired
states: deterministic 200 (19-driver field, 64/64 valid, repeat
identical). Unsupported states: exact 422 `simulation_unsupported`
with stable reasons (wet/compound, missing tyre, stale via service
path) — no fallback, no silent drop. Route mapping untouched.

## Local execution

Service path IS the local invocation path (same request/result
schema); verified working with identical scientific output. Docker
untouched. No demo cache generated (forbidden before V3.2F).

## Tests

25 presence/adapter tests + 77 parity/RNG/strategy/API nodes, all
green; inherited V3.2A/B suites green (R8 service suite green).
CI registration: 101 corpus-dependent V3.2 nodes pinned in
`ci_corpus_dependent.txt` (Tier 3); 19 pure V3.2 tests stay in Tier 1;
`EXPECTED_COLLECTED` 3496→3616. Tier-1 gate status in machine record.
No snapshot updated to force green; no failure skipped.

## Scientific identities

v3.1-race-dynamics →
`64c5af094bd1304e23a5c7d3d5b782b0eef11aca` (live-verified tag+HEAD);
V2 serving `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`;
Phase-2 content `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`;
Phase-2 parquet
`b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3`;
explainability
`bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f`;
replay `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298`
(artifacts byte-verified); simulation `r3-v1` through 2024
`phase6-r3-empirical`; V3.1 artifact
`9a1aac515d12c4e86ac369977392f74394cf7f6853b8e89d948bcdec28f58960`
(unpromoted, from provenance); field contract `mc2-field-v1` →
`713d6e4df22bf09664ca3c6a2a99fea1941c57492d5afe55fb836e7bdab32691`
(live-verified). Nothing regenerated.

## Known limitations

- Legitimate headroom stays small: +31 states (+0.3pp). The 107
  DNS-adjacent states carry independent blockers; stale exclusion
  remains unproven at T by construction.
- 6 winner-cases inside the transient class: any absence-based rule
  remains catastrophic-risk until feed semantics are proven.
- position_null (+1899 potential) deliberately not promoted: recorded
  with full evidence as the prime V3.2D feed-semantics lead.
- RC feed unsuitable as retirement evidence (recall 0.32→0.00
  collapse by season).
- Wet/neutralised need full new empirical programs; kernel limits
  persist (all R3 limits: no overtaking/traffic/DNF/weather/pit
  optimization).
- Stage skew: LATE coverage 10.1%; recovered states are EARLY/MID.

## V3.2D entry gate

V3.2C hands off: presence adapter (`v3.2c-presence-v1`) with DNS
exclusion proven; tyre backfill REJECTED (0/628); retirement rules
ADMIT_NONE with measurements (STOPPED/PIT_IN/position_null + season
tables + FP examples) as V3.2D input; actual coverage 2305/9644 with
full accounting; R3 parity corpus frozen (70 entries, bit-exact);
strategy compat pinned; no stochastic change. V3.2D owns: anchor
estimator, regime residuals, AR(1), traffic penalty, stint
recalibration — each versioned, none started here.
