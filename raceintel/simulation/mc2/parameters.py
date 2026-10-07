"""MC2 parameter artifact schema (V3.2D Part AD-AE).

Versioned MC2 parameter artifacts live SEPARATE from R3. Each carries:
schema_version, parameter_family, training seasons, conditioning
hierarchy, minimum-N rules, fallback rules, estimator configuration, and
a content hash. No timestamps, absolute paths, or usernames in identity.

Temporal rule (Part AE): a fold evaluating period Y uses only history
before Y. Retrospective through-2024 artifacts are for post-acceptance
demo only, never inside earlier backtests.
"""

from __future__ import annotations

import hashlib
import json

__all__ = [
    "MC2_PARAMS_SCHEMA",
    "MC2_PARAM_FAMILIES",
    "make_artifact",
    "artifact_identity",
    "check_temporal",
]

#: Schema version for every MC2 research parameter artifact.
MC2_PARAMS_SCHEMA = "mc2-params-v1"

#: Parameter families owned by MC2 (R3 families are never redefined here).
MC2_PARAM_FAMILIES = (
    "driver_anchor",
    "pace_dynamics",
    "residual_variance",
    "residual_ar1",
    "traffic_penalty",
)


def make_artifact(*, parameter_family: str, train_through_season: int,
                  conditioning: list, min_n: dict, fallback: dict,
                  estimator_config: dict, values: dict) -> dict:
    """Build one versioned, hashable MC2 parameter artifact."""
    if parameter_family not in MC2_PARAM_FAMILIES:
        raise ValueError(f"unknown MC2 family {parameter_family!r}")
    artifact = {
        "schema_version": MC2_PARAMS_SCHEMA,
        "parameter_family": parameter_family,
        "training_seasons": {"min": 2018, "through": int(train_through_season)},
        "conditioning_hierarchy": list(conditioning),
        "minimum_n": dict(min_n),
        "fallback_rules": dict(fallback),
        "estimator_config": dict(estimator_config),
        "values": dict(values),
    }
    artifact["content_hash"] = artifact_identity(artifact)
    return artifact


def artifact_identity(artifact: dict) -> str:
    """SHA-256 over scientific content only (hash field itself excluded)."""
    payload = {k: v for k, v in artifact.items() if k != "content_hash"}
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_temporal(artifact: dict, evaluation_season: int) -> None:
    """Raise unless the artifact was trained strictly before Y."""
    through = artifact["training_seasons"]["through"]
    if not through < int(evaluation_season):
        raise ValueError(
            f"temporal violation: artifact through={through} must be "
            f"< evaluation season {evaluation_season}")
