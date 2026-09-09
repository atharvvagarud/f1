# Phase-1 Exit Report — F1 Intelligence v2 Historical Data Platform

> Date: 2026-09-08. Scope: D12 documentation/freeze/exit only — no data
> semantics changed in D12. Every number below was measured by the pipeline;
> authoritative evidence lives in `data/v2/reports/data_quality/` (gitignored)
> and the cited docs/modules. D12 pass criteria: all met; no unresolved
> BLOCKER. **PHASE 1 — HISTORICAL DATA PLATFORM: COMPLETE. STOP.**
> Phase 2 is NOT AUTHORIZED.

## 1. Phase-1 objective

Build a reproducible, leakage-safe canonical data platform over official F1
sources: full Tier-B history plus a rich 2018–2025 lap-level Tier-A dataset
with deterministic state, temporal context, separated outcome labels, and a
measured telemetry decision — as the frozen input contract for Phase 2.

## 2. Completed stages D0–D12

D0 foundation verification · D1 source/coverage audit · D2 schemas/contracts
· D3 resumable ingestion · D4 historical results (1950–2025) · D5 rich race
ingestion (173 sessions) · D6 canonical lap state · D7 temporal enrichment ·
D8 telemetry decision (DEFER, ADR-0001) · D9 derived state + labels · D10
legacy comparison (read-only) · D11 final validation (44/0/0) · D12
documentation/freeze/exit (this report).

## 3. Final measured inventory (D11-reverified)

- Tier-B: 76 seasons, 1,149 races, 25,784 result rows (3,819 standings).
- Tier-A normalized: races 173 · results 3,458 · driver_laps 189,420 ·
  pit_stops 6,336 · stints 9,324 · weather 25,779 · race_control 14,992.
- Canonical: D6 state 189,420 + race_quality 173; D7 enriched 189,420;
  D9 derived state 189,420 + labels 3,458.
- Canonical store: 1,783 Parquet files, ~74.1 MB. Source cache ~16.16 GB
  (never canonical, never committed).

## 4. Architecture summary

Jolpica/Ergast history + FastF1 rich timing → D3 ingestion/normalization →
Tier-A/B → D6 lap-end state (`state_time_s` = LAP_END) → D7 temporal
enrichment → D9 structural derived state → Phase 2. Official results → D9
labels (separate). Telemetry → DEFERRED (ADR-0001). Full detail:
`docs/DATA_PLATFORM_ARCHITECTURE.md`.

## 5. Canonical contract

Grain `(race_id, driver_id, lap_number)`; stable Ergast-slug driver ids and
season-scoped constructors; Parquet + season partitioning; machine-readable
schemas with availability/lineage vocabularies (`v2/contracts.py`,
`v2/d6schema.py`, `v2/d7schema.py`, `v2/d9schema.py`); manifests as the
source of truth; atomic idempotent writes; deterministic byte-identical
rebuilds.

## 6. Phase-2 handoff (authoritative)

**Inputs:** `driver_lap_state_d9` (189,420 rows, `state_time_s` = LAP_END —
features may use only information observable at/before it) and
`race_driver_labels` (3,458 rows, join explicitly; never part of state).
Allowed: D9 state, D5 supporting tables (with own temporal contract +
mutation tests), D9 labels for targets only, Tier-B for past-only context.
Full handoff (telemetry/DNF/gap rules, entry conditions) is §10 of
`data/README.md`.

## 7. Telemetry / DNF / gap decisions

- Telemetry: DEFERRED from canonical data (ADR-0001 Accepted;
  `telemetry_summary` INACTIVE; cache is source-only).
- Binary DNF/reliability target: DEFERRED; factual classification preserved.
- Gap-to-leader: legacy implementation NOT authoritative; Phase 2 rebuild.

## 8. Known limitations (consolidated)

PARTIAL 2021 Belgium / 2022 Japan (kept, flagged); 2018 TrackStatus sparsity;
69 untimestamped 2018-r02 race-control messages (never invented into history);
weather staleness gaps; 3 FastF1-null final positions; telemetry deferred; no
DNF target; no Phase-2 features; no chronological evaluation or V2 model yet.
(Not data defects: no V2 model, no backtesting, no replay/strategy/product
systems — all later phases.)

## 9. Definition-of-Done checklist (plan §51)

1. Rich 2018–2025 coverage attempted systematically — **PASS** (173/173
   terminal: 171 COMPLETE + 2 PARTIAL).
2. Every targeted race has a recorded status — **PASS** (manifests).
3. Broad historical results built and measured — **PASS** (76 seasons).
4. Driver-lap data at all available laps — **PASS** (189,420 vs 5 legacy
   checkpoints).
