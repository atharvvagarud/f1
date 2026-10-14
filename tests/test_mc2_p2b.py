"""P2B exact-order event-queue tests.

Proves the heap queue reproduces the legacy event-selection order
exactly: queue-level contract (ordinary/ties/insertion/reschedule/
failure/fuzz), instrumented live event-trace parity, small-live full
output parity, RNG identity, production canonical parity (via committed
artifacts, not 5000-future reruns), P1 compatibility, interpolation
untouched, frozen V3.8 provenance, and P2B-P1..P30 all zero.
"""

import hashlib
import heapq
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
P2B = ROOT / "results" / "v3" / "performance_mc2" / "p2b"
P0 = ROOT / "results" / "v3" / "performance_mc2" / "p0"
FROZEN_COMMIT = "15df86b864fa552c69c4b7a53e22f1fc3b4c4ca1"
FROZEN_TAG = "v3.8-model-simulation-consensus"

KERNEL_SRC = (ROOT / "raceintel" / "simulation" / "mc2"
              / "kernel.py").read_text()
LEGACY_SRC = (P2B / "legacy_kernel_p2a.py").read_text()

CORPUS = (ROOT / "data" / "v2" / "processed" / "results"
          / "season=2022" / "results__2022-r03-R.parquet")
needs_corpus = pytest.mark.skipif(
    not CORPUS.is_file(), reason="P2B live check needs ignored corpus")

STREAM_20240101_0 = [0.4264310906450923, 0.043876576516119314,
                     0.27832263913693145, 0.6992035439645221,
                     0.697574940730745]

FINISH = "FINISH"
FAIL = "FAIL"


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def _load(path):
    return json.loads(Path(path).read_text())


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


# --- queue-level selection transcriptions ---


def _legacy_select(init, reschedule):
    """Verbatim transcription of the pre-P2B selection block
    (kernel L350-367 as saved in legacy_kernel_p2a.py)."""
    assert "pending = {did: v for did, v in nxt.items()" in LEGACY_SRC
    assert "event_t = min(v[0] for v in pending.values())" in LEGACY_SRC
    assert "batch = sorted(did for did, v in pending.items()" in LEGACY_SRC
    nxt = dict(init)
    finished = {}
    seq = []
    ok = True
    steps = 0
    while ok and len(finished) < len(init) and steps <= 10_000_000:
        steps += 1
        pending = {did: v for did, v in nxt.items()
                   if did not in finished}
        if not pending:
            break
        event_t = min(v[0] for v in pending.values())
        batch = sorted(did for did, v in pending.items()
                       if v[0] == event_t)
        for did in batch:
            t, nl, na = nxt.pop(did)
            seq.append((t, did))
            out = reschedule(did, t, nl, na)
            if out == FINISH:
                finished[did] = t
            elif out == FAIL:
                ok = False
                break
            else:
                nxt[did] = out
    return seq, ok, finished


def _heap_select(init, reschedule):
    """Heap selection mirroring the P2B kernel implementation."""
    assert "heapq.heappop(heap)" in KERNEL_SRC
    assert "while heap and heap[0][0] == event_t:" in KERNEL_SRC
    heap = [(v[0], did, v[1], v[2]) for did, v in init.items()]
    heapq.heapify(heap)
    finished = {}
    seq = []
    ok = True
    steps = 0
    while ok and len(finished) < len(init) and steps <= 10_000_000:
        steps += 1
        if not heap:
            break
        event_t = heap[0][0]
        batch = []
        while heap and heap[0][0] == event_t:
            batch.append(heapq.heappop(heap))
        for t, did, nl, na in batch:
            seq.append((t, did))
            out = reschedule(did, t, nl, na)
            if out == FINISH:
                finished[did] = t
            elif out == FAIL:
                ok = False
                break
            else:
                heapq.heappush(heap, (out[0], did, out[1], out[2]))
    return seq, ok, finished


def _chain(did, t, nl, na):
    if nl >= 4:
        return FINISH
    return (t + 10.0, nl + 1, na + 1)


