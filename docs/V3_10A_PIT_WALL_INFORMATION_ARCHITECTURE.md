# V3.10A — Pit Wall UX + Information Architecture

Audit/design-contract stage. No frontend implementation, no science changes,
no telemetry features, no MC2 coverage work.

- V3.9 freeze: commit `fb0d8d8772bdc1343bc6be6c5ff9ee68cddd7203`, tag
  `v3.9-uncertainty-intelligence` (HEAD matches tag commit; verified).
- V3.8 consensus tag immutable. MC2 freeze immutable.
- Python collection: 5176 (verified). Frontend suite: 386 (not re-run;
  audit-only). Worktree was clean at start.
- Graphify: `graphify update .` before and after; 19308 nodes / 43446 links,
  topology unchanged (no runtime/science changes).
- Git: no commit, no tag, no push (review gate).

Governing principle: **more intelligence underneath, less interface on top.**

## 1. Current route inventory (summary)

10 routes audited (full census in `results/v3/v3_10a/route_inventory.json`):

| Route | Class | Future role |
|---|---|---|
| `/` Predict | candidate-for-merge | merge decision block into pit-wall driver intelligence |
| `/replay` | primary | pit-wall backbone; keep as deep surface |
| `/simulator` | expert | expert-only, via DETAILS links |
| `/consensus` | expert | expert-only, via DETAILS deep-link |
| `/uncertainty` | expert | expert-only, via DETAILS deep-link |
| `/strategy` | expert | via EXPLORE STRATEGY contextual entry |
| `/counterfactuals` | expert | via EXPLORE ALTERNATIVE intentional action |
| `/models` | supporting | keep evidence terminal |
| `/about` | supporting | keep dossier |
| `/spatial` | redundant | dev harness, stays unlinked |

No routes deleted in V3.10A. Nothing removed from default is deleted:
everything stays one selection / expansion / tab / drawer away.

## 2. Duplicated concepts (merge targets for V3.10B+)

1. Race/state picker reimplemented per workstation (replay, simulator,
   strategy, counterfactuals each own `raceId`+`frameIndex` and refetch the
   full timeline). Single shared store is V3.10B.
2. Model-vs-simulation field table in both `/consensus` and `/uncertainty`.
3. Demo-anchor availability pattern duplicated in `/consensus`, `/uncertainty`.
4. Independent-binary explainer at 4 reading sites (justified provenance,
   but tier it: one line by default).
5. Flag/status in both ContextBar and spatial strip at same T (keep one).
6. Probability-evolution chart vs field-at-T tables never linked by shared T.

## 3. Highest cognitive-load areas

- `/counterfactuals`: factual/simulated x alt/base x targets/items + rival.
- `/consensus` + `/uncertainty`: full-field tables + inspector + viz +
  telemetry simultaneously.
- `/strategy`: 8-fact strip + catalogue + seed + 9 alternatives pre-result.
- `/replay`: standings (7x20) + track + prediction + trend at once.
- Anchor-lap vs leader-lap duality; seed-as-identity; anchor vs analysed
  driver; relative bar widths with absolute labels.

## 4. Recommended primary workspace: PIT WALL

Hierarchy (justified in `workspace_hierarchy.json`):

- A. RACE HEADER / STATE — event, lap, race time, single status chip.
- B. TRACK / REPLAY — spatial map (shared T) + compact running order.
- C. SELECTED DRIVER INTELLIGENCE — position/gap, MODEL+SIM pair,
  tyre/stint, DETAILS, EXPLORE STRATEGY, EXPLORE ALTERNATIVE.
- D. RACE CONTROL / EVENT FEED — chronological, click-to-seek, causal-gated.
- E. STRATEGY / DECISION CONTEXT — availability line + entry (not a dash).
- F. TIMELINE / REPLAY NAVIGATION — the only clock; moves everything to T.

Read order: where are we → where is everyone → my driver → what changed →
move in time. Telemetry windows: fixed contextual panes + tabs + drawers.
Configurable draggable modules rejected (Bloomberg-terminal complexity).

## 5. Default information budget (L0)

