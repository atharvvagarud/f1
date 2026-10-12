"""V3.8E controlled fusion research tests (Tier A, deterministic).

Research-evaluation only: asserts frozen D-preflight reconciliation, exact
A/B/C/D provenance, the 277-row source identity set, temporal-prequential
integrity, convex-fusion arithmetic, sign conventions, race-level bootstrap
policy, pathology zeros, lineage exclusions, no-simulation-rerun, and
fusion-card/gate determinism. Never executes MC2 or retrains models.
"""

import hashlib
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_8d"
E = ROOT / "results" / "v3" / "v3_8e"
sys.path.insert(0, str(ROOT / "scripts"))

import v3_8e_run as RUN

EPS = 1e-15
EXTREME = "2023-r21-R|max_verstappen|3"


def _load(name, base=E):
    return json.loads((base / name).read_text())


def _proto():
    p = _load("fusion_protocol.json")
    ident = p.pop("protocol_identity")
    blob = json.dumps(p, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(blob).hexdigest() == ident
    p["protocol_identity"] = ident
    return p


def _d_rows():
    return json.loads((D / "per_row_records.json").read_text())


# --- D preflight arithmetic / sign reconciliation ---

def test_preflight_verdict_correctable_defect():
    a = _load("d_preflight_audit.json")
    assert a["verdict"] == "CORRECTABLE_D_ANALYSIS_DEFECT"
    assert "correction_01" in a["reconciliation_update"]


def test_preflight_advantage_sign_convention():
    a = _load("d_preflight_audit.json")
    assert a["definition"].startswith("advantage = ll_log - ll_mc2")
    better = [r["better"] for r in a["race_advantages"]]
    assert better.count("LOGISTIC") == 7
    assert better.count("MC2") == 1
    mc2 = next(r for r in a["race_advantages"]
               if r["better"] == "MC2")
    assert mc2["race_id"] == "2023-r05-R"
    assert mc2["stored_advantage"] > 0


def test_preflight_per_race_advantages_recompute():
    a = _load("d_preflight_audit.json")
    rows = _d_rows()

    def clip(p):
        return min(max(p, EPS), 1 - EPS)

    def ll(p, y):
        p = clip(p)
        return -(y * math.log(p) + (1 - y) * math.log(1 - p))

    by = {}
    for r in rows:
        by.setdefault(r["race_id"], []).append(r)
    for entry in a["race_advantages"]:
        rr = by[entry["race_id"]]
        ml = sum(ll(x["p_logistic"], x["target"]) for x in rr) / len(rr)
        mm = sum(ll(x["p_mc2"], x["target"]) for x in rr) / len(rr)
        assert abs((ml - mm) - entry["stored_advantage"]) < 1e-9
        assert abs(entry["recomputed_advantage"]
                   - entry["stored_advantage"]) < 1e-6


def test_preflight_bootstrap_reproduces_exactly():
    a = _load("d_preflight_audit.json")
    b = a["bootstrap_reproduction"]
    assert b["exact_match"] is True
    import numpy as np
    rows = _d_rows()
    by = {}
    for r in rows:
        by.setdefault(r["race_id"], []).append(r)
    # verbatim frozen D procedure: RandomState(987654321), race resample
    # with replacement, row-pooled mean of loss_advantage
    rng = np.random.RandomState(987654321)
    races = sorted(by)
    n = len(races)
    reps = []
    for _ in range(2000):
        picks = [races[i] for i in rng.randint(0, n, n)]
        ad = [x["loss_advantage"] for p in picks for x in by[p]]
        reps.append(sum(ad) / len(ad))
    assert abs(sum(reps) / len(reps) - b["mean_stored"]) < 1e-12
    s = sorted(reps)
    assert [s[int(0.025 * len(s))], s[int(0.975 * len(s))]] == \
        b["ci95_stored"]
    # negative mean favors Logistic under advantage = log - mc2
    assert b["mean_stored"] < 0


# --- provenance / population ---

def test_exact_abcd_identities():
    p = _proto()
    assert p["identities"]["a_contract"] == \
        "d0b8785a01347580125b38b311984c793c012352ce3ff175cfa3504379b9a67b"
    assert p["identities"]["b_contract"] == \
        "d212803f7ed7e8a8563abdd5b7686326e7094d810f415fa1468117541dfbfde7"
    assert p["identities"]["c_contract"] == \
        "07cf1ddd9708eaea2280b1d46492d972234f68c77cf3a59cbf412f638e3a74a8"
    assert p["identities"]["d_protocol"] == \
        "9cbe85de7c8f0553a098a9a03d016beed80159c785b566c312502d3bf10f2ed1"
    assert p["identities"]["d_card"] == \
        "523898b3d626a7c3baffd65d2c5c921983db361faeb3feb57a7f8984f2e137f9"


def test_protocol_identity_frozen():
    assert _proto()["protocol_identity"] == \
        "dbe6a565d5a6fa688dbb8e0b3a1be05bad71457777cd2e312f9c164219b128dd"


def test_source_identity_set_exact_277():
    d_ids = {r["state_id"] for r in _d_rows()}
    assert len(d_ids) == 277
    ev = _load("fusion_evaluation.json")
    assert ev["population"]["comparable_rows"] == 277
    assert ev["population"]["eval_rows"] == 216
    # eval rows are exactly the D rows of the 5 evaluation races
    eval_ids = {r["state_id"] for r in _d_rows()
                if r["race_id"] in ev["population"]["eval_races"]}
    assert len(eval_ids) == 216


def test_no_2025():
    rows = _d_rows()
    assert 2025 not in {r["season"] for r in rows}
    assert set(r["season"] for r in rows) <= {2022, 2023, 2024}


def test_no_final_fit():
    blob = json.dumps(_load("fusion_evaluation.json"))
    blob += json.dumps(_load("fusion_gate.json"))
    blob += json.dumps(_load("fusion_card.json"))
    blob += (ROOT / "scripts" / "v3_8e_run.py").read_text()
    assert "FINAL_FIT" not in blob
    assert "final_fit" not in blob


# --- temporal / prequential integrity ---

def test_chronology_ordering():
    p = _proto()
    assert p["chronology"] == [
        "2022-r03-R", "2022-r11-R", "2022-r19-R", "2023-r05-R",
        "2023-r13-R", "2023-r21-R", "2024-r07-R", "2024-r15-R"]
    ev = _load("fusion_evaluation.json")
    assert ev["population"]["eval_races"] == p["chronology"][3:]
    assert ev["population"]["warmup_races"] == p["chronology"][:3]


def test_expanding_window_split_construction():
    w = _load("prequential_weights.json")
    assert len(w) == 5
    for i, step in enumerate(w):
        assert step["history"] == _proto()["chronology"][:3 + i]
        assert step["race_id"] == _proto()["chronology"][3 + i]
        assert len(step["tuning_curve"]) == 11


def test_no_future_to_past_tuning():
    chrono = _proto()["chronology"]
    for step in _load("prequential_weights.json"):
        k = chrono.index(step["race_id"])
        for h in step["history"]:
            assert chrono.index(h) < k


def test_no_evaluation_race_self_tuning():
    for step in _load("prequential_weights.json"):
        assert step["race_id"] not in step["history"]


def test_no_random_row_split():
    text = (ROOT / "scripts" / "v3_8e_run.py").read_text()
    assert "shuffle" not in text
    assert "train_test_split" not in text
    for step in _load("prequential_weights.json"):
        assert isinstance(step["history"], list)


# --- fusion arithmetic ---

def test_alpha_grid_and_bounds():
    p = _proto()
    assert p["alpha_grid"] == [round(i / 10, 1) for i in range(11)]
    for step in _load("prequential_weights.json"):
        assert 0.0 <= step["selected_alpha"] <= 1.0
        assert step["selected_alpha"] in p["alpha_grid"]
        for a, _ in step["tuning_curve"]:
            assert a in p["alpha_grid"]


def test_deterministic_tie_break_largest_alpha():
    # synthetic exact tie must resolve to the largest alpha
    curve = [(a, 0.5) for a in [round(i / 10, 1) for i in range(11)]]
    best = min(v for _, v in curve)
    chosen = max(a for a, v in curve if v == best)
    assert chosen == 1.0
    # and every recorded step obeys the rule on its own curve
    for step in _load("prequential_weights.json"):
        curve = [(a, v) for a, v in step["tuning_curve"]]
        best = min(v for _, v in curve)
        assert step["selected_alpha"] == \
            max(a for a, v in curve if v == best)


def test_convex_fusion_arithmetic():
    assert RUN._fuse(0.3, 0.2, 0.8) == 0.3 * 0.2 + 0.7 * 0.8
    r = _d_rows()[0]
    a = 0.8
    assert abs(RUN._fuse(a, r["p_logistic"], r["p_mc2"])
               - (a * r["p_logistic"]
                  + (1 - a) * r["p_mc2"])) < 1e-15


def test_alpha_parity_endpoints():
    rows = _d_rows()
    for r in rows:
        assert RUN._fuse(1.0, r["p_logistic"], r["p_mc2"]) == \
            r["p_logistic"]
        assert RUN._fuse(0.0, r["p_logistic"], r["p_mc2"]) == r["p_mc2"]


def test_no_normalization():
    rows = _d_rows()
    by = {}
    for r in rows:
        by.setdefault(r["race_id"], []).append(r)
    # raw Logistic rows are independent-binary: race sums differ from 1
    sums = [sum(x["p_logistic"] for x in rr) for rr in by.values()]
    assert any(abs(s - 1.0) > 1e-6 for s in sums)
    # fused arm never race-normalized either: check one eval race sum
    amap = {w["race_id"]: w["selected_alpha"]
            for w in _load("prequential_weights.json")}
    rc = "2024-r07-R"
    s = sum(RUN._fuse(amap[rc], x["p_logistic"], x["p_mc2"])
            for x in by[rc])
    raw = sum(amap[rc] * x["p_logistic"] + (1 - amap[rc]) * x["p_mc2"]
              for x in by[rc])
    assert abs(s - raw) < 1e-12


def test_legitimate_mc2_zero_remains_zero():
    rows = _d_rows()
    zeros = [r for r in rows if r["p_mc2"] == 0.0]
    assert len(zeros) > 0  # simulated-but-winless natives exist
    # E reuses natives untouched: fused zero-input rows contribute
    # alpha * p_log exactly (no epsilon injected into natives)
    amap = {w["race_id"]: w["selected_alpha"]
            for w in _load("prequential_weights.json")}
    r = next(x for x in zeros if x["race_id"] in amap)
    assert RUN._fuse(amap[r["race_id"]], r["p_logistic"], 0.0) == \
        amap[r["race_id"]] * r["p_logistic"]


def test_unsupported_remains_unavailable():
    ev = _load("fusion_evaluation.json")
    assert ev["population"]["eval_rows"] == sum(
        e["n"] for e in _load("per_race_results.json"))
    d = json.loads((D / "historical_evaluation.json").read_text())
    assert (d["population"]["comparable_rows"]
            + d["population"]["excluded_rows"]
            == d["population"]["candidate_rows"] == 300)


def test_probability_finiteness_range():
    amap = {w["race_id"]: w["selected_alpha"]
            for w in _load("prequential_weights.json")}
    for r in _d_rows():
        if r["race_id"] not in amap:
            continue
        p = RUN._fuse(amap[r["race_id"]], r["p_logistic"], r["p_mc2"])
        assert math.isfinite(p) and 0.0 <= p <= 1.0


def test_row_order_invariance():
    rows = _d_rows()
    ev = _load("fusion_evaluation.json")
    amap = {w["race_id"]: w["selected_alpha"]
            for w in _load("prequential_weights.json")}

    def macro_ll(order):
        by = {}
        for r in order:
            by.setdefault(r["race_id"], []).append(r)
        means = []
        for rc in ev["population"]["eval_races"]:
            vals = [RUN._ll(RUN._fuse(amap[rc], x["p_logistic"],
                                      x["p_mc2"]), x["target"])
                    for x in by[rc]]
            means.append(sum(vals) / len(vals))
        return sum(means) / len(means)

    assert abs(macro_ll(rows) - macro_ll(list(reversed(rows)))) < 1e-15
    assert abs(macro_ll(rows) - ev["fusion"]["macro_ll"]) < 1e-12


def test_race_macro_aggregation():
    ev = _load("fusion_evaluation.json")
    per = _load("per_race_results.json")
    assert abs(sum(e["mean_ll_fused"] for e in per) / len(per)
               - ev["fusion"]["macro_ll"]) < 1e-12
    assert abs(sum(e["mean_ll_log"] for e in per) / len(per)
               - ev["controls"]["macro_ll_log"]) < 1e-12


# --- sign semantics ---

def test_loss_delta_sign_semantics_synthetic():
    # fusion better (lower loss) => negative delta by frozen convention
    assert (0.01 - 0.05) < 0
    ev = _load("fusion_evaluation.json")
    d = ev["deltas"]
    assert d["delta_fusion_vs_log_macro_ll"] == \
        ev["fusion"]["macro_ll"] - ev["controls"]["macro_ll_log"]
    assert d["delta_fusion_vs_mc2_macro_ll"] == \
        ev["fusion"]["macro_ll"] - ev["controls"]["macro_ll_mc2"]
    # stored primary outcome: worse than Logistic, better than MC2
    assert d["delta_fusion_vs_log_macro_ll"] > 0
    assert d["delta_fusion_vs_mc2_macro_ll"] < 0


# --- bootstrap ---

def test_race_level_bootstrap_deterministic_seed():
    p = _proto()
    assert p["bootstrap"]["unit"].startswith("evaluation race")
    assert p["bootstrap"]["B"] == 2000
    assert p["bootstrap"]["seed"] == 987654322
    assert p["bootstrap"]["level"] == 95
    # independently re-execute the frozen race-level procedure
    per = {e["race_id"]: e for e in _load("per_race_results.json")}
    races = _proto()["chronology"][3:]
    rng = random.Random(987654322)
    reps = []
    for _ in range(2000):
        picks = [races[rng.randrange(len(races))]
                 for _ in range(len(races))]
        f = sum(per[x]["mean_ll_fused"] for x in picks) / len(picks)
        m = sum(per[x]["mean_ll_mc2"] for x in picks) / len(picks)
        reps.append(f - m)
    ev = _load("fusion_evaluation.json")
    stored = ev["bootstrap"]["delta_fusion_vs_mc2_macro_ll"]
    assert abs(sum(reps) / len(reps) - stored["mean"]) < 1e-12
    s = sorted(reps)
    assert [s[int(0.025 * len(s))], s[int(0.975 * len(s))]] == \
        stored["ci95"]


def test_no_row_level_bootstrap():
    text = (ROOT / "scripts" / "v3_8e_run.py").read_text()
    assert "randrange(len(eval_races))" in text


# --- robustness / descriptive marking ---

def test_known_p0_row_retained_in_primary():
    ev = _load("fusion_evaluation.json")
    assert EXTREME in {r["state_id"] for r in _d_rows()
                       if r["race_id"] in ev["population"]["eval_races"]}
    rb = _load("robustness_analysis.json")
    assert rb["extreme_row"]["retained_in_primary"] is True
    assert rb["extreme_row"]["state_id"] == EXTREME
    assert rb["outlier_removed"]["scope"] == "EXPLORATORY_SENSITIVITY_ONLY"


def test_fixed_weight_curve_marked_descriptive():
    fw = _load("fixed_weight_curve.json")
    assert fw["scope"] == "REVEALED_DESCRIPTIVE_ONLY"
    assert fw["oracle"]["mark"] == "DESCRIPTIVE_ORACLE_WEIGHT"
    assert "deploy" not in json.dumps(fw).lower()


# --- lineage / exclusions ---

def test_v35_lineage_exclusion():
    p = _proto()
    assert "V3_5_P_WIN" in p["excluded_sources"]
    for name in ("fusion_evaluation.json", "fusion_gate.json",
                 "fusion_card.json", "per_race_results.json",
                 "prequential_weights.json", "fixed_weight_curve.json",
                 "robustness_analysis.json"):
        assert "p_v35" not in json.dumps(_load(name))


def test_v34_exclusion():
    blob = (ROOT / "scripts" / "v3_8e_run.py").read_text()
    blob += json.dumps(_load("fusion_evaluation.json"))
    assert "v3_4" not in blob and "V3_4" not in blob


def test_no_run_mc2_path_from_e():
    text = (ROOT / "scripts" / "v3_8e_run.py").read_text()
    assert "run_mc2" not in text
    assert "raceintel.simulation" not in text
    assert "raceintel.model_lab" not in text
    assert "simulation_count" not in text
    assert "5000" not in text or "simulation" not in text


# --- pathology / gate / card ---

def test_all_e_pathology_zero():
    path = _load("fusion_evaluation.json")["pathology"]
    assert set(path) == {f"E-P{i}" for i in range(1, 25)}
    assert all(v == 0 for v in path.values())


def test_gate_decision_not_supported():
    g = _load("fusion_gate.json")
    assert g["decision"] == "FUSION_IMPROVEMENT_NOT_SUPPORTED"
    assert set(g["evidence"]) == {
        "primary_beats_log", "primary_beats_mc2",
        "bootstrap_supportive_vs_log", "bootstrap_supportive_vs_mc2",
        "loro_stable_both_controls",
        "outlier_removed_still_beats_both", "brier_macro_beats_both"}
    assert g["evidence"]["primary_beats_log"] is False
    assert g["evidence"]["primary_beats_mc2"] is True
    assert g["protocol_identity"] == _proto()["protocol_identity"]


def test_fusion_card_identity_recomputes():
    c = _load("fusion_card.json")
    identity = c.pop("card_identity")
    blob = json.dumps(c, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(blob).hexdigest() == identity
    assert "revealed" in c["revealed_corpus_limitation"].lower()
    assert c["gate"] == "FUSION_IMPROVEMENT_NOT_SUPPORTED"
    assert c["e_protocol_identity"] == _proto()["protocol_identity"]
    assert c["d_preflight_verdict"] == "CORRECTABLE_D_ANALYSIS_DEFECT"
    assert c["d_card_identity"] == \
        "67f97c185ca8cc687b59b376bc5a48776e9290d6463a05653fa1a6e18a298985"


def test_revealed_limitation_present():
    assert "REVEALED" in _proto()["revealed_corpus_limitation"]
    card = _load("fusion_card.json")
    assert "revealed" in card["revealed_corpus_limitation"].lower()
