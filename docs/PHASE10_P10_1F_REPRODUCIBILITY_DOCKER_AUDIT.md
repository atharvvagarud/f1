# PHASE 10 P10-1F REPRODUCIBILITY + DOCKER AUDIT

Closing audit of the P10-1 reproducible-runtime tranche. Audit + hardening
only: zero product, infrastructure, science, or dependency changes. One
new 6-test contract file pins previously untested cross-stage invariants;
no Dockerfile/Compose/application/Makefile behavior was modified (no
defect found that warranted it).

## Final verdict

P10-1F COMPLETE — READY FOR P10-2. The deployment contract is complete,
internally consistent, reproducible (live double-prepare determinism +
full `--no-cache` rebuild), safe (secret/network/failure-injection
audits green), documented, and ready as CI input.

## Frozen baseline

- HEAD: `440f2a370aff56c799e69b65781199b158064fa0`
  (`440f2a3 feat(v2): freeze models and about phase 9`)
- Tag on HEAD: `v2-models-about-phase9` — matches, start to end.
- Nothing staged/committed/tagged/reset/restored/cleaned/stashed.

## Repository safety

- `git log -1 --oneline` / `git tag --points-at HEAD` / empty
  `git diff --cached --stat` verified at start and end.
- Dirty files classify cleanly (below); PREEXISTING_OTHER_WORK untouched.

## P10-1 owned inventory

- P10-1A: `scripts/prepare_runtime_artifacts.py`,
  `tests/test_runtime_artifact_packaging.py` (12),
  `docs/PHASE10_P10_1A_RUNTIME_ARTIFACT_CONTRACT.md`,
  `.gitignore` modification (staging entry).
- P10-1B: `.python-version`, `frontend/.nvmrc`,
  `scripts/check_runtime_environment.py`,
  `tests/test_runtime_environment.py` (22), `Makefile` bootstrap targets
  (shared file), `frontend/package.json` engines field (only diff),
  `docs/PHASE10_P10_1B_RUNTIME_BOOTSTRAP_CONTRACT.md`.
- P10-1C: `Dockerfile.backend`, `.dockerignore` (shared file),
  `tests/test_backend_container_contract.py` (12), Make docker-backend-*,
  `docs/PHASE10_P10_1C_BACKEND_CONTAINER.md`.
- P10-1D: `Dockerfile.frontend`, `frontend/next.config.ts` (+standalone),
  `tests/test_frontend_container_contract.py` (13), Make docker-frontend-*,
  `docs/PHASE10_P10_1D_FRONTEND_CONTAINER.md`.
- P10-1E: `compose.yaml`, `tests/test_compose_contract.py` (13), Make
  docker-compose-*, `docs/PHASE10_P10_1E_COMPOSE_RUNTIME_VALIDATION.md`.
- P10-1F: `tests/test_production_reproducibility_contract.py` (6, new),
  this document.
- Overlaps verified safe: `Makefile` (purely additive per-stage blocks),
  `.dockerignore` (P10-1D frontend refinement leaves every backend pattern
  intact — enforced by contract tests + live backend rebuild/identity).
- PREEXISTING_OTHER_WORK: tooling deletions (`.claude/`, `.cursor/`,
  `.gemini/`, `.ignore`, `.mcp.json`), `AGENTS.md`/`GEMINI.md`/`opencode.json`
  mods, untracked `.impeccable/`/`.opencode/`, root JS manifests — all
  preserved, none read for secrets.

## Source vs deployable contract

A clean source clone is NOT a complete offline deployable runtime.
Deployable = SOURCE TREE + VALIDATED `runtime_artifacts/` BUNDLE (1939
files, 157,647,360 bytes, gitignored, deliberately uncommitted).
`git clone && docker compose up` is NOT claimed and NOT true: the bundle
must first be prepared (`prepare_runtime_artifacts.py`) and validated
(`--validate` + `--deployable` preflight). `runtime_artifacts/` is absent
on clean clone (classes A–D per P10-1A); tracked classes E–F are present.

## Runtime artifact contract

