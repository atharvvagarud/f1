# Phase 5 — Historical Race Replay

R0 architecture/contract stage. READ-ONLY findings + implementation contract
for R1–R8. **No code changed in R0.** Phase 5 builds replay on the frozen
Phase-4 primitives; it does not mutate them, retrain, serve 2025, normalize
probabilities, or add infrastructure speculatively.

Phase-4 seal: commit `4f26801ffb0bb1a10725d6c78fba11c5547cb432`, tag
`v2-race-state-prediction-phase4`, contract v1.

---

## 1. Objective

Let the user select a historical race (2018–2024), load its timeline, move
chronologically through it (first/previous/next/last/jump, play/pause,
0.5x–8x speeds), inspect the factual `RaceState` at the selected point
(order, gaps, tyres, pit/stint context, weather, race control, staleness),
and see frozen winner probabilities at prediction checkpoints plus their
evolution — all with strict historical temporal semantics (`<= T`,
no fall-forward, no interpolation presented as inference).

Out of scope for Phase 5: track SVG rendering, Monte Carlo, strategy engine,
what-if simulation, richer probability UI beyond the checkpoint timeline
contract (§17). Those are future-phase consumers of the seams in §21.

---

## 2. Frozen Inputs from Phase 4

| Input | Frozen value | Source |
|---|---|---|
| Time-T key | `AnchorObservation(race_id, anchor_driver_id, anchor_lap_number, anchor_state_time_s)`; exact match, never nearest/rounded | `v2/race_state.py`, `v2/race_state_reconstruction.py` |
| `RaceState` | Complete roster in `driver_id` order; observable members with lap/time/position/gap/tyre/stint facts + `observation_age_s`; unobservable = explicit nulls; past-as-of weather; verbatim race control; `to_dict()` | `v2/race_state.py` |
| `RaceStateReconstructor` | Exact 4-key anchor → `RaceState`; `RaceNotFoundError` / `AnchorNotFoundError` | `v2/race_state_reconstruction.py` |
| `RaceStateFeatureBridge` | Observable-only `FeatureRequest`s at each driver's OWN observed lap/time → exact ALL_84 `FeatureBatch`; read-only; per-race slice cache | `v2/race_state_features.py` |
| `RacePredictionEngine` | One batch `predict_proba` → `PredictionSnapshot`; null + `NO_OBSERVATION_AT_SNAPSHOT`; `INDEPENDENT_BINARY`; do-not-renormalize note | `v2/prediction.py` |
| Anchor discovery | `GET /v2/races/{race_id}/states`, deterministic `(state_time_s, lap_number, driver_id)` order, paginated (limit 1–500, default 100) | `api/v2_service.py`, `api/v2_routes.py` |
| Endpoints | `/v2/races`, `/states`, `/state`, `POST /v2/predictions/winner-snapshot`; 404/422/503/500 mapping | `docs/PHASE4_V2_API_CONTRACT.json` |
| Serving scope | 2018–2024 only; 2025 → 404 | `api/v2_service.py` (`SERVED_SEASONS`) |
| Cost fact | Full-field snapshot ≈ **~12 s** (features dominate; inference ~7 ms; warm state ~39 ms) | `docs/PHASE4_FINAL_REPORT.md` §16 |
| Corpus | 189,420 D9 rows (Phase-1 tag); **162,728 rows / 149 races** in 2018–2024 serving scope (measured R0, §3) | freeze manifest + R0 audit |

---

## 3. Repository Audit

**Docs read:** `PHASE5_REPLAY_HANDOFF.md`, `PHASE4_FINAL_REPORT.md`,
`PHASE4_FREEZE_MANIFEST.json`, `PHASE4_V2_API_CONTRACT.json`,
`PHASE4_RACE_STATE_PREDICTION_PLAN.md` (§§1–25 incl. R1–R7 records).

**Implementation verified (not just reports):**

- `v2/race_state.py` — `AnchorObservation`, `DriverRaceState`
  (`observable` + full-null `unobserved()` factory), `RaceContext`
  (progress = leader laps ÷ scheduled, never eventual total),
  `WeatherState` (backward-as-of + age), `RaceControlState` (D9-exact
  `flag_*` + `track_state` token + last-message lineage, no text),
  `RaceState` (anchor membership/observability/`observed_time <= T`/age
  consistency enforced at construction). stdlib-only.
- `v2/race_state_reconstruction.py` — sole sync authority is frozen
  `RaceIndex`; gap geometry is frozen F6 `gaps_for_snapshot` evaluated at
  each member's **own observed time** (not at T); weather/RC/context come
  from the **anchor target row**; `end_lap` ignored via allowlist.
  Key R0 finding: per-driver factual entries (sync + gaps) depend only on
  T, not on which anchor driver was chosen; only the anchor-row-sourced
  weather/RC/context block can vary with anchor choice at shared T.
- `v2/prediction.py` — `ModelIdentity` (winner/is_winner/
  eligible_is_winner, ALL_84/v8, LogReg recorded params, RAW,
  `INDEPENDENT_BINARY`, 2018–2024, dim 106, artifact SHA, spec fp);
  positional `identities[i] ↔ proba[i]` merge; unobservable → null +
  single reason `NO_OBSERVATION_AT_SNAPSHOT`.
- `api/v2_service.py` — process-local singleton; corpus + `PriorHistory`
  + reconstructor + bridge + predictor + engine loaded once (~6.8 s);
  `list_anchors` returns identity-only rows in canonical order.
- `api/v2_routes.py` / `api/v2_schemas.py` — thin routing, `{error,
  detail}` bodies, probabilities pass through verbatim.

**Canonical data reality (measured R0 on 2018–2024 D9 scope):**

- 162,728 rows / 149 races; per-race rows min 60 (2021-r12-R, partial),
  max 1534, mean 1092.1.
- Unique `state_time_s` per race: mean 1091.5, total **162,639** frames.
- Multi-driver same-T groups corpus-wide: **58** (0.04% of rows).
- Context agreement at shared T: `race_leader_laps_at_state` and
  `wx_air_temp_c` agree in all 58 groups; `track_state` disagrees in
  **1** group → anchor tie-break is still required for determinism (§7).
- 2022 `track_state` tokens: `all_clear` 20827, `safety_car` 1295,
  `yellow` 1004, `vsc` 364, `vsc_ending` 49, `red_flag` 38 — SC/VSC/red
  are representable from frozen flags; no new detection needed.
- Side entities (2022-r01-R shapes): weather 163 rows
  (`observed_at_s` clock), race_control 60 rows (`observed_at_s`,
  category/flag/status/message_text), pit_stops 59 rows
  (`pit_in_s`/`pit_out_s`), stints 78 rows (start-side facts +
  `end_lap` future, must stay firewalled).
- Leader-lap checkpoint totals: max leader laps 3–87/race, mean 59.9;
  **8,926** leader-lap transitions across 149 races.
- Cost arithmetic at ~12 s/snapshot: every unique-T frame → **~542
  CPU-hours** (infeasible); leader-lap cadence → **~29.8 CPU-hours**
  one-time offline (feasible, §9–10).

**Tests present:** `test_v2_phase4_r1..r6` + `test_v2_phase4_freeze`;
canonical fixtures reused in §22: 2023-r01-R alonso-28 (full field),
2022-r07-R norris-30 (stale), 2021-r12-R hamilton-2 (partial),
2022-r18-R ocon-2 (red), 2021-r08 stroll same-T tie, Monaco 2022
(pre-existing NaN xfails, legacy only).

**Frontend reality (`frontend/`):** Next.js; `lib/api.ts` calls **legacy**
routes only (`/races`, `/predict/ensemble`, `/predict/single-model`) —
V2 is untouched by the UI. Page composes `usePrediction` hook +
`PredictionHero`/`EnsembleResults`/`SingleResults`/`PredictionTabs`/
`ControlsPanel` under `features/prediction/`. No replay code exists;
no state-management library beyond hooks. Replay enters as a new
`features/replay/` slice + V2 API client, leaving the legacy prediction
feature untouched (§16).

---

## 4. Historical Time Model

- **Authoritative factual coordinate:** `state_time_s`, the D9 LAP_END
  clock of an exact anchor row. Knowledge boundary = all information
  observable at or before T per field availability class. Verified in
  `v2/race_state_reconstruction.py` (`sync_lookup(race_id, m, T)`,
  `observed_time <= T` enforced by `RaceState.__post_init__`).
- **Anchors:** every canonical driver-lap row (race, driver, lap, T) is a
  valid anchor; enumerated by `GET .../states` in `(state_time_s,
  lap_number, driver_id)` order. Anchors are per driver-lap, not
  race-global.
- **Shared timestamps:** possible (58 cross-driver groups corpus-wide)
  but rare; each observation keeps its own anchor identity.
- **Ordering:** `(state_time_s, lap_number, driver_id)` is deterministic;
  never input row order (matches `list_anchors` sort).
- **`lap_number` is DRIVER PROGRESS**, never a global race clock.
  Same-lap spreads reach 121 s dry / 1320 s red (Phase-4 plan §3). Any
  "lap" navigation must name its reference (leader lap, §11).
- **Lapped drivers:** appear with their own observed lap/time; staleness
  grows naturally via `observation_age_s`. No special casing.
- **No observation yet:** `observable=False`, full nulls. Zero-state
  entrants (6 corpus-wide) and pre-first-observation members are
  deliberately indistinguishable in one snapshot.
- **Stale drivers:** stay observable with `(observed_lap,
  observed_time_s, observation_age_s)` provenance; no cutoff drops them.
- **Retirement / no further observations:** represented only as growing
  age + absence of newer rows. Never infer retirement from future
  classification (LABEL_ONLY firewall).
- **Red flags:** temporal sync is unchanged; `flag_red=true` /
  `track_state='red_flag'` marks suspension; seconds-gap validity=false
  + lapdiff companions do the work (frozen F6 tri-state).
- **SC/VSC:** `flag_safety_car` / `flag_vsc` + `track_state` tokens
  (`safety_car`, `yellow`, `vsc`, `vsc_ending`) + as-of RC messages.
- **Partial races:** same rule on thin histories (e.g. 2021-r12-R: 60
  rows, leader laps max 3); `scheduled_laps` nullable; progress via
  leader laps ÷ scheduled.

---

## 5. Canonical Replay Timeline Decision

**Recommended: D — race-wide synchronized event timeline derived from
canonical observations** — concretely: **one frame per unique
`state_time_s` per race, ordered by `(state_time_s, lap_number,
driver_id)` of its canonical representative observation**, each frame
resolving to exactly one `AnchorObservation` (the representative) and
hence one exact `RaceState` via the frozen reconstructor.

Assessment of options:

| Option | Temporal correctness | Frames/race (mean) | Prediction cost | Verdict |
|---|---|---|---|---|
| A. every driver-state row a frame | Exact; but 58 same-T pairs produce duplicate-content frames differing at most in anchor-row context (1 known `track_state` divergence) | ~1092 | Same as D +58 redundant snapshots | Rejected: duplicate-equivalent frames |
| B. one frame per unique `state_time_s` | Exact; dedups the 58 collisions deterministically | ~1091 | 162,639 total → ~542 CPU-h if predicted per frame | **Accepted as frame cadence** (factual only; predictions on separate cadence §9) |
| C. one frame per selected anchor driver/lap | Breaks for lapped/stale drivers; anchor driver's laps ≠ race progression | ~55 but lossy | Cheap but wrong | Rejected: confuses driver progress with race clock |
| D. synchronized event timeline (B + representative anchor + metadata) | Exact; deterministic; complete-roster per frame | ~1091 factual frames | Decoupled via checkpoints | **RECOMMENDED** |
| E. wall-clock resampling (e.g. every 5 s) | Requires interpolation = new temporal semantics; forbidden without explicit contract | Arbitrary | Arbitrary | Rejected: freeze conflict by construction |

Why D-over-B matters: B alone leaves "which anchor?" ambiguous at the 58
shared-T groups; D adds the representative-anchor rule (§7), making every
frame exactly one frozen `AnchorObservation`. UX: ~1,091 cheap factual
frames/race gives smooth scrubbing (warm reconstruction ~39 ms, §19);
backward/forward navigation is index arithmetic; reproducibility is a pure
function of canonical data + contract version (§18).

Lapped/stale/partial/red behavior is inherited verbatim from `RaceState`
semantics — the timeline adds no new rules, only an ordering over exact
anchors.

---

## 6. Replay Frame Identity

```text
ReplayFrameId
  race_id: str              # canonical race slug, e.g. "2023-r01-R"
  frame_index: int          # 0-based position in the race timeline (§5)
  anchor_driver_id: str     # representative observation's driver
  anchor_lap_number: int    # representative observation's lap (>= 1)
  anchor_state_time_s: float# representative observation's T, exact binary value
  replay_contract_version: str  # e.g. "replay-v1" (timeline derivation rules)
```

- **Minimal deterministic representation:** `(race_id, frame_index)` is
  the lookup key; the anchor triple is the reconstruction key. Both are
  stored — index for navigation, anchor for exactness.
- **Stable/sortable/serializable:** sort key `(race_id, frame_index)`;
  JSON primitives only; `state_time_s` serialized with full float
  precision (`repr`, never rounded display values) — no float ambiguity.
- **Exact:** frame → `AnchorObservation` → frozen reconstructor; no
  nearest lookup at any layer (miss → 422 `unknown_state`, frozen mapping).
- **Navigation:** PREVIOUS/NEXT = `frame_index ± 1`; FIRST/LAST = bounds;
  JUMP = direct index; JUMP-TO-LAP = leader-lap index (§11).
- **Invariants (pinned by tests, §22):**
  1. `frame_index` is dense `0..N-1` with strictly non-decreasing T and
     `(T, lap, driver)`-ordered representatives.
  2. Same `(canonical data, replay_contract_version, race_id)` → same N,
     same order, same identities, same `RaceState` bytes.
  3. Representative = first row of the T-group in `(lap_number,
     driver_id)` order (§7); the 1 known `track_state`-divergent group is
     resolved by this rule, deterministically.
  4. Frame identity never contains predictions, probabilities, or model
     metadata (factual/prediction separation, §8).

