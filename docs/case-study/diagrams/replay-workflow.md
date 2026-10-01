# Historical Replay Workflow (D-REPLAY)

```mermaid
flowchart LR
    SEL["race selection<br/>149 served races<br/>2018-2024"]
    CKPT["exact checkpoint<br/>9644 checkpoints<br/>no snapping"]
    RS["RaceState at T"]
    FEAT["temporal feature vector<br/>ALL_84"]
    CACHE["cached frozen prediction<br/>HIT only"]
    EXPL["local explanation<br/>LOG_ODDS"]
    CHG["timeline change<br/>vs previous checkpoint"]
    UI["frontend replay panel"]
    SEL --> CKPT
    CKPT --> RS
    RS --> FEAT
    FEAT --> CACHE
    CACHE --> EXPL
    CACHE --> CHG
    EXPL --> UI
    CHG --> UI
```

Facts shown: 149 races, 9644 checkpoints, HIT-only exact checkpoints,
cached prediction p50 ≈1.0 ms container. Null semantics: 3206 null
checkpoints are served as null (`NO_OBSERVATION_AT_SNAPSHOT`), never
substituted — not every lap/driver has a prediction. 2025 races refuse
with 404 `unknown_race`. Sources: P11-2 summary (replay, firewall2025),
E2 manifest, P11-3 benchmark (B4a/B4b).
