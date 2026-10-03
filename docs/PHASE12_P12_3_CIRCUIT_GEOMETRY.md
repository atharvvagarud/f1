# PHASE 12 P12-3 CIRCUIT GEOMETRY

> Deterministic reusable 2D circuit geometry from canonical P12-2
> observations. Baseline `post-v2-clean-baseline` untouched. Nothing
> staged, committed, tagged, or pushed. P12-4 not started.

## Final verdict

**P12-3 COMPLETE — READY FOR P12-4**

## Baseline

- HEAD `218f4a653f8e7148d06fefc69798053b275795bc` =
  `post-v2-clean-baseline^{commit}`, before and after.
- Accumulated P12-0/P12-1/P12-2 work intact and unreorganized.
  `git diff` touches only `.gitignore`, `scripts/run_ci_tests.py`
  (collection pin via the governed path). Everything else untracked.

## P12-2 corpus

Source authority is the P12-2 observation manifest (identity
`87797e3f…`, never reconstructed): 173 sessions → 164 COMPLETE + 6
PARTIAL observations (170 artifacts, 106.76M rows) + 2 UNAVAILABLE +
1 FAILED (2024-r09-R, contract intact — see disposition below).
Geometry eligibility follows this manifest exactly.

## Empirical geometry study

Inspected Bahrain 2023, Monaco 2021, Japan 2024, Australia 2023 plus
Italy 2023 (high-speed), Belgium 2021 (very long, rain-shortened),
Netherlands 2024 (compact) — raw traces, moving-only traces, step
statistics, density, all in `/tmp` (no committed assets). Findings:

- Event-relative arbitrary origins; spans 7.5–20 km-units.
- 25–90% of samples are stationary repeats (garage/grid/red-flag/
  freeze tails) — the dominant contaminant, removed by motion rule.
- Teleport spikes to ~16 km; legitimate feed gaps to ~3.8 s.
- **Scale finding: 1 unit ≈ 0.1 m** (lap-length match on all study
  circuits), not 1 m as P12-0 prose loosely said. P12-1 dtypes
  (integral int64) are unaffected — no contract change; geometry is
  scale-agnostic with a uniform scale in the transform.
- Pit lanes form clean separable parallel bundles (Bahrain, Monaco).
- Suzuka crossover survives only with time-ordered phasing.
- Even Spa 2021 (9.6% moving) outlines the full circuit.

The algorithm was chosen AFTER this study (reference-lap + phase
binning), not before.

## Geometry contract

`spatial-geometry-v1` (declared in P12-1, now populated): race_id,
season, per-race layout scope, algorithm version, source block
(observation hash, row/selection counts, reference-lap facts),
`main_track` (render + raw points, closed_loop, length),
optional `pit_lane` branch, `pit_status`, deterministic transform,
quality metrics, logical content hash. No corner names, no sectors,
no speculative fields.

## Geometry scope

Per-race identity retained (`layout_scope: per-race`): layout edits,
coordinate-frame changes, and source variation across years make
cross-event deduplication unsafe. No global circuit registry built.

## Source selection

Moving (`step > 2u`) non-spike (`≤ 5000u`) observations; points
adjacent to spikes dropped. Stationary/garage/freeze clusters leave
by motion, never coordinate boxes. No lap/outcome labels used.
Typical yield ~45–70% of source rows (Spa 2021: 9.6%, still works).

## Main-track extraction

Reference lap (shortest qualifying window between consecutive passes
of the densest-100u-cell anchor; gap-free to 150 m, duration/path
bounded, deterministic tie-break) → 2048 arc-length anchors →
heading-gated nearest-anchor assignment → per-bin median with 15 m
trim → cyclic interpolation → Savitzky-Golay smoothing (derived
geometry only) → 512-point render loop. numpy/pandas/scipy only; no
new dependencies, no ML/CV. Two corpus-driven hardenings: the
gap-free bound was relaxed 40 m → 150 m after Silverstone 2023
(systematic ~1 s feed gaps, max step ~900u in every window), and
every candidate reference must pass an anchor-support check (≥ 97%
of anchors near eligible points) so shortcut/teleport chords fail
closed instead of ordering bins. Centerline length is descriptive
metadata: noisy feeds inflate it (Silverstone +17% vs the lap book)
while the rendered shape stays data-faithful; the transform is
bounds-based, never length-based.

## Reference-lap decision

Reference-backbone wins over direct point-cloud ordering: it gives
true loop order (required at the Suzuka crossover, where spatial
clustering is ambiguous), resists stationary clusters and spikes by
construction, and needs no lap tables. Alternatives (spatial
clustering, multi-driver averaging without order) were rejected on
the crossover and pit-branch evidence.

