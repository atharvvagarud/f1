"""V3.8B identity-safe alignment (pure, deterministic, no metrics).

align_pair / align_multi join NativePrediction records on exact
(state_id, driver_id) identity with metadata-consistency checks and
complete support accounting. Output ordering is canonical (sorted),
never input-order dependent. No agreement metrics, no ground truth.
"""

from __future__ import annotations

from raceintel.consensus import contracts as C


def _meta_of(record: C.NativePrediction) -> tuple:
    return (record.race_id, record.year, record.round, record.lap,
            record.stage)


def check_metadata_consistency(records: tuple) -> None:
    """Equal state_id with contradictory metadata fails closed."""
    by_state: dict = {}
    for rec in records:
        prior = by_state.setdefault(rec.state_id, _meta_of(rec))
        if prior != _meta_of(rec):
            raise ValueError(
                f"state identity collision with contradictory metadata: "
                f"{rec.state_id!r}")


def _support(records_by_source: dict, source: C.SourceId,
             reason: C.ReasonCode) -> tuple:
    if source in records_by_source:
        rec = records_by_source[source]
        return (rec.support_status, rec.support_reason, rec)
    return (C.SupportStatus.UNAVAILABLE, reason.value, None)


def align_pair(state_id: str, driver_id: str,
               records: tuple,
               source_a: C.SourceId, source_b: C.SourceId,
               mc2_targets: frozenset = frozenset({C.Target.WIN})
               ) -> C.ComparisonFrame:
    """One canonical pair frame. Missing sides stay explicit."""
    by_source: dict = {}
    for rec in records:
        if rec.state_id != state_id or rec.driver_id != driver_id:
            raise ValueError("alignment input mixes comparison keys")
        if rec.source_id in by_source:
            raise ValueError(
                f"duplicate source record for key: {rec.source_id}")
        by_source[rec.source_id] = rec
    check_metadata_consistency(tuple(by_source.values()))
    status_a, reason_a, rec_a = _support(
        by_source, source_a, C.ReasonCode.SOURCE_NOT_AVAILABLE)
    status_b, reason_b, rec_b = _support(
        by_source, source_b, C.ReasonCode.SOURCE_NOT_AVAILABLE)
    if rec_a is not None and rec_b is not None:
        meta = _meta_of(rec_a)
        race_id, year, round_, lap, stage = meta
        fam_a, fam_b = rec_a.source_family, rec_b.source_family
        tgt_a, tgt_b = rec_a.target, rec_b.target
        compat = C.targets_compatible(source_a, tgt_a, source_b, tgt_b,
                                      mc2_targets)
        comparable = (
            status_a is C.SupportStatus.AVAILABLE
            and status_b is C.SupportStatus.AVAILABLE and compat)
        prov_a, prov_b = rec_a.provenance, rec_b.provenance
        p_a, p_b = rec_a.native_probability, rec_b.native_probability
        mc_a = rec_a.mc_valid_trials
        mc_b = rec_b.mc_valid_trials
    else:
        present = rec_a if rec_a is not None else rec_b
        if present is None:
            raise ValueError("alignment requires at least one record")
        race_id, year, round_, lap, stage = _meta_of(present)
        fam_a = present.source_family if rec_a is not None else None
        fam_b = present.source_family if rec_b is not None else None
        tgt_a = present.target if rec_a is not None else None
        tgt_b = present.target if rec_b is not None else None
        compat = False
        comparable = False
        prov_a = present.provenance if rec_a is not None else None
        prov_b = present.provenance if rec_b is not None else None
        p_a = present.native_probability if rec_a is not None else None
        p_b = present.native_probability if rec_b is not None else None
        mc_a = present.mc_valid_trials if rec_a is not None else None
        mc_b = present.mc_valid_trials if rec_b is not None else None
    return C.ComparisonFrame(
        state_id=state_id, driver_id=driver_id, race_id=race_id,
        year=year, round=round_, lap=lap, stage=stage,
        source_a=source_a, source_b=source_b,
        family_a=fam_a, family_b=fam_b,
        target_a=tgt_a, target_b=tgt_b,
        target_compatible=compat, p_a_native=p_a, p_b_native=p_b,
        support_a=status_a, support_b=status_b,
        reason_a=(reason_a.value if isinstance(reason_a, C.ReasonCode)
                  else reason_a),
        reason_b=(reason_b.value if isinstance(reason_b, C.ReasonCode)
                  else reason_b),
        pair_comparable=comparable,
        provenance_a=prov_a, provenance_b=prov_b,
        mc_valid_trials_a=mc_a, mc_valid_trials_b=mc_b)


