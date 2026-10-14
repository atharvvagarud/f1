// Pit Wall transport (V3.10C).
//
// First / previous / play-pause / next / last over exact frames plus speed
// selection. Step bounds reuse replayMachine helpers; every move delegates
// to workspace-validated seeks owned by usePitWall. No lap-jump input in C:
// lap/event jumps arrive with V3.10D event navigation. Touch targets are
// h-11 (44px) per the V3.10A responsive contract.

"use client";

import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import {
  canGoNext,
  canGoPrevious,
  type PlaybackSpeed,
} from "@/features/replay/lib/replayMachine";

const stepButtonClass =
  "inline-flex h-11 w-11 items-center justify-center border border-ink-700 bg-ink-950 text-fg-muted " +
  "transition-colors hover:border-ink-600 hover:text-fg " +
  "disabled:cursor-not-allowed disabled:border-dashed disabled:border-ink-700 disabled:text-fg-dim " +
  "focus-visible:outline-2 focus-visible:outline-focus";

const playButtonClass =
  "inline-flex h-11 min-w-11 items-center justify-center gap-2 border border-ink-700 bg-ink-950 px-3 text-fg-muted " +
  "transition-colors hover:border-ink-600 hover:text-fg " +
  "disabled:cursor-not-allowed disabled:border-dashed disabled:text-fg-dim " +
  "focus-visible:outline-2 focus-visible:outline-focus";

export function PitWallTransport({
  index,
  totalFrames,
  playing,
  speed,
  speeds,
  busy,
  onFirst,
  onPrevious,
  onPlay,
  onPause,
  onNext,
  onLast,
  onSpeed,
}: {
  index: number;
  totalFrames: number;
  playing: boolean;
  speed: PlaybackSpeed;
  speeds: readonly PlaybackSpeed[];
  busy: boolean;
  onFirst: () => void;
  onPrevious: () => void;
  onPlay: () => void;
  onPause: () => void;
  onNext: () => void;
  onLast: () => void;
  onSpeed: (speed: PlaybackSpeed) => void;
}) {
  const prev = canGoPrevious(index) && !busy;
  const next = canGoNext(index, totalFrames) && !busy;
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
      <div
        className="flex flex-wrap items-center gap-1.5"
        role="group"
        aria-label="Pit wall transport controls"
      >
        <button
          type="button"
          aria-label="First frame"
          disabled={!prev}
          onClick={onFirst}
          className={stepButtonClass}
        >
          <SkipBack size={16} aria-hidden="true" />
        </button>
        <button
          type="button"
          aria-label="Previous frame"
          disabled={!prev}
          onClick={onPrevious}
          className={stepButtonClass}
        >
          <span aria-hidden="true">‹</span>
        </button>
        {playing ? (
          <button
            type="button"
            aria-label="Pause replay"
            onClick={onPause}
            className={playButtonClass}
          >
            <Pause size={16} aria-hidden="true" />
          </button>
        ) : (
          <button
            type="button"
            aria-label="Play replay"
            disabled={!next}
            onClick={onPlay}
            className={playButtonClass}
          >
            <Play size={16} aria-hidden="true" />
          </button>
        )}
        <button
          type="button"
          aria-label="Next frame"
          disabled={!next}
          onClick={onNext}
          className={stepButtonClass}
        >
          <span aria-hidden="true">›</span>
        </button>
        <button
          type="button"
          aria-label="Last frame"
          disabled={!next}
          onClick={onLast}
          className={stepButtonClass}
        >
          <SkipForward size={16} aria-hidden="true" />
        </button>
      </div>
      <fieldset className="flex flex-wrap items-center gap-1.5">
        <legend className="sr-only">Playback speed</legend>
        {speeds.map((option) => (
          <label
            key={option}
            className={`inline-flex h-11 cursor-pointer items-center border px-3 font-data text-[12px] tabular-nums transition-colors has-focus-visible:outline-2 has-focus-visible:outline-focus ${
              option === speed
                ? "border-signal font-semibold text-fg"
                : "border-ink-700 text-fg-muted hover:border-ink-600 hover:text-fg"
            }`}
          >
            <input
              type="radio"
              name="pitwall-speed"
              value={option}
              checked={option === speed}
              onChange={() => onSpeed(option)}
              className="sr-only"
            />
            {option}×
          </label>
        ))}
      </fieldset>
    </div>
  );
}
