# PHASE 10 P10-1D FRONTEND CONTAINER

Containerization only. No frontend redesign, no route/behavior change, no
evidence change, no dependency change, no CORS change, no reverse proxy, no
scientific change. P10-1C backend untouched. No compose, no CI (P10-1E and
later, NOT started).

## Final verdict

P10-1D COMPLETE — READY FOR P10-1E. The production frontend image
`f1-intelligence-frontend:p10-1d` builds reproducibly on Node 22
(bookworm-slim, multi-stage standalone runner, 553 MB, arm64), requires an
explicit browser-reachable `NEXT_PUBLIC_API_BASE` at build time (fails
closed without it), serves all routes on port 3000 as non-root, renders
frozen /models + /about evidence byte-faithful, and drives representative
prediction / replay / simulation / strategy workflows against the frozen
P10-1C backend with no console, CORS, or asset failures observable at the
protocol level.

## Frozen baseline

- HEAD: `440f2a370aff56c799e69b65781199b158064fa0`
  (`440f2a3 feat(v2): freeze models and about phase 9`)
- Tag on HEAD: `v2-models-about-phase9` — matches.
- Nothing staged at start or end; P10-0–P10-1C work and
  PREEXISTING_OTHER_WORK preserved.

## Repository safety

- Start: HEAD/tag as above, `git diff --cached --stat` empty.
- End: HEAD/tag unchanged, nothing staged/committed/tagged/reset/
  restored/cleaned/stashed (verified).
- Owned changes only: `Dockerfile.frontend` (new),
  `frontend/next.config.ts` (+`output: "standalone"` + comment),
  `.dockerignore` (frontend exclusion refined, backend patterns intact),
  `Makefile` (two additive targets + two `.PHONY` names),
  `tests/test_frontend_container_contract.py` (new, 13 tests),
  this document (new).

## Docker environment

- Client: Docker 29.8.0; Server/engine: 29.8.0; arch: aarch64 (arm64,
  Apple Silicon, native build — no cross-platform claim). Re-recorded,
  not assumed.

## API base semantics

- Only two consumers, both module-load constants with localhost fallback:
  `frontend/lib/api.ts:1`
  (`const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000"`)
  and `frontend/lib/v2.ts:12` (same shape, `V2_API_BASE`).
- All API calls originate from `"use client"` components; no `route.ts`
  handlers exist; no `fetch(` in `app/` server components or the
  models/about feature trees. So the inlined build-time value is what the
  browser uses; no server-runtime fetch needs the var (runner carries none).
- `NEXT_PUBLIC_API_BASE` is PUBLIC configuration, intentionally embedded
  in client chunks (verified inlined `http://localhost:8000` in served JS).
  It is not a secret.
- `http://backend:8000` was NOT baked in: Docker DNS is meaningless to a
  host browser. P10-1D validation used `http://localhost:8000` with the
  frontend on `localhost:3000`. Compose naming is P10-1E's problem.

## Frontend image design

`Dockerfile.frontend` (root, matching the `Dockerfile.backend`
convention), three stages on `node:22-bookworm-slim` (debian slim chosen
over alpine for build predictability):

1. `deps`: `COPY frontend/package.json frontend/package-lock.json` +
   `npm ci` (371 added / 372 audited, ~7 s; no install, no lockfile churn —
   verified byte-identical afterwards via the gate `npm ci`).
2. `builder`: `ARG NEXT_PUBLIC_API_BASE` → `ENV NEXT_PUBLIC_API_BASE`,
   fail-closed `test -n` guard, `COPY frontend/`, `npm run build`
   (no backend running; /models + /about prerender from checked-in
   `frontend/data/*.v1.json`).
3. `runner`: `.next/standalone` + `.next/static` + `public` only,
   `NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0`, chowned to the
   image's existing `node` user, `EXPOSE 3000`,
   exec-form `CMD ["node", "server.js"]`. No nginx, no Python, no backend.

## Dependency stage

Exact locked install per P10-1B (`npm ci`, never `npm install`); root
manifests never copied; no versions changed (`engines >=22 <23` honored —
image reports Node 22.23.3, same LTS line as validated 22.23.1).

## Build configuration

`ARG NEXT_PUBLIC_API_BASE` + builder `ENV` + pre-build `test -n` guard.
Missing/empty arg fails the build in <1 s with
`NEXT_PUBLIC_API_BASE is required` (proven by negative test; no image
produced). `make docker-frontend-build` enforces the same at the Make
level (`NEXT_PUBLIC_API_BASE=...` required).

## Next output strategy

`output: "standalone"` was NOT previously enabled. Enabled in
`frontend/next.config.ts` (build-packaging only) and validated: identical
7-route table (`/`, `/about`, `/models`, `/replay`, `/simulator`,
`/strategy`, all static), frontend 197/197 + tsc + lint green, prerendered
evidence HTML present, runner 553 MB with a 72 MB traced-minimal
`node_modules` (next/react/sharp/swc; no eslint/test deps). Correctness
held, so standalone stays. Measured benefit: no full-`node_modules`
(491 MB) or source tree in the final stage.

