# V3.8 Final Freeze — Model × Simulation Consensus (V3.8H)

V3.8H is the FINAL FREEZE / RELEASE stage for the V3.8 Model × Simulation
Consensus programme. No new science, no new product feature, no new UI feature.

## Final verdict

V3.8H VALIDATION COMPLETE — FREEZE APPROVED (recorded in
`results/v3/v3_8h/freeze_manifest.json`; targeted, Tier-1, frontend, graph,
and worktree gates in §§ Targeted validation / Full Tier-1 / Frontend below).

## Frozen parent

- commit `30fe18908a41d95113c189274598269a95ef44ca`
- tag `v3.7-counterfactual-engine`

V3.7 history untouched. Frozen V3.1–V3.7 scientific behavior unchanged.

## Scientific conclusion (frozen)

- V3.1B LOGISTIC: strongest predictive control.
- MC2-E: distinct simulator-conditional mechanism.
- DISAGREEMENT: empirically meaningful and productizable.
- FUSION: researched but improvement NOT supported.

Final product architecture: MODEL / SIMULATION / DISAGREEMENT. There is no
fused probability, consensus probability, combined probability, source winner,
preferred source, confidence score, or consensus score.

## Provenance chain (authoritative)

| Stage | Identity |
|---|---|
| A contract | `d0b8785a01347580125b38b311984c793c012352ce3ff175cfa3504379b9a67b` |
| B contract | `d212803f7ed7e8a8563abdd5b7686326e7094d810f415fa1468117541dfbfde7` |
| C contract | `07cf1ddd9708eaea2280b1d46492d972234f68c77cf3a59cbf412f638e3a74a8` |
| D protocol (original) | `9cbe85de7c8f0553a098a9a03d016beed80159c785b566c312502d3bf10f2ed1` |
| D card (original, historical) | `523898b3d626a7c3baffd65d2c5c921983db361faeb3feb57a7f8984f2e137f9` |
| D card (corrected, authoritative) | `67f97c185ca8cc687b59b376bc5a48776e9290d6463a05653fa1a6e18a298985` |
| E card (original, superseded) | `86d94ba7da69eb1e45aeb496a92c51d7519e70851253de043c53a332ff5f47ac` |
| E card (corrected, authoritative) | `ec6578de410f1ec8f6975e1cf4a2575aa4984967804b22a0b583fe2740948357` |
| E protocol | `dbe6a565d5a6fa688dbb8e0b3a1be05bad71457777cd2e312f9c164219b128dd` |
| F card | `0086785cafe4298dafe171e9a7b6c0fd099d4636151568b3a6c4f7ed1f1f2a45` |
| G card | `7c2313fc36e98f58a3f8fd7b3dd328d16fa5f0c3245403c2c80e970785a45391` |

## D correction (authoritative)

Correction 01 (`results/v3/v3_8d/correction_01.json`): defect class
`CORRECTABLE_D_ANALYSIS_DEFECT`; 0 prediction changes, 0 population changes,
0 MC2 reruns. Logistic better 7/8 races, MC2 better 1/8 races.

Corrected race-macro advantage (LL_logistic − LL_mc2; negative favors
Logistic): `-0.23278202`. Corrected race-level bootstrap (B=2000,
seed=987654321, unit=RACE): mean `-0.23183646`, 95% CI
`[-0.67507080, -0.00383419]`, fraction > 0 `0.0055`, fraction < 0 `0.9945`.

The old row-pooled result (mean −0.151, CI [−0.537, −0.0007]) remains
explicitly `SUPERSEDED_ROW_POOLED_BOOTSTRAP` and is never authoritative.

Corrected D gate: `FUSION_RESEARCH_WARRANTED` — sufficient distinct
signal/complementarity to justify testing fusion. Not contradictory with E:
D warranted the test, E ran it.

## E negative fusion result (authoritative)

Gate: `FUSION_IMPROVEMENT_NOT_SUPPORTED`. Primary prequential fusion
race-macro LL `0.03853` vs Logistic `0.03566` vs MC2 `0.39256`.
Fusion vs Logistic `+0.00288` CI `[−0.0011, +0.0097]` (positive = worse).
Fusion vs MC2 `−0.35403` CI `[−1.0555, +0.0019]`. Descriptive full-corpus
alpha surface reaches `1.0` (pure Logistic). Fusion research was warranted;
improvement over Logistic was not supported. Fusion is not promoted.

## Guard-debt reconciliation

Four V3.8 stage-entry/allow-list guards tripped on legitimate later-stage
V3.8 files in the intentionally accumulated working tree (api wiring,
frontend wiring, later scripts/docs). They were intentionally not weakened
during A–G. H reconciles them to the FINAL V3.8 freeze invariant: an
explicit allowlist of exactly the chartered V3.8-owned paths, the two
additive wiring files (`api/main.py`, `CommandBar.tsx`), the Tier-1 runner
reclassification, and exactly the Tier-1-driven historical-guard
reconciliations below. Forbidden modifications (frozen science, non-V3.8
paths) still fail. No test deleted, no xfail, no skip, no weakened
assertion:

- `test_v3_8a …::test_no_scientific_source_files_modified` → final freeze
  allowlist (was: only `v3_8a` paths).
