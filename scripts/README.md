# scripts/

## Role today

`scripts/` contains historical research/stage entry points and frozen
provenance-sensitive scripts. It grew organically: builders, analyzers,
runners, freezers, validators, and CI gates live here side by side
(161 files, no subdirectories).

Two facts matter:

1. Some historical scripts contain real domain logic (research models,
   ledgers, regime analyses). That is how past stages were built.
2. Frozen `v3_*` scripts are provenance artifacts. Guard allowlists and
   lineage references key on their exact paths.

These must NOT be retroactively moved during active V3 development.
Reorganizing frozen stages would break provenance links for cosmetic
benefit. Index over them (`docs/INDEX.md`); do not relocate them.

## FORWARD RULE (new work only)

For NEW work from this point onward:

- Reusable domain/scientific logic should live in `raceintel/` under an
  appropriate domain-owned module/package.
- `scripts/` should primarily contain thin executable entry points,
  orchestration, CLI parsing, and artifact/report generation.
- `scripts/` should not become a second authoritative source tree.
  Deletion test: deleting `scripts/` must delete wiring — never the only
  copy of a model.
- Exceptions must be justified explicitly (in the stage doc and the
  script header).

This rule applies only to NEW work. Do NOT move or rewrite existing
frozen `v3_*` scripts to comply with it.

## Naming guideline for new work

Prefer domain-first names:

Good:

- `vsc_duration_analysis.py`
- `tyre_persistence.py`
- `track_regime_validation.py`

Avoid using stage numbers as the main semantic name where possible.
Stage identity may remain in artifact metadata, result directories,
scientific cards, and docs lineage.

Do NOT rename existing files.
