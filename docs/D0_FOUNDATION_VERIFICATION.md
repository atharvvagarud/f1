# D0 — Verify Foundation Refactor

> **Plan:** `V2_PHASE_1_DATA_PLATFORM.md`, stage D0 only.
> **Date:** 2026-09-08.
> **Historical record:** D0 is COMPLETE; this document records the D0-time
> state. Current status lives in `README.md`.
> **Authoritative inputs read completely:** `V2_PHASE_1_DATA_PLATFORM.md`
> (all 2329 lines), `docs/FOUNDATION_REFACTOR_REPORT.md`,
> `docs/V2_REPOSITORY_AUDIT.md` (R0–R8 record).
> **Scope:** verification and planning only. No ingestion, no schemas, no
> Parquet writes, no resumability, no downloads, no retraining, no behaviour
> change. The only file written in D0 is this document.

---

## 1. Foundation verification result — PASS (with one hygiene flag)

| Check | Command / method | Result |
|---|---|---|
| One canonical Git repo | `find . -name .git -maxdepth 3`, `git branch` | Only `./.git`, branch `master`, one commit `e7d3467` — PASS |
| Expected Foundation architecture | `ls api ml tests frontend/features/prediction docs` | `api/{main,routes,schemas,services/prediction_service}.py`, `ml/{config,features,inference}.py`, `features/prediction/{hooks,lib,components}`, 7 pytest files — PASS |
| Foundation report exists | `docs/FOUNDATION_REFACTOR_REPORT.md` | 12 sections + appendix, untracked (awaiting approved commit) — PASS |
| Python regression suite | `/tmp/r8fresh/bin/python -m pytest tests/ -q` | **67 passed, 4 xfailed, 0 failed** (3.99 s) — PASS |
| Frontend regression tests | `node --test` (3 files, from `frontend/`) | **21 passed, 0 failed** — PASS |
| Golden fixture unchanged | `shasum -a 256 tests/fixtures/legacy_predictions.json` | `8e23031a…c1f65302`, identical to R0 — PASS |
| Model artifacts intact | `git status data/… results/models tests/fixtures` + in-suite load/score | 30/30 `.pkl`, zero modifications, all 15 tuned artifacts load — PASS |
| Legacy datasets intact | same + `test_datasets.py` | 14/14 CSVs, 104 races, 2019–2023, 1-winner-per-race — PASS |
| `ml.inference` paths unchanged | `git status ml/ api/` shows only the known uncommitted R3/R4 refactor files; no D0 edits | PASS |
| Canonical verify command | `make PYTHON=/tmp/r8fresh/bin/python verify` | exit 0 in R9; targets unchanged since (only this doc added) — PASS |

The 4 xfails are exactly the Monaco 2022 NaN markers (failing-as-expected).
No legacy data/model file was modified in D0; no external data was
downloaded (cache sizes unchanged: 6.6 GB source, 100 MB runtime); no
Phase-1 implementation code was introduced (only this doc).

### ⚠️ D0 finding 1 — staged cache untracking was lost (hygiene, not data)

R7 ran `git rm -r --cached data/raw/fastf1_cache` (staged, index-only).
D0 finds **`git diff --cached --name-only` is empty**: the index was reset
to HEAD at some point after R9, so the **1113 `.ff1pkl` blobs are tracked in
the index again** (`git ls-files | grep -c fastf1_cache` → 1113, path clean
vs HEAD). Worktree cache is intact (6.6 GB, all 2019–2023 seasons present);
nothing was downloaded, deleted, or rewritten — only the staging was lost.
**Remediation (at commit time, D1+): re-run**
`git rm -r --cached data/raw/fastf1_cache` **before any commit and verify
with `git status` that the commit contains no cache blobs.** This does not
block D1–D3 ingestion work, but it blocks any clean commit until re-applied.
The `.gitignore` entries (`/.fastf1_cache/`, `/data/raw/fastf1_cache/`) are
correct and verified via `git check-ignore`; they take effect for untracked
files once the blobs leave the index.

> **Post-D0 note (D1, 2026-09-08): RESOLVED.** Outside-session commits
> `5a4001e` (1113 cache-blob deletions), `999076b` (foundation refactor),
> and `5e4c72c` (this document) landed after D0. HEAD now holds 317 files
> with **0** `.ff1pkl` blobs and the index holds **0**; the worktree cache
> (6.6 GB) is intact and ignored. No remediation remains — future commits
> must simply keep cache blobs out (verified via `git status` + `git
> ls-files | grep -c ff1pkl` → 0).

