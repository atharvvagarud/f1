# Phase 7 — S6: Scientific Validation + Adversarial Red Team

Status: **S6 COMPLETE — READY FOR S7** (see the final verdict and the
condition attached to finding F2).

S6 is the final scientific validation and adversarial gate for the Phase-7
Strategy Engine. It adds **no** Strategy capability. It attempts to break the
existing S1–S5 system, then characterises it descriptively. The historical
future is never an input; no counterfactual, recommendation or accuracy claim
is made anywhere.

Historical Phase-6 checkpoint: `b813ffe1` (`v2-monte-carlo-phase6`).
Frontend foundation: `6c04438` (`v2-frontend-foundation`).
S3 decision inherited: `ADOPT_CRN_WITH_LIMITATIONS`.
S4/S5 decisions inherited: complete-valid-pair comparison estimand, frozen
delta signs, three explicit single-metric objectives, no weighting.

---

## 1. Files changed

| File | Change |
|---|---|
| `tests/s6_validation_protocol.py` | **New.** Frozen S6 protocol identity and the deterministic, eligibility-based state/target selection (single source of truth for runner and tests). |
| `scripts/run_phase7_s6_validation.py` | **New.** Broad 1k corpus, deep 1k-vs-10k subset, historical characterisation, unsupported-state / temporal-firewall / future-channel audits, performance + memory, reproducibility metadata. Writes `data/v2/strategy/s6_validation_v1.json`. |
| `scripts/run_phase7_s6_red_team.py` | **New.** Adversarial red team A–W (83 checks). Writes `data/v2/strategy/s6_red_team_v1.json`. |
| `tests/test_v2_phase7_s6_validation.py` | **New.** 24 offline S6 invariant tests. |
| `v2/strategy/comparison.py` | **Narrow MINOR fix.** The shared result-`limitations` metadata still said "No production uncertainty (CI / SE / significance) is exposed; that belongs to S5", which is stale after S5. Reworded to state that S5 adds an additive, sampling-only view. No scientific value, delta, ordering or `identity()` changes (limitations are excluded from `identity()`). |
| `docs/PHASE7_S6_VALIDATION_REPORT.md` | **New.** This report. |
| `data/v2/strategy/s6_validation_v1.json` | Generated artifact. **Not tracked** (`/data/v2/` is git-ignored by repository policy; reproducible from the script). |
| `data/v2/strategy/s6_red_team_v1.json` | Generated artifact. **Not tracked**; reproducible from the script. |
| `graphify-out/*` | Refreshed by `graphify update .`. |

No frozen Phase-6 scientific runtime file changed. `v2/simulation/monte_carlo.py`
still matches its S3-authorized hash
`d2166075e2d4b90bf4604ac3d586fe4d07f1ae577cb413ec8991317309e68c68`;
`docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json` and
`docs/PHASE6_FREEZE_MANIFEST.json` are untouched. No API or frontend file
changed. Nothing is staged, committed or tagged.

---

## 2. Validation protocol

`STRATEGY_VALIDATION_PROTOCOL_VERSION = "s6-validation-v1"` (`tests/s6_validation_protocol.py`).
Frozen **before** the final corpus ran. The protocol predeclares:

- **Selection rule.** Reuse the Phase-6 R7 protocol pool (accepted seasons
  2020–2024; 2018/2019/2025 excluded; `through_season = season - 1`), keep only
  anchors the frozen simulator itself accepts (R7.1 whole-state
  `_validate_start_state` eligibility, no simulation, no draw), and within each
  season take the lexicographically-first eligible race that carries the stage
  anchor. Eligibility-based, never Strategy-result-based.
- **Target rule.** Roster sorted by `(position, driver_id)`; FRONT = rank 0,
  MIDFIELD = rank n//2, BACK = rank n−1. All three bands per state.
- **Counts / seeds.** Broad `1 000`; deep `10 000`; seeds `20240101` (broad and
  deep) and `7` (determinism); bootstrap root `20240101`, B = 2 000, 95%.
- **Candidate space.** The canonical nine (`STAY_OUT`, `PIT_NOW`×{sampled,SOFT,
  MEDIUM,HARD}, `PIT_NEXT_LAP`×{sampled,SOFT,MEDIUM,HARD}); deep subset
  `STAY_OUT`, `PIT_NOW`, `PIT_NEXT_LAP` (sampled).
