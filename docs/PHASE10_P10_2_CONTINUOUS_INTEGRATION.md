# PHASE 10 P10-2 CONTINUOUS INTEGRATION

CI only. No scientific, product, dependency, CORS, readiness, or
observability changes. No Docker builds in normal CI, no registry, no
deployment, no secrets, no browser framework. P10-3 NOT started.

## Final verdict

P10-2 COMPLETE — READY FOR P10-3. `.github/workflows/ci.yml` (two jobs:
Python 3.11 source contract + Node 22 frontend contract) protects every
P10-1 contract that is checkable from a plain source checkout, with an
honest source-vs-deployable split, an explicit stale-pin exclusion list
with evidence, and local `make ci*` equivalents proven green.

## Frozen baseline

- HEAD: `440f2a370aff56c799e69b65781199b158064fa0`
  (`440f2a3 feat(v2): freeze models and about phase 9`)
- Tag on HEAD: `v2-models-about-phase9` — matches, start to end.
- Nothing staged/committed/tagged/reset/restored/cleaned/stashed.

## Repository safety

- Start/end: HEAD/tag as above, `git diff --cached --stat` empty.
- Owned changes only: `.github/workflows/ci.yml` (new),
  `scripts/run_ci_tests.py` (new), `tests/test_ci_contract.py` (new),
  `Makefile` (three additive targets + three `.PHONY` names),
  this document (new).
- P10-0–P10-1F work and PREEXISTING_OTHER_WORK preserved; README untouched
  (no badge — P11 owns README).

## Test inventory

- Python: 97 `test_*.py` files, **3144 collected** (with P10-2's own 17
  contract tests; 3127 before them). Full local run WITH the validated
  bundle present: **3106 passed, 5 skipped, 4 xfailed, 12 failed in
  ~57 min** — the 12 failures are pre-existing stale historical pins
  (evidence below), zero caused by P10 work.
- Data-dependent tests (≈25 files) guard on `_has_canon`/`_HAS_*`
  directory checks and **skip** when the ignored corpus is absent — so a
  plain source checkout runs the source-safe subset with no exclusion
  machinery for them.
- Frontend: 197 `node:test` tests, plus `tsc`, `eslint`, production build.
- P10 contract tests: 12 + 22 + 12 + 13 + 13 + 6 + 17 = **95 passed**.

## CI architecture

One workflow, `.github/workflows/ci.yml`, two parallel jobs:

- `python` (3.11 source contract, ~30 min timeout): checkout → setup-python
  3.11 (pip cache on both requirements files) → `--source` preflight →
  canonical installs → serving-model SHA assert → `run_ci_tests.py`.
- `frontend` (Node 22 contract, ~20 min timeout): checkout → setup-node 22
  (npm cache on the lockfile) → `npm ci` → `node --test` → `tsc` →
  `lint` → `npm run build` (`NEXT_PUBLIC_API_BASE=http://localhost:8000`)
  → lockfile-unchanged gate.

No third job: contract version/SHA checks live as named steps inside the
two jobs; topology stays minimal and logs attributable.

## Trigger policy

`push` + `pull_request` (no invented branch names — repo default is
`master`, remotes vary), least-privilege `contents: read`, no
`pull_request_target`, no secrets, official actions only
(checkout/setup-python/setup-node). No `workflow_dispatch` (nothing
manual to trigger in ordinary CI).

## Permission model

Workflow-level `permissions: contents: read`. No write/packages/id-token.

## Runtime versions

Python `3.11` (no matrix — P10-1 validates exactly 3.11); Node `22`
(satisfies `engines >=22 <23`). Concurrency group `ci-${{ github.ref }}`
cancels superseded runs except on `main`/`master` (guarded by expression;
mainline safety over minutes).

## Python dependency installation

Canonical `python -m pip install -r requirements.txt` then
`-r requirements-test.txt`; pins untouched; setup-python pip cache covers
downloads only (never data/results/caches).

## Source preflight

`python scripts/check_runtime_environment.py --source` runs in ordinary
CI. `--deployable` is ABSENT by design (test-enforced): the ignored
bundle is not a CI input, and attempting it would fake the
source-vs-deployable distinction. `V2_ALLOW_NETWORK` appears nowhere.

## Python test selection

`scripts/run_ci_tests.py` (stdlib-only, no science): full `tests/ -q`
minus **7 node IDs covering 12 known-stale instances**, each with a
recorded reason; fails closed (exit 2) if a deselect target disappears.
Data-dependent tests self-skip without data — no list needed for them.

