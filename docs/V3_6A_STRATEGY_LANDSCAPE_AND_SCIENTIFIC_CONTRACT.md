# V3.6A STRATEGY LANDSCAPE + SCIENTIFIC CONTRACT

## Final verdict

**V3.6A COMPLETE — STRATEGY CONTRACT FROZEN — READY FOR V3.6B** (pending focused-test gate).

Headline finding: frozen Phase 7 is not primitive. It already implements paired
CRN strategy comparison with uncertainty, objectives, eligibility discipline,
API, and frontend. Strategy 2.0's defensible delta is therefore narrow: rebase
the intervention seam onto frozen MC2-E semantics, widen the paired outcome
vector, adopt 5000 paired futures, and freeze the comparison/eligibility
contracts — while keeping V3.5 strictly out of computation (consistency-signal
role only). No implementation was done in V3.6A.

## Frozen parent

- Tag: `v3.5-outcome-distribution`
- Commit: `6df5d41d3ebead9a1c9b4f0f40ed20a21ce0bff1`
- Entry verified: `HEAD == v3.5-outcome-distribution^{commit}`, working tree
  clean, nothing staged. Prior tags intact (`v2-final`,
  `post-v2-clean-baseline`, `phase12-spatial-replay`, `v3.1-race-dynamics`,
  `v3.2-monte-carlo-2`, `v3.3-multi-model-lab`, `v3.4-ensemble`,
  `v3.5-outcome-distribution`).

## Repository entry state

- `git rev-parse HEAD` = `6df5d41…0bff1`; `git status --short` empty;
  `git diff --cached --stat` empty at entry.

## Graphify

- `graphify update .` at entry: no topology changes; **16272 nodes / 37044
  edges / 475 communities** (matches `v3_5_freeze.json` graphify_final).
- Targeted subagent audits (Phase 7 / MC2 / V3.5+API+UI) used before broad
  source reads, per navigation policy.

## Scientific question

Frozen wording:

> "Given a causal race state at decision time T, how do plausible strategy
> interventions change the simulated distribution of future race outcomes
> under paired stochastic futures?"

Causal/interventional framing; no claim to observed historical optimal
strategy; no "best strategy" language; preserves uncertainty; answerable by
paired MC2.

## Phase 7 strategy audit

Modules (`raceintel/strategy/`, freeze `v2-strategy-engine-phase7`,
manifest `docs/PHASE7_STRATEGY_FREEZE_MANIFEST.json`):

| Capability | Phase 7 behavior | Keep | Replace | Extend | Unknown |
|---|---|---|---|---|---|
| Decision question | Valid intervention + paired counterfactual comparison from exact factual state at T | KEEP | | | |
| Actions | STAY_OUT, PIT_NOW, PIT_NEXT_LAP × {SAMPLED,SOFT,MEDIUM,HARD}; canonical 9 | KEEP | | | |
| Timing/horizon | Single decision at L_T / L_T+1(+2); then frozen mechanics | KEEP | | | |
| Tyre assumptions | Sampled or explicit; age reset 0 on forced stop; NO compound pace delta | KEEP (+disclose) | | | |
| Pit assumptions | R6 dynamics; frozen draw order compound→loss→stint; SUPERSEDED/inert/race-end-cancelled tracked | KEEP | | | |
| Driver/field scope | Single target driver; full field simulated | KEEP | | | |
| Simulator | Frozen Phase-6 MonteCarloEngine r5+r6 (pre-MC2-E) | | | EXTEND (MC2-E rebase in V3.6C) | |
| Simulation count | Product 100–10000, default 1000 | | | EXTEND (5000 paired default) | |
| Seeding/CRN | CRN_ADOPTED_WITH_LIMITATIONS; per-(seed,index) streams | KEEP | | | |
| Estimator | Paired mean over complete valid pairs | KEEP | | | |
| Output metrics | Win/pod/expected-finish + distributions + execution rates | KEEP | | EXTEND (Top5/Top10/downside vector) | |
| Uncertainty | Paired SE + paired percentile bootstrap, sampling-only | KEEP | | | |
| Eligibility/unsupported | Exact anchor; 15-code taxonomy; supported=false / evaluated=false | KEEP | | EXTEND (StrategyEligibility in V3.6B) | |
| Temporal/stale safety | RETROSPECTIVE_PRODUCT; through-2024 params; exact-state authority; stale-roster refusal | KEEP | | | |
| Wet/retirement/SC | Wet/neutralized/red refused; no DNF/points; no weather-SC evolution | KEEP | | | |
| Cache | No result cache | KEEP (V3.6F designs) | | | |
| API | POST /v2/strategies/compare; per-index never leaves process | KEEP | | EXTEND (V3.6F) | |
| Frontend | /strategy; leader-not-recommendation; forbidden-copy guard | KEEP | | EXTEND (V3.6G) | |
| Wording | No best/recommended/optimal in shipped surfaces | KEEP | | | |

