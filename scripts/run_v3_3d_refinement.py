"""V3.3D nested refinement + temporal calibration (ET + XGB, PRE-2025).

Execution: identities + D-grid match -> pre-firewall -> C references
(read-only) -> run_d_fold per family-fold -> D RAW + D CALIBRATED OOF
parquets + per-fold result JSONs. Analysis in scripts/analyze_v3_3d.py.
Checkpointed per family-fold. HGB refused. 2025 never touched.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, ".")
from raceintel.model_lab import v3_3b_harness as H  # noqa: E402
from raceintel.model_lab import v3_3d_refinement as D  # noqa: E402
from raceintel.model_lab import v3_dynamics_experiment as V3C  # noqa: E402
from raceintel.model_lab.errors import ProtectedHoldoutError  # noqa: E402

OUT = Path("results/v3/v3_3d")
OOF_DIR = Path("data/v3/v3_3d")
FOLDS = ("D1", "D2", "D3")


def write(name: str, payload: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / name
    dest.write_text(json.dumps(payload, indent=1, sort_keys=True,
                               default=str) + "\n")
    return dest


def write_oof(frame: pd.DataFrame, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    H.validate_oof_frame(frame)
    frame.to_parquet(dest, index=False)
    return dest


def load_d_prereg() -> dict:
    prereg = json.loads((OUT / "preregistration.json").read_text())
    payload = {k: v for k, v in prereg.items()
               if k != "preregistration_identity"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(blob.encode()).hexdigest() != \
            prereg["preregistration_identity"]:
        raise RuntimeError("D preregistration hash mismatch")
    return prereg


def main() -> None:
    contracts = H.verify_contracts()
    d_prereg = load_d_prereg()
    c_prereg = json.loads(
        Path("results/v3/v3_3c/preregistration.json").read_text())
    assert d_prereg["c_prereg_sha"] == c_prereg["preregistration_identity"]
    live = D.d_grids()
    for fam in D.D_FAMILIES:
        frozen = d_prereg["refinement_grids"][fam]
        assert len(live[fam]) <= 6
        assert [D.d_config_id(fam, c) for c in live[fam]] == \
            [g["id"] for g in frozen], f"D grid drift: {fam}"
    print("A/B/C/D identities + D grid match verified.", flush=True)

    firewall_pre = {"2025_CONTACT": "NONE", **contracts,
                    "d_prereg_sha": d_prereg["preregistration_identity"]}
    for bad in ("HOLDOUT", "2025", "FINAL_FIT"):
        try:
            H.assert_development_fold(bad)
            firewall_pre[bad] = "NOT_BLOCKED"
        except ProtectedHoldoutError:
            firewall_pre[bad] = "BLOCKED:ProtectedHoldoutError"
    try:
        D.require_d_family("hist_gradient_boosting")
        firewall_pre["hgb_closed"] = "NOT_ENFORCED"
    except Exception:  # noqa: BLE001 -- HGB must be refused
        firewall_pre["hgb_closed"] = "REFUSED"
    if any(v in ("NOT_BLOCKED", "NOT_ENFORCED")
           for v in firewall_pre.values()):
        write("firewall_pre.json", firewall_pre)
        raise RuntimeError("V3.3D BLOCKED - firewall/HGB-gate failure")
    write("firewall_pre.json", firewall_pre)
    print("pre-firewall: 2025_CONTACT = NONE; HGB refused.", flush=True)

    # -- C references preserved read-only -------------------------------
    c_sel = json.loads(
        Path("results/v3/v3_3c/selected_configs.json").read_text())
    c_oof = json.loads(
        Path("results/v3/v3_3c/oof_identities.json").read_text())
    c_refs = {"c_prereg_sha": d_prereg["c_prereg_sha"], **contracts,
              "selected_configs": {f: c_sel["selected"][f]
                                   for f in D.D_FAMILIES},
              "raw_oof": {f: c_oof["oof"][f] for f in
                          ("v3_1b_baseline",) + D.D_FAMILIES}}
    write("c_reference_identities.json", c_refs)

    augmented, plain = V3C.load_joined_frame()
    names_110 = H.feature_names_110()
    H.check_feature_contract(
        V3C.v3_feature_names(V3C.ARM_A), names_110)

    import subprocess as sp
    try:
        commit = sp.run(["git", "rev-parse", "HEAD"], capture_output=True,
                        text=True).stdout.strip()
    except Exception:
        commit = "unknown"
    for family in D.D_FAMILIES:
        for fold in FOLDS:
            result_path = OUT / f"d_result_{family}__{fold}.json"
            raw_path = OOF_DIR / f"oof_d_refined_{family}__{fold}.parquet"
            cal_path = OOF_DIR / f"oof_d_calibrated_{family}__{fold}.parquet"
            if result_path.exists() and raw_path.exists() \
                    and cal_path.exists():
                print(f"skip {family}/{fold} (checkpointed)", flush=True)
                continue
            t0 = time.perf_counter()
            out = D.run_d_fold(augmented, plain, family, fold, names_110)
            wall_s = round(time.perf_counter() - t0, 1)
            write_oof(out["frame_raw"], raw_path)
            write_oof(out["frame_calibrated"], cal_path)
            res = out["outer"]
            prov = H.provenance_envelope(
                family=family, config=out["selection"]["selected_config"],
                fold_id=fold, feature_arm=H.ARM_PRIMARY,
                feature_names=names_110, dataset=res["dataset"],
                code_commit=commit)
            payload = {
                "family": family, "fold": fold,
                "selection": out["selection"],
                "config_aggregates": {
                    k: {"mean": v["mean"], "std": v["std"]}
                    for k, v in out["aggregates"].items()},
                "estimator_fits": out["estimator_fits"],
                "calibration": out["calibration_selection"],
                "calibration_method": out["calibration_method"],
                "raw_metrics": {
                    m: {"race_macro": p["race_macro"]["value"],
                        "state_pooled": p["state_pooled"]["value"]}
                    for m, p in res["metrics"].items()
                    if p.get("status") == "OK"},
                "raw_per_race_ll": res["metrics"]["log_loss"][
                    "race_macro"]["per_race"],
                "raw_stages": {
                    s: {m: pay[s]["race_macro"]["value"]
                        for m, pay in res["stages"].items()
                        if pay.get("status") == "OK" and s in pay
                        and pay[s].get("race_macro")}
                    for s in ("EARLY", "MID", "LATE")},
                "raw_calibration": res["calibration"],
                "raw_topk": res["topk"],
                "provenance": prov,
                "timings": out["timings"],
                "wall_seconds": wall_s,
                "d_prereg_sha": d_prereg["preregistration_identity"]}
            write(f"d_result_{family}__{fold}.json", payload)
            ll = res["metrics"]["log_loss"]["race_macro"]["value"]
            print(f"{family}/{fold}: {out['selection']['selected_key']} "
                  f"RAW_LL={ll:.6f} cal={out['calibration_method']} "
                  f"wall={wall_s}s", flush=True)
    print("D execution complete.", flush=True)


if __name__ == "__main__":
    main()
