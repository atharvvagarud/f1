// Replay product view (Phase-5 R5).
//
// Timing-tower layout: header + race selector, factual context bar,
// transport + scrubber, running order beside the model panel. Prediction
// failure never destroys factual replay; frame transitions keep the last
// good frame visible with a lightweight loading cue.

"use client";

import Link from "next/link";
import { useReplay } from "@/features/replay/hooks/useReplay";
import { RaceSelector } from "@/features/replay/components/RaceSelector";
import { TimelineScrubber } from "@/features/replay/components/TimelineScrubber";
import { PlaybackControls } from "@/features/replay/components/PlaybackControls";
import { StandingsTable } from "@/features/replay/components/StandingsTable";
import { ContextBar } from "@/features/replay/components/ContextBar";
import { PredictionPanel } from "@/features/replay/components/PredictionPanel";
import { ProbabilityTimelineChart } from "@/features/replay/components/ProbabilityTimelineChart";

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

  return (
    <main className="min-h-screen bg-slate-950 text-white">
      <div className="mx-auto flex max-w-7xl flex-col gap-5 px-4 py-6 sm:px-6">
        <header className="flex flex-wrap items-end justify-between gap-3 border-b border-white/10 pb-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-red-500">
              Historical replay
            </p>
            <h1 className="font-heading mt-1 text-2xl font-bold tracking-tight">
              Race replay
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-400">
              Step through a served 2018–2024 race frame by frame. Every frame
              is an exact historical observation; winner estimates appear only
              at model checkpoints.
            </p>
          </div>
          <div className="flex gap-2">
            <Link
              href="/"
              className="rounded-md border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-white/25 focus-visible:outline-2 focus-visible:outline-red-500"
            >
              ← Prediction home
            </Link>
            <Link
              href="/simulator"
              className="rounded-md border border-white/10 bg-slate-900 px-3 py-2 text-sm text-slate-200 hover:border-white/25 focus-visible:outline-2 focus-visible:outline-red-500"
            >
              Simulator →
            </Link>
          </div>
        </header>

        {racesError && (
          <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {racesError}
          </div>
        )}

        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="md:col-span-1">
            <RaceSelector
              races={races}
              raceId={raceId}
              disabled={racesLoading}
              onSelect={selectRace}
            />
          </div>
          <div className="md:col-span-2">
            {frame ? (
              <ContextBar frame={frame} />
            ) : (
              <p className="text-sm text-slate-500">
                {timelineLoading || racesLoading
                  ? "Loading replay…"
                  : "Select a race to enter replay."}
              </p>
            )}
          </div>
        </div>

        {timelineError && (
          <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {timelineError}{" "}
            <button
              type="button"
              className="underline"
              onClick={() => raceId && selectRace(raceId)}
            >
              Retry
            </button>
          </div>
        )}

        {totalFrames > 0 && (
          <div className="flex flex-col gap-4 rounded-lg border border-white/10 bg-slate-900/40 p-4">
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
            <TimelineScrubber
              index={frameIndex}
              totalFrames={totalFrames}
              disabled={busy}
              onCommit={navigation.seek}
            />
            <div aria-live="polite" className="min-h-4 text-xs text-slate-500">
              {frameLoading && "Loading frame…"}
              {playbackStatus === "playing" && !frameLoading && `Playing ${speed}x — factual frames only`}
            </div>
          </div>
        )}

        {frameError && (
          <div role="alert" className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-200">
            {frameError}
          </div>
        )}

        {raceId && !timelineLoading && totalFrames > 0 && (
          <div className="rounded-lg border border-white/10 bg-slate-900/40 p-4">
            <ProbabilityTimelineChart
              key={raceId}
              view={probabilityTimeline}
              frameIndex={frameIndex}
            />
          </div>
        )}

        {frame && (
          <div className="grid grid-cols-1 gap-5 xl:grid-cols-5">
            <div className="rounded-lg border border-white/10 bg-slate-900/40 p-4 xl:col-span-3">
              <h2 className="font-heading mb-2 text-sm font-bold uppercase tracking-[0.16em] text-slate-300">
                Running order
              </h2>
              <StandingsTable frame={frame} />
            </div>
            <div className="rounded-lg border border-white/10 bg-slate-900/40 p-4 xl:col-span-2">
              <PredictionPanel
                prediction={prediction}
                isCheckpoint={frame.is_prediction_checkpoint}
                checkpointReasons={frame.checkpoint_reasons}
              />
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
