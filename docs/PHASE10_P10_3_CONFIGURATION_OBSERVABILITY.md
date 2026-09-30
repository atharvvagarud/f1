# PHASE 10 P10-3 CONFIGURATION + LIGHTWEIGHT OBSERVABILITY

Production hardening only: explicit serving configuration, meaningful
readiness distinct from liveness, lightweight request/runtime
observability. No infrastructure, no metrics/tracing backends, no
scientific behavior change.

## Final verdict

P10-3 COMPLETE — READY FOR P10-4. The backend serves behind explicit
configurable origins (safe local default, no wildcard), `/health` stays
cheap liveness while `/ready` validates frozen-runtime deployability
(cached, 503 on failure), every request emits one structured stdlib log
record, Compose health semantics moved to readiness, and all identities,
workflows, and gates remain green.

## Frozen baseline

- HEAD: `440f2a370aff56c799e69b65781199b158064fa0`
  (`440f2a3 feat(v2): freeze models and about phase 9`)
- Tag on HEAD: `v2-models-about-phase9` — matches, start to end.
- Serving model SHA: `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
- Winner semantics: `INDEPENDENT_BINARY`. Serving years: 2018–2024.
  2025: frozen holdout / not served.
- Nothing staged/committed/tagged/reset/restored/cleaned/stashed.

## Repository safety

- Start/end: HEAD/tag as above, `git diff --cached --stat` empty.
- Owned changes only: `api/config.py`, `api/readiness.py`,
  `api/observability.py` (new); `api/main.py`, `api/routes.py`,
  `compose.yaml` (small modifications); `tests/test_serving_config.py`,
  `tests/test_readiness.py`, `tests/test_request_observability.py` (new);
  `tests/test_v2_model_lab_p31.py`, `tests/test_compose_contract.py`
  (two owned contract-evolution assertions); this document (new).
- P10-0–P10-2 work and PREEXISTING_OTHER_WORK preserved untouched.
- `graphify update .` run first; graphify used for targeted orientation
  only (developer tooling, never a runtime input).

## Baseline behavior

Recorded before any code change (TestClient + live services):

- `GET /health` → 200 `{"status":"ok"}`.
- CORS preflight from `http://localhost:3000` →
  `access-control-allow-origin: *` (the wildcard debt).
- `GET /v2/races` → 200, 149 served races.
- `POST /v2/predictions/winner-snapshot` (2023-r01-R, max_verstappen,
  lap 1, t=3855.902) → 200, `INDEPENDENT_BINARY`.
- No scientific evaluation run.

## Configuration contract

`api/config.py` (stdlib only: `os`, `dataclasses`; no new dependency,
no `.env` loader; production config comes from the environment):

| Variable | Default | Invalid handling |
|---|---|---|
| `F1_ALLOWED_ORIGINS` | `http://localhost:3000` | set-but-empty (e.g. `",,,"`) → `ValueError` at startup (fail fast); never silently wildcard |
| `F1_LOG_LEVEL` | `INFO` | outside DEBUG/INFO/WARNING/ERROR/CRITICAL → `ValueError` at startup (fail fast) |

Parsing: split on comma, trim whitespace, discard empty entries,
preserve explicit scheme/host/port verbatim, deterministic, no regex.
Existing variables (`V2_PROJECT_ROOT`, `V2_ALLOW_NETWORK`,
`NEXT_PUBLIC_API_BASE`) unchanged and not renamed. No sprawling system:
one frozen `ServingConfig` dataclass plus two pure parse functions.

## CORS policy

- Default: `http://localhost:3000` only — `docker compose up` works
  with no env file; wildcard absent by default.
- Multiple origins: `F1_ALLOWED_ORIGINS=http://localhost:3000,https://example.invalid`.
- Explicit `"*"` is honored as a deliberate operator choice (credentials
  stay disabled, so FastAPI semantics remain clear); it is never
  produced silently from missing/malformed config.
- Credentials: `allow_credentials=False` (unchanged — the application
  has no credentialed browser sessions; verified against frontend
  workflows, which are unauthenticated reads/computes).
- Methods/headers remain `["*"]` (unchanged, not broadened).
- Verified live: localhost:3000 echoed on simple + preflight; unknown
  origin gets no allow-origin header (preflight → 400 rejection).

## Liveness contract

`GET /health` unchanged: static `{"status":"ok"}`, no artifact access,
no model load, no cache scan. Liveness only — it answers whether the
HTTP process is alive.

## Readiness contract

`GET /ready` (added in `api/routes.py`): 200 `ready` when the frozen V2
runtime can actually be served, else HTTP 503 `not_ready` with bounded
machine-readable per-check codes. `GET /health` can remain 200 while
`/ready` is 503 (proven by test). Response shape:

```json
{"status": "ready", "service": "f1-intelligence-v2",
 "model_sha_short": "1116b34f", "winner_semantics": "INDEPENDENT_BINARY",
 "serving_years": "2018-2024",
 "checks": {"serving_model": "ok", "replay": "ok",
  "explainability": "ok", "simulation": "ok",
  "processed_data": "ok", "network_policy": "ok"}}
```

