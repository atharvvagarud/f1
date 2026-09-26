# PHASE 8 E2 — REPLAY PREDICTION CACHE BACKFILL REPORT

Status: **E2 COMPLETE — READY FOR E3**

Starting checkpoint: commit `17c04b30b124c087c51243a53d2f55bb3d9feeae`
(tag `v2-strategy-engine-phase7`); E0/E1/E1.5/E1.6 complete.

## 1. Pre-build gate (all green)

- HEAD == tag commit `17c04b30…`.
- Serving SHA `1116b34f…`, matrix SHA `b0f17b66…`, Phase-2 hash
  `d2ee966c…`, spec fingerprint `3164de9e…` — all match frozen records.
- Served seasons 2018–2024; `--all-served-races --dry-run`: 149 races /
  9,644 checkpoints.
- `results/v2_replay/` absent before build (no production cache), dir is
  gitignored, 33 GB free, no other builder running.
- E1.6 fast tests 17/17 green (coverage + full-probe proven in E1.6,
  builder unchanged since).

## 2. Build command

```
python scripts/build_replay_prediction_cache.py --all-served-races \
    --feature-source matrix \
    --progress-manifest results/v2_replay/replay_build_manifest_v1.json
```

Serial matrix path (no `--force`, no workers), CPython 3.11.15,
NumPy 2.4.2 / pandas 2.3.3 / sklearn 1.8.0, darwin arm64.
Start 2026-09-25 11:48:10 BST.

## 3. Build execution

149 races / 9,644 checkpoints / 149 generated / 0 skipped in **578.3 s
(9.6 min)** — under the ~15 min central projection. Per-race mean
3.88 s / median 3.76 s / p95 5.14 s. Fastest 2021-r12-R (3 ckpts,
0.2 s); slowest 2022-r07-R (89 ckpts, 6.2 s). Output 56 MB
(`results/v2_replay/checkpoints/`, gitignored).

## 4. Corpus validation (read-only validator)

`scripts/validate_replay_prediction_cache.py` (new, read-only) →
`results/v2_replay/phase8_e2_cache_manifest_v1.json` (3.1 s):

- 149 artifacts == frozen served set; 0 missing, 0 extra, 0 2025.
- 9,644 checkpoints; series/frame/anchor/reason/order exact per race
  (frozen selector recomputed).
- Observable predictions **189,610 — exactly the E1.6 structural
  evidence** (no difference to explain); nulls 3,206, all
  `NO_OBSERVATION_AT_SNAPSHOT` (single reason, never zero).
- Every artifact: format `replay-checkpoints-v1`, `complete: true`,
  valid series/model/cache-key/roster/semantics; strict T ordering.
- One frozen model identity corpus-wide (serving SHA, spec fp,
  ALL_84 v8, RAW, INDEPENDENT_BINARY, Phase-2 hash).
- All probs finite in [0, 1]; no normalization (independent binary).
- Cache keys recompute correctly; generation mode absent from identity.
- Aggregate corpus SHA-256:
  `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298`
  (algorithm: sha256 over sorted `race_id + artifact_sha256`).

## 5. Serving / timeline / frontend smoke

- Backend vs production cache: checkpoint predictions (2018 + 2024
  sampled), probability timelines for 2018/2020/2022/2024 races, model
  identity (LogReg, serving SHA), INDEPENDENT_BINARY notes.
- Timeline == artifact values exactly (2024-r14-R: 44/44 checkpoints,
  19 nulls preserved, driver order sorted, 0 invalid probs).
- Non-checkpoint frame → frozen 404; 2025 → 404 `unknown_race`.
- Frontend `/replay` (2018-r01-R, 2024-r14-R): PredictionPanel shows
  real cached values (HAMILTON 80.49%, Σ 80.5% "valid, not shares"),
  ProbabilityTimelineChart renders 72/44 real checkpoints, frame
  stepping works, between-checkpoint state explicit ("No model
  checkpoint — factual frame only"), INDEPENDENT_BINARY visible, 0
  console errors, no page overflow. No redesign.
- Missing-cache 503 + 2025 route/CLI rejection: R7 subset 6/6 green
  (temp fixtures only; production cache untouched).
- Reference spot check: `--feature-source recompute` on 2021-r12-R
  (3 ckpts) **byte-identical** to the production matrix artifact.

## 6. Regression

E1 + E1.6 + Phase-5 r3 + Phase-4 r3 + P3.1: **124 passed** in 1452 s
(including the E1.6 149-race structural gate and the full-probe
byte-equivalence gate). No test weakened.

## 7. Known limitations

- Validator asserts corpus shape/identity, not per-cell feature
  recomputation (covered pre-build by E1.5/E1.6 byte-equivalence).
- Two pre-existing `test_v2_phase5_freeze.py` failures (Phase-6/7
  `api/main.py` drift postdating the Phase-5 manifest; HEAD==tree).
- Frontend smoke is manual (Playwright) + existing node suites
  untouched; no visual redesign.

## 8. Files changed (working tree only, NOT committed)

- `scripts/validate_replay_prediction_cache.py` (new, read-only)
- `docs/PHASE8_E2_REPLAY_CACHE_BACKFILL_REPORT.md` (this file)
- Generated (gitignored): `results/v2_replay/checkpoints/` (149 files,
  56 MB), `results/v2_replay/replay_build_manifest_v1.json`,
  `results/v2_replay/phase8_e2_cache_manifest_v1.json`
