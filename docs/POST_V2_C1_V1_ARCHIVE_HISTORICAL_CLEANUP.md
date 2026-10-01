# POST-V2 C1 V1 ARCHIVE + HISTORICAL CLEANUP

> C1 executed the C0 plan: reverify → archive outside repo → verify →
> remove approved copies → validate. `v2-final` untouched. Nothing staged,
> committed, tagged, or pushed.

## Final verdict

**C1 COMPLETE — READY FOR C2**

## Frozen v2 reference

- `git rev-parse HEAD` → `487f15dee184f32f2adeb94814054eb60c98e505` ✅
- `git tag --points-at HEAD` → `v2-final` ✅
- `git rev-parse v2-final^{commit}` → same ✅ (annotated tag; object hash
  differs by design, commit dereference exact)
- Tag not moved/deleted; history not rewritten; `v2-final` unamended.
- Nothing staged before, during, or after (`git diff --cached` empty
  throughout; removals done with plain `rm`, never `git rm`).

## Repository safety

Pre-mutation dirt classification (19 paths + ignored runtime files):

| Path(s) | Category |
|---|---|
| `?? docs/POST_V2_C0_REPOSITORY_CONSOLIDATION_AUDIT.md` | C0 |
| 11× `D` graft-era tooling + 3× `M` (`AGENTS.md`, `GEMINI.md`, `opencode.json`) + 4× `??` (`.impeccable/`, `.opencode/`, root `package.json`/`package-lock.json`) | PREEXISTING_OTHER_WORK (unchanged since C0; untouched in C1) |
| `graphify-out/`, `.venv/`, `runtime_artifacts/`, caches | EXPECTED_LOCAL_GENERATED (ignored) |
| UNKNOWN | **none** — zero-UNKNOWN gate met before any mutation |

## Graphify snapshot

- `graphify update .` re-run: **12209 nodes / 29362 edges / 391 communities**
  (delta vs C0: +35 nodes/+34 edges/+14 communities from the C0 report file).
- Graphify-first navigation for candidate dependency shape; `git grep` /
  `git ls-files` for Makefile/Docker/CI/manifest/fixture/filesystem refs.

## C0 candidate inventory

106 tracked files in 4 families (C0 LEGACY_UNUSED, path-explicit in C1):

- 47 workflow scripts: `scripts/{analysis(5),baselines(4),cleaning(3),
  data(7),dev(5),models(10),models_weather(4),predict(3),results(3),
  utils(3)}`
- 16 top-level one-off/benchmark scripts (per C0 list)
- 37 result files: `results/{analysis(16),baselines(13),comparisons(8)}`
- 6 root docs: `V2_PHASE_1/2/3*.md`, `V2_FOUNDATION_REFACTOR.md.md`,
  `req.md`, `section5report.txt`
- Plus C0-UNCERTAIN re-checks: `results/debug/` (7), `DESIGN.md`,
  `data/sequences/`, `data/models/`, `build_replay_prediction_cache.py`,
  `build_simulation_parameters.py`, `build_phase9_evidence.py`

## Re-reference audit

Every candidate re-searched across: Python/TS imports, Makefile, Dockerfiles,
Compose, CI, tests, fixtures, scripts, README, PRODUCT, case-study, phase
docs, manifests, runtime preparation, frontend evidence generation.

