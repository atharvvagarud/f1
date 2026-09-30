# PHASE 10 P10-4R CLEAN-CHECKOUT CI CONTRACT REMEDIATION

Remediation-only stage: P10-4 proved Docker/runtime reproducibility
from clean source but exposed that normal source CI was red without
the ignored scientific corpus. P10-4R fixes ONLY the CI/source-test
selection contract. No models, features, labels, scientific
semantics, artifacts, frozen tests, Docker, Compose, application, or
frontend product code was changed.

## Final verdict

P10-4R COMPLETE — P10-4 COMPLETE — READY FOR P10-5.

## Frozen baseline

- HEAD: `440f2a370aff56c799e69b65781199b158064fa0`, tag
  `v2-models-about-phase9` — unchanged throughout. Nothing staged,
  committed, tagged, reset, restored, cleaned, or stashed.

## Repository safety

Start/end verified: HEAD/tag as above, `git diff --cached --stat`
empty. PREEXISTING_OTHER_WORK untouched. `graphify update .`
succeeded (graph is developer tooling, never a CI input).

## Root cause

P10-2 assumed data-dependent tests self-skip on a clean runner.
P10-4 disproved it: frozen scientific tests with module-level corpus
assumptions (e.g. F14 `_HAS_D9 = True`), fixture-time corpus loads,
and builder-CLI invocations fail via FileNotFoundError / empty-glob
concatenation / NaN-estimation instead of skipping. The P10-2
WITH-data evidence was always valid; only the no-data behavior was
assumed.

## Failure classification (P10-4 evidence + clean-clone repro)

Reproduced in a fresh `git clone` + P10 overlay (CLEAN_CI_CHECKOUT,
with `.git`, no corpus, no bundle): 374 failed / 1947+2 passed /
344 errors — the P10-4 delta of exactly 2 is the git-metadata test
passing with `.git` present, confirming the classification.

- A REQUIRES_IGNORED_SCIENTIFIC_CORPUS: 718 nodes across 31 files
  (every traceback sampled: corpus-path FileNotFoundError,
  empty-glob `No objects to concatenate`, NaN from estimation over
  empty inputs, missing model-lab reports/matrix, builder CLI
  failing closed without inputs).
- B REQUIRES_RUNTIME_ARTIFACT_BUNDLE: 0 (zero failures reference
  the bundle).
- C REQUIRES_GIT_METADATA: 1
  (`test_runtime_bundle_survives_ignore`) — passes wherever
  `actions/checkout` provides `.git`; stays in normal CI.
- D TRUE_SOURCE_SAFE_REGRESSION: 0.
- E UNKNOWN: 0.

## Source-safe definition

A normal-CI Python test is SOURCE_SAFE only if it runs from a fresh
git checkout + Python 3.11 + requirements files with no bundle,
corpus, FastF1 cache, acquisition, generation, or developer files.
Tracked small artifacts allowed. Documented in
`scripts/run_ci_tests.py`.

## Python selection contract

`scripts/run_ci_tests.py` owns three disjoint manifests:

- `KNOWN_STALE_NODE_IDS` (7 ids / 12 instances, reasons; P11 debt).
- `RUNTIME_DEPENDENT_NODE_IDS` (empty, explicit).
- `scripts/ci_corpus_dependent.txt` (718 node ids in 31 per-file
  groups with dependency reasons).

Fail-closed: collection must equal `EXPECTED_COLLECTED` (3184 at
freeze + 7 new P10-4R contract tests = 3191); every manifest node
must still be collected (bare ids cover parametrizations); no
duplicates; stale/corpus disjoint; selection non-empty; counts
printed (collected/selected/deselected/skipped/xfail/passed).
pytest's exit code propagates untouched — no suppression.

## Frontend selection contract

`frontend/features/models/lib/evidence.test.ts` is the single
corpus-dependent file: it reads IGNORED
`data/v2/model_lab/reports/final_holdout_2025_v1.json` at module
top level for one test ("holdout values equal the frozen report"),
making the file atomic — the other 15 tests (TRACKED evidence JSON
+ TRACKED generator script) are Tier-3 covered. Not a product
defect: shipped `frontend/data/*.v1.json` is tracked and
self-contained. `scripts/run_ci_frontend_tests.py` selects the
other 16/17 files, fail-closed on file count (17) and manifest
existence. Plain `node --test` semantics unchanged for developers.

## Git metadata distinction

Deployment snapshot (`git archive`, no `.git`) and CI checkout
(`actions/checkout`, with `.git`) are different tools for different
questions, now documented. The single `.git`-dependent contract
test remains valid normal CI.

## Clean CI checkout methodology

`/tmp/f1-p10-4r-ci`: local `git clone` (read-only w.r.t. origin) +
P10 overlay (7 modified + P10-new files + docs). Contains `.git`,
tracked source, P10 source. Excludes corpus, bundle, FastF1 cache,
node_modules/.next (pre-npm-ci), env files, PREEXISTING_OTHER_WORK.

## Python clean-CI result

`make ci-python` (Python 3.11): source preflight OK, then
`collected=3191 selected=2466 deselected=725` → **1956 passed,
501 skipped, 4 xfailed, 0 failed, 0 errors in ~30 s.**

## Frontend clean-CI result

