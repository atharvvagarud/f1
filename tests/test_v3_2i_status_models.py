"""V3.2I status-source models (source-safe, normal CI).

Pure-logic pins: causal state-at-T reconstruction invariants (incl.
the measured Ricciardo flip), stream-clock parsing, scorecard verdict
vocabulary. No corpus, no network, no simulation.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from analyze_v3_2i_status import hms_to_s, state_at_T  # noqa: E402

ALLOWED_VERDICTS = {"VIABLE", "PARTIALLY_VIABLE", "VALIDATION_ONLY",
                    "EVALUATION_ONLY", "NOT_VIABLE", "UNKNOWN"}
ALLOWED_DECISIONS = {"EXTERNAL_STATUS_SOURCE_VIABLE",
                     "EXTERNAL_STATUS_SOURCE_PARTIALLY_VIABLE",
                     "NO_EXTERNAL_STATUS_SOURCE_FOUND",
                     "LOCAL_RAW_STATUS_SOURCE_VIABLE",
                     "LOCAL_RAW_STATUS_SOURCE_PARTIALLY_VIABLE"}


def test_clock_parse():
    assert hms_to_s("00:00:04.180") == 4.18
    assert hms_to_s("02:28:36.888") == 2 * 3600 + 28 * 60 + 36.888


def test_state_at_T_basic():
    seq = [{"t": 100.0, "value": False}, {"t": 200.0, "value": True}]
    assert state_at_T(seq, 50.0) is False
    assert state_at_T(seq, 200.0) is True
    assert state_at_T([], 999.0) is False


def test_state_at_T_ricciardo_flip():
    """Measured BEL 2018 transient: true@[1402] cleared@[1671]
    re-set@[4812]. First-true alone would wrongly retire him for
    T in [1402, 1671); state-at-T does not."""
    seq = [{"t": 5.9, "value": False}, {"t": 1402.9, "value": True},
           {"t": 1671.3, "value": False}, {"t": 4812.9, "value": True}]
    assert state_at_T(seq, 1402.8) is False
    assert state_at_T(seq, 1500.0) is True  # transient window: known hazard
    assert state_at_T(seq, 2000.0) is False  # cleared: racing again
    assert state_at_T(seq, 4812.9) is True  # final retirement


def test_state_at_T_post_race_safe():
    """Post-race true (Alonso CAN 2018 style) never affects race-T."""
    seq = [{"t": 5.0, "value": False}, {"t": 5973.0, "value": True}]
    assert state_at_T(seq, 5855.0) is False
    assert state_at_T(seq, 5973.0) is True


def test_verdict_vocabulary():
    assert ALLOWED_VERDICTS == {"VIABLE", "PARTIALLY_VIABLE",
                                "VALIDATION_ONLY", "EVALUATION_ONLY",
                                "NOT_VIABLE", "UNKNOWN"}
    assert "LOCAL_RAW_STATUS_SOURCE_PARTIALLY_VIABLE" in ALLOWED_DECISIONS


def test_no_runtime_status_imports():
    """V3.2I was research-only; V3.2J sanctions exactly one runtime
    consumer of the raw-timing format: the pinned immutable adapter
    (raceintel/simulation/driver_status.py, v3.2j-raw-adapter-v1), which
    reads local derived artifacts only. The runtime must still reference
    no I research artefact, no alternative status source, and no
    status-feed fetcher (no network client imports, no feed host)."""
    import ast

    sanctioned = {"driver_status.py"}
    banned_imports = {"urllib", "urllib3", "socket", "requests", "http",
                      "httpx", "fastf1"}
    for base in (ROOT / "raceintel" / "simulation", ROOT / "api"):
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            assert "v3_2i" not in text
            for token in ("openf1", "jolpica", "ergast", "livetiming",
                          "formula1.com", "fastf1"):
                assert token not in lowered, (path.name, token)
            if "jsonstream" in lowered:
                assert path.name in sanctioned, path.name
            tree = ast.parse(text)
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module.split(".")[0])
            assert not (imported & banned_imports), (
                path.name, sorted(imported & banned_imports))
