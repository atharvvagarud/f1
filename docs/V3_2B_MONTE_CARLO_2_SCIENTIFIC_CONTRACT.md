# V3.2B MONTE CARLO 2.0 SCIENTIFIC CONTRACT

Contract stage. This document freezes what MC2.0 may consume, support,
improve, and promise — before any simulator change. No kernel, parameter,
artifact, strategy, serving, or frontend code was modified or built.

## Final verdict

V3.2B COMPLETE — READY FOR V3.2C (scope handed off below; V3.2C not started).

## Frozen baseline

`v3.1-race-dynamics` = `64c5af0`, HEAD identical. V3.2A complete with four
uncommitted audit files intact. Simulation identity `r3-v1` through 2024
`phase6-r3-empirical`; replay 149/9644; capable 2274/9644 (23.6%).

## V3.2A inheritance

V3.2A reconstructed one-run semantics, the 16-entry input contract, the
supported output set, PCG64 determinism (chunk-invariant), circuit
conditioning without hardcoding, the ML/MC firewall, and the refusal
counts this contract resolves: STALE_ROSTER 4590, TRACK_STATE 1138,
WET 801, MISSING_DRIVER 492, MISSING_TYRE 198, TERMINAL 151.

## STALE_ROSTER root cause

Independent decomposition of all 4590 stale checkpoints (9801 offender
records, mean 2.1/state) against diagnostic future evidence (later D9
rows, final DNF flags — diagnosis only, never contract inputs):

- 9394/9801 offenders (95.8%) never produce another lap row: terminal
  absence. 9376 of them are factual DNFs.
- 407/9801 (4.2%) produce later rows: transient absence (garage repairs,
  red-flag clock artifacts, timing gaps). 55 such records finished top-5,
  including 6 eventual race winners (e.g. Monza/Mugello 2020 red-flag
  races). Excluding them would drop live contenders — catastrophically.
- 4379/4590 states (95.4%) are all-terminal; 211 (4.6%) contain ≥1
  transient offender. Transient ages (247–4949 s) fully overlap terminal
  ages (210–10233 s): age alone cannot separate them.
- The only positive ≤T signal, race-control "CAR X STOPPED", has 12.5%
  offender recall and collapses by season (33% 2018 → 0% 2023: later feeds
  report only "OFF TRACK AND CONTINUED"-style non-terminal events). It is
  a feed artifact, not a stable contract basis.
- 42% (sampled) of terminal no-signal offenders end with a pit_in on
  their last row (garage retirement) — a causal, cross-season-stable
  candidate signal for V3.2C to measure, not a frozen rule.

Roster semantics confirmed: replay/RaceState exposes the full entry list;
the adapter requires every member observed ≤T; the engine requires every
member contemporaneous. The mismatch is absence, and absence at T cannot
prove retirement.

## Retirement causality

No causal at-T retirement signal exists in the system by construction:
RaceState forbids DNF-shaped names; D9 carries no per-lap retirement
column (`source_unit_status` is uniformly `complete`); results/DNF flags
are post-race oracle. At T, all the system observes is absence.

- A driver retired before T: retirement was observable at T only as
  absence (+ sometimes an RC STOPPED message). The cause is not in evidence.
- A driver retiring after T: their later retirement is invisible at T —
  pinned by test (`test_t1_active_despite_later_factual_retirement`:
  grosjean active at lap 2 despite a factual lap-1 crash DNF).
- Poisoning final classification leaves all at-T presence inputs
  byte-identical (tested).

## Active field contract

Frozen presence levels (`raceintel/simulation/field_contract.py`,
`mc2-field-v1`, identity `713d6e4d…2691`):

- ACTIVE — observed within bound; always simulated.
- EXCLUDE_DNS_PRE_RACE — never observed AND no qualifying/grid slot
  (pre-race fact, never final classification). Only safe exclusion frozen.
