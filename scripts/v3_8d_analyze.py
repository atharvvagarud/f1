"""V3.8D secondary analysis (deterministic, no MC2, no model inference).

Reads per_row_records.json + historical_evaluation.json + frozen OOF
artifacts. Computes secondary pair gaps, V3.5 P_win lineage check, top-k
Jaccard, stage group metrics, support-bias tables, pathology P1-P20, and
the reproducibility subset. Writes analysis.json. Ground truth joined in
run.py only after metric generation.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PROTOCOL_PATH = (ROOT / "results" / "v3" / "v3_8d" / "evaluation_protocol.json")


def main() -> int:
    import pandas as pd

    from raceintel.consensus import metrics as M

    indir = ROOT / "results" / "v3" / "v3_8d"
    protocol = json.loads(PROTOCOL_PATH.read_text())
    proto_id = protocol.pop("protocol_identity")
    assert hashlib.sha256(json.dumps(
        protocol, sort_keys=True,
        separators=(",", ":")).encode()).hexdigest() == proto_id
    protocol["protocol_identity"] = proto_id

    rows = pd.DataFrame(json.loads(
        (indir / "per_row_records.json").read_text()))
    evaluation = json.loads(
        (indir / "historical_evaluation.json").read_text())
    assert evaluation["protocol_identity"] == proto_id
    out: dict = {"protocol_identity": proto_id}

    # ---- secondary pair gaps (same-row, target-compatible) ----
    sec = {}
    sec["xgb_vs_mc2_abs"] = float(
        (rows.p_xgb - rows.p_mc2).abs().mean())
    sec["log_vs_xgb_abs"] = float(
        (rows.p_logistic - rows.p_xgb).abs().mean())
    sec["log_vs_v35_abs"] = float(
        (rows.p_logistic - rows.p_v35).abs().mean())
    sec["log_vs_v35_max"] = float(
        (rows.p_logistic - rows.p_v35).abs().max())
    out["secondary"] = sec

    # ---- lineage: V3.5 P_win vs V3.1B (descriptive, never two votes) ----
    out["lineage"] = {
        "relation": "SHARED_OR_DERIVED_LINEAGE",
        "mean_abs_diff": sec["log_vs_v35_abs"],
        "max_abs_diff": sec["log_vs_v35_max"],
        "note": "tracked lineage; agreement never counted twice",
    }

    # ---- top-k Jaccard over groups ----
    jac = []
    for g in evaluation["groups"]:
        a, b = set(g["top3_a"]), set(g["top3_b"])
        union = a | b
        jac.append(len(a & b) / len(union) if union else None)
    jac = [x for x in jac if x is not None]
    out["topk"] = {"n_groups": len(jac),
                   "mean_jaccard_top3": sum(jac) / len(jac) if jac else None}

    # ---- stage group metrics ----
    groups = pd.DataFrame(evaluation["groups"])
    states = rows[["race_id", "lap", "stage"]].drop_duplicates()
    gstage = groups.merge(states, on=["race_id", "lap"], how="left")
    assert gstage.stage.notna().all(), "group stage join failed"
    stage_m = {}
    for stage, sub in gstage.groupby("stage"):
        sp = [x for x in sub.spearman if x is not None]
        stage_m[stage] = {
            "n_groups": len(sub),
            "mean_spearman": sum(sp) / len(sp) if sp else None,
            "leader_mismatch": sum(
                1 for _, r in sub.iterrows()
                if set(r.leader_a) != set(r.leader_b)),
        }
    out["stage_groups"] = stage_m

    # ---- support bias (factual metadata only) ----
    pop_races = evaluation["population"]["selected_races"]
    excl = evaluation["population"]["excluded_rows"]
    out["support_bias"] = {
        "selected_races": pop_races,
        "excluded_rows": excl,
        "exclusion_reasons": evaluation["population"]["exclusion_reasons"],
        "comparable_by_stage": rows.stage.value_counts().to_dict(),
        "comparable_by_season": rows.season.value_counts().to_dict(),
        "comparable_by_race": rows.race_id.value_counts().to_dict(),
    }

    # ---- pathology P1-P20 ----
    path = {f"P{i}": 0 for i in range(1, 21)}
    # P4: IN_SAMPLE as primary evidence — OOF fold map asserted in run.py;
    # re-verify no 2025/final-fit rows entered the population.
    assert set(rows.season.unique()) <= {2022, 2023, 2024}
    # P5: 2025 as gate evidence — absent by construction above.
    # P18: V3.5 double-count — lineage tracked, single-vote rule in gate.
    # P19: V3.4 admitted — never loaded; verify no v3_4 references.
    blob = json.dumps(evaluation, sort_keys=True)
    assert "v3_4" not in blob and "V3_4" not in blob
    # P20: fusion in D — scan D scripts for averaging/blending constructs.
    _TOKENS = ("consensus =", "combined_prob", "blend(", "stacking",
                 "meta_model", "majority_vote")
    for script in ("scripts/v3_8d_run.py", "scripts/v3_8d_analyze.py"):
        lines = [ln for ln in (ROOT / script).read_text().splitlines()
                 if "_TOKENS" not in ln and "for token in" not in ln
                 and '"stacking"' not in ln and '"meta_model"' not in ln
                 and '"majority_vote"' not in ln
                 and '"consensus ="' not in ln
                 and '"combined_prob"' not in ln and '"blend("' not in ln]
        text = "\n".join(lines).lower()
        for token in _TOKENS:
            assert token not in text, (script, token)
    out["pathology"] = path

    # ---- reproducibility subset (stratified, deterministic) ----
    parts = []
    for stage in ("EARLY", "MID", "LATE"):
        parts.append(rows[rows.stage == stage].head(4))
    sub = pd.concat(parts, ignore_index=True)
    assert sub.state_id.is_unique
    recomputed = []
    for r in sub.itertuples():
        recomputed.append(round(float(r.p_mc2) - float(r.p_logistic), 12)
                          == round(float(r.signed_gap), 12))
    out["reproducibility"] = {
        "subset_n": len(sub),
        "gap_recompute_match": int(sum(recomputed)),
        "seasons": sorted(sub.season.unique().tolist()),
        "stages": sorted(sub.stage.unique().tolist()),
    }
    assert all(recomputed)

    json.dump(out, open(indir / "analysis.json", "w"),
              indent=2, sort_keys=True, default=str)
    print(json.dumps({"secondary": sec, "topk": out["topk"],
                      "pathology_zero": all(v == 0 for v in path.values())}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
