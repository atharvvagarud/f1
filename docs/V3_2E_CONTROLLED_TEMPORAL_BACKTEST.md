# V3.2E CONTROLLED TEMPORAL BACKTEST + SCIENTIFIC VERDICT

## Final verdict

V3.2E COMPLETE — KEEP_MC2_E — READY FOR V3.2F.

Arm E (anchor + bounded dynamics + conditioned variance + AR(1)) beats
frozen R3 on the primary race-macro winner log score (+0.696,
95% CI [+0.236, +1.210], 49 improved / 22 degraded / 4 ties over
75 races) with no secondary degradation, zero invalid runs, identical
coverage, and coherence across all folds and stages. No tuning occurred
after results; the rule-based proposal was independently verified
robust (median +0.161, ex-top-3 mean +0.359).

## Frozen baseline

- tag `v3.1-race-dynamics` = `64c5af094bd1304e23a5c7d3d5b782b0eef11aca`;
  HEAD matched at entry; R3 (`r3-v1` / `phase6-r3-empirical`) unmodified
  (zero diffs on all R3 modules; parity spot green).
- Accumulated V3.2A–D work intact; V3.2D verdict
  V3.2D COMPLETE — READY FOR V3.2E.

## Files changed

V3.2E additions only (nothing staged): `scripts/freeze_v3_2e_prereg.py`,
`scripts/run_v3_2e_backtest.py`, `scripts/analyze_v3_2e_results.py`,
`scripts/verify_v3_2e_verdict.py`, `tests/test_v3_2e_backtest.py`
(15 tests), `scripts/ci_corpus_dependent.txt` (+5 pins),
`scripts/run_ci_tests.py` (3649), `raceintel/simulation/mc2/kernel.py`
(additive position-distribution outputs only — zero trajectory change),
`results/v3/v3_2e/` (19 artifacts), `docs/V3_2E_CONTROLLED_TEMPORAL_BACKTEST.md`,
`results/v3/v3_2e_controlled_backtest.json`.

## Repository safety

Entry: HEAD = tag = `64c5af0`, only V3.2A–D paths, nothing staged.
Exit: same + justified V3.2E paths; nothing staged, committed, tagged,
or pushed.

## Graphify

Entry `graphify update .` (no topology change — docs only since V3.2D);
targeted queries for R7 metrics (`validation.py`), MC2 candidate,
temporal/parameter/eligibility/RNG/CRN neighborhoods. Final update
re-run after changes; no new model coupling, no frontend coupling, no
forbidden data dependency, no V3.2E-attributable cycle.

## V3.2D inheritance

Candidate E frozen from V3.2D (anchor window 5, shrinkage 4, decay 0.5,
±1.5 s bound, era/global variance, ρ=0.264, traffic NOT_RUN). V3.2D
prereg `dc0ae2db…854ee16` hash-verified full value before scoring and
confirmed predating V3.2D comparative artifacts by mtime. One additive
kernel extension (position counts/distributions, podium frequency) with
byte-identical trajectories (all 18 V3.2D tests still green).

## Preregistration

V3.2E prereg `296b7a3e0d5ff322b578c97b733d462e28909020c47d75810eefbf0a7e899c87`
(`results/v3/v3_2e/preregistration.json`), frozen before the backtest;
verified by hash at every script entry. Refines evaluation mechanics
only — E's scientific parameters untouched. Decision logic with
predeclared non-degradation margins; no minimum-improvement invention.

## Evaluation population

1636 evaluated / 1 excluded / 75 races, hash
`5d038db83111a1a9dc9e885ed107358d8e018ad1c3a4570f14d1f78697b8383d`.
Rule: V3.2C-eligible + fold-param eligible + truth available (results
present, factual winner in active roster). The single exclusion
(`2023-r14-R@57`, `fold_param:STALE_ROSTER_OBSERVATION`) is a genuine
temporal-honesty effect: contemporaneity is scaled by the selected pace
base, which differs between through-2024 and fold parameters — exactly
why eligibility is re-verified under fold params. Season split
2020:208 / 2021:299 / 2022:333 / 2023:322 / 2024:474; stages
EARLY 876 / MID 513 / LATE 247.

## Temporal folds

D1 (through 2019 → 2020–21, n=507), D2 (through 2021 → 2022–23, n=655),
D3 (through 2023 → 2024, n=474). Every checkpoint satisfies
through < season (tested); 2025 firewall asserted in population,
truth, params, and tests — 2025 never read.

## Arms

A frozen R3 (`MonteCarloEngine`, pits-off) vs B/C/D/E (`run_mc2` arm
switches, identical prepared states, roster cross-checked per task).
No new parameter variants. F NOT_RUN per V3.2D gate.

## Simulation count

n_runs=1000 all arms, via blind precision pilot (6 checkpoints, arm E
seeds S/S+1, mean winner repeat-TV 0.0190 < 0.05 gate; no truth
inspected). MC noise well below observed A-vs-E effects (0.09–0.35 dev,
0.696 backtest mean).

## Randomness

