# PHASE 10 P10-0 PRODUCTION READINESS AUDIT

Read-only audit. No application/scientific code was modified. No Docker, CI,
or config implementation was started. All facts below were established by
direct repository inspection on the audit date (measured sizes/hashes are
machine-local and will differ where generated artifacts are concerned).

## Final verdict

P10-0 COMPLETE — READY FOR P10-1. The runtime topology, startup paths,
dependency sources, environment inventory, artifact ownership, and bootstrap
gaps are all determined from repository evidence. No blocking unknown remains;
the blockers for a clean clone are enumerated exactly.

## Frozen baseline

- HEAD: `440f2a3 feat(v2): freeze models and about phase 9`
- Full SHA: `440f2a370aff56c799e69b65781199b158064fa0` — matches the required commit.
- Tag on HEAD: `v2-models-about-phase9` — matches.
- Frozen: Phase 1–9 per the mission statement. This audit did not re-verify
  frozen scientific semantics; it used them only to determine runtime needs.

## Repository safety

`git status --short` (abridged):

- Deleted, unstaged (tooling only): `.claude/helpers/*`, `.claude/settings.json`,
  `.claude/skills/graft/SKILL.md`, `.cursor/hooks.json`,
  `.cursor/hooks/graft-hooks.cjs`, `.cursor/mcp.json`,
  `.cursor/rules/graft.mdc`, `.gemini/settings.json`, `.ignore`, `.mcp.json`.
- Modified, unstaged: `AGENTS.md`, `GEMINI.md`, `opencode.json`.
- Untracked: `.impeccable/`, `.opencode/`, `package.json`, `package-lock.json`.
- `git diff --cached --stat`: empty — nothing is staged.
- `git diff --stat`: 14 files, 38 insertions, 620 deletions (tooling/config only).

Classification of every dirty path:

| Path | Class |
|---|---|
| `.claude/`, `.cursor/`, `.gemini/`, `.ignore`, `.mcp.json` deletions | PREEXISTING_OTHER_WORK |
| `AGENTS.md`, `GEMINI.md`, `opencode.json` modifications | PREEXISTING_OTHER_WORK |
| `.impeccable/`, `.opencode/`, root `package.json`, root `package-lock.json` | PREEXISTING_OTHER_WORK |
| `GENERATED_IGNORED` / `UNKNOWN` dirty paths | none found |

No dirty path touches `api/`, `ml/`, `v2/`, `frontend/` (tracked files),
`data/` (tracked files), `results/` (tracked files), `tests/`, `Makefile`,
`requirements*.txt`, or `docs/`. Nothing was staged, committed, tagged,
restored, or cleaned. The only new file created by this audit is this document
(left uncommitted per instructions).

## Graphify-first navigation

Attempted first per policy: `graphify update .` failed —
`command not found: graphify` (no graphify CLI on this machine), although
`graphify-out/` exists (regenerable local output, gitignored per
`.gitignore:119-122`). Fallback used throughout: targeted `Read`/`Glob`/`Grep`
for entry points, services, and path resolution; `git`/`du`/`sha256sum` for
artifact state. No broad directory dumps were relied on for conclusions.
P10-1 should not assume a graphify CLI exists in clean/CI environments.

## Runtime topology

Actual architecture as it runs today (evidence-backed, not the example copied):

```text
Browser
  ├── Next.js 16.1.6 static/CSR pages (/, /replay, /simulator, /strategy)
  │     fetch at request time (cache: no-store) → FastAPI
  ├── Next.js /models + /about — ZERO backend dependency
  │     (compile-time import of frontend/data/*.v1.json, validated)
  ↓  HTTP JSON, base = NEXT_PUBLIC_API_BASE or http://127.0.0.1:8000
FastAPI (api/main.py:app), lazy per-process singletons
  ├── V1 legacy: ml/inference over data/processed CSVs + results/models pickles
  ├── V2 factual: canonical Parquet (data/v2/processed) → RaceStateReconstructor
  ├── V2 prediction: frozen serving joblib → RacePredictionEngine
  ├── V2 replay/explain: read-only replay cache (results/v2_replay/checkpoints)
  ├── V2 simulation: MonteCarloEngine + frozen params (data/v2/simulation/params)
  └── V2 strategy: Strategy Engine over the same simulation stack
```

Per-component record:

| Component | Entry | Runtime | Startup command today | FS resources | Env | Network | Writes |
|---|---|---|---|---|---|---|---|
| Frontend dev | `frontend/package.json:dev` | Node + Next | `cd frontend && npm run dev` (`make frontend-dev`) | `frontend/` + `node_modules` | `NEXT_PUBLIC_API_BASE` (build-time inlined for client) | backend at API_BASE | `.next/` |
| Frontend prod | `frontend/package.json:start` | Node + Next | `cd frontend && npm start` (after `npm run build`) | `.next/` build output | same | same | none at runtime |
| Backend dev | `api/main.py:app` | Python + uvicorn + FastAPI | `python3 -m uvicorn api.main:app --reload --port 8000` (`make backend-dev`) | repo root (see artifact inventory) | `V2_PROJECT_ROOT` (optional), `V2_ALLOW_NETWORK` (ingestion only, default off) | none at serving time | none on serving path (see writes audit) |
| Scientific runtime | `v2/*`, `ml/*` imported in-process | same Python process | lazy: first request per service (`lru_cache` singletons) | Parquet + joblib + caches (Part I) | same | none (network sealed unless `V2_ALLOW_NETWORK=1` for ingestion CLIs only) | none on serving path |
| Static evidence | `frontend/data/models.v1.json`, `about.v1.json` | bundled at Next build | none (import-time) | tracked JSON in repo | none | none | none |

No database, worker, queue, or external cache service exists or is needed:
simulation/strategy run synchronously in-process with documented caps
(10k simulations; strategy min 100), and the replay path is explicitly
read-only by construction (`api/v2_replay_service.py:13-19`).

## Backend startup

