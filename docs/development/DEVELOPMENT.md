# Development Guide

Operational companion to the portfolio-oriented root README. Versions,
commands, and boundaries for working in this repository. Scientific and
product behavior are frozen; this guide changes nothing about them.

## Runtime versions

Python **3.11** (system `python3` may be a non-functional shim or a wrong
version — always verify first), Node **22**, Docker + Compose. Tier-3
science additionally needs the canonical local corpus (`data/v2/`).

## Bootstrap

```bash
python3.11 -m venv .venv && source .venv/bin/activate
make PYTHON=/path/to/python3.11 install-python-test   # exact pins + test deps
make install-frontend                                  # reproducible npm ci
```

If `PYTHON` is unset, `make` uses `python3`; every Python target starts
with `check-python`, which fails fast on a broken interpreter. Use
`make PYTHON=<venv-python> <target>` when unsure.

## Backend / frontend start

```bash
make backend-dev     # uvicorn api.main:app with reload (api/ + ml/)
make backend-prod    # single-process uvicorn, no reload
make frontend-dev    # cd frontend && npm run dev
make frontend-start  # serve the production build (run make build first)
```

## Validation

```bash
make preflight-source   # tracked-declarations gate (fresh-clone safe)
make preflight          # deployable gate: source + bundle + network-off
make ci                 # ordinary source-safe CI (Python + frontend)
make verify             # pytest + node tests + tsc + lint + build
make science            # Tier-3 full regression (corpus required, ~1 h)
```

`make ci` = `ci-python` (source preflight + `scripts/run_ci_tests.py`,
collection pinned at 3210) + `ci-frontend` (`npm ci` + source-safe node
tests + `tsc` + `lint` + production `build`). Never substitute Tier-1
green for Tier-3 science.

## Runtime bundle + Docker/Compose

```bash
python scripts/prepare_runtime_artifacts.py --validate
make docker-compose-up      # backend :8000, frontend :3000
curl localhost:8000/ready
make docker-compose-down
```

Single-service variants: `docker-backend-build/run`,
`docker-frontend-build/run` (frontend build requires
`NEXT_PUBLIC_API_BASE=...`), `docker-compose-build`.

## Regeneration utilities (intentionally supported)

```bash
python scripts/build_replay_prediction_cache.py  # replay checkpoints (needs source inputs)
python scripts/build_simulation_parameters.py    # simulation params (provenance in raceintel/simulation/)
python scripts/build_phase9_evidence.py          # Models/About evidence dossiers
python scripts/run_p11_performance_benchmark.py  # P11 latency evidence (JSON kept)
```

One-off benchmark/validation scripts from frozen phases are historical
tooling (runnable from history, not part of current workflows). V1-era
workflow scripts were archived outside the repo (see
`results/post_v2_consolidation/c1_v1_archive_record.json`).

## Generated artifacts (local-only, never commit)

`runtime_artifacts/`, `results/v2_replay/`,
`results/v2_explainability/`, `data/v2/`, `data/raw/fastf1_cache/`,
`.fastf1_cache/`, `.venv/`, `frontend/.next`, `frontend/node_modules`,
`graphify-out/`. All covered by `.gitignore`. Local tool state
(`.opencode/`, `.impeccable/`) is likewise ignored, never a repo
requirement.

## Repository navigation (Graphify-first)

This project keeps a knowledge graph at `graphify-out/` (regenerable,
ignored). For codebase questions, run `graphify query "<question>"`
first; use `graphify path "<A>" "<B>"` for relationships. Run
`graphify update .` after code changes. See `AGENTS.md` for the full
agent execution policy (long-command handling, no fixed sleeps).
