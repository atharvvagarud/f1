# V3.1A RACE DYNAMICS SCIENTIFIC CONTRACT

Contract stage: freezes WHAT Race Dynamics means before V3.1B computes
anything. No feature values computed, no model trained, no 2025 dynamics
performance inspected, no frozen artifact regenerated or overwritten.

- Frozen baseline: `phase12-spatial-replay` (`e99a78f8`), worktree held.
- V3-0 parent: `docs/V3_0_SCIENTIFIC_ARCHITECTURE_BASELINE_AUDIT.md` +
  `results/v3/v3_0_scientific_architecture_baseline_audit.json` (intact).
- Contract module: `raceintel/features/dynamics/contract.py`
  (`CONTRACT_VERSION=v3.1a-v1`,
  hash `cc63a548eaf493383df03c4341cbd85678b9eb64303194652718b1bcf2632b77`).
- Graphify: no code-graph topology change at entry (12682/30309/359);
  targeted queries drove navigation (RaceIndex, F8 rates, D11 pattern).

## Final verdict

V3.1A COMPLETE — 26 CORE + 3 VARIANT dynamics contracted, windows frozen
LAP-based (3/10 + frozen 5-bridge), pit/neutralisation/early/missingness
policies frozen, arms/manifest/identity/leakage suite frozen. Ready for
V3.1B (pending review).

## Frozen baseline

Winner task (`winner`/`is_winner`/`eligible_is_winner`), ALL_84 immutable
(registry v8, 84 predictive; re-verified 84 in V3.1A tests), LogReg C=0.01
RAW independent-binary, FINAL_FIT 2018–2024 → sealed 2025 holdout
(race-macro LL 0.0680353741 etc., V3-0 record). D1/D2/D3 expanding-window
development folds unchanged. Calibration evaluation-only. Phase-12 spatial
excluded. Null result acceptable.

## V3-0 inheritance

V3.0 fixed: same winner target, frozen family, representation-first
experiment, race-macro LL primary, race paired unit, RAW calibration,
spatial exclusion. V3.0's 10-item catalogue is the input reconciled below;
its {3,5,10}×{lap,time} window grid was a proposal, not a decision —
decided here from cadence evidence.

## Candidate reconciliation

| V3-0 candidate | V3.1A status | Rationale |
|---|---|---|
| gap multi-horizon slopes | CORE_V3_1 | Absent (only 5-lap OLS exists); causal via sync≤T + same-ref runs; extra horizons carry shape; cost O(H) grouped scans |
| gap acceleration | VARIANT_A (provisional) | Second-order shape is new but noisy (needs ≥3 slope segments); test only after core slopes prove stable |
| pace volatility | CORE_V3_1 | Orthogonal to all medians/means (no spread exists); robust IQR; low contamination (eligibility-masked inputs) |
| relative-pace trajectory | CORE_V3_1 | Levels exist, trajectories don't; causal iff per-endpoint comparators (contract §Relative pace); moderate missingness (≥5 contributors both ends) |
| behind-threat dynamics | CORE_V3_1 | Entirely absent (no behind gap at all); F6-mirror geometry is proven causal machinery; null-when-last is clean |
| field compression | CORE_V3_1 | No dispersion exists; race-level broadcast from ≤T valid populations; min-5 rule prevents degenerate spreads |
| traffic persistence | CORE_V3_1 | Instant exists, persistence doesn't; fraction + explicit depth; bounded missingness (geometry-valid laps) |
| stint-age residual | VARIANT_A (provisional) | Age-conditioned view is new but confound risk (fuel/track evolution inseparable) — honest descriptive naming required; test separately |
| pit-transition indicators | CORE_V3_1 | Transition markers absent (counts only); doubles as contamination control for H3 masking; cheap boolean flags |
| neutralization-gated slopes | VARIANT_A (provisional) | Interaction form of masking; needs the base masking policy proven first (T1-vs-T2 comparison) |

Rejected: position volatility/change-counts (ordinal noise + pit/SC
discontinuities), curvature beyond slope-diff (redundant), weather-trajectory
couplings (deferred with weather), telemetry/sector shapes (no D9 source),
DRS/proximity outcomes (no source), catch-time/projections (forbidden),
full-race aggregates (future). Deferred beyond V3.1: none pending — all
non-core items above are either VARIANT_A or rejected with reason.

