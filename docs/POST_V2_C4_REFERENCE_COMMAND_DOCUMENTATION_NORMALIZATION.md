# POST-V2 C4 REFERENCE / COMMAND / DOCUMENTATION NORMALIZATION

> Documentation/reference/developer-experience stage only. No source,
> script, test, dependency, artifact, API-contract, or Makefile change.
> `v2-final` untouched. Nothing staged, committed, tagged, or pushed.

## Final verdict

**C4 COMPLETE — READY FOR C5**

Current documentation now describes the consolidated repository:
`raceintel/` as implementation, `/v2/` as API contract, `v2/` as shim,
`ml/` as frozen serving compatibility. Two stale current references
repaired (README architecture map + Tier-1 numbers; PRODUCT.md note),
three navigation documents created, zero broken current links, all
commands structurally resolved, Makefile fully canonical, all 14 scripts
kept in place by explicit decision.

## Frozen v2 reference

- `git rev-parse HEAD` → `487f15dee184f32f2adeb94814054eb60c98e505` ✅
- `git rev-parse v2-final^{commit}` → same ✅
- `git tag --points-at HEAD` → `v2-final` ✅
- Nothing staged before, during, or after ✅

## Repository safety

Pre-mutation dirt (367 paths: 235 `D`, 125 `M`, 7 `??`) classified: C0
report · C1 (106 removals intact + report + record) · C2 (118 `v2/` moves
+ `raceintel/` + import repairs + report + record) · C3A report · C3B
(tooling disposition, ignore entries, motion removal, record + report) ·
PREEXISTING_OTHER_WORK_RETAINED (policy-file mods) ·
EXPECTED_LOCAL_GENERATED (ignored) · UNKNOWN none. C1/C2/C3-B decisions
all preserved; zero UNKNOWN before mutation.

## Graphify snapshot

- Baseline: **11458 nodes / 27772 edges / 345 communities** (recorded
  `27815 edges` in the live log line; snapshot table uses the post-C3-B
  graph state before C4 doc edits).
- Graphify used only to confirm shim/dependency relationships inherited
  from C3-A; no dead-code audit conducted.

## Current-vs-historical classification

Model applied to every candidate reference (Part C):

- CURRENT_OPERATIONAL / CURRENT_ARCHITECTURE: README guide + Tier
  numbers, data/README commands, Makefile, DEVELOPMENT.md, new
  architecture doc — normalized to the consolidated tree.
- PUBLIC_CONTRACT: `/v2/...` routes, `frontend/lib/v2.ts`, `api/v2_*`
  module names — unchanged by rule.
- HISTORICAL_PROVENANCE / FROZEN_EVIDENCE: all phase reports, ADRs,
  freeze manifests/contracts, case-study `v2/` namespace, P11 numbers,
  `frontend/data/*.v1.json`, d10/provenance strings — untouched.
- ARCHIVED_REFERENCE: none needed in current docs (zero hits).
- STALE_CURRENT_REFERENCE: exactly 3 repaired (§ README, § PRODUCT /
  case study). No global `v2` replacement performed anywhere.

## Current architecture

Canonical package is `raceintel/` with the C2 subpackage layout
(`data/`, `pipeline/`, `features/`, `labels/`, `race_state/`, `replay/`,
`simulation/`, `strategy/`, `explainability/`, `model_lab/`,
`experiments/` — all verified to exist). Documented in README
Repository Guide and fully in
`docs/architecture/CURRENT_ARCHITECTURE.md`: layers, one-way `api/` →
`raceintel/` direction, legacy compatibility (`ml/`, `v2/` shim,
legacy data/models), artifact/runtime and scientific-data boundaries,
Tier 1/2/3. `v2/` is never presented as implementation.

## README

Audited, not rewritten. Portfolio value, metrics, limitations, and
future-work framing preserved. Two surgical fixes:

1. Repository Guide: `v2/` bullet replaced (shim truth + removal
   condition), `raceintel/` bullet added with all subpackages, `ml/`
   reframed as frozen serving compatibility, `api/` bullet clarifies
   contract-vs-implementation, `docs/` bullet points at the new index.
2. Tier-1 outcome corrected from stale `1971 passed / 501 skipped` to
   `make ci` reality (`2480 passed / 4 xfailed`, 2,489 of 3,210
   selected). Tier-3 P11 numbers (3193/5/4) kept — frozen evidence with
   provenance (`PHASE11_P11_7_FINAL_V2_FREEZE.md`).

All README commands structurally validated (`make` targets, scripts,
routers, compose services).

## PRODUCT / case study

- `PRODUCT.md`: body frozen (declared pre-Phase-7 sketch); the C4 change
  extends its historical note to name the Phase-7-status and `motion`
  stalenesses explicitly, with the current stack stated in the note.
  No prose rewritten, no numbers altered.
- `docs/case-study/`: no stale module/command/dependency references
  found (`python -m v2`, `from v2.`, `motion`-as-dep all absent); its
  `v2/` namespace is correct-at-write-time provenance — preserved.