- **Acceptance / blocking criteria** (unchanged after seeing results): 0
  blockers; no temporal leakage; no Phase-6 baseline drift; no wrong
  intervention/pairing/denominator/uncertainty/objective behaviour; no
  unexplained non-determinism; no silent unsupported-state simulation.

No protocol amendment was needed; the original protocol was applied unchanged.

---

## 3. Environment / reproducibility

Recorded in `data/v2/strategy/s6_validation_v1.json` (`environment`):

| Field | Value |
|---|---|
| Python | 3.11.15 |
| NumPy | 2.4.2 |
| pandas | present (used only by the evaluation replay seam, never by `v2.strategy`) |
| scikit-learn | importable, never imported by Strategy |
| platform | macOS (arm64) |
| simulation contract | `v1`; engine `r4-engine-v1`; Monte Carlo `r5-monte-carlo-v1`; pit dynamics `r6-pit-dynamics-v1` |
| Strategy versions | contract `s1`, intervention `v1`, comparison `v1`, candidates `s4-candidates-v1`, paired `s3-paired-v1`, uncertainty `v1`, objective `v1` |
| parameter identity | R3 `through-2024` manifest SHA-256 recorded in the artifact |
| simulation runtime | `monte_carlo.py` SHA-256 = S3-authorized drift hash |
| seeds / counts | `20240101` (1 000 / 10 000), `7` (determinism) |
| machine paths | not recorded (project convention) |

---

## 4. Graphify pre-audit

Pre-edit `graphify query` located the Strategy community (candidates,
comparison, paired, contracts, interventions, uncertainty, objectives) and the
S1–S5 seams. AST dependency check before edits:

- `v2/simulation/*` imports of `v2.strategy` = **0**;
- Strategy internal edges form a DAG
  (`__init__ → {candidates, comparison, contracts, interventions, objectives,
  paired, uncertainty}`, `candidates/contracts/interventions → contracts`,
  `comparison → {candidates, contracts, paired}`,
  `objectives → uncertainty`, `uncertainty → ∅`); **no cycle**;
- `v2/strategy` imports no `api` / `frontend` / `model_lab` / `prediction` /
  `replay` / oracle / `pandas` / `sklearn` material.

Post-edit `graphify update .`: **9 725 nodes, 24 771 edges, 307 communities**;
graph `simulation → strategy` edges = **0**; no Strategy cycle.

---

## 5. Historical validation corpus

99 R7 anchors were tested for frozen-simulator eligibility. **35 are eligible;
64 are rejected** by the R7.1 whole-state contemporaneity rule
(`non_contemporaneous_roster_member`). The R7 raw artifact predates R7.1, so
this is an R7-corpus property, not a Strategy defect (finding F3). The rejected
anchors are excluded with their engine reason, never replaced by a more
convenient state.

The resulting representative corpus is 15 eligible states (5 seasons × 3
stages); every state is run for all three bands → **45 broad jobs**. Selected
states:

| Season | Race | EARLY | MID | LATE |
|---|---|---|---|---|
| 2020 | r03 / r05 | 2020-r03-R | 2020-r05-R | 2020-r05-R |
| 2021 | r07 | 2021-r07-R | 2021-r07-R | 2021-r07-R |
| 2022 | r01 | 2022-r01-R | 2022-r01-R | 2022-r01-R |
| 2023 | r01 / r07 | 2023-r01-R | 2023-r07-R | 2023-r07-R |
| 2024 | r01 | 2024-r01-R | 2024-r01-R | 2024-r01-R |

Coverage: EARLY/MID/LATE; five seasons; FRONT/MIDFIELD/BACK bands; dry
compounds and varied tyre ages occur naturally; BACK covers lapped/behind
drivers. Near-race-end and near-pit-window behaviour is exercised by LATE
states and by the adversarial fixtures (unsupported-state audit, red-team G).

---

## 6. Red-team threat matrix

`data/v2/strategy/s6_red_team_v1.json`: **83 checks, 0 failures, 0 blockers.**
No leakage was detected under the implemented adversarial test suite; this is
not an absolute proof of no leakage.