Do not implement in R0.

---

## 7. Anchor Selection Policy

**Policy:** at each unique T, the frame's anchor is the canonical
representative observation = the row first in `(lap_number, driver_id)`
order among rows with that exact `(race_id, state_time_s)`. `driver_id`
is the final deterministic tie-breaker.

**Verified from implementation (not assumed):**

- Driver factual entries do NOT depend on anchor choice at fixed T:
  `reconstruct()` resolves every member via `sync_lookup(race_id, m, T)`
  and evaluates F6 gaps at each member's own observed time. Two anchors
  sharing T yield identical driver entries (same sync inputs).
- Anchor choice CAN affect the anchor-row-sourced block (weather as-of,
  RC flags/message, `race_leader_laps_at_state`, `race_progress_frac`),
  which is read from the target row. Measured: context agrees at all 58
  shared-T groups except one `track_state` divergence — hence the
  representative rule is load-bearing for byte-determinism, not merely
  cosmetic.
- Anchor selection is therefore **identity with one pinned contextual
  consequence**: the representative fully determines the frame; no other
  anchor at the same T may substitute.

Tie ordering: `(state_time_s, lap_number, driver_id)` — the same order
`list_anchors` already serves, so timeline construction can reuse the
`/states` enumeration order directly. Every meaningful state transition
is preserved (one frame per unique T); duplicate-equivalent frames are
eliminated by construction (only 58 deduped corpus-wide).

**Gap (documented, not modified):** no frozen interface change is needed —
`RaceStateReconstructor.reconstruct(anchor)` already accepts any exact
anchor, so the representative anchor is directly consumable. No Phase-4
gap.

---

## 8. Factual Frame vs Prediction Snapshot

Two separate domain concepts, separate cadences, separate cache lifetimes:

```text
ReplayFrame                      ReplayPrediction (checkpoint)
  ReplayFrameId                    ReplayFrameId (checkpoint frame only)
  RaceState (factual, cheap)       PredictionSnapshot (frozen, ~12 s)
  timeline metadata:               ModelIdentity (from snapshot)
    T, leader lap, progress,         availability: AVAILABLE | PENDING |
    track_state/flags summary,       UNAVAILABLE (unobservable-heavy edge)
    observable count               generated_at, cache key (§10)
```

- **Factual replay frame** (~39 ms warm): navigation-grade. Rendered
  directly from `RaceState.to_dict()` — order, gaps (+validity), tyres,
  stint/pit facts, weather as-of, RC state, staleness ages. No model
  dependency (matches Phase-4 plan: UI renders domain state directly).
- **Prediction snapshot** (~12 s uncached): checkpoint-grade. Only a
  subset of frames carry predictions (§9). A frame without a checkpoint
  shows factual state + the nearest past checkpoint's probabilities
  explicitly labeled as past (never interpolated, §17).
- **Contract rule:** frame payloads never embed probabilities; prediction
  payloads reference frames by `ReplayFrameId` and carry the frozen
  `PredictionSnapshot` verbatim including `ModelIdentity`,
  `INDEPENDENT_BINARY` note, and null+reason entries.

---

## 9. Prediction Cadence

**Recommended: hybrid — (5) precomputed checkpoints at every leader-lap
transition + (4) event-driven extras at first `flag_red`/`flag_safety_car`
transitions not coinciding with a checkpoint, served from cache; factual
frames at every unique T (§5).**

Evaluation:

1. Prediction every factual frame — 162,639 × 12 s ≈ 542 CPU-h. Rejected.
2. Prediction every race-wide lap transition (leader lap) — 8,926 × 12 s
   ≈ 29.8 CPU-h one-time. **Accepted as base cadence** (~60/race,
   smooth probability evolution, deterministic, Monte-Carlo-compatible
   series).
3. Every N seconds of race time — resampling needs interpolation rules;
   rejected (same as §5-E).
4. Only on meaningful state changes — change-detection is a new semantic;
   accepted ONLY in the narrow frozen-flag form (SC/red transitions are
   already exact `RaceState` facts, no new detector).
5. Precomputed checkpoints — **accepted** (§10); the only way to reconcile
   ~12 s cost with replay responsiveness.
6. Hybrid — **RECOMMENDED**: leader-lap checkpoints (uniform, complete)
   + flag-transition extras (red/SC onsets visible in the probability
   timeline even mid-lap).

**REPLAY FRAME CADENCE** (every unique T, ~1091/race, cheap, navigable)
is distinct from **MODEL PREDICTION CADENCE** (~60+extras/race, expensive,
precomputed). The API exposes both; the UI scrubs frames and overlays the
checkpoint series.

---

## 10. Precomputation / Cache Strategy

**Recommended: hybrid — precompute the leader-lap checkpoint series per
race offline (one batch job, ~30 CPU-h total, resumable per race);
serve from immutable filesystem artifacts; lazily generate flag-transition
extras on first request then persist; never generate synchronously on the
replay interaction path.**

- Typical frames/race: ~1,091 factual; checkpoints/race: ~60 (mean 59.9
  leader laps) + ≤ a few flag extras.
- Compute/race at base cadence: ~60 × 12 s ≈ **~12 min**; full 2018–2024:
  **~30 CPU-h** (measured-input arithmetic, §3 — a budget, not a claim).
- Serialized size (structural estimate, not measured): `PredictionSnapshot.
  to_dict()` ≈ roster (20 × ~8 small fields) + `ModelIdentity` ≈ single
  KBs JSON; ~8,926 checkpoints → **tens of MB total** — trivially
  storable; exact sizes measured in R3.
- No massive generation job in R0 (prohibition respected); R3 runs it.

**Cache identity (deterministic key inputs):**

```text
checkpoint_key = hash(
  replay_contract_version,     # timeline + checkpoint selection rules
  race_id, frame_index, anchor triple + T (exact),
  phase4_contract_version,     # "v1"
  feature_set_id,              # "ALL_84" + FEATURE_SET_VERSION "v8"
  serving_artifact_sha256,     # 1116b34f…
  spec_fingerprint,            # 3164de9e…
  phase2_content_hash,         # d2ee966c…
  canonical_data_version,      # D9 scope/tag + per-race max state_time_s or row count
)
```

Any change in model bytes, feature identity, Phase-4 contract, replay
rules, or source data invalidates (miss → regenerate, never serve stale).
Factual frames need no cache (reconstruction is ms-scale and pure).

---

## 11. Navigation Semantics

Index arithmetic over the §5 timeline; `lap_number` below always means a
named reference lap, never a global clock.

- FIRST / LAST: `frame_index` 0 / N-1.
- PREVIOUS / NEXT: `frame_index ± 1`, clamped (at bounds: stay + signal
  `at_boundary`, no wrap, no error).
- JUMP TO FRAME: direct `frame_index` lookup; out-of-range → 422-style
  client error (contract detail in R4).
- JUMP TO LAP: reference = **race leader lap** (`race_leader_laps_at_state`
  carried per frame). Mapping: first frame with `leader_lap >= L`
  (forward-fill, exact, no interpolation). Per-driver lap jump is NOT
  offered (would resurrect the global-lap fallacy).
- PLAY/PAUSE: client-side clock over frame indices (§12); server is not
  involved per tick.
- Before first observation: frame 0 always has ≥1 observable member (the
  anchor itself, enforced by `RaceState` construction) — no empty race
  state exists.
- After final observation: LAST frame; no extrapolation beyond final T.
- Red flags: frames pass through; UI surfaces `flag_red`/`track_state`;
  gaps render null+invalid per frozen validity (no invented values).
- Partial races: timeline is shorter (e.g. 60 frames, 2021-r12-R); same
  semantics, no minimum-length assumption.

---

## 12. Playback Clock

Historical time and UI playback time are strictly separated:

- **Historical time:** canonical `state_time_s` deltas between frames
  (real lap-completion gaps, including long red-flag suspensions).
- **Playback time:** wall-clock rate owned entirely by the frontend.

**Recommended policy: step-based playback with compressed long gaps.**
Advance one factual frame per tick at `speed × base_frame_interval`;
when the historical delta to the next frame exceeds a cap (e.g. red-flag
gaps; exact cap in R5), compress to the cap and surface a "time
compressed" indicator. Rationale: reproducing real-time deltas makes
red-flag periods unwatchable; fixed-frame stepping keeps 0.5x/1x/2x/4x/8x
meaningful and deterministic; compression is a display policy, never a
data mutation (frame identities and T values untouched). No timers,
workers, or server pushes — the client owns the clock (§15).

---

## 13. Partial / Red Flag / SC / Stale Semantics

| Situation | Replay behavior (factual state at T only) |
|---|---|
| PARTIAL RACE | Short timeline; thin histories; nullable `scheduled_laps`; progress via leader laps. Same rule, no minimum length. Fixture: 2021-r12-R (60 rows). |
| RED FLAG | Sync unchanged; `flag_red=true`, `track_state='red_flag'`; seconds gaps null + `valid=false` (+lapdiff); weather/RC as-of persist. No gap reinterpretation. Fixture: 2022-r18-R. |
| SAFETY CAR | `flag_safety_car=true`, `track_state='safety_car'`; gaps under SC keep frozen validity semantics (validity companions authoritative, never UI guesswork). 2022: 1,295 SC rows. |
| VSC | `flag_vsc=true`, tokens `vsc`/`vsc_ending`; same treatment as SC. 2022: 413 rows. |
| STALE DRIVER | Observable with age provenance; render last-observed facts + explicit age (e.g. "data 48 s old"); never present as live. Fixture: 2022-r07-R norris-30. |
| RETIRED / NO MORE OBSERVATIONS | Growing age; no retirement label (future classification is LABEL_ONLY). Unknown reason, honestly shown. |
| PRE-FIRST-OBSERVATION | `observable=false`, full nulls; visually "not yet on timing screens"; indistinguishable from zero-state entrants by design. |

Phase 5 knows at T only: synced rows `<= T`, ages, flags, as-of context.
It never knows: retirement reason/status, final classification, future
laps, eventual stint length (`end_lap` stays firewalled).

---

## 14. Proposed Replay API

Minimum surface (design; NOT implemented in R0). Reuses frozen endpoints
internally (`/states` enumeration order, `/state` reconstruction,
`winner-snapshot` generation for checkpoint backfill):

```text
GET /v2/races/{race_id}/replay/timeline
  → { race_id, replay_contract_version, frame_count,
      frames: [{ frame_index, anchor_driver_id, anchor_lap_number,
                 anchor_state_time_s, leader_lap, progress_frac,
                 track_state, observable_count }] }   # paginated

GET /v2/races/{race_id}/replay/frames/{frame_index}
  → { frame identity, RaceState (V2RaceStateResponse shape),
      prev/next indices, leader_lap, prediction_checkpoint: frame_index | null }

GET /v2/races/{race_id}/replay/predictions/{frame_index}
  → { frame identity, PredictionSnapshot (frozen shape verbatim),
      cache_status: HIT | COMPUTED }                  # checkpoint frames only;
                                                      # non-checkpoint → 404 + nearest-past pointer

GET /v2/races/{race_id}/replay/probability-timeline
  → { race_id, series_identity (model + feature + artifact),
      checkpoints: [{ frame_index, state_time_s,
                      probs: [{ driver_id, winner_probability,
                                unavailable_reason }] }] }  # §17
```

Endpoint count is deliberately small (4 new); frame payloads reuse the
frozen V2 state/prediction shapes so the frontend never learns anchor
mechanics beyond the opaque frame identity. Full HTTP method/status/body
contract (including pagination, 404/422 matrix, 2025 exclusion) is fixed
in R4, not R0.

---

## 15. Transport Decision

**HTTP request/response only. No WebSocket, no SSE, no streaming.**

Justification: replay data is deterministic history — every frame and
checkpoint is a pure function of (canonical data, contract version,
model bytes). The client owns the playback clock (§12) and already holds
(or pages) the timeline; the server never has an unpredictable live event
to push. Prediction checkpoints are precomputed/cached (§10), so no
long-lived computation needs progress streaming; a cache-miss generation
(~12 s) is an ordinary slow GET/POST with HTTP timeouts set accordingly,
not a reason for sockets. Adding WS/Redis/queues/workers would be
speculative infrastructure — explicitly prohibited.

---

## 16. Frontend Integration Boundary

- **Current state:** `frontend/lib/api.ts` speaks legacy routes only;
  page state lives in `features/prediction/hooks/usePrediction`; no V2
  client, no replay components, no shared state library.
- **Entry point (R5):** new `frontend/features/replay/` slice
  (hooks: `useReplayTimeline`, `useReplayFrame`, `useReplayPlayback`,
  `useProbabilityTimeline`; components: race selector, timeline
  scrubber, state inspector, checkpoint overlay) + `frontend/lib/v2.ts`
  API client for `/v2/*` + replay endpoints. Legacy `features/
  prediction/` and `lib/api.ts` stay untouched (legacy routes frozen).
- **Reusable:** race-selector patterns and panel/hero layout idioms only;
  no prediction-response coupling is reused (legacy response shapes are a
  different universe; replay consumes V2 shapes).
- **No redesign** of unrelated frontend code in Phase 5.

---

## 17. Probability Timeline Contract

Backend/domain contract (conceptual; wire shape in R4):

```text
ProbabilityTimeline
  race_id, series_identity { task winner, target is_winner,
    feature_set ALL_84/v8, artifact_sha256, spec_fingerprint,
    replay_contract_version, checkpoint_policy_id }
  probability_semantics: INDEPENDENT_BINARY (+ fixed note verbatim)
  checkpoints: list[{ frame_index, state_time_s, leader_lap,
    entries: [{ driver_id, winner_probability | null,
                unavailable_reason | null }] }]   # driver_id order
```