Master seed 20240101 (R7). Paired-by-checkpoint design (same states, n,
seed). Cross-arm CRN not applicable: R3 internal streams vs MC2
`mc2-ar1` domain are distinct processes and the R3 engine accepts no
external pool (modifying it is forbidden). Race-level paired bootstrap
(B=2000, seed 42) handles comparison noise honestly.

## Ground truth

`winner_flag` / `podium_flag` / non-null `classified_position` from
results parquet, joined AFTER per-checkpoint simulation outputs were
frozen. Order metrics over classified ∩ roster only (DNFs excluded, no
favourable treatment). Separation tested (static import scan + constants).

## Primary metric

Race-macro winner log-loss difference, A-minus-E (positive favors E):
per-checkpoint R7 `winner_log_loss` (predeclared ε=1e-6; zero-frequency
→ −log(1e-6), never −inf), macro-averaged to race, mean over 75 races,
95% race-level paired bootstrap CI.

## Secondary metrics

Winner Brier, podium Brier (mean (p−y)² over roster), expected-finish
MAE (R7, classified), mean RPS (R7 normalized, classified), winner ECE
(R7 bins, descriptive), top-1/top-3 (diagnostic). Hierarchy frozen in
prereg, unchanged after results.

## Winner results

Log-loss Δ +0.696 CI [+0.236, +1.210] (49/22/4 over 75 races); Brier Δ
+0.0068 CI [+0.0030, +0.0107] (52/23). Median Δ +0.161; ex-top-3 mean
+0.359 — not a few-races artifact.

## Podium results

Podium Brier Δ +0.0058 CI [−0.0006, +0.0121] (45/30) — neutral-to-better,
inside the predeclared −0.005 margin. Marginal driver probabilities,
documented as such.

## Expected finish / distribution results

MAE Δ +0.199 laps CI [+0.118, +0.280] (54/21); mean RPS Δ +0.0124 CI
[+0.0007, +0.0233] (48/27). Top-1 favorite hit rate 0.567 (A) → 0.624 (E).

## Calibration

Favorite-based reliability (descriptive; checkpoints correlated within
race): ECE A 0.202 → B 0.150 → C/D 0.149 → E 0.113. Monotone improvement
along the mechanism chain.

## Stage results

Winner log-loss Δ: EARLY +1.141, MID +1.059, LATE +0.460 — E better at
every stage; no late-only pattern (more causal information helps
throughout, smallest edge late).

## Season results

2020 +0.146, 2021 +0.866, 2022 +0.337, 2023 −0.107, 2024 +2.720.
2023 slightly negative but D2 overall positive (+0.119); no
regulation-era collapse (2022–2024 mixed,new-era all non-negative folds).

## Race-level results

75 paired race-macro diffs; improved 49, degraded 22, ties 4 (primary).
Full table in `race_results.json`.

## Bootstrap

B=2000, seed 42, race-level paired (never checkpoint-level). Primary CI
excludes 0; all secondaries exclude meaningful degradation. Deterministic
(tested: repeat identical).

## Coverage / invalid runs

Identical 1636-checkpoint population by construction + per-task roster
cross-check (a wrong roster returns a typed error, tested). Invalid: 0
on all 5 arms over 1.636M simulations each. MC2 gains nothing by
discarding futures.

## Determinism

3 checkpoints (one per fold) × all arms rerun: byte-identical outputs
(`all_match: true`). One investigation closed honestly: the first
comparison reported False due to int-vs-str position keys across the
JSON persistence boundary (values identical); after JSON-round-trip
normalization (floats round-trip exactly) all match. No nondeterminism.

## Convergence

Verdict arm E, 9 checkpoints (3 seasons × EARLY/MID/LATE) at
100/500/1000/5000 (+10000 on 3 MIDs): TV vs max-n collapses
(100: ≤0.21, 500: ≤0.056, 1000: ≤0.036, 5000: ≤0.0046).

## Run-count decision

5000 — smallest n with max TV ≤ 0.005 (V3.2A convention) across all 9
checkpoints (1000 fails: max TV 0.036). First frozen production n_runs.

## Performance

Measured backtest throughput: A 1314, B 125, C 103, D 102, E 97 runs/s
→ E ≈13.6× slower (unoptimized research loop). ACCEPTABLE_FOR_SCIENCE,
REQUIRES_OPTIMIZATION_FOR_PRECOMPUTE. No optimization before verdict.

## Catalogue cost

2305 states at 96.9 runs/s (MEASURED basis, EXTRAPOLATED with 0.7
parallel efficiency, no perfect-scaling claim): n=1k → 6.6 serial h
(2.4 h @4w, 1.2 h @8w); n=5k → 33.1 h (11.8 h @4w, 5.9 h @8w);
n=10k → 66.1 h (23.6 h @4w, 11.8 h @8w).

## Complexity

E adds 4 parameter families (anchor/dynamics/variance/AR1, 12 fold
artifacts), 9 source modules (~1300 lines), explicit fallback rules at
every level, one new failure mode class (typed worker errors — zero
observed in 8.18M simulations), ~13.6× runtime. Justified by:
significant primary win + all-secondary non-degradation + calibration
halved + zero invalids + full determinism. The chain is interpretable
(end-to-end causal quantities, no black box).