---

## 2. Git / repository state

- Root repo, `master`, HEAD `e7d3467` (baseline commit from outside the agent
  session). All R3–R9 work remains uncommitted in the worktree (tracked
  modifications + `??` new files: `Makefile`, `README.md`, `api/routes.py`,
  `api/schemas.py`, `api/services/prediction_service.py`,
  `frontend/.env.example`, `frontend/features/`, `ml/`,
  `docs/FOUNDATION_REFACTOR_REPORT.md`, plus this file). No commit is made
  in D0.
- No nested repos, no stashes, one branch. `__pycache__` dirs present from
  verification runs are ignored build noise.
- Uncommitted-deletion entries (`app.py`, `legacy/`, `repo/`, `gpt.txt`,
  doc dupes, `notes.txt`, `api/services/predictor.py`) are the approved R6
  removals, still awaiting the approved commit sequence (Foundation report
  §12 / R9 handoff).

---

## 3. Legacy protection strategy

The 2019–2023 checkpoint datasets stay the protected baseline:

- **Coexistence, not migration:** `data/processed/lap{5,10,15,20,25}/base/
  dataset_clean.csv` + `data/interim/lap{5,10,15,20,25}/` remain the sole
  inputs to `ml.inference` (`ml/config.py::get_dataset_path` — D0 forbids
  changing these paths). V2 canonical data will live in a **separate
  namespace** (§11) until a later explicit migration decision.
- **Guards already in place:** `test_datasets.py` pins schema/inventory
  (104 races, required columns, 1-winner-per-race); `test_prediction_
  equivalence.py` pins outputs with fixture-sha assertion. Any accidental
  legacy modification fails loudly.
- Forbidden in Phase 1 until authorised: overwrite/rename/regenerate legacy
  CSVs, Parquet-migrate them, alter their schema, touch model artifacts.

---

## 4. Current data tree

```text
data/
├── raw/fastf1_cache/      # 6.6 GB, 2019–2023 year dirs, 104 session entries — IGNORED, local-only
├── interim/lap{5,10,15,20,25}/   # 7 tracked CSVs (build outputs)
├── processed/lap{5,10,15,20,25}/ # 7 tracked CSVs (clean datasets incl. base/dataset_clean.csv)
├── models/                # EMPTY (R0 finding, still empty)
└── sequences/             # EMPTY (R0 finding, still empty)
results/
├── models/{logreg,hgb,xgboost}_lap{5,10,15,20,25}_multilap/  # 30 tracked .pkl (runtime)
├── models/*_lap10* / *weather*   # legacy artifacts, preserved, not loaded by API
├── debug/                 # per-build race/year failure CSVs + header-only evidence
├── data_quality/          # per-dataset quality + race-integrity reports
└── {analysis,baselines,comparisons}/  # historical experiment evidence
.fastf1_cache/             # 100 MB runtime HTTP cache — IGNORED, local-only
```

---

## 5. Existing ingestion inventory (reusable in D1–D3)

| Script | Role | Reusable logic |
|---|---|---|
| `scripts/data/build_dataset_multi_race_multilap.py` | Canonical multilap builder (`--lap`, `--start-year/--end-year`, `--cache-dir`, `--retries`, `--sleep`) | schedule+session **bounded retry** (3×, sleep 2 s), per-race try/except → `results/debug/*_failures.csv` + year-failures, stable sort, inf→NaN, 1-winner sanity gate |
| `scripts/data/build_dataset_multi_race_weather.py` | Weather-variant builder | **time-safe weather join** `weather_at_time_seconds` (latest row ≤ lap-X leader time; see §9 for the one edge case), same failure-CSV pattern |
| `scripts/data/build_dataset_single_race.py`, `build_missing_base_races.py`, `build_dataset_multi_race.py` | Single/repair/base builders | Same FastF1 access pattern, repair-workflow precedent |
| `scripts/data/inspect_lapX_fields.py` | Field inspector | Precursor to the D1 source-field inventory |
| `scripts/utils/smoke_test_fastf1.py` | Connectivity check | Minimal load-one-session probe (2023 Bahrain R) |
| `scripts/utils/compare_race_sets.py`, `append_missing_into_interim_base.py` | Set-diff + append repair | Precursor to coverage/dedup logic |
| `scripts/cleaning/clean_dataset*.py` (3) | Interim → processed + reports | Coercion/clipping conventions, `results/data_quality/` quality + integrity CSV pattern |
| `scripts/results/*`, `scripts/analysis/*`, `scripts/baselines/*`, `scripts/models/*` | Comparisons, plots, CV, training | Historical evidence + methodology reference; NOT ingestion |

