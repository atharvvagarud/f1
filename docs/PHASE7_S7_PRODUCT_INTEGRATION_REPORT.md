# Phase 7 — S7: Production API + Frontend Integration

Status: **S7 COMPLETE — READY FOR S8** (see the final verdict).

S7 exposes the validated S1–S6 Strategy Engine as a production product
surface: one Strategy API endpoint plus one Strategy frontend workspace. It
adds **no** Strategy science: no candidate-semantics, intervention-mechanics,
CRN-policy, delta-estimand, bootstrap, objective, simulation-dynamics, or
scientific-identity change. No frozen Phase-6 scientific runtime file changed.

Historical Phase-6 checkpoint: `b813ffe1` (`v2-monte-carlo-phase6`).
Frontend foundation: `6c04438` (`v2-frontend-foundation`).
S6 verdict inherited: `S6 COMPLETE — READY FOR S7` (0 blockers; finding F2
carried as binding latency guidance).

---

## 1. Files changed

### Backend (additive only)

| File | Change |
|---|---|
| `api/v2_strategy_service.py` | **New.** `V2StrategyService`: exact-anchor → `RaceState` → `SimulationState` → frozen through-2024 parameters → S4 `compare_strategies` → S5 `evaluate_objective` → compact projection. Product validation (duplicates, count/candidate caps, objective, seed) before execution. |
| `api/v2_strategy_schemas.py` | **New.** Request/response Pydantic models. `objective` required (no hidden backend default). `simulation_count` 100..10000, default 1000. `master_seed` optional, resolved default `20240101`. `candidates` optional, default neutral ≤4 set. |
| `api/v2_strategy_routes.py` | **New.** `POST /v2/strategies/compare` with frozen-convention error mapping. |
| `api/main.py` | **Additive.** Registers the strategy router + `StrategyParameterUnavailableError` → 503 handler. No existing route touched. |
| `tests/test_v2_phase7_s7_strategy_api.py` | **New.** 25 product API tests. |

### Frontend (additive only)

| File | Change |
|---|---|
| `frontend/lib/v2.ts` | **Additive.** Strategy types, `postStrategyCompare`, `isStrategyRequestInvalid`. No existing client changed. |
| `frontend/features/strategy/lib/strategyMachine.ts` | **New.** Canonical 9-candidate catalog, neutral defaults, workload bands, identity guards, unit formatting. |
| `frontend/features/strategy/hooks/useStrategy.ts` | **New.** Explicit-run state, session/request-id stale protection, abort. |
| `frontend/features/strategy/components/StrategyView.tsx` | **New.** Strategy workspace. |
| `frontend/features/strategy/components/StrategyResults.tsx` | **New.** Baseline / leader / comparison / detail presentation. |
| `frontend/app/strategy/page.tsx` | **New.** `/strategy` route. |
| `frontend/components/shell/CommandBar.tsx` | **Additive.** `STRATEGY` nav entry (Predict/Replay/Simulate untouched). |
| `frontend/features/strategy/lib/strategyMachine.test.ts` | **New.** 17 machine/copy tests. |
| `frontend/lib/v2.strategy.test.ts` | **New.** 5 client tests. |

Nothing staged, committed, or tagged. S8 not started.

---

## 2. Graphify pre-audit

Pre-edit `graphify update .`: **9 765 nodes, 24 828 edges, 288 communities**.
AST/grep dependency check before edits:

- `v2/simulation/*` imports of `v2.strategy` = **0**;
- `v2/strategy` imports of `api` = **0**;
- `api` imports of `v2.strategy` = **0** (S7 adds `api → strategy` only).

Expected direction `api → strategy → simulation` confirmed plannable; forbidden
`strategy → api` and `simulation → strategy` absent.

---

## 3. Product architecture

```
Frontend Strategy workspace (/strategy)
        ↓  POST /v2/strategies/compare (exact anchor + target + count + seed + candidates + objective)
API schema validation (pydantic bounds + product caps)
        ↓
V2StrategyService (api/v2_strategy_service.py)
        ↓  exact Phase-4 historical state reconstruction (no nearest/interpolation)
SimulationState adapter (R2 from_race_state)
        ↓  frozen through-2024 R3 parameters, RETROSPECTIVE_PRODUCT
S4 compare_strategies (one shared baseline + K paired arms)
        ↓
S5 evaluate_objective (selected objective only; no simulation rerun)
        ↓  compact projection (aggregates + paired deltas + selected-objective uncertainty)
frontend telemetry workspace (baseline / leader / table / detail)
```

