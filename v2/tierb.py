"""Tier-B historical normalisation + season adapter (D4).

Pure normalisation (Jolpica/Ergast-shaped dicts -> exact D2 Tier-B frames)
is stdlib + pandas and fully offline-testable. The season adapter
(``make_tierb_season_adapter`` / ``tierb_season_adapter``) is the thin D3
``AdapterFn`` that fetches one season through ``v2.jolpica`` and returns
the seven Tier-B frames for ``run_unit`` to validate, write and manifest.

Normalisation rules (D4 §8, D2 contracts authoritative):
- Source facts preserved; nothing invented. Source null / missing ->
  canonical null wherever the contract permits nullability.
- Ergast-style sentinels (``-1`` / ``"-1"`` via auto_cast, ``""``) ->
  canonical null. Numeric strings -> typed values only when semantically
  valid; malformed values -> null, NEVER zero.
- ``positionText`` / ``status`` preserved verbatim (DNF/DNS/DSQ/NC codes
  included). Tier-B carries NO derived dnf boolean by contract design:
  classification semantics stay evidence-backed and unreduced.
- Identity is source-native slugs (``circuitId`` / ``driverId`` /
  ``constructorId``); display names, codes and numbers are attributes.
- Constructor grain is (constructor_id, season): renames are separate rows.
  NO automatic cross-season lineage is derived here — see
  ``CONSTRUCTOR_LINEAGE_DECISION`` (D4 §12): source IDs preserved, curated
  mapping explicitly deferred rather than guessed from similar names.
- Dedupe is deterministic (first occurrence wins, source order kept) with
  counts reported; parents are never manufactured to satisfy FKs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from v2 import contracts as C
from v2.errors import IngestionError
from v2.ingestion import AdapterResult, UnitContext
from v2.jolpica import (JolpicaClient, season_constructors_endpoint,
                        season_constructor_standings_endpoint,
                        season_drivers_endpoint, season_driver_standings_endpoint,
                        season_results_endpoint, season_schedule_endpoint)

TIERB_ENTITIES = ("hist_seasons", "hist_circuits", "hist_drivers",
                 "hist_constructors", "hist_races", "hist_results",
                 "hist_standings")

# D4 §12 constructor-lineage decision (evidence-backed, minimal):
# source constructor slugs are season-scoped rows per the D2 contract and
# are NEVER merged on name similarity. A curated cross-season lineage map
# is explicit derived metadata for a later stage — not guessed here.
CONSTRUCTOR_LINEAGE_DECISION = (
    "preserve source constructor IDs season-scoped; no automatic lineage; "
    "curated mapping deferred to a later stage (see architecture docs §D4)")

# D4 §15 standings-grain decision: season-final snapshots ONLY
# (round_no = final championship round). Round-by-round snapshots are NOT
# mixed in; the PK (season, round_no, standing_type, entrant_id) keeps the
# grain explicit and future round-level ingestion additive, not conflicting.
STANDINGS_GRAIN_DECISION = (
    "season-final snapshots only; round-by-round deferred")

STANDING_TYPES = ("driver", "constructor")


def tierb_unit_id(season: int) -> str:
    return f"tierb-{int(season)}"


# --------------------------------------------------------------------------
# Scalar coercion: honest nulls, typed values, never zero-fill.
# --------------------------------------------------------------------------

_NULL_TOKENS = frozenset({"", "-", "n/a", "N/A", "na", "NA", "none", "None",
                          "NONE", "null", "NULL", "unknown", "Unknown",
                          "UNKNOWN"})


def clean_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and value != value:  # NaN -> missing
        return None
    text = str(value).strip()
    if not text or text in _NULL_TOKENS:
        return None
    return text


def to_int_or_null(value: object) -> int | None:
    """Ergast ints (incl. ``-1`` sentinel) -> int | None.

    ``grid == 0`` (pit-lane start) is a genuine source fact and is kept.
    Malformed values -> None, never 0. Bools are rejected (not counts).
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return None if value == -1 else value
    if isinstance(value, float):
        if value != value:  # NaN
            return None
        return None if int(value) == -1 else int(value)
    text = str(value).strip()
    if not text or text in _NULL_TOKENS:
        return None
    try:
        parsed = int(text)
    except ValueError:
        try:
            as_float = float(text)
        except ValueError:
            return None
        if as_float != as_float or not as_float.is_integer():
            return None
        parsed = int(as_float)
    return None if parsed == -1 else parsed


