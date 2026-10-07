"""V3.2J immutable raw TimingData driver-status adapter (read-only science).

Parses pinned historical Formula 1 live-timing ``TimingData.jsonStream``
deltas and reconstructs the causal per-driver ``Retired`` state:

    status(T) = latest causally observed Retired value at or before T.

Contract (``v3.2j-driver-status-v1``, EXCLUSION-ONLY):

- ``True`` at T proves retirement (driver may be excluded).
- ``False`` or unknown proves NOTHING (never proves activity).
- Missing ``Retired`` key preserves prior state (never read as False).
- Deltas after T are never inspected.
- First-``True`` is never sticky: ``True -> False`` clearings take
  effect and a driver may re-enter the unknown/active field.
- ``Stopped`` / ``InPit`` / ``PitOut`` / absence / position-null /
  final labels are never retirement evidence (counted for diagnostics
  only, never consulted by the runtime rule).

Stdlib-only, no RNG, no network, no result labels. The stochastic
kernel never imports this module; presence resolution consumes the
derived artifacts through :class:`DriverStatusResolver`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

__all__ = [
    "RAW_ADAPTER_VERSION",
    "STATUS_CONTRACT_VERSION",
    "STATUS_CONTRACT_ID",
    "UNKNOWN",
    "ParseDiagnostics",
    "clock_to_seconds",
    "parse_timing_stream",
    "build_retired_transitions",
    "retired_known_at",
    "DriverStatusResolver",
    "load_status_corpus",
    "load_unreliable_windows",
]

#: Immutable adapter identity (pins byte-level parse semantics).
RAW_ADAPTER_VERSION = "v3.2j-raw-adapter-v1"

#: Exclusion-only status contract identity.
STATUS_CONTRACT_VERSION = "v3.2j-driver-status-v1"
STATUS_CONTRACT_ID = STATUS_CONTRACT_VERSION

#: Unknown state: no causally observed Retired value at or before T.
UNKNOWN = None


@dataclass
class ParseDiagnostics:
    """Deterministic parse census for one stream."""

    n_lines: int = 0
    n_messages: int = 0
    n_retired_updates: int = 0
    n_stopped_updates: int = 0
    n_inpit_updates: int = 0
    n_pitout_updates: int = 0
    n_malformed_rows: int = 0
    n_non_dict_deltas: int = 0
    drivers_seen: tuple = ()


def clock_to_seconds(prefix: str) -> float:
    """Convert a 12-char ``HH:MM:SS.mmm`` session-clock prefix to seconds."""
    h, m, s = prefix.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_timing_stream(text: str) -> tuple[list, ParseDiagnostics]:
    """Parse one pinned ``TimingData.jsonStream`` body.

    Returns ``(events, diagnostics)`` where ``events`` is a chronologically
    ordered list of ``(t_seconds, driver_key, value)`` for every boolean
    ``Lines[driver].Retired`` update (one entry per delta that carries
    the key, including repeats). Tied timestamps keep file order
    (stable sort), so reconstruction is deterministic. Malformed rows
    are counted and skipped; non-dict deltas / non-dict ``Lines``
    payloads fail closed with ``ValueError``.
    """
    diag = ParseDiagnostics()
    events: list[tuple[float, str, bool]] = []
    drivers: set[str] = set()
    order = 0
    staged: list[tuple[float, int, str, bool]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        diag.n_lines += 1
        if len(line) < 13:
            diag.n_malformed_rows += 1
            continue
        prefix, body = line[:12], line[12:]
        try:
            t = clock_to_seconds(prefix)
        except (ValueError, AttributeError):
            diag.n_malformed_rows += 1
            continue
        try:
            delta = json.loads(body)
        except json.JSONDecodeError:
            diag.n_malformed_rows += 1
            continue
        if not isinstance(delta, dict):
            diag.n_non_dict_deltas += 1
            raise ValueError("non-dict TimingData delta")
        lines = delta.get("Lines")
        if lines is None:
            diag.n_messages += 1
            continue
        if not isinstance(lines, dict):
            diag.n_non_dict_deltas += 1
            raise ValueError("non-dict TimingData Lines payload")
        diag.n_messages += 1
        for drv, entry in lines.items():
            if not isinstance(entry, dict):
                continue
            key = str(drv)
            drivers.add(key)
            if isinstance(entry.get("Stopped"), bool):
                diag.n_stopped_updates += 1
            if isinstance(entry.get("InPit"), bool):
                diag.n_inpit_updates += 1
            if isinstance(entry.get("PitOut"), bool):
                diag.n_pitout_updates += 1
            value = entry.get("Retired")
            if isinstance(value, bool):
                diag.n_retired_updates += 1
                staged.append((t, order, key, value))
                order += 1
    staged.sort(key=lambda e: (e[0], e[1]))
    events = [(t, key, value) for t, _, key, value in staged]
    diag.drivers_seen = tuple(sorted(drivers))
    return events, diag


def build_retired_transitions(
        events: list) -> dict[str, list[tuple[float, bool]]]:
    """Compress raw Retired updates to per-driver change transitions.

    Only value CHANGES are kept (``[(t, bool)]`` sorted by time); repeats
    of the same value carry no state information. Missing keys never
    appear here (the parser only emits present boolean updates), so
    absence can never clear a state.
    """
    current: dict[str, bool] = {}
    transitions: dict[str, list[tuple[float, bool]]] = {}
    for t, driver, value in events:
        if current.get(driver, UNKNOWN) != value:
            transitions.setdefault(driver, []).append((t, value))
            current[driver] = value
    return transitions


def retired_known_at(transitions: list | tuple | None,
                     T: float) -> bool | None:
    """Causal Retired state at checkpoint T for one driver.

    Latest transition with ``t <= T`` wins; no transition at or before
    T means UNKNOWN (``None``). Exact-timestamp equality counts
    (``<=``). Transitions after T are never inspected.
    """
    if not transitions:
        return UNKNOWN
    state: bool | None = UNKNOWN
    for t, value in transitions:
        if t <= T:
            state = value
        else:
            break
    return state


class DriverStatusResolver:
    """Runtime resolver over pinned derived status artifacts.

    ``corpus`` maps ``race_id -> {driver_id -> [(t, bool)]}``. Answers
    only the exclusion-only question ``retired_known_at``; unknown
    races/drivers/T return ``None`` (fail closed: no inference).
    """

    def __init__(self, corpus: dict) -> None:
        self._corpus = {
            race: {drv: tuple((float(t), bool(v)) for t, v in seq)
                   for drv, seq in drivers.items()}
            for race, drivers in corpus.items()
        }

    def retired_known_at(self, race_id: str, driver_id: str,
                         T: float) -> bool | None:
        """``True`` iff latest Retired value for driver at or before T."""
        seq = self._corpus.get(race_id, {}).get(driver_id)
        return retired_known_at(seq, float(T))

    @property
    def race_ids(self) -> tuple:
        """Races covered by this corpus."""
        return tuple(sorted(self._corpus))


def load_status_corpus(status_dir) -> DriverStatusResolver:
    """Load pinned derived per-race status artifacts (local files only).

    No network, no result labels. Unknown/missing races simply resolve
    UNKNOWN (fail closed) via the resolver's ``.get`` lookups.
    """
    import json as _json
    from pathlib import Path as _Path

    corpus: dict = {}
    for path in sorted(_Path(status_dir).glob("*.json")):
        artifact = _json.loads(path.read_text(encoding="utf-8"))
        if artifact.get("status_contract_version") != STATUS_CONTRACT_VERSION:
            raise ValueError(
                f"status contract mismatch in {path.name}: "
                f"{artifact.get('status_contract_version')!r}")
        corpus[artifact["race_id"]] = artifact["transitions"]
    return DriverStatusResolver(corpus)


def load_unreliable_windows(path) -> dict:
    """Load pinned unreliable-window map: ``(race_id, driver_id) -> [(a,b)]``.

    A checkpoint T inside a window must not use that driver's Retired
    claim for exclusion (the source retracted it while the driver
    demonstrably continued). Build-time pinning from stream + lap
    continuation only; no result labels.
    """
    import json as _json

    doc = _json.loads(open(path, encoding="utf-8").read())
    out: dict = {}
    for key, spans in doc.get("windows", {}).items():
        race_id, _, driver_id = key.partition("|")
        out[(race_id, driver_id)] = [(float(a), float(b)) for a, b in spans]
    return out
