# V3.6H FINAL VALIDATION AND FREEZE

## Final verdict

V3.6H COMPLETE — V3.6 FROZEN — READY FOR V3.7

## Frozen parent

- Tag: `v3.5-outcome-distribution`
- Commit: `6df5d41d3ebead9a1c9b4f0f40ed20a21ce0bff1`
- At H entry HEAD equaled the parent; working tree held only V3.6 A/B/C/D/F/G
  changes; nothing staged, nothing committed, no `v3.6*` tag.

## Stage ledger

| Stage | Identity | Verdict |
|---|---|---|
| V3.6A | `2d29c19b…ae59b` (recomputed exact) | V3.6A COMPLETE — STRATEGY CONTRACT FROZEN — READY FOR V3.6B |
| V3.6B | `df821fe1…443e3644` (recomputed exact) | contract frozen; 9 actions, CRN, complete pairs |
| V3.6C | `v3.6c-engine-v1` | V3.6C COMPLETE — PAIRED MC2 ENGINE VALIDATED — READY FOR V3.6D |
| V3.6D | protocol `0c2bf7fb…64088fc` (recomputed exact) | V3.6D COMPLETE — REFINEMENT NOT WARRANTED — READY FOR V3.6F |
| V3.6E | — | INTENTIONALLY SKIPPED (see below) |
| V3.6F | runtime_integration verdict | V3.6F COMPLETE — RUNTIME/API/CACHE INTEGRATED — READY FOR V3.6G |
| V3.6G | `v3.6g-frontend-validation-v1` | Strategy 2.0 frontend validated |

## V3.6E skip

`V3.6E = SKIPPED_BY_V3.6D_GATE`. No `*v3_6e*` / `*V3_6E*` file exists
(asserted by `test_v3_6e_absent`, green). Occurrences of the V3.6E token
are skip-descriptions only.

## File inventory

Scientific/runtime/evaluation/API/cache/frontend/tests/docs/result changes only.
Full per-path classification lives in `results/v3/v3_6_freeze.json`.

- New: `raceintel/strategy/v3_contracts.py`, `raceintel/strategy/v3_engine.py`,
  `api/v2_strategy_v3_{routes,schemas,service}.py`,
  `scripts/v3_6d_{sample,run_layer1,run_layer2,analyze}.py`,
  `scripts/v3_6f_build_strategy_cache.py`,
  Strategy2 frontend (`Strategy2View/Strategy2Results/useStrategy2/
  strategy2Machine{,.test}`), V3.6A–D/F/G docs, results, tests
  (`test_v3_6a/b/c/d/f`), H machinery (card, freeze, H doc, `test_v3_6h_freeze.py`).
