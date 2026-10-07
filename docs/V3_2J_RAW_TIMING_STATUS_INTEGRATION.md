# V3.2J RAW TIMING DRIVER-STATUS INTEGRATION

## Final verdict

**V3.2J COMPLETE — STATUS INTEGRATED — COVERAGE EXPANDED — READY FOR V3.2K.**
Full 2018–2024 source validated under the frozen contract; 2305 → 3678/9644
(23.90% → 38.14%, +1373, +14.24pp), every recovered checkpoint attributed.

## Frozen baseline

Tag `v3.1-race-dynamics`, commit `64c5af0`, verified exact at entry; only
accumulated V3.2A–I dirty, nothing staged. MC2-E science untouched.

## Why V3.2J exists

Legitimate simulation coverage stood at 2305/9644 with STALE_ROSTER the
largest blocker (6407 all-blocker-set hits). V3.2G proved processed data
holds no safe retirement signal; V3.2I found explicit per-driver
`Retired` state in live-timing `TimingData.jsonStream` (distinct from
`Stopped`), locally cached for 2018+2024 only, with a partial projection
of +380. V3.2J completes 2018–2024.

## V3.2I evidence inherited

Retired is CURRENT STATE (Ricciardo Belgium 2018 true→false), so
first-true-forever is forbidden; state-at-T is the latest value ≤ T.
Absence ≠ retirement. 2018: 21/21, 2024: 24/24 local; 2019–2023 fetched
here. One 2021 stream probe-verified there is now a 104-stream corpus.

## Preregistration

`results/v3/v3_2j/preregistration.json` frozen BEFORE any 2019–2023
download/evaluation (sha256 `ead0aaa4…`, verified by every J script):
Retired-only runtime field, latest-≤-T reconstruction, unknown semantics,
season acceptance rules, firewalls, accounting/parity/API rules, fail-closed
failure policy.

## Source manifest

149 races from the frozen replay catalogue (never from download success):
45 local-cache (sha pinned), 104 pending → all fetched. No 2025 anywhere.

## Fetch completeness

104/104, 0 failed, 0 silent skips (`fetch_report.json`). Bounded
concurrency (4), retry/backoff, streaming writes, atomic rename, resume,
content SHA256. Official host serves 2019/2020/2021/2023; the full 2022
prefix 403s there, so 22 streams came via the FastF1 mirror fallback
(same path/bytes, `served_by` recorded per race — the same fallback
order `fastf1/_api.py` uses). Three São_Paulo locators needed NFC
normalization (local dirs use NFD combining marks, host uses NFC).

## Raw TimingData schema

12-char `HH:MM:SS.mmm` session-clock prefix + JSON delta; first messages
carry snapshots, later ones changed keys only. Per-driver keys audited per
season (`schema_by_season.json`); `Retired` present in all 7 seasons.
Runtime reads `Retired` only; `Stopped`/`InPit`/`PitOut` counted for
diagnostics, never consulted.

## Clock alignment

Feed clock shares the live-timing session origin with D9 `state_time_s`
(`clock_alignment.json`): first-Retired gaps cluster one lap after the
last timed lap; 13 negatives investigated — 10 inside pinned unreliable
windows (mass red-flag transients), 3 terminal/post-race clears. Query is
strictly latest-delta-≤-T (equality counts, no future lookup). Clock
edge cases (before-first/exact/between/clearing/re-set) are Tier-1 tested.

## Delta reconstruction

Immutable stdlib adapter (`raceintel/simulation/driver_status.py`,
`v3.2j-raw-adapter-v1`): chronological application, missing key preserves
state, repeats compressed to change-only transitions, tied timestamps keep
file order (stable sort), malformed rows counted+skipped, non-dict
structure fails closed.

## Retired semantics

Exclusion-only `v3.2j-driver-status-v1`: True-at-T proves retirement;
False/unknown prove nothing. Stopped/InPit/absence/position-null/final-DNF
are never evidence.

## True-to-false clearings

19 clearings audited (`retired_clearings.json`): 13 unreliable windows
pinned (source retracted while the driver demonstrably continued —
2020-r09 Tuscan red-flag mass event ×10, Ricciardo Belgium 2018,
Magnussen 2020-r14, Perez 2023-r16) plus 6 terminal/post-race clears that
stay reliable (Alonso Canada 2018, Verstappen Japan 2019 genuine
retirements with post-race feed reset; sub-15s blips with 0 checkpoints).

## Winner firewall

PASS: all 4 mandatory cases never retired (Vettel 2018-r02, Bottas
2020-r01, Perez 2021-r06, Verstappen 2022-r18); the only winner with any
True event (Hamilton 2020-r09, red-flag artifact) has 0 checkpoint hits.

## Top-5 firewall

5 classified top-5 drivers with True events (all 2020-r09); 3 checkpoint
hits (Albon/Ricciardo/Perez frame 603), ALL inside suppressed windows —
kept refused, documented per hit.

## Transient firewall

101 checkpoints fall inside clearing windows; 92 would have wrongly
resolved under naive state-at-T. Suppression keeps all 22 affected
resolvable checkpoints refused; corpus-wide continuation hazard is 0
(no excluded offender has a timed lap after T).

## Label diagnostics

Diagnostic-only join (`label_diagnostics.json`): 171 TP-like, 40
classified-with-True (backmarkers by 90% rule + suppressed 2020-r09
finishers), 225 DNFs never flagged (crash Stopped-without-Retired etc.).
Runtime never reads labels.

## Status contract

