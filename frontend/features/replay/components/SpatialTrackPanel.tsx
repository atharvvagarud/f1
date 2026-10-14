// Integrated spatial track panel (Phase-12 P12-7; additive presentation).
//
// One synchronized replay experience: the caller passes the existing
// authoritative replay position (raceId, frameIndex, anchorStateTimeS owned
// by useReplay) plus the existing race-tagged driver selection. There is no
// spatial clock, no spatial slider, no second selection state.
//
// Loading policy: geometry stays mounted (panel never flashes away); while
// a new frame resolves, the last same-race frame remains visible ONLY under
// an explicit "updating" cue naming both frames — previous markers are
// never silently presented as the current frame. Any failure is isolated
// to this panel: the factual replay keeps working.
//
// No trail (evidence-first deferral), no status/race-control overlays
// (P12-8 owns those), no predictive input.

"use client";

import { SpatialTrackRenderer } from "@/features/replay/components/SpatialTrackRenderer";
import { useSpatialTrack } from "@/features/replay/hooks/useSpatialTrack";
import {
  raceControlMessageOf,
  raceStatusOf,
} from "@/features/replay/lib/raceStatus";
import { spatialSelectionForRace } from "@/features/replay/lib/spatialIntegration";
import { geometryMatchesFrame } from "@/lib/spatial";
import type { RaceControlState } from "@/lib/v2";

/**
 * Race-status strip (P12-8): WHAT IS HAPPENING TO THE RACE RIGHT NOW, from
 * the already-authoritative RaceState at the current replay frame. Shares
 * the replay clock by construction; renders in every panel branch so
 * status stays visible even when spatial data is loading, failing, or
 * unavailable (PARTIAL spatial coverage never implies unknown status).
 * Circuit geometry stays neutral; status lives in this strip only.
 */
function RaceStatusStrip({
  raceControl,
}: {
  raceControl: RaceControlState | null;
}) {
  const status = raceStatusOf(raceControl);
  const message = raceControlMessageOf(raceControl);
  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border border-ink-700 bg-ink-900 px-4 py-2">
      <span className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
        Race status
      </span>
      <span
        role="status"
        aria-label={`Race status: ${status.label}`}
        className={`inline-block rounded-chip px-2 py-0.5 font-ui text-[11px] font-bold uppercase tracking-[0.12em] ${status.chipClassName}`}
      >
        {status.label}
      </span>
      {message ? (
        <span className="font-data text-[11px] uppercase tracking-[0.1em] text-fg-muted">
          RC {message.flag}
        </span>
      ) : null}
    </div>
  );
}

export function SpatialTrackPanel({
  raceId,
  frameIndex,
  anchorStateTimeS,
  raceControl,
  selectedDriverId,
  selectionRaceId,
  announcePending = true,
}: {
  raceId: string;
  frameIndex: number;
  anchorStateTimeS: number;
  raceControl: RaceControlState | null;
  selectedDriverId: string | null;
  selectionRaceId: string | null;
  /**
   * V3.10H §34: whether the frame-pending cue announces. Pit Wall passes
   * false while playing so per-frame pending flicker cannot spam
   * announcements; the cue stays visible (meaningful latency is never
   * hidden). Defaults true, preserving /replay behavior.
   */
  announcePending?: boolean;
}) {
  const spatial = useSpatialTrack({ raceId, frameIndex, anchorStateTimeS });
  const scopedSelection = spatialSelectionForRace(
    selectedDriverId,
    selectionRaceId,
    raceId,
  );

  const { geometry, geometryStatus, frame, frameStatus, displayFrame } = spatial;

  // Failure isolation first: spatial problems never touch replay state.
  // The status strip still renders — status comes from the replay frame,
  // not the spatial fetch (unknown positions never imply unknown status).
  if (geometryStatus === "unavailable" || frameStatus === "unavailable") {
    return (
      <div className="flex min-w-0 flex-col gap-2">
        <RaceStatusStrip raceControl={raceControl} />
        <SpatialTrackRenderer
          geometry={null}
          frame={null}
          status="unavailable"
          headline="Track map"
        />
      </div>
    );
  }
  if (geometryStatus === "error" || frameStatus === "error") {
    return (
      <div className="flex min-w-0 flex-col gap-2">
        <RaceStatusStrip raceControl={raceControl} />
        <SpatialTrackRenderer
          geometry={null}
          frame={null}
          status="error"
          errorDetail={spatial.errorDetail}
          headline="Track map"
        />
        <button
          type="button"
          onClick={spatial.retry}
          className="h-8 self-start border border-ink-700 px-3 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg"
        >
          Retry track data
        </button>
      </div>
    );
  }

  // Authoritative current frame. The hook admits it only on exact
  // race + index + clock agreement; the renderer re-checks geometry
  // identity itself and withholds markers on mismatch. A residual mismatch
  // here therefore surfaces as the renderer's integrity block, never as
  // silently stale markers.
  if (
    geometryStatus === "ready" &&
    frameStatus === "ready" &&
    geometry !== null &&
    frame !== null
  ) {
    return (
      <div className="flex min-w-0 flex-col gap-2">
        <RaceStatusStrip raceControl={raceControl} />
        <SpatialTrackRenderer
          geometry={geometry}
          frame={frame}
          status="ready"
          selectedDriverId={scopedSelection}
          headline="Track map"
        />
      </div>
    );
  }

  // Frame in flight: retain the last same-race frame under an explicit
  // pending cue (governed continuity, not silent staleness).
  if (
    geometry !== null &&
    displayFrame !== null &&
    displayFrame.race_id === raceId &&
    geometryMatchesFrame(geometry, displayFrame)
  ) {
    return (
      <div className="flex min-w-0 flex-col gap-2" aria-busy={spatial.isFramePending}>
        <RaceStatusStrip raceControl={raceControl} />
        {spatial.isFramePending ? (
          <p
            {...(announcePending ? { "aria-live": "polite" } as const : {})}
            className="border border-ink-700 bg-ink-900 px-4 py-2 font-data text-[11px] uppercase tracking-[0.12em] text-fg-dim"
          >
            Updating track — showing frame {displayFrame.frame_index} while
            frame {frameIndex} loads…
          </p>
        ) : null}
        <SpatialTrackRenderer
          geometry={geometry}
          frame={displayFrame}
          status="ready"
          selectedDriverId={scopedSelection}
          headline="Track map"
        />
      </div>
    );
  }

  return (
    <div className="flex min-w-0 flex-col gap-2">
      <RaceStatusStrip raceControl={raceControl} />
      <SpatialTrackRenderer
        geometry={null}
        frame={null}
        status="loading"
        headline="Track map"
      />
    </div>
  );
}
