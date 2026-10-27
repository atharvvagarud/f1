# V3.11A — MC2 Coverage Forensics

Status: **MC2_COVERAGE_FORENSICS_COMPLETE — REVIEW BEFORE CAUSAL RECONSTRUCTION.**
Stage is observational. No eligibility, RaceState, freshness, MC2, simulator,
wet-weather, or Pit Wall change was made. All recovery numbers are
**DIAGNOSTIC / HYPOTHETICAL ONLY**.

## 1. Frozen verification

- `git status`: clean except V3.11A additions (`results/v3/v3_11a/`,
  `scripts/v3_11a_mc2_coverage_forensics.py`,
  `tests/test_v3_11a_forensics.py`, this doc, CI-pin reconciliations).
- `HEAD == v3.10-pit-wall^{commit} == 2c00e7e`. Tags `v3.10-pit-wall`,
  `v3.9-uncertainty-intelligence`, `v3.8-mc2-performance`,
  `v3.8-model-simulation-consensus` unmoved.
- Graphify entry: 19796 nodes / 44602 links (no topology change from
  diagnostics; doc-only delta).

## 2. Baseline reproduction (exact)

Source: `results/v3/v3_2n/final_eligibility_catalogue.json` (corpus hash
pinned in `baseline_reproduction.json`), multi-cause join against
`results/v3/v3_2f/coverage_opportunity_raw.json`, cross-checked to
`results/v3/v3_2n/final_blockers.json` (match: true).

| candidate | eligible | unsupported | coverage |
|---|---|---|---|
| 9644 | 3678 | 5966 | 38.14% |

| STALE | TRACK | WET | MISSING_DRIVER | MISSING_TYRE | TERMINAL |
|---|---|---|---|---|---|
| 3294 | 1165 | 801 | 354 | 198 | 154 |

Invariant `3294+1165+801+354+198+154 = 5966` holds. Raw-vs-final primary
mismatches = 1373, exactly the V3.2J retired-status relief
(STALE → CAPABLE); all other primaries frozen.

Reproduce: `.venv/bin/python scripts/v3_11a_mc2_coverage_forensics.py`
(~7 s, ~360 MB peak). Ledger: `results/v3/v3_11a/unsupported_state_ledger.csv`
(5966 rows, one per unsupported state, stable `(race_id, frame_index)` sort).

## 3. Core finding: STALE is disappearance, not threshold tuning

Frozen STALE has **one** stale dimension: per-driver D9-row
`observation_age_s = T − observed_time_s` versus `3.0 × base_pace_s`
(median threshold 267.7 s). There is no per-field tyre/track/weather
freshness gate; multi-cause overlap rides on `blocking_conditions`.

- Offender counts/state: 1:988, 2:1028, 3:751, 4:285, 5:149, 6:25, 7:42,
  8:12, 9:1, 18:1, 19:12 (7977 offender instances).
- Age excess beyond threshold: median **2066 s**, p75 3476 s, p90 4619 s,
  max 9945 s. Only **46/7977** offenders are within 30 s beyond threshold.
  STALE is **genuinely old/missing evidence**, not slight misses.
- Causal probes (`state_time_s ≤ T` only) agree with frozen ages to ≤1 s
  for all 7977 offenders (0 mismatches) while future rows demonstrably
  exist and were ignored (poison PASS).
- Shape split of the 3294 STALE states: **TIMING_GAP 51** (all offenders
  causally reappear later), **MASS_CLOCK_RESET_SUSPECTED 196** (≥5
  offenders all >600 s stale, concentrated in red-flag/restart races such
  as 2020-r09-R ×48, 2018-r01-R ×27, 2019-r16-R ×19 — restart/clock
  semantics, not gap-filling), **INDIVIDUAL_DISAPPEARANCE 3047**
  (≥1 offender never observed again — retirement-adjacent).
- Stale offenders additionally coexist in **1740** harder-blocked states
  (TRACK 788, WET 615, TYRE 192, TERMINAL 145). All 3294 final-STALE
  states carry STALE alone. Field-level recovery sums must use
  unique-state accounting or they double-count these 1740.

## 4. Other reasons (evidence, not assumptions)

- **TRACK (1165):** yellow 521, safety_car 371, vsc 124, vsc_ending 67,
  null 64, red_flag 18. Split: RECONSTRUCTION 64 (null token, nothing
  causal to persist from — all pre-first-message laps 2–8) /
  SIMULATOR_CAPABILITY 580 (vsc/sc/vsc_ending/red, token known, no regime)
  / BOTH 521 (yellow: token known but local exposure unknown AND no
  regime model, per V3.2F evidence). 146 yellow states co-carry WET.
- **WET (801):** rainfall-only 206, compound-only 567 (INTERMEDIATE-heavy),
  both 269. Reconstruction establishes the state (compounds factual);
  the block is simulator capability (no wet pace family, no weather
  evolution, dry-filtered R6 transitions) → BOTH, capability-dominated.
  Wet→dry mapping forbidden.
- **MISSING_DRIVER (354):** frame-0 boundary 149, mid-race gaps 205
  (incl. 2022-r02-R tsunoda gap). 199 drivers never seen in the whole
  race; 155 unseen at T but seen later (future identity ignored → R5).
  Genuine absence of ≤T observation, not alias confusion. No
  auto-resolution performed.
