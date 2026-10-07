# V3.2I EXTERNAL HISTORICAL DRIVER-STATUS FEASIBILITY

## Final verdict

**V3.2I COMPLETE — LOCAL RAW STATUS SOURCE PARTIALLY VIABLE — READY FOR V3.2J DECISION.**

The required causal signal exists: F1 live-timing `TimingData.Lines[driver].Retired`
is an explicit, timestamped, per-driver retirement flag, recoverable from raw
delta streams already cached locally for 2018 + 2024, and probe-verified
obtainable for the missing 2019–2023 seasons from the same public static host.
It is PARTIAL, not full: local holdings cover 45/149 races, feed recall vs
official DNF is ~39% (misses are intrinsic, not bugs), and one genuine
mid-race transient in 45 races forces state-at-T semantics (designed, not yet
implemented). Runtime is untouched; coverage stays 2305/9644.

## Why V3.2I exists

Coverage is frozen at 2305/9644 (23.90%). STALE_ROSTER appears in 6407 blocker
sets — the largest remaining barrier. V3.2G proved no processed-corpus signal
(telemetry absence, position_null, STOPPED, pit duration, final DNF) is an
authoritative runtime retirement source, and V3.2H admitted no regimes. I asks
whether the information exists OUTSIDE the processed corpus. No heuristic was
re-attempted.

## Existing-data limitation

V3.2G: the FastF1-derived processed corpus (D9 laps, timing-app stints,
position Status sampled uniformly OnTrack, session-status session-level only,
zero RETIRED race-control family) cannot establish causal retirement. I
confirms the gap is in the INGESTION layer, not in history itself: the raw
timing feed carries per-driver Retired/Stopped/InPit booleans that the current
pipeline discards.

## Local raw-data inventory

- `data/raw/fastf1_cache/fastf1_http_cache.sqlite` (1.7 GB): 1141 cached
  responses; original `.jsonStream` delta-message bodies for 9 topics × (2018:
  21 races, 2024: 24, 2025: 24). **2019–2023 raw streams absent.**
- Per-race `*.ff1pkl` parsed artefacts all years (extended timing, timing-app,
  position with OnTrack/OffTrack-only Status, driver info, race control…).
- D9 lap parquets + results parquets (with dnf_flag/status_text evaluation
  labels) all seasons. No 2025 used anywhere in I evidence.

## Raw TimingData investigation

`TimingData.jsonStream` = 12-char session-clock prefix + JSON delta Ghosts;
first messages carry full per-driver snapshots (`Retired:false, Stopped:false,
InPit/PitOut`, sectors, speeds), later messages carry changed keys only.
2018 and 2024 schemas agree on the status namespace (2024 adds numeric sector
Status codes); a 2021 probe stream parses identically. Reconstruction applies
deltas chronologically per driver — never backwards from final state.

## Status semantics

- `Retired` bool: explicit retirement flag with session timestamp. Distinct
  from `Stopped` (track stoppage, transient) and `InPit/PitOut`.
- **Not monotone**: 2 measured true→false clearings in 45 races. Ricciardo
  Belgium 2018 (`Retired:true@1402` + `Stopped:true`, cleared on `PitOut@1671`,
  re-set `@4812` at his real lap-28 retirement) is one genuine mid-race
  transient (~4.5-min hazard window, **zero checkpoints impacted** — verified).
  Alonso Canada 2018 cleared post-race (benign).
- Causal rule therefore: retired-at-T = last value ≤ T (state reconstruction).
  First-true-alone is UNSAFE and is rejected as a future rule.
- Winners never carry a TRUE event (45/45). Post-race/cool-down trues exist
  (e.g. Alonso France 2018 @5957 after the flag) and are causally safe by
  timestamp comparison.
- Feed-vs-official divergence is informative, not error: Norris Austria 2024
  (`Retired@8042`, classified P20 via the >90% rule) and Hartley China 2018
  are genuine on-track retirements the results table classifies as finishers.
  Final classification ≠ causal retirement — the mission premise, confirmed.
- Misses (≈61% of official DNFs): lap-0 non-starters (no stream events
  possible), pit/garage retirements without a track flag, abandoned-without-
  Retired (Baku 2018: 7/7 DNFs fire `Stopped` but never `Retired`).
  Absence of Retired NEVER implies active (V3.2G lesson preserved).

## Historical availability

Local streams: 2018 21/21 races, 2024 24/24, 2019–2023 0. 56 retired-driver
timelines vs 127 official DNFs in cached races (recall ≈39%, precision at
event level high modulo the documented transient class). 2025 excluded.

## OpenF1

Historical since 2023 only (vendor FAQ, verified). 18 endpoints surveyed: no
retirement-transition endpoint exists. Live probe (Austria 2024, Norris):
position stream ends 14:21:36 (absence), `session_result.dnf=false`
(result-level, mirrors the >90% classification quirk), race control has flags
but no per-driver retirement. **VALIDATION_ONLY** (2023+ cross-check);
NOT_VIABLE as causal 2018–2024 source. Free no-key tier, CC BY-NC-SA 4.0.

## Jolpica

Ergast-compatible, result grain only (`status` e.g. Finished/Collision, laps;
verified live on 2024 round 24). No timestamps. **EVALUATION_ONLY**; rejected
as runtime causal source (exactly the future-derived class V3.2G forbids).

## Other sources

