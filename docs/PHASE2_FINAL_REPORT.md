# Phase 2 — Temporal Feature Engine: Final Report + Freeze (F17)

> **F17 scope:** verify the frozen Phase-2 contracts, consolidate the
> architecture, record exact versions/counts/hashes/artifacts, run the
> final quality gates, state limitations honestly, and hand off to the
> Phase-3 Model Lab. F17 introduces **no** new feature, label, mask,
> temporal rule, matrix content or ablation semantics. It does not
> train, split, evaluate, select or calibrate, and does not start M0.
>
> **Freeze verdict: PHASE 2 — COMPLETE / FROZEN.**
>
> Interpreter note: bare `python3` in this environment is a documented
> no-op shim (see `Makefile::check-python`); all commands below were run
> with the functional `/opt/homebrew/bin/python3.11`
> (Python 3.11.15, pandas 2.3.3, pyarrow 25.0.1, numpy 2.4.2,
> pytest 9.1.1; Node v22.23.1, Next.js 16.1.6). No network was used.

---

## 1. Executive summary

Phase 2 (Temporal Feature Engine) is complete and frozen. Starting from
the frozen Phase-1/D12 data platform (tag `v2-data-platform-phase1`,
commit `2fa0a7c`), F0–F16 produced:

- a frozen temporal/synchronization contract (F1);
- a machine-readable feature registry (`FEATURE_SET_VERSION=v8`, **84**
  predictive definitions) and a separate label registry
  (`LABEL_SET_VERSION=v1`, **7** targets);
- a leakage-audited, parity-proven batch engine (F3–F11, F14);
- telemetry formally deferred (F12, ADR-0001);
- a canonical, model-ready Parquet matrix (`MATRIX_VERSION=v1`,
  **189,420 rows × 106 columns**) + manifest (F15);
- a frozen ablation/experiment configuration (`ABLATION_CONFIG_VERSION=v1`)
  and 11 Model-Lab fixtures (F16).

The complete offline regression is green: **861 passed, 4 xfailed**
(Python/V2), **21 passed** (frontend node tests), typecheck/lint/build
green, and the D11 validation gate reports **43 findings / 0 failed /
0 blockers** with `fresh_env` intentionally skipped offline. No
unresolved BLOCKER or MAJOR remains.

The pipeline is sufficiently frozen, reproducible, leakage-audited and
documented for Phase 3 to begin without redefining Phase-2 semantics.

---

## 2. Phase-2 objective

Turn the frozen Phase-1 canonical data platform into an in-race
temporal feature engine: deterministic, leakage-safe predictive state
at each driver-lap (LAP_END), physically separated from post-race
labels, materialized as a canonical model-ready dataset with
experiment configuration — **without** training any model, claiming any
predictive value, or touching telemetry.

---

## 3. Entry state from Phase 1 (verified)

| Fact | Expected | Measured | Source |
|---|---|---|---|
| rich seasons | 2018–2025 | 2018–2025 | manifest `season_range` |
| rich Race sessions | 173 | 173 | manifest, D11 manifests |
| COMPLETE / PARTIAL | 171 / 2 | 171 / 2 | D11 `MANIFESTS` finding |
| PARTIAL race ids | Belgium 2021, Japan 2022 | `2021-r12-R`, `2022-r18-R` | D11 finding |
| D9 driver-lap states | 189,420 | 189,420 | manifest `source.d9_states.rows` |
| race-driver outcomes | 3,458 | 3,458 | manifest `source.race_driver_labels.rows` |
| races | 173 | 173 | manifest `race_count` |
| telemetry | absent | absent | D11 `TELEMETRY`; ADR-0001 |
| Phase-1 freeze tag | `v2-data-platform-phase1` | commit `2fa0a7c` | `git rev-parse` |

Entry baseline at F17 start: 861 passed / 4 xfailed / 21 frontend;
F16 offline D11 = 43 / 0 / 0 (`fresh_env` skipped); historical complete
D11 baseline = 44 / 0 / 0 (with `fresh_env`). No telemetry active.

---

## 4. Stage completion F0–F16