- Canonical app object: `app` in `api/main.py:25` (`FastAPI(title="F1 Race
  Winner Predictor API")`), routers from `api/routes.py` (V1) plus six V2
  routers (replay, explanation, timeline-explanation, simulation, strategy,
  core V2). Verified route inventory in Part P.
- Module path: `api.main:app`. Working directory assumption: repository root
  (all services resolve `_REPO_ROOT = Path(__file__).resolve().parents[1]`;
  V2 resolves root via `V2_PROJECT_ROOT` env → else walk-up discovery from
  `Path.cwd()` requiring `v2/` + `data/` dirs — `v2/config.py:30-78`). So the
  backend starts from the repo root, OR from anywhere with `V2_PROJECT_ROOT`
  set. It does NOT depend on `PYTHONPATH` (no evidence of such a requirement;
  imports are top-level `api.*`/`v2.*`/`ml.*` packages).
- Host/port: uvicorn defaults (127.0.0.1:8000 in practice); `make backend-dev`
  passes only `--port 8000` plus `--reload --reload-dir api --reload-dir ml`.
  `--reload` and the reload dirs are dev-only assumptions that must not carry
  into production.
- Critical lazy-loading property: all V2 services are `functools.lru_cache`
  process-local singletons built on first request (`api/v2_service.py:177-184`
  and equivalents in replay/explanation/timeline/simulation/strategy
  services). **Import of `api.main` succeeds with zero artifacts present;
  failures (missing Parquet, missing joblib, missing cache) surface on first
  request, not at startup.** This is the liveness/readiness gap (Part Q).
- Environment reliance: current shell's Python + installed pins; no undeclared
  env vars on the serving path (only `V2_PROJECT_ROOT` optional). No absolute
  paths in serving code (all `__file__`-relative or root-resolved).
- Lightweight verification limit: `python3 -c "import api.main"` could NOT run
  here — system `python3` is 3.14.7 with no third-party packages
  (`ModuleNotFoundError: No module named 'fastapi'`). This itself confirms the
  clean-clone finding: backend startup requires creating an environment and
  installing `requirements.txt` first. No venv exists in the repo.

## Frontend startup

- Node assumptions: README says Node.js 22 + npm; **no `engines` field in
  `frontend/package.json`**; local machine runs Node v23.11.0 / npm 11.17.0.
  Unpinned `engines` is a SHOULD_FIX for P10-1 (pin what CI/Docker validate).
- Package manager: npm (`frontend/package-lock.json`, lockfileVersion 3,
  434 packages). No pnpm/yarn artifacts.
- Versions: `next 16.1.6` (exact), `react`/`react-dom 19.2.3` (exact),
  `eslint-config-next 16.1.6`; caret ranges on `lucide-react`, `motion`,
  tailwind/types/eslint/typescript devDeps.
- Scripts (`frontend/package.json:5-10`): `dev` (`next dev`), `build`
  (`next build`), `start` (`next start`), `lint` (`eslint`). Plus Makefile
  `typecheck` (`./node_modules/.bin/tsc --noEmit -p .`, needs `npm install`
  first) and `test-frontend` (`node --test` from `frontend/`).
- Backend URL handling: `frontend/lib/api.ts:1` and `frontend/lib/v2.ts:11-12`
  both do `process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000"`.
  `.env.example` documents the variable; `frontend/.env.local` (untracked,
  gitignored) currently sets it to `http://127.0.0.1:8000`. Consequence:
  **the default production build bakes in `127.0.0.1:8000`** unless the
  variable is set at build time (`NEXT_PUBLIC_*` is inlined by Next). Any
  Docker/future-deploy design must set `NEXT_PUBLIC_API_BASE` at image build
  (or refactor to runtime config in P10-1/P10-3 — audit only notes it).
- Client/server: all backend calls use `cache: "no-store"` runtime fetch;
  `/models` and `/about` are fully static (compile-time JSON import +
  validation, "No fetching, no spinners" per `app/models/page.tsx`). So
  `next build` needs NO running backend — verified by code (no
  `generateStaticParams`/server fetch of the API in app pages; replay,
  simulator, strategy pages fetch client-side through `lib/v2.ts`).
- CORS implication: browser → API is cross-origin in dev
  (`localhost:3000` → `127.0.0.1:8000`); backend currently allows all origins
  (Part R).

## Python dependencies

- Canonical source: `requirements.txt` (45 packages, **all `==` pinned**,
  incl. `fastapi==0.135.1`, `uvicorn==0.41.0`, `scikit-learn==1.8.0`,
  `xgboost==3.2.0`, `pyarrow`, `pandas`, `numpy`, `fastf1`, `joblib`).
  Test-only: `requirements-test.txt` (`pytest==9.1.1`, `httpx==0.28.1`),
  cleanly separated with an explicit install line. No `pyproject.toml`,
  `setup.py`, `setup.cfg`, or Python lockfile beyond the pinned requirements.
- Canonical install command today: `pip install -r requirements.txt
  -r requirements-test.txt` (README + Makefile `test-python` assumes it).
- No `Makefile` install target exists (setup gap for P10-1).
- No virtualenv in repo; no Python version pin anywhere (README prose says
  3.11; local interpreter is 3.14 — drift risk: pinned `numpy==2.4.2` /
  `pandas==2.3.3` / `scipy` wheels and `scikit-learn==1.8.0` unpickle
  compatibility are version-sensitive; P10-1 must choose and freeze one
  interpreter).
- Unused/obsolete: not fully provable read-only, but the serving path imports
  only fastapi/uvicorn/pandas/numpy/pyarrow/joblib/sklearn (+ scipy via
  sklearn) — while `requirements.txt` also ships `fastf1`, `matplotlib`,
  `signalrcore`, `xgboost`, `tabulate`, `timple`, `requests-cache`, etc.,
  needed by ingestion/research/V1 paths. A slim production requirements set is
  a P10-1 SHOULD_FIX, not a blocker. No import-without-declaration was found
  on the serving path (all serving imports resolve to declared pins).
- Classification: missing interpreter pin + missing install target =
  SHOULD_FIX (P10-1); no BLOCKER (pins themselves are complete and exact).

