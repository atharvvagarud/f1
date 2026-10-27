# F1 Intelligence V3 — Final Programme Synthesis

Status: **V3_PROGRAMME_FROZEN** (release freeze, no further V3 science).
Parent: `v3.11-mc2-coverage` (`7664963`).
Top-level human-readable V3 scientific record. Machine-readable companions live
under `results/v3/final/`.

## 1. Objective

V3 is production-quality race intelligence built on:

- temporal-safe historical state reconstruction (`RaceState`),
- predictive modelling (winner prediction over frozen dynamics features),
- simulation (MC2 over eligible states),
- decision analysis (strategy comparison, counterfactuals),
- explainability (consensus, uncertainty, Pit Wall workspace).

Every capability is fail-closed: unsupported regimes refuse instead of guessing.

## 2. Scientific principles

V3 work was held to these invariants across all stages:

- no future leakage (causal-at-T features; temporal poison tests),
- reproducibility (pinned seeds, deterministic identities, frozen artifacts),
- no fake metrics (held-out/temporal validation; no coverage-as-accuracy),
- exact state identity (eligibility by construction, not by threshold luck),
- frozen holdouts where applicable,
- simulator-conditional claims only (outputs are conditional on the simulator),
- LLM explains structured outputs only (no free-form race prediction),
- no unsupported causal claims,
- no silent probability normalization,
- no pretending unsupported regimes are supported.

## 3. Programme lineage

| Stage | Purpose | Frozen outcome | Tag / commit |
|---|---|---|---|
| V3.1 | Race Dynamics: 26 CORE features + 84 → 110 | Logistic champion (research) | `v3.1-race-dynamics` / `64c5af0` |
| V3.2 | Monte Carlo 2 (MC2-E): 5000 futures, seed 20240101 | production simulation frozen; eligibility basis | `v3.2-monte-carlo-2` / `197979d` |
| V3.3 | Multi-Model Lab (Logistic / XGB diversity) | no serving promotion | `v3.3-multi-model-lab` / `563fff2` |
| V3.4 | Ensemble (.8/.2) | mixed result; no serving promotion | `v3.4-ensemble` / `3cbd284` |
| V3.5 | Outcome Distribution | marginal thresholds only; no joint; no promotion | `v3.5-outcome-distribution` / `6df5d41` |
| V3.6 | Strategy 2.0 | simulator-conditional comparison; no utility/ranking | `v3.6-strategy-2.0` / `1eb4626` |
| V3.7 | Counterfactual Engine | controlled interventions; no alternate-history truth | `v3.7-counterfactual-engine` / `30fe189` |
| V3.8 | Model × Simulation Consensus | comparison retained; no fusion promoted | `v3.8-model-simulation-consensus` / `15df86b` |
| V3.8P | MC2 performance optimization | frozen perf contract (§7) | `v3.8-mc2-performance` / `32466c4` |
| V3.9 | Uncertainty Intelligence | disagreement + MC precision; no scalar score | `v3.9-uncertainty-intelligence` / `fb0d8d8` |
| V3.10 | Pit Wall | primary integrated workspace; frozen | `v3.10-pit-wall` / `2c00e7e` |
| V3.11 | MC2 Coverage Expansion | terminal 3678/9644 (38.14%); VSC insufficient evidence; SC/yellow/red/wet not started | `v3.11-mc2-coverage` / `7664963` |

Main limitations carried into the freeze: MC2 covers 38.14% of candidate
states; strategy authority between Phase-7 and Strategy 2.0 is
`AUTHORITY_NOT_YET_FORMALIZED` (both mounted); VSC/SC/wet/yellow/red remain
unsupported. Full per-stage evidence stays in the frozen stage docs, cards,
and `results/v3/` artifacts; this synthesis does not rewrite them.

## 4. Canonical production stack

- **RaceState**: `raceintel/race_state/` (+ `raceintel/features/`).
- **Features**: frozen dynamics (110: 84 + 26 CORE).
- **Winner model**: serving path `ml/inference.py` over `results/models`
  multilap checkpoints (logreg/hgb/xgboost; majority-vote ensemble +
  single-model selection). Research champion: V3.1B Logistic. V3.3/V3.4
  candidates were NOT promoted.
- **MC2**: `raceintel/simulation/` (engine + `mc2/` kernel + `monte_carlo.py`
  compatibility surface); 5000-future campaigns; master seed `20240101`.
- **Strategy**: Phase-7 and Strategy 2.0 both mounted
  (`raceintel/strategy/`, `api/v2_strategy_*`); simulator-conditional
  comparison only; authority not yet formalized.
- **Counterfactuals**: `raceintel/counterfactual/` + `api/v2_counterfactual_*`;
  controlled interventions only.
- **Consensus**: `raceintel/consensus/` + `api/v2_consensus_service.py`;
  sources V3.1B Logistic + MC2-E; comparison only, no fusion.
