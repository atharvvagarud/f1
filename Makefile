# Minimal developer command surface (R7). Transparent wrappers only —
# behaviour lives in pytest / npm scripts / uvicorn, never here.
PYTHON ?= python3

.PHONY: backend-dev frontend-dev test-python test-frontend typecheck lint build verify check-python install-python install-python-test install-frontend install preflight preflight-source backend-prod frontend-start docker-backend-build docker-backend-run docker-frontend-build docker-frontend-run docker-compose-build docker-compose-up docker-compose-down docker-compose-logs ci-python ci-frontend ci science

check-python:  ## Fail fast if PYTHON is broken/no-op (R8 finding: bare python3 shim exits 0 doing nothing)
	@test "$$( "$(PYTHON)" -c 'print("py-preflight-ok")' 2>/dev/null)" = "py-preflight-ok" || (echo "error: PYTHON='$(PYTHON)' is not a functional Python interpreter (probe produced no output). Override with e.g. 'make PYTHON=/path/to/python <target>'." >&2; exit 1)

backend-dev: check-python  ## Run the FastAPI backend with reload
	$(PYTHON) -m uvicorn api.main:app --reload --reload-dir api --reload-dir ml --port 8000

frontend-dev:  ## Run the Next.js frontend
	cd frontend && npm run dev

test-python: check-python  ## Backend + ML regression suite (needs requirements-test.txt)
	$(PYTHON) -m pytest tests/ -q

test-frontend: check-python  ## Frontend Tier-1 suites via canonical selector (P10-4R selection)
	cd frontend && $(PYTHON) ../scripts/run_ci_frontend_tests.py

typecheck:  ## Frontend TypeScript check
	cd frontend && ./node_modules/.bin/tsc --noEmit -p .

lint:  ## Frontend eslint
	cd frontend && npm run lint

build:  ## Frontend production build
	cd frontend && npm run build

verify: test-python test-frontend typecheck lint build  ## Full verification battery

# ---- P10-1B runtime bootstrap (additive; no dev-target behaviour changed) ----
# Activate your desired Python 3.11 environment FIRST (e.g.
# `python3.11 -m venv .venv && source .venv/bin/activate`, or
# `make PYTHON=/path/to/python3.11 <target>`). These targets never sudo,
# install OS packages, generate science, download F1 data, prepare replay
# caches, modify env files, or start services.

install-python: check-python  ## Production Python deps (exact pins)
	$(PYTHON) -m pip install -r requirements.txt

install-python-test: check-python  ## Python deps + test-only deps
	$(PYTHON) -m pip install -r requirements.txt -r requirements-test.txt

install-frontend:  ## Reproducible frontend install (lockfile, NOT npm install)
	cd frontend && npm ci

install: install-python install-frontend  ## Python prod deps + frontend deps

preflight: check-python  ## DEPLOYABLE gate: source + runtime_artifacts + network-off
	$(PYTHON) scripts/check_runtime_environment.py --deployable

preflight-source: check-python  ## SOURCE gate: tracked declarations only (fresh clone)
	$(PYTHON) scripts/check_runtime_environment.py --source

backend-prod: check-python  ## Production backend (single process, no --reload)
	$(PYTHON) -m uvicorn api.main:app --host 0.0.0.0 --port 8000

frontend-start:  ## Serve the production frontend build (run build first)
	cd frontend && npm start

# ---- P10-1C backend container (additive; no target above changed) ----
# Canonical backend image workflow: host preflight (bundle validation +
# deployable gate) BEFORE docker build. Never generates science inside
# the image; the Dockerfile only merges the validated bundle.

docker-backend-build: preflight  ## Validate bundle + build backend image
	docker build -f Dockerfile.backend -t f1-intelligence-backend:p10-1c .

docker-backend-run:  ## Run the backend image (:8000, no network-ingestion flag)
	docker run --rm -p 8000:8000 f1-intelligence-backend:p10-1c

# ---- P10-1D frontend container (additive; no target above changed) ----
# NEXT_PUBLIC_API_BASE is build-time public config (not a secret) and MUST
# be passed explicitly; the Dockerfile fails closed without it.

docker-frontend-build:  ## Build frontend image (requires NEXT_PUBLIC_API_BASE=...)
	@test -n "$(NEXT_PUBLIC_API_BASE)" || (echo "error: NEXT_PUBLIC_API_BASE is required, e.g. 'make $@ NEXT_PUBLIC_API_BASE=http://localhost:8000'" >&2; exit 1)
	docker build -f Dockerfile.frontend --build-arg NEXT_PUBLIC_API_BASE="$(NEXT_PUBLIC_API_BASE)" -t f1-intelligence-frontend:p10-1d .

docker-frontend-run:  ## Run the frontend image (:3000)
	docker run --rm -p 3000:3000 f1-intelligence-frontend:p10-1d

# ---- P10-1E compose deployment (additive; no target above changed) ----
# Exactly two services (backend + frontend). No volumes: images carry baked
# artifacts, so up/down validates the real artifacts, not host leakage.

docker-compose-build: preflight  ## Deployable preflight, then compose build
	docker compose build

docker-compose-up:  ## Start the two-service deployment
	docker compose up -d

docker-compose-down:  ## Stop the deployment (no volumes to destroy)
	docker compose down

docker-compose-logs:  ## Tail both services
	docker compose logs --tail=100 backend frontend

# ---- P10-2 ordinary CI equivalents (additive; mirror .github/workflows/ci.yml) ----
# Source-contract gates only: never the deployable preflight (the ignored
# runtime_artifacts bundle is not a CI input), never Docker builds, never
# scientific generation. Activate a Python 3.11 environment first.

ci-python: check-python  ## CI python gate: source preflight + source-safe suite (P10-4R selection)
	$(PYTHON) scripts/check_runtime_environment.py --source
	$(PYTHON) scripts/run_ci_tests.py

ci-frontend: check-python install-frontend test-frontend typecheck lint  ## CI frontend gate: npm ci + source-safe tests (P10-4R) + tsc + lint + build
	cd frontend && NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run build && git diff --exit-code -- package-lock.json

ci: ci-python ci-frontend  ## Full ordinary CI equivalent

# ---- P11-1 Tier-3 full scientific regression (additive; NOT ordinary CI) ----
# make ci-python = Tier 1 source-safe engineering validation (clean-checkout
# safe; corpus-dependent + stale-debt nodes excluded via run_ci_tests.py).
# make science = Tier 3 corpus-backed scientific regression: the COMPLETE
# pytest suite with NO Tier-1 deselection (all 718 corpus-dependent nodes +
# all corrected former stale pins run). Requires the canonical ignored
# local scientific corpus; fails early via check_science_environment.py when
# it is absent. Never downloads, generates, retrains, or runs FastF1.
# Neither gate substitutes for the other.

science: check-python  ## Tier-3 full scientific regression (needs canonical corpus)
	$(PYTHON) scripts/check_science_environment.py
	$(PYTHON) -m pytest tests/ -q -p no:cacheprovider