## Node dependencies

- Source: `frontend/package.json` + `frontend/package-lock.json`
  (lockfileVersion 3, 434 packages) — canonical and consistent.
- Prod deps (5): `lucide-react`, `motion`, `next`, `react`, `react-dom`.
  Dev deps (7): tailwind/postcss, node/react types, eslint + config-next,
  typescript. Scripts cover dev/build/start/lint; typecheck and node:test run
  via binaries (`tsc`, `node --test`) after `npm install`.
- Root `package.json` / `package-lock.json`: **PREEXISTING_OTHER_WORK /
  tooling-only** — root manifest contains solely `devDependencies.shadcn`
  (`^4.21.0`); no application code imports it, no Makefile/README references
  it, frontend build does not depend on it. P10-1 must NOT install it, must
  NOT copy it into any image, and must leave both files untouched.
- No `engines` declaration (see Part D); lockfile present and should be
  installed with `npm ci` in Docker/CI.

## Environment variables

Complete inventory from application-owned code search:

| Variable | Consumer | Required? | Default | Prod requirement |
|---|---|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `frontend/lib/api.ts:1`, `frontend/lib/v2.ts:11-12` | optional in code, effectively required for any non-localhost deploy | `http://127.0.0.1:8000` | must be set at BUILD time to the reachable backend URL (baked into client bundle) |
| `V2_PROJECT_ROOT` | `v2/config.py:18,75-77` | optional | cwd walk-up discovery | set explicitly in containers (robustness, not strictly required if workdir = repo root) |
| `V2_ALLOW_NETWORK` | `v2/jolpica.py:58,241`, `v2/tiera.py:64,693`, `v2/cli.py:155` | optional, default OFF | anything other than `"1"` = offline | must remain UNSET (or ≠1) in production; ingestion-only opt-in |

Findings: no `.env.example` at repo root; `frontend/.env.example` documents
only `NEXT_PUBLIC_API_BASE`. No documented-but-unused variables. No secrets in
tracked code (secret-pattern grep over `api/` clean). Unsafe defaults: the
`127.0.0.1:8000` fallback is a localhost trap for any containerized/staged
deploy (P10-1/P10-3 must make the effective API base explicit and visible).
No new variables are introduced by this audit.

## Filesystem/path assumptions

Serving-path path handling is disciplined: `api/*_service.py` files resolve
`_REPO_ROOT = Path(__file__).resolve().parents[1]`; V2 ingestion/config code
derives everything from an explicit root (`v2/config.py`). No absolute
personal paths in serving code. Runtime-relevant relative paths:

| Path | Owner | Class |
|---|---|---|
| `data/v2/processed/**` (canonical Parquet incl. `driver_lap_state_d9`, `results`, `races`, model matrix) | V2 serving corpus | GENERATED_REPRODUCIBLE, runtime-REQUIRED, ignored |
| `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib` | frozen winner | SOURCE_CONTROLLED (tracked), runtime-REQUIRED |
| `results/v2_replay/checkpoints/*.json` (149) + manifests | replay cache | GENERATED_REQUIRED (ignored), runtime-REQUIRED for prediction/explanation endpoints |
| `results/v2_explainability/global_winner_logreg_v1.json` | global explanation | GENERATED_REQUIRED (ignored), runtime-required by explanation endpoints |
| `data/v2/simulation/params/r3-v1__through-2024` | sim/strategy params | GENERATED_REQUIRED (ignored), runtime-REQUIRED for sim/strategy |
| `data/processed/**`, `data/interim/**` (V1 CSVs) | V1 serving | SOURCE_CONTROLLED (tracked), runtime-required for V1 endpoints |
| `results/models/**` (V1 pickles) | V1 serving | SOURCE_CONTROLLED (tracked), runtime-required for V1 endpoints |
| `frontend/data/*.v1.json` | Phase-9 evidence | SOURCE_CONTROLLED (tracked), build-time bundled |
| `data/raw/fastf1_cache/` + `.fastf1_cache/` | FastF1 HTTP cache | OPTIONAL_CACHE / local-only source infra, NOT runtime-required for serving |
| `data/raw/` 15G blobs | ingestion source | DEVELOPMENT_ONLY / research; must NEVER enter build context |
| `data/v2/model_lab/`, `reports/`, `results/analysis`, `results/baselines`, `comparisons`, `debug`, `v2_validation` | research outputs | REQUIRED ONLY FOR RESEARCH |
| `frontend/.next/`, `node_modules/`, `__pycache__/`, `.pytest_cache/` | build/test byproducts | DEVELOPMENT_ONLY / generated |

Container must contain: repo root checkout (tracked files) + the five
GENERATED_REQUIRED runtime inputs (or a bootstrap step that creates them —
Parts L/M/N). `configure_fastf1_cache` (`v2/config.py:92-104`) mkdirs the
cache dir on use, so any path passed to it must be writable (or the call must
never happen on the serving path — it does not today).

## Runtime artifact inventory

