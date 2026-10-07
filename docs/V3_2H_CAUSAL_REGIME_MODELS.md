# V3.2H CAUSAL RACE-REGIME MODELS + COVERAGE RECOVERY

## Final verdict

**V3.2H COMPLETE — NO REGIME ADMITTED — READY FOR V3.2I.**

Every regime in the preregistered order (VSC, VSC_ENDING, WET, SAFETY_CAR,
YELLOW, RED) was given a genuine implementation-stage attempt: causal
episode datasets were built, past-only temporal parameters were
estimated, offline validation was scored against frozen prereg gates,
and each regime failed at least one load-bearing gate. All refusals
remain explicit 422s; the accepted DRY_GREEN MC2 E is byte-unchanged;
coverage is exactly 2305/9644 before and after, with zero unexplained
growth. Scientific validity was prioritised over coverage, as the
mission requires.

## Frozen baseline

- Tag `v3.1-race-dynamics` = commit `64c5af0`; HEAD = `64c5af0` at entry.
- Accumulated uncommitted research V3.2A–G intact; nothing staged,
  committed, tagged, or pushed by H (verified at exit).
- V3.2E `KEEP_MC2_E`; V3.2F `NO REGIME ADMITTED`; V3.2G
  `NO AUTHORITATIVE STATUS ADMITTED` — all preserved.

## Repository safety

Entry: `git rev-parse HEAD` == `git rev-parse v3.1-race-dynamics^{commit}`
== `64c5af0`; `git diff --cached --stat` empty; working-tree diff only
the 4 tracked-file edits plus untracked V3.2A–G paths (plus justified
V3.2H paths at exit). No `V3.2H BLOCKED — BASELINE SAFETY FAILURE`.

## Graphify

`graphify update .` at entry (no code-graph topology changes) and at
exit. Scoped to MC2 E, kernel, R3/R6 boundary, TrackStatus, WeatherData,
race-control, tyres, pits, replay state, eligibility, regime_support,
parameter estimation, temporal folds, R7 evaluation, RNG domains.
No future-historical-state → simulation edge; no evaluation-truth →
runtime edge; no model-lab or frontend coupling.

## Accepted MC2 inheritance

`mc2-r1-research` / `mc2-kernel-v1` / `mc2-rng-v1` / `mc2-field-v1` /
`v3.2c-presence-v1`, arm `E_AR1_RESIDUAL`, rho=0.264, 5000 production
runs. No source file under `raceintel/simulation/mc2/` was modified in
H (static test `test_no_runtime_regime_reads` pins this).

## CI debt

V3.2G full Tier-1 never completed (machine memory pressure) — not
claimed as green. H added 15 tests (7 source-safe, 8 corpus-dependent
pinned in `scripts/ci_corpus_dependent.txt`) and bumped
`EXPECTED_COLLECTED` 3691 → 3706 with zero removals. Focused suites for
all touched paths pass (49 passed: H source-safe + V3.2F/V3.2G regime
and status suites). Full Tier-1 was relaunched in H (background PID, polled per repo
execution policy) and **completed green: 2825 passed, 0 failed,
0 errors, 4 xfailed (pre-existing), 877 deselected corpus-dependent,
in 42m43s** (collected=3706 as expected). The V3.2G CI debt is
therefore **cleared in H** — no deferral to the final freeze gate is
needed on this evidence. No test failure is hidden behind resource
deferral.

## Preregistration

`results/v3/v3_2h/preregistration.json`, hash
`a31aec4e7297dd81be17a850295e014c569fbcbd57ee90b56ecb6e93122f6054`,
frozen **before** any outcome scoring; both evidence scripts
(`analyze_v3_2h_regimes.py`, `build_v3_2h_results.py`) assert the hash
on every run. Candidate order VSC → VSC_ENDING → WET → SC → YELLOW →
RED; folds H1 (train ≤2021 / eval 2022–2023) and H2 (train ≤2023 /
eval 2024); 2025 forbidden everywhere; minimum cell N=30 with
era/circuit fallback reporting.

## Opportunity map

From the frozen V3.2F raw audit (`opportunity.json`, member identities
frozen): TRACK-only **292** = yellow 123, safety_car 66, null/None 59,
vsc 29, vsc_ending 12, red_flag 3. WET-only **176** = (rain, wet-tyre):
(rain+slicks) 44, (rain+wet) 28, (dry+wet-compound) 104. Regime × STALE:
TRACK×STALE 811, WET×STALE 799. Regime-only headroom 468 is NOT claimed
recoverable — H proves none of it is reachable with a valid mechanism.