| Stage | Objective | Output | Evidence (code/tests/artifacts) | Status |
|---|---|---|---|---|
| F0 | Verify Phase-1 handoff, no drift | `docs/PHASE2_F0_HANDOFF_VERIFICATION.md` | measured artifact table; git delta planning-doc-only | COMPLETE |
| F1 | Freeze temporal/sync contract | `docs/PHASE2_TEMPORAL_SEMANTICS.md` | semantics contracts §1–23; edge-case audit §10 | COMPLETE |
| F2 | Registry + parity skeleton | `v2/features/{contracts,registry,engine}.py`; `docs/PHASE2_FEATURE_REGISTRY.md` | `tests/test_v2_features_f2.py` (30) | COMPLETE |
| F3 | Primitive temporal operators | `v2/features/temporal.py`; `docs/PHASE2_TEMPORAL_OPERATORS.md` | `tests/test_v2_features_f3.py` (38) | COMPLETE |
| F4 | D9 factual passthrough | `v2/features/passthrough.py`; `docs/PHASE2_D9_PASSTHROUGH.md` | `tests/test_v2_features_f4.py` (22) | COMPLETE |
| F5 | Eligibility + pace | `v2/features/pace.py`; `docs/PHASE2_PACE_FEATURES.md` | `tests/test_v2_features_f5.py` (31) | COMPLETE |
| F6 | Gap engine | `v2/features/gaps.py`; `docs/PHASE2_GAP_ENGINE.md` | `tests/test_v2_features_f6.py` (22) | COMPLETE |
| F7 | Relative/teammate/field/traffic | `v2/features/context.py`; `docs/PHASE2_RELATIVE_FIELD_CONTEXT.md` | `tests/test_v2_features_f7.py` (28) | COMPLETE |
| F8 | Rates + momentum | `v2/features/rates.py`; `docs/PHASE2_RATES_MOMENTUM.md` | `tests/test_v2_features_f8.py` (20) | COMPLETE |
| F9 | Race-control + weather context | `v2/features/environment.py`; `docs/PHASE2_ENVIRONMENT_CONTEXT.md` | `tests/test_v2_features_f9.py` (21) | COMPLETE |
| F10 | Past-only priors + grid | `v2/features/priors.py`; `docs/PHASE2_PRE_RACE_PRIORS.md` | `tests/test_v2_features_f10.py` (26) | COMPLETE |
| F11 | Thin domain interactions | `v2/features/interactions.py`; `docs/PHASE2_INTERACTIONS.md` | `tests/test_v2_features_f11.py` (15) | COMPLETE |
| F12 | Telemetry ADR revisit | `docs/PHASE2_TELEMETRY_REASSESSMENT.md` | `tests/test_v2_features_f12.py` (10); decision KEEP DEFERRED; no telemetry module/column | COMPLETE |
| F13 | Label join contract | `v2/labels/{contracts,builder}.py`; `docs/PHASE2_LABEL_CONTRACTS.md` | `tests/test_v2_labels_f13.py` (20) | COMPLETE |
| F14 | Combined leakage + parity | `tests/f14_helpers.py`; `docs/PHASE2_LEAKAGE_PARITY_AUDIT.md` | `tests/test_v2_features_f14.py` (41) | COMPLETE |
| F15 | Canonical matrix | `model_matrix.parquet` + `manifest.json`; `v2/features/build_matrix.py` | `tests/test_v2_features_f15.py` (39) | COMPLETE |
| F16 | Ablation config + fixtures | `v2/experiments/feature_sets.py`; `ablation_config.json`; `docs/PHASE2_ABLATION_CONFIG.md` | `tests/test_v2_experiments_f16.py` (36) | COMPLETE |

No stage is marked complete on documentation alone: every row above has
executable tests and/or a verified materialized artifact.

---

## 5. Final architecture

**Feature path**

```text
Phase-1 canonical sources (D5/D6/D7)
        ↓
D9 driver-lap race state (189,420 rows, LAP_END state_time_s)
        ↓
Temporal operators (F3: prefix / latest≤T / sync / snapshots)
        ↓
Feature families F4–F11 (passthrough, pace, gaps, context, rates,
                         environment, priors, interactions)
        ↓
84-feature predictive surface (FEATURE_SET_VERSION=v8)
        ↓
Canonical F15 matrix (model_matrix.parquet + manifest.json)
        ↓
Manifest-controlled loader (load_features / load_labels / load_task)
        ↓
F16 named feature configurations (ALL_84, cumulative, LOGO, baselines)
        ↓
Phase-3 Model Lab            (NOT STARTED — M0 next)
```

**Label path (isolated)**

```text
Phase-1 race-driver results (D5 results → D9 race_driver_labels)
        ↓
F13 label builder + contracts (LABEL_SET_VERSION=v1, 7 targets)
        ↓
labels / task eligibility (companion classified_flag)
        ↓
F15 label join (many-to-one on race_id, driver_id)
        ↓
Phase-3 task loader (load_task → (X, y, eligibility_mask))
```

**Firewall:** feature calculators never consume the label builder,
target values, or target-race final results. The only shared edge is
the *name* guard set `CANONICAL_LABEL_NAMES` (metadata only). The F10
historical-priors exception consumes strict `H < R` historical result
information, which is the approved and tested exception. F15/F16 are
assembly/config layers and may legitimately know both sides.

---

## 6. Temporal semantics (consolidated — not redefined)

- Target state uses only information observable at or before `T`
  (`state_time_s` = accepted LAP_END clock).
- `lap_number` is per-driver progress, **not** a global race clock;
  equal lap numbers are not simultaneous.
- Rivals synchronize to the latest state with `state_time_s <= T`
  (tie-broken deterministically); no fall-forward, no `nearest(T)`, no
  future-nearest.
- Same-lap future rival states are forbidden (real dry same-lap spreads
  reach 121 s; red 1,320 s).
- Stale rival ≠ retired; no global staleness cutoff; staleness is
  provenance, consumed per feature.
- Final result/status cannot define running state; no retirement
  inference from future absence.
- Weather uses backward as-of joins; untimestamped race-control
  messages are never attached.
- Priors use strict historical `H < R` chronology (season/round order,
  never lexical race_id).
- Labels are post-race and physically separated from features.
- Interactions inherit approved primitive semantics only.

Full normative text: `docs/PHASE2_TEMPORAL_SEMANTICS.md`.

---

## 7. Feature inventory (derived programmatically)

`FEATURE_SET_VERSION = v8`; `build_f11_registry()` → **84** definitions,
all `predictive_eligible`. Registry fingerprint
`a04d5475e8ac113bfffe8af3ba35db5dedf127d0306803dcb71332c5be863fe6`.
No handwritten conflicting inventory exists.

**By registry family (predictive):**

