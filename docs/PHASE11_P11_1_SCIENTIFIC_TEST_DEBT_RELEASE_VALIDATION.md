# PHASE 11 P11-1 SCIENTIFIC TEST DEBT + RELEASE VALIDATION

P11-0 identified two release-validation gaps: 12 stale scientific test
instances and no canonical Tier-3 command. P11-1 resolves both. No
science was modified; the scientific implementation is byte-untouched.

## Final verdict

P11-1 COMPLETE — READY FOR P11-2. All 14 stale instances (12 planned +
2 newly-identified siblings) resolved with strength preserved; Tier-3
release contract created, preflighted, and proven: full scientific
regression green on the canonical corpus.

## Frozen baseline

HEAD `3c069b529f568dd25ea4a8213a6579afad631c0e`, tag
`v2-productionization-phase10` pointing at HEAD. Nothing staged before,
during, or after P11-1 work.

## Repository safety

Dirty paths throughout P11-1: PREEXISTING_OTHER_WORK only (11 worktree
deletions under `.claude/`/`.cursor/`/`.gemini/`/`.ignore`/`.mcp.json`;
`AGENTS.md`/`GEMINI.md`/`opencode.json` modifications; untracked
`.impeccable/`/`.opencode/`/root `package.json`/`package-lock.json`) plus
the untracked P11-0 report. P11-1 touched exactly 11 paths (9 modified
tracked + 2 new), all Phase-11-owned. No `git add/commit/tag/reset/
restore/checkout/clean/stash` executed. P11-0 report unmodified.

## P11-0 findings

12 stale instances over 7 node-IDs (r71 node × 6 params), all frozen-
constant drift after legitimate Phase-5→P10 evolution or a documented
Python-version sensitivity — never behavior regressions. Plus: no
canonical Tier-3 release command (`make science` missing). Source:
`docs/PHASE11_P11_0_FINAL_EVALUATION_PORTFOLIO_READINESS_AUDIT.md`
(stale table, Tier-3 assessment, validation matrix, source-of-truth map).

## 12 stale-test inventory

| ID | Test file :: node | Old assertion | Current authoritative contract |
|----|-------------------|---------------|--------------------------------|
| 1 | `test_v2_phase4_freeze.py::test_frozen_module_hashes_match` | every Phase-4-manifest file byte-identical | all except `api/main.py` + self-file exact; `api/main.py` authorized evolution |
| 2 | `test_v2_phase5_freeze.py::test_freeze_manifest_file_hashes_match` | every Phase-5-manifest file byte-identical | 19 files authorized evolution; rest exact |
| 3 | `test_v2_phase5_freeze.py::test_freeze_manifest_generated_cache_not_required` | `results/v2_replay` absent | cache REQUIRED: 149 races / 9644 checkpoints (renamed `test_generated_cache_required_in_bundle_era`) |
| 4 | `test_v2_phase5_freeze.py::test_freeze_manifest_documents_authorized_api_main_drift` | Phase-5 `api/main.py` SHA is current | drift chain phase4→phase5→phase6→Phase-7/P10-3 |
| 5 | `test_v2_phase5_r7.py::test_head_and_phase4_tag_intact` | HEAD == `4f26801…` | Phase-4 seal + P10 freeze are ancestors; both tags resolve |
| 6 | `test_v2_phase6_r6.py::test_pit_disabled_reproduces_r5_result_identity` | R5 identities `ee315af7…/d9d2df0b…/238be238…` | 3.11 identities `435535b8…/8fcce6a4…/e694871d…` |
| 7–12 | `test_v2_phase6_r71.py::test_accepted_state_matches_pre_fix_result_identity[×6]` | pre-fix `r6_result_identity` from R7 raw artifact | `state_identity` still exact vs raw artifact; post-fix result pins (see §Per-test evidence) |
| 13 | `test_v2_phase5_r7.py::test_frozen_module_hashes_unchanged_except_authorized_main` | Phase-4 files except `api/main.py` byte-identical | same + `tests/test_v2_phase4_freeze.py` exempt (P11-1-corrected) |
| 14 | `test_v2_phase8_e1.py::test_frozen_modules_untouched_by_e1` | Phase-4 files except `api/main.py` byte-identical | same + `tests/test_v2_phase4_freeze.py` exempt (P11-1-corrected) |

