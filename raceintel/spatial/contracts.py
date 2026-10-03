"""Phase-12 spatial observation contract constants (P12-1).

Single source of contract truth for P12-2 ingestion: persisted schema,
identity, time, availability, seasons, artifact layout, and serialization
conventions. Pure constants and pure helpers only — no I/O, no FastF1
import, no predictive imports.

Evidence basis (P12-0, FastF1 3.7.0 position stream):
- columns Time/Date/Status/X/Y/Z/Source per driver-number key;
- ~1 Hz unique samples after exact-duplicate removal, max gap ~3.8 s;
- X/Y/Z int64 metre-scale on an event-relative arbitrary origin;
- (0, 0, 0) rows are a no-fix sentinel (pre-race garage), never a track
  position;
- same-(driver, Time) rows differ only by sub-second Date order; same
  (Time, Date) never conflicts (0 observed conflicts).
"""

from __future__ import annotations

import math

from raceintel.spatial.errors import SpatialContractError

#: Persisted observation schema version. Participates in content hashing
#: and manifest provenance. Never a generic version framework.
SPATIAL_SCHEMA_VERSION = "spatial-observation-v1"

#: Geometry schema version, declared here so P12-3 shares one version
#: authority. No geometry is produced or consumed in P12-1.
SPATIAL_GEOMETRY_SCHEMA_VERSION = "spatial-geometry-v1"

#: Manifest schema version for the P12-2 ingestion manifest.
SPATIAL_MANIFEST_SCHEMA_VERSION = "spatial-manifest-v1"

#: FastF1 version the P12-0 evidence was measured against. P12-2 records
#: the actual version per artifact; drift fails provenance validation.
EVIDENCE_FASTF1_VERSION = "3.7.0"

#: Source stream name inside a FastF1 session load.
SOURCE_STREAM = "position"

# ---------------------------------------------------------------------------
# Persisted observation schema
# ---------------------------------------------------------------------------

#: Canonical persisted column order. `source_observed_at` (absolute FastF1
#: Date, transient ordering key for sub-second duplicate resolution) is
#: deliberately NOT persisted: once deduped to one row per
#: (driver_number, observation_time_s) it adds no sync/render value, and
#: the session clock already joins to replay time.
OBSERVATION_COLUMNS = (
    "race_id",
    "driver_number",
    "observation_time_s",
    "x",
    "y",
    "z",
    "source",
    "status",
)

#: Exact persisted dtypes. Raw source coordinates are integral metres;
#: persisting int64 preserves them losslessly. P12-3 owns any float
#: normalized geometry — never this table.
OBSERVATION_DTYPES = {
    "race_id": "str",
    "driver_number": "int64",
    "observation_time_s": "float64",
    "x": "int64",
    "y": "int64",
    "z": "int64",
    "source": "str",
    "status": "str",
}

#: Uniqueness key inside one race artifact (race_id is constant per file).
OBSERVATION_UNIQUE_KEY = ("driver_number", "observation_time_s")

#: Canonical sort order for persisted artifacts and content hashing.
OBSERVATION_SORT_ORDER = ("driver_number", "observation_time_s")

# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------

#: Canonical spatial identity: (race_id, driver_number). `race_id` uses the
#: frozen `season-rRR-R` form (e.g. `2021-r05-R`); `driver_number` is the
#: integer behind FastF1's string driver-number keys and the corpus
#: `driver_number` column. Display names are never identity.
DRIVER_NUMBER_MIN = 1
DRIVER_NUMBER_MAX = 99

# ---------------------------------------------------------------------------
# Raw value vocabularies (persisted raw, fail-closed on drift)
# ---------------------------------------------------------------------------

#: Only Source value observed across sampled 2018/2021/2023/2024 races.
KNOWN_SOURCE_VALUES = frozenset({"pos"})

#: Status values observed (OffTrack seen in 2018 Spain). Persisted raw;
#: strict validation rejects anything outside this set so new semantics
#: force a deliberate contract extension, never silent acceptance.
KNOWN_STATUS_VALUES = frozenset({"OnTrack", "OffTrack"})

#: No-fix sentinel: exact (0, 0, 0) rows occur pre-race (garage, no GPS
#: fix) and are never track positions. P12-2 must exclude them; persisted
#: artifacts containing them fail validation.
ZERO_FIX_COORDINATES = (0, 0, 0)

# ---------------------------------------------------------------------------
# Duplicate handling
# ---------------------------------------------------------------------------