`make ci-frontend` (Node v22.23.1), exit 0: `npm ci`,
`collected=17 selected=16 deselected=1` → **180/180, 0 fail**,
then `tsc` clean, `eslint` clean, production build (7 static
routes), lockfile unchanged.

## Workflow changes

- `.github/workflows/ci.yml` frontend job now runs
  `python3 scripts/run_ci_frontend_tests.py` instead of bare
  `node --test` (python job already used `run_ci_tests.py`).
- `Makefile`: `ci-python` comment updated; `ci-frontend` uses the
  frontend selector (and now requires `check-python`).

## CI contract tests

`tests/test_ci_contract.py`: 17 → 24 tests, enforcing manifest
existence/shape/disjointness, fail-closed markers, no
bundle/corpus/generation requirements, stdlib-only selectors,
canonical workflow commands, and the standing SHA/permission/
no-suppression invariants. Green in the clean checkout (24/24);
green for the standing P10 matrix in the corpus tree.

## Validation tiers (survives to P10-5/P11)

- TIER 1 — NORMAL SOURCE CI: clean checkout, no corpus, fast;
  every push/PR. This stage.
- TIER 2 — DEPLOYABLE RUNTIME VALIDATION: source + bundle +
  Docker/Compose (P10-1/P10-4); not ordinary CI until bundle
  distribution exists.
- TIER 3 — FULL SCIENTIFIC REGRESSION: needs canonical corpus;
  local/release/science-owner validation. "Not run in Tier 1" ≠
  "validated".

## Stale scientific debt

The 12 stale-pin instances stay separately classified with reasons;
P11 must disposition them. Never mixed with corpus dependence
(enforced by a disjointness check).

## Deployment contract regression check

CI remediation touched no Dockerfiles/Compose/packaging/app code.
Static P10 container/Compose/runtime contracts re-run in the clean
checkout: **108 passed, 1 skipped** (incl. full
`test_production_reproducibility_contract.py`, green with `.git`).

## Scientific firewall

No FastF1/training/fit/generation/backfill/2025-eval, and no corpus
generation fallback anywhere (builder CLIs appear only as the
failing-closed subjects of deselected Tier-3 tests). Frozen science
files byte-untouched.

## Performance

Clean Tier 1: ~30 s Python + ~5 min frontend (dominated by `npm ci`
+ production build). Practical for every-push CI; no source-safe
test was dropped to buy speed (whole-file exclusions: none — all
corpus files had meaningful source-safe mixtures, hence node-level
selection).

## Cleanup / final safety

- CLEAN_CI_CHECKOUT removed after validation; no repo files harmed.
- End state: HEAD/tag unchanged, nothing staged,
  PREEXISTING_OTHER_WORK untouched. Permanent files only (below).

## Files changed

- `scripts/run_ci_tests.py` (selection contract rewrite)
- `scripts/ci_corpus_dependent.txt` (new, 718 nodes)
- `scripts/run_ci_frontend_tests.py` (new)
- `tests/test_ci_contract.py` (+7 contract tests)
- `Makefile` (`ci-frontend` selector; comments)
- `.github/workflows/ci.yml` (frontend selector step)
- `docs/PHASE10_P10_2_CONTINUOUS_INTEGRATION.md` (marked
  post-P10-4 correction only)
- `docs/PHASE10_P10_4_CLEAN_ENVIRONMENT_REPRODUCIBILITY.md`
  (remediation note + gate update only)
- `docs/PHASE10_P10_4R_CLEAN_CI_REMEDIATION.md` (new, this file)

## P10-5 handoff

Tier-1 CI is now genuinely green from a clean checkout; the
deployment contract (P10-4) is unregressed. P10-5 freeze can proceed
with: Tier 1/2/3 distinction, stale-pin debt for P11, and the
fail-closed pins (`EXPECTED_COLLECTED=3191`,
`EXPECTED_TEST_FILES=17`) as the tripwires for future suite drift.

## Entry gate

- [x] failure population completely classified (718/0/1/0/0)
- [x] zero UNKNOWN; zero true regressions hidden
- [x] source-safe definition explicit (runner docstring)
- [x] corpus-dependent Python tests classified (718 nodes)
- [x] runtime-dependent class explicit (empty, evidenced)
- [x] stale pins separately classified + disjointness enforced
- [x] runner fails closed (collection pin, manifest existence,
  non-empty selection; demonstrated live twice)
- [x] no blanket suppression (exit codes propagate)
- [x] frontend failure classified (single atomic file, A not B/C)
- [x] frontend source-safe selection implemented
- [x] checkout-vs-snapshot distinction documented
- [x] CLEAN_CI_CHECKOUT had .git, no corpus/bundle/preexisting work
- [x] source preflight green
- [x] clean `make ci-python` 0 failed / 0 errors (1956/501/4)
- [x] clean frontend tests 0 failed (180/180); tsc/lint/build green
- [x] lockfile unchanged
- [x] workflow uses validated commands
- [x] CI contract tests green (24/24 clean)
- [x] serving SHA still protected (workflow step + contract test)
- [x] no bundle/corpus requirement, generation fallback, or FastF1
- [x] deployment contract unchanged (static contracts 108 green)
- [x] P10-2 corrected transparently; P10-4 records remediation
- [x] three tiers documented; stale debt explicit
- [x] nothing staged/committed/tagged; preexisting work untouched
- [x] P10-5 handoff has a genuinely green clean-CI contract
