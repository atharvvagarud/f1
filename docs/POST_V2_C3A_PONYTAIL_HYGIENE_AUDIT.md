# POST-V2 C3-A PONYTAIL HYGIENE AUDIT

> Status: READ-ONLY audit. No file was deleted, moved, renamed, edited,
> staged, committed, tagged, or pushed to produce this report, except this
> file itself. Frozen reference `v2-final` untouched. C3-B NOT started.

## Final verdict

**C3-A COMPLETE — READY FOR C3-B REVIEW**

Ponytail's audit lens was applied to the full post-C2 worktree and every
finding was challenged against Graphify + exact reference search + frozen
provenance. Result: **zero CONFIRMED_C3_CANDIDATE deletions**. The
repository is lean post-C1/C2; Ponytail's signal is almost entirely
false-positive-by-design (pickle shim, frozen transitive pins, framework
registration, intentional era separation). Two UNCERTAIN items carry
forward to C3-B (`motion` frontend dep, root shadcn stub disposition);
everything else is KEEP_* / NO_ACTION / DEFER.

## Frozen v2 reference

- `git rev-parse HEAD` → `487f15dee184f32f2adeb94814054eb60c98e505` ✅
- `git rev-parse v2-final^{commit}` → same ✅
- `git tag --points-at HEAD` → `v2-final` ✅
- Tag unmoved, history unrewritten, `git diff --cached --stat` empty
  (nothing staged before, during, or after) ✅

## Repository safety

`git status --short` classes (staged: none) and their classification:

| Worktree dirt | Category |
|---|---|
| 11× `D` graft-era tooling (`.claude/` 4, `.cursor/` 4, `.gemini/` 1, `.mcp.json`, `.ignore`) + 3× `M` (`AGENTS.md`, `GEMINI.md`, `opencode.json`) + 4× `??` (`.impeccable/`, `.opencode/`, root `package.json`/`package-lock.json`) | PREEXISTING_OTHER_WORK (unchanged since C0; untouched) |
| `?? docs/POST_V2_C0_REPOSITORY_CONSOLIDATION_AUDIT.md` | C0 |
| 106× `D` archived V1 copies + `?? docs/POST_V2_C1_…` + `results/post_v2_consolidation/c1_v1_archive_record.json` (inside untracked dir) | C1 (C1 removals verified intact, never restored) |
| 121× `D` under `v2/` (moved) + `?? raceintel/` + ~200× `M` import/path repairs (`api/`, `scripts/` survivors, `tests/`, `v2/` shim ×3, `Dockerfile.backend`, `data/README.md`) + `?? docs/POST_V2_C2_…` + `results/post_v2_consolidation/c2_structural_migration_record.json` | C2 |
| `graphify-out/`, `.venv/`, `runtime_artifacts/`, `.fastf1_cache/`, `frontend/.next`, `frontend/node_modules`, `data/v2/`, `__pycache__`, `.pytest_cache` | EXPECTED_LOCAL_GENERATED (ignored, not in status) |
| UNKNOWN | **none — zero-UNKNOWN gate met before audit** |

C1 archive identity re-verified from the record (not re-extracted):
ZIP sha `ea466002…4ff983`, 106 files. C1 removals remain removed (no
restored path appears as `M`/`??` outside `raceintel/`).

## Graphify snapshot

- `graphify update .` re-run per Part B.
- **Nodes: 11419 · Edges: 27772 · Communities: 332**
  (delta vs C2-after 11390/27740/322: +29/+32/+10 from the C2 report file
  now present in-tree plus community relabeling; no structural change).
- Used as primary challenge evidence: `graphify query` for shim identity
  (`v2/model_lab/preprocessing.py` ↔ `raceintel/model_lab/preprocessing.py`
  ↔ `FittedPreprocessor`) and survivor-script dependency shape
  (`build_replay_prediction_cache.py` ↔ replay/test communities); `rg`
  for everything Graphify cannot answer (dynamic imports, string refs,
  Docker COPY, Makefile/CI refs, fixture consumers, dist metadata).

## Ponytail installation

There is **no Ponytail executable**. Ponytail is a review-philosophy
package, not a scanner binary:

- Package: `@dietrichgebert/ponytail` **version 4.10.0** (from its
  `package.json` in the opencode package cache). No install/upgrade
  performed (nothing to install; forbidden anyway).
- Exact source: `.../node_modules/@dietrichgebert/ponytail/skills/`
  (`ponytail`, `ponytail-review`, `ponytail-audit`, `ponytail-debt`,
  `ponytail-gain`, `ponytail-help`). `which ponytail` → not found.