## Dockerignore

Decision: root context kept (P10-1E-compatible), blanket `frontend/`
exclusion replaced with `frontend/node_modules/` + `frontend/.next/`
(`frontend/.env.local` stays excluded via explicit line + `.env.*`).
Backend contract verified intact by test (all `data/*`, `.fastf1_cache`,
secret, and tooling patterns still present; `runtime_artifacts/` still
unmatched) and by the untouched backend image.

## Secret safety

- Image: no `.env.local`, no root `.env`, no `.git`, no backend/scientific
  files, no key-name env entries (filename + env scan; values never
  printed). Local `.env.local` sets only `NEXT_PUBLIC_API_BASE` (public)
  and never entered the build — the builder used the build-arg; `npm run
  build` had no `.env.local` to read.
- NOTICE: the standalone `node_modules` contains a traced `typescript`
  package (Next server dependency, inert) — recorded, not a secret, not
  pruned per no-slimming policy.

## Build evidence

- `docker build -f Dockerfile.frontend --build-arg
  NEXT_PUBLIC_API_BASE=http://localhost:8000 -t
  f1-intelligence-frontend:p10-1d .` green, zero errors.
- Image: 553 MB, `arch=arm64`, `User=node`, `WorkingDir=/app`,
  `Cmd=["node","server.js"]`, `ExposedPorts={3000/tcp}`.
- `make docker-frontend-build NEXT_PUBLIC_API_BASE=...` verified green;
  without the var it fails with the documented error.

## Missing-argument negative test

Build without `--build-arg` fails at the guard step
(`test -n "" → NEXT_PUBLIC_API_BASE is required`, exit 1); tag
`f1-intelligence-frontend:neg-test` does not exist afterwards. Production
builds cannot silently inherit the localhost fallback.

## Image content audit

Present: `server.js`, traced `node_modules` (72 MB), `.next/static`,
`public/`, prerendered HTML+RSC for all 6 routes (+ `_not-found`,
`_global-error`). Absent: env files, `.git`, tests, `api/`, `v2/`, `ml/`,
`data/`, `results/`, `runtime_artifacts/`, `docs/`, Python, root JS
manifests, dev dependencies. Inlined API base confirmed in served chunks;
all V2 endpoint families (`v2/races`, `v2/replay/`, `v2/simulations/race`,
`v2/strategies/compare`) present in client bundles.

## Image size

553 MB final (vs 682 MB host `frontend/` with dev `node_modules` +
stale `.next`). No arbitrary target; no pruning undertaken.

## Frontend route smoke

Frontend-only container (`:3000`): `/` 200, `/replay` 200, `/simulator`
200, `/models` 200 (204 KB), `/about` 200 (139 KB), `/strategy` 200.
All 13 referenced `_next/` assets return 200 (zero 404s).

## Static evidence smoke

- `/models` HTML contains `INDEPENDENT_BINARY`, `LogisticRegression`,
  `1116b34f` (serving SHA prefix), `84` (feature count), 2018–2024 —
  frozen production identity renders, not just 200.
- `/about` HTML contains race-state, architecture, simulation, strategy,
  replay, and Monte Carlo evidence topics. Nothing recomputed.

## Backend integration

Frozen `f1-intelligence-backend:p10-1c` on `localhost:8000` + frontend
(built with `NEXT_PUBLIC_API_BASE=http://localhost:8000`) on
`localhost:3000` run together; browser-facing JS resolves the backend
through host localhost. No Docker DNS in the API base, no proxy.

## Prediction workflow

Client bundle issues `GET /races` + `POST /predict/single-model`
(verified strings); executed exactly so: races 200, 2019-Australia/logreg
prediction 200. Root SSR shell carries the interactive controls; race data
loads client-side from the configured base. Independent-binary semantics
live backend-side and are unrelabeled by the frontend (no product change).

## Replay workflow

`timeline` 200 → cached `predictions/0` 200 → `explanation`
(max_verstappen frame 0) 200. Timeline/frame/driver/explanation endpoint
families all present in served chunks.

## Simulator workflow

`POST /v2/simulations/race` (2022-r01-R perez lap-30 anchor, count 10) →
200 through the configured backend. No benchmark.

## Strategy workflow

Strategy lives in its own `/strategy` route (200) and API family
(`v2/strategies/compare` in bundles). `POST` (perez target,
MAXIMIZE_WIN_PROBABILITY, 100 sims = schema minimum, STAY_OUT) → 200 with
baseline + candidate. No new route invented.

## Browser console

