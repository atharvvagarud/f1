"""V3.1B governance tests (source-safe, no corpus, no training).

Pins the frozen contract identity, the import firewall, label-blind
input declarations, and the ALL_84 firewall without touching data.
"""

import pathlib

from raceintel.features.dynamics import contract as C
from raceintel.features.dynamics import validation as V
from raceintel.features.dynamics import build as B


def test_contract_identity_pinned_exact():
    assert C.CONTRACT_VERSION == "v3.1a-v2"
    assert C.contract_hash() == \
        "abd5300816d79270b1cd5b9b4952ebe447817f770eeddd2c598d0f07fbd5a0a4"


def test_no_training_or_product_imports():
    pkg = pathlib.Path(B.__file__).parent
    forbidden = ("model_lab", "simulation", "strategy", "prediction",
                 "spatial", "sklearn", "train", "serve", "frontend",
                 "api", "replay")
    for path in sorted(pkg.glob("*.py")):
        if path.name == "__init__.py":
            continue
        src = path.read_text()
        for line in src.splitlines():
            s = line.strip()
            if s.startswith(("import ", "from ")):
                for word in forbidden:
                    assert word not in s, f"{path.name}: {s}"


def test_builder_inputs_label_blind():
    label_fragments = ("is_winner", "is_podium", "scored_points",
                       "final_position", "gains_position",
                       "loses_position", "position_change_from_state",
                       "classified_flag", "eligible_")
    for col in B.MATRIX_INPUT_COLUMNS + B.D9_JOIN_COLUMNS:
        assert not any(f in col for f in label_fragments), col


def test_all_84_firewall_registry():
    from raceintel.experiments.feature_sets import (
        EXPECTED_PREDICTIVE_FEATURE_COUNT,
        canonical_predictive_names,
    )
    names = canonical_predictive_names()
    assert len(names) == 84 == EXPECTED_PREDICTIVE_FEATURE_COUNT
    assert not [n for n in names if n.startswith("dyn_")]
    assert set(names).isdisjoint(set(C.feature_set_names("all")))


def test_validation_rejects_wrong_contract():
    import pytest
    with pytest.raises(V.DynamicsValidationError):
        V.check_contract_pinned("vX", "0" * 64)
    with pytest.raises(V.DynamicsValidationError):
        V.check_parent_identities("0" * 64, "0" * 64)
    with pytest.raises(V.DynamicsValidationError):
        V.validate_feature_names(["dyn_only_one"])
