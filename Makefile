# Minimal developer command surface (R7). Transparent wrappers only —
# behaviour lives in pytest / npm scripts / uvicorn, never here.
PYTHON ?= python3

.PHONY: backend-dev frontend-dev test-python test-frontend typecheck lint build verify check-python

check-python:  ## Fail fast if PYTHON is broken/no-op (R8 finding: bare python3 shim exits 0 doing nothing)
	@test "$$( "$(PYTHON)" -c 'print("py-preflight-ok")' 2>/dev/null)" = "py-preflight-ok" || (echo "error: PYTHON='$(PYTHON)' is not a functional Python interpreter (probe produced no output). Override with e.g. 'make PYTHON=/path/to/python <target>'." >&2; exit 1)

backend-dev: check-python  ## Run the FastAPI backend with reload
	$(PYTHON) -m uvicorn api.main:app --reload --reload-dir api --reload-dir ml --port 8000

frontend-dev:  ## Run the Next.js frontend
	cd frontend && npm run dev

test-python: check-python  ## Backend + ML regression suite (needs requirements-test.txt)
	$(PYTHON) -m pytest tests/ -q

test-frontend:  ## Frontend node:test suites (no extra dependencies)
	cd frontend && node --test

typecheck:  ## Frontend TypeScript check
	cd frontend && ./node_modules/.bin/tsc --noEmit -p .

lint:  ## Frontend eslint
	cd frontend && npm run lint

build:  ## Frontend production build
	cd frontend && npm run build

verify: test-python test-frontend typecheck lint build  ## Full verification battery
