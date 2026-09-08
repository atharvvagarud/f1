# F1 Intelligence v2 --- Phase 3 Model Lab & Temporal Evaluation

> **Purpose:** Build a rigorous, reproducible model experimentation and
> temporal evaluation system for F1 Intelligence v2, then compare
> legitimate model families for race-outcome prediction.
>
> **Execution environment:** OpenCode Desktop + Meta Spark 1.3
> Contributor
>
> **Prerequisites:** `V2_FOUNDATION_REFACTOR.md`,
> `V2_PHASE_1_DATA_PLATFORM.md`, and
> `V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md` are complete and their quality
> gates pass.
>
> **Primary rule:** No model becomes "production" because it is
> fashionable, complex, or has the highest single metric. Selection must
> be based on legitimate chronological evaluation, probabilistic
> quality, calibration, robustness, latency, reproducibility, and
> product requirements.

------------------------------------------------------------------------

# 1. Mission

The original university project compared:

``` text
Logistic Regression
HistGradientBoosting
XGBoost
```

using race-grouped cross-validation at fixed checkpoints.

Those experiments remain valid historical project artifacts, but they
are **not sufficient evidence for F1 Intelligence v2 production claims**
because the final v2 system requires strict temporal evaluation.

Phase 3 builds a proper Model Lab:

``` text
CANONICAL DATA
      |
      v
TEMPORAL FEATURE SET
      |
      v
EXPERIMENT CONFIG
      |
      +-------- Model
      +-------- Feature families
      +-------- Target
      +-------- Temporal split
      +-------- Hyperparameters
      |
      v
TEMPORAL BACKTEST
      |
      v
METRICS + CALIBRATION + LATENCY
      |
      v
EXPERIMENT RECORD
      |
      v
MODEL COMPARISON
      |
      v
JUSTIFIED PRODUCTION CANDIDATE
```

No fabricated metrics, benchmarks or conclusions.

------------------------------------------------------------------------

# 2. Hard Scope

This phase MAY:

-   build chronological backtesting
-   establish simple racing baselines
-   compare legitimate tabular models
-   perform training-only hyperparameter tuning
-   evaluate feature-family ablations
-   evaluate race-stage performance
-   evaluate calibration
-   calibrate models using training/validation data only
-   benchmark inference latency
-   build reproducible experiment configs
-   build a lightweight model/experiment registry
-   investigate ranking models
-   investigate ordinal finishing-position models
-   investigate survival models for DNF
-   investigate neural/tabular/sequence models as research experiments
-   choose justified production candidates for defined tasks

This phase MUST NOT:

-   implement Monte Carlo simulation
-   implement strategy recommendations
-   implement What-If
-   implement Race Engineer AI
-   redesign the frontend
-   invent model metrics
-   tune against the final holdout
-   repeatedly inspect the final holdout while making modelling
    decisions
-   use random row-level train/test splits
-   allow future races into training data
-   allow calibration on test data
-   declare neural models superior without evidence
-   automatically ensemble models because "ensembles are better"

------------------------------------------------------------------------

# 3. Core Evaluation Principle

F1 is temporal.

A model predicting a historical race must be trained only on races that
happened before it.

Never use:

``` text
random train_test_split()
```

for final F1 Intelligence evaluation.

Never mix future races into training for an earlier test race.

------------------------------------------------------------------------

# 4. Recommended Historical Protocol

The exact protocol must be finalized against actual Phase 1 coverage.

A preferred expanding-window structure is:

``` text
TRAIN                 TEST

2018–2022       ->    2023
2018–2023       ->    2024
2018–2024       ->    2025
```

However, **2025 should preferably remain the strongest final historical
holdout** during model development.

A safer development workflow is:

``` text
DEVELOPMENT

2018–2021 -> 2022
2018–2022 -> 2023
2018–2023 -> 2024

FINAL LOCKED EVALUATION

2018–2024 -> 2025
```

Choose the exact protocol once and document it.

Do not repeatedly evaluate 2025 while tuning models/features.

------------------------------------------------------------------------

# 5. Holdout Discipline

Create an explicit final-holdout policy.

Before final evaluation:

``` text
2025 labels/results
```

must not influence:

-   feature-family selection
-   hyperparameter selection
-   model-family selection where avoidable
-   calibration choices
-   architecture changes

