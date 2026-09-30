# PHASE 10 P10-1E COMPOSE + END-TO-END RUNTIME VALIDATION

Deployment integration only. Exactly two containers; no databases, queues,
proxies, observability, CI, readiness, or CORS changes. No scientific,
product, model, or dependency changes. No Dockerfiles modified. P10-1F NOT
started.

## Final verdict

P10-1E COMPLETE — READY FOR P10-1F. `compose.yaml` (backend + frontend
only) builds from the frozen Dockerfiles after deployable preflight,
starts with one command, serves every route, preserves all scientific
identities, drives prediction / replay / explanation / timeline-change /
simulation / strategy workflows end-to-end under read-only filesystems,
rejects 2025 on both factual and predictive paths, survives restart and
full down/up without rebuild, and shuts down cleanly.

## Frozen baseline

- HEAD: `440f2a370aff56c799e69b65781199b158064fa0`
  (`440f2a3 feat(v2): freeze models and about phase 9`)
- Tag on HEAD: `v2-models-about-phase9` — matches.
- Nothing staged at start or end; P10-0–P10-1D and PREEXISTING_OTHER_WORK
  preserved.

## Repository safety

- Start/end: HEAD/tag as above, `git diff --cached --stat` empty.
- Owned changes only: `compose.yaml` (new), `Makefile` (four additive
  compose targets + four `.PHONY` names), `tests/test_compose_contract.py`
  (new, 13 tests), this document (new).

## Docker/Compose environment

- Client: Docker 29.8.0; engine: 29.8.0; Compose: v5.5.1; arch: aarch64
  (arm64, Apple Silicon — re-recorded, native only).

## Compose architecture

`compose.yaml` (modern spec, no `version:`): service `backend` builds
`Dockerfile.backend` (:8000, `V2_PROJECT_ROOT=/app`, liveness
healthcheck, read-only + `/tmp` tmpfs, `no-new-privileges`) and service
`frontend` builds `Dockerfile.frontend` with
`NEXT_PUBLIC_API_BASE=http://localhost:8000` (:3000, `depends_on:
backend` as ordering-only, read-only + `/tmp` tmpfs,
`no-new-privileges`). No volumes, no bind mounts, no command overrides,
no third service, no secrets.

## Backend service

Frozen P10-1C contract: same Dockerfile/CMD/port, `V2_ALLOW_NETWORK`
absent (not merely unset-in-effect — absent from resolved config),
healthcheck explicitly LIVENESS ONLY via stdlib python (no curl added).

## Frontend service

Frozen P10-1D contract: same Dockerfile/CMD/port, build arg
`http://localhost:8000`. Browser is outside Docker DNS, so backend-DNS
was never an option.

## API base contract

Build arg `http://localhost:8000`; served chunks contain it (3 chunk
files); zero `http://backend:8000` occurrences in the served static
tree (proven by inspecting built output, not YAML).

## Startup semantics

`depends_on` is ordering/convenience only — `/health` is liveness, never
claimed as readiness (no fake semantics before P10-3). The frontend
tolerates backend timing as before. Backend healthcheck reaches `healthy`.

## Read-only filesystem

`read_only: true` + `tmpfs: [/tmp]` on BOTH services, retained: every
workflow in this stage (all smokes, all 6 workflows, restart, down/up)
ran under it. No additional writable path needed. `no-new-privileges`
caused zero behavior change (proven by the same green workflows).

## Build evidence

- `check_runtime_environment.py --deployable` → OK (reuses P10-1A
  validator; no regeneration).
- `docker compose build` → both images built, zero errors.
- `docker compose config` → resolved cleanly; `--services` returns exactly
  `backend`, `frontend`. No secret values in resolved output.

## Service count

`docker compose config --services` → 2 lines: backend, frontend. No
hidden infrastructure. Contract test enforces the same statically.

## Host HTTP smoke

All 200: backend `/health`, `/v2/races`; frontend `/`, `/replay`,
`/simulator`, `/strategy`, `/models`, `/about`.

## Static evidence

Through the Compose frontend: /models renders `INDEPENDENT_BINARY`,
`LogisticRegression`, serving SHA `1116b34f`, 84 features, 2018–2024;
/about renders `FACT`, `PREDICTION`, `SIMULATION`, `STRATEGY`,
architecture topics. No regeneration.

## Artifact identity

Inside the running Compose backend (hash reads, no recomputation):
joblib `1116b34f…fcaa59f4` ✓, explainability `bae84b61…982939f` ✓,
replay 149 / 9644 / `78a3c059…98` ✓, simulation `phase6-r3-empirical` /
through 2024 ✓.

## CORS

OPTIONS preflight from `http://localhost:3000` → `access-control-allow-origin:
*` on V1 + V2 POST routes; origin-bearing POST succeeds. Frozen wildcard
unchanged; hardening stays P10-3.

## Prediction workflow

Frontend loads → races load (200) → 2019-Australia/logreg prediction 200
(5 laps, BOT). `INDEPENDENT_BINARY` wording lives backend-side,
unrelabeled (no product change).

## Replay workflow

/replay 200 → timeline 200 → checkpoint prediction 200 + `HIT` (no 503)
→ driver-scoped explanation 200 (`LOG_ODDS`, `INDEPENDENT_BINARY`).

## Timeline change

Frame-0 change honestly reports `NO_PREVIOUS_CHECKPOINT`; frame 1 is not
a prediction checkpoint (structured 404 naming frames 0/20 — frozen
contract, not a defect); frame-20/max_verstappen change → 200
`AVAILABLE`, `LOG_ODDS`, deltas present, limitations state the
associational-not-causal semantics verbatim.

