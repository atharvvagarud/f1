# Phase-2 Pace Features (F5)

> F5 first derived family: past-only target-driver pace context in
> `v2/features/pace.py` (12 features, registry 24→36, schema v1→v2),
> 36 tests green, full 189,420-row audit clean. Depends on F1 (prefix),
> F2 (registry/versioning), F3 (`driver_prefix`, `within_stint_prefix`
> semantics), F4 (engine dispatch, tyre passthroughs). No cross-driver
> data anywhere (all sync NONE).

## 2. Source fields

`driver_lap_state_d9.lap_time_s` (value) + eligibility inputs
`pit_in_s`, `pit_out_s`, `track_state` (derived token, NOT raw
`track_status` codes), `lap_number` (+ `stint_number` for stint
features). Tyre context (`compound`, `tyre_life`, `fresh_tyre`,
`stint_lap`) is F4 passthrough reuse — never recomputed, never scored.

## 3. Measured timing-quality audit (189,420 states)

lap_time null 1.67%, zero non-positive; extremes factual (2024-r08
lap-1 SC ~2,500 s; slowest green pit-free ~150 s — both stay eligible:
no magnitude filter). pit-in 6,177 / pit-out 6,090 laps, slower
(out-lap median 112.6 s vs clean-green 87.0 s). Track tokens:
all_clear 170,989; safety_car 8,237 (median 121.3 s); yellow 6,541
(median 95.5 s, +10% vs clean — systematic, excluded); vsc 1,643;
vsc_ending 360; red_flag 310 (median 144.1 s); null 1,340 (unknown,
excluded). Lap 1 (3,452 rows): median 103.8 s vs 87.0 s (+19%,
standing-start effects — excluded). Stints: 9,324, median length 19,
6.81% single-lap. Compounds include verbatim 2018 names
(SUPERSOFT/ULTRASOFT/HYPERSOFT) — categorical, never ordered.

## 4–5. Pace-eligibility policy (frozen)

Eligible iff: lap_time non-null and > 0; no pit-in/out marker on the
lap; `track_state == 'all_clear'`; lap_number > 1. Eligible share
84.42% (159,910/189,420). Exclusions are factual flags, never speed:
slow/fast laps stay eligible (tested); no outlier filtering, no
future-informed masks. Yellow excluded on measured systematic shift;
unknown (null token) excluded as unestablishable green.

## 6. Observed vs representative

(A) observed lap timing = D6 `lap_time_s` facts; (B) pace-eligible
observations = the §4 mask; (C) derived summaries below, each-capable
stating its window + min_n. Raw lap_time is Phase-1 state, not an F5
feature.

## 7. Recent windows (eligible-stream, not lap numbers)

Latest-N eligible observations from `prefix(driver,T)`, target
included (LAP_END). `pace_median_3`, `pace_median_5`, `pace_mean_5`,
`pace_median_10` + `pace_n_3/5/10` counts. Median = robust central
tendency (caution/pit tails); mean retained at 5 only — pairs median
for skew and matches the trend's OLS-mean basis (documented
justification, no wider mean proliferation).

## 8. Minimum-history policy (measured)

min_n: w3→2, w5→3, w10→5. Availability: 93.89% / 91.97% / 88.07%
whole-scope, stable per season (w5 85–94%). Null below min_n; counts
always available (0 allowed). min_n = 1 never used.

## 9. Representative pace

`representative_recent_pace_s` = median of latest 10 eligible with
min_n = 8 (81.98% available): the high-confidence operating point,
distinct from `pace_median_10` (min_n = 5, coverage point) by its
strict minimum — no duplicate formulas. Never "clean-air" (F1/F2 ban
upheld; name search test-pinned).

## 10–12. Current-stint pace + trend proxy

