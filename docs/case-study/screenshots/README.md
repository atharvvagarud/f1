# Screenshot Capture Specification (S-SPEC)

Status: CAPTURE_REQUIRED. No validated browser/screenshot engine exists
in this environment (no Chromium, no Playwright; installing one is out
of scope for P11-4), so no screenshots are captured here and none are
fabricated. Capture on the deployable compose stack
(`docker compose up -d` with the validated bundle), desktop viewport
1440×1000, fresh profile (no bookmarks, no personal tabs), crop to the
product surface, and verify captures contain no personal paths, keys,
usernames, or unrelated desktop content.

## 1. Predict (S-PREDICT)

- Route: `/`
- State: frozen 2019-r01-R bottas lap-1 anchor served prediction
  (INDEPENDENT_BINARY, field sum ≈0.56, never normalized).
- Visible: per-driver probability panel, independent-binary note.
- Proves: prediction semantics (unnormalized per-driver probabilities).
- File: `screenshots/01-predict.png`
- Caption facts: 20-driver snapshot; probabilities do not sum to 1.
- Must NOT claim: accuracy, "AI picks the winner", ranking.

## 2. Replay (S-REPLAY)

- Route: `/replay`
- State: 2019-r01-R frame 0 (bottas, lap 1, 2106.767s), CACHE HIT.
- Visible: timeline scrubber at exact checkpoint, cached prediction,
  local LOG_ODDS explanation panel.
- Proves: exact-checkpoint replay + HIT serving + explanation.
- File: `screenshots/02-replay.png`
- Caption facts: 149 races / 9644 checkpoints; exact checkpoints only.
- Must NOT claim: every lap/driver predicted (nulls exist).

## 3. Simulator (S-SIMULATOR)

- Route: `/simulator`
- State: 2022-r01-R perez lap-20, seed 7, 1000-trial distribution.
- Visible: win/podium frequency distribution, mutually-exclusive note.
- Proves: MC frequency semantics (field sums to 1).
- File: `screenshots/03-simulator.png`
- Caption facts: frequencies over valid simulated outcomes, seed shown.
- Must NOT claim: predicted race result, equivalence to prediction.

## 4. Strategy (S-STRATEGY)

- Route: `/strategy`
- State: 2022-r01-R perez lap-20, MAXIMIZE_WIN_PROBABILITY, baseline + 4
  candidates with paired deltas and uncertainty classification.
- Visible: candidate table, delta orientation, INCONCLUSIVE-classified
  uncertainty, no recommendation label.
- Proves: counterfactual comparison without prescription.
- File: `screenshots/04-strategy.png`
- Caption facts: compares candidates; never BEST/RECOMMENDED/OPTIMAL.
- Must NOT claim: optimal strategy found.

## 5. Models (S-MODELS)

- Route: `/models`
- State: static dossier (11 sections).
- Visible: 2025 holdout table (LL 0.0680, Brier 0.0200, Top-1 79.6%,
  Top-3 97.9%), RAW-retained note, limitations.
- Proves: frozen evaluation evidence with limitations.
- File: `screenshots/05-models.png`
- Caption facts: 2025 ONE-SHOT HOLDOUT; LogReg C=0.01, 84 features.
- Must NOT claim: SOTA, comparison with other systems.

## 6. About (S-ABOUT)

- Route: `/about`
- State: static dossier (12 sections).
- Visible: system-semantics lattice (FACT/PREDICTION/SIMULATION/
  STRATEGY/EXPLAINABILITY), dataset statistics, limitations.
- Proves: semantic boundaries and acknowledged limits.
- File: `screenshots/06-about.png`
- Caption facts: architecture + dataset + limitations in one surface.
- Must NOT claim: live data, cloud deployment.
