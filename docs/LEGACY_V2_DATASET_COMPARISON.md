# Legacy ↔ V2 dataset comparison (D10, COMPLETE 2026-09-08)

> Plan: `V2_PHASE_1_DATA_PLATFORM.md` D10. Audit scope: the frozen legacy
> university-project checkpoint datasets vs the Phase-1 V2 canonical platform.
> Machine-readable evidence: `data/v2/reports/data_quality/
> d10_legacy_comparison.json` (gitignored), produced by `python -m v2.d10`
> (read-only; no network, no training). This document is the human-readable
> twin; on any divergence the JSON governs the numbers. Findings use the plan's
> D10 vocabulary: **matching / expected difference / legacy issue /
> new pipeline issue / upstream-source difference / unresolved**.

Status: **no unresolved high-impact discrepancy** (D10 gate satisfied: every
legacy concept is classified, every significant difference is explained).

## 1. What the legacy dataset contains (inventory, MEASURED)

Seven tracked CSVs under `data/processed/`:

| File | Role | Rows | Cols | Seasons | Races | Drivers | Winners |
|---|---|---|---|---|---|---|---|
| `lap5/base/dataset_clean.csv` | **ACTIVE** (inference) | 1,996 | 17 | 2019–2023 | 103 | 33 | 103 |
| `lap10/base/dataset_clean.csv` | **ACTIVE** (inference) | 2,067 | 17 | 2019–2023 | 104 | 33 | 104 |
| `lap15/base/dataset_clean.csv` | **ACTIVE** (inference) | 1,955 | 17 | 2019–2023 | 103 | 33 | 103 |
| `lap20/base/dataset_clean.csv` | **ACTIVE** (inference) | 1,935 | 17 | 2019–2023 | 103 | 33 | 103 |
| `lap25/base/dataset_clean.csv` | **ACTIVE** (inference) | 1,918 | 17 | 2019–2023 | 103 | 33 | 103 |
| `lap10/weather/dataset_clean.csv` | INACTIVE (no consumer) | 2,075 | 25 | 2019–2023 | 104 | 33 | 104 |
| `lap10/snapshots/bahrain_2023.csv` | INACTIVE (no consumer) | 20 | 17 | 2023 | 1 | 20 | 1 |

Base schema (17 cols): `year, event_name, lap_x, driver, driver_number,
position_x, session_time_x_seconds, gap_to_leader_seconds, lap_time_x_seconds,
compound_x, tyre_life_x, stint_x, fresh_tyre_x, pit_in_time_present,
pit_out_time_present, track_status_x, is_winner`. The weather variant adds 8
columns (`weather_airtemp/tracktemp/humidity/pressure/windspeed/
winddirection/rainfall/is_raining`). Duplicate `(year, event_name, driver)`
keys: **0** in every file. Active prediction path (`ml/inference.py`,
via `ml.config`): only the five base files; the weather variant and the
snapshot are never loaded by `ml`/`api`. The snapshot equals the base
Bahrain-2023 rows except `event_name` (`"Bahrain"` vs `"Bahrain Grand Prix"`).

Active models: 15 serving slots — `{logreg,hgb,xgboost}_lap{5,10,15,20,25}_
multilap/` under `results/models/` — each with `model.pkl` **and**
`model_tuned.pkl` (the tuned file wins at inference whenever present: **all
15 slots serve tuned pipelines**). Recorded 5-fold GroupKFold CV summaries
(`summary_cv.csv`) exist in all 15 slots (see §14).

## 2. How legacy was generated (code trace, no changes)

`session = fastf1.get_session(year, event, "R")` for all schedule events
2019–2023 → rows from `session.laps` per checkpoint → cleaning → CSV →
training per checkpoint → `model.pkl`/`model_tuned.pkl` → inference via
`ml.inference` and the API.

- **Base row selection** (`scripts/data/build_dataset_multi_race_multilap.py`):
  rows with `LapNumber == lap_x` (`pick_laps(lap_x)`). A driver who retired
  before lap X has **no row** in that checkpoint file.
- **Weather-variant row selection**
  (`scripts/data/build_dataset_multi_race_weather.py`): each driver's latest
  lap row with `LapNumber <= X`, labelled `lap_x = X` (grain differs from base;
  keeps 8 extra drivers without a lap-10 row).
