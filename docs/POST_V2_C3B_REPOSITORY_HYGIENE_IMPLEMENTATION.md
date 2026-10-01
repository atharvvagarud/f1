# POST-V2 C3-B REPOSITORY HYGIENE IMPLEMENTATION

> Only the C3-A-justified hygiene actions were implemented. No source,
> script, test, Python-dependency, artifact, or API-contract change.
> `v2-final` untouched. Nothing staged, committed, tagged, or pushed.

## Final verdict

**C3-B COMPLETE — READY FOR C4**

C3-B was intentionally small and stayed small: graft-era tracked tooling
dispositioned (11 files, already absent in the worktree), local tool
state ignored (2 `.gitignore` entries), root shadcn-stub residue
removed locally (2 files), and the proven-unused `motion` frontend dep
removed via `npm rm` with full frontend validation green. All retain
sets, firewalls, identities, and pins hold.

One honest accounting note (not a behavior failure): the terminal
`git diff --exit-code -- package-lock.json` guard inside `make
ci-frontend` exits 1 because the intentional `motion` removal is
uncommitted — C0–C3 are uncommitted by design and C6 owns the freeze
commit. Every behavior gate beneath that guard is green, twice
(standalone + full `make ci`). Detail in § Validation.

## Frozen v2 reference

- `git rev-parse HEAD` → `487f15dee184f32f2adeb94814054eb60c98e505` ✅
- `git rev-parse v2-final^{commit}` → same ✅
- `git tag --points-at HEAD` → `v2-final` ✅
- Tag unmoved, history unrewritten, `git diff --cached --stat` empty
  throughout (nothing staged before, during, or after) ✅

## Repository safety

Pre-mutation classification (367 dirty paths: 235 `D`, 122 `M`,
10 `??`; staged: none):

| Worktree dirt | Category |
|---|---|
| 11× `D` graft-era tooling | PREEXISTING_OTHER_WORK → C3B_TOOLING (dispositioned, § Graft-era tooling) |
| 3× `M` (`AGENTS.md`, `GEMINI.md`, `opencode.json`) + 4× `??` (`.impeccable/`, `.opencode/`, root `package.json`/`package-lock.json`) | PREEXISTING_OTHER_WORK → policy files ratified (§ Current policy files); local/tooling residue resolved (§ Local tool state, § Root package files) |
| `?? docs/POST_V2_C0_…` | C0 |
| 106× `D` + `?? docs/POST_V2_C1_…` + `results/post_v2_consolidation/` (C1 record) | C1 (removals verified intact, never restored) |
| 118× `D` under `v2/` + `?? raceintel/` + ~117× `M` import/path repairs + `?? docs/POST_V2_C2_…` + C2 record | C2 (migration intact) |
| `?? docs/POST_V2_C3A_…` | C3A |
| Ignored caches/bundles/venvs | EXPECTED_LOCAL_GENERATED |
| UNKNOWN | **none — zero-UNKNOWN gate met before mutation** |

C1 removals remain removed (235 `D` = 106 C1 + 118 C2 + 11 graft-era,
exact). C2 `raceintel/` migration intact.

## Graphify snapshot

- Baseline (Part B, before mutation): **11447 nodes / 27804 edges /
  334 communities**.
- Final (Part S, after all mutations): **11435 nodes / 27793 edges /
  318 communities** (delta is community relabeling + the motion-removal
  lockfile churn; no source-shape change).
- No broad dead-code hunt performed — C3-A owns that audit.

## Protected retain set

Enforced untouched (verified via `git diff --name-status` scoping, § Git
diff audit): `v2/` shim (3 files) · `ml/` · full `api/` serving stacks
(legacy + `/v2/*`, public paths byte-identical) · `raceintel/` ·
all 14 surviving scripts + `ci_corpus_dependent.txt` · all tests ·
`DESIGN.md` · `data/sequences/` + `data/models/` · `tabulate` and all 45
Python pins (`requirements*.txt` byte-identical) · serving joblib,
freeze manifests, fixtures, case-study/release evidence · C1/C2 records.

## Graft-era tooling

Expected candidates were NOT used as authority. Exact tracked-at-v2-final
set enumerated via `git ls-tree v2-final` (11 files):