| family | n | family | n |
|---|---:|---|---:|
| weather | 11 | stint | 7 |
| race_control | 10 | tyre | 5 |
| pace | 8 | driver_prior | 5 |
| gap | 8 | field | 5 |
| constructor_prior | 4 | teammate | 4 |
| circuit | 3 | race_state | 3 |
| interaction | 3 | momentum | 2 |
| rate | 2 | traffic | 2 |
| relative | 1 | grid | 1 |

**By temporal rule:** `driver_prefix` 23, `synchronized_field` 24,
`target_state` 17, `past_races` 12, `backward_asof` 7,
`pre_race_constant` 1.

**By synchronization:** `none` 60, `synchronized_field` 19,
`synchronized_rival` 5.

**By status:** `passthrough` 23, `candidate` 61 (no `deferred` is
predictive).

**By missingness policy:** `null_if_insufficient_history` 30,
`preserve_source_null` 24, `null_if_no_sync_state` 13,
`null_if_not_applicable` 13, `null_if_invalid_geometry` 4.

Documented per-stage inventories: `docs/PHASE2_FEATURE_REGISTRY.md`
and `docs/PHASE2_ABLATION_CONFIG.md` §6.

---

## 8. Primary semantic group counts (F16, verified programmatically)

| Group | Count |
|---|---:|
| STATE | 23 |
| PACE | 12 |
| GAPS | 8 |
| FIELD_CONTEXT | 12 |
| RATES_MOMENTUM | 4 |
| ENVIRONMENT_HISTORY | 9 |
| PRE_RACE_PRIORS | 13 |
| INTERACTIONS | 3 |
| **Total** | **84** |

`partition_audit()` confirms each feature assigned exactly once: 84/84,
zero unassigned, zero multiply assigned. `ALL_84` equals the F15
manifest `predictive_columns` (list equality verified).

---

## 9. Label contracts (F13)

`LABEL_SET_VERSION = v1`; `build_label_registry()` → **7** definitions.
Grain is `(race_id, driver_id)` for CANONICAL targets and
`(race_id, driver_id, lap_number)` for SPECIFIED state-dependent
formulas (materialized only in F15).

| Target | Type | Status | Grain | Source lineage |
|---|---|---|---|---|
| `final_position` | int64 (ORDINAL) | CANONICAL | race-driver | `race_driver_labels.position_final` |
| `is_winner` | bool (BINARY) | CANONICAL | race-driver | `race_driver_labels.winner_flag` |
| `is_podium` | bool (BINARY) | CANONICAL | race-driver | `race_driver_labels.podium_flag` |
| `scored_points` | bool (BINARY) | CANONICAL | race-driver | `race_driver_labels.points_finish_flag` |
| `position_change_from_state` | int64 (CONTINUOUS) | SPECIFIED | race-driver+lap | state `position`, label `position_final` |
| `gains_position_by_finish` | bool (BINARY) | SPECIFIED | race-driver+lap | `position_change_from_state > 0` |
| `loses_position_by_finish` | bool (BINARY) | SPECIFIED | race-driver+lap | `position_change_from_state < 0` |

Companion/source semantic field `classified_flag` remains in the F15
matrix (non-predictive, `label_companion_columns`) so ordinal
eligibility is reconstructible; it is **not** one of the 7 targets.
`is_winner`/`is_podium` cardinality: exactly 1 / exactly 3 per race;
`scored_points` ≡ points > 0 (half-points included). DNF/reliability is
**deferred**, not hidden.

---

## 10. Ordinal safety

- Non-null `final_position` ≠ ordinal-training eligibility.
- Measured state-level: non-null `final_position` = **189,420**;
  `eligible_ordinal_final_position` True = **178,963**.
- W/D back-rank numeric source values (classified_flag=False) are
  excluded because they are source orderings, not earned finishing
  slots.
- `load_task("final_position")` returns the ordinal mask, never
  `final_position.notna()`. Verified: `mask.sum() == 178,963`.
- Gain/loss masks: `eligible_gain_loss` True = **189,126** (294
  position-null states excluded).
- Binary masks (`winner`/`podium`/`points`) = **189,420** each (the 3
  fully-null W rows belong to the 6 stateless entrants with zero D9
  states, so no state row carries a null).

---

## 11. Canonical matrix contract (F15, verified not rebuilt)

| Property | Value |
|---|---|
| `MATRIX_VERSION` | `v1` |
| entity | `model_matrix` |
| rows | 189,420 |
| columns | 106 |
| metadata columns | 9 |
| predictive columns | 84 |
| label columns | 7 (+1 companion `classified_flag`) |
| task-eligibility masks | 5 |
| season range | 2018–2025 |
| races | 173 |
| canonical sort | `season, round_no, race_id, state_time_s, lap_number, driver_id` |
| identity | `(race_id, driver_id, lap_number, state_time_s)` + `state_id` |
| label join | many-to-one; matched 189,420; missing 0 |
| content hash (recomputed) | `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db` |
| schema hash | `b1ccbc62380da8e841e7b2d78d8d37aac2b67c72b0306a2495fbabc3fb224f0e` |
| feature registry fingerprint | `a04d5475e8ac113bfffe8af3ba35db5dedf127d0306803dcb71332c5be863fe6` |
| label registry fingerprint | `0a4d0bb6369f880add679731f46e992f0bee98b2930caeefa392297cf29515cd` |
| source fingerprints | see §18 |

Column classification is exhaustive and non-overlapping (verified: no
unclassified or duplicate columns; predictive ∩ label = ∅). No matrix
rebuild was required for F17.

## 12. Matrix immutability

Fingerprinted **before** F17 work and re-verified at the end of the
regression battery (which includes F15 idempotent-rebuild tests):

