"""Phase-12 spatial track replay: presentation-only data contracts (P12-1).

This package owns the canonical schemas, identity, time, availability,
provenance, manifest, and serialization contracts for historical spatial
position data. It implements NO ingestion, NO geometry, NO temporal
resolution, NO API, and NO frontend — P12-2 onward builds on these
contracts.

SCIENTIFIC BOUNDARY (frozen): spatial data is a presentation /
historical-state extension. Nothing here may enter ALL_84, the Phase-2
matrix, the winner model, model-lab evaluation, simulation parameters,
the strategy engine, or explainability. Import-direction firewall tests
(`tests/test_spatial_firewall.py`) enforce both sides of this boundary.

TIME BASIS (P12-0 evidence): `observation_time_s` shares the FastF1
session clock with replay `anchor_state_time_s` (measured agreement
~0.1s on 2021-r05-R lap 1). No offset calibration is required.
"""

from __future__ import annotations

SPATIAL_CONTRACT_VERSION = "spatial-observation-v1"
SPATIAL_GEOMETRY_SCHEMA_VERSION = "spatial-geometry-v1"
SPATIAL_MANIFEST_SCHEMA_VERSION = "spatial-manifest-v1"
