"""P1 deterministic state-level multiprocessing tests.

Fast unit/audit checks plus small corpus-guarded live parity smoke tests.
Production-scale proof lives in results/v3/performance_mc2/p1/ artifacts
(asserted here without rerunning). P1 adds no kernel changes.
"""

import hashlib
import json
import pickle
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
P1 = ROOT / "results" / "v3" / "performance_mc2" / "p1"
P0 = ROOT / "results" / "v3" / "performance_mc2" / "p0"
FROZEN_COMMIT = "15df86b864fa552c69c4b7a53e22f1fc3b4c4ca1"
FROZEN_TAG = "v3.8-model-simulation-consensus"

CORPUS = (ROOT / "data" / "v2" / "processed" / "results"
          / "season=2022" / "results__2022-r03-R.parquet")
needs_corpus = pytest.mark.skipif(
    not CORPUS.is_file(), reason="P1 live check needs ignored corpus")

BATCH_SRC = (ROOT / "raceintel" / "simulation" / "mc2_batch.py").read_text()


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def _load(path):
    return json.loads(Path(path).read_text())


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


# --- identity / contracts ---


def test_task_identity_exact():
    from raceintel.simulation.mc2_batch import Mc2StateTask

    t = Mc2StateTask("2022-r03-R", 39, 2021)
    assert t.key() == ("2022-r03-R", 39)
    assert t.simulation_count == 5000
    assert t.master_seed == 20240101
    assert t.rho == 0.264
    assert Mc2StateTask.from_dict(t.to_dict()) == t
    assert pickle.loads(pickle.dumps(t)) == t  # spawn requirement


def test_task_identity_rejects_reduction():
    from raceintel.simulation.mc2_batch import Mc2StateTask, run_batch

    with pytest.raises(ValueError):
        run_batch([], workers=1)
    with pytest.raises(ValueError):
        run_batch([Mc2StateTask("2022-r03-R", 39, 2021)], workers=0)
    with pytest.raises(ValueError):
        run_batch([Mc2StateTask("2022-r03-R", -1, 2021)], workers=1)


def test_default_worker_policy():
    from raceintel.simulation.mc2_batch import MAX_WORKERS, default_workers

    assert MAX_WORKERS == 8
    assert default_workers(100) <= 8
    assert default_workers(1) == 1
    assert default_workers(0) == 1


def test_stamp_matching():
    from raceintel.simulation.mc2_batch import (
        _stamp_matches,
        Mc2StateTask,
    )

    t = Mc2StateTask("2022-r03-R", 39, 2021)
    good = {"executor_version": "mc2-batch-v1",
            "config_stamp": {"arm": "E_AR1_RESIDUAL",
                             "master_seed": 20240101,
                             "simulation_count": 5000, "rho": 0.264}}
    assert _stamp_matches(good, t) is True
    bad = {"executor_version": "mc2-batch-v1",
           "config_stamp": {"arm": "E_AR1_RESIDUAL",
                            "master_seed": 1,
                            "simulation_count": 5000, "rho": 0.264}}
    assert _stamp_matches(bad, t) is False


def test_no_worker_specific_rng():
    for token in ("getpid", "worker_id", "worker_index", "time.time(",
                  "task_index", "submit_index"):
        assert token not in BATCH_SRC, token
    assert "perf_counter" in BATCH_SRC  # timing only, never seeds


def test_single_pool_no_threads_no_nesting():
    assert BATCH_SRC.count("ProcessPoolExecutor") == 1
    assert "ThreadPool" not in BATCH_SRC
    assert "spawn" in BATCH_SRC
    assert "with concurrent.futures.ProcessPoolExecutor" in BATCH_SRC


def test_parent_only_checkpoint_writing():
    assert BATCH_SRC.count("_atomic_write_json(") >= 2  # def + call
    worker_fn = BATCH_SRC.split("def execute_state_task")[1].split(
        "# --- parent side ---")[0]
    assert "checkpoint_path" not in worker_fn
    assert "os.replace" not in worker_fn
    assert "sorted(store" in BATCH_SRC  # canonical parent assembly