## Anchor ablation

A-vs-B primary Δ +0.477 CI [−0.020, +1.004] — largest point estimate,
just crossing zero. Driver-specific causal pace state is the biggest
single contributor by magnitude; AR(1) is the most statistically secure.

## Dynamics ablation

B-vs-C Δ −0.027 CI [−0.064, +0.006] — neutral. The bounded drift neither
helps nor harms outcome quality at n=1000; retained in E as mechanistic
structure (trend paths feed the AR(1) evolution coherently), flagged for
V3.2F review (simplification candidate if precompute budget binds).

## Variance ablation

C-vs-D Δ exactly 0.000 — conditioned variance is inert by construction
(era-only levels available; no per-circuit groups). Retained as
architecture for future families; zero outcome risk either way.

## AR(1) ablation

D-vs-E Δ +0.246 CI [+0.133, +0.375] — significant. Residual persistence
materially improves historical outcome quality; it is not cosmetic.

## Failure inspection

Top improves (2024-r13/r18/r17, Δ +7..+10, EARLY/MID, deep-history
fields) vs top degrades (2023-r11/r19: n=3 checkpoints each,
thin-history `none`-fallback heavy; 2021-r21: n=8). Pattern: E's edge
concentrates where causal history is rich; thin-history states are
noisier (anchor falls back to R3 expectation while AR(1) still acts).
No tuning from these cases; future work: history-aware AR(1) gating.

## Parameter stability

Variance stds: 0.98 (through-2019) → 1.46 (2021) → 1.58 global (2023);
lag-1 ρ: 0.225/0.485/0.365 (all admitted); anchor fallbacks per fold
from backtest diagnostics (recorded in `parameter_stability.json`). No
refitting after outcomes; frozen ρ=0.264 development prior used
throughout (per-fold estimates would be a tuning step — deferred).

## Temporal safety

All V3.2D poison tests green (18/18 incl. construction suite); backtest
harness asserts no 2025 in population/truth/params; fold through<season
tested per checkpoint; truth joined post-simulation (static separation
scan green).

## R3 immutability

Zero diffs on every R3/R7 module; V3.2D parity spot still bit-exact;
A-arm behavioral sanity (1.636M valid, 0 invalid). R3 parameters,
identities unchanged.

## ML / MC firewall

Static import scans green over MC2 + all three V3.2E scripts (only
policy-declaration mentions, never imports); no classifier, V3.1
artifact, or ML probability in any simulation path. MC2 independently
interpretable.

## Strategy compatibility

Preserved: deterministic (seed, sim) streams, per-simulation event-order
consumption, CRN-pairable architecture. No Phase-7 migration (verdict:
compatible, unmigrated).

## Scientific verdict

KEEP_MC2_E — primary CI excludes 0; all non-degradation margins hold
(Brier low +0.003, podium-Brier low −0.0006 > −0.005, MAE low +0.118);
invalid 0.0% both arms; coverage exact; 3/3 folds neutral-or-better with
no fold CI degradation. Null result was permitted; evidence supports
adoption.

## V3.2F coverage-expansion handoff

Next: V3.2F COVERAGE EXPANSION (not precompute/export): neutralisation
(yellow/VSC/SC), wet, remaining causal state-source limits. Current
2305/9644 (23.90%) is not the final target, but no percentage is frozen.
V3.2F must not resurrect unsafe roster inference; must not alter E's
frozen science except through a new preregistered stage. Precompute
uses n_runs=5000 after MC2 optimization (currently 13.6× slower).

## Known limitations

- 2023 season slightly negative (−0.107; D2 still positive overall).
- Thin-history states noisier under E (fallback + AR(1) interaction).
- Dynamics neutral on outcomes (retained for structure, flagged).
- Variance inert pending per-circuit families.
- Favorite-based calibration is descriptive (within-race correlation).
- Research loop 13.6× slower — optimization required before precompute.
- Frozen ρ=0.264 prior rather than per-fold estimates (deliberate
  anti-tuning choice; revisit in V3.2F with preregistration).

## Entry gate

All boxes green: baseline, V3.2A–D intact, graphify-first, both preregs
verified, 2025 firewall tested, frozen common population (hash
`5d038db8…`), identical R3/MC2 coverage + roster cross-checks, exact
fold parameters, frozen arms, pilot-gated n_runs=1000, deterministic
seeds, truth separation, frozen primary + hierarchy, all metric families
evaluated, EARLY/MID/LATE + season + race-level + bootstrap (B=2000)
reported, determinism green, convergence + run-count 5000 decided,
performance + catalogue cost, complexity audit, all four ablations,
failure inspection without tuning, parameter stability, poison suite +
firewall green, R3 bit-exact, ML firewall green, strategy compatible,
exact verdict KEEP_MC2_E, no out-of-scope work (wet/neutralisation/
traffic/DNF/overtaking/strategy/cache/frontend/serving/training),
15 tests + CI green (pending final confirmation), identities exact,
V3.2F handoff is coverage expansion, nothing staged/committed/tagged/
pushed, V3.2F not started.
