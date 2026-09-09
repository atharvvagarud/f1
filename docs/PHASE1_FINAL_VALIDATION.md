# Phase-1 Final Validation (D11, COMPLETE 2026-09-08)

> Plan: `V2_PHASE_1_DATA_PLATFORM.md` D11. This is the FINAL TECHNICAL
> ACCEPTANCE GATE for the Phase-1 Data Platform. Machine-readable evidence:
> `data/v2/reports/data_quality/d11_validation.json` (gitignored), produced by
> `python -m v2.d11` (read-only except deterministic rebuilds, which rewrite
> byte-identical outputs). Audit engine `v2/d11.py`; offline tests
> `tests/test_v2_d11.py` (6). Gate result: **44 findings, 0 failed,
> 0 unresolved BLOCKERs. Phase 1 is safe to freeze.**

## 1. Validation scope

Source coverage, schema/contracts, PK/FK integrity, identity integrity,
temporal integrity, state/label separation, missingness, source-anomaly
preservation, PARTIAL races, deterministic builds, manifest/idempotency,
recovery semantics, cache/Git hygiene, telemetry-deferred invariant, legacy
preservation, regression suite, fresh-environment reproducibility — 27 matrix
entries (`v2/d11.py::VALIDATION_MATRIX`), each with invariant, method,
expected result and severity (BLOCKER/MAJOR/MINOR/INFORMATIONAL).

## 2. Authoritative measured inventory

Canonical `data/v2/processed`: **1,783 Parquet files, ~74.1 MB** —
Tier-B 532 files (~2.6 MB), Tier-A 1,211 files (~24 MB), D6 16 files
(~12.5 MB), D7 8 files (~17.3 MB), D9 16 files (~17.7 MB incl. labels).
Reports: 10 JSON/schema artifacts. Manifests: `tierb-full.json` (76 units),
`tiera-2018…2025.json` (173 units), `d6/d7/d9-canonical.json`. Raw/source
cache (`data/raw/fastf1_cache`, FastF1 HTTP cache): **~16.16 GB, 1,900 blobs**
— source infrastructure, never canonical data. Zero tmp files, zero
unexpected files, all expected entities/reports present.

## 3. Validation matrix result

All 27 matrix entries executed; **44 findings, 0 failed**. No unresolved
BLOCKER. (Timings: full gate ≈108 s, peak RSS ≈870 MB.)

## 4. Contracts / schemas

All canonical files scanned via pyarrow schemas: column sets (and order where
contracted) conform for every Tier-A/B entity and D6/D7/D9 tables; dtype
spot-checks pass (D5 native int64/float64 physical forms accepted as
contract-conformant). `telemetry_summary` absent (inactive per ADR-0001).

## 5. PK / FK

PKs present, 0 null, 0 duplicates in all 19 canonical tables (Tier-B 7,
Tier-A 7, D6 state/quality, D7 state, D9 state/labels). All 16 declared
foreign-key relationships resolve with **0 orphans**, including state PK-set
equality across D6/D7/D9, labels PK == results PK, and Tier-B cross-checks.

## 6. Identities (adversarial)

- Driver numbers are attributes: multi-number drivers observed
  (max_verstappen 33→1 plus substitute numbers), correctly non-keyed.
- `(race_id, driver_number)` resolves to exactly one driver: 0 collisions.
- Constructor season scoping holds; renames present as distinct slugs
  (toro_rosso/alphatauri/rb, racing_point/aston_martin).
- Circuit per (season, round) non-null in all 173 races; Tier-A vs Tier-B
  circuit match: 0 mismatches. Race/event ids unique (173/173).
- No display-name/abbreviation in any primary key (schema scan); no builder
  merge keys on display strings (code scan).

## 7. Temporal safety

All **39 predictive-eligible fields** enumerated from the schemas with
per-field availability/lineage justification; all carry LAP_START/IN_LAP/
LAP_END availability; zero outcome-named fields; zero `model_feature`
lineage. Quality metadata (`source_unit_status`, `shortened_race`,
staleness anchors, message seqs, pit/stint boundary lineage) is never
eligible; results-sourced state identity is never eligible. D9 outcome fields
are LABEL_ONLY (identity keys non-eligible).

## 8. Leakage / future mutation

Executed leakage suites (`test_v2_d6/d7/d9.py`) green, plus the D11 combined
synthetic proof mutating **all families at once** (laps, weather,
race-control, pit events, stint facts/endings, results/winner) at a cutoff:
earlier predictive state identical; labels change appropriately. Recovery /
idempotency suites green (skip-COMPLETE, partial policy, stale recovery,
atomic writes, bounded retries).

## 9. State / label separation

D6/D7/D9 state tables carry **zero** LABEL_ONLY outcome columns (audited on
written parquet). Labels live at race×driver grain (3,458 rows == results
grain/PK set). Result-mutation proof re-verified: state unchanged, labels
change.

## 10. Labels

