"""Phase-6 R1 simulation error taxonomy (narrow, deterministic).

No HTTP imports and no framework coupling: API error mapping belongs to
R8. Every error is a plain ``ValueError`` subclass, matching the frozen
domain convention (Phase-4 ``RaceStateError``, Phase-5
``ReplayTimelineError``).
"""

from __future__ import annotations


class SimulationError(ValueError):
    """Base error for every Phase-6 simulation contract failure."""


class SimulationContractError(SimulationError):
    """A simulation-domain contract object is structurally malformed.

    Wrong types, missing collections, duplicate identities, and
    inconsistent field combinations raise this.
    """


class SimulationValidationError(SimulationContractError):
    """A boundary value is numerically or semantically invalid.

    NaN/Infinity, negative progress, out-of-range probabilities, and
    impossible positions raise this. It is a subclass so callers may
    catch the broad contract error.
    """


class SimulationRNGError(SimulationError):
    """Invalid RNG identity/seed or a nondeterministic stream request."""
