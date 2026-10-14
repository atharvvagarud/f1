// Replay event model + causal index (V3.10D).
//
// Events are evidence associated with the canonical replay domain — never
// another clock, never WorkspaceState members. Derivation is a pure function
// of dense per-frame digests (0..N-1); mapping rule: FIRST canonical frame
// at which the source change is observable (never nearest — nearest could
// move an event backward before it occurred).
//
// Closed taxonomy (audited evidence only):
//   FLAG_*    track_state transitions (D9 contemporaneous token)
//   RC_MESSAGE (category,flag) pair changes (lineage-only, text excluded upstream)
//   PIT       pit_stops_completed_so_far increments (observed completion only)
//   LAP       leader_lap increments (first frame of the lap)
// Omitted by audit: retirements (no causal signal; backdating forbidden),
// SC GPS position (unobserved), inferred incidents (never claimed).
//
// This module is value-import-free (type-only imports erase under
// `node --test` type-stripping) so every rule below is unit-tested
// dependency-free, including the mandatory future-data poison tests.

export type ReplayEventKind =
  | "FLAG_YELLOW"
  | "FLAG_SAFETY_CAR"
  | "FLAG_VSC"
  | "FLAG_RED"
  | "FLAG_GREEN"
  | "FLAG_UNKNOWN"
  | "RC_MESSAGE"
  | "PIT"
  | "LAP";

export type ReplayEventCategory = "FLAG" | "MESSAGE" | "PIT" | "LAP";

export function categoryOf(kind: ReplayEventKind): ReplayEventCategory {
  switch (kind) {
    case "RC_MESSAGE":
      return "MESSAGE";
    case "PIT":
      return "PIT";
    case "LAP":
      return "LAP";
    default:
      return "FLAG";
  }
}

/** Minimal per-frame evidence needed for event derivation. */
export interface FrameDigest {
  frameIndex: number;
  anchorStateTimeS: number;
  leaderLap: number | null;
  trackState: string | null;
  messageCategory: string | null;
  messageFlag: string | null;
  /** driver_id -> completed pit-stop count (entries with null counts omitted). */
  pits: Readonly<Record<string, number>>;
}

export interface ReplayEvent {
  id: string;
  raceId: string;
  frameIndex: number;
  eventTimeS: number;
  leaderLap: number | null;
  kind: ReplayEventKind;
  label: string;
  driverId: string | null;
}

export interface RejectedCandidate {
  frameIndex: number;
  reason:
    | "pit-from-unknown"
    | "pit-decrease"
    | "lap-decrease"
    | "null-lap-skipped";
  detail: string;
}

export interface EventIndex {
  raceId: string;
  totalFrames: number;
  /** All accepted events, sorted by (frameIndex, derivation order). */
  events: ReplayEvent[];
  /** First frame of each observed lap, ascending. */
  lapStarts: number[];
  /** Candidates refused mapping (never rendered as events). */
  rejected: RejectedCandidate[];
}

/** Intentional 1-line parity copy of StandingsTable.readableDriverId: this
 *  module stays value-import-free so node --test runs dependency-free. */
function readableDriverId(driverId: string): string {
  return driverId.replace(/_/g, " ").toUpperCase();
}

function flagKind(trackState: string | null): ReplayEventKind {
  switch (trackState) {
    case "yellow":
      return "FLAG_YELLOW";
    case "safety_car":
      return "FLAG_SAFETY_CAR";
    case "vsc":
    case "vsc_ending":
      return "FLAG_VSC";
    case "red_flag":
      return "FLAG_RED";
    case "all_clear":
      return "FLAG_GREEN";
    default:
      return "FLAG_UNKNOWN";
  }
}

function flagLabel(trackState: string | null): string {
  switch (trackState) {
    case "yellow":
      return "YELLOW";
    case "safety_car":
      return "SAFETY CAR";
    case "vsc":
    case "vsc_ending":
      return "VIRTUAL SC";
    case "red_flag":
      return "RED FLAG";
    case "all_clear":
      return "GREEN";
    default:
      return "TRACK STATUS — NO DATA";
  }
}