| Artifact | Size (local) | Tracked? | Required by | Reproduction | Absent behavior |
|---|---|---|---|---|---|
| `data/v2/processed/` Parquet corpus (+ model matrix) | 109 MB (`data/v2` total) | ignored / generated | ALL V2 endpoints (states/results/races load in `load_v2_service`) | `python -m v2.d6/d7/d9 --all --validate` + `python -m v2.features.build_matrix` (offline; full rich rebuild needs network + long time) | `RuntimeError: no canonical rows for entity …` on first V2 request |
| `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib` | 17,401 B, sha256 `1116b34f…fcaa59f4` | TRACKED (`git ls-files` confirms) | winner prediction, replay predictions, explanations, sim adaptation | `materialize_serving_artifact` (frozen M9 path, `v2/model_lab/serving.py:335`) | serving-artifact validation error on first prediction request |
| `results/v2_replay/checkpoints/` 149 race JSONs | 56 MB total | ignored / generated | `/replay/predictions/*`, probability-timeline, local/timeline explanations | `python scripts/build_replay_prediction_cache.py --all-served-races` (~9.6 min prior measurement; current 56 MB/149 races/9644 checkpoints per manifest) | `PredictionUnavailableError` → 503 `prediction_unavailable` (never generated at request time, by design) |
| `results/v2_explainability/global_winner_logreg_v1.json` (+`.sha256`) | 147,114 B, sha256 `bae84b61…9829f739` | ignored / generated | global explanation endpoint | `python -m v2.explainability` (cheap) | explanation endpoint failure |
| `data/v2/simulation/params/r3-v1__through-2024/` | inside `data/v2` 109 MB | ignored / generated | `/v2/simulations/race`, `/v2/strategies/compare` | `python scripts/build_simulation_parameters.py` | 503 `parameter_unavailable` (service-construction error, `v2_simulation_service.py:79-83`) |
| `frontend/data/models.v1.json` / `about.v1.json` | 30,417 / 10,251 B, sha256 `9ae9b6bb…`, `4e73f032…` | TRACKED | `/models`, `/about` (build-time import, no backend) | `python scripts/build_phase9_evidence.py` (do NOT regenerate — frozen) | Next build fails (import-time) — fail-fast, desirable |
| V1 `data/processed/lap{5,10,15,20,25}/**`, `data/interim/**` | ~2.5 MB | TRACKED | `/races`, `/predict/*` | n/a (frozen source) | V1 endpoint errors |
| V1 `results/models/*_multilap/model_tuned.pkl` | 13 MB (`results/models`) | TRACKED | `/predict/*` via `ml/inference.py:29-35` | n/a (frozen, do not retrain) | V1 prediction errors |

REQUIRED FOR RUNTIME: the seven rows above. REQUIRED ONLY FOR
RESEARCH/REGENERATION: everything else under `data/raw/`, `.fastf1_cache/`,
`data/v2/model_lab/`, `data/v2/reports/`, `results/analysis|baselines|
comparisons|debug|data_quality|v2_validation`, `scripts/benchmark_*`,
`scripts/validate_*`, `tests/fixtures/` (test-only).

## Large-file audit

Measured (`du -sh`): `data/` 15G (`data/raw/` 15G; `data/v2/` 109M;
`data/processed/` 1.2M; `data/interim/` 1.3M), `results/` 71M
(`v2_replay` 56M; `models` 13M; `analysis` 1.3M; rest KBs),
`.fastf1_cache/` 100M, `frontend/` 669M (`.next/` 190M; `node_modules/`
478M), `frontend/data/` 44K. Image-bloat hazards, in order: `data/raw`
(15G — five orders above the runtime corpus), `.fastf1_cache` (100M),
`frontend/node_modules` + `.next` (build-context only), `results/` research
outputs outside the three runtime-required paths, `graphify-out/` (~15M per
gitignore comment), IDE/tooling dirs. The runtime-relevant generated set is
small (~165M: 109M corpus + 56M replay + KB artifacts) and well-understood.

## Gitignore / future Docker context

Current `.gitignore` covers: `__pycache__`, venvs, `.env*`, `*.log`,
`frontend/node_modules`, `frontend/.next`, `frontend/out`, `build/`,
`.pytest_cache`, `.fastf1_cache/` + `/data/raw/fastf1_cache/`, `/data/v2/`,
`graphify-out/`, `results/v2_replay/`, `results/v2_explainability/`. Gaps
vs. need: `results/v2_model_lab/` is correctly NOT ignored (tracked
artifact); sim params under `data/v2` are covered by `/data/v2/`.

Proposed `.dockerignore` classification for P10-1 (NOT created):

- ALWAYS EXCLUDE: `.git/`, `node_modules/`, `.next/`, `__pycache__/`,
  `.pytest_cache/`, `.venv/`, `venv/`, `graphify-out/`, `.impeccable/`,
  `.opencode/`, `.claude/`, `.cursor/`, `.gemini/`, `.mcp.json`, IDE dirs,
  `*.log`, `.DS_Store`, root `package.json`/`package-lock.json` (if context
  is the repo root).
- EXCLUDE (bloat): `data/raw/`, `.fastf1_cache/`, `frontend/.next`
  (rebuild inside), `results/analysis|baselines|comparisons|debug|
  data_quality|v2_validation`, `data/v2/model_lab`, `data/v2/reports`,
  `scripts/benchmark_*`, screenshots, `*.tmp/*.bak`.
- NEVER EXCLUDE (runtime-required despite being generated/ignored):
  `data/v2/processed/`, `data/v2/simulation/params/`,
  `results/v2_replay/`, `results/v2_explainability/`
  (or, if excluded from context, the image build/bootstrap MUST regenerate
  or COPY them via an explicit artifact stage — Parts L/M/N decision).

## Replay cache bootstrap

- Lives at `results/v2_replay/checkpoints/` (`DEFAULT_CHECKPOINTS_DIR`,
  `v2/replay_predictions.py:66`), overridable via `--checkpoints-dir`.
- Tracked? NO — `git ls-files results/v2_replay` returns nothing (dir +
  both manifests ignored per `.gitignore:128`). Clean clone = absent.
- Current reality: 149 race JSONs, 56 MB; manifest
  `phase8_e2_cache_manifest_v1.json`: `race_count` 149, `checkpoint_count`
  9644, `manifest_version phase8-e2-cache-manifest-v1`. Consistent with the
  prior "~58.6 MB / ~9.6 min" measurement (same order; exact re-measurement
  was deliberately not rerun — that would violate the no-regeneration rule).
- Generation: `python scripts/build_replay_prediction_cache.py
  --all-served-races` (resumable, skips valid-complete artifacts; `--dry-run`
  does model-free selection only; `--workers` exists). Requires the full V2
  corpus + serving artifact + matrix history, i.e. the heaviest bootstrap
  input of all runtime artifacts.
- Startup behavior if absent: backend imports and serves factual
  timeline/frame endpoints FINE; only cached-prediction reads raise
  `PredictionUnavailableError` → HTTP 503 `prediction_unavailable`
  (`api/v2_replay_service.py:86-100`). The read path can NEVER generate
  (import firewall documented at `api/v2_replay_service.py:13-19`).
