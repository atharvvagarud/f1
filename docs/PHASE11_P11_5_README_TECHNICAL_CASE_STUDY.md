# PHASE 11 P11-5 README + TECHNICAL CASE STUDY

Portfolio presentation layer for frozen F1 Intelligence v2: rewritten
root README, evidence-driven technical case study, verified navigation
from README to evidence to implementation. Documentation work only —
no product change.

## Final verdict

P11-5 COMPLETE — READY FOR P11-6. README rewritten (1812 words),
case study created (3501 words), all claims/commands/links/wording
audited, screenshots honestly capture-pending, manifest hashed.

## Frozen baseline

- HEAD: `3c069b529f568dd25ea4a8213a6579afad631c0e`
- Tag at HEAD: `v2-productionization-phase10`

## Repository safety

At start: HEAD/tag exact, nothing staged. Dirty paths classified, zero
UNKNOWN: PREEXISTING_OTHER_WORK (untouched), P11_0–P11_4 (untouched).
Graphify updated. No git add/commit/tag/reset/restore/checkout/clean/
stash; P11-5 files uncommitted.

## Source evidence

P11-4 fact sheet (primary), storyboard, asset manifest, case-study
index, screenshot spec; P11-2/P11-3/P11-4 reports; P11-2/P11-3/P11-4
machine manifests (SHAs `5091cb77…`, `c9fe7f89…`, `b2d90680…`). No
metric rediscovered from arbitrary files — fact-sheet values used
throughout.

## Root README

Rewritten (1812 words, in the 1800–3000 target): subtitle, summary,
What It Does (6 surfaces), Key Results table, Product, Architecture
(+serving-separation paragraph), prominent Temporal Safety, Prediction
Model (normalization stated), MC (10k + 16.5 s, semantics separated),
Strategy (non-prescriptive), Explainability (equations + scope),
three-tier Validation, Performance table (container p50/p95 + Apple M4
+ concurrency 1), Running Locally (verified commands + live curl
anchor check), Testing (4 commands + purposes), Technology (used-only
list), Limitations (in-README), case-study link, Repository Guide,
Future Work (future-labeled). Recruiter-readable in ~2 minutes.

## Technical case study

Created at `docs/case-study/TECHNICAL_CASE_STUDY.md` (3501 words, in
the 3500–6000 target): all 18 storyboard sections as an
evidence-driven narrative (problem → decision → implementation →
evidence → trade-off → limitation), phase chronology suppressed except
where provenance matters. Mathematics limited to implemented
equations: sigmoid probability, logit decomposition, paired win/finish
deltas with orientation prose. All 11 P11-4 visuals referenced;
screenshots section points to the capture spec.

## Screenshot status

Tooling inspected: no Chromium/Firefox/Playwright/puppeteer anywhere;
nothing installed; frontend untouched. All six surfaces remain
CAPTURE_REQUIRED per spec. README handles absence structurally
(spec link + "capture-pending" note, no mock, no AI imagery). Hero is
title + description + architecture link — no fake substitute.

## Diagram integration

Case study embeds/references all 11 assets (architecture, temporal
safety, semantic boundaries, MC, strategy, validation, deployment at
minimum). README uses two (architecture link, temporal-safety link)
plus evaluation-adjacent tables — deliberately fewer, not overwhelming.

## Portfolio navigation

README → case study → fact sheet/diagrams → phase reports/manifests →
`api/`, `frontend/`, `v2/`, `scripts/`, `tests/` via the Repository
Guide. Concise links (10 README + 14 case-study), all resolve.

## V1/stale documentation disposition

- Root README: REPLACED (Phase-8-era: 1540 counts, stale commands, no
  Docker/P9/P10/P11).
- PRODUCT.md: narrow historical banner prepended (UPDATE-in-place);
  body preserved. It contradicted shipped v2 (strategy "not started",
  Models/About "not implemented") — now marked pre-Phase-7 history.
- V1-era `results/analysis/*.png`: REMOVE_FROM_PRESENTATION (README
  references none); files kept untouched as history, not deleted.
- Stale Phase-6/7/8 body bullets and 1540 test counts: gone with the
  README rewrite; owning reports remain the historical record.
- No scientific historical evidence deleted anywhere.

## Claim validation

Every numeric claim cross-checked against the fact sheet (comma/dash
normalized): holdout metrics, Tier counts, performance numbers, replay
counts, MC/strategy records — all present. One exception documented:
"1,041 anchors (2019-r01-R)" is live API enumeration from the P11-2
smoke, not fact-sheet content — recorded as such in the manifest, a
product-facing enumeration rather than a scientific metric.

