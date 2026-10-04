# V3.1A-C1 BEHIND-RELATIONSHIP CONTRACT CORRECTION

## Final verdict

CORRECTION_D: replace the invalid v1 behind pair (+validity flag) with a
latest-observed follower gap level, its staleness companion, and its H5
trajectory; keep the laps geometry under a renamed follower feature.
Contract bumped v3.1a-v1 -> v3.1a-v2. V3.1B repaired and complete.
26 CORE + 3 VARIANT membership changed; counts unchanged for scientific
reasons, not symmetry preservation.

## Trigger

V3.1B construction measured across the full 189,420-state corpus:
`dyn_gap_behind_seconds` 3 valid / 189,420; `dyn_gap_behind_slope_l5`
0 valid / 189,420. The behind relationship contracted in V3.1A as a mirror
of the ahead relationship does not form a usable feature. V3.1B correctly
refused to consume future follower crossings and blocked.

## Superseded contract

v3.1a-v1, SHA `cc63a548eaf493383df03c4341cbd85678b9eb64303194652718b1bcf2632b77`.
Preserved as superseded; never rewritten.

## Independent reproduction

Independent cohort-grouped snapshot audit (no V3.1B calculator imports)
over all 189,420 states. Target at T; successor (pos+1 latest <= T) vs
predecessor (pos-1 latest <= T):

| side | same lap | one lap behind/ahead | two+ | none/ambiguous |
|---|---|---|---|---|
| successor/follower | 4 | 151,094 | 2,419 | 35,903 |
| predecessor/ahead | 171,565 | ~0 / 301* | ~0 | ~17,500 |

\* 301 `pred_ahead_lap` (predecessor observed lap ahead, pit-cycle skew);
leaders excluded from predecessor counts (10,662).

V3.1B reported 3 / 151,094 / 171,563. Deltas of 1-2 rows come only from
exact same-T tie handling (sequential vs cohort-grouped sweep); the
substance is identical: behind same-lap ~0.002%, ahead same-lap ~90.6%.

## Crossing-time asymmetry

For a target crossing at T, the target has just established its lap-N
state. The predecessor normally crossed lap N earlier, so its lap-N
timing is historical at T. The follower normally has not crossed lap N
yet, so its lap-N timing lies in the future. Real example (2018-r01-R,
raikkonen lap 2, T=613.906, pos 2):

- predecessor hamilton crossed lap 2 at 612.664 (1.242 s earlier) ->
  ahead gap 1.242 s, VALID.
- successor vettel latest <= T: lap 1 at F=524.360 (diff 1) ->
  same-lap behind seconds NULL (correctly).
- last observed gap: at F, raikkonen's latest was lap 1 at 523.640
  (same lap as F, predecessor check passes) -> 524.360 - 523.640 =
  0.72 s, stale 89.546 s at T.
- vettel's eventual lap-2 crossing at 614.922 lies 1.016 s AFTER T;
  consuming it would be future leakage.

## Why this is not ordinary missing data

The missingness is structural and directional: it holds for ~80% of
states in every season and stage, by the clock geometry of ordered
crossings. No larger sample, better sensor, or imputation fixes it; only
waiting for the future crossing would fill it, which causality forbids.
The correct response is a different, causally valid concept, not a
tolerance for the invalid one.

## Invalid v1 features

- `dyn_gap_behind_seconds`: INVALID_CAUSALLY. Same-lap-at-T interval is
  unobservable by construction (3/189,420). The three values are causal
  but the concept cannot form a feature. Removed.
- `dyn_gap_behind_slope_l5`: INVALID_CAUSALLY. All-NaN (0/189,420);
  trajectory over a base series that never forms. Removed.
- `dyn_gap_behind_seconds_valid`: VALID_BUT_DEGENERATE under v1
  (near-constant False); redundant under v2 since presence/geometry is
  carried by lap-diff non-null. Removed per the missingness contract
  (no per-reason flags).
