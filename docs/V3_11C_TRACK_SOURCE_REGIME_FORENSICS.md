# V3.11C — Track-Source Semantics & Regime Forensics

Status: **TRACK_SOURCE_REGIME_FORENSICS_COMPLETE — REVIEW BEFORE TRACK
REGIME IMPLEMENTATION.** Research/forensics only. No regime simulation,
no eligibility/RaceState/MC2 change, no null→GREEN mapping, no MC2
futures, no product changes.

## 1. Sources (Q1–Q2)

- **S1 `track_state` token** (D9): per-lap TrackStatus string,
  last-code-wins → all_clear/yellow/safety_car/red_flag/vsc/vsc_ending
  (FastF1 3.7.0 mapping, SOURCE-DOCUMENTED). A lap-boundary SNAPSHOT;
  multi-code laps (`12`,`126`,`64`) prove intra-lap history is dropped.
  Null iff source null/empty/unknown. Global token, no sector channel.
- **S2 race-control messages** (D5 parquet, 173 files): timestamped EVENT
  feed (category/flag/status/scope/sector, session clock shared with D9).
  YELLOW/DOUBLE YELLOW are Sector-scoped only (zero Track-scoped in
  corpus); GREEN is Track-scoped pit-exit/session light (42); CLEAR is
  Sector (302) + Track (53); BLUE is Driver-scoped (5388, regime-
  irrelevant); SafetyCar lifecycle explicit (DEPLOYED 171 / ENDING 41 /
  IN THIS LAP 100 / THROUGH PIT LANE 13). Unt imestamped messages
  excluded from as-of joins (69 in 2018-r02). Latest-≤T attaches via
  `merge_asof backward` (exact counts).
- S3 derived flags and S4 `rc_last_message_*` join are views/mechanisms,
  not independent sources. S5 frozen V3.2F episodes are offline-only.
- V3.10D concepts reused: FIRST-frame observability, no nearest-frame
  logic, future hidden.

## 2. NULL / liveness (Q3–Q4)

- All 64 NULL states are pre-first-message (64/64, laps 2–8). **H0
  HELD**: no message means UNKNOWN. **H1 REJECTED** (intuition only;
  no liveness guarantee: no guaranteed initial emission, feed silent
  while GREEN, first sport message is YELLOW/DOUBLE YELLOW/CLEAR in 9
  races). **H2 fails**: 63/64 have a Track-GREEN ≤T, but every one is
  `GREEN LIGHT - PIT EXIT OPEN` — session liveness, NOT green-flag
  racing. First-token medians 1200–3800 s by season: systematic feed
  behavior, not ingestion failure.

## 3. Persistence & intervals (Q5–Q6)

- Contract **EXPLICIT_STATUS_PERSISTS_UNTIL_EXPLICIT_SUPERSESSION** is
  defensible for post-observation tokens (sector-yellow→token agreement
  636/1078 at overlapping-lap granularity; Track CLEAR returns
  all_clear; 1255 run-length intervals over 149 races) but NOT
  implemented; pre-first interval stays UNKNOWN regardless.
- Transition graph (24 edges): all_clear→yellow 372, yellow→all_clear
  285, safety_car→all_clear 100, vsc→vsc_ending 56,
  vsc_ending→all_clear 59, yellow→safety_car 59, yellow→vsc 53,
  red_flag→all_clear 18, safety_car→red_flag 13. First-observation edges
  out of None: 6 (2018 only). Anchor/modal tokens agree 1165/1165 —
  the token is a coherent session snapshot at T.

## 4. Regimes (Q7–Q10)

- **Yellow (521):** always local in the feed; exposure
  LOCAL_SECTOR_ACTIVE 268 / LOCAL_EXPOSURE_UNKNOWN 245 / UNKNOWN 8 /
  GLOBAL 0. No sector→driver channel exists → unaffected-driver
  ignoring impossible; global penalty rejected (V3.2F). Local pace +
  exposure science required.
- **VSC (191 = 124 vsc + 67 vsc_ending):** global delta-time regime;
  82 VSC intervals, 56 with explicit 6→7 withdrawal, 59 endings→green;
  no VSC RC category (token codes only). Causal intervals
  establishable; mid-interval T needs duration/withdrawal knowledge
  only for simulation.
