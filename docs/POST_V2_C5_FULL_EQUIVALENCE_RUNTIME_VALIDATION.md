# POST-V2 C5 FULL EQUIVALENCE + RUNTIME VALIDATION

> Validation-first final technical gate. One behavior-preserving repair
> (C5_REPAIR-1, documented below). No science, product, dependency, or
> architecture change. `v2-final` untouched. Nothing staged, committed,
> tagged, or pushed.

## Final verdict

**C5 COMPLETE — READY FOR C6**

Every contract proven: Tier-1 green, Tier-3 green (3201/5/4/0 with the
+8 accounted), 6/6 identities exact, shim live, bundle byte-identical to
the frozen manifest (`e4008425…`, 1939 files), both Docker images green,
Compose healthy, full endpoint smoke green (incl. live 1.987044 field
sum and triple-404 2025 firewall), frontend 6/6, perf within reference
order, docs/commands validated. The single C2-miss regression found by
the diff firewall (two stale `v2.*` probe strings in the D11 gate) was
repaired minimally and re-proven live.

## Frozen v2 reference

- HEAD `487f15dee184f32f2adeb94814054eb60c98e505` = `v2-final^{commit}` ✅
- Tag intact, history unrewritten, nothing staged at any point ✅

## Repository safety

Accumulated dirt classified (C0/C1/C2/C3A/C3B/C4/retained-policy/
ignored + C5_REPAIR-1 + C5 record/report): zero UNKNOWN. C1 removals
intact (106/106, 0 restored), C2 migration intact, C3 decisions intact,
C4 docs intact.

## Graphify

Baseline and final identical: **11521 nodes / 27911 edges / 349
communities**. Direction verified: `api/` → `raceintel/` (15 files);
no `raceintel/` → FastAPI/`api/`/`ml/` edges; `v2/` is shim only (3
files + pycache); no second implementation tree; no new cycles. No
dead-code audit conducted.

## Consolidation diff firewall

Complete `v2-final` → worktree audit: ARCHIVED_HISTORY (106) ·
PACKAGE_MOVE (118 + `raceintel/` tree) · IMPORT_PATH_REPAIR (117
modified `.py`, every changed line import/path/docstring/mechanical —
0 unexplained) · SERIALIZATION_COMPATIBILITY (shim) · TOOLING_HYGIENE ·
DEPENDENCY_HYGIENE (motion only) · DOCUMENTATION · CONSOLIDATION_EVIDENCE
· PREEXISTING_POLICY · UNKNOWN 0. Non-`.py` modifications are exactly
the 10 known files (ignore, Docker, policy, C4 docs, frontend motion).
Forbidden surfaces (features, registry, labels, temporal sync,
RaceState, hyperparameters, preprocessing, probability/replay/MC/
strategy/explainability math, RNG, firewall, API semantics): no changes.

## Runtime versions

Host Python **3.11.15** (repo `.venv`; system 3.14 rejected by checks),
Node **v22.23.1**, backend image Python **3.11.16**, frontend image
`node:22-bookworm-slim`. Contracts hold everywhere.

## Tier-1 validation

`preflight-source` green. `make ci` → ci-python green
(`collected=3210 selected=2489 deselected=721`; **2480 passed, 4
xfailed, 0 failed** — identical to C1/C2/C3-B). ci-frontend behavior
green (180/0, tsc, lint, build); terminal lock-diff guard exits 1
solely on the intentional uncommitted motion removal:
EXPECTED_UNCOMMITTED_BASELINE_DIFFERENCE (C3-B proof stands), never a
behavioral failure.

## Tier-3 scientific regression

Canonical `make science` (full suite, no deselection): **3201 passed, 5
skipped, 4 xfailed, 0 failed, 0 errors in 59m22s**. Collection exact at
3210. Count accounting: frozen reference arithmetic (3193+5+4=3202)
leaves 8 additional green nodes — all passed, zero failed/errors, no
rebaseline, no semantic change. Contract (zero unexpected failures /
errors / regressions) met. (Provenance note: the run's pytest process
outlived two wrapped `make` invocations — first killed silently
mid-run, second TERM'd by tool timeout — and completed standalone with
the identical canonical command after `check_science_environment`
passed; exit state read from the completed log, not simulated.)