- `dyn_gap_behind_laps`: VALID (causal, 81.05% coverage). Kept with
  unchanged definition, renamed `dyn_follower_lap_diff`.

## Information available at T

- follower identity from synchronized order: AVAILABLE_AT_T (81.05%).
- follower latest completed crossing (lap Fl, time F <= T):
  AVAILABLE_AT_T whenever identity resolves.
- T, lap difference N - Fl: AVAILABLE_AT_T.
- last causally observed gap F - T_at_F (strict check): AVAILABLE_AT_T
  (71.91%).
- staleness T - F: AVAILABLE_AT_T iff level finite.
- same-lap follower seconds at T: NOT_AVAILABLE_AT_T (~0.002%).
- follower current-lap pace / projected crossing: NOT_AVAILABLE_AT_T
  (future; forecasting forbidden).
- relative pace vs follower from frozen medians:
  CONDITIONALLY_AVAILABLE but stale-mixed; rejected as redundant with
  the last-gap slope.

## Candidate alternatives

Evaluated: follower observation age (level + H5 slope), last observed
gap (+ staleness + H5 slope), relative-pace trajectory overlap, traffic
overlap, presence/validity indicator, removal without replacement.

## Observation-age analysis

Age = T - F has 81.05% coverage (finite whenever the successor
resolves), median 84.1 s, stable across seasons (81.8-85.8 s) and stages.
But age = follower lap time minus true gap (diff-1 regime): a 2 s-close
follower on a 120 s SC lap and a distant follower on a fast lap can share
the same age. Small age marks a FAR follower; large age marks a CLOSE
one or a pit/SC lap. It is NOT a gap and must never be named one. For
diff >= 2 (lapped traffic, 2,419 rows, ages up to 7,751 s) it is pure
lap-difference bookkeeping with no competitive meaning. REJECTED as a
gap replacement; ACCEPTED only as staleness provenance for the last-gap
level, where lap-time scale is exactly the honest "how old" reading.

## Last-observed-gap analysis

Level F - T_at_F (>= 0): finite 136,199/189,420 = 71.91% under the
strict predecessor check (target is the follower's unique predecessor at
F; same observed lap; non-red; both timings available). Without the
strict check 79.35%; the check costs ~7.4 points and removes
third-car-contaminated intervals. Median 2.52 s (p05 0.54, p95 21.03,
p99 44.76; max 1,524 s red/lapped extremes, honestly retained).
Coverage stable: seasons 69.5-73.7%, EARLY 68.8 / MID 68.7 / LATE 78.4,
green 73.7 vs neutralised 55.4. H5 same-follower same-regime slope:
96,126/189,420 = 50.75%, median 0.075 s/lap, sign convention negative =
closing (matches ahead slopes). Staleness median 83.5 s (~one lap).

## Relative-pace overlap

No overlap. Contracted relative trajectories are target-vs-predecessor
(`dyn_relpace_ahead_change_l5`) and target-vs-field median; no
follower-relative trajectory exists. The last-gap slope is the only
follower-relative trajectory and uses direct gap semantics rather than
median-pace levels.

## Traffic overlap

No overlap. `in_traffic_2s` is ahead-gap-only (valid same-lap ahead gap
<= 2.0 s); the follower almost never shares the observed lap at T, so
follower pressure is invisible to the traffic band by construction.
`nearby_cars_within_5s` likewise requires same observed lap. The
follower descriptor adds strictly new information.

## Selected correction

CORRECTION_D (evidence-supported minimal representation):

- ADD `dyn_follower_gap_last_seconds` (level, seconds).
- ADD `dyn_follower_gap_last_age_s` (staleness, seconds).
- ADD `dyn_follower_gap_slope_l5` (trajectory, s/lap, negative = closing).
- RENAME `dyn_gap_behind_laps` -> `dyn_follower_lap_diff` (def unchanged).
- DROP `dyn_gap_behind_seconds`, `dyn_gap_behind_seconds_valid`,
  `dyn_gap_behind_slope_l5`.