No Strategy logic is reproduced in API or React: the service composes
`compare_strategies` + `evaluate_objective` + `candidate_uncertainty` and
projects their immutable outputs.

---

## 4. Strategy API contract

`POST /v2/strategies/compare`

Request:

```json
{
  "race_id": "2022-r01-R",
  "anchor_driver_id": "perez",
  "anchor_lap_number": 30,
  "anchor_state_time_s": 6745.686,
  "target_driver_id": "perez",
  "simulation_count": 1000,
  "master_seed": null,
  "objective": "MAXIMIZE_WIN_PROBABILITY",
  "candidates": [{"action": "PIT_NOW", "requested_compound": null}]
}
```

- `objective` is **required**: one of `MAXIMIZE_WIN_PROBABILITY`,
  `MAXIMIZE_PODIUM_PROBABILITY`, `MINIMIZE_EXPECTED_FINISH`. The scientific
  layer defines no default.
- `candidates` omitted → neutral default set (§6). `requested_compound: null`
  = sampled (baseline-drawn) compound.
- `master_seed` omitted → deterministic `20240101`; the resolved seed is
  echoed in every response.

Response (top level): contract versions (`strategy/intervention/comparison/
objective/uncertainty`), race/state identity, target, simulation count,
resolved seed, objective + metric, `probability_semantics =
"MONTE_CARLO_FREQUENCY"`, counterfactual semantics, CRN policy, comparison
identity, baseline block, per-candidate blocks, objective analysis
(leader / indistinguishable / distinguishable / order), limitations, runtime.

Per candidate: `candidate_key`, identity, action, requested compound,
valid/reason/evaluated; estimates (win/podium/expected finish +
finish-position distribution); paired deltas (win/podium/finish, frozen S4
signs); selected-objective uncertainty (point estimate, paired SE, 95%
sampling CI, classification); execution rates (applied/suppressed/superseded/
inert/race-end-cancelled).

Per-index outcomes never cross the boundary (S6-verified retention stays
internal). A JSON-wide audit in tests asserts no
`intervention_outcomes` / `baseline_outcomes` / per-index key leaks.

---

## 5. Request limits / latency policy (binding S6 F2)

| Control | Policy |
|---|---|
| `simulation_count` | min 100, default 1000, max synchronous 10000 |
| Default candidate set | ≤4 (neutral, §6) |
| 1000 trials | up to all 9 only when explicitly requested (heavy) |
| 10 000 trials | explicit advanced/manual only; max 3 candidates synchronously |
| Counts 1001–9999 with >3 candidates | rejected (`candidate_count_limit`) |
| Duplicates / empty set | rejected (`duplicate_candidates` / `no_candidates`) |

Note: the Phase-6 simulator floor is 1; S7 narrows the product floor to 100
so the default path stays practical. The 10000 ceiling is unchanged.

---

## 6. Exact-state integration

The endpoint reuses the Phase-4 authority verbatim: `AnchorObservation` →
shared `RaceStateReconstructor` → `from_race_state`. No nearest lap, no
timestamp rounding, no interpolation, no fall-forward, no future lookup. An
anchor miss is 422 `unknown_state` (verified: +0.5 s offset → 422).

---

## 7. Served-season firewall

`V2StrategyService` shares the `V2Service` served registry (2018–2024).
Any 2025 `race_id` is 404 `unknown_race` (verified). No backtest artifact is
ever selected: production parameters are the frozen through-2024 set.

---

## 8. Candidate selection policy

Default (omitted `candidates`), neutral product coverage — **not**
performance:

```
STAY_OUT  ·  PIT_NOW sampled  ·  PIT_NOW MEDIUM  ·  PIT_NEXT_LAP sampled
```

covers stay-out, immediate pit, explicit compound example, delayed pit. S6
showed `STAY_OUT` often led by point estimate; that outcome was deliberately
**not** used to choose the default.

Full canonical 9 (`STAY_OUT`, `PIT_NOW`×{sampled,SOFT,MEDIUM,HARD},
`PIT_NEXT_LAP`×{sampled,SOFT,MEDIUM,HARD}) is allowed only as an explicit
heavier comparison (workload band HEAVY), never automatic. Duplicates are
rejected, never silently deduped.

---

## 9. Objective / seed policy

- Exactly three objectives; the request carries no default. The UI preselects
  `MAXIMIZE_WIN_PROBABILITY` as a **visible, editable, explicitly submitted**
  control value with the note "No objective is inherently correct."