What Phase 7 already solves: paired CRN comparison, closed valid action
space, static validity gate, sampling-only uncertainty, objective leader
without recommendation, eligibility/unsupported discipline, temporal safety,
shipped API + frontend. What Strategy 2.0 must improve: MC2-E rebase,
widened paired outcome vector, 5000 paired default, frozen comparison and
eligibility contracts, V3.5 consistency-signal audit.

## Phase 7 semantics

Existing estimator is **paired, CRN, single-driver, whole-field-simulated**:
baseline arm run once from SimulationState(T); each candidate arm shares the
seed family and per-(seed,index) stream identity; deltas
(d_win/d_podium/d_finish) averaged over complete valid pairs. Shared: pace
streams, pit-domain streams pre-intervention, state, count, seed. Divergent by
design post-intervention (extra draws, reordered events). Phase 7 therefore
already supports the statement "under identical simulated stochastic futures,
intervention A changes outcome X relative to B" — with the documented
limitation that streams (not trajectories) are shared.

## MC2 audit

Frozen `v3.2-monte-carlo-2` (`197979d…047`): accepted simulator **MC2-E
(E_AR1_RESIDUAL)**; production/demo **5000** runs; mutually exclusive winners;
joint futures/finish ordering; causal status integration (exclusion-only
V3.2J); explicit eligibility (15-code taxonomy); deterministic PCG64 seeding
with domain separation. Interfaces: `RaceState → from_race_state →
SimulationState` (factual-only); `DriverSimState`; `SimulationConfig`;
`MonteCarloEngine.run(..., intervention=..., collect_index_outcomes=...)`;
`FinishOrder` + `DriverSimulationSummary` under MONTE_CARLO_FREQUENCY
invariants. MC2 accepts controlled strategy intervention without violating
frozen semantics (Phase 7 precedent: `intervention=None` byte-identical).

## MC2 outcome capabilities

DIRECTLY_SUPPORTED: win/pod frequency, finish-position frequency
distribution, expected finish. DERIVABLE: Top5/Top10 frequency, median +
quantiles, position gain/loss distribution, downside risk, DNF reporting
(not-modeled; engine emits none). REQUIRES_EXTENSION: expected points (no
points table in frozen summaries). NOT_DEFENSIBLE: anything absent from
simulated futures (e.g. invented DNF rates, weather-conditional outcomes).

## V3.5 semantics

Frozen `v3.5-outcome-distribution` (`6df5d41…0bff1`): task
`ordered_cumulative_finish_thresholds`; outputs p_win/p_podium/p_top5/p_top10;
semantics **PER_DRIVER_MARGINAL** (not joint, not field-normalized, not exact
P1–P20, not MC2 frequencies); champion **LOGISTIC_CONTROL**; XGB_E nonlinear
research candidate; **SERVING = NONE**; card identity
`8d3a8d2e…4446d`. Verified: no joint distribution, no causal effects, no
runtime path (import-audit coupling: none).

## V3.5 role decision

Primary role: **C — VALIDATION / CONSISTENCY SIGNAL**. A (primary objective)
and B (secondary signal) rejected: observational marginals are not
interventional and mixing them with MC2 frequencies risks double counting.
E (no role) rejected: discards a just-built diagnostic. D (UI context only)
admitted as supporting use with explicit marginal labeling. V3.5 never enters
Strategy 2.0 computation; V3.6D compares MC2 paired win frequencies against
frozen V3.5 p_win offline as a disagreement diagnostic.

## Prohibited fusion

V3.6 MUST NOT average, normalize, weight-blend, stack, or heuristically fuse
V3.5 marginals with MC2 frequencies. V3.8 owns Model × Simulation
consensus/fusion.

## Strategy comparison unit

