# V3.8F CONSENSUS / DISAGREEMENT PRODUCT API

## Verdict

V3.8F COMPLETE — CONSENSUS PRODUCT CONTRACT VALIDATED — READY FOR V3.8G.
Productization of existing science only: no new research, no fusion, no
frontend, no serving-model promotion.

## Scientific basis (all corrected, all locked)

- D corrected gate `FUSION_RESEARCH_WARRANTED` (card `67f97c18…a298985`):
  Logistic × MC2 disagreement/complementarity empirically observed.
- E gate `FUSION_IMPROVEMENT_NOT_SUPPORTED` (card `ec6578de…`): fusion
  researched under preregistered rules and not supported.
- Therefore this product exposes MODEL, SIMULATION, and their descriptive
  DISAGREEMENT. There is no fourth probability and no fusion path.

## What F exposes

A. MODEL — frozen `V3_1B_LOGISTIC` raw independent-binary WIN probability
   (never race-normalized).
B. SIMULATION — frozen `MC2_E` mutually-exclusive simulation WIN frequency
   (never reinterpreted as Logistic-family probability).
C. DISAGREEMENT — C-verbatim comparison: signed/absolute gap
   (simulation_minus_model), descending average ranks + displacement,
   tie-safe leader sets + exact match, top-k boundary-tie WIN-ranking
   overlap + Jaccard, SE + Wilson 95% labelled finite-MC-context-only.

The product exposes evidence. It does not adjudicate the sources: no
preferred/winning source, no recommendation, no trust or quality scores.

## Endpoints (additive, existing conventions)

- `GET /v2/consensus/availability` — cheap availability, never triggers
  expensive work.
- `POST /v2/consensus/compare` — strict typed
  state/availability/model/simulation/disagreement/provenance response.

Errors mirror frozen conventions: 404 `unknown_race`, 422
`unknown_state`, 422 `consensus_unsupported` (stable machine-readable
`reason` from the B vocabulary), 503 `parameter_unavailable` on corrupt
artifacts (fail loudly, never benign fallback), 500 `internal` without
internals.

## Runtime behavior

- Providers take the anchor only. No seed, simulation-count,
  variance-mode, or configuration controls exist on any F path.
- Exact-key in-memory result cache; availability never populates it.
- Support-first: per-source AVAILABLE/UNAVAILABLE, COMPARABLE only when
  both serve; supported MC2 zeros stay numeric 0.0; missing stays absent.
- Temporal safety: exact `(race_id, anchor_lap_number,
  anchor_state_time_s)` identity with B exact-identity alignment; no
  interpolation, future lookup, forward fill, outcome labels, or D/E
  ground truth in runtime (poison-tested).
- 2025: REVEALED_HOLDOUT / PRODUCT_EXCLUDED — availability reports
  UNAVAILABLE/NOT_COMPARABLE, compare refuses 422 STATE_NOT_AVAILABLE.
  No research artifact extends product support.

## Demonstration fixtures (for V3.8G)

- Supported: `2022-r03-R` lap 2 (20 drivers, leader mismatch
  hamilton/Logistic vs sainz/MC2, top-3 Jaccard 0.5). Truth-blind
  selection: D leader-mismatch group with largest max|gap| (0.8088).
  Values verbatim from D records + checkpoint valid-trials.
- Unsupported: `2022-r19-R` lap 1 (model AVAILABLE, simulation
  MC2_STATE_INELIGIBLE → NOT_COMPARABLE) and any 2025 anchor (refused).
- Ground truth was irrelevant to fixture selection.

## Files

- `raceintel/consensus/product.py` — pure composer (imports consensus
  only; science never imports API).
- `api/v2_consensus_{schemas,service,routes}.py` + one-line router
  registration in `api/main.py`.
- `results/v3/v3_8f/` — `product_contract.json`,
  `product_validation.json`, `product_card.json`
  (`0086785cafe4298dafe171e9a7b6c0fd099d4636151568b3a6c4f7ed1f1f2a45`),
  `fixtures/`.
- `tests/test_v3_8f_consensus_{api,contract}.py` — 39/39 pass.

## Pathology

F-P1…F-P24 all zero (no fused probability, no runtime alpha, no
normalization either direction, no zero-fill, no silent drops, no target
or state mismatch, no future/outcome/D-E-truth ingress, no V3.5 vote, no
V3.4, no 2025 support expansion, no winner logic, no uncertainty
relabelling, no top-k misdescription, no public science controls, no
silent corruption fallback, no science mutation, no frontend, no upward
API dependency).

## Regression / debt

Subsystem + targeted A/B/C/corrected-D/E + prediction-API,
replay/temporal-safety, MC2-semantics, cache, and leakage suites run
separately. Full Tier-1 remains V3.8H-owned. Pre-existing V3.8
stage-entry guard debt (narrow per-stage allow-lists tripping on later
V3.8 files) was not weakened; F adds its proportional share
(`v2_consensus` modules) to the H record.

## Performance

Compare on the demo fixture completes in milliseconds (in-process
TestClient, cache hit on repeat); no MC2 launched from any F path in
tests. Broader MC2 optimization remains a separate post-V3.8 stage.
