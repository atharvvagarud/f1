# V3.10 Pit Wall — Final Release Record

Integrated causal race-intelligence workspace, frozen. Programme range
V3.10A–V3.10I on frozen parent `fb0d8d8` (`v3.9-uncertainty-intelligence`).

## What shipped

- **A:** information architecture (race → track → driver → order →
  notes → timeline; track dominant).
- **B:** canonical `WorkspaceState` (`raceId`, `frameIndex`,
  `selectedDriverId`) with one-way URL sync and `?race=&frame=&driver=`.
- **C:** pit-wall shell on validated replay components; primary nav
  PIT WALL / RACES / MODELS / ABOUT + subordinate Expert strip.
- **D:** causal race-control layer (<=T index, recent-5 + disclosure,
  past-only markers, generic next-event).
- **E:** frozen V3.9C uncertainty bundle per anchor, MODEL/SIM/DIFFERENCE
  side-by-side, DETAILS disclosure, no blending.
- **F:** read-only telemetry API over the frozen D9 corpus; causal
  LAP/SECTORS + TYRE HISTORY disclosures; one race-scoped fetch.
- **G:** contextual strategy/counterfactual entries — availability-first,
  explicit cached compare / explicit PIT_IN_N_LAPS intervention, exact
  parity with expert surfaces, expert deep-link hydration.
- **H:** polish — single announcer, calm spatial cue, deduped expert row,
  persistent run controls, render-fill + in-flight request sharing,
  full audit suite (causal poison, identity, budget, a11y).
- **I:** reconciliation of 19 worktree guards via exact V3.10-owned path
  admission + pin arithmetic (5176 + 10 = 5186); zero science changes;
  authoritative Tier-1; freeze commit + annotated tag.

## Frozen contracts (see results/v3/v3_10i/v3_10_contract.json)

Exact frames, no interpolation, no snapping. Causal <=T everywhere.
No blending, no source winner, no recommendation, no scores.
Simulator-conditional counterfactuals. 2025 excluded. 11 routes kept.

## Known limitations (bounded by contract, not freeze failures)

- MC2 coverage 38.14% (3678/9644); STALE/TRACK/WET/MISSING/TERMINAL
  out of scope — next programme is MC2 SIMULATION COVERAGE EXPANSION.
- 2025 excluded from served/analysis surfaces.
- Model×simulation comparable anchors are sparse (e.g. neither strategy
  precompute anchor is E-comparable).
- Event source is contemporaneous-token derived (partial by nature).
- Telemetry missingness renders as em-dash, never zero.
- No Bayesian tyre degradation; no strategy recommendation; no causal
  counterfactual claim; no model/simulation fusion.
- Expert surfaces remain separate by design (context → expert).

## Deferred work

MC2 coverage expansion (forensics → reconstruction → re-evaluation →
regime support if justified → freeze). Wet-weather modelling stays a
separate scientific gate. No V3.11 started here.
