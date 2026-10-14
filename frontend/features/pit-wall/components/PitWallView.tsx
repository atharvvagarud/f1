// Pit Wall primary workspace shell (V3.10C).
//
// Visual hierarchy (V3.10A §6): A. race header → B. track/replay (dominant)
// → C. selected-driver region → running order → quiet reserved notes →
// F. timeline. Region D (race control) renders the causal event layer
// (V3.10D); the driver region carries E intelligence (V3.10E) and F
// telemetry (V3.10F); the notes column carries G contextual strategy +
// alternative entry points — availability-gated, explicit-run only, never
// advice (V3.10G).
//
// Identity comes exclusively from the V3.10B WorkspaceProvider. The outer
// shell reads workspace identity plus the served-race registry; the per-race
// workspace follower mounts with key={raceId}, so a race change remounts
// with fresh data instead of reset logic. Presentation reuses validated
// replay components: RaceSelector, ContextBar, SpatialTrackPanel,
// StandingsTable, TimelineScrubber.

"use client";

import { RaceSelector, raceLabel } from "@/features/replay/components/RaceSelector";
import { ContextBar } from "@/features/replay/components/ContextBar";
import { SpatialTrackPanel } from "@/features/replay/components/SpatialTrackPanel";
import { StandingsTable } from "@/features/replay/components/StandingsTable";
import { TimelineScrubber } from "@/features/replay/components/TimelineScrubber";
import { DriverPanel } from "@/features/pit-wall/components/DriverPanel";
import { DecisionExploration } from "@/features/pit-wall/components/DecisionExploration";
import { PitWallTransport } from "@/features/pit-wall/components/PitWallTransport";
import { EventFeed } from "@/features/pit-wall/components/EventFeed";
import { EventMarkers } from "@/features/pit-wall/components/EventMarkers";
import { EventNav } from "@/features/pit-wall/components/EventNav";
import {
  usePitWallRace,
  usePitWallRaces,
  type PitWallRace,
} from "@/features/pit-wall/hooks/usePitWall";
import {
  usePitWallEvents,
  type PitWallEvents,
} from "@/features/pit-wall/hooks/usePitWallEvents";
import {
  useDriverIntelligence,
  type DriverIntelligenceView,
} from "@/features/pit-wall/hooks/useDriverIntelligence";
import { workspaceDeepLink } from "@/features/workspace/lib/deepLinks";
import {
  nextEventFrame,
  nextLapFrame,
  olderEvents,
  previousEventFrame,
  previousLapFrame,
  recentEvents,
  visibleEvents,
  visibleMarkers,
} from "@/features/pit-wall/lib/events";
import { useWorkspace } from "@/features/workspace/hooks/useWorkspace";

const regionTitleClass =
  "font-display text-[13px] font-bold uppercase tracking-[0.14em] text-fg";