- Current architecture/developer docs (`data/README.md`, Makefile,
  compose, Docker docs): already current; verified, untouched.

## Archived V1 references

Swept current docs/commands (README, PRODUCT, data/README, Makefile,
Compose, AGENTS/GEMINI, case-study, frontend app/features/lib) for all
106 C1-archived path families: **zero hits** — no BROKEN_CURRENT_REFERENCE,
no CURRENT_REQUIRED_REFERENCE blocker. C1's conclusion holds. Remaining
mentions live only in frozen phase-history docs and provenance strings
(HISTORICAL_ONLY / PROVENANCE_STRING, intentionally kept).

## Canonical commands

Established from existing Makefile targets (no duplicates created):
bootstrap (`install-python-test` + `install-frontend`), backend dev/prod,
frontend dev, source-safe validation (`make ci`), frontend validation
(`ci-frontend`), Tier-3 (`make science`), bundle prep
(`prepare_runtime_artifacts.py --validate`), Docker/Compose up/down,
replay-cache / sim-params / P9-evidence generators. Recorded in the C4
record and `docs/development/DEVELOPMENT.md`.

## Makefile audit

All 27 targets classified: 26 CANONICAL + `check-python`
INTERNAL_HELPER. Zero STALE (notably `backend-dev --reload-dir ml`
still valid; frontend/container/compose/CI/science targets all resolve).
**Makefile left untouched** — no repair needed, no redesign permitted.

## Script inventory