- **Uncertainty**: `raceintel/uncertainty/` + `api/v2_uncertainty_*`;
  disagreement + sampling precision; no scalar score.
- **Spatial replay**: `raceintel/spatial/`, `raceintel/replay/`,
  `frontend/lib/spatial.ts`.
- **Pit Wall**: `/pit-wall` (`frontend/app/pit-wall/`,
  `frontend/features/pit-wall/`); primary integrated workspace.

Research-only (NOT production): V3.3 XGB diversity, V3.4 ensemble blend, V3.5
outcome marginals, V3.11D VSC model, V3.2F/H regime precursors.

## 5. What V3 does not claim

- no true causal effect claims from simulator outputs,
- no "optimal strategy" claim,
- no wet-regime support,
- no SC/VSC/yellow/red simulation support,
- no 100% race-state support (38.14% eligible),
- no fused probability promotion,
- no alternate-history truth.

The enforceable form of these boundaries is
`results/v3/final/scientific_claim_registry.json`.

## 6. MC2 coverage

Production MC2 coverage is pinned at **3678 / 9644 = 38.14%**.

Unsupported states fail closed by reason (STALE 3294, TRACK 1165, WET 801,
MISSING_DRIVER 354, MISSING_TYRE 198, TERMINAL 154). V3.11 proved no safe
expansion exists on current evidence: STALE is genuinely stale, NULL track is
not reconstructable, VSC evidence is insufficient (gap/spread/duration/pit
underpowered), and SC/yellow/red/wet were never started. Arithmetic and stage
pins: `results/v3/v3_11_final/coverage_reconciliation.json`.

## 7. Validation history

- V3.2F/H regime and determinism guards; MC2 parity/determinism suites.
- V3.8 performance integrity freeze (final mean ~9.22 s/state; original total
  ~88.87 s → optimized ~27.65 s) guarded by `test_perf_mc2_*`.
- V3.8/V3.9/V3.10/V3.11 stage freeze guards with pinned collection counts.
- Temporal poison coverage across regimes (future withdrawal/duration/status/
  pit/timing/tyre ignored at T).
- V3.11 terminal decision: `STOP_V3_11_COVERAGE_EXPANSION`
  (`results/v3/v3_11_final/terminal_decision.json`).
- V3 Final: authoritative Tier-1 (0 failures), frontend tests/typecheck/lint/
  build, API smoke, performance guard — recorded in the freeze report and
  `results/v3/final/test_guard_audit.json`.

## 8. Product surface

Pit Wall (`/pit-wall`) is the primary V3 experience. Expert/scientific pages
remain available but are secondary. Serving seams: `ml/` (winner inference),
`api/` (HTTP composition), `frontend/` (UI). `v2/` is a zero-importer tracked
baseline (frozen evidence, not a product surface).

## 9. Reproducibility

- Seeds: MC2 master `20240101` (historical provenance; no retraining here).
- Frozen artifacts: `results/models/` (21 checkpoint dirs), `data/v2/`,
  `data/v3/`, stage cards under `results/v3/`.
- Result manifests: `results/v3/final/` (registry, manifest, audits,
  claim registry, inventory, card, release manifest, identities).
- Tags: 12 frozen V3 tags (§3) plus `v3-final` at the freeze commit.
- Navigation: `docs/INDEX.md` first, Graphify before broad reads,
  `scripts/README.md` forward rule for any future work.

## 10. Future work (non-committed possibilities)

- Additional regime science only with new evidence/methodology under an
  explicitly reopened programme (V3.11 is terminal; nothing is scheduled).
- Post-V3 architecture/refactor (see POST-V3 ENGINEERING HANDOFF below).
- Future model research outside V3.

No V4 roadmap is created here.

## POST-V3 ENGINEERING HANDOFF

Already-audited architecture backlog (engineering/refactor tasks, NOT V3
science; frozen V3 evidence must remain immutable):

- C1 — model_lab suite orchestration,
- C2 — API registration seam,
- C4 — reconcile model worlds / v2 legacy,
- C5 — frontend client split,
- C7 — derived guard pins,
- C8 — strategy authority/legacy cleanup.

## V3 FINAL IDENTITIES

Deterministic sha256 identities (see
`results/v3/final/identity_registry.json`); recorded at freeze:

- `v3_programme_manifest.json`:
  `62bb8ba35a358e6037801c95097c4bbeb633c73c3052c247f7291ebedc404011`
- `v3_scientific_card.json`:
  `667b6cbb17b5cf485a5f8aa40f53b150aa2aa660250e3a284b5591629ac1187f`
- `release_manifest.json`:
  `5afff004e6e6deec0c5bec23b370de66bb9372fd1b47d70646405cad2bf275c3`
- `scientific_claim_registry.json`:
  `4fdf0264b8188ac725400cf610ecd01c422a97aaf56f12c874d2ca889d626b61`
- `product_authority_audit.json`:
  `949b60ca2d07c0d261bcec156425e8d30bd5a7f03204b58becdf224f55759d93`