| Candidate | References found | Classification | Disposition |
|---|---|---|---|
| 47 workflow scripts | none (zero imports from api/v2/tests/scripts/ml) | NO_REFERENCE | ARCHIVE_AND_REMOVE |
| `benchmark_phase6_monte_carlo/product`, `benchmark_phase7_s3_paired`, `run_phase7_s3/s4/s5_validation`, `validate_replay_prediction_cache` | none on active surfaces; plan/report mentions only | HISTORICAL_DOCUMENTATION_REFERENCE | ARCHIVE_AND_REMOVE |
| `run_phase7_s6_validation`, `run_phase7_s6_red_team` | docstrings in `s6_validation_protocol.py` + `test_v2_phase7_s6_validation.py` only (direction: scripts→helper) | HISTORICAL_DOCUMENTATION_REFERENCE | ARCHIVE_AND_REMOVE |
| `results/analysis,baselines,comparisons` | producers/consumers all inside archive set; `prepare_runtime_artifacts.py` FORBIDDEN_PREFIXES denylist (never-read; removal aligns) | NO_REFERENCE (active) | ARCHIVE_AND_REMOVE |
| `results/debug/` | archive-set producers only + denylist; README self-declares superseded ("should not be used for current reporting") | NO_REFERENCE (active) | ARCHIVE_AND_REMOVE |
| 6 root docs | frozen phase-report provenance notes only ("Inputs read: …") | HISTORICAL_DOCUMENTATION_REFERENCE | ARCHIVE_AND_REMOVE |
| `benchmark_phase4.py` | P4 freeze manifest `benchmark` section + `test_frozen_module_hashes_match` exact-hash | ACTIVE_TEST_REFERENCE | **RETAIN** |
| `benchmark_phase5_replay.py` | P5 freeze manifest `benchmark_files` (HASH_SECTION) + existence/hash test | ACTIVE_TEST_REFERENCE | **RETAIN** |
| `run_p11_performance_benchmark.py` | imported by `test_p11_benchmark_script.py` (source-safe CI) | ACTIVE_TEST_REFERENCE | **RETAIN** |
| `validate_phase6_simulation.py` | imported by `test_v2_phase6_r7.py` + `test_v2_phase6_r71.py` | ACTIVE_TEST_REFERENCE | **RETAIN** |
| `capture_phase7_s1_baseline.py` | imported by `test_v2_phase7_s1_phase6_compat.py`; `compatibility_fixture_producer` in P6 drift JSON | ACTIVE_TEST_REFERENCE | **RETAIN** |
| `build_replay_prediction_cache.py` | imported by 4 phase-8 test files; existence+content asserted by P5 freeze test | ACTIVE_TEST_REFERENCE | **RETAIN** |
| `build_simulation_parameters.py` | generator provenance in `v2/simulation/estimator.py` + `params.py` + contract tests | CURRENT_DOCUMENTATION_REFERENCE / ACTIVE_VALIDATION_REFERENCE | **RETAIN** (resolves C0 conflict conservatively) |
| `build_phase9_evidence.py` | `evidence.test.ts` + `evidence.ts` + `run_ci_frontend_tests.py` + phase-9 manifest | ACTIVE_TEST_REFERENCE | **RETAIN** (C4 owns replacement) |
| `DESIGN.md`, `data/sequences/`, `data/models/` | UNCERTAIN per C0, no new evidence | UNCERTAIN | **RETAIN** |
| Hard forbidden set (`ml/`, legacy api, `data/processed`, `data/interim`, `results/models`, R2 fixtures/tests, `v2/`, frontend, serving artifacts, freeze manifests, `v2_final_validation`, `v2_validation`, `data_quality`, case-study, P11 evidence, Docker/Compose/CI, deps, tooling dirt, `.gitignore`) | — | V2_REQUIRED / protected | **untouched** ✅ |

Unexpected-active-reference rule applied: 8 script candidates moved to
retained (above). No silent archiving.

## Retained candidates

C1_RETAINED_FROM_C0: the 8 scripts + `DESIGN.md` + 2 empty dirs (full reasons
in § Re-reference audit and in `results/post_v2_consolidation/
c1_v1_archive_record.json`). `results/debug/` was C0-UNCERTAIN but APPROVED
after grep (self-declared superseded, zero active refs).

## Final archive set

C1_ARCHIVE_SET = **106 files**, all LEGACY_UNUSED / ARCHIVE_AND_REMOVE
(explicit list in the archive manifest + record; no wildcards used):

- 47 workflow scripts · 9 one-off/benchmark scripts ·
  44 result files (incl. `results/debug/`) · 6 root docs.
- No directory deleted unless every contained tracked file was individually
  classified (verified via `git ls-files` per directory).
- Historical fastf1 blobs in git history: retained by design (never purge).

## Archive manifest

`f1-race-intelligence-v1-archive-manifest.json` (schema_version 1):

- source_reference `v2-final`, source_commit `487f15d…`, basis
  "C0 LEGACY_UNUSED + C1 per-path re-reference audit"
- file_count 106, total_uncompressed_bytes 1878778
- per-file: path (repo-relative, sorted), size_bytes, sha256,
  classification LEGACY_UNUSED, removal_disposition ARCHIVE_AND_REMOVE
- manifest sha256 `454308b9…c9478b2c0`; no timestamps, paths, users, secrets

## ZIP creation

- `f1-race-intelligence-v1-archive.zip` (1,316,037 bytes) built OUTSIDE the
  repo via deterministic builder (sorted entries, fixed timestamps,
  `files/<repo-path>` + root manifest; 107 entries).
- Contains only manifest + 106 files. Excluded by construction: `.git`,
  caches, `.env`/secrets, raw datasets, runtime artifacts,
  PREEXISTING_OTHER_WORK.
- Builder: temp-directory script (outside worktree; not committed).

## ZIP verification