After the experiment plan is frozen, run the final holdout once or only
according to a documented controlled procedure.

If 2025 has already been inspected during development, state that
honestly and choose another defensible evaluation protocol rather than
pretending it is untouched.

------------------------------------------------------------------------

# 6. Experiment Framework

Do not create independent scripts where every model performs its own:

``` text
load data
split
train
evaluate
print metrics
```

Build shared infrastructure.

Suggested conceptual structure:

``` text
ml/
├── experiments/
│   ├── config/
│   ├── runner.py
│   ├── registry.py
│   └── comparison.py
│
├── evaluation/
│   ├── temporal_split.py
│   ├── metrics.py
│   ├── calibration.py
│   ├── race_stage.py
│   └── latency.py
│
└── models/
    ├── baselines/
    ├── tabular/
    ├── ranking/
    ├── ordinal/
    ├── survival/
    └── experimental/
```

Adapt to the actual repository.

------------------------------------------------------------------------

# 7. Experiment Configuration

Every run should record enough information to reproduce it.

Conceptually:

``` yaml
experiment_id:
task:
model:
feature_set:
feature_families:
train_period:
validation_period:
test_period:
hyperparameters:
random_seed:
calibration:
dataset_version:
feature_set_version:
code_version:
```

Record actual values automatically where possible.

------------------------------------------------------------------------

# 8. Experiment Record

Persist:

``` text
experiment_id
timestamp

dataset_version
feature_set_version
model_family
model_version
hyperparameters
seed

train races
validation races
test races

metrics
calibration metrics
latency
training duration

artifact path
status
notes
```

Do not rely on terminal output as the experiment history.

------------------------------------------------------------------------

# 9. Targets / Tasks

Do not force one model to solve every race question.

Model Lab should support distinct tasks.

## T1 --- Winner probability

``` text
P(win)
```

## T2 --- Podium probability

``` text
P(finish <= 3)
```

## T3 --- Points probability

Use the correct points/classification definition for the target era.

``` text
P(points finish)
```

## T4 --- Expected finishing position

Potential formulations:

``` text
regression
ordinal modelling
ranking
simulation-derived expectation later
```

## T5 --- Position gain/loss

Potential:

``` text
P(gain position)
P(lose position)
```

or expected positional change.

## T6 --- DNF / survival

Potential:

``` text
binary DNF probability
survival probability over remaining laps
```

Do not assume one formulation is best.

------------------------------------------------------------------------

# 10. Probability Semantics

The original binary per-driver winner classifier can produce independent
driver probabilities that do not necessarily sum to 1 across a race.

Do not silently call these a coherent mutually exclusive race
distribution.

For every probabilistic task document:

``` text
What exactly does this probability mean?
```

Possible approaches to evaluate later include:

-   independent binary probabilities with explicit semantics
-   race-level normalization only if mathematically justified
-   field-aware/ranking formulations
-   simulation-derived mutually exclusive finish distributions

Do not cosmetically normalize scores and claim the statistical problem
is solved.

------------------------------------------------------------------------

# 11. Baseline Models

Every sophisticated model must beat meaningful baselines.

Implement legitimate simple baselines.

Candidates:

``` text
B0 — current leader wins
B1 — pole/grid leader wins
B2 — current order remains final order
B3 — best recent representative pace
B4 — simple position-based probability baseline where properly defined
```

Not every baseline applies to every target.

Document exact rules.

------------------------------------------------------------------------

# 12. Production Candidate Tier

These models deserve serious evaluation.

## Logistic Regression

Purpose:

-   interpretable baseline
-   low latency
-   probability baseline
-   sanity check

Keep it even if it does not win.

------------------------------------------------------------------------

## HistGradientBoosting

Purpose:

-   strong sklearn-native tabular baseline
-   continuity with original project
-   efficient nonlinear model

------------------------------------------------------------------------

## XGBoost

Purpose:

-   existing project continuity
-   strong gradient-boosting benchmark
-   supports classification/ranking variants

------------------------------------------------------------------------

## LightGBM

Purpose:

-   efficient boosted-tree candidate
-   strong tabular benchmark
-   useful at larger driver-lap scale

Add only through the project's dependency-management process.

------------------------------------------------------------------------

## CatBoost

Purpose:

