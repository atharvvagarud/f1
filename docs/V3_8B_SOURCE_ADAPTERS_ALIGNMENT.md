# V3.8B SOURCE ADAPTERS + IDENTITY-SAFE ALIGNMENT

## Final verdict

V3.8B COMPLETE — SOURCE ALIGNMENT VALIDATED — READY FOR V3.8C. Infrastructure only: no agreement metrics, no historical evaluation, no fusion, no runtime/API/frontend.

## Frozen parent

- Commit: `30fe18908a41d95113c189274598269a95ef44ca`
- Tag: `v3.7-counterfactual-engine`
- V3.7 card `a7b6d33e…19c3`, V3.8A contract `d0b8785a…9b9a67b` — both recomputed from artifacts at entry.

## A provenance

V3.8A contract (`v3.8a-consensus-contract-v1`, identity above) is the sole semantic authority. B re-decides nothing: PRIMARY (V3.1B Logistic, MC2), SECONDARY (V3.5 marginals, V3.3 XGBoost), EXCLUDED (V3.4 ensemble); four probability families; `(state_id, driver_id)` key; exact-identity alignment; nine fail-closed classes; poison blacklist; 2025 non-pristine.

## Architecture

New narrow package `raceintel/consensus/` (`__init__`, `contracts`, `adapters`, `alignment`) — the repo has no `v2/` directory, so the `raceintel/` science-package convention (cf. `counterfactual/`, `strategy/`) applies. Dependency strictly downward: B consumes frozen in-memory types (`PredictionResult`, `DriverSimulationSummary`, `STAGES`); no frozen source imports B; no API/frontend/V3.6/V3.7/fusion imports anywhere in B.

## Source registry

`V3_1B_LOGISTIC`, `MC2_E`, `V3_5_LOGISTIC_CONTROL`, `V3_5_XGB_E`, `V3_3_XGBOOST`. Closed registry: unknown names fail; anything V3.4/ensemble-shaped fails with the double-count rationale. No ENSEMBLED adapter exists.

## Adapter identities

`v3.8b-logistic-adapter-v1`, `v3.8b-mc2-adapter-v1`, `v3.8b-v3.5-adapter-v1` (shared by both V3.5 lineages), `v3.8b-xgb-adapter-v1`. Mechanics-only; frozen source/model identities travel separately in every record's provenance.

## Source-native record

Frozen `NativePrediction`: state/race/year/round/lap/stage/driver keys, source/family/target, `native_probability`, explicit `normalization_semantics`, support status + reason, mandatory provenance, MC trial count + derived flag where applicable. No outcome, label, metric, or consensus field exists on the type.

## Logistic adapter

`from_independent_binary` / `from_prediction_result`: RAW positive-class pass-through, target WIN, family INDEPENDENT_BINARY, semantics NOT_RACE_NORMALIZED. Identity-keyed metadata (never positional); duplicates/length mismatches fail. No retraining, no refit, no calibration, no ranking, no ground truth.

## MC2 adapter

`from_mc2_win`: native winner-frequency pass-through with mandatory positive valid-trial count. `from_mc2_topk` + `mc2_derived_topk`: mechanical sums over frozen full-field position distributions (DNF bucket excluded), explicitly flagged `derived_from_mc2_counts`. Missing distribution or trial count fails closed. Frequencies are never called calibrated.

## V3.5 adapter

`from_v35_row`: explicit row-dicts with named `raw_/cal_/proj_top{1,3,5,10}` columns (never positional), explicit target enum, family MARGINAL_THRESHOLD, semantics NOT_JOINT_NOT_RACE_NORMALIZED. Ground-truth keys (`is_winner`, etc.) rejected at the door; provenance mandatory.

## XGBoost adapter

Same independent-binary mechanics as Logistic with source `V3_3_XGBOOST`; secondary status is an A classification preserved in docs/audit, never a mechanical promotion.

## V3.4 exclusion

No registry member, no adapter, no family admission. `admit_source_name` rejects V3.4/ensemble strings with the convex-blend double-count rationale (tested). The frozen artifact may be read for provenance; it can never become a comparison source.

## Probability validation

`validate_probability`: finite, numeric (bools rejected), within [0,1]. NaN/±inf/negatives/>1 raise; nothing is clamped, coerced, or normalized.

## Native-value preservation

Primary invariant: adapted `native_probability` equals the frozen source value exactly (difference 0 across the full validation corpus: 18 Logistic, 15 MC2, 15 V3.5, 6 XGB spot records). No rounding before comparison.

## Normalization semantics

