# F1 Intelligence — Frontend

Next.js product UI for F1 Intelligence: prediction, replay, simulator,
strategy, counterfactuals, consensus, uncertainty, spatial, and the
pit-wall workspace. It renders backend data; it never reconstructs
simulation or race-state logic (see `docs/FRONTEND_DESIGN_SYSTEM.md`
§18 for the semantics the visuals must not break).

## Development

Requirements: Node 22 (`engines` + `.nvmrc`), npm with the committed
lockfile. Install with `npm ci` (never `npm install`):

```bash
make install-frontend   # cd frontend && npm ci
```

Run from the repository root (frontend on `:3000`, backend on `:8000`):

```bash
make backend-dev    # uvicorn api.main:app with reload
make frontend-dev   # cd frontend && npm run dev
```

## Backend configuration

`NEXT_PUBLIC_API_BASE` is the public backend base URL captured by
`lib/http.ts` at module load (local fallback
`http://127.0.0.1:8000`). Production builds require it explicitly:

```bash
make docker-frontend-build NEXT_PUBLIC_API_BASE=http://localhost:8000
```

The value is browser-facing, so it must be host-reachable
(`http://localhost:8000` in compose) — never a Docker-internal host.

## Code map

- `app/` — Next.js routes (one directory per surface).
- `features/` — per-domain UI: components, hooks, view-models, tests.
- `components/` — shared shell/prediction/UI primitives.
- `lib/` — backend clients (`v2.ts`, `api.ts`, `spatial.ts`,
  `http.ts`) with `node --test` contract tests.
- `data/` — versioned static evidence (`about.v1.json`,
  `models.v1.json`) backing the Models/About surfaces.

## Checks

```bash
make test-frontend   # canonical Tier-1 frontend selector
make typecheck       # tsc --noEmit
make lint            # eslint
make build           # npm run build (production bundle)
```

## Further documentation

- Root `README.md` — product, capabilities, running, testing.
- `docs/development/DEVELOPMENT.md` — bootstrap, validation,
  Docker/Compose, generated artifacts.