-   strong tabular candidate
-   evaluate handling of categorical variables such as
    driver/constructor/circuit/compound where appropriate

Do not allow target encoding/categorical processing to leak future
information.

------------------------------------------------------------------------

## Extra Trees

Purpose:

-   randomized nonlinear ensemble baseline
-   useful comparison against boosting

------------------------------------------------------------------------

## Random Forest

Purpose:

-   conventional nonlinear baseline
-   helps determine whether boosting complexity is actually required

It does not need to remain in production if clearly dominated.

------------------------------------------------------------------------

# 13. Model Preprocessing

Preprocessing must be fitted only on training data.

This includes:

``` text
imputation
scaling
categorical encoding
feature selection
calibration
target-derived encodings
```

Use pipelines where appropriate.

Never fit preprocessing on the full dataset before temporal splitting.

------------------------------------------------------------------------

# 14. Hyperparameter Tuning

Tuning must occur inside the historical training/development period.

Conceptually:

``` text
OUTER TEMPORAL TEST
      |
      +-- untouched test period

TRAINING HISTORY
      |
      +-- internal temporal validation/tuning
```

Do not optimize hyperparameters on the outer test period.

Use modest, cost-conscious search.

Do not perform enormous tuning runs unless measured evidence justifies
them.

------------------------------------------------------------------------

# 15. Random Seeds

Where algorithms contain randomness:

-   set explicit seeds
-   record them
-   use deterministic options where practical
-   report unavoidable nondeterminism

One lucky seed must not determine the production model.

For important stochastic experiments, evaluate stability across multiple
seeds where affordable.

------------------------------------------------------------------------

# 16. Primary Metrics

For probabilistic classification tasks prioritize:

``` text
Log Loss
Brier Score
Calibration Error
```

Also report appropriate ranking/decision metrics.

Do not optimize only accuracy.

------------------------------------------------------------------------

# 17. Top-K Metrics

Where appropriate:

``` text
Top-1
Top-3
```

can be useful for winner-ranking analysis.

Define exactly how race-level Top-3 is computed.

Do not treat Top-3 as a substitute for probability quality.

------------------------------------------------------------------------

# 18. Calibration

Evaluate:

``` text
reliability curves
Brier score
ECE or another documented calibration metric
```

If calibration is needed, evaluate legitimate methods such as:

``` text
Platt / sigmoid
isotonic
```

Calibration models must be fitted only using training/validation data.

Never calibrate on final test labels.

------------------------------------------------------------------------

# 19. Calibration by Race Stage

Probability quality may differ between:

``` text
early race
mid race
late race
```

Evaluate calibration by race progress where sample size permits.

Do not create misleading small-sample plots without reporting counts.

------------------------------------------------------------------------

# 20. Race-Stage Evaluation

Define race stages using `race_progress_pct`.

For example, candidate boundaries might be:

``` text
early
middle
late
```

but choose/document actual boundaries before evaluation.

Report model performance by stage.

This answers:

> How quickly does the model become useful during a race?

------------------------------------------------------------------------

# 21. Lap / Progress Curves

Generate performance curves across race progress where statistically
sensible.

Potential:

``` text
log loss vs race progress
Brier vs race progress
Top-3 vs race progress
calibration vs race progress
```

Do not cherry-pick individual laps.

------------------------------------------------------------------------

# 22. Feature-Family Ablation

Use the infrastructure from Phase 2.

Suggested experiments:

``` text
A — basic race state
B — A + pace
C — B + tyres
D — C + pits
E — D + traffic
F — E + race control/weather
G — F + teammate
H — G + historical priors
I — H + telemetry
```

Record:

-   metric change
-   latency change
-   missingness impact
-   complexity impact

A feature family may be rejected even if it produces a tiny metric
improvement.

------------------------------------------------------------------------

# 23. Model Comparison Fairness

When comparing models:

-   same temporal split
-   same target
-   same feature set unless testing feature interaction intentionally
-   same evaluation implementation
-   equivalent test population

Do not compare numbers produced under incompatible protocols as though
they were directly comparable.

------------------------------------------------------------------------

# 24. Learning-to-Rank Experiment

F1 is an ordered competition.

Create an explicit ranking experiment.

Potential candidates:

``` text
XGBoost ranking
LightGBM ranking
```

Group samples by race-state:

``` text
race_id + lap/state
```

