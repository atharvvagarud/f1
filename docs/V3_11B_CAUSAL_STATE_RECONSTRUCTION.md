# V3.11B — Causal State Reconstruction

Status: **CAUSAL_STATE_RECONSTRUCTION_REJECTED — scientifically valid,
investigation complete.** Zero production implementation, zero eligibility
change, zero MC2 futures. Coverage is an outcome: 3678/9644 (38.14%),
delta +0.

## 1. Basis

- Frozen base `v3.10-pit-wall == 2c00e7e` (HEAD matches; tag unmoved).
- Predecessor V3.11A `MC2_COVERAGE_FORENSICS_COMPLETE` (uncommitted,
  artifacts read-only, never rewritten).
- R2 registry: exactly **114** unique states from the machine-readable A
  ledger — 51 TIMING_GAP, 59 NULL_TRACK, 4 TYRE_STINT.
- Arithmetic: 3678+114 = 3792/9644 = **39.32%**. The 39.91% in A prose
  corresponds to 3849 = 3678+171, an intermediate A run predating the
  mass-clock-reset refinement; final A machine artifacts already say 114.
  Machine arithmetic governs; no A artifact rewritten.

## 2. Protocol (pre-declared, sha `58496070`)

Three field-specific classes, no generic carry-forward:
H-T1 timing-gap (unanimity criteria from V3.2K gates: lap/position exact
51/51, exclusions 51/51), H-Y1 tyre-within-stint (same-stint ≤T 4/4,
unambiguous boundary 4/4), H-K1 null-track (pre-declared REJECTED-for-B:
no prior status exists, source interpretation belongs later).

## 3. V3.2K review

K sought fresher raw observations (gates: position 0.8551, lap 0.9485,
pit 0.9412, tyre absent → REJECT_DIRECT_RAW_STATE_RECONSTRUCTION;
RAW_SOURCE_STALE 2866: staleness is real-world). H-T1 is not the revived
K rule (persist stale row vs fetch fresher row) but hits the same wall:
no contemporaneous evidence exists.

## 4. Verdicts

- **TIMING_GAP_RECONSTRUCTION: REJECTED.** Persisted-vs-next: lap exact
  0/54, position exact 0/54; exclusions survive 0/51. Gaps 247–2813 s
  (median 1506 s); leader advanced 4–29 laps (median 16) during gaps;
  48/54 gaps contain yellow regimes; race_time errors median 3990 s.
  Even the 6 regime-clean gaps fail exactness. Freezing dynamic timing
  across live-race evolution fabricates state.
- **TYRE_WITHIN_STINT_PERSISTENCE: REJECTED.** All 4 states are 2018
  lap-2 states whose missing drivers' only ≤T rows are compound-null /
  stint-null lap-1 rows: 0 drivers with prior ≤T compound, Y1 0/4. The
  next-lap ULTRASOFT is future backfill, forbidden. No testable R2
  instance; broader validation would serve zero B transitions (§15).
- **NULL_TRACK_SEMANTICS: REJECTED for B / DEFERRED.** All 59 are
  pre-first-message nulls with no causal prior (0/64). Feed-liveness
  proof is source interpretation for the track-source stage. Nothing
  invented.

## 5. Consequences

- Accepted rules: none. Production diff: none (verified empty over
  `raceintel/ api/ frontend/ ml/`). Native parity: catalogue hash
  unchanged, frozen suites green. Unsupported parity: 5966 unchanged,
  same reasons, zero collateral expansion, zero eligible→unsupported.
- Transitions: none. Coverage reaffirmed 3678/9644. MC2 input validation:
  NOT_APPLICABLE (0 newly eligible). Simulations run: 0 (no 5000-future
  campaign, no smoke simulation needed).
- Poison: nothing new to poison; analysis scripts use
  `searchsorted(T, side=right)-1` with next-native rows as offline labels
  only; H-T1's reappearance-knowledge temptation is blocked by the
  rejection itself. Boundaries: `==T` observed, `>T` excluded, no
  nearest-row behavior; no red-flag bridging; no pit-boundary carries.

## 6. Tests / guards / collection

- Focused `tests/test_v3_11b_reconstruction.py`: 21/21 (registry,
  protocol, verdicts, rejections, parity, eligibility, poison,
  read-only firewall).
- Regression green: V3.11A suite, RaceState/phase-4/5 suites, J/K/2F
  suites, presence/contract/parity/2N, phase-6 freeze, MC2 batch,
  V3.8/V3.9/perf/V3.10 guards (collection pins reconciled 5208→5229
  for the 21 new tests + B allowlist, established pattern).
- Collection: 5229. Pre-existing, untouched:
  `test_v39_freeze_provenance_unchanged` (stale commit pin, fails on the
  clean tree). No Tier-1 (no shared-runtime change to justify it), no
  frontend run (untouched).

## 7. Deferred / next gate

Mass-reset (196), disappearance (3047), driver identity (no-op),
wet/regimes (out of scope). Recommended next gate: **TRACK REGIME
SUPPORT research** (yellow local-exposure semantics + VSC/SC/restart
modelling per V3.2F/H) rather than further stale stretching — or the
track-source stage for null-token/feed-liveness semantics, which would
also unlock re-examination of the 59+4 null-track states. Do NOT
implement V3.11C, TRACK/WET modelling, or commit/tag/push (A+B stay
reviewable together).