| Section | Checks | Result |
|---|---:|---|
| A future-information poisoning | 4 | PASS |
| B state / anchor attacks | 6 | PASS |
| C intervention attacks | 11 | PASS |
| D RNG / determinism | 7 | PASS |
| E CRN failure modes | 3 | PASS |
| F validity denominators | 5 | PASS |
| G inert / superseded | 4 | PASS |
| H compound semantics | 3 | PASS |
| I objective attacks | 5 | PASS |
| K leader ambiguity | 4 | PASS |
| L candidate-set attacks | 6 | PASS |
| M mutability | 4 | PASS |
| N probability semantics | 3 | PASS |
| O counterfactual language | 2 | PASS |
| P zero-uncertainty | 2 | PASS |
| R memory / data volume | 3 | PASS |
| S unsupported states | 1 | PASS |
| T Phase-6 compatibility | 2 | PASS |
| U authorized drift | 2 | PASS |
| V dependency / architecture | 3 | PASS |
| W serialization / identity | 3 | PASS |

---

## 7. Future-information poisoning (A)

- Parameters fit **including** the target season are refused whole-state with
  `parameter_temporal_leak` under `HISTORICAL_BACKTEST`; parameters fit through
  `season − 1` are accepted.
- No Strategy entry point (`compare_strategies`, `generate_candidates`,
  `build_candidate`, `compute_uncertainty`, `evaluate_objective`) accepts a
  future/history/oracle/actual/truth/replay argument.
- No Strategy module imports a future-history or oracle module.
- Mutating the R7 artifact's recorded historical-future fields in memory
  (`actual_winner`, `predicted_winner`, `top1`, `brier`) leaves the comparison
  identity byte-identical.

## 8. State / anchor attacks (B)

Wrong state identity → `anchor_mismatch`; wrong decision lap →
`decision_lap_mismatch`; unknown target → `target_driver_not_in_roster`;
state copied from another race → `anchor_mismatch`; decision beyond race →
`decision_beyond_race`. `build_candidate` returns a structured invalid
candidate. No nearest-match behaviour, no fallback, no silent correction.

## 9. Intervention attacks (C)

Unknown action → rejected; lowercase `"pit_now"` → rejected (no coercion);
unknown compound `PLASMA` → rejected; wet compound `WET` → rejected; empty
compound → rejected; `STAY_OUT` + compound → `malformed_intervention`; wrong
provenance / intervention version / contract version → `StrategyContractError`.
Raw duck-typed objects are rejected at the neutral simulator boundary
(`unsupported_action`, `unsupported_compound`).

## 10. RNG / determinism attacks (D)

Same request → identical paired identity and identical per-index outcomes;
chunk sizes 1/7/64/512 → identical arm identity; candidate order → identical
comparison identity; different simulation seed → different identity; bootstrap
seed-root change leaves the point estimate and paired SE unchanged (it may
move only the interval). No simulation RNG is touched by the bootstrap.

## 11. CRN failure-mode audit (E)

Broad 1k corpus, 711 defined `se_ratio = paired_se / unpaired_se` cells:
median **0.922**, mean 0.824, min 0.0, max **1.015**; **657 below 1**, **31
above 1**. By stage the medians are EARLY 0.933, MID 0.930, LATE 0.907. The
system never selects whichever SE is smaller; the canonical uncertainty remains
paired. Unfavourable cells are preserved (worst observed ratio 1.015). This is
consistent with the S3 `ADOPT_CRN_WITH_LIMITATIONS` decision and confirms no
universal variance-reduction claim is made.

## 12. Validity-denominator audit (F)

Across all 405 evaluated candidates in the broad corpus: **0 validity-set
mismatches**; every candidate used the complete-valid-pair estimator for
deltas and each arm kept its own valid denominator for aggregates
(405 000 total valid pairs). Crafted synthetic fixtures pin both-valid /
baseline-only / candidate-only / both-invalid behaviour, `NO_VALID_PAIRS` with
no imputation, exhaustive A/B bucket counts, and that the paired estimator
differs from a naive arm-aggregate subtraction when validity sets differ
(paired +1.0 vs naive −1.0).

## 13. Inert / superseded audit (G)

At 400 paired trials on a real MID state: `STAY_OUT` was `SUPPRESSED` in 41
realizations, of which 359-equivalent were inert (0 baseline pit to suppress in
the rest), `PIT_NOW` `APPLIED` 400/400, `PIT_NEXT_LAP` `APPLIED` 359 /
`SUPERSEDED` 41 / 0 double pits. Across the broad corpus the mean inert rate is
10.4%, mean supersession 2.8% (max 51.4%), `RACE_END_CANCELLED` 0. Inert,
superseded and cancelled outcomes are never counted as fully applied.

