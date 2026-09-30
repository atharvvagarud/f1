# PHASE 10 P10-1B RUNTIME VERSION + BOOTSTRAP CONTRACT

No Dockerfiles, compose files, CI workflows, readiness endpoints, or
observability middleware were created. No scientific behavior, model,
feature, RaceState, simulation, strategy, or replay code was changed. No
dependency version was upgraded. This stage is runtime reproducibility
only.

## Final verdict

P10-1B COMPLETE — READY FOR P10-1C. Python 3.11 and Node 22 contracts are
established and validated by real installs (not by README prose):
requirements.txt installs cleanly under Python 3.11.15, the frozen serving
joblib deserializes through the existing safe path with SHA identity
intact, `npm ci` + node tests + typecheck + lint + production build are
green under Node v22.23.1 / npm 10.9.8, and SOURCE/DEPLOYABLE preflight
plus a Makefile bootstrap surface are implemented and green.

## Frozen baseline

- HEAD: `440f2a370aff56c799e69b65781199b158064fa0`
  (`440f2a3 feat(v2): freeze models and about phase 9`)
- Tag on HEAD: `v2-models-about-phase9` — matches.
- Phase 1–9: FROZEN (unchanged by this stage; verified by SHA identity of
  the frozen serving artifact, see below).

## Repository safety

- `git log -1 --oneline`: `440f2a3 feat(v2): freeze models and about
  phase 9`; `git tag --points-at HEAD`: `v2-models-about-phase9`.
- `git diff --cached --stat`: empty — nothing staged at start or end.
- Pre-existing dirty paths (tooling-only deletions/modifications,
  PREEXISTING_OTHER_WORK per P10-0) preserved untouched; no path under
  `api/`, `ml/`, `v2/`, `data/` (tracked), `results/` (tracked),
  `frontend/` (tracked app files), or `tests/` (existing) was modified
  except the owned additions listed below.
- P10-0/P10-1A uncommitted work preserved:
  `docs/PHASE10_P10_0_PRODUCTION_READINESS_AUDIT.md`,
  `docs/PHASE10_P10_1A_RUNTIME_ARTIFACT_CONTRACT.md`,
  `scripts/prepare_runtime_artifacts.py`,
  `tests/test_runtime_artifact_packaging.py`, `.gitignore`
  `runtime_artifacts` entry — all still present and uncommitted.
- `runtime_artifacts/` remains gitignored (`git check-ignore` confirms)
  and untracked.
- `graphify update .` succeeded (graph rebuilt: 11171 nodes, 28052
  edges); graphify used for entry/dependency orientation only.

## Python runtime contract

- Canonical: **Python 3.11.x** (validated on 3.11.15), Docker base family
  `python:3.11-slim` (declared for P10-1C; no Dockerfile created here).
- Chosen by validation, not by prose: the full `requirements.txt` pin set
  (45 packages, incl. `numpy==2.4.2`, `pandas==2.3.3`,
  `scikit-learn==1.8.0`, `xgboost==3.2.0`, `pyarrow`, `fastf1`, `joblib`)
  installs cleanly under Python 3.11.15 in an isolated venv, and the
  frozen serving joblib deserializes through the existing safe loader
  under that environment (Part: Frozen model deserialization).
- System `python3` on this machine is 3.14.7 with no third-party packages;
  it is explicitly NOT supported. The preflight fails closed on it with
  an actionable message (verified: `unsupported Python 3.14`).
- Declaration: `.python-version` contains `3.11` (informational/
  contractual; no version-manager dependency introduced).

## Python dependency installation

- Production: `python -m pip install -r requirements.txt`
- Development/test: `python -m pip install -r requirements.txt
  -r requirements-test.txt`
- No versions changed (`git diff` on both files is empty).
- Validated in a disposable venv (`/tmp/p10-1b-py311`, outside the repo,
  system Python uncontaminated): all 45 production pins installed
  (`Successfully installed … fastapi-0.135.1 … scikit-learn-1.8.0 …
  xgboost-3.2.0 …`), then `pytest==9.1.1` + `httpx==0.28.1` installed
  from `requirements-test.txt`.
- Freeze spot-check in that env: `fastapi==0.135.1`,
  `uvicorn==0.41.0`, `numpy==2.4.2`, `pandas==2.3.3`,
  `pyarrow==25.0.1`, `scikit-learn==1.8.0`, `joblib==1.5.3`,
  `xgboost==3.2.0`, `fastf1==3.7.0`.

## Frozen model deserialization