def test_no_public_worker_controls():
    for rel in ("api/v2_consensus_routes.py",
                "api/v2_consensus_schemas.py",
                "api/v2_consensus_service.py"):
        text = (ROOT / rel).read_text()
        assert "workers" not in text and "mc2_batch" not in text, rel


def test_frozen_v38_provenance():
    assert _git("rev-list", "-n", "1", FROZEN_TAG) == FROZEN_COMMIT
    out = _git("merge-base", "--is-ancestor", FROZEN_COMMIT, "HEAD")
    assert out == ""


# --- live smoke (small, corpus-guarded) ---


@needs_corpus
def test_executor_w1_vs_w2_small(tmp_path):
    from raceintel.simulation.mc2_batch import Mc2StateTask, run_batch

    tasks = [Mc2StateTask("2022-r03-R", 39, 2021, simulation_count=30),
             Mc2StateTask("2022-r03-R", 30, 2021, simulation_count=30)]
    s1 = run_batch(tasks, workers=1,
                   checkpoint_path=str(tmp_path / "c1.json"))
    s2 = run_batch(tasks, workers=2,
                   checkpoint_path=str(tmp_path / "c2.json"))
    assert s1["n_complete"] == s2["n_complete"] == 2
    assert s1["n_failed"] == s2["n_failed"] == 0
    h1 = _canon([(e["winner_counts"], e["valid"]) for e in s1["results"]])
    h2 = _canon([(e["winner_counts"], e["valid"]) for e in s2["results"]])
    assert hashlib.sha256(h1).hexdigest() == \
        hashlib.sha256(h2).hexdigest()
    assert [e["task"]["frame_index"] for e in s1["results"]] == [30, 39]
    assert (tmp_path / "c1.json").is_file()


@needs_corpus
def test_refusal_is_typed_not_fabricated(tmp_path):
    from raceintel.simulation.mc2_batch import Mc2StateTask, run_batch

    tasks = [Mc2StateTask("2022-r03-R", 39, 2021, simulation_count=10),
             Mc2StateTask("2022-r03-R", 999999, 2021, simulation_count=10)]
    s = run_batch(tasks, workers=2,
                  checkpoint_path=str(tmp_path / "c.json"))
    assert s["n_complete"] == 1 and s["n_refused"] == 1
    assert s["n_failed"] == 0
    refused = [e for e in s["results"] if e["status"] == "refused"]
    assert refused and refused[0]["reason"] in (
        "PREP_REFUSAL", "ZERO_VALID_TRIALS")
    assert "winner_counts" not in refused[0]


@needs_corpus
def test_unexpected_worker_error_raises(tmp_path):
    from unittest.mock import patch

    from raceintel.simulation import mc2_batch as B
    from raceintel.simulation.mc2_batch import (
        Mc2BatchError,
        Mc2StateTask,
        execute_state_task,
    )

    with pytest.raises(Exception):
        execute_state_task({})  # malformed task: raises, never fabricates
    with pytest.raises(ValueError):
        B.run_batch([Mc2StateTask("2022-r03-R", 39, 2021,
                                  simulation_count=0)], workers=1)

    class _BoomFuture:
        def result(self):
            raise RuntimeError("synthetic worker crash")

    class _Pool:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def submit(self, fn, arg):
            return _BoomFuture()

    with patch.object(B.concurrent.futures, "ProcessPoolExecutor",
                      _Pool), \
         patch.object(B.concurrent.futures, "as_completed",
                      lambda fns: list(fns)):
        with pytest.raises(Mc2BatchError):
            B.run_batch([Mc2StateTask("2022-r03-R", 39, 2021,
                                      simulation_count=10)], workers=2)


# --- production-scale proof artifacts (asserted, not rerun) ---


def test_production_parity_artifacts():
    parity = _load(P1 / "parity_results.json")["parity"]
    assert parity["p0_fixtures_match"] is True
    assert parity["direct_serial_match"] is True
    assert parity["all_identical"] is True
    for w in ("1", "2", "4", "6", "8"):
        assert parity["cross_worker_identical"][w] is True