- Objective changes the analysis only: verified same `comparison_identity`,
  identical simulation deltas, different metric/leader (live test).
- Seed: advanced control, blank = backend default `20240101` (the R7
  validation seed, consistent with product simulation conventions). The
  resolved seed is echoed; seed 7 vs 8 yields different comparison identities.

---

## 10. Response projection

Built by `_response_payload` from the frozen `to_dict()` shapes plus
`candidate_uncertainty` per evaluated candidate and `classify_uncertainty`.
Baseline exposes win/podium/expected-finish/distribution/valid/invalid only
(no DNF/points — still deferred/null upstream). Pairwise detail is summarized
as leader + indistinguishable/distinguishable sets; the 36 raw pairwise
records are not dumped. Unsupported comparisons return
`supported: false` + canonical `unsupported_reason` with `baseline: null`
and all candidates `evaluated: false` (verified: wet → `wet_compound_state`;
unknown target → `target_driver_not_in_roster`).

---

## 11. Unsupported / error mapping

| Case | HTTP |
|---|---|
| Unknown race (incl. 2025) | 404 `unknown_race` |
| Anchor miss / malformed anchor | 422 `unknown_state` |
| Duplicate/empty/over-cap candidates, bad objective/seed | 422 `strategy_request_invalid` + stable `reason` |
| Malformed action/compound (schema) | 422 (pydantic) |
| Un-simulatable factual state / unknown target | 200 `supported: false` + canonical reason |
| Missing parameter artifact | 503 `parameter_unavailable` |
| Anything else | 500 `internal` |

---

## 12. API tests

`tests/test_v2_phase7_s7_strategy_api.py`: **25 passed** — bounds constants,
neutral defaults, shared authority init, duplicate/10k-cap/objective/count/
action/compound rejection (service + route), firewall, anchor-miss,
compact live response, omitted-candidates default, seed echo, structured
unsupported (target + wet state), determinism, seed sensitivity, subset
consistency, objective-invariance of simulation, no-recommendation-language
scan, no per-index leak scan, existing simulation API unchanged.

---

## 13. Frontend architecture

`/strategy` route (`app/strategy/page.tsx`) renders `StrategyView`, composed
of the frozen shell (`AppShell`/`CommandBar` + `STRATEGY` entry), shared
`Panel` primitives, the replay `RaceSelector`, and new strategy
`strategyMachine` (pure) + `useStrategy` (state/identity) + `StrategyResults`
(presentation). `lib/v2.ts` gains an additive strategy client. No existing
surface is redesigned.

---

## 14. Strategy workspace

Command bar → `STRATEGY / COUNTERFACTUAL PIT ANALYSIS` header with
`MONTE_CARLO_FREQUENCY` status → setup (race combobox, exact-anchor
scrubber, factual facts, target combobox from the frame roster) → objective
radios → run config (count radios, seed advanced, workload band) →
candidate matrix (STAY OUT / PIT NOW / PIT NEXT LAP groups, checkbox
semantics, canonical keys, 10k cap enforced by disabling) → RUN COMPARISON
→ baseline reference → point-estimate leader → comparison table →
candidate detail. Idle/running/unsupported/error panels mirror the
simulator's first-class technical states.

---

## 15. Candidate controls

Grouped checkboxes with `candidate_key` sub-labels; `SAMPLED` annotated
"modelled compound" with the note that explicit compounds change only stint
sampling/transitions (no pace effect). Count display ("N selected"),
keyboard-focusable native inputs, 10k cap disables further selection with
the workload note as the explanation.

---

## 16. Objective / simulation controls

Objective: native radio group, always visible, submitted explicitly.
Count: 1000/10000 radios (bounded synchronous options). Seed: numeric
advanced input, blank = default, recorded in the response. Changing any
control marks the result stale (clears it) and requires rerun — verified
live (objective change cleared the table back to Awaiting).

---

## 17. Baseline presentation

Rendered as the reference panel (estimates, valid/invalid trials, target),
never as a candidate action. Deltas are labeled "Estimated change vs
baseline". No baseline Strategy action is assigned.

---

## 18. Candidate comparison presentation

Dense table: Candidate | Win | Δ Win | Podium | Δ Podium | Exp finish |
Δ Finish | Objective Δ | 95% MC interval | Status (classification chip +
execution summary). Win/podium as percent, deltas as percentage points,
finish as positions, finish deltas signed positions (positive = estimated
improvement). Leader row carries a "Leader" chip. Non-evaluated candidates
show their reason, never fabricated numbers.

---