Rejected: age-as-gap, age slope (confounded level, flipped sign),
future-crossing interpolation (forecast), spatial workaround
(firewall), count-preserving keep of the invalid pair.

## Corrected mathematical definitions

Let T = target state time, N = target lap, S = unique successor at T
(pos+1 holder in the <= T snapshot), (F, Fl) = S's latest observation
(F <= T). Let T_at_F = target's latest observation time <= F (own
collapsed history) with lap tL.

- Level: lg = F - T_at_F iff S known AND predecessor(S at F) == target
  AND tL == Fl AND neither side red AND both timings finite; else null.
  Units seconds, >= 0. Levels exempt from pit/neutralisation masking
  (own geometric gating).
- Staleness: age = T - F iff lg finite; else null. Seconds.
- Lap diff: d = N - Fl iff S known; else null. Integer laps
  (1 typical; 0 equal; >= 2 lapped).
- Slope_l5: OLS over x = target lap numbers of trailing (same S,
  same d, usable target laps, finite lg) points within [N-5, N],
  >= 2 points spanning >= 1 lap; else null. s/lap, negative = closing.
  Uniform target-side masking (pit in/out, non-all_clear break runs).

## Feature names / dtypes / units

| feature | dtype | unit | null |
|---|---|---|---|
| dyn_follower_gap_last_seconds | float64 | seconds | yes |
| dyn_follower_gap_last_age_s | float64 | seconds | yes |
| dyn_follower_lap_diff | int64 | laps | yes |
| dyn_follower_gap_slope_l5 | float64 | seconds_per_lap | yes |

Statistic vocabulary extended with `level` and `age` (F6 age convention).

## Feature-set membership

CORE 26 (unchanged count, changed membership: -3 v1 behind, +3
follower, 1 rename). VARIANT_A 3 unchanged. FULL 29. PLUS_CORE 110,
PLUS_FULL 113. ALL_84 = 84 untouched; combined sets remain separate.

## Complexity change

Zero net count change, for scientific reasons: the follower side keeps
one level + one staleness companion + one trajectory + one geometry
companion, mirroring the information shape (not the values) of the other
gap domains. No preservation rule was applied; 25 CORE was considered
(dropping the geometry companion) and rejected because lapped-vs-lead-lap
follower regime is not carried by the level (null for laps-apart).

## Pit / neutralisation behavior

Frozen V3.1A policies unchanged. Levels carry geometric gating (red ->
null on either side; pit laps produce factual crossings and are NOT
nulled at level). Trajectories use uniform target-side masking; pit
in/out and non-all_clear target laps break follower runs. Follower-side
pit distortion inside a run (inflated source crossing) is a documented
limitation: it is one lap inside an H5 OLS, usually terminated anyway by
successor re-resolution when the stop costs track position.

## Early-history / missingness

Lap 1: levels null (no own history at-or-before F); lap diff defined
whenever the successor resolves. Missing reasons collapse to one null
state per the frozen missingness contract (+ universal depth
`dyn_hist_laps_available`). Null sources: no successor (17.5%),
ambiguous successor (1.3%), unknown position, predecessor-check failure
(7.4%), laps-apart at F (1.4%), red (0.3%), target unobserved at F
(~0.02%).

## Crossing-boundary invariant

Permanent regression `test_follower_crossing_boundary_invariant`:
target crosses lap 6 at T with follower uncrossed; adding the follower
crossing at T+eps leaves feature(T) bit-identical; the lap-7 state then
honestly consumes it (level 0.5 s, age 1.5 s). Assembly looks strictly
backwards (own history <= F, window <= N); sweep provenance for rows
at-or-before T is invariant to strictly-after-T row mutations
(`test_sweep_follower_provenance_future_poison`).

## Leakage tests

