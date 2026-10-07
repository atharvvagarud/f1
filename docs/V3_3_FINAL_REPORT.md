# V3.3 MULTI-MODEL LAB — FINAL REPORT

## Final verdict

V3.1B LogisticRegression remains the standalone champion. XGBoost (RAW,
110-feature arm, lr=0.03/max_depth=3/min_child_weight=5) is retained as a
diversity candidate for V3.4 ensemble research only. HGB and Extra Trees
are rejected. No serving promotion occurred in V3.3.

## Frozen parent

- Tag: `v3.2-monte-carlo-2`
- Commit: `197979d40af0c9dbf90667781d9c83e41613b047`
- HEAD equaled the parent before the V3.3 freeze commit; nothing staged at
  entry; the dirty tree contained only V3.3 A→E work plus two explained
  M0/M1 test-guard allowlist entries.

## Stage ledger

| Stage | Verdict | Identity |
|---|---|---|
| A contract | COMPLETE | `d877e8b2…399d7` |
| B harness prereg | COMPLETE | `da60e8d9…712d8` |
| C screening prereg | COMPLETE | `a8a3d8be…a4eb29a8` |
| D refinement prereg | COMPLETE | `b74a9a7c…94bca2` |
| D finalist recipe | frozen | `ca0cd5d5…ea332d` |
| E execution manifest | COMPLETE | `34188a85…51c50` |
| E XGB predictions | frozen | `71b9bb80…3b3e5d3` |

Machine-readable: `results/v3/v3_3f/stage_ledger.json`. All six identities
recomputed with their exact freeze-time schemes; all match byte-for-byte.

## Scientific question

Can any admitted non-logistic family beat the frozen V3.1B logistic
champion on out-of-time race-macro log loss, and does any non-winner merit
V3.4 ensemble research as a diversity candidate?

## Task contract

Task `winner`: binary per-driver P(is_winner | causal state at T),
INDEPENDENT_BINARY semantics, RAW probabilities, never field-normalized.

## Feature contract

Primary arm ALL_84 + CORE_26 = 110 features, hash
`e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e`.
CORE exactly 26; 3 sidecar non-CORE columns excluded; no target leakage;
identical arm for baseline and XGB final fit.

## Candidate landscape

| Family | Development primary LL | Dev delta vs V3.1B | Temporal class | D outcome | 2025 outcome | Final disposition |
|---|---|---|---|---|---|---|
| V3.1B Logistic | champion reference | 0 | — | baseline | LL 0.0634166678 | STANDALONE CHAMPION |
| HGB | no improvement | — | — | n/a (not advanced) | NOT_EVALUATED_ON_2025_BY_DESIGN | REJECT_NO_IMPROVEMENT |
| Extra Trees | no improvement (refined+calibrated worse) | — | MIXED | rejected | NOT_EVALUATED_ON_2025_BY_DESIGN | REJECT_NO_IMPROVEMENT |
| XGBoost | +0.003539, CI [-0.00381, 0.011191] | +0.003539 | MIXED | sole finalist, RAW | LL 0.0672136469, delta +0.003797 | KEEP_DIVERSITY_CANDIDATE |

## Temporal evaluation design

Outer folds D1/D2/D3 validate on 2022/2023/2024 with strictly expanding
history-only training. Inner tuning stays inside outer TRAIN; outer
validation never selects hyperparameters. D calibration uses
temporal/cross-fitted training-history predictions. 2025 was absent from
all A–D candidate science (firewall assertions in B/C/D artifacts).

## V3.3A contract

Four families admitted with documented exclusions (LightGBM/CatBoost/RF/
NN/ranking). Small preregistered grids (≤12/family), race-macro LL
primary, paired race bootstrap (seed 42, B=2000), no-ensembling rule,
2025 sealed as FINAL HOLDOUT.

## V3.3B harness

Deterministic screening harness with D1 logistic parity bit-exact vs
V3.1 lineage, 110-feature materialization parity, season-scan firewall.
Smoke-only label; no KEEP/REJECT decisions in B.

## V3.3C screening

Full D1/D2/D3 screening. HGB rejected (no improvement). ET and XGB
advanced on credible diversity/calibration value. Grids frozen after
execution began; no superseded prereg referenced downstream.

## V3.3D refinement and calibration

Controlled refinement of ET + XGB only (HGB refused by the module).
Calibrated variants tested against RAW with the M-calibration selection
rule: ET calibrated sharply worse (D3 0.203), XGB calibrated equal to
RAW, so RAW retained. Finalists exactly ["xgboost"] + baseline.

## V3.3E one-shot holdout

Manifest `34188a85…` frozen after recipe `ca0cd5d5…`, before any 2025
contact. Single XGB fit on 2018–2024 (162,728 rows, RAW, seed 42),
single prediction artifact `71b9bb80…` (26,692 states, 24 races).
HOLDOUT_REVEALED=TRUE with no_retry attestation. No alternate post-reveal
prediction artifact exists.