def align_multi(state_id: str, driver_id: str, records: tuple,
                candidate_sources: tuple) -> C.MultiSourceFrame:
    """Deterministic multi-source view: canonical source ordering."""
    for rec in records:
        if rec.state_id != state_id or rec.driver_id != driver_id:
            raise ValueError("alignment input mixes comparison keys")
    check_metadata_consistency(records)
    present = {rec.source_id: rec for rec in records}
    if len(present) != len(records):
        raise ValueError("duplicate source record for key")
    ordered = tuple(sorted(present, key=lambda s: s.value))
    entries = tuple(
        {"source_id": s,
         "support_status": C.SupportStatus.AVAILABLE,
         "target": present[s].target,
         "native_probability": present[s].native_probability,
         "family": present[s].source_family,
         "provenance": present[s].provenance,
         "mc_valid_trials": present[s].mc_valid_trials,
         "derived_from_mc2_counts":
             present[s].derived_from_mc2_counts} for s in ordered)
    excluded = tuple(
        {"source_id": s,
         "support_status": C.SupportStatus.UNAVAILABLE,
         "reason": C.ReasonCode.SOURCE_NOT_AVAILABLE.value}
        for s in candidate_sources if s not in present)
    first = records[0]
    return C.MultiSourceFrame(
        state_id=state_id, driver_id=driver_id, race_id=first.race_id,
        year=first.year, round=first.round, lap=first.lap,
        stage=first.stage, entries=entries, excluded=excluded)


def account_support(candidate_drivers: tuple,
                    records_by_state: dict) -> C.SupportAccounting:
    """Driver/state-set accounting with explicit exclusions."""
    states = tuple(sorted(records_by_state))
    avail: dict = {}
    inter = set(candidate_drivers)
    exclusions = []
    for state_id in states:
        recs = records_by_state[state_id]
        by_src: dict = {}
        for rec in recs:
            by_src.setdefault(rec.source_id, set()).add(rec.driver_id)
        for src, drivers in sorted(by_src.items(),
                                   key=lambda kv: kv[0].value):
            avail.setdefault(src, {}).setdefault(state_id, tuple(sorted(
                drivers)))
        have = {d for drivers in by_src.values() for d in drivers}
        # Comparable set: drivers holding a record from EVERY source
        # present in this state's records.
        every = set.intersection(
            *(set(drivers) for drivers in by_src.values()))
        inter &= every
        # Exclusions: every candidate driver missing from ANY source
        # present in this state's records (partial coverage included;
        # fully-absent drivers list every present source).
        for drv in sorted(set(candidate_drivers) - every):
            missing = [s.value for s in sorted(by_src,
                                               key=lambda s: s.value)
                       if drv not in by_src[s]]
            exclusions.append(
                {"state_id": state_id, "driver_id": drv,
                 "missing_from": tuple(missing),
                 "reason": C.ReasonCode.DRIVER_NOT_AVAILABLE.value})
    avail_rows = []
    for src in sorted(avail, key=lambda s: s.value):
        per_state = tuple(sorted(avail[src].items()))
        avail_rows.append((src.value, per_state))
    return C.SupportAccounting(
        candidate_drivers=tuple(candidate_drivers),
        available_by_source=tuple(avail_rows),
        intersection=tuple(sorted(inter)),
        exclusions=tuple(exclusions),
        candidate_states=states,
        pair_supported_states=states,
        multi_supported_states=states)
