"""Phase-3 Model Lab — M0 protocol freeze (experimental constitution).

Configuration, contracts and validation ONLY. This module defines *how*
Phase 3 will evaluate models; it contains no estimator, no fit, no
prediction, no metric computation, no preprocessing execution, no split
execution and no matrix mutation. Nothing here may bypass the frozen
Phase-2 artifacts: versions, counts, hashes and task masks are verified
against the F15 manifest / F16 ablation config, never re-derived.

The protocol is versioned independently (`MODEL_LAB_PROTOCOL_VERSION`);
it never bumps `FEATURE_SET_VERSION`, `LABEL_SET_VERSION`,
`MATRIX_VERSION` or `ABLATION_CONFIG_VERSION`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from v2.config import V2Paths
from v2.experiments.feature_sets import (
    ABLATION_CONFIG_VERSION,
    all_feature_set_names,
    resolve_feature_set,
)
from v2.features.build_matrix import (
    MATRIX_VERSION,
    TASK_ELIGIBILITY_COLUMNS,
    TASKS,
    content_hash,
    load_manifest,
    load_matrix,
)
from v2.features.registry import FEATURE_SET_VERSION
from v2.labels.contracts import LABEL_SET_VERSION

# ---------------------------------------------------------------------------
# Protocol identity / Phase-2 freeze boundary
# ---------------------------------------------------------------------------

#: Independent Model-Lab protocol version. Never aliases a Phase-2 version.
MODEL_LAB_PROTOCOL_VERSION = "v1"

#: Path (repo-relative) of the deterministic machine-readable protocol.
PROTOCOL_FILENAME = "model_lab_protocol_v1.json"
PROTOCOL_REL_PATH = f"docs/generated/{PROTOCOL_FILENAME}"

#: Phase-2 freeze boundary this protocol consumes (immutable input).
PHASE1_FREEZE_TAG = "v2-data-platform-phase1"
PHASE1_FREEZE_COMMIT = "2fa0a7c54f9fbcf7dd52fe71ea9ced620304a4ee"
PHASE2_FREEZE_TAG = "v2-temporal-feature-engine-phase2"
PHASE2_FREEZE_COMMIT = "adb558395c07733e5f0f5051a92714d8b037951c"

#: Required Phase-2 semantic versions.
REQUIRED_FEATURE_SET_VERSION = "v8"
REQUIRED_LABEL_SET_VERSION = "v1"
REQUIRED_MATRIX_VERSION = "v1"
REQUIRED_ABLATION_CONFIG_VERSION = "v1"

#: Required Phase-2 artifact facts (counts + fingerprints).
EXPECTED_PREDICTIVE_COUNT = 84
EXPECTED_LABEL_COUNT = 7
EXPECTED_MATRIX_ROWS = 189420
EXPECTED_MATRIX_COLUMNS = 106
EXPECTED_RACE_COUNT = 173
EXPECTED_SEASON_RANGE = (2018, 2025)
EXPECTED_ORDINAL_ELIGIBLE = 178963
EXPECTED_GAIN_LOSS_ELIGIBLE = 189126
EXPECTED_BINARY_ELIGIBLE = 189420

EXPECTED_MATRIX_CONTENT_HASH = (
    "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db")
EXPECTED_MATRIX_SCHEMA_HASH = (
    "b1ccbc62380da8e841e7b2d78d8d37aac2b67c72b0306a2495fbabc3fb224f0e")
EXPECTED_FEATURE_REGISTRY_FINGERPRINT = (
    "a04d5475e8ac113bfffe8af3ba35db5dedf127d0306803dcb71332c5be863fe6")
EXPECTED_LABEL_REGISTRY_FINGERPRINT = (
    "0a4d0bb6369f880add679731f46e992f0bee98b2930caeefa392297cf29515cd")
EXPECTED_ABLATION_SEMANTIC_HASH = (
    "c88bcbaafe72ff2a615f24563d631f4e313cbc1d41e23b3818d3f9d86f6b087c")
EXPECTED_MATRIX_PARQUET_SHA256 = (
    "b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3")
EXPECTED_MANIFEST_SHA256 = (
    "b6a63f5eb0577906ee6496d05c4f7a20c3eb79f2f8048d4ff06acb764d6cbc62")
EXPECTED_ABLATION_CONFIG_SHA256 = (
    "bb59d936b14552779a4ab192c4d3e9c9d1e2ff31e2ef8608b30c44ed86f2f5a7")


class ModelLabProtocolError(RuntimeError):
    """Fatal Model-Lab protocol/contract violation. Never repairs."""


# ---------------------------------------------------------------------------
# Temporal frame: chronology, development era, folds, protected holdout
# ---------------------------------------------------------------------------

#: Rich-data era available to Phase 3.
FULL_SEASON_RANGE = (2018, 2025)
#: Development era: everything a model may see before final selection.
DEVELOPMENT_SEASONS = tuple(range(2018, 2025))  # 2018–2024 inclusive
#: Protected final holdout: never touched before model/config selection.
PROTECTED_HOLDOUT_SEASON = 2025
#: Final fit window (after selection, before the single locked holdout run).
FINAL_FIT_SEASONS = tuple(range(2018, 2025))  # 2018–2024 inclusive

#: Canonical chronology key. Never filesystem order, row order or labels.
CHRONOLOGY_KEY = ("season", "round_no", "race_id")


@dataclass(frozen=True)
class DevelopmentFold:
    """One expanding-window development fold (TRAIN strictly before VAL)."""

    fold_id: str
    train_seasons: tuple
    validation_season: int
    rationale: str = ""

    @property
    def train_season_range(self) -> tuple:
        return (self.train_seasons[0], self.train_seasons[-1])


DEVELOPMENT_FOLDS: tuple = (
    DevelopmentFold(
        "D1", (2018, 2019, 2020, 2021), 2022,
        "Earliest fold: four full seasons of history, first validation "
        "season kept in the development era."),
    DevelopmentFold(
        "D2", (2018, 2019, 2020, 2021, 2022), 2023,
        "Expanding window; validation strictly after all training races."),
    DevelopmentFold(
        "D3", (2018, 2019, 2020, 2021, 2022, 2023), 2024,
        "Latest development fold; 2025 stays protected."),
)

#: First validation season is 2022: 2018–2021 supplies four seasons, which
#: leaves 2025 protected without adding folds merely to raise fold count.
FOLD_START_RATIONALE = (
    "Training 2018–2021 gives four seasons and allows three expanding "
    "folds while retaining 2025 as the protected final holdout. No fold is "
    "added only to increase fold count.")

#: Splitting is race-chronological. Row-level randomness is forbidden.
ALLOWED_SPLIT_POLICIES = ("expanding_window_race_chronology",)
FORBIDDEN_SPLIT_POLICIES = (
    "random_row_split",
    "shuffled_train_test_split",
    "random_kfold_over_states",
    "random_state_split",
)

#: Partial race sessions (factual Phase-1 limitation; retained, not dropped).
PARTIAL_RACE_IDS = ("2021-r12-R", "2022-r18-R")


def validate_chronology_key(key=CHRONOLOGY_KEY) -> None:
    if tuple(key) != CHRONOLOGY_KEY:
        raise ModelLabProtocolError(
            f"chronology key {key!r} != frozen {CHRONOLOGY_KEY!r}")


def validate_fold(fold: DevelopmentFold) -> None:
    if not fold.train_seasons:
        raise ModelLabProtocolError(f"{fold.fold_id}: empty training seasons")
    if fold.validation_season in fold.train_seasons:
        raise ModelLabProtocolError(
            f"{fold.fold_id}: validation season is inside training")
    if max(fold.train_seasons) >= fold.validation_season:
        raise ModelLabProtocolError(
            f"{fold.fold_id}: train season {max(fold.train_seasons)} >= "
            f"validation season {fold.validation_season}")
    if fold.validation_season == PROTECTED_HOLDOUT_SEASON:
        raise ModelLabProtocolError(
            f"{fold.fold_id}: protected holdout cannot be a validation fold")
    if PROTECTED_HOLDOUT_SEASON in fold.train_seasons:
        raise ModelLabProtocolError(
            f"{fold.fold_id}: protected holdout leaked into training")
    if sorted(set(fold.train_seasons)) != list(fold.train_seasons):
        raise ModelLabProtocolError(f"{fold.fold_id}: training seasons not "
                                    "strictly ordered/unique")
    if tuple(range(fold.train_seasons[0], fold.train_seasons[-1] + 1)) \
            != fold.train_seasons:
        raise ModelLabProtocolError(
            f"{fold.fold_id}: training seasons are not contiguous")


def validate_folds(folds=DEVELOPMENT_FOLDS) -> None:
    seen_ids: set = set()
    for fold in folds:
        if fold.fold_id in seen_ids:
            raise ModelLabProtocolError(f"duplicate fold id {fold.fold_id!r}")
        seen_ids.add(fold.fold_id)
        validate_fold(fold)
    # Expanding windows must partition the development era chronologically.
    for a, b in zip(folds, folds[1:]):
        if b.validation_season <= a.validation_season:
            raise ModelLabProtocolError(
                "fold validation seasons are not strictly increasing")
        if not set(a.train_seasons) < set(b.train_seasons):
            raise ModelLabProtocolError(
                "development folds are not nested expanding windows")
    if folds[-1].validation_season != DEVELOPMENT_SEASONS[-1]:
        raise ModelLabProtocolError(
            "last development fold must validate on the last development "
            "season")


def validate_holdout_policy() -> None:
    if PROTECTED_HOLDOUT_SEASON in DEVELOPMENT_SEASONS:
        raise ModelLabProtocolError("holdout season is in the development era")
    if PROTECTED_HOLDOUT_SEASON in FINAL_FIT_SEASONS:
        raise ModelLabProtocolError("holdout season is in the final-fit era")
    if FINAL_FIT_SEASONS != DEVELOPMENT_SEASONS:
        raise ModelLabProtocolError(
            "final-fit era must equal the development era (2018–2024)")


def validate_split_policy(name: str) -> None:
    if name not in ALLOWED_SPLIT_POLICIES:
        raise ModelLabProtocolError(
            f"split policy {name!r} not allowed; permitted: "
            f"{list(ALLOWED_SPLIT_POLICIES)}")
    if name in FORBIDDEN_SPLIT_POLICIES:
        raise ModelLabProtocolError(f"split policy {name!r} is forbidden")


# ---------------------------------------------------------------------------
# Task inventory (Phase-2 masks are the only eligibility authority)
# ---------------------------------------------------------------------------

class TaskTier(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"
    DEFERRED = "DEFERRED"


class TaskKind(str, Enum):
    BINARY = "binary"
    ORDINAL = "ordinal"
    REGRESSION = "regression"


@dataclass(frozen=True)
class TaskSpec:
    name: str
    tier: TaskTier
    kind: TaskKind
    label_column: str | None
    eligibility_mask: str | None
    rationale: str


#: Model-Lab task inventory. Phase-2 `TASKS` entries provide the exact
#: (label, mask) pairs for the six materialized tasks; `position_change` is a
#: frozen SPECIFIED label whose only defensible Phase-2 eligibility mask is
#: `eligible_gain_loss` (== position_change_from_state.notna()); DNF has no
#: frozen target and stays DEFERRED.
_TASK_SPECS: tuple = (
    TaskSpec(
        "winner", TaskTier.PRIMARY, TaskKind.BINARY,
        "is_winner", "eligible_is_winner",
        "Primary selection task: in-race P(win) feeding the product and "
        "downstream Monte Carlo/strategy. Exactly one winner per race."),
    TaskSpec(
        "podium", TaskTier.SECONDARY, TaskKind.BINARY,
        "is_podium", "eligible_is_podium",
        "P(finish <= 3); exactly three per race."),
    TaskSpec(
        "points", TaskTier.SECONDARY, TaskKind.BINARY,
        "scored_points", "eligible_scored_points",
        "P(officially scored > 0); half-points included by the frozen flag."),
    TaskSpec(
        "final_position", TaskTier.SECONDARY, TaskKind.ORDINAL,
        "final_position", "eligible_ordinal_final_position",
        "Ordinal finishing position; ordinal mask only, never non-null "
        "position."),
    TaskSpec(
        "position_change", TaskTier.SECONDARY, TaskKind.REGRESSION,
        "position_change_from_state", "eligible_gain_loss",
        "Continuous current-minus-final position; uses the frozen "
        "gain/loss eligibility mask. Not an overtake count."),
    TaskSpec(
        "gain", TaskTier.SECONDARY, TaskKind.BINARY,
        "gains_position_by_finish", "eligible_gain_loss",
        "P(finishes ahead of current slot)."),
    TaskSpec(
        "loss", TaskTier.SECONDARY, TaskKind.BINARY,
        "loses_position_by_finish", "eligible_gain_loss",
        "P(finishes behind current slot)."),
    TaskSpec(
        "dnf", TaskTier.DEFERRED, TaskKind.BINARY,
        None, None,
        "No frozen Phase-2 DNF target exists; M0 invents none. A binary "
        "event definition is a prerequisite for M12."),
)

TASK_SPECS: dict = {spec.name: spec for spec in _TASK_SPECS}
PRIMARY_TASK = "winner"
TASK_ORDER: tuple = tuple(spec.name for spec in _TASK_SPECS)


def validate_task(task: str) -> TaskSpec:
    if task not in TASK_SPECS:
        raise ModelLabProtocolError(
            f"unknown task {task!r}; known: {list(TASK_ORDER)}")
    spec = TASK_SPECS[task]
    if spec.tier is TaskTier.DEFERRED:
        raise ModelLabProtocolError(
            f"task {task!r} is DEFERRED and has no frozen target")
    return spec


def validate_task_contract() -> None:
    """Every materialized Phase-2 task must map to the exact frozen pair."""
    for name, (label_col, mask_col) in TASKS.items():
        if name not in TASK_SPECS:
            raise ModelLabProtocolError(
                f"Phase-2 task {name!r} missing from Model-Lab inventory")
        spec = TASK_SPECS[name]
        if (spec.label_column, spec.eligibility_mask) != (label_col, mask_col):
            raise ModelLabProtocolError(
                f"task {name!r} contract drift: spec "
                f"{(spec.label_column, spec.eligibility_mask)} != Phase-2 "
                f"{(label_col, mask_col)}")
    for name, spec in TASK_SPECS.items():
        if spec.eligibility_mask and spec.eligibility_mask \
                not in TASK_ELIGIBILITY_COLUMNS:
            raise ModelLabProtocolError(
                f"task {name!r} mask {spec.eligibility_mask!r} is not a "
                "frozen Phase-2 mask")
    if TASK_SPECS[PRIMARY_TASK].tier is not TaskTier.PRIMARY:
        raise ModelLabProtocolError("primary task is not marked PRIMARY")


def task_eligibility_contract() -> dict:
    return {
        name: {
            "tier": spec.tier.value,
            "kind": spec.kind.value,
            "label_column": spec.label_column,
            "eligibility_mask": spec.eligibility_mask,
        }
        for name, spec in TASK_SPECS.items()
    }


# ---------------------------------------------------------------------------
# Metrics (frozen before any candidate result is observed)
# ---------------------------------------------------------------------------

#: Probability quality is primary: the platform consumes probabilities.
BINARY_PRIMARY_METRICS = ("log_loss", "brier")
BINARY_SECONDARY_METRICS = ("roc_auc", "pr_auc")
RACE_LEVEL_WINNER_METRICS = (
    "winner_top1_accuracy",
    "winner_top3_inclusion",
    "race_level_log_loss_within_valid_distribution",
)
CALIBRATION_METRICS = ("brier", "reliability_curve", "expected_calibration_error")
#: ECE binning policy frozen before results: equal-width [0, 1], 10 bins.
ECE_N_BINS = 10
ECE_BINNING = "equal_width"
ORDINAL_METRICS = ("mae", "rmse", "spearman")
ORDINAL_PRIMARY_METRIC = "mae"
POSITION_CHANGE_METRICS = ("mae", "rmse")
POSITION_CHANGE_BINARY_METRICS = ("log_loss", "brier", "pr_auc")

#: One registry of all named metrics -> applies_to task kinds.
METRIC_REGISTRY: dict = {
    "log_loss": ("binary",),
    "brier": ("binary", "calibration"),
    "roc_auc": ("binary",),
    "pr_auc": ("binary",),
    "winner_top1_accuracy": ("race_winner",),
    "winner_top3_inclusion": ("race_winner",),
    "race_level_log_loss_within_valid_distribution": ("race_winner",),
    "reliability_curve": ("calibration",),
    "expected_calibration_error": ("calibration",),
    "mae": ("ordinal", "regression"),
    "rmse": ("ordinal", "regression"),
    "spearman": ("ordinal",),
}


def validate_metric(name: str) -> None:
    if name not in METRIC_REGISTRY:
        raise ModelLabProtocolError(
            f"unknown metric {name!r}; known: {sorted(METRIC_REGISTRY)}")


def metrics_contract() -> dict:
    for name in (BINARY_PRIMARY_METRICS + BINARY_SECONDARY_METRICS
                 + RACE_LEVEL_WINNER_METRICS + CALIBRATION_METRICS
                 + ORDINAL_METRICS + POSITION_CHANGE_METRICS):
        validate_metric(name)
    return {
        "binary_primary": list(BINARY_PRIMARY_METRICS),
        "binary_secondary": list(BINARY_SECONDARY_METRICS),
        "race_level_winner": list(RACE_LEVEL_WINNER_METRICS),
        "calibration": list(CALIBRATION_METRICS),
        "ece": {"n_bins": ECE_N_BINS, "binning": ECE_BINNING},
        "ordinal": list(ORDINAL_METRICS),
        "ordinal_primary": ORDINAL_PRIMARY_METRIC,
        "position_change_regression": list(POSITION_CHANGE_METRICS),
        "position_change_binary": list(POSITION_CHANGE_BINARY_METRICS),
        "accuracy_headline_forbidden": True,
    }


# ---------------------------------------------------------------------------
# Non-ML prediction baselines (distinct from F16 feature sets)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class BaselineSpec:
    name: str
    description: str
    applies_to: tuple
    requires: tuple
    notes: str = ""


BASELINES: tuple = (
    BaselineSpec(
        "CURRENT_LEADER",
        "Predict the driver currently leading the race as the winner.",
        ("winner", "podium", "points"),
        ("position",),
        "Factual at state time; no future data."),
    BaselineSpec(
        "CURRENT_ORDER",
        "Assume the current running order is the final order.",
        ("winner", "podium", "points", "final_position"),
        ("position",),
        "Race-level rank baseline for winner/finish tasks."),
    BaselineSpec(
        "GRID_POLE",
        "Pre-race: predict the pole/grid leader as the winner and order by "
        "grid position.",
        ("winner", "podium", "points", "final_position"),
        ("grid_position",),
        "Null grid slots are structurally missing; never imputed "
        "globally."),
    BaselineSpec(
        "RECENT_PACE",
        "Rank by a simple factual recent-pace summary available at state "
        "time.",
        ("winner", "podium", "points"),
        ("representative_recent_pace_s",),
        "Must read only past/current state; a frozen recent-pace column may "
        "be used rather than a new formula."),
    BaselineSpec(
        "CLASS_PRIOR",
        "Constant training-prevalence probability per task.",
        ("winner", "podium", "points", "gain", "loss"),
        (),
        "Probability sanity floor for log loss / Brier; fit on fold "
        "training rows only."),
)

#: F16 sets that are FEATURE configurations, not prediction baselines.
FEATURE_SETS_NOT_BASELINES = (
    "CURRENT_ORDER_ONLY", "MINIMAL_RACE_STATE", "ALL_84")

BASELINE_NAMES: tuple = tuple(b.name for b in BASELINES)
BASELINES_BY_NAME: dict = {b.name: b for b in BASELINES}


def validate_baseline(name: str) -> BaselineSpec:
    if name not in BASELINES_BY_NAME:
        raise ModelLabProtocolError(
            f"unknown baseline {name!r}; known: {list(BASELINE_NAMES)}")
    return BASELINES_BY_NAME[name]


def baselines_contract() -> list:
    return [
        {"name": b.name, "description": b.description,
         "applies_to": list(b.applies_to), "requires": list(b.requires),
         "notes": b.notes}
        for b in BASELINES
    ]


# ---------------------------------------------------------------------------
# Preprocessing / missingness / categorical / imbalance / tuning / seeds
# ---------------------------------------------------------------------------

PREPROCESSING_POLICY = {
    "fit_scope": "training only",
    "transform_scope": "validation and holdout receive transform-only "
                       "behaviour",
    "includes": ["imputers", "scalers", "encoders", "feature selectors",
                 "dimensionality reduction", "learned transforms"],
    "global_fit_forbidden": True,
    "target_aware_forbidden": True,
    "matrix_mutation_forbidden": True,
}

MISSINGNESS_POLICY = {
    "structural_missingness_preserved": True,
    "global_fill_forbidden": True,
    "native_missing_models": "may consume supported nulls directly",
    "complete_input_models": "receive train-fitted imputation inside a "
                             "leakage-safe pipeline",
    "indicators": "allowed only as an explicit, justified pipeline component",
    "target_aware_forbidden": True,
    "global_statistics_forbidden": True,
}

#: Three string categoricals frozen in the 84-feature surface.
CATEGORICAL_COLUMNS: tuple = ("compound", "stint_compound", "track_state")
CATEGORICAL_POLICY = {
    "columns": list(CATEGORICAL_COLUMNS),
    "default_treatment": "one-hot or native categorical support fitted on "
                         "training data only",
    "native_categorical_models": ["catboost"],
    "unknown_category": "explicit, frozen per pipeline (ignore/other); never "
                        "silently mapped to a target-correlated category",
    "target_encoding": "forbidden unless train-only and evaluated as an "
                       "explicit experiment dimension",
}

CLASS_IMBALANCE_POLICY = {
    "synthetic_resampling_initially": False,
    "class_weights": "allowed only as an explicit experiment dimension",
    "sample_weights": "allowed only as an explicit experiment dimension",
    "silent_balancing_forbidden": True,
    "calibration_note": "weighting that changes effective training prevalence "
                        "must be followed by calibration evaluation",
}

TUNING_POLICY = {
    "starting_point": "sensible defaults, then small documented search spaces",
    "search_scope": "inside development-training folds only",
    "holdout_tuning_forbidden": True,
    "budget_recorded": True,
    "automl_default": False,
    "note": "no Optuna/AutoML unless the plan explicitly requires it and the "
            "budget is recorded",
}

REQUIRED_SEED = 42
SEED_SET: tuple = (REQUIRED_SEED,)
SEED_POLICY = {
    "project_seed": REQUIRED_SEED,
    "seed_set": list(SEED_SET),
    "record_every_seed": True,
    "seed_averaging_by_default": False,
    "monte_carlo_seeds": "separate later subsystem; not governed here",
}


def validate_seed(seed) -> int:
    if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
        raise ModelLabProtocolError(f"invalid seed {seed!r}: expected a "
                                    "non-negative int")
    return seed


# ---------------------------------------------------------------------------
# Evaluation aggregation, stage buckets, uncertainty
# ---------------------------------------------------------------------------

#: Training weights: every driver-state is one training unit (no resampling).
TRAINING_WEIGHTING = "state_equal"
#: Headline evaluation aggregation: races contribute equally (race macro),
#: so an unusually long race cannot dominate. State-level metrics are
#: reported as diagnostics.
EVALUATION_AGGREGATION = "race_macro_headline_state_diagnostic"
FOLD_AGGREGATION = "simple_mean_across_folds_with_dispersion"

STAGE_BUCKETS: tuple = (
    ("EARLY", 0.0, 1.0 / 3.0),
    ("MID", 1.0 / 3.0, 2.0 / 3.0),
    ("LATE", 2.0 / 3.0, 1.0),
)
#: Reuses the Phase-2 descriptive progress thirds (64,016 / 63,437 /
#: 61,967 states), half-open [lo, hi) with the final bucket inclusive.
STAGE_RULE = "race_progress_frac_phase2_thirds"

UNCERTAINTY_POLICY = {
    "method": "race_level_bootstrap_and_fold_dispersion",
    "resample_unit": "race",
    "row_level_resampling_forbidden": True,
    "note": "N=189,420 rows are not independent samples; report fold "
            "dispersion and race-level bootstrap intervals only when "
            "implemented",
}

#: Optional secondary evaluation, NOT the main selection protocol. Not
#: adopted in M0; it would better approximate live deployment by training
#: through race R and evaluating race R+1 within a season.
WITHIN_SEASON_EVALUATION = {
    "adopted": False,
    "classification": "SECONDARY EVALUATION (optional)",
    "description": "train through race R, evaluate race R+1 within a season",
    "role": "never replaces the expanding-window chronological folds used "
            "for model selection",
    "justification_required": True,
    "runs_in_m0": False,
}


def stage_of(progress: float) -> str:
    """Frozen stage bucket for one race_progress_frac value (M0 policy)."""
    if progress is None or progress != progress:
        raise ModelLabProtocolError("race_progress_frac is null")
    for name, lo, hi in STAGE_BUCKETS:
        if name == "LATE":
            if lo <= progress <= hi:
                return name
        elif lo <= progress < hi:
            return name
    raise ModelLabProtocolError(f"race_progress_frac out of range: {progress}")


# ---------------------------------------------------------------------------
# F16 feature-set / ablation contract
# ---------------------------------------------------------------------------

def feature_set_vocabulary() -> tuple:
    """Frozen F16 configuration names Phase 3 may request."""
    return tuple(all_feature_set_names())


def validate_feature_set_name(name: str, manifest: dict | None = None) -> tuple:
    try:
        return resolve_feature_set(name, manifest)
    except Exception as exc:  # feature_sets raises AblationConfigError
        raise ModelLabProtocolError(
            f"unknown/incompatible feature set {name!r}: {exc}") from exc


ABLATION_POLICY = {
    "run_before_baselines": False,
    "same_folds": True,
    "same_metrics": True,
    "same_preprocessing_family": True,
    "same_tuning_budget": True,
    "cumulative_and_logo": True,
    "dependency_aware_interactions": True,
    "intuition_based_feature_removal_forbidden": True,
}


# ---------------------------------------------------------------------------
# Candidate model tiers (documented, never trained in M0)
# ---------------------------------------------------------------------------

class CandidateTier(str, Enum):
    PRODUCTION_CANDIDATE = "PRODUCTION_CANDIDATE"
    EXPERIMENTAL = "EXPERIMENTAL"
    DEFERRED = "DEFERRED"


@dataclass(frozen=True)
class CandidateSpec:
    family: str
    tier: CandidateTier
    supported_tasks: tuple
    preprocessing: str
    missing: str
    categorical: str
    probability_output: str
    calibration: str
    compute_class: str
    dependency: str


CANDIDATES: tuple = (
    CandidateSpec(
        "logistic_regression", CandidateTier.PRODUCTION_CANDIDATE,
        ("binary",), "impute + scale in pipeline", "requires complete inputs",
        "one-hot (train-fitted)", "calibrated binary probability",
        "natively probabilistic; still evaluate reliability",
        "low", "sklearn"),
    CandidateSpec(
        "hist_gradient_boosting", CandidateTier.PRODUCTION_CANDIDATE,
        ("binary",), "native nulls; no scaling", "native missing support",
        "ordinal/one-hot encoding (train-fitted)", "binary probability",
        "evaluate reliability; calibrate if needed", "medium", "sklearn"),
    CandidateSpec(
        "xgboost", CandidateTier.PRODUCTION_CANDIDATE,
        ("binary", "ranking"), "native nulls; no scaling",
        "native missing support", "one-hot or native categorical",
        "binary probability (calibrate)", "evaluate reliability",
        "medium", "xgboost"),
    CandidateSpec(
        "lightgbm", CandidateTier.PRODUCTION_CANDIDATE,
        ("binary", "ranking"), "native nulls; no scaling",
        "native missing support", "native categorical support",
        "binary probability (calibrate)", "evaluate reliability",
        "medium", "lightgbm"),
    CandidateSpec(
        "catboost", CandidateTier.PRODUCTION_CANDIDATE,
        ("binary", "ranking"), "native nulls; no scaling",
        "native missing support", "native categorical support",
        "binary probability", "evaluate reliability", "medium-high",
        "catboost"),
    CandidateSpec(
        "extra_trees", CandidateTier.PRODUCTION_CANDIDATE,
        ("binary",), "impute in pipeline; no scaling",
        "requires complete inputs (train-fitted imputation)",
        "one-hot (train-fitted)", "binary probability", "evaluate reliability",
        "medium", "sklearn"),
    CandidateSpec(
        "random_forest", CandidateTier.PRODUCTION_CANDIDATE,
        ("binary",), "impute in pipeline; no scaling",
        "requires complete inputs (train-fitted imputation)",
        "one-hot (train-fitted)", "binary probability", "evaluate reliability",
        "medium", "sklearn"),
    CandidateSpec(
        "learning_to_rank", CandidateTier.EXPERIMENTAL,
        ("winner", "final_position"), "per-library; groups by race state",
        "native/library dependent", "library dependent",
        "ranking score (NOT a probability)", "n/a unless calibrated separately",
        "medium", "xgboost / lightgbm"),
    CandidateSpec(
        "ordinal_model", CandidateTier.EXPERIMENTAL,
        ("final_position",), "impute + scale in pipeline",
        "requires complete inputs", "one-hot (train-fitted)",
        "ordinal distribution / expected rank", "evaluate rank quality",
        "medium", "mord / statsmodels (not installed)"),
    CandidateSpec(
        "mlp", CandidateTier.EXPERIMENTAL,
        ("binary",), "impute + scale in pipeline", "requires complete inputs",
        "one-hot (train-fitted)", "binary probability", "evaluate reliability",
        "medium", "torch (not installed)"),
    CandidateSpec(
        "sequence_gru_lstm", CandidateTier.DEFERRED,
        ("binary",), "strictly past-only lap windows",
        "padding/masking must not expose future laps",
        "as tabular", "binary probability", "evaluate reliability",
        "high", "torch (not installed)"),
    CandidateSpec(
        "temporal_transformer", CandidateTier.DEFERRED,
        ("binary",), "strictly past-only lap windows",
        "padding/masking must not expose future laps", "as tabular",
        "binary probability", "evaluate reliability", "very high",
        "torch (not installed)"),
    CandidateSpec(
        "tabpfn", CandidateTier.DEFERRED,
        ("binary",), "library dependent", "library dependent",
        "library dependent", "binary probability", "evaluate reliability",
        "high", "tabpfn (not installed)"),
    CandidateSpec(
        "dnf_survival", CandidateTier.DEFERRED,
        ("dnf",), "n/a until a DNF target exists", "n/a", "n/a",
        "survival/hazard (not a race probability)", "n/a", "medium",
        "lifelines/rsf (not installed)"),
)

CANDIDATES_BY_FAMILY: dict = {c.family: c for c in CANDIDATES}


def validate_candidate(family: str) -> CandidateSpec:
    if family not in CANDIDATES_BY_FAMILY:
        raise ModelLabProtocolError(
            f"unknown candidate family {family!r}; known: "
            f"{list(CANDIDATES_BY_FAMILY)}")
    return CANDIDATES_BY_FAMILY[family]


def candidates_contract() -> list:
    return [
        {"family": c.family, "tier": c.tier.value,
         "supported_tasks": list(c.supported_tasks),
         "preprocessing": c.preprocessing, "missing": c.missing,
         "categorical": c.categorical,
         "probability_output": c.probability_output,
         "calibration": c.calibration, "compute_class": c.compute_class,
         "dependency": c.dependency}
        for c in CANDIDATES
    ]


# ---------------------------------------------------------------------------
# Model-selection rule / probability semantics / partial races
# ---------------------------------------------------------------------------

MODEL_SELECTION_RULE = {
    "primary_task": PRIMARY_TASK,
    "order_of_evidence": [
        "probabilistic quality (log loss, Brier)",
        "calibration",
        "temporal consistency across folds",
        "stage-of-race behaviour",
        "inference latency",
        "complexity / operational cost",
    ],
    "weighted_score_forbidden": True,
    "single_metric_selection_forbidden": True,
    "decision_table_required": True,
    "task_specific_models": True,
    "one_model_must_win_every_task": False,
}

PROBABILITY_SEMANTICS = {
    "independent_binary": "per-driver P(win) from independent binary "
                          "classification; does NOT sum to 1 across a race",
    "mutually_exclusive_race": "a coherent race winner distribution that "
                               "sums to 1; requires a model/probability "
                               "contract, not post-hoc normalization",
    "post_hoc_normalization": "forbidden unless explicitly justified and "
                              "evaluated",
    "requirement": "each model/task experiment must state which of the two "
                   "it outputs before results are interpreted",
}

MULTI_DRIVER_RESEARCH_QUESTIONS = (
    "independent binary classification",
    "grouped ranking",
    "softmax/multinomial race-state formulation",
    "learning-to-rank",
)

PARTIAL_RACE_POLICY = {
    "race_ids": list(PARTIAL_RACE_IDS),
    "default": "retain valid observed states and official outcomes",
    "casual_drop_forbidden": True,
    "race_level_flag": "record the PARTIAL status in evaluation grouping",
    "task_exclusion": "only if a task is semantically invalid for the race, "
                      "justified at task/protocol level",
}


# ---------------------------------------------------------------------------
# Experiment identity / result schema / storage / artifacts
# ---------------------------------------------------------------------------

#: Fields that define the semantic identity of an experiment. The
#: experiment_id is a deterministic hash over these (timestamps excluded).
EXPERIMENT_ID_FIELDS: tuple = (
    "protocol_version", "phase2_freeze_commit", "feature_set_version",
    "label_set_version", "matrix_version", "ablation_config_version",
    "matrix_content_hash", "feature_set", "task", "fold", "model_family",
    "model_parameters", "preprocessing_config", "calibration_config", "seed",
)

#: Required configuration metadata when running any experiment.
EXPERIMENT_CONFIG_REQUIRED: tuple = (
    "experiment_id", "protocol_version", "git_commit", "phase2_freeze_commit",
    "feature_set_version", "label_set_version", "matrix_version",
    "ablation_config_version", "matrix_content_hash", "feature_set", "task",
    "fold", "model_family", "model_parameters", "preprocessing_config",
    "calibration_config", "seed", "training_rows", "training_races",
    "validation_rows", "validation_races", "split_policy",
    "holdout_accessed",
)

#: Result fields recorded after a run (never populated by M0).
RESULT_REQUIRED: tuple = (
    "experiment_id", "status", "fit_seconds", "inference_latency",
    "metrics", "calibration_metrics", "stage_metrics", "artifact_refs",
    "warnings",
)

#: Holdout metadata that must accompany every experiment record.
HOLDOUT_ACCESS_FIELDS: tuple = ("holdout_accessed", "holdout_purpose",
                                "holdout_protocol_version")

#: Storage: tracked config/code + gitignored artifacts + summary reports.
STORAGE_POLICY = {
    "tracked": ["configuration", "code", "protocol", "summary reports"],
    "gitignored": ["JSON/Parquet result artifacts", "fitted model artifacts"],
    "mlflow": "not introduced; reconsider only if measured pain justifies it",
}

#: Deterministic, structured artifact identifier (no "best_model_final").
ARTIFACT_ID_TEMPLATE = "mlab-{task}-{model_family}-{feature_set}-{fold}-{seed}"
RUN_DIR_TEMPLATE = "experiments/{protocol_version}/{experiment_id}"

#: Metadata every future fitted model artifact must carry.
MODEL_ARTIFACT_CONTRACT: tuple = (
    "model_family", "task", "feature_set", "feature_names_ordered",
    "training_chronology", "preprocessing", "calibration", "seed",
    "dependency_versions", "matrix_version", "matrix_content_hash",
    "protocol_version", "git_commit", "creation_command",
    "metrics_reference",
)

LATENCY_BENCHMARK_CONTRACT = {
    "warmup": "warm up before timing",
    "repeats": "repeated timed calls",
    "batch_sizes": ["single_driver_state", "full_field_race_state",
                    "batch_historical_inference"],
    "report": ["p50", "p95", "p99_where_supported"],
    "environment": "record hardware/environment metadata",
    "fabrication_forbidden": True,
}

TRAINING_COST_CONTRACT = {
    "record": ["fit_wall_time", "peak_memory_where_practical",
               "artifact_size", "hardware"],
    "fabrication_forbidden": True,
}

LEGACY_REFERENCE_POLICY = {
    "status": "LEGACY REFERENCE",
    "direct_benchmark": False,
    "reason": "legacy race-grouped CV is not comparable to Phase-3 temporal "
              "evaluation",
    "mixing_metrics_forbidden": True,
}


def validate_experiment_config(config: dict) -> None:
    missing = [f for f in EXPERIMENT_CONFIG_REQUIRED if f not in config]
    if missing:
        raise ModelLabProtocolError(
            f"experiment config missing required fields: {missing}")
    validate_task(config["task"])
    validate_seed(config["seed"])
    validate_split_policy(config["split_policy"])
    if config["fold"] not in [f.fold_id for f in DEVELOPMENT_FOLDS] \
            and config["fold"] != "FINAL_FIT":
        raise ModelLabProtocolError(
            f"unknown fold {config['fold']!r}")
    if config["task"] == "dnf":
        raise ModelLabProtocolError("DNF has no frozen target")
    if not isinstance(config["holdout_accessed"], bool):
        raise ModelLabProtocolError("holdout_accessed must be a boolean")


def holdout_access_metadata(accessed: bool, purpose: str) -> dict:
    if not isinstance(accessed, bool):
        raise ModelLabProtocolError("holdout accessed must be a boolean")
    if accessed and not purpose:
        raise ModelLabProtocolError("accessed holdout requires a purpose")
    return {
        "holdout_accessed": accessed,
        "holdout_purpose": purpose,
        "holdout_protocol_version": MODEL_LAB_PROTOCOL_VERSION,
    }


def experiment_id(config: dict) -> str:
    payload = {k: config.get(k) for k in EXPERIMENT_ID_FIELDS}
    if payload.get("protocol_version") is None:
        payload["protocol_version"] = MODEL_LAB_PROTOCOL_VERSION
    return _sha256_json(payload)


# ---------------------------------------------------------------------------
# Phase-2 freeze verification
# ---------------------------------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_manifest_contract(manifest: dict) -> None:
    """Pure validation of the F15 manifest against the frozen facts."""
    checks = {
        "feature_set_version": REQUIRED_FEATURE_SET_VERSION,
        "label_set_version": REQUIRED_LABEL_SET_VERSION,
        "matrix_version": REQUIRED_MATRIX_VERSION,
    }
    for field, expected in checks.items():
        if manifest.get(field) != expected:
            raise ModelLabProtocolError(
                f"Phase-2 drift: {field}={manifest.get(field)!r} != "
                f"{expected!r}")
    if int(manifest.get("predictive_feature_count", -1)) \
            != EXPECTED_PREDICTIVE_COUNT:
        raise ModelLabProtocolError("predictive feature count drift")
    if len(manifest.get("predictive_columns", [])) != EXPECTED_PREDICTIVE_COUNT:
        raise ModelLabProtocolError("predictive column count drift")
    if len(manifest.get("label_columns", [])) != EXPECTED_LABEL_COUNT:
        raise ModelLabProtocolError("label column count drift")
    if int(manifest.get("row_count", -1)) != EXPECTED_MATRIX_ROWS:
        raise ModelLabProtocolError("matrix row count drift")
    if int(manifest.get("column_count", -1)) != EXPECTED_MATRIX_COLUMNS:
        raise ModelLabProtocolError("matrix column count drift")
    if int(manifest.get("race_count", -1)) != EXPECTED_RACE_COUNT:
        raise ModelLabProtocolError("race count drift")
    if tuple(manifest.get("season_range", ())) != EXPECTED_SEASON_RANGE:
        raise ModelLabProtocolError("season range drift")
    if manifest.get("content_hash") != EXPECTED_MATRIX_CONTENT_HASH:
        raise ModelLabProtocolError("matrix content hash drift")
    if manifest.get("schema_hash") != EXPECTED_MATRIX_SCHEMA_HASH:
        raise ModelLabProtocolError("matrix schema hash drift")
    if manifest.get("feature_registry_fingerprint") \
            != EXPECTED_FEATURE_REGISTRY_FINGERPRINT:
        raise ModelLabProtocolError("feature registry fingerprint drift")
    if manifest.get("label_registry_fingerprint") \
            != EXPECTED_LABEL_REGISTRY_FINGERPRINT:
        raise ModelLabProtocolError("label registry fingerprint drift")
    if list(manifest.get("task_eligibility_columns", [])) \
            != list(TASK_ELIGIBILITY_COLUMNS):
        raise ModelLabProtocolError("task eligibility columns drift")
    for task, (label_col, mask_col) in TASKS.items():
        if manifest.get("task_contract", {}).get(task) != [label_col, mask_col]:
            raise ModelLabProtocolError(f"task contract drift for {task!r}")


def validate_ablation_contract(ablation: dict) -> None:
    if ablation.get("ablation_config_version") \
            != REQUIRED_ABLATION_CONFIG_VERSION:
        raise ModelLabProtocolError("ablation config version drift")
    if ablation.get("config_hash", ablation.get("semantic_hash")) \
            != EXPECTED_ABLATION_SEMANTIC_HASH:
        raise ModelLabProtocolError("ablation config semantic hash drift")


def verify_phase2_artifacts(paths: V2Paths | None = None, *,
                            verify_content_hash: bool = True,
                            verify_bytes: bool = True) -> dict:
    """Verify the frozen Phase-2 boundary. Read-only; never repairs."""
    from v2.features.build_matrix import output_dir

    paths = paths or V2Paths.resolve()
    out = output_dir(paths)
    manifest = load_manifest(paths, out)
    validate_manifest_contract(manifest)

    report = {
        "feature_set_version": manifest["feature_set_version"],
        "label_set_version": manifest["label_set_version"],
        "matrix_version": manifest["matrix_version"],
        "ablation_config_version": ABLATION_CONFIG_VERSION,
        "rows": manifest["row_count"],
        "columns": manifest["column_count"],
        "races": manifest["race_count"],
        "content_hash": manifest["content_hash"],
        "manifest_sha256": None,
        "parquet_sha256": None,
        "ablation_config_sha256": None,
        "content_hash_recomputed": None,
    }

    if verify_bytes:
        parquet = out / "model_matrix.parquet"
        manifest_path = out / "manifest.json"
        ablation_path = out / "ablation_config.json"
        for name, path, expected in (
                ("parquet_sha256", parquet, EXPECTED_MATRIX_PARQUET_SHA256),
                ("manifest_sha256", manifest_path, EXPECTED_MANIFEST_SHA256),
                ("ablation_config_sha256", ablation_path,
                 EXPECTED_ABLATION_CONFIG_SHA256)):
            if not path.exists():
                raise ModelLabProtocolError(f"missing Phase-2 artifact {path}")
            actual = _sha256_file(path)
            if actual != expected:
                raise ModelLabProtocolError(
                    f"Phase-2 artifact drift: {path.name} sha256 {actual} != "
                    f"{expected}")
            report[name] = actual

    ablation = json.loads((out / "ablation_config.json").read_text())
    validate_ablation_contract(ablation)

    if verify_content_hash:
        matrix, _ = load_matrix(paths, out)
        recomputed = content_hash(matrix)
        if recomputed != EXPECTED_MATRIX_CONTENT_HASH:
            raise ModelLabProtocolError(
                f"matrix content hash drift: {recomputed} != "
                f"{EXPECTED_MATRIX_CONTENT_HASH}")
        report["content_hash_recomputed"] = recomputed
    return report


# ---------------------------------------------------------------------------
# Protocol payload + deterministic semantic hash + export
# ---------------------------------------------------------------------------

def _sha256_json(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def protocol_payload() -> dict:
    """Meaningful protocol fields only (no timestamps/paths/machine info)."""
    return {
        "protocol_version": MODEL_LAB_PROTOCOL_VERSION,
        "phase2_freeze": {
            "phase1_tag": PHASE1_FREEZE_TAG,
            "phase1_commit": PHASE1_FREEZE_COMMIT,
            "phase2_tag": PHASE2_FREEZE_TAG,
            "phase2_commit": PHASE2_FREEZE_COMMIT,
        },
        "required_phase2_versions": {
            "feature_set_version": REQUIRED_FEATURE_SET_VERSION,
            "label_set_version": REQUIRED_LABEL_SET_VERSION,
            "matrix_version": REQUIRED_MATRIX_VERSION,
            "ablation_config_version": REQUIRED_ABLATION_CONFIG_VERSION,
        },
        "expected_phase2_hashes": {
            "matrix_content_hash": EXPECTED_MATRIX_CONTENT_HASH,
            "matrix_schema_hash": EXPECTED_MATRIX_SCHEMA_HASH,
            "feature_registry_fingerprint":
                EXPECTED_FEATURE_REGISTRY_FINGERPRINT,
            "label_registry_fingerprint": EXPECTED_LABEL_REGISTRY_FINGERPRINT,
            "ablation_semantic_hash": EXPECTED_ABLATION_SEMANTIC_HASH,
            "matrix_parquet_sha256": EXPECTED_MATRIX_PARQUET_SHA256,
            "manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "ablation_config_sha256": EXPECTED_ABLATION_CONFIG_SHA256,
        },
        "expected_counts": {
            "rows": EXPECTED_MATRIX_ROWS,
            "columns": EXPECTED_MATRIX_COLUMNS,
            "races": EXPECTED_RACE_COUNT,
            "predictive_features": EXPECTED_PREDICTIVE_COUNT,
            "ordinal_eligible": EXPECTED_ORDINAL_ELIGIBLE,
            "gain_loss_eligible": EXPECTED_GAIN_LOSS_ELIGIBLE,
            "binary_eligible": EXPECTED_BINARY_ELIGIBLE,
        },
        "chronology": {
            "key": list(CHRONOLOGY_KEY),
            "season_range": list(FULL_SEASON_RANGE),
        },
        "development_seasons": list(DEVELOPMENT_SEASONS),
        "development_folds": [
            {"fold_id": f.fold_id, "train_seasons": list(f.train_seasons),
             "validation_season": f.validation_season,
             "rationale": f.rationale}
            for f in DEVELOPMENT_FOLDS
        ],
        "fold_start_rationale": FOLD_START_RATIONALE,
        "final_fit_seasons": list(FINAL_FIT_SEASONS),
        "protected_holdout_season": PROTECTED_HOLDOUT_SEASON,
        "holdout_access_policy": {
            "development_runners_exclude_holdout": True,
            "separate_holdout_evaluator": True,
            "holdout_access_recorded": True,
            "single_locked_access": True,
            "repeated_holdout_tuning_forbidden": True,
            "explicit_opt_in_required": True,
        },
        "split_policy": {
            "allowed": list(ALLOWED_SPLIT_POLICIES),
            "forbidden": list(FORBIDDEN_SPLIT_POLICIES),
            "row_level_random_splits_forbidden": True,
            "observation_grain": "driver-state / driver-lap",
            "rows_independent": False,
        },
        "tasks": task_eligibility_contract(),
        "task_order": list(TASK_ORDER),
        "primary_task": PRIMARY_TASK,
        "primary_task_rationale": TASK_SPECS[PRIMARY_TASK].rationale,
        "metrics": metrics_contract(),
        "baselines": baselines_contract(),
        "feature_sets_not_baselines": list(FEATURE_SETS_NOT_BASELINES),
        "feature_set_vocabulary": list(feature_set_vocabulary()),
        "preprocessing_policy": PREPROCESSING_POLICY,
        "missingness_policy": MISSINGNESS_POLICY,
        "categorical_policy": CATEGORICAL_POLICY,
        "class_imbalance_policy": CLASS_IMBALANCE_POLICY,
        "tuning_policy": TUNING_POLICY,
        "seed_policy": SEED_POLICY,
        "training_weighting": TRAINING_WEIGHTING,
        "evaluation_aggregation": EVALUATION_AGGREGATION,
        "fold_aggregation": FOLD_AGGREGATION,
        "stage_buckets": [list(s) for s in STAGE_BUCKETS],
        "stage_rule": STAGE_RULE,
        "uncertainty_policy": UNCERTAINTY_POLICY,
        "within_season_evaluation": WITHIN_SEASON_EVALUATION,
        "ablation_policy": ABLATION_POLICY,
        "candidates": candidates_contract(),
        "model_selection_rule": MODEL_SELECTION_RULE,
        "probability_semantics": PROBABILITY_SEMANTICS,
        "multi_driver_research_questions": list(MULTI_DRIVER_RESEARCH_QUESTIONS),
        "partial_race_policy": PARTIAL_RACE_POLICY,
        "legacy_reference_policy": LEGACY_REFERENCE_POLICY,
        "experiment_id_fields": list(EXPERIMENT_ID_FIELDS),
        "storage_policy": STORAGE_POLICY,
        "artifact_id_template": ARTIFACT_ID_TEMPLATE,
        "run_dir_template": RUN_DIR_TEMPLATE,
        "model_artifact_contract": list(MODEL_ARTIFACT_CONTRACT),
        "latency_benchmark_contract": LATENCY_BENCHMARK_CONTRACT,
        "training_cost_contract": TRAINING_COST_CONTRACT,
        "result_schema": {
            "config_required": list(EXPERIMENT_CONFIG_REQUIRED),
            "result_required": list(RESULT_REQUIRED),
            "holdout_access_fields": list(HOLDOUT_ACCESS_FIELDS),
        },
    }


def protocol_semantic_hash(payload: dict | None = None) -> str:
    return _sha256_json(payload if payload is not None else protocol_payload())


def protocol_document() -> dict:
    payload = protocol_payload()
    payload["protocol_semantic_hash"] = protocol_semantic_hash(payload)
    return payload


def render_protocol() -> str:
    return json.dumps(protocol_document(), indent=2, sort_keys=True) + "\n"


def write_protocol(path: str | Path | None = None) -> Path:
    """Write the deterministic protocol artifact (semantic body only)."""
    dest = Path(path) if path else Path(PROTOCOL_REL_PATH)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_protocol())
    return dest


def validate_protocol_document(doc: dict) -> None:
    """Reject protocol drift: the recorded hash must match the payload."""
    recorded = doc.get("protocol_semantic_hash")
    payload = {k: v for k, v in doc.items()
               if k != "protocol_semantic_hash"}
    actual = protocol_semantic_hash(payload)
    if recorded != actual:
        raise ModelLabProtocolError(
            f"protocol hash drift: recorded {recorded!r} != actual {actual!r}")
    if doc.get("protocol_version") != MODEL_LAB_PROTOCOL_VERSION:
        raise ModelLabProtocolError("protocol version drift")


# ---------------------------------------------------------------------------
# Aggregate validation entry point (no data access, no model)
# ---------------------------------------------------------------------------

def validate_protocol() -> dict:
    validate_chronology_key()
    validate_folds()
    validate_holdout_policy()
    validate_split_policy(ALLOWED_SPLIT_POLICIES[0])
    validate_task_contract()
    metrics_contract()
    for name in BASELINE_NAMES:
        validate_baseline(name)
    for c in CANDIDATES:
        validate_candidate(c.family)
    feature_set_vocabulary()
    doc = protocol_document()
    validate_protocol_document(doc)
    return {
        "protocol_version": MODEL_LAB_PROTOCOL_VERSION,
        "protocol_semantic_hash": doc["protocol_semantic_hash"],
        "folds": [f.fold_id for f in DEVELOPMENT_FOLDS],
        "primary_task": PRIMARY_TASK,
    }
