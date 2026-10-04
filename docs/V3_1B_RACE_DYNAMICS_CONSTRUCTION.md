# V3.1B RACE DYNAMICS CONSTRUCTION

## Final verdict

V3.1B COMPLETE -- 29 contracted dynamics (26 CORE + 3 VARIANT_A) built
deterministically beside Phase-2, provenance-pinned, all gates green.
Built against corrected contract v3.1a-v2 (V3.1A-C1); the blocked v1
construction was repaired, not resumed.

## Contract consumed

v3.1a-v2, SHA
`abd5300816d79270b1cd5b9b4952ebe447817f770eeddd2c598d0f07fbd5a0a4`
(`raceintel/features/dynamics/contract.py`). V3.1A-C1 correction:
`docs/V3_1A_C1_BEHIND_RELATIONSHIP_CONTRACT_CORRECTION.md`.

## Implementation

- `raceintel/features/dynamics/calculators.py`: per-race time-ordered
  sweep (latest-per-driver <= T snapshots; F6 leader/ahead identities
  reused; follower provenance: successor id, its latest time/lap, its
  predecessor at that observation, red-side flag; field spread) +
  per-(race, driver) lap-window assembly (all 29 features; follower
  last-gap resolved against own causal history; uniform pit/SC masking;
  same-follower same-regime H5 runs). Label-blind (no label/mask/result
  field in schema; architectural test).
- `raceintel/features/dynamics/build.py`: deterministic sidecar builder
  (D9 join 1:1 validated; canonical dtypes; atomic write; provenance).
- `raceintel/features/dynamics/validation.py`: fail-closed checks
  (contract pin, parent identities, schema/dtypes/order, no infinities,
  nulls only where nullable, row identity 189,420 unique).
- `scripts/build_v3_race_dynamics.py`: refuses overwrite without
  --force; never trains/evaluates.

## Fixtures

`tests/v3_dynamics_synth.py`: label-blind point builders with causally
coherent follower defaults (last-gap 5.0 s / age 85 s / diff 1; lap-1
null by construction). Deterministic sweep rows.

## Suites (all green)

- contract (11): names/counts/dtypes/units/policies/sets/ALL_84/hash.
- primitives (9): OLS/F8 parity/endpoint-rate/IQR/spread/window/masking.
- calculators (9+4 new): goldens, boundaries, follower identity/regime
  breaks, strict predecessor check, red nulling.
- leakage (14+4 new): full future-poison battery, cross-driver poison +
  identity history, sweep poison, crossing-boundary regression (permanent
  V3.1A-C1 guard), future-follower poison, overtake identity.
- governance (5): v2 identity pin, import firewall, label-blind inputs,
  ALL_84 firewall, validation rejects.
- artifact Tier-3 (7): row identity, schema, join integrity both
  directions, provenance pinned, determinism rebuild, season/stage
  coverage, missingness/distribution sanity.

## Artifact

Ignored sidecar `data/v3/race_dynamics/` (git-ignored, reproducible):
189,420 rows x 29 features, logical SHA
`40ef05809e2932d725785a0e991bcecede8d884f2388affec3f56147611696a1`,
contract v3.1a-v2 pinned, parent content/parquet identities exact,
season coverage 2018-2025, join-exact both directions, deterministic
across rebuilds.

## Firewalls

ALL_84 = 84 (registry re-verified; no `dyn_` inside; disjoint sets). No
model trained. No predictions generated. No 2025 performance inspected.
No frozen artifact regenerated or overwritten. No spatial/simulation/
strategy/API coupling (graphify direction: frozen state -> contract ->
calculators -> validation/build).

## V3.1C handoff

Consume sidecar + provenance as-is (verify logical SHA). Arms/manifest/
splits/metrics per frozen V3.1A contract. VARIANT_A runs only under
predeclared promotion evidence. Holdout 2025 stays locked.