No paths, no env values, no secrets, no tracebacks, no manifests.

## Readiness prerequisites

Minimum critical serving prerequisites, reusing existing
manifests/helpers (never duplicating identity logic):

1. Serving model: `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`
   exists + SHA-256 equals the frozen identity (17 KB hash; the constant
   is test-pinned equal to the source-preflight pin).
2. Replay: `results/v2_replay/phase8_e2_cache_manifest_v1.json` parses
   with `manifest_version`/`race_count` 149/`checkpoint_count` 9644 and
   manifest model SHA equal to the serving SHA; checkpoints dir exists.
3. Explainability: `results/v2_explainability/global_winner_logreg_v1.json`
   exists + `.sha256` sidecar matches (resolved via the existing
   `E3.default_artifact_path`, never re-derived).
4. Simulation: `data/v2/simulation/params/r3-v1__through-2024/manifest.json`
   parses with `parameter_set_id phase6-r3-empirical`, `through_season`
   2024 (dir resolved via the existing `parameter_storage_dir`).
5. Processed data: parquet partitions present per entity
   (`driver_lap_state_d9`, `results`, `races`) × season 2018–2024 —
   glob presence only, zero file reads (the 109 MB corpus is never
   loaded for readiness).
6. Network policy: `V2_ALLOW_NETWORK` is not `1`.

Readiness reads/stats/hashes/parses only. It never regenerates,
repairs, downloads, trains, loads models for inference, or evaluates.

## Readiness caching

`get_readiness()` validates once per process per project root
(`functools.lru_cache`, keyed by resolved root) and returns the cached
payload thereafter — repeated orchestrator polls cost microseconds
(first live call 3.7 ms, cached 0.3–0.4 ms). Root resolution honors
`V2_PROJECT_ROOT` (the container sets `/app`), giving tests clean
dependency injection. `reset_readiness_cache()` exists for tests only.

## Readiness failure semantics

Proven with temp roots/mocks (canonical artifacts untouched):
missing serving artifact, wrong SHA, missing replay manifest,
missing explainability artifact, missing simulation params, missing
processed partition, `V2_ALLOW_NETWORK=1` — each yields 503 with a
bounded code (`missing_artifact`, `sha_mismatch`, `missing_manifest`,
`manifest_invalid`, `model_identity_mismatch`, `missing_partition`,
`network_ingestion_enabled`) while `/health` stays 200.

## Compose health semantics

- Before P10-3: backend healthcheck = liveness (`/health`).
- After P10-3: backend healthcheck = deployable readiness (`/ready`);
  `GET /health` remains liveness. Frontend uses
  `depends_on: backend: condition: service_healthy`.
- Browser contract unchanged: `NEXT_PUBLIC_API_BASE=http://localhost:8000`.
- Backend environment now explicit: `F1_ALLOWED_ORIGINS`,
  `F1_LOG_LEVEL=INFO` (no `.env` file, no secrets).

## Logging contract

`api/observability.py` (stdlib `logging`/`json`/`time`; one
`BaseHTTPMiddleware`; no new dependency). One single-line JSON record
per completed request:

```json
{"event": "request_complete", "method": "GET", "path": "/v2/races",
 "status": 200, "duration_ms": 12.4}
```

Path prefers the matched route template
(`/v2/races/{race_id}/replay/predictions/{frame_index}`) for low
cardinality, else the exact path; query strings, request/response
bodies, headers, and cookies are never logged (structurally impossible:
the record has exactly five keys). `F1_LOG_LEVEL` sets the `f1.serving`
logger level (default `INFO`).

## Request-duration semantics

`duration_ms` is server-side REQUEST DURATION measured with
`time.perf_counter()` (monotonic). It is never labeled inference
latency — the span covers the whole request, not isolated inference.

## Error semantics

- 4xx (incl. legitimate 404/422 domain guardrails): completion at INFO.
- Unexpected 5xx: distinct ERROR record (`request_error` if unhandled,
  `request_complete` with 5xx status if converted downstream);
  tracebacks are not duplicated (uvicorn owns them); existing exception
  handling is untouched.

## Startup metadata

One lifespan startup record, safe fields only:

```json
{"event": "startup", "service": "f1-intelligence-v2",
 "log_level": "INFO", "allowed_origin_count": 1,
 "network_ingestion_enabled": false}
```

Per-request model/version injection deliberately omitted (noise);
`/ready` already carries the factual contract labels.

## Docker/Compose integration

- Backend image needs no Dockerfile change: `api/` is COPYed wholesale,
  so `config.py`/`readiness.py`/`observability.py` ride along.
- Non-root (UID 10001), read-only + `/tmp` tmpfs, network ingestion
  off — all re-verified inside the running Compose backend.
- Normal (cached-layer) rebuild green; `docker compose up` green;
  backend reaches `healthy` via `/ready`.
- In-container: `/health` 200, `/ready` 200 `ready`, serving SHA exact,
  `V2_ALLOW_NETWORK` unset, `F1_ALLOWED_ORIGINS`/`F1_LOG_LEVEL` as
  composed. Failure semantics come from unit tests, never from damaging
  the validated container.

