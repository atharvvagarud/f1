"""V3.10G live contract + parity validation (read-only).

Uses only frozen cached paths: strategy mode="cached" and the
cache-first counterfactual endpoint (server live_enabled=False, so
uncached plans return an explicit 404 cache_miss — nothing executes).

Emits results/v3/v3_10g/{availability,refusal,strategy_parity,
counterfactual_parity,v36_v37_parity}_validation.json.
"""

import json
import pathlib
import sys
import urllib.request

API = "http://localhost:8000"
OUT = pathlib.Path("results/v3/v3_10g")
OUT.mkdir(parents=True, exist_ok=True)

FIXTURE = {
    "race_id": "2022-r01-R",
    "anchor_driver_id": "perez",
    "anchor_lap_number": 30,
    "anchor_state_time_s": 6745.686,
    "target_driver_id": "perez",
}


def get(path):
    try:
        with urllib.request.urlopen(API + path, timeout=60) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def post(path, payload):
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def main():
    # --- availability --------------------------------------------------
    _, strat_avail = get("/v2/strategies/v3/availability")
    _, strat_avail_race = get(
        "/v2/strategies/v3/availability?race_id=2022-r01-R"
    )
    _, cf_avail = get(
        "/v2/counterfactuals/availability?race_id=2022-r01-R"
        "&anchor_driver_id=perez&anchor_lap_number=30"
        "&anchor_state_time_s=6745.686"
    )
    perez_row = next(
        d for d in cf_avail["drivers"] if d["driver_id"] == "perez"
    )
    availability = {
        "audit": "V3.10G availability-before-execution contracts (live)",
        "strategy_catalogue": {
            "endpoint": "GET /v2/strategies/v3/availability[?race_id=]",
            "entry_count": strat_avail["entry_count"],
            "race_filtered_count": strat_avail_race["entry_count"],
            "entries": [
                {k: e[k] for k in (
                    "race_id", "anchor_driver_id", "anchor_lap_number",
                    "anchor_state_time_s", "target_driver_id",
                    "master_seed", "simulation_count", "supported",
                    "alternative_count")}
                for e in strat_avail["entries"]
            ],
            "note": "no per-anchor endpoint: pit wall loads the per-race "
                    "catalogue once and matches race+anchor+target exactly "
                    "and locally (zero simulation).",
        },
        "counterfactual_availability": {
            "endpoint": "GET /v2/counterfactuals/availability"
                        "?race_id=&anchor_driver_id=&anchor_lap_number="
                        "&anchor_state_time_s=",
            "supported": cf_avail["supported"],
            "reason_code": cf_avail["reason_code"],
            "eligible_targets_include_perez": "perez" in cf_avail["eligible_targets"],
            "perez_n_domain": [perez_row["eligible_n_min"], perez_row["eligible_n_max"]],
            "perez_decision_lap": perez_row["decision_lap"],
            "supported_compounds": cf_avail["supported_compounds"],
            "live_enabled": cf_avail["live_enabled"],
            "note": "cheap factual availability per exact anchor; never simulates.",
        },
    }
    (OUT / "availability_validation.json").write_text(
        json.dumps(availability, indent=2) + "\n")

    # --- strategy compare (cached full 9) -------------------------------
    s_status, s_full = post("/v2/strategies/compare-v3", {
        **{k: FIXTURE[k] for k in (
            "race_id", "anchor_driver_id", "anchor_lap_number",
            "anchor_state_time_s", "target_driver_id")},
        "mode": "cached",
    })
    assert s_status == 200 and s_full["supported"], (s_status, s_full)
    strategy_parity = {
        "audit": "V3.10G strategy parity: contextual surface consumes the "
                 "same frozen endpoint + payload as the expert page "
                 "(POST /v2/strategies/compare-v3 mode=cached, full 9-action set)",
        "http_status": s_status,
        "execution_source": s_full["execution_source"],
        "simulation_count": s_full["simulation_count"],
        "master_seed": s_full["master_seed"],
        "reference_kind": s_full["reference_kind"],
        "supported": s_full["supported"],
        "alternative_count": len(s_full["alternatives"]),
        "candidate_order": [a["candidate_key"] for a in s_full["alternatives"]],
        "alternatives": [
            {
                "candidate_key": a["candidate_key"],
                "evaluated": a["evaluated"],
                "reason": a["reason"],
                "deltas": {d["metric"]: {
                    "point_estimate": d["point_estimate"],
                    "paired_se": d["paired_se"],
                    "ci_low": d["ci_low"],
                    "ci_high": d["ci_high"],
                    "valid_pairs": d["valid_pairs"]} for d in a["deltas"]},
                "complete_pairs": a["complete_pairs"],
                "excluded_pairs": a["excluded_pairs"],
            }
            for a in s_full["alternatives"]
        ],
        "delta_sign_semantics": "probability deltas ALT - REF; "
            "expected-finish delta REF - ALT (positive = improvement).",
        "parity_claim": "contextual compact rows select WIN/PODIUM/EXPECTED "
            "deltas verbatim from this payload via frozen formatters; "
            "no recomputation. Exact payload equality with the expert page "
            "holds by construction (identical request, identical cache "
            "artifact, identical typed client).",
    }
    (OUT / "strategy_parity_validation.json").write_text(
        json.dumps(strategy_parity, indent=2) + "\n")

    # --- counterfactual compare (cached N=1 MEDIUM) ----------------------
    c_status, c_cmp = post("/v2/counterfactuals/compare", {
        **{k: FIXTURE[k] for k in (
            "race_id", "anchor_driver_id", "anchor_lap_number",
            "anchor_state_time_s")},
        "comparison_form": "REFERENCE_VS_PLAN",
        "alternative_plan": {
            "target_driver_ids": ["perez"],
            "interventions": [{
                "target_driver_id": "perez",
                "kind": "PIT_IN_N_LAPS",
                "lap_offset_n": 1,
                "requested_compound": "MEDIUM"}]},
    })
    assert c_status == 200 and c_cmp["supported"], (c_status, c_cmp)
    counterfactual_parity = {
        "audit": "V3.10G counterfactual parity: contextual surface consumes "
                 "the same frozen endpoint + payload as the expert page "
                 "(POST /v2/counterfactuals/compare REFERENCE_VS_PLAN, "
                 "single PIT_IN_N_LAPS)",
        "http_status": c_status,
        "execution_source": c_cmp["execution_source"],
        "simulation_count": c_cmp["simulation_count"],
        "supported": c_cmp["supported"],
        "intervention": "PIT_IN_N_LAPS N=1 MEDIUM on perez",
        "lifecycle_summary": c_cmp["lifecycle_summary"],
        "complete_pairs": c_cmp["complete_pairs"],
        "deltas": {k: {
            "point_estimate": v["point_estimate"],
            "paired_se": v["paired_se"],
            "ci_low": v["ci_low"],
            "ci_high": v["ci_high"]} for k, v in c_cmp["deltas"].items()},
        "delta_sign_semantics": "probability deltas ALT - BASE; expected "
            "finish BASE - ALT; position gain ALT - BASE (verbatim backend "
            "orientation, no UI sign flips).",
        "parity_claim": "contextual compact rows select PRIMARY_METRIC_ROWS "
            "verbatim via frozen formatters; no recomputation. Exact payload "
            "equality with the expert page holds by construction.",
    }
    (OUT / "counterfactual_parity_validation.json").write_text(
        json.dumps(counterfactual_parity, indent=2) + "\n")

    # --- V3.6/V3.7 parity relation ---------------------------------------
    _, s_sub = post("/v2/strategies/compare-v3", {
        **{k: FIXTURE[k] for k in (
            "race_id", "anchor_driver_id", "anchor_lap_number",
            "anchor_state_time_s", "target_driver_id")},
        "alternatives": [{"action": "PIT_NOW",
                          "requested_compound": "MEDIUM"}],
        "mode": "cached",
    })
    s_alt = next(a for a in s_sub["alternatives"]
                 if a["candidate_key"] == "PIT_NOW:MEDIUM")
    s_deltas = {d["metric"]: d["point_estimate"] for d in s_alt["deltas"]}
    c_deltas = {k: v["point_estimate"] for k, v in c_cmp["deltas"].items()}
    v36_v37 = {
        "audit": "frozen V3.6/V3.7 parity relation on the supported fixture",
        "fixture": FIXTURE,
        "pit_in_1_vs_pit_now": {
            "strategy_PIT_NOW_MEDIUM": s_deltas,
            "counterfactual_PIT_IN_1_MEDIUM": {
                "delta_win_frequency": c_deltas["delta_win_frequency"],
                "delta_podium_frequency": c_deltas["delta_podium_frequency"],
                "delta_expected_finish": c_deltas["delta_expected_finish"]},
            "exact_match": (
                abs(s_deltas["delta_win_frequency"] - c_deltas["delta_win_frequency"]) < 1e-9
                and abs(s_deltas["delta_podium_frequency"] - c_deltas["delta_podium_frequency"]) < 1e-9
                and abs(s_deltas["delta_expected_finish"] - c_deltas["delta_expected_finish"]) < 1e-9),
        },
        "reference_aggregates_match": (
            s_alt["reference_aggregate"]["win_frequency"]
            == c_cmp["base_aggregate"]["win_frequency"]
            and s_alt["alternative_aggregate"]["win_frequency"]
            == c_cmp["alternative_aggregate"]["win_frequency"]),
        "note": "PIT_IN_2 vs PIT_NEXT_LAP uses the same engine relation; "
                "N=2 cached counterfactual verified separately in the "
                "request audit (live 200 supported).",
    }
    (OUT / "v36_v37_parity_validation.json").write_text(
        json.dumps(v36_v37, indent=2) + "\n")

    # --- refusals ---------------------------------------------------------
    refusals = {"audit": "V3.10G refusal taxonomy (live, fail-closed)"}
    st, body = get(
        "/v2/counterfactuals/availability?race_id=2025-r01-R"
        "&anchor_driver_id=perez&anchor_lap_number=30"
        "&anchor_state_time_s=6745.686")
    refusals["cf_availability_2025"] = {"http_status": st, "body": body}
    st, body = post("/v2/strategies/compare-v3", {
        "race_id": "2025-r01-R", "anchor_driver_id": "perez",
        "anchor_lap_number": 30, "anchor_state_time_s": 6745.686,
        "target_driver_id": "perez", "mode": "cached"})
    refusals["strategy_compare_2025"] = {"http_status": st, "body": body}
    st, body = post("/v2/counterfactuals/compare", {
        "race_id": "2022-r01-R", "anchor_driver_id": "perez",
        "anchor_lap_number": 30, "anchor_state_time_s": 6745.686,
        "comparison_form": "REFERENCE_VS_PLAN",
        "alternative_plan": {
            "target_driver_ids": ["perez"],
            "interventions": [{
                "target_driver_id": "perez", "kind": "PIT_IN_N_LAPS",
                "lap_offset_n": 99, "requested_compound": "MEDIUM"}]}})
    refusals["cf_invalid_n"] = {"http_status": st, "body": body}
    st, body = post("/v2/counterfactuals/compare", {
        "race_id": "2022-r01-R", "anchor_driver_id": "perez",
        "anchor_lap_number": 30, "anchor_state_time_s": 6745.686,
        "comparison_form": "REFERENCE_VS_PLAN",
        "alternative_plan": {
            "target_driver_ids": ["perez"],
            "interventions": [{
                "target_driver_id": "perez", "kind": "PIT_IN_N_LAPS",
                "lap_offset_n": 3, "requested_compound": "MEDIUM"}]}})
    refusals["cf_uncached_valid_plan"] = {
        "http_status": st,
        "supported": body.get("supported"),
        "error": body.get("error"),
        "note": "live_enabled=False so an uncached valid plan is an "
                "explicit 404 cache_miss — never a silent live run, never zeros."}
    st, body = post("/v2/counterfactuals/compare", {
        "race_id": "2022-r01-R", "anchor_driver_id": "perez",
        "anchor_lap_number": 30, "anchor_state_time_s": 6745.686,
        "comparison_form": "REFERENCE_VS_PLAN",
        "alternative_plan": {
            "target_driver_ids": ["perez"],
            "interventions": [{
                "target_driver_id": "perez", "kind": "PIT_IN_N_LAPS",
                "lap_offset_n": 5, "requested_compound": "MEDIUM"}]}})
    refusals["cf_cached_n5_plan"] = {
        "http_status": st,
        "supported": body.get("supported"),
        "note": "N=5 MEDIUM is in the precomputed demo cache (200 supported)."}
    st, body = post("/v2/strategies/compare-v3", {
        "race_id": "2022-r01-R", "anchor_driver_id": "norris",
        "anchor_lap_number": 30, "anchor_state_time_s": 6840.903,
        "target_driver_id": "perez", "mode": "cached"})
    refusals["strategy_uncached_valid_anchor"] = {
        "http_status": st,
        "supported": body.get("supported"),
        "error": body.get("error"),
        "note": "valid exact anchor with no precomputed artifact is an "
                "explicit 404 cache_miss — rendered as its own product "
                "state, never zeros."}
    (OUT / "refusal_validation.json").write_text(
        json.dumps(refusals, indent=2) + "\n")

    print("wrote", sorted(p.name for p in OUT.glob("*validation.json")))
    print("v36_v37 exact_match:",
          json.load(open(OUT / "v36_v37_parity_validation.json"))
          ["pit_in_1_vs_pit_now"]["exact_match"])


if __name__ == "__main__":
    sys.exit(main())