The model should learn relative ordering of the field.

Evaluate against:

-   independent winner classifier
-   current-order baseline
-   expected finish formulations

Do not automatically interpret raw ranking scores as probabilities.

------------------------------------------------------------------------

# 25. Ranking Metrics

Potential legitimate metrics:

``` text
NDCG where meaningful
Spearman rank correlation
Kendall rank correlation
mean absolute finishing-position error
Top-1 / Top-3 field ranking
```

Choose metrics that correspond to the actual target.

Document them.

------------------------------------------------------------------------

# 26. Ordinal Finishing-Position Experiment

Finishing position is ordered.

Compare:

``` text
standard regression
ordinal modelling
ranking
```

Potential outputs:

``` text
expected finish
position distribution if model supports it
```

Do not assume ordinary regression is correct simply because positions
are numeric.

------------------------------------------------------------------------

# 27. Survival / DNF Experiment

Investigate DNF as a time-to-event problem.

Potential methods:

``` text
Cox proportional hazards baseline
Random Survival Forest
gradient-boosted survival model
```

Only add dependencies justified by the experiment.

Potential outputs:

``` text
P(survive next N laps)
P(finish race)
hazard over remaining distance
```

Define censoring and event semantics carefully.

Distinguish mechanical retirement, crash and classification issues where
the data permits.

Do not claim mechanical-failure prediction unless the labels/features
genuinely support it.

------------------------------------------------------------------------

# 28. Survival Evaluation

Use legitimate survival metrics where implemented, such as:

``` text
concordance index
Brier-style survival evaluation
```

plus product-relevant finish-survival probabilities.

Do not evaluate a survival model solely with ordinary classification
accuracy.

------------------------------------------------------------------------

# 29. Experimental Neural Tier

Neural approaches are research experiments, not requirements.

## MLP

First neural baseline.

Purpose:

> Determine whether a simple neural network improves over tree models on
> the engineered current-state representation.

If not, document and stop.

------------------------------------------------------------------------

# 30. Sequence Models

The dataset naturally contains:

``` text
Driver Lap L-N
...
Driver Lap L
```

Evaluate sequence modelling only after strong tabular baselines exist.

Initial candidates:

``` text
GRU
LSTM
```

Prefer a modest GRU experiment before a Transformer.

Potential windows:

``` text
last 5 laps
last 10 laps
last 20 laps
```

Window lengths must be evaluated rather than assumed.

------------------------------------------------------------------------

# 31. Sequence Leakage

Sequence construction is high risk.

For state Lap L, the sequence must end at L.

Never include:

``` text
L+1
L+2
...
```

Padding/masking must not expose future information.

Add explicit sequence leakage tests.

------------------------------------------------------------------------

# 32. Temporal Transformer

Only evaluate if:

-   GRU/LSTM results justify further work
-   dataset scale supports it
-   compute cost is acceptable
-   there is a clear hypothesis

Do not build a Transformer merely for portfolio buzzwords.

It remains experimental until it beats simpler approaches on meaningful
metrics/cost.

------------------------------------------------------------------------

# 33. TabPFN / Modern Tabular Models

Modern pretrained tabular approaches may be evaluated if their current
implementation supports the dataset/task scale.

Treat them as experiments.

Before adding:

-   verify current library capabilities
-   verify licensing
-   verify dataset limits
-   benchmark memory/runtime
-   compare fairly

Do not architect the project around them.

------------------------------------------------------------------------

# 34. Multi-Task Neural Experiment

Optionally evaluate a shared representation with multiple heads:

``` text
Race State
    |
Shared Encoder
    |
    +--> Win
    +--> Podium
    +--> Points
    +--> DNF
    +--> Finish Position
```

Only attempt after single-task baselines exist.

Document loss weighting and target definitions.

Do not assume multi-task learning helps.

------------------------------------------------------------------------

# 35. Complexity Budget

For every candidate consider:

``` text
predictive quality
calibration
training cost
inference latency
memory
dependency burden
explainability
operational complexity
```

A tiny metric improvement may not justify a much heavier model.

------------------------------------------------------------------------

# 36. Latency Benchmarking

Measure real inference latency.

At minimum benchmark:

``` text
single driver state
full field / race state
batch historical inference
```

Report:

``` text
p50
p95
p99 where sample size supports it
```

