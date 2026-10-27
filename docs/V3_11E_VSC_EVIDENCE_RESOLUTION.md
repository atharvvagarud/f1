# V3.11E — VSC Evidence Resolution

Status: **VSC_EVIDENCE_STILL_INSUFFICIENT — TERMINAL FOR V3.11 COVERAGE
EXPANSION.** Evidence stage only: no model redesign, no threshold
changes, no production integration, no eligibility change, no MC2
campaign. Coverage unchanged 3678/9644 (38.14%).

## 1. Basis

- Frozen base `v3.10-pit-wall == 2c00e7e` (HEAD matches; tag unmoved).
- Predecessors (uncommitted, read-only, never rewritten): V3.11A
  `MC2_COVERAGE_FORENSICS_COMPLETE`, V3.11B
  `CAUSAL_STATE_RECONSTRUCTION_REJECTED`, V3.11C
  `TRACK_SOURCE_REGIME_FORENSICS_COMPLETE`, V3.11D
  `VSC_REGIME_MODEL_INSUFFICIENT_EVIDENCE`.
- Navigation baseline (`docs/INDEX.md`, `scripts/README.md`) used for
  orientation only; unmodified; no scientific content.
- E protocol `evidence_resolution_protocol.json`, sha `b298c0a3…`,
  created and hashed BEFORE any E scoring (script
  `scripts/v3_11e_protocol.py` ran first; content-addressed writes).
  D thresholds reused verbatim; no coverage gate; split unchanged.

## 2. D blockers (frozen input, registry `d_blocker_registry.json`)

D: G1 pass (MAE 9.54s pooled), G2 fail (gap median 1.06 vs ≤1.0),
G3 pass (order 4.7%), G4 fail (spread 1.418 vs [0.8,1.25]), G5–G8
pass; duration independently blocking (median rule unidentifiable);
pit-loss insufficient (out-lap n=7); `vsc_ending` micro-scope refused
post-hoc. R_cal=1.272 frozen; E does not refit pace.

## 3. Duration (EQ1/EQ2) — UNDERPOWERED, still blocking

- EQ1 mapping (read-only MC2 sources): **B HOLDS**. MC2 builds a
  forward kernel at T and steps laps beyond factual time
  (`engine.py:_schedule_next`, `_trace_event`); A holds only for
  anchoring/replay AT T. Forward VSC simulation needs duration
  handling; C (stochastic distribution) was the candidate under test.
- Dataset: 82 intervals (43 calibration / 39 validation; 80 complete,
  2 right-censored END_OF_DATA, 11 competing SC/RED exits, 41
  single-lap-or-less). Median 69.8s, max 394.45s; 26 circuits, none
  with ≥10 calibration-complete durations (D2 circuit bar fails);
  N_cal_complete=43 < 50 (D2 bar fails) → D2 not constructed.
- D1 (Kaplan-Meier + conditional survival), 62 scored validation
  queries at elapsed {30,60,120}s: DUR1 sample PASS; DUR3 sharpness
  PASS (median AE 56.9s ≤ 90s); **DUR2 calibration FAIL** (80%
  interval hit rate 0.581 vs [0.6,1.0]). Hit rate degrades with
  elapsed (0.71 → 0.50 → 0.36): conditional calibration fails exactly
  where MC2 needs it (longer elapsed). Verdict UNDERPOWERED
  (feasibility; refutation not applicable).

## 4. Gap (EQ3) — UNDERPOWERED (N=2 episodes)

- EQ5 first: `vsc_ending` N=7 driver-laps (<20) →
  INSUFFICIENT_EVIDENCE; quarantine holds; D construction retained
  exactly (no merge). Ending-lap MAE 11.78s is reported, not gated.
- Validation: 17 pairs over **2 episodes**, point median 1.06s
  (exact D replication), p90 2.85s; 95% episode-cluster CI
  [1.04, 2.85]. Point gate fails; N<5 → UNDERPOWERED per the
  predeclared rule (with 2 clusters the bootstrap atoms are
  degenerate, so the CI excluding 1.0 is instability, not
  refutation). Full-sample context 69 pairs @ 0.66s (diagnostic).

## 5. Spread (EQ4) — UNDERPOWERED (N=3 episodes)

