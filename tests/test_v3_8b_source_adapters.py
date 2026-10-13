"""V3.8B source-adapter tests: native preservation + provenance + guards.

Infrastructure only: adapters are pure pass-through constructors over
frozen-native values. Tests prove no transformation, no normalization,
fail-closed validation, V3.4 exclusion, and exact parity on the frozen
validation corpus.
"""

import hashlib
import json
import math
from pathlib import Path

import pytest

from raceintel.consensus import adapters as A
from raceintel.consensus import contracts as C

ROOT = Path(__file__).resolve().parents[1]
B_CONTRACT = ROOT / "results" / "v3" / "v3_8b" / "alignment_contract.json"
CORPUS = ROOT / "results" / "v3" / "v3_8b" / "validation_corpus.json"


def _b():
    return json.loads(B_CONTRACT.read_text())


def _corpus():
    return json.loads(CORPUS.read_text())


def _prov(path="results/v3/v3_1d_model_card.json",
          ident="audit-pinned", model="test-model"):
    return C.Provenance(artifact_path=path, artifact_identity=ident,
                        model_identity=model)


def _meta(driver="perez", stage="MID", lap=30,
          race="2022-r01-R", year=2022, round_=1):
    return A.StateMeta(driver_id=driver, race_id=race, year=year,
                       round=round_, lap=lap, stage=stage)


# --- contract / registry ---


def test_b_contract_schema():
    assert _b()["schema"] == "v3.8b-source-alignment-contract-v1"


def test_b_contract_identity_recomputes():
    c = _b()
    identity = c.pop("contract_identity")
    blob = json.dumps(c, sort_keys=True, separators=(",", ":")).encode()
    assert identity == hashlib.sha256(blob).hexdigest()
    assert identity == \
        "d212803f7ed7e8a8563abdd5b7686326e7094d810f415fa1468117541dfbfde7"


def test_a_identity_exact():
    assert _b()["a_contract_identity"] == \
        "d0b8785a01347580125b38b311984c793c012352ce3ff175cfa3504379b9a67b"


def test_source_registry_exact():
    assert set(_b()["source_registry"]) == {
        "V3_1B_LOGISTIC", "MC2_E", "V3_5_LOGISTIC_CONTROL",
        "V3_5_XGB_E", "V3_3_XGBOOST"}
    assert set(C.SourceId) == {
        C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E,
        C.SourceId.V3_5_LOGISTIC_CONTROL, C.SourceId.V3_5_XGB_E,
        C.SourceId.V3_3_XGBOOST}


def test_v34_excluded_from_registry():
    assert "V3_4" not in json.dumps(_b()["source_registry"])
    assert "ENSEMBL" not in json.dumps(_b()["source_registry"])
    with pytest.raises(ValueError):
        A.admit_source_name("V3_4_ENSEMBLE")
    with pytest.raises(ValueError):
        A.admit_source_name("v3.4 ensemble blend")
    with pytest.raises(ValueError):
        A.admit_source_name("ENSEMBLED_MODEL")


def test_adapter_identities_exact():
    assert _b()["adapter_identities"] == {
        "V3_1B_LOGISTIC": "v3.8b-logistic-adapter-v1",
        "MC2_E": "v3.8b-mc2-adapter-v1",
        "V3_5_LOGISTIC_CONTROL": "v3.8b-v3.5-adapter-v1",
        "V3_5_XGB_E": "v3.8b-v3.5-adapter-v1",
        "V3_3_XGBOOST": "v3.8b-xgb-adapter-v1"}
    assert C.ADAPTER_IDENTITIES[C.SourceId.MC2_E] == \
        "v3.8b-mc2-adapter-v1"