5. Typed Parquet storage — **PASS**.
6. Resumable ingestion — **PASS** (D3 state machine, exercised).
7. Idempotent ingestion — **PASS** (tested + byte-identical rebuilds).
8. Schemas documented — **PASS** (machine-readable + docs).
9. Stable race/driver identifiers — **PASS** (adversarial audit clean).
10. Labels separated from features — **PASS** (0 LABEL_ONLY in state).
11. Temporal leakage tests pass — **PASS** (per-stage + combined suites).
12. Weather/race-control temporal boundaries — **PASS** (0 violations).
13. Missing data reported, not fabricated — **PASS** (honest nulls).
14. Quality reports contain measured coverage — **PASS**.
15. Legacy 2019–2023 data compared — **PASS** (D10, no unresolved issues).
16. Telemetry policy decided from measurements — **PASS** (ADR-0001).
17. FastF1 caches excluded from source control — **PASS** (ignored/untracked).
18. Later seasons addable without rewrite — **PASS** (season-partitioned,
   explicit-scope CLI; 2026 excluded by config, not architecture).
19. `docs/DATA_PLATFORM_ARCHITECTURE.md` exists — **PASS**.
20. `docs/DATASET_V2_REPORT.md` exists — **PASS**.
21. No later product feature implemented — **PASS** (D11 scope audit; nothing
   beyond Phase 1 exists).

No FAIL. No DEFERRED-BY-DECISION items outside the documented telemetry/DNF/
gap deferrals (which the plan explicitly permits as decided outcomes).

## 10. Validation / regression status

D11 gate: 44 findings, 0 failed, 0 unresolved BLOCKERs
(`docs/PHASE1_FINAL_VALIDATION.md`, `d11_validation.json`). Python/V2 suite
320 passed / 4 xfailed; frontend 21 passed; `tsc` clean; eslint 0 errors;
production build green; golden legacy equivalence green; fresh-env
validation passed; deterministic rebuilds byte-identical.

## 11. Documentation index

`data/README.md` (platform + handoff) · `README.md` (repo status/vision) ·
`docs/DATA_PLATFORM_ARCHITECTURE.md` · `docs/DATASET_V2_REPORT.md` ·
`docs/PHASE1_FINAL_VALIDATION.md` · `docs/PHASE1_EXIT_REPORT.md` (this file) ·
`docs/LEGACY_V2_DATASET_COMPARISON.md` ·
`docs/adr/ADR-0001-telemetry-retention.md` · `V2_PHASE_1_DATA_PLATFORM.md`
(complete) · `V2_PHASE_2/3_*.md` (future, not started).

## 12. Freeze statement

Frozen as of this report: source coverage boundaries (Tier-B 1950–2025,
Tier-A 2018–2025 Race-only); canonical entity semantics; D9 state grain and
`state_time_s` = LAP_END; label separation and label grain; the
temporal-availability policy; ADR-0001; DNF deferral; the generated-artifact
policy (code/contracts/docs tracked; Parquet/reports/manifest-outputs and
caches ignored). Future changes to these must be intentional versioned
changes, not silent Phase-2 edits.

## 13. Unresolved blockers

**None.**

## 14. Deferred work (explicit, not forgotten)

Telemetry summaries (ADR triggers), binary DNF policy (Phase 2/3),
gap-to-leader rebuild (Phase 2), all Phase-2 feature families, Phase-3
evaluation/models, and all product stages (RaceState → hardening).

## 15. Git / commit / tag recommendation (no commit performed)

Working tree currently holds the entire uncommitted Phase-1 work product on
top of the foundation baseline. Proposed structure (for explicit approval):

1. `docs: Phase-1 data platform documentation and freeze` — track:
   `data/README.md`, `README.md`, `docs/DATA_PLATFORM_ARCHITECTURE.md`,
   `docs/DATASET_V2_REPORT.md`, `docs/PHASE1_FINAL_VALIDATION.md`,
   `docs/PHASE1_EXIT_REPORT.md`, `docs/LEGACY_V2_DATASET_COMPARISON.md`,
   `docs/adr/`, the four historical-doc banners, plus already-staged V2
   code/tests (`v2/`, `tests/test_v2_*.py`).
2. Verify `git status` shows only intended paths; confirm `data/v2/`,
   caches, `__pycache__`, `node_modules/`, `frontend/.next|out` stay ignored.
3. Tag the Phase-1 completion point: **`v2-data-platform-phase1`**.

Do NOT create the commit or tag without explicit approval. Do NOT rewrite
history. Generated data (`data/v2/`, caches) must never be committed.

## 16. Final Phase-1 status

**PHASE 1 — HISTORICAL DATA PLATFORM: COMPLETE. STOP.**
Awaiting user approval. Next (unauthorized until approved): Phase 2 —
Temporal Feature Engine, starting only from the §6 handoff contract.