- Artifact: `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`,
  SHA `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
  — matches the expected identity exactly (before and after this stage).
- Under Python 3.11.15 + exact pins, `load_frozen_winner_model()`
  (existing safe path in `v2/model_lab/serving.py`) constructs a
  `FrozenWinnerPredictor`; `describe_serving_artifact()` reports the same
  SHA plus frozen anchors (`C=0.01 lbfgs`, `INDEPENDENT_BINARY`,
  training seasons 2018–2024). Identity only: no predictions, no
  evaluation, no fitting, no transforms, no retraining.
- The preflight itself does NOT load the model; it verifies SHA identity
  by hashing (17 KB file).

## Node runtime contract

- Canonical: **Node 22 LTS** (`>=22 <23`), npm canonical.
- Validated on Node v22.23.1 / npm 10.9.8 (machine default `node`
  already satisfies the contract; no toolchain install was needed).
- Against: `frontend/package.json` + `frontend/package-lock.json`
  (lockfileVersion 3, 434 packages), Next 16.1.6, React 19.2.3,
  TypeScript, ESLint, `node:test` — all install and pass (see Test
  evidence).
- Package manager unchanged: npm only; no pnpm/yarn artifacts; root
  `package.json`/`package-lock.json` remain PREEXISTING_OTHER_WORK,
  untouched, never part of bootstrap (not installed, not copied).

## npm contract

- Canonical install: `cd frontend && npm ci` (never `npm install` for
  CI/container bootstrap).
- Validated twice from a real `npm ci`: 365 packages installed; second
  run (after the engines addition) completed in 6 s with the lockfile
  byte-identical afterwards — deterministic.
- No dependency version changed. `npm install --package-lock-only` was
  trialled to mirror the new `engines` field into the lockfile but
  produced unrelated re-resolution churn (added nested optional
  `@tailwindcss/oxide`/`@emnapi` entries); per the engines-only policy
  that churn was rejected and the lockfile reverted. `npm ci` provably
  does not require the engines mirror.

## Version declarations

- `.python-version`: `3.11` (new, tracked).
- `frontend/.nvmrc`: `22` (new, tracked).
- `frontend/package.json`: `engines: { node: ">=22 <23" }` (only diff to
  that file; no dependency touched).
- `frontend/package-lock.json`: unchanged (see npm contract).
- No pyenv/nvm/asdf/Volta dependency; files are informational/
  contractual for developers, CI, and future Docker builds.

## Backend production command

- Canonical: `python -m uvicorn api.main:app --host 0.0.0.0 --port 8000`
  (no `--reload`, single process; worker/concurrency choices deferred —
  heavy synchronous simulation/strategy semantics make them
  operationally meaningful, out of scope here).
- Working directory: repository root (or anywhere with
  `V2_PROJECT_ROOT` set); artifact precondition: DEPLOYABLE tree
  (`make preflight` green).
- Proven live: the exact command shape (port 8123 to avoid the dev port)
  booted under Python 3.11.15 + exact pins and `GET /health` returned
  `{"status":"ok"}`; server then stopped. No API code changed.
- Makefile: `make backend-prod` (existing `backend-dev` with `--reload`
  preserved untouched).

## Frontend production lifecycle

- Canonical: `cd frontend && npm ci && npm run build && npm start`.
- Proven: `npm run build` green (`Compiled successfully`, all 7 routes
  prerendered static incl. `/models`, `/about`); `npm start` is Next's
  canonical server, wired as `make frontend-start`.
- Contract (from P10-0 evidence, unchanged): port 3000;
  `NEXT_PUBLIC_API_BASE` required at BUILD time (client-inlined,
  localhost fallback otherwise); build needs no backend; `/models` and
  `/about` are static; dynamic pages need the backend at browser
  runtime. Runtime-config architecture explicitly NOT solved here
  (P10-1D).

## Environment variables

| Variable | Dev default | Container/prod expectation | Time | Required? |
|---|---|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `http://127.0.0.1:8000` fallback | set at frontend BUILD time to reachable backend URL | build | effectively required beyond localhost |
| `V2_PROJECT_ROOT` | cwd walk-up discovery | set explicitly (robustness; not strictly required if workdir = repo root) | runtime | optional |
| `V2_ALLOW_NETWORK` | off unless `=1` | must remain UNSET (≠1) | runtime | must be OFF for serving |

No new variables added; no speculative variables. Consumers unchanged:
`frontend/lib/api.ts`, `frontend/lib/v2.ts`, `v2/config.py`,
`v2/jolpica.py`, `v2/tiera.py`, `v2/cli.py`.

## CORS handoff

- Current: `CORSMiddleware, allow_origins=["*"]` (`api/main.py:45`) —
  dev configuration, NOT changed (implementation explicitly deferred).
