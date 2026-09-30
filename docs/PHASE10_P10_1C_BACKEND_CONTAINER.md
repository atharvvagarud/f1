# PHASE 10 P10-1C BACKEND CONTAINER

Packaging only. No scientific development: no retraining, refitting,
feature/label changes, RaceState, replay, Monte Carlo, strategy, or
2025-evaluation changes. No application routes, schemas, CORS, model
behavior, or dependency pins changed. No frontend Dockerfile, compose,
CI, readiness endpoint, or observability added (P10-1D and later,
NOT started).

## Final verdict

P10-1C COMPLETE — READY FOR P10-1D. The production backend image
`f1-intelligence-backend:p10-1c` builds from the validated workspace on
`python:3.11-slim` (arm64), installs only the exact pinned production
requirements, merges the P10-1A validated bundle onto canonical paths,
serves as non-root via the exact P10-1B command with network ingestion
off, and proves representative V1 + V2 functionality from inside the
container with all scientific identities exact.

## Frozen baseline

- HEAD: `440f2a370aff56c799e69b65781199b158064fa0`
  (`440f2a3 feat(v2): freeze models and about phase 9`)
- Tag on HEAD: `v2-models-about-phase9` — matches.
- Phase 1–9: FROZEN. Proven by SHA identity inside the container
  (see Artifact identity); no `api/`, `ml/`, `v2/`, tracked-data, or
  tracked-model file was modified.

## Repository safety

- Start: HEAD/tag as above, `git diff --cached --stat` empty.
- End: HEAD/tag unchanged, nothing staged/committed/tagged/reset/
  restored/cleaned/stashed (verified).
- P10-0/P10-1A/P10-1B uncommitted work preserved; PREEXISTING_OTHER_WORK
  (tooling deletions/modifications, root manifests, env files) untouched.
- Owned changes only: `Dockerfile.backend` (new), `.dockerignore` (new),
  `tests/test_backend_container_contract.py` (new),
  `docs/PHASE10_P10_1C_BACKEND_CONTAINER.md` (new), `Makefile` (two
  additive targets + two `.PHONY` names; all existing lines byte-identical).

## Docker environment

- Client: Docker 29.8.0; Server/engine: 29.8.0; arch: aarch64 (arm64,
  Apple Silicon, native build — no cross-platform claim).
- NOTE: a previous session attempt found only a broken
  `/usr/local/bin/docker` symlink (no engine) and correctly STOPPED with
  BLOCKED — DOCKER ENGINE UNAVAILABLE without creating anything. This
  session re-verified availability first, then implemented.

## Backend image design

`Dockerfile.backend`, layered for cache reuse:

1. `FROM python:3.11-slim` (3.11.x family per P10-1B; resolved patch
   3.11.16 — same language line as validated 3.11.15, exact wheel pins).
2. `ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 V2_PROJECT_ROOT=/app`
   (`V2_ALLOW_NETWORK` deliberately absent).
3. `COPY requirements.txt` + `python -m pip install --no-cache-dir`
   (binary wheels; `requirements-test.txt` never installed).
4. `COPY api/ ml/ v2/` (full packages — 387 source-only files, ~7 MB;
   no pruning: serving imports span all three).
5. Tracked V1 inputs + serving joblib + two frozen identity manifests
   (see Source allowlist).
6. `COPY runtime_artifacts/data/ ./data/` +
   `COPY runtime_artifacts/results/ ./results/` (bundle merged onto
   canonical paths; staging dir itself never copied — no duplication).
7. Presence assertion (`test -f` on 5 sentinels), non-root user,
   `EXPOSE 8000`, exec-form CMD.