## 2025 wording audit

All 2025 references scoped: one-shot holdout evaluation season (24
races, evaluated once, sealed) vs unserved production surface (404 on
all paths). No blurring in either document.

## Probability semantics audit

Independent per-driver binaries (unnormalized, field sum ≈0.56 live)
vs mutually exclusive MC frequencies (field sum 1.0) preserved in
every relevant description; never collapsed into "win probability".
Strategy non-prescriptive throughout.

## Performance wording audit

Local container HTTP + Apple M4 + concurrency 1 on every table;
endpoint duration never called inference latency; no page-load,
throughput, cloud, or browser claims. Small-N p99 caveat inherited
from P11-3.

## Test evidence wording

Tier-1 (1971/501/4) and Tier-3 (3193/5/4) never combined into one
headline; tier purposes and corpus requirement stated; skips shown as
measured.

## Command validation

All nine user-facing commands verified against Makefile targets or
P11-2-verified live behavior: `make ci/science/preflight-source/
preflight`, artifact `--validate`, `docker-compose-up/down`,
`backend-prod`, and the README curl anchor examples (path + params
match the validated contract). No expensive science executed.

## Link validation

10/10 README + 14/14 case-study relative links resolve (script-checked).

## Limitation coverage

Full matrix in README Limitations + case-study §17 + fact sheet;
nothing relegated to a hidden document. Future work explicitly future.

## Documentation manifest

`results/v2_final_validation/p11_5_documentation_manifest.json`
(schema `p11-5-documentation-manifest-v1`): sections, word counts,
assets, screenshots, verified claims/commands, link + unsafe-word
audits, limitations. Deterministic, sanitized. SHA-256:
`2eee92422142bb8884533e36728106fee486bd8fe2f55c2202a7628babd12f3f`.

## Scientific firewall

P11-5 modified only `README.md`, `TECHNICAL_CASE_STUDY.md`,
`PRODUCT.md` (banner), the doc manifest, and this report. No change to
`ml/`, `v2/`, `api/`, `data/`, scientific results, frontend code,
Dockerfiles, Compose, CI, or tests. No training/evaluation/benchmark/
generation/FastF1.

## Risks / blockers

None blocking. Residual: screenshots need a browser-equipped future
session; Mermaid GitHub rendering to be eyeballed in P11-6; V1-era
plots await P11-6 link-integrity judgment.

## P11-6 handoff

Inputs: this report, doc manifest (SHA above), README + case study +
fact sheet + diagrams + spec. P11-6 (Final Release Audit) re-runs
claim/link/secret checks against the new docs, verifies source-of-truth
compliance, and judges V1-plot disposition; it writes no new portfolio
copy.

## Entry gate

- [x] frozen HEAD/tag verified
- [x] nothing staged
- [x] dirty paths fully classified
- [x] authoritative P11-4 writing sources used
- [x] root README rewritten
- [x] README recruiter-readable in ~2 minutes
- [x] README key results concise
- [x] README temporal safety prominent
- [x] README independent-binary semantics explicit
- [x] README 2025 firewall explicit
- [x] README limitations visible
- [x] technical case study created
- [x] case study follows evidence-driven narrative
- [x] architecture integrated
- [x] temporal-safety visual integrated
- [x] semantic-boundary visual integrated where useful
- [x] Monte Carlo visual integrated
- [x] strategy visual integrated
- [x] validation visual integrated
- [x] deployment visual integrated
- [x] screenshot tooling inspected
- [x] no browser installed
- [x] no fake screenshots
- [x] all real screenshots privacy-safe if captured (none captured)
- [x] README handles missing screenshots cleanly
- [x] hero uses real screenshot or no fake substitute
- [x] stale V1 presentation classified
- [x] PRODUCT.md contradiction handled if necessary
- [x] all numeric claims verified
- [x] all 2025 references correctly scoped
- [x] prediction/MC probability semantics preserved
- [x] strategy wording non-prescriptive
- [x] performance boundaries explicit
- [x] no fabricated browser metrics
- [x] test counts not misleadingly combined
- [x] all commands verified
- [x] all relative links resolve
- [x] no fake badges
- [x] limitations adequately represented
- [x] future work clearly future
- [x] documentation manifest created
- [x] manifest deterministic/sanitized
- [x] manifest SHA recorded
- [x] unsafe-word audit complete
- [x] root README contains no unsupported claims
- [x] case study contains no unsupported claims
- [x] no application/scientific behavior changed
- [x] scientific firewall green
- [x] report complete
- [x] nothing staged/committed/tagged
- [x] unrelated work untouched
- [x] P11-6 handoff explicit