- EXCLUDE_SIGNALED_STALE — stale AND RC STOPPED ≤T AND ≥2 laps behind:
  candidate rule with measured 90% state precision; NOT frozen for use
  until V3.2E validates no calibration harm.
- STALE_UNRESOLVED — refused (status quo).
- UNOBSERVED_PRE_FIRST — refused (lap-1 boundary; drivers are active).
- UNOBSERVED_DATA_GAP — refused (a started driver with zero telemetry,
  e.g. 2022-r02 tsunoda, must never be dropped).

Lapped, in-pit, and temporarily-gapped-but-fresh drivers are ACTIVE.
Nobody disappears because of a future result.

## Retirement boundary invariant

T1 (before knowable): driver MUST remain ACTIVE — enforced even against
poisoned future truth. T2 (after): exclusion only via the frozen levels
above. Permanent tests pin both directions.

## Projected coverage

Contract-only recalculation (no source changed; PROJECTED_ELIGIBILITY,
not actual coverage):

- Current: 2274/9644 (23.6%).
- DNS no-grid exclusion (sole frozen rule): +138 → 2412/9644 (25.0%),
  recovering 2021-r22 and 2023-r15 (2022-r02 stays refused: tsunoda gap).
- Tyre backfill candidate: bounded ≤+166 → ≤26.7%, pending V3.2C proof.
- Stale exclusion: +0 frozen. HYPOTHETICAL ceiling (future-informed,
  all-terminal states): 6653/9644 (69.0%) — headroom illustration only,
  not contract-reachable. Best ≤T candidate (signaled-stale): 364 states
  at 90% precision, season-unstable — deferred to V3.2C measurement.

Sobering and honest: legitimate headroom in current evidence is small.
Larger gains need new empirical programs (neutralisation, wet), not
weaker safety.

## STALE_ROSTER decision

MIXED: STALE_TERMINAL (95.4% of stale states, in-principle excludable,
identification unproven at T) vs STALE_TRANSIENT (4.6%, must stay
refused — contains eventual winners). V3.2C scope is exactly this split:
measure positive-signal rules (garage pit-in-without-return, combined
absence+laps-down guards) or keep refusal.

## Track-state policy

1138 refusals: yellow 508, SC 363, VSC 120, VSC_ending 65, null 64,
red 18. DRY_GREEN stays the sole initial support. Null stays INVALID
(never assume green). Red stays refused (restart = new race, no model).
Yellow/VSC/SC/VSC_ending: DEFERRED — admitting them needs a
neutralisation evolution model (bunching, unlapping, restart deltas)
that does not exist; coverage must not buy them without it.

## Wet-state policy

DEFER_WET. 801 refusals split: rain-falling (347, incl. 164 on slicks),
wet compounds without current rainfall (454, drying track). Current wet
condition is observable (wx_rainfall, compounds) but no wet pace family
or wet residual distribution exists — supporting wet means inventing
pace. Future weather evolution is separately out of scope regardless.

## Missing-driver policy

492 states: 155 lap-1 boundary (active drivers, refused); 196 DNS
no-grid records (196 → 138 recoverable states across the two clean
races); 202 data-gap records (started drivers, zero telemetry: refused
permanently); 0 mid-race transient gaps. Never conflate with retirement.

## Missing-tyre policy

198 states: 166 with ≤2 null drivers (backfill candidate: carry forward
last ≤T (compound, age+laps) only across unchanged stint+pit-count —
V3.2C must prove safety, default REMAIN_REFUSAL); 18 wholesale-null
(early-2018 start tyres, truly unavailable); rest multi-null. No
forward-fill without proven-unchanged source semantics.

## Terminal-state policy

TERMINAL (151) REMAINS an intentional unavailable state: boundary
`leader_laps_done >= scheduled_laps`; nothing remains to simulate.

## Support matrix

Frozen in `field_contract.py`: DRY_GREEN=SUPPORTED_INITIAL;
DRY_YELLOW/VSC/SC, RED, WET_GREEN, WET_NEUTRALISED=DEFERRED;
TERMINAL/UNKNOWN_TRACK=INVALID. Determinism-tested, ValueError on
unknown tokens.