def to_float_or_null(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and value != value:
            return None
        return float(value)
    text = str(value).strip()
    if not text or text in _NULL_TOKENS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Entity normalisation (pure; list[dict] in -> DataFrame out).
# --------------------------------------------------------------------------

def _frame(rows: list[dict], entity: str) -> pd.DataFrame:
    contract = C.get_table(entity)
    return pd.DataFrame(rows, columns=contract.column_names())


def _dedupe(rows: list[dict], key: tuple[str, ...]) -> tuple[list[dict], int]:
    seen: set = set()
    unique: list[dict] = []
    dupes = 0
    for row in rows:
        k = tuple(row.get(col) for col in key)
        if k in seen:
            dupes += 1
            continue
        seen.add(k)
        unique.append(row)
    return unique, dupes


def normalize_seasons(seasons: list) -> tuple[pd.DataFrame, int]:
    """``seasons``: iterable of year ints/strs (existence already proven by
    a non-empty upstream schedule — never inferred from local coverage)."""
    rows = [{"season": to_int_or_null(s)} for s in seasons]
    rows = [r for r in rows if r["season"] is not None]
    unique, dupes = _dedupe(rows, C.HIST_SEASONS.primary_key)
    return _frame(unique, "hist_seasons"), dupes


def normalize_circuits(circuits: list[dict]) -> tuple[pd.DataFrame, int]:
    """Identity = source-native ``circuitId``; names are attributes, so a
    historical rename of the same venue never forks identity."""
    rows = []
    for c in circuits:
        if not isinstance(c, dict):
            continue
        loc = c.get("Location") or {}
        if not isinstance(loc, dict):
            loc = {}
        rows.append({
            "circuit_id": clean_str(c.get("circuitId")),
            "circuit_name": clean_str(c.get("circuitName")),
            "locality": clean_str(loc.get("locality")),
            "country": clean_str(loc.get("country")),
            "latitude": to_float_or_null(loc.get("lat")),
            "longitude": to_float_or_null(loc.get("long")),
        })
    rows = [r for r in rows if r["circuit_id"] is not None]
    unique, dupes = _dedupe(rows, C.HIST_CIRCUITS.primary_key)
    return _frame(unique, "hist_circuits"), dupes


def normalize_drivers(drivers: list[dict]) -> tuple[pd.DataFrame, int]:
    """Identity = source-native ``driverId``. Code / permanent number /
    display names are attributes, never keys; historical gaps stay null."""
    rows = []
    for d in drivers:
        if not isinstance(d, dict):
            continue
        rows.append({
            "driver_id": clean_str(d.get("driverId")),
            "driver_code": clean_str(d.get("code")),
            "permanent_number": to_int_or_null(d.get("permanentNumber")),
            "given_name": clean_str(d.get("givenName")),
            "family_name": clean_str(d.get("familyName")),
            "date_of_birth": clean_str(d.get("dateOfBirth")),
            "nationality": clean_str(d.get("nationality")),
        })
    rows = [r for r in rows if r["driver_id"] is not None]
    unique, dupes = _dedupe(rows, C.HIST_DRIVERS.primary_key)
    return _frame(unique, "hist_drivers"), dupes


def normalize_constructors(constructors: list[dict],
                           season: int) -> tuple[pd.DataFrame, int]:
    """Season-scoped rows: the same slug in two seasons is two rows, and a
    rename is a new identity — never merged on name similarity (D4 §12)."""
    rows = []
    for c in constructors:
        if not isinstance(c, dict):
            continue
        rows.append({
            "constructor_id": clean_str(c.get("constructorId")),
            "season": int(season),
            "constructor_name": clean_str(c.get("name")),
            "nationality": clean_str(c.get("nationality")),
        })
    rows = [r for r in rows if r["constructor_id"] is not None]
    unique, dupes = _dedupe(rows, C.HIST_CONSTRUCTORS.primary_key)
    return _frame(unique, "hist_constructors"), dupes


def normalize_races(races: list[dict]) -> tuple[pd.DataFrame, int]:
    """Historical race metadata. Missing times/names stay null; unusual
    rounds kept as given; no rich Race-session records are created."""
    rows = []
    for r in races:
        if not isinstance(r, dict):
            continue
        circuit = r.get("Circuit") or {}
        if not isinstance(circuit, dict):
            circuit = {}
        rows.append({
            "season": to_int_or_null(r.get("season")),
            "round_no": to_int_or_null(r.get("round")),
            "race_name": clean_str(r.get("raceName")),
            "circuit_id": clean_str(circuit.get("circuitId")),
            "race_date": clean_str(r.get("date")),
        })
    rows = [r for r in rows
            if r["season"] is not None and r["round_no"] is not None]
    unique, dupes = _dedupe(rows, C.HIST_RACES.primary_key)
    return _frame(unique, "hist_races"), dupes


def normalize_results(races: list[dict]) -> tuple[pd.DataFrame, int]:
    """Official post-race outcomes, one row per driver per race.

    ``position``/``grid``/``laps`` are typed only when semantically valid
    (``grid == 0`` = pit-lane start, kept); ``position_text``/``status``
    verbatim (``R``/``D``/``F``/``W``/``N``/... codes preserved). No
    ``status != Finished => DNF`` reduction is performed anywhere.
    """
    rows = []
    for r in races:
        if not isinstance(r, dict):
            continue
        season = to_int_or_null(r.get("season"))
        round_no = to_int_or_null(r.get("round"))
        if season is None or round_no is None:
            continue
        results = r.get("Results") or []
        if not isinstance(results, list):
            continue
        for res in results:
            if not isinstance(res, dict):
                continue
            driver = res.get("Driver") or {}
            constructor = res.get("Constructor") or {}
            if not isinstance(driver, dict):
                driver = {}
            if not isinstance(constructor, dict):
                constructor = {}
            rows.append({
                "season": season,
                "round_no": round_no,
                "driver_id": clean_str(driver.get("driverId")),
                "constructor_id": clean_str(constructor.get("constructorId")),
                "grid": to_int_or_null(res.get("grid")),
                "position": to_int_or_null(res.get("position")),
                "position_text": clean_str(res.get("positionText")),
                "points": to_float_or_null(res.get("points")),
                "laps": to_int_or_null(res.get("laps")),
                "status": clean_str(res.get("status")),
            })
    rows = [r for r in rows if r["driver_id"] is not None]
    unique, dupes = _dedupe(rows, C.HIST_RESULTS.primary_key)
    return _frame(unique, "hist_results"), dupes


def _normalize_standings_list(entries: list, standing_type: str, season: int,
                              round_no: int) -> list[dict]:
    rows = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if standing_type == "driver":
            entrant = e.get("Driver") or {}
        else:
            entrant = e.get("Constructor") or {}
        if not isinstance(entrant, dict):
            entrant = {}
        key = "driverId" if standing_type == "driver" else "constructorId"
        rows.append({
            "season": int(season),
            "round_no": int(round_no),
            "standing_type": standing_type,
            "entrant_id": clean_str(entrant.get(key)),
            "standing_position": to_int_or_null(e.get("position")),
            "standing_points": to_float_or_null(e.get("points")),
            "wins": to_int_or_null(e.get("wins")),
        })
    return [r for r in rows if r["entrant_id"] is not None]


def normalize_standings(driver_lists: list[dict],
                        constructor_lists: list[dict],
                        season: int, round_no: int) -> tuple[pd.DataFrame, int]:
    """Season-final snapshots (see STANDINGS_GRAIN_DECISION). Driver and
    constructor types share one table, distinguished by ``standing_type``
    — never silently mixed. Ranks/points/wins verbatim from source."""
    driver_entries = _final_standings_entries(driver_lists, "DriverStandings")
    constructor_entries = _final_standings_entries(
        constructor_lists, "ConstructorStandings")
    rows = (_normalize_standings_list(driver_entries, "driver", season,
                                      round_no)
            + _normalize_standings_list(constructor_entries, "constructor",
                                        season, round_no))
    unique, dupes = _dedupe(rows, C.HIST_STANDINGS.primary_key)
    return _frame(unique, "hist_standings"), dupes


def _final_standings_entries(lists: list, key: str) -> list:
    """Pick the final snapshot when several are returned (max round);
    normally exactly one list is present for season-final endpoints."""
    if not lists:
        return []
    if len(lists) == 1:
        entries = lists[0].get(key) if isinstance(lists[0], dict) else None
        return entries if isinstance(entries, list) else []
    best: list = []
    best_round = -1
    for lst in lists:
        if not isinstance(lst, dict):
            continue
        entries = lst.get(key)
        if not isinstance(entries, list):
            continue
        rnd = to_int_or_null(lst.get("round"))
        if rnd is not None and rnd >= best_round:
            best, best_round = entries, rnd
    return best


# --------------------------------------------------------------------------
# Referential integrity (measured, never repaired by invention).
# --------------------------------------------------------------------------

@dataclass
class IntegrityReport:
    """Measured Tier-B relationship health for one season unit."""

    counts: dict = field(default_factory=dict)
    fk_violations: list[dict] = field(default_factory=list)
    missingness: dict = field(default_factory=dict)
    duplicate_pks: dict = field(default_factory=dict)

    def has_violations(self) -> bool:
        return bool(self.fk_violations)

    def summary(self) -> str:
        parts = [f"{e}={n}" for e, n in sorted(self.counts.items())]
        if self.fk_violations:
            parts.append(f"fk_violations={len(self.fk_violations)}")
        return "tierb integrity: " + ", ".join(parts)


def _col_set(frame: pd.DataFrame, col: str) -> set:
    if col not in frame.columns:
        return set()
    return set(v for v in frame[col].tolist()
               if v is not None and v == v)  # drop None/NaN, keep 0


def check_integrity(frames: dict[str, pd.DataFrame],
                    dupe_counts: dict[str, int] | None = None) -> IntegrityReport:
    """Validate Tier-B relationships. Anomalies are REPORTED (PARTIAL
    downstream), never fixed by manufacturing parent records."""
    report = IntegrityReport(
        counts={e: (len(f) if f is not None else 0)
                for e, f in frames.items()},
        duplicate_pks=dict(dupe_counts or {}))
    for entity, frame in frames.items():
        if frame is None or len(frame) == 0:
            continue
        for col in frame.columns:
            nulls = int(frame[col].isna().sum())
            if nulls:
                report.missingness[f"{entity}.{col}"] = nulls

    def _violations(check: str, orphans: set, limit: int = 10) -> None:
        if orphans:
            sample = sorted(orphans, key=repr)[:limit]
            report.fk_violations.append(
                {"check": check, "orphan_count": len(orphans),
                 "sample": sample})

    drivers = _col_set(frames.get("hist_drivers", pd.DataFrame()), "driver_id")
    constructors = set()
    cons_frame = frames.get("hist_constructors", pd.DataFrame())
    if len(cons_frame):
        constructors = set(
            zip(cons_frame["constructor_id"].tolist(),
                cons_frame["season"].tolist()))
    circuits = _col_set(frames.get("hist_circuits", pd.DataFrame()),
                        "circuit_id")
    races = set()
    races_frame = frames.get("hist_races", pd.DataFrame())
    if len(races_frame):
        races = set(zip(races_frame["season"].tolist(),
                        races_frame["round_no"].tolist()))

    results = frames.get("hist_results", pd.DataFrame())
    if results is not None and len(results):
        _violations("results.driver_id -> drivers",
                    set(results["driver_id"].tolist()) - drivers)
        orphan_cons = {(c, s) for c, s in
                       zip(results["constructor_id"].tolist(),
                           results["season"].tolist())
                       if c is not None and c == c and (c, s) not in constructors}
        _violations("results.constructor_id -> constructors(season)",
                    orphan_cons)
        _violations("results.race -> races",
                    {(s, r) for s, r in
                     zip(results["season"].tolist(),
                         results["round_no"].tolist())} - races)
    if len(races_frame):
        import math

        def _present(value):
            return value is not None and not (
                isinstance(value, float) and math.isnan(value))
        _violations("races.circuit_id -> circuits",
                    {v for v in races_frame["circuit_id"].tolist()
                     if _present(v)} - circuits)
    standings = frames.get("hist_standings", pd.DataFrame())
    if standings is not None and len(standings):
        drv_rows = standings[standings["standing_type"] == "driver"]
        _violations("standings.driver -> drivers",
                    set(drv_rows["entrant_id"].tolist()) - drivers)
        con_rows = standings[standings["standing_type"] == "constructor"]
        orphan_scons = {(c, s) for c, s in
                        zip(con_rows["entrant_id"].tolist(),
                            con_rows["season"].tolist())
                        if c is not None and c == c and (c, s) not in constructors}
        _violations("standings.constructor -> constructors(season)",
                    orphan_scons)
    return report


# --------------------------------------------------------------------------
# Season adapter (D3 AdapterFn): one manifest unit = one season.
# --------------------------------------------------------------------------

def make_tierb_season_adapter(client: JolpicaClient,
                              season: int):
    """Build the D3 adapter for one Tier-B season unit (``tierb-<YYYY>``).

    The injected client keeps every test offline; the default live client
    (``tierb_season_adapter``) requires ``V2_ALLOW_NETWORK=1``.
    """
    def adapter(ctx: UnitContext) -> AdapterResult:
        unit_season = ctx.entry.season
        if unit_season is None or int(unit_season) != int(season):
            raise IngestionError.config(
                f"tierb adapter for season {season} got unit "
                f"{ctx.entry.unit_id} (season={unit_season})")
        schedule = client.fetch_collection(
            season_schedule_endpoint(season), ("MRData", "RaceTable", "Races"))
        if not schedule:
            raise IngestionError.missing(
                f"season {season}: upstream schedule empty "
                f"(no Tier-B data to ingest)")
        races_frame, race_dupes = normalize_races(schedule)
        circuits_raw: list[dict] = []
        for r in schedule:
            circuit = (r.get("Circuit") or {}) if isinstance(r, dict) else {}
            if isinstance(circuit, dict) and circuit.get("circuitId"):
                circuits_raw.append(circuit)
        circuits_frame, circuit_dupes = normalize_circuits(circuits_raw)
        driver_raw = client.fetch_collection(
            season_drivers_endpoint(season), ("MRData", "DriverTable",
                                              "Drivers"))
        drivers_frame, driver_dupes = normalize_drivers(driver_raw)
        constructor_raw = client.fetch_collection(
            season_constructors_endpoint(season),
            ("MRData", "ConstructorTable", "Constructors"))
        constructors_frame, constructor_dupes = normalize_constructors(
            constructor_raw, season)
        results_raw = client.fetch_collection(
            season_results_endpoint(season), ("MRData", "RaceTable", "Races"))
        # Cross-page safety: the same (season, round) must never yield two
        # rows for one driver even if pages overlap; PK dedupe counts it.
        results_frame, result_dupes = normalize_results(results_raw)
        final_round = int(races_frame["round_no"].max())
        driver_lists = client.fetch_collection(
            season_driver_standings_endpoint(season),
            ("MRData", "StandingsTable", "StandingsLists"))
        constructor_lists = client.fetch_collection(
            season_constructor_standings_endpoint(season),
            ("MRData", "StandingsTable", "StandingsLists"))
        standings_frame, standings_dupes = normalize_standings(
            driver_lists, constructor_lists, season, final_round)
        seasons_frame, _ = normalize_seasons([season])

        frames = {
            "hist_seasons": seasons_frame,
            "hist_circuits": circuits_frame,
            "hist_drivers": drivers_frame,
            "hist_constructors": constructors_frame,
            "hist_races": races_frame,
            "hist_results": results_frame,
            "hist_standings": standings_frame,
        }
        dupe_counts = {
            "hist_races": race_dupes, "hist_circuits": circuit_dupes,
            "hist_drivers": driver_dupes,
            "hist_constructors": constructor_dupes,
            "hist_results": result_dupes, "hist_standings": standings_dupes,
        }
        report = check_integrity(frames, dupe_counts)
        notes = list(client.notes)
        if report.has_violations():
            details = "; ".join(
                f"{v['check']}: {v['orphan_count']} orphans "
                f"(e.g. {v['sample'][:3]!r})" for v in report.fk_violations)
            notes.append(f"source FK anomalies, parents NOT manufactured: "
                         f"{details}")
        # D5 PARTIAL-semantics adjudication (shared core): client notes
        # ("empty page ... data incomplete") and FK orphans are MATERIAL
        # incompleteness (a truncated fetch or a raced identity absent from
        # the drivers table) -> PARTIAL. Real D4 runs have no such notes.
        partial_reason = "; ".join(notes) if notes else None
        return AdapterResult(frames=frames, partial_reason=partial_reason)

    return adapter


def tierb_season_adapter(ctx: UnitContext) -> AdapterResult:
    """Default live adapter for the CLI (explicit network opt-in inside)."""
    season = ctx.entry.season
    if season is None or ctx.entry.unit_id != tierb_unit_id(int(season)):
        raise IngestionError.config(
            f"tierb adapter got non-Tier-B unit {ctx.entry.unit_id}; "
            f"plan Tier-B scope with 'plan-tierb' first")
    # Intentionally the default single-attempt client: the D3 orchestration
    # budget (run_with_retry) owns retries; the client only classifies
    # failures (429/timeout -> TRANSIENT) with a finite timeout.
    return make_tierb_season_adapter(JolpicaClient(), int(season))(ctx)