CASES = [
    ("unequal", {"A": (30.0, 2, 2), "B": (10.0, 2, 2),
                 "C": (20.0, 2, 2)}, lambda d, t, nl, na: FINISH),
    ("tie2-AB", {"A": (10.0, 2, 2), "B": (10.0, 2, 2)},
     lambda d, t, nl, na: FINISH),
    ("tie2-BA", {"B": (10.0, 2, 2), "A": (10.0, 2, 2)},
     lambda d, t, nl, na: FINISH),
    ("tie3", {"C": (5.0, 2, 2), "A": (5.0, 2, 2), "B": (5.0, 2, 2)},
     lambda d, t, nl, na: FINISH),
    ("chain-ties", {"B": (10.0, 2, 2), "A": (10.0, 2, 2)}, _chain),
    ("mixed", {"D": (7.5, 2, 2), "A": (5.0, 2, 2), "C": (5.0, 3, 3),
               "B": (9.0, 2, 2)}, lambda d, t, nl, na: FINISH),
]


def test_legacy_tie_rule_is_driver_id_not_insertion():
    a = _legacy_select({"B": (10.0, 2, 2), "A": (10.0, 2, 2)},
                       lambda d, t, nl, na: FINISH)
    # B inserted first, yet A processes first: explicit driver_id sort,
    # not insertion order. The heap key must (and does) reproduce this.
    assert [d for _, d in a[0]] == ["A", "B"]
    b = _heap_select({"B": (10.0, 2, 2), "A": (10.0, 2, 2)},
                     lambda d, t, nl, na: FINISH)
    assert a == b


def test_queue_scripted_cases_exact():
    for name, init, rs in CASES:
        assert _legacy_select(dict(init), rs) == \
            _heap_select(dict(init), rs), name
    # hypothetical same-stamp reschedule: frozen batch wins in both
    def same_stamp(did, t, nl, na):
        if did == "A" and nl == 2:
            return (10.0, 3, 3)
        return FINISH
    init = {"A": (10.0, 2, 2), "B": (10.0, 2, 2)}
    assert _legacy_select(dict(init), same_stamp) == \
        _heap_select(dict(init), same_stamp)
    # mid-batch failure: trailing batch event never processes, in both
    def fail_a(did, t, nl, na):
        return FAIL if did == "A" else FINISH
    assert _legacy_select(dict(init), fail_a) == \
        _heap_select(dict(init), fail_a)


def test_queue_fuzz_exact():
    import random
    dids = ["A", "B", "C", "D", "E"]
    pool = [1.0, 1.0, 2.5, 2.5, 2.5, 5.0, 7.0, 10.0, 0.5, 3.0]
    for i in range(1500):
        seed = 1000000 + i
        r0 = random.Random(seed + 777)
        order = dids[:]
        r0.shuffle(order)
        init = {d: (r0.choice(pool), 2, 2) for d in order}

        def mk(s):
            r = random.Random(s)

            def rs(did, t, nl, na):
                x = r.random()
                if nl >= 5:
                    return FINISH
                if x < 0.05:
                    return FAIL
                if x < 0.15:
                    return (t, nl + 1, na + 1)
                return (t + r.choice(pool), nl + 1, na + 1)
            return rs

        assert _legacy_select(dict(init), mk(seed)) == \
            _heap_select(dict(init), mk(seed)), i


def test_heap_invariant_no_stale_entries():
    import heapq as _hq
    real_push, real_pop = _hq.heappush, _hq.heappop
    stat = {"maxlen": 0, "push": 0, "pop": 0}

    def push(h, x):
        r = real_push(h, x)
        stat["push"] += 1
        stat["maxlen"] = max(stat["maxlen"], len(h))
        return r

    def pop(h):
        stat["pop"] += 1
        return real_pop(h)

    _hq.heappush, _hq.heappop = push, pop
    try:
        _prep, kw = _small_prep("2022-r03-R", 39, 2021, sims=6)
        from raceintel.simulation.mc2.kernel import run_mc2
        out = run_mc2(*_prep, **kw)
    finally:
        _hq.heappush, _hq.heappop = real_push, real_pop
    assert out["valid"] == 6
    assert stat["push"] == stat["pop"]  # every push popped exactly once
    assert stat["maxlen"] <= 20  # bounded by field size; no growth