- **Features**: Driver/DriverNumber/Position/Time/LapTime/Compound/TyreLife/
  Stint/FreshTyre/PitInTime/PitOutTime/TrackStatus from the selected lap row;
  `gap_to_leader_seconds = session_time − leader_time` (see §7 for the
  reference-time audit); `is_winner = (driver == official winner
  abbreviation from final results)`. Every race is required to have exactly
  one winner row, else the build fails the race.
- **Missing-value handling**: NaN preserved end-to-end (no drops; interim and
  processed row counts are identical per checkpoint).
- **Clipping** (`scripts/cleaning/*`): numerics coerced, ±inf→NaN, then bounds
  `gap [0,300]`, `lap_time [30,300]`, `tyre_life [0,60]`, `position [1,30]`
  (weather variant additionally clips its 8 weather columns). No row is
  dropped.
- **Training** (`scripts/models/*multilap*.py`): features = 9 numerics
  (median imputer) + `compound_x` (most-frequent imputer + one-hot);
  HGB / LogReg / XGBoost with fixed seeds; GroupKFold(5) grouped by
  `(year, event_name)`; per-fold top-1/top-3 race accuracy + log loss; final
  full-data refit → `model.pkl`; tuned variants → `model_tuned.pkl`.
- **Inference** (`ml/inference.py`, pinned by characterization tests):
  per-driver `predict_proba(X)[:,1]` on the checkpoint rows; latest available
  checkpoint per race; majority vote across 3 models, XGBoost tie-break,
  XGBoost winner's probability as confidence. 10 inference columns
  (`ml/features.py`, order load-bearing).

## 3. Grain

Legacy grain is **race × driver × checkpoint** (verified: 0 duplicate keys;
104/103 races × ~20 drivers per file). V2 grain is **race × driver × observed
lap** (189,420 states). Consequence: legacy is five sparse fixed snapshots
(9,871 base rows total); V2 is continuous observed-lap history. The weather
variant's grain further diverges: it mixes `LapNumber == 10` rows with
latest-≤10 rows mislabelled `lap_x = 10` (see §4).

## 4. Coverage comparison (MEASURED)

| Dimension | Legacy | V2 |
|---|---|---|
| Seasons | 2019–2023 | 2018–2025 |
| Races | 103 (lap5/15/20/25), 104 (lap10) | 173 |
| Drivers | 33 abbreviations (identical set in both for 2019–2023) | 43 slugs (2018–2025) |
| Rows | 9,871 base checkpoint rows | 189,420 states + 3,458 labels |
| Winner rows | exactly 1 per race in every file | exactly 1 per race (D9) |

Overlap: all 103 races of lap5/15/20/25 are V2 2019–2023 races; lap10 adds
only **(2021, Belgian Grand Prix)**. Races V2-only: all of 2018 (21),
2024 (24), 2025 (24) = 69 races. Drivers: the 33 legacy abbreviations equal
the 33 V2 2019–2023 abbreviations exactly.

Row-level overlap (legacy rows mapped to V2 `(race_id, driver_number,
lap_number=X)`; driver number is a race-local exact key, abbreviation
fallback counted): lap5/15/20/25 map **100%** (1,996 + 1,955 + 1,935 + 1,918).
lap10/base maps **1,971/2,067 (95.4%)**; 96 rows have no V2 lap-10 row —
**but all 96 share an exact V2 (race, number, session-time) row at a lap
< 10**: 41 at lap 1, 24 at lap 3 (including all 20 Belgium farce rows —
the drivers' final racing lap-3 rows relabelled "lap 10"), 7 at lap 2, 7 at
lap 6, 6 at lap 9, 6 at lap 7, 4 at lap 8, 1 at lap 4. I.e. lap-10's unmatched
rows are retired/crashed drivers' latest-≤10 rows (old FastF1 inventory,
no longer present in FastF1 3.7/V2), not missing V2 data. lap-10 grain is
therefore **not uniform**: 1,971 true LapNumber==10 rows + 96 mislabelled
latest-≤10 rows. The weather variant matches 1,971/2,075 (its 8 extra rows
are the same retired-driver phenomenon by construction).

## 5. Field crosswalk (every active column classified)

