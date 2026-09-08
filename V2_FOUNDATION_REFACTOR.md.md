# F1 Intelligence v2 — Foundation Refactor Plan

> **Purpose:** Behaviour-preserving restructuring of the existing F1 In-Race Winner Prediction repository before F1 Intelligence v2 feature development.
>
> **Execution environment:** OpenCode Desktop + Meta Spark 1.3 Contributor
>
> **Status:** Pre-V2 Foundation Refactor
>
> **Primary rule:** Refactor the existing system without changing its intended behaviour, predictions, model methodology, or user-facing functionality.

---

# 1. Mission

This repository contains an existing university F1 In-Race Winner Prediction application.

It already includes:

- FastF1 historical data ingestion
- Historical race datasets
- Lap checkpoint datasets
- Data cleaning/validation scripts
- Logistic Regression models
- HistGradientBoosting models
- XGBoost models
- Model training/tuning/evaluation scripts
- Saved model pipelines
- FastAPI prediction backend
- Next.js/React/TypeScript frontend
- Legacy Streamlit application
- Historical experiment/evaluation outputs

The project will eventually evolve into:

**F1 Intelligence v2 — an F1 race intelligence, simulation and strategy platform.**

However:

## DO NOT IMPLEMENT V2 FEATURES DURING THIS PLAN.

The purpose of this plan is to make the current repository clean, modular, testable and safe to extend.

The desired transformation is:

```text
CURRENT WORKING PROJECT
        ↓
ESTABLISH BASELINE
        ↓
ADD REGRESSION SAFETY NET
        ↓
CLEAN REPOSITORY
        ↓
RESTRUCTURE EXISTING CODE
        ↓
REMOVE DUPLICATION
        ↓
VERIFY BEHAVIOUR
        ↓
V2-READY FOUNDATION
```

Not:

```text
CURRENT PROJECT
        ↓
REWRITE EVERYTHING
        ↓
IMPLEMENT V2
```

---

# 2. Non-Negotiable Rules

These rules override refactoring convenience.

## 2.1 Preserve working functionality

Existing working functionality must remain functional unless explicitly identified as obsolete and approved for removal.

Do not silently remove behaviour.

---

## 2.2 Do not change ML behaviour

During this refactor, do NOT intentionally change:

- model algorithms
- model parameters
- model training methodology
- model tuning methodology
- model feature definitions
- feature calculations
- probability calculations
- ensemble behaviour
- checkpoint behaviour
- prediction selection logic
- historical datasets
- training/test splits
- model outputs

The current ML methodology has known limitations.

Those limitations will be addressed during F1 Intelligence v2.

This phase is about **structural refactoring**, not model improvement.

---

## 2.3 Do not retrain models unnecessarily

Existing trained model artifacts should remain usable.

Do not retrain models simply because code has moved.

If compatibility requires retraining, STOP and document why before proceeding.

---

## 2.4 Do not introduce V2 functionality

Do NOT implement:

- RaceState engine
- lap-by-lap arbitrary replay
- Monte Carlo simulation
- strategy optimiser
- what-if simulator
- podium prediction
- points prediction
- DNF prediction
- expected finishing position
- prediction calibration
- temporal backtesting
- SHAP explanations
- track visualisation
- Race Engineer AI
- WebSockets
- model monitoring
- drift monitoring

Those belong to later phases.

---

## 2.5 Do not "fix" known ML limitations

Known issues include, but are not limited to:

- GroupKFold is not true temporal validation.
- Driver win probabilities are currently produced independently.
- The majority-vote ensemble is simplistic.
- XGBoost confidence is not necessarily a race-level probability distribution.
- Existing predictions operate at predefined lap checkpoints.

DO NOT fix these during the foundation refactor.

Document them.

Preserve them until their corresponding V2 phases.

---

## 2.6 No infrastructure for portfolio buzzwords

Do NOT introduce:

- Kubernetes
- Kafka
- Redis
- Celery
- PostgreSQL
- TimescaleDB
- MLflow
- Terraform
- AWS services
- microservices

during this refactor unless they are already required by the existing application.

They will be evaluated later based on actual requirements.

---

## 2.7 Avoid unnecessary dependency changes

Do not upgrade frameworks/packages merely because newer versions exist.

Dependency upgrades introduce unrelated risk.

Only change dependencies when required for:

- repository restructuring
- test infrastructure
- security-critical issues
- broken existing setup

Document every significant dependency change.

---

## 2.8 No fake results

Never invent:

- test results
- model metrics
- performance benchmarks
- API latency
- prediction accuracy
- build success
- compatibility claims

If something cannot be tested, state that explicitly.

---

# 3. Existing Repository — Known Architecture

Before modifying anything, verify these findings against the actual repository.

Do not blindly assume this document is perfectly current.

The audited repository currently appears to contain the following architecture.

## Data

FastF1 is used to retrieve historical Formula 1 session/race data.

Existing features include concepts such as:

- position
- session time
- gap to leader
- lap time
- compound
- tyre life
- stint
- fresh tyre state
- pit state
- track status

Historical checkpoint datasets exist for approximately:

```text
Lap 5
Lap 10
Lap 15
Lap 20
Lap 25
```

Historical data primarily covers:

```text
2019–2023
```

Verify exact coverage before changing anything.

---

# 4. Existing ML System

Known candidate models:

```text
Logistic Regression
HistGradientBoosting
XGBoost
```

Existing ML functionality includes:

- dataset construction
- cleaning
- training
- hyperparameter tuning
- race-grouped cross-validation
- baseline comparison
- Top-1 evaluation
- Top-3 evaluation
- Log Loss
- feature analysis
- probability evolution analysis
- saved model pipelines
- model comparison artifacts

Existing models and historical results are valuable evidence.

Do not delete them during cleanup.

---

# 5. Existing Backend

The existing backend uses FastAPI.

Known endpoints include functionality similar to:

```text
GET  /health
GET  /races

POST /predict/ensemble
POST /predict/single-model
```

Verify actual routes.

The existing prediction service currently performs multiple responsibilities, potentially including:

- dataset access
- model discovery
- model loading
- feature selection
- prediction
- race filtering
- ensemble logic
- response formatting

These responsibilities may be separated during this refactor.

Behaviour must remain equivalent.

---

# 6. Existing Frontend

The current primary frontend uses:

```text
Next.js
React
TypeScript
Tailwind
Motion
```

Known existing functionality includes:

- year/race selection
- checkpoint selection
- model selection
- ensemble prediction
- single-model prediction
- probability visualisation
- prediction tables
- driver information
- predicted winner
- confidence display
- actual-result comparison

Preserve working functionality.

---

# 7. Legacy Streamlit Application

A legacy Streamlit application exists.

It appears to duplicate functionality now available through FastAPI + Next.js.

DO NOT immediately delete it.

First determine:

1. What functionality exists in Streamlit?
2. What functionality exists in Next.js?
3. Does Streamlit contain anything unique?
4. Does any documentation still depend on it?
5. Does it contain useful implementation logic not migrated elsewhere?

Only after parity has been established should it be marked for removal/deprecation.

---

# 8. Target Outcome

At completion, the repository should:

- have one clear Git root
- have clear frontend/backend/ML boundaries
- have no accidental generated artifacts tracked
- have minimal duplicated prediction logic
- have automated regression protection
- have deterministic verification fixtures where practical
- have documented architecture
- have documented legacy components
- have clean local development instructions
- retain existing functionality
- retain existing prediction behaviour
- retain existing model artifacts
- be straightforward to extend with F1 Intelligence v2

---

# 9. Proposed Target Architecture

Do NOT blindly create empty directories just to match this diagram.

Use this as architectural guidance.

Adapt based on actual repository dependencies.

