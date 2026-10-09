# V3.5D TEMPORAL MODEL SCREENING

## Final verdict

V3.5D COMPLETE — MODEL SCREENING COMPLETE — READY FOR V3.5E. XGB advances
as diversity candidate; HGB rejected; control untouched; 2025 untouched.
216 binary fits (192 inner + 24 outer), all preregistered, no expansion.

## Frozen parent

- Tag: `v3.4-ensemble`, commit `3cbd28470ffa211bd754d4262eb10d66d149bf00`
- D protocol `8d82448e…39dfdf78ba4`, frozen BEFORE the first challenger fit;
  the runner asserts the hash pre-fit.

## Provenance

A `15ca7c17…` → B dataset `e9ac34e5…` + features `e054c6fb…` (110) +
projection v3.5b-projection-v1 → C harness `9dfee182…` (control D1
0.221024 / D2 0.202037 / D3 0.187885 projected) → D screening.

## D preregistration

Closed set {LOGISTIC_CONTROL, HGB, XGB}; 4-config grids per family (HGB:
lr×leaves; XGB: lr×min_child around the V3.3D refined point); one shared
family config across thresholds; M6 expanding-window inner selection on
outer-TRAIN history only; tie-break lowest-score then preregistered
simplicity order (1e-6); outer selects nothing; advancement priority
primary > consistency > bootstrap > Brier/ECE > coherence > stages >
complementarity; at most two advance; null valid.

## Scientific question

Is nonlinear capacity worth carrying into V3.5E? Answer: XGB marginally
yes (diversity), HGB no. No benchmark-maximizing; evidence for E.

## Candidate families

HIST_GRADIENT_BOOSTING (sklearn, log_loss, max_iter 200, no early
stopping) and XGBOOST (pinned, 300 trees, hist CPU) — the only admitted
challengers. No ExtraTrees, no ordinal/ranking/multiclass/neural, no new
dependencies.

## Candidate grids

As preregistered (see protocol artifact). HGB prior: mission neighborhood
around tree experience. XGB prior: V3.3D refined winner (lr 0.03, depth 3,
min_child 5) neighborhood — prior engineering knowledge, zero V3.5
validation evidence. Grids unchanged after results.

## Temporal selection

Inner layouts: D1→[I1], D2→[I1,I2], D3→[I1,I2,I3] (M6 rule, verified
inner seasons never touch outer validation). Score: mean over inner folds
of threshold-mean race-macro LL. Selected (STABLE, identical all folds):
HGB {lr 0.03, leaves 15, min_leaf 20}; XGB {lr 0.03, depth 3, min_child 10}.

## Control reproduction

C logistic OOF reloaded; RAW+PROJECTED primaries recomputed: exact
(<1e-12) on all folds before any challenger evaluation. Control never
retrained.

## Selected configurations

Above. Stability STABLE/STABLE. No post-hoc search on instability (there
was none).

## Raw results

Primary raw: HGB D1 0.224122 / D2 0.207642 / D3 0.187216; XGB D1 0.210631 /
D2 0.203232 / D3 0.185460 (control raw: 0.221509 / 0.202229 / 0.187933).

## Projected results

HGB D1 0.223532 / D2 0.206436 / D3 0.187063; XGB D1 0.210427 / D2 0.202929 /
D3 0.185392 (control: 0.221024 / 0.202037 / 0.187885). Deltas vs control:
HGB +0.0025/+0.0044/−0.0008; XGB −0.0106/+0.0009/−0.0025.

## Threshold-specific results

12-cell direction matrices in `threshold_consistency.json`: HGB 7/12, XGB
8/12. XGB improves top10 in all 3 folds and top5 in D1/D3, but top1
regresses in D1 (+0.0031) and D3 (+0.0022) — win quality is the documented
reason XGB is diversity, not performance. HGB top1 regresses badly in D1
(+0.0207) and D3 (+0.0162).

## Probability quality

Mean Brier/ECE deltas vs control: XGB −0.00185/−0.00224 (both improve);
HGB +0.00025/−0.00067 (Brier regresses). Quality supports XGB, weighs
against HGB.

## Coherence behavior

Violation rates ~13.7% both (vs logistic ~5%); mean adjustments tiny
(~7e-4); projected−raw primaries ~1e-4 — projection does NOT carry either
result (RAW already shows the same pattern). No coherence rescue, no
dependence rejection; behavior reported honestly.

## Race-level evidence

Pooled 68-race deltas: XGB mean −0.00402 (36 improved / 32 worsened),
median −0.00368; HGB mean +0.00194. Per-fold tables persisted.

## Bootstrap

Paired race, B=2000/seed 42/95%: XGB pooled CI [−0.00887, +0.00029] (spans
zero; frac improved 0.53); HGB pooled CI [−0.00311, +0.00730]. Fold CIs
persisted. Uncertain superiority is why XGB is diversity, not performance.

## Temporal consistency

XGB MIXED (D1 improve, D2 parity +0.0009, D3 improve); HGB leans regression (only D3 marginally improves). Neither is consistent —
performance candidacy correctly out of reach for both.

## Stage analysis

Frozen EARLY/MID/LATE (descriptive): BOTH families improve LATE in all 6
fold-cells (HGB −0.005…−0.019, XGB −0.014…−0.019); EARLY/MID mixed. Nonlinear
capacity helps late in races — a real consistency signal, not a selection
input.

## Threshold consistency

HGB 7/12, XGB 8/12 improved cells (matrices in artifact).

## Diversity

Diagnostics only — correlations with control 0.92–0.97; XGB improves 15
control-weak races (of 36 improved); HGB 17 (of 37). Thousands of
high-confidence threshold disagreements exist. NOTHING blended, stacked, or
weighted — a later contracted experiment would own that, if ever.

## Candidate dispositions

- LOGISTIC_CONTROL: frozen control (never advances, never replaced).
- XGB: KEEP_DIVERSITY_CANDIDATE — uncertain primary superiority (mixed
  folds, CI spans zero) but pooled improvement + Brier/ECE gains + material
  complementarity + acceptable coherence; win-threshold weakness documented
  for E to weigh.
- HGB: REJECT_NO_IMPROVEMENT — pooled worse than control, gains isolated to
  one fold, Brier regresses, top1 badly regressed in two folds.
- Advancing: [xgb] (≤2 satisfied).

## 2025 firewall

2025_CONTACT = NONE. Dev seasons + tripwire + ProtectedHoldoutError +
artifact scans (names + rows) PASS. No 2025 targets/prevalence/fits/
predictions/metrics.

## Compute

216 binary fits (192 inner + 24 outer) in 745.7 s; metrics/bootstrap fast.
Within preregistered budget; no expansion.

## Tests

`tests/test_v3_5d_screening.py`. Policy: D + C + B + A + family/harness/
metrics/aggregation/temporal guards; no full Tier-1; V3.4 sentinel
untouched.

## Known limitations

Small grids by design; XGB superiority uncertain with win-threshold
weakness; HGB out; no calibration/blending/2025 in D.

## V3.5E recommendation

Carry XGB (diversity) and the frozen control into controlled refinement:
weigh win-threshold weakness explicitly; HGB stays out. E decides whether
any refinement earns out-of-time evaluation.