## CI integration

No workflow/runner change needed: `scripts/run_ci_tests.py` collects
`tests/` automatically, so the 39 new P10-3 tests execute in ordinary
CI; all are source-safe (synthetic tmp roots, test-built apps, or
skip-guarded live checks). `make ci-python` (source preflight +
runner) is the local equivalent; source preflight green.

## Test evidence

- New: `tests/test_serving_config.py` (16: parsing + live CORS),
  `tests/test_readiness.py` (14, incl. 1 skip-guarded live),
  `tests/test_request_observability.py` (9) — 39 passed with bundle,
  source-safe subset passes without it.
- Owned contract evolutions (P10-3 scope, documented): P3.1 CORS test
  now pins explicit local origins instead of wildcard; Compose
  healthcheck test now pins `/ready` + `service_healthy` plus explicit
  backend env.
- Regression: P10 contract suites green; live TestClient + Compose
  smokes green — `/health`, `/v2/races` (149), one winner-snapshot
  (`INDEPENDENT_BINARY`), replay timeline + cached prediction (HIT),
  `LOG_ODDS` explanation, small simulation (10/10), small strategy
  (200), 2025 rejected (404 `unknown_race`) on factual + predictive
  paths.
- Container logs: structured records for every request incl. one 404
  probe; zero tracebacks; startup record factual.
- Performance sanity: 10× `/health` ≈ 1–3 ms steady; no formal
  benchmark (P11 owns measured performance).

## Scientific firewall

New/modified files contain no training, fit, FastF1 ingestion, feature/
label/matrix generation, replay generation, simulation parameter
generation, explainability generation, or 2025 evaluation (grep-clean).
Readiness performs hash/manifest/stat reads only. `requirements*.txt`
untouched — zero dependency changes.

## Security/privacy considerations

- Logs carry no bodies, query strings, headers, cookies, paths, env
  values, manifests, or secrets (five-key record, test-enforced).
- CORS narrowed from wildcard to explicit origins; credentials stay
  disabled; no secret required for any new variable.
- `/ready` leaks no filesystem paths (bounded failure codes only).

## Known limitations

- Readiness checks partition presence, not parquet validity (by design:
  content validation stays with the P10-1A validator + preflight).
- Unmatched paths log the exact path (no route template exists); no
  sensitive data is encoded in current route paths; query strings are
  still never logged.
- CORS preflight requests are answered by the outer CORS middleware and
  are not request-logged (real requests are).
- arm64-only container validation carries over from P10-1F.
- No browser engine on host (carried limitation); browser-origin HTTP
  behavior proven at protocol level via Origin/preflight assertions.

## P10-4 handoff

P10-3 owns no open items. P10-4 (clean-environment reproducibility,
NOT started) receives: explicit `F1_*` config surface with safe
defaults, `/ready` as the deployable gate (Compose already uses it),
structured request logs for diagnosing clean-env runs, and the
contract that `/health` 200 + `/ready` 503 means "alive but not
deployable". Do not reintroduce wildcard CORS to make any environment
green; diagnose exact origin behavior instead.

## Entry gate

- [x] baseline HEAD/tag unchanged; nothing staged
- [x] explicit serving config exists (`api/config.py`, stdlib only)
- [x] `F1_ALLOWED_ORIGINS` supported; safe local default; no wildcard
      by default; explicit `*` honored as operator choice; malformed
      config fails closed deterministically
- [x] `F1_LOG_LEVEL` supported; invalid values fail fast
- [x] `/health` remains cheap liveness
- [x] `/ready` exists; validates the six critical prerequisites with
      zero scientific regeneration; 503 with bounded codes on failure;
      200/503 health/readiness distinction proven; response bounded with
      no path/secret leaks; repeated calls cached in process memory
- [x] Compose healthcheck moved to `/ready`; frontend gated on
      `service_healthy`; browser base unchanged
- [x] request logging exists (method, route/path, status, duration_ms);
      query/bodies/headers never logged; generic duration never
      mislabeled inference latency; 4xx INFO, 5xx ERROR; factual startup
      record; request IDs deliberately omitted
- [x] CORS localhost:3000 works (simple + preflight); unknown origin
      rejected; multiple origins tested; no credentials
- [x] backend image rebuilds; non-root, read-only, network-off
      preserved; `/health` + `/ready` 200 in container; frozen SHA
      exact; all six workflows + 2025 firewall green in Compose; logs
      validated with zero tracebacks; responsiveness sanity normal
- [x] CI picks up new tests with no workflow change; P10 contract tests
      green; full CI-equivalent gate executed: 3184 collected
      (3127 + 17 P10-2 + 39 P10-3 + 1 compose-test split), 3163 passed,
      5 skipped, 12 deselected (documented stale pins), 4 xfailed,
      0 failed in 57:14
- [x] no dependency, frontend-product, or scientific behavior changes;
      firewall + privacy audits green; unrelated work untouched;
      nothing committed/tagged
- [x] documentation complete; P10-4 handoff explicit
