# V3.2M CAUSAL PIT LIFECYCLE FEASIBILITY + STALE COVERAGE RECOVERY

## Final verdict

V3.2M COMPLETE — PIT LIFECYCLE REJECTED — READY FOR V3.2N

## Frozen baseline

- Tag `v3.1-race-dynamics` == HEAD `64c5af0`. Nothing staged.
- Dirty state is V3.2A–L research + M only (scripts/docs/results/tests).

## Why V3.2M exists

V3.2L rejected the general driver lifecycle model but decomposed 1874
LIFECYCLE_FULLY_ADDRESSABLE checkpoints (projection only, never admitted)
and 214 PIT_CONTEXT episodes (Stopped onset with InPit True). M tested the
narrower hypothesis: a causally observable routine pit/service state with a
hold/resume mechanism could recover STALE checkpoints without solving
general retirement/return uncertainty.

## V3.2L inherited evidence

- 476 episodes: CLEAN 211 / PIT_CONTEXT 214 / INITIAL_UNKNOWN 41 /
  LATE_SESSION 10. Returned 85 (definition: any later D9 crossing).
- PIT_CONTEXT (L rule): latest InPit True at stop start. Nothing more.
- Coverage 3678/9644 (38.14%); primary STALE 3294.
- Identities: J `v3.2j-driver-status-v1`, corpus `8229a8606…`, K prereg
  `567260af…`, L prereg `4c3eb5c8…`, dry-green `7ae97c3c…`. All verified.

## Preregistration

`results/v3/v3_2m/preregistration.json`, SHA
`3161cf5275e8a2cfe3ef71032315c0084f3a6ca09fd297940576c1a74123bea6`.
Season-forward folds, forbidden future signals, admission gates, stopping
rule. Every M script verifies it.

## PIT_CONTEXT episode audit

Split tables: `pit_episode_causal.json` (x_ only) /
`pit_episode_future.json` (y_ only). Per episode: InPit/PitOut/Stopped/
Retired latest at start, InPit entry time, elapsed-in-pit, pit-stop count,
D9 last state, track; future: time to PitOut / clearing / D9 return /
Retired-after / terminal.

## Causal pit-state candidates

Causal-only rule: PitOut latest True → PIT_EXIT_TRANSITION; InPit True +
entry ≤120 s → PIT_SERVICE_ACTIVE (n=11); InPit True older/unknown →
PIT_LANE_STOPPED (n=203); else AMBIGUOUS (n=0).

## Source semantics

- InPit updates in nearly all races; True persists (~sticky) — a set True
  is still True minutes later at high rate.
- PitOut is a pulse (median True-hold short), not a persistent state.
- Stopped True→False clearing is slow/unreliable (L finding confirmed).
- NumberOfPitStops stream key: season availability tabulated in artifact.
- L's RED/NEUTRALISED episode classes are empty: stage-1 compared the raw
  D9 `track_status` code ('5') against the token `'red_flag'` (canonical
  token lives in `track_state`). Red-flag stops therefore leak into
  PIT_CONTEXT/CLEAN. M handles this by mechanism analysis, not relabelling.

## Pit-return firewall

- P(return | PIT_CONTEXT) = 14/214 = 6.5%.
- PIT_SERVICE_ACTIVE (recent entry): 0/11. PIT_LANE_STOPPED: 14/203 (6.9%).
- 9/14 returns: 2020-r09-R (Tuscan GP) with elapsed-in-pit ≈21 min —
  red-flag suspension with cars held in pit lane (canonical `flag_red`
  confirmed), i.e. session resumption in an MC2-unsupported regime, not
  routine service. Remainder: late retirements / artifact blips
  (13.5 s D9 with no PitOut; 41 min garage return then retirement).
- 198/200 non-returns: no clearing, no PitOut, no D9 — terminal.
- Verdict: REJECT_CANDIDATE_SCOPE. No causal sub-state separates routine
  service from garage/terminal.

## Temporal folds

`<=2020→2021, <=2021→2022, <=2022→2023, <=2023→2024`. No random split.

## Remaining-duration target

First D9 crossing after stop start minus start (PitOut timing also
reported; target choice is by MC2-resumption semantics, not by error).

## Duration baselines

Returned N=14: median 29.3 s, p90 400.8 s, max 2468.2 s. Folds carry ≤1
eval episode each — no baseline is supportable, let alone ML.

## Duration model

Elapsed-conditional empirical distribution (design only). No driver
identity, no future outcome.

## Temporal validation

DURATION_MODEL_FAILURE: too few returned episodes per fold for stable
temporal validation (fold MAE on n=1 is meaningless: 15.8 s vs 2441 s).

