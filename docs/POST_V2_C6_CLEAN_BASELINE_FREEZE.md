# POST-V2 C6 CLEAN BASELINE FREEZE

> Release engineering only. No cleanup, refactoring, documentation
> rewriting, dependency work, scientific development, feature
> development, or v3 development was performed in C6. `v2-final` was
> not moved, amended, or rewritten. Nothing was pushed.

## Final verdict

**C6 COMPLETE — POST-V2 CONSOLIDATION FROZEN**

## Original v2 reference

- `v2-final^{commit}` = `487f15dee184f32f2adeb94814054eb60c98e505`
- Pre-staging HEAD was exactly that commit; `v2-final` pointed at HEAD.
- Nothing was staged before C6 work began.
- The C6 consolidation commit is the single commit directly after
  `v2-final`. Commit: SELF (the commit containing this report).
- Tag `post-v2-clean-baseline` points exactly at the new HEAD commit.

## Consolidation scope

C0 inventory, C1 archive of superseded V1 workflow material, C2
behavior-preserving `v2/` to `raceintel/` migration with a minimal
pickle shim, C3-A audit plus C3-B hygiene, C4 current-documentation
normalization, C5 full equivalence and runtime validation, C6 freeze.
No scientific, model, feature, simulation, strategy, API-contract, or
dependency change beyond the documented C3-B `motion` removal and the
mechanical C5 D11 probe-string repair.

## C1 archive

106 LEGACY_UNUSED files archived to the external
`f1-race-intelligence-v1-archive.zip` (sha256 `ea466002…4ff983`,
verified 106/106 by count, size, and hash before removal) and removed
from the active tree. 8 scripts with live test/manifest references
were retained, plus `DESIGN.md` and 2 empty placeholder dirs. Record:
`results/post_v2_consolidation/c1_v1_archive_record.json`.

## C2 structural migration

121 implementation files moved `v2/` to `raceintel/` (domain
subpackages `data/`, `pipeline/`, `race_state/`, `replay/`,
`explainability/`, plus whole `features/`, `labels/`, `model_lab/`,
`simulation/`, `strategy/`, `experiments/`). Compatibility shim
retained (`v2/__init__.py`, `v2/model_lab/__init__.py`,
`v2/model_lab/preprocessing.py`) for the frozen serving joblib's
embedded `v2.model_lab.preprocessing` class path. Active imports
repaired across `api/`, scripts, tests, Dockerfile, and docs.
Test layout and the 3210 collection pin unchanged. Record:
`results/post_v2_consolidation/c2_structural_migration_record.json`.

## C3 repository hygiene

C3-A audit found zero confirmed removal candidates (shim,
transitive pins, framework registration, and era separation overturn
every flag). C3-B dispositioned 11 obsolete Graft-era tracked files,
ignored local `.opencode/`/`.impeccable/` state, removed the root
shadcn-stub residue locally, and removed the proven-unused frontend
`motion` dependency with full validation green. Python pins
unchanged. Record:
`results/post_v2_consolidation/c3_hygiene_record.json`.

## C4 normalization

Current docs/reference model normalized: README repository guide and
Tier-1 numbers repaired, PRODUCT.md historical note extended (body
frozen), docs index added, current architecture added, development
guide added. Historical evidence preserved untouched. Record:
`results/post_v2_consolidation/c4_normalization_record.json`.

## C5 equivalence evidence

Tier-1: 3210 collected, 2480 passed, 4 xfailed, 0 failed.
Tier-3: 3201 passed, 5 skipped, 4 xfailed, 0 failed, 0 errors
(59m22s; collection exact, +8 green nodes accounted, no rebaseline).
Frontend 180 passed with TypeScript, lint, and production build
green. Backend and frontend Docker builds green. Compose runs exactly
backend plus frontend with runtime smoke green. One mechanical D11
probe-string repair (C5_REPAIR-1, 0 logic). Record:
`results/post_v2_consolidation/c5_equivalence_validation_record.json`.

## Scientific identities

6/6 exact, no regeneration:

- serving: `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
- Phase-2 content: `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`
- Phase-2 parquet: `b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3`
- Explainability: `bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f`
- Replay: `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298`
- Simulation: `r3-v1` through 2024, `phase6-r3-empirical`

## Runtime equivalence

Runtime bundle VALID (1939 files, manifest `e4008425…`,
byte-identical to the frozen Phase-10 reference). Serving joblib
loads through the shim via `raceintel.model_lab.serving`. Live
container proof covers health, ready (6/6), state, winner-snapshot
(INDEPENDENT_BINARY, field sum 1.987044), replay, explainability,
Monte Carlo determinism, strategy, legacy ensemble, and the 2025
triple-404 firewall. Frontend routes all 200 in production.

## Compatibility surfaces

Public `/v2/` API namespace, the 3-file `v2/` pickle shim (removal
only when no frozen artifact embeds a `v2.*` class path), the frozen
`ml/` legacy serving stack with legacy `/predict/*` routes, tracked
legacy lap-checkpoint CSVs, and the frontend route set are preserved
compatibility surfaces, not deprecation targets in this baseline.

## Final repository architecture

- `raceintel/` — current domain implementation
- `api/` — HTTP/service boundary (imports `raceintel/` one-way)
- `frontend/` — Next.js product
- `ml/` — frozen legacy serving compatibility
- `v2/` — minimal pickle compatibility shim (3 files)
- `scripts/` — reproducibility/build/validation utilities
- `tests/` — regression/scientific contracts
- `data/` — scientific/local data boundaries
- `results/` — evidence/artifacts
- `docs/` — current plus historical documentation

Nothing was renamed in C6.

## Historical recovery

- `v2-final` — frozen original v2 repository
  (`487f15dee184f32f2adeb94814054eb60c98e505`).
- `post-v2-clean-baseline` — scientifically equivalent consolidated
  repository (the C6 commit, child of `v2-final`).
- Every archived file retains full Git history at or before
  `v2-final`; `git checkout v2-final` restores the frozen release.

## External archive

`f1-race-intelligence-v1-archive.zip` (106 files, sha256
`ea466002…4ff983`) lives outside the repository. NAS transfer is a
user out-of-band step. The ZIP is convenience storage, never the
recovery path.

## Known limitations

Tier-3 wall-time (~59 min) is environmental; C6 does not rerun it.
Docker Desktop Mac loopback timings carry virtualization overhead.
The 2025 holdout firewall (404) is intentional behavior. Retained
uncertains (`DESIGN.md`, empty placeholder dirs, `tabulate` pin)
stay owner/proof-gated. Directory rename to `f1-race-intelligence`
remains local-only and out of scope.

## Security note

LIVE_IGNORED_CREDENTIAL_PRESENT = true. ROTATION_REQUIRED_OUT_OF_BAND.
`.env` is ignored, untracked, never staged. No secret-like local file
is tracked, no credential appears in staged additions, and no
credential appears in consolidation records/reports (safe-pattern
sweep clean; values never read or printed).

## Staged-path audit

362 tracked paths staged by explicit per-path manifest (no `git add .`
or equivalent): 106 C1 archived removals, 118 C2 move-source
deletions, 3 C2 shim modifications, ~117 C2 import/path repairs, 11
C3-B tooling deletions, `.gitignore` +2 ignore entries, frontend
`motion` removal, README/PRODUCT C4 prose, policy-file current
versions, plus new paths: `raceintel/` tree (121 moved + 5 inits, incl.
C5_REPAIR-1), 7 consolidation reports, 3 current docs, 6
consolidation records (incl. the C6 record and this report).
Zero UNKNOWN. No generated cache, binary surprise, secret,
machine-specific file, or absolute-user-path leakage staged. No
unrelated preexisting work staged
(PREEXISTING_OTHER_WORK_NOT_OWNED = 0).

## Validation

`make preflight-source` green before staging, against the staged
index, and after commit. Current documentation links green. Current
command paths resolve. Serving joblib loads. Six scientific
identities exact. Frontend package lock consistent with the
motion-free tree. Tier-3 not rerun (release candidate matches the
C5-validated tree). Staged source diff is import/path/docstring/
probe-string mechanics only.

## Commit

Commit message exactly: `chore(repo): freeze post-v2 consolidated baseline`

Commit: SELF (the commit containing this report). SELF is used
because the hash cannot be known before the commit exists; this file
is not amended after commit merely to insert its own hash. History
before `v2-final` was not rewritten; exactly one commit was created.

## Tag

Annotated tag exactly: `post-v2-clean-baseline`

Tag message exactly: `F1 Race Intelligence post-v2 consolidated baseline`

The tag points exactly at the new HEAD commit. `v2-final` was not
moved, deleted, or rewritten.

## v3 boundary

F1 Race Intelligence v2 development is closed. Post-v2 repository
consolidation is closed. Future development begins from
`post-v2-clean-baseline`. Future implementation belongs under the
stable `raceintel/` domain architecture. No v3 branch was created,
no v3 files were created, and Phase 12 was not started in C6.