## ALL_84 duplication map

Per admitted feature (closest existing → new → increment): 5-lap gap
slopes → 3/10-lap slopes + l3−l10 diff + 5-lap IQR → horizon shape +
instability; 5-lap position delta → 3/10-lap deltas → short/stint-scale
momentum; median-5 pace change → 3/10-anchored changes + 5-lap IQR →
pace momentum horizons + spread; relative-pace levels → 5-lap level
deltas (per-endpoint comparators) → battle/field trajectory;
observable counts → P90−P10 spread + spread delta → compression level +
dynamics; in_traffic_2s → 5-lap traffic fraction + geometry depth →
exposure persistence; pit/stint counts → in/out flag + recent-stop flag
→ transition markers; pace_n_* → universal lap depth + gap valid-counts
→ window-scoped depth for every family. No CORE feature lacks an
incremental-information statement (pinned by contract test).

## State cadence study

Read-only measurement on frozen D9 states (189420 rows, 173 races,
2018–2025): states/race median 1061 (p05 818, p75 1251, p95 1396, min 60
partial); states/driver-race median 57 (p05 9, p95 72, max 87); exactly
1 state per (driver, lap) — zero multi-state laps; state-time deltas
median 89.7 s (p05 70.9, p95 120.3, max 7754 s red suspension); lap
quantiles p05 3 / p50 30 / p95 62; pace-eligible 84.4%; non-green 8.9%
(SC 8237, yellow 6541, VSC 1643+360, red 310); pit in/out ~3.3% each.
Stage thirds (protocol): 64016/63437/61967.

## Window unit decision

LAP-BASED PRIMARY. Evidence: one lap-end state per driver-lap makes lap
windows ≡ state-count windows for own trajectories (no overweighting
possible); deltas cluster at lap cadence; motorsport interpretation is
lap-relative (battles, stints, undercut windows); F8 precedent measured
last-5 coverage 84.0% vs 82.9% last-3. Time-based framing retained only
for environment (existing 5-min features) — no new time windows.
State-count windows coincide with lap windows here and add nothing.

## Horizon contract

H3 (tactical: battles, response), H5 (frozen bridge — reuse ALL_84
5-lap features, recompute only where no frozen counterpart: behind
slope, field/persistence/volatility statistics), H10 (stint-scale form).
Minimums: slopes ≥2 valid points spanning ≥1 lap (F8 rule inherited);
volatility/spread ≥3/5 points; endpoint deltas require both endpoints
non-null. Boundary: current_lap−H ≤ source_lap ≤ current_lap, inclusive
both ends, current observation participates.

## Temporal window semantics

Invariant: source_time ≤ T for every input (own laps, rival sync states,
weather rows, track-state rows). One value per driver lap-end state
(latest state_time_s row per (driver, lap); empirically unique, pinned
by contract). No partial-current-lap concept exists (lap-end states
only). Red-flag interruption segments windows (points excluded, runs
broken). Repeated same-lap states collapse before trajectory assembly so
OLS x (target lap) is unique.

## Observation unit

Trajectory = sequence of per-lap values, each computed at its own
historical lap-end state with that state's own causal inputs
(sync field at that T, eligibility at that lap). Never the current
row's values copied backward. Scientific reading: "the driver's
observable lap-end record over the trailing window."

## Position dynamics

Admitted: endpoint deltas at 3/10 (same anchor convention as frozen
5-lap: latest own state with lap ≤ N−H; positive = gained; never called
overtakes). No slopes (ordinal), no volatility/change-counts (pit/SC
discontinuities dominate). Interpretable momentum only.

## Gap dynamics

Minimum useful set: leader slope_l3 + slope_l10 + slope_diff_l3_l10 +
vol_l5(IQR); ahead slope_l3 + slope_l10; behind seconds + slope_l5.
All slopes OLS over trailing same-reference valid-seconds runs
(F8 `gap_rate_from_points` rule: stop at invalid/different-ref, ≥2
points, ≥1 lap span). slope_diff is the honest shape statistic (never
"curvature"). Volatility is IQR (robust, unwinsorized).

