# Deployment — Local Deployable Runtime (D-DEPLOY)

No cloud infrastructure exists. No production cloud deployment is implied.

```mermaid
flowchart TD
    BR["Browser<br/>http://localhost:3000"]
    FE["Next.js container<br/>node:22, UID 1000 node<br/>read-only rootfs, /tmp tmpfs"]
    BE["FastAPI container<br/>python:3.11, non-root appuser<br/>read-only rootfs, /tmp tmpfs<br/>network ingestion OFF"]
    BUNDLE["runtime_artifacts bundle<br/>runtime-artifacts-v1<br/>1939 files, validated, ignored"]
    HEALTH["GET /health — liveness only"]
    READY["GET /ready — 6 deployability checks"]
    BR --> FE
    FE --> BE
    BUNDLE --> BE
    BE --> HEALTH
    BE --> READY
```

Exactly two Compose services (backend + frontend). No volumes/bind
mounts, no secrets, no DB/Redis/worker/proxy. CORS: explicit
`http://localhost:3000` only, no wildcard. Observability: one
`request_complete` record per request (method, templated path, status,
endpoint duration only). Sources: P11-2 summary (containers, runtime,
health_readiness, observability, cors), P10-5 freeze report.
