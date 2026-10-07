# V3.2K RAW TIMING STATE RECONSTRUCTION

## Final verdict

**V3.2K COMPLETE — DIRECT STATE RECONSTRUCTION REJECTED — READY FOR V3.2L DECISION**

## Frozen baseline

- Tag `v3.1-race-dynamics`, commit `64c5af0` (HEAD matches tag; entry safety passed).
- Accumulated uncommitted V3.2A–J research only; nothing staged/committed/tagged/pushed.

## Why V3.2K exists

V3.2J relieved 1373 stale checkpoints via authoritative raw `Retired=True` (path A:
prove the driver is out at T). K investigates path B: keep the stale driver in the
field by reconstructing a sufficiently current causal state from raw timing. Central
question: for the 3294 remaining primary-STALE checkpoints, does the raw live-timing
corpus contain enough information at or before T to reconstruct the stale driver's
contemporaneous race state without future information? Measured answer: **no**.

## V3.2J inherited state

Coverage 3678/9644 (38.14%), primary STALE 3294; contracts `v3.2j-driver-status-v1`,
`v3.2j-raw-adapter-v1`, `v3.2j-presence-v2`; dry-green parity `7ae97c3c…` intact.

## Preregistration

`results/v3/v3_2k/preregistration.json`, SHA256
`567260af8072d2e1700a4d1e9ad24265fc458c838010dc8a0d27b745c6a2f22b`, frozen
2026-10-07 before any target scoring. Target = exact 3294 primary-STALE verdicts in
frozen J `coverage_after.json` (corpus hash `8229a8606…`). Trusted controls = 420
deterministic stratified pure-capable checkpoints. Admission gates with numeric
thresholds frozen before scoring (position ≥0.99, lap ≥0.99, pit ≥0.95, poison 100%,
determinism, season consistency, lapped/tyre/pace safety, winner firewall).

## Target population

3294 checkpoints; offender distribution {1:988, 2:1028, 3:751, 4:285, 5:149, 6:25,
7:42, 8:12, 9:1, 18:1, 19:12}, max 19. Offender ids parsed from frozen J reason
detail strings. `target_population.json`.

## Minimum MC2 driver state

Derived from runtime (`adapter.py`, `state.py`, `engine.py`), not intuition:
`driver_id, lap_number, race_time_s, position (nullable), compound, tyre_age
(required non-null), stint_number (nullable), pit_count (required), constructor_id,
status=ACTIVE, observation_age_s (≤ 3.0 × base pace)`. Pace selection is
circuit/season/constructor-level — no per-driver recent-form need.
`minimum_state_contract.json`.

## Raw timing sources

TimingData local for all 149 races (104 files, 547 MB, 2019–2023 + 45 sqlite-cached
2018/2024). TimingAppData/Position/CarData in sqlite for 2018+2024 only (45/86/80
streams). Zero bulk download per prereg. `raw_topic_inventory.json`.

## TimingData reconstruction

Research-only chronological reconstructor: per racing-number, per-key event lists
for Position, NumberOfLaps, GapToLeader, IntervalToPositionAhead, InPit, PitOut,
NumberOfPitStops, LastLapTime, BestLapTime, Retired, Stopped, Status, Line;
delta-persistent; causal lookup = latest `t <= T` (`bisect_right`, equality counts).
Number→driver via D9 `driver_number`. No runtime component created.

## Temporal semantics

J clock alignment reused (feed session clock shares D9 origin). Poison probes 40/40
unchanged. `future_poison.json`.

## Trusted-state validation

420 control states, ~8381 position / 8394 lap / 7187 gap / 5563 pit comparisons
against canonical RaceState reference.

## Position validation

Exact agreement 0.8551 → gate FAIL. Anatomy (8-race probe, 65 mismatches): raw
Position is FRESHER than canonical in 100% of mismatches (median 7.5s) — tower
shuffles vs older lap-crossing classification. Different observation events, not
reconstructor error. Position reconstruction NOT admitted.