Rules: one entry per roster member per checkpoint (complete roster, never
dropped); missing checkpoints are absent (never fabricated, never
zero-filled); no renormalization at any layer (pinned by test both sides
of 1.0, mirroring Phase-4 R4); UI may linearly connect points **for
drawing only** — the drawn segments are explicitly not model inference
and the API never serves interpolated values.

---

## 18. Determinism

Factual timeline — given same canonical data + same
`replay_contract_version` + same `race_id`: same frame count, same
`(T, lap, driver)` order, same identities, same `RaceState` bytes
(`to_dict()` equality). Test method: rebuild timeline twice incl. input
row shuffle (mergesort-stable ordering) — mirrors Phase-4 shuffle tests.

Prediction checkpoints — additionally same artifact bytes + same feature
identity: same probabilities within the frozen serving determinism
contract (max abs diff 0.0 on parity fixtures, per Phase-4 R6 precedent).

Hashed/versioned: `replay_contract_version` (timeline + representative
rule + checkpoint policy), Phase-4 contract v1, ALL_84/v8, serving
artifact SHA-256, spec fingerprint, Phase-2 content hash, canonical data
scope/tag. All are inputs to the §10 cache key, so determinism and cache
correctness share one mechanism.

---

## 19. Performance Targets

TARGETS (not claims; Phase-4 measured values are baselines):

| Operation | Baseline (measured, Phase 4) | Phase-5 target |
|---|---|---|
| Timeline construction/race | — (sort ~1.1k rows + paged `/states`) | < 1 s cold, < 200 ms warm |
| Frame lookup (index → anchor) | — (binary search / pagination) | < 100 ms p95 |
| `RaceState` reconstruction | ~39 ms warm (R6) | < 100 ms p95 warm |
| Cached frame response (HTTP) | — | < 250 ms p95 |
| Prediction cache lookup (HTTP) | — | < 250 ms p95 |
| Uncached prediction generation | ~12.18 s (R6, frozen path, NOT optimized) | No target — served from precompute; backfill is offline |
| Checkpoint precompute/race | — (~60 × 12 s ≈ 12 min arithmetic) | Offline batch, resumable per race; full 2018–2024 ≈ 30 CPU-h budget |
| Frontend frame transition | — | < 200 ms (cached frame + paint) |

The ~12 s feature path is explicitly NOT optimized in Phase 5 (frozen).

---

## 20. Storage Decision

**Minimum justified: filesystem artifacts, no database.**

- Timeline: derived on demand from canonical D9 (`/states` order) — no
  storage at all (deterministic, ms-scale inputs).
- Factual frames: reconstructed on demand (~39 ms) — no storage.
- Prediction checkpoints: immutable per-race artifact files
  (JSONL or Parquet, one record per checkpoint × roster member — exact
  format fixed in R3 after measuring §10 size estimates) under
  `results/v2_replay/checkpoints/{race_id}/` + a manifest carrying the
  §10 cache identity. Rationale: ~tens of MB total, write-once/read-many,
  process-local serving already assumed by `V2Service`; SQLite/Postgres/
  Redis add operational surface for no evidenced need.
- No DB, no queues, no workers, no object store in Phase 5.

---

## 21. Future-Phase Seams

Stable seams later phases consume (designed here, not built beyond):

- `ReplayFrameId` (§6) — the universal handle for track UI, Monte Carlo
  initial conditions, strategy branch points, what-if mutations,
  explainability anchors.
- `RaceState` (frozen) — state consumed by Monte Carlo/strategy; mutated
  only by what-if under explicit new semantics.
- `PredictionSnapshot` + `ProbabilityTimeline` (§17) — baselines for
  strategy comparison and explainability pairing.
- Historical time (`state_time_s`, leader-lap index) — common x-axis.

No speculative abstractions: no simulator interfaces, no strategy types,
no explanation schemas in Phase 5.

---

## 22. Test Strategy

Future matrix (designed, not implemented in R0). Representative fixtures
from Phase-4 tests where possible:

- Timeline determinism (rebuild ×2 + row shuffle; N/order/identity
  equality) — all 149 races cheap (no model).
- Frame identity (uniqueness, density `0..N-1`, JSON round-trip,
  `repr`-precision T, no nearest lookup on miss → 422).
- Ordering (canonical `(T, lap, driver)`; shuffle invariance).
- Exact reconstruction (frame anchor → `RaceState` equals direct
  `reconstruct()`; representative-anchor equality at the 58 shared-T
  groups incl. the 1 `track_state`-divergent group).
- Same-time ties (2021-r08 stroll duplicate + synthetic).
- Lapped drivers (leader vs backmarker divergent laps, same frame).
- Zero-state entrants (6 corpus members; permanent nulls).
- Stale drivers (2022-r07-R norris-30; age provenance preserved).
- Partial races (2021-r12-R hamilton-2; 2022-r18-R ocon-2).
- Red flags (2022-r18-R; validity=false, no invented gaps).
- SC/VSC (2022 token coverage; flag companions verbatim).
- Backward/forward/boundary navigation (index arithmetic, clamp+signal).
- Checkpoint mapping (leader-lap transitions exact; flag extras exact).
- Cache identity/invalidation (each §10 input mutated → miss).
- `INDEPENDENT_BINARY` preservation (sums ≠ 1 pass through; no
  `probability_share`/sum-to-one field anywhere).
- No normalization (property test on timeline payloads).
- 2025 exclusion (unknown race → 404 on all replay routes).
- Future-data mutation resistance (same-lap +1 s injection leaves
  frame/checkpoint bytes identical — mirrors R6 hazard).
- Legacy compatibility (4 legacy routes byte-identical; legacy frontend
  feature untouched).

---

## 23. R0 Findings

1. Frame cadence (unique T, ~1,091/race) and prediction cadence (~60/race)
   must be separate contracts — ~12 s/snapshot makes per-frame prediction
   (~542 CPU-h total) infeasible; leader-lap precompute (~30 CPU-h) is
   feasible.
2. Same-T collisions are negligible (58 groups / 162,728 rows) but the
   representative-anchor rule is still load-bearing (1 `track_state`
   divergence measured).
3. Anchor choice at fixed T does not alter driver factual entries
   (sync-at-T + own-time gaps); only the anchor-row context block can
   vary — verified in code, corroborated by data.
4. `lap_number` can never index replay; leader-lap reference is the only
   sound "jump to lap".
5. SC/VSC/red/partial/stale all have frozen representations; no new
   detection semantics needed.
6. Frontend is legacy-coupled and V2-untouched — replay is a clean new
   slice, no migration.
7. HTTP suffices; no real-time infrastructure is justified.
8. No database is justified; filesystem checkpoint artifacts suffice.
9. **No frozen Phase-4 interface gap found**: representative anchors are
   directly consumable by `reconstruct()`; `/states` order is directly
   consumable for timeline construction; `PredictionSnapshot` is directly
   storable. No Phase-4 modification required.

---

## 24. R1–R8 Roadmap

**R1 — Replay Timeline + Frame Domain.** Scope: `ReplayFrameId`
dataclass (+ ordering/serialization/invariants), timeline derivation
function (D9 slice or `/states` pages → ordered frame list) in a new
`v2/replay_timeline.py` (or `v2/replay/` package — R1 decides, single
module preferred); no reconstruction, no model. Tests: determinism,
identity, ordering, tie-break, 58-group fixture, shuffle invariance,
2025 exclusion at service boundary. Verification: FAST (unit + small
canonical reads). STOP gate: any need to alter `RaceState`/anchor
semantics ⇒ freeze conflict, halt.

**R2 — Replay Reconstruction Service.** Scope: frame → `RaceState` service
over cached per-race timeline + frozen reconstructor; FIRST/PREV/NEXT/
LAST/JUMP/LAP resolution; boundary clamping. Files: new
`v2/replay_service.py` (or in package); reuse `RaceStateReconstructor`,
`extract_roster`. Tests: navigation matrix, lap-reference mapping,
stale/zero-state/partial/red/SC fixtures, exact-reconstruction equality.
Verification: MEDIUM (needs `data/v2` artifacts). STOP gate: nearest
lookup or interpolation requested ⇒ defer, halt.

**R3 — Prediction Checkpoints + Cache.** Scope: checkpoint selection
(leader-lap + flag extras), cache-key computation (§10), filesystem
artifact writer/reader + manifest, offline backfill script
(`scripts/backfill_replay_checkpoints.py`), lazy single-checkpoint
generation path (offline/cached, never on tick). Tests: checkpoint
mapping, key inputs, invalidation matrix, `INDEPENDENT_BINARY`
preservation, size/perf measurement. Verification: MEDIUM + measured
budgets. STOP gate: any retrain/recalibration/renormalization temptation
⇒ freeze conflict, halt.

**R4 — Replay API.** Scope: the 4 endpoints of §14 + error mapping
(404/422/500/503 mirroring frozen conventions) + OpenAPI; additive router
include only. Tests: golden shapes, pagination, boundary errors, 2025
404s, legacy baseline green. Verification: FAST. STOP gate: legacy
behavior change required ⇒ default no, halt for decision.

**R5 — Frontend Replay Controls + State View.** Scope:
`features/replay/` (timeline/scrubber/playback clock per §12, state
inspector rendering §13 semantics) + `lib/v2.ts`; legacy feature
untouched. Tests: node:test suites mirroring existing frontend tests +
tsc/eslint/build. Verification: frontend battery. STOP gate: any new
backend need ⇒ back to R4, no ad-hoc endpoints.

**R6 — Probability Timeline Integration.** Scope: checkpoint overlay +
`probability-timeline` consumption; past-checkpoint labeling; draw-only
interpolation guard (visual, never served). Tests: contract tests (§17
rules), no-normalization property, missing-checkpoint honesty.
Verification: MEDIUM. STOP gate: interpolated values presented as
predictions ⇒ defect, halt.

**R7 — Hardening / Performance / Adversarial Tests.** Scope: full §22
matrix, measured §19 budgets recorded, 149-race timeline sweep (factual
only), backfill completion evidence. Verification: FULL (`pytest tests/`
per AGENTS.md serialization; frontend battery). STOP gate: leakage or
normalization found ⇒ fix Phase-5 code only, never frozen code.

**R8 — Freeze / Documentation / Commit / Tag.** Scope: freeze manifest
(replay contract version, checkpoint policy id, cache-key inputs, artifact
SHAs), final report, seal commit + tag per repo convention. Verification:
FULL review. STOP gate: any frozen Phase-1–4 hash drift ⇒ halt,
diagnose.

---

## 25. R0 Definition of Done

- [x] Phase-4 handoff read (§3)
- [x] Repository reality inspected (implementation + data + tests,
      not reports alone)
- [x] Historical time axes audited with measured evidence (§§3–4)
- [x] Canonical replay timeline selected with per-option assessment (§5)
- [x] `ReplayFrameId` designed with invariants (§6)
- [x] Deterministic anchor policy designed and code-verified (§7)
- [x] Factual/prediction separation defined (§8)
- [x] Prediction cadence selected with cost arithmetic (§9)
- [x] Precompute/cache strategy selected with measured inputs (§10)
- [x] Cache identity designed (§10)
- [x] Backward/forward semantics designed (§11)
- [x] Playback-clock semantics designed (§12)
- [x] Partial/red/SC/VSC/stale behavior defined (§13)
- [x] Replay API boundary designed, endpoint-light (§14)
- [x] Transport decision made with justification (§15)
- [x] Frontend boundary audited (§16)
- [x] Probability timeline contract designed (§17)
- [x] Determinism requirements defined (§18)
- [x] Performance targets marked as targets (§19)
- [x] Storage decision made, minimal (§20)
- [x] Future-phase seams identified, no speculative design (§21)
- [x] Test strategy designed with fixtures (§22)
- [x] R1–R8 roadmap created (§24)
- [x] This plan created, concrete + repository-referenced
- [x] Frozen implementation unchanged (§R0-W verification below)
- [x] Phase-4 seal unchanged
- [x] Unrelated worktree changes untouched
- [x] Phase 5 implementation NOT started (no endpoints, no components,
      no tests, no timers, no storage code)

**R0-W verification (documentation-only):** `git status` shows only the
new untracked `docs/PHASE5_HISTORICAL_REPLAY_PLAN.md` as the R0 addition;
no tracked file modified by R0 (verified via `git status --short` +
`git diff --stat`); serving artifact SHA-256 re-verified
`1116b34f…` (match); HEAD remains Phase-4 seal `4f26801`, tag
`v2-race-state-prediction-phase4` present. No full pytest rerun (per R0-W:
implementation untouched). No commit (per R0-X; unrelated worktree
changes preserved).

---

## 26. R1 implementation record (2026-09-19, R1 COMPLETE — READY FOR R2)

Status: replay timeline + frame domain implemented; no RaceState
reconstruction, no features, no predictions, no API, no storage. No
frozen Phase-1/2/3/4 file modified (only two new files below + this
plan note); no 2025 access; serving artifact sha re-verified
`1116b34fc716035c…` (full match).

Actual files:

- `v2/replay.py` (~new): `REPLAY_CONTRACT_VERSION = "v1"`;
  `ReplayTimelineError(ValueError)`; frozen `ReplayFrame{race_id,
  frame_index, anchor_driver_id, anchor_lap_number, anchor_state_time_s,
  replay_contract_version}` with exact-type guards (numpy/pandas scalars
  rejected structurally), foreign-version rejection, `to_anchor()` exact
  conversion to frozen `AnchorObservation`, `to_dict()` primitives-only;
  frozen `ReplayTimeline{race_id, replay_contract_version, frames}` —
  validates but NEVER reorders (non-dense indices, non-increasing T,
  mixed races/versions fail loudly); `frame_count`/`first`/`last`/
  `frame_at` (out-of-range raises) / `previous`/`next` (None at
  boundaries, no wraparound); `build_replay_timeline(states)` one-race
  builder (allowlist projection of the 4 factual columns only; exact-T
  dict grouping; sorted unique T; per-group `(lap_number ASC, driver_id
  ASC)` explicit sort; duplicate identity → reject; dense 0..N-1).
  Imports frozen `AnchorObservation` (conversion target) + pandas (input
  frame only); no FastAPI/model/feature/storage imports.