## Behind relationship

Behind(t) = unique successor (position+1 holder) from the synchronized
field at each historical state's own T. Null when: target last, no
successor observable, successor ambiguous (0 or 2+ holders), geometry
invalid (laps-apart/red). Slope runs stop at identity change (same-ref
rule). No future-stable competitor: a driver that becomes the behind-car
later never retroactively fills earlier laps. Car-behind pits/retires →
successor re-resolved per state; disappearance yields null, never
forward-fill.

## Pace dynamics

Existing: medians/means (3/5/10), strict representative, stint summaries,
confounded trend proxy, median-5 change rate. Incremental admitted:
3/10-anchored median changes (same endpoint-delta math as frozen),
5-lap IQR volatility. Sources: eligible lap_time_s only (F5 predicate:
finite, >0, no pit markers, all_clear, lap>1) — future completed laps,
post-state sectors, and ineligible laps never enter. VARIANT stint
residual defined descriptively (see Tyre/stint trajectory).

## Relative pace

Comparators: car ahead (unique predecessor at that historical state),
car behind (unique successor), field median (comparable set at that
state, ≥5 contributors, target excluded). Each historical observation
uses whoever held the relationship THEN. Retroactive T-competitor
comparison is forbidden (major trap, pinned by cross-driver tests).
Trajectory = endpoint delta of per-endpoint recomputed levels over 5
laps; null when either end lacks its comparator population.

## Field compression