```text
f1-intelligence/
│
├── frontend/
│   ├── app/
│   ├── components/
│   ├── features/
│   ├── hooks/
│   ├── lib/
│   └── types/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── schemas/
│   │   └── services/
│   │
│   └── tests/
│
├── ml/
│   ├── data/
│   ├── features/
│   ├── training/
│   ├── evaluation/
│   ├── inference/
│   └── models/
│
├── scripts/
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── README.md
│
├── artifacts/
│   ├── models/
│   └── results/
│
├── tests/
│
├── docs/
│   ├── architecture/
│   ├── V2_REPOSITORY_AUDIT.md
│   └── FOUNDATION_REFACTOR_REPORT.md
│
├── .gitignore
├── README.md
└── ...
```

The exact architecture should reflect the actual codebase.

---

# 10. Refactor Execution Strategy

Execute the refactor sequentially.

```text
R0  Baseline & Inventory
 ↓
R1  Repository Hygiene
 ↓
R2  Characterisation & Regression Tests
 ↓
R3  Python / ML Restructuring
 ↓
R4  FastAPI Restructuring
 ↓
R5  Frontend Restructuring
 ↓
R6  Legacy & Duplication Cleanup
 ↓
R7  Developer Experience
 ↓
R8  Full Regression Verification
 ↓
R9  V2 Readiness Report
```

Do not perform all stages simultaneously.

Complete and verify one stage before proceeding.

---

# R0 — BASELINE & INVENTORY

## Objective

Understand and record the current working state before structural changes.

## Tasks

Inspect:

- complete directory tree
- Python packages
- frontend packages
- datasets
- model artifacts
- result artifacts
- scripts
- FastAPI routes
- frontend routes
- environment variables
- cache directories
- generated files
- setup scripts
- documentation
- Git configuration
- nested Git repositories
- duplicated functionality
- import relationships

Create:

```text
docs/V2_REPOSITORY_AUDIT.md
```

If one already exists, update it rather than blindly replacing useful information.

Document:

### Current architecture

Describe:

```text
FastF1
  ↓
Data preparation
  ↓
Checkpoint datasets
  ↓
ML models
  ↓
FastAPI
  ↓
Next.js
```

Use the actual repository structure.

### What currently works

List verified functionality.

### What should remain

List reusable components.

### What requires restructuring

List structural problems.

### What should eventually be retired

Identify legacy components.

### Known ML limitations

Document without fixing.

### Migration risks

Identify imports, artifacts, scripts or paths likely to break when files move.

---

## Baseline execution

Attempt to run the existing system before restructuring.

Verify where possible:

```text
Python environment installs
FastAPI starts
/health works
/races works
prediction endpoints work
models load
datasets load
frontend installs
frontend builds
frontend starts
frontend communicates with API
```

Record commands and results.

---

## Golden prediction baseline

Create regression fixtures using representative existing predictions.

Choose multiple examples covering:

- different races
- different seasons
- multiple checkpoints
- Logistic Regression
- HistGradientBoosting
- XGBoost
- ensemble prediction

Store representative inputs and outputs under a suitable test fixture location.

Example concept:

```text
tests/
└── fixtures/
    └── legacy_predictions.json
```

The exact format should reflect the current API.

Do not invent expected predictions.

Generate them from the current working implementation.

Record enough precision to detect unintended prediction changes.

---

## R0 Definition of Done

R0 is complete when:

- current architecture is documented
- current application can be run, or blockers are documented
- model locations are known
- dataset locations are known
- API behaviour is recorded
- frontend behaviour is recorded
- representative prediction outputs are captured
- known migration risks are documented

DO NOT proceed if the baseline is poorly understood.

---

# R1 — REPOSITORY HYGIENE

## Objective

Remove accidental/generated repository clutter without affecting source data or valuable artifacts.

## Inspect for

```text
.DS_Store
__MACOSX/
__pycache__/
*.pyc
.next/
node_modules/
FastF1 cache directories
temporary files
editor files
build output
coverage output
nested .git directories
```