- P10-1E local Compose may operate under current wildcard behavior.
- P10-3 requirement recorded: allowed origins must become
  environment-driven with a strict/same-origin default; expected future
  variable (name TBD in P10-3, e.g. backend-origins allow-list). Do not
  just widen.

## Source-tree preflight

- `scripts/check_runtime_environment.py --source` (stdlib-only):
  supported Python 3.11 check, tracked serving-model existence + SHA,
  Phase-9 evidence JSONs, V1 resources (`data/processed`,
  `data/interim`, `results/models`), frontend manifest + lockfile.
- Never installs, serves, downloads, regenerates, loads datasets, or
  runs inference.

## Deployable-tree preflight

- Default mode (`--deployable`, also `make preflight`): SOURCE checks
  plus `runtime_artifacts/` + `manifest.json` presence, manifest-version
  gate (`runtime-artifacts-v1`), reuse of
  `scripts/prepare_runtime_artifacts.py --validate --root <root>` via
  subprocess (no shell, no cwd assumption, 300 s cap, fail closed with
  the validator's tail output), and the network-off gate
  (`V2_ALLOW_NETWORK=1` → FAIL).
- Verified green on the real tree in both modes (under Python 3.11);
  verified FAIL with `V2_ALLOW_NETWORK=1`, and FAIL with an actionable
  message under system Python 3.14.

## Makefile command surface

Added (existing targets byte-identical, verified by diff):

| Target | Command |
|---|---|
| `install-python` | `python -m pip install -r requirements.txt` |
| `install-python-test` | `python -m pip install -r requirements.txt -r requirements-test.txt` |
| `install-frontend` | `cd frontend && npm ci` |
| `install` | `install-python install-frontend` |
| `preflight` | `python scripts/check_runtime_environment.py --deployable` |
| `preflight-source` | `python scripts/check_runtime_environment.py --source` |
| `backend-prod` | `python -m uvicorn api.main:app --host 0.0.0.0 --port 8000` |
| `frontend-start` | `cd frontend && npm start` |

No Docker targets (per non-goals). `make install` never sudo/OS-packages/
generates-science/downloads-data/prepares-caches/touches-env-files/starts-
services; users activate their Python 3.11 environment first (documented
in the Makefile header). `make preflight` and `make preflight-source`
exercised green.

## Developer bootstrap

```bash
git clone <repo>; cd <repo>
python3.11 -m venv .venv && source .venv/bin/activate   # 3.11 required
make install-python-test                                 # exact pins + pytest
make preflight-source                                    # tracked-tree gate
cd frontend && npm ci && npm run dev                     # frontend dev
python -m uvicorn api.main:app --port 8000               # backend dev (or make backend-dev)
```

## Deployable bootstrap

```bash
make install                 # prod Python pins + npm ci (3.11 env active)
python scripts/prepare_runtime_artifacts.py   # stage runtime bundle (P10-1A)
make preflight               # DEPLOYABLE gate incl. validator + network-off
make backend-prod            # :8000 (terminal 1)
cd frontend && npm run build && npm start     # :3000 (terminal 2, NEXT_PUBLIC_API_BASE set at build time)
```

## Local env safety

- Root `.env` → ignored by `.gitignore:13` (`.env`); `frontend/.env.local`
  → ignored by `frontend/.gitignore:34` (`.env*`). Verified via
  `git check-ignore -v` (no file contents read, printed, or copied).
- Neither file was modified; no test/log/report contains secret content
  (new tests use synthetic tmp dirs; the only real-tree reads are the
  17 KB model SHA and JSON manifest/version files).

## Network-off serving contract

- `V2_ALLOW_NETWORK` remains default-off in all serving code (ingestion
  CLIs only); no serving/bootstrap path sets it to `1` (verified by
  code inspection of consumers; no ingestion semantics altered).
- DEPLOYABLE preflight fails closed if `V2_ALLOW_NETWORK=1` is exported
  (verified live).

## Test evidence

| Gate | Result |
|---|---|
| Isolated Python 3.11.15 `pip install -r requirements.txt` | clean, 45 pins |
| `pip install -r requirements-test.txt` | `pytest==9.1.1`, `httpx==0.28.1` |
| Frozen model `load_frozen_winner_model()` + SHA | loads; SHA `1116b34f…fcaa59f4` matches |
| `tests/test_runtime_environment.py` (22 tests) + P10-1A packaging (12) | 34 passed |
| `py_compile` new/owned scripts | OK |
| `npm ci` (×2, incl. post-engines) | 365 packages, lockfile untouched |
| `node --test` (frontend) | 197 passed, 0 failed |
| `tsc --noEmit -p .` | clean |
| `npm run lint` | clean |
| `npm run build` | `Compiled successfully`, 7 routes static |
| `prepare_runtime_artifacts.py --validate` | VALID, 1939 files / 157,647,360 bytes |
| `preflight --source` / `--deployable` (py3.11) | both OK |
| `V2_ALLOW_NETWORK=1` deployable | FAIL as designed |
| System Python 3.14 preflight | FAIL with actionable 3.11 message |
| Production uvicorn boot + `GET /health` | `{"status":"ok"}` |
| Full ~1,500-test scientific suite | NOT run (per scope; shared-file changes: none — Makefile/package.json/preflight/tests are outside scientific imports) |

## Scientific firewall

- `scripts/check_runtime_environment.py`: stdlib only (`argparse`,
  `hashlib`, `json`, `os`, `subprocess`, `sys`, `pathlib`) — enforced by
  `test_preflight_imports_stdlib_only` (import allowlist over the file).
  It hashes, reads JSON, checks paths, and delegates science-adjacent
  validation to the P10-1A script; the sole model interaction in this
  stage was the manual one-time deserialization check above.
- `tests/test_runtime_environment.py`: synthetic tmp fixtures; only
  real-tree reads are the model SHA (identity guard) and
  `.python-version`/`.nvmrc`/`package.json` declarations.
- No training/feature/matrix/simulation/replay/FastF1/explainability
  imports added anywhere; no artifact regenerated; no retraining.

## Known limitations

- Validation ran on macOS (Apple silicon), not Linux; `python:3.11-slim`
  equivalence for P10-1C rests on the 3.11 language line + exact wheel
  pins, to be confirmed by the container build.
- Disposable venv and npm cache live outside the repo (`/tmp`,
  `~/Library/Caches`); the repo contains no venv, no `node_modules`
  additions to tracked files.
- `npm ci` re-resolution churn (nested optional entries) was observed
  with npm 10.9.8 and deliberately rejected; if a future npm refuses the
  current lock, P10-1C/1D must re-evaluate rather than silently accept
  churn.
- Full scientific suite and D11 not run (out of scope; documented above).

## P10-1C handoff

Backend-container assumptions now fixed: base `python:3.11-slim`;
install `python -m pip install -r requirements.txt` (exact pins, no
test file); workdir = staged root (or set `V2_PROJECT_ROOT`); start
`python -m uvicorn api.main:app --host 0.0.0.0 --port 8000` single
process; bake tracked files + P10-1A `runtime_artifacts/` content (or
regenerate-then-validate in-build); `V2_ALLOW_NETWORK` unset; `/health`
= liveness only (readiness is P10-3); no FastF1 cache writes on the
serving path.

## Entry gate

- [x] Python runtime contract established (3.11.x, validated 3.11.15)
- [x] Python 3.11 compatibility validated with evidence (isolated venv,
  real install + deserialization)
- [x] exact Python dependency install contract established (prod/dev
  split, pins untouched)
- [x] frozen serving model deserializes under chosen environment
- [x] model identity unchanged (`1116b34f…fcaa59f4`)
- [x] Node runtime contract established (`>=22 <23`, validated
  v22.23.1)
- [x] npm remains canonical (`npm ci` validated twice)
- [x] frontend dependencies unchanged (lockfile byte-identical)
- [x] runtime declarations added (`.python-version`,
  `frontend/.nvmrc`, `engines`)
- [x] backend production command established + boot-proven
- [x] frontend production lifecycle established + build-proven
- [x] environment-variable contract established (no new variables)
- [x] `V2_ALLOW_NETWORK` production behavior remains off + gated
- [x] CORS implementation explicitly deferred/handoff documented
- [x] SOURCE preflight implemented
- [x] DEPLOYABLE preflight implemented
- [x] P10-1A validator reused, not duplicated
- [x] Makefile bootstrap targets implemented
- [x] existing Make targets preserved
- [x] no scientific artifact regeneration
- [x] local env/secret files untouched
- [x] focused environment tests green (22 new)
- [x] P10-1A tests remain green (12)
- [x] frontend node tests green (197)
- [x] TypeScript green
- [x] ESLint green
- [x] Next production build green
- [x] runtime_artifacts validation green (1939 files / 157,647,360 B)
- [x] source preflight green
- [x] deployable preflight green
- [x] scientific firewall green
- [x] no application/scientific behavior changed
- [x] unrelated work untouched
- [x] nothing staged/committed/tagged
- [x] P10-1C backend-container assumptions explicit
