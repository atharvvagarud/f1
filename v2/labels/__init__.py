"""F13 canonical label/target layer (contracts + builder).

Separate namespace from predictive features by design. Feature code
must never import label values; only the outcome-NAME guard set is
shared (see v2.features.registry).
"""

from v2.labels.builder import (
    CANONICAL_COLUMN_MAP,
    COMPANION_COLUMNS,
    build_label_frame,
    gains_position_by_finish,
    join_labels_for_f15,
    loses_position_by_finish,
    ordinal_training_eligible,
    position_change_from_state,
)
from v2.labels.contracts import (
    CANONICAL_LABEL_NAMES,
    LABEL_GRAIN,
    LABEL_SET_VERSION,
    LabelDef,
    LabelRegistry,
    LabelStatus,
    LabelTask,
    build_label_registry,
)

__all__ = [
    "CANONICAL_COLUMN_MAP",
    "CANONICAL_LABEL_NAMES",
    "COMPANION_COLUMNS",
    "LABEL_GRAIN",
    "LABEL_SET_VERSION",
    "LabelDef",
    "LabelRegistry",
    "LabelStatus",
    "LabelTask",
    "build_label_frame",
    "build_label_registry",
    "gains_position_by_finish",
    "join_labels_for_f15",
    "loses_position_by_finish",
    "ordinal_training_eligible",
    "position_change_from_state",
]