Independent verifier, SECOND temp directory — all green before any removal:

- integrity (`testzip`) pass · file count 106/106 · sizes 106/106 ·
  sha256 106/106 · unexpected files 0 · **100% match**
- ZIP sha256 `ea466002…4ff983`. Originals removed only after this PASS.

## Archive location

Local filesystem path reported without claiming NAS transfer (Part L).
The verified ZIP remains OUTSIDE the repository (temp-directory staging
area). NAS copy is the user's separate step; C1 does not require it and
this report claims no transfer. (Exact local path available in the session
record; deliberately not committed to Git per Part T sanitization rules.)

## Removed active-tree material

- 106 files removed with explicit per-path `rm` (manifest-driven, verified
  `is_file` each; no `rm -rf scripts/*`, no `find -delete`).
- 15 now-empty directories removed with `rmdir` only (14 immediately +
  `results/debug/` chain after confirming zero files): `scripts/{analysis,
  baselines,cleaning,data,dev,models,models_weather,predict,results,utils}`,
  `results/{analysis,baselines,comparisons,debug(+archive_pre_alignment)}`.
- `ARCHIVE_COPY_ONLY`: none — every archived file was approved for removal.

## Forbidden-set verification

All Part E entries untouched: `ml/`, legacy api, `data/processed`,
`data/interim`, `results/models`, R2 fixtures/tests, `v2/`, frontend,
serving joblib, freeze manifests, `v2_final_validation`, `v2_validation`,
`data_quality`, case-study, P11 evidence, Dockerfiles, Compose, CI, deps,
tooling dirt, `.gitignore`, all V2_REQUIRED + UNCERTAIN. Verified via
`git diff --name-status` (only 106 approved D + preexisting dirt).

## Pre-removal validation

- `make preflight-source` (repo 3.11 venv; system python3 is 3.14 and
  correctly rejected): **pass** before removal.
- No Tier-3, no benchmarks (per spec; removal set has no scientific
  contract surface — confirmed by re-grep).

## Post-removal validation

- `make preflight-source`: **pass** after removal.
- `make ci` = `ci-python` + `ci-frontend`, both **green**:
  - ci-python: `collected=3210 selected=2489 deselected=721
    (stale=0 runtime=0 corpus=721)` — collection pin intact (no test drift);
    **2480 passed, 4 xfailed, 0 failed** (41m59s).
  - ci-frontend: **exit 0** (npm ci + node tests + tsc + lint + build +
    package-lock diff). Note: first invocation failed on launcher mechanics
    (relative `PYTHON=.venv/bin/python` after `cd frontend`), unrelated to
    C1 content; re-ran with absolute PYTHON — green.
- No Tier-3 rerun: not justified (no scientific contract touched; collection
  pin + identities confirm equivalence).

## Scientific identities

All exact, no regeneration:

- serving model `1116b34f…2eaf3fcaa59f4` ✅ (recomputed sha256)
- phase-2 content `d2ee966c…592799db` ✅ (manifest record intact)
- phase-2 parquet `b0f17b66…032d7ba1590b3` ✅ (manifest record intact)
- explainability `bae84b61…2828f73982939f` ✅ (sidecar intact)
- replay aggregate `78a3c059…1ce0f03ee3b8ba96298` ✅ (freeze manifest + report)
- simulation `r3-v1__through-2024` ✅ (params dir + generator provenance)

## Documentation safety

- `README.md`, `docs/case-study/README.md`,
  `docs/case-study/TECHNICAL_CASE_STUDY.md`: **29 relative links checked,
  0 broken** (pre-existing zero refs to candidates confirmed).
- Remaining mentions of archived paths live in frozen phase-history docs
  and `v2/d10.py` provenance-evidence strings (no file I/O; verified) —
  classified historical, left for C4 per spec. No active entry point broken.

## Git diff audit

- `git diff --stat`: 120 files, +38/−19844.
- `git diff --name-status`: 117× `D` + 3× `M`, zero other classes.
- Classification: 106× C1_APPROVED_REMOVAL; 11× `D` + 3× `M`
  PREEXISTING_OTHER_WORK (graft-era, pre-C1); C0 report untracked (C0_REPORT).
- **Zero UNKNOWN. No source/test/config/dep/tooling changes. No renames.**

## Archive record

`results/post_v2_consolidation/c1_v1_archive_record.json` (13,989 bytes,
new directory `results/post_v2_consolidation/`): schema_version,
archive_filename, archive_sha256, counts, source_reference/commit,
manifest_sha256, sorted archived/removed paths (106), 11 retained candidates
with reasons, verification + validation blocks. Sanitized: no absolute
paths, usernames, NAS paths, timestamps, or secrets.