`status_contract.json`: RETIRED_KNOWN_AT_T, exclusion-only, forbidden
evidence list, presence binding, pinned inputs, no runtime network.

## Derived timeline artifacts

149 per-race files (`results/v3/v3_2j/status/`, 596K total) with
season/round/session, locator, raw SHA256, `served_by`, adapter/contract
versions, transitions, content hash. Corpus identity pinned by hash.

## Temporal poison

Truncating all raw rows after T leaves status(T) unchanged (prefix-closed
reconstruction); Tier-1 T1–T4 lifecycle + corpus stream checks green.
Mutating final results/future laps/positions cannot reach the resolver
(no such inputs exist).

## Presence integration

Two-pass, additive, opt-in (`presence.py`, relieved results stamped
`v3.2j-presence-v2`): previously eligible states return before any status
logic (bit-identical); STALE refusals attempt relief only with a resolver,
excluding only fully-authoritative offenders, re-validating the reduced
field. Without a resolver behavior is exactly V3.2C. API service mirrors
this with preloaded local artifacts (default off).

## Field safety

Every removed stale offender is authoritative Retired-True at T outside
unreliable windows; one unresolved offender keeps the checkpoint refused.
Attribution is exact: gained == relieved == 1373.

## DNS preservation

DNS path untouched; 31 V3.2C DNS-recovered states unchanged.

## Dry-green parity

50/50 identical state identity + roster with resolver attached; full MC2
corpus re-run bit-exact (valid/invalid/winner/expected-finish/positions/
sample order). Any difference would have STOPped J; none found.

## Newly recovered-state validation

14-checkpoint season×stage spread, 500 sims each: 14/14 valid=500,
invalid=0, winner mass 1.0, distributions normalized. Still-unsupported
states raise the frozen error (route 422).

## Coverage before / after

2305/9644 (23.90%) → 3678/9644 (38.14%): +1373, +14.24pp. Conservation:
primary STALE 4667 → 3294 (Δ exactly 1373); every other primary
byte-identical (TRACK 1165, WET 801, TYRE 198, DRIVER 354, TERMINAL 154).

## Coverage attribution

`coverage_attribution.json`: gained set == relieved set exactly, each with
pinned offender list under `v3.2j-driver-status-v1`. No unexplained growth.

## Coverage by season

2018 8.7%→18.1%, 2019 40.2%→52.5%, 2020 18.5%→32.5%, 2021 21.3%→41.9%,
2022 23.2%→32.3%, 2023 22.9%→40.5%, 2024 31.1%→47.6%.

## Coverage by stage

EARLY 39.55%→48.44%, MID 23.22%→39.29%, LATE 10.14%→27.53% (nearly tripled).

## Coverage by race

≥1 supported 103→104 races; zero-support 46→45; median 0.094→0.207;
≥50% 30→56; ≥75% 15→40; ≥95% 7→17; full 0→0.

## Remaining blockers

STALE 3294 primary remains largest; TRACK 1165 / WET 801 unchanged (no
regime source). Intersections: TRACK-only 292, WET-only 176,
TRACK×STALE 579, WET×STALE 579.

## Retired-signal coverage

Per-season official-DNF vs feed-True agreement in `signal_coverage.json`
(diagnostic recall-like only): partial by design — 225 DNFs never flagged.

## API behavior

Opt-in status support → relieved states succeed; still-unsupported raise
frozen errors (422, no fallback); resolver preloaded from local files.

## Provenance

Source locator pattern/version, raw SHA256 per race, `served_by` per race,
adapter/contract versions, per-race content hashes, corpus hash — all in
tracked lightweight artifacts; raw payloads ignored, never committed.

## Reproducibility

`reproducibility.json`: fetch → verify → build → validate → recount
commands, no manual browser work, no credentials.

## Repository/raw-data policy

Raw streams (ignored `data/raw/fastf1_cache/v3_2j_timing/`, ~0.5GB +
existing 1.6GB sqlite cache) never committed. Tracked: manifest, hashes,
149 derived artifacts (596K), validation records. No redistribution
assumed; F1 terms apply to the upstream feed.

## Performance

Corpus load 69ms; lookup ~90ns; presence overhead unmeasurable at 20-call
grain vs ~0.4–1.5s per 500-sim run. MC2 untouched.

## Regime opportunity after J

TRACK-only 292 / WET-only 176 (informational). V3.2H rejection frozen and
unaffected.

## Tests

Tier-1: 18 in `tests/test_v3_2j_status_models.py` (parser, clock,
transitions, T1–T4 lifecycle, poison, contract, presence helper, schema
variants, no-network). Tier-3: 11 in `tests/test_v3_2j_status_corpus.py`
(prereg hash, manifest, fetch, schema, clearings, firewalls, hazard-free
resolution, 2025 firewall, attribution, dry-green parity). Full Tier-1
green; corpus tests green locally.

## Scientific identities

Adapter `v3.2j-raw-adapter-v1`, contract `v3.2j-driver-status-v1`,
relieved presence `v3.2j-presence-v2`, parity corpus `7ae97c3c…`, prereg
`ead0aaa4…`, status corpus hash in `status_corpus_identity.json`.

## Known limitations

Feed recall partial (unknown stays unknown); reliability rests on 13
pinned windows (future seasons need re-validation); 2022 via mirror;
STALE still dominates; no wet/track/terminal relief.

## V3.2K handoff

3678/9644 eligible; STALE 3294 primary; options: TRACK-only (292) /
WET-only (176) regimes (H science still rejected — new science needed) or
alternative stale signals. Status corpus pinned and reusable.