| Legacy field | Class | V2 equivalent | Notes |
|---|---|---|---|
| `year` | B | `season` | same value, canonical name |
| `event_name` | B | `event_name` (D5 races, attribute) | attribute only, never a key |
| `lap_x` | B | `lap_number` | checkpoint label ↔ lap grain value |
| `driver` | B | `driver_abbreviation` | 3-letter code is an attribute in both |
| `driver_number` | B | `driver_number` | race-local exact key |
| `position_x` | A | `position` (D6) | checkpoint-lap-end position; nulls on both sides |
| `session_time_x_seconds` | A | `state_time_s` (D6) | identical to 1e-6 s on all 9,775 matched rows |
| `gap_to_leader_seconds` | **D** | none yet (**Phase 2**) | legacy reference semantics broken (§7); correct per-state gap must be rebuilt with leakage tests; NOT rebuilt in D9/D10 |
| `lap_time_x_seconds` | A | `lap_time_s` (D6) | identical; legacy clips [30,300] but no shipped row binds |
| `compound_x` | A | `compound` (D6) | identical incl. nulls |
| `tyre_life_x` | A | `tyre_life` (D6) | identical; legacy clips [0,60], no row binds |
| `stint_x` | A | `stint_number` (D6) | identical |
| `fresh_tyre_x` | A | `fresh_tyre` (D6) | identical (kept in dataset, not a model feature) |
| `pit_in_time_present` | A | `pit_in_s` presence (D5/D6/D7) | same-checkpoint-lap source marker; history/counts live in D7/D9 |
| `pit_out_time_present` | A | `pit_out_s` presence (D5/D6/D7) | same |
| `track_status_x` | **C** | `track_status` (D6) + `track_state` (D9) | legacy coerces the code string to int; multi-char codes become meaningless magnitudes (776 rows: e.g. `'41'→41`, `'124'→124`); V2 keeps verbatim codes + deterministic D9 flags |
| `is_winner` | **F** | `winner_flag` (D9 labels) | official outcome duplicated across legacy checkpoint rows; stored once per race-driver in V2; never in any state table |
| `weather_*` (8) | B/C | `wx_*` (D7) | race-level as-of values at/before leader time; `weather_is_raining` is a legacy-derived flag of the source bool |

No legacy column is class E (removed), none needs class G: **nothing useful is
lost** (see §12).

## 6. Value agreement (MEASURED, 9,775 matched rows)

On matched rows, every genuinely equivalent source field agrees **exactly**
(0 differing values): driver identity, driver number, position (incl. shared
nulls), session/lap-end time (±1e-6 s), lap time, compound, tyre life, stint,
fresh flag, pit-in/out markers. Track status: all single-char-code rows agree
exactly (1,775 + 1,854 + 1,747 + 1,818 + 1,879); 702 matched rows carry
multi-char codes that legacy mangles into integers. Same-upstream
arithmetic confirmed — differences are confined to the documented legacy
transforms (gap reference, clipping, int-coercion).

## 7. `gap_to_leader_seconds` special audit — classification **D (Phase 2)**

The legacy gap is checkpoint-local arithmetic, but its reference is broken:

- lap{5,15,20,25}: stored gap == `session_time − position-1-row time` exactly
  (modulo a 3–7-row clip residue) — the documented rule.
- **lap10 (base + weather): stored gap == `session_time − session minimum`
  exactly** (modulo the 300 s clip). The reference is the fastest row in the
  group — often a stale/retired row (e.g. a pit-lane-start row at RAI,
  2021 Portugal) — not the leader. Combined with the `[0,300]` cleaning clip,
  **672/2,067 base rows (32.5%) and 764/2,075 weather rows (36.8%) are pinned
  at exactly 300.0**, and every other row is shifted by the wrong reference.
- Extreme case: 2019 Belgium lap10 is **20/20 rows at 300.0** (even the
  leader, recomputed gap 0.0) plus a 0.0 row for VER (a negative −1,193 s
  value clipped to 0). The interim file proves this came from generation
  (min-rule), not cleaning alone.

Decision: do NOT rebuild gap in D9/D10. The correct position-referenced
per-state gap is a Phase-2 derived feature with leakage tests.

## 8. Pit semantics

Legacy `pit_in/out_time_present` = `PitInTime`/`PitOutTime` non-null **on the
checkpoint-lap row** — i.e. "a pit event occurred on this lap", not history.
On all 9,775 matched rows these equal the V2 same-lap `pit_in_s`/`pit_out_s`
presence exactly. Semantic improvement in V2: asymmetric in-only/out-only
boundaries preserved (246/159), plus D7 latest-event lineage and D9
completed-so-far/since derivations. No semantic conflict.