- Options tradeoff: (A) bake into image — simplest runtime, +56M layers, but
  ignored files are easy to accidentally exclude from context; (B) generate
  during image build — reproducible, but needs full corpus + deps in the
  build stage and ~10 min build penalty; (C) generate during container
  bootstrap — slow first start (~10 min), needs idempotent entrypoint;
  (D) external mount — fastest image, but reintroduces host-state dependence
  P10 exists to remove; (E) prune scope — NOT available (frozen serving scope
  2018–2024, 149 races is the product).
- Recommendation: **A with B as the verified fallback** — COPY the cache into
  the backend image from a prepared build context (smallest reproducible
  approach: no compute at build/start, deterministic bytes), with CI
  validating presence + manifest identity (`race_count`/`checkpoint_count`/
  contract versions); if context-transfer of 56M proves awkward, B (build-
  stage backfill with the same manifest gate). P10-1 decides on evidence.

## Model artifact bootstrap

- `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib` (17,401 B,
  sha256 `1116b34f…fcaa59f4`): TRACKED, present after clean clone, no
  bootstrap needed. Load path `default_serving_artifact_path` → `V2Paths`
  root + `SERVING_ARTIFACT_REL` (`v2/model_lab/serving.py:39-63`); loading
  enforces strict anchors (84 features, 106 dims, LogReg C=0.01, 2018–2024
  seasons) plus artifact sha/spec fingerprint (`serving.py:43-57` and
  `describe_serving_artifact` exposed via `predictor_identity()`).
- Clean-clone availability: YES. Regeneration (`materialize_serving_artifact`,
  frozen M9 path) exists but must never run in production bootstrap.
- P10-1 action: none beyond ensuring the file stays tracked and is COPYed
  into the image; add a startup/readiness check surfacing
  `predictor_identity()` (Part Q/Y).

## Explainability artifact bootstrap

- `results/v2_explainability/global_winner_logreg_v1.json` (147,114 B,
  sha256 `bae84b61…9829f739` + sidecar `.sha256`): IGNORED (`git ls-files`
  empty; `.gitignore:132`), generated via `python -m v2.explainability`
  (cheap, single-file write with sha sidecar — `v2/explainability.py:820-827`).
- Clean-clone availability: NO. Generation cost is trivial (seconds-scale,
  in-process over frozen model/matrix — no backfill).
- Recommendation: regenerate in the image build (or backend bootstrap) and
  verify the sha sidecar; cheapest of all generated artifacts. Exact command
  + failure behavior to be pinned in P10-1.

## Phase-9 static evidence

- `frontend/data/models.v1.json` (30,417 B) and `about.v1.json` (10,251 B):
  TRACKED, static, available after clean clone, consumed ONLY via validated
  typed entry points (`modelsEvidence.ts` → `validateModelsEvidence`;
  `aboutEvidence.ts`), never raw, never from backend APIs, never touching
  2025 data. `/models` page header: "No fetching, no spinners, no scientific
  computation."
- Container assets: trivially bundled by `next build`. No action needed
  beyond `COPY frontend` + build. Do not regenerate (frozen evidence).

## API surface

Methods/routes with runtime deps and missing-artifact behavior:

| Class | Method + route | Deps | Weight | If dep missing |
|---|---|---|---|---|
| health | `GET /health` | none (static `{"status":"ok"}`) | trivial | n/a (always 200 — the gap) |
| registry | `GET /races` (V1) | V1 CSVs | light | error |
| prediction V1 | `POST /predict/ensemble`, `POST /predict/single-model` | V1 pickles + CSVs | moderate (full-field batch) | error; known frozen Monaco-2022 NaN 500 preserved |
| registry V2 | `GET /v2/races` | D9 `races` parquet | light | `RuntimeError` → 500 |
| states V2 | `GET /v2/races/{id}/states`, `GET /v2/races/{id}/state` | corpus + reconstructor | light–moderate | 404 unknown race / 500 |
| prediction V2 | `POST /v2/predictions/winner-snapshot` | corpus + serving joblib | heavy (~12 s full-field, feature-dominated) | serving-artifact error |
| replay | `GET /v2/races/{id}/replay/timeline`, `/replay/frames/{i}` | corpus only (model-free) | light (ms) | 404s only |
| replay predictions | `GET /v2/races/{id}/replay/predictions/{i}`, `/replay/probability-timeline` | replay cache (+ identity check vs corpus/matrix/model) | light (reads) | 503 `prediction_unavailable` / `not_prediction_checkpoint` 404 |
| explainability | `GET /v2/replay/{id}/frames/{i}/predictions/{d}/explanation`, `…/change`, global explanation route | cache + joblib + matrix + E3 artifact | light–moderate (exact recompute, cached probabilities) | 503 / 500 per contract |
| simulation | `POST /v2/simulations/race` | corpus + through-2024 params | HEAVY (sync caps 1–10k; ~0.7–24.6 s per 1k–10k) | 503 `parameter_unavailable`, 422 `simulation_unsupported` |
| strategy | `POST /v2/strategies/compare` | same + strategy engine (min 100, default 1k) | HEAVIEST (9-candidate/1k ~10–35 s; 10k/3-cand ~35–142 s) | 503 / 422 `strategy_request_invalid` |

No redesign proposed. Note for P10-2: heavy sync endpoints need timeout-aware
tests, never full-count load tests in CI.

## Health / readiness

- Today: `GET /health` returns static `{"status": "ok"}`
  (`api/services/prediction_service.py:18-19`). It proves PROCESS LIVENESS
  only — import success + event loop. It says nothing about: corpus presence,
  serving artifact validity, replay cache coverage, sim params, matrix
  availability.
- Combined with lazy singletons, the process can be "healthy" while EVERY
  scientific endpoint fails. This is the central P10-3 readiness gap.
