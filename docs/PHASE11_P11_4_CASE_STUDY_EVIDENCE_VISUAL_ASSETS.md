# PHASE 11 P11-4 CASE STUDY EVIDENCE + VISUAL ASSETS

Evidence and visual layer for the final portfolio case study. The
project is made visually understandable without changing the product:
11 Mermaid/Markdown diagrams, screenshot specification (capture
required, nothing fabricated), storyboard, recruiter/engineer evidence
maps, asset manifest, portfolio fact sheet, and a machine-readable
manifest. No README prose, no marketing copy, no product change.

## Final verdict

P11-4 COMPLETE — READY FOR P11-5. All 11 visual assets created with
traceable claims, 6-surface screenshot spec written (no fake
screenshots), hero selected with exact frozen state, storyboard and
both evidence maps complete, manifests created and hashed.

## Frozen baseline

- HEAD: `3c069b529f568dd25ea4a8213a6579afad631c0e`
- Tag at HEAD: `v2-productionization-phase10`

## Repository safety

At start: HEAD/tag exact, nothing staged. Dirty paths classified, zero
UNKNOWN: PREEXISTING_OTHER_WORK (untouched), P11_0/P11_1/P11_2/P11_3
(all untouched, including the P11-3 pin update and benchmark tooling).
Graphify updated (code graph). No git add/commit/tag/reset/restore/
checkout/clean/stash; P11-4 files uncommitted.

## Source evidence

P11-0 readiness audit, P11-2 validation report + summary (SHA
`5091cb77…`), P11-3 benchmark report + artifact (SHA `c9fe7f89…`),
owning frozen phase artifacts per asset (E2 manifest, holdout report,
Phase-6/7 reports, P10-5 freeze). No unsupported architecture inferred.

## Visual design rules

Brutalist motorsport telemetry direction respected; documentation
diagrams prioritize clarity, accuracy, legibility, GitHub rendering.
No decorative complexity, fake telemetry/metrics/traces, AI imagery,
copyrighted photography, gradients, glassmorphism, or illustrations.
Mermaid-in-Markdown (version-controlled, diffable, GitHub-renderable);
no heavyweight dependencies, no proprietary software.

## Architecture

`diagrams/architecture.md` (D-ARCH): data → feature → model/RaceState →
replay/MC/explainability → strategy → API → frontend, plus separate
deployment flow (browser → 2 containers → bundle). No DB/Redis/Kafka/
Celery/WebSockets/MLflow/Kubernetes shown.

## Temporal safety

`diagrams/temporal-safety.md` (D-TEMP): past—T—future boundary,
AVAILABLE vs FORBIDDEN sets, guards (no fall-forward, exact
checkpoints, label separation, 2025 firewall). Strongest
technical-interview visual.

## Semantic boundaries

`diagrams/semantic-boundaries.md` (D-SEM): FACT/PREDICTION/SIMULATION/
STRATEGY/EXPLAINABILITY with the explicit non-interchangeability of
unnormalized winner probabilities and mutually-exclusive MC
frequencies.

## Replay

`diagrams/replay-workflow.md` (D-REPLAY): selection → exact checkpoint →
RaceState → features → cached HIT prediction → explanation/change → UI.
149/9644 shown; 3206 nulls served-as-null stated; 2025 refused.

## Monte Carlo

`diagrams/monte-carlo.md` (D-MC): factual state + r3-empirical params +
assumptions + seed → trajectories → distributions. Deferred dynamics in
exact P11-2 wording; validation metrics + 10k latency cited.

## Strategy

`diagrams/strategy.md` (D-STRAT): baseline/candidates → CRN pairing →
deltas → B=2000 uncertainty → 4 classifications. No BEST/RECOMMENDED/
OPTIMAL anywhere. Orientations, objectives, 83/0 evidence recorded.

## Model evaluation

`diagrams/model-evaluation.md` (D-EVAL): 2025 ONE-SHOT HOLDOUT table
(LL 0.0680, Brier 0.0200, ROC-AUC 0.9845, PR-AUC 0.8032, Top-1 79.6%,
Top-3 97.9%) + stages + model/training block. No composite score, no
external ranking, AUCs not presented as ranking metrics.

## Dataset

`diagrams/dataset.md` (D-DATA): Tier-B → Tier-A → matrix flow with
Tier-B-priors-only distinction explicit.

## Validation architecture

`diagrams/validation-pyramid.md` (D-VALID): Tier-1/2/3 with final
evidence (1971/501/4 clean; 3193/5/4 Tier-3); skips/xfails shown as
measured.

## Deployment

`diagrams/deployment.md` (D-DEPLOY): LOCAL DEPLOYABLE RUNTIME, two
services, non-root/read-only/tmpfs/network-off, health vs readiness. No
cloud shown or implied.

## Performance

`diagrams/performance.md` (D-PERF): exact P11-3 container values
(predict 102.2/109.4 ms; HIT 1.0/1.7 ms; explain 22.5/24.7 ms; 10k
≈16.5 s; strategy ≈1.09 s) labeled LOCAL CONTAINER HTTP, Apple M4,
concurrency 1. No cloud/throughput/browser/inference claims.

## Screenshot inventory

`screenshots/README.md`: CAPTURE_REQUIRED for all 6 routes (no browser
engine exists; installing one out of scope). Per surface: route,
frozen input state, required panels, proven concept, filename, caption
facts, forbidden claims. Viewport 1440×1000, fresh profile, crop to
product, privacy rules.

