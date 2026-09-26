"""Phase-8 E3: global explainability of the frozen winner model.

Scope: global coefficient + permutation evidence only (no local/driver
explanations — that is E4). These tests pin:

- frozen model identity (serving SHA, spec fingerprint, 84 / 106 dims);
- the 106 -> 84 transformed/canonical mapping and the frozen family map;
- fitted-preprocessor statistics (never recomputed from current data);
- categorical one-hot semantics (no dropped reference, unknown=ignore);
- the 2025 and label firewalls;
- a deterministic, race-preserving permutation protocol on the frozen
  race-macro log-loss metric, including red-team guards;
- deterministic artifact ordering + identity/staleness;
- the explanation language contract;
- absence of SHAP.

They never retrain, retune, or touch 2025.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from model_lab_helpers import (  # noqa: E402
    load_canonical_or_skip,
    require_generated_artifact,
)
from v2 import explainability as X  # noqa: E402
from v2.experiments.feature_sets import PRIMARY_GROUP_ORDER  # noqa: E402

SERVING_SHA = (
    "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4")
SPEC_FINGERPRINT = (
    "3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d")
PHASE2_CONTENT_HASH = (
    "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db")


@pytest.fixture(scope="module")
def predictor():
    return X.load_frozen_explanation_model()


@pytest.fixture(scope="module")
def canonical():
    return load_canonical_or_skip()


@pytest.fixture(scope="module")
def map_entries(predictor):
    return X.build_transformed_feature_map(predictor)


@pytest.fixture(scope="module")
def small_population(canonical, predictor):
    pop = X.permutation_population(canonical, predictor)
    return X._truncate_population(pop, 3)


# ---------------------------------------------------------------------------
# Frozen model identity
# ---------------------------------------------------------------------------

def test_frozen_model_identity(predictor):
    assert predictor.feature_names == tuple(sorted(predictor.feature_names))
    assert len(predictor.feature_names) == 84
    assert predictor.transformed_dim == 106
    estimator = predictor._estimator
    assert type(estimator).__name__ == "LogisticRegression"
    assert estimator.coef_.shape == (1, 106)
    assert estimator.intercept_.shape == (1,)
    assert float(estimator.C) == 0.01
    assert estimator.solver == "lbfgs"
    assert int(estimator.max_iter) == 1000
    assert estimator.class_weight is None
    assert int(estimator.random_state) == 42
    assert predictor.specification_fingerprint == SPEC_FINGERPRINT


def test_serving_artifact_sha_is_frozen():
    from v2.model_lab import serving as SERVING

    path = require_generated_artifact(
        SERVING.default_serving_artifact_path(),
        purpose="E3 serving artifact")
    assert X.artifact_sha256(path) == SERVING_SHA


def test_preprocessor_is_fitted(predictor):
    pre = predictor._preprocessor
    assert len(pre.numeric_columns) == 70
    assert len(pre.boolean_columns) == 11
    assert len(pre.categorical_columns) == 3
    assert pre.output_dim == 106


# ---------------------------------------------------------------------------
# PART B — 106 -> 84 transformed feature mapping
# ---------------------------------------------------------------------------

def test_transformed_dimensions_mapped(predictor, map_entries):
    assert len(map_entries) == 106
    assert [e["transformed_index"] for e in map_entries] == list(range(106))
    assert len({e["transformed_name"] for e in map_entries}) == 106
    counts = {}
    for entry in map_entries:
        counts[entry["feature_type"]] = counts.get(entry["feature_type"], 0) + 1
    assert counts == {"numeric": 70, "boolean": 11, "categorical": 25}


def test_transform_names_match_get_feature_names_out(predictor, map_entries):
    authority = [str(n) for n in
                 predictor._preprocessor.transformer.get_feature_names_out()]
    assert [e["transformed_name"] for e in map_entries] == authority


def test_every_canonical_feature_mapped(predictor, map_entries):
    seen = {e["canonical_feature"] for e in map_entries}
    assert seen == set(predictor.feature_names)
    assert len(seen) == 84


def test_prefix_semantics(predictor, map_entries):
    for entry in map_entries:
        name = entry["transformed_name"]
        if entry["feature_type"] == "numeric":
            assert name == f"num__{entry['canonical_feature']}"
        elif entry["feature_type"] == "boolean":
            assert name == f"bool__{entry['canonical_feature']}"
        else:
            assert name.startswith(f"cat__{entry['canonical_feature']}_")


def test_feature_family_mapping(predictor, map_entries):
    families = {e["feature_family"] for e in map_entries}
    assert families == set(PRIMARY_GROUP_ORDER)
    groups = X.canonical_group_view(predictor, map_entries)
    total = sum(len(v) for v in groups["groups"].values())
    assert total == 84
    assert groups["family_order"] == list(PRIMARY_GROUP_ORDER)


# ---------------------------------------------------------------------------
# PART E — coefficient evidence from the fitted artifact
# ---------------------------------------------------------------------------

def test_numeric_scaler_statistics_from_fitted_artifact(predictor):
    view = X.numeric_coefficient_view(predictor)
    assert len(view) == 70
    pre = predictor._preprocessor
    num = pre.transformer.named_transformers_["num"]
    medians = np.asarray(num.named_steps["impute"].statistics_, dtype=float)
    means = np.asarray(num.named_steps["scale"].mean_, dtype=float)
    scales = np.asarray(num.named_steps["scale"].scale_, dtype=float)
    for position, row in enumerate(view):
        assert row["training_median"] == float(medians[position])
        assert row["training_mean"] == float(means[position])
        assert row["training_scale"] == float(scales[position])
        sign = np.sign(row["coefficient"])
        assert ("positive" in row["direction"]) == (sign > 0)
        assert ("negative" in row["direction"]) == (sign < 0)


def test_boolean_imputer_statistics(predictor):
    view = X.boolean_coefficient_view(predictor)
    assert len(view) == 11
    pre = predictor._preprocessor
    boolean = pre.transformer.named_transformers_["bool"]
    modes = np.asarray(boolean.named_steps["impute"].statistics_, dtype=float)
    for position, row in enumerate(view):
        assert row["training_imputation_mode"] == float(modes[position])
        assert row["training_imputation_mode"] in (0.0, 1.0)
    note = view[0]["units_note"]
    assert "unscaled" in note


def test_categorical_vocabulary(predictor):
    view = X.categorical_coefficient_view(predictor)
    pre = predictor._preprocessor
    encoder = pre.transformer.named_transformers_[
        "cat"].named_steps["encode"]
    assert set(view) == {"compound", "stint_compound", "track_state"}
    for column, categories in zip(pre.categorical_columns,
                                  encoder.categories_):
        node = view[str(column)]
        assert node["fitted_categories"] == [str(c) for c in categories]
        assert node["fitted_category_count"] == len(categories)
        assert len(node["category_coefficients"]) == len(categories)


def test_unknown_category_semantics(predictor):
    view = X.categorical_coefficient_view(predictor)
    for node in view.values():
        assert node["reference_category"] is None
        assert "all-zero" in node["unknown_behavior"]
        assert node["missing_category_present"] is True


def test_categorical_grouping_preserves_categories(predictor, map_entries):
    groups = X.canonical_group_view(predictor, map_entries)
    for column in ("compound", "stint_compound", "track_state"):
        assert column in groups["groups"]["STATE"]
    view = X.categorical_coefficient_view(predictor)
    assert len(view["compound"]["category_coefficients"]) == 9
    assert "summed" not in json.dumps(view).lower()
    assert "policy" in groups


def test_no_fake_universal_coefficient_ranking(predictor):
    view = X.categorical_coefficient_view(predictor)
    for node in view.values():
        assert "category_coefficients" in node
        assert set(node).isdisjoint({"importance", "global_importance",
                                     "rank", "score"})


# ---------------------------------------------------------------------------
# PART F — population + firewalls
# ---------------------------------------------------------------------------

def test_population_is_pre_2025_only(canonical, predictor):
    pop = X.permutation_population(canonical, predictor)
    assert set(pop["seasons"]) <= set(range(2018, 2025))
    assert 2025 not in pop["seasons"]
    assert pop["n_races"] == 149
    assert pop["n_rows"] > 0


def test_2025_firewall_fails_closed():
    with pytest.raises(X.ExplainabilityError):
        X.assert_pre_2025_seasons([2018, 2019, 2025])
    with pytest.raises(X.ExplainabilityError):
        X.assert_pre_2025_seasons([2026])
    assert X.assert_pre_2025_seasons([2018, 2024]) == [2018, 2024]


def test_injected_2025_row_is_excluded(canonical, predictor):
    class _Stub:
        def __init__(self, frame):
            self.frame = frame

    frame = canonical.frame.copy()
    eligible = np.flatnonzero(frame["season"].to_numpy() <= 2024)[:1]
    frame.loc[frame.index[eligible], "season"] = 2025
    base = X.permutation_population(canonical, predictor)
    injected = X.permutation_population(_Stub(frame), predictor)
    assert injected["n_rows"] == base["n_rows"] - 1
    assert 2025 not in injected["seasons"]


def test_label_firewall(canonical, predictor):
    manifest = canonical.manifest
    predictive = set(manifest["predictive_columns"])
    forbidden = set(manifest["label_columns"])
    forbidden |= set(manifest.get("label_companion_columns", []))
    forbidden |= set(manifest["task_eligibility_columns"])
    assert predictive.isdisjoint(forbidden)
    pop = X.permutation_population(canonical, predictor)
    assert "is_winner" not in pop["frame"].columns
    assert list(pop["frame"].columns) == list(predictor.feature_names)


def test_target_not_shuffled_with_feature(small_population, predictor):
    before = small_population["target"].copy()
    X.permutation_importance(small_population, predictor, repeats=2,
                             feature_names=["position", "compound"])
    assert np.array_equal(before, small_population["target"])


# ---------------------------------------------------------------------------
# PART F — permutation unit, determinism, metric
# ---------------------------------------------------------------------------

def _numeric(values):
    import pandas as pd

    return pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy()


def _sorted_nan_last(values):
    array = _numeric(values)
    return np.sort(np.where(np.isnan(array), np.inf, array))


def test_permutation_preserves_race_identity(small_population):
    frame = small_population["frame"]
    codes, _ = X._race_codes(small_population["race_ids"])
    rng = np.random.default_rng([1, 2, 3])
    column = frame["position"]
    permuted = X.permute_feature_within_race(column, codes, rng)
    for code in range(int(codes.max()) + 1):
        mask = codes == code
        assert np.array_equal(
            _sorted_nan_last(column.to_numpy()[mask]),
            _sorted_nan_last(np.asarray(permuted, dtype=object)[mask]))


def test_permutation_not_global_row_shuffle(small_population):
    """A global shuffle would move values across races; this must not."""
    frame = small_population["frame"]
    races = small_population["race_ids"]
    codes, _ = X._race_codes(races)
    rng = np.random.default_rng([7, 7, 7])
    permuted = X.permute_feature_within_race(frame["gap_to_leader_seconds"],
                                             codes, rng)
    original = frame["gap_to_leader_seconds"].to_numpy()
    # At least one race has an unchanged (as a set) column; globally the
    # order changed for a non-constant feature.
    changed = False
    for code in range(int(codes.max()) + 1):
        mask = codes == code
        before = original[mask]
        after = _numeric(np.asarray(permuted, dtype=object)[mask])
        if not np.array_equal(before, after, equal_nan=True):
            changed = True
    assert changed


def test_permutation_deterministic(small_population, predictor):
    names = ["position", "compound", "gap_to_leader_seconds"]
    first = X.permutation_importance(small_population, predictor, repeats=3,
                                     base_seed=42, feature_names=names)
    second = X.permutation_importance(small_population, predictor, repeats=3,
                                      base_seed=42, feature_names=names)
    assert first == second


def test_permutation_seed_is_effective(small_population, predictor):
    names = ["position", "compound", "gap_to_leader_seconds"]
    first = X.permutation_importance(small_population, predictor, repeats=2,
                                     base_seed=1, feature_names=names)
    second = X.permutation_importance(small_population, predictor, repeats=2,
                                      base_seed=2, feature_names=names)
    assert first["results"] != second["results"]
    assert first["protocol"]["base_seed"] == 1


def test_permutation_unit_and_metric_declared(small_population, predictor):
    result = X.permutation_importance(small_population, predictor, repeats=2,
                                      feature_names=["position"])
    protocol = result["protocol"]
    assert protocol["metric"] == "race_macro_log_loss"
    assert "race_macro" in protocol["aggregation"]
    assert protocol["unit"] == "state_within_race (race identity preserved)"
    assert "IN_SAMPLE" in protocol["population"]["evidence_class"]
    assert "NOT temporally out-of-sample" in \
        protocol["population"]["evidence_class"]
    assert protocol["population"]["holdout_2025"] == "excluded"


def test_race_macro_metric_correctness(small_population, predictor):
    frame = small_population["frame"]
    target = small_population["target"]
    races = small_population["race_ids"]
    probability = predictor.predict_proba(frame)
    value = X.race_macro_log_loss(target, probability, races)
    groups = {}
    for y, p, race in zip(target, probability, races):
        groups.setdefault(race, []).append((y, p))
    manual = []
    for race in sorted(groups):
        pairs = groups[race]
        loss = -np.mean([
            y * np.log(max(p, 1e-15)) + (1 - y) * np.log(max(1 - p, 1e-15))
            for y, p in pairs])
        manual.append(float(loss))
    assert value == pytest.approx(float(np.mean(manual)), abs=1e-12)


def test_one_hot_columns_never_permuted_independently(small_population,
                                                      predictor):
    """Permuting the raw categorical input keeps a valid one-hot block."""
    frame = small_population["frame"]
    codes, _ = X._race_codes(small_population["race_ids"])
    rng = np.random.default_rng([9, 9, 9])
    probe = frame.copy()
    probe["compound"] = X.permute_feature_within_race(
        frame["compound"], codes, rng)
    matrix = predictor._preprocessor.transform(probe)
    names = list(predictor._preprocessor.transformer.get_feature_names_out())
    block = [index for index, name in enumerate(names)
             if name.startswith("cat__compound_")]
    block_matrix = matrix[:, block]
    row_sums = block_matrix.sum(axis=1)
    # unknown categories fire the all-zero block; fitted ones fire exactly one
    assert np.all(np.isin(row_sums, (0.0, 1.0)))


# ---------------------------------------------------------------------------
# PART H — deterministic artifact, identity / staleness
# ---------------------------------------------------------------------------

def test_artifact_deterministic_ordering(canonical, predictor):
    first = X.build_global_explanation(canonical=canonical, predictor=predictor,
                                       repeats=1, base_seed=42, max_races=2)
    second = X.build_global_explanation(canonical=canonical, predictor=predictor,
                                        repeats=1, base_seed=42, max_races=2)
    assert X.render_global_explanation(first) == \
        X.render_global_explanation(second)
    assert first["format"] == X.GLOBAL_EXPLANATION_FORMAT
    assert first["explanation_space"] == "LOG_ODDS"
    assert first["probability_semantics"] == "INDEPENDENT_BINARY"
    assert first["transformed_feature_count"] == 106
    assert first["canonical_feature_count"] == 84
    assert first["model_identity"]["serving_artifact_sha256"] == SERVING_SHA
    assert first["model_identity"]["specification_fingerprint"] == \
        SPEC_FINGERPRINT


def test_artifact_identity_staleness(canonical, predictor):
    artifact = X.build_global_explanation(
        canonical=canonical, predictor=predictor, repeats=1, base_seed=42,
        max_races=2)
    assert not X.is_artifact_stale(artifact, predictor=predictor)
    tampered = json.loads(X.render_global_explanation(artifact))
    tampered["model_identity"]["serving_artifact_sha256"] = "deadbeef"
    assert X.is_artifact_stale(tampered, predictor=predictor)


def test_render_is_byte_stable(predictor, canonical):
    artifact = X.build_global_explanation(canonical=canonical, predictor=predictor,
                                          repeats=1, base_seed=42, max_races=1)
    text = X.render_global_explanation(artifact)
    assert text.endswith("\n")
    assert json.loads(text)["format"] == X.GLOBAL_EXPLANATION_FORMAT


# ---------------------------------------------------------------------------
# Language contract + SHAP
# ---------------------------------------------------------------------------

def test_language_contract_guard():
    X.assert_language_compliant({"note": "a positive model coefficient"})
    with pytest.raises(X.ExplainabilityError):
        X.assert_language_compliant({"note": "this caused the win"})
    with pytest.raises(X.ExplainabilityError):
        X.assert_language_compliant({"note": "the model thinks it is fastest"})


def test_stored_artifact_language_and_shape():
    path = require_generated_artifact(X.default_artifact_path(),
                                      purpose="E3 global artifact")
    artifact = json.loads(Path(path).read_text())
    X.assert_language_compliant(artifact)
    assert artifact["format"] == X.GLOBAL_EXPLANATION_FORMAT
    assert artifact["transformed_feature_count"] == 106
    assert artifact["canonical_feature_count"] == 84
    assert artifact["permutation_importance"]["status"] == "OK"


def test_stored_artifact_is_current_and_hash_matches():
    path = require_generated_artifact(X.default_artifact_path(),
                                      purpose="E3 global artifact")
    sha = X.artifact_sha256(path)
    sidecar = Path(path).with_suffix(".sha256")
    if sidecar.exists():
        assert sidecar.read_text().strip() == sha
    artifact = json.loads(Path(path).read_text())
    assert not X.is_artifact_stale(artifact)


def test_shap_absent():
    assert "shap" not in sys.modules
    source = Path(X.__file__).read_text()
    assert "import shap" not in source
    assert "shap." not in source


def test_no_sklearn_permutation_dependency():
    source = Path(X.__file__).read_text()
    assert "sklearn.inspection" not in source
    assert "from sklearn" not in source


def test_artifact_hash_is_deterministic(canonical, predictor, tmp_path):
    artifact = X.build_global_explanation(canonical=canonical, predictor=predictor,
                                          repeats=1, base_seed=42, max_races=2)
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    X.write_global_explanation(artifact, path=first)
    X.write_global_explanation(artifact, path=second)
    assert hashlib.sha256(first.read_bytes()).hexdigest() == \
        hashlib.sha256(second.read_bytes()).hexdigest()
