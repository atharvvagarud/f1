# Phase-2 Leakage + Parity Audit (F14)

> F14 objective: attack the complete F4–F13 feature + label pipeline
> and attempt to prove it unsafe. Adversarial verification ONLY: no
> new feature family, no new target, versions frozen (features `v8` /
> 84 defs, labels `v1` / 7 defs). Depends on F1–F13 without
> reinterpreting any of them. One narrow validation hardening was
> applied under §50 (duplicate-key guard in grid resolution);
> everything else held as frozen.

## 2. Frozen entry state (verified, not assumed)

`FEATURE_SET_VERSION=v8`, 84 predictive definitions;
`LABEL_SET_VERSION=v1`, 7 label definitions; D9 states 189,420;
race-driver labels 3,458; races 173; no telemetry family/module/
artifact. Entry baseline: 641 passed / 4 xfailed / 21 frontend /
D11 44-0-0.

## 3. Threat model

20 classes (A–T) frozen in `tests/f14_helpers.py::THREAT_MODEL`:
same-driver future (A), cross-driver future (B), same-lap rival (C),
future weather (D), future race control (E), current-race results
(F), future-race priors (G), label leakage (H), presentation
identity (I), row-order dependence (J), single/batch drift (K),
missingness collapse (L), tri-state collapse (M), race-boundary
off-by-one (N), source contamination (O), final-state inference (P),
state-dependent label mistakes (Q), stateless participants (R),
cache/index leakage (S), equal-timestamp ties (T).

## 4. Leakage matrix

`leakage_matrix()`: every active family × 16 mutation ids →
NO (forbidden) or MAY (eligible). All 10 forbidden classes
(F_OWN/F_RIVAL/F_INSERT/F_DELETE/F_WX/F_RC/CUR_RES/FUT_RES/LABELS/
IDENT) are NO for every family; SELF/PAST_*/GRID_SELF are MAY only
where the family contract consumes them (e.g. priors MAY only on
PAST_PRIOR; grid MAY only on SELF/GRID_SELF). Pinned by test.

## 5. Feature dependency manifest

`feature_dependency_manifest()`: 84 machine-readable entries (name,
family, version, temporal rule, sync, exact sources, status,
allowed/forbidden mutation sets). Every entry forbids LABELS and
IDENT; cross-driver families declare non-NONE sync (registry-validated).

## 6. Label dependency manifest

`label_dependency_manifest()`: 7 entries (source, grain, derivation,
eligibility, constant-vs-specified, task, status). All forbid
`feature_calculator` upstream. The 4 CANONICAL targets are
race-driver constant; the 3 SPECIFIED formulas are state-dependent
specifications materialized only in F15.

## 7. Own-driver future attacks (§§5–7)

Per target (10-target campaign): extreme mutation of ALL future own
rows (position/lap-time/tyre/stint/pit/track/weather/identifiers),
synthetic future-row insertion (incl. T+0.001 same-lap rival row),
and full future-row deletion — all 84 features bit-identical
(`results_equal`). Attacks `tail()/last()/rolling`-over-unsliced-frame
bug classes directly. 10/10 targets × 3 attacks green.

## 8. Cross-driver future attacks (§8)

Future rival rows (all drivers, all columns incl. pace/stint/track/
pit inputs) mutated to extremes: identical. Mandatory for
gap/relative/teammate/field/traffic/rate/interaction — green on all
campaign targets.

## 9. Same-lap adversary (§9)

Real pair (2019-r04-R: same nominal lap crossing after T within the
121 s dry spread): rival same-lap future row set to P1/45 s — target
unchanged; the system used the rival's latest row ≤T. Synthetic
T+0.001 insert covered in §7. T+eps/1 ms/equal-timestamp/lap-behind/
lap-ahead semantics hold per F1 §4 (latest ≤T, never same-lap).

## 10. Equal-time adversary (§10)

2021-r08 stroll laps 4/5 (T=2349.136): both states resolve
distinctly (lap 4 precedes lap 5); full-84 at lap 5 identical across
3 shuffle seeds; single/batch parity holds. Cross-driver ties (max
observed size 5) resolve by driver_id; no "last input row wins"
(frame/index parity pinned in F3, re-verified here).

## 11. Cache / index audit (§11)

`RaceIndex` (searchsorted fast path) vs module-level reference path:
duplicate target keys raise explicitly on both (`TemporalError` /
`TargetNotFoundError`); exact target resolves identically; shuffled
inputs agree (see §28). No optimized path exposes more than the
reference semantics.

## 12. Weather attacks (§§12–13)

Future obs mutated/inserted at T+eps/T+1/T+59/T+300 (rain flip,
extreme temps/pressure/humidity/wind): F9 outputs identical —
nearest-future remains impossible; the 5-minute anchor lookup only
walks backward. Positive control: +5 °C on all eligible past obs
moves air/track deltas (suite would fail if the source were
ignored).

