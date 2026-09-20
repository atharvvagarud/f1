"""Phase-5 R2 factual replay reconstruction service.

``ReplayFrame -> to_anchor() -> frozen RaceStateReconstructor.reconstruct()
-> RaceState``. Lazy by construction: building the timeline and this
service performs ZERO reconstructions; only explicit per-frame resolution
invokes the frozen pipeline.

Model-free, feature-free, API-free, storage-free. No cache: warm
reconstruction sits at the Phase-4 baseline (~39 ms), so an extra cache
layer buys nothing and adds invalidation surface (decision recorded in
the Phase-5 plan §27).

R2-E decision (no wrapper type): ``RaceState`` + ``ReplayFrame`` are
jointly sufficient. Navigation metadata (has_previous/has_next, neighbor
indices) derives from the frozen R1 ``ReplayTimeline``; duplicating it
around every ``RaceState`` would split navigation authority. The service
therefore returns ``RaceState`` directly.

Leader-lap jump (R2-I): ``race_context.race_leader_laps_at_state`` is
non-null and monotone non-decreasing along every served timeline
(audited R2: 149/149 races), so jump-to-leader-lap is a binary search
over frames — ``frame_for_leader_lap`` returns the FIRST frame with
leader progress >= L. "Lap" always means leader progress, never a
driver's ``lap_number``.
"""

from __future__ import annotations

from v2 import replay as RP
from v2.race_state import RaceState
from v2.race_state_reconstruction import RaceStateReconstructor


class ReplayReconstructionError(RP.ReplayTimelineError):
    """Replay resolution failure (frame lookup or frozen mismatch)."""


class ReplayReconstructor:
    """Lazy factual resolution of replay frames to frozen ``RaceState``.

    Holds a ``ReplayTimeline`` and one reusable frozen
    ``RaceStateReconstructor`` (which owns its immutable ``RaceIndex``).
    The reconstructor is built once by the caller and never rebuilt per
    frame. Both inputs must cover the same race.
    """

    def __init__(self, timeline: RP.ReplayTimeline,
                 reconstructor: RaceStateReconstructor):
        if not isinstance(timeline, RP.ReplayTimeline):
            raise ReplayReconstructionError(
                f"timeline must be a ReplayTimeline, got {timeline!r}")
        if not isinstance(reconstructor, RaceStateReconstructor):
            raise ReplayReconstructionError(
                "reconstructor must be a frozen RaceStateReconstructor, "
                f"got {reconstructor!r}")
        roster_races = set(reconstructor.roster)
        if timeline.race_id not in roster_races:
            raise ReplayReconstructionError(
                f"timeline race {timeline.race_id!r} has no reconstructor "
                f"coverage")
        self._timeline = timeline
        self._reconstructor = reconstructor

    @property
    def timeline(self) -> RP.ReplayTimeline:
        return self._timeline

    @property
    def race_id(self) -> str:
        return self._timeline.race_id

    def state_at(self, frame_index: int) -> RaceState:
        """Exact ``RaceState`` for one frame (the ONLY reconstruction path)."""
        frame = self._timeline.frame_at(frame_index)
        state = self._reconstructor.reconstruct(frame.to_anchor())
        self._check_consistency(frame, state)
        return state

    def first_state(self) -> RaceState:
        """RaceState at frame 0."""
        return self.state_at(0)

    def last_state(self) -> RaceState:
        """RaceState at the final factual frame (no extrapolation past it)."""
        return self.state_at(self._timeline.frame_count - 1)

    def previous_state(self, frame_index: int) -> RaceState | None:
        """State before index, or None at the first frame (no wrap)."""
        neighbor = self._timeline.previous(frame_index)
        return self.state_at(neighbor.frame_index) if neighbor else None

    def next_state(self, frame_index: int) -> RaceState | None:
        """State after index, or None at the last frame (no wrap)."""
        neighbor = self._timeline.next(frame_index)
        return self.state_at(neighbor.frame_index) if neighbor else None

    def leader_lap_at(self, frame_index: int) -> int | None:
        """Leader progress at a frame (factual; None only if unknown)."""
        return self.state_at(frame_index).race_context. \
            race_leader_laps_at_state

    def frame_for_leader_lap(self, lap: int) -> RP.ReplayFrame:
        """First frame with leader progress >= lap (binary search).

        Raises when lap < 1 or no frame reaches it (e.g. beyond a
        partial race's factual end). Never treats a driver's own
        ``lap_number`` as the race lap.
        """
        if type(lap) is not int or lap < 1:
            raise ReplayReconstructionError(
                f"leader lap must be an int >= 1, got {lap!r}")
        low, hit = 0, None
        high = self._timeline.frame_count - 1
        while low <= high:
            mid = (low + high) // 2
            value = self.leader_lap_at(mid)
            if value is None or value < lap:
                low = mid + 1
            else:
                hit, high = mid, mid - 1
        if hit is None:
            raise ReplayReconstructionError(
                f"no replay frame reaches leader lap {lap} "
                f"in race {self.race_id!r}")
        return self._timeline.frame_at(hit)

    @staticmethod
    def _check_consistency(frame: RP.ReplayFrame, state: RaceState) -> None:
        """Frame/state identity must match exactly (never coerced)."""
        mismatches = []
        if state.race_id != frame.race_id:
            mismatches.append(("race_id", state.race_id))
        if state.anchor_driver_id != frame.anchor_driver_id:
            mismatches.append(("anchor_driver_id",
                               state.anchor_driver_id))
        if state.anchor_lap_number != frame.anchor_lap_number:
            mismatches.append(("anchor_lap_number",
                               state.anchor_lap_number))
        if state.state_time_s != frame.anchor_state_time_s:
            mismatches.append(("state_time_s", state.state_time_s))
        if mismatches:
            raise ReplayReconstructionError(
                f"frame/state identity mismatch at frame "
                f"{frame.frame_index}: {mismatches}")