## Closed-loop semantics

First point stored once, `closed_loop: true`, renderer closes the
path — no artificial chord, no duplicated endpoint. Corpus closure
≈ 1 median segment (validation fails closed beyond 5×).

## Pit-lane decision

**PIT_GEOMETRY_SUPPORTED** where evidenced: Tier-A `pit_in_s/out_s`
windows (±8 s, documented historical-fact use) → moving-only
time-ordered paths → phase-normalized median → 128-point open path
with entry/exit connections to the main trace (≤ 30 m tolerance).
Moving-only is load-bearing: while boxed under GPS-denying
structures the feed parks on one fallback cell shared across all
stops of a race (observed: identical freeze cell in all 45 Brazil
2019 windows, then a catch-up teleport on reacquire). Frozen repeats
are box/fallback dwells — a render point, not a path — so windows
keep moving samples only; the median then stays on the lane (Brazil
2019 flips from wrongly-deferred to supported with 1 m/35 m
connections). Per-race gating (< 3 windows, bad connections,
degenerate length → `PIT_GEOMETRY_DEFERRED` with reason, main
geometry still COMPLETE). Corpus split: 168 SUPPORTED / 2 DEFERRED.
No fabricated paths.

## Outlier handling

General rules only, no per-circuit boxes: spike break + neighbor
drop, stationary exclusion, 15 m bin trim, median robustness.
Counts recorded (`source_rows`, `eligible_rows`,
`excluded_stationary`, `excluded_spikes`, `empty_anchor_bins`).

## Smoothing / simplification

Savitzky-Golay (41/3, wrap mode) on the 2048-bin centerline;
displacement recorded per race. Canonical observations untouched.

## Geometry resolution

Measured max chord deviation from the dense trace: 256 → 6–13.5 m,
**512 → 3–6.8 m**, 1024 → 1.6–3.4 m. Chose 512: deviations are
sub-pixel at any reasonable render size (1 px ≈ 11 m on an 800 px
minimap), 1024 doubles bytes for invisible gains, 256 exceeds 10 m
on fast circuits. Error recorded per race (`simplification_error_u`).

## Coordinate transform

Raw → translate → uniform scale → y-flip, stored as
`{scale, offset_u, offset_v, rotation_deg: 0, y_down: true, pad}`.
Single scale (aspect preserved by construction); source orientation
preserved (no aesthetic rotation). `raw↔render` closed-form both
directions; validation recomputes render from raw exactly.

## Orientation

Native FastF1 orientation retained in all corpus geometries (shapes
render correctly unrotated). No rotation applied anywhere.

## Render coordinate space

`[0, 1]²`, y-down (SVG-ready), 3% aspect-fit padding with centering
offsets stored. No race-specific frontend magic numbers: points are
used as-is; the same stored transform maps future driver
coordinates (P12-4).

## Transform consistency

Every artifact stores raw + render points; validation recomputes
render from raw with the stored transform (`atol=1e-9`) for main and
pit. Proven on all corpus artifacts (Part X analysis asserts it).

## Validation

Fail-closed: schema, identity, finite, ≥ 64 points, ordered NaN-free,
transform recomputation, render bounds, closure sanity, no
zero-length segments, pit consistency, hash reproducibility, plus a
metrics report. No brittle circuit-specific assertions.

## Quality metrics

Detection-only, no composite score, no ranking:
source-to-centerline median/p95, closure + closure/segment ratio,
segment median/max, simplification error, point-reduction ratio
(~1400× rows→points).

## Visual validation

All four golden plus study-circuit geometries plotted from the
persisted artifacts to `/tmp` and inspected: no shortcuts, no
self-crossing corruption (Suzuka crosses correctly), no broken
closure, no garage spikes, pit branches diverge/rejoin cleanly,
aspect correct. Qualitative development evidence; no committed
screenshots.

## Artifact format

Canonical JSON (`data/spatial/geometry/{race_id}.json`, ~95 KB):
small, frontend/API-friendly, independently hashable (content hash
over canonical values + byte identity of sorted-key bytes).
Parquet rejected: geometry is metadata-shaped, not tabular.

## Geometry manifest

Dedicated `data/spatial/manifests/spatial_geometry_manifest.json`
(`spatial-geometry-manifest-v1`, deterministic bytes): per-race
status + source observation hash + geometry hash + points + pit
status. Never mixed into the P12-2 manifest.

## Staleness

`verify_geometry_artifact`: COMPLETE row + source hash equals current
observation provenance + artifact validates + content hash matches.
Source change, tampering, or loss → rebuild. Tested (wrong-hash,
tampered-bytes, missing-file cases).

## Corpus generation