## 13. Race-control attacks (§14)

Future yellow/SC/VSC/red/all-clear transitions: duration/transition/
fraction features unchanged. Repeated-token stability: durations
derive from run starts; future repeats cannot reset them (covered by
future-row mutation + F9 transition tests).

## 14. Current/future-result attacks (§15)

Radical rewrite of race R outcomes (finish/points/status in both D5
results and Tier-B rows for R) and of all future races: all 84
features identical, priors included (H<R excludes R; future
excluded). Documented exception, tested as positive: changing the
factual PRE_RACE grid itself moves only `grid_position` +
`positions_from_grid`.

## 15. Historical-prior positive controls (§§16–17)

Eligible H<R result rewrite moves dependent driver priors while
leaving all non-prior families identical (dependency isolation, not
just non-leakage). Off-by-one pinned: round N+1 rewrite → identical;
round N−1/prior-season rewrite → moves. Season-boundary chronology
(last Y → first Y+1) unit-tested on `history_before` (canonical
season/round ordering, never lexical race_id).

## 16. Label firewall (§18)

Radical label rewrite (all winners False, all positions 20, all
points 0) → all-84 recompute identical across campaign races, with
null/bool/int exactness and float tolerance only where
mathematically required. Engine accepts no labels input by
construction (source-scan pinned).

## 17. State-dependent label audit (§§21–22)

Formulas verified on ties/±1/nulls. Ordinal-eligibility helper
(`ordinal_training_eligible`, F14 verification scope, no label
value changed): classified+numeric → True; unclassified (incl. W/D
back-rank numerics) → False; unknown → None. Measured: 3,007
eligible vs 3,455 non-null final_position — pinning that non-null
≠ ordinal-eligible. Phase 3 conditions ranking/ordinal use on this.

## 18. Final-position eligibility (§22)

See §17. The contract never implies every non-null final_position
is ordinal-training-valid; the helper + tests make the distinction
mechanical for Phase 3.

## 19. Stateless participants (§24)

Six zero-state keys keep labels, contribute zero D9 states
(verified both directions; 0 state keys lack labels), resolve to
permanent unobservable entries in field snapshots (mazepin 2021-r22
proven via the frozen roster path), and cannot acquire future state
(sync only reads ≤T rows; none exist). F15 join semantics safe.

## 20. Stale rivals (§25)

Retirees persist as observable history with factual ages (e.g.
>60 s ages present and observable at 2023-r01-R sargeant-55); no
global cutoff removes them; no final result/status decides
retirement (stale ≠ retired, F1 §14). Ages always ≥0.

## 21. Gap/reference attacks (§§26–27)

Invalid geometry → seconds null (VALID_SECONDS=false never carries a
number; valid seconds ≥0); traffic tri-state never collapses unknown
to True/False; F11 gates propagate nulls. Reference takeover:
clocks shifted +30 s deep in a superseded era leave the trailing
rate identical (no bridging; reset semantics proven, not just
documented).

## 22. Pace correctness (§§28–29)

Eligibility matrix pinned (pit-in/out, lap 1, yellow/SC/VSC/red,
unknown token, null lap time → ineligible; huge factual 2,500 s lap
→ eligible — no magnitude filter, no new clipping). Semantic
correctness independent of parity: synthetic window [103, 200-pit,
90, 91, 92+pit-out] yields exactly pace_n_3=3, median 91.0
(pit laps excluded from the rolling window, not just parity-equal).

## 23. Missingness (§30)

Registry audit: all 84 definitions carry explicit missing policies;
no unjustified deterministic fallback (validator-enforced). Code
scan: zero `fillna(` in feature/label code. Observed: leader has no
car ahead (null, never zero); unknown gaps stay null; 294
position-null states propagate.

## 24. Tri-state semantics (§31)

True/False/None preserved through gap validity, traffic flags, F11
gated interactions (legitimate 0.0 distinguished from null), and
nullable labels (3 winner nulls survive, never coerced). No
`bool(None)`/`fillna(False)` anywhere in the pipeline.

## 25. Identity (§32)

Global presentation rewrite (abbreviation, number) → all-84
identical; roster/label joins keyed on slugs only (presentation
rewrite → identical canonical frame, F13). No name/number matching
in temporal selection, sync, priors, or joins.

## 26. Shuffle/determinism (§§33, 36)

Multi-seed shuffles of states (and weather/history/labels by
construction of order-free operators) → identical outputs. Complete
84-feature batch rebuilt twice → identical schema/order/values.
Request order and subset/superset requests return identical values
(registry-ordered output; no mutable cross-request state). Engine
reuse A→B→A → identical (no stale cache contamination).

## 27. Duplicate-key defense (§34)