Use warmed/cold distinctions where relevant.

Record hardware/environment.

Never invent latency.

------------------------------------------------------------------------

# 37. Training Benchmarking

Record actual:

``` text
training duration
peak memory where practical
artifact size
```

This helps compare production practicality.

------------------------------------------------------------------------

# 38. Model Artifact Metadata

Every saved model should include/associate:

``` text
model_id
model_family
task
dataset_version
feature_set_version
training period
hyperparameters
seed
calibration method
metrics
created_at
code version
```

Do not save anonymous `model.pkl` files without context.

------------------------------------------------------------------------

# 39. Model Registry

A lightweight registry is sufficient.

Do not introduce MLflow merely because it is an MLOps product.

Start with structured local metadata/artifact management.

MLflow may be introduced later if actual experiment volume/operational
requirements justify it.

------------------------------------------------------------------------

# 40. Production Candidate Criteria

A production candidate should satisfy:

``` text
temporal evaluation passed
no known leakage
probability quality competitive
calibration acceptable or corrected legitimately
race-stage behaviour understood
latency acceptable
artifact reproducible
feature availability suitable for runtime
dependency burden acceptable
```

Do not select based only on one leaderboard column.

------------------------------------------------------------------------

# 41. Ensemble Experiments

The original project uses a majority-style ensemble.

Preserve it as a legacy artifact.

For v2, only evaluate ensembles after individual models have been
evaluated.

Potential legitimate approaches:

``` text
probability averaging
weighted averaging
stacking with temporal validation
```

Any meta-model/weights must be trained without test leakage.

Do not ensemble automatically.

------------------------------------------------------------------------

# 42. Explainability Readiness

For production candidates verify compatibility with later truthful
explainability.

Potential:

``` text
coefficients for Logistic Regression
tree SHAP for tree models
permutation importance
model-appropriate neural explanations if later justified
```

Do not select a worse model solely because it is easier to explain, but
include explainability as an engineering tradeoff.

------------------------------------------------------------------------

# 43. Error Analysis

Do not stop at aggregate metrics.

Analyse failures by:

``` text
season
circuit
wet/dry where available
Safety Car context
race stage
starting position
driver/constructor where sample size supports it
tyre state
pit context
retirement status
```

Avoid over-interpreting tiny groups.

------------------------------------------------------------------------

# 44. Probability Sanity Checks

For classification models inspect:

-   probability range
-   overconfidence
-   underconfidence
-   reliability
-   race-level behavior
-   stability across adjacent laps

Sudden probability jumps should be investigated against actual state
changes.

Do not smooth predictions cosmetically to hide instability.

------------------------------------------------------------------------

# 45. Adjacent-Lap Stability

Measure prediction change:

``` text
P(t) -> P(t+1)
```

Large changes are not inherently wrong.

Determine whether large changes correspond to:

-   overtake
-   pit stop
-   Safety Car
-   pace swing
-   retirement
-   weather
-   model instability

This will later support Prediction Timeline explanations.

------------------------------------------------------------------------

# 46. Reproducibility Test

Given the same:

``` text
dataset
feature set
config
seed
code version
```

the experiment should reproduce the same or appropriately
tolerance-bounded result.

Document unavoidable nondeterminism.

------------------------------------------------------------------------

# 47. Results Storage

Suggested:

``` text
artifacts/
├── models/
└── experiments/
    ├── manifests/
    ├── metrics/
    ├── calibration/
    └── comparisons/
```

Do not commit huge redundant artifacts without an explicit repository
policy.

------------------------------------------------------------------------

# 48. Comparison Table

Generate a machine-produced comparison table.

Conceptually:

``` text
Model       LogLoss  Brier  ECE  Top3  p95_ms  Size
----------------------------------------------------
Baseline    ...
LogReg      ...
HGB         ...
XGBoost     ...
LightGBM    ...
CatBoost    ...
ExtraTrees  ...
```

Only actual results.

Do not manually type benchmark values into documentation if they can be
generated.

------------------------------------------------------------------------

# 49. Research Model Separation

Clearly distinguish:

``` text
PRODUCTION CANDIDATE
EXPERIMENTAL
LEGACY
REJECTED
```

A portfolio viewer should not mistake every trained model for something
used in production.

------------------------------------------------------------------------

# 50. Documentation

Create:

``` text
docs/MODEL_LAB_ARCHITECTURE.md
docs/TEMPORAL_EVALUATION_PROTOCOL.md
docs/MODEL_COMPARISON_REPORT.md
docs/MODEL_SELECTION_DECISION.md
```

The final selection decision should explain tradeoffs rather than simply
state a winner.

------------------------------------------------------------------------

# 51. Execution Stages

Execute sequentially:

``` text
M0  Verify Feature Engine
 ↓
M1  Freeze Temporal Evaluation Protocol
 ↓
M2  Build Experiment Framework
 ↓
M3  Implement Racing Baselines
 ↓
M4  Re-evaluate Legacy Models
 ↓
M5  Add LightGBM / CatBoost / RF / ExtraTrees
 ↓
M6  Hyperparameter Tuning Framework
 ↓
M7  Calibration Evaluation
 ↓
M8  Feature Ablation
 ↓
M9  Race-Stage & Error Analysis
 ↓
M10 Ranking Experiment
 ↓
M11 Ordinal Finish Experiment
 ↓
M12 DNF / Survival Experiment
 ↓
M13 Neural Tabular Baseline
 ↓
M14 Sequence Experiment
 ↓
M15 Optional Advanced Research Models
 ↓
M16 Latency / Complexity Benchmark
 ↓
M17 Final Locked Holdout
 ↓
M18 Model Selection Decision
 ↓
M19 Documentation & Phase Exit
```

------------------------------------------------------------------------

# M0 --- Verify Feature Engine

Read:

``` text
V2_PHASE_2_TEMPORAL_FEATURE_ENGINE.md
docs/FEATURE_ENGINE_ARCHITECTURE.md
docs/FEATURE_REGISTRY.md
docs/FEATURE_ENGINE_REPORT.md
```

Confirm:

-   feature set exists
-   leakage tests pass
-   training-serving parity passes
-   dataset/feature versions are known

STOP if temporal safety is unresolved.

------------------------------------------------------------------------

# M1 --- Freeze Temporal Evaluation Protocol

Write:

``` text
docs/TEMPORAL_EVALUATION_PROTOCOL.md
```

Define:

-   development folds
-   tuning rules
-   final holdout
-   race-stage buckets
-   metrics
-   calibration metrics
-   statistical aggregation
-   seed policy
-   holdout access policy

Do this before running model comparisons.

------------------------------------------------------------------------

# M2 --- Experiment Framework

Build:

-   config-driven experiments
-   shared dataset loading
-   shared temporal splitting
-   shared preprocessing boundaries
-   shared metric implementation
-   artifact metadata
-   experiment registry
-   deterministic IDs where useful

Run a tiny smoke experiment.

------------------------------------------------------------------------

# M3 --- Racing Baselines

Implement and evaluate simple baselines first.

These establish the minimum useful performance.

------------------------------------------------------------------------

# M4 --- Legacy Models

Re-evaluate:

``` text
Logistic Regression
HistGradientBoosting
XGBoost
```

using the new feature/data system and temporal protocol.

Do not compare new temporal metrics directly with legacy GroupKFold
metrics without clearly labelling the protocols.

------------------------------------------------------------------------

# M5 --- Additional Tabular Models

Add/evaluate:

``` text
LightGBM
CatBoost
Random Forest
Extra Trees
```

Keep dependencies/versioning controlled.

Use identical temporal evaluation.

------------------------------------------------------------------------

# M6 --- Hyperparameter Tuning

Create training-only temporal tuning.

Use cost-conscious search spaces.

Record every selected parameter and tuning period.

------------------------------------------------------------------------

# M7 --- Calibration

Evaluate raw probabilities.

Only calibrate candidates that need it.

Compare legitimate calibration methods using validation data.

Never calibrate on the final holdout.

------------------------------------------------------------------------

# M8 --- Feature Ablation

Run the Phase 2 family groups.

Measure:

``` text
predictive change
calibration change
latency change
missingness/coverage
complexity
```

Recommend a production feature set, but keep the decision traceable.

------------------------------------------------------------------------

# M9 --- Race-Stage & Error Analysis

Evaluate:

``` text
early
mid
late
```

and relevant race contexts.

Generate actual plots/tables.

------------------------------------------------------------------------

# M10 --- Ranking