def test_benchmark_corpus_rule():
    corpus = _load(P1 / "benchmark_corpus.json")
    assert corpus["simulation_count"] == 5000
    assert len(corpus["states"]) >= 8
    ck = _load(ROOT / "results" / "v3" / "v3_8d"
               / "mc2_checkpoint.json")["mc2_out"]
    races = set()
    for c in corpus["states"]:
        races.add(c["race_id"])
        hit = [s for s, d in ck.items()
               if s == c["state_id"]
               and d["frame_index"] == c["frame_index"]]
        assert hit, c  # genuine frozen states only
    assert len(races) >= 4


def test_worker_matrix_equivalent_workloads():
    matrix = _load(P1 / "worker_matrix.json")["rows"]
    assert [r["workers"] for r in matrix] == [1, 2, 4, 6, 8]
    for row in matrix:
        assert row["futures_per_state"] == 5000
        assert row["states"] == matrix[0]["states"]
        assert row["speedup_vs_w1"] > 0 and row["efficiency"] > 0


def test_p1_card_identity():
    card = _load(P1 / "p1_card.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident


def test_collection_guard_reconciled():
    import re
    import sys as _sys

    text = (ROOT / "scripts" / "run_ci_tests.py").read_text()
    m = re.search(r"EXPECTED_COLLECTED\s*=\s*(\d+)", text)
    assert m, "pin missing"
    proc = subprocess.run(
        [_sys.executable, "-m", "pytest", "tests/", "--collect-only",
         "-q", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=ROOT)
    last = proc.stdout.strip().splitlines()[-1]
    n = int(re.search(r"(\d+) tests collected", last).group(1))
    assert int(m.group(1)) == n


# --- P1-P1..P1-P30 ---


def _p1_counts():
    counts = {}
    status = _git("status", "--porcelain=v1").splitlines()
    dirty = [ln for ln in status if ln.strip()]
    frozen_hits = [ln for ln in dirty if any(
        s in ln for s in ("results/v3/v3_8", "docs/V3_8",
                          "raceintel/consensus", "api/v2_consensus",
                          "frontend/app/consensus",
                          "frontend/features/consensus"))]
    counts["P1-P1"] = 0 if _git(
        "rev-list", "-n", "1", FROZEN_TAG) == FROZEN_COMMIT else 1
    counts["P1-P2"] = len(frozen_hits)
    kernel_files = ("raceintel/simulation/mc2/kernel.py",
                    "raceintel/simulation/mc2/residuals.py",
                    "raceintel/simulation/mc2/dynamics.py",
                    "raceintel/simulation/mc2/variance.py",
                    "raceintel/simulation/rng.py",
                    "raceintel/simulation/engine.py",
                    "raceintel/simulation/monte_carlo.py",
                    "scripts/v3_8d_run.py",
                    "scripts/run_v3_2e_backtest.py",
                    "scripts/run_v3_2d_diagnostics.py")
    diff = _git("diff", "--name-only").splitlines()
    # P2A carve-out (performance programme only): exactly
    # kernel.py + residuals.py may differ, and only when P2A parity is
    # EXACT (checked below via the p2a artifact); every other kernel
    # file still fails closed.
    p2a_ok = _load(ROOT / "results" / "v3" / "performance_mc2" / "p2a"
                    / "parity_results.json")["overall"] == "EXACT"
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
                "tests/test_v3_7a_contract.py"}
    counts["P1-P3"] = sum(
        1 for f in diff
        if f in kernel_files and not (
            p2a_ok and f in p2a_pair
            and set(d for d in diff if d in kernel_files) <= p2a_pair))
    from raceintel.simulation.mc2_batch import Mc2StateTask as T

    counts["P1-P4"] = 0 if T("r", 0, 2021).simulation_count == 5000 else 1
    counts["P1-P5"] = 0 if T("r", 0, 2021).master_seed == 20240101 else 1
    counts["P1-P6"] = sum(
        1 for t in ("getpid", "worker_id", "time.time(") if t in BATCH_SRC)
    counts["P1-P7"] = 0 if "sorted(store" in BATCH_SRC else 1
    counts["P1-P8"] = 0 if BATCH_SRC.count("os.replace") == 1 else 1
    counts["P1-P9"] = 0 if "raise Mc2BatchError" in BATCH_SRC else 1
    counts["P1-P10"] = 0 if "incomplete batch" in BATCH_SRC else 1
    counts["P1-P11"] = 0 if "frame_index" in BATCH_SRC else 1
    dup = _load(P0 / "duplicate_work_audit.json")
    cross = [c for c in dup["candidates"]
             if c["item"].startswith("full-field run_mc2 across")]
    counts["P1-P12"] = 0 if cross and cross[0]["verdict"] == \
        "NOT_REUSABLE" else 1
    counts["P1-P13"] = sum(
        1 for t in ("target driver treated", "per-driver parallel")
        if t in BATCH_SRC.lower())
    import re as _re

    assert len(_re.findall(r"ProcessPoolExecutor", BATCH_SRC)) == 1
    counts["P1-P14"] = sum(
        1 for t in ("driver pool", "per-driver worker") if t in BATCH_SRC)
    counts["P1-P15"] = 0 if "no within-run future chunking" in BATCH_SRC \
        else 1
    counts["P1-P16"] = sum(
        1 for t in ("ThreadPool", "threading") if t in BATCH_SRC)
    matrix = _load(P1 / "worker_matrix.json")["rows"]
    counts["P1-P17"] = 0 if len({r["states"] for r in matrix}) == 1 else 1
    counts["P1-P18"] = sum(
        1 for r in matrix if r["futures_per_state"] != 5000)
    corpus = _load(P1 / "benchmark_corpus.json")["states"]
    ck = _load(ROOT / "results" / "v3" / "v3_8d"
               / "mc2_checkpoint.json")["mc2_out"]
    counts["P1-P19"] = sum(
        1 for c in corpus
        if c["state_id"] not in ck or ck[c["state_id"]]["frame_index"]
        != c["frame_index"])
    parity = _load(P1 / "parity_results.json")["parity"]
    counts["P1-P20"] = 0 if parity["all_identical"] is True else 1
    counts["P1-P21"] = sum(
        1 for v in parity["cross_worker_identical"].values()
        if v is not True)
    api_blob = "".join(
        (ROOT / f).read_text() for f in (
            "api/v2_consensus_routes.py", "api/v2_consensus_schemas.py",
            "api/v2_consensus_service.py"))
    counts["P1-P22"] = sum(
        1 for t in ("workers", "mc2_batch", "max_workers")
        if t in api_blob)
    counts["P1-P23"] = 0 if BATCH_SRC.count(
        "ProcessPoolExecutor") == 1 else 1
    counts["P1-P24"] = 0 if "mkstemp" in BATCH_SRC and "os.replace" in \
        BATCH_SRC else 1
    strat = [ln for ln in dirty if "raceintel/strategy" in ln
             or "counterfactual" in ln]
    counts["P1-P25"] = len(strat)
    from raceintel.consensus import product as _P

    try:
        _P.compose(race_id="2025-r01-R", lap_number=1, state_time_s=None,
                   stage="EARLY", season=2025, model_probs={"a": 0.5},
                   simulation_probs={"a": 0.5}, valid_trials={"a": 5})
        counts["P1-P26"] = 1
    except ValueError:
        counts["P1-P26"] = 0
    counts["P1-P27"] = 0 if "temporal_poison_blacklist" in (
        ROOT / "results" / "v3" / "v3_8a"
        / "consensus_contract.json").read_text() else 1
    p0card = _load(P0 / "p0_card.json")
    ident = p0card.pop("card_identity")
    counts["P1-P28"] = 0 if hashlib.sha256(
        _canon(p0card)).hexdigest() == ident else 1
    text = (ROOT / "scripts" / "run_ci_tests.py").read_text()
    counts["P1-P29"] = 0 if "EXPECTED_COLLECTED" in text and \
        "KNOWN_STALE_NODE_IDS" in text else 1
    rows = matrix
    counts["P1-P30"] = 0 if all(
        r["speedup_vs_w1"] == round(rows[0]["wall_s"] / r["wall_s"], 3)
        for r in rows) else 1
    return counts


def test_p1_pathology_all_zero():
    counts = _p1_counts()
    assert set(counts) == {f"P1-P{i}" for i in range(1, 31)}, set(counts)
    bad = {k: v for k, v in counts.items() if v != 0}
    assert bad == {}, bad
