#!/usr/bin/env python3
"""V3.2N Parts C+D: stage ledger + artifact identity audit.

No 2025. No network. Deterministic. Uses actual stage artifacts only.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_2n"


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sha_canonical(obj) -> str:
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()


STAGES = [
    {"stage": "V3.2A", "purpose": "simulation coverage architecture audit",
     "verdict": "V3.2A COMPLETE — READY FOR V3.2B CONTRACT",
     "disposition": "accepted-foundation",
     "runtime_effect": "none (audit)",
     "scientific_effect": "eligibility taxonomy + 5000-run recommendation",
     "coverage_effect": "baseline measurement only",
     "artifacts": ["results/v3/v3_2a_simulation_coverage_architecture_audit.json"],
     "limitations": ["audit only; no simulator change"]},
    {"stage": "V3.2B", "purpose": "Monte Carlo 2.0 scientific contract",
     "verdict": "V3.2B COMPLETE — READY FOR V3.2C",
     "disposition": "accepted-foundation",
     "runtime_effect": "none (declarative mc2-field-v1 + support matrix)",
     "scientific_effect": "presence levels + condition support matrix frozen",
     "coverage_effect": "none",
     "artifacts": ["results/v3/v3_2b_mc2_scientific_contract.json",
                   "raceintel/simulation/field_contract.py"],
     "limitations": ["contract only; stale handling mixed-decision"]},
    {"stage": "V3.2C", "purpose": "causal initial-state coverage repair",
     "verdict": "V3.2C COMPLETE — READY FOR V3.2D",
     "disposition": "accepted",
     "runtime_effect": "presence adapter (DNS exclusion only)",
     "scientific_effect": "FACTUAL_AT_T binding; no retirement inference; no tyre backfill",
     "coverage_effect": "DNS repair (part of 2305 baseline chain)",
     "artifacts": ["results/v3/v3_2c_causal_initial_state_coverage.json",
                   "raceintel/simulation/presence.py"],
     "limitations": ["STALE_UNRESOLVED still refused"]},
    {"stage": "V3.2D", "purpose": "Monte Carlo 2.0 dynamics (arms A–F)",
     "verdict": "V3.2D COMPLETE — READY FOR V3.2E (candidate ADVANCE_E)",
     "disposition": "accepted",
     "runtime_effect": "MC2 kernel arms; traffic gated off",
     "scientific_effect": "anchor+dynamics+variance+AR1 selected; params per era",
     "coverage_effect": "none",
     "artifacts": ["results/v3/v3_2d_mc2_dynamics.json",
                   "results/v3/v3_2d/mc2_params_through-2023_anchor.json",
                   "raceintel/simulation/mc2/"],
     "limitations": ["traffic context gated off; dry-green only"]},
    {"stage": "V3.2E", "purpose": "controlled temporal backtest",
     "verdict": "V3.2E COMPLETE — KEEP_MC2_E",
     "disposition": "accepted",
     "runtime_effect": "MC2-E accepted; 5000 runs frozen",
     "scientific_effect": "winner log-loss A-E +0.696 [0.236,1.210]; top1 0.567->0.624; ECE 0.202->0.113",
     "coverage_effect": "none",
     "artifacts": ["results/v3/v3_2e_controlled_backtest.json",
                   "results/v3/v3_2e/preregistration.json"],
     "limitations": ["dry-green population; no DNF/weather/SC modelling"]},
    {"stage": "V3.2F", "purpose": "regime support coverage expansion",
     "verdict": "V3.2F COMPLETE — NO REGIME ADMITTED",
     "disposition": "rejected/deferred",
     "runtime_effect": "none (dry-green parity corpus 7ae97c3c frozen)",
     "scientific_effect": "RED/SC/VSC/YELLOW/WET support rejected/deferred with evidence",
     "coverage_effect": "none admitted",
     "artifacts": ["results/v3/v3_2f_regime_coverage.json"],
     "limitations": ["regime checkpoints remain unsupported by design"]},
    {"stage": "V3.2G", "purpose": "causal driver status (processed sources)",
     "verdict": "V3.2G COMPLETE — NO AUTHORITATIVE STATUS ADMITTED",
     "disposition": "rejected",
     "runtime_effect": "none",
     "scientific_effect": "processed sources carry no authoritative terminal vocabulary",
     "coverage_effect": "none",
     "artifacts": ["results/v3/v3_2g_driver_status.json"],
     "limitations": ["motivated raw-source investigation (V3.2I/J)"]},
    {"stage": "V3.2H", "purpose": "causal regime models",
     "verdict": "V3.2H COMPLETE — NO REGIME ADMITTED",
     "disposition": "rejected/deferred",
     "runtime_effect": "none",
     "scientific_effect": "no regime evolution model admitted",
     "coverage_effect": "none admitted",
     "artifacts": ["results/v3/v3_2h_regime_models.json"],
     "limitations": ["neutralisation science out of scope"]},
    {"stage": "V3.2I", "purpose": "external status feasibility (raw TimingData)",
     "verdict": "V3.2I COMPLETE — LOCAL RAW STATUS SOURCE PARTIALLY VIABLE",
     "disposition": "accepted-feasibility",
     "runtime_effect": "none (feasibility only)",
     "scientific_effect": "TimingData.Retired viable as exclusion-only signal",
     "coverage_effect": "projected 2685/9644 (27.84%)",
     "artifacts": ["results/v3/v3_2i_external_status_feasibility.json"],
     "limitations": ["projection only; integration deferred to J"]},
    {"stage": "V3.2J", "purpose": "raw TimingData Retired integration",
     "verdict": "V3.2J COMPLETE — STATUS INTEGRATED — COVERAGE EXPANDED",
     "disposition": "accepted",
     "runtime_effect": "v3.2j-presence-v2: J-relieved exclusion; 422 otherwise",
     "scientific_effect": "v3.2j-driver-status-v1 exclusion-only; 13 unreliable windows; firewalls pass",
     "coverage_effect": "+1373 (+14.24pp) to 3678/9644 (38.14%)",
     "artifacts": ["results/v3/v3_2j_raw_timing_status.json",
                   "raceintel/simulation/driver_status.py"],
     "limitations": ["exclusion-only; False/unknown prove nothing"]},
    {"stage": "V3.2K", "purpose": "raw timing state reconstruction",
     "verdict": "V3.2K COMPLETE — DIRECT STATE RECONSTRUCTION REJECTED",
     "disposition": "rejected",
     "runtime_effect": "none",
     "scientific_effect": "tyre/compound absent from TimingData; 2019-2023 only",
     "coverage_effect": "none (2866 raw-source-stale remain)",
     "artifacts": ["results/v3/v3_2k_raw_timing_state_reconstruction.json"],
     "limitations": ["hands 3294 STALE + lifecycle framing to L"]},
    {"stage": "V3.2L", "purpose": "causal driver lifecycle model",
     "verdict": "V3.2L COMPLETE — LIFECYCLE MODEL REJECTED",
     "disposition": "rejected",
     "runtime_effect": "none",
     "scientific_effect": "unstable calibration, small-N, N=30 return-time, concurrent-stop dependence, no hold/resume",
     "coverage_effect": "none admitted (5552 projection NOT admitted)",
     "artifacts": ["results/v3/v3_2l_causal_driver_lifecycle.json"],
     "limitations": ["track-code/token defect in stage-1 (corrected in N); 214 PIT_CONTEXT handed to M"]},
    {"stage": "V3.2M", "purpose": "causal pit lifecycle feasibility",
     "verdict": "V3.2M COMPLETE — PIT LIFECYCLE REJECTED",
     "disposition": "rejected",
     "runtime_effect": "none",
     "scientific_effect": "P(return|PIT_CONTEXT)=6.5%; recent-entry 0/11; duration N=14; stale pit opportunity structurally 0",
     "coverage_effect": "none (+0)",
     "artifacts": ["results/v3/v3_2m_causal_pit_lifecycle.json"],
     "limitations": ["TimingAppData stream audit deferred; red-flag cluster explained"]},
]


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ledger = {"schema_version": "v3.2n-stage-ledger-v1",
              "baseline": {"tag": "v3.1-race-dynamics",
                           "commit": "64c5af094bd1304e23a5c7d3d5b782b0eef11aca"},
              "stages": STAGES}
    (OUT / "stage_ledger.json").write_text(
        json.dumps(ledger, indent=1, sort_keys=True), encoding="utf-8")

    # ---- identity audit ----
    checks = []

    def check(name: str, path: str, expected: str | None,
              consumer: str, kind: str = "sha256-file"):
        p = ROOT / path
        rec = {"name": name, "path": path, "consumer": consumer,
               "exists": p.exists()}
        if not p.exists():
            rec.update({"match": False, "note": "MISSING"})
            checks.append(rec)
            return
        if kind == "sha256-file":
            actual = sha_file(p)
            rec.update({"hash_expected": expected, "hash_actual": actual,
                        "match": actual == expected})
        elif kind == "prereg-canonical":
            obj = json.load(open(p, encoding="utf-8"))
            actual = sha_canonical(obj)
            rec.update({"hash_expected": expected, "hash_actual": actual,
                        "match": actual == expected})
        elif kind == "embedded":
            obj = json.load(open(p, encoding="utf-8"))
            actual = _find_hash(obj, expected)
            rec.update({"hash_expected": expected, "hash_actual": actual,
                        "match": actual == expected})
        checks.append(rec)

    def _find_hash(obj, needle: str):
        if isinstance(obj, str) and obj == needle:
            return obj
        if isinstance(obj, dict):
            for v in obj.values():
                r = _find_hash(v, needle)
                if r is not None:
                    return r
        if isinstance(obj, list):
            for v in obj:
                r = _find_hash(v, needle)
                if r is not None:
                    return r
        return None

    # prereg .sha256 sidecars use canonical-json hashing in some stages;
    # verify with the stage's own convention: compare file bytes hash ONLY
    # where the sidecar was produced that way, else canonical.
    # Each stage's own hashing convention: J/K/L scripts hash
    # json.dumps(obj, sort_keys=True) with DEFAULT separators; M hashes
    # canonical compact separators. Accept the stage's own convention.
    for stage, prefix in [("V3.2J", "results/v3/v3_2j/preregistration"),
                          ("V3.2K", "results/v3/v3_2k/preregistration"),
                          ("V3.2L", "results/v3/v3_2l/preregistration"),
                          ("V3.2M", "results/v3/v3_2m/preregistration")]:
        side = (ROOT / (prefix + ".sha256")).read_text(
            encoding="utf-8").strip()
        obj = json.load(open(ROOT / (prefix + ".json"), encoding="utf-8"))
        default_sep = hashlib.sha256(
            json.dumps(obj, sort_keys=True).encode()).hexdigest()
        compact_sep = sha_canonical(obj)
        byted = hashlib.sha256(
            (ROOT / (prefix + ".json")).read_bytes()).hexdigest()
        match = side in (default_sep, compact_sep, byted)
        checks.append({"name": f"{stage} preregistration",
                       "path": prefix + ".json",
                       "consumer": f"{stage} scripts + N audit",
                       "exists": True, "hash_expected": side,
                       "hash_actual_default_sep": default_sep,
                       "hash_actual_compact_sep": compact_sep,
                       "hash_actual_bytes": byted, "match": match})
    # pinned scientific identities (embedded in artifacts)
    pins = [
        ("J status corpus", "results/v3/v3_2j/status_corpus_identity.json",
         "8229a8606d5331338607dfd4a117a58369534325e0444a3052815299137c6f30",
         "presence/driver_status resolver", "exact"),
        ("dry-green parity", "results/v3/v3_2j/dry_green_parity.json",
         "7ae97c3c8575679a", "O parity gate", "substring"),
        ("L episode corpus", "results/v3/v3_2l/episode_corpus.json",
         "v3.2l-episode-corpus-v1", "M audit + N correction", "substring"),
        ("L prereg embedded", "results/v3/v3_2l_causal_driver_lifecycle.json",
         "4c3eb5c8cdfe9ebf44555de540ee1378d0b12089d5c8cbc44dea7c0de6c48533",
         "N audit", "exact"),
        ("K prereg embedded", "results/v3/v3_2k_raw_timing_state_reconstruction.json",
         "567260af8072d2e1700a4d1e9ad24265fc458c838010dc8a0d27b745c6a2f22b",
         "N audit", "exact"),
    ]
    for name, path, needle, consumer, mode in pins:
        p = ROOT / path
        rec = {"name": name, "path": path, "consumer": consumer,
               "exists": p.exists()}
        if p.exists():
            if mode == "substring":
                text = p.read_text(encoding="utf-8") if path.endswith(
                    ".py") else json.dumps(
                        json.load(open(p, encoding="utf-8")), sort_keys=True)
                rec.update({"hash_expected": needle,
                            "match": needle in text,
                            "note": "substring pin"})
            else:
                found = _find_hash(json.load(open(p, encoding="utf-8")),
                                   needle)
                rec.update({"hash_expected": needle, "hash_actual": found,
                            "match": found == needle})
        else:
            rec.update({"match": False, "note": "MISSING"})
        checks.append(rec)
    # code version strings (accepted contracts)
    code_pins = [
        ("field contract", "raceintel/simulation/field_contract.py",
         "mc2-field-v1"),
        ("presence adapter C", "raceintel/simulation/presence.py",
         "v3.2c-presence-v1"),
        ("presence adapter J", "raceintel/simulation/presence.py",
         "v3.2j-presence-v2"),
        ("status contract", "raceintel/simulation/driver_status.py",
         "v3.2j-driver-status-v1"),
        ("raw adapter", "raceintel/simulation/driver_status.py",
         "v3.2j-raw-adapter-v1"),
    ]
    for name, path, token in code_pins:
        text = (ROOT / path).read_text(encoding="utf-8")
        checks.append({"name": f"code:{name}", "path": path,
                       "consumer": "runtime/presence",
                       "exists": True, "token": token,
                       "match": token in text})
    audit = {"schema_version": "v3.2n-artifact-identity-audit-v1",
             "checks": checks,
             "all_match": all(c.get("match") for c in checks)}
    (OUT / "artifact_identity_audit.json").write_text(
        json.dumps(audit, indent=1, sort_keys=True), encoding="utf-8")
    bad = [c["name"] for c in checks if not c.get("match")]
    print(f"ledger stages={len(STAGES)} identity_checks={len(checks)} "
          f"mismatches={bad}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