## Initial-state schema

MC2.0 consumes: race identity/season/round/circuit/scheduled/leader-laps/T
(race level, required); per-driver lap/clock/position/compounds/ages/
stints/pits/constructor (required except nullable tyre, refused if null
pending backfill rule); observation ages (required for eligibility);
track token + rainfall (required, gated by matrix); anchor handle
(optional); presence level per driver (V3.2C output, required then);
driver pace anchor + provenance (V3.2D output); variance-regime tags
(V3.2D output). Types mirror frozen R1 guards (plain int/float/str,
finite, no NaN).

## State vs model features

Admitted quantities come from raw RaceState/history or from reusable
causal past-only dynamics calculations (the frozen V3.1 calculators:
null-on-insufficient-history, synchronized-field geometry) — never from
classifier coefficients, importances, or scores. A large coefficient is
not a mechanism.

## V3.1 dynamics admission

Of 13 V3.2A candidates: ADMIT_NOW via PACE_ANCHOR —
`dyn_pace_slope_l3/l10` (driver-specific current pace). ADMIT_CONDITIONAL
(pending the named V3.2D mechanism + parameter family, else DEFER) —
gap slopes/diff (`INTERACTION_REGIME` overtake pressure),
`dyn_field_spread_change_l5` + pace/gap vols (`VARIANCE_REGIME`
conditioning), traffic frac/n + follower slope (`INTERACTION_REGIME`
exposure/pressure). EXCLUDE — all 5 REDUNDANT (outcome-derived/counts)
and 8 MODEL_ONLY (pit flags, relpace deltas, absolute spread, follower
snapshots: descriptors without stochastic role), plus 3 unjustified
variants.

## ML firewall

MC2.0 must never call the winner classifier: forbidden as pace input,
overtaking weight, terminal selector, or renormalization source.
Simulation stays independently interpretable end-to-end (tested: no
model tokens in runtime sources).

## Pace contract

`mu = base(circuit|era) + constructor_offset + driver_anchor +
progress_slope·(l−T) + degradation_slope·(clamped age − anchor age) +
traffic_penalty·regime(T)`. New terms (anchor, traffic) arrive with
their own versioned parameter families in V3.2D; coefficients are not
set here. Stint context enters only via the existing factual age anchor.

## Driver-specific anchor

Today drivers differ only by constructor offset + tyre-age anchor: same-
constructor teammates share pace. MC2.0 anchor contract: causal
past-only per-driver offset = robust central tendency of recent eligible
own laps relative to `base+offset` expectation, with minimum-history and
fallback-to-zero rules; exact estimator and parameters are V3.2D work.

## Variance contract

Parsimonious conditioning: `sigma(era → traffic-regime → phase)`,
era-pooled global fallback, mirroring R3 fallback discipline; stint-age
and neutralisation conditioning deferred. No fitting now.

## Autocorrelation contract

ADMIT AR(1) to V3.2D scope: justification lag-1 ≈0.264 + 6–22% width
mismatch; causal input = the trajectory's own previous residual only;
stability |φ|<1 enforced by construction; latent state rides the
existing per-(seed,index) stream under a NEW domain word (pace stream
bit-stable); chunk/scalar parity required before acceptance.

## Traffic / interaction contract

Minimal legitimate mechanism: traffic-dependent pace penalty —
expected time cost while in a factual traffic regime
(`in_traffic_2s`-style geometry exists at T), estimated as an empirical
family in V3.2D. No per-driver constants invented; no threshold without
evidence.

## Overtake boundary

V3.2 does NOT simulate explicit overtakes: evidence insufficient
(R6-O/P/Q confounding stands), terminal ordering stays pace-derived.
Visual appeal is not a mechanism.

## Pit contract