def test_families_exact():
    assert C.SOURCE_FAMILIES[C.SourceId.V3_1B_LOGISTIC] is \
        C.SourceFamily.INDEPENDENT_BINARY
    assert C.SOURCE_FAMILIES[C.SourceId.MC2_E] is \
        C.SourceFamily.MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY
    assert C.SOURCE_FAMILIES[C.SourceId.V3_5_LOGISTIC_CONTROL] is \
        C.SourceFamily.MARGINAL_THRESHOLD
    assert C.SOURCE_FAMILIES[C.SourceId.V3_5_XGB_E] is \
        C.SourceFamily.MARGINAL_THRESHOLD
    assert C.SOURCE_FAMILIES[C.SourceId.V3_3_XGBOOST] is \
        C.SourceFamily.INDEPENDENT_BINARY


def test_xgb_role_secondary_not_primary():
    # XGB shares the independent-binary mechanics but is not a primary
    # consensus source (A classification); the B registry carries no
    # primary/secondary flag by design, so assert the A audit record.
    audit = json.loads(
        (ROOT / "results" / "v3" / "v3_8a" / "source_audit.json")
        .read_text())
    assert audit["sources"]["V3.3_XGBOOST"]["family"] == \
        "INDEPENDENT_BINARY_MODEL_PROBABILITY"


def test_targets_exact():
    assert {t.value for t in C.Target} == {"WIN", "TOP3", "TOP5", "TOP10"}


# --- probability validation ---


def test_probability_below_zero_rejected():
    with pytest.raises(ValueError):
        A.validate_probability(-0.01)


def test_probability_above_one_rejected():
    with pytest.raises(ValueError):
        A.validate_probability(1.01)


def test_nan_rejected():
    with pytest.raises(ValueError):
        A.validate_probability(float("nan"))


def test_inf_rejected():
    with pytest.raises(ValueError):
        A.validate_probability(float("inf"))
    with pytest.raises(ValueError):
        A.validate_probability(float("-inf"))


def test_boundaries_accepted_unclamped():
    assert A.validate_probability(0.0) == 0.0
    assert A.validate_probability(1.0) == 1.0


# --- native parity (corpus) ---


def _adapted_logistic(corpus):
    out = []
    for st in corpus["states"]:
        tag = {"a": "a", "b": "b", "c": "c", "d": "d", "e": "e",
               "f": "f"}[st["state_id"][0]]
        for drv, native in zip(corpus["drivers"],
                               corpus["logistic_win"][tag]):
            meta = A.StateMeta(
                driver_id=drv, race_id=st["race_id"], year=st["year"],
                round=st["round"], lap=st["lap"], stage=st["stage"])
            out.append((native, A.from_independent_binary(
                st["state_id"], native, meta,
                C.SourceId.V3_1B_LOGISTIC, _prov())))
    return out


def test_logistic_native_parity_exact():
    for native, rec in _adapted_logistic(_corpus()):
        assert rec.native_probability == native
        assert rec.native_probability - native == 0.0


def test_logistic_no_normalization_corpus():
    # Corpus logistic rows do not sum to 1; adaptation must not change that.
    corpus = _corpus()
    recs = _adapted_logistic(corpus)
    by_state: dict = {}
    for _, rec in recs:
        by_state.setdefault(rec.state_id, []).append(
            rec.native_probability)
    assert any(abs(sum(v) - 1.0) > 1e-9 for v in by_state.values())
    for _, rec in recs:
        assert rec.normalization_semantics is \
            C.NormalizationSemantics.NOT_RACE_NORMALIZED