## Final model comparison

XGB RAW (lr=0.03, depth 3, min_child_weight 5, 300 trees) vs V3.1B
Logistic C=0.01, same 110-feature arm, same INDEPENDENT_BINARY RAW
semantics.

## 2025 results

- Baseline race-macro LL: 0.0634166678
- XGB race-macro LL: 0.0672136469
- Delta: +0.003797 (XGB worse)
- Independently recomputed from frozen parquets via state_id merge
  (separate code path from `scripts/analyze_v3_3e.py`): exact match.

## Race-level bootstrap

24 races: 11 XGB improved, 13 worsened, 0 ties. Mean delta +0.003797,
B=2000, seed 42, 95% CI [-0.003725, +0.011783]. Race is the bootstrap
unit. Independently rebuilt: CI matches to 6dp.

## Probability quality

XGB ECE 0.00888 < baseline 0.00939; XGB top-1 0.8019 > baseline 0.7941.
XGB loses overall LL, Brier (0.01963 vs 0.01858), ROC (0.98311 vs
0.98586), PR (0.80770 vs 0.82530), top-3 (0.9598 vs 0.9848).

## Temporal consistency

Development delta +0.003539 (CI spans zero) vs holdout +0.003797 (CI
spans zero). XGB failed to establish standalone superiority; out-of-time
behavior broadly consistent with development. CI-spans-zero is not proof
of equality.

## Diversity evidence

For: 11/24 races improved, ECE/top-1 slightly better, 5 top-1
disagreement races, 433 high-confidence disagreement states,
non-identical race-level behavior. Against: 13/24 worse, overall LL
worse, ROC/PR/top-3 worse, correlations still high (pred 0.950,
residual 0.923, race-LL 0.919), top-1 disagreement record not dominant
(XGB correct in 1 of 5, baseline in 2).

## Standalone model decision

NO. V3.1B LogisticRegression remains the standalone champion.

## V3.4 eligibility

XGBoost: YES — narrowly, as diversity-candidate research material (no
claim of superiority, no serving change). HGB/ET: not evaluated on 2025
by design; no holdout eligibility.

## Row-order incident

Initial E analysis reported ~0.438 LL because baseline/XGB sets matched
but row order differed during analysis (positional pairing of wrong
drivers). Reproduced here via positional merge: 0.438039. Frozen XGB
predictions were never modified, no refit occurred, no recipe changed.
Corrected identity-based analysis reproduces 0.0672136469. Classification:
ANALYSIS_ALIGNMENT_BUG, SCIENTIFIC_PREDICTIONS_UNCHANGED. Regression
test: `tests/test_v3_3f_freeze.py::test_row_permutation_invariance`.

## Leakage audit

Temporal poison/leakage suites green; A–D firewall assertions confirm
2025_CONTACT=NONE; final fit training seasons exactly 2018–2024;
feature hash identical between contract and final fit; calibration fit
data inside outer-train history only.

## Artifact provenance

Contract chain A→B→C→D→E verified byte-for-byte at freeze time (E
manifest script asserts) and re-verified in F by exact-scheme
recomputation. Grids frozen after execution began. D recipe predates E
reveal (mtime-ordered, plus frozen_at/revealed_at timestamps).

## Reproducibility

Documented commands re-verified: A–E hash recomputation, C/D analysis
rebuild from OOF, E analysis rebuild from frozen holdout predictions,
row-alignment invariance, focused V3.3 tests. No notebook/manual-only
scientific step.

## Tests

Focused: A14 + B20 + C17 + D20 + E20 + F7 = 98 passed. Full Tier-1
(`pytest tests/`) green at the freeze boundary; see
`results/v3/v3_3_freeze.json` for exact counts.

## Known limitations

Single 24-race 2025 holdout; small preregistered grids; only one
challenger reached the final holdout; XGB standalone superiority not
established; XGB diversity evidence modest, not proof ensemble will
improve; RAW XGB retained; HGB/ET not evaluated on 2025 by design;
row-order analysis incident corrected from immutable predictions; V3.4
ensemble benefit untested; no serving promotion in V3.3.

## Frozen conclusions

V3.1B Logistic: STANDALONE CHAMPION. HGB: REJECT_NO_IMPROVEMENT. Extra
Trees: REJECT_NO_IMPROVEMENT. XGBoost: KEEP_DIVERSITY_CANDIDATE —
eligible for V3.4 ensemble research, does NOT replace V3.1B.

## Next phase

V3.4 may research ensembles using XGB as a diversity candidate against
the frozen V3.1B champion. No model, feature, calibration, metric, or
scientific decision from V3.3 may be revisited without a new
preregistration.
