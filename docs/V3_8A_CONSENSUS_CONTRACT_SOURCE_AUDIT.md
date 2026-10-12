# V3.8A CONSENSUS CONTRACT + SOURCE AUDIT

## Final verdict

V3.8A COMPLETE — CONSENSUS CONTRACT FROZEN — READY FOR V3.8B. Contract-only stage: no models trained, no scores built, no probabilities averaged or normalized, no frozen science modified.

## Frozen parent

- Commit: `30fe18908a41d95113c189274598269a95ef44ca`
- Tag: `v3.7-counterfactual-engine`
- Verified at entry: HEAD exact, tag resolves, working tree clean (0 lines).

## V3.7 provenance

- Card schema: `v3.7-counterfactual-engine-scientific-card-v1`
- Card identity: `a7b6d33e89d4157144fad1fa9f380b764bff0d41313995a9fae8b2bbff191fe5` (recomputed from artifact at entry).

## Scientific question

What can be learned from the agreement and disagreement between distinct predictive mechanisms viewing the same factual race state? Disagreement is information; any later fusion must earn its way through empirical evidence.

## Source inventory

Five candidates inspected against code and artifacts (details in `results/v3/v3_8a/source_audit.json`):

1. **V3.1B Logistic winner probabilities** — frozen champion (`C=0.01` RAW, 110-col `ALL_84_PLUS_V3_1_DYNAMICS_CORE`), artifact `data/v3/v3_1d/final_model_arm_b.joblib`; research-only (serving uses a separate frozen 84-col model). 2025 one-shot holdout consumed.
2. **V3.5 marginal outcome probabilities** — `LOGISTIC_CONTROL` champion + `XGB_E` research candidate; `P(finish<=1/3/5/10)` per-driver marginals with PAVA coherence; serving NONE. 2025 evaluation-only, revealed.
3. **MC2 simulation winner frequencies** — `MC2-E` arm, 5000 futures, seed 20240101; full-field `finish_position_distribution` frozen per driver (top-k derivable without new science). 2025 never read.
4. **V3.3 XGBoost winner predictions** — same winner task/semantics as V3.1B; diversity candidate; standalone superiority not established; 2025 revealed.
5. **V3.4 Logistic+XGB ensemble** — fixed convex blend (0.2 XGB / 0.8 Logistic); research-only.

## Source classification

- PRIMARY_CONSENSUS_SOURCE: V3.1B Logistic, MC2.
- SECONDARY_DIAGNOSTIC_SOURCE: V3.5 marginals (P_win target-compatible; top-k contextual), V3.3 XGBoost.
- EXCLUDED_FROM_V3_8: V3.4 ensemble — blends two admitted sources; independent-vote treatment would double-count model information.

## Probability-family taxonomy

- INDEPENDENT_BINARY_MODEL_PROBABILITY (V3.1B, V3.3): per-driver binaries, never sum to 1, must never be renormalized; simultaneous high values legitimate; model calibration error only.
- MARGINAL_THRESHOLD_PROBABILITY (V3.5): per-driver cumulative thresholds, not joint, not field-normalized; PAVA-coherent; calibration regressed out-of-time (kept as result).
- MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY (MC2): sums to 1 by construction (one winner per valid trial); MC sampling variability only — not model confidence, not real-world uncertainty.
- ENSEMBLED_MODEL_PROBABILITY (V3.4, excluded): blended binaries with compounded calibration risk.

## Logistic semantics

RAW positive-class probabilities, typed `INDEPENDENT_BINARY` (`v3_dynamics_experiment.py:296-311`); the prediction type system rejects them where race distributions are required (`predictions.py:134-143`); serving repeats the never-normalized rule. ECE ~0.009 (veto-grade, RAW retained).

## MC2 semantics

Empirical frequencies over valid simulated outcomes, one winner per trial (`results.py:38-43`); win-probability sum-to-1 and position-count invariants enforced in code (`monte_carlo.py:2211-2231`). Full-field distributions make top-k derivable from frozen outputs. Eligibility ~38% of states; dry-green only.

## V3.5 semantics

Per-driver marginal cumulative thresholds, explicitly NOT a joint finishing-order distribution, NOT MC2 frequencies (`outcomes.py`, final card, final report all agree). `P_win` is the same event as the winner label (alias `is_top1↔p_win`) and matches frozen V3.1B OOF to 3e-11 — diagnostic alignment, not identity; V3.1B remains the winner lineage.

## XGBoost / ensemble role

XGB is a same-task diversity candidate (secondary). The V3.4 0.2/0.8 blend is excluded from initial consensus to avoid double-counting.

## Source independence

Honest language only: **distinct predictive mechanisms**, not independent systems. Model sources share the ALL_84 feature family and 2018–2024 training data; MC2 shares only the RaceState(T) initialization while its generative mechanism is distinct. This shapes how agreement must be interpreted.

## Common comparison unit

`(state_id, driver_id)` with race/season/round/lap/state_time/stage metadata. Identity-based joins only — the V3.3 row-order incident is on record as why positional alignment is forbidden.

## State synchronization

EXACT STATE IDENTITY ONLY. Canonical `SimulationState.identity()` (sha, no timestamps/hosts) and `PredictionResult.align()` (identity, never positional) already exist; B must use them. No nearest-lap substitution; mismatch → UNSUPPORTED_COMPARISON, fail closed.

