# V3.11 — MC2 Coverage Expansion (Final Synthesis)

Programme: **V3.11 MC2 Coverage Expansion**
Parent: `v3.10-pit-wall` / `2c00e7e…`
Classification: **V3_11_MC2_COVERAGE_EXPANSION_FROZEN**
Decision: **STOP_V3_11_COVERAGE_EXPANSION** (terminal)

## Motivation

Production MC2 classified only 3678 of 9644 candidate states as
eligible (38.14%). V3.11 investigated whether that coverage could be
expanded safely — by understanding exactly why states were
unsupported, and by testing whether causal reconstruction or regime
modelling could admit more of them without breaking temporal safety.

Frozen starting breakdown:

| Class | Count |
|---|---|
| total | 9644 |
| eligible | 3678 |
| unsupported | 5966 |
| STALE | 3294 |
| TRACK | 1165 |
| WET | 801 |
| MISSING_DRIVER | 354 |
| MISSING_TYRE | 198 |
| TERMINAL | 154 |

## V3.11A — MC2 coverage forensics (`MC2_COVERAGE_FORENSICS_COMPLETE`)

Established the ground truth the whole programme rests on:

- STALE states are genuinely stale (real-world roster latency), not
  threshold-edge artefacts.
- TRACK states split into reconstruction candidates vs simulator
  capability gaps (the split C later re-derived exactly).
- R2 candidate discovery: 114 unique states (51 TIMING_GAP, 59
  NULL_TRACK, 4 TYRE_STINT) — the machine-readable ledger B validated.
- 39.91% arithmetic context: early A prose cited 39.91%
  (3849 = 3678+171) from an intermediate run predating the
  mass-clock-reset refinement; final machine artifacts say 114
  (3678+114 = 3792 = 39.32%). Machine arithmetic governs; no A
  artifact was rewritten to hide the intermediate figure.

## V3.11B — Causal reconstruction (`CAUSAL_STATE_RECONSTRUCTION_REJECTED`)

All three reconstruction rules rejected under a predeclared protocol:

- Timing-gap persistence invalid: persisted-vs-next exactness 0/54
  (lap and position); gaps span live-race evolution (median 16 laps).
- Tyre persistence unavailable: 0/4 states have a prior ≤T compound;
  the next-lap compound is future backfill (forbidden).
- NULL track not reconstructable: all 59 are pre-first-message nulls
  with no causal prior; feed-liveness is source interpretation,
  deferred to C.
- Zero production transitions. Coverage reaffirmed 3678/9644.

## V3.11C — Track-source/regime forensics (`TRACK_SOURCE_REGIME_FORENSICS_COMPLETE`)

- 1165 TRACK states forensically mapped: 1101 causally known regime,
  64 causally unknown (pre-first-message NULLs).
- Yellow is always local in the feed (no sector→driver channel
  exists); SC needs compression/restart modelling; RED is suspension
  discontinuity (unsupported by design).
- Feasibility: YELLOW F3, **VSC F2**, SC F3, RED F4. At most one
  regime recommended for research: VSC. Diagnostic ceilings labelled
  (VSC-secondary-free 41 → 38.57%; combined 233 → 40.56%).

## V3.11D — VSC regime model (`VSC_REGIME_MODEL_INSUFFICIENT_EVIDENCE`)

- Global pace ratio ~1.272 (validation MAE 9.54s pooled, 9.22s
  macro — passes the H-comparable 10s gate).
- Pace/order/withdrawal promising (all pass with good N).
- Gap/spread underpowered (validation N ≈ 2–3 episodes; failures are
  small-N instability, full-sample descriptives pass).
- Duration independently blocking (median rule unidentifiable).
- Pit semantics insufficient (out-lap n=7; fail-closed rule instead).
- No production integration authorized.

## V3.11E — VSC evidence resolution (`VSC_EVIDENCE_STILL_INSUFFICIENT`)

Predeclared evidence protocol (sha `b298c0a3…`) tested whether D's
failed dimensions could be resolved without weakening gates:

- Gap effective N=2 episodes (17 pairs; CI [1.04, 2.85]) → underpowered.
- Spread effective N=3 episodes (CI [1.18, 1.52]) → underpowered.
- Duration underpowered/miscalibrated (D1 KM: DUR1+DUR3 pass, DUR2
  hit rate 0.581 vs [0.6, 1.0]; calibration degrades with elapsed).
- `vsc_ending` micro-scope: N=7 laps → insufficient; quarantine held.
- Pit semantics mandatory (MC2 simulates pits forward) and
  insufficient (out-lap N=7 primary / 14 secondary) → blocker retained.
- Zero model dimensions refuted; four mandatory dimensions
  underpowered; D's supported dimensions (pace/order/withdrawal)
  re-verified.

## Terminal decision

Production integration is NOT scientifically authorized.

V3.11 coverage expansion terminates.

Production MC2 coverage remains 38.14% (3678/9644, delta 0).

SC, wet, yellow, and red/restart research are NOT automatically
authorized. Unchanged coverage is the honest programme result, not a
failure: the evidence was insufficient, not the investigation.

## Future research

Future work MAY revisit these questions only as a new, explicitly
funded/reopened research programme with additional
evidence/methodology. No continuation is scheduled.

## Programme identities

Deterministic sha256 over frozen bytes (recorded here; this document
is not itself hashed, so there is no circularity):

- `results/v3/v3_11_final/programme_manifest.json`
  `75fee65e8a5e873e4dbd535ebbe177970ceea7aae242ce436e3a07bd8b492d4e`
- `results/v3/v3_11_final/programme_scientific_card.json`
  `0921d834c988ba9c5528c788d1b3c21a7efc81f613c9b965d48ebc2a64805f49`
- `results/v3/v3_11_final/terminal_decision.json`
  `8864b43af04aa812cb1f950971c201cd8a7ecd93b506f2eaeac16c488170c600`