- P10-3 should add (not in this audit): liveness = today's `/health`
  unchanged; readiness = new endpoint (or extended payload) reporting per-
  artifact status (present/valid + identity: artifact sha, spec fingerprint,
  manifest race/checkpoint counts, params season) without running inference.

## CORS / network boundary

- Backend: `CORSMiddleware, allow_origins=["*"]` (`api/main.py:43-49`).
  Wildcard is the current dev configuration; fine for local non-Docker, wrong
  as a production default. P10-1/P10-3 must make allowed origins
  environment-driven with a same-origin/strict default; do NOT just widen.
- Frontend: build-time `NEXT_PUBLIC_API_BASE`, runtime cross-origin fetch.
  Requirements per environment: local non-Docker — today's defaults work;
  Docker Compose — API base must be the compose service address baked at
  frontend build time (or runtime-config refactor), backend CORS must allow
  the frontend origin; future deployment — explicit origin list + HTTPS base,
  no `*`.
- No other network dependencies at serving time (no external APIs, DBs, or
  telemetry endpoints in serving code).

## Runtime writes / mutability

- Serving path writes: NONE found. Replay service cannot generate by
  construction; sim/strategy compute in memory and return aggregates (no
  persistence calls on the request path); V1 inference is read-only over
  CSVs/pickles.
- Codebase writes exist ONLY in offline/research paths: atomic parquet/JSON
  writers (`v2/storage.py`, `v2/model_lab/results.py`), D6/D7/D9/matrix
  builders, `build_replay_prediction_cache.py`, `v2/explainability.py`,
  sim-params builders, plus `configure_fastf1_cache` mkdir
  (`v2/config.py:102`). `subprocess` appears only in `v2/d11.py` (validation
  gate incl. fresh-env/App checks) and `v2/model_lab/results.py` (git
  metadata) — never on the serving path.
- Filesystem policy for P10-1: backend image CAN be read-only except
  (a) temp dirs (parquet/arrow readers, Python bytecode), (b) the FastF1
  cache path IF any serving-adjacent code enables it (today it does not —
  verify in P10-1 and either mount an empty writable dir or remove the call
  from the serving image path). All offline generation stays out of the
  runtime image.

## Test topology

| Suite | Command | Weight | CI recommendation |
|---|---|---|---|
| Python backend+ML safety net + V2 | `python -m pytest tests/ -q` (97 files; baseline "1540 passed, 4 xfailed + freeze seal") | HEAVY (full) | full run = release/manual; EVERY-PUSH runs a focused subset (freeze-seal + API contract + serving-boundary tests) |
| Frontend node tests | `node --test` from `frontend/` (colocated `*.test.ts`: api, v2, simulator, strategy, replay, models/about evidence, transforms) | FAST | EVERY PUSH |
| TypeScript | `tsc --noEmit -p .` from `frontend/` | FAST | EVERY PUSH |
| ESLint | `npm run lint` from `frontend/` | FAST | EVERY PUSH |
| Next build | `npm run build` from `frontend/` | MODERATE | EVERY PUSH (also validates Phase-9 evidence contracts) |
| Evidence integrity | sha/contract checks (fixture sha, Phase-9 validators, replay manifest identity) | FAST | EVERY PUSH |
| D11 acceptance `python -m v2.d11` | full gate | HEAVY | RELEASE/MANUAL only |
| Scientific suites (d6/d7/d9 realdata, model-lab, sim/strategy validation) | pytest subsets | HEAVY, some network-adjacent | RELEASE/MANUAL only |
| Boundary guards (no-retrain/no-regen/no-network-by-default) | existing contract tests | FAST | EVERY PUSH |

Do NOT put full pytest, D11, matrix builds, or backfills in per-push CI.

## Makefile / command surface

Current targets (`Makefile`, all transparent wrappers): `check-python`
(preflight), `backend-dev` (uvicorn --reload, port 8000), `frontend-dev`,
`test-python` (full pytest), `test-frontend` (`node --test`), `typecheck`,
`lint`, `build` (frontend), `verify` (everything). Classification:

- working: all (modulo needing installs first).
- stale: none, but `backend-dev` bakes dev-only `--reload`; `test-python`
  always runs the FULL suite (no focused-test target for CI).
- missing for production: `install` (pip + npm ci), `backend-prod`
  (uvicorn without reload, host/port via env), `frontend-start`, `build`
  separation (backend image has no build step — nothing to compile), `clean`,
  evidence/manifest check target, `docker-*`, `ci-*` equivalents.
- Do not modify yet (P10-1).

## Clean-clone analysis

`git clone …; cd repo` then per-goal blockers (exact):

1. run backend — BLOCKED by: (a) no environment (create venv, `pip install
   -r requirements.txt`; needs choice of Python — README says 3.11,
   unpinned); (b) generated runtime data absent (`data/v2/processed`,
   sim params, replay cache, E3 artifact — all ignored); tracked serving
   joblib + V1 data present. Import alone succeeds; first V2 request fails.
2. run frontend — BLOCKED by: `npm install` in `frontend/` (478M today);
   then `npm run dev`. `.env.local` optional (defaults to localhost:8000).
3. execute prediction — BLOCKED by: backend blocker chain + V1/V2 data as
   above; V1 works once `requirements.txt` installed (tracked CSVs+pickles);
   V2 winner-snapshot additionally needs corpus + joblib (joblib tracked).
4. open replay — BLOCKED by: corpus (timelines/frames need it) and, for any
   prediction column, the 56M replay cache backfill (~10 min) — the longest
   single bootstrap step.
5. run Monte Carlo — BLOCKED by: corpus + through-2024 sim params
   (`build_simulation_parameters.py`) + compute time per request.
6. run strategy — BLOCKED by: same as (5), heavier.
7. open /models — BLOCKED ONLY by: `npm install` + `npm run dev/build`
   (evidence tracked; no backend needed).
8. open /about — same as (7).
9. run tests — BLOCKED by: (a) Python env + BOTH requirements files;
   (b) `npm install` in frontend for tsc/lint/build; (c) generated artifacts
   for artifact-dependent tests (corpus/cache/matrix) — full `pytest` assumes
   the local build this machine has.