The audited ZIP previously contained examples such as:

```text
.DS_Store
__MACOSX/
__pycache__/
frontend/.next/
frontend/.git/
.fastf1_cache/
```

Verify what actually exists.

---

## Git root

The project should ultimately use one intentional repository root.

If `frontend/.git/` is merely an accidental nested repository:

- confirm it is unnecessary
- preserve anything important
- remove the nested Git metadata

Do not delete Git history blindly.

---

## `.gitignore`

Create/update a comprehensive root `.gitignore`.

Cover at minimum:

```text
macOS files
Python caches
Python virtual environments
pytest cache
coverage
FastF1 runtime cache
Node modules
Next.js build output
environment files
IDE metadata
temporary files
logs
```

Do NOT accidentally ignore intentional datasets or model artifacts without documenting the artifact strategy.

---

## Data/artifact policy

Classify files into:

```text
SOURCE CODE
DATASET
MODEL ARTIFACT
EXPERIMENT RESULT
CACHE
GENERATED BUILD OUTPUT
TEMPORARY FILE
```

Document where each belongs.

Do not delete historical ML results merely because they are generated.

They may be useful for the portfolio case study.

---

## R1 Definition of Done

- generated junk is removed
- Git structure is clear
- `.gitignore` is correct
- valuable model artifacts remain
- valuable evaluation artifacts remain
- historical datasets remain
- FastF1 runtime cache is not treated as source code
- application behaviour remains unchanged

Run baseline verification again.

---

# R2 — CHARACTERISATION & REGRESSION TESTS

## Objective

Create a safety net BEFORE major restructuring.

The existing project has limited automated testing.

This must be corrected before moving important code.

---

## Backend tests

Add tests for current behaviour.

At minimum:

### Health

Verify `/health`.

### Race discovery

Verify race listing using controlled/local data.

### Model discovery/loading

Verify supported existing model artifacts can load.

### Prediction response

Verify response schema.

### Probability bounds

Where applicable:

```text
0 <= probability <= 1
```

Do NOT introduce new probability semantics.

### Known race prediction

Verify representative predictions against golden fixtures.

---

## ML characterisation tests

Test current behaviour for:

- feature column selection
- checkpoint discovery
- dataset loading
- model loading
- preprocessing
- single-model prediction
- ensemble selection

These are characterisation tests.

They describe what the system does TODAY.

They do not assert that the existing methodology is theoretically ideal.

---

## Frontend tests

Do not create an enormous frontend testing suite.

Protect critical existing flows.

At minimum test, where practical:

- controls render
- year/race selection works
- checkpoint selection works
- model selection works
- API request construction is correct
- prediction results render
- errors/loading states do not crash the page

Use the project's existing frontend testing infrastructure if present.

If none exists, introduce a minimal appropriate testing setup.

Avoid unnecessary testing dependencies.

---

## R2 Definition of Done

- meaningful backend tests exist
- ML behaviour has regression protection
- golden prediction fixtures are exercised
- critical frontend behaviour has basic protection
- test commands are documented
- tests pass against the pre-refactor behaviour

Only then begin significant code movement.

---

# R3 — PYTHON / ML RESTRUCTURING

## Objective

Separate ML/data responsibilities while preserving behaviour.

---

## Current concern

The existing project mixes concepts across scripts and runtime code.

Separate concerns into logical areas such as:

```text
ml/
├── data/
├── features/
├── training/
├── evaluation/
├── inference/
└── models/
```

Use the actual dependency graph to determine exact modules.

---

## `ml/data`

Responsible for existing:

- FastF1 ingestion
- dataset generation
- cleaning
- dataset validation
- checkpoint data handling

Do NOT change the meaning of generated features.

---

## `ml/features`

Centralise existing feature definitions where practical.

Avoid having feature lists independently duplicated across:

- training
- API
- Streamlit
- evaluation scripts

There should eventually be a clear source of truth.

