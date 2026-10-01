# Performance Evidence (D-PERF)

LOCAL CONTAINER HTTP, Apple M4, concurrency 1. Exact P11-3 artifact
values (p50 / p95). Never cloud latency, throughput, browser
performance, or model-only inference latency.

| Operation | p50 | p95 | N |
|---|---|---|---|
| Prediction (20-driver snapshot) | 102.2 ms | 109.4 ms | 200 |
| Replay cache HIT | 1.0 ms | 1.7 ms | 200 |
| Explanation (LOG_ODDS) | 22.5 ms | 24.7 ms | 100 |
| 10,000-trial simulation | ≈16.5 s | ≈16.6 s | 10 |
| Strategy comparison (baseline + 4) | ≈1.09 s | ≈1.13 s | 20 |

Also: RaceState 2.2/3.6 ms, replay timeline 1.4/2.1 ms, timeline change
45.3/47.9 ms, health 0.9/2.1 ms, readiness 0.9/1.5 ms. MC-1k p50
≈1.70 s. Source: `p11_3_performance_benchmark.json` (SHA
`c9fe7f89…`), methodology in P11-3 report. p99 over N<100 is empirical,
not an SLO.