Implement at least one legitimate field-ranking candidate if technically
supported.

Compare against classification/current-order baselines.

Do not interpret ranking scores as calibrated probabilities.

------------------------------------------------------------------------

# M11 --- Ordinal Finish

Compare ordinal vs standard regression/ranking approaches for finishing
position.

Document whether ordinal structure helps.

------------------------------------------------------------------------

# M12 --- DNF / Survival

Start with a simple binary DNF baseline.

Then evaluate survival analysis only if labels/censoring are
sufficiently reliable.

Do not force survival modelling if source semantics are inadequate.

------------------------------------------------------------------------

# M13 --- Neural Tabular Baseline

Train a modest MLP using the same temporal protocol.

This establishes whether neural tabular modelling is worth further
effort.

------------------------------------------------------------------------

# M14 --- Sequence Experiment

If justified, evaluate GRU/LSTM with strictly past-only lap windows.

Compare against strong tabular models.

If sequence models do not provide meaningful value, document and stop.

------------------------------------------------------------------------

# M15 --- Optional Advanced Research

Only if earlier evidence justifies:

``` text
Temporal Transformer
TabPFN / modern tabular model
multi-task neural model
```

These are optional.

Skipping them for evidence-based reasons is a valid result.

------------------------------------------------------------------------

# M16 --- Latency / Complexity

Benchmark serious candidates under the same environment.

Record:

``` text
p50/p95/p99 inference
training time
artifact size
memory where practical
dependency burden
```

------------------------------------------------------------------------

# M17 --- Final Locked Holdout

Freeze:

``` text
model families
feature set
hyperparameters
calibration
evaluation code
```

before final holdout access.

Run the locked evaluation.

Record results automatically.

Do not tune after seeing final holdout results without explicitly
declaring the holdout compromised and creating a new protocol.

------------------------------------------------------------------------

# M18 --- Model Selection

Create:

``` text
docs/MODEL_SELECTION_DECISION.md
```

For each serious candidate discuss:

-   predictive quality
-   calibration
-   robustness
-   stage-of-race performance
-   latency
-   complexity
-   explainability
-   runtime feature availability

Select models per task where justified.

There does not need to be one universal model.

------------------------------------------------------------------------

# M19 --- Documentation & Exit

Create/update all required reports.

Then STOP.

Do not automatically implement Monte Carlo or strategy.

------------------------------------------------------------------------

# 52. Quality Gates

## Temporal Evaluation

``` text
[ ] No random final split
[ ] Future races never enter earlier training
[ ] Tuning occurs inside training history
[ ] Calibration excludes test labels
[ ] Final holdout policy documented
```

## Experiment Reproducibility

``` text
[ ] Dataset version recorded
[ ] Feature version recorded
[ ] Model config recorded
[ ] Seed recorded
[ ] Code version recorded
[ ] Artifacts identifiable
```

## Baselines

``` text
[ ] Racing baselines implemented
[ ] Logistic Regression evaluated
[ ] Legacy models re-evaluated temporally
```

## Candidate Models

``` text
[ ] HGB evaluated
[ ] XGBoost evaluated
[ ] LightGBM evaluated
[ ] CatBoost evaluated
[ ] Extra Trees evaluated
[ ] Random Forest evaluated or explicitly deferred
```

## Advanced Tasks

``` text
[ ] Ranking investigated
[ ] Ordinal finish investigated
[ ] DNF baseline investigated
[ ] Survival evaluated or explicitly rejected/deferred
[ ] Neural baseline evaluated or explicitly deferred
[ ] Sequence model evaluated only if justified
```

## Probability Quality

``` text
[ ] Log loss reported
[ ] Brier reported
[ ] Calibration evaluated
[ ] Probability semantics documented
```

## Performance

``` text
[ ] Real latency benchmarked
[ ] Artifact sizes recorded
[ ] Training cost/time recorded where practical
[ ] No invented benchmarks
```

## Documentation

``` text
[ ] Temporal protocol documented
[ ] Model Lab architecture documented
[ ] Comparison report generated
[ ] Selection decision documented
[ ] Legacy vs v2 metrics clearly distinguished
```

------------------------------------------------------------------------

# 53. Anti-Patterns

Never:

``` text
randomly split driver-lap rows for final evaluation
```

Never:

``` text
tune on 2025 then call 2025 an untouched holdout
```

