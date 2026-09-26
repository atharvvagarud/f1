# PHASE 8 E1 — CACHE PIPELINE VERIFICATION + TRANSPARENT OPTIMIZATION

Status: **E1 COMPLETE — E2 GO (option B: RACE-PARALLEL OPTIMIZED)**

Starting checkpoint: commit `17c04b30b124c087c51243a53d2f55bb3d9feeae`
(`v2-strategy-engine-phase7`), E0 complete. No full backfill was run in E1
(`--all-served-races` never invoked for production; probes only).

## 1. Baseline fixture (captured BEFORE optimization)

- Fixture: `tests/fixtures/phase8_e1_baseline.json` (234 KiB, committed in
  working tree, never regenerated after the optimization edit).
- Probe set (E0 characterization preserved): `2023-r12-R` small
  (815 frames / 45 checkpoints), `2023-r02-R` typical (943 / 51),
  `2023-r06-R` expensive (1515 / 95). Total 191 checkpoints.
- Full small race for complete artifact comparison: `2023-r12-R`
  (`complete: true`, 45/45 checkpoints, 268 KiB).
- Environment recorded in fixture: Python 3.11.15, NumPy 2.4.2,
  pandas 2.3.3, sklearn 1.8.0, serving SHA
  `1116b34f…`, spec fingerprint `3164de9e…`, Phase-2 content hash
  `d2ee966c…`, commit `17c04b30…` (matches E0 freeze exactly).
- Clean serial baseline timings (solo machine, production builder):
  r12 485.7 s (10.8 s/ckpt), r02 629.1 s (12.3 s/ckpt),
  r06 1139.4 s (12.0 s/ckpt); total 2254.3 s for 191 ckpts
  (mean 11.8 s/ckpt). Single-core CPU-bound (CPU time ≈ wall time).

## 2. Baseline profiling (bounded, current path)

3-checkpoint profile of `2023-r12-R` (`/tmp/e1_profile.py`):

| stage | share |
|---|---|
| `features_for_state` / `features_for_batch` (ALL_84 temporal reconstruction) | **98.9 %** |
| `RaceState` reconstruction (`field_snapshot`/`sync_lookup`/`gaps_for_snapshot`) | 0.8 % |
| model `predict_proba` (one batch per checkpoint, full roster) | 0.30 % (~8 ms) |

Per-checkpoint cost grows with race progress (frame 0: 0.19 s roster 2;
late: 4.9 s roster 20) because frozen feature formulas scan full
driver prefixes. Season-parquet re-read costs 0.07 s/race; bridge /
reconstructor construction (incl. duplicate `RaceIndex`) 0.01 s each.
Model + history one-time load 1.6 s. **E0 confirmed with no material
contradiction.**

Expensive call graph (graphify pre-audit: 10002 nodes, AST-only, plus
manual trace):
`build_replay_prediction_cache.main` → per race `load_race_inputs`
(whole-season D9 re-read) → `build_replay_timeline` →
`select_checkpoints` → `RacePredictionEngine(RaceStateFeatureBridge,
FrozenWinnerPredictor)` → per checkpoint `ReplayReconstructor.state_at`
→ `RaceStateReconstructor.reconstruct` → `bridge.features_for_state` →
`features_for_batch` (8 family calculators × boolean-mask scans) →
`predictor.predict_proba`. `RaceIndex` itself is already
`searchsorted`-indexed; the cost sits *inside* the frozen family
calculators, which is why Class C was rejected (see §4).

## 3. Optimization design (transparent only)

Single authorized surface: `scripts/build_replay_prediction_cache.py`.
**Zero frozen-module changes** (pinned by
`test_frozen_modules_untouched_by_e1`: all Phase-4 manifest hashes and
all Phase-5 domain/benchmark hashes intact except the builder itself).

- **Class A — `SeasonStatesCache`**: read-once per-season D9 frame,
  read-only, keyed by season; per-race `.copy()` slices with identical
  rows/order/dtypes/values as fresh reads (`assert_frame_equal`
  exact). Measured: 0.09 s → 0.01 s per 3 same-season races (~4 s over
  the full 149-race corpus). Small, free, zero-risk.
- **Class B — already done by existing code**: bridge + reconstructor
  are built once per race; `build_one_race` refactor preserves this.
  Sharing the duplicate `RaceIndex` across the two frozen classes would
  require frozen-module surgery for 0.02 s/race — rejected.