Instances 13–14 were STALE_EXPECTATION_NOT_PREVIOUSLY_IDENTIFIED: P11-0
missed them because they passed at the frozen baseline and broke only as
a consequence of P11-1's own authorized correction of instance 1 (same
self-pin class). Discovered by the Tier-1 dev run (2 failed / 2470
passed), corrected with the identical REPLACE treatment, verified
individually green before the Tier-1 re-run.

Owning sources: Phase-4 seal (`PHASE4_FREEZE_MANIFEST.json`), Phase-5
seal (`PHASE5_FREEZE_MANIFEST.json`), Phase-6 (`PHASE6_FINAL_REPORT.md`
§"Python-version-sensitive frozen identity",
`PHASE6_FREEZE_MANIFEST.json` `api_main_drift`), Phase-8 E2
(`phase8_e2_cache_manifest_v1.json`, `PHASE8_E2_REPLAY_CACHE_BACKFILL_REPORT.md`),
P10 freeze (`3c069b5` / `v2-productionization-phase10`).

## Per-test evidence

1. **Phase-4 hash loop.** Live scan: every recorded file matches EXCEPT
   `api/main.py` (current `≠ 455910f5…`, markers for replay/simulation/
   strategy routers + `ServingConfig` + `RequestLoggingMiddleware`
   present) and the test file itself (self-pin cannot survive its own
   authorized correction). Invariant (frozen files byte-identical)
   valid; manifest is a superseded time capsule for `api/main.py` only.
2. **Phase-5 hash loop.** Live scan: exact evolved set of 19 —
   `api/main.py`; 14 frontend files (Phase-9 workspace/evidence);
   `scripts/build_replay_prediction_cache.py` (`--feature-source matrix`,
   Phase-8); `.gitignore` (`/runtime_artifacts/`); the 2 self-pinned
   test files. Test asserts `diverged == evolved` exactly plus
   per-family authorized-evolution evidence. All other recorded files
   still byte-exact.
3. **Cache absence → presence.** E2 manifest: `race_count` 149,
   `checkpoint_count` 9644, aggregate `78a3c059…`, model `1116b34f…`;
   149 per-race files in `results/v2_replay/checkpoints/`. Corpus-
   dependent (ignored generated cache) → Tier 3.
4. **Drift chain.** Phase-5 record (`455910f5…→2840271a…`) intact as
   history; Phase-6 record continues (`…→5a0ec439…`); current file
   differs from all three recorded SHAs and carries all stage markers.
5. **Lineage.** `merge-base --is-ancestor` (exit-code read; the file's
   `_git` helper drops it) proves `4f26801…` and `3c069b5…` are both
   ancestors of HEAD; both tags resolve to their frozen commits.
6. **R6 identities.** Owning report documents the mechanism: pins were
   recorded on Python 3.13.14; `MonteCarloResult.identity()` hashes
   numpy float values (version-sensitive formatting). Same engine,
   same fixtures, same seeds on 3.11.15 → new pins, verified
   deterministic by independent rerun (byte-identical outputs).
   Invariant (pit-disabled path reproduces R5 behavior) unchanged.
