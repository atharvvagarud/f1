# Phase-2 Gap Engine (F6)

> F6 factual race separation in `v2/features/gaps.py` (8 features,
> registry 36→44, schema v2→v3), ~30 tests green, full 189,420-row
> audit clean. Depends on F1 (sync), F2 (registry/versioning), F3
> (snapshot/index), F4/F5 (engine dispatch). No cross-family logic.

## 2. Why the legacy scalar is rejected

D10: lap10 used a session-minimum reference (often a stale/retired
row) with [0, 300] clipping — 672/2,067 rows pinned at 300, 2019
Belgium 20/20 at 300 (incl. the leader, true gap 0.0) plus a −1,193 s
value clipped to 0.0. F6 never references a session minimum, never
clips, and returns null with reason instead of a fabricated number.

## 3. Measured timing evidence

4,000-target sample: leader rules agree 97.6%; unique-P1 98.4% (0: 0%,
2+: 1.6% — pit-cycle skew); duplicate snapshot positions 32.5%
(transient skew, motivates the ahead guard); same-lap leader
availability 87%. Predecessor rule: 96.3% unique / 3.7% multi / ~0%
zero; 99.8% of unique-ahead pairs share the observed lap.

## 4. Leader identity semantics

Unique synchronized position-1 holder (official timing order); else
the target itself when it holds P1 (provisional, e.g. first lap-1
crosser); else max-lap earliest-crossing among OTHER observables
(pit-skew fallback); else unknown. Never final results, never a guess.

## 5. Car-ahead identity semantics

Unique holder of (target_pos − 1) among observable sync states.
Leader/null-position → NO_CAR_AHEAD; 0 or 2+ holders →
ORDER_AMBIGUOUS (null, 3.7% measured multi). F7 traffic/packs build on
this, not vice versa.

## 6. Structured gap contract

`GapResult(status, target_id, reference_id, target_lap,
reference_lap, lap_difference, seconds_gap, seconds_valid,
reference_age_s, basis)` with `GapStatus`: VALID_SECONDS, LAPS_APART,
NO_CAR_AHEAD, REFERENCE_UNOBSERVED, TIMING_UNAVAILABLE (defensive),
RED_FLAG_INVALID, ORDER_AMBIGUOUS. One status per result; no redundant
flag sprawl.

## 7. Sign convention (frozen, tested)

`seconds_gap = T_target − T_reference ≥ 0`; positive = target trails
(crossed the shared line later); 0.0 = leader self or dead heat.
`lap_difference = target_lap − reference_lap` (0 equal, negative =
laps down; +0.04% positive transients reported, never clipped).

## 8. Same-lap crossing semantics

Both crossings are lap-end `state_time_s` values ≤ T (target's own row
+ reference sync row on the same observed lap). The difference is the
official-style line interval. A rival's future crossing of that lap is
never retrieved (tested: adding it leaves T-output identical).

## 9. Lapped-car semantics

Different observed laps → LAPS_APART with signed lap_difference;
seconds null, never lap×seconds fabrication. 13.13% of leader gaps
are laps-down; 0.04% laps-up transients preserved.

## 10. Observation-age distinction

`reference_age_s = T − reference_time` always carried, even when
seconds is null (laps-apart 190 s age vs null gap — tested). Separate
names make accidental conflation impossible; age has no cutoff.

## 11. Red-flag behavior

Red token on either observed row → RED_FLAG_INVALID (seconds null;
identity/lap/age kept). Measured: 93.2% of red-target rows invalid;
the remainder are leader self-references (0.0 by identity, documented).
Suspension breaks the spatial reading of clocks — frozen.

## 12. SC/VSC behavior

Factual intervals retained (SC 92.1% valid med 17.0 s; VSC 89.0%;
yellow 87.5%): the cars did cross those lines at those times. F6
measures separation, not performance — downstream conditions on the
`track_state` passthrough. Nothing auto-nulled without evidence.

## 13. Pit behavior

Crossing times are used as-is: a reference that pitted on the shared
lap yields its factual (inflated) interval — the on-track gap
including pit loss, which is the correct gap. No pit-loss math, no
"correction" (tested both directions).

## 14. Stale-reference behavior

Ages ride along (leader age p50 26.3 s, p95 76.9 s, max 2,501.8 s);
no global cutoff; staleness never implies retirement. Validity comes
from lap/flag geometry, not recency.