- **Class C — REJECTED after analysis**: memoizing feature rows across
  checkpoints has ~zero hit rate (each checkpoint advances nearly every
  driver's observed `(lap, T)` by one lap row); any real win needs
  incremental/prefix-indexed family calculators, i.e. a scientific
  rewrite. Per the E1 contract this would be
  `E1 BLOCKED — OPTIMIZATION REQUIRES SCIENTIFIC REWRITE`; instead E1
  keeps the frozen engine byte-identical and takes wall-time from
  parallelism. No second ALL_84 implementation was written.
- **Race-granularity parallelism** (`--workers N`, default 1): each
  worker owns complete races, loads model/history once via initializer,
  atomic publish retained. Default serial path is line-for-line the
  baseline behavior. No checkpoint-level parallelism.
- **Progress/audit manifest** (`--progress-manifest PATH`, default off):
  additive builder-only `replay-build-manifest-v1` (per race: frames,
  checkpoint count, cache key, artifact SHA-256, runtime, status; plus
  run metadata). Never read by serving; artifacts contain no manifest
  reference.
- **Resume hardening (found by test, builder-only)**: truncated/
  unreadable artifact files raised raw `JSONDecodeError`/`OSError`
  instead of regenerating (frozen validator only converts semantic
  corruption to `CheckpointCacheError`). `build_one_race` now treats
  undecodable files as not-valid-complete → removes and regenerates;
  generation errors still propagate loudly from the forced retry.
- `--resume` help text clarified as a no-op default-behavior marker.

## 4. Equivalence proof (all exact, diff == 0.0)

- Full-race artifacts baseline vs optimized-serial: **byte-identical**
  (SHA-256 equal on all 3 probes, matching the immutable fixture SHAs:
  `ce5619b7…`, `9ae3cefe…`, `491bf335…`). Probabilities, rosters,
  series, model identity, cache keys — identical down to the byte.
- ALL_84 vectors (EARLY/MID/LATE): `assert_frame_equal` exact.
- Transformed (106-dim) matrices: `assert_array_equal` exact.
- Logits (`decision_function`): exact. Probabilities: max abs diff
  **== 0.0** (no 1e-12 fallback needed; fallback never invoked).
- Fixture reproduction: frozen path regenerates fixture probs exactly.
- Checkpoint identity/order/reasons/anchors, roster order/availability
  reasons, cache keys, model identity: exact (19/19 E1 tests green).
- Determinism: two independent runs byte-identical; serial vs
  `--workers 2` byte-identical.
- Checkpoint count invariance: 45/51/95 probes; corpus 9644 pinned by
  existing R7 test (unchanged selector).

## 5. Resume / interruption / rebuild (tested)

- Valid-complete → `skipped`, SHA unchanged; `--resume` same.
- Corrupt (truncated) → regenerated complete (see §3 hardening).
- Incomplete subset (`complete: false`) → fails
  `load_validated_artifact`, never served; full run regenerates.
- Interruption simulation (prefix artifact + unrelated race build):
  interrupted race untouched, other race completes.
- Single-race rebuild: deleted race regenerates, existing race skipped
  (SHA unchanged).

## 6. Performance benchmark (same probe set)

| race | ckpts | baseline serial | optimized serial | speedup |
|---|---|---|---|---|
| 2023-r12-R | 45 | 485.7 s | 479.1 s* | ~1.00× |
| 2023-r02-R | 51 | 629.1 s | 689.6 s* | ~1.00× |
| 2023-r06-R | 95 | 1139.4 s | 1561.2 s* | ~1.00× |

\*Optimized full runs overlapped concurrent pytest load (see §8); the
byte-identical outputs prove the per-checkpoint science cost is
unchanged. Honest single-process verdict: **~1.00×** — Class A saves
~4 s/corpus; the ~99 % feature-reconstruction cost is inherent to the
frozen formulas.

- Parallel micro-benchmark (clean, 2 races × 2 ckpts): serial 6.6 s
  wall vs `--workers 2` 4.8 s wall (1.4×; startup-dominated on tiny
  probes; full races project to ~1.9×/2 workers).
- Memory: single-process RSS ~150–190 MB; `--workers 2` peak 238 MB
  (`/usr/bin/time -l`). Projected 4-worker footprint < 1 GB on a
  10-core/16 GB machine. No multi-GB trade.

## 7. Full-corpus ETA (from clean baseline rates)

- Serial CPU: lower 28.9 h / **central 31.6 h** / upper 37.9 h
  (inside E0's 30–60 h band).
- Wall: 2 workers ≈ 16 h central; **4 workers ≈ 8 h central**
  (7–10 h band; sublinear allowance included).
- Disk: 5.94 KiB/ckpt → **~56 MB** for 9644 checkpoints + ~100 KiB
  manifest (inside E0's 60–90 MB band, lower end).

## 8. E2 recommendation: **B. RACE-PARALLEL OPTIMIZED**

Serial optimized path proven byte-identical; race-parallel path proven
byte-identical to serial; memory bounded; manifest + resume + 2025
firewall tested. Suggested E2 invocation: `--all-served-races
--workers 4 --progress-manifest <path>` from the frozen commit, then
audit manifest (149 races, 9644 checkpoints, key sample) before serving.

Known limitations: single-process science is not faster (frozen
formulas dominate — expected); parallel scaling projected, not
full-corpus measured; two pre-existing `test_v2_phase5_freeze.py`
failures (`api/main.py` hash + drift record) predate E1 — HEAD file ==
working tree, drift comes from Phase-6/7 routers added after the
Phase-5 manifest; unrelated to E1 and unchanged by it. E1 diligence
regression green: `test_v2_phase4_r3` + `test_v2_model_lab_p31` +
`test_v2_features_f3` = **93 passed**; `test_v2_phase5_r3` +
`test_v2_phase5_freeze` = 57 passed + the 2 pre-existing failures.

## 9. 2025 firewall

Builder `require_served` rejects 2025 pre-worker-spawn (serial and
`--workers 2` tested); no 2025 artifact generated; serving artifact
training seasons remain 2018–2024; fixture model identity pinned.

## 10. Files changed (working tree only, NOT committed)

- `scripts/build_replay_prediction_cache.py` — only optimization surface
  (Class-A cache, `build_one_race`, `--workers`, `--progress-manifest`,
  resume hardening, `--resume` help).
- `tests/test_v2_phase8_e1.py` — 19 focused E1 tests (all green).
- `tests/fixtures/phase8_e1_baseline.json` — immutable baseline (frozen
  before optimization; never regenerated).
- `docs/PHASE8_E1_CACHE_OPTIMIZATION_REPORT.md` — this report.

Graphify final: `graphify update .` (no topology changes; builder-only
edit adds no scientific dependency cycle — new code imports only the
same frozen modules the builder already used).