However, ensure this consolidation does not change ordering or preprocessing expected by existing saved pipelines.

---

## `ml/training`

Move existing:

- model training
- hyperparameter tuning
- model persistence

Do not change training methodology.

---

## `ml/evaluation`

Move existing:

- model comparisons
- baseline comparisons
- error analysis
- feature analysis
- probability evolution analysis

Preserve historical results.

---

## `ml/inference`

Provide reusable runtime functionality for:

- model discovery
- model loading
- checkpoint resolution
- feature preparation
- single-model inference
- existing ensemble logic

This layer should be usable by FastAPI without FastAPI-specific concerns.

---

## Model artifacts

Establish a clear location/policy for saved model artifacts.

For example:

```text
artifacts/models/
```

Do not move models if doing so risks breaking pickle/joblib compatibility without adequate migration.

If moved, compatibility must be tested.

---

## Import safety

After each meaningful move:

- run Python tests
- verify model loading
- verify golden predictions
- check scripts for stale paths/imports

Do not perform the entire restructure before testing.

---

## R3 Definition of Done

- ML/data responsibilities are understandable
- inference is reusable independently from API routing
- feature definitions are not unnecessarily duplicated
- training remains operational
- evaluation scripts remain available
- model artifacts remain loadable
- golden predictions remain equivalent
- no V2 ML behaviour has been introduced

---

# R4 — FASTAPI RESTRUCTURING

## Objective

Make the backend extensible without changing the existing API contract unnecessarily.

Suggested direction:

```text
backend/
└── app/
    ├── main.py
    ├── api/
    │   └── routes/
    ├── schemas/
    ├── services/
    └── core/
```

Adapt to the actual project.

---

## Routes

Move HTTP-specific concerns into route modules.

For example:

```text
health
races
predictions
```

Do not create dozens of tiny files without benefit.

---

## Schemas

Move request/response models into a clear schema layer.

Avoid embedding large Pydantic models throughout route files.

---

## Services

Services should orchestrate application behaviour.

Prediction calculations themselves should use reusable ML/inference modules rather than duplicating ML logic.

Desired dependency direction:

```text
FastAPI route
      ↓
application service
      ↓
ML inference
      ↓
model artifact
```

Avoid:

```text
ML code → FastAPI
```

ML modules should not depend on the web framework.

---

## Configuration

Centralise runtime configuration where useful:

- model directories
- dataset directories
- frontend origins
- environment configuration

Avoid hardcoded machine-specific paths.

---

## API compatibility

Existing frontend calls should continue working unless there is a compelling reason to change the API.

If an endpoint must change:

1. document why
2. update frontend simultaneously
3. update tests
4. verify equivalent functionality

Avoid unnecessary API churn.

---

## R4 Definition of Done

- backend structure is modular
- route logic is thin
- prediction logic is reusable
- schemas are explicit
- configuration is understandable
- existing frontend can still communicate with backend
- golden predictions remain equivalent
- API tests pass

---

# R5 — FRONTEND RESTRUCTURING

## Objective

Make the existing Next.js application easier to extend before replay/simulation features arrive.

Do NOT redesign the entire product.

Do NOT implement the future race intelligence UI yet.

---

## Preserve stack

Keep the existing:

```text
Next.js
React
TypeScript
Tailwind
Motion
```

unless a dependency is demonstrably unnecessary.

---

## Break down oversized page logic

If `app/page.tsx` still contains excessive:

- state
- API logic
- formatting
- charts
- controls
- results
- error handling

move responsibilities into appropriate modules.

Potential structure:

```text
frontend/
├── app/
├── components/
├── features/
│   └── prediction/
├── hooks/
├── lib/
└── types/
```

Do not create abstraction merely for abstraction's sake.

---

## API layer

Centralise frontend API access.

Components should not independently construct backend URLs throughout the application.

---

## Types

Centralise prediction/API TypeScript types where practical.

Avoid duplicate interface definitions.