## 14. Compound-semantics audit (H)

Under a controlled uniform-mechanics fixture (all dry compounds mapped to the
same stint grid and transition distribution), `PIT_NOW SOFT`, `PIT_NOW HARD`
and `PIT_NOW` sampled produce **identical** per-index outcomes: compound
identity is the only difference. Under real parameters no per-compound pace
delta exists — the pace `mu` computation does not reference `compound` — so
compound differences are stint-grid / transition / sampling-noise only. The
baseline compound draw is always consumed under an override (draw alignment).

## 15. Objective audit (I)

Exactly three objectives; no default (`objective_value(None)` raises); no
weighted score, no `best_strategy`, no `recommendation`, no `utility`. A
synthetic fixture where A leads on win, B on podium and C on expected finish
produces three different point-estimate leaders, proving the objective
transparently selects one canonical metric and no candidate dominates by
hidden cross-metric weighting.

## 16. Uncertainty audit (J)

`n = 0` → `NO_VALID_PAIRS`, all fields `None`; `n = 1` → point estimate
defined, `paired_se = None`, `INSUFFICIENT_PAIRS`; `n < 30` → interval
withheld; constant difference → `paired_se = 0.0` with a collapsed interval;
sparse/all/no win and high-variance finish differences compute without NaN,
inf, p-values or significance terminology.

## 17. Leader-ambiguity audit (K)

A crafted fixture whose leader is a hair above a rival with a direct pairwise
interval spanning zero yields `leader_by_point_estimate` **and**
`indistinguishable_from_leader = [rival]`, with a clearly distinguishable
third candidate; the exact-tie case is inconclusive. No unique scientific
winner field exists. On the broad corpus the leader was ambiguous
(indistinguishable set non-empty) in **73/135** objective results (54%).

## 18. Candidate-set audit (L)

Exactly nine unique canonical candidates; duplicates deduplicated once;
reordered input returns canonical order; malformed manual candidates
(`("PIT_NOW","PLASMA")`, `("TELEPORT",None)`) are structured-invalid;
enum/string candidate identity equal; a candidate's result is identical
whether evaluated alone or inside a larger set (no candidate-set-dependent
RNG, no duplicate execution).

## 19. Mutability audit (M)

Before/after the full comparison + all three objectives, the `SimulationState`
identity, `SimulationConfig` identity, parameter identity, the parameter
artifact hash and the comparison scientific `to_dict()` are unchanged. All 45
broad jobs report `all_lower_layers_immutable = true`.

## 20. Probability-semantics audit (N)

`PROBABILITY_SEMANTICS == "MONTE_CARLO_FREQUENCY"`; no
`INDEPENDENT_BINARY` anywhere in Strategy source; no import of the frozen
Phase-3 winner model / `model_lab` / `sklearn` into Strategy execution.

## 21. Counterfactual-language audit (O)

Result metadata (`COUNTERFACTUAL_SEMANTICS`, the comparison limitations, the
objective limitations) contains no "would have won/finished", "best/optimal/
correct strategy", "guaranteed", "proves" or "real advantage". The Phase-7
docs contain one "best strategy" occurrence, in the plan's negated statement
"No universal best strategy is defined" (NOTE, no change). A substring
false-positive on "improves" was excluded by word-boundary scanning.

## 22. Zero-uncertainty audit (P)

A constant difference legitimately yields `SE = 0` and a collapsed interval,
but the metadata still declares `MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY` and
never uses "certain"/"guaranteed". A constant **zero** is classified
`INCONCLUSIVE` ("no Monte Carlo difference observed"), never equivalence in
reality.

## 23. Performance / memory audit (Q, R)

Measured on the deep corpus (EARLY 2020-r03-R, MID/LATE 2020-r05-R), seed
`20240101`, `pit_dynamics_enabled=True`:

| Stage | Config | candidates | comparison | S5 analysis | total | traced peak |
|---|---|---:|---:|---:|---:|---:|
| EARLY | 1k | 9 | 33.4 s | 1.4 s | **34.9 s** | 40.7 MB |
| EARLY | 10k | 3 | 140.8 s | 1.0 s | **141.8 s** | 55.3 MB |
| MID | 1k | 9 | 16.4 s | 1.5 s | **17.9 s** | 24.0 MB |
| MID | 10k | 3 | 64.8 s | 1.0 s | **65.8 s** | 38.2 MB |
| LATE | 1k | 9 | 8.5 s | 1.5 s | **10.0 s** | 15.7 MB |
| LATE | 10k | 3 | 33.9 s | 1.0 s | **34.9 s** | 29.7 MB |

