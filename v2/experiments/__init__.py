"""Phase-2/Phase-3 experiment configuration (F16).

Configuration metadata only: feature-family ablation groups, named
feature sets and Model-Lab handoff fixtures. This package is the clean
Phase-3 dependency point and contains no feature calculator, estimator,
split, preprocessing or matrix builder.
"""

from v2.experiments.feature_sets import (  # noqa: F401
    ABLATION_CONFIG_VERSION,
    FIXTURES,
    PRIMARY_GROUP_ORDER,
    AblationConfigError,
    FixtureDef,
    FeatureGroup,
    FeatureSet,
    ablation_config_dict,
    build_primary_groups,
    get_feature_set,
    load_canonical_matrix,
    load_task,
    resolve_feature_set,
    resolve_fixture,
    semantic_hash,
    validate_fixtures,
    validate_manifest_compatibility,
    validate_registry,
    write_ablation_config,
)

__all__ = [
    "ABLATION_CONFIG_VERSION",
    "FIXTURES",
    "PRIMARY_GROUP_ORDER",
    "AblationConfigError",
    "FeatureGroup",
    "FeatureSet",
    "FixtureDef",
    "ablation_config_dict",
    "build_primary_groups",
    "get_feature_set",
    "load_canonical_matrix",
    "load_task",
    "resolve_feature_set",
    "resolve_fixture",
    "semantic_hash",
    "validate_fixtures",
    "validate_manifest_compatibility",
    "validate_registry",
    "write_ablation_config",
]