All 14 surviving scripts enumerated in the C4 record (path,
responsibility, invoked_by, references, developer-facing, canonical).
Decision for every script: **KEEP_CURRENT_PATH** — names and
responsibilities are clear; moving would churn CI/Makefile/tests/freeze
manifests/provenance for cosmetic gain (C2's deferral re-confirmed).
No `MOVE_IN_C4`, no `DEFER` left open.

## Test tiers

Layout frozen (`tests/` untouched). Documented accurately against
`Makefile` + selector scripts: Tier 1 source-safe CI (`make ci`,
3210-collected selectors), Tier 2 deployable/runtime (`preflight`,
Docker/Compose, readiness, smoke), Tier 3 full regression
(`make science`, corpus-required, no deselection). Tier-1-green ≠ Tier-3
stated in README, architecture doc, and dev guide alike.

## API documentation

`/health`, `/ready`, legacy routes, and `/v2/...` preserved; no rename.
Current docs now state the contract-vs-implementation distinction
explicitly (`/v2/` API version ≠ `raceintel/` package). Route set
verified against routers (`/races/{id}/state(s)`,
`/predictions/winner-snapshot`, `unknown_race` guard present).

## Serialization shim

`docs/architecture/CURRENT_ARCHITECTURE.md` + README guide explain the
`v2/` shim briefly (frozen joblib embeds
`v2.model_lab.preprocessing.FittedPreprocessor`; removal condition
stated). Portfolio material does not overemphasize it. Shim untouched,
artifact not regenerated.

## Legacy ml compatibility

Current docs describe `ml/` as frozen legacy serving compatibility
required by product + regression contracts (README guide, architecture
doc). No implication of disuse; no migration; no merge into `raceintel/`.

## Naming audit

- Directory name `f1-in-race-prediction`: HISTORICAL_OK at freeze;
  rename is C6 local-only — not performed.
- "Winner prediction" wording: CURRENT_OK where it names the live
  Predict surface; HISTORICAL_OK in the case-study origin story.
- Stale `v2/`-as-implementation wording: exactly one CURRENT instance
  (README guide) — repaired. Remainder is frozen-provenance — kept.
- No broad artifact/data renames. No RENAME_FUTURE beyond the C6
  directory note.

## Documentation architecture

Decision explicit: **no physical hierarchy migration**. Moving ~100
frozen reports into `architecture/`, `history/`, etc. would churn
provenance paths for navigation gain achievable by index. Outcome:
historical files stay; new `docs/README.md` index + two focused current
docs (`architecture/`, `development/` subdirs contain ONLY new current
material, no moved history).

## Docs index

`docs/README.md` created: Getting Started, Architecture, Scientific
Methodology, Evaluation, Simulation/Strategy, Case Study,
Deployment/Runtime, Historical Phase Reports, Post-v2 Consolidation,
Release Evidence — every entry an existing file (link-validated).

## Developer guide

`docs/development/DEVELOPMENT.md` created: versions, bootstrap,
dev servers, validation, bundle + Docker/Compose, regeneration
utilities, generated-artifact boundaries, Graphify-first navigation.
Operational, not a README duplicate (README stays product/portfolio).

## Link validation

Relative-link sweep over README, PRODUCT, new docs, and all case-study
pages: **0 broken CURRENT links** (10 files checked). Historical textual
mentions of archived paths are prose, not hyperlinks — differentiated,
not counted.

## Path / command validation

All 18 documented `make` targets exist; `raceintel` modules referenced
in commands exist; `backend`/`frontend` compose services exist; API
routes in README examples resolve in routers. 0 unresolved. Expensive
execution deferred to C5 (structural resolution only, per spec).

## Tooling references

Current docs contain zero graft-era operational instructions
(`rg graft` over README/PRODUCT/AGENTS/GEMINI/Makefile/case-study/
frontend/data-readme: empty). No `.opencode/`/`.impeccable/` contents
advertised as requirements (dev guide states they are ignored
local-only). `motion` appears in current docs only inside PRODUCT.md's
removal-framing note and as the `prefers-reduced-motion` CSS feature —
never as a current dependency.

## Scientific firewall

No scientific source changes: zero edits under `raceintel/`, `api/`,
`ml/`, `v2/`, `tests/`, `scripts/`, `frontend/`, `requirements*.txt`,
`frontend/package*.json`, Docker/CI config. Only `.md` prose (README,
PRODUCT note) and three new navigation docs. No dependency changes. No
C5/C6 blocker encountered — nothing to escalate.

## Validation

- `make preflight-source`: **green** (repo 3.11 venv).
- Documentation/link/path/command validation: green (0 broken, 0
  unresolved, Makefile fully canonical).
- No `make ci` (nothing executable changed — C4 is prose + new docs;
  C3-B's `make ci` evidence stands for the unchanged tree).
- No Tier-3, no Docker rebuild (C5-owned).

## Scientific identities

All six exact, no regeneration: serving `1116b34f…` (recomputed) ·
phase-2 content `d2ee966c…` (manifest `matrix.content_hash`) · phase-2
parquet `b0f17b66…` (manifest `matrix.parquet_sha256`) · explainability
`bae84b61…` (sidecar) · replay `78a3c059…` (phase-8 manifest) ·
simulation `r3-v1__through-2024` (params dir present).

## Git diff audit

C4-owned changes: `README.md` M + `PRODUCT.md` M (C4_DOC/C4_REFERENCE) +
`docs/README.md`, `docs/architecture/CURRENT_ARCHITECTURE.md`,
`docs/development/DEVELOPMENT.md` (C4_DOC) + C4 record + this report
(C4_RECORD/C4_REPORT). Everything else retains its C0/C1/C2/C3A/C3B/
PREEXISTING_OTHER_WORK_RETAINED/EXPECTED_LOCAL_GENERATED class. Zero
UNKNOWN. C1 removals intact, C2 migration intact, C3-B decisions intact,
no source/science changes, nothing staged.

## Deferred work

C5 (regression/runtime/Docker/smoke) · C6 (freeze commit, incl. local-only
directory rename) · rejected-with-reason (docs hierarchy move, script
moves) · retained uncertains (DESIGN.md, empty dirs, tabulate) ·
out-of-band credential rotation. Full list in the C4 record.

## C5 handoff

C5 may start on approval of this report + record. C5 owns: `make verify`,
`make science` (Tier-3, corpus-gated), Docker backend+frontend builds,
Compose smoke, `prepare_runtime_artifacts --validate`, benchmark parity
vs `results/v2_final_validation/`. C4 hands over a tree whose current
docs match its layout, with structural command resolution pre-verified
and all behavior gates from C3-B still standing (nothing executable
changed since).

## Entry gate

- [x] HEAD still v2-final
- [x] v2-final unchanged
- [x] nothing staged
- [x] accumulated dirt classified
- [x] zero UNKNOWN
- [x] C0-C3 evidence read
- [x] Graphify refreshed (11458/27815/345)
- [x] current/historical references distinguished
- [x] no global v2 replacement
- [x] raceintel documented as current implementation
- [x] /v2 API documented as public contract
- [x] v2 shim documented correctly
- [x] ml legacy compatibility documented correctly
- [x] README current
- [x] no future v3 features presented as implemented
- [x] frozen metrics unchanged
- [x] PRODUCT/case-study current references checked
- [x] historical reports not rewritten
- [x] C1 archived references classified (zero current hits)
- [x] zero broken CURRENT references
- [x] canonical commands established
- [x] Makefile targets audited (26 CANONICAL + 1 helper, untouched)
- [x] 14 surviving scripts inventoried
- [x] script move/keep decisions explicit (14/14 KEEP_CURRENT_PATH)
- [x] tests not moved
- [x] validation tiers documented accurately
- [x] API docs current
- [x] naming audit complete
- [x] docs physical-move decision explicit (index-first, no migration)
- [x] docs navigation clear (index + architecture + dev guide)
- [x] current architecture doc present if needed (created)
- [x] developer guide present if needed (created)
- [x] CURRENT relative links green (0 broken / 10 files)
- [x] CURRENT command paths green (0 unresolved)
- [x] stale Graft operational instructions removed (zero found)
- [x] motion not documented as current dependency
- [x] no scientific source changes
- [x] no dependency changes
- [x] make preflight-source green
- [x] expensive validation deferred to C5
- [x] six scientific identities exact
- [x] no artifact regeneration
- [x] C4 record created
- [x] C4 report created
- [x] final diff classified
- [x] zero UNKNOWN
- [x] nothing staged
- [x] nothing committed
- [x] nothing tagged
- [x] nothing pushed
- [x] C5 handoff explicit