- Audit command used: the **`ponytail-audit`** one-shot whole-tree review
  lens (tags: `delete` / `stdlib` / `native` / `yagni` / `shrink`, ranked,
  biggest cut first), applied manually over the repo root with
  read-only tools (`read`, `rg`, `graphify query`, dist-metadata reads).
- Relevant options: none — the skill takes no flags; scope is
  over-engineering/complexity only (correctness, security, performance
  explicitly out of scope per the skill).
- Mutation: **none** — the skill lists findings and applies nothing
  ("Lists findings, applies nothing. One-shot."). No auto-fix, no
  deletion, no formatting, no cache, no output files created by the tool
  (there is no tool process; this report is the only artifact, and it is
  the explicitly permitted C3-A deliverable).
- Categories it analyzes: dead code, unused flexibility, speculative
  features (`delete`); hand-rolled stdlib (`stdlib`); replaceable deps /
  platform-covered code (`native`); single-implementation abstractions,
  unset configs, single-caller layers (`yagni`); longer-than-needed logic
  (`shrink`); repo-wide dependency/flag/config hygiene (per `Hunt`: deps
  the stdlib ships, one-product factories, delegate-only wrappers,
  one-thing files, dead flags/config).

## Audit command

No binary invocation exists. Executed audit (all read-only, repo root):

1. Full-worktree `rg` sweeps per candidate: direct `import X` / `from X`
   for all 45 `requirements.txt` pins + `requirements-test.txt`;
   substring + framework + dynamic (`importlib`, `__import__`,
   `import_module`, `python -m`, `ADAPTER_SOURCE`) sweeps.
2. `rg` reference sweeps for the 8 C1-retained scripts, the `v2/` shim
   path, `DESIGN.md`, empty dirs, tooling residue, frontend deps.
3. `graphify query` challenges for shim and survivor-script findings.
4. Installed-dist `Requires-Dist` reads in `.venv/lib/python3.11/`
   for transitive-closure proof (fastf1, matplotlib, requests,
   pandas, sklearn, fastapi chains).
5. Byte-level joblib strings check for the pickle class path.
6. `.gitignore` cover check per generated/cache path; secret presence
   check without reading values.

## Ponytail findings summary

Normalized into required categories (raw Ponytail tags in parentheses).
Counts are post-challenge (Part M statuses in later sections):

| Category | Ponytail-flagged | Confirmed C3 candidate | False positive | Retain-required | Uncertain |
|---|---|---|---|---|---|
| DEAD_CODE | 1 (shim, `delete`) | 0 | 1 | 0 | 0 |
| UNUSED_FILE | 4 (`delete`) | 0 | 2 | 0 | 2 |
| UNUSED_PYTHON_DEPENDENCY | 26 pins (`delete`) | 0 | 24 | 0 | 2* |
| UNUSED_FRONTEND_DEPENDENCY | 1 (`delete`) | 0 | 0 | 0 | 1 |
| DUPLICATION | 4 (`yagni`/`shrink`) | 0 | 4 | 0 | 0 |
| STALE_CONFIGURATION | 1 (`yagni`) | 0 | 0 | 0 | 1 |
| GENERATED_CLUTTER | 8 paths | 0 | 0 (all ignored) | 7 ignored-OK | 1 gap set |
| DEVELOPER_TOOLING | 10 items | 0 | 0 | 0 | 10 (C3-B decides) |
| SECURITY_HYGIENE | 1 (`.env`) | 0 | 0 | 1 (ignored, rotate) | 0 |
| OTHER | 0 | 0 | 0 | 0 | 0 |

\* `tabulate` + `matplotlib`: zero direct imports but proven transitive
pins (see below) — recorded as FALSE_POSITIVE for removal, with the
closure-pin rationale; `tabulate` alone could be re-examined only with
Docker-rebuild proof, so it also appears in Uncertain as a pin-only
question. Conservative verdict: retain.

## Dead code findings