`.claude/helpers/graft-hooks.cjs`, `.claude/helpers/graft-statusline.cjs`,
`.claude/settings.json`, `.claude/skills/graft/SKILL.md`,
`.cursor/hooks.json`, `.cursor/hooks/graft-hooks.cjs`, `.cursor/mcp.json`,
`.cursor/rules/graft.mdc`, `.gemini/settings.json`, `.mcp.json`, `.ignore`.

Per-file verdict — all 11 **REMOVE_TRACKED_TOOLING**:

1. Tracked at v2-final: yes (all 11).
2. Worktree state: already deleted (pre-C3-B), untouched by C3-B.
3. Graft-era: exclusively — Claude hooks/skill, Cursor hooks/MCP/rule,
   Gemini/MCP `graft mcp` servers, ripgrep `!graft/` re-admit.
4. Active refs: zero (`rg graft` over Makefile, Compose, Dockerfiles, CI,
   frontend, policy files: empty; `graft/` index dir absent in repo).
5. Superseded: yes, by the Graphify-first workflow in `AGENTS.md`.
6. Surviving contracts: none (workflow prose + hook commands only; one
   file embeds a user-machine absolute path, confirming local residue).

Disposition implemented: deletions accepted (no restore); recorded in
`results/post_v2_consolidation/c3_hygiene_record.json`. The C6 freeze
commit will record the removal. No UNCERTAIN items.

## Current policy files

`AGENTS.md`, `GEMINI.md`, `opencode.json` — all **KEEP_TRACKED_CURRENT_VERSION**,
no edits:

- Content: F1 long-command execution policy + graphify rules + headroom
  wrapper policy (AGENTS.md); same execution policy (GEMINI.md);
  shadcn + playwright MCP entries (opencode.json).
- Hygiene screen: zero stale graft references, valid tool names, no
  machine-specific paths, no secrets, no obsolete provider config.
- No graft-specific configuration remains in them, so the permitted
  minimal-edit clause was not triggered. No useful policy discarded.

## Local tool state

- `.opencode/` (61M: node_modules + plugins + own manifests) — active
  opencode plugin runtime env → **KEEP_LOCAL_IGNORED** (directory kept;
  destruction would break local tooling for zero repo benefit).
- `.impeccable/` (20K: `config.local.json`, `design.json`) — design-skill
  local tokens → **KEEP_LOCAL_IGNORED**.
- Both were untracked+unignored; now covered by narrow `.gitignore`
  entries (no broad patterns). Verified: neither appears in `git status`
  after the ignore change.

## Root package files

Investigation: root `package.json` held only `{devDependencies:
{shadcn: ^4.21.0}}` with a 148K lockfile named for this directory
(tooling-created stub). No `components.json` anywhere; zero invokers in
Makefile/scripts/tests/CI/Docker; frontend uses only
`frontend/package.json`; `opencode.json`'s shadcn MCP runs
`npx shadcn@latest` (needs no local stub). Not confused with the
protected `frontend/package*.json`.

Classification: **REMOVE_LOCAL_RESIDUE** — both files deleted locally
with explicit `rm` (untracked; no git operation). Nothing in the repo
can reference them (verified by invoker sweep).

## Frontend motion investigation

Final classification: **REMOVED_CONFIRMED_UNUSED** (proof-complete,
behavior-compared, no restore needed).

- Source/config/scripts/tests: zero `motion` imports across
  `.ts/.tsx/.css/.json`; zero dynamic `import()`/`require()`; no
  `next.config.ts` reference; only `package.json`/lockfile plus
  `prefers-reduced-motion` CSS substring noise.
- Lockfile graph: zero exact reverse dependents of `node_modules/motion`
  (`framer-motion` needs only `motion-dom`/`motion-utils`/`tslib`); top
  level listed it as a direct dep only.