def _small_prep(race_id, frame, through, sims=6):
    sys.path.insert(0, str(ROOT / "scripts"))
    import run_v3_2e_backtest as B2E
    from dataclasses import replace
    from raceintel.simulation.mc2.variance import (
        RegimeStat, select_variance)
    from raceintel.simulation.params import (
        load_simulation_parameters, parameter_storage_dir)
    params = load_simulation_parameters(
        parameter_storage_dir(ROOT, through))
    import pandas as pd
    res = pd.read_parquet(
        str(ROOT / "data" / "v2" / "processed" / "results"
            / f"season={int(race_id[:4])}"
            / f"results__{race_id}.parquet"))
    grid = B2E._grid_map(res)
    prep = B2E._prepare_state_and_mechanisms(race_id, frame, params, grid)
    sim_state, selection, sampler, mechanisms, _ = prep
    resid = params.family("lap_residual_distribution_s")
    era_e = resid.entries.get(selection.era)
    g_e = resid.entries.get("global")
    sel = select_variance({
        "era": RegimeStat(float(era_e.std or 1.5), era_e.sample_count)
        if era_e and era_e.std else None,
        "global": RegimeStat(float(g_e.std or 1.5), g_e.sample_count)
        if g_e and g_e.std else None})
    mechs = {did: replace(m, regime_std_s=sel.std_s, rho=0.264,
                          ar1_enabled=True)
             for did, m in mechanisms.items()}
    return ((sim_state, selection, sampler, mechs),
            {"arm": "E_AR1_RESIDUAL", "master_seed": 20240101,
             "simulation_count": sims})


def _load_kernel_from_source(path, modname, anchor, trace_line):
    src = Path(path).read_text()
    assert "_trace" not in src
    assert anchor in src
    src = src.replace(
        "    for sim_id in range(simulation_count):\n",
        "    for sim_id in range(simulation_count):\n"
        "        _sim_id = sim_id\n", 1)
    src = src.replace(anchor, anchor + trace_line, 1)
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix=".py")
    import os
    with os.fdopen(fd, "w") as fh:
        fh.write("from __future__ import annotations\n_trace = []\n"
                 "_sim_id = -1\n"
                 + src.replace(
                     "from __future__ import annotations\n", "", 1))
    spec = importlib.util.spec_from_file_location(modname, tmp)
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "raceintel.simulation.mc2"
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    os.unlink(tmp)
    return mod


@needs_corpus
def test_event_trace_exact_parity_live():
    legacy = _load_kernel_from_source(
        P2B / "legacy_kernel_p2a.py", "p2b_test_legacy",
        "                t, nl, na = nxt.pop(did)\n",
        "                _trace.append((_sim_id, t, did))\n")
    new = _load_kernel_from_source(
        ROOT / "raceintel" / "simulation" / "mc2" / "kernel.py",
        "p2b_test_new",
        "            for t, did, nl, na in batch:\n",
        "                _trace.append((_sim_id, t, did))\n")
    events = []
    for mod in (legacy, new):
        mod._trace.clear()
        args, kw = _small_prep("2022-r03-R", 39, 2021, sims=6)
        out = mod.run_mc2(*args, **kw)
        assert out["valid"] == 6
        events.append([(s, float(t).hex(), d)
                       for s, t, d in mod._trace])
    assert events[0] == events[1]
    assert len(events[0]) > 6000  # ~1120 events/sim; non-trivial trace


@needs_corpus
def test_small_live_full_output_parity():
    spec = importlib.util.spec_from_file_location(
        "p2b_parity_legacy", str(P2B / "legacy_kernel_p2a.py"))
    legacy = importlib.util.module_from_spec(spec)
    legacy.__package__ = "raceintel.simulation.mc2"
    sys.modules["p2b_parity_legacy"] = legacy
    spec.loader.exec_module(legacy)
    from raceintel.simulation.mc2.kernel import run_mc2 as new
    for race_id, frame, through in (("2022-r03-R", 39, 2021),
                                    ("2023-r21-R", 40, 2021)):
        args, kw = _small_prep(race_id, frame, through, sims=10)
        assert json.dumps(legacy.run_mc2(*args, **kw), sort_keys=True,
                          default=str) == json.dumps(
            new(*args, **kw), sort_keys=True, default=str)


def test_rng_stream_identity_unchanged():
    from raceintel.simulation.mc2.residuals import mc2_stream
    assert list(mc2_stream(20240101, 0).random(5)) == STREAM_20240101_0
    assert "rng.random(bound)" in KERNEL_SRC
    assert KERNEL_SRC.count("cursor += 1") == 1