Race/lap, replay state, track, selected driver, position/gap, MODEL + SIM
(one value each), current tyre/stint, latest important RC event, strategy
availability/status, timeline with markers. Everything else requires
selection, expansion, tab, drawer, or context panel.

## 6. Selected-driver model

Single shared `selectedDriverId` tagged with `raceId` (extends the existing
ReplayView pattern). Track, standings, intelligence panels, and feed all
resolve to it. Immediate reveal: position/gap, MODEL/SIM, compound+age.
DETAILS: ranks, disagreement, k/n/SE/Wilson, family provenance, U3 note.
Entries: EXPLORE STRATEGY / EXPLORE ALTERNATIVE prefilled. Sector/lap via
expansion tab (completed laps only). Never all at once by default.

## 7. Replay state model

Canonical: `raceId` + `frameIndex` (exact discrete frames, no interpolation)
+ `selectedDriverId` + checkpoint-gated intelligence context. Timeline moves
the whole workspace to one T; followers admit frames only on exact
race+index+clock agreement (existing `useSpatialTrack` pattern generalized).
Play/pause, speed, lap jump (existing), plus prev/next event seeks derived
from the event feed. Predictions only at `is_prediction_checkpoint`.
Causal gating: only events <= T visible; future never leaks.

## 8. Navigation simplification

`PIT WALL / RACES / MODELS / ABOUT`. Expert tools contextual-only
(DETAILS / EXPLORE deep-links carrying shared T + driver). 9 items -> 4.

## 9. Integration contracts

- Prediction: L0 compact MODEL/SIM -> DETAILS (checkpoints, trend).
- Consensus: L0 `MODEL x / SIM y / Δ z` row -> DETAILS -> full page.
- Uncertainty: L0 Δ + precision line (`n=… 95% […, …]`) -> DETAILS
  (WilsonViz, U3, provenance) -> full page. No agreement buckets, no winner.
- Strategy: availability line -> EXPLORE STRATEGY (prefilled) -> expert
  page. V3.6 semantics kept; no recommendation language.
- Counterfactuals: intentional EXPLORE ALTERNATIVE -> builder + deltas.
  Simulator-conditional framing kept; no causal alternate-history claims.
- Race-control feed: flag/SC/VSC/red, pits, retirements, RC messages;
  chronological, click-to-seek, causal-gated.
- Sector/lap: selected-driver expansion tab; completed laps only; answers
  "where did time go" without permanent space.
- Tyre/stint: L0 current chip (compound + age); L2 completed-stint drawer;
  future stints hidden at T.
- SC/VSC: single status strip + feed/timeline markers; never simulated GPS
  position; no redundant overlays.

## 10. Terminology placement

Keep by default (short form): independent-binary one-liner, STAY OUT / PIT
NOW / PIT NEXT LAP, Δ definition, refusal chips, flag/weather states, AT T
chips. Move to DETAILS/methodology/About: full family names, k/SE/Wilson
grids, U3 parameter detail, anchor mechanics, contract/engine strings, seeds,
Spearman/Jaccard internals, catalogue mechanics. Full map in
`terminology_audit.json`. No semantics weakened.

## 11. Desktop wireframe (~1600)

```
+================================================================+
| F1 Intelligence   PIT WALL RACES MODELS ABOUT    Historical     |
+================================================================+
| [A] MON 2024 R21 . LAP 34/57 . 1:23:45 . [SAFETY CAR] . 20 drv |
+================================================================+
| [B] TRACK MAP              | [C] DRIVER · VER . P3 . +4.2s      |
|  (shared T, VER highlight) | MODEL 0.312 . SIM 0.287 . Δ -0.025|
|                            | Tyre MEDIUM age 12 . [DETAILS]    |
|                            | [EXPLORE STRATEGY] [EXPLORE ALT]  |
| [B] ORDER P DRV GAP TYRE   +----------------------------------+
|  1 NOR ...  2 LEC ...      | [D] RACE CONTROL (<= T)            |
|  3 VER +4.2s MED ...        |  L33 VSC ...  L31 PIT NOR ...     |
+================================================================+
| [F] |◀ ◀ ▶/❚❚ ▶ ▶| 1x 2x | Lap [__] Go | FRAME 812/1400 =====●== |
|     ⚑ VSC L33 · ⛽ PIT L31 · ☰ markers · prev/next event       |
+================================================================+
DETAILS opens as side drawer: ranks, k/n/SE/Wilson + interval, U3 note,
family provenance, contract versions. Sector/lap + stint history are
tabs inside the driver panel, not new panes.
```