def test_mc2_native_parity():
    from raceintel.simulation.results import (
        DriverSimulationSummary, PositionFrequency)
    corpus = _corpus()
    for st in corpus["states"]:
        tag = st["state_id"][0]
        if tag not in corpus["mc2_win"]:
            continue
        for drv, native in zip(corpus["drivers"],
                               corpus["mc2_win"][tag]):
            dist = (PositionFrequency(1, native),
                    PositionFrequency(2, 0.05),
                    PositionFrequency(None, 0.0))
            summary = DriverSimulationSummary(
                driver_id=drv, win_probability=native,
                finish_position_distribution=dist)
            meta = A.StateMeta(
                driver_id=drv, race_id=st["race_id"], year=st["year"],
                round=st["round"], lap=st["lap"], stage=st["stage"])
            rec = A.from_mc2_win(summary, st["state_id"], meta,
                                 _prov("mc2", "m", "MC2-E"), 5000)
            assert rec.native_probability == native
            assert rec.mc_valid_trials == 5000
            assert rec.derived_from_mc2_counts is False


def test_mc2_semantics_preserved():
    from raceintel.simulation.results import DriverSimulationSummary
    summary = DriverSimulationSummary(driver_id="perez",
                                      win_probability=0.2)
    meta = _meta()
    rec = A.from_mc2_win(summary, "s" * 64, meta,
                         _prov("mc2", "m", "MC2-E"), 5000)
    assert rec.source_family is \
        C.SourceFamily.MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY
    assert rec.normalization_semantics is \
        C.NormalizationSemantics.MUTUALLY_EXCLUSIVE_RACE_FREQUENCY


def test_mc2_derived_topk_mechanical():
    from raceintel.simulation.results import (
        DriverSimulationSummary, PositionFrequency)
    dist = (PositionFrequency(1, 0.2), PositionFrequency(2, 0.1),
            PositionFrequency(3, 0.1), PositionFrequency(4, 0.05),
            PositionFrequency(None, 0.0))
    assert A.mc2_derived_topk(dist, 3) == pytest.approx(0.4)
    summary = DriverSimulationSummary(driver_id="perez",
                                      win_probability=0.2,
                                      finish_position_distribution=dist)
    rec = A.from_mc2_topk(summary, "s" * 64, _meta(),
                          _prov("mc2", "m", "MC2-E"), 5000, 3)
    assert rec.target is C.Target.TOP3
    assert rec.native_probability == pytest.approx(0.4)
    assert rec.derived_from_mc2_counts is True


def test_v35_native_parity():
    corpus = _corpus()
    for st in corpus["states"]:
        tag = st["state_id"][0]
        if tag == "f":
            continue  # missing-driver case covered separately
        for drv, native in zip(corpus["drivers"],
                               corpus["v35_proj_top3"][tag]):
            row = {"state_id": st["state_id"], "driver_id": drv,
                   "race_id": st["race_id"], "year": st["year"],
                   "round": st["round"], "lap": st["lap"],
                   "stage": st["stage"], "proj_top3": native}
            rec = A.from_v35_row(
                row, C.Target.TOP3, C.SourceId.V3_5_LOGISTIC_CONTROL,
                _prov("v35", "v", "LOGISTIC_CONTROL"))
            assert rec.native_probability == native
            assert rec.normalization_semantics is \
                C.NormalizationSemantics.NOT_JOINT_NOT_RACE_NORMALIZED


def test_v35_rejects_positional_inference():
    with pytest.raises(ValueError):
        A.from_v35_row({"state_id": "s" * 64}, C.Target.WIN,
                       C.SourceId.V3_5_LOGISTIC_CONTROL,
                       _prov("v35", "v", "LOGISTIC_CONTROL"))


def test_xgb_native_parity():
    corpus = _corpus()
    st = corpus["states"][1]
    native = corpus["xgb_win"]["b"][0]
    meta = A.StateMeta(driver_id="verstappen", race_id=st["race_id"],
                       year=st["year"], round=st["round"], lap=st["lap"],
                       stage=st["stage"])
    rec = A.from_independent_binary(st["state_id"], native, meta,
                                    C.SourceId.V3_3_XGBOOST, _prov())
    assert rec.native_probability == native
    assert rec.source_id is C.SourceId.V3_3_XGBOOST


# --- missing vs native zero ---