def test_interpolation_untouched_no_vectorization():
    assert "np.interp" in KERNEL_SRC
    for tok in ("reshape", "vecdot", "ThreadPool", "threading",
                "ProcessPool", "concurrent.futures", ".sample(",
                "global "):
        assert tok not in KERNEL_SRC, tok
    import inspect
    from raceintel.simulation.mc2.kernel import run_mc2
    sig = inspect.signature(run_mc2)
    assert sig.parameters["master_seed"].default == 20240101
    assert sig.parameters["simulation_count"].default == 100
    assert "chunk_size" in sig.parameters


def test_production_parity_artifacts_exact():
    parity = _load(P2B / "production_parity.json")
    assert parity["overall"] == "EXACT"
    fix = {f["label"]: f
           for f in _load(P0 / "baseline_fixtures.json")["fixtures"]}
    final = _load(P2B / "final_benchmark.json")
    assert final["config"]["simulation_count"] == 5000
    for r in final["reps"]:
        for k, h in r["hashes"].items():
            assert h == fix[r["label"]]["hashes"][k], (r["label"], k)
    qp = _load(P2B / "queue_parity.json")
    assert qp["live_event_trace"]["exact"] is True
    assert qp["small_live_full_output"]["exact"] is True


def test_p1_compatibility_artifacts():
    compat = _load(P2B / "p1_compatibility.json")
    assert compat["smoke"]["serial_eq_w1_eq_w2_eq_w4"] is True
    assert compat["production_5000_executor_vs_fixture"] is True
    from raceintel.simulation.mc2_batch import Mc2StateTask as T
    assert T("r", 0, 2021).simulation_count == 5000


def test_frozen_v38_provenance():
    assert _git("rev-list", "-n", "1", FROZEN_TAG) == FROZEN_COMMIT
    # Freeze-tolerant: V3.8 commit must be an ancestor of HEAD (passes at
    # V3.8 HEAD and at the mc2-performance freeze descendant; fails on
    # history rewrite or tag move). Strict HEAD== would break the freeze.
    out = _git("merge-base", "--is-ancestor", FROZEN_COMMIT, "HEAD")
    assert out == ""


