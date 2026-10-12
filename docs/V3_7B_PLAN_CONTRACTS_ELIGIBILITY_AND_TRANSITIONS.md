# V3.7B PLAN CONTRACTS, ELIGIBILITY AND TRANSITIONS

## Final verdict

V3.7B COMPLETE — COUNTERFACTUAL EXECUTION CONTRACT FROZEN — READY FOR V3.7C

## Frozen parent

V3.6 `v3.6-strategy-2.0` (`1eb46263…`), card `102079ab…a64c80aeb`. V3.7A
contract `17359542…b0a12` (working-tree dirt at entry). Nothing in V3.6,
MC2, V3.5, Phase 7/12, API, frontend modified by B.

## A provenance

Schema `v3.7a-counterfactual-contract-v1`, identity
`1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12`.
Admitted: PIT_IN_N_LAPS, compound plans, multi-stop / competitor /
multi-driver as causal extensions, derived undercut/overcut, rival-ahead
outcomes. Rejected: weather/SC/retirement/red-flag/state-edits.
Architecture: generic schedule above MC2. Reference unchanged.

## Reuse audit

REUSE_VERBATIM: StrategyAction enum (untouched), compounds+SAMPLED, lap
offsets, SimulationConfig/State identity, execution statuses, 5000,
seed 20240101, CRN substrate, uncertainty patterns, canonical_sha256.
WRAP: StrategyIntervention → ScheduledIntervention; StrategyComparisonKey
→ PlanComparisonKey. EXTEND_ADDITIVELY: eligibility +PLAN; forbidden
fields + plan fields. NEW: plan/schedule/key/outcome-schema versions,
lifecycle transitions, conflict matrix, 6 reason codes. Full table in
contract artifact. Import discipline: stdlib + `simulation.state` leaf
only; V3.6 literals re-declared and equality-tested (V3.6B precedent), so
no engine/API/frontend/V3.5 import path exists.

## CounterfactualPlan

Declarative schedule: targets, ordered interventions, optional rival.
Canonical SHA256 identity; no timestamps/paths/labels; no historical
future, outcomes, scores, or state mutations. USER_ASSUMPTION provenance.

## Scheduled interventions

Single admitted kind `PIT_IN_N_LAPS`: target, N (≥1), compound,
decision_lap, state identity. N is simulation-relative offset, never a
historical lookup. Scheduled lap = decision_lap + N.

## PIT_IN_N_LAPS semantics

Off-by-one frozen from runtime rule: N=1 forces at first simulated lap
(PIT_NOW mechanics); N=2 baselines then forces (PIT_NEXT_LAP mechanics);
N≥3 has no V3.6 counterpart. Equivalence is validation-only; V3.6 actions
unreinterpreted. Horizon: N ≤ remaining_laps − 1; earlier baseline pit
supersedes; race end cancels.

## Compound semantics

SOFT/MEDIUM/HARD/SAMPLED reused. Intervention parameter, not a pace
guarantee (pace delta absent per frozen MC2). No INTERMEDIATE/WET.

## Multi-stop representation

Compositional ordered schedules; canonical chronological identity;
chained-runs-from-simulated-state rejected (provenance + CRN break).
Contract now; execution in C.

## Canonical ordering

Sort key (scheduled_lap, target, kind, compound): input-order invariant
across targets, chronological within a target.

## Targets

Canonical driver identities from simulation state (never display names).
Single, competitor, and multiple forms at contract level; multi-target
execution deferred to C extension.

## Rival retention

Rival must exist factually, differ from targets, and exist in valid
paired futures. No V3.5, no historical classification; unavailable =
explicit unsupported, never zero/substitute.

## Lifecycle

PLANNED/ELIGIBLE/EXECUTED/INERT/SUPERSEDED/CANCELLED/TERMINAL/INVALID.
Mapping: EXECUTED→APPLIED, SUPERSEDED→SUPERSEDED,
CANCELLED→RACE_END_CANCELLED; rest contract-level only.

## Transition table