## Simulator workflow

2022-r01-R perez lap-30 anchor, count 10 → 200, 10/10 valid,
`phase6-r3-empirical`. No benchmark.

## Strategy workflow

perez target, MAXIMIZE_WIN_PROBABILITY, 100 sims, STAY_OUT → 200 with
baseline + 1 candidate. Response contains none of BEST / RECOMMENDED /
OPTIMAL.

## 2025 firewall

`2025-r01-R` → 404 `unknown_race` on BOTH the factual state path and the
winner-snapshot path. No evaluation run.

## Browser availability

Searched without installing anything: no Chrome/Chromium/Edge/Firefox
apps, no playwright/selenium/puppeteer modules or caches, no project e2e
harness. `safaridriver` exists as a macOS binary but driving it needs new
bindings plus a user Safari settings change — not an already-available
capability. Result: NOT EXECUTABLE — NO EXISTING BROWSER AUTOMATION
AVAILABLE (recorded, not passed).

## Browser console/hydration

NOT EXECUTABLE — NO EXISTING BROWSER AUTOMATION AVAILABLE. Substitute
evidence (all green): 8/8 pages 200, 13/13 assets 200, CORS preflights
pass, all workflow APIs 200 with contract bodies, zero-error static
prerender, backend logs free of tracebacks. No console pass claimed.

## Responsive validation

NOT EXECUTABLE — NO EXISTING BROWSER AUTOMATION AVAILABLE. Standing
P10-1D by-construction case unchanged (no product file changed in P10-1E
at all — compose/Makefile/tests/docs only). No pass claimed.

## Container logs

Backend: uvicorn access lines only; zero tracebacks/errors/ingestion
mentions. Five 404s are Docker Desktop's own prober hitting `/` and
`/favicon.ico` (backend has no such routes; source IP is the desktop
gateway, not app traffic). Frontend: clean `Ready`. No permission or
write failures under read-only.

## Restart validation

`docker compose restart` → health 200, frontend 200, replay prediction
200 + HIT. No regeneration, no volumes.

## Down/up validation

`docker compose down` (network + containers removed) →
`docker compose up -d` WITHOUT rebuild → health 200, frontend 200,
replay 200 + HIT. Image-contained resources proven.

## Network-off validation

`V2_ALLOW_NETWORK` absent inside Compose backend (exec → `None`); logs
contain zero FastF1/ingestion evidence; no external calls made.

## Resource observation

Snapshot only, not a benchmark: backend ~1 GB RSS (in-memory corpus),
~0.3% CPU idle; frontend ~36 MB, 0.00% CPU idle. No optimization
undertaken.

## Makefile surface

Added (previous targets untouched): `docker-compose-build` (preflight →
`docker compose build`), `docker-compose-up`, `docker-compose-down`,
`docker-compose-logs`. Exercised via direct `docker compose` equivalents;
targets are thin wrappers over the same commands.

## Test evidence

- `tests/test_compose_contract.py` (13 new, stdlib-only): exactly 2
  services, correct Dockerfiles, ports, localhost base, no backend-DNS
  leak, network-off, no volumes/mounts, read-only + tmpfs ×2, no command
  overrides, liveness-only healthcheck, Dockerfiles intact, firewall.
- Python gate: 12 + 22 + 12 + 13 + 13 = **72 passed**.
- Frontend 197 NOT re-run: no frontend build inputs changed since the
  P10-1D gate (compose/Makefile/tests/docs only); both production images
  built green through Compose instead, which is the required proof.
- Full scientific suite: NOT run (no shared app/science file changed).

## Scientific firewall

`compose.yaml` + compose Make targets contain no training, fitting,
FastF1, matrix/replay/sim/explainability generation, or 2025 evaluation
(test-enforced). Startup regenerates nothing (restart/down-up HITs
prove it).

## Known limitations

- arm64-only; no browser engine on host (console/responsive honestly
  not-executable — P10-1F cannot close these either without a browser;
  flagging for P10-4 or manual QA).
- Backend ~1 GB idle RSS (corpus) — descriptive, not a finding.
- Desktop prober 404 noise in backend logs (environmental, documented).

## P10-1F handoff

Reproducibility-audit inputs: `compose.yaml` (2 services, read-only,
no volumes), both Dockerfiles frozen, `.dockerignore` refined once
(frontend source access; backend patterns intact), Make targets
`docker-backend-build`, `docker-frontend-build` (arg-enforced),
`docker-compose-build/up/down/logs`. Open: browser-based validation
still needs an engine; CORS/readiness/observability belong to P10-3.

## Entry gate

- [x] Docker + Compose available (29.8.0 / v5.5.1 / arm64)
- [x] compose.yaml, exactly 2 services, frozen image contracts
- [x] browser base localhost:8000, no backend-DNS leak, ports correct
- [x] no DB/Redis/worker/proxy/volumes; network ingestion off
- [x] read-only + minimal tmpfs retained; preflight/build/config green
- [x] all 8 host smokes 200; frozen evidence renders
- [x] all 4 artifact identities exact; all 6 workflows green
- [x] 2025 rejected on factual + predictive paths; CORS supports product
- [x] browser availability investigated (not-executable, honestly recorded)
- [x] logs clean of failures; restart + down/up green; no regeneration
- [x] 2 services proven; resources recorded; 72 Python tests green
- [x] no science/app changes; nothing staged/committed/tagged
- [x] P10-1F handoff explicit