---

## 6. FastF1 / cache findings

- **Pinned version:** `fastf1==3.7.0` (`requirements.txt`); verified installed
  `3.7.0` in the pinned test env alongside pandas 2.3.3.
- **Cache configuration in use:** `fastf1.Cache.enable_cache("data/raw/
  fastf1_cache")` in every ingestion script (some via relative path —
  cwd-dependent — others via `ROOT / …`; the multilap builder exposes
  `--cache-dir` defaulting to `data/raw/fastf1_cache`). **D3 must centralise
  this** (single helper, absolute path, no cwd dependence).
- **Locally cached coverage (directory listing only, no session loads):**
  year dirs 2019–2023, **104 session entries** — exactly matching the
  104-race legacy inventory. No 2018 / 2024 / 2025 data is cached; those
  seasons will require fresh downloads in D5.
- **Reuse verdict:** the existing cache can safely accelerate Phase-1
  reprocessing/validation of 2019–2023 (it is the same upstream byte source
  the legacy datasets were built from), but **cache files are not canonical
  data** — they stay local/ignored, never enter Git, and the V2 pipeline
  must run identically from a cold cache.
- **Cache paths stay separate** from canonical V2 datasets (§11).

---

## 7. Parquet readiness — NOT AVAILABLE (expected gap)

- `pyarrow`: **not installed** (`ModuleNotFoundError` in the pinned env).
- `fastparquet`: **not installed.**
- `requirements.txt` / `requirements-test.txt`: **zero** mentions of
  `arrow`/`parquet`.
- **Consequence:** Phase 1 **will require a dependency addition during
  D1–D3** (prefer `pyarrow`, pinned, before any canonical Parquet is
  written; D2 schema work should select the engine). No dependency is added
  in D0. No silent CSV fallback for V2 canonical storage is accepted.

---

## 8. Dependency gaps (for D1–D3)

1. Parquet engine (`pyarrow`, pinned) — required before D6 output.
2. Nothing else identified at D0: pandas/numpy/fastf1/joblib/sklearn pins
   already satisfy audit/validation/probe needs; `requirements-test.txt`
   (pytest/httpx) covers test needs.
3. Per plan §41, no database/queue/infra dependencies are to be introduced
   in Phase 1 (Parquet suffices for the analytical layer).

---

## 9. Temporal / leakage-risk classification

Existing `build_snapshot` behaviour (`build_dataset_multi_race_multilap.py`,
`build_dataset_multi_race_weather.py`), classified for the future feature
contract (no calculations modified in D0):

| Field / behaviour | Class | Rationale |
|---|---|---|
| `position_x`, `session_time_x_seconds`, `lap_time_x_seconds`, `compound_x`, `tyre_life_x`, `stint_x`, `fresh_tyre_x`, `pit_in/out_time_present`, `track_status_x` (from `pick_laps(lap_x)` snapshot) | **SAFE SOURCE FIELD** | Single-lap FastF1 snapshot; no future laps accessed |
| `gap_to_leader_seconds` (snapshot-internal: leader session-time at lap X minus own) | **SAFE SOURCE FIELD** | Computed strictly within the lap-X snapshot |
| `weather_*` via `weather_at_time_seconds` (latest row ≤ lap-X leader time) | **SAFE SOURCE FIELD** with one edge case → **REQUIRES TEMPORAL HANDLING**: if *all* weather rows are after `t_sec`, the code takes the earliest (future) row as "best-effort" (`build_dataset_multi_race_weather.py:82-84`). D7/D9 must replace the fallback with explicit null + missingness record |
| `is_winner` (from post-race `session.results`, `Position == 1`) | **LABEL-ONLY** | Must never enter feature/state side; future label transport for D9 |
| `year`, `event_name`, `driver`, `driver_number`, `lap_x` | **SAFE SOURCE FIELD** (identifiers/metadata) | Known at inference time; but see §10 — not stable IDs |
| Cleaning clips (`gap ≤ 300`, `lap_time 30–300`, `tyre_life 0–60`, `position 1–30`) | **REQUIRES TEMPORAL HANDLING** (review in D9) | Value clamps fitted to legacy checkpoint ranges; must be re-justified, not inherited blindly, for all-lap data |
| `session.results` sorted `Position` for winner (`weather` builder) | **LABEL-ONLY** | Same as `is_winner` |
| Nothing in the current builders uses full-session aggregates, forward-fill, or future-lap rolling windows | — | No `whole_race_dataframe → Lap Y` pattern exists today; the risk is *introduction*, not inheritance |