- **SC (371):** 119 intervals + DEPLOYED/ENDING lifecycle; withdrawal
  →green 100, →red 13. Needs compression/queue/duration/restart/pit
  models (restart sd 21.2s per V3.2F).
- **RED (18):** 21 red intervals; post-red clock gaps median 1491 s
  (max 7709 s) — suspension discontinuity quantified; links the 196
  A MASS_CLOCK_RESET states. Unsupported by design; no bridging.

## 5. Ledger & split (Q8/Q11–Q12)

- `track_candidate_ledger.csv`: 1165/1165 unique rows (anchor-exact
  token; prior ≤T; next >T offline label; RC ≤T; exposure; secondary
  blockers; disposition).
- Split re-derived from C evidence reproduces A exactly:
  RECONSTRUCTION 64 / SIMULATOR_CAPABILITY 580 / BOTH 521 / UNKNOWN 0.
- Causally known 1101 (yellow 521, SC 371, VSC 191, red 18) — regime
  known, simulator-blocked. Causally unknown 64.

## 6. Simulator science (Q13–Q14)

- MC2 assumes dry-green pace, independent draws, factual gaps, lap-step
  classification, dry pit loss/degradation, ACTIVE-only starts, no
  interactions, continuous clock — hence every regime gap (audit).
- Minimum semantics specified per regime (REQUIRED/OPTIONAL/UNKNOWN);
  historical targets available causally (lap deltas, gap compression,
  order stability, spread, pit-loss delta, restart ordering).
- Feasibility: YELLOW F3, **VSC F2**, SC F3, RED F4.

## 7. Recommendation (Q15–Q16 + §28)

- **At most ONE regime: VSC → V3.11D VSC REGIME MODEL (research).**
  Only F2: global exposure (no local-mapping science), explicit 6/7
  lifecycle, measurable pace delta (+19.6 s), 59 clean
  ending→green withdrawals. Chosen by feasibility × evidence, not count
  (SC larger at 371 but F3). NO_REGIME_READY rejected only because VSC
  clears the F2 bar; YELLOW/RED correctly not recommended.

## 8. Ceilings & secondary blockers

- TRACK-only 292 = 123 yellow + 66 SC + 59 null + 41 VSC + 3 red
  (reconciles A exactly). Secondary-free AND causally known: 233
  (nulls excluded as unknown). Diagnostic ceilings: VSC-secondary-free
  41 → 3719 (38.57%); combined 233 → 3911 (**40.56%**). Regime support
  never erases STALE/WET/TYRE/TERMINAL co-blocks. No double counting;
  ceilings labelled diagnostic, never production.

## 9. Poison / tests / guards

- Offline resolver: modal token at max(t≤T); RC latest-≤T corroboration;
  pre-first → UNKNOWN. Future status/RC/SC/VSC/GREEN-withdrawal/red/
  restart injections ignored; ==T visible per source equality semantics;
  no nearest-message; first-future-type variation leaves T UNKNOWN.
- Focused `test_v3_11c_track_forensics.py`: 21/21. Regression green:
  A+B suites, RaceState/phase suites, presence/contract/parity/2N,
  2J/2F/2H/2K suites, phase-6 freeze, MC2 batch, V3.8/V3.9/perf/V3.10
  guards (pins 5229→5250 + C allowlist, established pattern).
  Collection 5250. Pre-existing, untouched:
  `test_v39_freeze_provenance_unchanged` (stale pin, fails clean).
  No Tier-1, no frontend (diagnostic-only, zero runtime change).
- P1–P20 all zero (tags unmoved; A/B untouched; eligibility/RaceState/
  MC2 unchanged; no GREEN-by-default/backfill/nearest/local-as-global/
  physics/wet; no erased blockers/double counts/futures/product
  changes; ceilings labelled diagnostic; unknowns presented as unknown).

## 10. Deferred

V3.11D VSC research (not implemented here), SC/YELLOW/RED regimes, wet
modelling, any production/track-source implementation, commit/tag/push
(A+B+C reviewable together).