None needed: the official static host (`livetiming.formula1.com/static`,
public S3, no auth — the same host FastF1 itself fetches) serves every
season's streams. HEAD probe 2021 Abu Dhabi → HTTP 200, 5.5 MB; one full
targeted GET parsed (schema identical, 3 Retired:true for #7/#63/#11). No fan
scraping, no Wikipedia-as-data, no fabricated providers. No bulk download
performed (one 5 MB schema probe only).

## Source scorecard

| source | 2018–24 | per-driver | ts | explicit | causal@T | verdict |
|---|---|---|---|---|---|---|
| local TimingData.Retired (45 races) | partial | yes | yes | yes | yes (state-at-T) | PARTIALLY_VIABLE |
| static-host fetch 2019–2023 | full (probe-verified) | yes | yes | expected | expected | VIABLE completion path |
| OpenF1 | 2023+ | yes | positions only | no | no | VALIDATION_ONLY |
| Jolpica/Ergast | full, result grain | yes | no | result-only | no | EVALUATION_ONLY |
| V3.2G heuristics | n/a | no | no | no | no | NOT_VIABLE (stand) |

## Sample verification

55 retired-driver timelines + 2 explicit crash-absence cases (VER/RIC Baku
2018: Stopped, never Retired). Categories covered: normal retirements,
pit-lane retirements (Norris Austria @8042 after returning to pits),
classified-despite-retirement (>90% rule: Norris, Hartley, Vandoorne),
post-race stops (Alonso France 2018), crash-without-flag (Baku trio),
DNS-with-flag (Albon Interlagos 2024, feed-only #23). Gap first→ no:
final-Retired minus last-lap-start p50 ≈236 s, p90 ≈291 s, zero negatives.

## Winner firewall

No winner carries a TRUE event in any cached race. Vettel Bahrain 2018
explicitly PASS (no event). Bottas 2020-r01, Verstappen 2022-r18, Perez
2021-r06: UNTESTABLE_LOCALLY (no streams; must be re-run in V3.2J after
fetch — mandatory gate before any integration).

## Causal timeline

T1 < T_ret: NOT retired; T2 ≥ T_ret: retired; final result never consulted
(labels joined after, evaluation only). Feed clock and D9 state_time_s share
the live-timing session origin (gaps cluster within one lap of the last timed
lap). 55 timelines, deterministic, hash-pinned sequences per race.

## Current coverage

2305/9644 (23.90%) — unchanged (runtime untouched).

## Projected coverage

OFFLINE, cached races only: 2004 STALE checkpoints, 469 with every stale
offender retired-at-T, of which **380 are STALE-only → 2685/9644 (27.84%,
+3.94 pp)**. 2019–2023 project zero until fetched. Resolved-member identities
frozen in `projected_coverage.json`.

## Projected blockers

STALE all-sets 6407 → 5938 in the cached-races upper bound; TRACK 1317 and
WET 1157 unchanged (no regime source). Relief deepens covered races rather
than adding new ones (103 ≥1 unchanged, zero-support 46 unchanged).

## Projected stage coverage

LATE gains most (204 of 469; LATE 10.14% is the structural weakness and
retirements accumulate late) — relief where it matters: EARLY +83, MID +182.

## Projected race coverage

Median race coverage 9.38% → 12.7%; ≥50%: 39 races; ≥75%: 23; ≥95%: 11; full:
0. Per-race before/gain/fraction table frozen.

## Source completeness

Explicit signal, partial recall — intrinsic (non-starters, garage
retirements, abandoned-without-flag can never fire a track flag). Unknown is
the default state; source-unavailable vs active vs unknown are separated in
the design. Not a universal solution; a large, well-defined partial one.

## Licensing / reproducibility

Static host public, no auth observed; underlying data is F1 proprietary —
no legal claims made, uncertainty flagged. Raw blobs (GB) never committed;
derived transition tables (KB: race, driver, t, value + stream sha256) are
committable and pinned with adapter/contract versions. OpenF1/Jolpica terms
documented for their validation/evaluation roles.

## Proposed architecture

(DESIGN ONLY) static stream (pinned URL + sha256) → immutable adapter →
chronological state-at-T reconstruction → causal timeline artifact → V3.2C
presence as EXCLUSION input only → unchanged eligibility → unchanged MC2-E.
Invariants: nothing inside the kernel; absence≠active; transient guard by
construction; post-race excluded by T; parity bit-exact or stop.

## Provenance

(DESIGN ONLY) source identity + race/session + content hash + adapter version
+ status-contract version + rules hash.

## Runtime unchanged

`raceintel/` diff vs HEAD: empty. `api/` diffs are pre-existing V3.2A–G only.
Coverage recomputed from frozen audit: 2305/9644 exactly. Static CI test pins
no `v3_2i`/feed references in simulation + api.

## Known limitations

- 2019–2023 streams not yet fetched (one probe only); per-race validation
  and the three untestable firewall cases are mandatory V3.2J gates.
- Feed recall ~39%: STALE states with garage/non-flag retirements stay
  refused (correctly — unknown, not active).
- One genuine transient (RIC BEL 2018) bounds the hazard class; the guard
  (state-at-T) is specified, its integration unfunded until V3.2J.
- Official labels disagree with the feed in both directions (>90% rule);
  evaluation must use timeline-vs-checkpoint accounting, never label-match.
- Vendor terms for the static host are undocumented here; redistribution
  posture for derived tables flagged, not resolved.

## V3.2J recommendation

**V3.2J DECISION (not auto-start):** fetch 2019–2023 TimingData streams from
the probe-verified static pattern; validate per-race (recall/precision, flips,
all four firewall cases); build the exclusion-only presence input with the
state-at-T guard; re-test dry-green parity bit-exact; recompute coverage over
9644. Estimated tractable scope: ~104 streams, mechanical fetch + validation.
If V3.2J validates, projected ceiling with full-season streams is above the
27.84% cached-races bound (2019–2023 unmeasured — no number claimed).
