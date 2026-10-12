# V3.8D HISTORICAL CONSENSUS EVALUATION + FUSION GATE

## Final verdict

V3.8D COMPLETE — FUSION RESEARCH WARRANTED — READY FOR V3.8E. First empirical MODEL × SIMULATION comparison on temporally safe historical predictions; all five gate evidence classes PASS under preregistered rules.

## Frozen parent

- Commit: `30fe18908a41d95113c189274598269a95ef44ca`
- Tag: `v3.7-counterfactual-engine`

## A provenance

Contract `v3.8a-consensus-contract-v1` (`d0b8785a…9b9a67b`).

## B provenance

Contract `v3.8b-source-alignment-contract-v1` (`d212803f…1dfbfde7`). Adapters + alignment reused unchanged; zero-frequency handling follows B's native-zero rule (simulated-but-winless = source-native 0.0, AVAILABLE).

## C provenance

Contract `v3.8c-consensus-metrics-contract-v1` (`07cf1ddd…3a74a8`). All metrics reused unchanged; no redefinition.

## Protocol

`results/v3/v3_8d/evaluation_protocol.json` (`v3.8d-consensus-evaluation-protocol-v1`), written and hashed BEFORE any evaluation run. One versioned amendment (01, population rule) decided on support grounds before amended results existed.

## Protocol identity

`9cbe85de7c8f0553a098a9a03d016beed80159c785b566c312502d3bf10f2ed1` (recomputed by tests; referenced by every result artifact).

## Historical prediction provenance

- Logistic OOF: `data/v3/v3_3c/oof_baseline__D{1,2,3}.parquet` (74,605 rows, 68 races, v3_1b_baseline C=0.01) — TEMPORALLY_OUT_OF_FOLD (fold→season map asserted in code; per-fold counts 23577/24422/26606 asserted).
- XGB OOF: `oof_xgboost__D*` — same row universe (set-equality asserted).
- V3.5: `v3_5c/oof_D*` l2_logistic (proj columns) + `v3_5e/oof_xgb_e__D*` — same row universe (asserted).
- MC2: executed E_AR1_RESIDUAL at 5000/20240101 with fold-through params (2022→2021, 2023→2021, 2024→2023) — temporally safe by construction (history ≤ T + pre-season params).
- 2018–2021 have no OOF rows by design (train-only years); FINAL_FIT and 2025 artifacts never loaded.

## Evaluation population

68 OOF races sorted by (season, round); every 8th from index 2 → 8 races; per race-stage the amendment-01 lap rule; all 20 driver rows per (race, lap); 300 candidate rows. Selection uses factual metadata only (never agreement, probability, or outcome).

## OOF safety

Fold→season map exact; per-fold counts exact; winner-row structure verified (exactly one all-positive driver per race); state_id shared across all four OOF sources (set equality asserted, fail-closed).

## 2025 status

REVEALED_HOLDOUT / NON_PRISTINE / PRODUCT_EXCLUDED. Absent from the gate population (seasons ⊆ {2022,2023,2024} asserted in analysis); discussed only as excluded context.

## Primary source pair

V3_1B_LOGISTIC vs MC2_E, target WIN — same event, distinct mechanisms.

## Secondary source pairs

XGB vs MC2 (mean |gap| 0.0275), Logistic vs XGB (0.0175), Logistic vs V3.5 P_win (lineage diagnostic, mean 1.3e-05), V3.5 top-k vs MC2 derived top-k where exposed.

## MC2 configuration

Arm E_AR1_RESIDUAL, 5000 futures, seed 20240101, frozen `_prepare_state_and_mechanisms` + conditioned variance (rho 0.264, AR1). 281 runs executed (wall 5446.5s single-process, mean ~19.4s/run). No cheaper mode, no science change.

## Support intersection

Candidate 300 rows → comparable 277, excluded 23 (PREP_REFUSAL 19 incl. race-start presence refusals, ZERO_VALID_TRIALS 4). No silent drops: every exclusion carries state_id + reason. 14 (race,lap) groups across 8 races.

## Coverage

Races 20/40/1/58/20/20/60/58 rows (max share 21.7%); stages EARLY 141 / MID 80 / LATE 56; seasons 2022–2024 all represented. No single race dominates.

