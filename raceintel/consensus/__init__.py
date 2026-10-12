"""V3.8 consensus/alignment package (V3.8B infrastructure only).

Read-only, deterministic alignment of frozen predictive views. Depends
downward on frozen source types; no frozen source depends on this
package. No metrics, no fusion, no normalization, no ground truth.
"""

from raceintel.consensus import alignment, contracts  # noqa: F401
from raceintel.consensus import adapters  # noqa: F401
from raceintel.consensus import metrics, trajectories  # noqa: F401
