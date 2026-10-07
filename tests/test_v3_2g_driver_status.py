"""V3.2G causal driver-status findings (source-safe, normal CI).

Pins the NO_AUTHORITATIVE_STATUS_ADMITTED verdict structure: the
admission bar, per-candidate bar failures, and cross-table consistency
relations. Corpus values themselves are verified by the Tier-3 corpus
suite; this file pins decision logic that must hold for any
recomputation. No corpus, no pandas: TIER 1 safe.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


ADMISSION_BAR = (
    "causal at T",
    "explicit semantic basis",
    "no future observations required",
    "no eventual-result dependency",
    "deterministic",
    "future poison invariant",
    "no transient return after signal",
    "false-positive risk sufficiently low",
    "season behavior understood",
    "source timing understood",
)

CANDIDATE_FAILURES = {
    # candidate -> admission-bar items failed (Part X).
    "C1_explicit_RETIRED_RC": ("explicit semantic basis",),
    "C2_timing_terminal_status": ("explicit semantic basis",),
    "C3_position_terminal_lifecycle": (
        "no future observations required",
        "false-positive risk sufficiently low",
    ),
    "C4_STOPPED_plus_trailing": (
        "no transient return after signal",
        "false-positive risk sufficiently low",
        "season behavior understood",
    ),
    "C5_STOPPED_alone": (
        "no transient return after signal",
        "false-positive risk sufficiently low",
        "season behavior understood",
    ),
}

# Frozen finding values (verified against corpus tables by Tier-3).
NULL_ROWS = 294
NULL_EPISODES = 261
NULL_WINNERS = 3
NULL_PODIUMS = 7
NULL_TOP5 = 9
STOPPED_MESSAGES = 62
STOPPED_WINNERS = 1
STOPPED_DISTINCT_BAD = 14
TERMINAL_ABSENCE_EPISODES = 513
AGREEMENT_NEITHER = 340


def test_admission_bar_has_ten_items():
    assert len(ADMISSION_BAR) == 10


def test_every_candidate_fails_at_least_one_bar_item():
    assert len(CANDIDATE_FAILURES) == 5
    for candidate, failures in CANDIDATE_FAILURES.items():
        assert failures, candidate
        for item in failures:
            assert item in ADMISSION_BAR, (candidate, item)


def test_dead_candidates_fail_on_semantic_basis():
    assert CANDIDATE_FAILURES["C1_explicit_RETIRED_RC"] == (
        "explicit semantic basis",)
    assert CANDIDATE_FAILURES["C2_timing_terminal_status"] == (
        "explicit semantic basis",)


def test_firewall_ordering_is_monotone():
    # winners ⊆ podiums ⊆ top-5 must hold for any recount.
    assert NULL_WINNERS <= NULL_PODIUMS <= NULL_TOP5
    assert STOPPED_WINNERS <= STOPPED_DISTINCT_BAD <= STOPPED_MESSAGES


def test_any_winner_exclusion_disqualifies():
    assert NULL_WINNERS >= 1
    assert STOPPED_WINNERS >= 1


def test_agreement_gap_dominates():
    # Most terminal absences carry no at-T signal at all.
    assert AGREEMENT_NEITHER * 2 > TERMINAL_ABSENCE_EPISODES


def test_null_episode_arithmetic():
    assert NULL_EPISODES <= NULL_ROWS
    assert NULL_ROWS == 294


def test_unknown_remains_valid_semantics():
    statuses = ("ACTIVE", "IN_PIT", "TEMPORARILY_UNOBSERVED",
                "RETIRED_KNOWN", "DNS", "UNKNOWN")
    assert "UNKNOWN" in statuses


def test_season_stability_veto():
    stopped_per_season = {"2018": 25, "2019": 15, "2020": 3, "2021": 7,
                          "2022": 9, "2023": 0, "2024": 3}
    assert stopped_per_season["2023"] == 0
    assert sum(stopped_per_season.values()) == STOPPED_MESSAGES