## 12. Tablet wireframe (~820)

```
+==========================================+
| PIT WALL RACES MODELS ABOUT              |
+==========================================+
| [A] header strip (wraps to 2 rows)       |
+==========================================+
| [B] TRACK full width (shared T)          |
+==========================================+
| [ORDER | DRIVER]  (tabbed, one at a time)|
| ORDER: tower (5 cols, scroll)            |
| DRIVER: MODEL/SIM/Δ + tyre + entries     |
+==========================================+
| [D] latest 3 events + [expand]           |
+==========================================+
| [F] transport + timeline full width      |
+==========================================+
DETAILS becomes a full overlay drawer.
```

## 13. Mobile wireframe (390)

```
+======================+
| PIT WALL RACES ...   |
+======================+
| [A] LAP 34 . [SC]    |
| race time . gap      |
+======================+
| [B] TRACK (compact)  |
| transport essential  |
+======================+
| [C] VER P3 +4.2s     |
| MODEL . SIM . Δ      |
| tyre chip [DETAILS]  |
+======================+
| [F] timeline+markers |
+======================+
| [D] latest event     |
| [ORDER|DRIVER|MORE]  |
+======================+
Priority: replay/state -> driver -> timeline -> feed. Standings tower,
DETAILS, strategy/counterfactual entries, sector/stint history all behind
tabs. Scrubber thumb >= 44px target. Never a stacked copy of desktop.
```

## 14. Accessibility model (retained)

Keyboard transport + tabs with arrow keys, focus-visible outlines, semantic
landmarks (`main/nav/header/section/table`), `role=status/alert` live
regions, `aria-expanded` driver rows, `th scope`, table captions,
text+color status (never color-only), `prefers-reduced-motion` kill-switch,
native buttons/inputs/selects. No density-at-cost-of-a11y trade.

## 15. Expert-view policy

All deep pages stay reachable (reviewers/recruiters/inspection) via
contextual deep-links carrying (race, T, driver) plus direct URLs. No page
deleted without migration; no evidence deleted.

## 16. Portfolio demo journey (30-60s)

Choose race -> jump to event marker (whole workspace moves) -> select driver
-> read MODEL/SIM -> DETAILS (Δ, precision, provenance) -> EXPLORE STRATEGY
(prefilled, no recommendation language) -> EXPLORE ALTERNATIVE
(simulator-conditional deltas) -> back to identical T. One race, one T, one
driver; coherent, not six pages. Full script in `demo_user_journey.json`.

## 17. Risk register + stage sequence

Top risks: state coupling, causal leakage, terminology dilution, selection
divergence, timeline drift, stacked-mobile, a11y regression, recommendation
creep, accidental MC2 start. Mitigations per risk in
`implementation_risk_register.json`.

Recommended: B state store -> C shell+nav -> D feed+timeline -> E driver
intelligence -> F sector/tyre -> G strategy/counterfactual entries ->
H responsive/a11y polish -> I freeze. State before shell so nav never
fronts divergent clocks.

## 18. Validation

`validation.json` records: freeze integrity (HEAD == tag commit), clean
start, graphify 19308/43446 unchanged, Python collection 5176 match,
frontend 386 untouched (smoke only, no Tier-1), pathology P1-P20 all zero,
no commit/tag/push. MC2 eligibility 3678/9644 (38.14%) deferred, untouched.

## 19. Classification

**A. PIT_WALL_INFORMATION_ARCHITECTURE_READY** — review before any
implementation. Next gate: human review, then V3.10B (shared workspace state
architecture only).