## Support bias

Supported vs candidate reported by race/year/stage/driver with full reason distribution. Race-start states are systematically MC2-ineligible under frozen presence rules (diagnosed, motivated amendment 01); late-race coverage dominates LATE. Generalization beyond dry-green eligible states is not claimed.

## Rank agreement

Pooled Spearman 0.637, race-macro 0.561 (bootstrap 95% CI [0.516, 0.715]); Kendall computed per group. Non-trivial but imperfect (H1 supported).

## Leader agreement

Exact-match agreement in 9/14 states; mismatch in 5 (EARLY 4, MID 1, LATE 0). Leader sets tie-safe; scope COMMON_UNIVERSE (H2 supported).

## Top-k agreement

Top-3 drivers-by-WIN Jaccard mean 0.558 over 14 groups. Labeled as win-ranking overlap, never confused with P(finish≤3) marginals.

## Magnitude disagreement

Signed gap = MC2 − Logistic. Mean |gap| 0.0318, median 0.0007, max 0.8088 — heavy-tailed. 53% of model values inside the MC Wilson interval; 130/277 rows outside it (H3 supported). Never called error/loss/miscalibration.

## MC sampling context

Per-row SE + Wilson 95% + inside-boolean; absolute-gap distribution reported against sampling scale only. Outside-interval rows are candidates for real mechanism difference, never proof beyond all uncertainty.

## Stage analysis

Group Spearman EARLY 0.598 / MID 0.731 / LATE 0.602; leader mismatches concentrate EARLY. Agreement varies by stage descriptively (H4); no direction assumed or claimed.

## Temporal trajectories

C trajectory contract applied to exact states; gap/displacement series with lap deltas; no interpolation across the 23 exclusions. Per-race descriptive trajectories retained in group records.

## Race analysis

Per-race means for Spearman, gap, and both losses (8 races). Highest/lowest disagreement races are descriptive examples post-fixation; sample unchanged because of them.

## Year/fold analysis

Folds D1/D2/D3 = years 2022/2023/2024 reported separately in stage/year views; no stability claim beyond observed ranges; 2022-heavy rows noted.

## Ground-truth evaluation

Joined AFTER alignment + metrics from OOF binary winner labels (sole-positive-driver structure verified). Never present in B/C structures (pathology P10 zero).

## Logistic predictive quality

Mean log-loss 0.0496, Brier 0.0153 (eps 1e-15 evaluation-only clipping; natives untouched; identical policy both sources).

## MC2 predictive quality

Mean log-loss 0.1851, Brier 0.0235 — pooled means dominated by a single row (MC2 p=0.0 on the actual winner, 2023-r21-R lap 3 verstappen, ll 34.5). Race-macro agrees with pooled on ranking direction (Logistic lower loss in 7/8 races; MC2 lower in exactly 1 race, 2023-r05-R). Both reported; neither alone is the conclusion.

[V3.8E preflight correction: an earlier revision of this line claimed "MC2 better in 7/8 races". That wording repeated sign-swapped `log_better`/`mc2_better` counter labels from the D run script (`v>0` counted as Logistic-better although advantage = ll_log − ll_mc2 makes `v>0` MC2-better). Per-race advantages, pooled means, and the bootstrap below are numerically unchanged and all agree: Logistic better in 7/8 races. Gate decision unaffected — COMPLEMENTARITY is symmetric. See `results/v3/v3_8e/d_preflight_audit.json`.]

## V3.5 diagnostics

P_win tracks Logistic to mean 1.3e-05 / max 0.002 — lineage confirmed, independent-information contribution negligible (H6). Never double-counted (P18 zero; single-vote rule in gate code paths).

## XGBoost diagnostics

XGB↔MC2 gap 0.0275 vs Logistic↔MC2 0.0318; XGB↔Logistic 0.0175. Genuinely different rankings of similar magnitude — useful secondary diversity, superiority never assumed or promoted (H7).

## Disagreement × outcome

