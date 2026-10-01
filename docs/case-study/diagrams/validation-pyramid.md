# Validation Pyramid (D-VALID)

Skips and xfails are shown as measured, never as passes.

```mermaid
flowchart TD
    T1["TIER 1 — source-safe CI<br/>clean-checkout capable<br/>1971 passed / 501 skipped / 4 xfailed<br/>0 failures, 0 errors"]
    T2["TIER 2 — deployable runtime validation<br/>runtime_artifacts bundle + Docker/Compose<br/>readiness gate, endpoint + workflow smoke"]
    T3["TIER 3 — full scientific regression<br/>canonical corpus required: make science<br/>3193 passed / 5 skipped / 4 xfailed<br/>0 failures, 0 errors, 57:28"]
    T1 --> T2
    T2 --> T3
```

Tier 1 never implies Tier-3 science validation. Corpus-dependent: 721
nodes (ignored canonical corpus cannot ship in git — architecture, not
debt). Stale scientific debt: 0. Sources: P11-1 report (Tier-1 both
trees, Tier-3 full run), P11-2 summary (tier1, tier3, test_debt).