- `test_v3_8a …::test_frozen_parent_exact` → frozen-ancestor invariant
  (`merge-base --is-ancestor`; passes at entry HEAD and at freeze commit;
  fails on history rewrite).
- `test_v3_8b_source_adapters …::test_no_frozen_source_modified` → final
  freeze allowlist.
- `test_v3_8c_consensus_metrics …::test_no_frozen_source_modified` → final
  freeze allowlist.
- `test_v3_8d_evaluation …::test_no_frozen_science_modified` → final freeze
  allowlist.
- `test_v3_8d_correction_01 …::test_original_d_artifacts_untouched` →
  additionally permits exactly the two Tier-1 runner reclassifications
  and the historical-guard reconciliations.

The full Tier-1 run additionally surfaced 10 stale historical guards
(V3.5A/B/C/D, V3.6A/B/D/F/H, V3.7A) tripping on chartered V3.8 paths —
the same guard-debt class V3.7H narrowly reconciled for V3.7 dirt. H
reconciles each narrowly following the V3.7H precedent (exact
`api/v2_consensus_` / `frontend/app/consensus` /
`frontend/features/consensus` admissions; V3.6A/V3.7A full-worktree
allowlists admit exactly the V3.8-owned prefixes; V3.6H HEAD pin becomes
a frozen-ancestor invariant). No science changed.

After reconciliation: ZERO guard failures.

## Architecture (final)

G frontend → F API/product → consensus product composition → C metrics /
B alignment → frozen predictive/simulation sources. Research path E →
corrected D → C → B → frozen sources. No upward imports; no cycles. Science
never imports API/frontend; frontend never imports research scripts/results;
runtime API never uses D/E empirical records as predictive inputs (gate
strings are provenance metadata only).

Runtime sources: exactly `V3_1B_LOGISTIC` and `MC2_E`. V3.4 ensemble
excluded; V3.5 P_win stays shared/derived lineage, never an independent vote.
No fusion runtime.

## Semantics (final)

- MODEL (`V3_1B_LOGISTIC`, WIN, `INDEPENDENT_BINARY`): raw positive-class
  probabilities, NEVER race-normalized.
- SIMULATION (`MC2_E`, WIN, `MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY`):
  winner frequencies with explicit valid trials.
- DISAGREEMENT: `signed_gap = p_simulation − p_model`,
  `rank_displacement = simulation_rank − model_rank`. No sign reversal.
- Supported simulated driver with zero wins → numeric `0.0`;
  unsupported/missing → `UNAVAILABLE`. `AVAILABLE/UNAVAILABLE` and
  `COMPARABLE/NOT_COMPARABLE` explicit. No drops, no zero-fill, no
  interpolation, no future fill.
- Runtime operates at factual RaceState(T). 2025 is `REVEALED_HOLDOUT` /
  `NON_PRISTINE` / `PRODUCT_EXCLUDED`.

## API (final)

`GET /v2/consensus/availability` (cheap, never launches MC2) and
`POST /v2/consensus/compare` (strict/typed). No public seed, count, or
science configuration; cache semantics unchanged; corruption fails closed;
unsupported typed; no research leaks; no fusion/preferred-source fields.
No endpoints added in H.

## Frontend (final)

Route `/consensus` + CommandBar entry. MODEL / SIMULATION / DISAGREEMENT
only — no fused/average/combined probability, score, winner, recommendation,
slider, or midpoint marker. Fixture `2022-r03-R` lap 2 is an explicitly
labeled HISTORICAL REPLAY (illustrative, not representative); fixture
`2022-r19-R` lap 1 renders simulation unavailable (not 0); 2025 unsupported.

## Pathology superset

H-P1…H-P30 aggregated in `tests/test_v3_8h_freeze.py`; all zero at freeze.

## Freeze manifest / final card

- `results/v3/v3_8h/freeze_manifest.json` (schema
  `v3.8h-freeze-manifest-v1`) — stage ownership, identities, gates,
  supersession marking, tracked modifications.
- `results/v3/v3_8h/final_card.json` (schema
  `v3.8-model-simulation-consensus-final-card-v1`) — programme summary,
  deterministically hashed.

## Targeted validation

A/B/C/corrected-D/D-correction/E/F/G/H suites, prediction equivalence,
temporal leakage, RaceState/replay safety, MC2 field semantics, API
consensus, cache behavior, frontend typecheck/focused tests/build — all
green; the four known guards green after reconciliation.

## Full Tier-1

Canonical command `.venv/bin/python scripts/run_ci_tests.py` (plus
frontend `run_ci_frontend_tests.py`, typecheck, lint, build). Zero
unexpected failures required; see freeze manifest § tier1 (recorded at
freeze time in the final report).

## Performance handoff (no change in H)

V3.8D authoritative MC2 evaluation: 281 runs × 5000 futures ≈ 5446.5 s
total (≈19.4 s/run), predominantly CPU-bound/serial. Future dedicated stage
may investigate profiling, multiprocessing, deterministic worker-independent
seeds, cache reuse, allocation, exact vectorization, serial-vs-parallel
parity. H changes nothing.

## Next-stage boundary

STOP after freeze. No V3.9. No performance optimization. Next is the
separate MC2 PERFORMANCE ENGINEERING / PROFILING STAGE before V3.9
Uncertainty Intelligence.
