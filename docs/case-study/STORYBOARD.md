# Case-Study Storyboard (for P11-5)

Factual section plan only — no final prose. Each section lists the
reader question, primary evidence, visual asset, supporting metric, and
key limitation.

1. Problem — What is being predicted, and why is in-race prediction
   hard? Evidence: Tier-A session structure (P11-2 dataset). Visual:
   D-DATA. Metric: 189,420 states. Limitation: checkpoint granularity.
2. Why temporal leakage matters — What goes wrong if the future leaks?
   Evidence: P11-2 temporal-safety matrix (10 invariants). Visual:
   D-TEMP. Metric: 20-threat adversarial suite, no leakage detected.
   Limitation: "no leakage detected", never "zero guaranteed".
3. Architecture — How do the pieces fit? Evidence: P11-2 API/container
   matrices. Visual: D-ARCH. Metric: 6 product surfaces. Limitation:
   local deployable runtime only.
4. Data platform — What data, and what kind? Evidence: Tier-B/A
   manifests. Visual: D-DATA. Metric: 76 seasons metadata; 173 rich
   sessions. Limitation: Tier-B is priors only, not rich input.
5. Temporal feature engineering — How is T enforced? Evidence: D11 +
   D9 tests, label firewall. Visual: D-TEMP. Metric: 84 predictive
   features. Limitation: exact-T clock, no sub-lap resolution.
6. Winner prediction — What does the model output? Evidence: P11-2
   prediction smoke (sum 0.5625). Visual: D-SEM. Metric: holdout LL
   0.0680. Limitation: independent binary, never normalized.
7. Historical replay — How is history re-served? Evidence: E2 manifest
   + P11-2 replay smoke. Visual: D-REPLAY. Metric: 149/9644, HIT
   ≈1 ms. Limitation: 3206 null checkpoints served as null.
8. Monte Carlo — How are futures simulated? Evidence: Phase-6 reports +
   P11-2 MC smoke. Visual: D-MC. Metric: 42/23 validation; 10k ≈16.5 s.
   Limitation: empirical assumptions (weather/SC/VSC/DNF deferred).
9. Strategy comparison — How are interventions compared? Evidence:
   Phase-7 reports + P11-2 strategy smoke. Visual: D-STRAT. Metric:
   83 checks, 0 blockers; ≈1.1 s. Limitation: CRN with limitations;
   never a recommendation.
10. Explainability — What can be explained? Evidence: E3/E4/E5 + P11-2
    smoke (residual 0.0). Visual: D-SEM. Metric: ≈22 ms on demand.
    Limitation: associational log-odds; in-sample permutation; no SHAP.
11. Validation — How is correctness enforced? Evidence: Tier-1/Tier-3
    runs. Visual: D-VALID. Metric: 1971/501/4 clean; 3193/5/4 Tier-3.
    Limitation: Tier-3 needs corpus (~1 h).
12. Performance — How fast is it? Evidence: P11-3 artifact. Visual:
    D-PERF. Metric: candidates in fact sheet. Limitation: local-only,
    no browser/throughput claims.
13. Productionization — How does it deploy? Evidence: P10-5 + P11-2
    runtime matrices. Visual: D-DEPLOY. Metric: 2 containers, 6/6
    readiness. Limitation: arm64 only; no cloud.
14. Limitations — What is honestly out of scope? Evidence: P11-2
    limitation matrix. Visual: none (table). Metric: full list in fact
    sheet. Limitation: this section IS the limitation.
15. Future work — What is explicitly deferred? Evidence: P11-0 v2
    boundary. Visual: none. Metric: none. Limitation: deferred ≠
    planned.

## Recruiter evidence map (≤2 minutes)

- What is it? In-race F1 winner-prediction intelligence over frozen
  historical data (fact sheet: Project).
- What did Atharva build? Data platform → temporal features → frozen
  model → replay/MC/strategy/explainability → API → UI → Docker
  (visual: D-ARCH).
- What is technically difficult? Temporal leakage prevention at race
  time T (visual: D-TEMP, strongest interview visual).
- Strongest measured results? 2025 holdout LL 0.0680 / Brier 0.0200 /
  Top-1 79.6% / Top-3 97.9% (visual: D-EVAL); 149 races, 9644 exact
  checkpoints; Tier-3 3193 green.
- What does the UI look like? Screenshots CAPTURE_REQUIRED; spec in
  screenshots/README.md; hero candidate: Replay.
- How production-ready? Two-container local deployable runtime, 6/6
  readiness, Tier-1 clean green; no cloud, arm64 only (visual:
  D-DEPLOY).
- Limitations acknowledged? Full matrix in fact sheet (no SHAP, no live
  feed, MC assumptions, 2025 unserved).

## Engineer evidence map

- Temporal leakage prevention → D-TEMP + `PHASE2_TEMPORAL_SEMANTICS.md`
  + `PHASE2_LEAKAGE_PARITY_AUDIT.md` + D11 adversarial suite.
- RaceState semantics → `/v2/races/{id}/state` contract + P11-2 state
  smoke (exact anchor key).
- Feature engineering → Phase-2 canonical matrix (189420×106, ALL_84).
- Model selection → `MODEL_LAB_*` reports (M7 dev, M8 RAW, M9 holdout).
- Temporal validation → expanding folds D1–D3 + one-shot 2025 + seal.
- Probability semantics → D-SEM + served semantics notes (P11-2).
- Replay architecture → E1/E2/E7 reports + D-REPLAY + HIT smoke.
- Simulation design → Phase-6 reports + D-MC + determinism smoke.
- CRN strategy comparison → Phase-7 S3/S6 + D-STRAT + delta smoke.
- Explainability mathematics → E3/E4/E5 + residual-0.0 smoke.
- Testing architecture → D-VALID + P11-1 report + selector scripts.
- Docker/runtime artifacts → D-DEPLOY + P10-5 + bundle manifest SHA.
- Observability → 5-field request records + zero tracebacks (P11-2).
- Performance methodology → P11-3 report + benchmark script + artifact.
