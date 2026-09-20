// Transport + navigation controls (Phase-5 R5).
//
// FIRST / PREVIOUS / play-pause / NEXT / LAST with backend bounds (no wrap,
// impossible actions disabled), speed selection, and jump-to-leader-lap.
// Lap means leader progress; anchor laps are never treated as race laps.

"use client";

import { useState } from "react";
import {
  canGoNext,
  canGoPrevious,
  type PlaybackSpeed,
} from "@/features/replay/lib/replayMachine";
import type { JumpState } from "@/features/replay/hooks/useReplay";

const buttonClass =
  "rounded-md border border-white/10 bg-slate-900 px-3 py-2 text-sm font-semibold text-slate-100 " +
  "hover:border-white/25 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-40 " +
  "focus-visible:outline-2 focus-visible:outline-red-500";

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
      <div
        className="flex flex-wrap items-center gap-2"
        role="group"
        aria-label="Replay transport controls"
      >
        <button type="button" aria-label="First frame" className={buttonClass} disabled={!prev || busy} onClick={onFirst}>
          |◀
        </button>
        <button type="button" aria-label="Previous frame" className={buttonClass} disabled={!prev || busy} onClick={onPrevious}>
          ◀
        </button>
        {playing ? (
          <button type="button" aria-label="Pause replay" className={`${buttonClass} min-w-20 border-red-500/50 text-red-300`} onClick={onPause}>
            ❚❚ Pause
          </button>
        ) : (
          <button type="button" aria-label="Play replay" className={`${buttonClass} min-w-20`} disabled={!next || busy} onClick={onPlay}>
            ▶ Play
          </button>
        )}
        <button type="button" aria-label="Next frame" className={buttonClass} disabled={!next || busy} onClick={onNext}>
          ▶
        </button>
        <button type="button" aria-label="Last frame" className={buttonClass} disabled={!next || busy} onClick={onLast}>
          ▶|
        </button>
        <label className="ml-1 flex items-center gap-2 text-xs text-slate-400">
          Speed
          <select
            aria-label="Playback speed"
            className="rounded-md border border-white/10 bg-slate-900 px-2 py-2 text-sm text-slate-100 focus-visible:outline-2 focus-visible:outline-red-500"
            value={speed}
            onChange={(event) => onSpeed(Number(event.target.value) as PlaybackSpeed)}
          >
            {speeds.map((option) => (
              <option key={option} value={option}>
                {option}x
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-xs text-slate-400">
          Leader lap
          <input
            type="number"
            min={1}
            step={1}
            inputMode="numeric"
            aria-label="Jump to leader lap"
            placeholder="e.g. 20"
            className="w-24 rounded-md border border-white/10 bg-slate-900 px-2 py-2 font-mono text-sm tabular-nums text-slate-100 focus-visible:outline-2 focus-visible:outline-red-500"
            value={lapInput}
            disabled={busy || searching || totalFrames === 0}
            onChange={(event) => setLapInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submitLap();
            }}
          />
        </label>
        <button
          type="button"
          aria-label="Jump to leader lap"
          className={buttonClass}
          disabled={busy || searching || totalFrames === 0}
          onClick={submitLap}
        >
          {searching ? "Searching…" : "Go to lap"}
        </button>
        {jump.kind === "failed" && (
          <span role="alert" className="text-xs text-amber-300">
            {jump.message}
          </span>
        )}
      </div>
    </div>
  );
}