```
sha256(model_matrix.parquet)  = b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3
sha256(manifest.json)         = b6a63f5eb0577906ee6496d05c4f7a20c3eb79f2f8048d4ff06acb764d6cbc62
sha256(ablation_config.json)  = bb59d936b14552779a4ab192c4d3e9c9d1e2ff31e2ef8608b30c44ed86f2f5a7
content_hash (recomputed)     = d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db  (unchanged)
```

F17 did **not** modify the canonical matrix or manifest.

## 13. Ablation config contract (F16)

| Property | Value |
|---|---|
| `ABLATION_CONFIG_VERSION` | `v1` |
| required `FEATURE_SET_VERSION` | `v8` |
| required `LABEL_SET_VERSION` | `v1` |
| required `MATRIX_VERSION` | `v1` |
| semantic hash (file = recomputed) | `c88bcbaafe72ff2a615f24563d631f4e313cbc1d41e23b3818d3f9d86f6b087c` |
| primary partition | 8 groups, 84/84 exactly once |
| cumulative sets | C0…C7 (23→84, monotonic, C7 == ALL_84) |
| LOGO sets | 8 `ALL_MINUS_<GROUP>` with interaction-dependency removal |
| baselines | `CURRENT_ORDER_ONLY` (1), `MINIMAL_RACE_STATE` (3) |
| ALL_84 | equals F15 manifest `predictive_columns` (verified) |
| fixtures | 11 canonical `state_id`s, no train/test label |
| config file sha256 | `bb59d936b14552779a4ab192c4d3e9c9d1e2ff31e2ef8608b30c44ed86f2f5a7` |

Interaction dependency policy confirmed: cumulative appends
INTERACTIONS last; LOGO removes interactions whose required primitive is
in the removed group. `validate_manifest_compatibility` fails loudly on
version drift, count drift, reordering, or a forbidden column.

## 14. Config immutability

The F16 machine-readable export was not rewritten. `semantic_hash()`
recomputed from code equals the committed file's `config_hash`, and the
file's byte hash is unchanged across F17. Regeneration, if performed,
is byte- and hash-identical (`render_ablation_config` is deterministic).

---

## 15. Temporal safety summary

All Phase-2 temporal safety gates from `V2_PHASE_2…` §48 hold:
state-time contract documented; sync rule documented and tested; no
future lap/rival/weather/race-control/pit-stint access; priors past-only
(H<R); labels cannot enter the feature schema; no DNF target; D9
referenced not reimplemented; telemetry untouched. See §6 for the
consolidated rule list.

## 16. Leakage / red-team evidence (F14)

- **20 threat classes** (A–T) frozen in `tests/f14_helpers.py::THREAT_MODEL`.
- **84-feature dependency manifest** (name, family, version, temporal
  rule, sync, exact sources, status, allowed/forbidden mutations);
  every entry forbids LABELS and IDENT.
- **Negative controls:** all 10 forbidden mutation classes are `NO` for
  every active family; 10 targets × 10 forbidden mutations = 100 cases
  green.
- **Positive controls:** eligible `H<R` prior rewrite moves dependent
  priors and nothing else; factual grid rewrite moves only
  `grid_position` + `positions_from_grid`.
- **Future own-state / rival attacks:** extreme mutation, insertion
  (incl. T+0.001 same-lap rival) and deletion leave all 84 features
  bit-identical.
- **Same-lap adversary:** real 2019-r04 pair; the system uses the
  latest rival `≤ T`, never the same-lap future row.
- **Weather / race-control attacks:** future obs/transitions cannot
  change outputs; backward-only anchors proven.
- **Current/future result attacks:** radical rewrite of race-R and
  future-race outcomes leaves all 84 features identical.
- **Label firewall:** radical label rewrite leaves all-84 recompute
  identical; engine has no labels input by construction.
- **Row shuffle / duplicate defense / single-batch parity /
  deterministic rebuild / static future-pattern audit:** all green
  (no `shift(-1)`, `bfill`, `center=True`, `merge_asof`, executable
  `nearest`; duplicate keys fail explicitly).

This is evidence from an adversarial test suite, **not** a mathematical
proof: *no leakage was detected under the implemented adversarial test
suite.*

---

## 17. Feature / label firewall (re-verified statically)

- Feature calculators (`passthrough`, `pace`, `gaps`, `context`,
  `rates`, `environment`, `priors`, `interactions`, `temporal`,
  `engine`) import no label builder/registry/targets.
- `v2/features/registry.py` imports only the **name** guard
  `CANONICAL_LABEL_NAMES` (metadata-only, no values).
- `v2/features/build_matrix.py` is the **assembly layer**, permitted to
  know both features and labels; it joins labels but computes no feature
  from them.
- No feature column overlaps a label column (predictive ∩ label = ∅).

Distinction preserved: **calculator firewall** (strict) vs **assembly
layer** (may bridge).

## 18. Telemetry final status

`TELEMETRY = DEFERRED` (F12 decision A: KEEP DEFERRED; ADR-0001
Accepted). No telemetry module, column, family or artifact exists in
the 84/MATRIX. A frozen activation checklist exists
(`docs/PHASE2_TELEMETRY_REASSESSMENT.md` §16, 9 conditions incl. a
bounded Phase-3 experiment, exact formulas/units/temporal rule, full
173-race coverage audit, mutation proof, <10 MB representation,
measured cost, era robustness, and material held-out improvement).
F17 did not revisit the decision.

## 19. Feature coverage summary (no imputation)

