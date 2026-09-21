"""Phase-6 R1 deterministic RNG infrastructure (R1-O..R1-Q).

Contract: ``master_seed`` + ``simulation_id`` (+ the simulation contract
version as a domain tag) deterministically produce one ``Generator``.
Simulation ``i`` receives the same stream whether trials are executed
serially, on one worker, or on many workers in any chunking — the stream is
assigned per *simulation*, never per worker.

Firewall: NO ``np.random`` legacy global state, NO ``random`` module global
state, NO implicit or time-based seed, NO UUID/random identity. The global
``np.random`` state must be untouched by every call here.
"""

from __future__ import annotations

import hashlib

import numpy as np

from v2.simulation.errors import SimulationRNGError
from v2.simulation.state import SIMULATION_CONTRACT_VERSION

#: Versioned stream algorithm. Changing it changes every stream, so it is
#: part of the reproducibility contract.
SIMULATION_RNG_ALGORITHM = "PCG64"

MAX_SEED = 2**64 - 1
MAX_SIMULATION_ID = 2**63 - 1

#: Stable, non-``hash()`` domain identifiers for R6 domain-separated streams
#: (R6-K). ``pace`` is deliberately NOT a domain here: the R5 pace/residual
#: stream stays exactly ``rng_for_simulation`` so enabling R6 mechanics can
#: never shift an R5 draw. The other domains derive a fourth, stable entropy
#: word from the domain name.
SIMULATION_RNG_DOMAINS = (
    "pit_timing",
    "compound",
    "pit_loss",
    "reliability",
)


def _req_seed(value: object, name: str, maximum: int) -> int:
    if type(value) is not int:
        raise SimulationRNGError(
            f"{name} must be a plain Python int, got {value!r}")
    if value < 0 or value > maximum:
        raise SimulationRNGError(
            f"{name} must be in [0, {maximum}], got {value!r}")
    return value


def _domain_tag(contract_version: str) -> int:
    """Deterministic 32-bit domain tag for a contract version string.

    Keeps the RNG stream a documented function of
    ``(master_seed, simulation_id, contract_version)`` without letting a
    free-form version string become part of the seed entropy directly.
    """
    if not isinstance(contract_version, str) or not contract_version.strip():
        raise SimulationRNGError(
            f"contract_version must be a non-empty string, "
            f"got {contract_version!r}")
    digest = hashlib.sha256(contract_version.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def seed_sequence_for_simulation(
        master_seed: int, simulation_id: int, *,
        contract_version: str = SIMULATION_CONTRACT_VERSION
) -> np.random.SeedSequence:
    """Deterministic child ``SeedSequence`` for one simulation.

    The entropy is an explicit ordered list, so the stream is independent
    of trial ordering, chunk boundaries, and worker count.
    """
    seed = _req_seed(master_seed, "master_seed", MAX_SEED)
    sim_id = _req_seed(simulation_id, "simulation_id", MAX_SIMULATION_ID)
    tag = _domain_tag(contract_version)
    return np.random.SeedSequence([seed, sim_id, tag])


def rng_for_simulation(
        master_seed: int, simulation_id: int, *,
        contract_version: str = SIMULATION_CONTRACT_VERSION
) -> np.random.Generator:
    """One deterministic ``Generator`` for one simulation id.

    Same ``(master_seed, simulation_id, contract_version)`` -> an identical
    draw sequence. No race-specific draws live here; the engine draws from
    the returned Generator in a fixed documented order.

    This is the R5 pace/residual stream and is FROZEN: R6 domain-separated
    streams (``rng_for_domain``) use a different entropy length and therefore
    can never shift it (R6-K/R6-L).
    """
    sequence = seed_sequence_for_simulation(
        master_seed, simulation_id, contract_version=contract_version)
    return np.random.Generator(np.random.PCG64(sequence))


def _domain_dimension(domain: str) -> int:
    """Stable 32-bit entropy word for a named RNG domain.

    Uses SHA-256, never Python ``hash()`` (which is salted per process), so
    the stream is reproducible across processes and runs.
    """
    if domain not in SIMULATION_RNG_DOMAINS:
        raise SimulationRNGError(
            f"unknown simulation RNG domain {domain!r}; known domains are "
            f"{list(SIMULATION_RNG_DOMAINS)}")
    digest = hashlib.sha256(
        f"phase6-domain:{domain}".encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def rng_for_domain(
        master_seed: int, simulation_id: int, domain: str, *,
        contract_version: str = SIMULATION_CONTRACT_VERSION
) -> np.random.Generator:
    """Domain-separated deterministic ``Generator`` (R6-K).

    Adds the stable domain word as a fourth entropy element, so pit timing,
    compound selection, pit loss, and (future) reliability draws never
    consume from — or perturb — the frozen R5 pace stream. Same
    ``(master_seed, simulation_id, domain, contract_version)`` always yields
    the identical draw sequence, independently of chunking or worker count.
    """
    seed = _req_seed(master_seed, "master_seed", MAX_SEED)
    sim_id = _req_seed(simulation_id, "simulation_id", MAX_SIMULATION_ID)
    tag = _domain_tag(contract_version)
    dimension = _domain_dimension(domain)
    return np.random.Generator(
        np.random.PCG64(np.random.SeedSequence([seed, sim_id, tag, dimension])))
