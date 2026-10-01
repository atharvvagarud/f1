# Dataset (D-DATA)

Tier-B metadata is NOT rich model input. Only Tier-A states feed the
temporal matrix.

```mermaid
flowchart TD
    TB["Tier B historical metadata<br/>1950-2025, 76 seasons<br/>1149 races, 25784 results"]
    TA["Tier A rich race data<br/>2018-2025, 173 terminal sessions<br/>171 COMPLETE / 2 PARTIAL<br/>189420 driver laps"]
    MATRIX["Temporal ML matrix<br/>189420 states<br/>84 predictive features<br/>106 columns total"]
    TB --> TA
    TA --> MATRIX
```

Tier-B priors inform pre-race context only. Terminal-session detail:
3458 results, 6336 pit stops, 9324 stints, 25779 weather rows, 14992
race-control rows. Sources: `about.v1.json` dataset_statistics,
`docs/generated/phase2_freeze_manifest.json`, `DATASET_V2_REPORT.md`,
`PHASE2_FINAL_REPORT.md`.
