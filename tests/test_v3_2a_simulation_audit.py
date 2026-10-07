"""V3.2A read-only simulation coverage audit tests.

Audit-only regression net for ``scripts/audit_v3_2_simulation_coverage.py``:
pins the eligibility taxonomy, the stage rule, the frozen simulator reason
tokens the classifier maps, and the classifier outcome on three pinned
checkpoints of one clean race. No simulator source is touched, no parameter
is regenerated, no model is trained, and no Monte Carlo sweep runs here
(the classifier is input validation only by design).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from audit_v3_2_simulation_coverage import (  # noqa: E402
    TAXONOMY,
    _ADAPTER_TO_TAXONOMY,
    _ENGINE_TO_TAXONOMY,
    classify_checkpoint,
    stage_for,
)
from raceintel.simulation.adapter import (  # noqa: E402
    ADAPTER_UNAVAILABLE_REASONS,
)
from raceintel.simulation.engine import (  # noqa: E402
    ENGINE_UNSUPPORTED_REASONS,
)


def test_taxonomy_covers_every_frozen_adapter_reason():
    for reason in ADAPTER_UNAVAILABLE_REASONS:
        assert reason in _ADAPTER_TO_TAXONOMY, reason
        assert _ADAPTER_TO_TAXONOMY[reason] in TAXONOMY


def test_taxonomy_covers_every_frozen_engine_reason():
    for reason in ENGINE_UNSUPPORTED_REASONS:
        assert reason in _ENGINE_TO_TAXONOMY, reason
        assert _ENGINE_TO_TAXONOMY[reason] in TAXONOMY


def test_taxonomy_has_no_orphan_tokens():
    assert TAXONOMY[0] == "SIMULATION_CAPABLE"
    assert len(set(TAXONOMY)) == len(TAXONOMY)


def test_stage_rule_boundaries():
    assert stage_for(0.0) == "EARLY"
    assert stage_for(0.33) == "EARLY"
    assert stage_for(1.0 / 3.0) == "MID"
    assert stage_for(0.5) == "MID"
    assert stage_for(2.0 / 3.0) == "LATE"
    assert stage_for(0.99) == "LATE"


def test_classifier_is_deterministic_on_pinned_checkpoints():
    from audit_v3_2_simulation_coverage import (
        load_race_inputs,
        season_of,
    )
    from raceintel.race_state.race_state_reconstruction import (
        RaceStateReconstructor,
    )
    from raceintel.replay import replay as RP
    from raceintel.replay.replay_reconstruction import ReplayReconstructor
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )

    race_id = "2023-r05-R"
    parameters = load_simulation_parameters(
        parameter_storage_dir(ROOT, 2024))
    states, results, meta = load_race_inputs(season_of(race_id), race_id)
    timeline = RP.build_replay_timeline(states)
    service = ReplayReconstructor(
        timeline, RaceStateReconstructor(states, results,
                                         race_meta=meta or None))
    # Frame 0 (lap 1): roster not yet fully observed -> refused honestly.
    verdict0, _, _, _, _ = classify_checkpoint(
        service.state_at, 0, parameters)
    assert verdict0 == "MISSING_DRIVER_OBSERVATION"
    # Frame 160 (lap 9, clean green race): simulation-capable.
    verdict1, _, stage1, _, _ = classify_checkpoint(
        service.state_at, 160, parameters)
    assert verdict1 == "SIMULATION_CAPABLE"
    assert stage1 == "EARLY"
    # Re-running the same checkpoint is byte-stable in verdict/stage.
    verdict2, reason2, stage2, _, _ = classify_checkpoint(
        service.state_at, 160, parameters)
    assert (verdict2, reason2, stage2) == (
        verdict1, "capable", stage1)
    # Last checkpoint (frame 1118, leader lap 57 = scheduled distance):
    # terminal, never simulated.
    verdict3, _, _, _, _ = classify_checkpoint(
        service.state_at, 1118, parameters)
    assert verdict3 == "TERMINAL_STATE"


def test_audit_module_imports_no_model_or_api_layer():
    import audit_v3_2_simulation_coverage as audit

    source = Path(audit.__file__).read_text(encoding="utf-8")
    for forbidden in ("model_lab", "prediction", "FastAPI", "sklearn",
                      "v2_service", "replay_predictions"):
        assert forbidden not in source, forbidden
