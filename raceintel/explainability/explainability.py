"""Phase-8 E3 global explainability for the frozen winner model.

Read-only explanation of the production winner ``LogisticRegression`` **as
frozen**. This module never retrains, retunes, recalibrates, edits
coefficients, changes preprocessing or ALL_84, normalizes probabilities,
touches 2025 targets, or modifies the replay cache. It consumes only:

- the validated production serving artifact (``raceintel.model_lab.serving``);
- the frozen Phase-2 feature registry / F16 ablation grouping
  (``v2.features.interactions`` + ``v2.experiments.feature_sets``);
- frozen pre-2025 canonical matrix rows and the frozen race-macro metric
  (``raceintel.model_lab.aggregation``).

Design intent (E3 is global, not local):

- coefficient evidence describes the fitted linear model in log-odds space;
- permutation evidence is *empirical* and tied to one explicit protocol;
- the two are distinct evidence and are never merged into one ranking.

Probability semantics remain ``INDEPENDENT_BINARY``: the model emits one
independent per-driver winner estimate, never a race vote share, and
explanation never normalizes across a race.

No SHAP (E0 decision: deferred/dropped for v1); exact linear-model
contribution mathematics is sufficient.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

from raceintel.config import V2Paths
from raceintel.experiments.feature_sets import PRIMARY_GROUP_ORDER, primary_group_name
from raceintel.features.interactions import build_f11_registry
from raceintel.model_lab import serving as SERVING

#: Deterministic artifact format identifier (bump only on a format change).
GLOBAL_EXPLANATION_FORMAT = "global-explanation-v1"

#: Explanation space is additive model log-odds, never probability points.
EXPLANATION_SPACE = "LOG_ODDS"

#: The one frozen probability semantic every explanation must preserve.
PROBABILITY_SEMANTICS = "INDEPENDENT_BINARY"

#: Generated artifact (gitignored; never auto-committed).
OUTPUT_REL = "results/v2_explainability/global_winner_logreg_v1.json"

#: Frozen primary metric for permutation evidence (race-macro log loss).
PRIMARY_METRIC = "race_macro_log_loss"
METRIC_ROW_FUNCTION = "log_loss"
AGGREGATION = "race_macro (equal weight per race, then row metric)"

#: Permutation protocol constants (frozen before computation).
PERMUTATION_BASE_SEED = 42
PERMUTATION_REPEATS = 5
PERMUTATION_UNIT = "state_within_race (race identity preserved)"

#: Frozen allowed/forbidden explanation language (PART I).
ALLOWED_LANGUAGE = (
    "model coefficient",
    "model log-odds",
    "positive/negative association in the fitted model",
    "permutation increased race-macro log loss by ...",
    "under this evaluation protocol ...",
    "model input",
)
FORBIDDEN_LANGUAGE = (
    "caused",
    "proved",
    "prove",
    "driver won because",
    "added x probability points",
    "probability points",
    "most important factor in reality",
    "the model knows",
    "the model thinks",
)


class ExplainabilityError(RuntimeError):
    """Fatal E3 explainability failure. Never repairs or falls back."""


class StaleExplanationError(ExplainabilityError):
    """Raised when an artifact no longer matches the frozen model identity."""


# ---------------------------------------------------------------------------
# Read-only model / artifact introspection
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=float)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def feature_names_hash(feature_names) -> str:
    """Serving-convention hash of ordered feature names (newline-joined)."""
    return hashlib.sha256(
        "\n".join(feature_names).encode("utf-8")).hexdigest()


def preprocessor_fingerprint(preprocessor) -> str:
    """Deterministic digest of the fitted preprocessing state (read-only).

    Hashes the fitted *state* the serving artifact carries (imputation
    values, scaling statistics, categorical vocabulary, contract flags).
    Fitted statistics are never recomputed from current data.
    """
    transformer = preprocessor.transformer
    numeric = transformer.named_transformers_["num"]
    boolean = transformer.named_transformers_["bool"]
    categorical = transformer.named_transformers_["cat"]
    encoder = categorical.named_steps["encode"]
    payload = {
        "numeric_columns": list(preprocessor.numeric_columns),
        "boolean_columns": list(preprocessor.boolean_columns),
        "categorical_columns": list(preprocessor.categorical_columns),
        "output_dim": int(preprocessor.output_dim),
        "numeric_imputation": list(
            np.asarray(numeric.named_steps["impute"].statistics_,
                       dtype=float)),
        "numeric_mean": list(
            np.asarray(numeric.named_steps["scale"].mean_, dtype=float)),
        "numeric_scale": list(
            np.asarray(numeric.named_steps["scale"].scale_, dtype=float)),
        "boolean_imputation": list(
            np.asarray(boolean.named_steps["impute"].statistics_,
                       dtype=float)),
        "categorical_imputation": str(
            categorical.named_steps["impute"].fill_value),
        "categorical_handle_unknown": str(encoder.handle_unknown),
        "categorical_drop": (
            None if getattr(encoder, "drop_idx_", None) is None
            else [None if i is None else int(i)
                  for i in encoder.drop_idx_]),
        "categorical_categories": [list(map(str, cats))
                                   for cats in encoder.categories_],
    }
    return _json_digest(payload)


def load_frozen_explanation_model(path=None):
    """Load and validate the frozen serving model (read-only)."""
    return SERVING.load_frozen_winner_model(path)


def _model_identity(predictor, serving_path: Path) -> dict:
    estimator = predictor._estimator
    return {
        "serving_artifact_path": str(serving_path),
        "serving_artifact_sha256": _sha256_file(serving_path),
        "specification_fingerprint": predictor.specification_fingerprint,
        "feature_set": SERVING.EXPECTED_FEATURE_SET,
        "feature_set_version": "v8",
        "transformed_dim": int(predictor.transformed_dim),
        "canonical_feature_count": len(predictor.feature_names),
        "feature_names_hash": feature_names_hash(predictor.feature_names),
        "estimator_class": type(estimator).__name__,
        "estimator_params": {
            "C": float(estimator.C),
            "penalty": "l2",
            "solver": str(estimator.solver),
            "max_iter": int(estimator.max_iter),
            "class_weight": estimator.class_weight,
            "random_state": int(estimator.random_state),
        },
        "calibration_method": "RAW",
        "probability_kind": "BINARY_PROBABILITY",
        "probability_semantics": PROBABILITY_SEMANTICS,
        "training_seasons": list(SERVING.EXPECTED_TRAINING_SEASONS),
        "sklearn_version": predictor.sklearn_version,
        "preprocessor_fingerprint": preprocessor_fingerprint(
            predictor._preprocessor),
    }


# ---------------------------------------------------------------------------
# PART A/B — transformed feature map (106 -> canonical)
# ---------------------------------------------------------------------------

_PREPROCESSING_LABEL = {
    "numeric": "median imputation (train) + StandardScaler (train)",
    "boolean": "most-frequent imputation (train), cast to float, unscaled",
    "categorical": ("constant 'MISSING' imputation + OneHotEncoder "
                    "(train vocabulary, unknown=ignore)"),
}


def _family_map() -> dict:
    registry = build_f11_registry()
    return {d.name: primary_group_name(d) for d in registry
            if d.predictive_eligible}


def _categorical_pairs(predictor) -> list:
    preprocessor = predictor._preprocessor
    encoder = preprocessor.transformer.named_transformers_[
        "cat"].named_steps["encode"]
    pairs = []
    for column, categories in zip(preprocessor.categorical_columns,
                                  encoder.categories_):
        for value in categories:
            pairs.append((str(column), str(value)))
    return pairs


def build_transformed_feature_map(predictor) -> list:
    """Map every transformed dimension to its canonical feature (106 rows).

    Ordering authority is the fitted preprocessor
    (``ColumnTransformer.get_feature_names_out``); transformed order is never
    guessed. Raises on any unmapped/duplicate dimension.
    """
    preprocessor = predictor._preprocessor
    transformer = preprocessor.transformer
    names = [str(n) for n in transformer.get_feature_names_out()]
    coefficient = np.asarray(predictor._estimator.coef_, dtype=float).ravel()
    if len(names) != len(coefficient):
        raise ExplainabilityError(
            f"transformed name count {len(names)} != coefficient length "
            f"{len(coefficient)}")
    family = _family_map()
    canonical = set(predictor.feature_names)

    numeric = list(preprocessor.numeric_columns)
    boolean = list(preprocessor.boolean_columns)
    pairs = _categorical_pairs(predictor)
    expected = len(numeric) + len(boolean) + len(pairs)
    if expected != len(names):
        raise ExplainabilityError(
            f"transformed dimension contract violation: {expected} != "
            f"{len(names)}")

    entries = []
    for index in range(len(numeric)):
        feature = str(numeric[index])
        entries.append(_entry(index, names[index], feature, "numeric",
                              family, None, coefficient[index]))
    offset = len(numeric)
    for j, feature_raw in enumerate(boolean):
        feature = str(feature_raw)
        entries.append(_entry(offset + j, names[offset + j], feature,
                              "boolean", family, None,
                              coefficient[offset + j]))
    offset += len(boolean)
    for k, (feature, value) in enumerate(pairs):
        entries.append(_entry(offset + k, names[offset + k], feature,
                              "categorical", family, value,
                              coefficient[offset + k]))

    _validate_map(entries, canonical, len(names))
    return entries


def _entry(index, name, feature, feature_type, family, category_value, coef):
    if feature not in family:
        raise ExplainabilityError(
            f"canonical feature {feature!r} has no frozen family")
    return {
        "transformed_index": int(index),
        "transformed_name": name,
        "canonical_feature": feature,
        "feature_family": family[feature],
        "feature_type": feature_type,
        "category_value": category_value,
        "coefficient": float(coef),
        "preprocessing": _PREPROCESSING_LABEL[feature_type],
    }


def _validate_map(entries, canonical, expected_count):
    if len(entries) != expected_count:
        raise ExplainabilityError("transformed map is incomplete")
    indexes = [e["transformed_index"] for e in entries]
    if sorted(indexes) != list(range(expected_count)):
        raise ExplainabilityError("duplicate or missing transformed index")
    names = [e["transformed_name"] for e in entries]
    if len(set(names)) != len(names):
        raise ExplainabilityError("duplicate transformed name")
    unmapped = [e["canonical_feature"] for e in entries
                if e["canonical_feature"] not in canonical]
    if unmapped:
        raise ExplainabilityError(
            f"transformed map references unknown canonical features: "
            f"{sorted(set(unmapped))}")
    seen = {e["canonical_feature"] for e in entries}
    missing = sorted(canonical - seen)
    if missing:
        raise ExplainabilityError(
            f"canonical features with no transformed dimension: {missing}")


# ---------------------------------------------------------------------------
# PART C/E — coefficient evidence (numeric / boolean / categorical)
# ---------------------------------------------------------------------------

def _direction(coefficient: float) -> str:
    if coefficient > 0:
        return "positive coefficient (associated with higher model log-odds)"
    if coefficient < 0:
        return "negative coefficient (associated with lower model log-odds)"
    return "zero coefficient (no additive log-odds contribution)"


def numeric_coefficient_view(predictor) -> list:
    """Standardized numeric coefficients + fitted training statistics.

    Because the numeric block is standardized with train-fitted statistics,
    each coefficient is the change in model log-odds for a one training
    standard deviation increase in the transformed input, conditional on the
    other model inputs. Statistics come from the fitted preprocessor; they
    are never recomputed from current data.
    """
    preprocessor = predictor._preprocessor
    numeric_pipe = preprocessor.transformer.named_transformers_["num"]
    medians = np.asarray(numeric_pipe.named_steps["impute"].statistics_,
                         dtype=float)
    means = np.asarray(numeric_pipe.named_steps["scale"].mean_, dtype=float)
    scales = np.asarray(numeric_pipe.named_steps["scale"].scale_, dtype=float)
    entries = [e for e in build_transformed_feature_map(predictor)
               if e["feature_type"] == "numeric"]
    out = []
    for position, entry in enumerate(entries):
        coefficient = entry["coefficient"]
        out.append({
            "canonical_feature": entry["canonical_feature"],
            "feature_family": entry["feature_family"],
            "transformed_index": entry["transformed_index"],
            "transformed_name": entry["transformed_name"],
            "coefficient": coefficient,
            "direction": _direction(coefficient),
            "units_note": ("change in model log-odds per one training "
                           "standard deviation, conditional on other model "
                           "inputs"),
            "training_median": float(medians[position]),
            "training_mean": float(means[position]),
            "training_scale": float(scales[position]),
        })
    return out


def boolean_coefficient_view(predictor) -> list:
    """Boolean coefficients + fitted training imputation mode.

    A 0 -> 1 change in the transformed boolean input corresponds to the
    coefficient in model log-odds, conditional on the other model inputs.
    Boolean inputs are NOT standardized, so their raw magnitudes are not
    directly comparable with standardized numeric coefficients.
    """
    preprocessor = predictor._preprocessor
    boolean_pipe = preprocessor.transformer.named_transformers_["bool"]
    modes = np.asarray(boolean_pipe.named_steps["impute"].statistics_,
                       dtype=float)
    entries = [e for e in build_transformed_feature_map(predictor)
               if e["feature_type"] == "boolean"]
    out = []
    for position, entry in enumerate(entries):
        coefficient = entry["coefficient"]
        out.append({
            "canonical_feature": entry["canonical_feature"],
            "feature_family": entry["feature_family"],
            "transformed_index": entry["transformed_index"],
            "transformed_name": entry["transformed_name"],
            "coefficient": coefficient,
            "direction": _direction(coefficient),
            "units_note": ("change in model log-odds for a 0 -> 1 input "
                           "change, conditional on other model inputs; "
                           "unscaled, not magnitude-comparable with "
                           "standardized numeric inputs"),
            "training_imputation_mode": float(modes[position]),
        })
    return out


def categorical_coefficient_view(predictor) -> dict:
    """Per-category one-hot coefficients, preserving category identity.

    ``OneHotEncoder`` is fitted with ``handle_unknown='ignore'`` and no
    dropped category, so all fitted categories are encoded and there is no
    traditional reference category. An unseen category maps to the all-zero
    block (no fitted category fires), which is stated explicitly rather than
    described as a reference level.
    """
    preprocessor = predictor._preprocessor
    encoder = preprocessor.transformer.named_transformers_[
        "cat"].named_steps["encode"]
    family = _family_map()
    entries = [e for e in build_transformed_feature_map(predictor)
               if e["feature_type"] == "categorical"]
    by_feature: dict = {}
    cursor = 0
    for column, categories in zip(preprocessor.categorical_columns,
                                  encoder.categories_):
        rows = [e for e in entries
                if e["canonical_feature"] == str(column)]
        if len(rows) != len(categories):
            raise ExplainabilityError(
                f"categorical block size mismatch for {column!r}")
        category_rows = []
        for position, value in enumerate(categories):
            entry = rows[position]
            category_rows.append({
                "category_value": str(value),
                "transformed_index": entry["transformed_index"],
                "coefficient": entry["coefficient"],
                "direction": _direction(entry["coefficient"]),
                "is_missing_sentinel": str(value) == "MISSING",
            })
        coefficients = [row["coefficient"] for row in category_rows]
        block_first = rows[0]["transformed_index"]
        by_feature[str(column)] = {
            "canonical_feature": str(column),
            "feature_family": family[str(column)],
            "fitted_categories": [str(v) for v in categories],
            "fitted_category_count": len(categories),
            "missing_category_present": any(
                str(v) == "MISSING" for v in categories),
            "unknown_behavior": ("unseen category -> all-zero one-hot block "
                                 "(handle_unknown='ignore')"),
            "reference_category": None,
            "reference_category_note": (
                "no category is dropped; all fitted categories are encoded "
                "and there is no traditional reference category"),
            "category_coefficients": category_rows,
            "coefficient_range": {
                "min": float(min(coefficients)),
                "max": float(max(coefficients)),
            },
            "block_first_index": int(block_first),
            "block_size": int(len(categories)),
        }
        cursor += len(categories)
    return by_feature


def canonical_group_view(predictor, map_entries=None) -> dict:
    """Canonical feature -> family grouping (no invented global ranking).

    Summing one-hot coefficients is not presented as a universal global
    importance statistic. Categorical families keep their individual
    category coefficients; empirical importance stays with the permutation
    protocol.
    """
    entries = map_entries or build_transformed_feature_map(predictor)
    family = {e["canonical_feature"]: e["feature_family"] for e in entries}
    groups: dict = {name: [] for name in PRIMARY_GROUP_ORDER}
    for feature in predictor.feature_names:
        groups[family[feature]].append(feature)
    return {
        "family_order": list(PRIMARY_GROUP_ORDER),
        "groups": groups,
        "policy": ("coefficient evidence is reported per canonical feature / "
                   "category; category coefficients are never blindly summed "
                   "into a global importance score"),
    }


# ---------------------------------------------------------------------------
# PART F — permutation importance (pre-2025, within-race unit)
# ---------------------------------------------------------------------------

def assert_pre_2025_seasons(seasons) -> list:
    """Fail closed if any season outside 2018-2024 (especially 2025) is seen."""
    years = sorted(set(int(s) for s in seasons))
    if 2025 in years or not set(years) <= set(range(2018, 2025)):
        raise ExplainabilityError(
            f"2025 firewall: seasons outside 2018-2024: {years}")
    return years


def permutation_population(canonical, predictor) -> dict:
    """Build the frozen pre-2025 permutation population.

    2018-2024 canonical matrix rows with the frozen ``eligible_is_winner``
    mask and the frozen ordered ALL_84 columns. 2025 is rejected before any
    prediction. This is the frozen development population the production
    artifact was final-fit on; it is explicitly NOT temporally
    out-of-sample.
    """
    frame_all = canonical.frame
    predictive = list(predictor.feature_names)
    seasons = frame_all["season"].astype(int)
    eligibility = frame_all["eligible_is_winner"].astype(bool)
    selected = (seasons <= 2024).to_numpy() & eligibility.to_numpy()
    frame = frame_all.loc[selected, predictive].reset_index(drop=True)
    target = np.asarray(frame_all.loc[selected, "is_winner"], dtype=float)
    race_ids = frame_all.loc[selected, "race_id"].astype(str).to_numpy()
    row_seasons = np.asarray(seasons.loc[selected], dtype=int)
    used_seasons = assert_pre_2025_seasons(np.unique(row_seasons))
    if list(frame.columns) != predictive:
        raise ExplainabilityError(
            "permutation frame columns do not match frozen ALL_84 order")
    return {
        "frame": frame,
        "target": target,
        "race_ids": race_ids,
        "row_seasons": row_seasons,
        "seasons": used_seasons,
        "n_rows": int(len(frame)),
        "n_races": int(len(set(race_ids.tolist()))),
        "n_positives": int(target.sum()),
    }


def _race_codes(race_ids) -> tuple:
    codes, uniques = _factorize_sorted(race_ids)
    return np.asarray(codes), [str(u) for u in uniques]


def _factorize_sorted(values):
    unique = sorted(set(map(str, values)))
    lookup = {value: index for index, value in enumerate(unique)}
    codes = [lookup[str(value)] for value in values]
    return codes, unique


def permute_feature_within_race(series, race_codes, rng):
    """Permute one canonical feature's values within each race block.

    Race identity is preserved (values never cross a race boundary), so no
    cross-race or cross-era temporal mixture is introduced. The exact
    multiset of values per race is invariant. Target rows are untouched.
    """
    values = np.asarray(series, dtype=object).copy()
    codes = np.asarray(race_codes)
    for code in range(int(codes.max()) + 1 if len(codes) else 0):
        positions = np.flatnonzero(codes == code)
        if len(positions) <= 1:
            continue
        shuffled = values[positions][rng.permutation(len(positions))]
        values[positions] = shuffled
    return values


def race_macro_log_loss(target, probability, race_ids) -> float:
    """Frozen headline metric: equal-per-race mean of row log loss."""
    from raceintel.model_lab.aggregation import race_macro

    node = race_macro(target, probability, race_ids, METRIC_ROW_FUNCTION)
    value = node["value"]
    if value is None or not np.isfinite(float(value)):
        raise ExplainabilityError("race-macro log loss is undefined")
    return float(value)


def permutation_importance(population, predictor, *, repeats: int = None,
                           base_seed: int = None,
                           feature_names=None) -> dict:
    """Empirical permutation importance under the frozen protocol.

    For each canonical feature, independently and deterministically, the
    raw canonical input is permuted **within race blocks**, re-transformed
    through the fitted preprocessor (never touching one-hot columns
    directly), and re-scored. Importance is
    ``permuted_metric - baseline_metric`` for race-macro log loss; positive
    means the disruption increased log loss (performance became worse).

    Caveats (documented, not hidden): the population is the final-fit
    training population, so this is in-sample evidence; correlated
    engineered features can make a redundant input look unimportant; a
    constant-within-race input can have no within-race variation to
    permute.
    """
    repeats = PERMUTATION_REPEATS if repeats is None else int(repeats)
    base_seed = (PERMUTATION_BASE_SEED if base_seed is None else int(base_seed))
    if repeats < 1:
        raise ExplainabilityError("permutation repeats must be >= 1")
    names = list(feature_names or predictor.feature_names)
    frame = population["frame"]
    target = population["target"]
    race_ids = population["race_ids"]
    codes, _ = _race_codes(race_ids)

    baseline = race_macro_log_loss(target, predictor.predict_proba(frame),
                                   race_ids)
    results = []
    for feature_index, feature in enumerate(names):
        deltas = []
        for repeat in range(repeats):
            rng = np.random.default_rng([base_seed, feature_index, repeat])
            probe = frame.copy()
            probe[feature] = permute_feature_within_race(
                frame[feature], codes, rng)
            probability = predictor.predict_proba(probe)
            value = race_macro_log_loss(target, probability, race_ids)
            deltas.append(float(value - baseline))
        array = np.asarray(deltas, dtype=float)
        results.append({
            "canonical_feature": feature,
            "feature_family": primary_group_name(
                build_f11_registry().get(feature)),
            "mean_delta": float(array.mean()),
            "std_delta": float(array.std(ddof=1)) if len(array) > 1 else 0.0,
            "min_delta": float(array.min()),
            "max_delta": float(array.max()),
            "per_repeat_delta": [float(d) for d in deltas],
        })
    results.sort(key=lambda row: (-row["mean_delta"],
                                  row["canonical_feature"]))
    return {
        "status": "OK",
        "protocol": {
            "metric": PRIMARY_METRIC,
            "row_metric": METRIC_ROW_FUNCTION,
            "aggregation": AGGREGATION,
            "unit": PERMUTATION_UNIT,
            "repeats": repeats,
            "base_seed": base_seed,
            "seed_scheme": ("numpy.default_rng([base_seed, feature_index, "
                            "repeat])"),
            "population": {
                "seasons": population["seasons"],
                "n_rows": population["n_rows"],
                "n_races": population["n_races"],
                "n_positives": population["n_positives"],
                "target": "is_winner",
                "eligibility_mask": "eligible_is_winner",
                "evidence_class": (
                    "PRE_2025_FINAL_FIT_IN_SAMPLE (2018-2024 rows the "
                    "production artifact was final-fit on; NOT temporally "
                    "out-of-sample)"),
                "holdout_2025": "excluded",
            },
        },
        "baseline_metric": baseline,
        "results": results,
    }


# ---------------------------------------------------------------------------
# PART H — global explanation artifact
# ---------------------------------------------------------------------------

def build_global_explanation(*, canonical=None, predictor=None,
                             serving_path=None, repeats: int = None,
                             base_seed: int = None,
                             max_races: int = None) -> dict:
    """Assemble the deterministic global explanation artifact (in memory)."""
    paths = canonical.paths if canonical is not None else V2Paths.resolve()
    if canonical is None:
        from raceintel.model_lab import data as DATA

        canonical = DATA.load_canonical(paths, verify_content_hash=True)
    if predictor is None:
        predictor = load_frozen_explanation_model()
    if serving_path is None:
        serving_path = SERVING.default_serving_artifact_path(paths.root)

    map_entries = build_transformed_feature_map(predictor)
    population = permutation_population(canonical, predictor)
    if max_races is not None and max_races < population["n_races"]:
        population = _truncate_population(population, int(max_races))
    permutation = permutation_importance(
        population, predictor, repeats=repeats, base_seed=base_seed)

    intercept = float(np.asarray(predictor._estimator.intercept_,
                                dtype=float).ravel()[0])
    numeric = numeric_coefficient_view(predictor)
    boolean = boolean_coefficient_view(predictor)
    categorical = categorical_coefficient_view(predictor)

    model_identity = _model_identity(predictor, Path(serving_path))
    model_identity["phase2_matrix_content_hash"] = canonical.manifest.get(
        "content_hash")
    artifact = {
        "format": GLOBAL_EXPLANATION_FORMAT,
        "model_identity": model_identity,
        "feature_identity": {
            "feature_set": SERVING.EXPECTED_FEATURE_SET,
            "feature_set_version": "v8",
            "canonical_feature_count": len(predictor.feature_names),
            "transformed_feature_count": int(predictor.transformed_dim),
            "numeric_feature_count": len(predictor._preprocessor.numeric_columns),
            "boolean_feature_count": len(predictor._preprocessor.boolean_columns),
            "categorical_feature_count": len(
                predictor._preprocessor.categorical_columns),
            "one_hot_category_count": sum(
                len(v["fitted_categories"])
                for v in categorical.values()),
            "canonical_feature_order": list(predictor.feature_names),
            "family_order": list(PRIMARY_GROUP_ORDER),
        },
        "probability_semantics": PROBABILITY_SEMANTICS,
        "explanation_space": EXPLANATION_SPACE,
        "intercept": intercept,
        "transformed_feature_count": int(predictor.transformed_dim),
        "canonical_feature_count": len(predictor.feature_names),
        "mathematics": {
            "decision_function": "z = intercept + sum_j beta_j * x'_j",
            "link": "p = 1 / (1 + exp(-z))",
            "note": ("coefficients describe model log-odds for the "
                     "transformed inputs; they are not additive changes to "
                     "win probability"),
        },
        "transformed_features": map_entries,
        "numeric_coefficients": numeric,
        "boolean_coefficients": boolean,
        "categorical_coefficients": categorical,
        "canonical_groups": canonical_group_view(predictor, map_entries),
        "permutation_importance": permutation,
        "language_contract": {
            "allowed": list(ALLOWED_LANGUAGE),
            "forbidden": list(FORBIDDEN_LANGUAGE),
        },
        "limitations": _limitations(),
    }
    assert_language_compliant(artifact)
    return artifact


def _truncate_population(population, max_races):
    races = sorted(set(population["race_ids"].tolist()))[:max_races]
    keep = np.isin(population["race_ids"], races)
    return {
        "frame": population["frame"].loc[keep].reset_index(drop=True),
        "target": population["target"][keep],
        "race_ids": population["race_ids"][keep],
        "row_seasons": population["row_seasons"][keep],
        "seasons": sorted(set(
            int(s) for s in population["row_seasons"][keep])),
        "n_rows": int(keep.sum()),
        "n_races": len(races),
        "n_positives": int(population["target"][keep].sum()),
    }


def _limitations() -> list:
    return [
        "Coefficients describe the fitted model's log-odds structure; they "
        "are not causal effects and do not establish why a driver won.",
        "Coefficients must never be converted into win-probability "
        "increments; the explanation space is additive model log-odds.",
        "Standardized numeric coefficients are per one training standard "
        "deviation, conditional on the other model inputs.",
        "Unscaled boolean coefficients are not magnitude-comparable with "
        "standardized numeric coefficients without qualification.",
        "Categorical coefficients are one-hot increments for the fitted "
        "encoding with no dropped reference category; an unseen category "
        "fires the all-zero block.",
        "Category coefficients are reported individually; they are not "
        "summed into an invented global importance score.",
        "Permutation importance is empirical under one stated protocol and "
        "is in-sample with respect to the production artifact (final-fit "
        "on the 2018-2024 permutation population); it is not unbiased "
        "generalization evidence.",
        "Correlated engineered features can make a redundant input look "
        "unimportant under permutation; low permutation importance does "
        "not establish that an input is useless.",
        "A model input that is constant within every race offers no "
        "within-race variation for this permutation unit.",
        "Independent per-driver binary probabilities are never normalized "
        "into a race distribution for explanation.",
        "SHAP is deferred for v1; exact linear-model log-odds mathematics "
        "is the explanation method.",
    ]


def _iter_strings(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "language_contract":
                continue
            yield from _iter_strings(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _iter_strings(value)
    elif isinstance(node, str):
        yield node


def assert_language_compliant(payload, forbidden=None) -> None:
    """Fail loudly if generated copy uses forbidden causal/absolute language.

    The declarative ``language_contract`` block itself is exempt (it names
    the forbidden phrases by design). ``forbidden`` defaults to the E3 global
    contract so E4 local copy can extend it without mutating E3 output.
    """
    phrases = FORBIDDEN_LANGUAGE if forbidden is None else tuple(forbidden)
    for text in _iter_strings(payload):
        lowered = text.lower()
        for phrase in phrases:
            if phrase.lower() in lowered:
                raise ExplainabilityError(
                    f"forbidden explanation language present: {phrase!r}")


def default_artifact_path(paths=None) -> Path:
    base = Path(paths.root) if paths is not None else V2Paths.resolve().root
    return base / OUTPUT_REL


def artifact_sha256(path) -> str:
    return _sha256_file(Path(path))


def render_global_explanation(artifact) -> str:
    """Canonical JSON text; repeated calls are byte-identical."""
    return json.dumps(artifact, indent=2, sort_keys=True,
                      allow_nan=False) + "\n"


def write_global_explanation(artifact, path=None, paths=None) -> dict:
    """Write the artifact + its SHA-256 sidecar atomically; return record."""
    dest = Path(path) if path is not None else default_artifact_path(paths)
    dest.parent.mkdir(parents=True, exist_ok=True)
    text = render_global_explanation(artifact)
    tmp = dest.with_suffix(".json.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(dest)
    sha = artifact_sha256(dest)
    sidecar = dest.with_suffix(".sha256")
    sidecar.write_text(sha + "\n", encoding="utf-8")
    return {
        "path": str(dest),
        "sha256": sha,
        "bytes": int(dest.stat().st_size),
        "sha256_sidecar": str(sidecar),
    }


def is_artifact_stale(artifact, *, predictor=None, serving_path=None) -> bool:
    """True when a stored artifact no longer matches the frozen model identity."""
    if predictor is None:
        predictor = load_frozen_explanation_model()
    if serving_path is None:
        serving_path = SERVING.default_serving_artifact_path()
    current = _model_identity(predictor, Path(serving_path))
    recorded = (artifact or {}).get("model_identity") or {}
    keys = ("serving_artifact_sha256", "specification_fingerprint",
            "feature_names_hash", "transformed_dim",
            "preprocessor_fingerprint")
    return any(recorded.get(key) != current.get(key) for key in keys)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    import argparse
    import resource
    import time

    parser = argparse.ArgumentParser(
        prog="python -m raceintel.explainability.explainability",
        description="Build the Phase-8 E3 global explanation artifact "
                    "(read-only; never retrains).")
    parser.add_argument("--out", default=None)
    parser.add_argument("--repeats", type=int, default=PERMUTATION_REPEATS)
    parser.add_argument("--base-seed", type=int, default=PERMUTATION_BASE_SEED)
    parser.add_argument("--max-races", type=int, default=None,
                        help="bounded debugging only; not for the artifact")
    parser.add_argument("--coefficients-only", action="store_true",
                        help="skip permutation (coefficient evidence only)")
    parser.add_argument("--print-sha", action="store_true")
    args = parser.parse_args(argv)

    started = time.perf_counter()
    paths = V2Paths.resolve()
    if args.coefficients_only:
        predictor = load_frozen_explanation_model()
        artifact = {
            "format": GLOBAL_EXPLANATION_FORMAT,
            "model_identity": _model_identity(
                predictor, default_serving_path(paths)),
            "explanation_space": EXPLANATION_SPACE,
            "probability_semantics": PROBABILITY_SEMANTICS,
            "transformed_feature_count": int(predictor.transformed_dim),
            "canonical_feature_count": len(predictor.feature_names),
            "transformed_features": build_transformed_feature_map(predictor),
            "numeric_coefficients": numeric_coefficient_view(predictor),
            "boolean_coefficients": boolean_coefficient_view(predictor),
            "categorical_coefficients": categorical_coefficient_view(predictor),
            "canonical_groups": canonical_group_view(predictor),
            "permutation_importance": {
                "status": "SKIPPED",
                "reason": "coefficients-only invocation"},
            "language_contract": {
                "allowed": list(ALLOWED_LANGUAGE),
                "forbidden": list(FORBIDDEN_LANGUAGE)},
            "limitations": _limitations(),
        }
        assert_language_compliant(artifact)
    else:
        artifact = build_global_explanation(
            repeats=args.repeats, base_seed=args.base_seed,
            max_races=args.max_races)
    record = write_global_explanation(artifact, path=args.out)
    elapsed = time.perf_counter() - started
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({"artifact": record, "seconds": round(elapsed, 3),
                      "peak_rss_bytes": int(peak_rss)}, indent=2))
    if args.print_sha:
        print(record["sha256"])
    return 0


def default_serving_path(paths=None):
    return SERVING.default_serving_artifact_path(
        None if paths is None else paths.root)


if __name__ == "__main__":
    raise SystemExit(main())