Preserve R6 semantics exactly: observed stint state is factual input;
future stops are stochastic behaviour draws (conditional initial target,
dry-filtered transitions, effective loss once, domain separation,
final-lap suppression). V3.2D may recalibrate the stint family against
the measured 0.3–0.4 over-pitting — mechanism repair, never strategy
optimization (Strategy 2.0 owns decisions).

## DNF boundary

DEFER future-DNF stochasticity: no validated hazard (390 observable
DNFs are unmodelled by decision, not by oversight). Hard separation:
excluding factually-retired-at-T drivers (active-field rule) IS allowed
science; predicting future retirements IS deferred.

## Neutralisation / weather boundary

No future SC/VSC/red/weather simulation in V3.2 (scope explosion,
no models). Current-condition support beyond dry-green stays refused
until an evolution model exists. Matrix documents the distinction.

## Empirical parameter contract

Every MC2.0 family requires: training seasons, conditioning variables,
minimum-sample rule, fallback hierarchy, content hash, backtest policy
(`through < target` for evaluation; retrospective through-2024 for demo).
New families: driver anchor offsets, regime-conditioned residuals,
traffic penalties, recalibrated stints (optional wet family only if
V3.2D evidences it). No global full-history leakage, ever.

## Temporal backtesting

Evaluating season Y uses parameters estimated strictly before Y under
the frozen policy; the demo/retrospective corpus uses through-2024 with
explicit retrospective labelling. Adversarial future-poisoning tests
gate every stage.

## Randomness contract

All R5/R6 guarantees preserved: explicit seeds, per-(seed,index)
streams, domain separation (new AR(1) domain), chunk/parallel
invariance, scalar/batch parity, CRN compatibility for Phase-7 pairing.
`intervention=None` byte-equivalence and result identity untouched.

## Output schema

Versioned MC2 schema keeps: winner/podium frequencies, expected finish,
position distributions, bounded sample orders, valid/invalid counts —
plus schema/state/parameter/run identities and content hash. No
DNF/event/trajectory fields until their mechanisms exist.

## Demo cache contract

Key: simulation_version + checkpoint_identity + parameter_identity +
seed_policy + n_runs. Payload: the output schema above, scientific
formatting only, no frontend shaping inside the artifact.

## Demo run-count decision policy

V3.2A's 5000 is NOT frozen. V3.2E freezes 5000/10000/other iff:
TV(5k→10k) ≤ 0.005 with top-driver stability, 95% CI width on the leader
within ±0.01, serial precompute within budget, corpus ≤ ~100 MB, and no
visual rank flicker across seeds. Otherwise 10000.

## Coverage objective

Maximize legitimate supported replay states subject to exact causal and
state-validity requirements — never a percentage target. Report overall,
season, race, stage, and reason; expose every unavailable state honestly.

## Demo behavior

SUPPORTED → cached simulation. UNSUPPORTED → exact reason (taxonomy
token, user-worded). LOCAL_ONLY only for states deliberately excluded
from public cache but locally runnable. No silent fallback, no fake
simulation.

## Local execution contract

Same request/result schema as precompute: CLI/service entry takes
(race_id, frame_index, seed, n_runs, parameter identity), returns the
versioned result schema with identities. Docker unchanged in this stage.

## R3 baseline

Frozen R3 (pits off) is the immutable comparator. Future arms: A = R3,
B = MC2.0 candidate, plus predeclared ablations only. R3 is never
mutated in place.

## Validation metrics

Frozen hierarchy from R7 conventions: winner calibration (log-loss,
Brier, top-k, ECE), order (RPS, position log-score, expected-finish
MAE, Spearman), coverage, invalid-run rate, convergence (TV), runtime.
Only mathematically valid, output-supported measures.

## Statistical unit

Race is the paired comparison unit: checkpoints within a race are
non-independent; aggregate per race, then pair R3 vs MC2.0 across races.

## Coverage vs quality

Separate axes reported jointly: more states ≠ better; stronger science
with collapsed coverage is a product limitation. Neither axis alone
decides acceptance.

## Acceptance policy