PLANNED→{ELIGIBLE,CANCELLED,TERMINAL,INVALID};
ELIGIBLE→{EXECUTED,INERT,SUPERSEDED,CANCELLED,TERMINAL}; terminals sink.
Absent edge fails closed (machine-readable table in artifact).

## Supersession

Earlier natural pit, earlier-plan stint change, or invalidated second-stop
assumptions → SUPERSEDED (runtime) — never silent reschedule, never
historical inspection.

## Terminal semantics

Request-time impossibility = INVALID; simulated non-executability =
CANCELLED/TERMINAL. Neither is a negative result.

## Conflict matrix

Identical→DEDUPLICATE; same trigger different compounds→INVALID;
same-target staggered→RUNTIME_SUPERSESSION; distinct targets→VALID (no
stacking modelled — documented, not invented).

## Multi-driver contract

Order-invariant, same CRN family, deterministic target ordering,
ordering-only propagation (no traffic battles), conflict-safe,
complete-pair compatible. Same-lap multi-driver pits allowed by the pit
model (no team interaction modelled). Execution deferred.

## Eligibility

STATE/INTERVENTION/PLAN/COMPARISON (INTERVENTION succeeds V3.6 ACTION).
Frozen codes reused by reference; 6 new plan codes only where nothing fits.

## Unsupported results

supported=false, level, codes, identities, provenance; metrics EMPTY —
never zero/NaN/fallback/substitute.

## Comparison forms

REFERENCE_VS_PLAN (canonical reference) and PLAN_VS_PLAN (secondary).
Identity over state/plan(s)/config/seeds/schema/rival. Count fixed 5000.

## Delta orientation

Positive = improvement (alt−base; base−alt for expected finish).
Plan-vs-plan: BASE=A, ALT=B. Pit count descriptive only.

## Outcomes

V3.6 eight retained + p_ahead_of_rival + pit_count + position_gain_loss.
Time loss stays research; points/DNF rejected.

## Ahead-of-rival

Frequency over valid complete pairs from simulated order; ties/missing/
terminal handled explicitly in C; deltas alt−base.

## Pit count

Per-future integer + expected aggregate; forced pits counted; minimum
sufficient, descriptive.

## Position gain/loss

Factual T − simulated final (B1 correction): positive = numerically
lower/better finish (P5 → P2 = +3; P5 → P5 = 0; P5 → P8 = −3). Expected
aggregate is the arithmetic mean over valid membership. Comparative
delta is plan − reference (B − A for plan-vs-plan); expected finish
keeps its separate base − alt reversal. No historical finish.

## CRN

Same state/config/seed-family/index/streams; schedules differ only.
Structural divergence (pit-domain counts, supersession paths) documented;
pairs preserved; no model-uncertainty claims.

## Complete pairs

Comparative estimands use complete valid pairs only; no replacement/
imputation/borrowing/resampling. INERT/SUPERSEDED ≠ invalid futures.

## Temporal safety

Factual T + user schedule + frozen pre-T params + simulated future only.
All post-T historical classes + plan smuggling fields forbidden (poison/
contract-tested).

## Rejected interventions

WEATHER/SAFETY_CAR/VSC/RED_FLAG/RETIREMENT/RELIABILITY/ARBITRARY_*/
UNDERCUT/OVERCUT kinds fail closed at parse time.

## Undercut/overcut

Derived analytical labels only (relative timing + rival result).

## Provenance

12 compact deterministic fields (A/B identities, schemas, MC2, state,
config, seeds, count, outcomes). No volatile data in identity.

## Contract identity

`results/v3/v3_7b/counterfactual_execution_contract.json`
(`v3.7b-counterfactual-execution-contract-v1`),
`d8e14640930393c6193e5ecb1df601b9d8e40c986b986877f505f6e4307ccdeb`
superseded by B1 correction identity
`1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970`.

## C readiness

TRUE: no unresolved scientific decisions. No execution/API/cache/
frontend built. Readiness artifact `results/v3/v3_7b_readiness.json`.
C builds the schedule-capable engine against this contract.