No browser engine exists on this machine (no chromium/playwright/e2e
harness) and none was added per the no-new-framework rule. Protocol-level
substitute, all green: zero non-200 page/asset responses (13/13 assets
200), CORS preflights from `http://localhost:3000` return `*` for V1 and
V2 POST routes, every workflow API call returns 200 with contract-shaped
bodies, and all routes prerendered statically with zero build warnings.
Wildcard CORS left unchanged for P10-3. Full console/hydration observation
is an environment limitation, explicitly recorded — P10-1E (compose +
real browser) is the natural place to close it.

## Responsive smoke

Same constraint as above (no layout engine). By-construction case:
exactly one product file changed (`next.config.ts`, output mode only —
no tsx/css/asset touched; `git status` proves it), viewport meta present,
and standalone emits identical `.next/static` CSS/JS. No overflow
regression is constructible from this diff. Real 1440/390 rendering also
deferred to P10-1E's browser stage.

## Read-only runtime

`docker run --read-only --tmpfs /tmp` → `/` 200, `/models` 200. `/tmp`
tmpfs is the documented minimum; nothing else writable.

## Makefile surface

Added (previous targets untouched): `docker-frontend-build`
(requires `NEXT_PUBLIC_API_BASE=...`, fails with usage error otherwise)
and `docker-frontend-run` (`--rm -p 3000:3000`, no hidden env). Both
exercised.

## Test evidence

- `tests/test_frontend_container_contract.py` (13 new): Node 22
  multi-stage, `npm ci` (no install), frontend-only manifests, explicit
  arg + missing-arg guard, port/env/CMD, non-root, no backend/science
  copies, no env copies, dockerignore keep/protect, standalone contract,
  backend-Dockerfile-unchanged, scientific firewall.
- Python gate: P10-1A (12) + P10-1B (22) + P10-1C (12) + P10-1D (13) =
  **59 passed**.
- Frontend gate: `npm ci` clean, `node --test` **197 pass / 0 fail**,
  `tsc --noEmit` clean, `eslint` clean, `npm run build` green (7 static
  routes, standalone emitted).
- Full scientific Python suite: NOT run (only `next.config.ts` changed
  outside docs/tests/Dockerfiles — no shared app/science file).

## Backend regression boundary

`Dockerfile.backend` byte-untouched (no frontend references; verified by
contract test); backend image unchanged. Minimal regression on the live
pair: `/health` → `{"status":"ok"}`, `/v2/races` → 200. No endpoint
repetition needed.

## Scientific firewall

P10-1D changes contain no Python builders, evidence regeneration, FastF1,
training, model loading, 2025 evaluation, or parameter generation
(test-enforced over the Dockerfile). The image consumes checked-in
`frontend/data/*.v1.json` as frozen bytes (`models.v1.json`,
`about.v1.json`).

## Known limitations

- arm64-only; no multi-arch publishing.
- Image Node patch 22.23.3 vs validated 22.23.1 (same LTS line, locked
  npm tree).
- Console/hydration/responsive checks are protocol/by-construction level
  only — no browser engine on this host; P10-1E should close with a real
  browser.
- `typescript` rides in the traced standalone `node_modules` (inert).

## P10-1E handoff

Compose-stage inputs frozen: backend `f1-intelligence-backend:p10-1c`
(:8000, `/health` liveness), frontend `f1-intelligence-frontend:p10-1d`
(:3000, built with an explicit browser-reachable base). Open P10-1E
decisions: compose service naming (must NOT leak into browser API base —
keep a localhost-reachable base or introduce proxy architecture
deliberately), real-browser console/responsive closure, CORS stays
wildcard until P10-3.

## Entry gate

- [x] Docker engine available (29.8.0, arm64)
- [x] Node 22 image (`node:22-bookworm-slim`, 22.23.3)
- [x] `npm ci`, versions + lockfile unchanged
- [x] explicit `NEXT_PUBLIC_API_BASE` build contract; missing-arg build fails
- [x] browser-facing base semantics correct (localhost, no Docker DNS)
- [x] production build green; non-root (`node`); port 3000; no proxy
- [x] no env files/secrets/backend/science in image
- [x] `/`, `/replay`, `/simulator`, `/models`, `/about` (+`/strategy`) 200
- [x] frozen evidence renders on /models + /about
- [x] backend + frontend run together; prediction/replay/explanation/
  simulator/strategy workflows 200
- [x] CORS preflights pass; zero failed assets/pages at protocol level
- [x] responsive by-construction (one build-config file changed)
- [x] read-only green (`--tmpfs /tmp`); image size recorded (553 MB)
- [x] P10-1A + P10-1B + P10-1C + P10-1D tests green (59); frontend 197
  green; tsc/lint/build green; backend health + /v2/races green
- [x] no scientific regeneration; no product/science behavior changed;
  unrelated work untouched; nothing staged/committed/tagged
- [x] P10-1E handoff explicit
