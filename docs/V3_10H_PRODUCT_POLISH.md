# V3.10H — Responsive / Accessibility / Product Polish

Whole-product consolidation over the validated A–G pit wall. No new
intelligence, no new science, no API changes (zero backend diff).

## Decisions (evidence-backed)

- **Expert strip: keep (A).** One ~28px subordinate row; simulator and
  prediction home have no contextual entry — collapsing would cost a click
  everywhere and risk discoverability. Zero code change.
- **No forced single-expansion.** All-open 1600 render stays readable with
  the track dominant; independent disclosures preserve comparison
  (telemetry beside strategy result) and focus predictability. Documented
  in `disclosure_audit.json`.
- **Home unchanged.** `/` is the prediction tool itself; PIT WALL leads the
  primary nav. No redesign, no CTA change.
- **Mobile is its own hierarchy** (nav → race → track → driver →
  timeline), not stacked desktop; L0 shows less (methodology hidden,
  telemetry collapsed). Verified 390 = no overflow, 44px targets.
- **Decision density:** 9-row matrix appears only on explicit intent with
  RUN AGAIN + single expert row; no compact-summary ranking invented
  (would need a "best" action — forbidden).

## Code changes (polish/bug-fix only)

1. **Stuck-availability fix (real bug).** Render-phase cache reads never
   re-rendered on fill → settled pages could stick on "Checking…" forever.
   Every fill now schedules a render (`setCacheVersion`).
2. **In-flight request sharing.** Concurrent mounts/scrubs share one
   race-catalogue / one per-anchor availability GET; always-fill
   correctly-keyed caches with state-only stale guards. Verified: single
   catalogue GET, zero duplicates, zero refetches on scrub.
3. **Single playback announcer (§34).** Status message constant while
   playing; visible timeline line lost its second live region.
4. **Calm spatial cue.** `announcePending` prop (default true keeps
   /replay identical); pit wall passes false while playing.
5. **Deduped expert links.** Nine per-branch rows → one shared row under
   the decisions area.
6. **Persistent run controls (§33).** Explore/Run-again + intervention
   form persist across available → running → result (running/result carry
   the intervention domain); no dead end, focus retained live-verified.

## Validation

- Frontend 604/604 (573 + 31 new: 11 causal poison, 20 polish),
  typecheck/lint/build clean (build re-run in gates).
- Python collection 5186; guard subset re-run; 19 worktree failures
  preserved untouched for V3.10I (first failing path always an A–F file).
- Live: density audit, journey (10 interactions), request census, perf
  (toggle 1ms, reslice 72ms, strategy 604ms), keyboard walkthrough
  (40 stops, no traps), 1600/820/390 screenshots, route 200s.
- Pathology V3.10H-P1…P20 all zero.

Next gate: V3.10I (final reconciliation + freeze). Not performed here.