Loss advantage = ll_log − ll_mc2 (positive = MC2 better). Both signs present across rows; per-race advantage splits 7–1 for Logistic–MC2 (Logistic lower loss in 7 races, MC2 lower in 2023-r05-R only). Advantage varies with signed gap and stage (distributions in artifacts). Correlation never called causation.

## Complementarity

Each mechanism strictly better (lower race-macro loss) in ≥1 race (7 vs 1, Logistic vs MC2 — corrected per V3.8E preflight; the `log_better`/`mc2_better` counter labels in D artifacts are sign-swapped but the symmetric gate criterion is unaffected); both advantage signs present at row level; leader-disagreement cases split across outcomes. Evidence of COMPARED ERROR PATTERNS (H5), not statistical independence.

## Bootstrap uncertainty

Race-level B=2000, seed 987654321, 95%: spearman mean 0.631 CI [0.516, 0.715]; abs-gap mean 0.0335 CI [0.0179, 0.0586]. Historical-evaluation uncertainty only; never MC sampling uncertainty.

[V3.8D/E reconciliation correction 01: the advantage bootstrap originally reported here (mean −0.151 CI [−0.537, −0.0007]) was produced by a row-pooled resampling implementation, not the preregistered race-level procedure. It is preserved as SUPERSEDED_ROW_POOLED_BOOTSTRAP. The corrected race-level bootstrap (observed race-macro advantage −0.2328; mean −0.2318; CI [−0.6751, −0.0038]; 0.55% of replicates > 0) is reconstructed from the unchanged D records with zero MC2 reruns. Gate unchanged (FUSION_RESEARCH_WARRANTED). See `results/v3/v3_8d/correction_01.json` and `*_correction_01.json`; originals untouched.]

## Preregistered hypotheses

H1 supported, H2 supported, H3 supported, H4 supported-descriptive, H5 supported, H6 supported, H7 supported-as-secondary. None added post-hoc.

## Exploratory findings

(EXPLORATORY) Pooled MC2 mean loss is outlier-inflated (single p=0.0 row contributes ~12% of total MC2 log-loss mass); race-macro agrees with pooled on ranking direction (Logistic lower in 7/8 races) — there is no pooled-vs-macro ranking reversal. Implication for E: robust losses / outlier-aware combination are research questions, not conclusions. [V3.8E preflight correction: an earlier revision claimed "race-macro reverses the ranking"; recomputation shows race-macro mean advantage −0.233, same direction as pooled.]

## Pathology checks

P1–P20 all zero (computed in analysis: join integrity, provenance classes, no normalization, no zero-fill, no silent drops, target gates, truth isolation, finiteness, row-order determinism verified by B/C tests, trial counts, stage fidelity, race-macro weighting, lineage single-vote, V3.4 absence, fusion absence).

## Reproducibility

12-row stratified subset (EARLY/MID/LATE, 2022–2023) gap-recomputed 12/12; MC2 seed/config fixed; C metrics deterministic. Full-corpus rerun not needed for determinism evidence.

## Fusion gate

SEMANTIC_VALIDITY PASS, COVERAGE_ADEQUACY PASS, DISTINCT_SIGNAL PASS, COMPLEMENTARITY PASS, ROBUSTNESS PASS → **FUSION_RESEARCH_WARRANTED** (deterministic from evidence, no override). Artifact `fusion_gate.json` (`v3.8d-fusion-gate-v1`).

## V3.8E decision

V3.8E MAY EXIST: a controlled, temporally safe fusion experiment that must prove improvement empirically. It must respect lineage (no double vote), outlier sensitivity, and sampling-vs-evaluation uncertainty separation.

## Known limitations

8-race deterministic subsample (not exhaustive); 2022–2024 only (no earlier OOF); single MC2 seed/config; mc2-side complementarity is one race (2023-r05-R); pooled means outlier-sensitive; advantage CI fragile; 2025 excluded; disagreement dimensions are numeric, not causal. [V3.8E preflight correction: an earlier revision wrote "logistic-side" here; the single-complementarity race belongs to MC2.]

## V3.8F readiness

If E is later skipped or fails, disagreement itself (rank/leader/gap/stage views with support accounting) is productizable as MODEL / SIMULATION / DISAGREEMENT surfaces. F needs no new science from D beyond these artifacts.