## STALE pit opportunity

Strict causal contract (Stopped True + InPit True + sufficient anchor +
not J-retired) applied to frozen 3294 checkpoints (causal only):
- Offenders: GENERAL_LIFECYCLE 5661 / J_RETIRED 2067 / AMBIGUOUS 249 /
  NO_PIT_SIGNAL 0 / PIT_LIFECYCLE_CANDIDATE 0.
- Checkpoints: GENERAL_ONLY 3259 / J_ONLY 22 / OTHER 13 /
  PIT_FULLY_ADDRESSABLE 0.
- Structural reason: all 5661 ADDRESSABLE stale offenders are InPit False
  at T (median stopped age ≈41 min — routine pits never survive to
  staleness); all 2067 InPit-True-at-T offenders are J-retired (already
  covered, precedence holds); 48 stopped-cleared InPit-True rows are
  ambiguous, never hold states.

## Coverage projection

Projection only: +0 → 3678/9644 (38.14%) unchanged.

## Materiality

IMMATERIAL_OR_INADMISSIBLE: science gates fail first (firewall +
duration), and N=0 regardless.

## Initial pit-state design

Design-only (`initial_pit_state_design.json`): last valid race-distance
state + pit state + sampled additional delay; hold then resume MC2-E;
isolated `raceintel/simulation/pit_lifecycle.py`. NOT IMPLEMENTED.

## MC2 kernel boundary

Post-T pits exist only as forward R6 decisions (stint target → loss added
once). No driver can begin inside a pit process; all start ACTIVE and
schedule immediately. Initial pit delay = initial-condition extension +
local event-loop hold → LOCAL_KERNEL_EXTENSION (conditional; not crossed).

## RNG contract

Reserved only: `mc2-initial-pit-delay`. Frozen streams untouched.

## Finish-order semantics

No terminal classification added. Terminal branching would be general
lifecycle science → STOP (consistent with REJECT).

## Admission decision

REJECT_PIT_LIFECYCLE (firewall REJECT + DURATION_MODEL_FAILURE +
immaterial). Ten-gate evaluation recorded in `decision.json`.

## Runtime integration

NOT_APPLICABLE — no runtime modification.

## Future poison

NOT_RUN (representative-state poison required only if admitted).
Causal/future table separation + J-poison precedent preserved by
construction; scripts verified network-free and 2025-free.

## Old-state parity

NOT_APPLICABLE — 3678 eligible + dry-green `7ae97c3c` untouched (no code
change; J/K/L suites pass: 88/88).

## Newly recovered states

None (empty set by construction).

## Coverage before / after

BEFORE 3678/9644 (38.14%) → AFTER 3678/9644 (38.14%). Gain +0 / +0.00 pp.
Season/stage/race breakdowns identical to frozen V3.2L (EARLY 48.44% /
MID 39.29% / LATE 27.53%).

## Coverage attribution

`coverage_attribution.json`: all mechanisms 0; new eligible set empty.

## Coverage by season / stage / race

Identity files referencing frozen L breakdowns (before == after).

## Remaining STALE

3294 unchanged: general lifecycle 5661 offenders / J-retired 2067 /
ambiguous (stopped-cleared) 249 / pit candidate 0. General L lifecycle
not reopened.

## Performance

NOT_APPLICABLE — no runtime artifact.

## Tests

20 new M tests + 68 J/K/L contract tests pass (88/88).
FULL_TIER1 = NOT_REQUIRED_RESEARCH_ONLY (rejected/research-only, no
shared runtime/MC2 modification; final V3.2 validation runs full suite).

## Scientific identities

- M prereg `3161cf52…`, L prereg `4c3eb5c8…`, J corpus `8229a8606…`.
- `results/v3/v3_2m/` (35 files) + `results/v3/v3_2m_causal_pit_lifecycle.json`.
- Repro: `.venv/bin/python scripts/analyze_v3_2m_pit.py` then
  `scripts/build_v3_2m_results.py`.

## Known limitations

- L PIT_CONTEXT inherits the track-code/token mismatch (red-flag leakage).
- TimingAppData stream audit deferred (D9 tyre proxy used causally).
- Duration evidence N=14; folds ≤1 eval.
- 48 stopped-cleared InPit-True rows remain ambiguous (not hold states).

## V3.2N recommendation

Do not pursue pit-lifecycle recovery further (opportunity is structurally
zero, not just small). Next: FINAL V3.2 validation/freeze at 3678/9644,
or a non-lifecycle recovery direction if one exists. Do not start V3.2N
inside M.