The S5 analysis is a small fraction of simulation cost and never reruns a
simulation. The public `StrategyComparisonResult.to_dict()` omits the retained
per-index outcomes (payload ≈ 9.3 KB for a 3-candidate 256-trial run) and the
retained outcomes are excluded from `identity()`, so S5's data-lifetime
retention cannot leak a large per-index payload into an S7 response.

## 24. Unsupported-state audit (S)

Adversarial fixtures (labelled separately from representative metrics): wet
track (`wet_track_conditions`), neutralized (`neutralized_track_state`), red
flag (`red_flag_track_state`), unknown (`unknown_track_state`), wet compound
(`wet_compound_state`), missing tyre age (`missing_tyre_age`),
non-contemporaneous roster (`non_contemporaneous_roster_member`) and target not
in roster (`target_driver_not_in_roster`). Every one returns a structured
unsupported comparison (`supported=False`, canonical reason, no evaluated
candidate, no partial table, no silent driver dropping).

## 25. Phase-6 compatibility audit (T)

The S1 compatibility fixture (`tests/fixtures/phase7_s1_phase6_baseline.json`,
SHA-256 recorded) and `tests/test_v2_phase7_s1_phase6_compat.py` are unchanged
and pass: `intervention=None, collect_index_outcomes=False` reproduces the
captured pre-change Phase-6 baseline byte-for-byte. No regeneration. No
Phase-6 baseline drift.

## 26. Authorized-drift audit (U)

Only `v2/simulation/monte_carlo.py` differs from the Phase-6 manifest; its live
SHA-256 equals the S3-authorized `current_sha256`, its recorded historical
hash equals the untouched Phase-6 manifest hash, and no other frozen scientific
runtime file drifted. `docs/PHASE6_FREEZE_MANIFEST.json` is untouched
(SHA-256 recorded). S5/S6 introduced no simulation drift and no new freeze
conflict; no simulation runtime file was modified during S6.

## 27. Dependency / architecture audit (V)

`simulation → strategy = 0` (AST and Graphify). Strategy internal graph is
acyclic. Production Strategy modules import no `api` / `frontend` /
`model_lab` / `prediction` / `replay` / oracle / `sklearn` material. Validation
scripts depend on validation helpers only.

## 28. Serialization / identity audit (W)

`StrategyIntervention` identity is stable under dict key reorder and a
`to_dict → from_dict` roundtrip, and changes under a scientific mutation
(compound); fresh equal candidate objects have equal identity. The comparison
identity is stable under retained-outcome mutation (non-semantic) and sensitive
to scientific inputs (state, parameters, config, seed, count, target, candidate
set).

---

## 29. Historical Strategy characterization

`data/v2/strategy/s6_validation_v1.json` (`characterization`,
`characterization_by_stage`). **No recommendation accuracy, counterfactual
accuracy or "historically correct" percentage is computed** — no such ground
truth exists.

- Supported broad jobs: **45 / 45**; evaluated candidates: **405**; valid pairs:
  **405 000**; validity-set mismatches: **0**.
- Delta distributions over 405 candidates (positive = candidate improves):
  - `Δwin` mean **−0.043**, median 0.0, range [−0.326, +0.124];
  - `Δpodium` mean **−0.027**, median 0.0, range [−0.429, +0.037];
  - `Δexpected_finish` mean **−1.156**, median −0.793, range [−5.148, +0.287].
- Objective classifications: WIN 2 IMPROVEMENT / 104 DEGRADATION / 299
  INCONCLUSIVE; PODIUM 5 / 104 / 296; FINISH 4 / 331 / 70.
- Execution (mean over 405): APPLIED 0.861, SUPPRESSED 0.111
  (inert mean 0.104), SUPERSEDED 0.028, RACE_END_CANCELLED 0.0.
- Leader ambiguity (indistinguishable non-empty): EARLY 27/45, MID 24/45,
  LATE 22/45.
- `se_ratio` medians: EARLY 0.933, MID 0.930, LATE 0.907.

