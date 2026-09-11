# Phase-2 Relative / Field Context (F7)

> F7 cross-driver race context in `v2/features/context.py` (12 features,
> registry 44→56, schema v3→v4), 35 tests green, full 189,420-row audit
> clean. Depends on F1 (sync), F2 (registry/versioning), F3 (snapshot),
> F5 (pace basis), F6 (ahead identity/geometry). No rates, momentum,
> priors, or projections.

## 2. Temporal safety model

Every rival contribution comes from its own synchronized state ≤ T or
that rival's prefix ending there; target pace from its own prefix.
Same-lap future joins, nearest-time, final results, and
future-absence inference are impossible by construction (mutation-
tested). Ages are provenance, never gaps.

## 3. Measured synchronized-field evidence

18–20 participants/race; constructor_id never null; 1,722 pair-teams
vs 8 solos (429 solo rows: DNS/withdrawn teammates). Teammate
observable 98.9%; unique identity by construction (max observed team
size 2). Rivals with usable pace_median_5: median 19, ≥5 in 92.4%.
Ahead-gap bands (2 races): p50 ~2.6–3.1 s, ≤2 s ~40%, ≤5 s ~65%.

## 4–5. Pace basis + sign convention

ONE basis: `pace_median_5` (robust, highest coverage of the honest
options; representative's 82% would needlessly cut contributor
counts). Convention: target − reference (s/lap); negative = target
faster — identical across teammate/field/ahead (test-pinned).

## 6. Comparability policy

Both paces non-null under the same F5 eligibility; rival evaluated at
its own sync state; no causal adjustment. Named `relative_recent_
pace`, never advantage/delta claims. Stale pre-SC rival pace stays
valid history with its age — neutralization is downstream context,
not a correction.

## 7–9. Teammate identity, sync, features

Identity: exactly-one other observed driver sharing (race_id,
constructor_id) — slugs only, never number/display/final tables.
Substitutes inherit the seat's slug automatically; solos/ambiguous →
null (measured: 429 solo rows behave). Sync via `sync_state`; stale
kept with age (390 s test); unobservable → nulls. Four features:
relative pace, observation age, lap difference, synchronized position.

## 10–13. Observable field, aggregate, contributors, order

"Observable field" = sync states ≤ T (never "running field").
Median over comparable rivals (target excluded) with ≥5 contributors
(92.4% measured; null below). Count companion always defined.
Order counts (`observable_field_size`, `cars_ahead/behind_
observable`) count non-null sync positions directionally — duplicates
each count, no strict order manufactured. Percentile deferred (order
ambiguity unresolved by design).

## 14. Car-ahead relative pace

F6 unique-predecessor identity + same basis at its sync state; null
when ambiguous/absent or either pace missing. No closing rate, no
catch time (F8).

## 15–16. Traffic / pack decisions

`in_traffic_2s`: valid same-lap ahead gap ≤ 2.0 s (measured ~40%
band); null when geometry invalid/unknown; directional pressure
signal complementing (not duplicating) the continuous F6 gap. No DRS
inference anywhere (name search test-pinned). `nearby_cars_within_5s`:
same-lap line intervals ≤ 5 s both directions (~65% band),
laps-apart never counted, red-flag pairs excluded, 0 allowed. No
graph clustering — unjustified complexity deferred.

## 17–19. Staleness, race-state, lap-difference

No global or per-feature cutoff (ages exposed: teammate age; ahead
age via F6). Neutralized-state rival pace retained as history with
provenance. Lap differences don't gate pace (historical context)
while traffic/pack require same-lap valid geometry — separated
semantics by construction.

## 20–21. Registry / version

12 defs (teammate 4, field 5, relative 1, traffic 2), v1 each,
temporal SYNCHRONIZED_FIELD, sync RIVAL (teammate/relative) or FIELD
(field/traffic), exact D9 lineage, CANDIDATE. Schema v3→v4 exactly
once (+12 columns); Phase-1 untouched.

## 22–23. Single-state / batch-cache architecture

Single: exact target → snapshot → per-rival F5-at-sync via shared
`pace_values` → pure `context_for_snapshot` core. Batch: F5 basis
precomputed once per state, keyed by exact (driver, lap, time);
chronological equal-T-grouped sweep looks rival pace up. Cache is
past-only by construction (each value computed at its own boundary);
never latest-pace-reused-backwards (adversarial-tested).

## 24–25. Parity / leakage evidence

Single-vs-batch equality: synthetic + 8 real-race spots (dry, wet,
Britain, Belgium, Monaco, Japan, 2024/2025) green; shuffled-input
stable. Mutations (rival/teammate/ahead future pace, positions,
gaps, pits, weather/track, results, labels + extreme adversaries):
identical at T. Identifier mutations invisible (canonical IDs only).

## 26. Full-data coverage (189,420 rows, MEASURED)

teammate pace 87.55% / age 98.87% / lapdiff 98.87% / position 94.31%;
field median 91.51% / contributors always / field size always; ahead
pace 83.28%; in_traffic 90.43% (valid geometry); pack ~100% (null
0.16% = red targets). No infinities; deterministic rebuild.

## 27. Edge cases

Bahrain VER-28 (leads: no ahead, 19 behind, −1.94 vs field),
sargeant-55 (11 ahead/7 behind, pack 0, traffic false), Germany wet,
Belgium PARTIAL, Monaco/Japan suspensions, 2024/2025 nominal —
reviewed feature-by-feature with null reasons; no race-specific code.

## 28. Performance (MEASURED)

Full batch 97.7 s (incl. ~9 s F5 precompute); single-state 0.05 s
(per-rival recompute, spot-use only); suite impact small. No
infrastructure; state-keyed cache is the documented safe pattern.

## 29. Limitations

Percentile deferred; field median has no single age (contributor
count + individual ages via teammate/ahead instead); sector-local
yellows invisible (inherited); unknown-flag rows compute with null
context; 6-driver minimum implied by contributor rule (fine at
18–20-car fields).

## 30. F8 handoff

F8 consumes: relative levels (rates are differences of these),
validity/null patterns, age provenance, and the traffic/pack
geometry. Closing-rate, momentum, weather/RC trends, and priors are
F8+ — untouched here.