#: Within one (driver_number, observation_time_s) group, rows are ordered
#: by transient source timestamp and the LAST is kept (latest sub-second
#: update wins). Deterministic; no averaging, no interpolation.
DUPLICATE_RESOLUTION = "keep-last-by-source-time"

# ---------------------------------------------------------------------------
# Availability (future P12-4 resolver output; frozen here)
# ---------------------------------------------------------------------------

AVAILABILITY_FRESH = "FRESH"
AVAILABILITY_STALE = "STALE"
AVAILABILITY_UNAVAILABLE = "UNAVAILABLE"

#: age <= 3.0 s (covers the ~3.8 s max unique gap with margin for the
#: nominal ~1 Hz feed; P12-0 evidence).
FRESH_MAX_AGE_S = 3.0

#: 3.0 < age <= 15.0 s. Boundary values belong to the fresher state:
#: age 3.0 -> FRESH, age 15.0 -> STALE, age > 15.0 -> UNAVAILABLE.
STALE_MAX_AGE_S = 15.0


def classify_availability(age_s: float) -> str:
    """Classify a resolver observation age into availability.

    Pure helper frozen for P12-4. Negative or non-finite ages are never
    valid — they imply a future observation leaking into the query.
    """
    if not isinstance(age_s, (int, float)) or not math.isfinite(age_s):
        raise SpatialContractError(
            f"availability age must be a finite number, got {age_s!r}")
    age = float(age_s)
    if age < 0:
        raise SpatialContractError(
            f"availability age must be >= 0 (negative implies a future "
            f"observation), got {age!r}")
    if age <= FRESH_MAX_AGE_S:
        return AVAILABILITY_FRESH
    if age <= STALE_MAX_AGE_S:
        return AVAILABILITY_STALE
    return AVAILABILITY_UNAVAILABLE


# ---------------------------------------------------------------------------
# Seasons: data epoch vs product eligibility
# ---------------------------------------------------------------------------

#: Spatial data epoch. 2025 position streams exist and may be ingested,
#: but 2025 is never product-servable (holdout firewall).
SPATIAL_DATA_MIN_SEASON = 2018
SPATIAL_DATA_MAX_SEASON = 2025

#: Product eligibility mirrors the frozen replay serving boundary
#: (`api/v2_service.SERVED_SEASONS`; drift-guarded by firewall tests).
#: Single product truth stays in the API service; these constants let the
#: spatial contract reason about eligibility without depending on the API
#: layer (a raceintel-to-api dependency is a forbidden direction).
PRODUCT_SERVED_SEASONS = tuple(range(2018, 2025))


def is_data_ingestible(season: int) -> bool:
    """Whether a season's position streams may be ingested (incl. 2025)."""
    return isinstance(season, int) and (
        SPATIAL_DATA_MIN_SEASON <= season <= SPATIAL_DATA_MAX_SEASON)


def is_product_servable(season: int) -> bool:
    """Whether a season may be product-served (2025 excluded, always)."""
    return isinstance(season, int) and season in PRODUCT_SERVED_SEASONS


# ---------------------------------------------------------------------------
# Artifact layout (future; no I/O here)
# ---------------------------------------------------------------------------

#: Spatial artifacts live OUTSIDE the canonical `data/v2` corpus so the
#: frozen D11 artifact-inventory scope (data/v2) is untouched, and outside
#: the runtime bundle manifests. Pure path builders only.
SPATIAL_ROOT_DIRNAME = "spatial"
OBSERVATIONS_SUBDIR = "observations"
MANIFESTS_SUBDIR = "manifests"
SCHEMA_SUBDIR = "schema"
GEOMETRY_SUBDIR = "geometry"
SPATIAL_MANIFEST_FILENAME = "spatial_manifest.json"


def observations_filename(race_id: str) -> str:
    """Deterministic per-race artifact name (atomic writes, resume)."""
    if not isinstance(race_id, str) or not race_id.strip():
        raise SpatialContractError(
            f"race_id must be a non-empty string, got {race_id!r}")
    return f"{race_id}.parquet"


# ---------------------------------------------------------------------------
# Serialization conventions (future; no I/O here)
# ---------------------------------------------------------------------------

#: Parquet via the existing pyarrow dependency. No new dependency.
PARQUET_ENGINE = "pyarrow"

#: Measured compact choice (P12-0: 1.35 MB snappy vs 1.27 MB zstd for the
#: reference race; snappy chosen for read speed at this scale).
PARQUET_COMPRESSION = "snappy"

#: Never persist a pandas index column; the uniqueness key is the index.
PARQUET_WRITE_INDEX = False