Per-source explicit enum (never a hiding boolean): Logistic/XGB NOT_RACE_NORMALIZED, V3.5 NOT_JOINT_NOT_RACE_NORMALIZED, MC2 MUTUALLY_EXCLUSIVE_RACE_FREQUENCY. Package source contains no softmax/simplex/normalize helper (tested); a non-summing Logistic state survives adaptation unchanged (tested sentinel).

## Provenance

Every record binds artifact path + identity + model identity; adapters refuse to run without it. Corpus provenance pins the audited tracked identities (model cards, frozen MC2/V3.5/V3.3 structures).

## Canonical comparison key

`(state_id, driver_id)` with race/year/round/lap/stage as validation/context metadata. Never row/DataFrame/array index or driver order; canonical sorted output ordering makes results input-order independent.

## State alignment

`source_A.state_id == source_B.state_id` exactly — no nearest/previous/next lap, no same-race approximation, no timestamp proximity. Mismatch → pair not comparable with explicit reasons (fail closed, never silent).

## Driver alignment

Exact canonical driver-id strings. Row/driver/roster permutations produce identical output (tested, incl. a positional-poison case where naive index join would cross drivers).

## Stage

Frozen M0 thirds reused via `STAGES` membership validation (`stages.py` untouched); one canonical stage per aligned state; contradictory metadata on equal state_id fails.

## Target compatibility

Central `targets_compatible`: WIN↔WIN compatible across V3.1B/MC2/V3.5/XGB; any cross-target pair incompatible; V3.5-topk↔MC2-topk compatible only when B exposes that MC2 target. Magnitude comparison across incompatible targets is unrepresentable.

## Support accounting

`account_support` records candidate drivers/states, per-source availability, the every-source intersection, and per-driver/per-state exclusions with reason codes — partial coverage included. Inner intersections for downstream metrics always travel with complete exclusion records.

## Comparison frame

Frozen `ComparisonFrame`: keys, both sources/families/targets, compatibility flag, both natives (None when missing), both support states + reasons, comparability flag, both provenances, MC trial counts. Field scan proves no metric and no truth field exists on the type (tested).

## Multi-source frame

`align_multi`: deterministic source-ordinal entries plus explicit `excluded` list, so C inspects Logistic/MC2/V3.5/XGB without joining. Analysis structure, not a training vector.

## Missing-source semantics

Missing side → `UNAVAILABLE` + stable reason (`SOURCE_NOT_AVAILABLE` etc.), native `None`, comparability false. Never zero, NaN, dropped row, or silent omission (tested).

## Native zero vs missing

Source-emitted `0.0` with `AVAILABLE` (corpus: state-f perez Logistic) is structurally distinct from absent-with-reason (corpus: state-f perez V3.5 row, state-f MC2). Tests assert the representations share no field shape.

## Row-order safety

Shuffled source rows, reversed record order, and permuted rosters yield byte-identical frames/accounting (tested); the V3.3 incident class cannot recur through this layer.

## Temporal safety

B imports and structures contain no future/outcome/label token (tested with `__future__`-import-aware scan); alignment of identical inputs with/without any historical context is definitionally identical (no such input exists). A's 13-family blacklist is frozen in the B contract.

## Ground-truth boundary

`FORBIDDEN_GROUND_TRUTH_FIELDS` enforced at the V3.5 door and absent from all frame types (dataclass field scan tested). Ground truth joins only in D.

## 2025 boundary

REVEALED_HOLDOUT / NON_PRISTINE carried in the B contract; B reads no 2025 data (fixtures are synthetic), creates no product support, and never calls any year pristine.

## Validation corpus

`results/v3/v3_8b/validation_corpus.json` (`v3.8b-validation-corpus-v1`): 2 races × EARLY/MID/LATE × 3 drivers with fixed illustrative constants (agreement-neutral by construction), covering Logistic+MC2 overlap, V3.5 overlap, XGB overlap, an MC2-ineligible state, a missing-driver case, and a native-zero case. Selection rule documented in-artifact.

## Adapter parity

Adapted == source-native exactly (0 difference) for every corpus record, per source/target above; MC2 top-k derivation verified mechanically (0.2+0.1+0.1=0.4 sentinel).

## Reproducibility

No clock, no RNG, no global state; canonical ordering; identical inputs → identical outputs (tested at frame and multi-frame level).

## Known limitations

Fixtures are illustrative constants, not live frozen predictions (real per-state values flow in C/D through the same constructors); file-based parquet loaders deferred to corpus-backed stages rather than shipped as untestable dead code; MC2 top-k derivation validated on frozen-structure fixtures.

## V3.8C readiness

C consumes `ComparisonFrame`/`MultiSourceFrame` + `SupportAccounting` directly: keys, natives, compatibility, support, provenance, and MC trial counts are all present; metrics, ranks, leaders, and evaluation joins are C/D territory and absent by construction.
