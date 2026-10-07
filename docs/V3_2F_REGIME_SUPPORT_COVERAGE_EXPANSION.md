# V3.2F REGIME SUPPORT + COVERAGE EXPANSION

## Final verdict

**V3.2F COMPLETE — NO REGIME ADMITTED — READY FOR V3.2G**

Every candidate regime (YELLOW, VSC, SAFETY_CAR, WET, RED) was audited
against the eight scientific gates. Each fails at least one load-bearing
gate with quantitative evidence. Coverage is unchanged (2305/9644,
23.90%) with zero unexplained growth, dry-green MC2 E is bit-exact, and
all refusal/API behavior is preserved and test-pinned.

## Frozen baseline

- tag `v3.1-race-dynamics` = commit `64c5af0`, `HEAD` identical.
- Accumulated uncommitted work at entry: V3.2A–E only (4 modified
  tracked files: `api/v2_service.py`, `api/v2_simulation_service.py`,
  `scripts/ci_corpus_dependent.txt`, `scripts/run_ci_tests.py` — all
  V3.2C presence-adapter/CI work; nothing staged).

## Files changed

- `raceintel/simulation/regime_support.py` (new, declarative only:
  admission table, refusal taxonomy, reserved RNG domains; imported by
  nothing at runtime).
- `scripts/freeze_v3_2f_parity_corpus.py`, `scripts/audit_v3_2f_regimes.py`,
  `scripts/analyze_v3_2f_regime_pace.py`, `scripts/build_v3_2f_results.py`,
  `scripts/build_v3_2f_summary.py` (new research tooling).
- `scripts/ci_corpus_dependent.txt`, `scripts/run_ci_tests.py`
  (14 corpus nodes pinned; collection 3649 → 3672).
- `tests/test_v3_2f_regime_decisions.py` (9 source-safe),
  `tests/test_v3_2f_regime_corpus.py` (14 corpus-dependent).
- `docs/V3_2F_REGIME_SUPPORT_COVERAGE_EXPANSION.md` (this file).
- `results/v3/v3_2f/*` (24 deterministic artifacts) +
  `results/v3/v3_2f_regime_coverage.json` (machine summary).
- No change to the MC2 kernel, R3 engine, adapter, presence path,
  parameters, or API.

## Repository safety

Entry gate verified before any work: HEAD == tag, nothing staged,
diff limited to V3.2A–E. No commit/tag/push in this stage.

## Graphify

`graphify update .` at entry (no topology changes) and at close.
Targeted queries traced: MC2 E kernel/contract, V3.2C presence adapter,
eligibility classifier, RaceState/RaceControlState/WeatherState,
R3 empirical estimator, R7 evaluation, FastF1-derived D9 sources,
simulation service, failure taxonomy. No model-lab, frontend, or
future-data coupling introduced.

## Accepted MC2-E inheritance

Arm `E_AR1_RESIDUAL` (anchor + bounded dynamics + conditioned variance
+ AR(1) rho=0.264), kernel `mc2-kernel-v1`, RNG `mc2-rng-v1`, state
`mc2-field-v1`, presence `v3.2c-presence-v1`. Untouched throughout.

## Dry-green parity corpus

50 checkpoints from the frozen V3.2E population (10/season 2020–2024;
EARLY 20 / MID 15 / LATE 15; 9 races/circuits), arm E, seed 20240101,
n_runs 500. Hash `7ae97c3c8575679a…` frozen BEFORE any V3.2F analysis.

## Coverage opportunity

Full 9644-checkpoint recomputation reproduces V3.2C primaries exactly
(0 mismatches). All-blocker marginals: STALE 6407 sets, TRACK 1317,
WET 1157, MISSING_TYRE 342, MISSING_DRIVER 354, TERMINAL 154.
Single-blocker 5307; multi-blocker 2032 (2-blocker 1684, 3-blocker 336,
4-blocker 12).

## Blocker intersections

- TRACK-only 292; WET-only 176 → **max regime-only headroom 468
  (4.9pp)**, not 1165+801.
- TRACK×STALE 811; WET×STALE 799; TRACK×WET 278; TRACK×MISSING_DRIVER
  129; WET×MISSING_DRIVER 102; TRACK×MISSING_TYRE 88;
  WET×MISSING_TYRE 68; TRACK×TERMINAL 23; WET×TERMINAL 13.

## Track-state decomposition

