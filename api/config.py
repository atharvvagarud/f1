"""Explicit backend serving configuration (P10-3).

Small stdlib-only contract for production-like operation. Two variables::

    F1_ALLOWED_ORIGINS  comma-separated browser origins (default: local)
    F1_LOG_LEVEL        DEBUG/INFO/WARNING/ERROR/CRITICAL (default: INFO)

Existing variables (``V2_PROJECT_ROOT``, ``V2_ALLOW_NETWORK``,
``NEXT_PUBLIC_API_BASE``) are unchanged and NOT owned here.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

#: Local deployment default: `docker compose up` works with no env file.
DEFAULT_ALLOWED_ORIGINS: tuple[str, ...] = ("http://localhost:3000",)

DEFAULT_LOG_LEVEL = "INFO"

VALID_LOG_LEVELS: tuple[str, ...] = (
    "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

ALLOWED_ORIGINS_ENV_VAR = "F1_ALLOWED_ORIGINS"
LOG_LEVEL_ENV_VAR = "F1_LOG_LEVEL"


def parse_allowed_origins(raw: str | None) -> tuple[str, ...]:
    """Parse ``F1_ALLOWED_ORIGINS`` deterministically.

    Split on commas, trim whitespace, discard empty entries. ``None`` or a
    whitespace-only value falls back to the safe local default. An explicit
    ``"*"`` entry is honored as a deliberate operator choice (credentials
    stay disabled, so FastAPI semantics remain clear); it is never produced
    silently. A set-but-empty-after-trim value (e.g. ``",,,"``) is a
    configuration error, not a wildcard.
    """
    if raw is None or not raw.strip():
        return DEFAULT_ALLOWED_ORIGINS
    origins = tuple(
        entry.strip() for entry in raw.split(",") if entry.strip())
    if not origins:
        raise ValueError(
            f"{ALLOWED_ORIGINS_ENV_VAR} is set but contains no origins "
            "(unset it for the local default, or list explicit origins)")
    return origins


def parse_log_level(raw: str | None) -> str:
    """Parse ``F1_LOG_LEVEL``; fail fast on clearly invalid values."""
    if raw is None or not str(raw).strip():
        return DEFAULT_LOG_LEVEL
    level = str(raw).strip().upper()
    if level not in VALID_LOG_LEVELS:
        raise ValueError(
            f"{LOG_LEVEL_ENV_VAR}={raw!r} is invalid "
            f"(expected one of {', '.join(VALID_LOG_LEVELS)})")
    return level


@dataclass(frozen=True)
class ServingConfig:
    """Immutable serving settings (environment-provided, no .env loader)."""

    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS
    log_level: str = DEFAULT_LOG_LEVEL

    @classmethod
    def from_env(cls, env=None) -> "ServingConfig":
        source = os.environ if env is None else env
        return cls(
            allowed_origins=parse_allowed_origins(
                source.get(ALLOWED_ORIGINS_ENV_VAR)),
            log_level=parse_log_level(source.get(LOG_LEVEL_ENV_VAR)),
        )


def get_serving_config(env=None) -> ServingConfig:
    """Load the serving configuration (fail fast on invalid values)."""
    return ServingConfig.from_env(env)