`prepare_runtime_artifacts.py --validate --root .` → VALID, 1939 files /
157647360 bytes, `runtime-artifacts-v1`, manifest SHA-256
`e4008425d37c2c683c47a227b6acc8ba6d43f02d7e8906380e17f5f6a8751a81`
(matches the historical `e4008425…` prefix). Serving scope: 149 races /
9644 checkpoints / 2018–2024. The manifest's own validation contract
forbids raw/FastF1/research/env/secret/frontend-build prefixes. No
regeneration performed.

## Packaging determinism

LIVE (not inherited): prepared twice into temp in-root staging dirs via
the packager's supported `--staging` mechanism (external `/tmp` staging
is correctly refused by the tool — good fail-closed design), then
removed. Result: identical inventory (1940 paths), identical per-file
content hashes, identical manifest bytes, identical to canonical. Temp
dirs verified gone (zero `git status` trace). Canonical bundle untouched
throughout. P10-1A synthetic determinism evidence remains valid backup.

## Runtime preflight

- `--source` → OK; `--deployable` → OK (Python 3.11).
- Fail-closed live: `V2_ALLOW_NETWORK=1` → DEPLOYABLE FAIL with explicit
  message; system Python 3.14 → FAIL with 3.11 activation guidance.
  Missing/invalid-bundle paths covered by the 22-test suite (green).

## Version contract

`.python-version` = 3.11; `Dockerfile.backend` = `python:3.11-slim`
(resolved 3.11.16); `frontend/.nvmrc` = 22; `package.json engines` =
`>=22 <23`; `Dockerfile.frontend` = `node:22-bookworm-slim` ×3 stages
(resolved 22.23.3). Docs + Makefile agree. No contradictions. New
contract test pins declaration↔Dockerfile agreement.

## Dependency contract

`requirements.txt`, `requirements-test.txt`,
`frontend/package-lock.json` byte-identical to tracked (only
`frontend/package.json` differs, by the approved P10-1B engines field).
Dockerfiles: `python -m pip install -r requirements.txt` (no test file)
and `npm ci` (no install/upgrade/lockfile generation). Nothing
regenerated.

## Makefile audit

Targets inventoried: bootstrap/install, preflight(+source),
backend-prod, frontend-start, docker-backend-*, docker-frontend-*,
docker-compose-*. All additive; earlier semantics preserved (existing
lines byte-identical apart from `.PHONY` name additions).
`docker-backend-build` + `docker-compose-build` depend on `preflight`;
`docker-frontend-build` enforces `NEXT_PUBLIC_API_BASE` (new test pins
both wirings). No science, sudo, env mutation, or destructive commands
(only `>&2` error redirections matched the audit grep).

## Dockerignore audit

Read in full (88 lines). Backend inputs (requirements, api/ml/v2,
processed/interim, models, one joblib, 2 docs manifests, 1 scripts
helper, runtime_artifacts) all unmatched-or-included; frontend source
available except `node_modules/`, `.next/`, `.env.local`. Exclusions
present for `.git`, raw data, FastF1 caches, venvs, env/secrets, tests,
non-runtime docs/scripts, research outputs, tooling. P10-1D's frontend
change provably backend-safe (backend COPYs nothing under `frontend/`;
fresh no-cache backend build + identity checks confirm).

## Secret audit

No `*_API_KEY`, `AWS_SECRET`, or private-key material in Dockerfiles,
compose, Makefile, scripts, or P10 tests. Both images contain no `.env*`
files. `.env.local` sets only public `NEXT_PUBLIC_API_BASE` and never
enters builds. Values never printed.

## Backend image contract

`Dockerfile.backend` unchanged and green: 3.11-slim, exact prod install,
allowlisted copies, bundle merge, no generation, `V2_PROJECT_ROOT=/app`,
no `V2_ALLOW_NETWORK`, appuser 10001, :8000, exec uvicorn, no reload.
Fresh no-cache image: 2.86 GB, arm64 (matches historical).

## Frontend image contract

`Dockerfile.frontend` unchanged and green: Node 22 ×3 stages, `npm ci`,
required build arg (live re-rejected), standalone, `node` user, :3000,
exec `node server.js`, no backend/science copies. Fresh no-cache image:
553 MB, arm64 (matches historical).

## Compose contract