No OS packages added; no Node/npm/Git/compiler/FastF1 tooling
(msgpack sdist built with the base image's toolchain without additions).

## Source allowlist

Determined by import/path evidence, not guessing:

| Image path | Host source | Evidence |
|---|---|---|
| `/app/api/` | `api/` (508 KB) | `api/main.py` routers; services import `ml.inference`, `v2.*` |
| `/app/ml/` | `ml/` (68 KB) | `api/services/prediction_service.py` → `ml.inference` → `ml.config` paths |
| `/app/v2/` | `v2/` (6.7 MB, source only — zero embedded parquet/csv/json/joblib) | serving stack across `v2_service`, `model_lab/serving`, replay, explainability, simulation, strategy |
| `/app/data/processed/`, `/app/data/interim/` | tracked V1 (1.2 + 1.3 MB) | `ml/config.py:get_dataset_path`; P10-1A class F required |
| `/app/results/models/` | tracked V1 (13 MB) | `ml/config.py:get_model_dir` |
| `/app/results/v2_model_lab/winner_logreg_raw_v1_serving.joblib` | tracked serving model (17 KB, copied once) | `v2/model_lab/serving.py` safe loader |
| `/app/docs/PHASE4_FREEZE_MANIFEST.json` | tracked (5.9 KB, phase2 hash only) | `api/v2_replay_service.py:59` `_FREEZE_MANIFEST` (cache-key identity) |
| `/app/docs/generated/phase2_freeze_manifest.json` | tracked (4.2 KB) | `scripts/replay_feature_matrix.py:44` `MANIFEST_REL` (explanation matrix) |
| `/app/scripts/replay_feature_matrix.py` | single runtime helper (stdlib+pandas+`v2.prediction` only) | `api/v2_explanation_service.py:164,203` imports it |
| `/app/data/v2/processed`, `/app/data/v2/simulation/params`, `/app/results/v2_replay`, `/app/results/v2_explainability` | P10-1A bundle (98 + 0.3 + 56 + 0.1 MB) | P10-1A contract classes A–D |

The two `docs/` manifests and the single `scripts/` helper were found by
two genuine container 500s during smokes (missing-file root causes in
`docker logs`) and fixed as packaging inputs only, per Part AF — no
application/scientific code changed. Full `scripts/` (builders, benchmarks,
validators) is NOT in the image; `frontend/`, `tests/`, research results
are NOT in the image.

## Runtime artifact integration

- Host prepares/validates: `prepare_runtime_artifacts.py --validate`
  → VALID (1939 files / 157,647,360 bytes, `runtime-artifacts-v1`).
- Docker only merges: no packaging mode, replay/simulation/matrix/
  explainability builders, or ingestion run during build (verified by
  scientific firewall).
- Consumers resolve existing canonical paths unchanged
  (`V2_PROJECT_ROOT=/app`, WORKDIR `/app`).
- `make docker-backend-build` = `preflight` (deployable gate incl.
  validator reuse + network-off) then `docker build`.

## Dockerignore

`.dockerignore` excludes `.git`, venvs, bytecode, logs, `data/*` (except
`data/processed/`, `data/interim/`), `results/*` (except `results/models/`
and the single serving joblib), `frontend/`, `tests/`, `docs/*` (except
the two manifests above), `scripts/*` (except the runtime helper),
tooling dirs, `*.md`, env files, and root JS manifests. `runtime_artifacts/`
is matched by NO pattern and survives filtering (proven: image COPY layers
98 + 56 MB ≈ bundle; `data/raw` and `.fastf1_cache` absent from image).

## Secret safety

- Image contains: no `.env*`/pem/key/credentials files, no `.git/`,
  zero `*API_KEY*/*SECRET*/*PASSWORD*/*TOKEN*` env entries (verified by
  filename search + env scan; values never printed).
- Host `.env` / `frontend/.env.local` are gitignored AND dockerignored;
  neither entered any layer (single-digit-KB context + layer audit prove
  no room for them; nothing was deleted-in-a-later-layer).

## Runtime environment

Only `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`,
`V2_PROJECT_ROOT=/app` (plus base-image defaults). `V2_ALLOW_NETWORK`
absent everywhere (inspect + exec); port 8000; WORKDIR `/app`.

## Non-root execution

`appuser:appuser`, UID/GID 10001, created via `useradd --create-home`;
`/app` chowned to it; nothing world-writable. All smokes ran as appuser
(uid check + image config `User=appuser:appuser`).

## Start command

Exec-form `CMD ["python", "-m", "uvicorn", "api.main:app", "--host",
"0.0.0.0", "--port", "8000"]` — byte-equivalent to the P10-1B command.
Single process, no `--reload`, no bootstrap script, no workers.

## Build evidence

- `docker build -f Dockerfile.backend -t f1-intelligence-backend:p10-1c .`
  green after host preflight (deployable OK under Python 3.11).
- First full build: deps + copies in minutes; final rebuild ~30 s (cache).
- Image: 2.86 GB, `arch=arm64 os=linux`, `User=appuser:appuser`,
  `WorkingDir=/app`, `ExposedPorts={8000/tcp}`.
- Base `python:3.11-slim` resolved to Python 3.11.16.
- `make docker-backend-build` (preflight + build) verified end-to-end.

## Image content audit

Present: `api`, `ml`, `v2`, installed runtime packages, serving joblib,
V1 `data/processed` + `data/interim` + `results/models`,
`data/v2/processed` corpus, simulation params, replay cache (149 files),
explainability artifact + sidecar, both `docs/` manifests, the one
`scripts/` helper. Absent: `data/raw`, `.fastf1_cache`,
`runtime_artifacts/` staging dir, `frontend*`, `tests`, `docs` (beyond the
two manifests), `graphify-out`, `.git`, `.venv`, env files, research-only
`results/*` trees, root JS manifests. No staging-tree duplication.

## Artifact identity

From inside the container (hash reads only, zero recomputation):

- serving joblib:
  `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4` ✓
- explainability:
  `bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f` ✓
- replay: 149 races / 9,644 checkpoints /
  `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298` ✓
  (plus matrix `b0f17b66…`, phase2 `d2ee966c…`, rows 189420 via manifests)
- simulation: `r3-v1`, through_season 2024,
  `parameter_set_id phase6-r3-empirical`, version
  `r3-v1.2024.4c2f85f08f1c`, scientific hash
  `4c2f85f08f1ce66cc6477982b2d5c97e9547f70927224b8e949ebe123ff3f140` ✓

## Liveness

`docker run -p 8000:8000` → `GET /health` → HTTP 200 `{"status":"ok"}`
(~2 s to ready). Liveness only; no readiness claim (P10-3).

## V1 smoke

- `GET /races` → 200 (2019 season list; Monaco defect untouched).
- `POST /predict/single-model` 2019 Australian GP / logreg → 200, five
  checkpoints, BOT winner throughout (matches actuals).

## V2 factual smoke

- `GET /v2/races` → 200 (2018-r01-R first; all seasons ≤ 2024).
- Anchor discovery `GET /v2/races/2023-r01-R/states` → 1,056 anchors.
- `GET /v2/races/2023-r01-R/state` (alonso/lap 28/t 6558.658) → 200,
  roster 20.

## Winner prediction smoke

Exactly one snapshot: `POST /v2/predictions/winner-snapshot`
(2023-r01-R, alonso, lap 28) → 200, `INDEPENDENT_BINARY` with
do-not-renormalize note, model `1116b34f…`, RAW, C=0.01 lbfgs, 2018–2024.
No 2025, no normalization, no metric recomputation.

## Replay smoke

- `GET /v2/races/2023-r01-R/replay/timeline` → 200, contract v1.
- `GET .../replay/predictions/0` → 200, `cache_status: HIT` (not 503),
  `INDEPENDENT_BINARY`, model `1116b34f…`.

## Explainability smoke

- `GET /v2/replay/2023-r01-R/frames/0/predictions/max_verstappen/explanation`
  → 200, `LOG_ODDS` space, `INDEPENDENT_BINARY`, fingerprint
  `3164de9e…` (matches replay model identity), RAW, 2018–2024, cache HIT.
  (An albon probe correctly returned structured 422
  `driver_not_observable` — honest unobserved-driver contract, kept as
  evidence the error path works.)

## Monte Carlo smoke

- `POST /v2/simulations/race` (2022-r01-R, perez, lap 30, count=10 —
  minimum-adjacent; schema minimum is 1) → 200, 10/10 valid, params
  `phase6-r3-empirical` / `r3-v1.2024.4c2f85f08f1c` /
  `4c2f85f0…3f140`, 20 drivers, ~0.03 s engine time.
- Two honest rejections on the way (stale-roster 294.3 s rule; unobserved
  roster at lap 1) confirm frozen engine guardrails, not packaging gaps.

## Strategy smoke

- `POST /v2/strategies/compare` (same anchor, target perez,
  MAXIMIZE_WIN_PROBABILITY, count=100 = schema minimum, one STAY_OUT
  candidate) → 200, baseline 100/100 valid, 1 candidate executed.

## Network-off validation

All smokes ran in a container where `V2_ALLOW_NETWORK` is absent
(`docker exec` → `None`). No ingestion touched; browser/client out of scope.

## Read-only validation

`docker run --read-only --tmpfs /tmp` → `/health` 200, `/v2/races` 200,
cached replay prediction 200 + HIT. No broader writable mounts needed;
`--tmpfs /tmp` is the documented minimum.

## Image/context size

- Image 2.86 GB. Layer SOS: pip deps 1.41 GB (exact validated pins incl.
  xgboost's CUDA pulls — kept, no slimming per policy), bundle 105 + 59 MB,
  V1 models 13.7 MB, source ~8 MB, manifests ~50 KB.
- Context: BuildKit reports ~300 KB metadata transfer (Desktop virtiofs
  reads on demand); decisive proof is the image itself — COPY layers sum to
  ≈ bundle bytes (98 + 56 MB on host), while the 15 GB `data/raw` and
  100 MB `.fastf1_cache` are absent from the image and excluded by pattern.
- No dependency slimming attempted; no size target exists.

## Makefile surface

Added (existing targets/lines untouched): `docker-backend-build`
(`preflight` → `docker build -f Dockerfile.backend -t
f1-intelligence-backend:p10-1c .`) and `docker-backend-run`
(`--rm -p 8000:8000`, no env flags to hide behavior). `make
docker-backend-build` executed green end-to-end.

## Test evidence

- `tests/test_backend_container_contract.py` (12 new, static, stdlib-only):
  base family, prod-requirements-only, `python -m pip`, exec CMD, no reload,
  port 8000, env defaults, `V2_ALLOW_NETWORK` absent, bundle merge without
  staging copy, no broad COPY before deps, joblib copied once, dockerignore
  keep/protect lists, scientific firewall over Dockerfile + docker targets.
- Gate suites: P10-1A (12) + P10-1B (22) + P10-1C (12) = **46 passed**.
- `runtime_artifacts --validate`: VALID 1939/157647360.
- `check_runtime_environment.py --deployable` (py3.11): OK.
- Full scientific suite / D11 / frontend suite: NOT run (no shared
  app/science file changed — packaging + tests + docs only).

## Scientific firewall

`Dockerfile.backend` + `Makefile` docker targets contain none of: `v2.d6`,
`v2.d7`, `v2.d9`, `build_matrix`, training, `materialize_serving_artifact`,
`build_replay_prediction_cache`, `build_simulation_parameters`,
explainability generation, FastF1 ingestion, 2025 evaluation (enforced by
contract test). No science regenerated, no pins changed.

## Known limitations

- arm64-only validation (native Apple Silicon); amd64 untested — no
  multi-arch publishing (deferred, as instructed).
- Base patch 3.11.16 vs validated 3.11.15: same 3.11.x line, exact pins.
- `nvidia-nccl-cu12` (~1 GB class) rides along with pinned xgboost; kept
  deliberately — slimming is out of scope.
- Two scientifically-honest 422s during probing are frozen guardrails, not
  defects (documented above).

## P10-1D handoff

Backend image contract is frozen: tag `f1-intelligence-backend:p10-1c`,
port 8000, `/health` liveness only, `V2_ALLOW_NETWORK` unset, CORS still
wildcard (P10-3), readiness P10-3, frontend container + compose explicitly
not started. P10-1D owns the frontend image only.

## Entry gate

- [x] Docker engine available (29.8.0, arm64)
- [x] Dockerfile.backend implemented (python:3.11-slim)
- [x] production requirements only, pins unchanged
- [x] source allowlist established with import evidence
- [x] runtime_artifacts integrated, no staging duplication
- [x] tracked serving joblib included once; V1 resources preserved
- [x] .dockerignore implemented; data/raw, FastF1 caches, env files,
  secrets, research outputs excluded
- [x] non-root runtime (appuser 10001); V2_PROJECT_ROOT correct;
  V2_ALLOW_NETWORK absent; exact uvicorn CMD; no reload
- [x] image builds; arch + size recorded
- [x] all artifact identities exact inside container
- [x] /health 200; V1 /races + prediction; V2 races + state; one winner
  snapshot; one cached replay prediction (HIT); one LOG_ODDS explanation;
  one small MC; one small strategy comparison
- [x] network-off serving proven; read-only smoke green (`--tmpfs /tmp`)
- [x] context excludes 15 GB raw; bundle included
- [x] P10-1A + P10-1B + P10-1C tests green (46); deployable preflight green
- [x] no science regenerated; no app/science code modified; unrelated work
  untouched; nothing staged/committed/tagged
- [x] P10-1D handoff explicit