function PitWallRaceView({
  pitWall,
  events,
  driverIntelligence,
  expertHrefs,
}: {
  pitWall: PitWallRace;
  events: PitWallEvents;
  driverIntelligence: DriverIntelligenceView;
  expertHrefs: { consensus: string; uncertainty: string } | null;
}) {
  const {
    raceId,
    totalFrames,
    timelineLoading,
    timelineError,
    frameIndex,
    frame,
    frameLoading,
    frameError,
    selectedDriverId,
    selectionRaceId,
    playbackStatus,
    speed,
    speeds,
    goFirst,
    goPrevious,
    goNext,
    goLast,
    seek,
    play,
    pause,
    setSpeed,
    selectDriver,
    clearDriver,
  } = pitWall;

  const busy = timelineLoading || frame === null;
  // Single playback announcer (V3.10H §34): while playing the message is
  // constant, so per-frame loading flicker cannot spam announcements.
  // Paused/at-rest loading still announces once. The visible timeline line
  // below mirrors this text without its own live region (one announcer).
  const statusMessage =
    playbackStatus === "playing"
      ? `Playing ${speed}× — factual frames only`
      : frameLoading
        ? "Loading frame…"
        : "";

  // Causal event layer: every selector below takes (index, frameIndex) and
  // can only ever observe events at or before T. nextEventFrame returns a
  // frame number alone — future identity cannot reach the chrome.
  const eventIndex = events.index;
  const visible = eventIndex ? visibleEvents(eventIndex, frameIndex) : [];
  const recent = eventIndex ? recentEvents(eventIndex, frameIndex) : [];
  const older = eventIndex ? olderEvents(eventIndex, frameIndex) : [];
  const markers = eventIndex ? visibleMarkers(eventIndex, frameIndex) : [];
  const prevEvent = eventIndex
    ? previousEventFrame(eventIndex, frameIndex)
    : null;
  const nextEvent = eventIndex ? nextEventFrame(eventIndex, frameIndex) : null;
  const prevLap = eventIndex ? previousLapFrame(eventIndex, frameIndex) : null;
  const nextLap = eventIndex ? nextLapFrame(eventIndex, frameIndex) : null;

  if (timelineLoading || (frame === null && !timelineError)) {
    return (
      <p
        aria-live="polite"
        className="mt-6 border border-ink-700 bg-ink-900 px-4 py-3 font-data text-[12px] text-fg-muted"
      >
        {timelineLoading ? "Loading replay timeline…" : "Loading frame…"}
      </p>
    );
  }

  return (
    <div>
      <p role="status" className="sr-only">
        {statusMessage}
      </p>

      {timelineError ? (
        <div
          role="alert"
          className="mt-4 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg"
        >
          {timelineError}
        </div>
      ) : null}

      {frameError ? (
        <div
          role="alert"
          className="mt-4 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg"
        >
          {frameError}
        </div>
      ) : null}

      {frame ? (
        <div className="mt-6 grid grid-cols-1 gap-x-8 gap-y-8 [grid-template-areas:'header'_'track'_'driver'_'order'_'notes'_'timeline'] xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)] xl:[grid-template-areas:'header_header'_'track_driver'_'order_notes'_'timeline_timeline']">
          <section aria-label="Race state" className="[grid-area:header]">
            <ContextBar frame={frame} />
          </section>

          <section
            aria-label="Track replay"
            className="min-w-0 [grid-area:track]"
          >
            <h2 className={regionTitleClass}>Track</h2>
            <div className="mt-3">
              <SpatialTrackPanel
                raceId={raceId}
                frameIndex={frameIndex}
                anchorStateTimeS={frame.frame.anchor_state_time_s}
                raceControl={frame.state.race_control}
                selectedDriverId={selectedDriverId}
                selectionRaceId={selectionRaceId}
                announcePending={playbackStatus !== "playing"}
              />
            </div>
          </section>

          <div className="min-w-0 [grid-area:driver]">
            <DriverPanel
              drivers={frame.state.drivers}
              selectedDriverId={selectedDriverId}
              onSelect={selectDriver}
              onClear={clearDriver}
              intelligence={driverIntelligence}
              expertHrefs={expertHrefs}
              telemetry={{
                raceId,
                tS: frame.frame.anchor_state_time_s,
                leaderLap: frame.leader_lap,
                raceComplete:
                  totalFrames > 0 && frameIndex >= totalFrames - 1,
              }}
            />
          </div>

          <section
            aria-label="Running order"
            className="min-w-0 [grid-area:order]"
          >
            <h2 className={regionTitleClass}>Running order</h2>
            <p className="mt-1 font-data text-[11px] text-fg-dim">
              {frame.state.roster_size} drivers · factual at this frame
            </p>
            <div className="mt-3 border-t border-ink-700">
              <StandingsTable frame={frame} />
            </div>
          </section>

          <div className="min-w-0 [grid-area:notes]">
            <section aria-label="Race control">
              <h2 className={regionTitleClass}>Race control</h2>
              <div className="mt-2">
                {events.status === "loading" ? (
                  <p
                    aria-live="polite"
                    className="font-data text-[12px] leading-5 text-fg-dim tabular-nums"
                  >
                    Loading events… {events.progress.loaded}/
                    {events.progress.total} frames
                  </p>
                ) : events.status === "unavailable" || !eventIndex ? (
                  <div>
                    <p className="font-data text-[12px] leading-5 text-fg-dim">
                      Event data unavailable for this race — not the same as
                      no events.
                    </p>
                    <button
                      type="button"
                      onClick={events.retry}
                      className="mt-2 h-9 border border-ink-700 px-3 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg focus-visible:outline-2 focus-visible:outline-focus"
                    >
                      Retry events
                    </button>
                  </div>
                ) : (
                  <EventFeed
                    visibleCount={visible.length}
                    recent={recent}
                    older={older}
                    onSeek={seek}
                    onSelectDriver={selectDriver}
                  />
                )}
              </div>
            </section>
            <div className="min-w-0">
              <DecisionExploration
                state={{ raceId, frameIndex, selectedDriverId }}
                frame={frame.frame}
              />
            </div>
          </div>

          <section
            aria-label="Replay timeline"
            className="min-w-0 border-t border-ink-700 pt-5 [grid-area:timeline]"
          >
            <h2 className={regionTitleClass}>Timeline</h2>
            <div className="mt-3">
              <PitWallTransport
                index={frameIndex}
                totalFrames={totalFrames}
                playing={playbackStatus === "playing"}
                speed={speed}
                speeds={speeds}
                busy={busy}
                onFirst={goFirst}
                onPrevious={goPrevious}
                onPlay={play}
                onPause={pause}
                onNext={goNext}
                onLast={goLast}
                onSpeed={setSpeed}
              />
            </div>
            <div className="mt-3">
              <TimelineScrubber
                index={frameIndex}
                totalFrames={totalFrames}
                disabled={busy}
                onCommit={seek}
              />
            </div>
            {markers.length > 0 ? (
              <div className="mt-1">
                <EventMarkers
                  markers={markers}
                  totalFrames={totalFrames}
                  onSeek={seek}
                />
              </div>
            ) : null}
            <div className="mt-3">
              <EventNav
                hasPreviousEvent={prevEvent !== null}
                hasNextEvent={nextEvent !== null}
                hasPreviousLap={prevLap !== null}
                hasNextLap={nextLap !== null}
                onPreviousEvent={() =>
                  prevEvent !== null && seek(prevEvent)
                }
                onNextEvent={() => nextEvent !== null && seek(nextEvent)}
                onPreviousLap={() => prevLap !== null && seek(prevLap)}
                onNextLap={() => nextLap !== null && seek(nextLap)}
              />
            </div>
            <div
              className="mt-1.5 min-h-4 font-data text-[11px] text-fg-dim"
            >
              {statusMessage}
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}

export function PitWallView() {
  const workspace = useWorkspace();
  const { races, racesLoading, racesError } = usePitWallRaces();
  const raceId = workspace.state?.raceId ?? null;
  const race = races.find((r) => r.race_id === raceId) ?? null;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <header>
        <p className="font-data text-[11px] font-semibold uppercase tracking-[0.2em] text-fg-muted">
          Race intelligence
        </p>
        <h1 className="mt-1 font-display text-2xl font-bold tracking-tight text-fg">
          Pit wall
        </h1>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-muted">
          {race
            ? raceLabel(race)
            : "Select a served historical race to enter the workspace."}
        </p>
      </header>

      {workspace.initError ? (
        <div
          role="alert"
          className="mt-4 border border-warn/40 bg-ink-900 px-4 py-3 text-[13px] text-fg"
        >
          {workspace.initError} Select a race below to start.
        </div>
      ) : null}

      {racesError ? (
        <div
          role="alert"
          className="mt-4 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg"
        >
          {racesError}
        </div>
      ) : null}

      <div className="mt-4 grid max-w-md grid-cols-1">
        <RaceSelector
          races={races}
          raceId={raceId}
          disabled={racesLoading}
          onSelect={workspace.setRace}
        />
      </div>

      {raceId === null ? (
        <div className="mt-6 border-t border-ink-700 pt-6">
          <p className="font-display text-[13px] font-bold uppercase tracking-[0.14em] text-fg">
            No race loaded
          </p>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-fg-muted">
            Choose a served 2018–2024 race above. The whole workspace — track,
            driver, order, timeline — follows one canonical race state.
          </p>
        </div>
      ) : (
        <PitWallRaceMount key={raceId} raceId={raceId} />
      )}
    </div>
  );
}

/**
 * Per-race mount boundary: usePitWallRace is called unconditionally here,
 * and the parent mounts this component with key={raceId}, so a race change
 * remounts with fresh data instead of reset logic — and no second race
 * authority exists.
 */
function PitWallRaceMount({ raceId }: { raceId: string }) {
  const pitWall = usePitWallRace(raceId);
  const eventLayer = usePitWallEvents(raceId, pitWall.totalFrames);
  // Intelligence anchor is the frame's own exact state identity
  // (anchor lap + anchor time); the frozen bundle is evidence about T.
  const anchor = pitWall.frame
    ? {
        raceId,
        anchorLapNumber: pitWall.frame.frame.anchor_lap_number,
        anchorStateTimeS: pitWall.frame.frame.anchor_state_time_s,
      }
    : null;
  const driverIntelligence = useDriverIntelligence(anchor);
  const expertHrefs =
    pitWall.frame && pitWall.selectedDriverId
      ? {
          consensus: workspaceDeepLink("/consensus", {
            raceId,
            frameIndex: pitWall.frameIndex,
            selectedDriverId: pitWall.selectedDriverId,
          }),
          uncertainty: workspaceDeepLink("/uncertainty", {
            raceId,
            frameIndex: pitWall.frameIndex,
            selectedDriverId: pitWall.selectedDriverId,
          }),
        }
      : null;
  return (
    <PitWallRaceView
      pitWall={pitWall}
      events={eventLayer}
      driverIntelligence={driverIntelligence}
      expertHrefs={expertHrefs}
    />
  );
}
