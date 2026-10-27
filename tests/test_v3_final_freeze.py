"""V3 Final freeze tests: programme consolidation is complete and frozen.

No production imports. Stdlib only. Fails closed on missing artifacts.
"""

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "results" / "v3" / "final"


def _load(name):
    p = FINAL / name
    assert p.exists(), f"missing {p}"
    return json.loads(p.read_text(encoding="utf-8"))


def _rev(obj):
    return subprocess.run(
        ["git", "rev-parse", obj], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


# ---- PROGRAMME ----

def test_final_records_complete():
    expected = {
        "v3_tag_registry.json", "v3_programme_manifest.json",
        "product_authority_audit.json", "research_production_separation.json",
        "scientific_claim_registry.json", "artifact_inventory.json",
        "test_guard_audit.json", "v3_scientific_card.json",
        "release_manifest.json", "identity_registry.json",
    }
    missing = [n for n in expected if not (FINAL / n).exists()]
    assert not missing, missing
    assert (ROOT / "docs" / "V3_FINAL_PROGRAMME_SYNTHESIS.md").exists()


def test_stage_registry_complete():
    reg = _load("v3_tag_registry.json")["tags"]
    assert set(reg) == {"V3.1", "V3.2", "V3.3", "V3.4", "V3.5", "V3.6",
                        "V3.7", "V3.8", "V3.8P", "V3.9", "V3.10", "V3.11"}
    assert all(v["immutable"] for v in reg.values())


# ---- TAGS ----

def test_tags_resolve_to_registry_commits():
    reg = _load("v3_tag_registry.json")["tags"]
    for stage, v in reg.items():
        assert _rev(v["tag"] + "^{commit}") == v["commit"], stage


def test_no_duplicate_stage_identity():
    reg = _load("v3_tag_registry.json")["tags"]
    tags = [v["tag"] for v in reg.values()]
    assert len(set(tags)) == len(tags)


# ---- PRODUCTION ----

def test_canonical_mc2_coverage_pinned():
    card = _load("v3_scientific_card.json")
    assert card["production_mc2_coverage"] == "3678 / 9644 (38.14%)"
    recon = json.loads((ROOT / "results" / "v3" / "v3_11_final"
                        / "coverage_reconciliation.json").read_text(
                            encoding="utf-8"))
    blob = json.dumps(recon)
    assert "3678" in blob and "9644" in blob


def test_no_unsupported_regime_integration():
    card = _load("v3_scientific_card.json")
    unsupported = set(card["unsupported_regimes"])
    assert {"wet", "VSC", "SC", "yellow", "red/restart"} <= unsupported
    assert _load("v3_programme_manifest.json")[
        "production_mc2_coverage"] == "3678 / 9644 (38.14%)"


# ---- CLAIMS ----

def test_forbidden_claims_present_as_prohibited():
    claims = _load("scientific_claim_registry.json")["claims"]
    assert "fused calibrated probability" in claims["consensus"][
        "prohibited"]
    assert "scalar confidence/quality score" in claims["uncertainty"][
        "prohibited"]
    assert "optimal strategy" in claims["strategy"]["prohibited"]
    assert "alternate-history truth" in claims["counterfactual"][
        "prohibited"]
    assert "production-supported VSC simulation" in claims["vsc"][
        "prohibited"]


# ---- SEPARATION ----

def test_separation_verdict_pass():
    sep = _load("research_production_separation.json")
    assert sep["verdict"] == "PASS"
    assert sep["forbidden_import_edges"] == []
    assert sep["production_code_refs_to_research_paths"] == []
    assert sep["frontend_code_hits"] == []


def test_known_edge_still_preexisting_only():
    sep = _load("research_production_separation.json")
    edge = sep["known_preexisting_edge"]
    assert edge["edge"] == ["api/v2_explanation_service.py",
                            "scripts.replay_feature_matrix"]
    helper = (ROOT / "scripts" / "replay_feature_matrix.py").read_text(
        encoding="utf-8")
    assert "v3_11" not in helper and "v3/final" not in helper


# ---- PRODUCT ----

def test_pit_wall_primary_workspace():
    card = _load("v3_scientific_card.json")
    assert card["product_surface"] == "Pit Wall (/pit-wall)"
    audit = _load("product_authority_audit.json")["domains"]
    assert audit["pit_wall"]["verdict"] == "CANONICAL"
    assert (ROOT / "frontend" / "app" / "pit-wall" / "page.tsx").exists()


def test_strategy_authority_not_formalized_retained():
    audit = _load("product_authority_audit.json")["domains"]
    assert audit["strategy"]["verdict"] == "AUTHORITY_NOT_YET_FORMALIZED"


# ---- PROVENANCE ----

def test_synthesis_points_to_frozen_evidence():
    doc = (ROOT / "docs" / "V3_FINAL_PROGRAMME_SYNTHESIS.md").read_text(
        encoding="utf-8")
    for ref in ("results/v3/v3_11_final/coverage_reconciliation.json",
                "results/v3/v3_11_final/terminal_decision.json",
                "results/v3/final/scientific_claim_registry.json",
                "results/v3/final/identity_registry.json"):
        assert ref in doc, ref
        assert (ROOT / ref).exists(), ref


def test_frozen_stage_tags_unmoved():
    assert _rev("v3.11-mc2-coverage^{commit}").startswith("7664963")
    assert _rev("v3.10-pit-wall^{commit}").startswith("2c00e7e")


def test_identity_registry_covers_peers():
    idents = _load("identity_registry.json")["sha256"]
    assert set(idents) == {"v3_programme_manifest.json",
                           "v3_scientific_card.json",
                           "release_manifest.json",
                           "scientific_claim_registry.json",
                           "product_authority_audit.json"}
    import hashlib
    for name, digest in idents.items():
        actual = hashlib.sha256(
            (FINAL / name).read_bytes()).hexdigest()
        assert actual == digest, name


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