Label keys: ValueError. Exact target: TemporalError. Grid lookup:
TemporalError (hardened in F14 — was silent iloc[0]; validation
only, upstream PK already guarantees uniqueness). Index snapshot:
explicit TargetNotFoundError. Nothing is silently dropped or
arbitrarily selected.

## 28. Complete single/batch parity (§35)

17-target set (seasons 2018–2025; early/mid/late; wet/dry; SC/VSC/
red; pit cycles; traffic; lapped cars; partial races; tie lap;
pit-lane starter kubica Baku-2019-49; takeover race): all-84 single
== batch, including on shuffled inputs. Belgium 2021 full-race
(60 states) batch == per-state singles. Family-by-family parity was
already proven in F4–F11; F14 proves the composed complete set.

## 29. Request/subset consistency (§§37–38)

Name-order permutations → identical values; pace-alone ==
pace-within-superset (no context-sensitive semantics; attacks hidden
mutable caches).

## 30. Static source audit (§40)

Predictive modules import no label builder/registry/targets/results
(`registry.py` NAME-guard import is metadata-only, §22-mandated).
Table readers: `priors.py` alone (H<R history + grid identity);
`temporal.py` operates on generic frames (no table names). No
feature calculator touches `race_driver_labels`.

## 31. Future-sensitive pattern audit (§41)

No `shift(-1)`, `bfill`/`backfill`, `center=True`, `merge_asof`, or
executable `nearest` in feature code (`nearest` appears once: the
temporal.py docstring forbidding substitution). Sorts use explicit
temporal keys; `iloc[-1]` only post-`<=T` filter. `tail()` only on
prefix-filtered (pace) or H<R-sorted (priors) frames. Every match
dispositioned; tests pin the clean set.

## 32. Full mutation campaign (§43)

10 targets × 10 forbidden mutations (100 negative cases) green;
6 eligible-source positives green with family-scoped isolation
(changed ⊆ MAY, forbidden-pure families untouched). Both directions
required; suite fails if either side goes silent.

## 33. Full-data invariants (§44)

Stratified sample (5 races × early/mid/late, 150+ states): 84-col
schema, finite floats, bool/int domains, ages ≥0, fractions in
[0,1], progress in [0,1]. Full-scope key audits: D9 PK clean
(F0: 0 dup/null over 189,420); labels match all 3,452 state keys
with 0 missing; no feature/label name overlap; no telemetry
family/module/artifact. No F15 artifact materialized (in-memory
audit only).

## 34. Season audit (§45)

States: 22,337 / 23,676 / 18,352 / 23,758 / 23,577 / 24,422 /
26,606 / 26,692. Labels: 420/420/340/440/440/440/479/479. Null-rate
spot: 2018 track_state missingness highest (sparse era, documented).
No suspicious discontinuity from weather/priors/circuit-history/
telemetry-absence; genuine historical differences (field sizes,
PARTIAL races, 2020 short season) preserved, not "fixed".

## 35. Race-stage audit (§46)

Bands on factual `race_progress_frac` (early <1/3, mid, late >2/3):
windowed-family null rates fall from early to late (min-history
bites early only — structural, asserted). Diagnostic only; no stage
feature created.

## 36. Abnormal races (§47)

Belgium 2021 (60 rows) and Japan 2022 (507 rows): full-84 computes
clean (finite, schematically valid); labels official/factual;
missingness explained by thin histories; code scan confirms zero
race-specific patches in feature/label code.

## 37. Performance (§48)

Measured (this session): full-84 single-state ≈0.47–0.57 s (normal
race, live primitive recompute); complete F14 suite 192.7 s
(139 tests, heavy mutation/parity campaign); full Python/V2
regression 1,049 s (17:28). No semantic optimization was performed.
F15 recommendation: compute per-family batch columns once and reuse
(F11's ~6 min audit pattern); avoid per-state engine fan-out over
189,420 states (naive ≈26 h single-threaded at 0.5 s/state).

## 38. Findings

- BLOCKER: none. MAJOR: none.
- MINOR-1 (fixed, §50-permitted): `resolve_grid` silent `iloc[0]`
  on duplicate results keys → now explicit TemporalError.
  Upstream PK already guarantees uniqueness (F0: 0 duplicates);
  doctrine now uniform (labels/target/grid/index all fail
  explicitly).
- INFO: pandas concat FutureWarning in f11 full-scope audit
  (pre-existing); `python3` no-op shim (use functional python3.11);
  W/D back-rank numerics require the §17 eligibility gate in
  Phase 3 (pinned, not a defect).

## 39. F15 readiness decision

READY FOR F15: all 45 pass criteria satisfied, versions frozen
(v8/84, v1/7), regression green, no unresolved BLOCKER or MAJOR.
F15 consumes: v8 registry, v1 labels, validated builder + join
contract, per-family batch reuse pattern, and the §17 eligibility
helper.