7–12. **R71 parity.** `state.identity()` still matches the pre-fix raw
   artifact EXACTLY for all 6 states (same inputs — the eligibility
   proof's load-bearing half). Result pins re-baselined on 3.11.15:
   `f6d3ddca…` (2020-r05 EARLY), `60e15a75…` (2020-r05 MID),
   `3561eec3…` (2021-r07 LATE), `55ae9eec…` (2022-r01 MID),
   `d71bb8f2…` (2023-r07 LATE), `d1c914a7…` (2024-r01 EARLY);
   deterministic by rerun. Not blind copying: mechanism documented by
   the owning phase, input side independently pinned, semantics covered
   by neighboring tests (blocker rejection, determinism, batch parity,
   future-poisoning invariance).

No Part-C stop condition triggered: implementation agrees with frozen
artifacts; no artifact conflicts; 2025 firewall, temporal safety, and
`INDEPENDENT_BINARY` untouched (neighboring freeze tests green).

## Dispositions applied

- REPLACE_WITH_CURRENT_CONTRACT: instances 1–2 (obsolete byte-pins →
  exact-where-frozen + authorized-evolution assertions; strictly
  stronger than skipping) and 13–14 (same self-pin class, one-file
  exemption + structural presence).
- UPDATE_STALE_EXPECTATION: instances 3 (incl. rename — old name
  asserted the opposite), 4, 5, 6, 7–12 (values only; purpose,
  strength, tolerances, invariants preserved).
- No DELETE; no weakening (`assert is not None`-style replacements:
  zero). Each replacement documents OLD/CURRENT/WHY in comments and
  above.

## Scientific byte-safety

`git status` over `ml/ v2/ api/ data/ results/ frontend/`: clean.
Changed: 6 stale TEST files + `run_ci_tests.py` + `ci_corpus_dependent.txt`
+ `Makefile` + 2 new (preflight, contract tests) + this report. No
artifact, matrix, cache, parameter, or joblib modification (all
identities re-verified below).

## Frozen identities

Hash/manifest reads only: serving `1116b34f…fcaa59f4` ✓;
explainability `bae84b61…982939f` ✓; replay 149/9644 `78a3c059…b96298`
✓; Phase-2 content `d2ee966c…` ✓; matrix `b0f17b66…` ✓; simulation
`r3-v1` through 2024 (`r3-v1.2024.4c2f85f08f1c`,
scientific `4c2f85f0…`) ✓.

## Tier-3 definition

Tier 3 = FULL SCIENTIFIC REGRESSION. Requires: canonical ignored
scientific corpus + tracked source + Python 3.11 + test deps. May use
`runtime_artifacts` only where tests genuinely depend on it (none
currently — `RUNTIME_DEPENDENT_NODE_IDS` stays empty). Must NOT:
download F1 data, run FastF1 ingestion, regenerate datasets/matrices/
caches/parameters, retrain models, regenerate explainability. Tier 3
validates frozen science; it does not rebuild it.

## Tier-3 corpus contract

`scripts/check_science_environment.py` (stdlib-only: argparse/json/sys/
pathlib): 5 marker dirs (D9 states, `r3-v1__through-2024` params, v1
matrix, `results/v2_replay`, model-lab reports) + 4 marker manifests
(params/matrix manifests parse as JSON objects; E2 manifest
`checkpoint_count == 9644` and `race_count == 149`; holdout report
parses) + checkpoints dir holds 149 entries + Python 3.11 gate.
Distinguishes MISSING_CORPUS (absent path) from INVALID_CONTRACT
(empty/unreadable/structural mismatch). Presence is structural only —
validity is proven by the suite, never certified by the preflight.

## Canonical release command

`make science`: `check_science_environment.py` FIRST (fail early, exit
2), then `pytest tests/ -q -p no:cacheprovider` with NO Tier-1 selector
(no `--deselect`/`-k`/`-m`-marker, no `run_ci_tests.py`, no corpus
manifest). Includes all 721 corpus-dependent nodes and all 12 corrected
former stale pins. Contract-pinned by 11 tests in
`tests/test_science_validation_contract.py`.

## Tier-1 relationship

`make ci-python` = Tier-1 source-safe engineering validation
(clean-checkout safe; 721 corpus exclusions via `run_ci_tests.py`).
`make science` = Tier-3 corpus-backed scientific regression (full
suite, needs corpus). Neither substitutes for the other (Makefile
documents both directions).

## Frontend evidence disposition

Option B (separate commands): `make science` runs the Python suite
only (contract test forbids frontend content in its pytest line).
`frontend/.../evidence.test.ts` keeps its P10-4R file-atomic Tier-1
deselect (top-level ignored holdout-JSON read would poison 15
source-safe tests); on corpus-present release trees `make ci-frontend`
executes it (P10-5 dev-tree evidence: 180/180). No frontend file
changed in P11-1. A future stage may split the test; not P11-1 scope.

## Contract tests

`tests/test_science_validation_contract.py`: 11 tests — target exists,
preflight-first ordering, no Tier-1 selector leakage, missing-corpus
fail-early (exit 2 + MISSING_CORPUS + canonical message), stdlib-only
preflight (AST import audit), no network/generation fallback (AST call
+ literal audit), Tier-1 mechanism intact, resolved stale debt absent
from Tier-1, corrected corpus nodes classified, Python 3.11 preserved,
`pytest tests/` scope. All 11 green (two initial over-strict token
assertions fixed in the TEST, implementation untouched).

## Tier-1 development-tree result

`make ci-python` (explicit Python 3.11.15 venv, corpus present):
`collected=3202 selected=2481 deselected=721 (stale=0 runtime=0 corpus=721)`
→ **2472 passed, 5 skipped, 726 deselected, 4 xfailed, 0 failed, 0 errors**
in 47:22. First attempt surfaced instances 13–14 (2 failed / 2470
passed); after their identical-class correction, the re-run is fully
green. Fail-closed pins hold exactly (3202 = 3191 + 11 new contract
tests; 721 = 718 + 3 corrected corpus nodes; pytest deselects 726
items via the bare r71 node covering 6 params).

## Tier-1 clean-checkout result

Local `git clone` at `3c069b5` + 11-file P11-1 overlay (tracked source
only: no corpus, no `runtime_artifacts`, no caches), `make ci-python`
with the same interpreter: `collected=3202 selected=2481
deselected=721 (stale=0 runtime=0 corpus=721)` → **1971 passed, 501
skipped, 726 deselected, 4 xfailed, 0 failed, 0 errors** in 27.23 s.
Reconciliation: 1971 + 501 = 2472 = dev-tree passes — the 501
file-presence-guarded tests skip clean and execute+pass with corpus
(same accounting as P10-5). Selector semantics proven clean-safe.

## Tier-3 missing-corpus result

`check_science_environment.py --root /tmp/p111_empty` → exit 2,
9× MISSING_CORPUS + canonical "requires the canonical local scientific
corpus. No data is downloaded or generated automatically." No pytest
spawned (preflight gates the recipe), no network, no generation.

## Tier-3 full scientific result

`make science` on the canonical dev corpus (Python 3.11.15, corpus +
bundle present): preflight SCIENCE OK, then full `pytest tests/` with
zero deselection → **3193 passed, 5 skipped, 4 xfailed, 0 failed,
0 errors** in 57:28 (3202 collected = 3193 + 5 + 4). Release target met.

## Failure classification

No Tier-3 failures: nothing to classify, zero UNKNOWN. The only
failures observed in P11-1 were instances 13–14 in the Tier-1 dev run
(classified STALE_EXPECTATION_NOT_PREVIOUSLY_IDENTIFIED, corrected,
re-run green). No TRUE_REGRESSION, ENVIRONMENTAL, NONDETERMINISTIC, or
INVALID_TEST findings. No open-ended cleanup undertaken.

## Release command surface

- `make ci` (= `ci-python` + `ci-frontend`): ordinary source-safe CI.
- `make science`: Tier-3 full scientific regression (corpus-gated).
- `make preflight-source`: tracked-tree gate (fresh-clone state).
- `make preflight` (deployable): source + validated bundle + network-off.
No stable target renamed.

## Scientific firewall

P11-1 permanent changes: 6 test files (expectations only), Tier-1
selector (empty stale list + pin 3191→3202), corpus manifest (+3 nodes),
`Makefile` (+`science`), 2 new tooling/test files, this report. No
model/feature/RaceState/simulation/strategy/replay/explainability/
generation/training change; no new dependency (`requirements*.txt`,
`package-lock.json` untouched); no FastF1 acquisition; no 2025
evaluation (holdout report used only as a presence marker — parsed as
JSON, never evaluated).

## Known limitations

- Tier-3 takes ~1 h single-core (parquet-heavy); clean Tier-1 ~30 s.
- MC result pins are Python-3.11-line-specific (documented mechanism);
  a future interpreter-line move must re-baseline via the same protocol
  (double-run determinism + state-identity anchoring), not by weakening.
- Frontend evidence validation stays a separate command (Option B).
- `make science` covers `tests/`; Docker/CI-workflow/frontend-node
  gates remain Tier-1/Tier-2 concerns.

## P11-2 handoff

Inputs: this report, `make science` + Tier-3 evidence (3193/5/4 green),
corrected pins (3.11-line MC identities), clean Tier-1 proof
(1971/501/4). P11-2 runs validation matrix A–C (Tier-1 both trees,
Tier-2 smoke, Tier-3 full) on the frozen tree and records evidence. Do
not bundle benchmark/README/visual work. Note for P11-2: MC result pins
are Python-3.11-line-specific; any interpreter-line move must repeat
the §Per-test evidence protocol, never weaken assertions.

## Entry gate

- [x] Phase-10 frozen HEAD verified (`3c069b5`)
- [x] Phase-10 tag verified (`v2-productionization-phase10`)
- [x] nothing staged
- [x] unrelated dirty work classified (PREEXISTING_OTHER_WORK + P11-0)
- [x] all 12 stale instances reconstructed
- [x] every stale instance independently verified (§Per-test evidence)
- [x] every owning authoritative source identified
- [x] zero blind expected-value updates (mechanism + anchoring + rerun)
- [x] zero scientific contract conflicts (no Part-C trigger)
- [x] UPDATE dispositions preserve test strength
- [x] REPLACE dispositions preserve/improve invariant strength
- [x] all 12 stale instances resolved (12/12 green) plus 2
  newly-identified siblings resolved (same class, §12 stale-test inventory)
- [x] affected tests pass individually (12 passed in 12.67 s; 2 in 1.14 s)
- [x] frozen science implementation byte-untouched
- [x] serving model identity exact
- [x] explainability identity exact
- [x] replay identity exact
- [x] Phase-2 identities exact
- [x] simulation identity exact
- [x] Tier-3 definition documented
- [x] canonical Tier-3 command exists (`make science`)
- [x] missing corpus fails early (exit 2, pre-pytest)
- [x] missing corpus triggers no generation
- [x] missing corpus triggers no network
- [x] corpus contract explicit (MISSING vs INVALID)
- [x] Tier-3 scope explicit (`pytest tests/`, no selector)
- [x] Tier-3 positively defined (not "whatever Tier-1 excluded")
- [x] Tier-1 remains distinct
- [x] frontend evidence test disposition explicit (Option B)
- [x] Tier-3 contract tests green (11/11)
- [x] resolved stale exclusions removed (stale list empty)
- [x] remaining corpus exclusions correctly classified (721, disjoint)
- [x] fail-closed selector pins reconciled (3191→3202 documented)
- [x] development-tree Tier-1 green (2472/5/4, 47:22)
- [x] clean-checkout Tier-1 green (1971/501/4, 27.23 s, pins exact)
- [x] missing-corpus Tier-3 negative test green
- [x] full Tier-3 scientific run completed (3193/5/4, 57:28)
- [x] Tier-3 = 0 failed / 0 errors
- [x] all Tier-3 failures, if any, classified (none; 13–14 done in Tier-1)
- [x] zero UNKNOWN failures
- [x] release command surface documented
- [x] no dependencies changed
- [x] no scientific generation
- [x] no FastF1 acquisition
- [x] no 2025 evaluation
- [x] scientific firewall green
- [x] P11-1 report complete (this file; unstaged)
- [x] nothing staged/committed/tagged
- [x] PREEXISTING_OTHER_WORK untouched
- [x] P11-2 handoff explicit
