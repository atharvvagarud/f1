# V3.9B Uncertainty Evidence Measurement

Offline measurement on frozen evidence only. No MC2 reruns, no refits, no
perturbations, no API/UI. Parent V3.9A card
`e3e2c3cfa2ebbd239b205479d6b7b9ee12130deddf3d4803c261c06b91ae099a`
(classification B, reviewed and accepted).

## U1 — MEASURED

Evidence: `results/v3/v3_8d/per_row_records.json` (277 aligned
`(state_id, driver_id)` pairs, 15 race-laps, 8 races, 2022–2024) joined with
`mc2_checkpoint.json` (n=5000 everywhere, derived not hard-coded). Outcome
labels present in frozen evidence were never read. Metrics: frozen
`v3.8c-consensus-metrics-v1`, imported unmodified, sim-minus-model.

- Magnitude (277 pairs): mean |gap| 0.0318, median 0.0007 — typically small
  gaps with a heavy tail of large disagreements. No LOW/MEDIUM/HIGH buckets.
- Rank/leader/top-k (14 full-field race-laps): median Spearman 0.6744,
  leader agreement 9/14, top-3 Jaccard distribution recorded.
- Temporal: within-race lap sequences for the 4 multi-lap races; stage
  splits EARLY/MID/LATE. Offline aggregates only; runtime stays state-local.
- A 90th-percentile gap is unusually large historically — not a confidence.

## U2 — MEASURED

- n=5000 at all 277 states (from evidence); zero states below 5000.
- Stored sampling context recomputed bit-exact (max diff 0.0) via the frozen
  implementation. Max SE 0.007071 (theory max at p=0.5); mean Wilson width
  0.00372; narrower at extremes.
- Boundaries: 187 valid k=0 zeros (NOT missing), 0 k=n. Precision language
  only: "given n futures, this frequency precision" — never true-probability
  or real-world claims.

## Diagnostic (descriptive only)

|gap|/SE distribution + inside-interval rate 0.5307, labelled diagnostic —
not a hypothesis test, no source winner. Large disagreement + narrow
interval means sampling noise is unlikely to explain it; neither source is
declared correct.

## U3 — PROVENANCE INSUFFICIENT (gate: NOT_EXECUTABLE)

- `regime_std_s`: population SD (ddof=0) of centered residuals + n frozen;
  no estimator SE/CI/bootstrap. Normal-theory SE invalid (repo's own AR(1)
  contradicts i.i.d.). Between-era spread is heterogeneity, not uncertainty.
  `support[]` is a data range, not a parameter range.
- `rho`: deployment value 0.264 is a hard-coded reference, not an estimate;
  lag-1 diagnostics (D1 0.225 / D2 0.485 / D3 0.365) are heterogeneity of a
  diagnostic, not a CI. min/max, percentiles, mean±SD as ranges: prohibited.
- Registry: every entry lower/upper null with reasons. Zero executable
  ranges — an acceptable, successful result.

## Classification

**B — U1_U2_MEASURED_U3_NOT_READY.** Recommended next gate: V3.9C
product/runtime uncertainty bundle using U1+U2 only (no sensitivity work).
