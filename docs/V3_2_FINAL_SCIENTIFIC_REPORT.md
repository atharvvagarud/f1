# V3.2 MONTE CARLO 2.0 — FINAL SCIENTIFIC REPORT

## Final verdict

V3.2N COMPLETE — V3.2 FREEZE CANDIDATE VALIDATED — READY FOR V3.2O
(pending full Tier-1 confirmation; all non-Tier-1 gates green at doc
write; test_report.json records the final Tier-1 result).

## Scope

V3.2N is validation-only: audit A–M, transparently repair the known L
track-code/token defect, verify contracts/artifacts, recompute and
freeze the 3678-checkpoint catalogue, validate MC2-E + J integration
end-to-end (5000 runs), and decide freeze readiness. No new coverage
mechanism, no retuning, no 5000-count change, no commit/tag/push.

## Frozen parent

Tag `v3.1-race-dynamics` == HEAD `64c5af0`. Nothing staged. Dirty tree =
V3.2A–N research only.

## Stage ledger

`results/v3/v3_2n/stage_ledger.json` (13 stages A–M with verdict,
disposition, runtime/scientific/coverage effects, artifacts,
limitations). Accepted: C (DNS), D/E (MC2-E), J (+1373). Rejected:
F/H (regimes), G (processed status), K (raw reconstruction), L/M
(lifecycles). Feasibility: I.

## Accepted architecture

Historical replay state → presence/field eligibility → J status
resolver → simulation adapter → MC2-E → simulation distributions.
Graphify-verified: no model-lab, frontend, network, or future-result
coupling.

## MC2-E science

Arm E_AR1_RESIDUAL: R3 baseline + driver anchor + bounded decaying
dynamics + conditioned variance + AR1 (rho=0.264) residual process.
Traffic gated off. Dry-green only. Kernel identity pinned in
`parameter_audit.json`. Parameters: through-2019/2021/2023 era files
(12 files, unmodified, no 2025).

## Causal field contract

`mc2-field-v1` + `v3.2c-presence-v1` + `v3.2j-presence-v2`. DNS exclusion
(pre-race grid fact) + J-relieved exclusion; everything else refuses
with frozen taxonomy reasons.

## Raw TimingData status integration

Adapter `v3.2j-raw-adapter-v1` over 149 pinned TimingData.jsonStream
sources (2018–2024, 2025 absent). 149/149 artifacts validate (contract
version, raw SHA vs manifest, session, content hash).

## Retired semantics

Retired is CURRENT STATE at T (latest value ≤ T; never sticky-forever).
False/unknown prove nothing. Missing key preserves state. 13 unreliable
windows suppressed. Winner/top-5/transient firewalls pass (J artifacts;
resolver probes re-checked in N).

## Corrected lifecycle analysis

Defect: L stage-1 compared raw D9 `track_status` code against token
`'red_flag'`; canonical token is D9 `track_state`. Originals preserved;
supplementary correction under `results/v3/v3_2n/l_correction/` with own
identity. Corrected classes: CLEAN 171 (was 211), PIT_CONTEXT 181 (was
214), RED_REGIME 11, NEUTRALISED_REGIME 63 (were 0), INITIAL_UNKNOWN 41,
LATE_SESSION 9. Re-ran L procedure identically (same features, IRLS,
folds): calibration still unstable across folds, eval N still ≤31,
return-time N 26 (< 30). Sensitivity: VERDICT_UNCHANGED.

## Rejected recovery experiments

F/H regimes, G processed retirement, K raw reconstruction, L general
lifecycle, M pit lifecycle — none silently admitted; runtime contains
only C + J field logic and MC2-E dynamics.

## Final eligibility catalogue

Recomputed twice from clean process state: 9644 checkpoints →
eligible 3678 / ineligible 5966 (38.14%), corpus hash
`368ec94f90ac…`, identical across passes. Set-equals frozen J
`coverage_after.json` eligibility exactly.

## Coverage

3678/9644 (38.14%); +1373 (+14.24 pp) vs pre-J 2305; ~59.6% relative
growth. ≥1 supported: 104 races; zero: 45; ≥50%: 56; ≥75%: 40;
≥95%: 17; full: 0.

## Coverage by season

Recomputed in `coverage_by_season.json` (2018–2024; do not rely on
copied J values).

## Coverage by stage

EARLY 48.44% / MID 39.29% / LATE 27.53% (recomputed).

## Coverage by race

`coverage_by_race.json` with the headline counts above.

## Remaining blockers

