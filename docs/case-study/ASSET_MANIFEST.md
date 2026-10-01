# Asset Manifest (P11-4)

Claim traceability: every metric traces to `p11_2_validation_summary.json`
(P11-2, SHA `5091cb77…`), `p11_3_performance_benchmark.json` (P11-3, SHA
`c9fe7f89…`), or the owning frozen phase artifact named per asset.

| ID | File | Format | Purpose | Source evidence | Claims shown | Limitations shown | README candidate | Status |
|---|---|---|---|---|---|---|---|---|
| D-ARCH | diagrams/architecture.md | Mermaid MD | canonical system + deployment architecture | P11-2 summary; about.v1.json; P10-5 | layers, 2 services | local runtime only | yes (architecture) | READY |
| D-TEMP | diagrams/temporal-safety.md | Mermaid MD | exact-T constraint, available vs forbidden | P11-2 temporal_safety; PHASE2_TEMPORAL_SEMANTICS | 10 invariants; 2025 firewall | "detected, not guaranteed" | yes (hero-adjacent) | READY |
| D-SEM | diagrams/semantic-boundaries.md | Mermaid MD | FACT/PRED/SIM/STRAT/EXPL boundaries | P11-2 prediction/simulation/strategy | unnormalized vs exclusive | non-interchangeable | yes | READY |
| D-REPLAY | diagrams/replay-workflow.md | Mermaid MD | replay pipeline | E2 manifest; P11-2 replay | 149/9644; HIT ≈1 ms | 3206 nulls; 2025 refused | yes | READY |
| D-MC | diagrams/monte-carlo.md | Mermaid MD | simulation pipeline + deferred dynamics | PHASE6 reports; P11-2 simulation | 42/23 metrics; 10k ≈16.5 s | full deferred list | yes | READY |
| D-STRAT | diagrams/strategy.md | Mermaid MD | comparison pipeline, no prescription | PHASE7 reports; P11-2 strategy | 83/0 checks; ≈1.1 s | CRN limits | yes | READY |
| D-EVAL | diagrams/model-evaluation.md | MD table | 2025 holdout record | final_holdout_2025_v1.json; model card | LL/Brier/AUC/Top-k + stages | one-shot; RAW; no ranking | yes (results) | READY |
| D-DATA | diagrams/dataset.md | Mermaid MD | Tier-B/A/matrix distinction | about.v1.json; phase2 manifest | 76/1149; 173/189420; 84 | Tier-B priors only | yes | READY |
| D-VALID | diagrams/validation-pyramid.md | Mermaid MD | Tier-1/2/3 architecture + evidence | P11-1 report; P11-2 tier1/tier3 | 1971/501/4; 3193/5/4 | skips shown as skips | yes | READY |
| D-DEPLOY | diagrams/deployment.md | Mermaid MD | local deployable runtime | P10-5; P11-2 runtime | 2 services; 6/6 ready | no cloud; arm64 | yes | READY |
| D-PERF | diagrams/performance.md | MD table | P11-3 evidence table | P11-3 artifact | p50/p95 per op | local-only; no SLO | yes (performance) | READY |
| S-PREDICT | screenshots/01-predict.png | PNG | Predict surface proof | live `/` (to capture) | unnormalized probabilities | no accuracy claim | yes | CAPTURE_REQUIRED |
| S-REPLAY | screenshots/02-replay.png | PNG | Replay surface proof (HERO) | live `/replay` frame 0 (to capture) | exact checkpoint + HIT | nulls exist | yes (hero) | CAPTURE_REQUIRED |
| S-SIMULATOR | screenshots/03-simulator.png | PNG | Simulator surface proof | live `/simulator` (to capture) | frequency semantics | not a prediction | yes | CAPTURE_REQUIRED |
| S-STRATEGY | screenshots/04-strategy.png | PNG | Strategy surface proof | live `/strategy` (to capture) | deltas + uncertainty | never optimal | yes | CAPTURE_REQUIRED |
| S-MODELS | screenshots/05-models.png | PNG | Models dossier proof | live `/models` (to capture) | holdout table + RAW | no SOTA | yes | CAPTURE_REQUIRED |
| S-ABOUT | screenshots/06-about.png | PNG | About dossier proof | live `/about` (to capture) | semantics + limits | no live/cloud | maybe | CAPTURE_REQUIRED |

No binary placeholders created. No mock/AI screenshots (forbidden).
Screenshot privacy rules apply at capture (no paths, keys, usernames,
bookmarks, unrelated desktop; crop to product surface).
