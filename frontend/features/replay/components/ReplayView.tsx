// Replay product view (Phase-5 R5; UI3 race-analysis workstation).
//
// Information architecture: race context (selector + factual ContextBar) →
// replay transport → timeline / current T → current running order beside model
// intelligence (winner snapshot + probability evolution). Factual replay state
// is authoritative in useReplay; this view is composition only. Prediction
// failure never destroys factual replay; frame transitions keep the last good
// frame visible with a lightweight loading cue.

"use client";

import { useReplay } from "@/features/replay/hooks/useReplay";
import { RaceSelector } from "@/features/replay/components/RaceSelector";
import { TimelineScrubber } from "@/features/replay/components/TimelineScrubber";
import { PlaybackControls } from "@/features/replay/components/PlaybackControls";
import { StandingsTable } from "@/features/replay/components/StandingsTable";
import { ContextBar } from "@/features/replay/components/ContextBar";
import { PredictionPanel } from "@/features/replay/components/PredictionPanel";
import { ProbabilityTimelineChart } from "@/features/replay/components/ProbabilityTimelineChart";
import { Panel, PanelHeader } from "@/components/ui/Panel";

export function ReplayView() {
  const replay = useReplay();
  const {
    races,
    racesLoading,
    racesError,
    raceId,
    totalFrames,
    timelineLoading,
    timelineError,
    frameIndex,
    frame,
    frameLoading,
    frameError,
    prediction,
    probabilityTimeline,
    playbackStatus,
    speed,
    speeds,
    jump,
    navigation,
    play,
    pause,
    setPlaybackSpeed,
    jumpToLap,
    selectRace,
  } = replay;

  const busy = timelineLoading || frame === null;
  const loadingCue = racesLoading
    ? "Loading served races…"
    : timelineLoading
      ? "Loading replay timeline…"
      : frame === null
        ? "Loading frame…"
        : null;

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
      <header className="border-b border-ink-700 pb-4">
        <h1 className="font-display text-2xl font-bold tracking-tight text-fg">
          Historical race replay
        </h1>
        <p className="mt-1 max-w-3xl text-sm leading-6 text-fg-muted">
          Step through a served 2018–2024 race frame by frame. Every frame is an
          exact reconstructed historical observation — no interpolation between
          frames; winner estimates appear only at model checkpoints.
        </p>
      </header>

      {racesError ? (
        <div
          role="alert"
          className="mt-4 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg"
        >
          {racesError}
        </div>
      ) : null}

      <section
        aria-label="Replay controls"
        className="mt-4 border border-ink-700 bg-ink-900"
      >
        <div className="grid grid-cols-1 gap-x-6 gap-y-4 border-b border-ink-700 px-4 py-3 lg:grid-cols-[minmax(15rem,1fr)_minmax(0,2.6fr)]">
          <RaceSelector
            races={races}
            raceId={raceId}
            disabled={racesLoading}
            onSelect={selectRace}
          />
          <div className="min-w-0">
            {frame ? (
              <ContextBar frame={frame} />
            ) : (
              <p className="font-data text-[11px] leading-5 text-fg-dim">
                {racesLoading || timelineLoading
                  ? "Loading race state…"
                  : "Select a race to enter replay."}
              </p>
            )}
          </div>
        </div>

        {totalFrames > 0 ? (
          <>
            <div className="border-b border-ink-700 px-4 py-3">
              <PlaybackControls
                index={frameIndex}
                totalFrames={totalFrames}
                playing={playbackStatus === "playing"}
                speed={speed}
                speeds={speeds}
                jump={jump}
                busy={busy}
                onFirst={navigation.goFirst}
                onPrevious={navigation.goPrevious}
                onPlay={play}
                onPause={pause}
                onNext={navigation.goNext}
                onLast={navigation.goLast}
                onSpeed={setPlaybackSpeed}
                onJumpToLap={jumpToLap}
              />
            </div>
            <div className="px-4 py-3">
              <TimelineScrubber
                index={frameIndex}
                totalFrames={totalFrames}
                disabled={busy}
                onCommit={navigation.seek}
              />
              <div
                aria-live="polite"
                className="mt-1.5 min-h-4 font-data text-[11px] text-fg-dim"
              >
                {frameLoading && "Loading frame…"}
                {playbackStatus === "playing" &&
                  !frameLoading &&
                  `Playing ${speed}× — factual frames only`}
              </div>
            </div>
          </>
        ) : null}
      </section>

      {timelineError ? (
        <div
          role="alert"
          className="mt-4 flex flex-wrap items-center justify-between gap-3 border border-danger/40 bg-ink-900 px-4 py-3 text-[13px] text-fg"
        >
          <span>{timelineError}</span>
          <button
            type="button"
            className="h-8 border border-ink-700 px-3 font-ui text-[11px] uppercase tracking-[0.14em] text-fg-muted transition-colors hover:border-ink-600 hover:text-fg"
            onClick={() => raceId && selectRace(raceId)}
          >
            Retry
          </button>
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
        <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <Panel className="overflow-hidden">
            <PanelHeader
              title="Running order"
              meta={`${frame.state.roster_size} drivers`}
            />
            <StandingsTable frame={frame} />
          </Panel>

          <div className="flex min-w-0 flex-col gap-4">
            <PredictionPanel
              prediction={prediction}
              isCheckpoint={frame.is_prediction_checkpoint}
              checkpointReasons={frame.checkpoint_reasons}
            />
            {raceId && !timelineLoading && totalFrames > 0 ? (
              <ProbabilityTimelineChart
                key={raceId}
                view={probabilityTimeline}
                frameIndex={frameIndex}
              />
            ) : null}
          </div>
        </div>
      ) : !timelineLoading && !racesLoading && !racesError && !timelineError ? (
        <div className="mt-5 border border-ink-700 bg-ink-900 px-4 py-6">
          <p className="font-display text-[13px] font-bold uppercase tracking-[0.14em] text-fg">
            No race loaded
          </p>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-fg-muted">
            Select a served historical race above to step through its exact
            reconstructed frames.
          </p>
        </div>
      ) : loadingCue && !racesError && !timelineError ? (
        <p
          aria-live="polite"
          className="mt-5 border border-ink-700 bg-ink-900 px-4 py-3 font-data text-[12px] text-fg-muted"
        >
          {loadingCue}
        </p>
      ) : null}
    </div>
  );
}