`current_stint_pace_median_s` / `_mean_s` (min_n = 2, 86.68%) +
`current_stint_eligible_laps` over start-side-only stint scope (end
never exposed; unknown stint → nulls). `current_stint_pace_trend_
s_per_lap` (min_n = 5, 72.86%): closed-form OLS slope over in-stint
progress index (no scipy), constant pace → exactly 0.0, never a zero
fallback for insufficient n. Named PROXY with explicit confounder
warning (fuel, traffic, management, tyre/track evolution, weather);
"degradation" appears nowhere in names/descriptions (test-pinned).

## 13. Tyre handling

Factual passthroughs only; compound categorical (ordinal SOFT>HARD
encoding banned and absent); no tyre scores.

## 14. Registry definitions (12, all CANDIDATE)

Family pace (8) / stint (4); dtype float64 (seconds,
seconds_per_lap) or int64 counts; temporal DRIVER_PREFIX; sync NONE;
missing NULL_IF_INSUFFICIENT_HISTORY; sources exact per §2;
formula_ref `pace.py::pace_values`; per-feature version 1. Engine
rejects unregistered/PLANNED names explicitly.

## 15. Feature-set version

v1 → v2 exactly once (12 added columns; F2 bump policy). No Phase-1
schema touched. Passthrough/result contracts unchanged.

## 16–17. Single-state / batch paths

Single: exact target → `driver_prefix` → mask → shared `pace_values`
core → `FeatureResult`. Batch: per-(race,driver) incremental walk
maintaining eligible/stint histories (same window semantics, no frame
rebuilds); engine `features_for_batch` loops the single-state path
(same definitions). No training/serving split.

## 18–19. Parity / mutation evidence

Single-vs-batch equality on synthetic + 8 real-race spot programs
(Bahrain dry, Germany wet, Britain, Belgium PARTIAL, Monaco, Japan,
2024/2025 openers) — all green. Future fast/slow laps (±extreme),
future pit/compound/stint/track/weather/result mutations: identical.
Eligibility mutation (past lap → pit-in) shifts membership per policy;
pure speed change (±210 s) never filters. Combined with F3 suites.

## 20–21. Missingness / stage-of-race coverage (189,420 rows)

Null rates: median_3 6.11%, median/mean_5 8.03%, median_10 11.93%,
counts 0%, representative 18.02%, stint median/mean 13.32%, stint
count 0.42% (null = unknown stint), trend 27.14%. By lap band
(med5/med10/rep/trend): 1–5: 23.9/0/0/0%; 6–10: 90.8/72.3/17.9/68.3%;
11–20: 98.8/98.1/90.6/77.9%; 21–40: 99.2/99.0/98.8/77.6%; 41+:
100/100/100/86.7%. Early-race missingness exposed, never hidden.

## 22. Edge cases

Belgium (≤2 eligible/target — nulls with counts, no exclusion);
Monaco (null-compound rows exact, incl. tyre independence);
SC/VSC/red sequences (eligibility by token, verified in Germany
2019/Japan 2022 spots); 2024/2025 openers nominal. No special-casing.

## 23. Full-data audit

189,420 rows in/out, identities exact, 12 columns only, no
label/outcome columns, finite non-null numerics, pace positives,
deterministic double-build identical. Encoded as
`test_full_scope_audit` (~18 s incl. rebuild).

## 24. Performance (MEASURED)

Full batch 8.8 s; single-state 9.5 ms (pandas prefix path; bulk uses
batch); suite impact +~7 s. No further optimization warranted.

## 25. Limitations/confounders

Trend is confounded (see §10–12); windows span caution-free green
only by token (sector-local yellows under green tokens are
indistinguishable — accepted, documented); wet/dry transitions are
NOT split in F5 (rainfall-conditioned pace is F9/Model-Lab business);
compound changes don't split windows (exposed via passthroughs).

## 26. F6 handoff

F6 consumes: `pace_batch` outputs as baseline columns, `RaceIndex`
for sync, the §9 validity doctrine. F5 owns no cross-driver state;
gap engine must not reuse window code paths for rival timing.