| Path/component | Ponytail tag/rationale | Tracked? | Challenge evidence | C3-A status |
|---|---|---|---|---|
| `v2/__init__.py` + `v2/model_lab/__init__.py` + `v2/model_lab/preprocessing.py` (delegate-only re-exports) | `delete`: wrapper that only delegates; nothing replaces it | yes (`M` vs HEAD, C2 shim) | Byte check: serving joblib embeds `v2.model_lab.preprocessing` ×1, `raceintel` ×0. Graphify confirms shim↔`FittedPreprocessor` edge. C2 removal condition (no artifact embeds `v2.*`) unmet. | FALSE_POSITIVE — RETAIN_REQUIRED |
| raceintel/model_lab/* (~40 modules: runners/suites/candidates) | lens sweep: no `yagni`/`shrink` flag raised; decomposition matches runner/suite/candidate responsibilities, each imported by suites/tests | yes | No single-implementation interface or delegate-only wrapper found by inspection of module roles + green C2 suites as behavior proof. Coverage-backed per-function dead-code proof explicitly out of scope for C3-A (C0 position holds). | NO_ACTION (no finding to classify) |

No other dead-code finding. `api/` route functions are framework-
registered (FastAPI router mounts); never `delete` candidates.

## Unused file findings

| Path/component | Ponytail rationale | Challenge evidence | C3-A status |
|---|---|---|---|
| `v2/` shim files (3) | `delete`: near-zero static refs | Pickle-required (see above); `Dockerfile.backend` `COPY v2/`; container-contract tests green in C2 | FALSE_POSITIVE |
| `ml/` (4 files, legacy serving lib) | looks superseded next to `raceintel/` | Dockerfile COPY + `api/services/prediction_service.py` + 6+ R2 test files + frontend legacy flow; C0 V2_REQUIRED, C2 frozen | FALSE_POSITIVE |
| `DESIGN.md` | `delete`: loose refs only | Referenced by `docs/FRONTEND_REDESIGN_PLAN.md`, `FRONTEND_FOUNDATION_FREEZE_*`, and `frontend/app/globals.css`; C0/C1 UNCERTAIN-retained | UNCERTAIN → retain (C3-B decides track vs ignore; never delete — provenance-adjacent) |
| `data/sequences/`, `data/models/` (empty dirs) | `delete`: empty, unreferenced | Zero refs confirmed; empty placeholders, zero removal benefit, possible scaffold intent | UNCERTAIN → retain |

## Python dependency findings

Ground truth: direct-import sweep over `raceintel api ml scripts tests v2`
(all `.py`) + installed-dist `Requires-Dist` chains from the repo 3.11
venv. Full table (45 pins):

CONFIRMED_REQUIRED (direct import or runtime entry, 19):
`fastapi`, `uvicorn` (Docker CMD + Makefile + serving), `pandas`,
`numpy`, `scikit-learn` (68 `sklearn` hits), `xgboost`, `joblib`
(serving load path), `pyarrow` (9 parquet hits: d6/d7/d9/d11/contracts),
`scipy` (pace.py + phase tests), `requests` (21 hits), `python-dateutil`
via pandas chain (kept as pin; see transitive), `pytz`, `tzdata`,
`python-multipart` (fastapi/starlette dep), `tabulate` (see note),
`matplotlib` (see note), `pytest`, `httpx` (test files).

FALSE_POSITIVE as removal candidates — proven transitive pins (26 pins
with zero direct imports, each with a named parent in installed metadata):

- Via **fastf1 3.7.0** (CONFIRMED_REQUIRED Tier-A ingestion; its
  `Requires-Dist`: cryptography, matplotlib, platformdirs, pyjwt,
  rapidfuzz, requests-cache, scipy, signalrcore, timple, websockets):
  `signalrcore`, `timple` (all hits are `NotImplemented` substrings —
  zero real refs), `RapidFuzz` (hits are prose "fuzzy", zero imports),
  `PyJWT`, `cryptography`, `requests-cache`, `websockets`,
  `platformdirs`, `matplotlib` (+ its subtree below).
- Via **matplotlib 3.10.8** (required by fastf1): `contourpy`,
  `cycler`, `fonttools`, `kiwisolver`, `packaging`, `pillow`,
  `pyparsing` (matplotlib itself has zero direct imports post-C1 —
  all plot producers were archived — but the pin holds the fastf1
  subtree reproducible).
- Via **requests** (required by fastf1/fastf1-tree): `certifi`,
  `charset-normalizer`, `idna`, `urllib3`.
- Via **cryptography** (required by fastf1): `cffi`, `pycparser`.
- Via **requests-cache** (required by fastf1): `cattrs`, `attrs`,
  `url-normalize`, `msgpack` (msgpack also via signalrcore).
- Via **pandas 2.3.3**: `python-dateutil`, `pytz`, `tzdata`, `six`
  (via dateutil).
- Via **scikit-learn/scipy**: `threadpoolctl`, `typing_extensions`
  (also via anyio), `six`.
- Via **fastapi/starlette**: `python-multipart`.

Note on `tabulate`: zero code refs (`to_markdown`/`tabulate` absent
worktree-wide) yet listed in installed pandas/scipy `Requires-Dist`
metadata — retained as frozen-closure pin. Not a C3-B removal without
`pipdeptree` + Docker-rebuild proof; default KEEP.

Per Part J rule (absence of direct import ≠ unused): **no Python pin
is CANDIDATE_UNUSED**. Ponytail's dependency signal here is NOISY
(it cannot see transitive-closure pins or native-extension consumers);
Graphify + dist metadata overturn all 26 flags.

## Frontend dependency findings

| Dep | Use evidence | Status |
|---|---|---|
| `next` 16.1.6, `react`/`react-dom` 19, `tailwindcss` 4 + `@tailwindcss/postcss`, `typescript`, `eslint` + `eslint-config-next`, `@types/*` | App builds/runs (C2 ci-frontend green: npm ci + tests + tsc + lint + build) | CONFIRMED_REQUIRED |
| `lucide-react` | Imported (`PlaybackControls.tsx`) | CONFIRMED_REQUIRED |
| `motion` ^12.35.2 | **Zero** source imports (`.ts/.tsx/.css/.json` sweep; only `package.json` + lockfile + `prefers-reduced-motion` CSS substring) | UNCERTAIN — sole CANDIDATE_UNUSED dep; removal needs `npm run build` + frontend-test proof in C3-B (LOW risk) |
| `shadcn` (root stub, NOT frontend) | No `components.json` in frontend, zero frontend source refs; only root `package.json` + `opencode.json` + docs mentions | Developer-tooling residue; UNCERTAIN (C3-B: keep-track-if-shadcn-stays vs remove-local; untracked either way) |

No duplication between root stub and `frontend/package.json`
(different ecosystems, confirmed).

## Duplication findings

All four Ponytail-visible duplications are intentional separation,
not accidental (C0 analysis re-confirmed; C2 changed nothing here):

1. **Dual serving stacks** (`ml/`+legacy `api/` vs `raceintel/`+v2 `api`;
   dual frontend prediction trees; `FEATURE_COLS` vs `features/registry.py`;
   `ml/config.py` vs `raceintel/config.py` vs `api/config.py`;
   `prediction_service.py` vs `v2_service.py`) — era-separated, R2-pinned,
   Docker-shipped. Consolidation would break frozen behavior. RETAIN.
2. **Duplicate setup narratives** (`README.md` vs `PRODUCT.md` vs
   case-study; root phase docs already archived in C1) — pointer
   reconciliation is C4 work, not deduplication. DEFER to C4.
3. **Triplicated lap-variant scripts** — resolved by C1 archive. NO_ACTION.
4. **Per-phase benchmark/validation helpers** — retained 8 are
   test-referenced evidence generators; rest archived. RETAIN.
5. `raceintel/model_lab/` name kept (not renamed `models/`) — deliberate
   single-dimension rename in C2 (pickle path + stable responsibility).
   RETAIN.

No `yagni` single-implementation interface and no `shrink`-grade
duplication found in active source that survives the 7-gate Part M test.

## Configuration findings

- Root `package.json` (`shadcn` stub): Ponytail `yagni` (lockfile without
  source). UNCERTAIN — C3-B decides track vs remove-local; needs frontend
  owner confirm shadcn stays in workflow. No `.gitignore` edit in C3-A.
- `requirements.txt` / `requirements-test.txt` / `frontend/package.json`:
  no stale entries found (all challenged above). NO_ACTION.
- `Makefile`, `compose.yaml`, Dockerfiles, CI workflow, `opencode.json`:
  active and referenced. NO_ACTION.
- `.gitignore`: covers all generated/cache paths (137 lines, verified per
  path) except the known C0 gap set (`.opencode/`, `.impeccable/`, root
  `package.json`/`package-lock.json` untracked+unignored) — C3-B decision,
  not C3-A edit.

## Generated/cache findings

| Path | Size (local) | `.gitignore` | Verdict |
|---|---|---|---|
| `graphify-out/` | 213M | ✅ line 122 | ignored-OK, regenerable, must preserve locally (C3 evidence) |
| `.venv/` | 567M | ✅ `.venv/` | ignored-OK, runtime-required local |
| `runtime_artifacts/` | 155M | ✅ `/runtime_artifacts/` | ignored-OK, Docker-staging generated, never commit |
| `.fastf1_cache/` | 100M | ✅ `/.fastf1_cache/` | ignored-OK, local-only |
| `data/v2/` (+`data/raw/fastf1_cache`) | 109M (corpus) | ✅ `/data/v2/`, `/data/raw/fastf1_cache/` | ignored-OK, scientific corpus, must preserve |
| `frontend/.next` / `frontend/node_modules` | 249M / 489M | ✅ | ignored-OK |
| `__pycache__`, `.pytest_cache`, coverage | small | ✅ | ignored-OK |
| `.opencode/` (61M), `.impeccable/`, root `package.json`/`package-lock.json` | 61M+ | ❌ GAP (same as C0) | C3-B: add ignore entries and/or track verdict; NO C3-A edit |
| `.env` | 78 bytes | ✅ `.env`, `.env.*` | ignored-OK + live credential (see Security) |

No `.gitignore` gap beyond the C0-known tooling set. No cleanup performed
in C3-A (forbidden). Safe-local-cleanup candidates for C3-B: none
proposed beyond the tooling-ignore decision (all caches are either
runtime-required or expensive to rebuild).

## Developer tooling findings

Ponytail view alongside C0 evidence (no mutation; C3-B decides):

| Item | Ponytail view | Disposition input for C3-B |
|---|---|---|
| `.claude/` `D`×4, `.cursor/` `D`×4, `.gemini/settings.json` `D`, `.mcp.json` `D`, `.ignore` `D` (graft-era, tracked at HEAD) | `delete`: dead config, zero refs (`graft` absent from AGENTS/GEMINI/opencode.json) | REMOVE_TRACKED_TOOLING candidate (LOW risk; files already absent in worktree) + ignore successor |
| `AGENTS.md` `M`, `GEMINI.md` `M`, `opencode.json` `M` | keep: live agent policy + MCP config, no secrets | KEEP_REQUIRED (C3 ratifies worktree state) |
| `.opencode/` `??` 61M, `.impeccable/` `??`, root `package.json`/`package-lock.json` `??` | clutter: unignored local env | IGNORE_LOCAL_TOOLING (`.gitignore` gap fix) + shadcn-stub verdict (DEFER detail above) |
| `DESIGN.md` | `delete` candidate | UNCERTAIN → retain (see Unused files) |
| `.env` | out of Ponytail scope; recorded for hygiene | KEEP_LOCAL_IGNORED; rotation out-of-band |

## C1 retained-script verification

All 8 scripts re-checked (Ponytail finding or absence + known active ref
+ Graphify/search evidence). Ponytail raises **no flag** on any (all are
small CLI/test-imported utilities, not abstractions); independence holds
via exact search:

| Script | Ponytail flag | Known active reference (C1) | Re-verified this run | Audit status |
|---|---|---|---|---|
| `scripts/benchmark_phase4.py` | none | P4 freeze manifest `benchmark` + `test_frozen_module_hashes_match` | manifest + `tests/test_v2_phase5_r7.py` refs | RETAIN_REQUIRED |
| `scripts/benchmark_phase5_replay.py` | none | P5 freeze manifest `benchmark_files` + freeze/hash test | manifest + `test_v2_phase5_freeze.py`, `test_v2_phase8_e1.py` | RETAIN_REQUIRED |
| `scripts/build_phase9_evidence.py` | none | `evidence.test.ts` + `evidence.ts` + `run_ci_frontend_tests.py` + P9 manifest | `scripts/run_ci_frontend_tests.py`, `results/v2_validation/phase9_freeze_manifest.json`, `frontend/features/models/lib/evidence.ts` header cites it as generator | RETAIN_REQUIRED |
| `scripts/build_replay_prediction_cache.py` | none | 4 phase-8 test files + P5 freeze existence assertion | `test_v2_phase5_freeze/r3/e1_6/e4/e1`, `test_ci_contract`, `test_backend_container_contract` | RETAIN_REQUIRED |
| `scripts/build_simulation_parameters.py` | none | generator provenance in `raceintel/simulation/estimator.py` + `params.py` | provenance strings present post-C2 | RETAIN_REQUIRED |
| `scripts/capture_phase7_s1_baseline.py` | none | `test_v2_phase7_s1_phase6_compat.py` import + P6 drift JSON producer tag | test import + `tests/fixtures/phase7_s1_phase6_baseline.json` | RETAIN_REQUIRED |
| `scripts/run_p11_performance_benchmark.py` | none | `tests/test_p11_benchmark_script.py` import | test import + `results/v2_final_validation/p11_6_release_audit.json` | RETAIN_REQUIRED |
| `scripts/validate_phase6_simulation.py` | none | `test_v2_phase6_r7.py` + `test_v2_phase6_r71.py` imports | both test imports | RETAIN_REQUIRED |

Plus the 6 runtime/CI survivors (not C1-rescued but same risk class):
`prepare_runtime_artifacts.py` (Docker COPY + Makefile),
`check_runtime_environment.py` / `check_science_environment.py`
(Makefile/CI), `replay_feature_matrix.py` (imported by
`api/v2_explanation_service.py`, Docker-shipped),
`run_ci_tests.py` + `ci_corpus_dependent.txt` (CI, pin 3210),
`run_ci_frontend_tests.py` (CI) — all RETAIN_REQUIRED.

## Pickle compatibility verification

- Serving artifact `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`
  (17,401 bytes) embeds `v2.model_lab.preprocessing` **exactly once** and
  `raceintel` zero times (byte-level strings check this run).
- Shim (`v2/__init__.py`, `v2/model_lab/__init__.py`,
  `v2/model_lab/preprocessing.py`) re-exports `FittedPreprocessor` from
  `raceintel.model_lab.preprocessing`; documented "do NOT add code".
- All 30 legacy `results/models/*.pkl` remain sklearn-only per C2 (no new
  evidence; no reserialization performed or needed).
- Classification: serialization-required. **Shim deletion is not a C3-B
  action** (removal condition from C2 stands: only when no frozen artifact
  embeds `v2.*`).

## False positives

Explicit list (Ponytail said cut; independent evidence says keep):

1. `v2/` shim — pickle-required (byte proof).
2. `ml/` + legacy `api/` + `data/processed` + `data/interim` +
   `results/models` — production Docker + R2 suite (C0 V2_REQUIRED).
3. 24 transitive Python pins (`signalrcore`, `timple`, `RapidFuzz`,
   `PyJWT`, `cryptography`, `requests-cache`, `websockets`,
   `platformdirs`, `matplotlib` subtree ×7, requests subtree ×4,
   `cffi`/`pycparser`, `cattrs`/`attrs`/`msgpack`/`url-normalize`,
   `six`, `threadpoolctl`, `typing_extensions`, `dateutil`/`pytz`/
   `tzdata`, `python-multipart`, `tabulate`) — installed-dist
   `Requires-Dist` chains from fastf1/matplotlib/requests/pandas/
   sklearn/fastapi (each chain named above).
4. `api/` route modules + FastAPI-registered functions — framework
   registration convention.
5. `raceintel/model_lab/` module granularity — domain decomposition,
   suite-imported.
6. Dual stacks / config triple / `FEATURE_COLS` vs registry —
   intentional era separation, R2-pinned.
7. `tests/` layout + phase-frozen names + collection pin 3210 —
   regression contracts by design.
8. `results/v2_final_validation/`, `v2_validation/`, `data_quality/`,
   freeze manifests, fixtures — release/temporal evidence.
9. `motion` CSS substring hits (`prefers-reduced-motion`) — not package
   usage (the zero-import verdict stands; the CSS lines are not evidence
   for keeping, only noise to discard).

## Confirmed C3 candidates

**None.** No finding satisfies all 7 Part M gates. In particular:

- No dead code/file passes gates 2–7 (every flag has an active
  dependency, framework/serialization requirement, or test/build/CI/
  runtime owner).
- No dependency passes gate 6 (all Python pins are direct or
  transitive-required; the single frontend candidate `motion` lacks the
  removal-validation proof required to promote it from UNCERTAIN).
- No duplication passes gate 7 (all separations are frozen/provenance
  boundaries).

## Uncertain findings

(Retain by rule. Carried to C3-B with the stated validation.)

| # | Item | Why uncertain | C3-B validation to resolve |
|---|---|---|---|
| U1 | `motion` (frontend) | Zero source imports, but absence ≠ proof (dynamic/CDN/route-lazy edge) | Remove dep → `npm run build` + frontend tests + lockfile diff (LOW risk) |
| U2 | Root `package.json`/`package-lock.json` (shadcn stub) | No frontend refs, but shadcn may stay in workflow | Frontend-owner confirm; then track or remove-local + ignore |
| U3 | `DESIGN.md` | Loose but real refs (redesign plan, freeze manifest, globals.css) | Frontend-owner track-vs-ignore verdict; never content-delete |
| U4 | `data/sequences/`, `data/models/` (empty) | Zero refs, zero benefit to removal | Keep as placeholders (default); removal only with scaffold-owner OK |
| U5 | `tabulate` pin | Zero code refs but present in installed pandas/scipy dep metadata | Keep default; removal only with `pipdeptree` + Docker-rebuild proof |

## Security hygiene

- `LIVE_IGNORED_CREDENTIAL_PRESENT = true` (ignored `.env`, 78 bytes,
  present, untouched). `ROTATION_REQUIRED_OUT_OF_BAND` (unchanged since
  C0/C1). Value never read, printed, copied, archived, or manifested.
- Ponytail reported no credentials (out of its scope; recorded here for
  hygiene completeness). No secret values appear in this report.
- No secrets in tracked files (unchanged C0 position; no new tracked
  files created except this report + prior C-stage reports/records,
  all secret-free).

## Proposed C3-B action matrix

No destructive action is confirmed. Matrix for NEXT-stage review:

| # | Target | Proposed action | Evidence | Risk | Focused validation | Rollback source |
|---|---|---|---|---|---|---|
| A1 | `.opencode/`, `.impeccable/`, root `package.json`/`package-lock.json` | IGNORE_LOCAL_TOOLING (`.gitignore` entries) | Untracked+unignored; noisy status; C0 gap | LOW | Fresh-clone `git status` clean; opencode/shadcn still launch | v2-final + C0/C1/C2 worktree (revert `.gitignore` hunk) |
| A2 | Tracked graft-era tooling (`.claude/`×4D, `.cursor/`×4D, `.gemini/`×1D, `.mcp.json`D, `.ignore`D) | REMOVE_TRACKED_TOOLING | Zero refs; files already absent in worktree; graft retired | LOW | `make ci` green (tooling-only); status clean of graft paths | v2-final + C0/C1/C2 worktree (`git checkout v2-final -- <paths>`) |
| A3 | `AGENTS.md`, `GEMINI.md`, `opencode.json` (worktree mods) | KEEP_REQUIRED | Live agent policy; C0 disposition | — | None (ratify as-is) | — |
| A4 | `motion` frontend dep (U1) | DEFER (candidate REMOVE_CONFIRMED_DEPENDENCY only after proof) | Zero-import sweep | LOW | Remove → `npm run build` + FE tests + lock diff; else keep | `frontend/package.json` + lock from C2 worktree |
| A5 | Root shadcn stub (U2) | DEFER | No frontend refs | LOW | Owner confirm → track or remove-local | C2 worktree copy |
| A6 | `v2/` shim, `ml/`, legacy `api/`, R2 fixtures, freeze manifests, serving joblib | KEEP_COMPATIBILITY / KEEP_REQUIRED | Byte proof + Docker + R2 pins | — | None | — |
| A7 | `DESIGN.md`, `data/sequences/`, `data/models/` (U3/U4) | KEEP_HISTORICAL (default retain) | Provenance/placeholder | — | Owner verdict only | — |
| A8 | All 45 Python pins | KEEP_REQUIRED | Direct + transitive evidence above | — | None (no removal proposed) | — |
| A9 | Generated caches (graphify-out, .venv, runtime_artifacts, fastf1 caches, .next, node_modules, data/v2) | NO_ACTION (local-only; never commit) | Ignored-OK table | — | None | — |
| A10 | `.env` credential | NO_ACTION in-repo; rotation out-of-band | Ignored + live | — | Rotation verification outside repo | — |
| A11 | Duplication items (dual stacks, configs, narratives) | NO_ACTION (C4 owns narrative pointers) | Frozen boundaries | — | None in C3 | — |

Destructive actions proposed: **A2 only** (tracked graft-era tooling
removal + ignore), LOW risk, with explicit validation (`make ci`) and
rollback (`git checkout v2-final -- <paths>`). A1 is ignore-only (no
tracked deletion). A4/A5 are DEFERRED pending proof/owner.

## Validation requirements

- A1: fresh-clone `git status` clean of tooling noise; opencode/shadcn
  smoke (plugin loads, `shadcn --version` if stub tracked).
- A2: `make ci` green (ci-python collection still 3210 / 2480+4xfail;
  ci-frontend exit 0) + `git status` shows only intended `D` + ignore
  coverage for successors.
- A4 (if attempted): `npm run build` + frontend test suite + lockfile
  diff green, from a clean `npm ci`.
- A5 (if attempted): owner sign-off recorded in C3-B report.
- Global C3-B gates (unchanged): `make ci` + `preflight-source` green,
  scientific identities exact (6/6 per C1/C2 values), no dep removal
  without Docker-rebuild proof, PREEXISTING_OTHER_WORK respected except
  the explicitly approved A1/A2 set, C1 archive + external ZIP untouched,
  pickle load verified through serving path after any v2-adjacent change
  (none proposed).

## Ponytail trust summary

Totals: **53 normalized findings** (1 dead-code, 4 unused-file, 27
Python-dep-pin flags incl. matplotlib subtree, 1 frontend-dep, 4
duplication, 1 stale-config, 8 generated/cache, 10 tooling, 1 security).
Confirmed candidates **0** · false positives **31** · required-retain
**14** · uncertain **6** (U1–U5 incl. tabulate double-count note +
tooling set decided in C3-B).

Qualitative assessment (no single score):

- **USEFUL**: delegate-only wrapper lens surfaced the shim for explicit
  byte-proof (worth re-proving); `yagni` lens forced the config-triple
  and dual-stack rationale to be restated against C2; clutter lens
  re-confirmed the exact `.gitignore` gap set.
- **NOISY**: all 26 transitive-pin flags (no notion of frozen closure or
  native-extension consumers); framework-registered functions; CSS
  substring matches; `NotImplemented`/`fuzzy`-prose substring matches.
  Roughly 3 in 5 flags overturned by the first independent check.
- **INCOMPLETE**: no coverage awareness (per-function dead code
  unjudgeable — correctly left to C5-style gates); no pickle/registry/
  convention awareness (its highest-severity `delete` was the most
  load-bearing keep); no lockfile/closure reasoning for either
  ecosystem.

## C3-B handoff

C3-B may start on review approval of this report. Inputs: this audit +
C0/C1/C2 reports + both consolidation records. Scope: A1 (ignore gaps),
A2 (grafted tooling removal), U1/U2 proof-or-retain — nothing else.
Forbidden: shim/ml/legacy-api/dep removals beyond A4-with-proof,
structural renames, science changes, `.env` handling in-repo, C1-restore,
history rewrite. Budget note: full `make ci` ≈ 42–45 min; C3-B should
run it once after A1+A2 (+ once more if A4 attempted).

## Entry gate

- [x] HEAD still v2-final (`487f15d…`)
- [x] tag unchanged (`v2-final` points at HEAD)
- [x] nothing staged
- [x] all existing dirty paths classified
- [x] zero UNKNOWN before audit
- [x] C0/C1/C2 evidence read
- [x] Graphify refreshed (11419/27772/332)
- [x] installed Ponytail command identified (no binary; skill
  `@dietrichgebert/ponytail@4.10.0`, `ponytail-audit` lens)
- [x] no Ponytail install/upgrade performed
- [x] audit mode confirmed (one-shot, lists-only, no fixes)
- [x] no auto-fix enabled
- [x] Ponytail audit completed (whole-tree lens + sweeps)
- [x] findings normalized (10 categories)
- [x] active-source dead-code findings Graphify checked
- [x] dynamic references checked (importlib/`__import__`/`python -m`/subprocess/strings)
- [x] framework conventions considered (FastAPI, Next.js, pytest fixtures)
- [x] serialization references considered (byte-level joblib proof)
- [x] C1 retained scripts checked (8/8 + 6 runtime/CI survivors)
- [x] v2 pickle shim checked (byte proof + removal condition restated)
- [x] Python dependency findings challenged (45/45 with dist chains)
- [x] frontend dependency findings challenged (all + shadcn stub)
- [x] developer tooling findings assessed (10 items, no mutation)
- [x] generated/cache findings assessed (8 paths + gap set)
- [x] secrets sanitized (presence-only, never values)
- [x] every destructive candidate evidence-classified (only A2, LOW)
- [x] false positives explicitly recorded (9-item list)
- [x] UNCERTAIN retained (U1–U5)
- [x] C3-B action matrix produced (A1–A11 with risk/validation/rollback)
- [x] validation requirements attached to actions
- [x] no cleanup implemented
- [x] no dependency removed
- [x] no file deleted/moved/renamed
- [x] no .gitignore edit
- [x] PREEXISTING_OTHER_WORK untouched
- [x] only C3-A report created
- [x] nothing staged
- [x] nothing committed
- [x] nothing tagged
- [x] nothing pushed
- [x] C3-B not started