Group-level mean / max null fraction over 189,420 states (from the F15
manifest null counts):

| Group | n | mean null | max null |
|---|---:|---:|---:|
| STATE | 23 | 0.017 | 0.321 |
| PACE | 12 | 0.089 | 0.271 |
| GAPS | 8 | 0.057 | 0.134 |
| FIELD_CONTEXT | 12 | 0.046 | 0.167 |
| RATES_MOMENTUM | 4 | 0.184 | 0.285 |
| ENVIRONMENT_HISTORY | 9 | 0.120 | 0.888 |
| PRE_RACE_PRIORS | 13 | 0.062 | 0.346 |
| INTERACTIONS | 3 | 0.456 | 0.695 |

Expected structural missingness: minimum-history pace/rates (early
laps); unavailable priors for early careers/circuit editions; invalid
gap geometry (red/SC/suspension); weather availability; classification
and task eligibility. Season and stage coverage are recorded in
`docs/PHASE2_CANONICAL_MATRIX.md` §§32–33. Missingness is preserved
exactly as produced; **no imputation** occurs anywhere (zero `fillna`
in feature/label code).

## 20. Data quality summary (Phase-1 facts carried forward)

173 rich Race sessions (171 COMPLETE, 2 PARTIAL: Belgium 2021, Japan
2022); 189,420 D9 states; official result labels; no fabricated
completion; 3,458 race-driver outcomes; historical Tier-B support
(76 seasons, 1,149 races, 25,784 results) for priors. Verified against
the frozen manifests.

---

## 21. Known data limitations

- Rich-data era is 2018–2025 only (historical Tier-B is results-only).
- Two PARTIAL race sessions (Belgium 2021, Japan 2022); no universal
  modelling exclusion is encoded.
- Weather/race-control source coverage differs by season (2018 sparse).
- Race-control representation limitations: 69/14,992 untimestamped
  messages never attached.
- Telemetry deferred (ADR-0001).
- Early-history missingness for pace/priors (structural).
- Historical prior source semantics: past-race aggregates from Tier-B,
  not driver-skill ratings.
- W/D classification semantics: back-rank numerics are source
  orderings; ordinal use must gate on `classified_flag`.
- State-dependent outcome interpretation (e.g. gain/loss) is not
  overtaking.
- Current features do not infer retirement.
- No future information is intentionally used.

## 22. Known feature limitations

- **PACE:** neutralized-lap policy is heuristic factual eligibility,
  not "true clean air".
- **GAP:** structured timing geometry; invalid/red/lapped states may
  produce null seconds.
- **TRAFFIC:** the 2 s threshold is a frozen feature definition, not
  universal DRS truth.
- **PACK:** the 5 s threshold is descriptive, not a physical cluster
  model.
- **RATES:** historical slopes, not forecasts (no catch-time).
- **POSITION CHANGE:** not overtakes.
- **PRIORS:** historical summaries, not driver skill ratings.
- **INTERACTIONS:** three explicit hypotheses, not proven useful.
- **TELEMETRY:** deferred.

## 23. Modeling non-claims (explicit)

Phase 2 has **not** demonstrated: predictive superiority; model
accuracy; calibration; causal feature importance; usefulness of all 84
features; usefulness of interactions; a best model; or production
probability quality. Those are Phase-3 questions. No metric, model,
split or result exists in Phase 2.

---

## 24. Reproducibility (commands verified from code/Makefile)

All offline; use a functional interpreter (e.g. `python3.11`).

```bash
# Full Python/V2 regression (includes F15 matrix idempotency/parity)
python3.11 -m pytest tests/ -q

# Canonical matrix build / validation (idempotent; --force to rebuild)
python3.11 -m v2.features.build_matrix --root . [--force]

# Ablation config generation is code-driven (write_ablation_config);
# validation is via the F16 test suite:
python3.11 -m pytest tests/test_v2_experiments_f16.py -q

# F17 freeze/loader smoke (ad-hoc, not committed):
#   load manifest -> load matrix -> resolve ALL_84 -> load binary task
#   -> load ordinal task/mask -> resolve fixture -> failure tests

# D11 offline validation gate (no network; fresh_env intentionally skipped)
python3.11 -m v2.d11 --root . --skip-fresh-env

# Frontend / build battery (Makefile)
make test-frontend
make typecheck
make lint
make build
```

No network is required for the frozen build when the source artifacts
and cache are present. D11 documents `fresh_env` as the only network
step.

## 25. Artifact catalog

| Artifact | Location | Version | Size/Rows | Semantic hash | Regenerable | Git | Purpose |
|---|---|---|---|---|---|---|---|
| D9 state source | `data/v2/processed/driver_lap_state_d9/` | D9 | 189,420 rows | src fp `66711cb6…` | yes (no network) | gitignored | predictive basis |
| race-driver labels | `data/v2/processed/race_driver_labels/` | v1 | 3,458 rows | src fp `fe17b227…` | yes | gitignored | label source |
| canonical matrix | `data/v2/processed/model_matrix/matrix_version=v1/model_matrix.parquet` | v1 | 189,420×106, 24,334,356 B | `d2ee966c…` | yes | gitignored | model-ready dataset |
| F15 manifest | `.../matrix_version=v1/manifest.json` | v1 | 9,406 B | schema `b1ccbc62…` | yes | gitignored | contract |
| F16 ablation config | `.../matrix_version=v1/ablation_config.json` | v1 | 65,547 B | `c88bcbaa…` | yes | gitignored | experiment config |
| feature registry | `v2/features/registry.py`, `v2/features/*.py` | v8 | 84 defs | `a04d5475…` | n/a | tracked | identity authority |
| label registry | `v2/labels/contracts.py`, `builder.py` | v1 | 7 defs | `0a4d0bb6…` | n/a | tracked | target authority |
| F16 config code | `v2/experiments/feature_sets.py` | v1 | — | — | n/a | tracked | config authority |
| Phase-2 docs | `docs/PHASE2_*.md` | — | — | — | n/a | tracked | semantics/audit |
| freeze manifest | `docs/generated/phase2_freeze_manifest.json` | — | small | deterministic | yes | tracked | machine freeze |