## 19. Uncertainty presentation

Selected objective's delta + `95% MC interval: <low> to <high>` in the metric
unit, paired SE in the detail panel, classification
IMPROVEMENT/DEGRADATION/INCONCLUSIVE/UNCERTAINTY_UNAVAILABLE labeled "under
simulation sampling". Withheld intervals render "interval withheld", never a
zero-width claim.

---

## 20. Execution-status presentation

Per-candidate execution text: `STAY_OUT` shows suppressed/inert rates;
`PIT_NEXT_LAP` shows applied/superseded; `PIT_NOW` shows applied. Detail
panel lists all five rates with the warning that a frequently inert or
superseded intervention with a near-zero delta is not equivalence evidence.

---

## 21. Counterfactual language

API + UI use: simulated strategy comparison, estimated probability, expected
finish, estimated change vs baseline, Monte Carlo sampling interval,
point-estimate leader, indistinguishable under sampling uncertainty,
counterfactual simulation. Audited (grep + shipped test) for: best/optimal/
recommended strategy, would have won/finish, guaranteed, correct strategy —
**0 occurrences** in S7 surfaces. The leader panel states "Leader refers to
the simulator point estimate, not a recommendation."

---

## 22. Loading / stale-result protection

Explicit RUN COMPARISON only; no auto-run on any control change. Running
state keeps controls disabled, prevents duplicate submits
(`view.kind !== "running"` gate + abort of in-flight), and shows "RUNNING
MONTE CARLO (count trials × N candidates)" with no fabricated progress.
Results bind to the full request identity (anchor + target + objective +
count + seed + sorted candidate keys); session/request-id guards plus
`AbortController` reject stale responses; `responseMatchesSelection`
re-verifies before render. Live-verified: control change during/after result
returns to Awaiting; race-condition guards unit-tested.

---

## 23. Responsive validation (Playwright, live server)

| Viewport | Page overflow | Notes |
|---|---|---|
| 1440 | none | dense table full width |
| 1024 | none | table fits |
| 768 | none | groups stack |
| 650 | none | result state checked |
| 390 | none | result state checked, table scrolls locally |
| 360 | none | initial state checked |

Table-local horizontal scroll (`overflow-x-auto`, `min-w-[56rem]`) preserves
all scientific columns on mobile; no content deleted. Focus order, visible
focus, and keyboard candidate toggling verified live (Space toggles checkbox,
legend count updates 4↔5).

---

## 24. Accessibility validation

Native `fieldset`/`legend`, checkbox/radio/select semantics, real buttons,
table `th scope` + `caption`, `aria-live` run status, `role="alert"` errors,
`role="status"` chips, slider `aria-valuetext`. Classification is text, never
color-only. No motion beyond the disabled opacity state (reduced-motion
safe). Live keyboard check passed.

---

## 25. Real-backend integration

Against the local backend (port 8001): supported 1k/4 comparison (6.7 s),
unsupported wet state (`wet_compound_state`, 0.1 s), objective change
(same identity), subset rerun, stale-clear rerun — all via the real
`POST /v2/strategies/compare`. Frontend exercised live against the same
backend: race switch → roster → target select → run → result → stale-clear.

---

## 26. Endpoint performance (measured, MID 2022-r01-R/perez/lap 30)

| Config | Wall | Simulation | Analysis |
|---|---|---|---|
| 1k / 1 candidate | 2.4 s | — | — |
| 1k / default 4 | 6.7 s | — | — |
| 1k / full 9 | 12.7 s | 12.0 s | 0.5 s |
| 10k / 3 candidates | 48.5 s | 48.0 s | 0.3 s |

Consistent with the S6 bands (9-cand/1k 10–35 s; 10k/3 35–142 s). The
default path is practical; full-9 stays explicit/heavy; 10k stays
advanced/manual. No async infrastructure added (correct bounded sync v1).

---

## 27. Frontend tests

22 new tests pass (`strategyMachine` 17: catalog, neutral defaults,
bounds/caps, workload, identity guards, formatting units, unsupported
messages, shipped-copy audit; `v2.strategy` 5: payload/URL, pass-through,
422 contract, abort). Full frontend suite: **119 pass / 0 fail** (97
pre-existing + 22 new). `tsc --noEmit` clean, `eslint` clean, production
`build` green with `/strategy`.

---

## 28. Typecheck / lint / build

`npx tsc --noEmit` clean; `npx eslint` clean (one `set-state-in-effect`
finding fixed by moving loading-flag resets into selection handlers);
`npm run build` green (`/strategy` static).