---

## State

Keep state local where possible.

Do NOT introduce Redux/Zustand/etc. solely because V2 may become larger.

Introduce global state later only if requirements justify it.

---

## Existing UI

Preserve:

- current visual functionality
- controls
- prediction displays
- charts
- driver information
- loading behaviour
- error behaviour

Visual polish is not the objective of this phase.

---

## R5 Definition of Done

- primary page is easier to understand
- API access is centralised
- types are organised
- major prediction UI responsibilities are modular
- current UI still works
- frontend tests pass
- production build succeeds

---

# R6 — LEGACY & DUPLICATION CLEANUP

## Objective

Remove unnecessary duplication only after modern application parity is verified.

---

## Streamlit comparison

Create a temporary feature comparison:

```text
Feature                    Streamlit    Next.js/FastAPI

Race selection                 ?              ?
Checkpoint selection           ?              ?
Model selection                ?              ?
Ensemble                       ?              ?
Probability view               ?              ?
Actual result comparison       ?              ?
Other                          ?              ?
```

Fill this using actual inspection.

---

## If Streamlit contains unique functionality

Either:

- retain Streamlit temporarily

or

- migrate the genuinely useful functionality to the modern application

Do NOT implement V2 functionality while doing so.

---

## If parity exists

Mark Streamlit as deprecated or remove it cleanly.

Update:

- README
- setup instructions
- dependencies
- scripts
- references

---

## Remove duplicated logic

Search for duplicated definitions of:

- feature columns
- checkpoint lists
- model names
- model paths
- dataset paths
- prediction functions
- ensemble logic

Consolidate where safe.

---

## Dead code

Identify dead code through:

- import analysis
- references
- routes
- scripts
- documentation

Do not delete code merely because an automated tool labels it unused.

Confirm first.

---

## R6 Definition of Done

- Streamlit status is explicitly decided
- useful functionality is preserved
- unnecessary duplication is reduced
- dead code removal is justified
- documentation reflects the supported application path
- regression suite passes

---

# R7 — DEVELOPER EXPERIENCE

## Objective

Make the repository easy for another engineer or coding agent to run safely.

---

## Root README

Update development instructions.

Include:

```text
Prerequisites
Python setup
Frontend setup
Data requirements
Model artifact requirements
FastF1 cache behaviour
Backend start command
Frontend start command
Testing
Repository structure
Known limitations
```

Do not yet rewrite the README as the final F1 Intelligence v2 portfolio README.

---

## Environment example

Where appropriate provide:

```text
.env.example
```

Never commit secrets.

---

## Common commands

Make common operations obvious.

Examples:

```text
backend install
frontend install
backend development
frontend development
backend tests
frontend tests
full test suite
frontend build
```

A lightweight Makefile/task runner may be introduced only if it genuinely simplifies development.

Do not introduce complex tooling unnecessarily.

---

## Formatting/linting

Use existing tooling where possible.

Ensure:

- Python code has a consistent formatter/linter strategy
- frontend linting works
- TypeScript checking works

Do not perform huge unrelated formatting changes that make Git history impossible to review.

---

## R7 Definition of Done

A new engineer should be able to understand:

1. what the project is
2. where frontend lives
3. where backend lives
4. where ML code lives
5. where datasets live
6. where models live
7. how to install it
8. how to run it
9. how to test it

without reverse-engineering the repository.

---

# R8 — FULL REGRESSION VERIFICATION

## Objective

Prove that the refactor preserved existing functionality.

Run the complete verification suite.

---

## Repository

Verify:

- one intentional Git root
- no accidental generated directories
- no stale internal paths
- no broken scripts

---

## Python

Verify:

- imports
- tests
- model loading
- dataset loading
- inference
- existing training scripts where practical
- existing evaluation scripts where practical

---

## Prediction regression

Run all golden fixtures.

Compare:

```text
BEFORE REFACTOR
vs
AFTER REFACTOR
```

