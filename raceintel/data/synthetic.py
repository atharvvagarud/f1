"""Synthetic framework-proving adapter (D3).

Produces tiny deterministic frames for the orchestrator/CLI to exercise —
NOT a source adapter. D4/D5 provide real adapters; this module exists so
the framework is proven without touching FastF1, the network, or real data.
"""

from __future__ import annotations

import pandas as pd

from raceintel.data.ingestion import AdapterResult, UnitContext


def synthetic_adapter(ctx: UnitContext) -> AdapterResult:
    """Two minimal contract-shaped frames for the unit's race."""
    entry = ctx.entry
    race_id = entry.race_id or entry.unit_id
    season = entry.season or 0
    round_no = entry.round_no or 0
    races = pd.DataFrame([{
        "race_id": race_id,
        "season": season,
        "round_no": round_no,
        "event_id": f"{season}-r{round_no:02d}",
        "circuit_id": "synthetic_circuit",
        "event_name": "Synthetic Grand Prix",
        "official_event_name": None,
        "country": None,
        "location": None,
        "event_format": "conventional",
        "total_laps_scheduled": 10,
        "f1_api_support": None,
    }])
    laps = pd.DataFrame([{
        "race_id": race_id,
        "driver_id": "synthetic_driver",
        "lap_number": 1,
        "position": 1,
        "session_time_end_s": 95.0,
        "lap_start_s": 0.0,
        "lap_time_s": 95.0,
        "sector_1_s": 30.0,
        "sector_2_s": 32.0,
        "sector_3_s": 33.0,
        "sector_1_end_s": 30.0,
        "sector_2_end_s": 62.0,
        "sector_3_end_s": 95.0,
        "speed_i1_kmh": 300.0,
        "speed_i2_kmh": 310.0,
        "speed_fl_kmh": 320.0,
        "speed_st_kmh": 330.0,
        "compound": "SOFT",
        "tyre_life": 1,
        "stint_number": 1,
        "fresh_tyre": True,
        "pit_in_s": None,
        "pit_out_s": None,
        "track_status": "1",
        "deleted": False,
        "deleted_reason": None,
        "is_accurate": True,
        "fastf1_generated": False,
    }])
    return AdapterResult(frames={"races": races, "driver_laps": laps})