Single most important output: the bootstrap chain is
`python pin → pip install → npm install → data/v2 corpus → sim params →
replay backfill (~10 min) → E3 artifact (seconds)`; everything else is tracked.

## Docker design inputs

- Container count justified: **2** — `backend` (Python/FastAPI) + `frontend`
  (Node/Next). No worker/DB/cache service is required by the architecture
  (synchronous in-process compute; read-only cache files; no sessions).
- Backend base: Python (version TBD — pin 3.11 per README unless P10-1
  re-validates; slim image) + `requirements.txt` (consider slimming research
  deps only with evidence) + tracked repo files + GENERATED_REQUIRED
  artifacts (Part I) or a build-stage that creates them. Port 8000. No build
  step. Writable: tmp only. Healthcheck: `/health` (liveness) today;
  readiness endpoint in P10-3.
- Frontend base: Node (pin; README 22 vs local 23 — decide in P10-1) +
  `npm ci` + `next build` with `NEXT_PUBLIC_API_BASE` as build-arg +
  `next start`. Port 3000. Depends on backend only at request time.
- Volumes: none required for the product (all runtime inputs baked or
  build-generated); optional dev-only mount for FastF1 cache. Explicitly
  avoid mounting `data/raw` or caches into prod images.
- Startup order: backend first (frontend degrades gracefully — static pages
  always work; dynamic pages surface API errors). No orchestrator-level
  health gating strictly needed for local compose beyond `depends_on` +
  healthcheck.
- Build contexts: keep `data/raw/`, `.fastf1_cache/`, `node_modules/`,
  `.next/`, research `results/`, `graphify-out/`, tooling dirs OUT (Part K).

## CI design inputs

No `.github/` exists. Minimum useful CI for P10-2, derived from the test
topology:

- Job 1 — frontend-fast: `npm ci` + `node --test` + `tsc --noEmit` +
  `eslint`. Fast, no artifacts needed.
- Job 2 — frontend-build: `npm run build` (validates Phase-9 evidence
  contracts + static bundling). Moderate, no backend needed.
- Job 3 — backend-focused: pip install + focused pytest subset (API
  contracts, serving boundary, freeze seals) with a minimal artifact fixture
  strategy (TBD in P10-2: either small fixtures or a cached corpus slice —
  do NOT build the full corpus per push).
- Job 4 — evidence integrity: fixture sha, replay manifest identity,
  serving-artifact anchors (`predictor_identity`), Phase-9 validators.
- Explicitly OUT of per-push CI: full `pytest`, D11, matrix builds,
  backfills, benchmarks, sim/strategy load runs (release/manual).
- Runners need pinned Python + Node versions (same pins as Docker).

## Observability

Today: effectively none as infrastructure. No request logging, no latency
middleware, no request IDs, no structured logs in `api/` (only domain
`simulation_request_identity`/`scientific_result_identity` echoes and a
per-request `runtime.{reconstruction,adaptation,simulation,total}_s`
breakdown in sim/strategy responses; model identity via
`predictor_identity()`/`V2ModelIdentity`; stable `{error, detail}` error
envelopes with 404/422/503/500 mapping and no traceback leakage on V2 routes
— `except Exception … stable 500, never a client error` pattern throughout).
Smallest useful P10-3 improvements: uvicorn access logs (already emitted by
the server) + a tiny ASGI middleware logging method/path/status/duration +
expose model/artifact identity + cache-manifest identity on the readiness
payload. No Prometheus/Grafana/OTel/ELK/Sentry — no requirement exists.

## Security/config sanity

- `allow_origins=["*"]` wildcard CORS (`api/main.py:43-49`) — must become
  environment-driven (P10-1/P10-3). Not exploitable beyond data exposure
  (all endpoints are unauthenticated reads/computes), but wrong for prod.
- Secrets: none in tracked code (grep clean). Hygiene note: untracked root
  `.env` on this machine contains a `GEMINI_API_KEY` value, and
  `frontend/.env.local` holds a localhost URL — both correctly ignored
  (`.gitignore:13-14`, `frontend/.gitignore:34`) and must never be committed
  or copied into images. Root `.env` is PREEXISTING_OTHER_WORK.
- Debug/reload: `--reload` is Makefile/dev-only, not code-default; no
  `debug=True` in app code. Prod startup must use plain `uvicorn
  api.main:app --host … --port …` (workers TBD in P10-1; note sync heavy
  endpoints block workers — keep default single-process semantics frozen,
  scale via replicas/timeouts documentation, no code change).
- Error exposure: V2 routes return stable envelopes, never tracebacks;
  legacy V1 preserves a known NaN 500 (frozen, xfailed — not a leak vector
  beyond a 500 status).
- Dependency install: `pip install -r requirements.txt` exact pins (safe);
  `npm` ranges on minor deps (`^`) — lockfile governs reproducibility via
  `npm ci`; root `shadcn` tooling dep is unrelated and must stay out.

## Risk register

