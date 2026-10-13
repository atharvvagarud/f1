"""MC2 residual distribution audit + AR(1) process (V3.2D Part Q-T).

Distribution (Part Q): the R3 empirical quantile residual is retained. It
is zero-MEDIAN with a heavy positive tail; R5 deliberately uses it as
stored (no rescale/recenter). No parametric replacement is introduced
without evidence — none is claimed in V3.2D.

AR(1) (Part R-S): V3.2A measured lag-1 correlation ~0.264. The mechanism,
admitted conditionally on stability:

    epsilon_t = rho * epsilon_{t-1} + innovation_t
    innovation_t ~ Empirical * sqrt(1 - rho^2)      (variance correction)

with |rho| < 1, own-driver residuals only, and a dedicated deterministic
RNG domain (Part U) that never perturbs R3 streams.

Variance correction (Part T): if the empirical draw has variance s^2 and
the stationary target is s^2, the innovation scale MUST be sqrt(1-rho^2);
scaling the innovation (not the AR recursion) keeps E[eps^2] = s^2
exactly under stationarity. Tested empirically in-suite.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass

import numpy as np

__all__ = [
    "MC2_AR1_DOMAIN",
    "RHO_REFERENCE",
    "RHO_BOUND",
    "innovation_scale",
    "validate_rho",
    "ar1_step",
    "mc2_stream",
    "empirical_stats",
]

#: Dedicated MC2 RNG domain (separate entropy from every R3/R6 domain, so
#: enabling MC2 mechanisms can never shift a frozen R3 draw).
MC2_AR1_DOMAIN = "mc2-ar1"

#: P2A hoisting: tag/dim below are pure functions of module-constant domain
#: strings, so they are computed once at import. mc2_stream() uses these
#: exact integers; SeedSequence entropy (and therefore every stream) is
#: bit-identical to the per-call derivation. Verified by fixture parity.
_MC2_TAG = int.from_bytes(hashlib.sha256(b"mc2-rng-v1").digest()[:4],
                          "big")
_MC2_DIM_BY_DOMAIN: dict = {}

#: V3.2A reference measurement (development prior, re-estimated per fold).
RHO_REFERENCE = 0.264

#: Stability bound: |rho| <= 0.8 (strictly inside the unit circle with
#: margin; values above are rejected as non-credible persistence).
RHO_BOUND = 0.8


def validate_rho(rho: float) -> float:
    """Coerce a candidate rho; reject non-finite or |rho| >= 1."""
    v = float(rho)
    if not math.isfinite(v):
        raise ValueError(f"rho must be finite, got {rho!r}")
    if abs(v) >= 1.0:
        raise ValueError(f"|rho| must be < 1, got {v!r}")
    if abs(v) > RHO_BOUND:
        raise ValueError(f"|rho| must be <= {RHO_BOUND}, got {v!r}")
    return v


def innovation_scale(rho: float) -> float:
    """Stationary-variance-preserving innovation multiplier sqrt(1-rho^2)."""
    v = validate_rho(rho)
    return math.sqrt(max(0.0, 1.0 - v * v))


def ar1_step(previous_eps: float, innovation: float, rho: float) -> float:
    """One stable AR(1) residual step (both inputs finite, else ValueError)."""
    v = validate_rho(rho)
    if not (math.isfinite(previous_eps) and math.isfinite(innovation)):
        raise ValueError("AR(1) inputs must be finite")
    out = v * previous_eps + innovation_scale(v) * innovation
    if not math.isfinite(out):
        raise ValueError("AR(1) step overflowed")
    return float(out)


def mc2_stream(master_seed: int, simulation_id: int,
               domain: str = MC2_AR1_DOMAIN) -> np.random.Generator:
    """Deterministic MC2 generator on its OWN domain (never an R3 stream).

    Entropy layout ``[seed, sim_id, tag, dim]`` mirrors ``rng_for_domain``
    structurally but tags ``mc2-rng-v1`` + domain, so no R3/R6 stream can
    collide: same (seed, sim) -> identical MC2 draws, chunk invariant by
    construction (one stream per simulation, consumed in event order).
    """
    if type(master_seed) is not int or type(simulation_id) is not int:
        raise ValueError("seeds must be plain Python ints")
    if master_seed < 0 or simulation_id < 0:
        raise ValueError("seeds must be non-negative")
    dim = _MC2_DIM_BY_DOMAIN.get(domain)
    if dim is None:
        dim = int.from_bytes(
            hashlib.sha256(f"mc2-domain:{domain}".encode()).digest()[:4],
            "big")
        _MC2_DIM_BY_DOMAIN[domain] = dim
    seq = np.random.SeedSequence([master_seed, simulation_id, _MC2_TAG,
                                  dim])
    return np.random.Generator(np.random.PCG64(seq))


def empirical_stats(values: list) -> dict:
    """Distribution audit: mean/std/tails/skew for one residual sample."""
    arr = np.asarray([float(v) for v in values], dtype=np.float64)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        raise ValueError("no finite values to audit")
    mean = float(arr.mean())
    std = float(arr.std())
    out = {
        "n": int(arr.size),
        "mean": mean,
        "std": std,
        "min": float(arr.min()),
        "max": float(arr.max()),
        "p01": float(np.percentile(arr, 1)),
        "p99": float(np.percentile(arr, 99)),
        "median": float(np.median(arr)),
    }
    if std > 0:
        out["skew"] = float(((arr - mean) ** 3).mean() / (std ** 3))
    else:
        out["skew"] = 0.0
    return out


@dataclass(frozen=True)
class AR1Config:
    rho: float
    fallback: str  # 'estimated' | 'reference' | 'disabled'

    def __post_init__(self) -> None:
        validate_rho(self.rho)
