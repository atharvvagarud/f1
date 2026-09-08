"""Central feature definitions (R3 foundation refactor).

Single source of truth for the inference feature columns. The list is moved
verbatim from ``api/services/predictor.py`` — ORDER IS LOAD-BEARING: saved
pipelines were fitted against this exact column order, so never reorder,
rename, add or remove entries here. Training scripts keep their own
NUM_COLS/CAT_COLS split (needed by their imputation/encoding pipelines);
unifying those requires executing training and is out of refactor scope.
"""

FEATURE_COLS = [
    "position_x",
    "session_time_x_seconds",
    "gap_to_leader_seconds",
    "lap_time_x_seconds",
    "tyre_life_x",
    "stint_x",
    "pit_in_time_present",
    "pit_out_time_present",
    "track_status_x",
    "compound_x",
]