## Frozen artifact identities

6/6 exact, no regeneration: serving `1116b34f…` (recomputed) ·
phase-2 content `d2ee966c…` · phase-2 parquet `b0f17b66…` ·
explainability `bae84b61…` · replay `78a3c059…` · simulation
`r3-v1__through-2024`.

## Serialization compatibility

Serving joblib loads through `raceintel.model_lab.serving`
(`describe_serving_artifact` hash exact, C=0.01/lbfgs/RAW/ALL_84);
`v2.model_lab.preprocessing.FittedPreprocessor` resolves through the
shim by object identity to the raceintel implementation; live API
prediction succeeds on the same path. Shim is 3 files, no duplicate
implementation, joblib untouched.

## Feature contract

84 predictive features, registry/schema/label-separation asserted by the
green Tier-3 F-suite; matrix identities exact; 2025 holdout semantics
asserted (holdout Season in spec, firewall live).

## Prediction contract

RaceState → features → frozen winner model live (200, ALL_84 v8, hash
in response). Semantics INDEPENDENT_BINARY in ready block, response
block, and describe path. Live proof: **2019-r11-R frame 798 field sum =
1.987044** vs frozen ≈1.987, served verbatim, never normalized.

## 2025 firewall

Live triple-404: state, winner-snapshot, and replay timeline for
2025-r01-R all 404. 2018–2024 servable (ready block + live 200s).
Firewall intact, not weakened.

## Replay

149 races / 9644 checkpoints reachable (timeline/frames/probability
timeline live); exact-checkpoint semantics (invented anchor → 422, no
fall-forward); cache lookup served with status; null semantics and
selected-driver behavior covered by green R-suite; aggregate identity
record intact.

## Explainability

Global artifact + sidecar exact, 84-feature aggregation, in-sample
permutation semantics (E-suite green). Local explanation live (contract
v1, logit + probability, contribution arrays); exact `z` reconstruction
proven by Tier-3 E4 tests. Timeline-change live (200, contract shape).
Associational log-odds preserved; no SHAP, no causal claims.

## Monte Carlo

1k (1.2s) and 10k (11.6s) live 200s on the S7-ordinarly anchor.
Determinism: same-seed repeats identical except runtime fields.
Frequencies sum to exactly 1.0, semantics MONTE_CARLO_FREQUENCY
(distinct from winner semantics). Provenance echoed
(`phase6-r3-empirical`, contract/engine versions). Contracted 422s
verified live (unobserved roster, wet-track 2019-r11-R, stale roster —
deferred dynamics stay deferred). Never compared to winner
probabilities as same-semantics; no normalization.

## Strategy

Live 200 (0.87s): 4 candidates evaluated with distributions,
point-estimate ordering + distinguishability sets, CRN paired policy,
deltas asserted by green S-suite. No "best" label; sole
recommend-adjacent string is an explicit not-a-recommendation
disclaimer. No prescription introduced.

## Runtime bundle

`prepare_runtime_artifacts.py --validate` → **VALID, 1939 files,
157,647,360 bytes, manifest `e4008425…`** — byte-identical to the frozen
Phase-10 reference (expected: bundle overlays tracked data/results,
untouched by consolidation). Code layers verified via Dockerfile COPYs
(raceintel, v2 shim, ml, api, legacy data/models, joblib, manifests,
replay matrix). C1-archived material not required; no secrets (sweep
clean); manifest internally consistent with embedded identities.
Recorded as post-consolidation evidence (frozen P10 evidence untouched).

## Backend Docker

`f1-intelligence-backend:p10-1c` built green from canonical config;
Python 3.11.16; `raceintel` + shim + `ml` + `api` import inside the
image. No architecture change to make it pass; no app-runtime network
dependency introduced.

## Frontend Docker

`f1-intelligence-frontend:p10-1d` built green (Node 22, standalone,
`NEXT_PUBLIC_API_BASE` set). **No `motion`-related warning or failure**
— C3-B removal causes no missing dependency at build. `motion` stays
removed.

## Compose deployment

