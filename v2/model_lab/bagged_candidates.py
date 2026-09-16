"""M5 bagged/randomized tree candidates: ExtraTrees + RandomForest (fixed).

Two representative bagged-tree candidate families for the PRIMARY winner
task, evaluated through the exact M2/M3/M4 canonical path (adapter ->
``PredictionResult`` -> M2 evaluator -> experiment artifact -> suite
summary). M5 EXTENDS the frozen M3 path; it does not redesign it. No tuning
of any kind was performed: one fixed specification per family was chosen
BEFORE inspecting D1/D2/D3 validation results.

Fixed-specification rationale (documented before validation):

- Both forests are symmetric, conservative references: sklearn defaults
  throughout except (a) ``n_estimators=300`` (raised from the 100 default so
  the ensemble average is a credible stable reference, without choosing an
  extreme forest size) and (b) ``n_jobs=4`` for controlled local CPU use on
  the 16 GB Apple-Silicon development machine. Neither value was selected by
  observing validation performance.
- The family-defining difference is kept exactly at the library defaults:
  ``ExtraTreesClassifier(bootstrap=False)`` grows fully randomized trees on
  the full training sample (random split thresholds), while
  ``RandomForestClassifier(bootstrap=True)`` baggs samples and searches for
  the best split. This is the scientific contrast M5 exists to measure.
- ``criterion="gini"``, ``max_depth=None``, ``min_samples_split=2``,
  ``min_samples_leaf=1`` and ``max_features="sqrt"`` are the resolved sklearn
  classification defaults, recorded explicitly for identity (no hidden
  defaults). ``class_weight=None`` preserves the frozen ``state_equal``
  weighting: natural prevalence, NO resampling, NO class rebalancing.

Preprocessing: both candidates reuse the exact M3/M4 train-fitted
preprocessing (``v2.model_lab.preprocessing``: median + StandardScaler
numerics, most-frequent booleans, MISSING-sentinel + train-vocabulary one-hot
categoricals, densified output). Scaling is harmless for trees; a second
encoding architecture would create scientifically incomparable feature
semantics for no estimator-required reason. Same 84 source features, same
~106-dim transformed representation, train-fitted only, leakage-safe.

Both adapters emit ``PredictionKind.BINARY_PROBABILITY`` with
``ProbabilitySemantics.INDEPENDENT_BINARY`` (never normalized across drivers).
NO tuning, NO resampling, NO class rebalancing, NO threshold tuning, NO
calibration fitting.
"""

from __future__ import annotations

import numpy as np
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier

from v2.model_lab import preprocessing as PRE
from v2.model_lab.tree_candidates import _TreeAdapterBase
from v2.model_lab.predictions import ProbabilitySemantics

#: Canonical M5 model family names (used in experiment identity).
EXTRA_TREES_FAMILY = "extra_trees"
RANDOM_FOREST_FAMILY = "random_forest"

#: Short CLI aliases accepted by the M5 runner CLIs.
EXTRA_TREES_ALIASES = ("EXTRATREES", "ET", "EXTRA_TREES", EXTRA_TREES_FAMILY)
RANDOM_FOREST_ALIASES = ("RANDOMFOREST", "RF", "RANDOM_FOREST",
                         RANDOM_FOREST_FAMILY)

#: Task / feature / seed contract (identical to M3/M4).
M5_TASK = "winner"
M5_FEATURE_SET = "ALL_84"
M5_SEED = 42

#: Fixed, untuned ExtraTrees specification (resolved values, no hidden
#: defaults). ``bootstrap=False`` is the library default and is the defining
#: contrast against RandomForest.
EXTRA_TREES_SPEC = {
    "estimator": "ExtraTreesClassifier",
    "n_estimators": 300,
    "criterion": "gini",
    "max_depth": None,
    "min_samples_split": 2,
    "min_samples_leaf": 1,
    "max_features": "sqrt",
    "bootstrap": False,
    "class_weight": None,
    "n_jobs": 4,
    "random_state": 42,
}

#: Fixed, untuned RandomForest specification (resolved values, no hidden
#: defaults). ``bootstrap=True`` is the library default and is the defining
#: contrast against ExtraTrees.
RANDOM_FOREST_SPEC = {
    "estimator": "RandomForestClassifier",
    "n_estimators": 300,
    "criterion": "gini",
    "max_depth": None,
    "min_samples_split": 2,
    "min_samples_leaf": 1,
    "max_features": "sqrt",
    "bootstrap": True,
    "class_weight": None,
    "n_jobs": 4,
    "random_state": 42,
}

#: sklearn runtime recorded at fit time (stored in artifacts).
SKLEARN_VERSION = __import__("sklearn").__version__