- `tests/test_v2_phase5_r1.py` (~new): 74 tests green (see below).

Builder contract: input = one-race canonical DataFrame with
`race_id/driver_id/lap_number/state_time_s`; output = `ReplayTimeline`.
Season-agnostic by design (2025-labeled single-race input builds fine);
2018–2024 scope stays enforced at the serving boundary
(`api/v2_service.py::SERVED_SEASONS`, asserted 2025-absent in test; R4
replay routes follow suit).

Representative-anchor implementation: per-T candidate list explicitly
`sorted()` on `(lap, driver)` tuples — independent of DataFrame,
groupby, dict, set, and filesystem order. No further tie-breaker needed:
served corpus contains zero duplicate canonical identity rows (audited).

Exact shared-T divergent fixture (R0 prediction confirmed, pinned in
test): **2020-r09-R @ T=2974.257** (Tuscan GP restart crash) —
giovinazzi/lap6 + kevin_magnussen/lap6 + sainz/lap6 (`yellow`) vs
latifi/lap7 (`safety_car`; `flag_safety_car=true` vs `flag_yellow=true`).
Rule selects **giovinazzi/lap6**. The divergence is NOT "fixed" — the
deterministic rule is the resolution.

Duplicate policy: exact-duplicate canonical identity rows are
data-contract corruption → `ReplayTimelineError`. Corpus has zero such
rows, so the policy is a guard, never a filter.

Navigation semantics: `frame_at` raises `ReplayTimelineError` outside
`[0, N)`; `previous(0)` / `next(N-1)` return None (no wraparound, no
exception type proliferation); navigation tested incl. divergent-frame
neighbors (prev T < 2974.257 < next T).

Serialization contract: `to_dict()` on frame + timeline (timeline adds
`frame_count`); JSON primitives only; T at full float precision;
`json.dumps(..., sort_keys=True)` byte-identical across repeats,
shuffles, and reversal — asserted.

Firewall result: label/future/model columns (`is_winner`,
`final_position`, `points`, `classified_flag`, future-shifted T,
`model_probability`) added/mutated on 2023-r01-R → byte-identical
timeline (builder never reads them — allowlist projection).

Determinism evidence: 5 canonical fixtures (2023-r01-R ordinary,
2021-r12-R partial, 2022-r18-R red, 2022-r07-R stale, 2020-r09-R
divergent) × rebuild + 2 deterministic shuffles → identical serialized
timelines; every frame anchor verified as an exact canonical row.

Corpus statistics (built, not estimated — match R0 exactly): 149 races,
162,728 observations, **162,639 frames**, 58 shared-T groups, 89
collapsed observations, 52 races with shared-T groups.

Performance measurements (factual build only): normal 2023-r01-R
**0.003 s**; largest served race 2020-r16-R (1534 rows) **0.004 s**;
full 149-race corpus **1.206 s (0.008 s/race)** — R0 target (<1 s cold
per race) met with ~100x margin. No profiling needed; Phase-4 untouched.

Tests: `tests/test_v2_phase5_r1.py` — **74 passed** (contract version,
frame validation incl. parametrized malformed values, anchor conversion,
timeline validation, builder, representative rule, exact-vs-near T,
duplicates, navigation + boundaries, serialization, firewall, 5
fixtures × count/shuffle/exact-anchor, divergent fixture ×2, 2025
policy, corpus audit, performance). Focused gate: R1 74 + freeze/R1/R2
87 passed (pre-existing pandas FutureWarning noise only, documented
Phase-4 debt). Full 57-minute suite NOT rerun (risk-based gate per
R1-U; R1 adds only `v2/replay.py` + test + plan note).