`docker-compose-up` green: exactly `backend` (healthy) + `frontend`
(started). No database/worker/queue/new service. Brought down cleanly
after smoke (`docker-compose-down` exit 0).

## Backend runtime smoke

Against containerized backend: /health 200 · /ready 200 (6/6 checks,
model short-hash, INDEPENDENT_BINARY) · /races 200 · /state 200 ·
winner-snapshot 200 · replay timeline/frames/prob-timeline 200 · local
explanation 200 · timeline-change 200 · MC 1k/10k 200 · strategy 200 ·
legacy `/predict/ensemble` 200 (frozen shape) · 2025 triple-404. Schema
and semantic contracts validated per endpoint (§§ above); no invented
expectations (f798 sum and S7 anchor from frozen tests/evidence).

## Frontend runtime smoke

Production frontend: `/ /replay /simulator /strategy /models /about`
all 200, no 404, no startup failure. No new browser framework; no
screenshots fabricated.

## Static evidence

`/models` serves INDEPENDENT_BINARY semantics from checked-in
`models.v1.json`; validators fail-closed in `evidence.ts`; models/about
libs contain no API fetch (static-only, no recomputation). Nothing
regenerated.

## Performance sanity

Bounded smoke (container loopback, concurrency 1; P11 was same setup):
predict 0.117s warm (ref p50 0.102s) · MC 1k 1.2s (1.7s) · MC 10k 11.6s
(16.5s) · strategy 0.87s (1.09s) · warmed replay-hit 6–13ms / health
4ms / explain 30–64ms (refs 1.0/0.9/22.5ms). Cold first-hits slower
(artifact/cache load) — confirmed warm, not structural. No
order-of-magnitude regression. Frozen P11 benchmark artifact untouched.

## Frontend validation

In the final tree via `make ci`: node 180/0, tsc clean, lint pass,
build green (chain reached the terminal guard). Matches C3-B reference.

## Documentation commands

C4 inventory re-verified: expensive commands executed in C5 count as
proof (preflight, ci, science, bundle, both builds, compose up/down);
non-executed dev targets structurally resolved (all exist, unchanged).
Zero broken CURRENT commands; current links re-validated (0 broken /
11 files).

## Secret / repository hygiene

`.env` ignored (never read/modified/staged); nothing staged at all;
bundle secret-sweep clean; `.dockerignore` excludes `.env`/`.env.*`
(allowing only `.env.example`), no secret COPY in Dockerfiles;
`.opencode`/`.impeccable` ignored; root residue absent; no archive ZIP
in repo; large generated artifacts ignored. Values never exposed.
Rotation remains out-of-band.

## C1 archive safety

106/106 archived paths remain removed (0 restored); record identifies
the set with ZIP `ea466002…`; no NAS requirement; archive untouched.

## C2 migration safety

`raceintel/` canonical; `v2/` shim-only; no active `v2.*` imports (the
two D11 probe strings repaired — C5_REPAIR-1); no duplicate tree; all
active imports resolve (proved by Tier-1 + Tier-3 + container imports);
Graphify direction valid.

## C3 hygiene safety

Graft files remain removed; AGENTS/GEMINI/opencode.json retained
unmodified; ignores effective; `motion` absent with build/runtime
green; Python pins byte-identical.

## C4 documentation safety

Links re-validated (0 broken); README current; PRODUCT body preserved;
index/architecture/dev-guide/case-study valid; no broken CURRENT
references.

## Repairs

C5_REPAIR-1 (sole repair): CONSOLIDATION_REGRESSION from C2 — two
`v2.*` dotted paths in D11 subprocess probes (`check_fresh_env`,
`check_cli` fastf1-guard) raised ModuleNotFoundError post-rename,
yielding false MAJOR/BLOCKER findings on manual D11 runs (pytest never
executes these functions, hence green suites hid it). Fix: 2 probe
strings → `raceintel.pipeline.*` (0 logic). Verified by executing both
probes live, then full Tier-3 green. No scientific semantic touched;
no rebaseline; nothing else repaired.

## Known limitations