Predictions should be equivalent within appropriate floating-point tolerance.

Investigate every unexpected difference.

Do not simply update fixtures to make tests pass.

If behaviour intentionally changed for a necessary reason, document and justify it.

---

## API

Verify:

```text
/health
/races
single-model prediction
ensemble prediction
```

plus any other existing endpoints.

---

## Frontend

Verify:

- install
- lint
- type checking
- tests
- production build
- development startup
- backend communication
- race selection
- checkpoint selection
- model selection
- prediction rendering

---

## Manual smoke test

Perform at least one complete existing user flow:

```text
Start backend
      ↓
Start frontend
      ↓
Select historical race
      ↓
Select checkpoint
      ↓
Run prediction
      ↓
Inspect predicted winner
      ↓
Inspect probabilities
      ↓
Compare result
```

Document any environment limitations that prevent manual verification.

---

# R9 — V2 READINESS REPORT

Create:

```text
docs/FOUNDATION_REFACTOR_REPORT.md
```

This document must contain:

# Foundation Refactor Summary

What changed?

# Repository Before

Brief description.

# Repository After

Brief description.

# Files Moved

Important migrations.

# Components Removed

Explain why.

# Components Preserved

Explain why.

# Testing Added

List actual tests.

# Regression Results

Report actual results.

# Prediction Equivalence

State whether legacy prediction outputs remained equivalent.

# Remaining Technical Debt

Do not hide problems.

# Known ML Limitations

Explicitly retain:

- non-temporal legacy evaluation
- independent binary probability issue
- simplistic legacy ensemble
- fixed checkpoint architecture
- any additional discovered limitations

# V2 Readiness

Assess whether the repository is ready for:

```text
PHASE 1 — Race State Engine
```

# Recommended Next Step

Do NOT automatically implement it.

State the recommended next task and STOP.

---

# 11. Required Quality Gates

The following gates must remain green as applicable.

## Gate A — Repository

```text
[ ] Clean repository structure
[ ] One intentional Git root
[ ] Generated files excluded
[ ] Artifact policy documented
```

## Gate B — Existing ML

```text
[ ] Existing datasets load
[ ] Existing models load
[ ] Existing feature ordering preserved
[ ] Golden predictions match
```

## Gate C — Backend

```text
[ ] Backend starts
[ ] Health endpoint passes
[ ] Race endpoint passes
[ ] Single-model prediction works
[ ] Ensemble prediction works
[ ] Automated tests pass
```

## Gate D — Frontend

```text
[ ] Dependencies install
[ ] Lint passes
[ ] Type checking passes
[ ] Tests pass
[ ] Production build succeeds
[ ] Existing prediction flow works
```

## Gate E — Documentation

```text
[ ] Repository architecture documented
[ ] Setup documented
[ ] Testing documented
[ ] Legacy components documented
[ ] Known ML limitations documented
[ ] Foundation refactor report created
```

---

# 12. Refactoring Philosophy

Prefer:

```text
small change
    ↓
test
    ↓
small change
    ↓
test
```

over:

```text
move entire repository
    ↓
rewrite imports
    ↓
hope it works
```

---

# 13. Behavioural Equivalence

The central success criterion is:

```text
same historical input
        ↓
same existing feature pipeline
        ↓
same existing model artifact
        ↓
same existing prediction behaviour
```

The internal architecture may change.

The intended existing output should not.

---

# 14. Do Not Hide Failures

If a test fails:

STOP.

Determine whether the failure is:

```text
pre-existing
refactor regression
environment problem
artifact incompatibility
dependency issue
test issue
```

Document the classification.

Do not:

- delete failing tests
- weaken assertions without justification
- regenerate golden fixtures after a regression
- silently modify model output
- skip important tests to reach completion

---

# 15. Cost-Conscious Agent Behaviour

This project is being developed using an AI coding agent.

Work efficiently.

Before editing:

1. inspect relevant files
2. understand dependencies
3. plan the smallest coherent change
4. modify only relevant files
5. run targeted verification
6. proceed only after success

Do not repeatedly scan the entire repository after every minor change.

Do not rewrite files unnecessarily.

Do not generate enormous status explanations after every small action.

Prefer targeted searches and targeted tests.

---

# 16. Git Strategy

Where possible, each refactor stage should correspond to a logical commit boundary.

Suggested sequence:

```text
refactor: establish legacy baseline

chore: clean repository artifacts

test: add legacy regression coverage

refactor: reorganise ml modules

refactor: reorganise fastapi backend

refactor: modularise prediction frontend

refactor: remove legacy duplication

docs: improve development workflow

docs: add foundation refactor report
```

Do not commit broken intermediate states where avoidable.

Do not rewrite Git history unless explicitly instructed.

---

# 17. Important Architectural Boundary for V2

The future F1 Intelligence architecture will eventually resemble:

```text
                        ┌── Prediction Engine
                        │
F1 Data → Ingestion → RaceState ── Simulation Engine
                        │                │
                        │                └── Strategy Engine
                        │
                        ├── Replay Engine
                        │
                        └── What-If Engine
                                │
                                ▼
                             FastAPI
                                │
                                ▼
                             Next.js
```

However:

## DO NOT BUILD THIS ARCHITECTURE YET.

The foundation refactor should merely ensure the repository can support it cleanly.

In particular, do not create placeholder RaceState/simulator/strategy modules just to anticipate future work.

They should be introduced when their requirements are implemented.

---

# 18. Exit Criteria

The Foundation Refactor is complete only when:

1. Existing application functionality is preserved.

2. Existing prediction behaviour has regression protection.

3. The repository has a clear structure.

4. ML, backend and frontend responsibilities have clear boundaries.

5. Duplicate prediction logic has been reduced.

6. Generated/cache files are separated from source.

7. Legacy Streamlit status has been resolved.

8. Automated tests protect important existing behaviour.

9. Setup and development instructions are accurate.

10. The frontend builds successfully.

11. The backend starts successfully.

12. Existing model artifacts load successfully.

13. Existing prediction endpoints work.

14. Golden prediction fixtures match.

15. `docs/FOUNDATION_REFACTOR_REPORT.md` exists.

16. Known limitations remain documented rather than silently "fixed."

17. No F1 Intelligence v2 product features have been implemented.

At that point:

```text
FOUNDATION REFACTOR
        │
        ▼
      COMPLETE
        │
        ▼
STOP AND REPORT RESULTS
        │
        ▼
WAIT FOR USER APPROVAL
        │
        ▼
PHASE 1 — RACE STATE ENGINE
```

Do not automatically begin Phase 1.

---

# 19. Instructions to the Coding Agent

When this file is supplied to OpenCode or another coding agent:

1. Read this entire document before modifying code.

2. Inspect the repository and verify assumptions against the actual files.

3. Begin at **R0**.

4. Do not implement future V2 features.

5. Complete stages sequentially.

6. Do not mark a stage complete without running its verification.

7. Preserve existing behaviour.

8. Use tests as the refactor safety net.

9. Never modify golden outputs merely to hide a regression.

10. Keep changes focused and reviewable.

11. Maintain/update `docs/V2_REPOSITORY_AUDIT.md` as discoveries are made.

12. At the end, create `docs/FOUNDATION_REFACTOR_REPORT.md`.

13. Stop after R9.

14. Report:
    - completed stages
    - files/modules significantly changed
    - tests added
    - exact verification commands run
    - actual test/build results
    - prediction regression result
    - unresolved issues
    - technical debt
    - readiness for Phase 1

15. **Do not begin Phase 1 without explicit user instruction.**

---

# 20. First Instruction

Start with:

```text
R0 — BASELINE & INVENTORY
```

Inspect the repository before making structural changes.

Establish the current working baseline and regression fixtures first.

**Do not refactor anything substantial until the baseline is captured.**