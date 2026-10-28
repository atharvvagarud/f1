# ADR-0002 — `v2/` pickle-compatibility shim retention (post-V3 C4)

- **Status:** Accepted (2026-10-27). Reversible only via the
  retirement condition below — see Revisit triggers.
- **Decision owner:** Post-V3 cleanup programme (C4 v2 retirement
  audit; `docs/INDEX.md` records "No ADR exists yet" for this
  decision — this file is that record).
- **Plan reference:** post-V3 C4 retirement audit; prior verdict
  `FALSE_POSITIVE — RETAIN_REQUIRED` in
  `docs/POST_V2_C3A_PONYTAIL_HYGIENE_AUDIT.md` (Dead code findings).

## Context

The 121-file `v2/` implementation was already migrated to
`raceintel/` (post-V2 C2 structural consolidation; freeze tests
assert the old paths absent). Only three tracked files remain:

- `v2/__init__.py`
- `v2/model_lab/__init__.py`
- `v2/model_lab/preprocessing.py`

They contain no implementation: each re-exports
`raceintel.model_lab` so the historical pickle import path
`v2.model_lab.preprocessing.FittedPreprocessor` keeps resolving.
`docs/INDEX.md` notes the directory appears unused but forbids
deletion without a provenance review and a recorded decision.

## Measured evidence (C4 audit, read-only)

- Serving artifact
  `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`:
  17,401 bytes, SHA-256
  `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
  (exact match to the frozen pin), embeds
  `v2.model_lab.preprocessing` exactly once, embeds `raceintel`
  zero times.
- Normal `joblib.load` of the artifact succeeds; the shim resolves
  to the identical class object as
  `raceintel.model_lab.preprocessing.FittedPreprocessor`.
- Negative control: with `v2` imports blocked, the same load fails
  with `ModuleNotFoundError` for `v2.model_lab.preprocessing`.
- `Dockerfile.backend` explicitly copies the directory
  (`COPY v2/ ./v2/`).
- C4 validation: artifact-loading/container contract tests 13/13
  green; collection unchanged at 5319; no production,
  scientific-data, selector, manifest, artifact, or frozen-V3
  changes.

## Decision

**`v2/` = RETAIN_REQUIRED.**

The remaining directory is a compatibility namespace, not an
alternative implementation tree. Canonical implementation remains
under `raceintel/`.

## Maintenance rule

Do not:

- delete `v2/`;
- rename the compatibility namespace;
- move its remaining files merely for repository cleanliness;
- rewrite or reserialize the frozen artifact under a new module
  path;
- treat the directory as duplicate production implementation.

Normal repository cleanup excludes these three files unless a
separately authorized artifact-migration project supersedes this
decision.

## Revisit triggers

Retirement may only be reconsidered through an explicitly
authorized serving-artifact migration that:

1. replaces the historical serialized import dependency safely;
2. resolves the container (`COPY v2/`) dependency;
3. proves serving/artifact loading still works;
4. addresses frozen artifact hashes and scientific provenance
   explicitly;
5. receives separate approval before modifying or replacing the
   frozen artifact.

That migration is outside current post-V3 cleanup scope.