The 12 (all pre-existing at `440f2a3`; the pinned files match HEAD
byte-for-byte, e.g. `git diff HEAD -- api/main.py` is empty, so P10 work
cannot have caused them; fixing them would mean rewriting frozen
Phase-4–6 test pins or frozen science — out of scope, dispositioned to
science owners):

- `phase4_freeze::test_frozen_module_hashes_match` — pins Phase-4 SHAs;
  Phases 5–9 evolved the files.
- `phase5_freeze` ×3 (file hashes, cache-not-required, api-main drift) —
  same staleness; cache test additionally contradicts the P10-1 bundle era.
- `phase5_r7::test_head_and_phase4_tag_intact` — pins Phase-4 HEAD
  `4f26801…`; baseline is Phase-9 `440f2a3…` by contract.
- `phase6_r6` ×1 + `phase6_r71` ×6 — pin pre-fix Monte Carlo identities
  later behavior moved past.

Local WITH-data evidence: deselecting exactly these yields the 3106-pass
remainder (5 skipped, 4 xfailed preserved — legitimate test semantics,
never workflow suppression).

## Frontend pipeline

Per P10-1B/D contract, validated live: `npm ci` (371/372 pkgs) →
`node --test` **197 pass / 0 fail** → `tsc --noEmit` clean → `eslint`
clean → `NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run build`
green (7 static routes) → `git diff --exit-code` lockfile clean. Only
benign pre-existing node module-type warnings.

## Evidence integrity

Phase-9 `/models` + `/about` evidence is protected by the existing
validators inside the 197 frontend tests (`evidence.test.ts` family) —
checked-in JSON consumed as frozen bytes. `scripts/build_phase9_evidence.py`
has NO check mode (it regenerates + writes), so CI must not run it;
rebuilding would also need ignored scientific inputs. Documented, not
executed.

## Serving artifact integrity

Tracked joblib SHA `1116b34f…fcaa59f4` asserted twice without loading any
model: a named CI step (stdlib hash) and the `--source` preflight + P10
runtime-environment tests. No prediction/evaluation.

## Docker/Compose contract validation

Static contracts only in normal CI, via the P10-1C/1D/1E/1F suites
(44 tests): Dockerfiles, Compose, cross-contract reproducibility —
including backend-Dockerfile-unchanged and no-backend-DNS-leak guards.
No image builds.

## Docker build policy

NORMAL CI BUILDS NOTHING: `npm run build` already exercises the Next
production build and static tests pin container structure, so a 553 MB /
2.86 GB image build would add cost without a distinct failure class
(`docker build`, `compose build` strings test-absent from the workflow).
P10-1F no-cache builds remain the standing reproducibility evidence.

## Heavy deployable validation policy

DEFERRED HONESTLY — no `deployable-validation.yml` created: the runtime
bundle is local/ignored with no CI-accessible distribution, and a
workflow that cannot acquire it would be fake. Deployable validation
stays a documented local procedure (`prepare → preflight → compose
build/up/smoke`, see P10-1E/1F reports) until bundle distribution is
defined. No artifact uploads, no invented sources (test-enforced).

## Scientific firewall

Workflow + runner + Make CI targets contain no FastF1/ingestion/feature/
label/matrix/training/backfill/simulation-param/explainability/2025
content (contract-test scanned); `V2_ALLOW_NETWORK` never set. Network in
CI is dependency-only (PyPI/npm/GitHub Actions) — scientific-data network
is absent by construction (no bundle, no download steps).

## Network policy

Allowed: PyPI, npm registry, GitHub Actions infra. Not present: F1 data
acquisition of any kind. The distinction is structural, not promissory.

## Action policy

`actions/checkout@v4`, `actions/setup-python@v5`, `actions/setup-node@v4`
— major pins, no SHAs (no repo SHA-pinning policy exists), no third-party
actions. Timeouts 30/20 min from local evidence (57 min full-suite wall
includes data-heavy integration CI will skip; margins are generous).

## Timeout policy

python 30 min, frontend 20 min. No `continue-on-error`, no `|| true` on
core gates (test-enforced); xfails/skips stay inside test semantics.

## Local CI equivalent

`make ci-python` (source preflight + runner), `make ci-frontend`
(npm ci → tests → tsc → lint → build with explicit base → lockfile
gate), `make ci` (both). Additive, non-destructive, dry-run verified
(`make -n`); full commands proven green by direct execution.

