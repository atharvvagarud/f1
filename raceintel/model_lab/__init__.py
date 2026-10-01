"""Phase-3 Model Lab (M0-M9 FROZEN) + P3.1 production serving boundary.

M0: frozen experimental protocol (`protocol`, `audit`).
M1: reusable experiment infrastructure (`data`, `tasks`, `splits`,
`predictions`, `metrics`, `calibration`, `stages`, `aggregation`,
`baselines`, `experiment`, `results`, `timing`).
M2-M8: development evidence (baselines, references, candidates, tuning,
boundary freeze, calibration selection) on folds D1/D2/D3.
M9: final development fit on ALL eligible 2018-2024 rows + the single
sanctioned 2025 holdout evaluation (consumed; mechanically sealed).

P3.1: narrow production serving boundary (`serving`): the frozen winner
model (ALL_84 -> train-fitted preprocessing -> LogReg C=0.01,
RAW, INDEPENDENT_BINARY) as a validated artifact + batch predictor. No
tuning, calibration, development folds, holdout evaluation, experiment
runners or model comparison live behind the serving interface.
"""

from raceintel.model_lab.aggregation import (  # noqa: F401
    aggregate_folds,
    race_macro,
    scoped_metric,
    state_pooled,
)
from raceintel.model_lab.baselines import (  # noqa: F401
    BASELINE_NAMES,
    get_baseline,
    run_baseline,
)
from raceintel.model_lab.data import (  # noqa: F401
    CanonicalMatrix,
    FeatureSchema,
    feature_frame,
    load_canonical,
    resolve_features,
)
from raceintel.model_lab.errors import (  # noqa: F401
    InvalidPredictionError,
    ModelLabError,
    PredictionAlignmentError,
    ProtectedHoldoutError,
    ProtocolDriftError,
    UnknownTaskError,
    UnsupportedMetricError,
)
from raceintel.model_lab.experiment import (  # noqa: F401
    PROJECT_SEED,
    ExperimentConfig,
    ExperimentResult,
    ExperimentStatus,
    build_config,
    set_project_seed,
)
from raceintel.model_lab.metrics import compute_metric  # noqa: F401
from raceintel.model_lab.predictions import (  # noqa: F401
    PredictionKind,
    PredictionResult,
    ProbabilitySemantics,
    align,
)
from raceintel.model_lab.protocol import (  # noqa: F401
    DEVELOPMENT_FOLDS,
    MODEL_LAB_PROTOCOL_VERSION,
    PRIMARY_TASK,
    PROTECTED_HOLDOUT_SEASON,
    TASK_SPECS,
    protocol_semantic_hash,
    validate_protocol,
)
from raceintel.model_lab.serving import (  # noqa: F401
    FrozenWinnerPredictor,
    default_serving_artifact_path,
    load_frozen_winner_model,
)
from raceintel.model_lab.results import (  # noqa: F401
    environment_metadata,
    read_experiment,
    write_experiment,
)
from raceintel.model_lab.splits import (  # noqa: F401
    ExperimentDataset,
    get_split,
    materialize,
    validate_task_masks,
)
from raceintel.model_lab.tasks import ResolvedTask, resolve_task  # noqa: F401
from raceintel.model_lab.winner import synchronized_winner_top_k  # noqa: F401

__all__ = [name for name in globals() if not name.startswith("_")]