| ID | Area | Evidence | Severity | Why it matters | Target |
|---|---|---|---|---|---|
| R1 | Replay cache absent on clean clone | `git ls-files results/v2_replay` empty; 56M/149/9644 measured | BLOCKER | prediction/explanation endpoints 503 without it; ~10 min backfill is the longest bootstrap | P10-1 |
| R2 | Canonical corpus absent on clean clone | `/data/v2/` ignored; `load_v2_service` raises on first request | BLOCKER | ALL V2 endpoints dead without it; rebuild cost highest | P10-1 |
| R3 | Sim params absent on clean clone | `data/v2/simulation/params/*` ignored; 503 `parameter_unavailable` | BLOCKER | sim + strategy dead without it | P10-1 |
| R4 | E3 artifact absent on clean clone | `git ls-files results/v2_explainability` empty | HIGH | explanation endpoints fail; trivial to regenerate — just wire it | P10-1 |
| R5 | Liveness ≠ readiness | static `/health` + lazy singletons | HIGH | orchestrator thinks app is ready when science is down | P10-3 |
| R6 | API base baked at build time | `NEXT_PUBLIC_API_BASE` fallback `127.0.0.1:8000` ×2 client modules | HIGH | prod frontend silently points at localhost | P10-1 |
| R7 | Wildcard CORS | `api/main.py:45` | MEDIUM | wrong prod default | P10-1/P10-3 |
| R8 | No interpreter pins | README 3.11 vs local 3.14; no `engines`, no python pin; no venv | HIGH | unpickle/wheel drift; "works on my machine" recurrence | P10-1 |
| R9 | No install/prod-run targets | Makefile has dev/test only | MEDIUM | clean-env onboarding is manual | P10-1 |
| R10 | 15G `data/raw` + 100M FastF1 cache near build context | measured `du` | MEDIUM | one careless COPY = enormous image / leaked source blobs | P10-1 |
| R11 | Full pytest/D11 in per-push CI temptation | 1540 tests + D11 + backfills | MEDIUM | slow CI gets skipped; protection rots | P10-2 |
| R12 | Secret-adjacent local files | untracked root `.env` has API key value | LOW | leak risk if ever staged/copied | P10-1 (document + verify ignore) |
| R13 | Heavy sync endpoints vs worker model | sim/strategy latency evidence in service comments | MEDIUM | prod timeouts/concurrency surprises | P10-3 (docs/limits) |
| R14 | Root shadcn package.json confusion | root manifest tooling-only | LOW | someone installs/builds the wrong manifest | P10-1 (docs; ignore in contexts) |
| R15 | graphify CLI absent | `command not found` | LOW | P10 automation cannot assume it | DEFER |

## Recommended P10-1 plan

Objective: reproducibly installable/buildable/testable + containerizable;
two images building from a clean clone with explicit artifact bootstrap.
Files likely affected: `Dockerfile.backend`, `Dockerfile.frontend` (new),
`.dockerignore` (new), `Makefile` (install/prod targets — additive),
`requirements*.txt` (pins for interpreter note only — no dep changes),
`frontend/` config for build-arg API base + CORS env wiring (minimal,
behavior-preserving), docs. Validation gate: clean-clone `docker build` both
images; compose up; `/health` 200; `/models`+`/about` render; V2 race list +
one winner-snapshot + one replay prediction + one small sim + one strategy
compare succeed against baked artifacts; manifest/sha identity checks pass.
Non-goals: no CI, no readiness endpoint, no CORS redesign beyond env wiring,
no scientific changes, no dependency upgrades.

## Recommended P10-2 plan

Objective: minimum useful per-push CI (Jobs 1–4 in Part X) on pinned
runners. Files likely affected: `.github/workflows/*` (new), focused-test
selection docs, minimal artifact fixture strategy for Job 3. Validation gate:
green run on a scratch PR; full-suite/D11 proven to remain manual (documented
trigger). Non-goals: no heavy validation in CI, no image publishing yet
(unless trivially additive), no scientific changes.

## Recommended P10-3 plan

Objective: configuration + lightweight observability. Files likely affected:
env-driven CORS/origins + host/port wiring, liveness vs readiness endpoint
(artifact-status payload incl. model/params/manifest identity), tiny request
log middleware (method/path/status/duration), docs. Validation gate: readiness
reflects artificially-removed artifact (staging test); logs verified on
sim/strategy calls. Non-goals: no metrics infra, no tracing infra, no secret
management system, no scientific changes.

## Recommended P10-4 plan

Objective: clean-environment reproducibility validation per AGENTS.md policy
(background PID capture, polling, log discipline; fast gates first; serial
heavy work). Likely: fresh container/VM clone → install → build → artifact
bootstrap → full `pytest` + D11 + frontend battery, reusing P10-0/P10-2
evidence where unchanged. Validation gate: all green in the clean env with
hashes recorded. Non-goals: no fixes for pre-existing xfail/known defects
(Monaco NaN stays), no retraining.

## Recommended P10-5 freeze plan

Objective: productionization final validation + freeze: re-run P10-4 gates,
tag, record P10-1 entry-gate checklist closure, freeze Docker/CI/config
surface. Validation gate: the P10-1 entry-gate list below all checked with
evidence links. Non-goals: any scientific behavior change (Phases 1–9 stay
frozen).

## Known limitations

- Graphify CLI unavailable — navigation fallback used (noted above).
- Backend import check not executable here (no deps in system Python 3.14);
  route inventory taken from source (decorators) rather than a live app.
- Sizes/hashes are machine-local snapshots; generated artifacts (56M replay,
  109M corpus) will differ byte-wise across rebuilds — identity (manifest
  counts, contract versions, artifact sha of the TRACKED joblib) is the
  stable comparator.
- Generation durations cited from prior Phase-8 evidence (~9.6 min), not
  re-measured (re-running would violate the no-regeneration rule).
- `pip`-level unused-dependency proof and load testing were out of scope for
  a read-only audit.

## P10-1 entry gate

- [x] actual runtime topology
- [x] canonical backend startup path
- [x] canonical frontend startup path
- [x] Python dependency source
- [x] Node dependency source
- [x] Node/package-manager assumptions
- [x] environment-variable inventory
- [x] filesystem/path assumptions
- [x] runtime artifact inventory
- [x] runtime-required vs research-only distinction
- [x] replay-cache bootstrap problem understood
- [x] model-artifact bootstrap understood
- [x] explainability-artifact bootstrap understood
- [x] static Phase-9 evidence availability understood
- [x] current API surface mapped
- [x] liveness/readiness gap understood
- [x] CORS/network assumptions understood
- [x] runtime write requirements understood
- [x] test topology mapped
- [x] Make command surface mapped
- [x] clean-clone blockers identified
- [x] Docker requirements derived
- [x] CI requirements derived
- [x] observability gaps identified
- [x] obvious production-config risks identified
- [x] risk register complete
- [x] P10-1 implementation scope derived from evidence
- [x] no scientific code modified
- [x] no unrelated work modified
- [x] nothing staged/committed/tagged