`docker compose config` clean; `--services` = exactly backend/frontend;
ports 8000/3000; build arg localhost:8000; read-only + `/tmp` tmpfs both;
no volumes/mounts; no DB/cache/worker/proxy; no secrets; no
`V2_ALLOW_NETWORK`; no backend-DNS in browser config.

## No-cache rebuild

`docker compose build --no-cache` → BOTH green, zero errors, ~3 min wall
clock (descriptive, not a benchmark). Fresh IDs: backend `a6eb2a02…`
(2.86 GB), frontend `33f6ebfe…` (553 MB), arm64. Sizes identical to
cached builds — reproducibility, not drift.

## Frontend missing-argument rejection

Live re-verified: build without the arg exits 1 with
`NEXT_PUBLIC_API_BASE is required`; no image produced.

## Fresh Compose validation

`down` → `up -d` (no rebuild) on the no-cache images: containers run the
fresh digests (verified via inspect), both UP, health + frontend 200.

## Runtime artifact identities

Inside the fresh backend (hash reads only): serving `1116b34f…fcaa59f4`
✓, explainability `bae84b61…982939f` ✓, replay 149/9644
`78a3c059…o98` ✓, matrix `b0f17b66…` ✓, phase-2 `d2ee966c…` ✓,
simulation `phase6-r3-empirical`/2024 ✓.

## Representative workflow smoke

Backend health + /v2/races 200; all six frontend routes 200; prediction
200; cached replay 200 + HIT; explanation 200; MC (10) 200; strategy
(100) 200.

## Restart and immutability

`compose restart` → health/frontend 200, replay still HIT. Read-only
services (except `/tmp`) make persistent mutation impossible; no
generation observed, no write errors in logs.

## Network-off validation

`V2_ALLOW_NETWORK` absent in Compose backend; zero FastF1/ingestion
traces in logs; no external calls made.

## 2025 firewall

Winner-snapshot for `2025-r01-R` → 404 (factual path re-proven in
P10-1E). No evaluation.

## Image-content audit

Backend: no raw/FastF1/frontend/tests/graphify/.git/.venv/staging/research
leak; `/app/docs` holds exactly the 2 allowlisted manifests. Frontend: no
backend/science/tests/env/git; 72 MB traced node_modules. Layer history
consistent with contracts. Nothing optimized (per non-goals).

## Host prerequisites

Deployable workflow needs from the host: git checkout, Python 3.11 (for
packager + preflight only), the validated bundle, Docker engine +
Compose, and (unless cached) network for base images + pinned packages.
NOT needed: host Node (no `node` in backend path; frontend builds inside
Docker), host FastF1/builders, Graphify (absent from all container/Make
paths — developer tooling only, per P10-0).

## Offline/reproducibility boundaries

- RUNTIME OFFLINE: yes — serving needs no FastF1/network (proven).
- BUILD OFFLINE: NOT guaranteed — base images + 45 Python pins + 372 npm
  packages need network unless cached.
- SOURCE-ONLY REBUILD: NOT supported — ignored bundle is required input.
- "Fully offline reproducible" is NOT claimed.

## Architecture validation boundary

Validated on arm64 only. No amd64/multi-arch claim (base images may
support it — untested, not validation).

## Browser-validation limitation

Carried forward verbatim: no existing browser automation; console/
hydration and measured 1440/390 rendering remain unexecuted. Not a
blocker (no UI code changes anywhere in P10-1F). P11 may use proper
tooling if available then.

## Failure injection

Live fail-closed proofs (canonical artifacts untouched): missing-arg
frontend build → exit 1; `V2_ALLOW_NETWORK=1` → DEPLOYABLE FAIL; wrong
Python (3.14) → DEPLOYABLE FAIL with guidance; external staging dir →
packager refusal; missing/invalid bundle → covered by green suites.

## Test evidence

- New `tests/test_production_reproducibility_contract.py` (6):
  version agreement ×2, Make preflight wiring, frontend-arg wiring,
  compose Dockerfiles exist, bundle ignored-yet-included. All pass.
- Full focused matrix: 12 + 22 + 12 + 13 + 13 + 6 = **78 passed**.
- Frontend 197 NOT re-run (no frontend build inputs changed; both
  production images built green via Compose + no-cache).
