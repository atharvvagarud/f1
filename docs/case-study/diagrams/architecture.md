# System Architecture (D-ARCH)

Canonical high-level architecture of frozen F1 Intelligence v2.
Deployment is shown separately from the scientific flow.

```mermaid
flowchart TD
    HIST["Historical F1 data<br/>Tier B 1950-2025 metadata<br/>Tier A 2018-2025 FastF1 sessions"]
    HDP["Historical Data Platform<br/>173 terminal sessions<br/>171 COMPLETE / 2 PARTIAL"]
    TFE["Temporal Feature Engine<br/>exact-T clock, rival-state &lt;= T<br/>label firewall"]
    MODEL["Frozen Winner Model<br/>LogReg C=0.01 RAW ALL_84<br/>INDEPENDENT_BINARY"]
    RS["Factual RaceState at T<br/>roster + observations &lt;= T"]
    REPLAY["Replay<br/>149 races / 9644 exact checkpoints<br/>HIT-only cached predictions"]
    MC["Monte Carlo<br/>r3-v1 empirical params through 2024<br/>deterministic seed"]
    EXPL["Explainability<br/>LOG_ODDS decomposition<br/>associational, not causal"]
    STRAT["Strategy<br/>paired counterfactual compare<br/>never a recommendation"]
    API["FastAPI Surface<br/>/v2 races state predict replay<br/>simulate strategize explain"]
    UI["Next.js Frontend<br/>/ replay simulator strategy models about"]
    HIST --> HDP
    HDP --> TFE
    TFE --> MODEL
    TFE --> RS
    RS --> REPLAY
    RS --> MC
    MODEL --> REPLAY
    MODEL --> EXPL
    MC --> STRAT
    REPLAY --> API
    MC --> API
    STRAT --> API
    EXPL --> API
    API --> UI
```

```mermaid
flowchart LR
    BR["Browser"]
    FE["Next.js container<br/>node, non-root, read-only<br/>/tmp tmpfs"]
    BE["FastAPI container<br/>non-root, read-only<br/>/tmp tmpfs, network ingestion OFF"]
    BUNDLE["runtime_artifacts bundle<br/>1939 files, validated<br/>model + replay + params"]
    BR --> FE
    FE --> BE
    BUNDLE --> BE
```

Facts shown: data → feature → model/RaceState → replay/MC/explainability →
strategy → API → frontend; exactly two Compose services (LOCAL
DEPLOYABLE RUNTIME). Sources: P11-2 summary (scientific_identities,
runtime, containers), `about.v1.json` system semantics, P10-5 freeze
report. Not shown (not in v2): DB, Redis, Kafka, Celery, WebSockets,
MLflow, Kubernetes, cloud infrastructure.