- Validation: **3 episode ratios**, point median 1.418 (D
  replication), 95% CI [1.18, 1.52]. Outside the band but N<5 →
  UNDERPOWERED per the predeclared rule (same degeneracy argument as
  gap). No calibration mixing. Full-sample context reported
  diagnostically.

## 6. Pit (EQ6/EQ7) — INSUFFICIENT, mandatory blocker retained

- Primary (usable-29, D method replicated exactly): in-lap N=73
  (distribution bit-identical to D: median −0.08s), out-lap N=7
  (matches D). Secondary (all non-truncated): in-lap N=163, out-lap
  N=14 — still below the predeclared out-lap bar (≥15), and primary
  in-lap CI width 7.29s > 5s. Bar missed →
  PIT_LOSS_INSUFFICIENT_EVIDENCE retained; fail-closed stands.
- EQ7: MC2 samples pit targets and applies pit losses forward
  (`PitParameterSet`, `select_pit_parameters`, `pit_effective_loss_s`,
  `pit_count`). No T-knowable pit-free scope exists → pit semantics
  MANDATORY, still blocking. No restriction invented for coverage.

## 7. Retained dimensions — all still SUPPORTED, nothing refuted

Recomputed on validation with frozen R: pace MAE 9.54s (≤10.0),
order rate 0.0469 (≤0.15), withdrawal |0.28s| (≤5.0). Hard-refutation
bounds untouched. Zero REFUTED gates anywhere: the VSC model remains
plausible but unproven on four mandatory dimensions.

## 8. Gate table (10 gates)

SUPPORTED: pace, order, withdrawal, poison, parity, fail-closed.
UNDERPOWERED: gap (N=2), spread (N=3), duration (calibration 0.581),
pit (out-lap N=7/14). REFUTED: none. NOT_APPLICABLE: none claimed.

## 9. Poison / parity / eligibility / simulations

- Poison PASS: E defines no runtime model; D interval contract
  verified intact; 9 injections (incl. withdrawal, duration) ignored
  at T; labels separated.
- Parity PASS: production diff empty; D inputs intact (82/29 rows,
  D protocol sha matches); 0 RNG/output changes.
- Projected eligibility: NOT_APPLICABLE (not classification A).
- Stochastic futures run: 0 (bootstrap is offline resampling,
  B=2000, seed=7, deterministic).

## 10. Decision — B, terminal

**VSC_EVIDENCE_STILL_INSUFFICIENT.** Per the predeclared terminal
rule: **STOP V3.11 COVERAGE EXPANSION.** Production coverage remains
3678/9644 = 38.14%. Do NOT start SC (F3, harder than the blocked
VSC) or wet modelling. Do NOT iterate again automatically; any
follow-up needs explicitly funded new data/methodology.

## 11. Code placement note (forward-rule exception, justified)

E analysis lives in `scripts/v3_11e_*.py` (4 scripts, stdlib +
numpy/pandas, no `raceintel`/`api` imports, AST-pinned). This is an
explicit, justified exception to the `scripts/README.md` forward
rule: E code is purely offline, single-use evidence resolution with
no production consumer; promoting it under `raceintel/` would create
a production-tree diff for zero runtime benefit and break the
empty-production-diff invariant. If a later integration stage needs
duration/evidence helpers, promote them then.

## 12. Tests / guards / collection

- Focused `tests/test_v3_11e_evidence_resolution.py`: 21/21
  (protocol, duration, gap/spread, ending, pit, poison, parity,
  verdict, A–D integrity).
- Regression green at E time: A+B+C+D suites, temporal poison/parity
  suites, V3.2F/H guards, V3.8 perf guards, V3.10 freeze guards (pins
  5268→5289 + E allowlist, established pattern). Collection 5289 at
  E; V3.11F freeze adds 16 freeze tests → 5305 (pins updated in F).
  The `test_v39_freeze_provenance_unchanged` stale pin (failing at E
  time) was narrowly repaired in F with equal strength (tag pin kept;
  ancestry asserted). No Tier-1 at E (no runtime change), no
  frontend; full Tier-1 + frontend confirmation run at F freeze.
- P1–P20 all zero (tag unmoved; A/B/C/D + nav baseline bytes intact;
  thresholds fixed; no cherry-pick/leakage/pseudo-replication
  (episodes are N); no ending merge; no invented pit loss; no
  SC/wet; no erased blockers; no coverage gate; 0 futures; product
  untouched; no follow-up started).