- Scientific suite NOT run (no shared app/science file changed).

## Documentation consistency

Cross-checked P10-0→P10-1E against current state: Docker-absent-at-P10-0
(historical fact, engine installed later), P10-1B family declaration →
P10-1C build (realized), browser unavailability P10-1D→P10-1E→P10-1F
(consistent), sizes/identities/ports stable across reports and fresh
evidence. No contradictions introduced.

## Scientific firewall

No training/fit/ingestion/feature/label/matrix/replay/sim/explainability/
2025 operations invoked anywhere in P10-1F. Hash/manifest reads only;
no model loaded (preflight's identity check is hash-based, per P10-1B).
No benchmarks.

## Final P10-1 runtime contract

- SOURCE: git checkout at `440f2a3` (`v2-models-about-phase9`).
- BUNDLE: `runtime_artifacts/` prepared + `--validate` green
  (`runtime-artifacts-v1`, 1939 files, 157647360 bytes,
  manifest `e4008425…8751a81`).
- PYTHON: 3.11.x (host tooling + `python:3.11-slim` image).
- NODE: 22 LTS, `>=22 <23` (host parity + `node:22-bookworm-slim`).
- BACKEND BUILD: `make docker-backend-build` (preflight → image, :8000,
  `V2_PROJECT_ROOT=/app`, network-off, appuser, read-only+/tmp).
- FRONTEND BUILD: `make docker-frontend-build
  NEXT_PUBLIC_API_BASE=<browser-reachable>` (standalone, :3000, node
  user, read-only+/tmp).
- COMPOSE: `make docker-compose-build/up/down` — exactly backend +
  frontend, :8000/:3000, base `http://localhost:8000`, no volumes.
- PORTS: 8000 backend, 3000 frontend.
- NETWORK: serving offline; builds need network unless cached.
- FILESYSTEM: read-only + `/tmp` tmpfs both services.
- IDENTITIES: joblib `1116b34f…fcaa59f4` (INDEPENDENT_BINARY, 2018–2024);
  explainability `bae84b61…982939f`; replay 149/9644 `78a3c059…o98`;
  simulation r3-v1/2024 `phase6-r3-empirical`; phase-2 `d2ee966c…`;
  matrix `b0f17b66…`.
- SERVING YEARS: 2018–2024 (2025 rejected with `unknown_race`).
- LIMITATIONS: arm64-only; builds not offline-guaranteed; source-only
  rebuild unsupported; no browser validation yet; backend ~1 GB idle RSS.

## Known limitations

- arm64-only validation; backend idle ~1 GB (corpus).
- No browser engine on host (carried limitation).
- Desktop-prober 404 noise in backend logs (environmental).
- Traced `typescript` in standalone node_modules (inert, recorded).

## P10-2 handoff

CI design inputs: the Final P10-1 runtime contract above; gate commands
(`--validate`, `--source`/`--deployable`, `docker compose build
--no-cache`, arg-less frontend build must fail, 78-test matrix, identity
recheck reads); known environment needs (py3.11, Docker + Compose,
network-unless-cached); honest boundaries (arm64, bundle prerequisite,
no browser). Images retained locally for P10-2/P10-3 reuse (not deleted).

## Entry gate

- [x] baseline unchanged; nothing staged; inventory complete
- [x] PREEXISTING_OTHER_WORK untouched
- [x] source/deployable distinction explicit; bundle validates + identity
  recorded; determinism proven live
- [x] both preflights green; versions consistent; deps unchanged
- [x] Makefile audited; dockerignore dual-safe; secrets green
- [x] backend/frontend/compose contracts green; 2 services; no volumes;
  no infra; read-only+/tmp; localhost base; no DNS leak
- [x] no-cache builds green (2.86 GB / 553 MB, arm64, ~3 min)
- [x] missing-arg rejected; fresh start on new digests green
- [x] all 6 identities exact; 13-point workflow smoke green
- [x] restart/HIT green; network-off green; 2025 firewall green
- [x] content audit green; host prereqs documented; offline/arch claims
  bounded; browser limitation preserved
- [x] failure injection green; 78 tests green; firewall green; docs
  consistent; final contract written; containers stopped; P10-2 handoff
  explicit