Never:

``` text
fit preprocessing on the full dataset
```

Never:

``` text
calibrate on test labels
```

Never:

``` text
choose a model only because accuracy is highest
```

Never:

``` text
call independent driver probabilities a coherent race distribution without justification
```

Never:

``` text
build a Transformer because it sounds impressive
```

Never:

``` text
ensemble weak models automatically
```

Never:

``` text
hide experiments that did not improve performance
```

Never:

``` text
reuse legacy GroupKFold numbers as v2 temporal benchmarks
```

------------------------------------------------------------------------

# 54. Portfolio Principle

A strong outcome may be:

> LightGBM/CatBoost/XGBoost remained superior to the neural experiments
> after chronological evaluation, so the production predictor uses the
> simpler model while sequence models are retained as documented
> research experiments.

That is stronger engineering than forcing a Transformer into production.

Likewise:

> Telemetry features increased processing cost without meaningful
> probabilistic improvement and were excluded.

is a valid and valuable result.

The project should demonstrate **decision quality**, not technology
count.

------------------------------------------------------------------------

# 55. Definition of Done

Phase 3 is complete when:

1.  Temporal evaluation protocol is frozen and documented.
2.  Final holdout policy exists.
3.  Experiment runs are config-driven and reproducible.
4.  Racing baselines exist.
5.  Legacy LogReg/HGB/XGBoost are re-evaluated under the new protocol.
6.  LightGBM and CatBoost are legitimately evaluated.
7.  Extra Trees is evaluated.
8.  Random Forest is evaluated or explicitly deferred.
9.  Hyperparameter tuning is training-only.
10. Calibration is evaluated without test leakage.
11. Feature-family ablation is performed.
12. Race-stage performance is measured.
13. Error analysis is performed.
14. Ranking is investigated.
15. Ordinal finish modelling is investigated.
16. DNF modelling is investigated.
17. Survival analysis is evaluated or explicitly rejected/deferred.
18. Neural tabular modelling is evaluated or explicitly deferred.
19. Sequence modelling is attempted only if justified.
20. Advanced research models are optional and evidence-driven.
21. Real latency is benchmarked.
22. Artifact metadata is complete.
23. Final holdout is run only after model decisions are frozen.
24. Production candidates are selected per task using documented
    tradeoffs.
25. No metric or benchmark is fabricated.
26. `docs/MODEL_LAB_ARCHITECTURE.md` exists.
27. `docs/TEMPORAL_EVALUATION_PROTOCOL.md` exists.
28. `docs/MODEL_COMPARISON_REPORT.md` exists.
29. `docs/MODEL_SELECTION_DECISION.md` exists.

Then:

``` text
PHASE 3 — MODEL LAB
        |
        v
     COMPLETE
        |
        v
 STOP AND REPORT
        |
        v
WAIT FOR USER APPROVAL
        |
        v
NEXT: RACE STATE / PREDICTION SERVICE
     AND THEN MONTE CARLO
```

------------------------------------------------------------------------

# 56. Final Instructions to OpenCode / Meta Spark 1.3

Read this document completely before modifying modelling code.

1.  Verify Phase 2 first.
2.  Start at M0.
3.  Freeze the evaluation protocol before running model comparisons.
4.  Preserve legacy artifacts/results as historical evidence.
5.  Never mix future races into earlier training.
6.  Never tune/calibrate on final test labels.
7.  Keep the final holdout protected.
8.  Use shared experiment/evaluation infrastructure.
9.  Re-evaluate old models fairly rather than assuming they remain good.
10. Add new model dependencies only when required.
11. Start with strong tabular models before neural complexity.
12. Treat ranking/ordinal/survival as distinct problem formulations.
13. Treat neural/Transformer/TabPFN work as experimental.
14. Use the Phase 2 ablation framework.
15. Benchmark real latency and complexity.
16. Record failed/negative experiments as legitimate results.
17. Generate comparison tables from actual experiment artifacts.
18. Make production selection evidence-driven.
19. Produce all required reports.
20. Stop after M19.
21. Do not begin Monte Carlo, Strategy or later V2 systems without
    explicit approval.

## First action

``` text
M0 — VERIFY FEATURE ENGINE
```

Do not begin model comparison until temporal feature safety and the
evaluation protocol are verified.