## NAS handoff

The verified ZIP waits OUTSIDE the repo for the user to copy to NAS.
C1 completion does not require NAS transfer. Do not delete the local ZIP
until the NAS copy is confirmed (out-of-band, later stage).

## Recovery

- `git checkout v2-final` restores everything (frozen release + all 106
  archived files, which are tracked at/before `v2-final`).
- V1 ZIP is external convenience storage, not the recovery path.
- History never rewritten. Rollback of C1 worktree changes: `git checkout
  -- .` equivalent via explicit restore (no staging was ever created).

## Risks / blockers

- None blocking. Notes: (1) retained 8 scripts keep `scripts/` top level
  populated — C2 organizes survivors; (2) frozen phase docs + d10 strings
  now point at archived paths — historically accurate, C4-owned;
  (3) `.env` live credential still present-ignored (see below);
  (4) ci-python takes ~42 min — C5 must budget accordingly.

## C2 handoff

C1 leaves: `scripts/` with 14 survivors (8 retained + 6 runtime/CI:
`prepare/check/replay-matrix/run_ci*`), `results/` without legacy
subdirs, root without duplicate phase docs. C2 (Option B per C0) may now:
rename `v2/`→domain package, split `api/` legacy/v2, re-home
`scripts/`+`tests/`+`docs/`. C2 must keep the 8 retained scripts'
importers green (freeze tests import 4 of them by path).

## Entry gate

- [x] v2-final commit exact (`487f15d…`)
- [x] v2-final tag exact (annotated; dereferences to HEAD)
- [x] nothing staged (before, during, after)
- [x] dirty paths classified before mutation (0 UNKNOWN)
- [x] C0 audit used as authoritative input (+ re-verified, not blind-copied)
- [x] Graphify refreshed (12209/29362/391)
- [x] every archive candidate explicitly listed (106 + retained)
- [x] every candidate re-reference checked (table above)
- [x] unexpected active references caused retention (8 scripts)
- [x] V2_REQUIRED untouched
- [x] UNCERTAIN untouched (except `results/debug`, promoted on evidence)
- [x] hard forbidden set untouched
- [x] final archive set explicit (C1_ARCHIVE_SET, 106 paths)
- [x] retained-candidate list explicit (11 entries with reasons)
- [x] archive construction outside repository (temp staging dir)
- [x] relative paths preserved (`files/<repo-path>`)
- [x] deterministic manifest created (sorted, hashed, sanitized)
- [x] no secrets included (`.env` never read/copied; only presence recorded)
- [x] no `.env` included
- [x] ZIP created outside repository
- [x] ZIP integrity test green
- [x] extracted file count exact (106/106)
- [x] extracted sizes exact (106/106)
- [x] extracted SHA-256 exact (106/106)
- [x] no unexpected archive files (0)
- [x] ZIP SHA-256 recorded (`ea466002…4ff983`)
- [x] archive local path reported (session; outside repo)
- [x] NAS transfer not falsely claimed
- [x] pre-removal validation green (`preflight-source`)
- [x] originals removed only after archive verification
- [x] only approved removal paths removed (manifest-driven `rm`)
- [x] no broad deletion command used (per-path `rm` + `rmdir`-if-empty)
- [x] post-removal reference audit complete (d10 strings triaged as provenance)
- [x] `make preflight-source` green (post-removal)
- [x] `make ci` green (2480 passed/0 failed + frontend exit 0)
- [x] no Tier-3 rerun (correctly unjustified)
- [x] scientific identities exact (6/6)
- [x] current README links green (29/29)
- [x] case-study links green (included in 29/29)
- [x] no active runtime/source modification
- [x] no dependency modification
- [x] no developer-tooling cleanup
- [x] no v2 rename
- [x] Git diff fully classified (106 C1 + 14 preexisting; 0 UNKNOWN)
- [x] zero UNKNOWN
- [x] archive record created (sanitized)
- [x] archive record sanitized (verified: no paths/users/timestamps/secrets)
- [x] C1 report created (this file)
- [x] ignored credential not exposed (value never printed/copied)
- [x] credential rotation requirement recorded (see below)
- [x] recovery via v2-final documented
- [x] nothing staged / committed / tagged / pushed
- [x] C2 handoff explicit

## Credential note

LIVE_IGNORED_CREDENTIAL_PRESENT = true (ignored `.env`, untouched by C1).
ROTATION_REQUIRED_OUT_OF_BAND. Value never displayed, copied, archived, or
manifested.