/**
 * Derives the ordered event index from dense digests. Frame 0 establishes
 * the baseline and never emits (starting conditions are not events).
 * Throws on a non-dense domain — a gapped corpus must fail loudly, never
 * derive across an unobserved gap.
 */
export function buildEventIndex(
  raceId: string,
  totalFrames: number,
  digests: FrameDigest[],
): EventIndex {
  if (digests.length !== totalFrames) {
    throw new Error(
      `Event corpus incomplete for ${raceId}: got ${digests.length} of ${totalFrames} digests.`,
    );
  }
  for (let i = 0; i < digests.length; i++) {
    if (digests[i].frameIndex !== i) {
      throw new Error(
        `Event corpus identity break for ${raceId} at position ${i}.`,
      );
    }
  }
  const events: ReplayEvent[] = [];
  const rejected: RejectedCandidate[] = [];
  const lapStarts: number[] = [];
  const emit = (event: Omit<ReplayEvent, "id">): void => {
    const key = `${event.raceId}:${event.frameIndex}:${event.kind}:${event.driverId ?? "-"}`;
    events.push({ ...event, id: key });
  };

  for (let i = 1; i < digests.length; i++) {
    const prev = digests[i - 1];
    const curr = digests[i];

    // FLAG: any track_state transition (including to/from unknown).
    if (curr.trackState !== prev.trackState) {
      emit({
        raceId,
        frameIndex: curr.frameIndex,
        eventTimeS: curr.anchorStateTimeS,
        leaderLap: curr.leaderLap,
        kind: flagKind(curr.trackState),
        label: flagLabel(curr.trackState),
        driverId: null,
      });
    }

    // RC_MESSAGE: (category, flag) pair change with a real new category.
    // The pair persists across frames; only a changed pair is a new message.
    if (
      (curr.messageCategory !== prev.messageCategory ||
        curr.messageFlag !== prev.messageFlag) &&
      curr.messageCategory !== null
    ) {
      const parts = [curr.messageCategory, curr.messageFlag].filter(
        (part): part is string => part !== null,
      );
      emit({
        raceId,
        frameIndex: curr.frameIndex,
        eventTimeS: curr.anchorStateTimeS,
        leaderLap: curr.leaderLap,
        kind: "RC_MESSAGE",
        label: parts.join(" · "),
        driverId: null,
      });
    }

    // PIT: per-driver count increments from a known previous count.
    // null -> n cannot establish an increment (unmappable, rejected).
    const drivers = Object.keys(curr.pits).sort();
    for (const driverId of drivers) {
      const next = curr.pits[driverId];
      const before = prev.pits[driverId];
      // A first-observed count of 0 proves nothing happened (no event,
      // no rejection). A first-observed count > 0 claims a stop whose
      // frame cannot be established — rejected, never placed.
      if (before === undefined) {
        if (next > 0) {
          rejected.push({
            frameIndex: curr.frameIndex,
            reason: "pit-from-unknown",
            detail: `${driverId} count ${next} without a known previous count`,
          });
        }
        continue;
      }
      if (next > before) {
        emit({
          raceId,
          frameIndex: curr.frameIndex,
          eventTimeS: curr.anchorStateTimeS,
          leaderLap: curr.leaderLap,
          kind: "PIT",
          label: `PIT STOP · ${readableDriverId(driverId)} · ${next}`,
          driverId,
        });
      } else if (next < before) {
        rejected.push({
          frameIndex: curr.frameIndex,
          reason: "pit-decrease",
          detail: `${driverId} count ${before} -> ${next}`,
        });
      }
    }

    // LAP: leader_lap increments. Nulls carry no lap evidence (skipped,
    // counted); decreases are data quirks (rejected, never mapped).
    if (curr.leaderLap !== null && curr.leaderLap !== prev.leaderLap) {
      if (prev.leaderLap === null || curr.leaderLap > prev.leaderLap) {
        lapStarts.push(curr.frameIndex);
        emit({
          raceId,
          frameIndex: curr.frameIndex,
          eventTimeS: curr.anchorStateTimeS,
          leaderLap: curr.leaderLap,
          kind: "LAP",
          label: `LAP ${curr.leaderLap}`,
          driverId: null,
        });
      } else {
        rejected.push({
          frameIndex: curr.frameIndex,
          reason: "lap-decrease",
          detail: `leader lap ${prev.leaderLap} -> ${curr.leaderLap}`,
        });
      }
    } else if (curr.leaderLap === null && prev.leaderLap !== null) {
      rejected.push({
        frameIndex: curr.frameIndex,
        reason: "null-lap-skipped",
        detail: "leader lap unobserved at this frame",
      });
    }
  }
  return { raceId, totalFrames, events, lapStarts, rejected };
}