Spread(T) = P90−P10 of synchronized valid-seconds leader gaps over the
valid-at-T population (min 5; null under red / below minimum). Change =
spread(T) − spread(anchor at lap ≤ N−5, that anchor's own population).
Population rule uses only drivers valid/present at each historical
state — never future finishers, never full-race cohorts.

## Traffic evolution

Admitted: 5-lap traffic fraction (in_traffic_2s true-rate) + geometry
depth count. Distinct from state: persistence vs instant (a driver
toiling for 5 laps differs from a 1-lap overlap). Kept minimal (2
features); count-trend and enter/leave timing rejected as
over-differentiation of one band.

## Tyre/stint trajectory

Frozen data cannot separate tyre ageing from fuel burn, traffic, track
evolution, neutralisation, and driver pace — so no V3.1 feature is
called degradation. CORE carries stint-scoped honest signals only via
existing features + pit-transition flags. VARIANT dyn_stint_pace_resid
is named "stint pace trajectory" (descriptive age-conditioned
residual), gated on its own evidence and wording review.

## Pit-cycle contract

H3 frozen (mask + indicators); H2 (mask-only) testable by dropping the 2
indicator features. Empirical anatomy (2023-r01-R verified): in-lap =
pit_in_s non-null (elevated time, stint unchanged); out-lap =
pit_out_s non-null (inflated time ~120 s, stint_number+1, stint_lap=1,
laps_since=0, completed+1); first clean lap = stint_lap=2 with no pit
markers. Trajectory inputs exclude in/out laps for ALL families (pace
already does via F5 eligibility; extended to gap/position/relative
point sets). Stint boundary = stint_number change (past-only). H1 raw
rejected (contaminated), H4 segmentation rejected for V3.1 (window
restart complexity unjustified before H3 evidence).

## Neutralisation contract

YELLOW/SC/VSC/VSC_ENDING: laps masked from all trajectory inputs and
break runs (pace eligibility already excludes non-all_clear; extended
to gap/position/relative). RED: segment (excluded + break runs; spread
null under red). Rationale: SC compresses gaps and nullifies pace
meaning; VSC/lap-40-type distortions verified empirically (113–114 s
laps). No per-status differential treatment in CORE (evidence first);
neutralisation LEVEL information rides the existing 5-min fractions.
VARIANT gated slope tests the T1 interaction form vs this T2 base.

## Early-race contract

Per family: slopes need ≥2 valid points + ≥1 lap span; volatility ≥3;
spreads ≥5 contributors; endpoint deltas need both endpoints; depths
always defined (0 allowed). Insufficient → null (NaN), never 0.
NaN-compatible with frozen preprocessing (numeric median / boolean mode
imputation handle NaN today, e.g. nullable in_traffic_2s precedent).
Universal depth dyn_hist_laps_available keeps missingness observable.

## Missingness contract

Reasons: short history, invalid geometry, no behind car, pit masking,
neutralisation masking, source nulls, inactive driver. Collapsed to ONE
missing state (NaN) + universal depth + family valid-counts — no
per-reason flags (explosion risk). Distinct companions exist only where
frozen pattern demands (pace_n_*) or construction needs it (gap depths,
traffic depth).

## Numerical definitions

Endpoint delta: (v_now − v_anchor)/lap_delta for rates, plain
difference for levels/spreads/counts; null unless both ends finite and
lap_delta > 0. OLS slope: closed-form over x = target lap numbers
(F8 `ols_slope_xy` convention), units s/lap, ≥2 points, ≥1 lap span,
duplicate-x impossible post-collapse, non-finite inputs excluded.
IQR/spread: linear-interpolated percentiles, no winsorization.
Fraction/count: over valid-geometry laps only. No "calculate trend"
remains unspecified — each definition names statistic, x-axis, minimums,
and finite-value rule.

## Units

positions | positions/lap (deltas reported as plain positions with
per-lap normalization where divided) | seconds, seconds/lap,
seconds_per_lap_squared (variant accel) | fraction | count | boolean.
No hidden normalization; preprocessing scales later.

## Outlier policy

No generic clipping/winsorization (extremes are signal: SC restarts,
out-laps, rain). Contamination handled semantically (masking by
eligibility/track-status/pit markers). Robust statistics (median, IQR)
chosen where tails dominate. Any V3.1C shrinkage (accel variant) is
predeclared analysis, not silent preprocessing.

## Feature names

`dyn_<domain>_<statistic>_l<H>` (horizon-free levels/flags omit `_lH`):
26 CORE + 3 VARIANT names frozen in `contract.py` (see catalogue).
Snake_case per repo style; horizons and relationships explicit in names.

## Dtypes

float64 nullable (all continuous; NaN = missing), int64 non-nullable
(depths/counts, 0 allowed), bool nullable (flags). No inference in V3.1B
(dtypes pinned per definition + contract test).

## Feature-set identities

ALL_84 untouched. V3_1_DYNAMICS_CORE (26, frozen list),
V3_1_DYNAMICS_VARIANT_A (3), V3_1_DYNAMICS = CORE ∪ VARIANT_A (29),
ALL_84_PLUS_V3_1_DYNAMICS_CORE (110),
ALL_84_PLUS_V3_1_DYNAMICS (113). No mutable lists; variants are separate
sets, never flags on one list.

## Complexity budget

CORE 26 (+31% over 84), VARIANT 3, total possible 29 (PLUS_FULL 113).
Justified: every CORE feature carries an incremental-information
statement vs ALL_84 (test-pinned); no weakly-differentiated multiples
(slopes at 2 new horizons + one shape + one spread per domain, not full
cross-products); depths/flags are companions, not signals.

## Experimental arms

A: ALL_84 + frozen LogReg C=0.01 RAW (reproduction gate). B:
ALL_84_PLUS_V3_1_DYNAMICS_CORE + identical model (primary test). C:
V3_1_DYNAMICS_CORE only + identical model (diagnostic). VARIANT_A runs
only under predeclared V3.1C promotion evidence. No C tuning, no
nonlinear models in V3.1.

## Baseline reproduction gate

Arm A through the new harness must reproduce frozen development values:
predictions within 1e-12, metrics within 1e-9 (deterministic sklearn
path permits exact identity). Else STOP + explain before B/C.

## Split contract

D1 train 2018–2021 / val 2022 (88123/23577 states); D2 2018–2022 / 2023
(111700/24422); D3 2018–2023 / 2024 (136122/26606); FINAL_FIT 2018–2024;
holdout 2025 (24 races, 26692 states). Expanding-window, TRAIN strictly
before VAL. No new random split.

## Holdout governance

2025 LOCKED for the dynamics experiment despite its historical
evaluation: V3.1B never inspects performance; V3.1C uses D1–D3 only;
all feature/horizon/treatment decisions freeze before V3.1D; V3.1D runs
one-shot 2025 of the frozen selected contract; no post-holdout tuning.

## Metric hierarchy

PRIMARY race-macro log loss; SECONDARY Brier, ROC-AUC, PR-AUC;
CALIBRATION ECE (veto/diagnostic); PRODUCT Top-1/Top-3 (synchronized
adapter, eligible denominator, k-way needs observable_field_size ≥ k);
STAGE EARLY/MID/LATE thirds of race_progress_frac. Implementations are
the existing `raceintel/model_lab/metrics.py` + `winner.py` — confirmed,
not redefined.

## Acceptance policy

Executable six-clause framework (V3-0 policy, no invented thresholds):
D1–D3 primary direction; race-level paired uncertainty (CI excludes
noise); fold consistency; Brier/discrimination non-regression; ECE
non-degradation; stage behavior (veto rule); complexity cost; 2025
one-shot consistency. Outcomes: KEEP / KEEP_WITH_LIMITATION / NULL_RESULT
/ REJECT. Null is publishable and still delivers the audited contract.

## Statistical contract

Unit = race. Paired race-level primary-metric deltas (B−A); deterministic
bootstrap seed 42, B=2000 replicates (S6 precedent), 95% CI; fold
dispersion across D1–D3 as second variance view. Never bootstrap states.
Races lacking a valid metric are excluded with counts reported.

## Stage veto

Veto iff a stage (especially EARLY) shows consistent directional
regression across D1–D3 AND the paired race-level CI excludes zero in
the bad direction. Single-fold numerical wobble is not a veto —
materiality comes from uncertainty, not an invented effect size.

## Calibration contract

RAW only. No Platt/isotonic/temperature/normalization fitting in V3.1.
ECE + reliability curves evaluated per arm; ECE degradation is veto-grade,
never calibrated away inside the experiment.

## Experiment manifest

V3.1C/D emit manifests with the frozen schema (42-field JSON schema in
machine record: identity, task/target/eligibility, feature set + names +
contract hash, dataset/split identity, model + hyperparameters + seed +
semantics, periods + holdout policy, metrics + aggregation + stages +
calibration, commit, artifacts + hashes). Rendered from evaluation JSON,
never hand-transcribed.

## Contract identity

sha256 over canonical semantic JSON (sorted keys, compact separators):
names, definitions, horizons, window semantics, pit/neutralisation/
missingness policies, dtypes, set membership. Excludes paths,
timestamps, formatting. Hash `cc63a548…b77`; V3.1B pins it; any semantic
change requires a version bump (test: mutation changes hash).

## Dataset identity

V3.1 builds on Phase-2 content `d2ee966c…`, parquet `b0f17b66…`,
matrix v1 (189420×106). Future V3.1 matrix carries parent_identity
(matrix version + content hash + state/race identity + contract hash).
Phase-2 artifacts never overwritten.

## Leakage threat model

14-threat model inherited from V3-0, instantiated per calculator:
rolling windows, future lap completion, pit outcomes, result-derived
fields, future cohorts, season aggregates, post-race stats, global
normalization, target-derived filtering, simulation outputs, spatial
artifacts, imputation scope, holdout tuning, telemetry side-channels —
each with mitigation + test ownership in the adversarial suite.

## Adversarial leakage suite

V3.1B MUST implement (D11 future-mutation pattern: mutate everything
strictly after T → feature(T) identical): future-row poison,
future-lap poison, future competitor change, future pit outcome, future
status change, future field membership, future season/race result,
window boundary (±1 lap inclusion), same-time ordering ties,
early-history minimums, pit boundary (in/out/clean), SC/VSC/red
boundary. Calculators fail closed (null) on contract violation.

## Cross-driver leakage

Dedicated contract: mutate another driver's future states after T →
target's ahead/behind/field dynamics at T unchanged; competitor identity
changes handled per historical state (no retroactive fill); field
population recomputed per endpoint from ≤T states. Tests use synthetic
two-driver frames with pinned identities.

## Season availability

Measured D9 null fractions per season: compound/stint/track_state/
lap_time/position/state_time all present every season 2018–2025;
2018 track_state 5.9% null (sparse era, handled by null paths);
2025 compound/stint ~1.8% null (same handling). No feature uses season
or behaves as a season proxy (uniform missingness treatment).

## Compute plan

189420 rows × ≤29 new columns; grouped causal scans per (race, driver)
with horizon-bounded lookback (no row×full-history scans, no per-feature
reloads). Reference costs: full fit sub-second, canonical eval ~10 s —
matrix construction dominates. Measurement plan: calculator s/race,
build wall time, D1–D3 fit+eval time, recorded in manifests.

## Repository architecture

`raceintel/features/dynamics/contract.py` (this stage),
`calculators.py` + `validation.py` in V3.1B; `tests/test_v3_race_dynamics_contract.py`
(now, 11 green). No top-level v3 package. Dependency direction:
calculators → contract (never reverse); no model/API/replay/spatial
imports in dynamics code.

## V3.1B handoff

Consume frozen contract (pin hash `cc63a548…`); implement calculators
only; build deterministic fixtures (early/SC/pit/red/rookie mirroring
F16); implement adversarial + cross-driver suites; construct new matrix
beside Phase-2 with provenance/hash; NO training; NO 2025 inspection.

## V3.1C handoff

Reproduce Arm A (gate tolerances); run B/C on D1–D3; paired race-level
comparison + B=2000 bootstrap; stage + calibration diagnostics;
freeze variant iff predeclared evidence supports; NO 2025 holdout.

## V3.1D handoff

Lock selected contract; FINAL_FIT; one-shot 2025; apply acceptance
policy → KEEP / KEEP_WITH_LIMITATION / NULL_RESULT / REJECT; freeze
artifacts/report; no post-holdout tuning.

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

Single-season holdout width; unmeasured telemetry/DNF/forecast/
qualifying ceilings; variant noise/confound risk; SC-heavy histories
thin honestly; cadence measured on D9 states (matrix inherits it).

## V3.1A-C1 correction

V3.1A-C1 (contract v3.1a-v2, SHA
`abd5300816d79270b1cd5b9b4952ebe447817f770eeddd2c598d0f07fbd5a0a4`)
supersedes the behind-relationship portion of this v1 contract. Reason:
V3.1B construction falsified the mirrored same-lap behind assumption
(behind seconds 3/189,420 finite; behind slope all-NaN) -- the follower
has generally not crossed lap N at target state T, so its same-lap
crossing lies in the future. v1 contract identity
(`cc63a548eaf493383df03c4341cbd85678b9eb64303194652718b1bcf2632b77`)
remains documented as superseded. All other v1 rationale below is
unchanged. Full record:
`docs/V3_1A_C1_BEHIND_RELATIONSHIP_CONTRACT_CORRECTION.md` +
`results/v3/v3_1a_c1_behind_relationship_correction.json`.

## Entry gate

- [x] phase12 tag exact HEAD; V3-0 two files intact; zero unexplained dirty
- [x] Graphify-first; candidates reconciled with per-item rationale
- [x] duplication map complete; cadence measured; LAP-based unit evidenced
- [x] horizons compact + predeclared; window/observation semantics exact
- [x] position/gap/behind/pace/relative/compression/traffic/tyre decisions frozen
- [x] pit/neutralisation/early/missingness frozen; no silent zero-fill
- [x] math form + units + outlier policy + names + dtypes frozen (29 defs)
- [x] sets frozen (CORE 26 / VARIANT 3); ALL_84 untouched (84 re-verified)
- [x] budget justified; A/B/C arms frozen; reproduction gate toleranced
- [x] D1/D2/D3 exact; holdout locked; hierarchy/stage/stats/calibration frozen
- [x] manifest + identity + dataset parentage frozen
- [x] 12-test adversarial + cross-driver suites specified
- [x] season coverage audited; no season proxy
- [x] compute bounded; repo locations defined; B/C/D handoffs exact
- [x] identities 6/6; no values computed; no training; no 2025 inspection
- [x] nothing staged/committed/tagged/pushed; V3.1B not started