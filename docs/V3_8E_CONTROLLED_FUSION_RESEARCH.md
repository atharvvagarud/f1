# V3.8E CONTROLLED MODEL × SIMULATION FUSION RESEARCH

## Final verdict

V3.8E COMPLETE — **FUSION_IMPROVEMENT_NOT_SUPPORTED** — temporally safe,
tightly controlled Logistic×MC2 fusion does not improve historical
out-of-time prediction over BOTH source controls. Research-only negative
result; nothing promoted to serving. STOP after V3.8E.

## Frozen parent / git safety

- Commit: `30fe18908a41d95113c189274598269a95ef44ca`
- Tag: `v3.7-counterfactual-engine`
- No frozen V3.1–V3.7 implementation or artifact modified. No V3.8A/B/C
  contract or metric modified. No staging, commit, tag, or push.
- New isolated paths only: `results/v3/v3_8e/`, `scripts/v3_8e_run.py`,
  `tests/test_v3_8e_fusion.py`, this doc.

## Revealed-corpus limitation (applies to every E claim)

V3.8E exists because D examined this historical corpus and warranted
fusion research. The D corpus is therefore REVEALED for the decision to
perform E. Source predictions remain temporally OOF, but nothing here is
pristine holdout validation, untouched confirmation, independent
confirmation, new unseen evidence, or prospective validation. Correct
framing: controlled historical fusion research on temporally OOF source
predictions, with fusion parameters evaluated prequentially/out-of-time
wherever applicable.

## D preflight audit: REPORTING_DEFECT_ONLY

Before any fusion work, the apparent D contradiction was reconciled from
existing D artifacts only (no MC2 rerun):

- `advantage = ll_log − ll_mc2`, so advantage > 0 means MC2 better.
- All 8 stored per-race advantages recompute exactly; Logistic is lower
  loss in 7/8 races, MC2 lower only in 2023-r05-R (+0.0128).
- The race-macro mean advantage (−0.233) agrees in direction with pooled
  means and with the bootstrap mean (−0.151, CI [−0.537, −0.0007],
  reproduced exactly from the frozen race-resample + row-pooled-mean
  procedure — a different statistic from the race-macro mean, hence the
  different value).