Primary (mutually accountable over 5966 refused): STALE 3294 / TRACK
1165 / WET 801 / MISSING_DRIVER 354 / MISSING_TYRE 198 / TERMINAL 154.
All-blocker intersections in `final_blockers.json`.

## Temporal safety

Representative poison (drop all post-T D9 rows): eligibility(T),
status(T), initial state(T) unchanged on pre-J, J-relieved, and refused
states. Status prefix-closure re-verified. Scripts AST-checked
network-free.

## Winner/top-5 firewalls

J firewall artifacts frozen and green; N re-probed mandatory cases
(Vettel 2018-r02, Bottas 2020-r01, Verstappen 2022-r18, Perez 2021-r06)
at resolver level + all Retired=True-event winners documented.

## Simulation semantics

MC2-E research loop mirrors R4 ordering (earliest next-completion
first, driver tie-break; final order by finish time). R6 pit dynamics
on the production path; no DNF/weather/SC generation. Outputs:
winner/podium frequencies, expected finish, position distributions,
sample orders, valid counts.

## 5000-run validation

Frozen 21-checkpoint corpus (7 seasons × 3 stages; 11 relieved / 10
pre-J; frozen BEFORE scoring). MC2-E at 5000 runs: 21/21 checkpoints
valid=5000/invalid=0, winner mass = 1, distributions normalized,
expected finish finite, field identities preserved, no NaN/inf.
475 runs/s (8 workers); ~10.5 s per 5000-checkpoint.

## Determinism

Fresh-process rerun of 4-checkpoint subset: bit-identical in stored
representation (int-key normalization, same convention as F parity
test). Corpus hash pinned.

## Convergence

100/500/1000/5000 winner-frequency TV on 6 states: TV(1000,5000) ≤
TV(100,5000) everywhere (0.0018–0.0442); confirms, not re-selects, 5000.

## Scientific evaluation

Frozen E headlines reproduced exactly: A−E log-loss +0.696, CI95
[+0.236, +1.210], podium Brier +0.0058, top1 0.567→0.624, ECE
0.202→0.113, all stage deltas positive, verdict KEEP_MC2_E. No new
model selection.

## API behavior

Eligible + J-relieved (with status resolver wired): 200 success.
Unsupported (all six blocker classes): 422 `simulation_unsupported`
with frozen reason. No fallback, no request-time network/raw-parse/
future access.

## Replay integration

Replay frame ↔ request anchor ↔ RaceState agree (state_time_s sync) on
pre-J and relieved representatives. No off-by-one.

## Failure behavior

Explicit refusal per blocker class (STALE/TRACK/WET/MISSING_DRIVER/
MISSING_TYRE/TERMINAL). No silent fallback, no fabricated simulation.

## Performance

Measured: 21 × 5000 MC2-E runs in 221 s wall (8 workers). Environment
recorded in `performance.json`.

## Precompute planning

3678 × 5000: ~10.8 serial-hours; ~3.2 h at 4 workers (0.85 eff.);
~1.8 h at 8 workers (0.75 eff.). Planning only; no full cache in N.

## Demo artifact contract

Future cache entries must carry race/checkpoint identity, state_time_s,
runs=5000, seed policy, MC2 + parameter + eligibility/status +
RaceState identities, output hash. Contract only.

## Trust boundaries

Raw data (SHA-verified) → derived status (version-gated) → API inputs
(validated) → frozen parameters → content-hashed outputs. Portfolio
Release security audit still required.

## Reproducibility

`reproducibility.json` lists exact commands (ledger, correction,
eligibility ~11 min, status, science/poison, API, 5000-run, focused +
Tier-1 tests, corpus tests, graphify). No hidden steps.

## Tests

24 focused N tests + J/MC2/presence/parity/API suites green before
Tier-1. Full Tier-1 run once (see test_report.json). Corpus-dependent
Tier-3 per manifest.

## Artifact identities

Ledger + `artifact_identity_audit.json` (14 checks, all match); J
corpus `8229a8606…`; dry-green `7ae97c3c…`; final eligibility
`368ec94f90ac…`; K/L/M preregs verified in stage conventions.

## Known limitations

L defect corrected supplementarily; 48 stopped-cleared InPit-True rows
ambiguous; duration evidence small-N; no DNF/weather/SC simulation;
45 zero-support races; LATE 27.53%; no full-coverage race; precompute
efficiency assumed.

## Freeze recommendation

FREEZE CANDIDATE subject to Tier-1 green (recorded in
`freeze_readiness.json` + `test_report.json`). No commit/tag/push in N.