- Baseline: `frontend/` pristine since C2 (empty git dirt), so C2's
  green `ci-frontend` is reused as explicitly identified baseline
  evidence (per fast-gates/don't-rerun-unchanged-gates policy).
- Removal: `npm rm motion` from `frontend/` (proper package-manager op,
  no manual lockfile edit) — 4 packages gone (`motion`,
  `framer-motion`, `motion-dom`, `motion-utils`); `package.json` −1
  line; lockfile removal-only (69 deletions, brace-reflow additions).
- Post-removal proof: standalone frontend validation green — node tests
  180 pass/0 fail (collected=17 selected=16 deselected=1), `tsc --noEmit`
  clean, `npm run lint` pass, `next build` green with static prerender.

## Python dependencies

No change. `requirements.txt` / `requirements-test.txt` byte-identical;
no pruning tools run; `tabulate` retained per C3-A closure-pin evidence.
C3-A's zero-removable-pins conclusion was not reopened (no new evidence).

## Generated/cache hygiene

`.gitignore` reviewed against C3-A: all large local material
(`graphify-out/`, `.venv/`, `runtime_artifacts/`, `frontend/.next`,
`frontend/node_modules/`, `data/v2/`, FastF1/raw caches,
`__pycache__/`, `.pytest_cache/`) already covered — no duplicates added.
Only the confirmed gaps were closed with two narrow, documented entries:
`.opencode/` and `.impeccable/`. Explicitly NOT ignored: `raceintel/`,
`v2/`, `results/post_v2_consolidation/`, reports, tracked evidence.

## Secret hygiene

`LIVE_IGNORED_CREDENTIAL_PRESENT = true`; `.env` (78 bytes) present,
still ignored (`.gitignore:13`), never read, printed, modified, staged,
archived, or copied. Rotation remains a USER out-of-band action.

## Source-code firewall

Zero source deletions: no file touched under `raceintel/`, `api/`,
`ml/`, `v2/` (beyond pre-existing C2 import repairs). No YAGNI
refactoring, deduplication, model-lab simplification, route cleanup, or
shim removal. C3-A's 0-candidate result respected, not re-litigated.

## Script/test firewall

All 14 surviving scripts + `ci_corpus_dependent.txt` retained at
unchanged paths. No test moved/renamed; pytest node IDs and the 3210
collection pin preserved (proven by `make ci` output, § Validation).
No new tests added (none required for these hygiene actions).

## Validation

Proportional + complete (repo 3.11 venv; system python3 is 3.14 and
correctly rejected throughout):

- `make preflight-source`: **pass** (pre- and post-change shape).
- `make ci` → `ci-python`: **pass** — `collected=3210 selected=2489
  deselected=721`, **2480 passed, 4 xfailed, 0 failed** (pin + outcome
  identical to C1/C2). No Tier-3 (C5-owned). No Docker rebuild (nothing
  in the container-construction closure changed: no source/dep/Docker
  edits; the only dep change is frontend-scoped and proven by build).
- `ci-frontend` behavior: **green** — `npm ci` ok, node 180 pass/0 fail,
  tsc clean, lint pass, `next build` green (verified in BOTH the
  standalone post-removal run and the full `make ci` run, whose `&&`
  chain reached the terminal guard).
- Terminal-guard accounting: `git diff --exit-code -- package-lock.json`
  exits 1 **solely** on the intentional uncommitted motion-removal diff
  (removal-only proof in the C3-B record). This guard compares worktree
  vs index, so it cannot pass for any dependency change until the C6
  freeze commit — an expected signature of the uncommitted-stages
  policy (Part P), not a behavior regression. Literal `make ci` exit
  code is therefore 1 for exactly this documented reason.

## Scientific identities

All six exact, no regeneration:

- serving `1116b34f…` — recomputed sha256 of the joblib ✅
- phase-2 content `d2ee966c…` — manifest record, git-pristine ✅
- phase-2 parquet `b0f17b66…` — manifest records (phase2 + phase8 + phase9), git-pristine ✅
- explainability `bae84b61…` — sidecar `.sha256` file ✅
- replay `78a3c059…` — phase8 freeze/validation manifests + P11 doc ✅
- simulation `r3-v1__through-2024` — params dir present with generator provenance ✅

## Git diff audit

Final dirty-path classification (staged: none; UNKNOWN: none):

| Paths | Class |
|---|---|
| 11 graft-era `D` (accepted) | C3B_TOOLING |
| `.gitignore` `M` (+2 entries) | C3B_IGNORE |
| `frontend/package.json` + `package-lock.json` `M` (motion removal) | C3B_DEPENDENCY |
| `docs/POST_V2_C3B_…` (this file) | C3B_REPORT |
| `results/post_v2_consolidation/c3_hygiene_record.json` | C3B_RECORD |
| Root `package.json`/`package-lock.json` gone; `.opencode/`+`.impeccable/` no longer listed | C3B (residue removed / ignored) |
| 106 C1 `D`, C0/C1/C2/C3A reports + records, 118 C2 `v2/` `D`, `?? raceintel/`, C2 `M` set, 3 policy `M` | C0 / C1 / C2 / C3A / PREEXISTING_OTHER_WORK_RETAINED |
| Caches/venvs/bundles/corpus | EXPECTED_LOCAL_GENERATED |

Transitions recorded: the 11 graft-era paths moved
PREEXISTING_OTHER_WORK → C3B_TOOLING (dispositioned, still uncommitted
until C6); `.opencode/`/`.impeccable/`/root-package paths moved
PREEXISTING_OTHER_WORK → resolved (ignored/removed).

## Deferred work

C3-B proposes nothing beyond its matrix. Carried forward: C4
normalization (references/commands/docs) · C5 full regression + Tier-3 +
Docker builds · C6 freeze commit (clears the lock-diff guard signature) ·
`DESIGN.md`, empty placeholder dirs, `tabulate` pin (retained uncertains,
owner/proof-gated) · out-of-band credential rotation.

## C4 handoff

C4 may start on approval of this report + record. Inputs: C0/C1/C2/C3-A
reports, C1/C2/C3-B records. C4 scope: reference/command/docs
normalization only — no moves/deletes beyond what C3-B already did, no
dep changes, no science changes. Pre-conditions met: tooling noise
classified + ignored, graft-era disposition explicit, motion proof
closed, retain sets intact, identities exact, collection pin 3210.

## Entry gate

- [x] HEAD still v2-final
- [x] v2-final unchanged
- [x] nothing staged
- [x] C0/C1/C2/C3A evidence read
- [x] all dirty paths classified before mutation
- [x] zero UNKNOWN
- [x] Graphify baseline recorded (11447/27804/334)
- [x] C3-A protected retain set enforced
- [x] no source dead-code deletion
- [x] no Python dependency removal
- [x] pickle shim untouched
- [x] ml/ untouched
- [x] legacy API stack untouched
- [x] raceintel scientific behavior untouched
- [x] all 14 surviving scripts retained
- [x] test paths retained
- [x] obsolete tracked Graft-era files individually resolved (11/11 REMOVE_TRACKED_TOOLING)
- [x] current AGENTS/GEMINI/opencode policy files resolved (KEEP_TRACKED_CURRENT_VERSION, no edits needed)
- [x] no useful current policy accidentally discarded
- [x] .opencode disposition resolved (KEEP_LOCAL_IGNORED)
- [x] .impeccable disposition resolved (KEEP_LOCAL_IGNORED)
- [x] .gitignore gaps repaired narrowly (2 entries, documented)
- [x] root package files investigated (evidence-backed REMOVE_LOCAL_RESIDUE, executed)
- [x] root package disposition evidence-backed
- [x] frontend motion investigated (zero-import + zero-reverse-dep proof)
- [x] motion removed only if proof complete (via `npm rm`, removal-only diff)
- [x] frontend validation green if motion changed (tests/tsc/lint/build, twice)
- [x] .env remains ignored
- [x] credential value never exposed
- [x] rotation remains out-of-band
- [x] make preflight-source green
- [x] make ci green (ci-python green; ci-frontend behavior green — terminal lock-diff guard accounted as the expected uncommitted-removal signature, removal-only proof in record)
- [x] CI collection contract preserved (3210)
- [x] no Tier-3 run
- [x] all six scientific identities exact
- [x] no artifact regeneration
- [x] Graphify refreshed (11435/27793/318)
- [x] C1 removals remain removed
- [x] C2 migration remains intact
- [x] final dirty paths fully classified
- [x] zero UNKNOWN
- [x] C3-B record created
- [x] C3-B report created
- [x] nothing staged
- [x] nothing committed
- [x] nothing tagged
- [x] nothing pushed
- [x] C4 handoff explicit