## 26. Version catalog

| Version | Value |
|---|---|
| `FEATURE_SET_VERSION` | `v8` |
| `LABEL_SET_VERSION` | `v1` |
| `MATRIX_VERSION` | `v1` |
| `ABLATION_CONFIG_VERSION` | `v1` |
| `REGISTRY_VERSION` | `1` |
| Phase-1 dataset tag | `v2-data-platform-phase1` @ `2fa0a7c` |

No semantic version numbers are invented where none exist.

## 27. Hash catalog (full values)

- Feature registry fingerprint: `a04d5475e8ac113bfffe8af3ba35db5dedf127d0306803dcb71332c5be863fe6`
- Label registry fingerprint: `0a4d0bb6369f880add679731f46e992f0bee98b2930caeefa392297cf29515cd`
- Matrix schema hash: `b1ccbc62380da8e841e7b2d78d8d37aac2b67c72b0306a2495fbabc3fb224f0e`
- Matrix content hash: `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`
- F16 config semantic hash: `c88bcbaafe72ff2a615f24563d631f4e313cbc1d41e23b3818d3f9d86f6b087c`
- `model_matrix.parquet` byte sha256: `b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3`
- `manifest.json` byte sha256: `b6a63f5eb0577906ee6496d05c4f7a20c3eb79f2f8048d4ff06acb764d6cbc62`
- `ablation_config.json` byte sha256: `bb59d936b14552779a4ab192c4d3e9c9d1e2ff31e2ef8608b30c44ed86f2f5a7`
- Source fingerprints (from F15 manifest):
  - `d9_states` (8 files): `66711cb632e920d89896f5a3b7ea326ae91d152b6cc3e107d6f65969706a5719`
  - `labels` (8 files): `fe17b2279f0fe7eae92dea5608c7bad1c3dacfe5ef18998a72e36c116882bb47`
  - `races` (173 files): `513e2beb74a54bf17237dc9192b2e69a10d7ab494bf7e004afef194088ec027f`
  - `results` (173 files): `1ba568a4682b6a86c579341da1423aa78788eb1d6055597ec3660f002ff28cd5`
  - `pit_stops` (173 files): `8f0f37633c92f5128851ecef858abcda3ec116f19b3207ff937d7453359b82f1`
  - `hist_races` (76 files): `b6cb0359b8ea8608f6fdf9404304d5cb2a516b3d1a4e450c81885706a1b2c19e`
  - `hist_results` (76 files): `f6ea01903f6e948d6c7ab6d4228099fdcef44ac57f0fba6a3b5f80bb6b6ca244`

## 28. Validation / test summary

| Area | Result |
|---|---|
| Full Python/V2 suite | **861 passed, 4 xfailed** (1,430 s) |
| Frontend node tests | **21 passed** |
| Typecheck (`tsc --noEmit`) | pass |
| Lint (`eslint`) | pass (1 warning) |
| Frontend build (`next build`) | pass |
| D11 offline (skip `fresh_env`) | **43 findings / 0 failed / 0 blockers** |
| D11 historical complete baseline | 44 / 0 / 0 (with `fresh_env`) |
| F14 threat classes | 20 |
| F14 test functions | 41 (plus upstream family suites) |
| F15 matrix tests | 39 |
| F16 config tests | 36 |
| F13 label tests | 20 |
| F12 telemetry-guard tests | 10 |

Test count is not equated with correctness; every gate above is
backed by explicit contract assertions.

---

## 29. Performance (recorded; artifacts unchanged)

| Operation | Measured |
|---|---|
| F15 full matrix build | ~349 s, ~1.2 GB peak RSS |
| canonical Parquet | 24,334,356 B (~24.3 MB) |
| matrix reload | seconds-scale |
| F16 config ops | milliseconds |
| F16 fixture validation + matrix load | ~1 s |
| full regression | ~1,430 s (dominated by F15 rebuild/idempotency tests) |

No expensive benchmark was re-run unnecessarily; the F15 artifact and
manifest are unchanged, and the regression timings corroborate the
recorded F16 figures.

## 30. D11 timeout-change review

F16 changed the D11 regression harness timeout from 1200 s to 3600 s
(`v2/d11.py`, `check_regression`). Review: this is a **harness-only**
change. The offline suite now legitimately takes ~1,430 s (F15
rebuild/idempotency tests), so the old budget produced a false
`timed_out` BLOCKER. The change does not alter any validation
semantics, swallows no failure (returncode and tail still drive
pass/fail; a timeout is still reported), and was corroborated by this
F17 run (861 passed / 4 xfailed in 1,430 s). Approved and documented.

## 31. Xfail review

