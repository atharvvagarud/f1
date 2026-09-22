// Transport + navigation controls (Phase-5 R5; UI3 engineering transport).
//
// FIRST / PREVIOUS / play-pause / NEXT / LAST with backend bounds (no wrap,
// impossible actions disabled), speed selection, and jump-to-leader-lap. Lap
// means leader progress; anchor laps are never treated as race laps. Compact,
// square, keyboard-reachable, with distinct (non-opacity-only) disabled state.

"use client";

import { useState } from "react";
import {
  ChevronLeft,
  ChevronRight,
  Pause,
  Play,
  SkipBack,
  SkipForward,
} from "lucide-react";
import {
  canGoNext,
  canGoPrevious,
  type PlaybackSpeed,
} from "@/features/replay/lib/replayMachine";
import type { JumpState } from "@/features/replay/hooks/useReplay";

const iconButtonClass =
  "inline-flex h-9 w-9 items-center justify-center border border-ink-700 bg-ink-950 text-fg-muted " +
  "transition-colors hover:border-ink-600 hover:text-fg " +
  "disabled:cursor-not-allowed disabled:border-dashed disabled:border-ink-700 disabled:text-fg-dim " +
  "focus-visible:outline-2 focus-visible:outline-focus";

const labelClass =
  "font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim";

const lapInputClass =
  "h-9 w-24 border border-ink-700 bg-ink-950 px-2.5 font-data text-[13px] text-fg tabular-nums transition-colors focus-visible:border-ink-600 disabled:border-dashed disabled:text-fg-dim";

const actionButtonClass =
  "h-9 border border-ink-700 bg-ink-950 px-3 font-ui text-[11px] font-semibold uppercase tracking-[0.14em] text-fg-muted " +
  "transition-colors hover:border-ink-600 hover:text-fg " +
  "disabled:cursor-not-allowed disabled:border-dashed disabled:text-fg-dim " +
  "focus-visible:outline-2 focus-visible:outline-focus";

export function PlaybackControls({
  index,
  totalFrames,
  playing,
  speed,
  speeds,
  jump,
  busy,
  onFirst,
  onPrevious,
  onPlay,
  onPause,
  onNext,
  onLast,
  onSpeed,
  onJumpToLap,
}: {
  index: number;
  totalFrames: number;
  playing: boolean;
  speed: PlaybackSpeed;
  speeds: readonly PlaybackSpeed[];
  jump: JumpState;
  busy: boolean;
  onFirst: () => void;
  onPrevious: () => void;
  onPlay: () => void;
  onPause: () => void;
  onNext: () => void;
  onLast: () => void;
  onSpeed: (speed: PlaybackSpeed) => void;
  onJumpToLap: (lap: number) => void;
}) {
  const [lapInput, setLapInput] = useState("");
  const prev = canGoPrevious(index);
  const next = canGoNext(index, totalFrames);
  const searching = jump.kind === "searching";

  const submitLap = () => {
    const lap = Number(lapInput);
    if (Number.isInteger(lap) && lap >= 1) onJumpToLap(lap);
    else onJumpToLap(NaN);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div
          className="flex flex-wrap items-center gap-1.5"
          role="group"
          aria-label="Replay transport controls"
        >
          <button
            type="button"
            aria-label="First frame"
            className={iconButtonClass}
            disabled={!prev || busy}
            onClick={onFirst}
          >
            <SkipBack className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label="Previous frame"
            className={iconButtonClass}
            disabled={!prev || busy}
            onClick={onPrevious}
          >
            <ChevronLeft className="h-4 w-4" aria-hidden="true" />
          </button>

          {playing ? (
            <button
              type="button"
              aria-label="Pause replay"
              className="inline-flex h-9 min-w-[6.5rem] items-center justify-center gap-1.5 border border-ink-600 bg-ink-600 px-3 font-ui text-[11px] font-semibold uppercase tracking-[0.14em] text-fg transition-colors hover:bg-ink-700 focus-visible:outline-2 focus-visible:outline-focus"
              onClick={onPause}
            >
              <Pause className="h-4 w-4" aria-hidden="true" />
              Pause
            </button>
          ) : (
            <button
              type="button"
              aria-label="Play replay"
              className="inline-flex h-9 min-w-[6.5rem] items-center justify-center gap-1.5 border border-signal bg-signal px-3 font-ui text-[11px] font-semibold uppercase tracking-[0.14em] text-focus transition-colors hover:bg-signal/90 disabled:cursor-not-allowed disabled:border-dashed disabled:border-ink-700 disabled:bg-ink-950 disabled:text-fg-dim focus-visible:outline-2 focus-visible:outline-focus"
              disabled={!next || busy}
              onClick={onPlay}
            >
              <Play className="h-4 w-4" aria-hidden="true" />
              Play
            </button>
          )}

          <button
            type="button"
            aria-label="Next frame"
            className={iconButtonClass}
            disabled={!next || busy}
            onClick={onNext}
          >
            <ChevronRight className="h-4 w-4" aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label="Last frame"
            className={iconButtonClass}
            disabled={!next || busy}
            onClick={onLast}
          >
            <SkipForward className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        <fieldset className="m-0 flex min-w-0 items-center gap-2 border-0 p-0">
          <legend className={labelClass}>Speed</legend>
          <div className="inline-flex h-9 border border-ink-700">
            {speeds.map((option, optionIndex) => (
              <label
                key={option}
                className={`relative inline-flex cursor-pointer ${
                  optionIndex > 0 ? "border-l border-ink-700" : ""
                }`}
              >
                <input
                  type="radio"
                  name="replay-speed"
                  value={option}
                  checked={speed === option}
                  disabled={busy}
                  onChange={() =>
                    onSpeed(Number(option) as PlaybackSpeed)
                  }
                  className="peer sr-only"
                />
                <span className="flex items-center px-2.5 font-data text-[11px] tabular-nums text-fg-muted peer-checked:bg-ink-600 peer-checked:text-fg peer-focus-visible:outline-2 peer-focus-visible:-outline-offset-2 peer-focus-visible:outline-focus peer-disabled:text-fg-dim">
                  {option}x
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <div className="flex flex-wrap items-center gap-2">
          <label htmlFor="replay-lap-jump" className={labelClass}>
            Leader lap
          </label>
          <input
            id="replay-lap-jump"
            type="number"
            min={1}
            step={1}
            inputMode="numeric"
            placeholder="e.g. 20"
            className={lapInputClass}
            value={lapInput}
            disabled={busy || searching || totalFrames === 0}
            onChange={(event) => setLapInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submitLap();
            }}
          />
          <button
            type="button"
            className={actionButtonClass}
            disabled={busy || searching || totalFrames === 0}
            onClick={submitLap}
          >
            {searching ? "Searching…" : "Go to lap"}
          </button>
          {jump.kind === "failed" && (
            <span role="alert" className="font-data text-[11px] text-warn">
              {jump.message}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
