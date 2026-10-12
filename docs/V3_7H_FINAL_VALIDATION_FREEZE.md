# V3.7H FINAL VALIDATION + FREEZE

## Final verdict

V3.7H COMPLETE — V3.7 FROZEN — READY FOR V3.8.

## Frozen parent

- Commit: `1eb462631b9d7a948e35b8a1658e3bb90035c94c`
- Tag: `v3.6-strategy-2.0`
- Verified: `git rev-parse HEAD` equals the required parent; no prior V3.7 commit; no V3.7 tag at entry; nothing staged.

## Complete stage chain

- V3.7A — scientific counterfactual contract (`v3.7a-counterfactual-contract-v1`)
- V3.7B/B1 — execution contract, corrected position-gain orientation (`v3.7b-counterfactual-execution-contract-v1`)
- V3.7C — counterfactual execution engine (`v3.7c-counterfactual-engine-v1`)
- V3.7D — historical evaluation + empirical gate (`REFINEMENT_NOT_WARRANTED`)
- V3.7E — `SKIPPED_BY_V3.7D_GATE` (no implementation; verified absent)
- V3.7F — runtime/API/cache integration
- V3.7G — Counterfactual Explorer frontend (`/counterfactuals`)
- V3.7H — this validation + freeze (no science change)

## Scientific definition

V3.7 computes SIMULATOR-CONDITIONAL OUTCOMES UNDER CONTROLLED INTERVENTIONS.
It does NOT compute true alternate history, causal treatment effects, optimal
or recommended strategy, historical truth, or guaranteed outcomes.

## A provenance

- Schema: `v3.7a-counterfactual-contract-v1`
- Identity: `1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12`
- Recomputed from `results/v3/v3_7a/counterfactual_contract.json` (canonical JSON, `contract_hash` excluded). Match.

## Corrected B provenance

- Schema: `v3.7b-counterfactual-execution-contract-v1`
- Corrected identity: `1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970`
- Recomputed from `results/v3/v3_7b/counterfactual_execution_contract.json`. Match.
- Superseded pre-B1 identity exists only as marked historical provenance, never as current.

## C engine

- Engine identity: `v3.7c-counterfactual-engine-v1`
- Validation artifact: `results/v3/v3_7c/counterfactual_engine_validation.json`
- No stage after C changed C scientific semantics (seam hash unchanged, parity sentinels green).

## D evaluation

- Protocol schema: `v3.7d-evaluation-protocol-v1`, identity `e4a6101c7267f2db9f85c76bcc07c17ed01c7f85de4a6481f94ab0941634c570` (recomputed, match).
- Card schema: `v3.7d-evaluation-card-v1`, identity `96debc6392c79019abedc3a51c7c26fb1536e97cabb3fed3136c43ed7c2b19c3` (recomputed, match).
- Gate: `REFINEMENT_NOT_WARRANTED` (preserved).
- Population: 71 candidate anchors, 70 evaluated, 1 adapter-unsupported (`mazepin`, unobserved roster member).
- Supported comparisons: 700.
- Pathology: P1–P17 zero; blocking invariants 0.
- Recorded sentinels: 4/4 reproducibility, 16/16 V3.6 parity, 12/12 position-gain, 12/12 pit-count, 12/12 ahead-of-rival.
- No stage after D changed D artifacts. Full D matrix NOT rerun (forbidden unless scientifically necessary; no necessity found).

## V3.7E skipped

- Status: `SKIPPED_BY_V3.7D_GATE`.
- Repository search for `v3_7e`/`v3.7e` returns nothing. No E engine, runtime, research artifact, or tests.

## F runtime/API/cache

- Runtime: `v3.7f-counterfactual-runtime-v1`; API: `v3.7f-counterfactual-api-v1`
- Cache key: `v3.7f-counterfactual-cache-key-v1`; cache artifact: `v3.7f-counterfactual-cache-v1`; manifest: `v3.7f-counterfactual-manifest-v1`
- Policy: cache-first, server-controlled live execution; production 5000 futures, root seed 20240101; no public seed/count/live overrides; no fast fallback; no V3.5/V3.6/historical substitution.
- DIRECT == LIVE == CACHED parity recorded for representative outputs; corruption fails closed (wrong state/plan/comparison/engine/seed/count/schema/malformed sentinels retained).

## G frontend

