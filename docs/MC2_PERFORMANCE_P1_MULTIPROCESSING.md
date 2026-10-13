# MC2 Performance P1 — Deterministic State-Level Multiprocessing

P1 wraps the frozen MC2 kernel without changing it: independent exact field
states run across processes. V3.8 immutable (`15df86b`,
`v3.8-model-simulation-consensus`). No kernel optimization, no future
chunking, no vectorization, no V3.9.

## Architecture

`raceintel/simulation/mc2_batch.py` (`mc2-batch-v1`): parent →
`ProcessPoolExecutor` (explicit spawn context, module-level worker,
initializer-injected repo paths, no fork inheritance) → one exact state per
task through the frozen path (prep → variance/mechanisms → `run_mc2`) →
deterministic parent assembly by `(race_id, frame_index)` → single-writer
atomic checkpoint (tmp+replace, version-stamped identity+config entries).
Refusals are typed envelopes; unexpected failures raise `Mc2BatchError`
naming exact states after checkpointing completions; interrupts clean up via
pool shutdown. No nested pools, no threads, no worker-specific RNG, no API
exposure. Default policy `min(8, cpu, tasks)`, execution-only.

## Task identity

`(race_id, frame_index, fold_through)` + config `(arm, seed 20240101,
count 5000, rho 0.264)`; production default 5000, no product/API control.

## Benchmark corpus

15 exact states: first 2 sorted `state_id`s per race with stored D runs
(8 races; fixed before timing; outcome-blind; all verified in the frozen
checkpoint). Production 5000 futures/state for every worker count.

## Exact parity (release gate — all true)

- direct serial == executor workers=1 (frozen path, no orchestration)
- executor w=1 == w=2 == w=4 == w=6 == w=8 (canonical hashes, 15 states)
- executor w=1 == P0 3×5000 fixtures (winner-count hashes)
- RNG: root seed, sim_id, tags, dims, AR1 draws unchanged; no PID/worker/
  time offsets (source-scanned + empirically proven)

## Worker matrix (15 states × 5000, cooled rerun)

| workers | wall(s) | speedup | effic. | futures/s |
|---|---|---|---|---|
| 1 | 412.3 | 1.00 | 1.00 | 181.9 |
| 2 | 263.0 | 1.57 | 0.78 | 285.2 |
| 4 | 201.7 | 2.04 | 0.51 | 371.8 |
| 6 | 167.0 | 2.47 | 0.41 | 449.2 |
| 8 | 151.2 | 2.73 | 0.34 | 496.1 |

Per-state median run_s grows 28.2 → 73.6s (total CPU-work 410 → 1054s):
heterogeneous 4P+6E cores + shared thermal/power contention. First
(heat-soaked) run showed a transient w=4 inversion (275.6s > w=2 246.4s),
not reproduced cooled — placement/thermal variance is real; prefer
efficient counts over max cores. Best wall here: 8; efficient: 2–4.

## Limitations

Single-state latency unchanged (one state = one task); `/compare` latency
is future work. Memory flat (~150–190MB/worker-class RSS); IPC negligible
(payload ~MBs vs ~400s compute).

## Strategy/counterfactual

Reusable executor exists; no caller migrated in P1 (frozen behavior
unchanged). V3.6/V3.7 MC2 callers are future candidates with their own
parity proofs.

## Pathology / tests / collection

P1-P1…P1-P30 all zero (`tests/test_mc2_batch_p1.py`, incl. live small-scale
parity smoke + artifact assertions). Collection: pre-P1 5010 (5002 + 8 P0)
+ P1 nodes → pin updated narrowly (see §26 record in final report).
Targeted regression green; full Tier-1 deferred per P1 policy (no shared
runtime behavior changed; kernel untouched; frozen callers unmigrated).

## Classification

**B — STATE_PARALLELISM_USEFUL_BUT_SINGLE_STATE_OPTIMIZATION_WARRANTED.**
Recommended next: P2 kernel-overhead elimination and/or within-run future
chunking. Do not start automatically.