- Modified: `api/main.py` (router append), `frontend/app/strategy/page.tsx`
  (Strategy2 root), `frontend/lib/v2.ts` (append-only v3 client),
  `strategyMachine.test.ts` (guard surface), stage-guard allowlists
  (broken-test corrections for chartered F/G paths), Tier-1 selector
  reclassification (see ## Full Tier-1).
- Deleted (deliberate G replacement, presentation only):
  `StrategyView.tsx`, `StrategyResults.tsx`, `useStrategy.ts`.
  Phase-7 backend, API, and science are untouched.
- Ignored/generated: graphify-out, validation cache payloads, screenshots —
  none staged.

## Scientific identity

- Question: Given causal RaceState(T), how do plausible strategy actions
  change the simulated distribution of future race outcomes?
- Engine: MC2-E (`v3.2-monte-carlo-2`, `197979d4`), 5000 production futures.
- Reference: `SIMULATED_NO_INTERVENTION_REFERENCE` (never STAY_OUT).
- Actions: frozen 9 (`STAY_OUT:SAMPLED`, `PIT_NOW` × {SAMPLED,SOFT,MEDIUM,HARD},
  `PIT_NEXT_LAP` × {SAMPLED,SOFT,MEDIUM,HARD}).
- Pairing: COMMON RANDOM NUMBERS; complete pairs only.
- Outcomes: win/podium/top5/top10 frequencies, expected/median/q25/q75 finish,
  downside probability, finish-position distribution.
- Delta orientation: positive = improvement (`alt - ref`; `ref - alt` for
  expected finish).
- Uncertainty: `MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY`, paired percentile
  bootstrap B=2000, 95%, n>=30 rule.
- Utility: `NO_SINGLE_UNIVERSAL_PRIMARY_UTILITY` (objective-specific leaders only).
- V3.5 role: `OFFLINE_DIAGNOSTIC_ONLY`. Serving: LIVE + scientifically
  identical CACHE; public default CACHE_FIRST. 2025 UNSUPPORTED.
- Claim posture: SIMULATOR-CONDITIONAL COUNTERFACTUAL ESTIMATES.

## Strategy semantics

Reference/action/CRN/pairing/outcome/delta/uncertainty semantics re-verified
across contract, engine, API, frontend, and docs in H. No drift from V3.6B.

## MC2 relationship

V3.6C engine wraps frozen MC2-E; NO-INTERVENTION parity, Phase-7
compatibility, determinism, action-order invariance, and complete-pair
accounting re-reconciled green in H (`test_v3_6c_engine.py`, 42 passed).

## CRN and complete pairs

Same state/config/seed-family/index; only the intervention differs.
Complete pairs only for comparative estimands; no independent-arm
substitution; no action-order RNG dependence.

## Outcomes

All Strategy 2.0 outcomes originate from MC2 futures. No V3.5 marginal
probability enters Strategy 2.0 computation. Position distributions are
mutually exclusive and normalized over valid futures.

## Uncertainty

Paired estimators, B=2000, 95% MC intervals. No copy describes intervals as
real-world confidence or recommendation certainty (one doc occurrence is an
explicit Never-use prohibition).

## Historical evaluation

- 298 candidates → 71 eligible (23.8%) → 639 comparisons, 71/71 supported.
- Reproducibility 4/4 exact; seed/count stability acceptable.
- CRN paired/independent ratios 0.85 / 0.93 / 0.96 (+ documented degenerate ties).
- Case studies 5/5 PLAUSIBLE, 0 PATHOLOGICAL.
- V3.5 diagnostic: 34 matched states, mean |diff| ≈ 0.026, median ≈ 0.0003,
  correlation ≈ 0.91.
- Decision: REFINEMENT_NOT_WARRANTED. Full catalogue materialization DEFERRED.

## V3.5 separation

No runtime computational dependency from V3.6 engine/API/cache/frontend to
V3.5 model/probabilities/calibration/PAVA. D's offline diagnostic only.
V3.8 owns fusion.

## Runtime/API

- Strategy 2.0: `POST /v2/strategies/compare-v3`, `GET /v2/strategies/v3/availability`.
- Phase-7 `POST /v2/strategies/compare` intact (byte-compatible).
- Parity proven: DIRECT == API LIVE, API LIVE == API CACHED (5000-run fixture).
- Production: 5000 simulations, `DEFAULT_MASTER_SEED = 20240101`, no caller
  count override (schema accepts no count field).
- Cache: deterministic key (`v3.6f-strategy-cache-key-v1`), provenance
  validated, corrupt rejected, miss explicit, unsupported explicit, 2025
  refused, no Phase-7 fallback, no V3.5 substitution.

## Cache

Cached results originate from the same V3.6C engine. No demo math, no
reduced-simulation public results, no hand-authored results. Validation
catalogue is tiny (2 states) by charter; NOT expanded in H. Capacity
estimate reconciled from artifact (`cache_capacity.json`):
D-style 298-state/5960-comparison reference; full-build estimate
775415 comparisons, 404–1615 machine-days at 45–180 s/state —
rough estimate, not measured fact. FULL MATERIALIZATION DEFERRED.

## Frontend

`/strategy` serves Strategy 2.0: cache-first default, availability-driven
selection, no silent live fallback, reference ≠ STAY_OUT, frozen 9 actions,
six trade-off metrics, positive-improvement orientation, 95% MC interval
terminology, downside definition, objective-specific leaders only, no global
score, MC2 finish-position distribution, execution diagnostics,
complete-pair counts, provenance, unsupported/cache-miss handling, 2025
unavailable, methodology, limitations. Phase-7 presentation deletions are
the deliberate G replacement (backend intact).

## Temporal safety

V3.6 runtime inputs audited: no historical post-T pit/tyre/lap-time/status/
weather/safety-car/finish data enters strategy computation.
Simulator-generated futures only. Leakage/temporal suites green.

## Phase 7 compatibility

Backend, old API, and scientific semantics unchanged and regression-tested
(S1 contracts, S7 API, C parity). Only the old presentation layer was
replaced by charter.

## Claim audit

Swept Python/TypeScript/docs/JSON for best/optimal/recommended/should-pit/
correct/guaranteed/proves/confidence/counterfactual-accuracy. All hits are
forbidden-copy lists (negated) or leader-with-qualification language.
No unsupported recommendation claim. H adds a permanent guard
(`test_no_forbidden_recommendation_claim`).

## Limitations

Preserved in the scientific card: dry-only, no compound pace delta, no
expected-points objective, no weather/SC evolution model, single-driver,
single-decision, CRN limitations, simulator-conditional, conservative
eligibility, 2025 unsupported, catalogue not yet materialized.

## Graphify

- Entry: 16933 nodes · 38592 edges · 494 communities.
- Final: 16990 nodes · 38674 edges · 498 communities.
- Dependency direction frontend → API client →
  V3.6 API → service/cache → engine → MC2; no engine→API/frontend/V3.5
  edges; no runtime→evaluation-script edges.

## Focused tests

- V3.6 A/B/C/D/F: 186 passed, 0 failed.
- V3.6H freeze tests: 20 passed.
- Phase-7 S1/S7 + C engine: 123 passed.
- V3.3–V3.5 files: 407 passed, 1 expected sentinel
  (`test_no_final_v34_freeze_tag_commit_yet`).
- Stale stage guards (A/B/D/F + V3.5a–d) corrected as broken-test
  allowlist updates for chartered F/G paths; all green after correction.

## Full Tier-1

Authoritative `scripts/run_ci_tests.py` (Tier-1 source-safe selector).
V3.6H reclassified the V3.2N-era backlog: 598 added tests (V3.3–V3.6),
109 corpus-dependent pinned in `scripts/ci_corpus_dependent.txt` with
clean-checkout simulation evidence, 489 source-safe, +20 H tests =
EXPECTED_COLLECTED 4449.
Result: collected 4449, selected 3406, deselected 1043 (corpus),
3396 passed, 1 failed, 0 skipped, 4 xfailed, runtime 2417 s.
The single failure is the known expected sentinel only:
`test_v3_4e_evaluation.py::test_no_final_v34_freeze_tag_commit_yet`
(pre-freeze-only guard; legitimate `v3.4-ensemble` tag exists; documented
in V3.5F). Full record in `results/v3/v3_6_freeze.json`
`full_tier1_summary`.

## Frontend validation

`tsc --noEmit` PASS, `npm run lint` 0 errors, production `next build` PASS
(`/strategy` route present), source-safe suite 236 passed / 0 failed
(21 files found, 20 selected, 1 corpus-deselected; EXPECTED 20→21 for the
G-chartered `strategy2Machine.test.ts`). Responsive smoke
(desktop/tablet/mobile) per G method; no frontend bytes changed in H, so G
screenshots/artifacts stand with test proof. Full record in the freeze
record `frontend_summary`.

## Scientific card

`results/v3/v3_6_final_scientific_card.json`
(`v3.6-final-scientific-card-v1`), identity
`102079ab81101f442d380c109a32b71a3b6850f0106e021f0fc4b05a64c80aeb`
(deterministic SHA256, no volatile fields).

## Freeze record

`results/v3/v3_6_freeze.json` (`v3.6-freeze-v1`): parent, message, tag,
card identity, stage identities, inventory, test/Tier-1/frontend summaries,
Graphify, sentinel, cleanliness expectation, `push_status = NOT_PUSHED`.

## Commit

Exactly one commit since `v3.5-outcome-distribution`:
`feat(strategy): add Strategy 2.0 paired race intelligence`.

## Tag

Annotated `v3.6-strategy-2.0`: "V3.6 Strategy 2.0 — paired MC2
counterfactual strategy intelligence". Points to HEAD. Older tags unmoved.
NOT PUSHED.

## Repository state

`git status` clean; one V3.6 commit; tag on HEAD; nothing pushed.

## Next phase

V3.7 (weather/SC evolution, per V3.6A boundary). V3.8 owns model×simulation
fusion. No deployment from H.