Checkpoint tokens: all_clear 8327, yellow 600, safety_car 417, vsc 137,
vsc_ending 71, null 70, red_flag 22. Tokens are the frozen D9 per-lap
last-char FastF1 mapping (1/2/4/5/6/7); no LOCAL/FULL distinction
exists. Non-green primaries: TRACK_STATE except where the adapter
(MISSING_DRIVER) or terminal check fires first; STALE never surfaces as
primary under neutralisation because contemporaneity is validated after
the track check (but is present in 811 TRACK all-blocker sets).

## Local-yellow semantics

**YELLOW_DEFERRED_INSUFFICIENT_SPATIAL_SEMANTICS.** Yellow-lap pace
delta median only +0.46s (n=3982 dry rows); per-yellow-lap median 5.9%
of drivers slowed >2s (315 laps) — the token is overwhelmingly local.
RC last-message channel is stale/unrelated in most rows (median age
16.9s; 2202/5877 rows carry no flag; only 771 YELLOW + 471 DOUBLE
YELLOW). Sector mentions exist (3155 rows) but no sector→driver
exposure mapping exists in frozen RaceState. A global yellow penalty
would misprice ~94% of the field. Frozen Phase-12 spatial data was not
coupled (no justified mapping).

## VSC evidence

Pace process measurable (median +19.6s, n=892 dry rows) but admission
needs: stochastic duration (55 lap-level episodes, p50 1 lap — thin),
restart transition, and regime-conditioned anchor history (mid-VSC
checkpoints carry +20s VSC laps in the 8-lap anchor window, breaking
accepted anchor/dynamics/variance/AR1 semantics).
**DEFER_VSC** (boundary A sketched, unestimated).

## Safety-Car evidence

SC reshapes pace (+33.2s median, sd 18.7s, n=3611), gaps (bunching),
pit incentives, and restarts (first-2-green-laps sd 21.2s, n=1840).
104 lap-level episodes (p50 3 laps). No compression/duration/restart
model exists; R6 transitions are dry-filtered. Pace+N-seconds modeling
explicitly rejected. **DEFER_SC**.

## Red-flag evidence

22 checkpoints, 0 usable lap rows, 21 episodes, 17 races. Suspension
semantics differ substantially. **DEFER_RED** (default expectation
confirmed).

## Wet-state decomposition

1157 WET-blocked sets: rain-falling 553, wet-compound 946, both 342.
Wet-compound counts are bimodal: full-field wet (19–20 drivers, 512
states) vs mid-transition partial fields (1–7 drivers, ~330 states) —
the compound-transition boundary in the data.

## Wet pace evidence

INTERMEDIATE laps plentiful (~6.9k); WET-compound rain laps thin (294
across eras → unstable circuit×compound cells, none created).
Slicks-in-rain 3818 laps. Dry anchor/dynamics/variance/rho transfer is
unproven and assumed invalid. **DEFER_WET**: weather evolution and
wet/dry compound transitions have no causal mechanism in scope.

## Weather evolution

No future weather may be read. Options assessed: stochastic
persistence/transition (unestimated), horizon-limited persistence
(unvalidated), refusal (adopted). No mechanism implemented.

## Compound transition

R6 `compound_transition_probability` is dry-filtered by design; wet
targets are removed and mass renormalized. Wet/dry transitions would be
strategy modeling (Strategy 2.0, forbidden). Boundary unresolved →
wet cannot be simulated to the flag honestly.

## Parameter temporal policy

Evaluation season Y → training strictly before Y (through-season
artifacts; no 2025). Fold pattern inherited from V3.2D. Zero new
families estimated in V3.2F.

## RNG domains

`mc2-vsc-duration`, `mc2-sc-duration`, `mc2-weather-transition`
reserved, unconsumed, disjoint from residual/pace streams by
construction (`regime_rng_domain`, tested). Same-seed/CRN rules stated
for future consumers.

## Future-regime firewall

Poison test mutates/removes after-T TrackStatus, rainfall, and
compounds (→ SC/rain/WET): capable T-state adaptation bit-identical,
eligibility unchanged. V3.2C presence poisons remain green.

## Admission decisions

DEFER_YELLOW / DEFER_VSC / DEFER_SC / DEFER_WET / DEFER_RED, each with
exact reason identity (see machine summary). Implemented: none.
Deferred regimes remain explicitly unavailable (422).

## Implemented regimes

None.

## Deferred regimes

YELLOW, VSC, SAFETY_CAR, WET, RED — all refuse via the unchanged
pipeline with frozen taxonomy tokens.

## Regime validation