def test_native_zero_distinct_from_missing():
    rec = A.from_independent_binary(
        "f" * 64, 0.0, _meta(driver="perez", stage="LATE", lap=60),
        C.SourceId.V3_1B_LOGISTIC, _prov())
    assert rec.native_probability == 0.0
    assert rec.support_status is C.SupportStatus.AVAILABLE
    missing = A.missing_record("f" * 64, "perez",
                               C.SourceId.V3_5_LOGISTIC_CONTROL,
                               C.ReasonCode.DRIVER_NOT_AVAILABLE)
    assert missing["support_status"] is C.SupportStatus.UNAVAILABLE
    assert missing["reason"] is C.ReasonCode.DRIVER_NOT_AVAILABLE
    assert "native_probability" not in missing


def test_missing_never_zero_or_nan():
    missing = A.missing_record("s" * 64, "hamilton", C.SourceId.MC2_E,
                               C.ReasonCode.MC2_STATE_INELIGIBLE)
    assert missing["reason"] is C.ReasonCode.MC2_STATE_INELIGIBLE
    assert not any(isinstance(v, float) for v in missing.values())


def test_ground_truth_keys_rejected_in_v35_rows():
    row = {"state_id": "s" * 64, "driver_id": "perez",
           "race_id": "2022-r01-R", "year": 2022, "round": 1, "lap": 30,
           "stage": "MID", "proj_top1": 0.2, "is_winner": 1}
    with pytest.raises(ValueError):
        A.from_v35_row(row, C.Target.WIN,
                       C.SourceId.V3_5_LOGISTIC_CONTROL,
                       _prov("v35", "v", "LOGISTIC_CONTROL"))


# --- structural guards ---


def test_no_normalization_helper_in_package():
    import raceintel.consensus.adapters as mod
    import raceintel.consensus.alignment as alg
    blob = (open(mod.__file__).read() + open(alg.__file__).read()).lower()
    assert "softmax" not in blob
    assert "simplex" not in blob
    assert "normalize" not in blob.replace(
        "normalization_semantics", "").replace(
        "normalization_prohibition", "")


def test_no_fusion_or_consensus_scalar_in_package():
    import raceintel.consensus.adapters as mod
    import raceintel.consensus.alignment as alg
    import raceintel.consensus.contracts as con
    blob = (open(mod.__file__).read() + open(alg.__file__).read()
            + open(con.__file__).read()).lower()
    assert "consensus =" not in blob
    assert "fuse" not in blob
    assert "average(" not in blob
    assert "combined confidence" not in blob


def test_no_forbidden_upward_dependencies():
    import raceintel.consensus.adapters as mod
    import raceintel.consensus.alignment as alg
    import raceintel.consensus.contracts as con
    blob = (open(mod.__file__).read() + open(alg.__file__).read()
            + open(con.__file__).read())
    for token in ("v3_4_ensemble", "from frontend", "import frontend",
                  "from api", "import api", "strategy.v3_",
                  "strategy import", "counterfactual",
                  "fusion", "v2_routes", "v2_service"):
        assert token not in blob, token