- **MISSING_TYRE (198):** lap-1 all-null rows + early-retirement gaps
  (stint fields null too). 58 have a prior ≤T compound, but 54 of those
  are co-blocked by harder conditions; 6 have no prior compound at all.
  No default compound, no future backfill.
- **TERMINAL (154):** all `leader ≥ scheduled` (8 pure + 146 multi-cause).
  EXPECTED_PERMANENT_UNSUPPORTED 154, defects 0. Remain unsupported.

## 5. Field semantics (code-evidenced)

`field_semantics_audit.json`: timing/position/gap INSTANTANEOUS (no
persistence candidate); tyre compound and track status EVENT_PERSISTENT
(reconstruction candidates, unimplemented); driver identity
SESSION_STATIC (grid persists, but T-state cannot be fabricated —
NEEDS_RESEARCH); weather INSTANTANEOUS needing an evolution model;
terminal EVENT_PERSISTENT by design.

## 6. Timestamp domains

`timestamp_domain_audit.json`: single D9 lap-end clock carried unchanged
D6→D9→RaceState→adapter; race-control clock shares the session origin
(V3.2J); no offset/restart/rounding defect evidenced. Boundary shapes
(frame-0 unobserved 149, null-track laps ≤1, lap-1 null tyres) are genuine
observation absence at T, not clock errors. Quantified, no repair.

## 7. Concentration

- Season: 2018 worst (1135/1386 unsupported, STALE-heavy 655); 2022–2024
  carry most MISSING_DRIVER (79/82/108 — substitute-driver era).
- Stage: LATE dominates (2422 unsupported; all 154 TERMINAL; STALE 1380).
  EARLY carries the frame-0 boundary (MISSING_DRIVER 211) and null-track.
- Races: 45 zero-support (median race coverage 20.69%); worst are
  2018 wet/attrition races (r02/r05/r10) and red-flag races.

## 8. Recovery classes (diagnostic, unique states)

| class | states | meaning |
|---|---|---|
| R0 permanent/intentional | 154 | terminal |
| R1 low-risk data fix | 0 | no deterministic defect found |
| R2 domain rule | 114 | 51 timing-gap + 59 null-token semantics + 4 stint persistence |
| R3 simulator support | 862 | neutralized regimes |
| R4 research | 4476 | 3434 stale retirement/restart science + 1042 wet |
| R5 not causally recoverable | 360 | 354 driver + 6 tyre, need future |
| R6 unknown | 0 | — |

Ceilings (diagnostic, not targets): R2-alone → 3792/9644 (**39.91%**);
R2+R3 → 48.85%; R4-stale included → 74.48%. Arithmetic contexts:
all-STALE 6972 (72.29%), STALE+TRACK 8137 (84.37%).

## 9. Prioritization → V3.11B scope

Ranked by feasibility × safety, not count. The **safest high-value V3.11B
(CAUSAL STATE RECONSTRUCTION)** scope A justifies is exactly the **114
R2-alone states**: validated timing-gap rule (51), validated null-token
semantics rule (59, noting no prior status exists to persist from), and
scoped stint-persistence rule (4). Everything else stays out: mass-reset
(196) and never-again stale (3238) need retirement/restart science;
regimes (862) need simulator models; wet (1042) is a separate modelling
programme; R5/R0 never.

## 10. Scientific review answers

1. STALE cause: driver disappearance (3047 never-again + 196 mass-reset),
   not threshold misses. 2. Genuinely old (median excess 2066 s; 46 near
   misses). 3. Persistence evidence: tyre-within-stint, track-until-change
   (both unimplemented); identity persists but yields no T-state.
4. Causal-reconstruction ceiling without physics change: **114 states**
   (39.91%). 5. TRACK: yellow 521 / SC 371 / VSC 124+67 / null 64 /
   red 18. 6. Split: reconstruction 64 / capability 580 / both 521 /
   unknown 0. 7. MISSING_DRIVER: genuine absence (149 boundary + 205
   gaps), not aliases. 8. MISSING_TYRE: 58 prior-compound but only 4
   unblocked by persistence alone; rest co-blocked or no-prior.
9. TERMINAL behaves as intended (154/154 permanent). 10. WET clearly
   needs new simulator science (pace + evolution + transitions).
11. Timestamp defects contribute ~0. 12. V3.11B = the 114 R2 states.

## 11. Pathology P1–P20 / tests

All P1–P20 zero except P20-by-construction (ceilings are labelled
diagnostic, never eligibility). Focused suite
`tests/test_v3_11a_forensics.py`: **22 passed**. Guards run green:
field-contract, presence-adapter, parity, 2K reconstruction, 2N final
validation, 2J/2F corpora, phase-6 freeze, MC2 batch (after reconciling
the collection pins 5186→5208 for the 22 new tests + V3.11A allowlist in
the three established pin files). Collection: **5208**. Pre-existing,
untouched: `test_v39_freeze_provenance_unchanged` (stale commit pin,
fails on clean tree too). No Tier-1 (diagnostic-only), no frontend
changes (frontend untouched).

## 12. Deferred

V3.11B implementation, eligibility/RaceState/freshness changes, track
regime support, wet modelling, large MC2 reruns, product/API changes.