Full future-poison suite re-green: future-row, future-lap, comparator,
pit-outcome, status, field-membership, result, window-boundary,
same-time-ordering, early-history, pit/status boundaries, cross-driver
poison, cross-driver identity history, sweep poison -- plus four new
follower-specific tests (boundary, future-follower poison, overtake
identity, sweep provenance poison). Mutations strictly after T leave
feature(T) unchanged in every case.

## Season / stage coverage

Last-gap level: 2018 72.7, 2019 72.5, 2020 69.8, 2021 73.5, 2022 69.9,
2023 69.5, 2024 72.9, 2025 73.7 (%). EARLY 68.8 / MID 68.7 / LATE 78.4.
Lap diff non-null 81.05% every season. Slope 50.75%. No pathological
column; no season proxy (uniform missingness treatment).

## Distribution sanity

Level s: min 0.00, p01 0.30, median 2.52, p95 21.03, p99 44.76, max
1,524.65 (genuine seconds). Age s: median 83.5, p05 60.9, p95 112.7,
max 7,199.9 (red/lapped tail). Slope s/lap: median 0.075, p01 -2.156,
p99 3.764, extremes -41.9/+72.8 (SC/pit edge windows; no winsorization
per frozen outlier policy). Lap diff: 1 x 151,094; 0 x 3; >= 2 x 2,419;
null x 35,904.

## Corrected contract identity

v3.1a-v2, SHA `abd5300816d79270b1cd5b9b4952ebe447817f770eeddd2c598d0f07fbd5a0a4`
(canonical semantic JSON, sorted keys, compact separators). Supersedes
v3.1a-v1 `cc63a548eaf493383df03c4341cbd85678b9eb64303194652718b1bcf2632b77`.

## V3.1B impact

V3.1B implementation repaired to v2 (sweep provenance + assembly
last-gap; invalid behind code removed). Blocked artifact rebuilt:
189,420 rows x 29 features, logical SHA
`40ef05809e2932d725785a0e991bcecede8d884f2388affec3f56147611696a1`,
deterministic across rebuilds, join-exact both directions. The two red
artifact tests became meaningful corrected-contract tests and pass.
V3.1B is complete; see `docs/V3_1B_RACE_DYNAMICS_CONSTRUCTION.md`.

## Scientific identities

6/6 exact without regeneration: serving
`1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`,
content `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`,
parquet `b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3`,
explainability
`bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f`,
replay `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298`,
simulation `r3-v1` through 2024 `phase6-r3-empirical`.

## Known limitations

- Last-gap staleness ~one lap (median 83.5 s); a full lap of racing can
  change the battle after measurement. Staleness is explicit, not hidden.
- Follower-side pit/SC distortion inside slope runs (see Pit section).
- Same-T dead-heat ties inherit sweep input-order dependence (4 rows
  corpus-wide); directionally immaterial.
- Lap-1 states carry no level (honest null, not zero-fill).
- No 2025 performance inspected; no model trained; frozen artifacts
  untouched.

## Entry gate

Baseline exact (HEAD = phase12-spatial-replay = e99a78f8; V3-0/V3.1A/
blocked-V3.1B work preserved, nothing discarded); asymmetry reproduced
independently; clock cause demonstrated with exact timestamps; invalid
v1 features classified; follower information inventoried; age semantics
and trajectory stability investigated with synthetic + real evidence;
last-gap alternative measured (strict 71.91%); relative-pace and traffic
overlap ruled out by construction audit; no future-crossing estimate;
no spatial workaround; count not preserved by rule (26 kept on
evidence); one strategy (CORRECTION_D) selected; features causally
defined with frozen names/dtypes/units; boundary test implemented;
poison/overtake/pit suites green; coverages acceptable; distributions
sane; contract v3.1a-v2 with recorded hashes; docs + machine record
created; v1 history intact; V3.1B repaired post-freeze; artifact rebuilt
deterministically; ALL_84 = 84; identities 6/6; no training/predictions/
2025 inspection/regeneration; CI manifests verified no-op; graphify
direction clean; zero UNKNOWN; nothing staged/committed/tagged/pushed;
V3.1C not started.
