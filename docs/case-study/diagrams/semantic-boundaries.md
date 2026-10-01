# Fact vs Prediction vs Simulation (D-SEM)

Semantic boundaries. The two probability systems are NOT interchangeable.

```mermaid
flowchart TD
    FACT["FACT<br/>RaceState at time T<br/>observed or reconstructed<br/>information known at T"]
    PRED["PREDICTION<br/>Phase-3 LogisticRegression<br/>independent binary P WIN<br/>per driver, NEVER normalized<br/>field sum differs from 1"]
    SIM["SIMULATION<br/>Monte Carlo stochastic futures<br/>mutually exclusive finishing orders<br/>win podium finish distributions<br/>frequencies sum to 1 across field"]
    STRAT["STRATEGY<br/>paired counterfactual interventions<br/>candidate vs baseline deltas<br/>compares, never prescribes"]
    EXPL["EXPLAINABILITY<br/>log-odds decomposition<br/>of one prediction<br/>associational, not causal"]
    FACT --> PRED
    FACT --> SIM
    SIM --> STRAT
    PRED --> EXPL
```

Critical distinction: Phase-3 winner probabilities are independent
per-driver binaries (served note: "They do not sum to 1"). Monte Carlo
winner frequencies are mutually exclusive simulated outcomes (measured
field sum 1.0). Different semantics, different purposes; the MC record
does not supersede the winner-model record. Sources: P11-2 summary
(prediction, simulation, strategy, explainability — all EXECUTED).