---

## 29. S1–S6 scientific regression

Run after integration (python3.11): S1 contracts/seam/compat, S2 mechanics,
S3 paired, S4 comparison, S5 uncertainty + objectives, S6 validation, freeze
governance (`test_v2_phase6_freeze.py`), and R8 simulation API regression —
**325 passed, 0 failed** (24.2 s). No new failure; the S6-documented
pre-existing pins live in files outside this run's surface (R6/R7.1 identity
pins, Phase-4/5 integration pins) and no S7 change can reach them: no
simulation file changed and the freeze governance test passes.

---

## 30. Phase-6 regression

No frozen Phase-6 scientific runtime file changed in S7
(`v2/simulation/monte_carlo.py` untouched). `test_v2_phase6_freeze.py`
passes (authorized S3 drift only, all other scientific hashes intact) and
the S1 compat fixture reproduces byte-for-byte. R8 simulation API suite
passes. No Phase-6 baseline drift.

---

## 31. Simulation API regression

`api/` changes are additive (3 new files + router registration + 503
handler). R8 suite passes unmodified (§29); `GET /v2/races` (149 races)
verified unchanged via test. No frozen endpoint changed.

---

## 32. Scientific drift audit

`simulation → strategy = 0`; `strategy → api = 0` (AST-verified, §33).
`docs/PHASE6_FREEZE_MANIFEST.json` and
`docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json` untouched. Only edges are
`api → strategy → simulation` (plus pre-existing `api → simulation`).

---

## 33. Graphify final result

`graphify update .`: **9 979 nodes, 25 361 edges, 298 communities**
(pre-edit: 9 765 / 24 828 / 288). AST check: `simulation → strategy = 0`,
`strategy → api = 0`; no Strategy cycle (`strategy → simulation` only).

---

## 34. Known limitations

Inherited S6 limitations unchanged: simulator-conditional Monte Carlo
frequencies; sampling uncertainty only; no traffic/overtaking (free-air
rejoin); no per-compound pace delta; CRN shares stream identities, not
trajectories; STAY_OUT frequently inert; small-n interval withheld below 30
pairs; leader ambiguity common; no observable counterfactual ground truth.
Product additions: synchronous-only execution (9×10k not permitted); no
caching layer; strategy page shows no Phase-3 prediction context by design.

---

## 35. Git safety

No `reset`/`restore`/`checkout`/`clean`/`stash`/`add`/`commit`/`tag`.
Nothing staged. Tags `v2-monte-carlo-phase6`, `v2-frontend-foundation`
preserved. Unrelated user work (modified `AGENTS.md`, `GEMINI.md`,
`opencode.json`, hook helpers) untouched. Temporary servers run on ports
8001/3001; the pre-existing servers on 8000/3000 untouched. S8 not started.

---

## 36. S7 DoD

- [x] S0–S6 docs/code read; graphify pre-audit (9765/24828/288)
- [x] Strategy service + `POST /v2/strategies/compare` implemented
- [x] Exact state authority reused; served-season firewall preserved
- [x] Target/candidate/objective/seed/count validation before execution
- [x] Default 1k; default neutral ≤4 set; full-9 explicit/heavy; 10k advanced
      with 3-candidate cap; duplicates rejected
- [x] Objective explicit (no backend default); UI preselect visible + submitted
- [x] Structured unsupported states; compact response; no per-index exposure
- [x] Baseline/candidate/delta/uncertainty/leader/execution projection with
      `MONTE_CARLO_FREQUENCY` + counterfactual semantics; no Phase-3 mixing
- [x] `/strategy` route + nav; brutalist telemetry preserved
- [x] Candidate/objective/count/seed controls; workload bands; explicit RUN;
      no auto-run; loading/duplicate/stale protection; retry
- [x] Bounded product copy (audit clean); point-estimate leader wording
- [x] Responsive 1440/1024/768/650/390/360, no page overflow; keyboard + a11y
- [x] API tests 25 green; frontend 119 green (97 prior + 22 new); tsc/lint/build
- [x] Real backend supported/unsupported/objective/rerun/stale tested with timings
- [x] Playwright visual + keyboard + stale validation complete
- [x] Copy audit complete
- [x] S1–S6 + Phase-6 + simulation API regression (325 passed, §29)
- [x] Graphify final (9979/25361/298; directions clean, §33)
- [x] Integration report created; nothing staged/committed/tagged; S8 not started

**Final verdict: S7 COMPLETE — READY FOR S8.**
