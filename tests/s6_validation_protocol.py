"""Phase-7 S6 frozen validation protocol and deterministic state selection.

This module is the single source of truth for the S6 scientific validation
protocol. It is imported by ``scripts/run_phase7_s6_validation.py``,
``scripts/run_phase7_s6_red_team.py`` and
``tests/test_v2_phase7_s6_validation.py`` so the protocol cannot drift between
the runner and its assertions.

The protocol was frozen **before** the final corpus was executed. It reuses the
Phase-6 R7 validation protocol's own deterministic selection rule
(``nearest_supported_frame_by_leader_lap`` and the accepted-season /
parameter-cutoff rules) rather than hand-picking states. No state is selected
on a Strategy result, and the historical future is never an input to Strategy.

Scope firewall (inherited from Phase-6 R7):

- evaluation seasons 2020-2024 only; 2018/2019/2025 excluded (2025 is under the
  scientific/serving firewall);
- parameters are fit strictly before the target season
  (``through_season = season - 1``);
- only R7-accepted, contemporaneous, dry/green states are used for the
  representative corpus; unsupported states are exercised only as explicitly
  labelled adversarial fixtures.

Dependency note: this is a validation/test helper. Production ``raceintel.strategy``
modules never import it.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Frozen protocol identity.
# ---------------------------------------------------------------------------

STRATEGY_VALIDATION_PROTOCOL_VERSION = "s6-validation-v1"
S6_RED_TEAM_VERSION = "s6-red-team-v1"

#: Broad representative validation: every accepted (season, stage) anchor at
#: this count with the full canonical candidate space.
BROAD_SIMULATION_COUNT = 1000
#: Deep validation: a smaller deterministic subset at this count.
DEEP_SIMULATION_COUNT = 10000

#: Predeclared master seeds (never selected on results).
BROAD_SEED = 20240101
DEEP_SEED = 20240101
#: Extra seed used only for determinism / seed-sensitivity checks.
ALT_SEED = 7

#: Bootstrap analysis seed root (Strategy statistical stream, never a
#: simulation seed).
BOOTSTRAP_SEED_ROOT = 20240101
BOOTSTRAP_REPLICATES = 2000
CONFIDENCE_LEVEL = 0.95

#: Evaluation seasons and stages (Phase-6 R7 protocol).
EVALUATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
STAGES = ("EARLY", "MID", "LATE")

#: Running-position bands; the target driver is chosen deterministically from
#: each state so front / midfield / backmarker coverage is guaranteed without
#: any result-based selection.
BANDS = ("FRONT", "MIDFIELD", "BACK")

#: Canonical candidate space (must match ``raceintel.strategy.candidates``).
CANONICAL_SPECS = (
    ("STAY_OUT", None),
    ("PIT_NOW", None),
    ("PIT_NOW", "SOFT"),
    ("PIT_NOW", "MEDIUM"),
    ("PIT_NOW", "HARD"),
    ("PIT_NEXT_LAP", None),
    ("PIT_NEXT_LAP", "SOFT"),
    ("PIT_NEXT_LAP", "MEDIUM"),
    ("PIT_NEXT_LAP", "HARD"),
)

#: Deep-validation candidate subset (isolates pit-timing from compound).
DEEP_SPECS = (
    ("STAY_OUT", None),
    ("PIT_NOW", None),
    ("PIT_NEXT_LAP", None),
)

#: S7 engineering guidance buckets (decision rules frozen pre-run).
S7_GUIDANCE = {
    "default_simulation_count": BROAD_SIMULATION_COUNT,
    "deep_count_requires_explicit_opt_in": DEEP_SIMULATION_COUNT,
    "full_candidate_space_size": len(CANONICAL_SPECS),
}

ARTIFACT_DIR = "data/v2/strategy"
VALIDATION_ARTIFACT = f"{ARTIFACT_DIR}/s6_validation_v1.json"
RED_TEAM_ARTIFACT = f"{ARTIFACT_DIR}/s6_red_team_v1.json"

R7_VALIDATION_ARTIFACT = "data/v2/simulation/validation/r7_validation_raw_v1.json"

PROTOCOL_RECORD = {
    "protocol_version": STRATEGY_VALIDATION_PROTOCOL_VERSION,
    "red_team_version": S6_RED_TEAM_VERSION,
    "broad_simulation_count": BROAD_SIMULATION_COUNT,
    "deep_simulation_count": DEEP_SIMULATION_COUNT,
    "broad_seed": BROAD_SEED,
    "deep_seed": DEEP_SEED,
    "alt_seed": ALT_SEED,
    "bootstrap_seed_root": BOOTSTRAP_SEED_ROOT,
    "bootstrap_replicates": BOOTSTRAP_REPLICATES,
    "confidence_level": CONFIDENCE_LEVEL,
    "evaluation_seasons": list(EVALUATION_SEASONS),
    "stages": list(STAGES),
    "bands": list(BANDS),
    "state_selection_rule": (
        "for each (season, stage): lexicographically-first R7-selected race "
        "with that stage present; frame index and leader lap taken from the "
        "Phase-6 R7 protocol artifact"),
    "target_selection_rule": (
        "roster sorted by (position, driver_id); FRONT=rank 0, MIDFIELD=rank "
        "n//2, BACK=rank n-1"),
    "parameter_cutoff_rule": "through_season = evaluation_season - 1",
    "excluded_seasons": [2018, 2019, 2025],
    "candidate_space": [list(spec) for spec in CANONICAL_SPECS],
    "deep_candidate_subset": [list(spec) for spec in DEEP_SPECS],
    "unsupported_state_policy": (
        "structured unsupported result or labelled adversarial fixture; never "
        "a partial Strategy table and never silent driver dropping"),
    "no_counterfactual_ground_truth_claim": True,
    "oracle_evaluation_only": (
        "historical future used only in a strictly separate descriptive audit; "
        "never an input to candidate generation, validity, outcome, "
        "uncertainty or objective"),
}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# Deterministic corpus selection.
# ---------------------------------------------------------------------------

def r7_artifact_path() -> Path:
    return repo_root() / R7_VALIDATION_ARTIFACT


def r7_artifact_available() -> bool:
    return r7_artifact_path().exists()


@functools.lru_cache(maxsize=1)
def _r7_races() -> tuple:
    payload = json.loads(r7_artifact_path().read_text())
    return tuple(payload["races"])


def _record_from(season: int, race: dict, stage: str, info: dict) -> dict:
    return {
        "season": season,
        "race_id": race["race_id"],
        "scheduled_laps": race["scheduled_laps"],
        "stage": stage,
        "frame_index": info["frame_index"],
        "leader_lap": info["leader_lap"],
    }


def record_eligibility(record: dict) -> tuple:
    """Frozen-simulator eligibility of one state (whole-state R7.1 rule).

    Returns ``(eligible, reason)``. Uses the engine's own start-state
    validation (no simulation, no draw), so selection is eligibility-based and
    never Strategy-result-based. A reason is a stable engine reason.
    """
    from raceintel.simulation.engine import ExecutionPolicy, SimulationUnsupportedError
    from raceintel.simulation.monte_carlo import _prepare
    state = load_state(record)
    parameters = load_parameters(record["season"])
    try:
        _prepare(state, parameters, ExecutionPolicy.RETROSPECTIVE_PRODUCT, False)
        return True, None
    except SimulationUnsupportedError as exc:
        return False, exc.reason


def eligibility_audit() -> dict:
    """Deterministic eligibility accounting over every R7 anchor."""
    races = _r7_races()
    total = 0
    eligible = 0
    reasons = {}
    per_season = {}
    for season in EVALUATION_SEASONS:
        season_races = sorted(
            (race for race in races if race.get("season") == season
             and race.get("selected")),
            key=lambda race: race["race_id"])
        season_total = season_eligible = 0
        for race in season_races:
            for stage in STAGES:
                info = (race.get("stages") or {}).get(stage)
                if not info:
                    continue
                record = _record_from(season, race, stage, info)
                ok, reason = record_eligibility(record)
                total += 1
                season_total += 1
                if ok:
                    eligible += 1
                    season_eligible += 1
                else:
                    reasons[reason] = reasons.get(reason, 0) + 1
        per_season[season] = {"total": season_total,
                              "eligible": season_eligible}
    return {"anchors_total": total, "anchors_eligible": eligible,
            "excluded_by_reason": reasons, "per_season": per_season,
            "rule": "frozen R7.1 whole-state start-state eligibility; an "
                    "ineligible anchor is excluded with its engine reason, "
                    "never replaced by a more convenient state"}


def select_corpus() -> tuple:
    """Deterministic representative corpus: one eligible race per (season,
    stage).

    Uses the R7 artifact's accepted-selection pool, keeps only anchors the
    frozen simulator itself accepts (R7.1 whole-state eligibility), and within
    each season takes the lexicographically-first eligible race that has the
    stage anchor. Deterministic and eligibility-based, never result-based.
    """
    races = _r7_races()
    records = []
    for season in EVALUATION_SEASONS:
        season_races = sorted(
            (race for race in races if race.get("season") == season
             and race.get("selected")),
            key=lambda race: race["race_id"])
        for stage in STAGES:
            for race in season_races:
                info = (race.get("stages") or {}).get(stage)
                if not info:
                    continue
                record = _record_from(season, race, stage, info)
                if record_eligibility(record)[0]:
                    records.append(record)
                    break
    return tuple(records)


def select_broad_jobs() -> tuple:
    """All (state record, band) broad-validation jobs in canonical order."""
    jobs = []
    for record in select_corpus():
        for band in BANDS:
            jobs.append((record, band))
    return tuple(jobs)


def select_deep_corpus() -> tuple:
    """Deterministic deep subset: the lexicographically-first race per stage.

    One state per stage (the earliest selected race), one target (FRONT band),
    a three-candidate subset at 10 000 trajectories.
    """
    races = _r7_races()
    records = []
    for stage in STAGES:
        for season in EVALUATION_SEASONS:
            season_races = sorted(
                (race for race in races if race.get("season") == season
                 and race.get("selected")),
                key=lambda race: race["race_id"])
            found = False
            for race in season_races:
                info = (race.get("stages") or {}).get(stage)
                if not info:
                    continue
                record = _record_from(season, race, stage, info)
                if record_eligibility(record)[0]:
                    records.append(record)
                    found = True
                    break
            if found:
                break
    return tuple(records)


# ---------------------------------------------------------------------------
# State / target loading (real replay seam, evaluation-only).
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _load_state(season: int, race_id: str, frame_index: int):
    from test_v2_phase6_r71 import _real_state_at
    return _real_state_at(season, race_id, frame_index)


def load_state(record: dict):
    """Load the exact factual state at T for one corpus record."""
    return _load_state(record["season"], record["race_id"],
                       record["frame_index"])


def load_parameters(season: int):
    from test_v2_phase6_r71 import _params_through
    return _params_through(season - 1)


def rank_drivers(state) -> tuple:
    """Deterministic roster ordering by (running position, driver_id).

    A driver with no factual running position sorts last (deterministically),
    never dropped.
    """
    def sort_key(driver_id):
        position = state.driver_by_id[driver_id].position
        return (position is None, position if position is not None else 0,
                driver_id)

    return tuple(sorted(state.roster_driver_ids, key=sort_key))


def select_targets(state) -> dict:
    """Deterministic FRONT / MIDFIELD / BACK target driver ids."""
    ranked = rank_drivers(state)
    if not ranked:
        return {}
    return {
        "FRONT": ranked[0],
        "MIDFIELD": ranked[len(ranked) // 2],
        "BACK": ranked[-1],
    }


def make_config(count: int, seed: int):
    from raceintel.simulation.config import SimulationConfig
    return SimulationConfig(simulation_count=count, master_seed=seed,
                            sample_orders=0, pit_dynamics_enabled=True)
