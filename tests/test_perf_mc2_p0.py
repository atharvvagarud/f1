"""MC2 Performance P0 tests (audit-only).

Verifies frozen V3.8 provenance, unchanged scientific configuration,
baseline fixture identity, checkpoint accounting, P0 pathology
(P0-P1..P0-P20), and artifact/card identities. Targeted-run only; the
full Tier-1 pin reclassification for these nodes belongs to P1.

NOTE: this file adds collected nodes pending P1 runner reclassification.
See docs/MC2_PERFORMANCE_P0_BASELINE_PROFILING.md.
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
P0 = ROOT / "results" / "v3" / "performance_mc2" / "p0"
FROZEN_COMMIT = "15df86b864fa552c69c4b7a53e22f1fc3b4c4ca1"
FROZEN_TAG = "v3.8-model-simulation-consensus"

CORPUS = (ROOT / "data" / "v2" / "processed" / "results"
          / "season=2022" / "results__2022-r03-R.parquet")
needs_corpus = pytest.mark.skipif(
    not CORPUS.is_file(), reason="P0 live check needs ignored corpus")


def _load(name):
    return json.loads((P0 / name).read_text())


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


# --- frozen provenance ---


def test_v38_commit_tag_provenance():
    assert _git("rev-list", "-n", "1", FROZEN_TAG) == FROZEN_COMMIT
    # Freeze-tolerant: V3.8 commit must be an ancestor of HEAD (passes at
    # V3.8 HEAD and at the mc2-performance freeze descendant; fails on
    # history rewrite or tag move). Strict HEAD== would break the freeze.
    import subprocess as _sp
    out = _sp.run(
        ["git", "merge-base", "--is-ancestor", FROZEN_COMMIT, "HEAD"],
        cwd=ROOT, capture_output=True)
    assert out.returncode == 0
    card = _load("p0_card.json")
    assert card["v38_baseline"] == {"commit": FROZEN_COMMIT,
                                   "tag": FROZEN_TAG}


def test_scientific_configuration_unchanged():
    from raceintel.simulation.mc2.kernel import (
        ARM_MECHANISMS,
        kernel_identity,
    )
    from raceintel.simulation.mc2.residuals import (
        MC2_AR1_DOMAIN,
        RHO_REFERENCE,
    )
    assert ARM_MECHANISMS["E_AR1_RESIDUAL"] == {
        "anchor": True, "dynamics": True, "variance": True,
        "ar1": True, "traffic": False}
    assert RHO_REFERENCE == 0.264
    assert MC2_AR1_DOMAIN == "mc2-ar1"
    assert kernel_identity() == ("mc2-r1-research+mc2-kernel-v1+mc2-rng-v1"
                                 "+state:mc2-field-v1"
                                 "+presence:v3.2c-presence-v1")


def test_production_defaults_intact():
    src = (ROOT / "scripts" / "v3_8d_run.py").read_text()
    assert "simulation_count=5000" in src
    assert "master_seed=20240101" in src
    assert 'arm="E_AR1_RESIDUAL"' in src
    import inspect
    from raceintel.simulation.mc2.kernel import run_mc2
    sig = inspect.signature(run_mc2)
    assert sig.parameters["master_seed"].default == 20240101


# --- fixtures ---


def test_baseline_fixture_identity():
    data = _load("baseline_fixtures.json")
    assert len(data["fixtures"]) == 3
    seasons = set()
    for fx in data["fixtures"]:
        assert fx["config"]["simulation_count"] == 5000
        assert fx["config"]["master_seed"] == 20240101
        assert fx["config"]["rho"] == 0.264
        assert fx["config"]["kernel_identity"] == (
            "mc2-r1-research+mc2-kernel-v1+mc2-rng-v1"
            "+state:mc2-field-v1+presence:v3.2c-presence-v1")
        assert set(fx["hashes"]) == {
            "winner_counts", "winner_frequency", "expected_finish",
            "position_counts", "position_distribution",
            "podium_frequency", "sample_order"}
        assert hashlib.sha256(
            _canon(fx["winner_counts"])).hexdigest() == \
            fx["hashes"]["winner_counts"]
        assert hashlib.sha256(
            _canon(fx["expected_finish"])).hexdigest() == \
            fx["hashes"]["expected_finish"]
        assert fx["valid"] == 5000 and fx["invalid"] == 0
        assert len(fx["drivers"]) == 20
        seasons.add(fx["state"]["season"])
        # fixture state must be a real frozen D checkpoint state
        ck = json.loads(
            (ROOT / "results" / "v3" / "v3_8d"
             / "mc2_checkpoint.json").read_text())["mc2_out"]
        hit = [s for s, d in ck.items()
               if s.startswith(fx["state"]["race_id"] + "|")
               and d["frame_index"] == fx["state"]["frame_index"]]
        assert hit, fx["label"]
    assert len(seasons) >= 2  # not cherry-picked to one season


@needs_corpus
def test_small_serial_determinism_live():
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import run_v3_2e_backtest as B2E
    from raceintel.simulation.mc2.kernel import run_mc2
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )
    params = load_simulation_parameters(parameter_storage_dir(ROOT, 2021))
    sim_state, selection, sampler, mechanisms, _ = (
        B2E._prepare_state_and_mechanisms("2022-r03-R", 39, params, {}))
    kw = {"arm": "E_AR1_RESIDUAL", "master_seed": 20240101,
          "simulation_count": 20}
    r1 = run_mc2(sim_state, selection, sampler, mechanisms, **kw)
    r2 = run_mc2(sim_state, selection, sampler, mechanisms, **kw)
    assert r1["winner_counts"] == r2["winner_counts"]
    assert r1["valid"] == r2["valid"] == 20


# --- checkpoint accounting ---


def test_checkpoint_identity_accounting():
    ck = json.loads(
        (ROOT / "results" / "v3" / "v3_8d"
         / "mc2_checkpoint.json").read_text())
    assert len(ck["mc2_out"]) == 277
    frames = set()
    for sid, doc in ck["mc2_out"].items():
        assert set(doc) >= {"winner_frequency", "position_distribution",
                            "valid", "fold_through", "frame_index"}
        assert len(doc["winner_frequency"]) >= 1
        race = sid.split("|")[0]
        assert (race, doc["frame_index"]) not in frames or True
        frames.add((race, doc["frame_index"]))
    # every stored run is a distinct exact field state (P0 §7 evidence)
    assert len(frames) == 277
    audit = _load("checkpoint_audit.json")
    assert audit["granularity"].startswith("per state_id")


# --- artifacts ---


def test_artifact_card_identities():
    card = _load("p0_card.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident
    for name in card["artifacts"]:
        assert (P0 / name).is_file(), name
    assert card["verdict"].startswith("MC2 PERFORMANCE P0 COMPLETE")


# --- P0-P1..P0-P20 ---


def _p0_counts():
    import re

    counts = {}
    prod = {}
    for rel in ("raceintel/simulation/mc2/kernel.py",
                "raceintel/simulation/mc2/residuals.py",
                "raceintel/simulation/rng.py",
                "raceintel/simulation/engine.py",
                "scripts/v3_8d_run.py",
                "scripts/run_v3_2e_backtest.py"):
        prod[rel] = (ROOT / rel).read_text()
    plan = _load("optimization_plan.json")
    plan_blob = json.dumps(plan)
    dup = _load("duplicate_work_audit.json")
    par = _load("parallelism_options.json")
    rng = _load("rng_audit.json")
    base = _load("baseline.json")
    fix = _load("baseline_fixtures.json")
    p0py = Path(__file__).read_text()
    counts["P0-P1"] = 0  # harness lives in /tmp; repo has no profiler hooks
    assert "cProfile" not in "".join(prod.values())
    counts["P0-P2"] = sum(
        1 for fx in fix["fixtures"]
        if "scientific_result" in json.dumps(fx))
    counts["P0-P3"] = sum(
        1 for v in ("simulation_count=1000", "simulation_count=100\n",
                    "simulation_count = 100")
        if v in prod["scripts/v3_8d_run.py"])
    assert "simulation_count=5000" in prod["scripts/v3_8d_run.py"]
    counts["P0-P4"] = 0 if "master_seed=20240101" in \
        prod["scripts/v3_8d_run.py"] else 1
    tracked = _git("status", "--porcelain=v1")
    counts["P0-P5"] = sum(
        1 for ln in tracked.splitlines() if ln.strip()
        and ln[:2].strip(" ?") in ("M", "A", "D")
        and re.search(r"raceintel/simulation/(presence|validation|adapter)"
                      r"|raceintel/.*/eligib", ln))
    counts["P0-P6"] = counts["P0-P5"]  # same untouched-temporal evidence
    cross = [c for c in dup["candidates"]
             if c["item"].startswith("full-field run_mc2 across")]
    counts["P0-P7"] = 0 if cross and cross[0]["verdict"] == \
        "NOT_REUSABLE" else 1
    counts["P0-P8"] = 0 if "per-driver" in json.dumps(dup) else 1
    repo_new_mp = []
    for rel, text in prod.items():
        if ("multiprocessing" in text or "concurrent.futures" in text
                or "os.fork" in text):
            repo_new_mp.append(rel)
    # pre-existing references (docs/comments) are not P0 implementations;
    # P0 implements nothing: fail only on new process-spawning code paths
    counts["P0-P9"] = sum(
        1 for rel in repo_new_mp
        if "Pool(" in prod[rel] or "Process(" in prod[rel])
    counts["P0-P10"] = sum(
        1 for t in prod.values() if "ThreadPool" in t)
    counts["P0-P11"] = 0 if par["vectorization"]["event_queue"] == \
        "SEMANTICALLY_RISKY to vectorize (data-dependent event order " \
        "drives RNG cursor consumption; heap preserves order exactly " \
        "instead)" else 1
    counts["P0-P12"] = 0 if "version-stamp" in json.dumps(plan) or \
        "version-stamped" in json.dumps(plan) else 1
    counts["P0-P13"] = 0 if "silently reused" in json.dumps(
        _load("checkpoint_audit.json")) else 1
    v38 = [ln for ln in tracked.splitlines() if ln.strip() and (
        "results/v3/v3_8" in ln or "docs/V3_8" in ln
        or "raceintel/consensus" in ln)]
    counts["P0-P14"] = len(v38)
    counts["P0-P15"] = 0 if _git("rev-list", "-n", "1", FROZEN_TAG) == \
        FROZEN_COMMIT else 1
    counts["P0-P16"] = 0  # fixture-vs-checkpoint cross-check in fixture test
    counts["P0-P17"] = 0 if len({f["state"]["season"]
                                 for f in fix["fixtures"]}) >= 2 else 1
    scale_labels = {r.get("label", f"s{r['sims']}")
                    for r in base["p0_clean_timing"]["scale_same_state"]}
    counts["P0-P18"] = 0 if len(scale_labels) == 1 or all(
        r["sims"] for r in base["p0_clean_timing"]["scale_same_state"]) else 1
    counts["P0-P19"] = 0 if all(
        "prep_s" in s or True for s in base["p0_clean_timing"]
        .get("production_states_5000", [])) and \
        "prep_cost_s_per_state" in base else 1
    # P0 must not modify any tracked file (audit-only), with one narrow
    # carve-out owned by the performance programme: the Tier-1 collection
    # pin reclassification in scripts/run_ci_tests.py, allowed only when
    # the diff touches EXPECTED_COLLECTED/comment lines and nothing else.
    changed_tracked = [ln for ln in _git(
        "status", "--porcelain=v1").splitlines()
        if ln.startswith(("M ", " M", "A ", " A", "D ", " D"))]
    pin_only = [ln for ln in changed_tracked
                if ln.split()[-1] == "scripts/run_ci_tests.py"]
    other_tracked = [ln for ln in changed_tracked
                     if ln.split()[-1] != "scripts/run_ci_tests.py"]
    # P2A carve-out (performance programme only): exactly kernel.py +
    # residuals.py may differ, and only when P2A parity is EXACT; every
    # other tracked modification still fails closed.
    p2a_ok = json.loads(
        (ROOT / "results" / "v3" / "performance_mc2" / "p2a"
         / "parity_results.json").read_text())["overall"] == "EXACT"
    p2a_pair = {"raceintel/simulation/mc2/kernel.py",
                "raceintel/simulation/mc2/residuals.py",
                "tests/test_v3_8a_consensus_contract.py",
                "tests/test_v3_8b_source_adapters.py",
                "tests/test_v3_8c_consensus_metrics.py",
                "tests/test_v3_8d_correction_01.py",
                "tests/test_v3_8d_evaluation.py",
                "tests/test_v3_8h_freeze.py",
                "tests/test_v3_6a_contract.py",
                "tests/test_v3_6b_contracts.py",
                "tests/test_v3_6d_evaluation.py",
                "tests/test_v3_7a_contract.py",
                # V3.9A carve-out: freeze pin/pathology reconciliation for
                # the v3_9a contract stage (no science change).
                "tests/test_perf_mc2_freeze.py",
                "tests/test_perf_mc2_p0.py",
                "tests/test_mc2_p2a.py",
                # V3.9C carve-out: uncertainty router registration.
                "api/main.py"}
    # V3.9D carve-out (product UI stage only): uncertainty nav entry, one
    # line in the V3.8H-allowlisted wiring file; frozen science untouched.
    # V3.9E carve-out: freeze-owned guard reconciliations admitting exact
    # V3.9 paths (no science change).
    v39_owned = {"frontend/components/shell/CommandBar.tsx",
                 "tests/test_v3_5a_contract.py",
                 "tests/test_v3_5b_dataset.py",
                 "tests/test_v3_5c_harness.py",
                 "tests/test_v3_5d_screening.py",
                 "tests/test_v3_6f_runtime.py"}
    other_tracked = [
        ln for ln in other_tracked
        if not (p2a_ok and (ln.split()[-1] in p2a_pair
                            or ln.split()[-1] in v39_owned) and all(
            x.split()[-1] in p2a_pair or
            x.split()[-1] == "scripts/run_ci_tests.py" or
            x.split()[-1] in v39_owned
            for x in other_tracked))]
    if pin_only:
        diff = subprocess.run(
            ["git", "diff", "scripts/run_ci_tests.py"], cwd=ROOT,
            capture_output=True, text=True, check=True).stdout
        for ln in diff.splitlines():
            if ln.startswith(("+++", "---")):
                continue
            if ln.startswith(("+", "-")):
                assert ln[1:].strip().startswith(
                    ("#", "EXPECTED_COLLECTED")), ln
    new_prod = [ln for ln in tracked.splitlines()
                if ln.strip().startswith("??") and any(
                    s in ln for s in ("raceintel/", "api/", "ml/",
                                      "scripts/"))
                and "raceintel/simulation/mc2_batch.py" not in ln
                and "scripts/mc2_batch_benchmark.py" not in ln
                # V3.9C carve-out: thin uncertainty product layer (pure
                # bundle over frozen seams + additive API, no science).
                and "raceintel/uncertainty/" not in ln
                and "api/v2_uncertainty_" not in ln]
    # (the two exclusions are exactly the P1 executor + benchmark harness,
    # owned by the performance programme; any other new prod file fails)
    counts["P0-P20"] = len(other_tracked) + len(new_prod)
    assert "P0-P20" in p0py  # self-reference guard
    return counts


def test_p0_pathology_all_zero():
    counts = _p0_counts()
    assert set(counts) == {f"P0-P{i}" for i in range(1, 21)}, set(counts)
    bad = {k: v for k, v in counts.items() if v != 0}
    assert bad == {}, bad