3,458 rows; PK clean; token vocab R 420 / W 18 / D 13; winners 173 (exactly
one per race); podiums 519; points finishers 1,730; classified 3,007; final
position null on exactly the 3 known DNS/withdrawn rows (unchanged);
binary DNF target still deferred.

## 11. Missingness

Recomputed whole-scope nulls equal the frozen d6/d7 stage reports on every
column (0 drifted columns): no silent imputation since stages closed. Known
gaps intact (lap_time/sectors/traps/compound/tyre-life/stint/track-status,
weather staleness, RC gaps).

## 12. Anomalies (all reproduce)

Belgium 2021: 60 rows/PARTIAL/shortened. Japan 2022: 507 rows/PARTIAL/
shortened. Monaco 2022 shortened with tyre-life missingness. 2018
track_status nulls = 1,317. 2018-r02: 69 RC messages, all untimed. Pit
asymmetry 246 in-only / 159 out-only. 3 null finals (identities unchanged).
Weather max staleness 477.348 s. Miami 2025 stint nulls 446.

## 13. PARTIAL races

Manifests: 171 COMPLETE + 2 PARTIAL (2021-r12, 2022-r18), nothing else. State
flags verbatim; no modelling-exclusion column exists in any state schema.

## 14. Weather / race-control / pit / stint audits

- Weather: 189,420/189,420 prior attachments; every `observed_at_s <=
  state_time_s`; ages ≥ 0 and recompute-exact; staleness top-3 races
  (2020-r01: 100 rows, 2023-r14: 27, 2018-r09: 9) reproduce; Germany-2019
  rain states 1,033; dry Bahrains 0. No future-nearest fallback.
- Race control: 14,992 / 14,923 / 69 recomputed; 2018-r02 states carry zero
  RC lineage (998 states); attachments as-of with non-negative ages; D9
  track-token distribution equals the D9 report per season.
- Pit/stint: 5,931 full / 246 in-only / 159 out-only; 0 negative durations;
  0 stint overlaps; 0 bad spans; no future-end columns in any state table;
  VER-2023-Bahrain final-lap spot check (2 completed stops) reproduces.

## 15. Telemetry invariant

ADR-0001 exists with Accepted status; contract marks the summary INACTIVE;
no `telemetry_summary` data; no telemetry columns in D9 state; `v2/d9.py`
imports neither fastf1 nor car data. Decision stands (not reopened).

## 16. Manifests / recovery / idempotency

Tier-B 76/76 COMPLETE; Tier-A 171 COMPLETE + 2 PARTIAL; every terminal unit
carries run_id, schema_version 1 and 7 output_refs, all files present.
Manifest (never file-existence) is authoritative in code. Recovery suites
green.

## 17. Determinism

D6 (1.44 s), D7 (7.54 s), D9 (4.09 s) rebuilt from existing sources:
**byte-identical** (0 changed files). D10 audit re-run stable. No FastF1
redownload; D8 caused no cache growth.

## 18. Reproducibility

Fresh isolated venv + exact `requirements.txt`/`requirements-test.txt`
install: pip OK, imports OK (`v2.d6/d7/d9/d10`, fastf1, pyarrow, pandas),
offline pytest subset green. Software reproducibility validated without
redownloading the cache.

## 19. Storage / performance

Canonical ~74.1 MB vs source cache ~16.16 GB (kept distinct; the cache is
never quoted as dataset size). Rebuild timings match prior manifests (no
regression >3× anywhere).

## 20. CLI smoke

All six CLIs print help (exit 0); explicit-scope planning and read-only
manifest status work; absent-data errors exit 2 with clear messages;
validation-only commands never import fastf1 (no network path).

## 21. Regression

Full Python/V2 suite green, frontend node tests green, `tsc` clean, eslint 0
errors, frontend production build green, golden legacy equivalence green,
API smoke green, legacy artifacts intact, D4–D10 invariants re-verified.

## 22. Git / repository hygiene

No tracked parquet/ff1pkl; `data/v2` and the FastF1 cache ignored and
untracked; no nested repos; no tracked `.env`; legacy tracked paths
(`data/processed`, `data/interim`, `results`, `ml`, `api`, `scripts`,
`tests/fixtures`, `frontend`) show zero modifications. Pre-existing
uncommitted V2 work product (`v2/`, `tests/test_v2_*`, report docs; plus the
inherited `.gitignore`/docs/requirements tweaks) is recorded as-is — history
rewrites are out of scope.

## 23. Findings register

44 findings, all `pass`, 0 failed, 0 unresolved BLOCKERs (full register with
severity/evidence/impact in `d11_validation.json`). No MINOR-or-worse
deviation was found, so **no fix was required or made** under the D11 fix
policy. No architectural BLOCKER exists; nothing was redesigned.

## 24. Blockers / D12 readiness

**Unresolved blockers: none.** Phase 1 is technically safe to freeze and
**D12 may proceed**: the platform is internally consistent, temporally safe,
leakage-tested, deterministic, reproducible, and fully documented. D12 scope
(data README, root README instructions, remaining documentation/exit) must
not change data semantics.