Adopt MC2.0 iff ALL hold: non-inferior calibration on shared states,
coverage non-decreasing, invalid-rate bounded, determinism/parity green,
runtime in envelope, strategy compatibility intact. Null result
(RETAIN R3) explicitly allowed. Improvement by fiat is forbidden.

## V3.2 experimental ladder

V3.2B contract (this) → V3.2C active-field + adapter/coverage repair
(state starts, no stochastic upgrades) → V3.2D pace/residual/parameter
science → V3.2E R3-vs-MC2.0 backtest → V3.2F precompute/export tooling
(post-verdict only) → V3.2G freeze. No 9644-state cache before freeze.

## V3.2C handoff

Owns: presence-level adapter, DNS exclusion, tyre-backfill rule with
proof, stale-signal measurement program (garage pit-in rule, combined
guards) or documented keep-refusal. Must NOT touch stochastic kernels.
Separates "can start" from "models better". Entry: this contract +
V3.2A evidence. Exit: measured projected coverage + boundary tests green.

## V3.2D handoff

Owns: driver anchor estimator, regime-conditioned residuals, AR(1),
traffic penalty family, stint recalibration — each with versioned
parameters and fallback discipline. No unevidenced mechanisms.

## V3.2E handoff

Owns: frozen R3-vs-MC2.0 temporal backtest, paired race evidence,
coverage/convergence/compute comparison, run-count freeze, accept/null
verdict. No cache generation before verdict.

## V3.2F handoff

Owns (post-acceptance only): reproducible precompute/export tooling,
corpus generation under the cache contract, local-execution parity.

## V3.2G handoff

Owns: docs, machine records, accepted parameters, artifact identities,
tests, Docker/local path, precompute schema, tag. No V3.3 work.

## Security / trust contract

Public/local inputs bounded: race_id ∈ manifest, frame ∈ checkpoints,
1 ≤ n_runs ≤ 10000, seed ∈ [0, 2⁶⁴−1], typed config payloads only. No
filesystem-path inputs, no code-bearing payloads, no unbounded counts.
Full audit remains Portfolio Release work.

## Scientific identities

v3.1-race-dynamics → `64c5af0…`; V2 serving `1116b34f…59f4`; Phase-2
`d2ee966c…` / `b0f17b66…`; explainability `bae84b61…`; replay
`78a3c059…98`; simulation `r3-v1` through 2024 `phase6-r3-empirical`;
V3.1 artifact `9a1aac51…f58960` (from provenance, unpromoted);
field contract `mc2-field-v1` → `713d6e4d…2691`. Verified, none
regenerated. Full values in machine record.

## Known limitations

Stale exclusion unproven at T (best ≤T rule 90% precision,
season-unstable); RC feed unsuitable as retirement evidence post-2021;
legitimate coverage headroom small (+1.4pp frozen, ≤+3pp candidate);
6 winner-cases inside the transient class; wet/neutralised need full new
empirical programs; kernel untouched so all R3 limits persist.

## Entry gate

Baseline exact · V3.2A intact · graphify-first · stale decomposed with
deterministic counts · causality traced · future-invisibility proven by
test · active-field exact · boundary invariant tested · projected
coverage measured and labelled hypothetical · MIXED decision with
subcategories · all five refusal policies frozen · matrix frozen ·
initial schema exact · no mechanism-less features · 13 candidates
individually decided · ML oracle prohibited by test · anchor/variance/
AR(1)/traffic/overtake/pit/DNF/SC-weather boundaries frozen ·
parameter versioning + backtest frozen · RNG/CRN preserved · output/cache
schemas frozen · run-count rule defined · scientific coverage objective ·
explicit demo/local behavior · R3 comparator · metric hierarchy · race
unit · coverage/quality split · null-allowed acceptance · C–G scopes
exact · input bounds noted · simulator/model/params/cache/frontend
untouched · identities exact · zero unexplained paths · nothing staged/
committed/tagged/pushed · V3.2C not started.
