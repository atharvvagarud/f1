# V3.7C COUNTERFACTUAL EXECUTION ENGINE

## Final verdict

V3.7C COMPLETE — COUNTERFACTUAL ENGINE VALIDATED — READY FOR V3.7D

## Frozen parent

V3.6 `v3.6-strategy-2.0` (`1eb46263…`). V3.6/MC2-science/V3.5/Phase-7/API/
frontend/cache untouched.

## A/B provenance

A `17359542…b0a12`; corrected B `18655375…4e970`; readiness C-ready TRUE.
Superseded B `d8e14640…` is history only.

## Architecture

`CounterfactualPlan → V3.7 schedule/tracker → frozen MC2 intervention
seam → MC2 future → V3.7 aggregation` (`raceintel/counterfactual/
engine.py`, ~500 lines). No duplicate simulator. MC2 changes are
additive seam plumbing (schedule resolve/state, call-site branches,
per-event outcomes, pit-count column); legacy paths proven byte-identical
(191 frozen tests green); pace/pit/RNG/eligibility science unchanged.

### Chartered seam extension vs frozen guards

V3.6B `test_no_mc2_change` trips on the additive schedule support above.
This is a change-detector doing its job, not a behavioral regression:
every frozen legacy path is green, N=1/N=2 parity is bit-identical, and
no scientific mechanism changed. Multi-event execution within one
trajectory is unimplementable without dispatch access (chained runs are
forbidden by B; duplicating the loop is forbidden architecture), so the
chartered C scope necessarily touches the seam file. The frozen test is
left unmodified per immutability; the trip is recorded in the validation
artifact (`chartered_change_detector_trip`). V3.7H owns Tier-1
reclassification (new C tests change collection).

## Engine identity

`v3.7c-counterfactual-engine-v1` (mechanics, not performance).

## Simulated-time trigger

scheduled_lap = decision_lap + N; trigger reads simulated lap
completions only. Zero-noise trace proves exact landing; poison tests
prove no historical reads (blocked-parquet rerun identical; source scan).

## V3.6 parity

N=1 vs PIT_NOW and N=2 vs PIT_NEXT_LAP BIT-IDENTICAL over 5000 futures
(positions, pit counts, full results). Strongest level; no weakening.

## Plan tracker

Separate runtime state (frozen plan never mutated): identity, trigger,
compound, lifecycle, evidence, terminal reasons per event.

## Lifecycle execution

B table enforced; illegal transitions fail closed. PLANNED→ELIGIBLE at
trajectory start; EXECUTED/INERT/SUPERSEDED/CANCELLED/TERMINAL per rule.

## Multi-event schedules

Multiple events in ONE trajectory (no extract-and-restart); chronological;
per-event evidence.

## Multi-stop execution

Two forced stops with R6 state continuity (age reset, stint/target
redraw); pit counts grow; no new tyre physics; no compound-realism claims
beyond frozen mechanics.

## Supersession

Natural pit strictly inside (decision, trigger) supersedes (absolute
window, conservative, documented). No blind forcing, rescheduling, or
history inspection.

## Conflict enforcement

Identical→deduplicated in seam adapter; same-trigger-different-compound→
INVALID at eligibility; staggered→runtime supersession; distinct
targets→VALID.

## Multi-driver execution

IMPLEMENTED — no new assumptions required: joint ordering propagates,
no stacking delay modelled (documented), canonical order-invariant
identity, same CRN family, pair-compatible. NOT blocked.

## Order invariance

Permuted inputs share plan and result identity (canonical targets +
sorted outcome events); RNG behavior identical.

## Reference

SIMULATED_NO_INTERVENTION_REFERENCE reused exactly; never STAY_OUT,
history, or team strategy; no V3.7-specific alternate.

## Reference-vs-plan

Same state/config/seed/index/streams; schedule differs only; complete
pairs; V3.6 positive-improvement orientation.

## Plan-vs-plan

BASE=A, ALT=B explicitly (canonicalization never swaps); probability
deltas B−A; expected finish A−B; position gain B−A.

## CRN

Generalized by construction (shared arms); determinism, order
invariance, orientation, stream identity, seed stability proven.
Structural divergence expected after intervention; no identical-
trajectory or model-uncertainty claims.

## Complete pairs

complete+excluded==requested with reasons; no replacement/imputation/
borrowing/resampling; INERT/SUPERSEDED keep valid futures.

## Outcomes

V3.6 ten (MC2 futures only; downside I(alt>ref) reused exactly) +
P(ahead), expected pit count, expected position gain (B1). Bootstrap
95%/B=2000/n≥30 for paired deltas where mechanically defined; MC
sampling only.

## Ahead-of-rival

Joint simulated order over complete pairs; exact P=1.0 synthetic case;
never history or V3.5. Ties: strict < (documented).

## Pit count

Per-future integers incl. forced pits; expected aggregate; natural/
forced/superseded cases behave.

## Position gain

B1: factual−simulated (P5→P2=+3) executed and aggregated; deltas
plan−ref / B−A; never historical final.

## Unsupported results

supported=false with level/codes/identities/provenance at all four
levels; metrics EMPTY; no substitutes.

## Eligibility

STATE (roster) / INTERVENTION (horizon) / PLAN (conflicts) /
COMPARISON (rival) tested per level; valid syntax ≠ eligible.

## Temporal safety

Factual T + schedule + frozen params + simulated future only. Seam
receives no historical fields; poison + structural evidence.

## Poison tests

Blocked-parquet rerun byte-identical; engine source has no historical
reads/reconstruction/weather/race-control references.

## Rejected interventions

All 12 kinds fail closed at contract AND seam (direct engine.run with
WEATHER raises); no placeholders.

## Determinism

Same seed → identical identity (incl. permutations); different seed →
valid independent run; no clock/global RNG.

## Real-state micro-validation

2022-r01-R perez lap-30 anchor, 5000 futures, seed 20240101: N=1, N=2,
N=5, multi-stop, rival, multi-driver — all supported with complete
pairs. Mechanical only; D owns evaluation.

## Performance

Synthetic 5000-arm ~0.1 s; 6-case micro ~70 s. Measured; no semantic
trade-offs, caches, or RNG parallelization.

## Known limitations

Conservative absolute supersession window; no stacking model; narrow
INERT; TERMINAL edge-only; time-loss still research; C tests partly
corpus-dependent (H to classify).

## D readiness

TRUE — D can sample eligible states, run plan comparisons, and evaluate
stability/CRN/cases with no new scientific decisions.
