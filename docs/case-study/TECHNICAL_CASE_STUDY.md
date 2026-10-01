# F1 Race Intelligence — Technical Case Study

An engineering narrative of a frozen, validated system: historical race
intelligence that cannot see the future. Written from the
[portfolio fact sheet](PORTFOLIO_FACT_SHEET.md); every number traces to
the P11-2 validation summary, the P11-3 benchmark artifact, or a named
frozen report. Section visuals come from the
[diagrams](diagrams/) folder, also indexed in the
[evidence index](README.md).

## 1. Problem

Lap-by-lap race intelligence is difficult for four compounding reasons.
**Temporal state**: a race is 189,420 driver-lap states of evolving gaps,
tyres, stops, and track events — not one row per race. **Partial
information**: at any moment each driver is observed at a different lap
and time; the field is never synchronized. **Race-level dependencies**:
a prediction about one driver depends on nineteen others, yet must not
become a disguised finishing-order distribution. **Probabilistic
outcomes**: identical-looking states diverge, so outputs must be honest
probabilities with sampling uncertainty, not point forecasts. A further
difficulty is that a race is watched, not just scored: the same
machinery that predicts must also replay any historical moment
exactly, explain its number on demand, and compare hypothetical
decisions — four consumers of one temporal truth, each with semantics
that must not leak into the others. The system
answers "what does the model say about this state", "what happened at
this checkpoint", "what could happen from here", and "how do two pit
decisions compare" — each with different semantics, each fenced off from
the others.

## 2. Starting Point

The legacy is a university winner-prediction project: lap-snapshot
classifiers (LogReg/HGB/XGBoost plus a majority-vote ensemble) over
2019–2023 data with race-grouped cross-validation, served by an early
FastAPI + Next.js stack. It worked, but snapshots at laps 5/10/15/20/25
are not race time, grouped CV is not temporal validation, and nothing
prevented future information from leaking into features. The legacy
also taught a lasting lesson in honest scope: a characterized defect
(Monaco 2022 serialization) is pinned by tests and documented rather
than quietly fixed, a habit the v2 validation architecture inherits.
v2 kept the stack shape and rebuilt the concept: every state is clocked at an exact
time T, every feature is provably observable at T, development is
chronological, and the final evaluation is a sealed one-shot holdout.
The legacy pipelines remain frozen and untouched; v2 is the canonical
platform this case study describes.

## 3. Historical Data Platform

Two tiers with different jobs. **Tier B** (1950–2025: 76 seasons, 1,149
races, 25,784 results) is historical metadata that informs pre-race
priors only — it is never rich model input. **Tier A** (2018–2025: 173
terminal race sessions, 171 complete / 2 partial, 189,420 driver laps,
3,458 results, 6,336 pit stops, 9,324 stints, 25,779 weather rows,
14,992 race-control rows) is the rich timing data everything is built
from. Canonical IDs, machine-readable contracts, resumable idempotent
ingestion with manifests, and outcome labels stored in a separate side
channel (never beside the inputs they must not contaminate) make the
platform reproducible: deterministic builds from manifests, validated
by per-stage gates. The pipeline itself is staged — D6 canonical lap
state, D7 temporal enrichment (weather, race control, pit, stint
attachment), D9 structural derived state — each stage carrying its own
manifest and validation evidence, so a defect traces to the stage that
introduced it instead of being debugged backwards from the final matrix.
Raw telemetry stays deferred by recorded decision (ADR-0001): retaining
gigabytes of source-only cache would bloat every checkout for evidence
the v2 contracts never consume. See the
[dataset visual](diagrams/dataset.md).

## 4. Temporal Feature Engineering

The most important section. Each of the 189,420 states carries an exact
clock, `state_time_s`, at lap end. Features are computed under one rule:
nothing dated after T may influence the state at T. Concretely, rival
observations must satisfy `state_time ≤ T` (same-lap future data is
forbidden even when the time gaps look small); qualifying and grid
information enter only as pre-race priors; final race status is never a
running-state input; and the 84 predictive features (registry ALL_84
v8, in families from race STATE through GAPS, PACE, and FIELD context)
are physically separated from the 7 label columns plus companion and
mask columns that complete the 106-column matrix. The 84 features are
organized in families — race STATE (23), pre-race PRIORS (13), FIELD
context (12), PACE (12), ENVIRONMENT history (9), GAPS (8),
RATES/MOMENTUM (4), INTERACTIONS (3) — which is also how explanations
partition their contributions. Enforcement is not a convention but a
test battery: a 20-threat adversarial suite mutates all source families
just after the cutoff and requires earlier predictive state to be
bit-identical, label calculators take no label input by
construction, and chronological development folds make time-travel
structurally impossible. A final guard sits at the roster level: a
state whose roster cannot be validated against the serving contract is
refused whole rather than simulated approximately — stopped-car
invention is worse than an honest error. See the
[temporal-safety diagram](diagrams/temporal-safety.md). The honest
statement of the result is "no leakage detected" — a guarantee is never
claimed.