## VSC episode evidence

56 lap-modal VSC episodes from D9 (2018–2024), durations p50 = 1 lap
(survival table in `vsc_parameters.json`). During-VSC pace offset
≈ +19 s median (train n = 481/857) with driver-offset sd 8.5–9.5 s.
Field spread during/before ≈ 1.1 (no bunching, no dispersion). Post-exit
laps return to ≈ green within ~3–6 s MAE. 2025 never touched; all
references past-only with recorded era-fallback.

## VSC duration

Empirical residual-duration distribution conditional on elapsed age,
fit past-only per fold. H1 (23 eval episodes): median rule MAE 0.30
laps but calibration slope **2.61** (prereg band [0.5, 1.5]). H2 (6 eval
episodes): MAE 0.50, slope unmeasurable (<10 pairs). Duration gate FAILs
both folds: with ~55 historical episodes the survival curve cannot
calibrate, so `P(VSC continues | age)` is not trustworthy. Dedicated
domain `mc2-vsc-duration` stays reserved and unconsumed.

## VSC pace

Past-only median-offset rule: during-VSC MAE **10.38 s (H1) / 11.58 s
(H2)** vs prereg gate ≤ 10.0 s — FAIL both folds (H1 marginally, H2
clearly). Driver variation (≈9 s sd) dominates the central effect, and
no driver-conditioned form survives the minimum-N rule. Post-exit MAE
5.85/3.16 s (PASS) and gap ratios (PASS) do not rescue the two
load-bearing gates. AR(1) transfer/dynamics-freeze choices are moot
without a valid pace core; the smallest supported mechanism does not
exist at this sample size.

## VSC exit

Restart-transition audit supports returning to DRY_GREEN MC2 E in
principle (post-exit error small), but the exit state cannot be reached
because duration and pace gates fail. No factual restart observations
were read at any point.

## VSC validation

Temporal folds H1/H2 scored duration (calibration + MAE), during pace,
post-exit pace, and gap ratios. Outcome metrics (winner log-loss,
Brier, RPS, expected-finish MAE) are recorded as NOT_MEASURABLE_OFFLINE:
they require an integrated simulator, which prereg forbids building
before admission. Invalid rate N/A (no runtime). Race/episode is the
statistical unit throughout.

## VSC decision

**REJECT_VSC.** Gates: duration FAIL/FAIL, during-pace FAIL/FAIL,
post-exit PASS/PASS, gap PASS/PASS. Explicit 422 retained; dry-green
MC2 E unchanged.

## Wet episode evidence

Green-flag wet/intermediate lap hierarchy by (circuit, compound, rain)
with L0 minimum-N=30 backing off to L1 era cells (`wet_episodes.json`).
WET-compound rain cells are thin (e.g. 2018–2021 WET+rain n=29 across
all circuits); most 2022–2023 eval laps fall back cross-era (H1: 1378
cross-era of 1798 scored). 1320 weather-flip boundaries keep the same
compound family across the flip (289 with a stop ±2 laps, 1031 without).

## Wet pace

Circuit-conditioned past-only medians: MAE **14.43 s (H1) / 12.99 s
(H2)** vs gate ≤ 6.0 s — FAIL by a factor >2. Dry-anchor transfer is
untestable without a pace core that beats the gate; no anchor policy
(carry-shrunk / reset / wet-anchor) is adopted because the prerequisite
fails first. rho=0.264 was never reused; no wet residual process is
estimated for runtime.

## Weather evolution

Lap transition counts frozen (`weather_transition.json`) but no
transition/survival model is admitted: evolution is inseparable from
the compound decision (see below), and counts-only is not a simulator.

## Wet compound transition