def test_p2b_card_identity():
    card = _load(P2B / "p2b_card.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident
    assert card["verdict"].startswith("MC2 PERFORMANCE P2B COMPLETE")
    for name in card["artifacts"]:
        assert (P2B / name).is_file(), name


# --- P2B-P1..P2B-P30 ---


def _p2b_counts():
    counts = {}
    status = _git("status", "--porcelain=v1").splitlines()
    dirty = [ln for ln in status if ln.strip()]
    diff = _git("diff", "--name-only").splitlines()
    counts["P2B-P1"] = 0 if _git(
        "rev-list", "-n", "1", FROZEN_TAG) == FROZEN_COMMIT else 1
    counts["P2B-P2"] = sum(
        1 for ln in dirty if "results/v3/v3_8" in ln or "docs/V3_8" in ln)
    from raceintel.simulation.mc2_batch import Mc2StateTask as T
    counts["P2B-P3"] = 0 if T("r", 0, 2021).simulation_count == 5000 else 1
    counts["P2B-P4"] = 0 if T("r", 0, 2021).master_seed == 20240101 else 1
    from raceintel.simulation.mc2.residuals import mc2_stream
    counts["P2B-P5"] = 0 if list(
        mc2_stream(20240101, 0).random(5)) == STREAM_20240101_0 else 1
    counts["P2B-P5"] += 0 if "rng.random(bound)" in KERNEL_SRC else 1
    counts["P2B-P6"] = 0 if KERNEL_SRC.count("cursor += 1") == 1 else 1
    counts["P2B-P7"] = 0 if _load(
        P2B / "production_parity.json")["overall"] == "EXACT" else 1
    counts["P2B-P8"] = 0 if _load(
        P2B / "queue_parity.json")["live_event_trace"]["exact"] is True \
        else 1
    counts["P2B-P9"] = 0 if _load(
        P2B / "tie_case_validation.json")["fuzz"]["mismatches"] == 0 \
        else 1
    counts["P2B-P10"] = 0 if "heapq.heappush" in KERNEL_SRC and \
        "pending = {did" not in KERNEL_SRC else 1
    # no invented driver-id rule: heap key is (time, driver_id), the exact
    # legacy tie-break proven by tie2-BA (insertion order irrelevant)
    counts["P2B-P11"] = 0 if "heap[0][0] == event_t" in KERNEL_SRC else 1
    # no timestamp rounding/epsilon: exact == on raw floats only
    body = KERNEL_SRC.split("def run_mc2")[1]
    counts["P2B-P12"] = (0 if ("round(" not in body
                               and "1e-9" not in body
                               and "abs(" not in body
                               and "heap[0][0] == event_t" in body)
                         else 1)
    counts["P2B-P13"] = 0 if "heappop" in KERNEL_SRC and \
        _load(P2B / "heap_design.json")["stale_entry_handling"] \
        .startswith("stale entries are impossible") else 1
    counts["P2B-P14"] = counts["P2B-P7"]  # skipped live event == parity fail
    counts["P2B-P15"] = counts["P2B-P7"]  # retirement: no DNF queue exists
    counts["P2B-P16"] = counts["P2B-P7"]  # terminal: finished never pushed
    counts["P2B-P17"] = 0 if _load(
        P2B / "heap_design.json")["heap_growth"][
            "max_heap_entries_measured"] <= 20 else 1
    counts["P2B-P18"] = 0 if _load(
        P0 / "baseline_fixtures.json")["fixtures"][0]["valid"] == 5000 \
        else 1
    counts["P2B-P19"] = 0 if "temporal_poison_blacklist" in _load(
        ROOT / "results" / "v3" / "v3_8a" / "consensus_contract.json") \
        else 1
    try:
        from raceintel.consensus import product as _P
        _P.compose(race_id="2025-r01-R", lap_number=1, state_time_s=None,
                   stage="EARLY", season=2025, model_probs={"a": 0.5},
                   simulation_probs={"a": 0.5}, valid_trials={"a": 5})
        counts["P2B-P20"] = 1
    except ValueError:
        counts["P2B-P20"] = 0
    counts["P2B-P21"] = 0 if "np.interp" in KERNEL_SRC else 1
    counts["P2B-P22"] = sum(
        1 for t in ("reshape", "vecdot") if t in KERNEL_SRC)
    counts["P2B-P23"] = sum(
        1 for t in ("ProcessPool", "concurrent.futures") if t in KERNEL_SRC)
    counts["P2B-P24"] = sum(
        1 for t in ("ThreadPool", "threading") if t in KERNEL_SRC)
    counts["P2B-P25"] = 0 if _load(
        P2B / "p1_compatibility.json")["smoke"][
            "serial_eq_w1_eq_w2_eq_w4"] is True else 1
    counts["P2B-P26"] = sum(
        1 for ln in dirty if "mc2_checkpoint" in ln)
    api_blob = "".join(
        (ROOT / f).read_text() for f in (
            "api/v2_consensus_routes.py", "api/v2_consensus_schemas.py",
            "api/v2_consensus_service.py"))
    counts["P2B-P27"] = sum(
        1 for t in ("heapq", "mc2_batch", "workers") if t in api_blob)
    strat = [ln for ln in dirty if "raceintel/strategy" in ln
             or "counterfactual" in ln]
    # V3.10I reconciliation (freeze): the single admitted frontend
    # path below is the G expert-prefill edit (presentation only;
    # raceintel/strategy science untouched — verified zero diff).
    strat = [ln for ln in strat
             if "frontend/features/counterfactuals/components/CounterfactualView.tsx" not in ln]
    counts["P2B-P28"] = len(strat)
    base = _load(P2B / "baseline_benchmark.json")
    final = _load(P2B / "final_benchmark.json")
    counts["P2B-P29"] = 0 if sorted(
        {r["label"] for r in base["reps"]}) == sorted(
        {r["label"] for r in final["reps"]}) and \
        base["config"]["simulation_count"] == 5000 and \
        final["config"]["simulation_count"] == 5000 else 1
    counts["P2B-P30"] = 0 if _load(
        P2B / "queue_parity.json")["live_event_trace"]["exact"] is True \
        and _load(P2B / "production_parity.json")["overall"] == "EXACT" \
        else 1
    return counts


def test_p2b_pathology_all_zero():
    counts = _p2b_counts()
    assert set(counts) == {f"P2B-P{i}" for i in range(1, 31)}, set(counts)
    bad = {k: v for k, v in counts.items() if v != 0}
    assert bad == {}, bad