## Hero selection

Replay `/replay` at 2019-r01-R frame 0 (bottas, lap 1, 2106.767s, CACHE
HIT + LOG_ODDS panel): real product, dense, immediately F1, factual,
self-evident. Runners-up Simulator/Strategy documented.

## Case-study storyboard

`STORYBOARD.md`: 15 sections (Problem → Future work), each with reader
question, primary evidence, visual asset, supporting metric, and key
limitation. No final prose written.

## Recruiter evidence map

In STORYBOARD.md: 7 questions answered in evidence pointers (what it
is, what was built, difficulty, strongest results, UI, readiness,
limitations) — a ≤2-minute map, not prose.

## Engineer evidence map

In STORYBOARD.md: 14 concepts linked to exact evidence (leakage,
RaceState, features, selection, validation, semantics, replay, MC, CRN,
explainability math, testing, Docker, observability, perf
methodology).

## Claim safety

P11-2 claim matrix imported via the asset manifest: every visual's
metrics trace to the P11-2 summary, P11-3 artifact, or a named owning
frozen artifact. No unsupported claims created.

## Asset manifest

`ASSET_MANIFEST.md`: 11 READY diagram/table assets + 6
CAPTURE_REQUIRED screenshots, each with ID, file, format, purpose,
source, claims, limitations, README candidacy, status. No binary
placeholders; mocks and AI UI forbidden and absent.

## Portfolio fact sheet

`PORTFOLIO_FACT_SHEET.md`: concise verified facts under Project,
Dataset, Temporal safety, Model, Holdout, Replay, Simulation,
Strategy, Explainability, Validation, Performance, Deployment,
Limitations. No adjectives, no unsupported claims, no README prose.

## Machine-readable manifest

`results/v2_final_validation/p11_4_case_study_manifest.json` (schema
`p11-4-case-study-manifest-v1`): source evidence SHAs, 11 assets,
screenshot status, hero selection with exact anchor, 15 storyboard
sections, claim sources, limitations. Deterministic, sanitized
(no timestamps/paths/identifiers/secrets). SHA-256:
`b2d9068032dd503f83dd9b6e7a2710594d9d99efe17e0baf12ad23d3038e42f5`.

## Validation

Mermaid: static inspection pass over all 11 files (flowchart headers,
node-ID validity/uniqueness, edge syntax) via stdlib script; no
renderer available and none installed — GitHub rendering unverified,
stated in the manifest. Screenshot privacy: capture-time rules in
spec; nothing captured in P11-4. Root README untouched; frontend,
tests, application untouched.

## Scientific firewall

P11-4 created only `docs/case-study/**`, the machine manifest, and this
report. No change to `ml/`, `v2/`, `api/`, `data/`, frozen artifacts,
`frontend/`, Dockerfiles, Compose, CI, tests, or root README. No
training, evaluation/benchmark rerun, FastF1, generation, or 2025
serving.

## Risks / blockers

None blocking. Screenshots depend on a future capture environment with
a real browser + compose stack; GitHub Mermaid rendering should be
eyeballed in P11-6; V1-era `results/analysis/*.png` remain labeled or
regenerated per P11-0 (P11-5 scope).

## P11-5 handoff

Inputs: fact sheet (write from this), storyboard + maps (structure),
asset manifest (visuals + traceability), diagrams (embed), screenshot
spec + hero state (capture then embed), machine manifest (SHA above).
P11-5 writes the README + technical case study; it must not invent
metrics, browser numbers, or cloud claims.

## Entry gate

- [x] frozen HEAD/tag verified
- [x] nothing staged
- [x] dirty paths fully classified
- [x] P11-2 validation summary verified
- [x] P11-3 benchmark artifact verified
- [x] no science/evaluation/benchmark rerun
- [x] canonical architecture diagram created
- [x] temporal-safety diagram created
- [x] semantic-boundary diagram created
- [x] replay workflow created
- [x] Monte Carlo workflow created
- [x] strategy workflow created
- [x] model-evaluation visual created
- [x] dataset visual created
- [x] validation-pyramid visual created
- [x] deployment visual created
- [x] performance visual created
- [x] all metrics traceable
- [x] no composite model score
- [x] independent-binary semantics explicit
- [x] MC mutually-exclusive semantics explicit
- [x] strategy non-prescriptive semantics explicit
- [x] 2025 holdout firewall visible
- [x] deferred MC dynamics represented honestly
- [x] Tier-B vs Tier-A distinction explicit
- [x] screenshot inventory covers all 6 routes
- [x] no fake screenshots
- [x] hero surface selected
- [x] exact hero state specified
- [x] storyboard complete
- [x] recruiter evidence map complete
- [x] engineer evidence map complete
- [x] asset manifest complete
- [x] fact sheet complete
- [x] internal visual index complete
- [x] Mermaid syntax inspected/validated
- [x] no unsupported visual claims
- [x] screenshot privacy rules satisfied
- [x] case-study manifest created
- [x] manifest deterministic
- [x] manifest sanitized
- [x] manifest SHA recorded
- [x] root README untouched
- [x] frontend untouched
- [x] tests untouched
- [x] application untouched
- [x] scientific firewall green
- [x] report complete
- [x] nothing staged/committed/tagged
- [x] unrelated work untouched
- [x] P11-5 handoff explicit