## Lap-count validation

Exact agreement 0.9485 → gate FAIL. All non-exact diffs are −1 (raw behind); raw
NumberOfLaps lags canonical `observed_time_s` by median 88.2s (D9 LAP_END leads the
Lines delta). Raw lap count is a lagging indicator and cannot supply anything
fresher than D9. NOT admitted.

## Gap validation

Numeric gaps (n=6688): MAE 1.667s, median 0.585s, p90 2.746s, p95 6.79s, bias
+0.406s; 499 lap-deficit tokens preserved, never converted. Gaps are NOT MC2 inputs
(kernel anchors on `lap_number`/`race_time_s`), so this is representation-safety
only — inherently safe, scientifically irrelevant to admission.

## Lapped-driver analysis

4 lap-deficit offender rows; MC2 represents lapped drivers first-class via own
`lap_number`. Lapped representation is non-blocking by construction.

## Phase12 spatial feasibility

NOT_NEEDED (lapped non-blocking; no spatial coupling evaluated).

## Pit-state validation

Agreement 0.9412 → gate FAIL (threshold 0.95). All mismatches raw-ahead-by-one
(pit-entry vs pit-exit accounting boundary); NumberOfPitStops absent in
2020/2022/2023 seasons. Unsafe without season-uniform boundary proof. NOT admitted.

## Pace-state validation

No driver-history need (constructor/circuit-level parameters; kernel anchors on
lap_number, race_time_s, tyre_age). PASS as non-requirement.

## Tyre-state validation

TimingData carries no compound/age; causal TimingAppData exists locally only for
2018/2024 (stint schema: Compound/New/TyresNotChanged/TotalLaps/StartLaps/LapTime/
LapNumber confirmed on sample). 2019–2023 would need bulk download — not performed
per prereg. Direct reconstruction without tyre state is PARTIAL at best; required
MC2 field missing → gate FAIL.

## Activity corroboration

7977 offender rows: Stopped 5661, Retired 2067 (windowed or multi-offender residual,
never runtime evidence), fresh_TimingData 172, fresh_adjacent 6, InPit 48,
stale_only 23. Activity supports observability only; lack never implies retirement.
The stopped-not-retired mass is the V3.2L lifecycle population.

## Residual STALE decomposition

Exclusive primary over 3294 (conserved): RAW_SOURCE_STALE 2866,
LIFECYCLE_AMBIGUOUS 147, MULTIPLE_OFFENDER_MIXED 281; COMPLETE/PARTIAL 0.
Raw TimingData is equally stale for stale drivers — the staleness is real-world
(driver not crossing), not a processed-observation artifact. Hypothesis rejected.

## Driver-level decomposition

35 distinct offenders; top: ocon 518, kevin_magnussen 505, leclerc 445, sainz 418,
max_verstappen 414, stroll 406, perez 403, hulkenberg 378. A handful of recurring
drivers cause hundreds of refusals — consistent with stopped-but-unflagged cars,
not scattered source failures.

## Direct recovery candidate

Zero FULL candidates under the frozen required-state definition (every offender
complete validated causal state + all other gates). Partial-tyre states do not
satisfy the definition and are not admitted.

## Admission gates

position FAIL / lap FAIL / pit FAIL / tyre FAIL / season-consistency recorded /
poison PASS / lapped PASS / pace PASS (non-requirement) / determinism PASS.
Four load-bearing FAILs → no admission scope survives.

## Winner/top-5 firewall

Diagnostics-only join after freeze: 7977 rows checked, 6 winner-offender rows,
zero drivers removed or retired-marked by K. PASS.

## Future poison

40/40 unchanged; mechanism (bisect_right on T) makes post-T rows unreachable. PASS.

## Reconstruction decision

REJECT_DIRECT_RAW_STATE_RECONSTRUCTION: (1) tyre fields absent from TimingData;
(2) 2019–2023 TimingAppData not local, bulk download unjustified; (3) zero FULL
candidates; (4) J semantics preserved, no MC2/runtime change warranted.