## 5. Model Development

Development ran on chronological expanding folds — train 2018–2021 →
evaluate 2022, train 2018–2022 → 2023, train 2018–2023 → 2024 — so every
development decision was made with only past data. The lab itself was
staged (protocol, framework, baselines, tuning, selection, calibration,
nonlinear challengers, boundary resolution, holdout), each stage with a
frozen report, so the choice of a linear model is auditable step by
step rather than asserted at the end. Competing families
(XGBoost, HistGradientBoosting, extra trees, bagged trees) were measured
on the same protocol — development losses include XGB 0.109063 and HGB
0.138305 against the frozen M7 outer reference of 0.071374 — and lost to
a simple regularized linear model on the decision metric; calibration
variants (Platt, Isotonic) were measured
against uncalibrated output and lost, so RAW was retained — a decision
recorded with its evidence, not a default. The frozen choice,
LogisticRegression C=0.01 on ALL_84 with train-fitted median/scaler +
mode/one-hot preprocessing, was therefore selected from development
evidence alone. The 2025 season played no role in any selection: it was
evaluated exactly once, after the freeze, under a seal that refuses any
second access. That ordering — select on the past, measure once on the
future — is what makes the holdout numbers mean anything.

## 6. Final Holdout Results

The frozen 2025 one-shot holdout (24 races, 26,692 states), race-macro
aggregation (equal weight per race): log loss 0.0680, Brier 0.0200,
ROC-AUC 0.9845, PR-AUC 0.8032, ECE 0.0111, synchronized Top-1 79.6%,
Top-3 97.9%. The pooled view agrees (state-pooled log loss 0.0679,
Brier 0.0199), which matters: race-macro weighting prevents long races
from dominating, while the pooled check confirms the headline is not an
aggregation artifact — both views are published side by side in the
frozen holdout report. Log loss and Brier are the primary scoring rules
(mean surprisal and mean squared error of the win probabilities); the
AUCs
measure discrimination across thresholds, not race ranking, and are
never presented as ranking metrics; ECE measures calibration error in
ten equal-width bins; Top-k is synchronized through the frozen race
adapter onto independent probabilities. Stage split (EARLY 0.077468 /
MID 0.069800 / LATE 0.056847) shows predictions sharpening as the race
resolves, as physics suggests they should. The development-to-holdout
comparison is part of the record too: the frozen M7 outer development
evaluation sits nearby on every headline metric, so a reviewer can see
exactly how much changed between development and the sealed season —
small, in the expected direction, with no post-hoc adjustment. No
composite score is constructed and no external ranking is claimed. See
the
[evaluation record](diagrams/model-evaluation.md).

## 7. RaceState + Prediction Service

Serving owns a clean boundary: the client names an exact anchor
(race, driver, lap, state time) and the server reconstructs the factual
state — arbitrary client-constructed state JSON is never accepted. From
that state the frozen feature bridge builds the ALL_84 vector and one
batch `predict_proba` produces the snapshot. The probability semantics

