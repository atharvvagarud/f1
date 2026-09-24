# Phase 7 — Strategy Engine Final Report (S8 Freeze)

Status: **PHASE 7 FROZEN — READY FOR NEXT PHASE** (pending final commit/tag;
all scientific, product, architecture and hygiene gates pass).

Phase 7 delivers a frozen counterfactual pit-strategy comparison engine:
single-driver, single-decision interventions on the frozen Phase-6 Monte
Carlo simulator, paired CRN comparison of up to 9 candidates, Monte Carlo
sampling uncertainty, three explicit objectives, one production endpoint
(`POST /v2/strategies/compare`) and one frontend workspace (`/strategy`).

Historical checkpoints preserved: Phase 6 `b813ffe1`
(`v2-monte-carlo-phase6`); frontend foundation `6c04438`
(`v2-frontend-foundation`). `docs/PHASE6_FREEZE_MANIFEST.json` untouched.
S0–S7 verdicts inherited: S6 `83 checks / 0 failures / 0 blockers`; S7
`25 API + 22 frontend tests, 119/119 total, typecheck/lint/build green`.

Machine-readable companion: `docs/PHASE7_STRATEGY_FREEZE_MANIFEST.json`
(contract versions, semantics, bounds, drift, evidence, tracked SHA-256).

## 2. Phase-7 architecture

```
frontend /strategy  →  POST /v2/strategies/compare
  →  V2StrategyService (exact Phase-4 anchor → RaceState → SimulationState,
      frozen through-2024 parameters, RETROSPECTIVE_PRODUCT)
  →  S4 compare_strategies (one shared baseline + K paired arms)
  →  S5 evaluate_objective + candidate_uncertainty (analysis only, no rerun)
  →  compact projection (aggregates + paired deltas + selected-objective
      uncertainty; no per-index leakage)
```

Dependency direction enforced: `api → strategy → simulation`.
`simulation → strategy = 0`, `strategy → api = 0`, no Strategy cycle
(AST + Graphify, pre- and post-freeze).

## 3. Scientific contracts

| Contract | Version |
|---|---|
| strategy | s1 |
| intervention | v1 |
| candidates | s4-candidates-v1 |
| comparison | v1 |
| paired | s3-paired-v1 |
| uncertainty | v1 |
| objective | v1 |
| simulation | v1 / r4-engine-v1 / r5-monte-carlo-v1 / r6-pit-dynamics-v1 |

Probability semantics: `MONTE_CARLO_FREQUENCY`. Counterfactual semantics:
historical state at T is factual; baseline and intervention futures are
simulated counterfactual estimates, not observed truth; no historical
future is used. CRN: `CRN_ADOPTED_WITH_LIMITATIONS` (shares per-`(seed,
index)` stream identities, not trajectories). Compound pace: no direct
pace delta. Scope: single driver, single decision.

## 4. Intervention semantics