// --- causal selectors: everything visible is frameIndex <= T -------------

/** Visible prefix of the index at T (binary search; shared by all views). */
export function visibleEvents(index: EventIndex, frameIndex: number): ReplayEvent[] {
  const events = index.events;
  let lo = 0;
  let hi = events.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (events[mid].frameIndex <= frameIndex) lo = mid + 1;
    else hi = mid;
  }
  return events.slice(0, lo);
}

/** L0 budget: latest N causal events, chronological (oldest first). */
export function recentEvents(
  index: EventIndex,
  frameIndex: number,
  limit = 5,
): ReplayEvent[] {
  const visible = visibleEvents(index, frameIndex);
  return visible.slice(Math.max(0, visible.length - limit));
}

/** Older causal events behind disclosure (chronological). */
export function olderEvents(
  index: EventIndex,
  frameIndex: number,
  limit = 5,
): ReplayEvent[] {
  const visible = visibleEvents(index, frameIndex);
  return visible.slice(0, Math.max(0, visible.length - limit));
}

/** Exact frame of the previous observable event (strictly before T). */
export function previousEventFrame(
  index: EventIndex,
  frameIndex: number,
): number | null {
  const events = index.events;
  let result: number | null = null;
  for (const event of events) {
    if (event.frameIndex >= frameIndex) break;
    result = event.frameIndex;
  }
  return result;
}

/**
 * Exact frame of the next event (strictly after T). Returns the FRAME ONLY —
 * never the event — so navigation chrome cannot leak future type, driver,
 * label, count, or position before the user advances.
 */
export function nextEventFrame(
  index: EventIndex,
  frameIndex: number,
): number | null {
  for (const event of index.events) {
    if (event.frameIndex > frameIndex) return event.frameIndex;
  }
  return null;
}

/** First frame of the previous lap (strictly before T). */
export function previousLapFrame(
  index: EventIndex,
  frameIndex: number,
): number | null {
  let result: number | null = null;
  for (const start of index.lapStarts) {
    if (start >= frameIndex) break;
    result = start;
  }
  return result;
}

/** First frame of the next lap (strictly after T). */
export function nextLapFrame(
  index: EventIndex,
  frameIndex: number,
): number | null {
  for (const start of index.lapStarts) {
    if (start > frameIndex) return start;
  }
  return null;
}

export interface EventMarker {
  frameIndex: number;
  count: number;
  kinds: ReplayEventKind[];
  events: ReplayEvent[];
}

/**
 * Marker aggregation over the VISIBLE set only: same-frame events share one
 * deterministic marker (index order preserved, count + details kept). No
 * event is ever dropped — aggregation only groups.
 */
export function visibleMarkers(
  index: EventIndex,
  frameIndex: number,
): EventMarker[] {
  const markers: EventMarker[] = [];
  for (const event of visibleEvents(index, frameIndex)) {
    const last = markers[markers.length - 1];
    if (last && last.frameIndex === event.frameIndex) {
      last.events.push(event);
      last.count += 1;
      if (!last.kinds.includes(event.kind)) last.kinds.push(event.kind);
    } else {
      markers.push({
        frameIndex: event.frameIndex,
        count: 1,
        kinds: [event.kind],
        events: [event],
      });
    }
  }
  return markers;
}