def extra_trees_model_parameters() -> dict:
    """Resolved ExtraTrees parameters for identity (no hidden defaults)."""
    return dict(EXTRA_TREES_SPEC)


def random_forest_model_parameters() -> dict:
    """Resolved RandomForest parameters for identity (no hidden defaults)."""
    return dict(RANDOM_FOREST_SPEC)


def build_extra_trees_estimator() -> ExtraTreesClassifier:
    """Construct one fresh untuned ExtraTrees estimator."""
    return ExtraTreesClassifier(
        n_estimators=EXTRA_TREES_SPEC["n_estimators"],
        criterion=EXTRA_TREES_SPEC["criterion"],
        max_depth=EXTRA_TREES_SPEC["max_depth"],
        min_samples_split=EXTRA_TREES_SPEC["min_samples_split"],
        min_samples_leaf=EXTRA_TREES_SPEC["min_samples_leaf"],
        max_features=EXTRA_TREES_SPEC["max_features"],
        bootstrap=EXTRA_TREES_SPEC["bootstrap"],
        class_weight=EXTRA_TREES_SPEC["class_weight"],
        n_jobs=EXTRA_TREES_SPEC["n_jobs"],
        random_state=EXTRA_TREES_SPEC["random_state"],
    )


def build_random_forest_estimator() -> RandomForestClassifier:
    """Construct one fresh untuned RandomForest estimator."""
    return RandomForestClassifier(
        n_estimators=RANDOM_FOREST_SPEC["n_estimators"],
        criterion=RANDOM_FOREST_SPEC["criterion"],
        max_depth=RANDOM_FOREST_SPEC["max_depth"],
        min_samples_split=RANDOM_FOREST_SPEC["min_samples_split"],
        min_samples_leaf=RANDOM_FOREST_SPEC["min_samples_leaf"],
        max_features=RANDOM_FOREST_SPEC["max_features"],
        bootstrap=RANDOM_FOREST_SPEC["bootstrap"],
        class_weight=RANDOM_FOREST_SPEC["class_weight"],
        n_jobs=RANDOM_FOREST_SPEC["n_jobs"],
        random_state=RANDOM_FOREST_SPEC["random_state"],
    )


class _BaggedAdapterBase(_TreeAdapterBase):
    """Shared M5 adapter: M1 lifecycle + forest fit-screen sanity."""

    spec: dict = {}

    def _estimator_sanity(self) -> dict:
        importances = None
        try:
            values = np.asarray(
                self._estimator.feature_importances_, dtype=float)
            if values.size and np.all(np.isfinite(values)):
                importances = {
                    "n_features": int(values.size),
                    "finite": True,
                    "nonzero": int(np.count_nonzero(values)),
                }
        except (AttributeError, ValueError):
            importances = None
        return {
            "n_estimators_configured": int(self.spec["n_estimators"]),
            "fitted_tree_count": int(len(self._estimator.estimators_)),
            "bootstrap": bool(self.spec["bootstrap"]),
            "max_features": str(self.spec["max_features"]),
            "feature_importances": importances,
            "feature_importance_note": (
                "raw mean-decrease-in-impurity recorded as a fit screen only; "
                "explainability is out of scope for M5"),
        }

    def metadata(self) -> dict:
        return {
            "family": self.family,
            "model_parameters": dict(self.spec),
            "preprocessing": PRE.preprocessing_contract_dict(),
            "sklearn_version": SKLEARN_VERSION,
            "feature_set": M5_FEATURE_SET,
            "task": M5_TASK,
            "seed": M5_SEED,
            "positive_class": 1,
            "probability_semantics": ProbabilitySemantics.INDEPENDENT_BINARY.value,
        }


class ExtraTreesAdapter(_BaggedAdapterBase):
    """Concrete M1 ModelAdapter for the M5 ExtraTrees candidate."""

    family = EXTRA_TREES_FAMILY
    spec = EXTRA_TREES_SPEC

    def _build_estimator(self):  # noqa: ANN201
        return build_extra_trees_estimator()


class RandomForestAdapter(_BaggedAdapterBase):
    """Concrete M1 ModelAdapter for the M5 RandomForest candidate."""

    family = RANDOM_FOREST_FAMILY
    spec = RANDOM_FOREST_SPEC

    def _build_estimator(self):  # noqa: ANN201
        return build_random_forest_estimator()


#: Family name -> adapter class (the only trainable M5 estimators).
ADAPTERS = {
    EXTRA_TREES_FAMILY: ExtraTreesAdapter,
    RANDOM_FOREST_FAMILY: RandomForestAdapter,
}
