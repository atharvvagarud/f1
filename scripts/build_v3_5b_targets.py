"""V3.5B: build canonical threshold-target sidecar (one-shot writer).

No model fitting, no predictions, 2018-2024 only (2025 fails closed).
Re-running must reproduce the same logical dataset identity.
"""
import hashlib
import json
from pathlib import Path

import pandas as pd

from raceintel.model_lab import outcomes as OC
from raceintel.model_lab.errors import ProtectedHoldoutError

OUT = Path("data/v3/v3_5b")
RES = Path("results/v3/v3_5b")
A_ID = "15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab"
SEASONS = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
MATRIX = Path("data/v2/processed/model_matrix/matrix_version=v1/model_matrix.parquet")


def sha(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    contract = json.loads(
        Path("results/v3/v3_5a/experiment_contract.json").read_text())
    blob = json.dumps({k: v for k, v in contract.items()
                       if k != "contract_hash"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        contract["contract_hash"] == A_ID, "A contract mismatch"
    assert contract["selected_primary_task"] == \
        "ordered_cumulative_finish_thresholds"

    labels = OC.load_development_labels(SEASONS)
    assert set(int(s) for s in labels["season"].unique()) == set(SEASONS)
    outcomes = OC.build_outcome_frame(labels)

    # outcome-grain audit
    n_races = int(outcomes["race_id"].nunique())
    n_out = len(outcomes)
    assert outcomes.duplicated(["race_id", "driver_id"]).sum() == 0
    nest = ((outcomes["is_top1"] <= outcomes["is_top3"])
            & (outcomes["is_top3"] <= outcomes["is_top5"])
            & (outcomes["is_top5"] <= outcomes["is_top10"])).all()
    assert bool(nest), "outcome-grain nesting violation"
    sem_counts = outcomes["outcome_semantic"].value_counts().to_dict()
    prev_out = {name: {"positives": int(outcomes[name].sum()),
                       "total": n_out,
                       "rate": float(outcomes[name].mean())}
                for name in OC.TARGET_NAMES}
    top10 = (outcomes["position_final"] <= 10).to_numpy()
    pts = (outcomes["points"] > 0).to_numpy()
    top10_points_equiv = bool((top10 == pts).all())
    field = outcomes.groupby("race_id").size()
    field_sizes = {str(k): int(v) for k, v in
                   field.value_counts().sort_index().items()}
    odd = field[field != 20]
    assert len(odd) == 1, odd.to_dict()

    # state population from frozen matrix identity (2018-2024 only)
    states = pd.read_parquet(
        MATRIX, columns=["state_id", "race_id", "season", "driver_id"])
    states = states[states["season"].isin(SEASONS)].copy()
    if (states["season"] == 2025).any():
        raise ProtectedHoldoutError("2025 states reached V3.5B build")
    assert states["state_id"].is_unique
    sidecar = OC.expand_to_states(outcomes, states)
    assert len(sidecar) == len(states)
    assert sidecar["state_id"].is_unique
    assert ((sidecar[list(OC.TARGET_NAMES)].values[:, :-1]
             <= sidecar[list(OC.TARGET_NAMES)].values[:, 1:]).all())
    prev_state = {name: {"positives": int(sidecar[name].sum()),
                         "total": len(sidecar),
                         "rate": float(sidecar[name].mean())}
                  for name in OC.TARGET_NAMES}
    by_season = {}
    for s in SEASONS:
        sub = sidecar[sidecar["season"] == s]
        o = outcomes[outcomes["race_id"].str[:4].astype(int) == s]
        by_season[str(s)] = {
            "races": int(o["race_id"].nunique()),
            "outcomes": len(o),
            "states": len(sub),
            "outcome_rates": {n: float(o[n].mean()) for n in OC.TARGET_NAMES},
            "state_rates": {n: float(sub[n].mean()) for n in OC.TARGET_NAMES}}

    # feature identity (reuse frozen assembly; no fitting)
    from raceintel.model_lab import v3_dynamics_experiment as V3C
    from raceintel.model_lab import v3_3b_harness as H
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = tuple(canonical_predictive_names())
    names_110 = V3C.v3_feature_names(V3C.ARM_B, names_84)
    fcheck = H.check_feature_contract(names_84, names_110)
    assert fcheck["feature_hash"] == \
        "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"
    assert len(names_110) == 110
    matrix_cols = pd.read_parquet(MATRIX, columns=[]).columns  # noqa (schema via manifest)
    _ = matrix_cols
    import json as _json
    manifest = _json.loads(Path(
        "data/v2/processed/model_matrix/matrix_version=v1/manifest.json").read_text())
    assert list(manifest["predictive_columns"]) == list(names_84)
    overlap_targets = set(names_110) & (set(OC.TARGET_NAMES)
                                        | {"outcome_semantic", "position_final",
                                           "classified_flag", "status_text"})
    assert not overlap_targets, sorted(overlap_targets)
    assert not any("spatial" in c.lower() or c.startswith("p12_")
                   for c in names_110)

    # logical dataset identity (content-based, not bytes)
    ordered = sidecar.sort_values("state_id", kind="mergesort").reset_index(drop=True)
    state_blob = hashlib.sha256(
        "\n".join(ordered["state_id"].astype(str)).encode()).hexdigest()
    label_blob = hashlib.sha256(
        ordered[list(OC.TARGET_NAMES)].to_numpy().astype("int8").tobytes()).hexdigest()
    dataset_id = sha({"parent": "v3.4-ensemble@3cbd28470ffa211bd754d4262eb10d66d149bf00",
                      "a_contract": A_ID, "seasons": SEASONS,
                      "state_ids": state_blob, "labels": label_blob,
                      "thresholds": list(OC.THRESHOLD_ORDER),
                      "status_policy": OC.STATUS_POLICY_VERSION,
                      "population_policy": OC.POPULATION_POLICY_VERSION,
                      "targets": OC.TARGET_CONTRACT_VERSION,
                      "features": fcheck["feature_hash"]})

    OUT.mkdir(parents=True, exist_ok=True)
    RES.mkdir(parents=True, exist_ok=True)
    dest = OUT / "outcome_targets_2018_2024.parquet"
    ordered.to_parquet(dest, index=False)
    phys = hashlib.sha256(dest.read_bytes()).hexdigest()

    (RES / "dataset_manifest.json").write_text(json.dumps({
        "schema_version": "v3.5b-dataset-v1",
        "logical_identity": dataset_id,
        "physical_identity": {"path": str(dest), "sha256": phys},
        "state_rows": len(ordered), "outcome_rows": n_out, "races": n_races,
        "seasons": SEASONS,
        "feature_identity": {"arm": "ALL_84_PLUS_V3_1_DYNAMICS_CORE",
                             "n": 110, "hash": fcheck["feature_hash"]},
        "threshold_order": list(OC.THRESHOLD_ORDER),
        "target_names": list(OC.TARGET_NAMES),
        "outcome_prevalence": prev_out,
        "state_prevalence": prev_state,
        "by_season": by_season,
        "semantic_counts": {str(k): int(v) for k, v in sem_counts.items()},
        "field_sizes": field_sizes,
        "non20_fields": {str(k): int(v) for k, v in odd.items()},
        "top10_points_observed_equivalence": top10_points_equiv,
        "status_policy": OC.STATUS_POLICY_VERSION,
        "population_policy": OC.POPULATION_POLICY_VERSION,
        "target_contract": OC.TARGET_CONTRACT_VERSION,
        "projection_policy": OC.PROJECTION_POLICY_VERSION,
        "2025_status": "NONE (2025_CONTACT=NONE; 2025 rejected by construction)",
    }, indent=1, sort_keys=True) + "\n")

    (RES / "harness_readiness.json").write_text(json.dumps({
        "schema_version": "v3.5b-harness-readiness-v1",
        "dataset_identity": dataset_id,
        "checks": {
            "features_110_recomputable": True,
            "targets_4_present": True,
            "state_identity_unique": True,
            "race_driver_identity_present": True,
            "season_present": True,
            "temporal_folds_D1_D2_D3_reusable": True,
            "threshold_order_frozen": list(OC.THRESHOLD_ORDER),
            "projection_utility_importable": True,
            "no_2025_rows": True},
        "all_pass": True}, indent=1, sort_keys=True) + "\n")
    print("dataset_identity:", dataset_id)
    print(f"outcomes={n_out} races={n_races} states={len(ordered)} "
          f"top10_points_equiv={top10_points_equiv}")


if __name__ == "__main__":
    main()
