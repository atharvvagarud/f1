# V3.4C CONTROLLED SELECTION + ROBUSTNESS

## Final verdict

ENSEMBLE_SELECTED for development: fixed convex blend w=0.2
(80% Logistic + 20% XGB). Stacker REJECT_TEMPORAL_INSTABILITY. Selection
is a development candidate for V3.4D — NOT the final frozen recipe. Ready
for V3.4D.

## Frozen parent

`v3.3-multi-model-lab` / `563fff21f94f169097079b003816181c31227aa9`;
entry tree V3.4A+V3.4B only, nothing staged.

## Contract identities

A `d6b12074…b352`, B prereg `64ca2d29…31df82`, C protocol
`d0af402c…8a37891` — all recomputed and matched before disposition.

## Selection protocol

`selection_protocol.json` operationalizes A philosophy with zero new
numeric thresholds: closed 11-blend + stacker set, directional candidacy
(pooled Δ<0), race-unit bootstrap labels, fold/stage/quality/neighbor/
complexity/tie rules, max-one-selection cap.

## B integrity verification

Independent recompute from frozen B parquets: w=0/w=1 bitwise identities,
w=0.1–0.7 pooled + per-fold LL, race counts, stage LL, Brier, ECE — all
exact (≤1e-12). No new experiment run.

## Candidate landscape

Full table (pooled Δ, fold Δs, CI, improved/worsened, stage Δs, Brier/ECE
Δs, complexity, temporal class, neighbor status) in
`v3_4c_selection_robustness.json`. Pooled improvers: w=0.1…w=0.8;
w=0.9/1.0 regress.

## Primary evidence

Beats Logistic pooled: w=0.1–0.8. Beats on all of D1/D2/D3: w=0.1–0.4
(w=0.5 D1≈0). Pooled minimum (w=0.4) treated as evidence, not selection.

## Race-level bootstrap

w=0.1 CI [−0.00164,−0.00030] CLEAR; w=0.2 CI [−0.00282,−0.00026] CLEAR;
w=0.3 hi=+0.00000 BORDERLINE; w=0.4 spans zero UNCERTAIN. B=2000/seed42/
race-unit throughout. No p-value gates.

## Temporal consistency

Robust basin w=0.1–0.4 (3/3 folds each). D1/D2 tension resolved toward
moderate weights: w=0.6+ regresses D1; stacker gains D2 then regresses
D3. w=0.2 is the cross-temporal compromise with support on every fold.

## Stage consistency

w=0.2 and w=0.4 negative in all 9 fold×stage cells — independently
reverified cell-by-cell (18/18 match B). w=0.5+ drops to 6/9 or worse.

## Neighbor robustness

w=0.2 sits centrally in the w=0.1–0.4 basin: neighbors pooled-negative
with identical fold-sign/stage patterns; smooth primary curve; no
isolated/edge/exact-precision optimum.

## Probability quality

w=0.2: Brier Δ −0.000419, ECE Δ +0.000097 (negligible), worst-race and
extremes unremarkable. w=0.3/w=0.4 cost 5–9× more ECE for unclear gain.
No tail damage.

## Complexity analysis

One fixed scalar vs learned meta-model with unevaluable D1 and unstable
D2/D3. Blend wins on simplicity; stacker shows no materially stronger
robust evidence. Complexity not rewarded.

## Stacker disposition

REJECT_TEMPORAL_INSTABILITY (D2 −0.008786 CI-excluded-zero gain followed
by D3 +0.000862 regression). Model untouched.

## Blend dispositions

w=0.0 BASELINE_CONTROL; w=0.1/w=0.3/w=0.4 ROBUST_CANDIDATE;
w=0.2 SELECTED_DEVELOPMENT_RECIPE; w=0.5–w=0.7
REJECT_TEMPORAL_INSTABILITY; w=0.8–w=1.0 REJECT_NO_IMPROVEMENT.

## Final C decision

ENSEMBLE_SELECTED (exactly one candidate; protocol cap respected).

## Selected development candidate

Fixed convex blend w=0.2 over frozen V3.1B + V3.3-XGB, RAW
INDEPENDENT_BINARY, no calibration. Identity
`98b315970408000936aa9970224234436e9cd13c2573a823fec859650b41ed87`.
Rationale: CLEAR bootstrap + 3/3 folds + 9/9 stages + Brier gain +
negligible ECE + conservative distance — explicitly not argmin (w=0.4
lower pooled but weaker support and costlier ECE).

## 2025 firewall

2025_CONTACT=NONE before and after; selection logic loaded no 2025
labels/predictions/metrics; static history only. Fail closed.

## Tests

`tests/test_v3_4c_selection.py` (22 checks incl. protocol immutability,
closed set, hash verification, neighbor logic, disposition completeness,
max-one-selected, recipe-boundary) + A/B/V3.3/metric suites. No Tier-1
(NOT_REQUIRED_RESEARCH_SELECTION_ONLY).

## Known limitations

Development-only evidence; 68-race sample; w=0.3/w=0.4 remain plausible
but weaker-supported alternatives; 2025 untouched by selection.

## V3.4D recommendation

Freeze the final authoritative recipe from the w=0.2 development
candidate (method/weight/identities/semantics/provenance) with zero 2025
influence; then conditional V3.4E. Rebuild: `freeze_v3_4c_protocol.py`
(refuses post-disposition), `analyze_v3_4c.py`, focused tests. No 2025
command by design.