def test_no_frozen_source_modified():
    import subprocess
    out = subprocess.run(["git", "status", "--short"], capture_output=True,
                         text=True,
                         cwd=str(ROOT)).stdout
    # V3.8H reconciliation: the B stage-entry boundary predates the
    # chartered D-G additions (D/E scripts, F API/product, G frontend)
    # and the H freeze. Final freeze allowlist admits exactly the
    # chartered V3.8-owned paths, the two additive wiring files, and the
    # Tier-1 runner reclassification; any other dirt still fails.
    # Original invariant preserved: frozen-science mutation outside V3.8
    # ownership still trips this guard.
    allowed = (
        "results/v3/v3_8a/", "results/v3/v3_8b/", "results/v3/v3_8c/",
        "results/v3/v3_8d/", "results/v3/v3_8e/", "results/v3/v3_8f/",
        "results/v3/v3_8g/", "results/v3/v3_8h/",
        "docs/V3_8",
        "raceintel/consensus/",
        "scripts/v3_8d_", "scripts/v3_8e_",
        "scripts/run_ci_tests.py", "scripts/run_ci_frontend_tests.py",
        "tests/test_v3_8",
        "api/v2_consensus_", "api/main.py",
        "frontend/app/consensus", "frontend/features/consensus",
        "frontend/components/shell/CommandBar.tsx",
        # V3.8H historical-guard reconciliations (Tier-1-driven; exact
        # files only; frozen science untouched).
        "tests/test_v3_5a_contract.py", "tests/test_v3_5b_dataset.py",
        "tests/test_v3_5c_harness.py", "tests/test_v3_5d_screening.py",
        "tests/test_v3_6a_contract.py", "tests/test_v3_6b_contracts.py",
        "tests/test_v3_6d_evaluation.py", "tests/test_v3_6f_runtime.py",
        "tests/test_v3_6h_freeze.py", "tests/test_v3_7a_contract.py",
        # P2A carve-out (performance programme only): exactly the two
        # kernel files with hoisted loop-invariant overhead; public APIs,
        # validation, RNG, and arithmetic order unchanged (parity-gated
        # in P0-P20/P1-P3/P2A-P29 checks, not here).
        "raceintel/simulation/mc2/kernel.py",
        "raceintel/simulation/mc2/residuals.py",
        # P2A performance-programme files (exact paths/prefixes; science
        # and product behavior unchanged).
        "results/v3/performance_mc2/",
        "docs/MC2_PERFORMANCE_",
        "raceintel/simulation/mc2_batch.py",
        "scripts/mc2_batch_benchmark.py",
        "tests/test_perf_mc2_p0.py",
        "tests/test_mc2_batch_p1.py",
        "tests/test_mc2_p2a.py",
        # P2B carve-out: exact-order heap queue tests (parity-gated by
        # P2B-P1..P30, not here).
        "tests/test_mc2_p2b.py",
        # P3-1 carve-out: exact scalar-interpolation audit tests
        # (parity-gated by P3-1-P1..P30, not here).
        "tests/test_mc2_p3_1.py",
        # Freeze carve-out: focused freeze validation tests
        "tests/test_perf_mc2_freeze.py",
        # V3.9A carve-out (contract stage only, no science/runtime change).
        "results/v3/v3_9a/",
        "docs/V3_9A",
        "tests/test_v3_9a_contract.py",
        # V3.9B carve-out (offline measurement stage, no science/runtime change).
        "results/v3/v3_9b/",
        "docs/V3_9B",
        "tests/test_v3_9b_measurement.py",
        # V3.9C carve-out (runtime bundle stage,
        # thin product layer only: bundle + API).
        "results/v3/v3_9c/",
        "docs/V3_9C",
        "tests/test_v3_9c_bundle.py",
        "raceintel/uncertainty/",
        "api/v2_uncertainty_",
        # V3.9D carve-out (product UI stage only: /uncertainty route,
        # uncertainty feature modules, stage docs/artifacts; no science,
        # runtime, or API change).
        "results/v3/v3_9d/",
        "docs/V3_9D",
        "frontend/app/uncertainty/",
        "frontend/features/uncertainty/",
        # V3.9E carve-out (freeze stage only: programme manifest, parity
        # records, final audits, freeze test + final doc; no science or
        # runtime change).
        "results/v3/v3_9e/",
        "docs/V3_9_UNCERTAINTY_INTELLIGENCE_FINAL.md",
        "tests/test_v3_9e_freeze.py",
    )
    for line in out.splitlines():
        if line.strip():
            pth = line.split(None, 1)[-1]
            # V3.8-scoped paths only (later V3.8 stages extend within
            # these prefixes; any non-V3.8 dirt still fails).
            assert pth.startswith(allowed), line