Deviations from R0: none material. `ReplayFrameId` folded into
`ReplayFrame` (separate Id type added no correctness — R0 allowed this).
`previous`/`next` return None (R0's permitted minimal option).

Known risks: none new. R1 never resolves anchors against D9, so anchor
validity at serving time depends on canonical data stability (cache-key
input in R3).

R2 readiness: R2 consumes `frame.to_anchor()` → frozen
`RaceStateReconstructor.reconstruct()` per frame + navigation helpers;
no R1 change needed. R2 NOT started.

---

## 27. R2 implementation record (2026-09-19, R2 COMPLETE — READY FOR R3)

Status: factual replay reconstruction service implemented; lazy,
model-free, feature-free, API-free, storage-free, cache-free. No frozen
Phase-1/2/3/4 file modified (only two new files below + this plan
note); no 2025 access; serving artifact sha re-verified
`1116b34fc716035c…` (full match); tag resolves to `4f26801…`.

Actual files:

- `v2/replay_reconstruction.py` (~new): `ReplayReconstructionError`
  (`ReplayTimelineError` subclass); `ReplayReconstructor(timeline,
  reconstructor)` — holds one R1 timeline + one reusable frozen
  `RaceStateReconstructor` (owns its immutable `RaceIndex`; built once
  by the caller, never rebuilt per frame; same-race coverage checked at
  construction). `state_at(i)` = timeline lookup → `to_anchor()` →
  frozen `reconstruct()` → frame/state identity consistency check (all
  four parts exact, mismatch raises). `first_state`/`last_state`/
  `previous_state`/`next_state` delegate to R1 navigation (None at
  bounds, no wraparound). `leader_lap_at(i)` reads factual
  `race_context.race_leader_laps_at_state`; `frame_for_leader_lap(lap)`
  binary-searches the first frame with leader progress >= lap
  (lap < 1 or unreachable — e.g. beyond a partial race's factual end —
  raises). R2-E decision: NO wrapper type — `RaceState` + `ReplayFrame`
  are jointly sufficient; navigation authority stays in R1.
- `tests/test_v2_phase5_r2.py` (~new): 24 tests green (see below).

Frozen interface audit (R2-A): `RaceStateReconstructor(states, roster,
race_meta)` builds one `RaceIndex`, immutable and reusable — confirmed
in source; `reconstruct(anchor)` exact 4-key; `DriverRaceState`s in
`driver_id` order with observable/stale/zero-state/pre-first semantics;
weather/RC/context from the anchor target row; repeated reconstruction
byte-deterministic (pure function of corpus + index). R1 `ReplayFrame`
needs no change (additive-free R2).

Lazy behavior (proven by call-counting test): service + timeline
creation → 0 reconstructions; `state_at(i)` → exactly 1; repeat →
exactly 1 more (no hidden cache).

Shared-T fixture: 2020-r09-R @2974.257 resolves via giovinazzi/lap6 to
`track_state=yellow`/`flag_yellow` context (not latifi's SC row);
byte-identical on repeat; shuffle-rebuilt timeline selects the same
frame and identical `RaceState` bytes. (Side finding: shared-T
non-representative rows correctly own no frame — e.g. no
latifi/lap7-anchored frame exists.)

Stale (2022-r07-R norris-30): stale members present with `age > 0`,
own observed lap/time `<= T`, complete roster, no classification
inferred. Pre-first (2023-r01-R frame 0): unobservable members full
nulls, anchor observable. Partial (2021-r12-R): last frame
reconstructs, navigation stops, leader max 3 (jump-to-4 raises).
Red (2022-r18-R ocon-2): `flag_red`/`red_flag` preserved, exact T,
deterministic neighbors. SC (2020-r09-R bottas-1): `flag_safety_car`/
`safety_car` preserved. VSC (2018-r01-R alonso-26): `flag_vsc` + vsc
token preserved. Lapped (2023-r01-R last): field spans multiple
observed laps; members keep own laps, never forced to anchor lap.

Adversarial: future position/tyre/stint/track/weather/RC/leader-lap
rows poisoned strictly after T (alonso-28) → rebuilt service returns
byte-identical snapshot. Wording: no leakage was detected under the
implemented adversarial test.

Determinism: ordinary/partial/red/stale anchors × repeat × shuffle →
identical `RaceState` bytes and identical frame identity.

Cache decision: NO cache. Warm full-field reconstruction ≈ 150 ms on
this dev machine (stable across 8 repeats); early frames ≈ 3 ms;
20-frame sequential nav ≈ 24 ms/frame. A cache would add invalidation
surface for no evidenced interactive need at R2 scope; R7 re-measures.

Performance vs R0 target (<100 ms p95 warm): MISSED on this hardware
for full-field frames (p50/p95 ≈ 145/148 ms over 6 sampled frames;
isolated probe of alonso-28 stable at ~150–225 ms vs R6's 39 ms on
their benchmark machine). Investigated, not optimized: all time sits
inside frozen reconstruction (per-member F6 gap sync lookups); R2's own
layer (lookup + anchor + consistency check) is microseconds. No Phase-4
change per prohibitions; target stays a target; R7 re-measures on
consistent hardware. Timeline build remains ~ms (R1).

Tests: `tests/test_v2_phase5_r2.py` — **24 passed** (construction,
laziness, exact lookup/consistency, bounds, nav helpers, divergent
fixture ×2, leader-lap oracle + rejections, early/stale/partial/red/SC/
VSC/lapped, adversarial, 4-fixture determinism, hermetic import
firewall via subprocess, 2025 serving-boundary scope, perf smoke with
generous bounds). MEDIUM gate: Phase-5 R1+R2 + Phase-4 R1/R2/freeze =
**185 passed** (pre-existing FutureWarning noise only). Full suite NOT
rerun (risk-based gate per R2-W).

Deviations from R0/R1: one test-authored detour (SC anchor first
assumed latifi/lap7, which correctly owns no frame as a
non-representative row; switched to bottas/lap1, a true SC-anchored
frame). Import-firewall test made hermetic (subprocess) after a
test-order `sys.modules` interaction was found and fixed — no product
code involved.

Known risks: none new. Full-field frame latency (~150 ms here) is the
only target miss; tracked for R7.

R3 readiness: R3 consumes `ReplayReconstructor.state_at`,
`leader_lap_at`, `frame_for_leader_lap`, and `PredictionSnapshot`
cache-key inputs (§10); no R1/R2 change needed. R3 NOT started.

---

## 28. R3 implementation record (2026-09-19, R3 COMPLETE — READY FOR R4)

Status: prediction checkpoints + filesystem cache implemented; offline
generation path proven on a controlled subset; full 149-race backfill
NOT launched (explicitly prohibited for R3). No frozen Phase-1/2/3/4
file modified (only the four files below + this plan note); no 2025
access; all four frozen identities re-verified live (tag `4f26801…`,
artifact `1116b34f…`, phase-2 `d2ee966c…`, spec fp `3164de9e…`).

Actual files:

- `v2/replay_predictions.py` (~new): `REPLAY_PREDICTION_CONTRACT_VERSION
  = "v1"` (independent from frame `v1`); reasons `LEADER_LAP` /
  `FLAG_TRANSITION`; frozen `PredictionCheckpoint` (frame identity +
  sorted reasons + leader lap + both versions) and `CheckpointSeries`
  (increasing frame/T, no dup frames); `select_checkpoints(timeline,
  states)` — MODEL-FREE (reads only leader progress + `track_state`
  token of each frame's representative D9 row; module never imports
  bridge/predictor/model-lab — hermetic subprocess test pins this);
  identity (`canonical_data_identity` over exact anchor rows,
  `series_identity`, `cache_identity_inputs` with 13 scientific inputs,
  `cache_key` sha256 — no mtime/uuid/timestamps); artifact
  (`build_artifact` with snapshot-verbatim storage + anchor/roster
  validation + `complete` flag, atomic `write_artifact` via tmp +
  `os.replace`, `load_validated_artifact` raising miss/stale/incomplete,
  `read_cached_prediction`); offline generation (`generate_checkpoint`
  via injected frozen engine, `generate_race_artifact` with
  deterministic prefix subsets, `ensure_race_artifact` skip-valid
  resume). Read path structurally cannot generate (no engine import).
- `scripts/build_replay_prediction_cache.py` (~new): explicit scope
  (`--race-id`/`--season`/`--all-served-races`, exactly one required —
  no default full run); `--dry-run` (model-free selection only);
  `--force`; `--resume` (documents default skip-valid behavior);
  `--max-checkpoints` (validation subsets); predictor loaded once,
  per-race bridge+engine, per-race progress/ETA/size output; 2025 and
  out-of-scope seasons rejected before any model work.
- `tests/test_v2_phase5_r3.py` (~new): 31 tests green (see below).
- `.gitignore`: `results/v2_replay/` ignored (generated cache, tens of
  MB; reproducible via script; test fixtures under `tests/` exempt).
  Justified per R3-AA; no baseline results paths affected.

Frozen prediction audit (R3-A): `load_production_prediction_engine(
states, history)` builds bridge + frozen artifact + `ModelIdentity`
once; `engine.predict(state)` = one `features_for_state` + tuple-exact
order check + one `predict_proba` + positional roster merge; snapshot
`to_dict()` deterministic with complete roster, null + reason,
`INDEPENDENT_BINARY` note. Reused as-is (per-race slice input, shared
predictor in CLI). No second implementation.

Checkpoint policy (v1): LEADER_LAP = first frame reaching each new
leader lap (`>=` rule; `race_leader_laps_at_state` from representative
row, identical to frozen `race_context` value); FLAG_TRANSITION =
`track_state` token change vs previous frame (covers
normal↔SC/VSC/red, SC↔VSC; frame 0 never flag-only). One checkpoint per
frame max; reasons sorted tuple.

Measured selection (dry-run, factual only, 2.7 s full corpus):
2023-r01-R = 61 checkpoints (57 leader + 4 flag-only, 0 both; leader
laps 1..57, first checkpoint = frame 0); 2021-r12-R partial = leader
{1,2,3}, <10 total; 2020-r09-R SC/red race has flag extras; full
2018–2024 = **9,644 checkpoints / 149 races (~64.7/race)** vs R0's
8,926-leader estimate (difference = flag extras, as designed).

Cache identity inputs (13): replay/prediction/phase-4 versions, race,
series identity + count, ALL_84/v8, artifact SHA, spec fp, phase-2
hash, data identity, `INDEPENDENT_BINARY`. Live values read from
`engine.model_identity` + freeze manifest + canonical rows. All 11
mutable inputs individually tested to change the key (race +
checkpoint_count covered via series identity).

Artifact: `results/v2_replay/checkpoints/{race_id}.json`, canonical
JSON (sorted keys, exact float repr — round trip preserves
`4.086444508464821e-05`-scale values bit-for-bit), shared `ModelIdentity`
once at artifact level, per-checkpoint snapshot dicts verbatim (no
features/labels/normalization/interpolation). Validation rejects: wrong
format/race, any identity drift (stale), partial content as complete
(`complete:false` + count mismatch → `IncompleteCacheError`).
Subset artifacts fail complete-validation BY DESIGN (tested).

Generation: predictor once; per-race bridge+engine; `state_at` →
`engine.predict` → anchor/roster-checked snapshot dicts; skip-valid by
default (proven: stub engine never called), `--force` regenerates,
per-race atomic publish (invalid artifacts never look complete).
No interaction-path generation: read functions take artifact dicts /
paths only; `read_cached_prediction` miss → explicit error.

INDEPENDENT_BINARY preservation: real 2023-r01-R sums pass through
verbatim — lap 1: 0.8950 (<1), lap 20: 1.1210, lap 40: 1.2558, lap 57:
1.0748 (>1); mid-race checkpoint test pins sum > 1 with stored == live
bytes; synthetic 1.15/0.07 totals round-trip exactly; no
`probability_share`/sum-to-one field anywhere; nulls + reason preserved
(never 0.0).

Determinism: 3-checkpoint subset generated twice → identical canonical
bytes (generation timestamps deliberately absent from the payload).
Adversarial (checkpoint 3 @T, future position/tyre/stint/track/weather/
RC/leader rows poisoned): reselected checkpoints ≤ T identical,
regenerated prediction bytes identical. Wording: no leakage was
detected under the implemented adversarial test.

Real-race sample (controlled subset, full backfill NOT launched):
2023-r01-R first-3-checkpoint artifact — complete:false, 3 entries,
model identity pinned (sha/spec/fp/ALL_84/INDEPENDENT_BINARY), roster
complete (20/20 with null+reason for pre-first-observation members).

Measured runtime: full-field checkpoint ≈ 12.2 s (stable ×3, matches
Phase-4 ~12 s debt); early-race 1-observable checkpoint ≈ 0.1 s;
1-checkpoint artifact ≈ 22 KiB (series metadata + model + 1×20-driver
payload → extrapolated full-race ≈ 0.5–0.7 MB).

ESTIMATES (labeled, not work done): 9,644 checkpoints × ~11 s mean
(full-field-dominated) ≈ **~29–30 CPU-hours serial** (matches R0's ~30
h planning estimate); storage ≈ 149 × ~0.6 MB ≈ **~90 MB total**.
Operational backfill remains a separate explicit action
(`--all-served-races`).

2025 firewall: generation entry rejects 2025/out-of-scope before model
load (CLI-tested, nonzero exit mentioning 2025); protected evaluation
artifacts never read; low-level domain stays season-agnostic by design.

Tests: `tests/test_v2_phase5_r3.py` — **31 passed (~56 s)** (versions,
domain validation, selection counts/partial/flags/overlap/columns,
hermetic model-free probe, identity determinism + 11-field
invalidation, synthetic round-trip/stale/miss/skip/sums, real subset
content/determinism/adversarial/mid-race-sum/size-timing, CLI
scope/2025/dry-run). MEDIUM gate: Phase-5 R1+R2+R3 + Phase-4
R3/R4/R6/freeze = **230 passed in ~27 min** (R6 slowness is
pre-existing benchmark coverage). Full suite NOT rerun (risk-based).

Deviations: none material. `--resume` is an explicit marker for default
skip-valid behavior rather than a separate mode (documented in help).

Known risks: full backfill (~30 CPU-h) unstarted by design; per-frame
R2 latency debt (§27) unchanged and untouched.

R4 readiness: R4 consumes `load_validated_artifact`,
`read_cached_prediction`, series metadata, and the §14 endpoint
design; no R1–R3 change needed. R4 NOT started. Full backfill NOT
launched.

---

## 29. R4 implementation record (2026-09-19, R4 COMPLETE — READY FOR R5)

Status: historical replay HTTP API implemented over the read-only
`V2ReplayService`; timeline + factual frame + cached-prediction lookup
live on the existing `/v2` namespace. No frontend, no probability
timeline, no R5. No frozen Phase-1/2/3/4 scientific file modified; no
2025 access; no prediction ever generated on the HTTP path. Full
backfill NOT launched (generated cache stays gitignored; tests use
tmpdir artifacts only).

Actual files:

- `api/v2_replay_schemas.py` (~new): `V2ReplayFrameMeta` (factual
  identity only), `V2ReplayTimelineResponse` (race/version/total/
  offset/limit/returned_count/frames), `V2CheckpointMeta` (frame/
  reasons/leader_lap/versions — WHERE, never values),
  `V2ReplayFrameResponse` (frame + reused frozen
  `V2RaceStateResponse` + nav + leader_lap + checkpoint/cache
  pointers), `V2ReplayPredictionResponse` (frame + checkpoint +
  reused frozen `V2PredictionSnapshotResponse` + `cache_status: HIT`),
  `V2ReplayErrorResponse` (documents `{error, detail}` + optional
  `reason`/pointers). No pandas/numpy; no giant union model.
- `api/v2_replay_service.py` (~new): `V2ReplayService` — served-race
  registry (2018–2024), lazy per-race `ReplayTimeline` +
  `CheckpointSeries` caches (model-free, ms-scale), exact R2
  `ReplayReconstructor` resolution per frame, R3 read-only artifact
  access (`load_validated_artifact` / `read_cached_prediction` by
  explicit import; generation/engine/bridge/predictor names appear
  nowhere outside the boundary docstring — AST + hermetic subprocess
  tests pin this). Holds NO engine reference, so cache misses raise
  `PredictionUnavailableError(reason)` by construction. Domain
  errors: `ReplayFrameNotFoundError`, `NotPredictionCheckpointError`
  (carries prev/next pointers), `PredictionUnavailableError`
  (`cache_missing`/`cache_stale`/`cache_incomplete`/`cache_corrupt`).
  Factory `build_v2_replay_service` shares the loaded corpus +
  reconstructor by read-only reference (frozen `api/v2_service.py`
  untouched — no second corpus load); static cache-key inputs resolved
  once from engine identity attrs + freeze manifest (never `predict`);
  `api.v2_service` imported deferred-inside-factory so merely
  importing the replay module never pulls the model stack.
  `get_v2_replay_service` is the FastAPI dependency (lru singleton,
  overridable in tests).
- `api/v2_replay_routes.py` (~new): three routes on the existing
  `/v2` prefix (tag `v2-replay`): `GET
  /v2/races/{race_id}/replay/timeline` (offset>=0, limit 1–500,
  default 100, mirroring STATES conventions; reconstruction-free),
  `GET .../replay/frames/{frame_index}` (factual: frame + exact R2
  `RaceState` + has_previous/has_next + neighbor indices + leader
  lap + checkpoint pointers), `GET
  .../replay/predictions/{frame_index}` (CACHE-ONLY: HIT, or explicit
  miss). Error mapping: unknown race → 404 `unknown_race` (incl. any
  2025 id); unknown frame → 404 `unknown_frame`; malformed
  index/pagination → 422 via FastAPI validation; non-checkpoint →
  404 `not_prediction_checkpoint` (+ prev/next pointers, never a
  past-prediction substitution); checkpoint with missing/stale/
  incomplete/corrupt cache → 503 `prediction_unavailable` (+
  machine-readable `reason`); valid-frame reconstruction failure →
  500 `internal`. Bodies never carry traces/paths/model internals.
- `api/main.py` (permitted minimal additive change, 2 lines): import
  + `include_router` for the replay router. Phase-4 and legacy
  routers untouched.
- `tests/test_v2_phase5_r4.py` (~new): 51 tests green (see below).

Existing V2 audit (R4-A): router composition = legacy `api.routes`
+ `api.v2_routes` on one FastAPI app; DI = `Depends(get_v2_service)`
with `lru_cache` process-local singleton; errors = `{error, detail}`
JSONResponse mapping (404/422/503/500); Pydantic v2 boundary models
converting domain `to_dict()` one way; pagination = offset>=0 /
limit 1–500 / default 100 (`/states`); serialization = domain dicts
through frozen response models (probabilities verbatim);
served-season enforcement = `SERVED_SEASONS` registry → 404;
legacy isolation = separate router/module, replay imports neither.
R4 integrates additively per these conventions; no Phase-4 API
architecture refactored.

Timeline endpoint: paginated `ReplayFrame` metadata; builder +
selector run once per race on first request (~4 ms cold, ~0 ms
warm); listing provably never reconstructs (resolver cache stays
empty — asserted). Concatenated odd-sized pages reproduce the
domain timeline byte-for-byte (R1 ordering preserved).

Frame endpoint: exact R2 path (`timeline.frame_at` → `to_anchor()`
→ frozen `reconstruct()` → identity check). HTTP `state` equals the
direct `RaceState` projected through the SAME frozen
`V2RaceStateResponse` used by `GET /state` (the schema drops only
the 3 roster-id convenience keys `observable_driver_ids` /
`roster_driver_ids` / `unobservable_driver_ids` — pre-existing
Phase-4 projection, unchanged by R4). Parity proven for ordinary
mid-race, frame 0 (pre-first-observation nulls), partial
(2021-r12-R last, leader 3), red (flag_red/`red_flag`), stale
(positive-age members), shared-T divergence (2020-r09-R @2974.257
→ giovinazzi/lap6, `yellow`), SC (`flag_safety_car`), VSC
(`flag_vsc`).

Prediction endpoint: checkpoint hit → stored snapshot verbatim
(driver order, probs, null+reason, `ModelIdentity`, reasons, frame
identity, `INDEPENDENT_BINARY` note; synthetic sums >1 pass
through, no `probability_share` anywhere); non-checkpoint → 404
with pointers; missing/stale/corrupt/incomplete → 503 with reason.
Live frozen snapshot (2023-r01-R checkpoint 0) → R3 artifact →
`read_cached_prediction` proven bit-identical incl. probability
sums; the single-checkpoint prefix artifact is refused as
`cache_incomplete` (partial cache never served as complete).

No-generation proof: missing/stale cache → immediate explicit
error (<2 s, never ~12 s); service exposes no engine/bridge/
predictor attribute; AST scan of both replay modules finds no
generation token; hermetic subprocess import pulls no
`v2.prediction` / `v2.race_state_features` / `v2.model_lab` /
`api.v2_service` module; stale artifact bytes untouched by the read
path (asserted).

2025 firewall: `2025-r01-R` → 404 `unknown_race` on all three
routes; protected evaluation artifacts never read.

2023-r01-R integration: first/last pages, frames 0/mid/last,
leader laps 1..57, frame 0 = `LEADER_LAP` checkpoint; checkpoint
count re-pinned at 61 (57 leader + 4 flag-only).

Performance (smoke, this hardware): service init 0.000 s (shares
corpus); timeline cold 0.004–0.006 s (R0 <1 s target met ~200x);
timeline warm ~0.0000 s; factual frame 0.04–0.08 s single-sample
(vs R2 ~150 ms full-field p95 baseline — same order, API overhead
negligible; the <100 ms R0 target remains a target, no frozen
optimization per prohibitions); cached prediction read
0.0006–0.0011 s (3 orders below generation). Memory: one shared
corpus reference (identity-asserted, no second load); per-race
caches hold only small identity lists and grow only on first touch
of each race, stable across repeated requests; no model/engine
built by the replay service.

Tests: `tests/test_v2_phase5_r4.py` — **51 passed in ~4 s**
(init/lazy/lookup, schema, pagination incl. 9-case matrix,
determinism, reconstruction-free listing, frame shape/nav/parity
×8 fixtures, unknown/malformed frames, determinism, hit/miss/
stale/corrupt/incomplete, not-checkpoint pointers, live-snapshot
parity, AST + hermetic + behavioral no-generation, error-body pins,
2025 ×3, route inventory, legacy health, Bahrain sweep, perf +
memory smoke). MEDIUM gate: Phase-5 R1+R2+R3+R4 + Phase-4
R5/R6/freeze = **254 passed, 1 authorized drift, ~6 min**:
`test_frozen_module_hashes_match` flags ONLY `api/main.py`
(the 2-line permitted router include; all other 16 pinned paths
byte-identical per independent re-hash). Full suite NOT rerun
(risk-based gate per R4-Y).

Frozen identities: HEAD == Phase-4 seal `4f26801…`, tag
`v2-race-state-prediction-phase4` dereferences to `4f26801…`;
manifest values intact — artifact `1116b34f…`, phase-2
`d2ee966c…`, spec `3164de9e…` (all three match spec strings;
live re-verification via the gate's remaining freeze tests,
green). No frozen scientific implementation changed.

Deviations: one, authorized — `api/main.py` hash drift from the
explicitly permitted additive include (documented above; Phase-5
R8 owns the freeze update). `NotPredictionCheckpointError` uses
404 (the "409 or 404" option) to match the existing
resource-absence semantics.

Known risks: full backfill (~30 CPU-h) unstarted by design;
production `results/v2_replay/checkpoints/` absent → prediction
endpoints 503 until the offline backfill runs (factual replay
fully usable without it); R2 latency note unchanged.

R5 readiness: R5 consumes the three routes + schemas as-is (new
`features/replay/` slice + `lib/v2.ts` client); no new backend
need anticipated. R5 NOT started. Frontend NOT implemented.
Probability timeline NOT implemented.

---

## 30. R5 implementation record (2026-09-19, R5 COMPLETE — READY FOR R6)

Status: first production-quality historical replay UI live at
`/replay`. Race select → timeline → factual frame → transport /
scrubber / leader-lap jump / play-pause-speed → running order +
context + checkpoint-aware prediction panel. No backend file
changed by R5 (verified via worktree audit); R4 contracts consumed
as-is — no contract gap found. No normalization, no interpolation,
no anchor mechanics in React. Probability timeline NOT implemented
(R6); R6 NOT started.

Actual files:

- `frontend/lib/v2.ts` (~new): typed V2 client — `V2RaceSummary`,
  `ReplayFrameMeta/TimelinePage`, full `RaceState`/`Driver`/
  `Context`/`Weather`/`RaceControl` types, `ReplayFrameResponse`
  (incl. nav + leader_lap + checkpoint pointers),
  `CheckpointMeta`, `PredictionSnapshot`/`DriverPrediction`,
  `ReplayPredictionResponse`, `V2ApiError` (status/code/reason/
  checkpoint pointers, `isUnavailable()`/`isNotCheckpoint()`).
  `getV2Races` / `getReplayTimelinePage` / `getReplayFrame` /
  `getReplayPrediction` (fetch-injectable, `NEXT_PUBLIC_API_BASE`
  convention shared with legacy `lib/api.ts`, which is untouched),
  plus `fetchFullTimeline` (sequential pagination, deterministic)
  and `validateTimeline` (dense 0..N-1, no dup/gap/race-mix —
  missing frames are never inferred). No `any` in core contracts.
- `frontend/features/replay/lib/replayMachine.ts` (~new, React-free):
  navigation bounds (0-based identity, 1-based display), pure
  playback reducer (paused/playing, seek-pauses, tick, auto-pause
  at end with no wrap, reset, speeds 0.5/1/2/4 with 500 ms 1x
  base), `leaderLapSearchStep` binary-search mapping over
  (frameIndex → leaderLap) probes (null/unknown aborts loudly,
  never guesses), chronological race ordering, verbatim factual
  formatters (gap/lap/m:ss.mmm/age; probability text with null
  preserved; verbatim sums), observed/stale/unobserved
  classification from provenance.
- `frontend/features/replay/hooks/useReplay.ts` (~new): single
  authoritative `frameIndex`; exact frame fetches only; request-id
  + AbortController stale protection; bounded frame cache (200);
  advance-after-response playback loop (one fetch at a time, no
  timer pile-up); predictions fetched ONLY at checkpoint frames
  and remembered per frame (known 503 never retried per tick);
  race change stops playback and clears frame/prediction/caches
  (no previous-race bleed); jump-to-lap via probe search (40-probe
  cap, session-guarded); write-mostly URL deep-link
  (`?race=&frame=`, validated once, `replaceState` updates).
- Components (~new): `RaceSelector` (served registry as-is,
  chronological; nothing fabricated), `TimelineScrubber`
  (pointer-drag preview + commit on release; keyboard steps commit
  singly), `PlaybackControls` (FIRST/PREV/play-pause/NEXT/LAST
  with bound-disabled buttons, speed select, leader-lap jump with
  failure message), `StandingsTable` (complete roster by factual
  position, lap/gap/tyre/stops, STALE x.xs + NO DATA labels,
  nulls as em-dash, no inferred retirement), `ContextBar`
  (track-state banner with text+color, T, leader lap + progress,
  anchor, as-of weather, active flags), `PredictionPanel`
  (checkpoint badge vs NO-MODEL-CHECKPOINT note; HIT ranking by
  probability with bars — never a pie — INDEPENDENT_BINARY note
  with verbatim Σ >100% aggregate; 503 unavailable card;
  non-checkpoint frames never request), `ReplayView`
  (timing-tower layout, independent loading/error states, last
  good frame kept visible during transitions, aria-live status).
- `frontend/app/replay/page.tsx` (~new): route entry + metadata.
- `frontend/app/page.tsx` (+2 lines): "Historical replay →" link;
  prediction feature untouched.
- Tests (~new): `frontend/lib/v2.test.ts` (endpoint URLs,
  multi-page 1091-frame assembly, truncation/dup/gap/race-mix
  rejection, 404/503 error parsing with pointers+reason,
  pass-through race list) + `features/replay/lib/
  replayMachine.test.ts` (bounds, reducer incl. auto-pause +
  seek-pause + reset, search mapping incl. abort cases,
  formatting, null≠0%, status classes, identity, ordering).

Frontend audit (R5-A): Next 16 / React 19 / Tailwind v4, `@/`
alias, `"use client"` pages, legacy `lib/api.ts` + `features/
prediction/` + `components/prediction/` (untouched), `node
--test` type-stripping tests (no framework to install),
`NEXT_PUBLIC_API_BASE` convention, motion available (not needed
for replay). Replay entered through the new `lib/v2.ts` +
`features/replay/` boundary only.

Leader-lap behavior: displayed on every frame (mandatory);
jump-to-lap IMPLEMENTED (not deferred) via binary search over
frame `leader_lap` probes — monotone per R2 audit, null-abort
guarded, ~11 requests worst case, results land in the frame
cache. No anchor-lap confusion anywhere (anchor shown as plain
metadata).

Playback: client-owned paused/playing; 0.5x/1x/2x/4x over a
500 ms 1x base (step-based per R0, historical durations never
waited); auto-pause at last frame, no wrap; race change and
manual nav pause; `state_time_s` displayed, never mutated, never
presented as real-time simulation speed.

Stale/unobservable UX: STALE x.xs amber label + tooltip
(last-known, not live); NO DATA dimmed rows with full nulls;
stale rows never hidden, nulls never zero, no "retired" labels.

Flags/context UX: RED FLAG / SAFETY CAR / VIRTUAL SC / YELLOW /
GREEN text banner + matching color (never color-only); active
flag tokens listed; red-flag-invalid gaps render "n/a".

Prediction UX: checkpoint badge shows reasons; HIT panel ranks
by probability desc with driver identity exact and values
verbatim; non-checkpoint shows the factual-only note and issues
no request; 503 shows "Prediction unavailable / cache not
generated" while factual replay continues.

Loading/errors: independent race/timeline/frame/prediction
states; retry only for timeline; error bodies surfaced as plain
copy (no traces/paths). Deep-link decision: implemented
write-mostly (`?race=&frame=`), validated against served list +
bounds with safe fallbacks, no router loops.

Responsive/accessibility: standings + prediction side-by-side
on xl, stacked below; no row overflow (overflow-x-auto table);
labelled controls, correct disabled states, labelled slider,
keyboard-operable transport, focus-visible rings, aria-live
status, text (non-color) flag meaning, semantics as text.

Tests: `node --test` over all 5 frontend suites — **44 passed,
0 failed** (22 new: 10 client + 12 machine). TypeScript
`tsc --noEmit` clean. ESLint: 0 errors, 1 pre-existing warning
in untouched legacy `ResultCards.tsx` (`barClassName` unused —
left as-is). Production `next build` green with the `/replay`
route (static prerender).

Performance observations: no browser harness available —
structural instead: timeline = 3 sequential ≤500-frame
requests/race; playback = ≤1 frame fetch outstanding at any
time (advance-after-response) with 200-entry cache making
revisits free; predictions ≤1 per checkpoint frame ever (cached
hits + remembered misses); scrub drags issue zero requests
until release. Backend smoke (R4): cached prediction ~1 ms,
frame ~0.04–0.08 s sample — frontend overhead is one fetch per
transition, well under the 200 ms interaction budget where the
backend permits.

Backend contract regression (R5-AF): `tests/test_v2_phase5_r4.py`
**51 passed** — no backend file changed by R5 (worktree shows
only the R4 backend set + R5 frontend additions).

2025 behavior: frontend renders only the served registry (no
season filter, no hardcoded exclusion); backend 404s surface as
"Unknown race". Tests assert pass-through with no client-side
fabrication.

Deviations: jump-to-lap implemented rather than deferred (clean
deterministic mapping existed — binary search over frame
metadata, R4 change unnecessary). Scrubber has no checkpoint
tick marks (R4 timeline metadata carries no checkpoint flags by
design; ticks would require per-frame fetches). One lint fix
also repaired a real staleness bug (nav bounds now read reactive
state, not a ref).

Known risks: production prediction cache still absent → HIT
panel exercises only in tests/tmpdir until the offline backfill
runs; playback at 4x (125 ms interval) is backpressure-bound by
the ~150 ms factual fetch (correct, slightly slower than
nominal — by design, never overlapping requests).

R6 readiness: R6 consumes `fetchFullTimeline` frames +
checkpoint `frame_index` values for the probability-timeline
overlay plus the existing `V2ApiError` pointer fields for
nearest-past labelling; draw-only interpolation stays a pure
rendering concern. No backend need anticipated. R6 NOT started.


---

## 31. R6 implementation record (2026-09-19, R6 COMPLETE — READY FOR R7)

Status: read-only probability timeline projection + HTTP endpoint + replay
visualization implemented. R6 never runs the model, never interpolates
inference, never normalizes. No frozen Phase-1/2/3/4 scientific file
modified; no 2025 access; full backfill NOT launched. All four frozen
identities re-verified live (tag `4f26801…` via `^{commit}`, artifact
`1116b34f…`, phase-2 `d2ee966c…`, spec fp `3164de9e…`).

Actual files:

- `v2/replay_probability_timeline.py` (~new): projection contract
  `PROBABILITY_TIMELINE_CONTRACT_VERSION = "v1"`;
  `build_probability_timeline(artifact)` projects an already-validated R3
  artifact into `{race_id, replay/prediction/timeline contract versions,
  probability_semantics, model, timeline_identity, checkpoints,
  driver_series}`; `timeline_identity` = sha256 over race + versions +
  semantics + model + series content (no timestamps/uuids);
  `canonical_timeline_json` for byte determinism. Model-free: imports only
  `v2.replay` + R3 identity constants, never engine/bridge/predictor.
- `api/v2_replay_schemas.py` (+4 response models):
  `V2ProbabilityCheckpointResponse`, `V2DriverProbabilityPointResponse`,
  `V2DriverProbabilitySeriesResponse`, `V2ProbabilityTimelineResponse`
  (reuses `V2ModelIdentityResponse`); no pandas/numpy, no giant dict.
- `api/v2_replay_service.py`: added read-only
  `V2ReplayService.get_probability_timeline(race_id)` + per-race cached
  projection; imports only the projection + R3 read helpers.
- `api/v2_replay_routes.py`: added `GET
  /v2/races/{race_id}/replay/probability-timeline` on the existing router.
- `frontend/lib/v2.ts`: probability-timeline types +
  `getReplayProbabilityTimeline` (fetch-injectable, `AbortSignal`).
- `frontend/features/replay/lib/probabilityTimeline.ts` (~new, React-free):
  checkpoint lookup, deterministic top-N visibility,
  `probabilityAtCheckpoint` (no fill), `currentFrameAlignment`
  (checkpoint/between/before/after), `buildChartGeometry` (SVG geometry;
  segments break at null; raw values, no normalization).
- `frontend/features/replay/components/ProbabilityTimelineChart.tsx`
  (~new): SVG chart + driver toggles + accessible checkpoint detail
  table; factual FLAG_TRANSITION markers; no stacked/share/pie.
- `frontend/features/replay/hooks/useReplay.ts`: `ProbabilityTimelineView`
  fetched once per selected race, cleared on race change, 503 nonfatal.
- `frontend/features/replay/components/ReplayView.tsx`: full-width chart
  (keyed by race id to reset display overrides) above the running order.
- `tests/test_v2_phase5_r6.py` (~new, 53 tests);
  `frontend/lib/v2.test.ts` (+2); `frontend/features/replay/lib/
  probabilityTimeline.test.ts` (~new, 11).

Domain contract: one point per (driver_id, ACTUAL prediction checkpoint).
Grain preserved exactly — no frame expansion, no resampling, no
forward/backward fill, no nearest-checkpoint substitution; projected
frame set == stored checkpoint set. Driver ordering deterministic
(driver_id ascending); checkpoint metadata (frame_index, state_time_s,
leader_lap, reasons) exposed once in chronological order.

Null semantics: null stays null (never 0.0), null drivers are retained,
complete roster required at every checkpoint (drift rejected).

INDEPENDENT_BINARY preservation: sums > 1 and < 1 pass through verbatim
(tested at domain and HTTP layers); no `probability_share`/sum-to-one
field anywhere; chart uses independent lines (no stacked/pie).

Model identity: R3 artifact-level `ModelIdentity` exposed ONCE at the
timeline top level; per-entry model drift, non-INDEPENDENT_BINARY
semantics, anchor mismatch, roster drift, duplicate drivers, unsorted
reasons, non-finite probabilities, incomplete/unknown-format artifacts
all raise (tampered identity rejected).

Deterministic identity: repeated projection of identical artifact is
byte-identical; unrelated artifact fields (cache_key, series, observed
position/lap, note) do not move `timeline_identity`.

Read-only projection: operates on an already-validated artifact; never
reconstructs RaceState, builds features, runs the predictor, mutates the
artifact, or creates missing checkpoints. Cache miss/stale/incomplete →
unchanged; tampered content → `cache_corrupt`.

API endpoint: `GET /v2/races/{race_id}/replay/probability-timeline`
(existing router), one complete response (~61×20 ≈ 110–130 KB), no
pagination. Cache behavior: absent → 503 `prediction_unavailable`
`cache_missing`; stale/corrupt/incomplete → 503 with explicit reason;
unknown race and any 2025 race → 404 `unknown_race`; never generates.

No-generation proof: AST scan of the projection module + hermetic
subprocess import (no `v2.prediction` / `v2.race_state_features` /
`v2.model_lab` / `api.v2_service` / sklearn) + behavioral missing-cache
resolves < 2 s; artifact bytes untouched by the read path.

Backend parity: artifact → domain → HTTP exact for checkpoints, driver
series, probabilities/nulls, ModelIdentity, timeline_identity and
INDEPENDENT_BINARY.

Frontend visualization: `WIN PROBABILITY EVOLUTION`; x = checkpoint
ordinal with leader-lap labels (exact frame/T/lap in details); y = raw
winner_probability (values > 100% shown as-is); actual observations only,
lines connect visually only; nulls break the line; no stacked/share view.
Driver visibility: deterministic top-5 by peak probability, all series
toggleable, labelled "display filter only". Current-frame sync: exact
checkpoint highlighted; between-checkpoint frames show a distinct marker
and "between model checkpoints" — no current probability is implied.
Checkpoint details: factual frame/T/leader lap/reasons + per-driver
probabilities in a text table (accessible fallback), null shown "n/a".
FLAG_TRANSITION checkpoints marked factually (no causal text).
Cache-absent UX: compact nonfatal "Probability timeline unavailable …";
factual replay/playback/standings unaffected; no per-frame retry.

Payload size (synthetic 2023-r01-R: 61 checkpoints × 20 drivers):
**112,114 bytes** — comfortably one response; typical ≈ 110–130 KB.

Performance (this hardware, local): projection 0.0037 s, warm 0.0000 s,
HTTP ~0.0023 s — far below the R0 250 ms cached-HTTP target. No model
runtime in R6.

Scientific adversarial result: mutating non-probability/observed fields
does not change the projection; projected frame set equals stored
checkpoint set with no new inferred probability observations introduced
by the R6 projection.

Backend tests: `tests/test_v2_phase5_r6.py` — **53 passed** (grain,
ordering, metadata, roster, nulls, no-normalization sums both sides of 1,
determinism, tampered rejection ×9, cache states, HTTP states, parity,
INDEPENDENT_BINARY, read-only firewall, payload/perf smoke). MEDIUM gate:
R1+R2+R3+R4+R6 + Phase-4 freeze = **243 passed, 1 authorized drift** —
only `api/main.py` (the R4 2-line router include; all other pinned paths
byte-identical). No R6 frozen-file drift.

Frontend tests: `node --test` over 6 suites — **57 passed, 0 failed**
(11 new transform/geometry + 2 new client). TypeScript `tsc --noEmit`
clean. ESLint 0 errors, 1 pre-existing warning (untouched legacy
`ResultCards.tsx`). Production `next build` green (`/replay` route).

2025 firewall: `2025-r01-R` → 404 `unknown_race` on the
probability-timeline route; protected evaluation artifacts never read;
frontend renders only the served registry.

Frozen identities: HEAD == Phase-4 seal `4f26801…`; tag
`v2-race-state-prediction-phase4^{commit}` == `4f26801…`; manifest values
intact — artifact `1116b34f…`, phase-2 `d2ee966c…`, spec `3164de9e…`
(all re-verified live). No frozen scientific implementation changed.

Deviations: none material. Chart implemented as a small SVG (package.json
audited: no chart library present; a large dependency was not justified
for one plot). x-axis uses checkpoint ordinal with leader-lap labels
rather than raw leader-lap position because flag-transition checkpoints
can share a leader lap; both are display-only and exact metadata remains
in tooltips/details.

Known risks: production prediction cache still absent → probability
timeline returns 503 until the offline backfill runs (cache-absent UX
handled, factual replay unaffected). R2 per-frame latency debt unchanged.

R7 readiness: R7 owns the full §22 matrix, 149-race sweep (factual),
backfill evidence, and measured budget sign-off; no R1–R6 change needed.
R7 NOT started.

---

## 32. R7 implementation record (2026-09-19, R7 COMPLETE — READY FOR R8)

Status: hardening / adversarial / performance / pre-freeze audit. Two
Phase-5-owned defects found by evidence and fixed with the smallest safe
change; no frozen Phase-1/2/3/4 scientific file modified; no 2025 access;
production prediction cache NOT generated; full backfill NOT launched.
R8 work (freeze manifest, report, commit, tag, full verification) NOT
performed. All four frozen identities re-verified live.

**Actual files (R7):**

- `tests/test_v2_phase5_r7.py` (~new): 120 tests (115 passed + 5
  intentional skips), the R7 hardening suite below.
- `scripts/benchmark_phase5_replay.py` (~new): reproducible model-free
  benchmark (R7-Q).
- `v2/replay_predictions.py` (MODIFIED, hardening): added
  `validate_snapshot` + stricter `load_validated_artifact` (root-type,
  checkpoint-entry drift, roster/probability validation). Read-path only;
  no change to generation semantics or stored bytes.
- `frontend/features/replay/lib/replayMachine.ts` (MODIFIED): added pure
  `evictOldest` (bounded cache) and `isCurrentResponse` (stale guard)
  helpers.
- `frontend/features/replay/hooks/useReplay.ts` (MODIFIED): prediction
  effect now guards responses by navigation generation/session; frame
  cache uses `evictOldest`.
- `frontend/features/replay/lib/replayMachine.test.ts` (MODIFIED): +4
  tests (cache bound, stale-response suppression).
- `frontend/lib/v2.test.ts` (MODIFIED): +1 request-budget test.
- this §32 append only.

No change to `v2/replay.py`, `v2/replay_reconstruction.py`,
`v2/replay_probability_timeline.py`, `api/v2_replay_*.py`,
`scripts/build_replay_prediction_cache.py`, R1–R6 tests, or any frozen
Phase-1–4 module.

**R7-A contract inventory.** R1 `ReplayFrame`/`ReplayTimeline`/
`build_replay_timeline` + representative `(lap, driver)` rule;
R2 `ReplayReconstructor` (exact `state_at`, nav, `leader_lap_at`,
`frame_for_leader_lap`); R3 `PredictionCheckpoint`/`CheckpointSeries`/
`select_checkpoints`, `cache_identity_inputs`/`cache_key`, artifact
`build/write/load_validated`, offline `generate_*`/`ensure_race_artifact`;
R4 4 HTTP endpoints + schemas + `V2ReplayService`; R5 frontend
`replayMachine` + `useReplay`; R6 `build_probability_timeline` +
probability endpoint + chart. Dependency direction verified by AST scan:
domain (`v2/replay*`) imports no model/features/api; service imports
read-only R3 helpers only (no generation names); routes import service+
schemas only. Graphify `explain` confirms no edge from
`v2_replay_service.py` into `v2/prediction.py`, `v2/race_state_features.py`,
`v2/model_lab`, or sklearn (`V2Service` is imported deferred inside the
factory for static identity read only).

**Dependency / Graphify audit.** `graphify update .` exit 0: 7,140 nodes,
17,179 edges, 267 communities; **Import Cycles: None detected**; replay
nodes are not god nodes (`V2ReplayService` degree 43, `replay_predictions`
42, `replay.py` 28 vs top god `V2Paths` 202); replay communities are
cohesive; `graphify diagnose multigraph` same-endpoint examples 0. No new
cycle, god-node, or reverse-dependency problem. graphify-out/ stays
gitignored (not staged).

**R7-B scientific semantics audit.** Re-pinned across the 6-fixture slice:
one frame per unique `state_time_s` (dense 0..N-1, strictly increasing);
representative = `(lap_number, driver_id)` ascending; per-driver observed
time `<= T`; pre-first unobservable full nulls; stale observable with
positive age; partial race stops at leader lap 3 (jump to 4 raises);
red/SC/VSC flags + tokens verbatim; leader lap = leader progress (first
frame `>=` L with previous `<` L); checkpoints are actual timeline frames;
prediction only at checkpoints (non-checkpoint raises
`NotPredictionCheckpointError`); sums ≠ 1 pass through unnormalized; null
probability ≠ zero with a reason; probability timeline projects stored
observations only and is byte-deterministic. No semantic drift found.

**R7-C shared-T regression.** 2020-r09-R @ T=2974.257 → representative
`giovinazzi`/lap 6; reconstruction `track_state=yellow`,
`flag_yellow=true`, `flag_safety_car=false`; no latifi/lap7 frame exists;
HTTP shape + bytes stable; neighbors strictly chronological. Pinned at R1,
R2, R4, HTTP.

**R7-D edge-race matrix.** 9 cases × timeline/nav/RaceState/leader
lap/checkpoint/HTTP/frontend-shape: ordinary (2023-r01-R mid), early
pre-first (frame 0), late lapped (last, leader 57), partial (2021-r12-R
last, 60 frames, leader 3), red (2022-r18-R `red_flag`), stale
(2022-r07-R positive age), SC (2020-r09-R `safety_car`), VSC (2018-r01-R
`vsc`/`vsc_ending`), shared-T. All green; the 5 skips are cases where the
selected edge frame is itself a checkpoint, so the non-checkpoint pointer
test does not apply (documented, not debt).

**R7-E temporal adversarial suite.** Poisoning strictly-future rows
(position, lap, tyre, stint, pit, weather, RC/flags, leader lap) leaves the
current-T `RaceState` bytes, frame identity, and checkpoints `<= T`
identical (ordinary/partial/red × mid), and the stored synthetic artifact
+ probability projection byte-unchanged. Wording: **no leakage was
detected under the implemented adversarial test suite** (not a proof
beyond it).

**R7-F checkpoint distribution (measured, full 2018–2024 D9).** 149 races,
**9,644 checkpoints** (matches R3). Distribution: min 3, p25 57, median
63, p75 73, p95 82, max 95, mean 64.72. Reasons: LEADER_LAP-only +
both = leader-lap transitions; FLAG_TRANSITION-only extras exist
(total > leader-only); one checkpoint per frame max. Top races
2023-r06-R (95 = 78 leader + 17 flag), 2020-r16-R (94 = 87+7),
2022-r07-R (89 = 64+25); max flag-only in one race 25 → no malformed
track-state oscillation / checkpoint explosion. No policy change (no bug).

**R7-G cache hardening (defect fixed — MINOR).** Adversarial matrix over
a valid synthetic artifact: truncated/empty/invalid JSON, non-object
root, wrong format, wrong race, wrong cache key/identity, wrong series,
`complete:false`, missing/extra/reordered checkpoint, wrong frame
identity, malformed entry, missing/duplicate/extra driver, NaN/±Inf,
negative, `>1`, null-without-reason, roster-size drift. Before the fix,
non-object root raised an unhandled `AttributeError` (HTTP 500) and
NaN/`>1`/missing-driver predictions were **served**. Fix:
`validate_snapshot` + stricter `load_validated_artifact` in
`v2/replay_predictions.py`; all cases now fail deterministically as
`PredictionUnavailableError` (503 `cache_stale`/`cache_incomplete`/
`cache_corrupt`). HTTP bodies carry no traceback, path, model, or
`sklearn`/`joblib` token. Owner: Phase-5 R3 (inside boundary).

**R7-H atomic / interruption hardening.** A valid existing artifact
survives a forced failed regeneration (engine raises) byte-for-byte;
partial prefixes are never `complete`; `write_artifact` failure leaves no
`.tmp` orphan and no target file; publishing is temp+`os.replace`
(no partial window); resume skips valid-complete and regenerates
otherwise. Focused mocks/tempdirs only.

**R7-I concurrency / reentrancy.** 8–12 thread pools over same
frame/different frames/different races/timeline/cached prediction/
probability timeline: identical serialized results, no exceptions, no
mutation. Concurrent first-touch may build more than one immutable
timeline (no lock) but all results and the final cache entry are
identical — benign, no lock added.

**R7-J lazy cache audit.** All five in-process caches start empty;
timeline/series/resolver/artifact/probability caches reuse the same
immutable objects and grow only for served races actually requested
(bounded by the 149-race registry); unknown races never cached. Frontend
frame cache bounded at 200 with deterministic oldest-first eviction
(`evictOldest`, tested); race change replaces the cache map and clears
prediction memoization (no cross-race bleed).

**R7-K/L API hardening + route inventory.** Exact 4 replay GET routes,
each registered once; Phase-4 + legacy routes preserved. Error matrix:
unknown race → 404 `unknown_race` (incl. all 2025), unknown/huge frame →
404 `unknown_frame`, malformed index/pagination → 422, non-checkpoint →
404 `not_prediction_checkpoint` + pointers, corrupt/missing cache → 503
`prediction_unavailable` + reason, never a synchronous model run
(<2 s). Bodies never leak traces/paths/internals.

**R7-M frontend state-race hardening (defect fixed — MINOR).** The
prediction effect previously guarded only by race session: a late
prediction for an older checkpoint frame could overwrite a newer frame's
panel. Fixed with a navigation-generation guard (`isCurrentResponse`,
request id + session) in `useReplay.ts`; pure helper tested. Race change
already aborts/clears frame, prediction, caches, and probability series.

**R7-N/O frontend request budget + cache bounds.** Timeline = exactly
`ceil(total/500)` requests (tested at 1/499/500/501/1000/2001 frames);
probability timeline = max one request per race load (503 nonfatal, no
retry loop); frames = one per uncached requested frame (advance-after-
response backpressure); predictions only at checkpoints, remembered
per frame; scrubber drag commits once (pointer-up), zero requests during
drag; leader-lap jump bounded 40-probe binary search (~11 worst case) and
no backend endpoint added (evidence did not justify one). 200-frame cache
bound enforced + deterministic; race change isolates entries.

**R7-P accessibility / responsive smoke (code/test audit).** Labelled
transport buttons + speed select + leader-lap input, labelled range
slider, correct disabled states, `role="alert"` errors, `aria-live`
playback status, `role="status"` flag banner with text + color (never
color-only), null as em-dash / "n/a", probability-threshold text,
`focus-visible` rings, responsive stacking (xl grid → columns, tables
`overflow-x-auto`). No redesign.

**R7-Q controlled benchmark (`scripts/benchmark_phase5_replay.py`, 30
samples, this machine; ms):** service init 0.0004; timeline cold 2.73
(p95 2.75); timeline warm ~0.00; checkpoint selection 3.83; reconstruction
early 0.66 / mid 37.4 / late 37.5 / stale 37.0 / partial 37.4 / red 22.6 /
shared-T 34.2; artifact load 1.38; cached prediction 0.68 (p50 ~0);
probability projection 1.53; timeline HTTP pagination 4.38; frame HTTP
38.8 (p95 39.5); cached prediction HTTP 0.87; probability timeline HTTP
2.82 (p95 4.01). p95 shown (n=30); p99 intentionally n/a (n<100).
Leader-lap backend lookup 374 ms because `frame_for_leader_lap` probes via
full `RaceState` reconstruction (~10 × 37 ms) — R2-internal helper, not
served by any endpoint (frontend does client-side probes), documented
debt, not optimized.

**R7-R reconstruction latency investigation.** The R2 ~150 ms p95 vs R4
40–80 ms discrepancy is resolved as environment/measurement-sensitive:
under a controlled 30-sample warm benchmark on this machine full-field
reconstruction is stable at ~37 ms p50/p95 for ordinary mid/late, stale,
partial, and shared-T frames (matching the Phase-4 ~39 ms baseline); early
frames ~0.7 ms. No frozen code touched; no cache added.

**R7-S R0 performance target assessment.** timeline cold <1 s → MET
(2.7 ms). factual frame <100 ms p95 → MET (37–39 ms p95, controlled warm;
the earlier ~150 ms reading was environment-sensitive). cached HTTP
<250 ms p95 → MET (frame 39.5 ms, prediction 1.0 ms, probability 4.0 ms).
frontend transition <200 ms → NOT DIRECTLY MEASURED (no browser harness);
structurally supported (backend frame HTTP 38.8 ms p95 + paint). No fake
success.

**R7-T memory assessment (RSS, 6-race slice, this machine).** After
imports 93.0 MB → after corpus+reconstructor 213.5 → service init 213.5
(shares refs, no copy) → first timeline 214.1 → all 6 timelines 215.1 →
100 frame requests 215.4 → probability timeline 215.5 → repeat 215.5.
No unexpected monotonic growth; caches bounded by requested served races.
(Full-corpus Phase-4 memory debt is documented separately and unchanged.)

**R7-U production cache operational plan (verified, NOT launched).**
Commands: dry-run `python scripts/build_replay_prediction_cache.py
--race-id 2023-r01-R --dry-run`; single race `--race-id 2023-r01-R`;
season `--season 2023`; full `--all-served-races`; default resumes by
skipping valid-complete artifacts (`--resume` is the explicit marker),
`--force` regenerates, `--max-checkpoints` for subsets. Dry-run verified
live: 2023-r01-R = 61 checkpoints (57 leader + 4 flag); 2023 season = 22
races / 1,412 checkpoints (no write). Full expected **9,644** checkpoints
(149 races), ~29–30 serial CPU-hours, ~90 MB storage (R3 arithmetic,
retained). Before backfill: factual replay works; prediction endpoint and
probability timeline return 503 `cache_missing` (R7 API matrix). After a
valid artifact: prediction HIT + probability timeline verified with
controlled/synthetic artifacts (R4/R6/R7). `results/v2_replay/` absent.

**R7-V generated-artifact policy.** `results/v2_replay/` is ignored
(`.gitignore` line 128) and no generated cache is staged; the ignore is
narrow (one directory) and does not hide unrelated `results/` content.
Generated prediction cache must NOT be staged in R8.

**R7-W 2025 firewall.** `2025-r01-R` → 404 `unknown_race` on timeline,
frame, prediction, and probability-timeline routes; backfill CLI rejects
2025/out-of-scope before any model work; protected evaluation targets
never read.

**R7-X frozen upstream identity.** HEAD == Phase-4 seal
`4f26801ffb0bb1a10725d6c78fba11c5547cb432`; tag
`v2-race-state-prediction-phase4^{commit}` == `4f26801…`; serving artifact
SHA-256 `1116b34f…`; Phase-2 content hash `d2ee966c…`; model spec
fingerprint `3164de9e…` — all intact. All `phase4_tests`/`benchmark`/
`api_contract` hashes and every `phase4_modules` path except `api/main.py`
are byte-identical; `api/main.py` drift is exactly the authorized R4
additive replay-router include (2 lines). No forbidden scientific drift.

**Defects found / fixed.** Both MINOR, Phase-5-owned, regression-tested:
(D1) R3 read path could serve/500 on malformed cached artifacts
(non-object root, NaN/±Inf/out-of-range probability, incomplete/duplicate
roster, checkpoint-entry drift) → hardened `load_validated_artifact` +
`validate_snapshot`. (D2) R5 frontend could let a stale prediction response
overwrite a newer frame's panel → `isCurrentResponse` navigation-generation
guard. No BLOCKER/MAJOR. No frozen conflict.

**Verification.** `tests/test_v2_phase5_r7.py`: **115 passed, 5 skipped,
0 failed** (~16 s). Broader Phase-5 MEDIUM gate (R1+R2+R3+R4+R6+R7 +
Phase-4 freeze/R5): **407 passed, 5 skipped, 1 failed** — the single
failure is `test_frozen_module_hashes_match` flagging only `api/main.py`
(the authorized R4 include; R7's own identity test pins all other frozen
paths). Frontend: `node --test` **62 passed** (6 suites); `tsc --noEmit`
clean; ESLint 0 errors / 1 pre-existing warning (untouched legacy
`ResultCards.tsx`); production `next build` green (`/replay` prerendered).
Full ~57-minute repo suite NOT run (R8 owns final). No `tests/test_v2_phase5_r5.py`
exists (R5 tests are frontend-only).

**Pre-freeze file inventory for R8** (R7 does not stage):
- NEW Phase-5 source: `v2/replay.py`, `v2/replay_reconstruction.py`,
  `v2/replay_predictions.py`, `v2/replay_probability_timeline.py`,
  `api/v2_replay_schemas.py`, `api/v2_replay_service.py`,
  `api/v2_replay_routes.py`, `scripts/build_replay_prediction_cache.py`,
  `scripts/benchmark_phase5_replay.py`, `tests/test_v2_phase5_r1.py`,
  `tests/test_v2_phase5_r2.py`, `tests/test_v2_phase5_r3.py`,
  `tests/test_v2_phase5_r4.py`, `tests/test_v2_phase5_r6.py`,
  `tests/test_v2_phase5_r7.py`, `frontend/lib/v2.ts`,
  `frontend/lib/v2.test.ts`, `frontend/features/replay/**`,
  `frontend/app/replay/page.tsx`, `docs/PHASE5_HISTORICAL_REPLAY_PLAN.md`.
- MODIFIED Phase-5: `api/main.py` (authorized 2-line include),
  `frontend/app/page.tsx` (replay link), `.gitignore`
  (`results/v2_replay/`, `graphify-out/`).
- GENERATED/IGNORED: `results/v2_replay/` (absent), `graphify-out/`.
- UNRELATED USER WORK (do not stage/touch): `.claude/**`, `.cursor/**`,
  `.gemini/settings.json`, `.ignore`, `.mcp.json`, `AGENTS.md`, `GEMINI.md`,
  `opencode.json`, `package.json`, `package-lock.json`, `.opencode/**`.
No accidental Phase-5 drift detected.

**Remaining debt.** (1) Full prediction backfill (~30 CPU-h, ~90 MB)
unstarted by design → prediction endpoints 503 until run; factual replay
fully usable. (2) `frame_for_leader_lap` backend helper is ~374 ms
(reconstruct-per-probe); not served by any endpoint (frontend probes
client-side) — documented, not optimized. (3) R2 §27 latency note resolved
by R7 to an environment-sensitive reading; controlled p95 now 37–39 ms.
(4) Frontend transition target not directly measured (no browser harness).
(5) `api/main.py` hash drift remains authorized and unfrozen until R8.

**R8 readiness.** No scientific freeze conflict; no replay-correctness,
cache-correctness, API-correctness, or frontend-state blocker; performance
honestly characterized; remaining debt documented; upstream identities
intact; intended file inventory known. Production prediction cache not
generated (not required to freeze the software). R7 **COMPLETE — READY
FOR R8**.

---

## 33. R8 implementation record (2026-09-20, R8 COMPLETE — PHASE 5 FROZEN)

Status: final freeze/seal. Repository reality audited and every changed
path classified (`PHASE5_INTENDED` / `GENERATED_IGNORED` /
`UNRELATED_USER_WORK`); no unexplained Phase-5 drift. No product feature
added. No frozen Phase-1/2/3/4 scientific file modified. Production
prediction cache NOT generated; full backfill NOT launched. All four
frozen upstream identities recomputed from repository reality (Phase-4
seal `4f26801ffb0bb1a10725d6c78fba11c5547cb432`; tag
`v2-race-state-prediction-phase4`; serving artifact
`1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`;
Phase-2 content hash
`d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`;
model spec fingerprint
`3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d`).

Actual files (R8):

- `docs/PHASE5_REPLAY_API_CONTRACT.json` (~new): normalized compact
  contract for exactly the four replay routes (method, path, path/query
  parameters, success response model, error statuses/codes, semantic
  notes) plus the pagination pin (offset >= 0; limit 1..500 default 100),
  contract versions, `INDEPENDENT_BINARY`, and 2018–2024 scope.
- `tests/test_v2_phase5_freeze.py` (~new): compact cross-layer freeze
  seal (contract versions, exact four-route inventory, live-route vs
  API-contract artifact parity, representative rule, the shared-T
  critical fixture, served scope + 2025 exclusion, checkpoint policy
  identity, model-free 149/162,728/162,639/9,644 corpus facts,
  `INDEPENDENT_BINARY` + no normalization, read-only cache boundary,
  actual-checkpoints-only probability grain, null != zero,
  frontend/backend field compatibility, freeze-manifest identities,
  authorized `api/main.py` drift, upstream scientific identities). No
  production cache required; no model inference.
- `docs/PHASE5_FREEZE_MANIFEST.json` (~new): deterministic sorted JSON
  freeze manifest (upstream identities; Phase-5 contract versions; domain
  / API / frontend / tests / benchmark / documentation hashes; corpus
  facts; scientific identity; performance record; verification; known
  debt; git fields with expected tag and `manifest_self_hash: null`).
  No self-hash circularity.
- `docs/PHASE5_FINAL_REPORT.md` (~new): portfolio-quality technical
  report (§1–§18) using measured R1–R7/R8 facts.
- `docs/PHASE6_MONTE_CARLO_HANDOFF.md` (~new): what Phase 6 may rely on
  as frozen, the INDEPENDENT_BINARY-vs-simulated-outcomes distinction,
  and the 28 Phase-6 R0 open questions. Monte Carlo NOT implemented.
- this §33 append only.

**R8-A reality audit.** `git status` / `git diff` / untracked inventory
reconstructed the R1–R7 change set exactly; classification:
`PHASE5_INTENDED` = the new `v2/replay*.py`, `api/v2_replay_*.py`,
`scripts/build_replay_prediction_cache.py`,
`scripts/benchmark_phase5_replay.py`, `tests/test_v2_phase5_r1..r7.py`,
`tests/test_v2_phase5_freeze.py`, `frontend/lib/v2.ts`,
`frontend/lib/v2.test.ts`, `frontend/features/replay/**`,
`frontend/app/replay/page.tsx`, `docs/PHASE5_*.md`,
`docs/PHASE6_MONTE_CARLO_HANDOFF.md`, and the modified `api/main.py`
(authorized 2-line additive include), `frontend/app/page.tsx` (replay
link), `.gitignore` (`results/v2_replay/`, `graphify-out/`);
`GENERATED_IGNORED` = `results/v2_replay/` (absent), `graphify-out/`;
`UNRELATED_USER_WORK` = `.claude/**`, `.cursor/**`, `.gemini/**`,
`.ignore`, `.mcp.json`, `AGENTS.md`, `GEMINI.md`, `opencode.json`,
`.opencode/**`, root `package.json` / `package-lock.json`. No
`UNEXPECTED` paths.

**R8-B contract audit.** R1–R7 implementation audited against the frozen
product contract (factual replay, driver state, leader lap, checkpoint
policy, cache contract, probability semantics, probability timeline,
served scope). Representative rule and shared-T pinned: `2020-r09-R @
T=2974.257` -> `giovinazzi`/lap 6 (`track_state=yellow`); no latifi/lap7
frame. Corpus facts recomputed model-free and match R0/R1/R3/R7 exactly.

**R8 performance record (R7 benchmark authoritative).** timeline cold
2.73 ms (p95 2.75); frame HTTP 38.8 ms (p95 39.5); cached prediction HTTP
0.87 ms; probability HTTP 2.82 ms. Targets: frame <100 ms p95 MET in the
controlled R7 environment; timeline <1 s MET; cached HTTP <250 ms MET;
frontend <200 ms NOT DIRECTLY MEASURED. Representative values are not
universal guarantees.

**Known debt (carried forward honestly).** Full prediction cache not
generated (~9,644 checkpoints, ~29–30 serial CPU-hours, ~90 MB
estimated); prediction/probability endpoints return 503 `cache_missing`
until artifacts exist; leader-lap client jump ~11 probes typical bounded
by 40; backend `frame_for_leader_lap` ~374 ms and not exposed; frontend
<200 ms not browser-benchmarked; any Monaco-2022 Phase-4 xfails remain;
the legacy `ResultCards.tsx` ESLint warning remains.

**Authorized drift.** The Phase-4 `api/main.py` hash drifted solely from
the additive Phase-5 replay-router include. The old Phase-4 manifest is
NOT altered; the Phase-5 manifest records both identities and the reason.

**Verification.** See `docs/PHASE5_FINAL_REPORT.md` §14 and
`docs/PHASE5_FREEZE_MANIFEST.json` `verification` (freeze seal, all
Phase-5 suites, relevant Phase-4 gates, frontend battery, scientific/data
validator, and the full repository Python suite run exactly once at the
freeze gate). No unexplained failures; no new unexplained xfails; no
scientific freeze conflict.

**R8 readiness.** Phase 5 **FROZEN**. Commit and annotated tag
`v2-historical-replay-phase5` created after all gates. Phase 6 NOT
implemented.