NOT_APPLICABLE_NO_ADMITTED_REGIME. Validating a deferred regime by
running dry-green dynamics under a removed guard is forbidden and was
not done. Validation population/comparator/metrics rules are recorded
for admitted-regime use in V3.2G+.

## Dry-green parity

Rerun of all 50 corpus members: 100% bit-exact (values identical;
Part Y gate PASS via `test_dry_green_parity_corpus_bit_exact`).

## Coverage before / after

Before 2305/9644 (23.90%) → after 2305/9644 (23.90%). Gain +0 (+0.0pp).
103 races with ≥1 supported checkpoint; 46 zero-support; median race
coverage 9.38%; ≥50% races 30; ≥75% 15; ≥95% 7; fully-supported 0.

## Coverage by season

2018 8.73% (121/1386); 2019 40.19% (547/1361); 2020 18.46%
(208/1127); 2021 21.34% (299/1401); 2022 23.21% (333/1435); 2023
22.88% (323/1412); 2024 31.14% (474/1522). Unchanged after.

## Coverage by stage

EARLY 39.55% (1218/3080); MID 23.22% (748/3222); LATE 10.14%
(339/3342). Late-race weakness is structural (stale rosters +
terminal + neutralisations accumulate) and is not hidden.

## Coverage by regime

DRY_GREEN 27.68% (2305/8327); YELLOW/VSC/VSC_ENDING/SC/RED/UNKNOWN all
0% supported by decision (refused, not attempted).

## Remaining blockers

STALE_ROSTER 4667 primary (6407 sets) — next limiting factor, but
roster safety forbids exclusion. Then TRACK_STATE 1165, WET 801,
MISSING_DRIVER 354, MISSING_TYRE 198, TERMINAL 154. No new taxonomy
tokens introduced.

## Recovery accounting

0 newly supported checkpoints; per-admission and per-improvement maps
empty; unexplained growth 0. MISSING_TYRE 198 inspected: lap-1
all-null rows + early-retirement data gaps (stint fields null too) —
no causal source; V3.2C deferral stands with evidence.

## Roster safety

V3.2C authoritative. Absence ≠ retirement. 811 TRACK + 799 WET states
carrying STALE remain unavailable. No exclusion added.

## Position-null decision

DEFER_POSITION_NULL: no semantic proof found; V3.2C 0-false-positive
finding cited, never promoted.

## Performance

Parity corpus: 50×500 runs in 25.2s (~992 runs/s @8 workers).
Inherited V3.2E: ~97 runs/s single, 13.6× R3 slowdown, ~33.1 serial
hours / ~5.9h @8w for the 5000-run catalogue. No admitted regimes to
benchmark; MC2 E untouched.

## Precompute optimization plan

Bottlenecks: per-driver pandas anchor prep, Python event loop,
per-job parquet reload, full-distribution serialization. Safe vectors:
batched anchor prep (parity-proved), multiprocessing (in use),
shared-memory frame cache, CRN-preserving draw batching. Forbidden
without proof: kernel rewrites, RNG reassignment, n_runs cuts without
TV revalidation. Plan only — no risky optimization performed.

## API behavior

Deferred regimes → explicit 422 `simulation_unsupported` with frozen
reasons (tested per regime: yellow/SC/VSC/wet). Never silently falls
back to DRY_GREEN. capable-path behavior unchanged.

## Result provenance

No admitted regimes → schema unchanged. Existing artifacts already
carry MC2 identity + presence identity + seed + n_runs.

## Tests

9 source-safe (normal CI green) + 14 corpus-dependent (manifest
pinned; collection 3649 → 3672). Covers: decisions, RNG domains,
taxonomy, headroom identity, selection determinism, pinned refusals,
future poison, parity bit-exactness, API 422s.

## Scientific identities

- field contract `mc2-field-v1` (713d6e4df22bf096)
- presence adapter `v3.2c-presence-v1`
- MC2 research `mc2-r1-research` (25b35762c4f175dc)
- regime support `v3.2f-regime-support-v1`
- parity corpus `7ae97c3c8575679a…`

## Known limitations

See machine summary `known_limitations` (coverage flat at 23.90%;
LATE 10.14%; 46 zero-support races; STALE as next limiter; VSC/wet
need V3.2G+ programs).

## V3.2G entry gate

READY: opportunity map + intersections + regime evidence + wet dataset
+ draft contracts + reserved RNG domains + parity corpus + firewall
tests. V3.2G not started. Suggested order: VSC duration/restart pilot,
then wet evolution/transition feasibility — each as its own
estimate→validate→admit ladder with race-level aggregation.