- Root cause: `scripts/v3_8d_run.py` lines 457–460 count `v > 0` as
  `log_better` although `v > 0` is MC2-better; the D report prose
  repeated the swapped labels ("MC2 better in 7/8", "race-macro reverses
  the ranking"). Both sentences corrected in the D doc with inline
  notes; empirical values, population, gate criteria, and the
  FUSION_RESEARCH_WARRANTED decision are unchanged (COMPLEMENTARITY is
  symmetric: 7 vs 1 satisfies ≥1 each either way).
- Full evidence: `results/v3/v3_8e/d_preflight_audit.json`.

## Provenance locked

A `d0b8785a…9b9a67b` · B `d212803f…1dfbfde7` · C `07cf1ddd…3a74a8` ·
D protocol `9cbe85de…10f2ed1` · D card `523898b3…f8984f2e137f9` (all
recomputed). Population 300 candidate / 277 comparable / 23 excluded
(19 PREP_REFUSAL, 4 ZERO_VALID_TRIALS). Gate FUSION_RESEARCH_WARRANTED.
Pair V3_1B_LOGISTIC × MC2_E, target WIN, 2025 absent, no FINAL_FIT.

## E protocol (frozen before results)

`results/v3/v3_8e/fusion_protocol.json`
(`dbe6a565d5a6fa688dbb8e0b3a1be05bad71457777cd2e312f9c164219b128dd`):
convex `p_fused = α·p_log + (1−α)·p_mc2` on the preregistered grid
0.0–1.0 (step 0.1); expanding-window prequential over the 8 chronological
races with warm-up 3 (smallest history giving a stable race-macro tuning
mean while retaining 5 evaluation races) and 5 evaluation races;
race-macro log-loss tuning objective on prior races only; tie-break
largest α (defaults to the Logistic champion); paired race-level
bootstrap B=2000/95%/seed 987654322; strict 4-class gate; full A–E
robustness plan; V3.5 P_win and V3.4 excluded; no normalization anywhere;
no MC2 rerun; no serving promotion under any outcome.

## Primary experiment

Selected α trajectory: 2023-r05-R → 0.9, 2023-r13-R → 0.8,
2023-r21-R → 0.8, 2024-r07-R → 1.0, 2024-r15-R → 1.0. Tuning itself
leans to the Logistic endpoint — the history already favors the
champion, yet fusion still cannot beat it.

| arm | race-macro LL | pooled LL | race-macro Brier | pooled Brier |
|---|---|---|---|---|
| Logistic | 0.03566 | 0.03384 | 0.00940 | — |
| MC2 | 0.39256 | 0.19935 | 0.02533 | — |
| prequential fusion | 0.03853 | 0.03485 | 0.01001 | — |

Primary deltas (fusion − control, negative = fusion better):
vs Logistic +0.00288; vs MC2 −0.35403. Fusion beats MC2 decisively but
loses to Logistic — the gate requires beating BOTH.

Paired race-level bootstrap (5 evaluation races): vs Logistic mean
+0.0028 CI [−0.0011, 0.0097]; vs MC2 mean −0.3504 CI [−1.0555, 0.0019].
Neither direction is supported; the MC2-side interval barely includes
zero despite the large point estimate (one-race pathology: the p=0
outlier race dominates resamples that include it).

## Robustness

- Primary includes the known 2023-r21-R lap-3 MC2 p=0.0 winner row
  (fused p=0.613 at α=0.8, ll 0.489 vs Logistic 0.266 vs MC2 34.539).
- Leave-one-race-out: dropping the outlier race flips point estimates to
  marginally favor fusion (−0.00044 vs Logistic); all other 4 subsets
  keep fusion worse than Logistic. The apparent MC2-side gain is
  outlier-race-driven, not broad-based.
- Outlier-removed exploratory: fusion still worse than Logistic
  (+0.00070). The negative verdict is NOT an artifact of the p=0 row
  hurting fusion.
- Brier agrees with log loss (fusion worse than Logistic, better than
  MC2) — no contradictory secondary signal.
- Descriptive full-corpus fixed-α curve is monotone toward α=1.0
  (pure Logistic is the DESCRIPTIVE_ORACLE_WEIGHT) — the fusion surface
  itself points at the champion endpoint, never to be mistaken for a
  deployable optimum.

## Secondary XGB diagnostic

SECONDARY_XGB_FUSION_NOT_REQUIRED — skipped to bound complexity. The
primary gate stands alone.

## Gate

FUSION_IMPROVEMENT_NOT_SUPPORTED: primary prequential fusion fails to
beat the Logistic control on race-macro log loss (+0.00288), bootstrap
supports neither direction, and LORO shows no stable two-control win.
Artifact `results/v3/v3_8e/fusion_gate.json`; card
`results/v3/v3_8e/fusion_card.json`
(`86d94ba7da69eb1e45aeb496a92c51d7519e70851253de043c53a332ff5f47ac`).

## Pathology

E-P1…E-P24 all zero (no FINAL_FIT, no 2025, no future→past or
self-tuning, no row splits, no normalization of any source or of fused
output, no zero-fill, no silent drops, no target mismatch, no V3.5
double vote, no V3.4, no native mutation, no truth in B/C, no MC2 rerun,
no oracle-as-confirmatory, no silent p=0 removal, no row-level
bootstrap, no sampling/evaluation uncertainty conflation, no sign
violation, no post-result gate change, no serving promotion, no
product/API/frontend dependency).

## Tests / regression

36/36 `tests/test_v3_8e_fusion.py` pass. Targeted regression (A/B/C/D/E
plus prediction-equivalence, temporal-leakage, MC2 semantics, V3.5
lineage, V3.1D/OOF provenance files) run separately; full Tier-1 remains
owned by V3.8H. Known accumulated guard debt: the D
`test_no_frozen_science_modified` stage-entry guard allow-lists only
`v3_8d` paths and trips on the new isolated E paths — recorded, not
weakened, for V3.8H.

## Runtime

Eval 0.003 s, bootstrap 0.019 s, total 0.03 s (277 reused records; zero
MC2 compute, as required).

## V3.8F readiness

E answers its question with a clean negative: under temporally safe,
tightly controlled conditions, Logistic×MC2 convex fusion improves over
MC2 but not over the frozen Logistic champion, and the full-corpus
surface points at pure Logistic. F may use the disagreement surfaces
from D; it needs no new science from E beyond these artifacts. Do not
start V3.8F here.