| # | Test | Reason | Introduced | Intentional? | Blocks Phase 3? |
|---|---|---|---|---|---|
| 1 | `test_monaco_single_model_http_ok[logreg]` | Legacy V1 defect: NaN `tyre_life_x` breaks JSON for Monaco 2022 (audit §5.1) | pre-Phase-2 (legacy) | yes | **no** |
| 2 | `test_monaco_single_model_http_ok[hgb]` | same | pre-Phase-2 | yes | no |
| 3 | `test_monaco_single_model_http_ok[xgboost]` | same | pre-Phase-2 | yes | no |
| 4 | `test_monaco_ensemble_http_ok` | same | pre-Phase-2 | yes | no |

All four concern the frozen V1 serving path, not Phase-2 model data;
they are `strict=False` legacy-defect markers. No xfail represents an
unresolved correctness defect relevant to model data → **not a
blocker**.

## 32. Warning review

| Warning | Where | Affects feature values? | Affects reproducibility? | Affects Phase 3? | Action |
|---|---|---|---|---|---|
| pandas `concat` FutureWarning (empty/all-NA) | several tests + `build_matrix.py` | no (deprecation notice; current behavior unchanged) | no | no | not fixed (out of scope, trivial-cosmetic) |
| frontend `ResultCards` unused `barClassName` | `frontend/.../ResultCards.tsx` | n/a | no | no | not fixed (cosmetic eslint warning) |
| bare `python3` no-op shim | environment (Python 3.14) | no | **caution** — documented | no | documented; `Makefile::check-python` guards it; use `python3.11` |

No warning masks a correctness, feature-value or reproducibility
defect.

## 33. Phase-3 input contract

Phase 3 / M0 receives:

- **CANONICAL MATRIX** `model_matrix.parquet` + **F15 MANIFEST**;
- **F16 FEATURE CONFIG** (`ablation_config.json`) and `resolve_feature_set`;
- **LABEL / TASK CONTRACTS** (`TASKS`, `load_task`, eligibility masks);
- **FIXTURES** (`resolve_fixture`, `validate_fixtures`).

Phase 3 MUST:

- select features via the **manifest predictive allow-list** /
  `resolve_feature_set`, never dataframe `drop` logic;
- use **task eligibility masks**, never ad-hoc `.notna()` rules;
- **NOT mutate** Phase-2 artifacts during experiments.

## 34. Phase-3 responsibilities (handed off, not implemented)

Freeze the chronological evaluation protocol; protect the final
holdout; implement non-ML baselines; model-specific preprocessing;
train baseline tabular models; train serious candidate models;
calibration; ranking/ordinal tasks; feature-family ablations;
stage-of-race evaluation; latency/training benchmarks; model
comparison; production-model selection.

## 35. Temporal evaluation handoff (direction only — no executable folds)

Planned direction: development chronology such as 2018–2021 → 2022,
2018–2022 → 2023, 2018–2023 → 2024, with a protected final evaluation
involving 2025. M0 must inspect and freeze the exact protocol before
experiments. F16 fixtures are **not** train/test labels; do not run
2025 repeatedly.

## 36. M0 handoff (next stage; not implemented here)

**M0 — Model Lab Handoff + Temporal Evaluation Protocol Freeze.** M0
should verify the Phase-2 artifacts and freeze: tasks; eligibility;
chronological folds; final-holdout policy; metrics; baselines;
preprocessing boundaries; experiment recording. F17 recommends M0.

## 37. Documentation consistency findings

- **Fixed:** `README.md` top-level status said Phase 2 "NOT STARTED" and
  the architecture block ended at "Phase 2 feature engine (NOT
  STARTED)". Updated to Phase 2 COMPLETE/FROZEN with the matrix
  location, versions, rebuild/validate commands, and the Model-Lab
  handoff link.
- **Not changed (historically correct stage-local statements):**
  `docs/DATASET_V2_REPORT.md` "Phase-2 feature families remain NOT
  STARTED" and `docs/PHASE1_EXIT_REPORT.md` "Phase 2 is NOT
  AUTHORIZED" describe the state when those reports were written;
  rewriting them would falsify the record.