- Route `/counterfactuals` exists; V3.6 `/strategy` intact (unmodified).
- API-only: no scientific Python imports; no count/seed/live controls; deterministic result-neutral demo fixture selection; explicit cache-miss/unsupported/2025 states.
- Orientations correct (position-gain, expected-finish, probability); pit count descriptive; lifecycle/supersession/complete-pairs/MC-sampling-interval surfaced; provenance + limitations accessible.
- Fixtures captured from real F responses; representative fixture conforms to frozen F serialization (`v3.7f-counterfactual-api-v1`, 5000/20240101).

## C seam

- SHA-256 of `raceintel/simulation/monte_carlo.py`: `045f392e46b030744f18a76140685ceba7501f80c0b8e265af662e57ca5f5376`
- Recomputed from file bytes. Matches D card, F validation, G validation. Additive only.

## Supported interventions

- Primitive: `PIT_IN_N_LAPS` (N >= 1; scheduled_lap = decision_lap + N).
- Compositional: multi-stop, multi-driver, alternative compound plans, competitor/rival ordering where admitted.

## Rejected interventions

WEATHER, SAFETY_CAR, VSC, RED_FLAG, RETIREMENT, RELIABILITY, ARBITRARY_POSITION,
ARBITRARY_GAP, ARBITRARY_PACE, ARBITRARY_TYRE_AGE, UNDERCUT, OVERCUT remain
rejected and unexecutable (contract + engine + API guards all green).

## Temporal safety

- Canonical boundary RaceState(T); historical future forbidden as input; canonical reference SIMULATED_NO_INTERVENTION_REFERENCE.
- Poison sentinels (pit events, compounds, lap times, positions, gaps, status, retirement, weather, race control, SC/VSC/red flag, finish/result, team action) green across direct engine, runtime, API, and cache-generation paths.

## CRN and pairing

Same factual state, same config, same root seed (20240101), same future index, same stream family; only controlled plan differences. Production 5000 futures. Complete valid pairs only for paired metrics. Uncertainty = MONTE CARLO SAMPLING UNCERTAINTY only.

## Outcome orientation

- Probability-like deltas (win/podium/top5/top10/P(ahead of rival)): ALT - BASE.
- Expected finish delta: BASE - ALT (lower is better).
- Position gain: factual_position_T - simulated_final_position (P5→P2 = +3); expected_position_gain = mean; comparison ALT - BASE.
- Pit count descriptive only. No universal utility score, no global winner, no recommendation layer.
- Verified independently at contract, engine, runtime, API, cache, and frontend layers.

## Position gain

See above. 12/12 sentinel evidence preserved; all layers agree.

## Lifecycle

PLANNED / ELIGIBLE / EXECUTED / INERT / SUPERSEDED / CANCELLED / TERMINAL / INVALID
with frozen transition semantics. No silent rescheduling; SUPERSEDED is not failure;
no historical future in lifecycle decisions. D's increasing supersession with horizon
is simulator-mechanics evidence; NO_CAP_WARRANTED preserved.

## 2025 boundary

Unsupported throughout runtime, API (404 unknown_race), and frontend (explicit message).
No fallback, no substitution.

## Historical guard reconciliation

14 stale stage-entry guards narrowly reconciled (original invariant identified,
superseding charter cited, protection preserved with exact allowlists / pinned seam
hash; no deletions, no xfails, no skips):

- `test_v3_6a` (V3.6A): `test_head_matches_parent` → frozen-ancestor invariant for
  `1eb4626…`; `test_no_serving_api_frontend_mc2_v35_changes`, `test_no_api_change`,
  `test_no_frontend_change` → exact V3.7 chartered-path admissions;
  `test_no_mc2_change` → seam-only admission with pinned SHA-256.
- `test_v3_6b` (V3.6B seam detectors): same pattern for API/frontend and MC2 guards.
- `test_v3_6d`: `test_no_tuning` (untracked new files permitted by design; tracked
  mods pinned to exact chartered paths), `test_no_api_frontend_changes`.
- `test_v3_6f_runtime`: `test_no_frontend_changes`.
- `test_v3_5c_harness` / `test_v3_5d_screening`: serving-guard admissions.
- `test_v3_7a`: `test_baseline_clean_at_entry` (final-phase allowlist incl. H freeze
  machinery) and `test_no_mc2_api_frontend_modification` (final-state invariant,
  seam hash-pinned).
