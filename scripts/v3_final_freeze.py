#!/usr/bin/env python3
"""V3 Final -- programme consolidation records (offline, read-only inputs).

Reads the frozen V3 tree (never rewrites history) and emits the final
machine-readable release records under results/v3/final/:
  v3_tag_registry.json, v3_programme_manifest.json,
  product_authority_audit.json, research_production_separation.json,
  scientific_claim_registry.json, artifact_inventory.json,
  test_guard_audit.json, v3_scientific_card.json, release_manifest.json,
  identity_registry.json

Deterministic given the tree. Stdlib only. No production imports.
Safe to re-run (same inputs -> identical bytes, except the Tier-1
section once /tmp/tier1_v3final.log exists).

Usage:
    .venv/bin/python scripts/v3_final_freeze.py
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "final"

TAGS = (
    ("V3.1", "v3.1-race-dynamics", "Race Dynamics research complete"),
    ("V3.2", "v3.2-monte-carlo-2", "MC2 production simulation frozen"),
    ("V3.3", "v3.3-multi-model-lab", "Multi-model research, no promotion"),
    ("V3.4", "v3.4-ensemble", "Ensemble mixed, no promotion"),
    ("V3.5", "v3.5-outcome-distribution", "Marginals only, no promotion"),
    ("V3.6", "v3.6-strategy-2.0", "Strategy 2.0 additive integration"),
    ("V3.7", "v3.7-counterfactual-engine", "Counterfactual engine frozen"),
    ("V3.8", "v3.8-model-simulation-consensus", "Consensus frozen, no fusion"),
    ("V3.8P", "v3.8-mc2-performance", "MC2 performance optimization frozen"),
    ("V3.9", "v3.9-uncertainty-intelligence", "Uncertainty frozen, no scalar"),
    ("V3.10", "v3.10-pit-wall", "Pit Wall workspace frozen"),
    ("V3.11", "v3.11-mc2-coverage", "Coverage terminal 3678/9644"),
)


def _write(name, doc):
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / name, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def _sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main() -> int:
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- tag registry (repository truth) ----
    registry = {}
    for stage, tag, note in TAGS:
        commit = _git("rev-parse", tag + "^{commit}")
        try:
            objtype = _git("for-each-ref", "--format=%(objecttype)",
                           "refs/tags/" + tag)
        except subprocess.CalledProcessError:
            objtype = "unknown"
        annotation = ""
        if objtype == "tag":
            annotation = _git("for-each-ref",
                              "--format=%(contents:subject)",
                              "refs/tags/" + tag)
        registry[stage] = {
            "stage": stage,
            "tag": tag,
            "commit": commit,
            "annotation": annotation,
            "classification": note,
            "immutable": True,
            "notes": "verified resolvable at freeze time",
        }
    assert len(registry) == 12, len(registry)
    _write("v3_tag_registry.json", {
        "schema_version": "v3-final-tag-registry-v1",
        "tags": registry,
    })

    # ---- programme manifest ----
    _write("v3_programme_manifest.json", {
        "schema_version": "v3-final-manifest-v1",
        "programme": "F1 Intelligence V3",
        "parent_lineage": "V2 consolidated baseline -> V3.1 .. V3.11 "
                          "(see v3_tag_registry.json)",
        "v3_stages": [str(i) for i in range(1, 12)],
        "canonical_product_surface": "Pit Wall (/pit-wall)",
        "canonical_simulation": "MC2-E (raceintel/simulation, "
                                "mc2 kernel + R4/R5 engine family)",
        "canonical_winner_model": "serving path ml/inference over "
            "results/models multilap checkpoints (logreg/hgb/xgboost; "
            "majority-vote ensemble + single-model selection); research "
            "champion Logistic (V3.1B dynamics); V3.3/V3.4 unpromoted",
        "canonical_consensus": "model + simulation comparison "
                               "(PRIMARY_CONSENSUS_SOURCE: V3.1B "
                               "Logistic, MC2); no promoted fusion",
        "canonical_uncertainty": "model-simulation disagreement + "
                                 "finite MC sampling precision; no "
                                 "scalar confidence score",
        "production_mc2_coverage": "3678 / 9644 (38.14%)",
        "unsupported_domains": [
            "track regimes beyond supported green/dry semantics",
            "wet conditions",
            "unresolved missing observations (driver/tyre/temporal)",
            "terminal states where applicable",
        ],
        "frozen_research_only": [
            "XGBoost diversity candidate (V3.3)",
            "V3.4 ensemble recipe (.8/.2, mixed)",
            "V3.5 outcome-distribution candidate (marginals)",
            "V3.11D VSC regime model (insufficient evidence)",
            "V3.2F/H regime precursors (descriptive)",
        ],
    })

    # ---- product authority audit (evidence-backed) ----
    def exists(p):
        assert (ROOT / p).exists(), p
        return p

    audit = {
        "winner_prediction": {
            "verdict": "CANONICAL",
            "serving_path": [exists("ml/inference.py"),
                             exists("ml/config.py"),
                             exists("api/services/prediction_service.py")],
            "artifacts": exists("results/models"),
            "note": "R4 serving path; ensemble = majority vote over "
                    "checkpoints/models (not the V3.4 blend)",
        },
        "mc2": {
            "verdict": "CANONICAL",
            "runtime_path": [exists("raceintel/simulation/engine.py"),
                             exists("raceintel/simulation/mc2/kernel.py"),
                             exists("raceintel/simulation/monte_carlo.py")],
            "note": "MC2-E production runtime; 5000-future campaigns; "
                    "seed 20240101",
        },
        "strategy": {
            "verdict": "AUTHORITY_NOT_YET_FORMALIZED",
            "paths": [exists("raceintel/strategy"),
                      exists("api/v2_strategy_routes.py"),
                      exists("api/v2_strategy_v3_routes.py")],
            "note": "Phase-7 (POST /v2/strategies/compare) and Strategy "
                    "2.0 (POST /v2/strategies/compare-v3) both mounted; "
                    "no repository evidence supersedes either (E finding "
                    "retained)",
        },
        "counterfactuals": {
            "verdict": "CANONICAL",
            "paths": [exists("raceintel/counterfactual"),
                      exists("api/v2_counterfactual_routes.py"),
                      exists("frontend/features/counterfactuals")],
            "note": "V3.7 controlled interventions, simulator-conditional",
        },
        "consensus": {
            "verdict": "CANONICAL",
            "paths": [exists("raceintel/consensus"),
                      exists("api/v2_consensus_service.py")],
            "note": "comparison only; sources V3.1B Logistic + MC2-E; "
                    "no fusion promoted",
        },
        "uncertainty": {
            "verdict": "CANONICAL",
            "paths": [exists("raceintel/uncertainty"),
                      exists("api/v2_uncertainty_routes.py")],
            "note": "V3.9 disagreement + sampling precision; no scalar",
        },
        "spatial_replay": {
            "verdict": "CANONICAL",
            "paths": [exists("raceintel/spatial"),
                      exists("raceintel/replay"),
                      exists("frontend/lib/spatial.ts")],
            "note": "Phase-12 spatial programme + replay intelligence",
        },
        "pit_wall": {
            "verdict": "CANONICAL",
            "paths": [exists("frontend/app/pit-wall/page.tsx"),
                      exists("frontend/features/pit-wall"),
                      exists("api/v2_telemetry_routes.py")],
            "note": "primary integrated race-intelligence workspace",
        },
        "legacy_ml_island": {
            "verdict": "LEGACY_ACTIVE",
            "paths": [exists("ml")],
            "note": "serving seam retained; superseded for science by "
                    "model_lab (retire only post-V3 with ADR)",
        },
        "v2_package": {
            "verdict": "FROZEN_EVIDENCE_ONLY",
            "paths": [exists("v2")],
            "note": "zero importers; tracked baseline, not a product "
                    "surface (post-V3 backlog C4)",
        },
        "vsc_model": {
            "verdict": "RESEARCH_ONLY",
            "paths": [exists("results/v3/v3_11d"),
                      exists("results/v3/v3_11e")],
            "note": "plausible but insufficient evidence; no integration",
        },
    }
    _write("product_authority_audit.json", {
        "schema_version": "v3-final-authority-v1",
        "domains": audit,
    })
    # ---- research/production separation (mechanical) ----
    import io as _io
    import tokenize as _tok

    prod_roots = [ROOT / "raceintel", ROOT / "api", ROOT / "ml"]
    RESEARCH_INFRA = {"raceintel/model_lab"}
    # One known pre-existing edge (frozen long before V3.11; lazy import
    # of a frozen E1.6 utility; zero V3.11/final refs inside the target).
    KNOWN_EDGE = ("api/v2_explanation_service.py",
                  "scripts.replay_feature_matrix")
    _helper = (ROOT / "scripts" / "replay_feature_matrix.py"
               ).read_text(encoding="utf-8")
    assert "v3_11" not in _helper and "v3/final" not in _helper, \
        "known-edge target must not touch final research artifacts"

    forbidden_imports = []
    known_edges_seen = []
    dynamic_imports = []
    for base in prod_roots:
        for py in sorted(base.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    mods = ([a.name or "" for a in node.names]
                            if isinstance(node, ast.Import)
                            else [node.module or ""])
                    for mod in mods:
                        if mod.split(".")[0] in (
                                "scripts", "results", "docs", "tests"):
                            edge = (str(py.relative_to(ROOT)), mod)
                            if edge == KNOWN_EDGE:
                                known_edges_seen.append(edge[0])
                            else:
                                forbidden_imports.append(f"{edge[0]}: {mod}")
                elif isinstance(node, ast.Call):
                    f = node.func
                    name = getattr(f, "id", "") or getattr(f, "attr", "")
                    if name in ("__import__", "import_module"):
                        dynamic_imports.append(str(py.relative_to(ROOT)))

    def _doc_lines(tree):
        lines = set()
        cands = [tree] + [n for n in ast.walk(tree) if isinstance(
            n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        for cand in cands:
            body = getattr(cand, "body", [])
            if (body and isinstance(body[0], ast.Expr) and isinstance(
                    body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                seg = body[0]
                lines.update(range(seg.lineno, seg.end_lineno + 1))
        return lines

    code_refs = []
    comment_refs = []
    research_internal_refs = []
    for base in prod_roots:
        for py in sorted(base.rglob("*.py")):
            if "__pycache__" in py.parts:
                continue
            src = py.read_text(encoding="utf-8", errors="replace")
            if not any(p in src for p in ("v3_11", "results/v3")):
                continue
            try:
                tree = ast.parse(src)
            except SyntaxError:
                continue
            doc = _doc_lines(tree)
            try:
                toks = list(_tok.generate_tokens(_io.StringIO(src
                                                              ).readline))
            except _tok.TokenError:
                continue
            rel = str(py.relative_to(ROOT))
            is_research = any(rel.startswith(r + "/")
                              for r in RESEARCH_INFRA)
            for t in toks:
                if t.type not in (_tok.COMMENT, _tok.STRING):
                    continue
                if not any(p in t.string for p in ("v3_11",
                                                   "results/v3")):
                    continue
                hit = f"{rel}:{t.start[0]}"
                if t.type == _tok.COMMENT or t.start[0] in doc:
                    comment_refs.append(hit)
                elif is_research:
                    research_internal_refs.append(hit)
                else:
                    code_refs.append(hit)
    fe = ROOT / "frontend"
    fe_hits = []
    if fe.exists():
        for pat in ("*.ts", "*.tsx"):
            for src in sorted(fe.rglob(pat)):
                if any(seg in ("node_modules", ".next", "dist", "build")
                       for seg in src.parts):
                    continue
                if ".test." in src.name or src.name.endswith(".spec.ts"):
                    continue
                lines = src.read_text(encoding="utf-8",
                                      errors="replace").splitlines()
                for i, ln in enumerate(lines, 1):
                    code = ln.split("//")[0]
                    if "results/v3" in code:
                        fe_hits.append(f"{src.relative_to(ROOT)}:{i}")
    research_imports_prod = 0
    for sc in sorted((ROOT / "scripts").glob("v3_*.py")):
        if "raceintel" in sc.read_text(encoding="utf-8", errors="replace"):
            research_imports_prod += 1
    verdict = ("PASS" if not forbidden_imports and not code_refs
               and not fe_hits and known_edges_seen else "FAIL")
    _write("research_production_separation.json", {
        "schema_version": "v3-final-separation-v1",
        "verdict": verdict,
        "forbidden_import_edges": forbidden_imports,
        "known_preexisting_edge": {
            "edge": list(KNOWN_EDGE),
            "sites": sorted(set(known_edges_seen)),
            "justification": "lazy (function-level) import of frozen "
                "E1.6 offline cache utility; predates V3.11; target has "
                "zero v3_11/final refs; removal would be a behavior "
                "change, forbidden in V3 Final; post-V3 backlog (API "
                "seam / scripts forward rule)",
        },
        "production_code_refs_to_research_paths": code_refs,
        "comment_or_docstring_refs_non_edges": comment_refs,
        "research_internal_reads_model_lab": research_internal_refs,
        "frontend_code_hits": fe_hits,
        "dynamic_import_sites_reviewed": sorted(set(dynamic_imports)),
        "research_scripts_importing_production": research_imports_prod,
        "rule": "research may import production; production must not "
                "import results/docs/scripts/tests evidence",
    })
    assert verdict == "PASS", (forbidden_imports, code_refs, fe_hits,
                               known_edges_seen)

    # ---- scientific claim registry ----
    def _doc(*cands):
        for c in cands:
            hits = sorted((ROOT / "docs").glob(c))
            if hits:
                return str(hits[0].relative_to(ROOT))
        raise AssertionError(cands)

    claims = {
        "winner_prediction": {
            "allowed": "pre-race/lap-K winner probabilities from the "
                       "serving multilap checkpoints",
            "prohibited": "certainty about any single race outcome",
            "evidence": [_doc("V3_1B*.md"), "results/models"],
            "status": "production",
        },
        "mc2_simulation": {
            "allowed": "distribution of simulated futures over 3678 "
                       "eligible states (5000 futures)",
            "prohibited": "coverage of all 9644 states; support for "
                          "wet/track/terminal-missing regimes",
            "evidence": [_doc("V3_2*.md"),
                         "results/v3/v3_11_final/coverage_reconciliation.json"],
            "status": "production (eligible states only)",
        },
        "strategy": {
            "allowed": "simulator-conditional outcome comparison under "
                       "controlled interventions",
            "prohibited": "optimal strategy; causal historical effect",
            "evidence": [_doc("V3_6*.md")],
            "status": "production (authority not yet formalized: "
                      "Phase-7 vs 2.0 both mounted)",
        },
        "counterfactual": {
            "allowed": "controlled simulator intervention comparison",
            "prohibited": "alternate-history truth",
            "evidence": [_doc("V3_7*.md")],
            "status": "production",
        },
        "consensus": {
            "allowed": "model/simulation agreement/disagreement display",
            "prohibited": "fused calibrated probability",
            "evidence": [_doc("V3_8A*.md", "V3_8*.md")],
            "status": "production (comparison only)",
        },
        "uncertainty": {
            "allowed": "model-simulation disagreement and MC sampling "
                       "precision",
            "prohibited": "scalar confidence/quality score",
            "evidence": [_doc("V3_9*.md")],
            "status": "production",
        },
        "vsc": {
            "allowed": "research suggests plausible pace/order/"
                       "withdrawal structure",
            "prohibited": "production-supported VSC simulation",
            "evidence": [_doc("V3_11E*.md", "V3_11D*.md"),
                         "results/v3/v3_11_final/terminal_decision.json"],
            "status": "research-only (insufficient evidence)",
        },
        "sc_yellow_red_wet": {
            "allowed": "none (regimes characterized as unsupported)",
            "prohibited": "any production simulation claim",
            "evidence": [_doc("V3_11_MC2*.md")],
            "status": "not started",
        },
    }
    for _c in claims.values():
        for _e in _c["evidence"]:
            assert (ROOT / _e).exists(), _e
    _write("scientific_claim_registry.json", {
        "schema_version": "v3-final-claims-v1",
        "claims": claims,
    })

    # ---- artifact inventory (sizes at freeze time) ----
    inv_roots = {
        "results": "FROZEN_RESULT",
        "runtime_artifacts": "REPRODUCIBLE_ARTIFACT",
        "data/interim": "REPRODUCIBLE_ARTIFACT",
        "data/processed": "REPRODUCIBLE_ARTIFACT",
        "data/v2": "FROZEN_RESULT",
        "data/v3": "FROZEN_RESULT",
        "data/spatial": "REPRODUCIBLE_ARTIFACT",
        "data/raw/fastf1_cache": "CACHE",
        "graphify-out": "REPRODUCIBLE_ARTIFACT",
    }
    inv = {}
    for rel, cls in inv_roots.items():
        base = ROOT / rel
        n, size = 0, 0
        if base.exists():
            for f in base.rglob("*"):
                try:
                    if f.is_file() and not f.is_symlink():
                        n += 1
                        size += f.stat().st_size
                except OSError:
                    continue
        inv[rel] = {"class": cls, "files": n, "bytes": size,
                    "exists": base.exists()}
    _write("artifact_inventory.json", {
        "schema_version": "v3-final-inventory-v1",
        "policy": "inventory only; no deletions in V3 Final; cleanup is "
                  "a post-V3 engineering decision",
        "roots": inv,
    })

    # ---- test/guard audit (static; Tier-1 section filled on re-run) ----
    guard_files = [
        "scripts/run_ci_tests.py",
        "tests/test_perf_mc2_freeze.py",
        "tests/test_perf_mc2_p0.py",
        "tests/test_v3_8h_freeze.py",
        "tests/test_v3_9e_freeze.py",
        "tests/test_v3_final_freeze.py",
    ]
    guard_inventory = {}
    for gf in guard_files:
        p = ROOT / gf
        guard_inventory[gf] = {
            "exists": p.exists(),
            "sha256": _sha_file(p) if p.exists() else None,
        }
    freeze_tests = sorted(
        str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("*freeze*.py"))
    poison_tests = sorted(
        str(p.relative_to(ROOT)) for p in (ROOT / "tests").glob("*poison*.py"))
    tier1 = {"status": "PENDING",
             "note": "re-run after the authoritative Tier-1 writes "
                     "/tmp/tier1_v3final.log"}
    tier1_log = Path("/tmp/tier1_v3final.log")
    if tier1_log.exists():
        tail = tier1_log.read_text(encoding="utf-8",
                                   errors="replace")[-4000:]
        tier1 = {"status": "RECORDED", "log": str(tier1_log),
                 "tail": tail}
    _write("test_guard_audit.json", {
        "schema_version": "v3-final-guards-v1",
        "expected_collection": 5319,
        "collection_formula": "5268 base + 21 (E) + 16 (F) + 14 "
                              "(final freeze tests)",
        "policy": "no test bypassed for convenience; skips/xfails only "
                  "where pre-existing and documented in the Tier-1 record",
        "guard_inventory": guard_inventory,
        "freeze_test_files": freeze_tests,
        "temporal_poison_test_files": poison_tests,
        "tier1": tier1,
    })

    # ---- V3 scientific card ----
    _write("v3_scientific_card.json", {
        "schema_version": "v3-final-card-v1",
        "programme": "F1 Intelligence V3",
        "frozen_status": "V3_PROGRAMME_FROZEN",
        "canonical_parent": "v3.11-mc2-coverage "
                            "(766496322c393f5341f1fb46bbd2cd8d43d80dd1)",
        "stage_registry": "results/v3/final/v3_tag_registry.json",
        "production_mc2_coverage": "3678 / 9644 (38.14%)",
        "canonical_prediction_model": "ml/inference serving path over "
            "results/models multilap checkpoints (logreg/hgb/xgboost)",
        "canonical_simulation": "MC2-E "
                                "(raceintel/simulation, seed 20240101)",
        "product_surface": "Pit Wall (/pit-wall)",
        "promoted_capabilities": [
            "winner prediction", "MC2 simulation (eligible states)",
            "strategy comparison", "counterfactuals", "consensus "
            "comparison", "uncertainty (disagreement + precision)",
            "spatial replay", "Pit Wall workspace",
        ],
        "research_only_capabilities": [
            "V3.3 XGBoost diversity", "V3.4 ensemble blend",
            "V3.5 outcome marginals", "V3.11D VSC model",
        ],
        "unsupported_regimes": ["wet", "VSC", "SC", "yellow",
                                "red/restart", "unresolved-missing",
                                "terminal (where applicable)"],
        "validation_result": "authoritative Tier-1 + frontend + smoke + "
                             "perf recorded in the V3 Final freeze report",
        "tag_target": "v3-final (created at freeze commit)",
    })

    # ---- release manifest (reproducibility snapshot) ----
    try:
        from importlib import metadata as _md
    except ImportError:
        _md = None

    def _dep(name):
        if _md is None:
            return "unknown"
        try:
            return _md.version(name)
        except Exception:
            return "not-installed"

    try:
        node_v = subprocess.run(
            ["node", "--version"], capture_output=True, text=True,
            check=True).stdout.strip()
    except Exception:
        node_v = "unknown"
    models_dir = ROOT / "results" / "models"
    model_files = sorted(p.name + ("/" if p.is_dir() else "")
                         for p in models_dir.iterdir()) \
        if models_dir.exists() else []
    gside = ROOT / "results" / "v3" / "final" / "graphify_counts.json"
    graphify_state = {"status": "PENDING",
                      "note": "counts sidecar written from graphify "
                              "update stdout, then generator re-run"}
    if gside.exists():
        graphify_state = {"status": "RECORDED",
                          **json.loads(gside.read_text(encoding="utf-8"))}
    _write("release_manifest.json", {
        "schema_version": "v3-final-release-v1",
        "python": sys.version.split()[0],
        "python_full": sys.version,
        "dependencies": {
            "numpy": _dep("numpy"),
            "pandas": _dep("pandas"),
            "scipy": _dep("scipy"),
            "scikit-learn": _dep("scikit-learn"),
            "xgboost": _dep("xgboost"),
            "fastapi": _dep("fastapi"),
            "lightgbm": _dep("lightgbm"),
        },
        "node": node_v,
        "frontend_lock_sha256": _sha_file(
            ROOT / "frontend" / "package-lock.json"),
        "model_artifacts": {"dir": "results/models",
                            "files": len(model_files),
                            "names": model_files},
        "seeds": {
            "mc2_master": 20240101,
            "v3_11e_bootstrap": 7,
            "note": "no retraining in V3 Final; seeds are historical "
                    "provenance",
        },
        "config_identities": {
            "ml/config.py": _sha_file(ROOT / "ml" / "config.py"),
            "api/config.py": _sha_file(ROOT / "api" / "config.py"),
        },
        "graphify": graphify_state,
    })

    # ---- identity registry (no circularity: hashes peers, not self) ----
    idents = {}
    for name in ("v3_programme_manifest.json", "v3_scientific_card.json",
                 "release_manifest.json", "scientific_claim_registry.json",
                 "product_authority_audit.json"):
        idents[name] = _sha_file(OUT / name)
    _write("identity_registry.json", {
        "schema_version": "v3-final-identities-v1",
        "sha256": idents,
        "note": "re-run generator after Tier-1/graphify refresh, then "
                "copy these identities into "
                "docs/V3_FINAL_PROGRAMME_SYNTHESIS.md",
    })

    print(json.dumps({
        "status": "OK", "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