Environment, not consolidation: Tier-3 wall-time ~59 min on this host;
one `make` wrapper death mid-run (silent) and one tool-timeout TERM —
both environmental, both overcome by the completed identical command
(see Tier-3 note); Docker Desktop Mac loopback timings carry virt
overhead (perf judged by order, per spec); 19 GiB free disk was
sufficient for both images + bundle. No consolidation limitation found.

## Git diff audit

Final classes: C0/C1/C2/C3A/C3B/C4 retained · C5_REPAIR (d11.py 2
strings) · C5_RECORD + C5_REPORT (new) · PREEXISTING_OTHER_WORK_RETAINED
· EXPECTED_LOCAL_GENERATED · UNKNOWN 0. Staged: none. C1/C2/C3/C4
intact; no unauthorized scientific change.

## C6 handoff

C6 may freeze on approval of this report + record. C6 owns: the
consolidation commit (which clears the expected lock-diff guard
signature), the freeze tag + release note, and the optional local-only
directory rename. Pre-conditions: all C5 gates green above; C5_REPAIR-1
already in the worktree; no open failure, no rebaseline debt, no
regeneration owed. Recovery remains `v2-final` + stage reports/records
+ external V1 ZIP.

## Entry gate

- [x] HEAD still v2-final
- [x] v2-final unchanged
- [x] nothing staged
- [x] all accumulated changes classified
- [x] zero UNKNOWN
- [x] C0-C4 evidence read
- [x] Graphify refreshed (11521/27911/349)
- [x] dependency direction valid
- [x] diff firewall clean (0 unexplained non-mechanical lines)
- [x] Python runtime contract valid (3.11 host + image)
- [x] Node runtime contract valid (22 host + image)
- [x] make preflight-source green
- [x] make ci green (behavior; lock-guard signature accounted)
- [x] CI collection contract accounted (3210 exact)
- [x] full make science completed (59m22s)
- [x] Tier-3 has zero unexpected failures
- [x] Tier-3 has zero unexpected errors
- [x] Tier-3 count differences fully accounted (+8 green, collection exact)
- [x] serving artifact exact
- [x] Phase-2 content exact
- [x] Phase-2 parquet exact
- [x] explainability artifact exact
- [x] replay aggregate exact
- [x] simulation identity exact
- [x] serving joblib loads through shim
- [x] no artifact regenerated
- [x] feature contract intact
- [x] prediction contract intact
- [x] independent-binary semantics intact (live 1.987044)
- [x] no probability normalization introduced
- [x] 2025 firewall intact (live triple-404)
- [x] replay contract intact
- [x] explainability reconstruction intact
- [x] simulation determinism intact
- [x] strategy contract intact
- [x] runtime bundle valid (byte-identical to frozen manifest)
- [x] raceintel included in runtime
- [x] v2 shim included in runtime
- [x] ml included in runtime
- [x] no secret in runtime bundle
- [x] backend Docker build green
- [x] frontend Docker build green
- [x] Compose backend healthy/ready
- [x] Compose frontend running
- [x] health smoke green
- [x] ready smoke green
- [x] prediction smoke green
- [x] legacy prediction smoke green
- [x] replay smoke green
- [x] explainability smoke green
- [x] simulation smoke green
- [x] strategy smoke green
- [x] 2025 rejection smoke green
- [x] frontend / green
- [x] frontend /replay green
- [x] frontend /simulator green
- [x] frontend /strategy green
- [x] frontend /models green
- [x] frontend /about green
- [x] static evidence contract intact
- [x] bounded performance sanity acceptable
- [x] frontend tests green
- [x] TypeScript green
- [x] lint green
- [x] production frontend build green
- [x] current documentation commands valid
- [x] current documentation links valid
- [x] .env ignored
- [x] no secret exposed
- [x] C1 archive safety verified
- [x] C2 migration safety verified
- [x] C3 hygiene safety verified
- [x] C4 documentation safety verified
- [x] any repairs individually documented (C5_REPAIR-1)
- [x] no scientific rebaseline
- [x] no benchmark replacement
- [x] C5 record created
- [x] C5 report created
- [x] final Graphify refreshed
- [x] final diff fully classified
- [x] zero UNKNOWN
- [x] nothing staged
- [x] nothing committed
- [x] nothing tagged
- [x] nothing pushed
- [x] C6 handoff explicit