R6 is dry-filtered by design. 1320 historical weather flips would need
a causal wet/dry compound choice at runtime — a strategy decision that
cannot be separated from Strategy 2.0 (explicitly forbidden). Compound
gate FAIL. Per prereg fallback policy ("no fallback data → REJECT, no
fabrication"), faking permanent-current-compound races was not
considered scientifically valid.

## Wet validation

Pace gates FAIL both folds; weather/compound prerequisites missing;
outcome metrics NOT_MEASURABLE_OFFLINE (no runnable candidate).

## Wet decision

**REJECT_WET** (full and partial: not even INTERMEDIATE_STABLE_ONLY —
stable-intermediate green-flag pace itself misses the gate by 2×).

## Safety-Car evidence

119 lap-modal SC episodes. Duration median 3–4 laps (H1 slope 0.89 but
MAE 1.62; H2 slope 1.58). Pace +33 s median (V3.2F). Restart-lap MAE
13.6–15.3 s. Pit rate under SC ≈ 20–21% vs ≈ 4.6–4.9% green (4.4×
incentive shift). Naive field-spread ratios 1.2–1.45 (expansion, not
bunching) are reported with the pit-scatter confound made explicit:
no-pit spread is nearly identical (1.25/1.45), so lap-grain
`lap_start_s` spread cannot measure bunching while 1-in-5 SC laps
involve stops — joint compression+pit modelling is required, which is
exactly the out-of-scope mechanism V3.2F flagged.

## SC duration

Past-only survival fit recorded (`sc_parameters.json`) but unadmitted;
domain `mc2-sc-duration` reserved, unconsumed; factual SC end never
read.

## SC compression

Mandatory and missing: bunching is observed qualitatively but no
explicit interpretable compression mechanism is implemented or
validated. Pace-plus-seconds modelling remains explicitly rejected.

## SC restart

No causal restart model implemented; restart laps are the noisiest
segment measured (MAE ≈ 14–15 s).

## SC pit interaction

The 4.4× pit-rate shift means green-flag R6 pit semantics are not valid
under SC, and SC-aware pits are Strategy 2.0 — the prereg boundary
condition for rejection.

## SC validation

Duration/pace/restart audited offline; compression unmodelled;
outcomes NOT_MEASURABLE_OFFLINE.

## SC decision

**REJECT_SC.** Gates compression/restart/pit-boundary all FAIL by
construction (observed, not modelled). Explicit 422 retained.

## Yellow / spatial investigation

270 yellow episodes reconfirmed. `SimulationEnvironment` carries only
the lap-level `track_state` token (`state.py`); no sector→driver field
exists in frozen RaceState. Offline Phase-12 geometry exists but wiring
it into RaceState would be new subsystem coupling with future-info
risk — the exact thing Part AD forbids unless semantics are
exceptionally clear. They are not.

## Yellow decision

**REJECT_YELLOW.** No global pace penalty was ever fitted (prereg
forbids it; the token is local: median field impact small, ≈6% drivers
slowed).

## Red decision

**REJECT_RED** (default held): 22 checkpoints, 0 usable lap rows;
suspension semantics qualitatively different; nothing overturns V3.2F.

## RNG domains

`mc2-vsc-duration`, `mc2-sc-duration`, `mc2-weather-transition`:
RESERVED_UNCONSUMED. Same-seed equality, chunk invariance, and parallel
determinism hold vacuously (no consumer); dry-green streams are
provably unperturbed (parity bit-exact; static test pins no new MC2
reads). Future CRN compatibility preserved by keeping the names.

## Future-oracle firewall

`oracle_firewall.json`: zero runtime reads added; all nine poison
channels (TrackStatus, race-control, weather, rainfall, compounds,
pits, lap timing, regime end, restart @ >T) vacuously green — offline
estimation is strictly past-season, and the dry-green path is
byte-unchanged. Static check pinned in source-safe CI.

## Implemented regimes

None.

## Rejected regimes

VSC, VSC_ENDING, WET (incl. partial), SAFETY_CAR, YELLOW, RED — each
with gate-scored reasons above. All keep their frozen refusal taxonomy
(`UNSUPPORTED_TRACK_STATE` / `WET_CONDITIONS`) and API 422 behaviour.

## Result provenance

`regime_identities.json`: MC2 + presence identities, parameter content
hashes per admitted family (unadmitted families marked NOT_BUILT),
seed policy, empty evolution-model slot. No incompatible output schema
was created (common contract untouched: no admitted regime to carry
provenance for).

## Dry-green parity

Frozen 50-checkpoint corpus `7ae97c3c…`: PARITY_OK bit-exact at H entry
**and** at H final gate (Part AQ). Any difference would have blocked
H; none exists.

## Regime regression corpora

None (no admitted regime). Permanent gates remain the V3.2F dry-green
parity corpus.

## Coverage before / after

BEFORE 2305/9644 (23.90%) → AFTER 2305/9644 (23.90%). Absolute gain 0,
percentage-point gain 0. Verified by recount from the frozen raw audit,
not by assumption. Every recovered checkpoint attributed (all zeros;
`coverage_attribution.json`, unexplained growth 0).

## Coverage attribution

VSC 0, VSC_ENDING 0, WET/PARTIAL 0, SC 0, YELLOW 0, RED 0.

## Coverage by season

Unchanged (no admission; V3.2F frozen numbers reused explicitly):
2018 8.73%, 2019 40.19%, 2020 18.46%, 2021 21.34%, 2022 23.21%,
2023 22.88%, 2024 31.14%.

## Coverage by stage

Unchanged: EARLY 39.55%, MID 23.22%, LATE 10.14% (LATE remains the
structural weakness; regimes do not fix it — most LATE blockers are
STALE, not regime).

## Coverage by race

Unchanged: 103 races ≥1, 46 zero-support, median 9.38%.

## Remaining blockers

Primary: STALE_ROSTER 4667, TRACK_STATE 1165, WET 801, MISSING_DRIVER
354, MISSING_TYRE 198, TERMINAL 154. All-blocker sets: STALE 6407,
TRACK 1317, WET 1157, TYRE 342. TRACK×STALE 811, WET×STALE 799.
Regime headroom is now proven empty under valid mechanisms; STALE
remains frozen per V3.2G (no retirement heuristic re-attempted).

## Performance

Measured this stage: **140.7 runs/s** MC2-E arm-E (200 runs, single
green checkpoint), 5000-run latency ≈ 35.5 s. Regime relative cost N/A
(no admitted regime). No MC2 optimisation performed.

## Precompute cost

5000-run catalogue (measured throughput, linear extrapolation labelled
as such): serial ≈ 95.2 h, 4 workers ≈ 23.8 h, 8 workers ≈ 11.9 h;
eligible-only serial ≈ 22.8 h. No perfect-scaling claim.

## External-status limitation

Preserved verbatim from V3.2G: the corpus exposes no authoritative
causal driver-retirement/status source; STALE_ROSTER stays frozen;
absence ≠ retirement. Regime work changes nothing about this permanent
data limitation.

## Tests

+15 (7 source-safe incl. prereg-hash, gate, refusal, RNG, firewall,
MC2-identity pins; 8 corpus-dependent incl. decisions, opportunity,
coverage, blockers, parity-record, 2025-firewall). Focused suites
green. Corpus-dependent manifest extended with zero removals.
Full-Tier-1 status per machine summary (debt tracked, never hidden).

## Scientific identities

- preregistration `a31aec4e7297dd81be17a850295e014c569fbcbd57ee90b56ecb6e93122f6054`
- parity corpus `7ae97c3c8575679a…` (bit-exact before/after)
- vsc-duration-survival-v1 / vsc-pace-v1 / wet-pace-v1 /
  weather-transition-v1(counts-only) / sc-duration-v1 content hashes in
  `regime_identities.json`
- sc-compression-v1 / sc-restart-v1 NOT_BUILT
- regime_support `v3.2f-regime-support-v1` unchanged

## Known limitations

- ~55 VSC / ~119 SC episodes: survival calibration unachievable;
  episode is the binding sample-size constraint for any future retry.
- Lap-grain spread cannot measure SC bunching while pit rates shift
  4.4×; needs joint compression+pit evidence (Strategy-2.0-adjacent).
- Cross-era (2022 reg change) fallback contaminates H1 wet/VSC eval;
  documented via fallback counts, not hidden.
- Outcome-level metrics (log-loss/Brier/RPS) unmeasurable without an
  integrated simulator — by prereg design, not oversight.
- 46 zero-support races and LATE 10.14% persist; STALE is the next
  limiter and is out of scope without an external status source.

## V3.2I handoff

- No runtime integration occurred: V3.2I inherits the exact V3.2G
  runtime (MC2 E + presence + refusal taxonomy + parity corpus).
- Regime evidence artefacts (`results/v3/v3_2h/`) are reusable priors
  if V3.2I scope ever admits external data or Strategy work — but
  under current non-goals none of them may be promoted to runtime.
- The binding constraint for any future regime retry is sample size
  (episode counts), not modelling cleverness; and STALE_ROSTER (6407
  all-blocker sets) dominates any regime headroom.
- Do NOT start V3.2I in this stage.