On this corpus the forced/delayed pit candidates are mostly not distinguishable
from baseline, and `STAY_OUT` (the near-baseline candidate) is the usual
point-estimate leader. That is an honest result of a no-traffic, no-compound-
pace simulator, not a statement that any strategy is better.

Broad 1k and deep 10k confirm interval widths shrink by roughly √10
(EARLY PIT_NOW WIN: 0.0143 → 0.0046 SE). Three 1k→10k classification flips
occur (EARLY PODIUM `PIT_NEXT_LAP` INCONCLUSIVE→DEGRADATION; MID WIN `STAY_OUT`
INCONCLUSIVE→IMPROVEMENT; LATE PODIUM `STAY_OUT` IMPROVEMENT→INCONCLUSIVE) —
expected sampling noise, not a defect.

---

## 30. Findings

Severity: BLOCKER / MAJOR / MINOR / NOTE.

| ID | Sev | Finding | Resolution |
|---|---|---|---|
| F1 | MINOR | `StrategyComparisonResult.limitations` still claimed no production uncertainty was exposed (stale after S5). | **Fixed** — reworded to describe S5's additive sampling-only view. No identity/scientific change; S1–S6 tests green. |
| F2 | MAJOR | The full 9-candidate space at 1k exceeds a comfortable synchronous budget on EARLY (~35 s; MID ~18 s, LATE ~10 s). 10k/3-candidate is 35–142 s. | **Constrained for S7** — see §31 guidance: bounded synchronous candidate subset, full 9 advanced/async, 10k explicit/manual. Not a scientific blocker. |
| F3 | NOTE | 64/99 R7 raw anchors are rejected by the frozen R7.1 contemporaneity rule; only 35 eligible. | Documented; corpus restricted to eligible anchors, exclusions reported. R7-artifact property, not a Strategy defect. |
| F4 | NOTE | `STAY_OUT` inertness (mean 10.4%), `PIT_NEXT_LAP` supersession (mean 2.8%, max 51.4%). | Surfaced per candidate; near-zero deltas never presented as equivalence. |
| F5 | NOTE | CRN is worse than unpaired in 31/711 cells (max ratio 1.015). | Preserved and reported; canonical uncertainty stays paired; no universal variance-reduction claim. |
| F6 | NOTE | No candidate systematically improves over baseline on this corpus. | Reported descriptively; not a recommendation. |
| F7 | NOTE | Leader ambiguity in 54% of objective results. | `indistinguishable_from_leader` is always emitted; no unique winner. |
| F8 | NOTE | Three 1k→10k classification flips. | Expected sampling noise; documented. |
| F9 | NOTE | No observable counterfactual ground truth; no accuracy computed. | Stated in every result's counterfactual semantics. |
| F10 | NOTE | One negated "best strategy" in `PHASE7_STRATEGY_PLAN.md`. | Legitimate statement; no change. |

**BLOCKER count = 0.**

## 31. Scientific limitations

1. Estimates are simulator-conditional Monte Carlo frequencies; alternative
   strategy outcomes are counterfactual and not observable truth.
2. Uncertainty is Monte Carlo sampling uncertainty only — not parameter,
   model-form, pit-loss, pace, traffic, compound-effect, weather or real-world
   causal uncertainty.
3. No traffic/overtaking model (free-air rejoin only) and no per-compound pace
   delta.
4. CRN shares per-`(seed, index)` stream identities, not trajectories; pairing
   is not a universal variance reduction.
5. `STAY_OUT` is frequently inert; near-zero deltas are not equivalence proofs.
6. Small-n policy withholds the interval below 30 complete pairs.
7. The representative corpus is deterministic but finite (15 eligible states ×
   3 bands); estimates remain sampling-limited.
8. `leader_by_point_estimate` is a simulator point-estimate label only.

## 32. Remaining product limitations

- No traffic/overtaking, no compound pace delta, no DNF/points, no SC/weather
  evolution, no multi-stop/multi-driver optimisation, no LLM recommendation.
- No API/frontend Strategy product exists yet (S7).
- A reduced synchronous candidate budget is required (F2).

## 33. S7 product-performance guidance

Engineering guidance only; not a scientific ranking. Derived from the measured
performance rows:

- **Default:** `simulation_count = 1000` with a **reduced synchronous candidate
  subset (≤ 4)**.
- **Full 9-candidate 1k:** explicit advanced/async request (measured 10–35 s
  across EARLY/MID/LATE).