- Stage docs use stage-local version/count language (e.g. F2 "24
  definitions", F5 "v2", registry 81→84 in F11) which is correct for
  those stages. No stale global count/version/telemetry status
  remains in current top-level docs.

## 38. Phase-2 definition of done

| Criterion | Evidence | Pass |
|---|---|---|
| temporal semantics frozen | `PHASE2_TEMPORAL_SEMANTICS.md`; F1 | ✅ |
| synchronized rival semantics frozen | §4 of F1; F3 tests | ✅ |
| feature registry exists | `v2/features/registry.py`; fingerprint | ✅ |
| 84 predictive definitions frozen | `build_f11_registry()` == 84 | ✅ |
| predictive/label separation enforced | manifest lists; firewall test | ✅ |
| pace features implemented | `pace.py`; F5 tests | ✅ |
| structured gaps implemented | `gaps.py`; F6 tests | ✅ |
| field/context implemented | `context.py`; F7 tests | ✅ |
| rates/momentum implemented | `rates.py`; F8 tests | ✅ |
| environment history implemented | `environment.py`; F9 tests | ✅ |
| pre-race priors implemented | `priors.py`; F10 tests | ✅ |
| interactions restrained/documented | `interactions.py` (3); F11 doc | ✅ |
| telemetry formally deferred | F12; ADR-0001 | ✅ |
| labels/contracts frozen | `v2/labels`; F13 tests | ✅ |
| leakage/parity red-team passed | F14; 20 threat classes | ✅ |
| canonical matrix materialized | Parquet + manifest; content hash | ✅ |
| safe manifest loader exists | `load_features/load_labels/load_task` | ✅ |
| ordinal eligibility protected | mask == 178,963; `load_task` test | ✅ |
| ablation groups frozen | `feature_sets.py`; F16 tests | ✅ |
| experiment fixtures frozen | 11 fixtures; `validate_fixtures` | ✅ |
| reproducible hashes exist | §27 | ✅ |
| regression green | 861/4; 21 frontend; build green | ✅ |
| Phase-3 handoff documented | §33–36 | ✅ |

## 39. Freeze decision

All DoD items pass; no BLOCKER or MAJOR remains.

**PHASE 2 — COMPLETE / FROZEN.**

---

## 40. Git freeze preparation

Inspection only; no commit/tag was made.

Tracked modifications: `.gitignore` (adds `/graft/`),
`V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md` (approved revision),
`v2/d11.py` (harness timeout 1200→3600 s).

Untracked Phase-2 source/tests/docs: `v2/features/`, `v2/labels/`,
`v2/experiments/`, `tests/test_v2_features_f2..f15.py`,
`tests/test_v2_labels_f13.py`, `tests/test_v2_experiments_f16.py`,
`tests/f14_helpers.py`, `docs/PHASE2_*.md`, plus repo-tooling files
(`AGENTS.md`, `GEMINI.md`, `opencode.json`, `.claude/`, `.cursor/`,
`.gemini/`, `.mcp.json`, `.ignore`).

Generated gitignored artifacts: `data/v2/**` (canonical Parquet,
manifest, ablation config, D11 reports) and `graft/`. Large-file status:
`model_matrix.parquet` is ~24.3 MB, gitignored (not committed). No large
tracked artifact. Secrets scan: no tracked `.env`; no secret-like files
detected (D11 `GIT` finding: `tracked_env_files: []`,
`tracked_ff1pkl: []`, `tracked_parquet: []`; repo has no secret-scan
tooling).

Recommended future freeze commit/tag (do **not** execute here):
tag `v2-temporal-feature-engine-phase2`, consistent with the existing
`v2-data-platform-phase1` convention.

## 41. Freeze manifest

Machine-readable manifest written to
`docs/generated/phase2_freeze_manifest.json` (deterministic semantic
payload; no timestamp inside the semantic body).

## 42. Final static safety check

- no telemetry calculator in `v2/features`, `v2/labels`,
  `v2/experiments` ✅
- no model estimator / ML library import in Phase-2 modules ✅
- no label import in feature calculators (only the name-guard in
  registry + assembly-layer import in build_matrix) ✅
- no feature/label overlap (predictive ∩ label = ∅) ✅
- no train/test split implementation in F16 ✅
- no prediction metrics/results in fixtures or experiments ✅
- no accidental Phase-3 implementation ✅

## 43. Final artifact load test (final consumer smoke test)

From a clean Python process:

```
load manifest              -> v1, 189,420 rows
load canonical matrix      -> (189420, 106)
resolve ALL_84             -> 84 == manifest predictive_columns
load_task("winner")        -> X (189420, 93), mask sum 189420
load_task("final_position")-> y non-null 189420, mask sum 178963
resolve_fixture("wet_2019_germany") -> 2019-r11-R|hamilton|20
validate_fixtures          -> 11 fixtures OK
```

No model. **PASS.**

## 44. Incompatibility failure test

| Injected fault | Result |
|---|---|
| fake `feature_set_version` = v999 | `AblationConfigError` ✅ |
| wrong `matrix_version` = v99 | `AblationConfigError` ✅ |
| altered predictive list (83) | `AblationConfigError` ✅ |
| label placed in predictive list | `AblationConfigError` ✅ |
| unknown feature set | `AblationConfigError` ✅ |
| unknown fixture | `AblationConfigError` ✅ |

No canonical artifact was modified. **PASS.**

## 45. Findings by severity

- **BLOCKER:** none.
- **MAJOR:** none.
- **MINOR/INFO:**
  - `README.md` stale Phase-2 status (**fixed** in F17).
  - `context_batch`/`rates_batch` recompute the pace basis / gap sweep
    (bounded, documented F15 inefficiency; not a correctness issue).
  - `content_hash` stable for a fixed pandas/pyarrow version
    (documented cross-version caveat).
  - Combined Parquet means labels co-reside with features; separation
    is enforced by the manifest-driven loader, not file boundaries.
  - `v2.d11 --json <path outside repo root>` writes the report and then
    raises `ValueError` in the final `paths.relative(dest)` print
    (portable-path guard). Default invocation and in-root `--json`
    paths are unaffected; the gate itself returns 43/0/0. Discovered by
    F17's invocation choice; not fixed to avoid changing the validated
    harness after the gate run. MINOR.
  - pandas concat FutureWarning; frontend unused-variable warning; bare
    `python3` shim (all classified benign in §32).

## 46. Fixes made in F17

- `README.md`: updated top-level status/architecture/discoverability
  (F17 §36).
- Added `docs/PHASE2_FINAL_REPORT.md` (this report) and
  `docs/generated/phase2_freeze_manifest.json`.
- No semantic, feature, label, matrix or ablation change; no code
  defect fix was required.

## 47. Unresolved questions

- Exact Phase-3 chronological fold boundaries and final-holdout policy
  (M0).
- DNF/reliability event definition (deferred to Phase 3).
- Whether threaded pace/gap caches are worth adding post-freeze
  (perf-only; would not change semantics).

## 48. Unresolved blockers

None.

---

## Final recommendation

# PHASE 2 — COMPLETE / FROZEN
