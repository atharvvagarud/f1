"""V3.1A contract tests (declarative only; no calculators yet).

Verifies the frozen dynamics contract without computing any feature value,
training any model, or touching frozen artifacts.
"""

import sys

import pytest

from raceintel.features.dynamics import contract as C


def test_feature_names_unique_and_prefixed():
    names = [d.name for d in C.ALL_DEFINITIONS]
    assert len(names) == len(set(names)) == 29
    assert all(n.startswith("dyn_") for n in names)


def test_feature_counts_exact():
    assert len(C.CORE_DEFINITIONS) == 26
    assert len(C.VARIANT_DEFINITIONS) == 3
    assert len(C.ALL_DEFINITIONS) == 29
    assert len(C.FEATURE_SETS["V3_1_DYNAMICS_CORE"]) == 26
    assert len(C.FEATURE_SETS["V3_1_DYNAMICS_VARIANT_A"]) == 3
    assert len(C.FEATURE_SETS["V3_1_DYNAMICS"]) == 29


def test_dtypes_valid_and_nullable_declared():
    for d in C.ALL_DEFINITIONS:
        assert d.dtype in C.VALID_DTYPES, d.name
        assert isinstance(d.nullable, bool), d.name


def test_units_defined_and_horizons_valid():
    for d in C.ALL_DEFINITIONS:
        assert d.unit, d.name
        if d.horizon_laps is not None:
            assert d.horizon_laps in (3, 5, 10), d.name
        assert d.min_points >= 0, d.name
        assert d.temporal_rule in ("driver_prefix", "synchronized_field"), \
            d.name


def test_definitions_complete_with_incremental_rationale():
    for d in C.ALL_DEFINITIONS:
        assert d.description, d.name
        assert d.sources, d.name
        assert d.missing_policy, d.name
        if not d.variant:
            assert d.incremental_information, d.name


def test_feature_sets_deterministic_and_partitioned():
    core = set(C.FEATURE_SETS["V3_1_DYNAMICS_CORE"])
    variant = set(C.FEATURE_SETS["V3_1_DYNAMICS_VARIANT_A"])
    full = set(C.FEATURE_SETS["V3_1_DYNAMICS"])
    assert core & variant == set()
    assert core | variant == full
    assert [d.name for d in C.CORE_DEFINITIONS if d.variant] == []
    assert all(d.variant for d in C.VARIANT_DEFINITIONS)
    assert C.feature_set_names("core") == \
        C.FEATURE_SETS["V3_1_DYNAMICS_CORE"]
    assert C.feature_set_names("all") == \
        C.FEATURE_SETS["V3_1_DYNAMICS"]


def test_all_84_not_modified():
    from raceintel.experiments.feature_sets import (
        EXPECTED_PREDICTIVE_FEATURE_COUNT,
        canonical_predictive_names,
    )
    names = canonical_predictive_names()
    assert len(names) == 84 == EXPECTED_PREDICTIVE_FEATURE_COUNT
    assert not [n for n in names if n.startswith("dyn_")]
    assert "ALL_84" not in C.FEATURE_SETS


def test_canonical_serialization_deterministic():
    assert C.canonical_text() == C.canonical_text()
    assert C.contract_hash() == C.contract_hash()
    assert len(C.contract_hash()) == 64


def test_semantic_mutation_changes_hash():
    from dataclasses import replace
    mutated = replace(C.ALL_DEFINITIONS[0],
                      description="mutated description")
    orig = C.ALL_DEFINITIONS[0]
    try:
        C.ALL_DEFINITIONS = (mutated,) + C.ALL_DEFINITIONS[1:]
        assert C.contract_hash() != "0" * 64
        h1 = C.contract_hash()
    finally:
        C.ALL_DEFINITIONS = (orig,) + C.ALL_DEFINITIONS[1:]
    assert C.contract_hash() != h1


def test_no_forbidden_imports_or_io():
    src_path = C.__file__
    assert src_path.endswith("contract.py")
    with open(src_path) as fh:
        src = fh.read()
    import re
    imports = " ".join(
        line for line in src.splitlines()
        if re.match(r"\s*(import|from)\s", line))
    for forbidden in ("model_lab", "replay", "spatial", "simulation",
                      "strategy", "prediction", "pandas", "numpy",
                      "sklearn", "open(", "load_matrix"):
        assert forbidden not in imports, forbidden
    for mod in ("raceintel.model_lab", "raceintel.replay",
                "raceintel.spatial", "raceintel.simulation",
                "raceintel.strategy"):
        # Fresh-interpreter check: importing this contract file alone must
        # not pull frozen systems. (sys.modules of the current session is
        # order-dependent -- other test files legitimately import model_lab
        # first -- so a subprocess owns the isolation, not this process.)
        import subprocess
        code = ("import sys; "
                "import raceintel.features.dynamics.contract; "
                f"sys.exit(1 if {mod!r} in sys.modules else 0)")
        proc = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True)
        assert proc.returncode == 0, mod


def test_get_definition_and_unknown_name():
    d = C.get_definition("dyn_gap_leader_slope_l3")
    assert d.horizon_laps == 3 and d.dtype == "float64"
    with pytest.raises(KeyError):
        C.get_definition("no_such_feature")
    with pytest.raises(KeyError):
        C.feature_set_names("no_such_set")