---

## 10. Existing tests / schemas / identifiers / paths relevant to Phase 1

- **Reusable test patterns:** `test_datasets.py` (schema/inventory/integrity),
  `test_known_defects.py` (sha-pinning + xfail discipline for known defects),
  `conftest.py` (NaN-tolerant loading). D-phase validation/leakage tests
  should extend — not replace — these files.
- **Schema conventions:** `_x` suffix = lap-X snapshot value; interim
  (`*_base.csv`) → cleaning → processed (`base/dataset_clean.csv`);
  `results/data_quality/` CSV reports. No machine-readable schema yet (D2).
- **Identifiers (D2 must replace):** races keyed by display strings
  (`year` + `event_name` from the FastF1 schedule); drivers by 3-letter
  `driver` abbr + `driver_number`. No stable `race_id`/`driver_id`,
  no provenance/version columns. `RACE_KEYS = ["year", "event_name"]`.
- **Path assumptions Phase-1 code must not break:** `ml/config.py::ROOT`
  (`parents[1]`), `get_dataset_path` / `get_model_dir` (legacy inference
  paths — frozen); scripts resolve root via `parents[2]` or
  `find_project_root` (requires `data/` + `scripts/` siblings); relative
  `"data/raw/fastf1_cache"` in some scripts means **cwd = repo root**;
  frontend `NEXT_PUBLIC_API_BASE` default `http://127.0.0.1:8000`.
- **Technical debt relevant to Phase 1:** (a) §1 cache re-tracking; (b)
  no `pyarrow`; (c) `data/models/`, `data/sequences/` empty placeholders
  (leave or document in D2 — do not scatter V2 outputs into them
  ad hoc); (d) per-script cache/ROOT boilerplate → centralise in D3;
  (e) no manifests/checkpoints/idempotency (whole-CSV rewrite per run) —
  the core D3 work; (f) GroupKFold + independent-probability semantics stay
  frozen until their V2 phases.

---

## 11. Proposed V2 data namespace (proposal only — nothing created)

Per the brief and plan §6 (adapted so legacy paths are untouched; no empty
directories created in D0 — that would violate the plan's own rule):

```text
data/v2/                        # NEW namespace; legacy data/processed etc. untouched
├── raw/manifests/              # ingestion manifests / checkpoint state (D3)
├── interim/                    # normalised per-event frames (D5–D7)
├── processed/
│   ├── races/  results/  laps/ # season-partitioned Parquet (D6)
│   ├── stints/ pit_stops/      # (D7)
│   ├── weather/ race_control/  # (D7)
│   └── telemetry_summary/      # only if D8 decision says so
├── exports/                    # deterministic CSV exports (compat only)
└── reports/data_quality/       # machine + human quality reports (D11)
```

Rationale: `data/processed/` and `data/raw/` already have legacy meanings
(checkpoint CSVs; FastF1 cache), so nesting V2 tables under them invites
collision. A `data/v2/` root keeps legacy inference byte-stable while the
platform is built alongside. Final adoption is a D2 decision.

---

## 12. Blockers

- **To D1 (Source & Coverage Audit): NONE.** D1 needs only the installed
  FastF1 3.7.0, the existing cache, and probe scripts; all present. (D1 will
  need network access for 2018/2024/2025 probes — environment property, not
  a blocker.)
- **To D2 (Schema & Contracts): NONE** for design work. Implementation of
  Parquet-backed validation will need the §7–8 `pyarrow` pin first.
- **To D3 (Resumable Ingestion): NONE** for framework design (greenfield
  manifests/retries/idempotency). Operational note: centralise cache config
  and re-apply the §1 cache untracking before any commit containing D3 work.
- **Non-blockers recorded:** Monaco 500 (legacy serving defect, out of
  Phase-1 scope); GroupKFold/independent-probability semantics (frozen until
  later phases).

---

## 13. D0 Definition of Done verdict — SATISFIED

Per `V2_PHASE_1_DATA_PLATFORM.md` D0: plan + Foundation report read ✓;
regression tests run (67+21 green) ✓; application confirmed operational
(architecture present, fixture/artifacts intact, TestClient/live smoke basis
from R9 with no intervening code change) ✓; post-refactor structure
understood and documented (§§4–5, §10) ✓. The foundation is neither
incomplete nor materially broken — the §1 cache-staging flag is a
re-appliable hygiene item with no data/behaviour impact. **D0 PASSES. Do not
begin D1 without explicit approval.**