One comparison = race_id + decision_lap/checkpoint + driver_id + baseline
(SIMULATED_NO_INTERVENTION_REFERENCE) + alternative action + causal
RaceState(T) identity + simulation config + paired seed set + outcome
differences. Proposed `StrategyComparisonKey` (exact fields frozen in V3.6B;
must extend Phase 7 `comparison_identity` precedent).

## Baseline semantics

Adopted: **SIMULATED_NO_INTERVENTION_REFERENCE** — frozen stochastic pit
mechanics from the same factual state at T. NOT the observed historical
future, NOT a normative claim. Terminology frozen: decision-time-available
baseline vs historical-observed-future (post-hoc, V3.6D context only, never a
decision input or correctness label).

## Action landscape

Admitted initial set: the frozen 9 (STAY_OUT×1 + PIT_NOW×4 + PIT_NEXT_LAP×4).
PIT_IN_N_LAPS (N>1) and two-stop plans REQUIRE_NEW_MODELING (V3.7).
Undercut/overcut labels NOT_DEFENSIBLE as action primitives. Smallest
defensible V3.6 space = keep the frozen 9.

## Intervention semantics

Direct variables only: forced/suppressed pit event at L_T+1(+2), compound for
the forced stint, age reset, pit-count increment. Consequences (rejoin
position, lap times, finish order, execution status) must emerge from MC2 —
never set manually.

## Pit-loss semantics

Frozen R6 empirical quantile grids, causal at T, frozen draw order,
per-domain RNG. SC-dependence and uncertainty unmodeled. Verdict: **KEEP**;
V3.6C verifies under MC2-E rebase; no redesign in A.

## Tyre and pace semantics

Degradation: broad pooled per-era clamped slope anchored at factual T age
(empirical/heuristic). Compound pace effect: DEFERRED (unsupported — must be
disclosed). Fresh-tyre reset: implemented. Unknown compounds: statically
invalid. Verdict: KEEP with disclosed limitations.

## Common random numbers

Principle frozen (see contract `crn_semantics`): same state, count, seed
family, stream identities; only the intervention differs; shares streams not
trajectories; no forced identical draws where the intervention changes
stochastic structure. Reuses Phase 7 S3 substrate.

## Paired estimands

PRIMARY candidates: Δ win, Δ podium, Δ expected finish. SECONDARY: Δ
Top5/Top10. DIAGNOSTIC: execution rates, valid-pair counts, SE ratio,
downside-risk delta. UNSUPPORTED: points (until table audited), DNF effects
(engine emits none), any single synthetic score.

## Primary outcome policy

**NO_SINGLE_UNIVERSAL_PRIMARY_UTILITY.** Alternatives presented as trade-off
vectors with paired 95% MC intervals; objective-specific point-estimate leader
per explicit objective; never ranked "best". Synthetic strategy scores
forbidden.

## Strategy trade-offs

Example presentation (illustrative, not a claim):

> PIT_NOW: Δ podium +4.1 pp · Δ Top5 +6.3 pp · Δ expected finish −0.42 pos ·
> Δ downside risk −2.0 pp (each with 95% MC interval + classification)

— rather than `STRATEGY SCORE = 87`. No arbitrary utility weights admitted.

## Uncertainty semantics

Paired SE + paired percentile bootstrap (B=2000, 95%, complete pair as
unit); availability AVAILABLE / INSUFFICIENT_PAIRS(<30) / NO_VALID_PAIRS.
Terminology: **MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY**; UI "95% MC interval".
Never "model uncertainty" or "real-world confidence interval".

## Simulation count

Recommended default: **5000 paired futures per action** (baseline + each
admitted alternative share one seed family). Rationale: frozen MC2
production/demo count; V3.2E convergence TV(5k→10k)=0.0046 within gate; CRN
reduces required N. Feasibility: S7 measured 10k/3cands ~48.5s sync —
V3.6F owns async/cache/demo policy. Not changed in A.

## Eligibility

Base = frozen MC2/Phase-6 taxonomy; strategy-stricter additions:
target-not-in-roster, decision-beyond-race-end, pit-dynamics-unavailable,
invalid compound/action, STAY_OUT+compound contract error. Proposed
`StrategyEligibility` with explicit reason codes frozen in V3.6B. No silent
fallback.

## Unsupported states

**UNSUPPORTED != NEGATIVE RESULT.** Explicit `supported=false +
unsupported_reason` (200) or `evaluated=false + reason` per candidate. Never
fabricate, constant-fill, or silently use stale/future data.

