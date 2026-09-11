# Phase-2 Rates + Momentum (F8)

> F8 backward-looking change features in `v2/features/rates.py` (4
> features, registry 56→60, schema v4→v5), 27 tests green, full
> 189,420-row audit clean. Depends on F1–F7 without reinterpreting
> any of them. Descriptive only: no catch time, no projections, no
> outcome interpretation. Relative-pace momentum DEFERRED with
> rationale.

## 2. Descriptive vs projective boundary

Every F8 value answers "what has been happening" over the trailing
history. Formulas of the form gap/rate, future positions, overtake
likelihood, and win/podium expectations are banned and absent
(name-search test-pinned).

## 3. Measured history coverage (1,200-target sample + full audit)

≥2 valid same-leader points: last-5 window 84.0% vs last-3 82.9% →
span 5 frozen (one robust window, not a family of windows). Caution
spans 26.6% of windows. Position anchor (own state ≤ N−5): 91.1%.
Pace double-median anchor: ~80%+ (audit: pace-change null 16.7%).

## 4–5. Gap-change semantics + reference continuity

`gap_rate_from_points`: OLS slope over the contiguous trailing run
sharing the CURRENT reference id with valid seconds; the walk STOPS
at the first invalid/different-reference entry — never bridged
across identity changes, red flags, laps-apart transitions, or
missing timing. Leader takeover (A→B) resets to the B run (tested).

## 6–7. Sign convention + denominator

Rate = d(seconds)/d(target lap_number); negative = closing,
positive = falling away — identical for leader and ahead. x-axis is
target lap (factual progress; red-flag elapsed time never enters).
Zero lap span is structurally impossible (distinct laps) and guarded.

## 8–9. Window + estimator

Trailing 5 target laps, OLS closed-form (numpy only; 2-point OLS =
endpoint delta exactly). ≥2 points required, no zero fallback, no
carry-forward.

## 10. Invalidity/reset policy

Null when: current gap invalid, run < 2 points, identity changed,
zero span. Bridging explicitly tested and rejected (red-in-middle →
null despite 5 surrounding valid laps).

## 11. SC/VSC policy

Option A retained with evidence: 26.6% of windows span caution, and
F6 seconds there are factual separation; SC compression is real
change, conditioned downstream via the `track_state` passthrough. An
all-clear-only rule would gut coverage without adding truth.

## 12–13. Position change

`recent_position_change_5laps` = position(latest own state ≤ N−5) −
current; positive = gained, 0.0 = held (factual, not null). Called
position change, never overtakes (gains include pits/retirements).
Null only when anchor/current position missing (8.97%).

## 14–16. Pace momentum

`recent_pace_change_s_per_lap` = (median_5 now − median_5 at anchor) /
actual lap delta; negative = faster. Both medians exact-state
past-only (never latest-pace-backwards). The 5-lap anchor separation
nearly eliminates rolling-window overlap (documented limitation, not
a hidden bias).

## 17. Relative-momentum decision

DEFERRED: changing rival references, churning field contributor sets,
stale sync states, and overlapping F5 windows make it unstable. F8
needs no feature from every category; no stub registered.

## 18–19. No-catch-time / no-outcome rules

`gap / rate`, catch laps, projected laps, and all probability/
expectation semantics are absent (registry name-search pinned) and
must stay that way into the Model Lab inputs.

## 20. Inventory (4, all CANDIDATE)

`recent_gap_to_leader_change_s_per_lap` + `recent_gap_to_ahead_
change_s_per_lap` (RATE, s/lap, NULL_IF_INVALID_GEOMETRY) and
`recent_position_change_5laps` (MOMENTUM, count) +
`recent_pace_change_s_per_lap` (MOMENTUM, s/lap, both
NULL_IF_INSUFFICIENT_HISTORY), v1 each.

## 21. Reference provenance

Continuity is enforced internally (ids compared, never exposed as ML
categoricals — no driver-ID columns). Basis strings available in
GapResults for debugging.

## 22–23. Registry / version

4 defs (RATE ×2 with SYNCHRONIZED_FIELD; MOMENTUM ×2 target-only,
correctly NOT claiming field sync), exact lineage, COUNT n=2.
Schema v4→v5 exactly once (+4 columns); Phase-1 untouched.

## 24–25. Architecture + historical cache

One module (`rates.py`): pure cores (`ols_slope_xy`,
`gap_rate_from_points`, `change_from_anchors`,
`rate_values_for_target`) shared by both paths. Single-state rebuilds
bounded trailing histories live; batch sweeps with exact-state
GapResult + F5 caches (every cached value past-only at its own
boundary; reference ids preserved — the scalar-cache dead-end was
rejected during implementation for losing continuity).

## 26–27. Single/batch + parity

Single: exact target → bounded own-history (≤11 states) →
rate_values_for_target. Batch: chronological per-race sweep with
pruned per-driver trails through the same core. Parity green on
synthetic + 8 real-race spots + shuffle stability.

## 28. Leakage tests

Future gaps/reference/positions/pace/track/pits/weather/results/
labels + enormous ± adversaries: identical at T. Discontinuity
(A→B, X→Y) and invalid-geometry (→laps-apart/red/unavailable)
suites green. Identifier mutations invisible.

## 29. Invariants

All sources ≤ T; continuity satisfied; underlying seconds valid;
denominator > 0; finite; no inf; positions factual; F5 values
exact-state. Pinned by test.

## 30. Full-data coverage (189,420 rows, MEASURED)

Nulls: leader rate 19.40%, ahead rate 28.49%, position 8.97%, pace
16.72%. Leader rate p50 +1.04 / p95 +5.17 s/lap (backmarkers drift;
extremes ±75 factual pit/red sequences, unclipped). Ahead rate p50
+0.05 (largely spaced field), extremes ±180/280 (pit cycles,
factual). Position −16..+16 p50 0. Pace −5.7..+5.1 (wet
transitions). Deterministic rebuild identical.

## 31. Edge cases

Bahrain VER-28 (leader: 0.0 / null-ahead / held / −0.053 improving),
PER-28 (closing −0.216, +1 gained), sargeant-55 (drifting +0.9);
Germany/Britain/Belgium/Monaco/Japan/2024/2025 parity spots green.
Histories consumed per §4–5 rules, explained per target.

## 32. Performance (MEASURED)

Full batch ~110 s (sweep + exact-state caches); single-state 0.1 s
(spot-use); suite impact moderate. No infrastructure; caches are
plain dicts keyed by exact state identity.

## 33. Limitations

5-lap span is a coverage/stability trade (documented 84% vs 83%);
position anchor reaches >5 back on skipped laps (divided by actual
delta — correct, not fixed-5); trend-in-rate vs sudden jumps both
pass through OLS honestly (no regime detection — Model Lab
business).

## 34. F9 handoff

F9 consumes: rate levels, null patterns (history sparsity signals),
and the exact-state cache pattern for weather/RC temporal context.
No new temporal machinery needed beyond F3 operators.