Eligible: all 170 COMPLETE/PARTIAL observation races → **170
COMPLETE geometries, 0 FAILED**. UNAVAILABLE/FAILED sources (2 + 1)
→ SKIPPED rows (never fabricated). Pit split: **168 SUPPORTED, 2
DEFERRED** (Spa 2021: zero pit windows in the 2-lap SC race; Austin
2021: exit connection 317u over the 300u tolerance — marginal,
honestly deferred). 2025: 24 geometries. Full run 1983.1 s
(~11.7 s/race); resume 0.3 s (170 verified skips, manifest identity
unchanged); force-rebuild determinism verified (hashes + manifest
identical).

## 2025 firewall

2025 geometries generated (TBD count); `SERVED_SEASONS` untouched;
DATA_AVAILABLE/GEOMETRY_AVAILABLE vs PRODUCT_NOT_SERVABLE stay
separate (tested).

## Storage

16.0 MB total JSON (170 artifacts): median 94.2 KB/race, p95
94.8 KB, max 94.8 KB — ~35× smaller than the 563.6 MB observation
corpus, as required.

## Performance

Representative 10–16 s/race (goldens 10.8–12.9 s); full corpus
1983.1 s (~11.7 s/race, 0.086 races/s); resume 0.3 s. No
optimization: per-race cost is bin assignment + median loops in
Python, fast enough at this corpus scale.

## Determinism

Force-rebuild of 2021-r05-R and 2023-r12-R reproduces geometry
hashes exactly with manifest byte-identity unchanged; full resume
likewise stable. JSON canonical bytes ⇒ same file SHA in the same
environment (proven; artifacts carry no timestamps).

## Tests

27 P12-3 tests in `tests/test_spatial_geometry.py` (synthetic loops,
tmp dirs; corpus integration outside CI): contract, selection,
reference (+fail-closed, +anchor-support rejection), resampling,
heading-gated assignment, medians/trim, interpolation, smoothing,
transform (aspect, bounds, round-trip), pit support/defer paths,
frozen-fallback regression, missing-table deferral, build +
validation + hash stability/sensitivity, failure modes, atomic
write, manifest round-trip + determinism, staleness/tamper, CLI
list + SKIPPED, 2025 distinction, firewall text-scan. Pin
3289 → 3316 through the governed path.

## Predictive firewall

Re-run green (spatial package auto-covered + explicit P12-3 scan):
no predictive→spatial, no spatial→predictive/API/web; Tier-A table
reads are local-file historical facts, not imports. ALL_84 = 84, no
geometry features. Presentation infrastructure only.

## Scientific identities

6/6 exact without regeneration (frozen surface + zero diff on frozen
paths; Tier-3 not run per P12-3 AL).

## Known limitations

- 1 unit ≈ 0.1 m is an inferred descriptive scale (lap-length
  match); the contract stores raw integral units + uniform scale, so
  no P12-1 change was needed.
- Reference requires ≥ 1 gap-free single lap; persistent SC/rain
  fragmentation could fail a race closed (none observed; would be
  FAILED with reason, not concealed).
- Pit branch needs Tier-A tables; missing tables → per-race deferral.
- 512-point chords deviate up to ~7 m in hairpins (recorded per
  race; sub-pixel for rendering).
- Socket-free stage: geometry reads only local files (observations +
  Tier-A); no network surface exists to guard.

## P12-4 handoff

`data/spatial/geometry/{race_id}.json` (raw+render centerlines,
transform, pit branch, quality) + deterministic geometry manifest
source-linked to observations. Resolver consumes `apply_transform`
semantics for driver coordinates; no resolver/API/frontend started.

## Entry gate

- [x] baseline exact; accumulated work intact; nothing staged
- [x] zero UNKNOWN; Graphify-first
- [x] empirical study before algorithm; real circuits inspected
- [x] contract defined; per-race scope; deterministic extraction
- [x] reference-lap question resolved with evidence
- [x] closed-loop correct; pit decision evidence-based, no fabrication
- [x] outlier rules general; only derived geometry smoothed
- [x] observations untouched; resolution justified; aspect preserved
- [x] reusable raw→render transform; no frontend magic numbers
- [x] validation + quality metrics; goldens visually inspected
- [x] JSON format justified; atomic writes; deterministic manifest
- [x] source linkage + staleness detection; corpus generated
- [x] 2025 allowed, unservable; storage/perf/determinism measured
- [x] canonical CLI; tests green; pin via governed path
- [x] ALL_84 = 84; predictive firewall green; 6/6 identities
- [x] preflight + ci green; frontend untouched
- [x] 2024-r09-R still FAILED; no resolver/API/frontend
- [x] report + record created; geometry ignored
- [x] nothing staged/committed/tagged/pushed; P12-4 not started