## 15. Missing timing

Null crossing → TIMING_UNAVAILABLE (defensive; frozen D9 has 0 null
clocks — tested with synthetic nulls).

## 16. Registered F6 features (8, all CANDIDATE, family GAP)

`gap_to_leader_laps` (int64 laps), `gap_to_leader_seconds` (float64
s), `gap_to_leader_seconds_valid` (bool tri-state: True valid, False
invalid, None unknown reference), `leader_observation_age_s`
(float64 s, provenance), plus the `gap_to_ahead_*` / 
`ahead_observation_age_s` quartet. All temporal
SYNCHRONIZED_FIELD + sync SYNCHRONIZED_FIELD, min-history NONE,
seconds NULL_IF_INVALID_GEOMETRY, laps/age/valid NULL_IF_NO_SYNC_STATE,
exact D9 lineage, version 1 each. No undocumented outputs.

## 17. Legacy comparison (diagnostic, not reproduction)

2023 Bahrain lap 10: F6 seconds are a permutation of legacy values
(same multiset, row-order only) — F6 reproduces correct
position-referenced semantics on clean races. 2019 Belgium lap 10:
legacy 19×300.0 + one 0.0 (the −1,193 s clip) vs F6 0.0–51.5 s spread
with leader exactly 0.0 — the min-rule + clip defect chain replaced by
per-state synchronized crossings. Legacy never trains or validates F6.

## 18–19. Single-state / batch paths

Single: exact target → F1 field snapshot → `gaps_for_snapshot` →
registered values merged with earlier families (17.8 ms over a race
frame). Batch: chronological per-race sweep grouping equal timestamps
(same-T rivals visible per the ≤T rule) through the SAME pure core
(`gaps_for_snapshot`); 85.1 s whole-scope, no full scan per target
(vs 314 s naive). No training/serving split.

## 20. Parity

Single-vs-batch equality on synthetic + 8 real-race spots (dry, wet,
Britain, Belgium, Monaco, Japan, 2024/2025) — mandatory and green.

## 21. Leakage/mutation evidence

Future rival states/crossings/positions/track/pits/results/labels:
identical at T. Adversarial core: rival lap-L crossing after T never
creates seconds (tested both directions). Identifier mutations and
shuffles invisible. Red/SC/VSC/pit/stale/missing cases above.

## 22. Full-data coverage (189,420 rows, MEASURED)

Leader seconds valid 86.64% (median 26.9 s, p99 93.3 s, max 442.6 s
— investigated, factual backmarker spread, never clipped); laps
86.83% equal / 13.13% down / 0.04% up; valid-flag 86.64/13.36/0.00%.
Ahead seconds valid 90.43%, invalid 5.78%, unknown 3.79%. Leader age
p50 26.3 s / p95 76.9 s. By target track: green 86.4%, SC 92.1%,
VSC 88–89%, yellow 87.5%, red 6.8% (remainder = leader self-identity),
unknown 99.9%. Seasons 80–93% (early seasons lower via 2018
sparsity/PARTIAL mix). Race-level rebuild identical; null snapshot
printed by the audit test.

## 23. Edge cases (8-race review)

Bahrain/Germany/Britain/2024/2025 nominal with exact-valid leader and
midfield gaps; Belgium/Japan PARTIAL synchronize with thin histories;
Monaco red-suspension invalidates seconds while keeping identity;
lapped-driver rows carry laps-down + null seconds. All reviewed
against §8–§14 rules — valid or explicitly null, never fabricated.

## 24. Performance (MEASURED)

Single 17.8 ms (race-frame snapshot) · batch 85.1 s whole-scope ·
RSS within the existing pandas envelope · deterministic. No
infrastructure; no optimization claims beyond the sweep-vs-naive
measurement (85 s vs 314 s).

## 25. Limitations

Position-dependent identity inherits timing-skew transients (resolved
by the documented fallback, never hidden); sector-local yellows under
green tokens are invisible to the flag gate (accepted, F5-shared);
unknown-flag rows compute crossing facts with null context; ahead
coverage 96.3% by construction (ambiguity → null).

## 26. F7 handoff

F7 consumes: the 8 gap features, `GapResult.basis` strings for
debugging, predecessor/leader rules (do not re-derive identity), and
the validity doctrine for traffic/pack definitions. Relative pace,
teammate, field, traffic, and rates are F7 — untouched here.