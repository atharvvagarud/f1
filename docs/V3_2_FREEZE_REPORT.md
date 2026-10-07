# V3.2 Freeze Report (V3.2O, freeze-only)

Parent tag `v3.1-race-dynamics` == commit
`64c5af094bd1304e23a5c7d3d5b782b0eef11aca`.

N verdict: V3.2N COMPLETE — V3.2 FREEZE CANDIDATE VALIDATED — READY FOR V3.2O.

Accepted simulator MC2-E (`E_AR1_RESIDUAL`), 5000 runs frozen.
Coverage 3678/9644 (38.14%), corpus hash `368ec94f…`.
Status contract `v3.2j-driver-status-v1`, presence `v3.2j-presence-v2`,
raw adapter `v3.2j-raw-adapter-v1`.
Scientific card `v3.2-final-scientific-card-v1`.
Full Tier-1 inherited from N: 2888 passed, 0 failed.

Commit plan: exactly ONE commit on top of the parent. Tag plan: annotated
`v3.2-monte-carlo-2`. Push status: NOT_PUSHED.

Known limitations: L track-code/token defect corrected supplementarily
(verdicts unchanged); 48 stopped-cleared InPit-True rows ambiguous;
duration evidence small-N; no DNF/weather/SC simulation; 45 zero-support
races; LATE 27.53%; no full-coverage race.

Raw external timing data is intentionally NOT stored in Git; provenance
and content hashes are tracked (see V3.2J manifest).