p = P(driver wins | driver's observable state)

is an independent binary per driver. The served field routinely sums to
values like 0.56 — this is specified, tested, and documented on every
response ("They do not sum to 1"), because twenty correlated binaries
are not a twenty-way distribution. A full-field snapshot serves in about
102 ms median on local container infrastructure. Serving also owns
stable failure semantics the product depends on: unknown races 404 with
an `unknown_race` body, unresolvable anchors 422, unexpected internal
faults 500, and prediction outages 503 — each mapped by contract, never
by accident, so the frontend can distinguish "no such race" (including
every 2025 ID) from "state cannot be reconstructed" from "service is
down". Anchors are enumerable — a single race exposes on the order of a
thousand of them (2019-r01-R lists 1,041) — which is what makes replay
timelines, simulation sweeps, and strategy anchors all addressable by
the same key.

## 8. Historical Replay

Replay re-serves history without recomputing it: 149 races and 9,644
exact checkpoints were built once from the frozen matrix (verified
bit-identical over thousands of sampled states, ~200× faster than naive
reconstruction at build time) and are served HIT-only in about 1 ms.
Frames are exact historical observations — no interpolation, no
nearest-state snapping — and the 3,206 null checkpoints (drivers with no
observation at a snapshot) are served as null with their reason, never
as zero. Building that cache was itself an engineering phase: a backfill
over the frozen matrix finished in under ten minutes with per-checkpoint
costs in the low seconds, and matrix reuse was verified bit-identical
over thousands of sampled states. A 2025 race ID on any replay path
returns 404 `unknown_race`:
the holdout firewall is a serving behavior, verified live, not a policy
note. See the [replay workflow](diagrams/replay-workflow.md).

## 9. Explainability

Because the winner model is linear, every prediction decomposes exactly:

z = β0 + Σ βj xj,  p = sigmoid(z)

The served explanation returns the intercept, per-feature log-odds
contributions (with family, direction, and observed-vs-imputed state),
and a reconstruction proof: intercept plus contributions reproduces the
decision function to residual 0.0 within 1e-12, and the probability
matches the served prediction bit-for-bit. Timeline-change explanations
difference consecutive checkpoints (with an explicit
NO_PREVIOUS_CHECKPOINT state at the first), and the change itself
satisfies its own invariant: the logit delta equals the summed
contribution deltas with the intercept cancelling, verified over
hundreds of validations. Global permutation evidence
is honestly scoped: with no fold estimators surviving the freeze and
retraining forbidden, importance is measured in-sample on the final fit
and labeled as such — the leading gaps (`gap_to_leader_seconds`,
`gap_to_ahead`) and `position` dominate, which is consistent with the
served local contributions where gap features carry the largest
log-odds weight. No SHAP exists by deliberate decision, and the
served limitations say the decomposition is associational log-odds —
never causal, never probability increments. On-demand cost is about
22 ms.

## 10. Monte Carlo Simulation

Simulation is fenced off from both truth and prediction. History ends at
the anchor: the factual RaceState is the initial condition, and nothing
after T enters. From there, empirical parameters estimated through 2024
plus a deterministic seed generate N stochastic trajectories with one
winner per trial — mutually exclusive finishing orders by construction,
so field win frequencies sum to 1.0 (measured live). Same seed, same
result bit-for-bit (scientific identity verified across reruns).
Validation over 42 states / 23 races gives winner log loss 1.2237,
Brier 0.02669, Top-1 0.643, Top-3 0.881, finish MAE 2.4452, RPS 0.0928,
ECE 0.01899 — a separate record with different semantics that does not
supersede the winner model. For context the same protocol measures what
was beaten: a no-pit ablation and a naive current-leader baseline sit
well behind on the headline metrics, so the engine's skill is located,
not assumed. Coverage is explicit rather than
comprehensive: 75 candidate states were excluded with recorded reasons
(wrong regime, insufficient support), and the engine stack is versioned
by layer (race engine, Monte Carlo core, pit dynamics) so a future
dynamics change can be attributed to the layer that introduced it.
A 10,000-trial run completes in about
16.5 s locally. The assumption list is explicit: free-air,
constructor-shared pace, no DNF, no safety cars, no weather, no traffic,
mild over-pitting, compound changes as identity only. See the
[simulation workflow](diagrams/monte-carlo.md).

## 11. Strategy Comparison

Strategy reuses simulation as a comparator, not an optimizer. A baseline
(factual continuation) and up to four candidates (STAY_OUT, PIT_NOW,
PIT_NEXT_LAP, compound options) run under common random numbers, so each
candidate-baseline delta is paired within identical futures:

Δwin = P_candidate(win) − P_baseline(win) (positive improves)

Δfinish = E[finish_baseline] − E[finish_candidate] (positive improves,
i.e. lowers the finishing position)

Uncertainty is a B=2000 paired bootstrap over valid pairs, classified as
improvement, degradation, inconclusive, or uncertainty-unavailable; the
bootstrap covers sampling noise only, never model misspecification, and
the response says which. CRN
itself is adopted with documented limitations (median variance ratio
0.922 across 711 cells — variance reduction in most cells, never
universal). Nine canonical candidates cover the product space
(STAY_OUT, PIT_NOW, PIT_NEXT_LAP across compound options), with latency
caps enforced per validation stage so comparisons stay interactive.
The objective is required with no default, and no response
or surface anywhere contains best/recommended/optimal language — the
system compares counterfactuals and stops. Validation (99 anchors → 35
eligible, 83 red-team checks, 0 blockers) and a ~1.1 s local comparison
cost complete the picture. See the
[strategy workflow](diagrams/strategy.md).

## 12. Product Interface

Six surfaces over one frozen backend: Predict (snapshot at an anchor),
Replay (timeline + HIT predictions + log-odds panels), Simulator
(distribution from anchor and seed), Strategy (paired comparison table
with uncertainty, defaulting to an explicit objective the user must
confirm), Models (holdout evidence, calibration decision,
limitations), About (semantics lattice, dataset, limitations). Copy
rules are enforced, not aspirational: probabilities carry their
independent-binary note, simulations their frequency note, strategy its
counterfactual framing, explanations their associational wording.
The six surfaces share one backend but tell different stories on
purpose: Models shows the evidence behind the numbers, About shows the
boundaries around them, and the four working surfaces each commit to
exactly one semantic object — snapshot, checkpoint, distribution,
comparison. The interface itself follows a brutalist motorsport-telemetry
direction — dense tables, checkpoints, seeds, contract versions as
normal working material — because the audience is an analyst who reads
timing tables, not a newcomer learning the sport.
Screenshots are capture-pending per the
[specification](screenshots/README.md); the selected hero is Replay at
the frozen 2019-r01-R frame-0 anchor.

## 13. Productionization

FastAPI (single uvicorn process) + Next.js standalone, deployed as
exactly two Compose services from a validated `runtime_artifacts`
bundle (1939 files, manifest SHA pinned). Containers run non-root with
read-only root filesystems and /tmp tmpfs, no bind mounts, no secrets;
network ingestion is off (verified in the startup log); CORS allows
only the frontend origin; `/health` is liveness while `/ready` gates on
six deployability checks; each request emits one structured record with
method, templated path, status, and endpoint duration — no queries,
bodies, headers, or paths. Infrastructure beyond the two containers was
not added because no requirement demonstrated it: no database (frozen
artifacts are files), no queue (synchronous bounds suffice), no
orchestrator, no telemetry pipeline. Readiness itself is a designed semantic, not a
ping: `/health` answers whether the process is alive while `/ready`
checks the deployable resources (model, replay, explainability,
simulation, processed data, network policy) and fails with bounded
codes — proven by a test that holds health at 200 while readiness
returns 503. Productionization ran as its own phase with its own
gates: runtime packaging with a manifest contract, bootstrap and
preflight scripts for source vs deployable environments, container
contracts for both images, a Compose topology contract, configuration
and readiness contracts, and an observability contract — over a hundred
contract assertions green before the freeze, plus a full workflow smoke
(prediction, replay HIT, explanation, simulation, strategy, 2025
firewall) against live containers. The container images are explicit
about their weight: roughly 2.9 GB backend (Python 3.11, exact-pinned scientific
stack, validated bundle merged onto canonical paths) and roughly
550 MB frontend (Node 22 multi-stage standalone build) — large because
the bundle carries the frozen science, which is the point: the image is
the deployable unit under test. Non-root UIDs, read-only filesystems,
and the absence of mounts were verified against live containers, not
just Dockerfiles. See the
[deployment visual](diagrams/deployment.md).

## 14. Validation Architecture

Tier 1 (source-safe CI: 1971 passed / 501 skipped / 4 xfailed clean)
asks whether the tree is sound and deployable. Tier 2 (bundle +
containers + readiness + smoke) asks whether it runs. Tier 3 (full
scientific regression over the canonical corpus: 3193 passed / 5
skipped / 4 xfailed in ~57 min) asks whether the frozen science still
reproduces. Tier 2 earns its place between them with a live
deployable proof: the validated bundle boots in containers, readiness
goes 6/6, and a workflow smoke walks prediction, replay HIT,
explanation, simulation, strategy, and the 2025 firewall end to end —
the same smoke re-run at the final validation, green under the
read-only, non-root posture. Fail-closed selectors pin collection
counts so new tests
cannot silently enter or leave CI; the corpus exclusion list (721
nodes) is the documented consequence of the corpus being unshippable in
git, not hidden debt — stale-test debt stands at zero after a dedicated
release-validation stage re-baselined every drifted pin with its owning
phase mechanism rather than weakening a single assertion. See the
[validation pyramid](diagrams/validation-pyramid.md).

## 15. Performance

Measured, not modeled: client-observed local HTTP latency, concurrency
1, Apple M4, native and containerized separately (P11-3). Prediction
102 ms, replay HIT 1 ms, explanation 22 ms, timeline change 45 ms,
strategy ~1.1 s, 10k simulation ~16.5 s (container p50). Full p50/p95/
p99/max tables, warm-up policy, and the one documented rerun live in
the [benchmark report](../PHASE11_P11_3_FINAL_PERFORMANCE_BENCHMARK.md).
Endpoint duration is reported as endpoint duration; model-inference
latency is never claimed; throughput, cloud, and browser numbers do not
exist here. Two methodological details deserve emphasis because
portfolios routinely get them wrong: warm-up requests are excluded from
every statistic (cold caches and JIT paths must not pollute medians),
and native and containerized numbers are kept separate and never
averaged — the container pays Docker Desktop virtualization overhead on
macOS, and presenting one blended number would be dishonest about both
environments.

## 16. What Was Difficult

**Preventing temporal leakage** meant proving a negative across 189,420
states — solved with exact-T clocks plus an adversarial suite that
mutates the future and demands bit-identical pasts. **Synchronizing
field state** meant serving twenty drivers observed at twenty different
times from one anchor without inventing data — solved with ≤T sync and
explicit nulls. **Preserving probability semantics** meant resisting the
obvious normalization twice (prediction display, MC comparison) — solved
with schema-level semantics and served notes. **Building exact replay**
meant checkpoints that reuse the frozen matrix bit-identically instead
of recomputing — solved with a backfill cache and 1e-12 tolerances.
**Separating prediction from simulation** meant two probability systems
sharing artifacts but never numbers — solved with distinct contracts and
wording. **Paired strategy comparison** meant comparison noise
dominating small deltas — mitigated with CRN plus bootstrap, limitations
kept. **Reproducible artifacts** meant hashes over everything and seals
over the holdout — six artifact identities re-verified by hash reads at
every freeze, so "the frozen system" is a checkable claim rather than a
vibe. **Source-only CI vs corpus validation** meant a test
suite that is green in two different senses — solved with three tiers
and fail-closed selectors. And throughout, **resisting the obvious
shortcut** — normalizing probabilities, snapping to nearest states,
tuning on the holdout, averaging environments, deleting slow samples —
was the recurring discipline: each shortcut would have made some number
look better while making the system mean less. Underneath all of them
is the meta-difficulty the repository structure now reflects: this is a
system whose most important properties are absences — no future in the
features, no normalization in the probabilities, no prescription in
the strategy, no second touch of the holdout — and absences have to be
tested continuously, because unlike features they do not show up in a
demo. The freeze manifests, seals, selectors, and firewalls are that
continuous testing made permanent.

## 17. Limitations

The complete matrix: independent binaries (unnormalized); 2025
evaluated, never served; simulation assumptions (free-air, shared pace,
no DNF/SC/VSC/weather/traffic, identity-only compounds); single-decision
strategy scope; associational log-odds with in-sample permutation, no
SHAP; checkpoint granularity, no spatial track; no live feed; two
containers by design (no DB/queue/orchestrator); bundle required; arm64
only; no cloud, no browser-engine validation, no WCAG certification;
Tier-3 corpus and ~1 h runtime; endpoint duration is not inference
latency. Enumerated in full in the
[fact sheet](PORTFOLIO_FACT_SHEET.md) and the root README.

## 18. Future Work

Clearly future, none implemented: spatial track replay; learned race
dynamics (weather, safety cars, reliability, overtaking, compound pace);
richer multi-stop strategy search; outcome-distribution modelling; model
ensembles only if held-out evidence supports them. Each direction is a
response to a named current limitation rather than a wishlist — the
limitation matrix is, read backwards, the roadmap. The bar for promoting
any of them is the same bar v2 already applies to itself: chronological
development, a sealed evaluation the developers cannot touch, semantics
stated on every response, and limitations published next to the numbers.
v2 stays frozen as described.