## Driver synchronization

Explicit per-pair support accounting (`MODEL_AVAILABLE` / `OUTCOME_AVAILABLE` / `MC2_AVAILABLE` / `PAIR_COMPARABLE` / `MULTI_SOURCE_COMPARABLE`). Never zero-fill, never silent drop. Retired/unobserved/ineligible drivers follow frozen presence taxonomy.

## Target compatibility

Compatible: V3.1B↔MC2 winner, V3.1B↔V3.5 P_win, V3.3↔MC2 winner. Context-only: V3.5 top-3/5/10 vs MC2 derived top-k (same frozen distributions). Cross-target magnitude comparison (e.g. win vs top-3) is forbidden.

## No-silent-normalization rule

Frozen invariant: NEVER race-normalize, softmax, renormalize, or simplex-project source-native outputs. Raw values preserved always; any future transform needs explicit rationale + separate evaluation.

## Agreement taxonomy

RANK / MAGNITUDE / TOP-K / WINNER-LEADER / DIRECTIONAL-THROUGH-TIME / CALIBRATION-CONDITIONAL. No single scalar.

## Rank agreement

Spearman, Kendall, top-1 agreement, top-3 overlap, rank displacement, leader disagreement — candidates for C; tie handling must be explicit in B. Rank needs no shared normalization, which is why it is the primary cross-family comparator.

## Magnitude disagreement

`|p_model − p_sim|` for same-target pairs only, explicitly a diagnostic difference between distinct generators — not an error, not evidence either side is wrong.

## Simulation sampling uncertainty

MC2 side gets sampling SE/intervals in later stages; never called model confidence or real-world uncertainty. Small disagreements may be sampling noise (Q11).

## Calibration

V3.1B RAW/ECE-veto; V3.5 frozen sigmoid with documented out-of-time regression; MC2 frequencies are not calibrated real-world probabilities by virtue of being frequencies.

## Temporal safety

All comparisons on information available at T. Poison blacklist frozen in contract (13 families: future lap time/position/gap/pit/compound/retirement/status/weather/race control/SC-VSC-red/finish/winner label/team action). Contract tests forbid them in future implementation.

## Ground-truth boundary

Historical outcomes are EVALUATION ONLY and join only in the evaluation layer — never in the predictive comparison frame.

## 2025 status

REVEALED_HOLDOUT / NON_PRISTINE for V3.1B, V3.3, V3.5 (each consumed it once); never touched by MC2; excluded from all product paths. Never called unseen/pristine; no product expansion to 2025.

## Evaluation split principles

Race-level temporal separation; no random row splits; no driver-state leakage; no future tuning. Development/calibration/comparison/evaluation periods fixed in the D protocol, not in A.

## Race-level aggregation

Primary race-macro (equal per-race weight, per V3.5 precedent); state-pooled/stage/fold views secondary. State-dense races must not dominate silently.

## Stage analysis

Frozen M0 thirds on `race_progress_frac` (`stages.py`); redefinition forbidden. Later hypothesis: mechanisms may converge/diverge as information accumulates — unclaimed until measured.

## Eligibility intersection

MC2 ~38% coverage; future evaluation must report candidate/eligible/excluded counts with reason, race, stage, and driver coverage.

## Fusion prohibition

No average, weighted average, `1−disagreement` confidence, traffic lights, majority vote, or global certainty in A (nor B/C/D). The product surface may show MODEL / SIMULATION / DISAGREEMENT side by side instead.

## Fusion hypotheses

Blending, stacking, calibration-aware combination, sim-as-feature, model-as-prior — hypotheses only, each carrying leakage/double-count/contamination/overfitting/miscalibration/semantic-mismatch risks. None implemented.

## Fusion gate

D→E outcomes: FUSION_NOT_WARRANTED / FUSION_RESEARCH_WARRANTED / BLOCKING_SEMANTIC_MISMATCH. V3.8E exists only on the middle outcome; otherwise E is skipped and disagreement itself is productized.

## Proposed architecture

Frozen artifacts → adapters → identity-safe alignment → comparison frame → metrics → historical evaluation → empirical gate → optional product. Dependency strictly V3.8 → frozen sources.

## Stage plan

A (contract+audit, this stage) → B (adapters+alignment) → C (metrics) → D (empirical evaluation) → E (fusion ONLY if D justifies) → F (runtime/API) → G (frontend) → H (freeze). Evidence gate before fusion preserved.

## V3.9 boundary

V3.8 exposes disagreement + MC sampling info; never a universal uncertainty score (V3.9 owns uncertainty intelligence).

## V3.10 boundary

No unified Intelligence Explorer; the G surface must stay composable for V3.10.

## Known limitations

Contract only (no measurements); V3.5 P_win near-duplicates V3.1B (same family); MC2 38% coverage; 2025 non-pristine for models; modest XGB diversity; persistent V3.5 top-1 weakness; wide race-level CIs (24-race holdouts).

## V3.8B readiness

B implements source adapters + identity-safe alignment per the frozen adapter/comparison-frame contracts: exact state identity, explicit support accounting, source-native values + metadata, fail-closed rules, poison blacklist, no normalization, no metrics, no fusion.
