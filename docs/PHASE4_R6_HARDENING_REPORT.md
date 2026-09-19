# Phase 4 R6 Hardening Report

## 1. Scope

R6 profiled the Phase-4 prediction path, removed scientifically safe
serving-time feature overhead, proved exact frozen ALL_84 parity after
every optimization, and ran the full Phase-4
temporal/adversarial/integration hardening gate. No scientific redesign:
no retrain, no recalibration, no feature redefinition, no 2025 access,
no probability renormalization. Two serving-adapter optimizations were
kept; everything else was measured and documented, not changed.

## 2. Baseline architecture

```
HTTP -> V2Service -> AnchorObservation -> RaceStateReconstructor
  -> RaceState -> RaceStateFeatureBridge -> frozen Phase-2
  features_for_batch -> exact ALL_84 -> FrozenWinnerPredictor
  .predict_proba ONCE -> PredictionSnapshot -> HTTP response
```

The R5 service binds the full 2018-2024 D9 corpus (162,728 rows,
149 races), one reconstructor, one bridge, one frozen predictor, and one
engine per process. The R3/R4 path bound a per-race slice instead
(~1,056 rows for 2023-r01-R).

## 3. Baseline performance

Primary fixture 2023-r01-R alonso-28 (T=6558.658, 20/20 observable),
`scripts/benchmark_phase4.py --mode quick` (descriptive, no gates):

| stage | per-race slice (1,056 rows) | full corpus (162,728 rows) |
|---|---|---|
| corpus/history/artifact load | - | 0.18 / 0.47 / 0.90 s (once per process) |
| RaceState reconstruction (warm) | 37.1 ms | 37.7 ms |
| FeatureBatch generation | 11.92 s | 81.56 s |
| model inference (20x84 -> 106) | 7.2 ms | 7.2 ms |
| full snapshot (cold) | 12.05 s | 81.78 s |

Ratio full/per-race features: **6.8x**. Reconstruction is corpus-size
independent (RaceIndex binary search); inference is ~1500x cheaper than
features. Feature generation is the bottleneck.

## 4. Profiling methodology

- `scripts/benchmark_phase4.py` (new): reproducible harness with pinned
  dev-only fixtures, per-race vs full-corpus contexts, cold/warm and
  repeated warm samples, descriptive p50/p95 (p99 only at n>=20).
- `cProfile` + `pstats` (stdlib, no new dependency) over
  `bridge.features_for_state` on the full-corpus path; targeted timing
  probes for slice layout. No timing assertions in unit tests.

## 5. Measured hotspots

Full-corpus profile (103 s profiler time, 20 drivers, cumulative):

| function | ncalls | cumtime | share |
|---|---|---|---|
| `rates._history_for_prefix` | 40 | 80.7 s | per-target history sweep |
| `temporal.synchronized_field_snapshot` | 500 | 83.5 s | 20 gaps + ~480 rates-history |
| `temporal.synchronized_driver_state` | 9,500 | 79.7 s | full-frame boolean scans |
| pandas `comparison_op` / object-array `__eq__` | 46,184 | ~66 s self | 162k-row mask comparisons |
| `interactions._resolve_primitives` | 20 | 49.4 s | frozen 2x primitive recompute |
| `context.context_for_state` | 40 | 17.0 s | incl. 872 rival pace evaluations |
| `temporal.driver_prefix` | 1,392 | 11.9 s | full-frame prefix scans |
| `temporal.resolve_target` | 721 | 5.0 s | full-frame exact-match scans |

Top self-time is pandas object-array comparison: ~9,500+
`synchronized_driver_state` + ~1,400 `driver_prefix` + ~700
`resolve_target` + per-history-row roster scans, each sweeping all
162,728 rows. Per-race context runs the identical scan count over
1,056 rows, hence ~12 s.

## 6. 12s vs 82s explanation

The difference scales with **rows scanned per filter operation**, not
with races, drivers, or history size:

- Every frozen per-state calculator reads same-race rows through
  full-frame boolean masks (`states[(race==..)&(driver==..)&(time<=T)]`,
  `states[race==..]` for roster, exact 4-key match). No calculator
  touches other races' `states` rows; priors read only the untouched
  `PriorHistory` bundle (verified by inspection of all eight family
  calculators; `past_races_before` is never called on the serving
  path).
- Full corpus = 162,728 rows vs race slice = 1,056 rows (154x). Per-scan
  cost dominates: 9,500+ scans x 154x wider frames = the 6.8x
  end-to-end gap (sub-linear because fixed costs - sorting, python
  overhead, priors - do not scale with rows).
- Reconstruction does not scale (37 ms both contexts: RaceIndex binary
  search). Inference does not scale (7 ms both). `load_history`
  (0.3-0.5 s) and artifact load (0.6-0.9 s) are once-per-process.

## 7. Optimizations attempted

Family/context classification from the frozen calculators (R6-H):

- A - current race only: passthrough F4, pace F5, gaps F6, context F7,
  rates F8, environment F9 (target's own prefix + anchor row).
- B - prior races/history: priors F10 (`history` bundle only; `states`
  used solely for the target meta row, which lives in the race slice).
- C - both: interactions F11 (primitives via the same engine).

### OPT-1 (kept): per-race slice in the Phase-4 bridge

`v2/race_state_features.py`: the bridge materializes the bound corpus's
per-race slice lazily, cached under the complete semantic key
(`race_id`; corpus fixed at construction), and passes it - instead of
the 162k-row frame - to `requests_for` resolution and to the single
`features_for_batch` call. The `history` bundle passes through
untouched, preserving strictly-past (`H < R`) prior reads. Frozen
Phase-2 code unchanged.

- rationale: §6 - every `states` read is same-race; the slice exposes
  exactly the rows the full frame would.
- before/after (primary full-field): 81.56 s -> 15.12 s (5.4x);
  early 20.79 -> 3.60 s; stale 80.45 -> 14.92 s; partial/red ~21 ->
  ~3.7 s.
- parity: 4 anchors x 20 rows x 84 cols = 6,720 cells each, exact
  names/order, null mismatches 0, identity order exact, max abs diff
  **0.0** on all four.

### OPT-2 (kept): contiguous index on the cached slice

`reset_index(drop=True)` on the cached slice. The DataFrame index
carries no temporal semantics (all frozen operators are boolean-mask /
sort / iloc based); a fragmented filter index measurably slows pandas
take/copy paths (~25%: 15.08 s -> 11.97 s on the primary fixture,
parity `results_equal` True, then exact-gated below).

- before/after: 15.12 s -> 12.02 s primary (6.9x vs original 82.59 s);
  full-corpus now equals per-race speed (ratio 1.0x).
- parity: re-ran the 4-anchor gate: max abs diff **0.0**, null
  mismatches 0 on all four.

### Not attempted (deliberately)

- Batching/rewriting the frozen engine (e.g. removing the F11 2x
  primitive recompute, vectorizing `synchronized_driver_state`):
  requires frozen Phase-2 semantic change - out of scope, recorded as
  debt in §20.
- Approximate windows, fewer history rows, sampling, nearest-state
  substitution, rounding T, skipping validation: scientifically
  ineligible, never tried.
- Sharing one RaceIndex between reconstructor and bridge (~550 MB
  resident): safe-looking but touches construction contracts; left for
  Phase 5, recorded in §20.

## 8. Final serving architecture

Unchanged data flow (§2); one internal change: `RaceStateFeatureBridge`
holds the full corpus binding plus a bounded read-only per-race slice
cache (at most one entry per requested race; values never mutated by
the frozen engine, which copies on selection). The HTTP contract,
error mapping, 2025 policy, and probability semantics are untouched.

## 9. ALL_84 parity

- Slice vs full-frame oracle (`tests/test_v2_phase4_r6.py`,
  red-flag 2022-r18-R ocon-2): 20 rows x 84 cols = 1,680 cells,
  identity mismatches 0, null mismatches 0, max abs diff **0.0**.
- Post-optimization bridge vs frozen F15 model matrix (F15 idiom, same
  fixture): 1,680 cells, max abs diff **0.0** (tolerance idiom
  1e-9/1e-12, measured 0.0).
- Pre-optimization evidence (scratch, 4 anchors incl. mid full-field,
  stale, partial, red): 6,720 cells each, max abs diff **0.0**.
- R3/R4 direct-engine and matrix suites rerun green (§18).

## 10. Prediction parity

Same frozen artifact, post-opt snapshot vs pre-opt oracle frame:
same complete roster (20/20), same observable members, same
identities, same model identity, same INDEPENDENT_BINARY semantics and
note, probability max abs diff **0.0**. No normalization (each
probability equals the raw predictor output exactly). Repeated
`engine.predict` through shared wiring is dict-identical
(determinism/reentrancy).

## 11. Temporal adversarial results

- New end-to-end same-lap future hazard test (canonical red fixture):
  injected same-lap +1 s rival row leaves `RaceState`, the 84-col
  `FeatureBatch` (`assert_frame_equal`), identities, and the full
  `PredictionSnapshot` dict byte-identical. Green.
- Rerun unchanged: R2 11-case future-mutation harness, R3 7-case
  harness + shuffle determinism, R4 future-mutation regression -
  all green inside the full suite (§18).
- Zero-state entrants remain explicit nulls; partial (60-row race) and
  red-flag validity companions unchanged (parity fixtures §9).

## 12. 2025 firewall

`SERVED_SEASONS == (2018..2024)`, `MAX_SERVED_SEASON == 2024` pinned;
`_race_summaries` drops synthetic 2025 rows; `_require_race` raises
`RaceNotFoundError` for 2025-shaped ids; `/v2/races` contains no 2025
(R5 integration rerun green); holdout artifact covered by the M9 seal
tests (green, file never read by R6); no M9 path reachable from
Phase-4 (import-boundary test green).

## 13. API hardening

R5 V2 API suite rerun green (49 passed, incl. real state + real
prediction integration through the optimized path, OpenAPI paths,
404/422/503 matrix, deterministic repeat). Optimization is invisible
to the HTTP contract: same routes, same shapes, same error bodies.
Service init 6.78 s (149 races); warm state 39 ms; warm full-corpus
prediction 12.49 s end-to-end.

## 14. Legacy regression

`test_api_baseline.py` 11/11 green; all legacy characterization
suites green in the full run; no legacy file modified in R6
(`ml/*`, legacy routes/schemas/service untouched); no V2 import from
legacy and no `ml.*` import from V2 (boundary tests green).

## 15. Shared-state/reentrancy

Reconstructor, bridge (incl. new slice cache), PriorHistory, and
predictor are read-only during requests. Tests: interleaved anchors
stable, 8-thread x 10-iteration read-only access with zero errors and
no cache pollution, repeated predictions dict-identical. Caches are
process-local, keyed completely (`race_id` over a fixed corpus
binding), and bounded (one entry per requested race).

## 16. Memory

`scripts/benchmark_phase4.py --mode memory` (RSS peak, primary
fixture, MB): after init (imports + 162,728-row corpus + history +
artifact) 415.8; after wiring (2x full-frame RaceIndex + registry)
963.3; after first prediction 966.2 (+2.9: slice cache + batch);
after 3 repeated warm predictions 966.2 (+0.0 - no per-request
growth). No unbounded growth; new cache adds one ~1k-row slice per
requested race.

## 17. Final performance

Representative full-field dev fixture (2023-r01-R alonso-28, T=6558.658):

| | BEFORE (R5) | AFTER (R6) |
|---|---|---|
| service init | ~3.9 s | 6.78 s (same work + measured RaceIndex builds; once per process) |
| warm RaceState | ~41 ms | 39 ms |
| full-corpus FeatureBatch | 81.56 s | 12.11 s (**6.8x**) |
| model inference | 7.2 ms | 7.2 ms |
| full snapshot (cold) | 81.78 s | 12.18 s |
| warm end-to-end (service) | ~82 s | 12.49 s |

Per-race slice context unchanged at ~12 s (ratio full/per-race now
1.0x). Early/partial/red fixtures: 3-4.5 s. No cherry-picking:
primary fixture n=3 warm reps; p50 reported where sampled (descriptive
only, no SLA).

## 18. Full verification

- Full repository suite: **1540 passed, 4 xfailed** (48:40) - the 4
  xfails are the documented pre-existing Monaco-2022 NaN legacy
  xfails (`test_known_defects.py`, strict=False), no new xfails.
- Includes: R1-R6 (215), Phase-2 F2-F16 incl. F3/F5/F6/F7/F9/F13/F14/
  F15/F16, P3.1 serving/seal (18), all API characterization + V2
  suites, legacy baseline (11).
- Frontend: `eslint` 0 errors (1 pre-existing unused-var warning in
  `ResultCards.tsx`), `tsc --noEmit` clean, `next build` succeeds.
- D11 read-only: 17/19 areas PASS; `[legacy] FAIL` is the
  dirty-worktree hygiene detector (any `git status` output under
  `api/`/`scripts/` trips it - the sanctioned uncommitted R5/R6
  additions; all 7 legacy CSVs, 30/30 model pkls, and characterization
  tests intact, baseline 11/11 green); `[git] FAIL` is the same
  expected dirty-worktree signal (R1-R6 uncommitted by design). No new
  data blockers. The trailing `/tmp`-path traceback is the known
  cosmetic CLI reporting issue (report JSON written correctly).

## 19. Frozen hash verification

Live recompute vs frozen constants - all unchanged:

| hash | live == frozen |
|---|---|
| matrix content `d2ee966c…` | OK |
| matrix schema `b1ccbc62…` | OK |
| matrix parquet SHA `b0f17b66…` | OK |
| matrix manifest SHA `b6a63f5e…` | OK |
| feature registry fp `a04d5475…` | OK |
| label registry fp `0a4d0bb6…` (recorded) | OK |
| F16 semantic `c88bcbaa…` | OK |
| F16 config SHA `bb59d936…` | OK |
| serving artifact `1116b34fc716035c…` (full) | OK |
| spec fp `3164de9e61ca94ab…` (full) | OK |
| holdout `2c3a166d…` | OK via M9 seal tests (file untouched by R6) |
| freeze manifest identity | OK (`3164de9e61ca` model fp) |

New Phase-4 file SHAs (16-char prefixes) recorded for R7 freeze prep
(see hash script output): `race_state.py 5b4774b2518cbffe`,
`race_state_reconstruction.py 1655c205c89e9ca1`,
`race_state_features.py 7a0817238292a9b4` (post-OPT-2),
`prediction.py de676b3ac33b3d4e`, `api/v2_routes.py 21378283c5e39c99`,
`api/v2_schemas.py a19efff4ee1b1e3e`, `api/v2_service.py 040241f84ff32ef1`,
`tests/test_v2_phase4_r{1..6}.py` + `scripts/benchmark_phase4.py
52bfccdbf9723568`. Not frozen yet.

## 20. Remaining performance debt

1. Frozen engine does ~9,500 same-race sync scans per full-field
   snapshot (~12 s). The F11 2x primitive recompute alone is ~40% of
   engine time. Removing it requires frozen Phase-2 change - Phase 5
   replay must budget ~12-15 s per snapshot or revisit with explicit
   semantics.
2. Two full-frame RaceIndex copies (reconstructor + bridge, ~550 MB
   resident) - could share one read-only index; left untouched as a
   construction-contract change.
3. One-time per-process builds: RaceIndex ~1.5 s x2, registry build,
   history load - all inside the 6.78 s service init, never per-request.

## 21. R7 readiness

Bottleneck explained with evidence; safe overhead removed (6.8x);
exact parity preserved at every layer; full gate green; hashes
unchanged; debt documented. R7 may seal Phase 4 (commit + freeze
report). R7 NOT started.