## Runtime integration

NOT_APPLICABLE — no `driver_state.py` created; presence/state path untouched.

## MC2 representation boundary

No MC2 change needed or made. Lapped states representable (first-class lap_number);
no MC2_REPRESENTATION_LIMIT triggered because no state was admitted.

## Old-state parity

PASS by construction: K edits no eligibility-path code (only adds research
scripts/tests/results + CI ledger bump 3748→3760); all 3678 pre-K eligible states
preserved; J dry-green parity artifact intact.

## Newly recovered-state validation

NOT_APPLICABLE — zero new states; 500-run protocol triggers only on admission.

## Coverage before / after

BEFORE 3678/9644 (38.14%) → AFTER 3678/9644 (38.14%). Gain +0 / +0.00pp. Identity
recount re-derived from frozen J corpus hash.

## Coverage attribution

Empty new-eligible set; exact match; conservation holds trivially.

## Coverage by season

Identical before/after (no admitted recovery). MISSING_TYRE seasons: 2018: 99,
2020: 33, 2022: 33, 2023: 33.

## Coverage by stage

Identical before/after. (J: EARLY 48.44%, MID 39.29%, LATE 27.53%.)

## Coverage by race

Identical before/after. (J: ≥1 race 104, zero 45, median ~20.7%.)

## Remaining blockers

Unchanged: STALE 3294, TRACK 1165, WET 801, MISSING_DRIVER 354, MISSING_TYRE 198,
TERMINAL 154; TRACK-only 292, WET-only 176, TRACK×STALE 579, WET×STALE 579.

## Theoretical headroom

Direct 0; lapped non-blocking; tyre: 99 MISSING_TYRE in 2018 with local
TimingAppData (future experiment only); pace 0; lifecycle-uncertain 147 + 281
mixed (+5661 stopped-evidence rows); genuinely-missing 0. Upper bounds, not
admissions.

## Lifecycle-model handoff

Design-only `lifecycle_handoff.json`: P(return|state at T), P(terminal|state at T),
time-to-return; causal inputs enumerated; future labels as training targets only;
no training in K.

## API behavior

UNCHANGED: 3678 success, 5966 unsupported (422 frozen), no request-time network.

## Provenance / reproducibility

Prereg hash `567260af…` verified by every K script; deterministic (no RNG);
frozen inputs (J corpus hash `8229a8606…`); wall ~183s analysis.

## Performance

Analysis wall 182.9s (eval 173.7s); 547 MB local TimingData parsed; research-only,
zero MC2/request overhead introduced.

## Tests

12 K tests (`tests/test_v3_2k_reconstruction.py`) green; Tier-1 ledger 3748→3760.

## Scientific identities

- K preregistration: `567260af8072d2e1700a4d1e9ad24265fc458c838010dc8a0d27b745c6a2f22b`
- J parent corpus: `8229a8606d5331338607dfd4a117a58369534325e0444a3052815299137c6f30`
- J dry-green parity: `7ae97c3c8575679a`
- Decision: `REJECT_DIRECT_RAW_STATE_RECONSTRUCTION`

## Known limitations

- Offender ids parsed from frozen reason strings (format-pinned, asserted).
- TimingAppData audited on 2018 sample only; 2019–2023 tyre path unmeasured.
- Position.z/CarData.z corroboration not exercised (no admitted use-case).
- 2025 firewall intact (never read).

## V3.2L recommendation

Preregister CAUSAL DRIVER LIFECYCLE MODEL on the stopped-not-retired residual
(5661 stopped-evidence rows, 147 ambiguous + 281 mixed checkpoints): estimate
P(return)/P(terminal)/time-to-return from causal-at-T state only, with final labels
as training targets. Do NOT weaken J exclusion-only semantics or reinterpret
Stopped as Retired.