## Workflow validation

No YAML parser on host and none installed for this: validated by (a) 17
contract tests over workflow text (triggers, permissions, versions,
preflight split, installs, API base, SHA, science/build absence), (b)
zero-tab + required-key structural check, (c) Make dry-runs, (d) live
execution of every commanded step locally. No visual-only reliance.

## Test evidence

- New `tests/test_ci_contract.py`: 17 passed (covers every entry-gate CI
  invariant incl. runner-script stdlib-only + tracked checks).
- P10 matrix: **95 passed** (12+22+12+13+13+6+17).
- Full suite WITH data: 3106 passed / 12 stale-pin failures / 5 skipped /
  4 xfailed (~57 min); deselect set == failure set exactly.
- Frontend: 197/0 + tsc + lint + build + lockfile-clean.
- Full scientific suite as a whole: NOT separately run beyond the above
  (the above IS the whole `tests/` tree; no file outside it exists to run).

## Known limitations

- The 12 stale pins need science-owner disposition; CI deselects are
  explicitly documented debt, not a fix.
- CI cannot catch data-dependent regressions (no bundle on runners) —
  accepted by the reproducibility model; P10-4 clean-environment work may
  narrow this if bundle distribution is defined.
- No Docker image build in CI (documented cost decision).
- arm64-only validation carries over; GitHub runners are amd64 — static
  contracts are arch-independent, but container runtime remains
  arm64-validated.
- No README badge (remote/default-branch confirmed as
  `atharvvagarud/f1`, `master` — but P11 owns README).

## Post-P10-4 correction (P10-4R, 2026-09-30 — history preserved above)

P10-2's claim "data-dependent tests self-skip without data" was
disproved by P10-4 clean-checkout evidence: a clean clone run failed
376 + errored 344 because many frozen scientific tests have no skip
guard (e.g. F14 `_HAS_D9 = True`) and read the ignored corpus at
canonical paths. The P10-2 WITH-data evidence above remains true;
the no-data behavior was assumed, not measured.

Current contract (see `docs/PHASE10_P10_4R_CLEAN_CI_REMEDIATION.md`):
Tier 1 normal CI = source-safe selection owned by
`scripts/run_ci_tests.py` (`KNOWN_STALE_NODE_IDS` +
`RUNTIME_DEPENDENT_NODE_IDS` (empty) + `ci_corpus_dependent.txt`,
718 nodes) and `scripts/run_ci_frontend_tests.py` (16/17 files;
`evidence.test.ts` needs the ignored holdout report). Both runners
are fail-closed (collection/file-count pins, manifest-existence
checks, no suppression). Clean-checkout proof: 1956 passed /
0 failed / 0 errors (py, ~30 s), 180/180 + tsc + lint + build +
lockfile-clean (frontend). Corpus-dependent tests are Tier 3, not
Tier 1; "not run" ≠ "validated". The `actions/checkout`
distinction: GitHub CI provides `.git` (the one P10-4 git-metadata
test stays valid); P10-4's `git archive` deployment snapshot
intentionally lacks it — different tools for different questions.

## P10-3 handoff

CI protects everything P10-3 will touch without conflicting: CORS stays
wildcard (no CI assertion on origins — P10-3 will add env-driven config
plus its own tests), `/health` stays liveness-only (no readiness
assertion to collide with P10-3's endpoint), no logging middleware to
trip log-shape tests. P10-3 should add: origin-config tests, readiness
semantics tests, and their CI steps — no existing CI step needs removal.

## Entry gate

- [x] baseline unchanged; nothing staged
- [x] inventory documented (97 files / 3144 collected / 197 frontend)
- [x] source-safe suite from evidence (full tree + 7 deselect IDs, reasons
  recorded; skips preserved)
- [x] workflow exists; push + PR; read-only; no pull_request_target
- [x] py3.11 + node22; canonical installs; source preflight only
- [x] V2_ALLOW_NETWORK absent; SHA protected; P10 tests run
- [x] frontend tests/tsc/lint/build/API-base/lockfile all green
- [x] evidence validators exercised (via 197); Docker static contracts run
- [x] no image builds; heavy policy honest; no invented bundle source
- [x] firewall/network/pinning/timeout/suppression policies enforced by test
- [x] workflow validated; contract tests green; local equivalents green
- [x] deps/apps/science unchanged; docs complete; P10-3 handoff explicit