- Tier-1 runner: `EXPECTED_COLLECTED` 4449 → 4693 (244 new V3.7 tests across 7 files,
  0 corpus-dependent, no removals); `ci_corpus_dependent.txt` unchanged.
  Frontend runner: `EXPECTED_TEST_FILES` 21 → 22 (G machine test, source-safe).

## Architecture

Graphify entry: 17860 nodes / 40649 links / 489 communities. Targeted queries confirm
frontend → HTTP → API → runtime → C engine → MC2; evaluation tooling depends downward
on science only. No forbidden production dependency (no MC2→API/frontend, no engine→
API/frontend/cache, no runtime→D-implementation/V3.5, no frontend→Python/D/cache).
Import audit confirms C engine/contracts import only raceintel science + stdlib/numpy.

## Claim audit

Searched code, frontend, docs, artifacts for optimal/best/recommended/should-pit/
correct/wrong strategy, would-have-happened/won, causal effect, proves, guaranteed,
real-world confidence. All hits are explicit prohibitions or forbidden-language test
guards. No result-dependent recommendation language. Pass.

## Targeted tests

V3.7A/B/C/D-artifact/F-runtime/API/cache suites: 242 passed; only the 2 known stale
A stage-entry guards failed pre-reconciliation (now green after narrow reconciliation).

## Full Tier-1

- Command: `.venv/bin/python scripts/run_ci_tests.py` (repository-authoritative Tier-1 selector)
- First run: 4 failed / 3637 passed / 1048 deselected / 4 xfailed — all 4 classified STALE HISTORICAL GUARD (3 V3.7-dirt trips in V3.5A/V3.5B/V3.7A guards + 1 pre-existing `v3.4-ensemble` tag trip in V3.4E), narrowly reconciled with no science change.
- Final run: collected=4693, selected=3650, deselected=1048, passed=3641, failed=0, skipped=0, xfailed=4, duration 2882s (48:02). Zero unexplained failures.

## Frontend validation

- `npm ci`: ok. Node tests: 270 passed / 0 failed (22 files collected, 21 selected, 1 corpus-deselected). Typecheck (`tsc --noEmit`): clean. Lint: clean (exit 0). Production build: success; `/counterfactuals` prerendered; `package-lock.json` unchanged.
- Smoke (production servers, final tree): `/counterfactuals` returns 200 with correct title; shell/nav/methodology/limitations render; copy bounded; API-error states explicit (validation backend on :8001 green for availability + cached compare; page build targets :8000, occupied by an unrelated process, so the demo-data path was verified via fixture↔live `comparison_identity` match instead). Width 390: clean single-column render. G-stage 1600/820/390 screenshots stand.

## Final diff

Only chartered V3.7 paths (see freeze manifest in `results/v3/v3_7h/final_validation.json`).
Tracked modifications outside new V3.7 directories, each justified:

- `raceintel/simulation/monte_carlo.py` — chartered V3.7C additive MC2 seam (hash-pinned)
- `api/main.py` — chartered V3.7F router registration (one line)
- `frontend/lib/v2.ts` — chartered V3.7G append-only API client
- `frontend/components/shell/CommandBar.tsx` — chartered V3.7G nav entry (one line)
- Historical guard allowlists/tests + Tier-1 runner — Part-R reconciliation (this document)

## Scientific card

`results/v3/v3_7/v3_7_scientific_card.json` (schema `v3.7-counterfactual-engine-scientific-card-v1`).
Identity recorded in `results/v3/v3_7h/final_validation.json`.

## Freeze commit

PENDING_COMMIT — `feat(v3.7): freeze counterfactual engine` (one commit; no retrospective split; no V3.6 history rewrite).

## Freeze tag

PENDING_TAG — annotated `v3.7-counterfactual-engine` → freeze commit. No push (local only).

## Known limitations

Simulator-conditional, not causal truth; no weather-evolution intervention; no
SC/VSC/red-flag generation; no retirement/reliability hazard family; no arbitrary
factual-state edits; no primitive undercut/overcut; compound pace differentiation
limited; conservative supersession; no pit-box stacking model; no explicit
traffic-battle model; no team-order model; multi-driver propagation ordering-focused;
2025 unsupported; MC intervals are sampling uncertainty only; no global
utility/recommendation; spatial data visualization-context only; cache-first demo has
finite precomputed coverage.

## V3.8 readiness

V3.7 frozen and safe for V3.8 (MODEL × SIMULATION CONSENSUS) to consume. V3.8 work
NOT started: no consensus code, no probability averaging, no combined confidence.