- **STAY_OUT:** suppresses the target decision event once (at the target
  driver's own `L_T + 1`), then normal mechanics resume. No draw consumed;
  `target_age` untouched.
- **PIT_NOW:** forces one pit at the target driver's next completed lap
  (`L_T + 1`), replacing (never adding to) the baseline decision.
- **PIT_NEXT_LAP:** `L_T + 1` stays baseline-normal; if a baseline pit
  occurs there the intervention is `SUPERSEDED`
  (`intervention_superseded_by_baseline_pit`), otherwise forced at `L_T + 2`.
- Race-end suppression (R6-AB) overrides any forced pit; statically
  impossible decisions rejected (`decision_beyond_race`); forced pits reuse
  frozen draw order (compound → loss → stint target), age reset to 0,
  compound draw always consumed under override.

## 5. Candidate space

Canonical 9: `STAY_OUT`, `PIT_NOW × {sampled, SOFT, MEDIUM, HARD}`,
`PIT_NEXT_LAP × {sampled, SOFT, MEDIUM, HARD}`. Static validity reuses the
canonical simulator validator; invalid candidates are reported with stable
reasons, never simulated, never silently dropped.

## 6. Paired Monte Carlo / CRN

Baseline and each candidate arm share `SimulationState`, parameters,
config (including `master_seed`, `simulation_count`); only the
intervention differs. Pair identity covers state, parameters, config,
seed, index, contract versions and intervention identity.
`collect_index_outcomes` records compact terminal per-index outcomes from
the same terminal batch state (no second path, no draw change, default
off, aggregate-only product path unchanged).

## 7. Comparison estimand

Canonical estimand: mean over **complete valid pairs**; aggregates keep
each arm's own valid denominator. Delta signs frozen: positive =
estimated improvement. Unsupported states yield `supported: false` +
canonical reason, no partial table.

## 8. Uncertainty

Paired point estimate + paired SE, unpaired-SE diagnostic, SE-ratio
diagnostic, paired percentile bootstrap (B=2000, 95%, linear quantile,
complete pair as unit). Small-n: interval withheld below 30 pairs;
constant difference → SE 0 with collapsed interval (still labelled
sampling uncertainty). **CI is Monte Carlo sampling uncertainty, not a
causal real-world confidence interval.**

## 9. Objectives

Exactly three: `MAXIMIZE_WIN_PROBABILITY`,
`MAXIMIZE_PODIUM_PROBABILITY`, `MINIMIZE_EXPECTED_FINISH`. No default at
scientific-service level (API requires it; UI preselect is visible,
editable, explicitly submitted). No weighted score, no recommendation.
Classification `IMPROVEMENT / DEGRADATION / INCONCLUSIVE /
UNCERTAINTY_UNAVAILABLE` from the CI vs baseline. The point-estimate
leader is a label, not a best/optimal/recommended strategy.

## 10. Validation / red team

S6 protocol `s6-validation-v1`, frozen before the corpus ran: 45 broad
1k jobs (15 eligible states × FRONT/MIDFIELD/BACK), deep 1k-vs-10k
subset, future-poison, anchor, RNG, CRN, denominator, inert/superseded,
compound, objective, uncertainty, leader-ambiguity, candidate-set,
mutability, probability-semantics, language, zero-uncertainty,
performance/memory, unsupported-state, Phase-6 compat, drift,
dependency and identity audits. **83 adversarial checks, 0 failures,
0 blockers.** Artifacts `data/v2/strategy/s6_validation_v1.json` /
`s6_red_team_v1.json` (gitignored, reproducible; identities pinned in
the freeze manifest). No leakage was detected under the implemented
adversarial test suite (not an absolute proof).

## 11. API

`POST /v2/strategies/compare`: exact anchor + target + count + seed +
candidates + required objective. Default count 1000 (range 100–10000);
default seed `20240101` (echoed); default neutral ≤4 set (action-space
coverage, not performance); 1k allows explicit full 9; 1001–10000 caps
at 3 candidates; duplicates/empty rejected. Served seasons 2018–2024
(149 races); 2025 → 404 `unknown_race`. Compact response, no per-index
leakage (test-audited). 25 API tests green.

## 12. Frontend

`/strategy` route: setup (race combobox, exact-anchor scrubber, factual
facts, target combobox), objective radios, count/seed controls, workload
band, candidate matrix, explicit RUN COMPARISON, baseline reference,
point-estimate leader, comparison table, candidate detail, first-class
unsupported/error panels. Stale-result protection (full request identity
+ session guards + abort). 22 new tests; full suite 119/119; typecheck,
lint and production build green.

## 13. Performance

S7 measured (MID 2022-r01-R/perez/lap 30): 1k/1 ≈ 2.4 s, 1k/4 ≈ 6.7 s,
1k/9 ≈ 12.7 s, 10k/3 ≈ 48.5 s. S8 smoke re-verified: 100/1 → 0.34 s,
1k/default-4 → 6.08 s server-side. Guidance frozen: normal = 1k/default
set; heavy = 1k/full-9 explicit; advanced/manual = 10k/≤3. No async
jobs, no cache (correct bounded sync v1). Measurements are guidance,
not scientific guarantees.

## 14. Temporal safety

Strategy inherits `ExecutionPolicy` and all Phase-6 temporal guards;
parameters are through-2024 production artifacts; 2025 firewalled;
contemporaneity refusal inherited whole-state; request identity binds
state/parameters/config/seed. Bounded S6 temporal adversarial tests
re-run green. Wording: no leakage was detected under the implemented
adversarial test suite.

## 15. Phase-6 compatibility

Original S1 fixture (`tests/fixtures/phase7_s1_phase6_baseline.json`)
unchanged; `intervention=None, collect_index_outcomes=False` reproduces
the captured Phase-6 baseline byte-for-byte
(`test_v2_phase7_s1_phase6_compat.py` green). Freeze governance test
green.

## 16. Authorized drift

`docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json` (v3, S3): only
`v2/simulation/monte_carlo.py` differs from Phase 6 (historical
`f0a3447f…`, current `d2166075…`, both verified live); every other
frozen scientific runtime file matches its Phase-6 hash. S7 added no
simulation drift. `docs/PHASE6_FREEZE_MANIFEST.json` untouched.

## 17. Testing

- Strategy regression (S1–S7 + freeze governance): **305 passed, 0 failed**.
- Phase-6 R5–R8/freeze governance: covered in strategy run (green) + full suite.
- Full Python suite: **11 failed, 2860 passed, 5 skipped, 4 xfailed**
  in 3370.7 s. The 11 are exactly the S6-documented pre-existing set, no
  new failure: 7 environment-sensitive NumPy identity pins (R6 ×1
  `test_pit_disabled_reproduces_r5_result_identity`; R7.1 ×6
  `test_accepted_state_matches_pre_fix_result_identity[...]`) plus 4
  pre-existing Phase-4/5 pins (`test_frozen_module_hashes_match`,
  `test_freeze_manifest_file_hashes_match`,
  `test_freeze_manifest_documents_authorized_api_main_drift` — all
  `api/main.py` post-Phase-5 additive drift, live hash now the S7
  router-registration version — and `test_head_and_phase4_tag_intact`,
  HEAD having legitimately advanced past Phase 4). Passed count rose
  2835 → 2860, exactly the +25 new S7 API tests.
- Frontend: 119/119, tsc clean, eslint clean, build green with `/strategy`.

## 18. Known limitations

Counterfactuals are simulated, not truth; sampling uncertainty only; no
traffic/overtaking (free-air rejoin); no compound pace delta; no
reliability/DNF/points; no weather/SC evolution; single-driver
single-decision; STAY_OUT often inert; PIT_NEXT_LAP sometimes superseded;
CRN with limitations; full-9 sync runs slow; 10k manual/≤3; no async, no
cache; 2025 unserved; no Phase-3 mixing.

## 19. Product limits

Synchronous-only; count 100–10000; >3 candidates rejected above 1000
trials; objective required; unsupported states return structured reasons
with no partial table.

## 20. Reproducibility

Deterministic: same request → identical identities and per-index
outcomes (seed-echoed). S6 artifacts reproducible via
`scripts/run_phase7_s6_validation.py` / `run_phase7_s6_red_team.py`;
S1 baseline via `scripts/capture_phase7_s1_baseline.py` (fixture NOT
regenerated). Environment pinned in S6 artifact (Python 3.11.15,
NumPy 2.4.2).

## 21. Freeze checkpoint

- Commit: *(recorded at commit time; manifest `git_checkpoint` updated
  post-commit without touching scientific content)*
- Tag: `v2-strategy-engine-phase7` (annotated; historical tags untouched)
- Manifest: `docs/PHASE7_STRATEGY_FREEZE_MANIFEST.json`
- This report: `docs/PHASE7_STRATEGY_FINAL_REPORT.md`

## 22. Next-phase handoff

Phase 7 is closed; no next-phase work started. Natural follow-ups
(replay/strategy integration, track visualization, explainability,
prediction timelines, MLOps/deployment) are for the roadmap to decide;
the repository's next planned phase is not asserted here. Constraints
for any successor: preserve exact-state authority, the authorized-drift
record, per-index containment, counterfactual language discipline, and
the synchronous product bounds unless explicitly re-engineered.
