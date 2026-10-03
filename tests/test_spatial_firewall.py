"""P12-1 spatial firewall tests (predictive + ALL_84 + served seasons).

Both directions enforced by source scan (repo-idiomatic governance):
no frozen predictive module may depend on raceintel.spatial, and
raceintel.spatial may not depend on predictive modules, the API layer,
or web frameworks. Product-season truth is asserted against the frozen
api/v2_service authority (test-only import, mirroring existing tests).
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPATIAL = ROOT / "raceintel" / "spatial"

PREDICTIVE_MODULES = (
    "raceintel.features",
    "raceintel.labels",
    "raceintel.model_lab",
    "raceintel.simulation",
    "raceintel.strategy",
    "raceintel.explainability",
)

PREDICTIVE_DIRS = (
    ROOT / "raceintel" / "features",
    ROOT / "raceintel" / "labels",
    ROOT / "raceintel" / "model_lab",
    ROOT / "raceintel" / "simulation",
    ROOT / "raceintel" / "strategy",
    ROOT / "raceintel" / "explainability",
)

SPATIAL_FORBIDDEN_IMPORTS = PREDICTIVE_MODULES + (
    "raceintel.serving",
    "raceintel.prediction",
    "api.",
    "fastapi",
    "starlette",
)


def _python_sources(directory: Path):
    return sorted(p for p in directory.rglob("*.py")
                  if "__pycache__" not in p.parts)


def test_predictive_modules_do_not_import_spatial():
    offenders = []
    for directory in PREDICTIVE_DIRS:
        for path in _python_sources(directory):
            text = path.read_text()
            if ("raceintel.spatial" in text
                    or "raceintel import spatial" in text
                    or "from . import spatial" in text):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == [], f"predictive modules import spatial: {offenders}"


def test_spatial_does_not_import_predictive_or_web():
    offenders = []
    for path in _python_sources(SPATIAL):
        text = path.read_text()
        hits = [name for name in SPATIAL_FORBIDDEN_IMPORTS if name in text]
        if hits:
            offenders.append(
                f"{path.relative_to(ROOT)}: {sorted(set(hits))}")
    assert offenders == [], f"spatial imports forbidden modules: {offenders}"


def test_product_seasons_match_frozen_authority():
    from api import v2_service as VS

    from raceintel.spatial import contracts as SC

    assert tuple(VS.SERVED_SEASONS) == tuple(range(2018, 2025))
    assert tuple(SC.PRODUCT_SERVED_SEASONS) == tuple(VS.SERVED_SEASONS)
    assert 2025 not in VS.SERVED_SEASONS
    assert 2025 not in SC.PRODUCT_SERVED_SEASONS
    assert not SC.is_product_servable(2025)
    assert SC.is_data_ingestible(2025)


def test_all84_unchanged_and_spatial_free():
    from raceintel.experiments import feature_sets as A
    from raceintel.features import build_f11_registry

    assert A.EXPECTED_PREDICTIVE_FEATURE_COUNT == 84
    registry = build_f11_registry()
    names = A.canonical_predictive_names(registry)
    assert len(names) == 84
    assert len(A.get_feature_set("ALL_84", registry).features) == 84
    spatial_tokens = ("spatial", "pos_x", "pos_y", "pos_z",
                      "observation_time", "coordinate", "track_x",
                      "track_y")
    offenders = [n for n in names
                 if any(tok in n.lower() for tok in spatial_tokens)]
    assert offenders == [], f"spatial names in ALL_84: {offenders}"