## Historical-action leakage audit

Mandatory table (contract `historical_action_leakage_policy`): adapter,
candidates, params, replay anchor = SAFE_AT_T; historical action/results
after T = POST_T_FORBIDDEN / LABEL_ONLY; simulation futures =
SIMULATION_GROUND_TRUTH_ONLY; status corpus gated by `retired_known_at(T),
t<=T`; V3.5 = POST_T_FORBIDDEN as decision input.

## Evaluation design

V3.6D questions: reproducibility, CRN variance reduction, seed stability,
sanity scenarios, intervention sensitivity, coverage + unsupported rates,
consistency, case-study plausibility. Forbidden: "did the team choose the
same action" as correctness. (Designed here; executed in D.)

## Counterfactual ground-truth limitation

History provides the outcome of the action taken — never the counterfactual.
Strategy 2.0 cannot be supervised on counterfactual ground truth. V3.6
validates simulation consistency, causal safety, estimator stability,
invariants, sensitivity, coverage, and plausibility instead. No optimal-strategy
claims.

## Product language

Keep: COMPARE STRATEGIES / STRATEGY ALTERNATIVES / SIMULATED OUTCOME
DIFFERENCE / PIT NOW / STAY OUT / PAIRED SIMULATIONS / point-estimate leader
(not a recommendation) / 95% MC interval. Avoid: BEST / OPTIMAL /
RECOMMENDED / SHOULD PIT / CORRECT / GUARANTEED. Phase 7 surfaces already
compliant (FORBIDDEN_STRATEGY_COPY enforced); carry the policy into V3.6.

## API landscape

`POST /v2/strategies/compare` with explicit objective, neutral ≤4 default
candidates, per-index contained server-side, stable error mapping.
Recommendation: **EXTEND_EXISTING_API** (versioned-new only if V3.6B finds the
frozen schema cannot carry the outcome vector). No change in A.

## Frontend landscape

`/strategy`: setup → baseline → leader → comparison table → detail;
explicit-run + stale-guard + unsupported panels. Preserved as-is; V3.6G owns
the Strategy 2.0 experience (trade-off vectors, Top5/Top10, downside risk).
No change in A.

## Cache/demo landscape

Phase 7: no result cache. Demo needs: 5000 paired futures × action count ×
checkpoint catalogue with determinism/provenance/unsupported handling.
V3.6F designs; no build in A.

## Architecture options

OPTION 1 (extend Phase 7 directly): re-verification burden on frozen paths —
not selected. OPTION 2 (thin paired-intervention layer around frozen MC2,
Phase 7 compatible): lowest regression risk, highest reuse and V3.7
compatibility — **SELECTED**. OPTION 3 (replace Phase 7): discards validated
S6/S7 evidence — rejected.

## Selected architecture

**OPTION 2.** Reuse S3/S4/S5 substrates; rebase the intervention seam onto
frozen MC2-E; keep Phase 7 API/frontend contracts working throughout.

## V3.7 boundary

V3.6 owns: STAY_OUT / PIT_NOW / PIT_NEXT_LAP (+compound) for the target
driver from causal RaceState(T) under paired MC2 futures. V3.7 owns: SC
removal, weather changes, other-driver behavior, collision edits, arbitrary
state edits. Closed action set enforced.

## V3.8 boundary

V3.8 owns Model × Simulation consensus/fusion including any learned/empirical
V3.5×MC2 combination. V3.6 uses V3.5 only as C-role consistency signal and
D-role UI context.

## Stage plan

V3.6A landscape+contract (here) → B action/state/intervention+eligibility →
C paired MC2 engine → D evaluation → E refinement IF WARRANTED (skippable) →
F runtime/API/cache → G frontend → H validation+freeze.

## Known limitations

Free-air rejoin (no traffic); no compound pace delta; no DNF/points/weather-SC
evolution in strategy outcomes; single-driver single-decision; inert/
superseded possible; CRN with limitations; heavy sync runs; 2025 unserved;
no probability mixing; counterfactuals are simulator-conditional.

## V3.6B recommendation

Freeze `StrategyComparisonKey` field list, `StrategyEligibility` reason-code
table, closed action/compound validity matrix, intervention-variable mapping
onto MC2-E state fields, and the widened paired outcome vector (with points
decision) — reusing Phase 7 S1/S4 contracts verbatim where unchanged.
