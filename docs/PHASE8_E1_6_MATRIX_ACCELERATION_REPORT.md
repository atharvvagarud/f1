# PHASE 8 E1.6 — FROZEN MATRIX ACCELERATED BUILDER REPORT

Status: **E1.6 COMPLETE — E2 GO**

Starting checkpoint: commit `17c04b30b124c087c51243a53d2f55bb3d9feeae`
(E0/E1/E1.5 complete). No full backfill run in E1.6
(`--all-served-races` never invoked for production artifacts).

## 1. Scientific basis (E1.5, reused)

Replay at race-wide T selects each observable driver's latest factual
D9 state ≤ T; the frozen engine evaluates features using that driver's
own `(lap_number, state_time_s)` — never the anchor T. The frozen
Phase-2 matrix holds exactly those per-row evaluations. E1.5: 3,764 /
3,764 exact identity matches, 316,176 / 316,176 cells equal, max
probability diff 0.0.

## 2. Architecture (builder surface only)

New: `scripts/replay_feature_matrix.py` (offline; imports frozen code,
nothing frozen imports it):

- `FrozenReplayFeatureMatrix` — loads the frozen matrix, verifies
  identity once per process (file SHA-256 `b0f17b66…`, rows 189,420,
  84 predictive columns, registry order, content hash `d2ee966c…`),
  projects to served scope (2018–2024; 2025 refused) with ONLY lookup
  metadata + 84 registry-ordered predictive columns (labels never
  loaded), asserts duplicate-free identity, exposes exact-merge
  `lookup` (fail closed on missing/ambiguous, no tolerance/rounding).
- `AcceleratedReplayPredictionBuilder` — per race: frozen checkpoint
  selection + `RaceState` reconstruction (factual observable-state
  selection only), one exact join for the race, deterministic order
  restore (checkpoint order, driver order), per-checkpoint batch
  `predict_proba` with frozen serving objects, snapshot assembly with
  the existing frozen constructors (`DriverPrediction`,
  `PredictionSnapshot`, `NO_OBSERVATION_AT_SNAPSHOT`), anchor check,
  then existing `build_artifact` / `write_artifact` / cache identity.

Modified: `scripts/build_replay_prediction_cache.py` — `--feature-source
{matrix,recompute}` (default `matrix`), `build_one_race` dispatch,
per-worker matrix load, manifest records `feature_source`
(operational only, excluded from cache identity). No frozen scientific
module changed (see §14).

## 3. Equivalence (headline)

Full 3-probe accelerated builds vs immutable E1 baseline fixture:
**byte-identical artifacts** — SHA-256 `ce5619b7…` (r12),
`9ae3cefe…` (r02), `491bf335…` (r06), matching the E1-recorded values
exactly. Series, model identity, cache keys, all 191 checkpoints,
rosters, availability, probabilities (max diff 0.0) identical.

## 4. Performance

| race | ckpts | E1 baseline | E1.6 matrix | speedup |
|---|---|---|---|---|
| 2023-r12-R | 45 | 485.7 s | 2.4 s | ~200× |
| 2023-r02-R | 51 | 629.1 s | 2.8 s | ~225× |
| 2023-r06-R | 95 | 1139.4 s | 5.5 s | ~207× |
| 3-race total | 191 | 2254.3 s | 10.7 s | ~210× |

Breakdown (r06): enumeration+lookup+predict dominate at seconds scale;
transform of 1,881 rows and single-race merge are sub-second.
Corpus-wide structural dry scan (149 races, enumeration + exact join,
no prediction/writes): 448 s measured (7.5 min), 189,610 observable
requests all exact-match (see §8). E2 full-build projection (adds bulk
transform/predict ~seconds + artifact assembly/serialization of ~56 MB
over 149 atomic writes): **~15 min central, <30 min conservative,
serial** — no parallelism needed.

## 5. Memory

- Frozen parquet file: 24 MB.
- Served-scope lookup frame (162,728 rows × 89 cols — row count
  cross-checks the Phase-5 manifest `served_observations` exactly):
  155 MB in pandas.
- Serial 3-race build peak RSS: 769 MB (`/usr/bin/time -l`).
  Single full-corpus E2 process projected < 1 GB. No copies beyond the
  served slice + per-race views; 2-worker mode measured with identical
  outputs (see §6).

## 6. Parallelism decision

`--workers 2` on the 3-probe set: 10.3 s vs 10.7 s serial — no
meaningful gain (workload is now setup/I-O bound, not CPU bound).
Outputs identical. Decision: **serial matrix; do not parallelize E2**.
Workers support retained in code for future corpora.

## 7. E2 execution recommendation

**A. SERIAL MATRIX** — expected ~15 min wall, <1 GB RAM, manifest
audited (149 races / 9,644 checkpoints / key sample) before serving.

## 8. Corpus-wide structural coverage (model-free gate)

149 served races / 9,644 checkpoints / 189,610 observable requests /
189,610 exact-match (100.00%) / 0 missing / 0 ambiguous. Audit datum:
29,975 cross-checkpoint duplicate observations (15.8% — same driver
state reused by later checkpoints; harmless under exact join, and a
dedupe micro-optimization is unnecessary at this speed).

## 9. Files changed (working tree only, NOT committed)

- `scripts/replay_feature_matrix.py` (new)
- `scripts/build_replay_prediction_cache.py` (CLI dispatch only)
- `tests/test_v2_phase8_e1_6.py` (new, 19 tests)
- `docs/PHASE8_E1_6_MATRIX_ACCELERATION_REPORT.md` (this file)
