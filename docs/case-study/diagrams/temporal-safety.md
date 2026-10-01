# Temporal Safety (D-TEMP)

The core scientific constraint: at race time T the model may only see
what was observable at or before T.

```mermaid
flowchart LR
    PAST["past<br/>facts observed &lt;= T<br/>pre-race priors<br/>latest valid rival obs &lt;= T"]
    T["T<br/>exact LAP_END clock<br/>feature boundary"]
    FUT["future<br/>FORBIDDEN"]
    PAST --> T
    T --> FUT
```

```mermaid
flowchart TD
    AVAIL["AVAILABLE at T<br/>facts observed at or before T<br/>pre-race information<br/>latest valid rival observations &lt;= T"]
    FORB["FORBIDDEN<br/>future laps<br/>future pit events<br/>future race-control events<br/>final result and status<br/>labels in predictive inputs<br/>2025 holdout for serving and training"]
    GUARD["Guards<br/>no fall-forward<br/>exact replay checkpoints only<br/>labels side-channel only<br/>2025 firewall: 404 unknown_race<br/>chronological folds D1-D3"]
    AVAIL --> GUARD
    FORB --> GUARD
```

Facts shown: exact-T boundary, ≤T rival sync, label firewall,
no fall-forward, exact checkpoints, 2025 holdout firewall. Sources:
P11-2 summary (temporal_safety, 10 invariants EXECUTED),
`PHASE2_TEMPORAL_SEMANTICS.md`, `PHASE2_LEAKAGE_PARITY_AUDIT.md`,
D11 adversarial suite. Limitation: evidence wording is "no leakage
detected", never "zero leakage guaranteed".
