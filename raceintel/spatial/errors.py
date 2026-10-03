"""Phase-12 spatial contract errors (P12-1).

Minimal fail-closed hierarchy: one base plus one error per contract
surface. No absolute local paths in messages; race_id and row positions
are the allowed context.
"""

from __future__ import annotations


class SpatialContractError(ValueError):
    """Base for all spatial contract violations (never an HTTP code)."""


class SpatialSchemaError(SpatialContractError):
    """Persisted observation frame violates the schema contract."""


class SpatialIdentityError(SpatialContractError):
    """race_id / driver_number identity or join validation failed."""


class SpatialDuplicateConflictError(SpatialContractError):
    """Same (driver, Time, Date) carries conflicting coordinates."""


class SpatialProvenanceError(SpatialContractError):
    """Artifact provenance record is incomplete or inconsistent."""


class SpatialManifestError(SpatialContractError):
    """Ingestion manifest schema or row update is invalid."""


class SpatialResolutionError(SpatialContractError):
    """Temporal resolution failed: bad query time or unusable driver data."""


class SpatialGeometryMismatchError(SpatialContractError):
    """Geometry source identity does not match the observation identity."""


class SpatialArtifactUnavailableError(SpatialContractError):
    """Race has no resolvable observations or no renderable geometry."""