## 9. Track status

Legacy `track_status_x` = `pd.to_numeric(TrackStatus)`. Single-char codes
compare exactly to V2; **776 rows carry multi-char codes coerced to integers**
(e.g. '41', '124'), whose magnitudes are meaningless to a model (41 vs 14 vs
124 are distinct orderings, not quantities). V2 keeps the verbatim code
string (D6) and adds deterministic D9 `track_state`/flags from FastF1's
documented mapping. Legacy use of the int as a numeric model feature is a
**legacy issue** (fixed by V2 representation, not by value changes).

## 10. Missingness

On matched rows, nulls are identical (both-null counts only; 0 null-vs-value
differences): position, lap time, tyre life. Legacy nulls originate in the
source rows (no legacy imputation; median/most-frequent imputation happens
inside training pipelines = model-pipeline responsibility). V2 preserves the
same source nulls. Lower missingness is never "better" here — it is the same
missingness.

## 11. Cleaning audit

- Coerce numerics / ±inf→NaN: harmless normalization (no inf in shipped CSVs).
- Clips: `lap_time [30,300]`, `tyre_life [0,60]`, `position [1,30]` —
  **no shipped row binds** → harmless normalization. `gap [0,300]` —
  **information distortion**: censors 682 genuine >300 s rows (all of 2019
  Belgium lap10 at 300, incl. the leader; VER's −1,193 s → 0).
- No row drops: interim == processed row counts at every checkpoint.
- Training-side median/most-frequent imputers: model-pipeline responsibility,
  obsolete only when Phase 2/3 defines its own missingness policy.

## 12. Winner labels

Legacy `is_winner` (official winner abbreviation from final results) vs D9
`winner_flag` at race-driver grain: 2,069 distinct race-drivers compared
across checkpoints (`is_winner` constant across checkpoints everywhere),
**2,069 matched, 0 mismatches**. Winner rows per race == 1 in every legacy
file (build-enforced, verified). V2 stores the outcome once per race-driver;
legacy duplicates it across the 5 checkpoint rows — the documented
architectural improvement. Eleven V2 2019–2023 race-drivers have **no legacy
row at all** (first-lap retirements + 3 DNS: e.g. HAM Qatar 2023, PER Mexico
2023, NOR Vegas 2023, MAZ/MSC/STR/SAI W rows): the base pipeline silently
drops pre-checkpoint DNFs from both features and the effective label
population (**expected difference**, coverage-related).

## 13. Temporal safety (evidence-backed)

| Finding | Verdict | Evidence |
|---|---|---|
| Final-winner target separation | **confirmed safe** | target read from final results, used only as `TARGET`/`is_winner`; never in `FEATURE_COLS` |
| Weather future-nearest fallback | **confirmed leakage risk in code; 0 confirmed rows in data** | fallback branch verified in builder code; recovered 1,995/2,075 exact observation matches with `observed_at_s <= leader_time`; 80 unmatched rows are all 2019 Mexico with a single-channel wind-direction offset (**upstream-source difference**, not leakage) |
| Checkpoint construction | **confirmed safe** | features are functions of the same-window lap row only |
| Cleaning | **confirmed safe** | row-local coerce/clip; no cross-row information |
| Race grouping | **confirmed safe** | GroupKFold never trains on a test race |
| Train/test splitting | **leakage risk for chronological validity** | folds mix seasons 2019–2023 (future-season training data evaluated on past seasons) — fine for race-grouped CV, NOT chronological backtesting |
| Winner duplication | **safe by design** | duplicated target only; V2 stores it once |

## 14. Evaluation protocol

5-fold GroupKFold grouped by `(year, event_name)`; Pipeline(median-impute
numerics, most-frequent + one-hot compound); per-fold per-race top-1/top-3
accuracy + log loss; final full-data refit → `model.pkl`, tuned variant →
`model_tuned.pkl` (served preferentially). Fixed seeds (42). Recorded means
(top-1 / top-3 / logloss): lap5 — LR .549/.883/.122, HGB .511/.834/.163, XGB
.501/.824/.144; lap10 — LR .569/.895/.113, HGB .491/.867/.147, XGB
.511/.867/.128; lap15 — LR .632/.932/.107, HGB .641/.913/.141, XGB
.622/.913/.122; lap20 — LR .699/.913/.107, HGB .632/.903/.148, XGB
.660/.913/.121; lap25 — LR .688/.912/.095, HGB .678/.903/.140, XGB
.678/.922/.126 (from the 15 `summary_cv.csv` files; quoted, not re-run).
Race-group separation is useful but **not** chronological temporal
backtesting — Phase 3 owns that.

## 15. Probability semantics (verified from code + probe)

Each driver receives an **independent binary-classification probability**
(`predict_proba(X)[:,1]`); no normalization across the field exists anywhere
in the serving path. Probe: 2023 Bahrain lap-10 tuned XGBoost gives 20 scores
summing to **≈0.91** (max ≈0.70). These are legacy per-driver binary
scores/probabilities, **not** a mutually exclusive race-level win
distribution. NaN source values pass through into the API top-5 payload
(Monaco 2022 tyre-life NaN → documented serialization defect, pinned by
characterization tests).

## 16. Ensemble semantics (verified from code + characterization tests)

Votes from the 3 models **at the latest checkpoint with rows for that race**
only; majority (≥2) wins; full disagreement → XGBoost; no-XGBoost →
first available. Displayed confidence = the XGBoost winner's probability
(`"Confidence (XGBoost)"`), else the field max. `scripts/predict/*` variants
are dev scripts, not on the serving path.

## 17. Information-loss audit (D10 gate)

1. **REPRODUCIBLE NOW** (from D5–D9 source/state/labels): driver
   identity/abbreviation/number; checkpoint position, lap-end time, lap time;
   compound/tyre-life/stint/fresh-tyre with honest nulls; same-lap pit
   markers; track-status code + D9 flags; winner outcome; weather snapshot
   values + is-raining (via D7 as-of at/before leader time).
2. **INTENTIONALLY DEFERRED TO PHASE 2**: correctly-referenced gap-to-leader
   (and all rolling/relative/degradation/traffic/prior/strategy/telemetry
   features).
3. **NOT REPRODUCIBLE / POTENTIAL REGRESSION: none.** (The 96 lap-10-only
   rows have no canonical counterpart by design: 20 abandoned red-flag rows
   from an older FastF1 inventory + 76 mislabelled retired-driver rows,
   both classified as upstream-source difference / legacy grain issue.)

## 18. V2 improvement matrix (evidence-backed, no adjectives)

Season coverage (5→8 seasons), race coverage (103–104→173), temporal
resolution (9,871 sparse checkpoints → 189,420 continuous states), source
preservation (clips/coercion → verbatim + nulls), identifiers
(display/number keys → stable `race_id` + Ergast slugs), schema contracts
(implicit CSV → machine-readable availabilities), label separation
(duplicated target → race-driver-grain labels), temporal availability
(informal → `state_time_s` contract), weather joins (future-nearest risk →
backward-as-of, 0 violations), race-control handling (ignored → raw + lineage
+ flags), pit/stint semantics (same-lap 0/1 only → asymmetric + history),
missingness policy (silent censoring → honest nulls), provenance (none →
per-artifact manifests), resumability (one-shot scripts → D3 state machine),
deterministic builds (informal → byte-identical), leakage testing (none → per
stage suites), telemetry decision (none → ADR-0001). Evaluation readiness is
**unfinished in both**: neither system has chronological temporal backtesting.

## 19. What V2 does not yet improve

No new predictive model; no temporal backtesting; no calibration; no proper
race-level win distribution; no rolling pace/degradation/traffic features; no
Monte Carlo/strategy; no RaceState/replay; telemetry deferred; gap-to-leader
not rebuilt.

## 20. Legacy model compatibility — NO

Saved pipelines cannot consume V2 directly: different schema + column order
(load-bearing), checkpoint-grain vs continuous state, legacy gap/track
semantics baked into the fitted preprocessing (one-hot vocabulary incl.
`UNKNOWN`, median/most-frequent statistics of legacy distributions, clip
assumptions), separate label files. No compatibility shims (explicitly
forbidden; Phase 2/3 builds its own pipeline). Legacy stays frozen for
regression/reference.

## 21. Reproducibility

`python -m v2.d10` regenerates `d10_legacy_comparison.json` (deterministic;
relative paths only). D10 adds no canonical tables and retrains nothing.
