// Timeline scrubber (Phase-5 R5; UI3 primary replay control).
//
// Navigates by frame_index over DISCRETE reconstructed states. Pointer drags
// preview locally and fetch on release; keyboard steps commit immediately
// (single requests). Scrubbing never fires hundreds of frame requests and never
// invents frame state — the slider value is an exact frame ordinal.

"use client";

import { useState } from "react";
import { displayFrame } from "@/features/replay/lib/replayMachine";

export function TimelineScrubber({
  index,
  totalFrames,
  disabled,
  onCommit,
}: {
  index: number;
  totalFrames: number;
  disabled: boolean;
  onCommit: (index: number) => void;
}) {
  // drag holds the preview value while the pointer is down; null means the
  // slider tracks the committed frame. No effect needed: releasing the pointer
  // commits and clears, keyboard steps commit immediately.
  const [drag, setDrag] = useState<number | null>(null);
  const shown = drag ?? index;

  if (totalFrames <= 0) return null;
  const max = totalFrames - 1;

  const commit = (value: number) => {
    setDrag(null);
    if (value !== index) onCommit(value);
  };

  return (
    <div className="w-full">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="flex items-baseline gap-2">
          <span className="font-ui text-[10px] uppercase tracking-[0.14em] text-fg-dim">
            Replay position
          </span>
          <span className="font-data text-[13px] text-fg tabular-nums">
            FRAME {displayFrame(shown)} / {totalFrames}
          </span>
          <span className="font-data text-[11px] text-fg-dim tabular-nums">
            index {shown}
          </span>
        </div>
        <span className="hidden font-data text-[10px] uppercase tracking-[0.1em] text-fg-dim sm:inline">
          discrete reconstructed states
        </span>
      </div>

      <div className="mt-1.5 flex items-center gap-2">
        <span className="font-data text-[10px] text-fg-dim tabular-nums">0</span>
        <input
          type="range"
          aria-label="Replay timeline scrubber"
          aria-valuetext={`frame ${displayFrame(shown)} of ${totalFrames}`}
          min={0}
          max={max}
          step={1}
          value={shown}
          disabled={disabled}
          className="h-6 w-full min-w-0 cursor-pointer appearance-none bg-transparent disabled:cursor-not-allowed disabled:opacity-50 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-2 [&::-moz-range-thumb]:rounded-none [&::-moz-range-thumb]:border-0 [&::-moz-range-thumb]:bg-signal [&::-moz-range-track]:h-1.5 [&::-moz-range-track]:bg-ink-850 [&::-webkit-slider-runnable-track]:h-1.5 [&::-webkit-slider-runnable-track]:bg-ink-850 [&::-webkit-slider-thumb]:mt-[-5px] [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-2 [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-none [&::-webkit-slider-thumb]:bg-signal"
          onPointerDown={() => {
            setDrag(shown);
          }}
          onChange={(event) => {
            const value = Number(event.target.value);
            if (drag !== null) {
              setDrag(value);
            } else {
              commit(value);
            }
          }}
          onPointerUp={(event) =>
            commit(Number((event.target as HTMLInputElement).value))
          }
          onPointerCancel={() => {
            setDrag(null);
          }}
        />
        <span className="font-data text-[10px] text-fg-dim tabular-nums">
          {max}
        </span>
      </div>

      <p className="mt-1 font-data text-[10px] leading-4 text-fg-dim">
        drag to preview, release to load · keyboard arrows step one frame · no
        interpolation between frames
      </p>
    </div>
  );
}