- **10 000:** explicit advanced/manual only (measured 35–142 s for 3
  candidates; the full 9-candidate 10k path was intentionally not run and is
  out of the synchronous band).
- **Latency band:** full 9-candidate 1k ≈ 10–35 s; 3-candidate 10k ≈ 35–142 s.
- No API limits were implemented in S6.

## 34. Validation artifacts

- `data/v2/strategy/s6_validation_v1.json` — protocol, environment, eligibility
  audit, corpus, 45 broad jobs, deep 1k/10k runs, characterisation, unsupported
  audit, temporal firewall, future-channel audit, performance/memory, S7
  guidance, limitations. Generated, untracked (`/data/v2/`).
- `data/v2/strategy/s6_red_team_v1.json` — 83 red-team checks, leakage
  statement, per-cell CRN/status evidence. Generated, untracked.

## 35. Regression

- **S1–S5:** green (S1 contracts/seam/compat, S2 mechanics, S3 paired, S4
  comparison, S5 uncertainty + objectives).
- **S6 tests:** `tests/test_v2_phase7_s6_validation.py` **24 passed**.
- **Governance:** `test_v2_phase6_freeze.py` green (authorized drift only).
- **Full Python suite:** `11 failed, 2 835 passed, 5 skipped, 4 xfailed` in
  2 914 s. The 11 failures are all pre-existing and S6-unrelated:
  - the 7 documented environment-sensitive Phase-6 identity failures
    (R6 ×1 `test_pit_disabled_reproduces_r5_result_identity`; R7.1 ×6
    `test_accepted_state_matches_pre_fix_result_identity[...]`) under NumPy
    2.4.2 — same tests, same reason, no new failure;
  - 4 pre-existing Phase-4/5 integration failures (`api/main.py` hash drift
    recorded after the Phase-4/5 manifests — `api/main.py` was last changed in
    Phase-6 commit `b813ffe`; and `test_head_and_phase4_tag_intact`, which pins
    HEAD to the Phase-4 commit `4f26801` while HEAD is `6c04438`). S6 changed 0
    `api/` files and did not move HEAD.
- **API regression:** `tests/test_v2_phase6_r8.py` passes (full suite); no
  Strategy route exists.
- **Frontend:** untouched; `node --test` **97 pass / 0 fail**.
- **No simulation runtime change**; `monte_carlo.py` = S3-authorized hash.

## 36. Graphify final result

`graphify update .`: **9 725 nodes, 24 771 edges, 307 communities**.
`simulation → strategy = 0`; no Strategy cycle. Pre-existing unrelated cycles,
if any, are unchanged and outside Strategy.

## 37. Git safety

Nothing staged (`git diff --cached` empty); nothing committed; no tag created;
HEAD `6c04438` unchanged; tags `v2-monte-carlo-phase6` and
`v2-frontend-foundation` preserved. No `reset` / `restore` / `checkout` /
`clean` / `stash` / `add .` / `commit` / `tag`. Unrelated user work preserved.
S7 not started.

## 38. S6 DoD

All items satisfied: S0–S5 docs/code read; Graphify pre-audit; protocol frozen
before the corpus; deterministic eligibility-based state selection;
representative historical corpus; EARLY/MID/LATE and front/mid/back coverage;
broad 1k (45 jobs); deep 10k (3 states); future-poison, anchor, malformed
intervention, RNG/determinism, CRN failure-mode, validity-denominator,
inert/superseded, compound-semantics, objective, uncertainty boundary,
leader-ambiguity, candidate-set, mutability, probability-semantics,
counterfactual-language, zero-uncertainty, performance, memory, unsupported-
state, Phase-6 compatibility, authorized-drift, dependency/architecture and
serialization/identity audits; historical characterisation; no counterfactual
accuracy claim; findings severity assigned; BLOCKER = 0; MAJOR constrained;
validation + red-team artifacts created; report created; reproducibility
metadata recorded; S7 guidance produced; S1–S6 tests green; Phase-6 regression
and API regression checked; no simulation runtime change; frontend untouched;
Graphify updated; `simulation → strategy` remains 0; no Strategy cycle; nothing
staged or committed; no tag; S7 not started.

---

**Final verdict: S6 COMPLETE — READY FOR S7**

Finding F2 (synchronous full-candidate latency) is carried forward as binding
S7 engineering guidance, not a scientific blocker.
