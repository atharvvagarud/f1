"""Phase-7 S1: Phase-6 baseline through the default-off intervention seam.

Loads the PRE-CHANGE compatibility fixture captured from the frozen Phase-6
runtime (``tests/fixtures/phase7_s1_phase6_baseline.json``, produced by
``scripts/capture_phase7_s1_baseline.py``) and re-runs the identical corpus
through the extended runtime with no intervention supplied. It asserts exact
equality of the complete stable result structures and identities.

The only excluded field is ``runtime_s`` (wall-clock operational metadata),
which is already excluded from ``MonteCarloResult.identity()``. The fixture
was captured before any Phase-7 runtime edit and is never regenerated here.
"""

from __future__ import annotations

import json

import pytest

import scripts.capture_phase7_s1_baseline as capture

FIXTURE_PATH = capture.FIXTURE_PATH


@pytest.fixture(scope="module")
def baseline() -> dict:
    return json.loads(FIXTURE_PATH.read_text())


def _specs_by_name() -> dict:
    return {spec["name"]: spec for spec in capture.specs()}


def test_baseline_fixture_exists_and_is_machine_readable(baseline):
    assert baseline["historical_phase6_tag"] == "v2-monte-carlo-phase6"
    assert baseline["cases"], "fixture must carry cases"
    assert set(baseline["environment"]) >= {"python", "numpy"}


def test_baseline_fixture_covers_early_mid_late_and_pit_paths(baseline):
    names = {case["name"] for case in baseline["cases"]}
    assert {"real_early_2023_r01_alonso_lap2",
            "real_mid_2022_r01_perez_lap30",
            "real_late_2022_r01_russell_lap38"} <= names
    # Both the batch and scalar production/oracle paths are exercised.
    assert any(case["scalar"] is not None for case in baseline["cases"])
    assert sum(case["scalar"] is not None for case in baseline["cases"]) >= 2


@pytest.mark.parametrize("name", [spec["name"] for spec in capture.specs()])
def test_phase6_baseline_through_phase7_seam(baseline, name):
    expected = {case["name"]: case for case in baseline["cases"]}[name]
    actual = capture.run_case(_specs_by_name()[name])

    # Identities first: a drift here is the strongest signal.
    assert actual["state_identity"] == expected["state_identity"], \
        f"{name}: SimulationState identity drift"
    assert actual["config_identity"] == expected["config_identity"], \
        f"{name}: SimulationConfig identity drift"
    assert actual["parameter_identity"] == expected["parameter_identity"], \
        f"{name}: parameter identity drift"

    # Complete stable result structure, exactly.
    assert actual["batch"]["identity"] == expected["batch"]["identity"], \
        f"{name}: batch MonteCarloResult identity drift"
    assert actual["batch"]["result"] == expected["batch"]["result"], \
        f"{name}: batch result payload drift"

    if expected["scalar"] is not None:
        assert actual["scalar"]["identity"] == expected["scalar"]["identity"], \
            f"{name}: scalar MonteCarloResult identity drift"
        assert actual["scalar"]["result"] == expected["scalar"]["result"], \
            f"{name}: scalar result payload drift"


def test_no_intervention_reports_current_frozen_runtime_versions(baseline):
    # The intervention seam must not change the frozen scientific contract
    # versions reported in the result payload.
    from raceintel.simulation.monte_carlo import (
        MONTE_CARLO_VERSION,
        PIT_DYNAMICS_VERSION,
    )
    from raceintel.simulation.results import PROBABILITY_SEMANTICS

    first = baseline["cases"][0]["batch"]["result"]
    assert first["simulation_contract_version"] == "v1"
    assert first["probability_semantics"] == PROBABILITY_SEMANTICS
    assert MONTE_CARLO_VERSION == "r5-monte-carlo-v1"
    assert PIT_DYNAMICS_VERSION == "r6-pit-dynamics-v1"
