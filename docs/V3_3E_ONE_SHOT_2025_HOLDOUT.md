# V3.3E ONE-SHOT 2025 FINAL HOLDOUT

## Final verdict

V3.3E COMPLETE — HOLDOUT REVEALED — READY FOR V3.3 FINAL VALIDATION.
(XGB not promoted standalone; admitted to V3.4 ensemble research.
V3.1B remains standalone champion.)

## Frozen parent

- tag `v3.2-monte-carlo-2`, commit
  `197979d40af0c9dbf90667781d9c83e41613b047` (HEAD verified equal).

## Contract identities

- A `d877e8b2…`, B `da60e8d9…`, C `a8a3d8be…`, D `b74a9a7c…` — exact.
- D verdict `V3.3D COMPLETE — FINALISTS FROZEN — READY FOR V3.3E`.
- Finalists exactly `["xgboost"]`; recipe hash `ca0cd5d5…` recomputed
  match; recipe predates any 2025 challenger contact (no v3_3e
  artifacts existed at entry).

## Execution manifest

`results/v3/v3_3e/execution_manifest.json`, identity
`34188a8598db8c308ba288d2fc9ed8f8ec7db00c555869962affb1b77cb51c50`,
frozen with timestamp BEFORE any XGB/2025 contact. Refuses overwrite.

## Pre-reveal recipe audit

Execution loaded the D artifact directly (no transcription): family,
seasons, lr=0.03/d3/mcw5 (+300-tree/0.8/0.8/0/1.0/hist/4-cpu/seed-42
fixed block), frozen preprocessing, RAW, seed 42, threads, feature
hash, library versions — all EXACT. (One audit-tolerance fix: frozen
recipe records semantics as `"RAW"`; manifest carries the full
INDEPENDENT_BINARY/never-normalized pin. Recipe artifact itself
untouched.)

## Baseline holdout identity

Recovered canonical V3.1B 2025 parquet (26,692 states, 24 races, unique
identity, row-set equals XGB holdout set): recomputed race-macro LL
0.0634166678 == frozen headline. Never retrained.

## Holdout identity

Season exactly {2025}, 26,692 eligible states, 24 races, unique
state_ids, 110 features materialized by identity join, hash persisted
BEFORE scoring.

## Final XGB fit

ONE fit on 2018-2024 (162,728 rows, 149 races): preprocessing fit
~TRAIN-only, XGBClassifier per audited spec, ~1.7 s estimator fit.
No 2025 in train, no early stopping, no calibration. Model persisted
to ignored storage with SHA256 (research evidence only).

## Immutable prediction artifact

`data/v3/v3_3e/pred_xgb_final_2025.parquet`, SHA256
`71b9bb807a8a845e…`, validated (finite, bounds, count, uniqueness,
stable order, INDEPENDENT_BINARY) and persisted BEFORE analysis.

## No-retry gate

`HOLDOUT_REVEALED = TRUE` with timestamp; prediction hash
authoritative; execution script refuses regeneration (verified:
artifacts exist, rerun would abort). Analysis rebuilds from frozen
predictions only.

## Primary result

Baseline 0.063417 vs XGB 0.067214 → delta +0.003797. XGB does not win
standalone. (Analysis incident: first run reported 0.438 from a
row-order misalignment — sets matched, order didn't. Caught by the
+0.375 implausibility vs 0.95 prediction correlation, diagnosed via
frozen artifacts, fixed by identity-aligned reindex, re-verified by
independent recomputation. Execution artifacts were never at fault;
no refit occurred.)

## Secondary results

Brier 0.01963 vs 0.01858 (worse); ROC 0.9831 vs 0.9859 (worse); PR
0.8077 vs 0.8253 (worse); state-pooled LL 0.06685 vs 0.06308 (worse).
ECE 0.00888 vs 0.00939 (XGB WINS — first outright secondary win);
top-1 0.8019 vs 0.7941 (XGB WINS); top-3 0.9598 vs 0.9848 (worse).

## Race-level comparison

11 improved / 13 worsened / 0 ties. No rescue-by-slicing: losses are
broad-based, wins are real but insufficient.

## Bootstrap interval

Paired race 95% CI [-0.003725, +0.011783] — spans zero, almost
identical to the development interval [-0.0038, +0.0112]. The
development uncertainty estimate transferred essentially exactly.

## Development-to-holdout transfer

Development (+0.0035, tie, MIXED, D2 win, 38 improved) → holdout
(+0.0038, tie, 11/13). Standalone gap persisted (did not improve,
did not collapse); diversity partially transferred (11 improved races,
ECE/top-1 wins); disagreement volume shrank (5 races). Descriptive;
model unchanged.

## Stage analysis

Baseline EARLY 0.0749 / MID 0.0641 / LATE 0.0513. XGB gaps: EARLY
+0.0084, MID +0.0014, LATE +0.0013 — same shape as development (early
weakness, late closeness), no phase rescue.

## Probability quality

RAW only, nothing fitted. XGB ECE better, Brier worse, worst-race
0.49 vs 0.21, max prob 0.93 vs 0.97. No tail catastrophe, no
probability-quality disqualification on its own.

## Discrimination

ROC/PR slightly worse; top-1 better (+0.008), top-3 worse (-0.025).
Ranking quality mixed-positive; kept distinct from probability
quality per protocol.

## Diversity transfer

Correlation with baseline 0.950 (pred) / 0.923 (resid) / 0.919
(per-race LL); mean abs gap 0.018; 433 high-confidence disagreement
states; 11 XGB-improved vs 13 baseline-improved races; top-1
disagreements in 5 races (XGB right once, baseline twice). Modest but
genuine complementarity: XGB improves nearly half the races at a tied
overall level with better ECE/top-1.

## Final XGB disposition

KEEP_DIVERSITY_CANDIDATE — tie-level primary (11 improved, CI spans
zero), useful disagreement (ECE + top-1 wins, 11 improved races),
no tail disaster. Not primary (delta > 0); not rejected (evidence
thresholds met by rule and judgment).

## Standalone model decision

NO — XGB does not replace V3.1B. V3.1B remains standalone champion
(primary + Brier + ROC/PR + top-3). Nothing promoted to serving.

## V3.4 eligibility

YES — credible complementary out-of-time information (near-tied LL,
better ECE/top-1, 11 improved races, distinct errors). "Different"
alone was not the basis; the listed evidence was.

## Scientific card

`results/v3/v3_3e/v3_3_scientific_card.json`: question, baseline,
landscape, HGB/ET rejections, XGB development + holdout evidence,
decisions, limitations, all identities. Summary, not freeze record.

## Tests

E 20 + A/B/C/D 71 + M0/M1 guards 75 passed (no new guard entries: E
adds no model-lab training sources).
FULL_TIER1 = NOT_REQUIRED_HOLDOUT_EVALUATION_ONLY.

## Known limitations

Single 24-race holdout; one-shot by design (no retry even though
close); analysis row-order incident documented above (resolved without
refit); RAW only; serving promotion explicitly out of scope.

## Next recommendation

V3.3 final validation/freeze (Tier-1 if runtime/shared changes
justify it), then V3.4 ensemble research with XGB admitted. Not
started here.
